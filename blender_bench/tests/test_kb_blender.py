"""KB Blender : normalisation d'un rapport, magasin séparé, visuels jamais supprimés."""

import json

import pytest

from kb.builder import KbStore, KnowledgeBaseShrinkError, build_knowledge_base, upsert_entry
from kb_blender import builder as kb_builder
from kb_blender.normalizer import normalize_blender


def _report(target="livrables_blender/20260923_1000_claude-fable-5-1_high"):
    return {
        "meta": {
            "target_path": target, "challenge": "dreadhive_drone_mk1", "challenge_label": "Drone",
            "audit_started_at": "2026-09-23T10:00:00", "scoring_model": "blender_indicator_fibonacci_b1",
            "cost": {"cost_usd": 1.2, "total_tokens": 1000},
        },
        "summary": {
            "percentage_net": 72.5, "score_caps": [],
            "bucket_scores": {"visual": {"normalized_score": 12, "weight": 24, "label": "Fidélité visuelle"}},
        },
        "phases": [{"number": 5, "label": "Fidélité visuelle", "code": "5", "steps": [{"label": "S", "indicators": [
            {"code": "5-1-1", "name": "Silhouette FACE", "status": "PARTIEL", "kind": "scored",
             "polarity": "positive", "score": 6.5, "max_score": 13, "measured_value": 0.45, "remarks": "IoU"}]}]}],
        "artifacts": {
            "traceability": {"data": {"meta": {"model": "claude-fable-5-1", "effort": "high"}}},
            "media": [{"kind": "image", "file": "view_front.jpg", "label": "Rendu FACE"}],
        },
        "stats": {"triangles": 42000, "iou": {"front": 0.45}},
    }  # fmt: skip


def test_normalize_blender_entry():
    entry = normalize_blender(_report(), "cr_audits_blender/cr_x_20260923_100000.json", None)
    assert entry["id"] == "cr_x_20260923_100000"
    assert entry["model"] == "claude-fable-5-1" and entry["admission_status"] == "ADMIS"
    assert entry["bucket_scores"]["visual"]["short"] == "Visuel"
    assert entry["media"][0]["src"] == "challenges/dreadhive_drone_mk1/concept.jpg"  # l'attendu
    assert entry["media"][1]["src"] == "media/cr_x_20260923_100000/view_front.jpg"
    titles = [section["title"] for section in entry["sections"]]
    assert "Fidélité visuelle" in titles and "Score détaillé" in titles


def test_blender_store_upsert_publishes_media_and_guards_drops(tmp_path, monkeypatch):
    cr_dir = tmp_path / "cr_audits_blender"
    (cr_dir / "cr_x_20260923_100000_media").mkdir(parents=True)
    (cr_dir / "cr_x_20260923_100000_media" / "view_front.jpg").write_bytes(b"jpg")
    cr = cr_dir / "cr_x_20260923_100000.json"
    cr.write_text(json.dumps(_report()), encoding="utf-8")
    kb = tmp_path / "kb"
    monkeypatch.setattr(kb_builder, "MEDIA_DIR", kb / "media")
    monkeypatch.setattr(kb_builder, "SCAN_DIRS", [cr_dir])

    def load_one(path):
        return normalize_blender(json.loads(path.read_text(encoding="utf-8")), str(path), None)

    store = KbStore(kb_dir=kb, data_path=kb / "data.json", prompt_src=None, prompt_dst=None,
                    load_all=lambda: [], load_one=load_one, after_write=kb_builder.publish_media)  # fmt: skip
    upsert_entry(str(cr), store)
    assert (kb / "media" / "cr_x_20260923_100000" / "view_front.jpg").read_bytes() == b"jpg"
    assert "window.__HEXA_KB__" in (kb / "data.js").read_text(encoding="utf-8")
    with pytest.raises(KnowledgeBaseShrinkError):
        build_knowledge_base(store=store)  # rapport brut « perdu » : refus de supprimer l'entrée


def test_reaudit_supersedes_previous_audit_of_same_deliverable():
    from kb_blender.normalizer import latest_per_deliverable

    entries = [
        {
            "id": "cr_run_b",
            "target_path": "/x/livrables_blender/run",
            "audit_started_at": "2026-09-23T14:35",
        },
        {
            "id": "cr_run_a",
            "target_path": "/y/livrables_blender/run",
            "audit_started_at": "2026-09-23T14:06",
        },
        {
            "id": "cr_other",
            "target_path": "/x/livrables_blender/other",
            "audit_started_at": "2026-09-23T13:00",
        },
    ]
    assert [e["id"] for e in latest_per_deliverable(entries)] == ["cr_run_b", "cr_other"]
