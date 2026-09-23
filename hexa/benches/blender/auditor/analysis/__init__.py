"""Analyses côté hôte : transforment les mesures brutes (JSON d'inspection, rendus) en
contrôles notés. Fonctions pures, testables sans Blender ; aucun seuil dans bpy/.

Chaque analyse renvoie une liste de `Check`, traduits en indicateurs par auditor/emit.py.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Check:
    phase: int
    step: int
    step_label: str
    name: str
    ratio: float = 0.0  # 0..1, part du poids obtenue
    rank: int | None = None  # rang Fibonacci → poids (ignoré si weight est fourni)
    remarks: str = ""
    status: str | None = None  # déduit du ratio si absent
    kind: str = "scored"  # "scored" | "measured"
    polarity: str = "positive"  # "negative" pour un malus
    measured_value: Any = None
    weight: float | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def resolved_status(self) -> str:
        if self.status:
            return self.status
        if self.kind == "measured":
            return "MESURE"
        if self.polarity == "negative":
            return "DETECTE" if self.ratio > 0 else "NON_DETECTE"
        if self.ratio >= 1.0:
            return "OK"
        return "PARTIEL" if self.ratio > 0 else "KO"


def ratio_at_most(value: float | None, full: float, partial: float) -> float:
    """1 si value ≤ full, 0,5 si value ≤ partial, 0 sinon (None → 0)."""
    if value is None:
        return 0.0
    if value <= full:
        return 1.0
    return 0.5 if value <= partial else 0.0


def ratio_at_least(value: float | None, full: float, partial: float) -> float:
    if value is None:
        return 0.0
    if value >= full:
        return 1.0
    return 0.5 if value >= partial else 0.0


def fmt(value: Any, digits: int = 3) -> str:
    if isinstance(value, float):
        return f"{value:.{digits}f}".rstrip("0").rstrip(".")
    return str(value)
