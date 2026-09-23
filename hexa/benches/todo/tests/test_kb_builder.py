import json
from pathlib import Path

import pytest

from hexa.benches.todo.kb import builder
from hexa.benches.todo.kb.builder import (
    KnowledgeBaseShrinkError,
    _extract_report_markdown,
    build_knowledge_base,
)
from hexa.benches.todo.kb.normalizer import normalize
from hexa.paths import ROOT_DIR


def _entry(entry_id: str, **extra: object) -> dict:
    return {"id": entry_id, "model": "m", "score_percentage": 80.0, **extra}


@pytest.fixture
def kb_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the builder at a throwaway knowledge_base/ so tests never touch the real one."""
    monkeypatch.setattr(builder, "KB_DIR", tmp_path)
    monkeypatch.setattr(builder, "DATA_PATH", tmp_path / "data.json")
    monkeypatch.setattr(builder, "PROMPT_SRC", tmp_path / "absent.md")
    return tmp_path


def test_full_rebuild_refuses_to_drop_published_entries(
    kb_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """cr_audits/ is gitignored: a missing raw report must not silently erase a published run."""
    data_path = kb_dir / "data.json"
    published = [_entry("cr_kept"), _entry("cr_orphan", model="gpt-5.6-sol")]
    data_path.write_text(json.dumps(published), encoding="utf-8")
    monkeypatch.setattr(builder, "load_all", lambda: [_entry("cr_kept")])

    with pytest.raises(KnowledgeBaseShrinkError) as excinfo:
        build_knowledge_base()

    assert "cr_orphan" in str(excinfo.value)
    assert "--allow-drop" in str(excinfo.value)
    assert json.loads(data_path.read_text(encoding="utf-8")) == published


def test_full_rebuild_drops_entries_when_explicitly_allowed(
    kb_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_path = kb_dir / "data.json"
    data_path.write_text(json.dumps([_entry("cr_kept"), _entry("cr_orphan")]), encoding="utf-8")
    monkeypatch.setattr(builder, "load_all", lambda: [_entry("cr_kept")])

    build_knowledge_base(allow_drop=True)

    assert [e["id"] for e in json.loads(data_path.read_text(encoding="utf-8"))] == ["cr_kept"]


def test_full_rebuild_writes_when_no_entry_is_lost(
    kb_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_path = kb_dir / "data.json"
    data_path.write_text(json.dumps([_entry("cr_kept")]), encoding="utf-8")
    monkeypatch.setattr(builder, "load_all", lambda: [_entry("cr_kept"), _entry("cr_new")])

    build_knowledge_base()

    assert [e["id"] for e in json.loads(data_path.read_text(encoding="utf-8"))] == [
        "cr_kept",
        "cr_new",
    ]


def test_full_rebuild_on_a_fresh_checkout_is_not_blocked(
    kb_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No data.json yet — nothing published, so nothing can be lost."""
    monkeypatch.setattr(builder, "load_all", lambda: [_entry("cr_new")])

    build_knowledge_base()

    assert (kb_dir / "data.json").exists()


def test_source_file_is_repo_relative_however_the_path_is_given() -> None:
    """data.json is versioned: no machine-specific prefix, and a full rebuild (absolute paths)
    must agree with --add (whatever the caller typed)."""
    absolute = str(ROOT_DIR / "cr_audits" / "sample.json")
    relative = "cr_audits/sample.json"

    payload = {
        "meta": {"target_path": "livrables/20260701_0638_x", "scoring_model": "fib_v2"},
        "summary": {"percentage_net": 80, "bucket_scores": {}},
        "artifacts": {},
        "stats": {},
    }

    from_rebuild = normalize(dict(payload), absolute, None)
    from_add = normalize(dict(payload), relative, None)

    assert from_rebuild["source_file"] == "cr_audits/sample.json"
    assert from_rebuild["source_file"] == from_add["source_file"]
    assert from_rebuild["id"] == from_add["id"]


def test_report_markdown_source_file_is_repo_relative(tmp_path: Path, monkeypatch) -> None:
    report = ROOT_DIR / "runs" / "todo" / "cr_audits" / "_pytest_tmp_report.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("# Rapport d'Audit par Indicateurs\n", encoding="utf-8")
    try:
        extracted = _extract_report_markdown(report)
    finally:
        report.unlink()

    assert extracted is not None
    assert extracted["source_file"] == "runs/todo/cr_audits/_pytest_tmp_report.md"


def test_extract_report_markdown_collects_summary_and_findings(tmp_path: Path) -> None:
    report = tmp_path / "sample.md"
    report.write_text(
        """# Rapport d'Audit par Indicateurs
## Résumé global
| Mesure | Valeur |
|--------|--------|
| Pourcentage final du score net | 72.41% |
| Nombre total d'indicateurs | 63 |

## Revue détaillée des indicateurs par phase
### Phase 1. Opérationnalité (Score: 57.0/147)
#### Étape 1-1. Exécution des cibles make & Docker
| Code | Indicateur | Valeur mesurée | Score obtenu | Score max | Remarques |
|------|------------|----------------|--------------|-----------|-----------|
| 1-1-2 | make lint |  | 0 | 5 | exit_code=2; service "api" is not running |
| 1-1-3 | make build |  | 10 | 10 | exit_code=0 |
| 1-3-2 | Tests FAIL |  | 0 | 21 | count=0 |
""",
        encoding="utf-8",
    )

    extracted = _extract_report_markdown(report)

    assert extracted is not None
    assert extracted["summary_metrics"]["Pourcentage final du score net"] == "72.41%"
    assert extracted["findings_count"] == 1
    assert extracted["top_findings"][0]["indicator"] == "make lint"
    assert 'service "api" is not running' in extracted["top_findings"][0]["remarks"]


def test_extract_report_markdown_keeps_actual_failed_tests(tmp_path: Path) -> None:
    report = tmp_path / "sample.md"
    report.write_text(
        """# Rapport d'Audit par Indicateurs
## Revue détaillée des indicateurs par phase
### Phase 1. Opérationnalité (Score: 57.0/147)
#### Étape 1-3. Résultats des tests unitaires
| Code | Indicateur | Valeur mesurée | Score obtenu | Score max | Remarques |
|------|------------|----------------|--------------|-----------|-----------|
| 1-3-2 | Tests FAIL |  | -1.05 | 21 | count=1 |
""",
        encoding="utf-8",
    )

    extracted = _extract_report_markdown(report)

    assert extracted is not None
    assert extracted["findings_count"] == 1
    assert extracted["top_findings"][0]["indicator"] == "Tests FAIL"
    assert extracted["top_findings"][0]["score"] == -1.05


def test_extract_report_markdown_ignores_valid_trace_phase_count(tmp_path: Path) -> None:
    report = tmp_path / "sample.md"
    report.write_text(
        """# Rapport d'Audit par Indicateurs
## Revue détaillée des indicateurs par phase
### Phase 3. Traçabilité (Score: 0.0/13)
#### Étape 3-1. Fichier audit_trace.json
| Code | Indicateur | Valeur mesurée | Score obtenu | Score max | Remarques |
|------|------------|----------------|--------------|-----------|-----------|
| 3-1-1 | Fichier audit_trace.json |  | 0 | 5 | meta.prompt_version is required |
| 3-1-2 | Nombre de phases tracées >= 1 |  | 0 | 2 | phases_count=3 |
| 3-2-1 | Nombre total d'échanges (turns) |  | 0 | 5 | value=32; tranche=out_of_range |
""",
        encoding="utf-8",
    )

    extracted = _extract_report_markdown(report)

    assert extracted is not None
    assert extracted["findings_count"] == 1
    assert extracted["top_findings"][0]["indicator"] == "Fichier audit_trace.json"


def test_extract_report_markdown_keeps_missing_trace_phase_count(tmp_path: Path) -> None:
    report = tmp_path / "sample.md"
    report.write_text(
        """# Rapport d'Audit par Indicateurs
## Revue détaillée des indicateurs par phase
### Phase 3. Traçabilité (Score: 0.0/13)
#### Étape 3-1. Fichier audit_trace.json
| Code | Indicateur | Valeur mesurée | Score obtenu | Score max | Remarques |
|------|------------|----------------|--------------|-----------|-----------|
| 3-1-2 | Nombre de phases tracées >= 1 |  | 0 | 2 | phases_count=0 |
""",
        encoding="utf-8",
    )

    extracted = _extract_report_markdown(report)

    assert extracted is not None
    assert extracted["findings_count"] == 1
    assert extracted["top_findings"][0]["indicator"] == "Nombre de phases tracées >= 1"


def test_kb_normalizer_extracts_trace_model_metadata() -> None:
    entry = normalize(
        {
            "meta": {
                "target_path": "livrables/20260529_1007_AGY_GEMINI_3.5-flash",
                "audit_started_at": "2026-05-29 10:00:00",
                "scoring_model": "indicator_fibonacci_v1",
            },
            "summary": {
                "percentage_net": 40,
                "bucket_scores": {},
            },
            "artifacts": {
                "traceability": {
                    "data": {
                        "meta": {
                            "prompt_version": "2605291055",
                            "model": "gemini-3.5-flash",
                            "effort": "medium",
                        }
                    }
                },
                "trace_metrics": {
                    "phases_count": 1,
                    "total_turns": 2,
                    "total_tool_calls": 12,
                    "total_wall_time_seconds": 600,
                    "trace_errors_count": 0,
                },
            },
            "stats": {},
        },
        "cr_audits/sample.json",
        None,
    )

    assert entry["agent"] == "AGY_GEMINI_3.5-flash"
    assert entry["model"] == "gemini-3.5-flash"
    assert entry["effort"] == "medium"
    assert entry["prompt_version"] == "2605291055"
    assert entry["duration_seconds"] == 600

    trace_diag = next(
        section for section in entry["sections"] if section["title"] == "Détail traçabilité"
    )
    values = {item["label"]: item["value"] for item in trace_diag["items"]}
    assert values["Score trace"] == "0.0"


def test_kb_trace_diagnostic_exposes_trace_errors() -> None:
    entry = normalize(
        {
            "meta": {
                "target_path": "livrables/20260529_1042_claude-opus-4-8_temp1.0",
                "audit_started_at": "2026-05-29 11:00:00",
                "scoring_model": "indicator_fibonacci_v1",
            },
            "summary": {
                "percentage_net": 94.17,
                "bucket_scores": {
                    "traceability": {
                        "normalized_score": 0,
                        "weight": 10,
                    }
                },
            },
            "artifacts": {
                "traceability": {
                    "errors": ["meta.prompt_version is required"],
                    "data": {"meta": {"model": "claude-opus-4-8", "effort": "high"}},
                },
                "trace_metrics": {
                    "phases_count": 3,
                    "total_turns": 32,
                    "total_tool_calls": 100,
                    "total_wall_time_seconds": 1037,
                    "trace_errors_count": 1,
                },
            },
            "stats": {},
            "phases": [
                {
                    "code": "3",
                    "label": "Traçabilité",
                    "steps": [
                        {
                            "label": "Validation audit_trace.json",
                            "indicators": [
                                {
                                    "code": "3-1-1",
                                    "name": "Validation audit_trace.json",
                                    "status": "OK",
                                    "score": 1,
                                    "max_score": 1,
                                    "remarks": "phases_count=3",
                                    "details": {"data": {"ignored": "too verbose for tooltip"}},
                                },
                                {
                                    "code": "3-1-2",
                                    "name": "Nombre de phases tracées >= 1",
                                    "status": "OK",
                                    "score": 2,
                                    "max_score": 2,
                                    "remarks": "phases_count=3",
                                    "details": {"phases_count": 3},
                                },
                                {
                                    "code": "3-1-3",
                                    "name": "Cohérence wall time",
                                    "status": "KO",
                                    "score": 0,
                                    "max_score": 2,
                                    "remarks": "summary.total_wall_time_seconds differs from summed phases by more than 10% (summary=1200, phases=300)",
                                    "details": {
                                        "summary_total_wall_time_seconds": 1200,
                                        "phases_total_wall_time_seconds": 300,
                                    },
                                },
                            ],
                        },
                        {
                            "label": "Efficacité de la session (audit_trace.json)",
                            "indicators": [
                                {
                                    "code": "3-2-1",
                                    "name": "Nombre total d'échanges (turns)",
                                    "status": "SKIPPED",
                                    "score": 0,
                                    "max_score": 5,
                                    "measured_value": 32,
                                    "remarks": "value=32; tranche=out_of_range",
                                    "details": {"bands": "5..15=100%, 2..25=50%, else=0%"},
                                }
                            ],
                        },
                    ],
                }
            ],
        },
        "cr_audits/sample.json",
        None,
    )

    trace_diag = next(
        section for section in entry["sections"] if section["title"] == "Détail traçabilité"
    )
    values = {item["label"]: item["value"] for item in trace_diag["items"]}
    assert values["Score trace"] == "0.0 / 10.0 (0%)"
    assert values["3-1-1 Validation audit_trace.json"] == "OK · 1/1"
    assert values["3-1-3 Cohérence wall time"] == "KO · 0/2"
    assert values["3-2-1 Nombre total d'échanges (turns)"] == "SKIPPED · 0/5"
