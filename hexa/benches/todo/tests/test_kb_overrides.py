"""Tests for the KB datastore layer: tracked overrides, cost surfacing, unit upsert."""

import json

from hexa.benches.todo.kb import builder
from hexa.benches.todo.kb.normalizer import apply_overrides, normalize, normalize_new
from hexa.benches.todo.kb.render import section_cost


def _minimal_cr(**meta_extra):
    meta = {
        "scoring_model": "indicator_fibonacci_v2",
        "target_path": "livrables/x",
        "cost": {
            "cost_usd": 1.35,
            "total_tokens": 165000,
            "model_key": "claude-sonnet",
            "priced": True,
        },
    }
    meta.update(meta_extra)
    return {
        "meta": meta,
        "summary": {
            "percentage_net": 82.0,
            "bucket_scores": {},
            "cost_efficiency_pct_per_usd": 60.7,
        },
        "artifacts": {
            "traceability": {"data": {"meta": {"model": "claude-sonnet-5", "effort": "low"}}}
        },
        "stats": {},
        "phases": [],
        "indicators": [],
    }


def test_apply_overrides_merges_and_records():
    entry = {"id": "cr_x", "model": "raw-model", "effort": "low"}
    out = apply_overrides(entry, {"cr_x": {"model": "corrected", "effort": "high"}})
    assert out["model"] == "corrected"
    assert out["effort"] == "high"
    assert out["_overrides_applied"] == ["effort", "model"]


def test_apply_overrides_noop_without_patch():
    entry = {"id": "cr_y", "model": "raw"}
    out = apply_overrides(entry, {"cr_x": {"model": "z"}})
    assert out["model"] == "raw"
    assert "_overrides_applied" not in out


def test_overrides_add_corrections_section():
    entry = normalize(_minimal_cr(), "cr_zzz.json", None)  # fully normalized (has sections)
    out = apply_overrides(entry, {"cr_zzz": {"model": "corrected-model"}})
    assert out["model"] == "corrected-model"
    assert "Corrections manuelles" in [s["title"] for s in out["sections"]]


def test_normalize_new_surfaces_cost():
    entry = normalize_new(_minimal_cr(), "cr_test.json", None)
    assert entry["cost"]["usd"] == 1.35
    assert entry["cost"]["tokens"] == 165000
    assert entry["cost"]["model_key"] == "claude-sonnet"
    assert entry["cost"]["efficiency"] == 60.7


def test_section_cost_present_and_absent():
    section = section_cost(
        {
            "cost": {
                "usd": 1.35,
                "tokens": 100,
                "efficiency": 60.0,
                "model_key": "gpt-5",
                "priced": True,
            }
        }
    )
    assert section["title"] == "Coût estimé"
    assert section_cost({"cost": None}) is None
    assert section_cost({}) is None


def test_upsert_entry_upserts_by_id(tmp_path, monkeypatch):
    data_path = tmp_path / "data.json"
    monkeypatch.setattr(builder, "DATA_PATH", data_path)

    cr_file = tmp_path / "cr_20990101_0000_test_1.0_20990101_000000.json"
    cr_file.write_text(json.dumps(_minimal_cr()), encoding="utf-8")

    entries = builder.upsert_entry(str(cr_file))
    assert len(entries) == 1
    assert entries[0]["id"] == cr_file.stem
    assert entries[0]["cost"]["usd"] == 1.35

    # Re-adding the same cr replaces the entry (upsert by id, no duplicate).
    entries = builder.upsert_entry(str(cr_file))
    assert len(entries) == 1


def test_full_rebuild_refuses_to_drop_published_entries(tmp_path, monkeypatch):
    import pytest

    data_path = tmp_path / "data.json"
    published = [{"id": "cr_published_elsewhere"}]
    data_path.write_text(json.dumps(published), encoding="utf-8")
    monkeypatch.setattr(builder, "DATA_PATH", data_path)
    monkeypatch.setattr(builder, "load_all", lambda: [{"id": "cr_local_only"}])

    with pytest.raises(builder.KnowledgeBaseShrinkError):
        builder.build_knowledge_base()
    assert json.loads(data_path.read_text(encoding="utf-8")) == published  # untouched

    entries = builder.build_knowledge_base(allow_drop=True)
    assert [e["id"] for e in entries] == ["cr_local_only"]


def test_upsert_also_writes_embedded_js_for_file_protocol(tmp_path, monkeypatch):
    data_path = tmp_path / "data.json"
    monkeypatch.setattr(builder, "DATA_PATH", data_path)
    cr_file = tmp_path / "cr_20990101_0000_test_1.0_20990101_000000.json"
    cr_file.write_text(json.dumps(_minimal_cr()), encoding="utf-8")

    builder.upsert_entry(str(cr_file))

    js = (tmp_path / "data.js").read_text(encoding="utf-8")
    prefix = "window.__HEXA_KB__ = "
    assert js.startswith(prefix) and js.rstrip().endswith(";")
    payload = json.loads(js[len(prefix) :].rstrip().rstrip(";"))
    assert payload["entries"] == json.loads(data_path.read_text(encoding="utf-8"))
    assert "</script" not in js.lower()
