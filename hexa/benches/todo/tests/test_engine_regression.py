"""Rejeu du scoring sur des rapports réels figés.

Garde-fou de non-régression du moteur de notation (loi n°2 : les audits doivent rester
comparables dans le temps). Chaque fixture est la copie élaguée (sans `artifacts`/`stats`)
d'un `cr_audits/*.json` publié ; on efface `summary` et `points`, on rappelle
`_finalize_audit_db` et on exige que le moteur reproduise exactement ce qui a été publié.
Le test doit passer avant ET après toute refonte du moteur.
"""

import copy
import json
from pathlib import Path

import pytest

from hexa.benches.todo.auditor.main import _finalize_audit_db

FIXTURES = Path(__file__).parent / "fixtures" / "cr_regression"


def _published_subset(replayed, published):
    """Restreint `replayed` aux clés présentes dans `published`, récursivement."""
    if isinstance(published, dict) and isinstance(replayed, dict):
        return {
            key: _published_subset(replayed.get(key), value) for key, value in published.items()
        }
    return replayed


def _scoring_version(data: dict) -> str:
    version = data["meta"].get("scoring_version") or data["summary"].get("scoring_version")
    if version:
        return version
    return "v1" if str(data["meta"].get("scoring_model", "")).endswith("_v1") else "v2"


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("cr_*.json")), ids=lambda p: p.stem[:40])
def test_finalize_reproduces_published_summary(path):
    published = json.loads(path.read_text(encoding="utf-8"))
    replay = copy.deepcopy(published)
    replay.pop("summary")
    replay.pop("points")

    _finalize_audit_db(replay, _scoring_version(published))

    # Les rapports anciens n'ont pas toutes les clés ajoutées depuis (coût, détail du
    # bonus/malus) : on compare uniquement ce qui avait été publié, mais strictement.
    assert _published_subset(replay["summary"], published["summary"]) == published["summary"]
    assert replay["points"] == published["points"]
    assert replay["phases"] == published["phases"]
