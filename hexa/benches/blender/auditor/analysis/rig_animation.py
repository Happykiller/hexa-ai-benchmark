"""Phase 7 — Rig & Animation (depuis inspection.json)."""

import math
import re
from collections import defaultdict
from typing import Any

from hexa.benches.blender.auditor.analysis import Check, fmt, ratio_at_least, ratio_at_most
from hexa.benches.blender.auditor.bench_config import BONE_SYMMETRY_TOLERANCE_RATIO

PHASE = 7


def main_armature(inspection: dict[str, Any]) -> dict[str, Any] | None:
    armatures = inspection.get("armatures") or []
    return max(armatures, key=lambda arm: len(arm["bones"])) if armatures else None


def limb_bones(armature: dict[str, Any] | None, pattern: str) -> dict[str, list[str]]:
    """{"serre.L": [os…], …} d'après le motif contractuel des chaînes de membres."""
    chains: dict[str, list[str]] = defaultdict(list)
    if not armature:
        return chains
    regex = re.compile(pattern)
    for bone in armature["bones"]:
        match = regex.match(bone["name"])
        if match:
            chains[f"{match.group(1)}.{match.group(3)}"].append(bone["name"])
    return chains


def _mirror_ok(armature: dict[str, Any], height: float) -> tuple[int, int]:
    """(paires .L/.R en miroir, os .L au total)."""
    bones = {bone["name"]: bone for bone in armature["bones"]}
    tolerance = BONE_SYMMETRY_TOLERANCE_RATIO * max(height, 1e-6)
    left = [name for name in bones if name.endswith(".L")]
    ok = 0
    for name in left:
        right = bones.get(name[:-2] + ".R")
        if right is None:
            continue
        a, b = bones[name], right
        if all(
            math.dist((-a[key][0], a[key][1], a[key][2]), b[key]) <= tolerance
            for key in ("head", "tail")
        ):
            ok += 1
    return ok, len(left)


def real_motion_actions(inspection: dict[str, Any], spec: dict[str, Any]) -> list[str]:
    threshold = spec["animations"]["motion_threshold_ratio"]
    return [
        action["name"]
        for action in inspection.get("actions", [])
        if action.get("motion") and action["motion"]["max_displacement_ratio"] >= threshold
    ]


def analyze_rig_animation(inspection: dict[str, Any], spec: dict[str, Any]) -> list[Check]:
    checks: list[Check] = []
    height = float(inspection.get("height") or 0.0)
    limbs_spec = spec["limbs"]
    armature = main_armature(inspection)

    step = (PHASE, 1, "Armature")
    bone_count = len(armature["bones"]) if armature else 0
    checks.append(
        Check(
            *step,
            "Armature présente",
            1.0 if armature else 0.0,
            6,
            f"armatures={len(inspection.get('armatures') or [])}; os={bone_count}",
            measured_value=bone_count,
        )
    )
    expected = [f"{name}.{side}" for name in limbs_spec["names"] for side in ("L", "R")]
    chains = limb_bones(armature, limbs_spec["bone_pattern"])
    present = [limb for limb in expected if chains.get(limb)]
    checks.append(
        Check(
            *step,
            "Six membres riggés (serres + pattes, L/R)",
            len(present) / len(expected),
            5,
            f"{len(present)}/{len(expected)}; manquants={', '.join(sorted(set(expected) - set(present))) or 'aucun'}",
            measured_value=len(present),
        )
    )
    minimum = limbs_spec["min_bones_per_limb"]
    deep = [limb for limb in expected if len(chains.get(limb, [])) >= minimum]
    checks.append(
        Check(
            *step,
            f"≥ {minimum} os par membre",
            len(deep) / len(expected),
            3,
            "; ".join(f"{limb}={len(chains.get(limb, []))}" for limb in expected),
            measured_value=len(deep),
        )
    )
    mirrored, left = _mirror_ok(armature, height) if armature else (0, 0)
    checks.append(
        Check(
            *step,
            "Symétrie L/R des os",
            mirrored / left if left else 0.0,
            4,
            f"paires en miroir={mirrored}/{left}",
            measured_value=mirrored,
        )
    )

    step = (PHASE, 2, "Skinning")
    meshes = inspection.get("meshes", [])
    verts = sum(mesh["verts"] for mesh in meshes) or 1
    skinned = sum(
        mesh["verts"] * mesh.get("weighted_ratio", 0)
        for mesh in meshes
        if mesh.get("armature_modifier")
    )
    weighted = skinned / verts
    checks.append(
        Check(
            *step,
            "Sommets pondérés sur l'armature (≥ 99 %)",
            ratio_at_least(weighted, 0.99, 0.9),
            5,
            f"pondérés={fmt(weighted * 100, 2)} %",
            measured_value=round(weighted, 4),
        )
    )
    over4 = sum(mesh["verts"] * mesh.get("over4_ratio", 0) for mesh in meshes) / verts
    max_inf = max((mesh.get("max_influences", 0) for mesh in meshes), default=0)
    checks.append(
        Check(
            *step,
            "≤ 4 influences par sommet",
            ratio_at_most(over4, 0.0, 0.01) if weighted > 0 else 0.0,
            3,
            f"sommets > 4 influences={fmt(over4 * 100, 2)} %; max={max_inf}",
            measured_value=max_inf,
        )
    )

    step = (PHASE, 3, "Actions")
    anim = spec["animations"]
    actions = {action["name"]: action for action in inspection.get("actions", [])}
    for name, requirement in anim["required"].items():
        action = actions.get(name)
        if action is None:
            ratio, remarks = 0.0, "absente"
        else:
            long_enough = action["frames"] >= requirement["min_frames"]
            ratio = 1.0 if long_enough and action["targets_pose_bones"] else 0.5
            remarks = f"images={fmt(action['frames'])} (min {requirement['min_frames']}); os animés={action['targets_pose_bones']}"
        checks.append(
            Check(
                *step,
                f"Action « {name} »",
                ratio,
                5,
                remarks,
                measured_value=None if action is None else action["frames"],
            )
        )
    fps = (inspection.get("scene") or {}).get("fps")
    checks.append(
        Check(
            *step,
            f"Cadence {anim['fps']} fps",
            1.0 if fps == anim["fps"] else 0.0,
            2,
            f"fps={fps}",
            measured_value=fps,
        )
    )
    moving = real_motion_actions(inspection, spec)
    required = list(anim["required"])
    moved = [name for name in required if name in moving]
    checks.append(
        Check(
            *step,
            "Mouvement réel des actions requises",
            len(moved) / len(required),
            5,
            "; ".join(
                f"{name}={fmt(actions[name]['motion']['max_displacement_ratio'], 4) if actions.get(name, {}).get('motion') else 'n/a'}"
                for name in required
            )
            + f" (seuil {anim['motion_threshold_ratio']} × hauteur)",
            measured_value=len(moved),
        )
    )
    checks.append(_legs_check(actions.get("walk"), chains, anim, step))
    loop_tolerance = anim["loop_tolerance_ratio"]
    looping = [
        name
        for name in required
        if actions.get(name, {}).get("motion")
        and actions[name]["motion"]["loop_delta_ratio"] <= loop_tolerance
    ]
    checks.append(
        Check(
            *step,
            "Actions qui bouclent",
            len(looping) / len(required),
            3,
            "; ".join(
                f"{name}={fmt(actions[name]['motion']['loop_delta_ratio'], 4) if actions.get(name, {}).get('motion') else 'n/a'}"
                for name in required
            ),
            measured_value=len(looping),
        )
    )
    nan = sum(action.get("nan_keyframes", 0) for action in actions.values())
    checks.append(
        Check(
            *step,
            "Aucune clé NaN / infinie",
            1.0 if actions and nan == 0 else 0.0,
            2,
            f"clés invalides={nan}",
            measured_value=nan,
        )
    )

    step = (PHASE, 4, "Mesures")
    checks += [
        Check(
            *step,
            "Os (armature principale)",
            kind="measured",
            measured_value=bone_count,
            remarks=str(bone_count),
        ),
        Check(
            *step,
            "Actions",
            kind="measured",
            measured_value=len(actions),
            remarks=", ".join(sorted(actions)) or "aucune",
        ),
    ]
    return checks


def _legs_check(
    walk: dict[str, Any] | None, chains: dict[str, list[str]], anim: dict[str, Any], step
) -> Check:
    legs = [limb for limb in sorted(chains) if limb.startswith("patte")]
    name = "Cycle de marche : les 4 pattes bougent"
    if not walk or not walk.get("motion") or not legs:
        return Check(
            *step, name, 0.0, 4, "action walk ou chaînes de pattes absentes", measured_value=0
        )
    per_bone = walk["motion"]["per_bone"]
    threshold = anim["leg_motion_threshold_ratio"]
    moving = [
        limb
        for limb in legs
        if max((per_bone.get(bone, 0.0) for bone in chains[limb]), default=0.0) >= threshold
    ]
    return Check(
        *step,
        name,
        min(1.0, len(moving) / 4),
        4,
        f"pattes en mouvement={len(moving)}/4 ({', '.join(moving) or 'aucune'})",
        measured_value=len(moving),
    )
