"""Phase 4 — Bonus (initiatives au-delà du contrat) et malus (écarts de discipline)."""

from typing import Any

from hexa.benches.blender.auditor.analysis import Check
from hexa.benches.blender.auditor.analysis.rig_animation import real_motion_actions

PHASE = 4


def analyze_bonus_malus(
    inspection: dict[str, Any] | None,
    static: dict[str, Any],
    glb_mb: float | None,
    spec: dict[str, Any],
) -> list[Check]:
    checks: list[Check] = []
    bonus = (PHASE, 1, "Initiatives détectées")
    inspection = inspection or {}
    extra = [
        name
        for name in real_motion_actions(inspection, spec)
        if name not in spec["animations"]["required"]
    ]
    checks.append(
        Check(
            *bonus,
            "Action supplémentaire animée",
            1.0 if extra else 0.0,
            weight=2,
            remarks=f"actions={', '.join(extra) or 'aucune'}",
        )
    )
    shape_keys = sum(mesh.get("shape_keys", 0) for mesh in inspection.get("meshes", []))
    checks.append(
        Check(
            *bonus,
            "Shape keys (déformations)",
            1.0 if shape_keys else 0.0,
            weight=1,
            remarks=f"shape keys={shape_keys}",
        )
    )
    textures = [
        image
        for image in inspection.get("images", [])
        if image.get("has_data") and min(image.get("size") or [0]) >= 1024
    ]
    checks.append(
        Check(
            *bonus,
            "Textures générées ≥ 1K",
            1.0 if textures else 0.0,
            weight=1,
            remarks=f"images ≥ 1024 px={len(textures)}",
        )
    )
    lods = [obj["name"] for obj in inspection.get("objects", []) if "lod" in obj["name"].lower()]
    checks.append(
        Check(
            *bonus,
            "Niveaux de détail (LOD)",
            1.0 if lods else 0.0,
            weight=1,
            remarks=", ".join(lods[:5]) or "aucun",
        )
    )

    malus = (PHASE, 2, "Écarts détectés")
    absolute = static.get("absolute_paths") or []
    checks.append(
        Check(
            *malus,
            "Chemin absolu dans le code",
            1.0 if absolute else 0.0,
            weight=2,
            polarity="negative",
            remarks="; ".join(f"{h['file']}:{h['line']}" for h in absolute[:5]) or "aucun",
        )
    )
    too_big = glb_mb is not None and glb_mb > spec["budget"]["max_glb_mb"]
    checks.append(
        Check(
            *malus,
            "GLB au-delà du budget de taille",
            1.0 if too_big else 0.0,
            weight=3,
            polarity="negative",
            remarks=f"Mo={glb_mb}; max={spec['budget']['max_glb_mb']}",
        )
    )
    orphans = sum((inspection.get("orphans") or {}).values())
    checks.append(
        Check(
            *malus,
            "Données orphelines laissées dans la scène",
            1.0 if orphans else 0.0,
            weight=1,
            polarity="negative",
            remarks=f"orphelins={orphans}",
        )
    )
    armature = bool(inspection.get("armatures"))
    unrigged = [
        mesh["name"]
        for mesh in inspection.get("meshes", [])
        if armature and not mesh.get("armature_modifier")
    ]
    checks.append(
        Check(
            *malus,
            "Maillages non liés à l'armature",
            1.0 if unrigged else 0.0,
            weight=2,
            polarity="negative",
            remarks=", ".join(unrigged[:6]) or "aucun",
        )
    )
    return checks
