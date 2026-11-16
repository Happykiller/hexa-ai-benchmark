"""KPI exploratoires du benchmark Blender : mesurés, jamais notés.

Voir hexa/core/engine/exploratory.py pour la règle. Ils préparent le barème b2
(docs/KB/DAF/blender-piliers.md) : opérationnalité, géométrie et rig sont à 100 % sur tous
les runs b1, et les paliers d'IoU écrasent des écarts réels de silhouette. Tout est tiré de
l'inspection et des silhouettes déjà produites : aucun rendu ni passe Blender en plus.
"""

from statistics import mean
from typing import Any

from hexa.benches.blender.auditor.analysis.rig_animation import limb_bones, main_armature
from hexa.core.engine.exploratory import emit_exploratory

SHAPE_STEP = (2, "Modèle 3D : silhouette en continu")
RIG_STEP = (3, "Rig & animation : richesse réelle")


def measure_blender(
    inspection: dict[str, Any], imagery: dict[str, Any], spec: dict[str, Any]
) -> dict[str, Any]:
    ious = [
        view["iou"]
        for view in (imagery.get("silhouettes") or {}).values()
        if isinstance(view, dict) and view.get("iou") is not None
    ]
    measures: dict[str, Any] = {
        "iou_mean": round(mean(ious), 4) if ious else None,
        "iou_min": round(min(ious), 4) if ious else None,
        "iou_views": len(ious),
    }

    limbs_spec = spec["limbs"]
    expected = [f"{name}.{side}" for name in limbs_spec["names"] for side in ("L", "R")]
    armature = main_armature(inspection)
    chains = limb_bones(armature, limbs_spec["bone_pattern"]) if armature else {}
    depths = [len(chains.get(limb, [])) for limb in expected]
    measures["bones_per_limb_mean"] = round(mean(depths), 2) if armature else None
    measures["bones_per_limb_min"] = min(depths) if armature else None

    threshold = spec["animations"]["motion_threshold_ratio"]
    actions = {action["name"]: action for action in inspection.get("actions", [])}
    measures["actions"] = {}
    for name in spec["animations"]["required"]:
        per_bone = ((actions.get(name) or {}).get("motion") or {}).get("per_bone")
        if not per_bone:
            measures["actions"][name] = None
            continue
        moving = {bone for bone, value in per_bone.items() if value >= threshold}
        limbs_moving = [limb for limb in expected if moving & set(chains.get(limb, []))]
        measures["actions"][name] = {
            "moving_bones_pct": round(len(moving) / len(per_bone) * 100, 1),
            "limbs_moving": len(limbs_moving),
            "limbs_expected": len(expected),
            "median_displacement_ratio": round(sorted(per_bone.values())[len(per_bone) // 2], 5),
        }
    return measures


def emit_blender_exploratory(
    audit_db: dict[str, Any],
    inspection: dict[str, Any] | None,
    imagery: dict[str, Any],
    spec: dict[str, Any],
) -> dict[str, Any]:
    m = measure_blender(inspection or {}, imagery or {}, spec)
    no_render = "silhouettes non mesurées (rendu absent)"
    emit_exploratory(
        audit_db,
        SHAPE_STEP,
        "IoU moyen des silhouettes",
        m["iou_mean"],
        f"moyenne continue sur {m['iou_views']} vues (le barème b1 note par paliers)"
        if m["iou_views"]
        else no_render,
        details=m,
    )
    emit_exploratory(
        audit_db,
        SHAPE_STEP,
        "IoU de la vue la moins fidèle",
        m["iou_min"],
        "" if m["iou_views"] else no_render,
    )
    no_rig = "armature absente"
    emit_exploratory(
        audit_db,
        RIG_STEP,
        "Os par membre (moyenne)",
        m["bones_per_limb_mean"],
        f"minimum={m['bones_per_limb_min']}" if m["bones_per_limb_mean"] is not None else no_rig,
    )
    threshold = spec["animations"]["motion_threshold_ratio"]
    for name, action in m["actions"].items():
        absent = "action absente ou sans mouvement mesuré"
        emit_exploratory(
            audit_db,
            RIG_STEP,
            f"Os réellement animés dans « {name} » (%)",
            action["moving_bones_pct"] if action else None,
            f"déplacement ≥ {threshold} × hauteur ; médiane={action['median_displacement_ratio']}"
            if action
            else absent,
        )
        emit_exploratory(
            audit_db,
            RIG_STEP,
            f"Membres en mouvement dans « {name} »",
            action["limbs_moving"] if action else None,
            f"sur {action['limbs_expected']} membres attendus" if action else absent,
        )
    return m
