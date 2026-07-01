from pathlib import Path

from kb.builder import _extract_report_markdown
from kb.normalizer import normalize


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
