"""Traduction des contrôles (analysis.Check) en indicateurs du noyau commun, et caps."""

from typing import Any

from hexa.benches.blender.auditor.analysis import Check
from hexa.benches.blender.auditor.analysis.rig_animation import real_motion_actions
from hexa.benches.blender.auditor.bench_config import CAPS, PHASES
from hexa.core.engine import _append_indicator


def emit_checks(audit_db: dict[str, Any], checks: list[Check]) -> None:
    for check in checks:
        _append_indicator(
            audit_db,
            check.phase,
            PHASES[check.phase],
            check.step,
            check.step_label,
            check.name,
            check.ratio > 0,
            check.remarks,
            polarity=check.polarity,
            status=check.resolved_status(),
            details=check.details,
            kind=check.kind,
            measured_value=check.measured_value,
            score_ratio=check.ratio,
            rank=check.rank,
            weight=check.weight,
        )


def cap_reasons(
    build: dict[str, Any] | None,
    reimport: dict[str, Any] | None,
    inspection: dict[str, Any] | None,
    spec: dict[str, Any],
) -> list[dict[str, Any]]:
    """Caps éliminatoires. Un échec de RENDU (côté auditeur) n'en déclenche aucun : l'opérateur
    tranche avant publication (esprit de la loi n°3)."""
    reasons = []

    def cap(cap_id: str, reason: str) -> None:
        reasons.append({"id": cap_id, "max_percentage": CAPS[cap_id], "reason": reason})

    build = build or {}
    if build.get("violations"):
        calls = sorted({violation["call"] for violation in build["violations"]})
        cap("sandbox_violation", f"appels interdits pendant le build : {', '.join(calls)}")
    if build.get("build_status") != "OK" or not build.get("exported"):
        cap(
            "build_failed",
            build.get("error")
            or build.get("export_error")
            or build.get("runner_error")
            or "build.py n'a pas produit de GLB",
        )
        return reasons
    if (reimport or {}).get("status") != "OK":
        cap("gltf_not_reimportable", (reimport or {}).get("error") or "réimport glTF en échec")
    inspection = inspection or {}
    if not inspection.get("armatures"):
        cap("no_armature", "aucune armature : le rig est obligatoire")
    elif not real_motion_actions(inspection, spec):
        cap("no_real_animation", "aucune action ne produit de mouvement mesurable")
    return reasons
