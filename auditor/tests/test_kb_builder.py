import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from kb.builder import _extract_report_markdown


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
""",
        encoding="utf-8",
    )

    extracted = _extract_report_markdown(report)

    assert extracted is not None
    assert extracted["summary_metrics"]["Pourcentage final du score net"] == "72.41%"
    assert extracted["findings_count"] == 1
    assert extracted["top_findings"][0]["indicator"] == "make lint"
    assert "service \"api\" is not running" in extracted["top_findings"][0]["remarks"]
