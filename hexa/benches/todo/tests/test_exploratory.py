"""KPI exploratoires de la Todo List : mesures de code et carte KB."""

import json

from hexa.benches.todo.auditor.modules.exploratory import (
    measure_branch_coverage,
    measure_code,
    measure_dependencies,
)
from hexa.core.kb.cards import section_exploratory
from hexa.core.kb.common import exploratory_fields

_FUNCTION = """import x from "y";
export function {name}(v: number) {{
  const a = v + 1;
  const b = a * 2;
  if (b > 3 && a) {{
    return b;
  }}
  const c = b - 1;
  const d = c * c;
  return d ? d : 0;
}}
"""


def test_measure_code_counts_duplication_and_decisions(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.ts").write_text(_FUNCTION.format(name="fa"), encoding="utf-8")
    (src / "b.ts").write_text(_FUNCTION.format(name="fb"), encoding="utf-8")
    (src / "c.ts").write_text("export const u = 1;\nexport const w = 2;\n", encoding="utf-8")
    # Les tests et node_modules ne comptent pas : on ne mesure que le code livré.
    (src / "a.test.ts").write_text(_FUNCTION.format(name="ft") * 3, encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "z.ts").write_text(_FUNCTION.format(name="fz"), encoding="utf-8")

    code = measure_code(str(tmp_path))
    assert code["files"] == 3 and code["code_lines"] == 18
    # 7 des 8 lignes utiles de a.ts et b.ts sont identiques (seul le nom diffère).
    assert code["duplication_pct"] == round(14 / 18 * 100, 2)
    assert code["decisions_per_100_lines"] == round(6 / 18 * 100, 2)  # if, &&, ternaire × 2
    assert code["longest_file"] == "src/a.ts"


def test_measures_are_none_when_sources_are_missing(tmp_path):
    assert measure_code(str(tmp_path)) == {"files": 0, "code_lines": 0}
    assert measure_dependencies(str(tmp_path)) == {}
    assert measure_branch_coverage(str(tmp_path)) is None


def test_dependencies_and_branch_coverage(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"a": "1", "b": "1"}, "devDependencies": {"c": "1"}}),
        encoding="utf-8",
    )
    (tmp_path / "coverage").mkdir()
    (tmp_path / "coverage" / "coverage-summary.json").write_text(
        json.dumps({"total": {"branches": {"pct": 81.5}}}), encoding="utf-8"
    )
    assert measure_dependencies(str(tmp_path)) == {"runtime": 2, "dev": 1}
    assert measure_branch_coverage(str(tmp_path)) == 81.5


def test_old_reports_gain_no_field_and_no_card():
    """Continuité : un rapport d'avant les KPI exploratoires donne une entrée inchangée."""
    assert exploratory_fields({"meta": {}, "phases": []}) == {}
    assert section_exploratory({}) is None


def test_card_shows_unmeasured_kpis_as_such():
    card = section_exploratory(
        {
            "exploratory_kpis": [
                {"name": "A", "measured_value": 12.5, "remarks": "ok", "step": "s"},
                {
                    "name": "B",
                    "measured_value": None,
                    "remarks": "transcript non fourni",
                    "step": "s",
                },
            ]
        }
    )
    assert [(i["label"], i["value"]) for i in card["items"]] == [("A", "12.5"), ("B", "non mesuré")]


def _audit_payload(*names_and_ghsa):
    return {
        "metadata": {"vulnerabilities": {"high": 5, "critical": 0}},
        "vulnerabilities": {
            name: {
                "via": [
                    {
                        "name": name,
                        "severity": "high",
                        "title": f"faille {name}",
                        "url": f"https://github.com/advisories/{ghsa}",
                    },
                    "un-paquet-parent",  # dépendance transitive : pas un avis
                ]
            }
            for name, ghsa in names_and_ghsa
        }
        # Paquet signalé seulement parce qu'il dépend d'un paquet vulnérable.
        | {"parent": {"via": ["zod"]}},
    }


def test_advisories_are_counted_distinct_runtime_and_by_publication_date(tmp_path, monkeypatch):
    from datetime import UTC, datetime

    from hexa.benches.todo.auditor.modules import exploratory

    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
    full = _audit_payload(("zod", "GHSA-old"), ("jest-thing", "GHSA-new"))
    runtime = _audit_payload(("zod", "GHSA-old"))
    monkeypatch.setattr(
        exploratory, "_npm_audit", lambda target, *extra: runtime if extra else full
    )
    published = {
        "GHSA-old": datetime(2026, 10, 1, tzinfo=UTC),
        "GHSA-new": datetime(2026, 12, 1, tzinfo=UTC),
    }
    monkeypatch.setattr(exploratory, "_published_at", published.get)

    session = datetime(2026, 11, 16, tzinfo=UTC)
    measures = exploratory.measure_advisories(str(tmp_path), session)
    assert measures["distinct"] == 2  # et non 5 « high » comme le dit npm
    assert measures["runtime"] == ["GHSA-old"]
    assert measures["known_before_session"] == ["GHSA-old"]  # GHSA-new : révélé après

    # Une date de publication introuvable : on ne conclut pas à moitié.
    monkeypatch.setattr(exploratory, "_published_at", lambda ghsa: None)
    assert exploratory.measure_advisories(str(tmp_path), session)["known_before_session"] is None


def test_advisories_degrade_without_lockfile_or_network(tmp_path, monkeypatch):
    from hexa.benches.todo.auditor.modules import exploratory

    assert "error" in exploratory.measure_advisories(str(tmp_path), None)
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(exploratory, "_npm_audit", lambda target, *extra: None)
    measures = exploratory.measure_advisories(str(tmp_path), None)
    audit_db = {"meta": {}, "phases": [], "indicators": []}
    exploratory._emit_advisories(audit_db, measures)
    assert [i["measured_value"] for i in audit_db["indicators"]] == [None, None, None]


def test_session_start_is_the_earliest_declared_phase():
    from hexa.benches.todo.auditor.modules.exploratory import session_start_from_trace

    trace = {
        "data": {
            "phases": [
                {"start_time": "2026-11-16T09:04:10Z"},
                {"start_time": "2026-11-16T08:49:07Z"},
                {"start_time": "pas une date"},
            ]
        }
    }
    assert session_start_from_trace(trace).isoformat() == "2026-11-16T08:49:07+00:00"
    assert session_start_from_trace({}) is None
