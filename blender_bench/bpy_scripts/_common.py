"""Outils partagés par les scripts exécutés DANS Blender (bpy, bmesh, numpy ; pas de Pillow).

Chaque script est lancé par blender_bench/runner.py :
    blender -b [scene.blend] --factory-startup --python <script> -- <arguments>
et écrit un JSON que l'auditeur relit côté hôte. Ces scripts ne notent rien : ils mesurent.
"""

import argparse
import json
import math
import sys

import bpy


def parse_args(spec: list[tuple[str, dict]]) -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    for flag, options in spec:
        parser.add_argument(flag, **options)
    return parser.parse_args(argv)


def write_json(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False, allow_nan=False, default=str)


def linear_to_srgb(channel: float) -> float:
    channel = max(0.0, min(1.0, float(channel)))
    if channel <= 0.0031308:
        return channel * 12.92
    return 1.055 * math.pow(channel, 1.0 / 2.4) - 0.055


def rgb_hex(rgb_linear) -> str:
    return "#" + "".join(f"{round(linear_to_srgb(c) * 255):02X}" for c in list(rgb_linear)[:3])


def creature_meshes() -> list:
    """Objets maillés rendables de la scène courante."""
    return [
        obj
        for obj in bpy.context.scene.objects
        if obj.type == "MESH" and not obj.hide_render and not _is_bone_shape(obj)
    ]


def _is_bone_shape(obj) -> bool:
    for arm in bpy.data.objects:
        if arm.type == "ARMATURE" and arm.pose:
            for pbone in arm.pose.bones:
                if pbone.custom_shape is obj:
                    return True
    return False


def set_pose_position(position: str) -> None:
    """'REST' pour mesurer la posture de référence, 'POSE' pour jouer une action."""
    for obj in bpy.data.objects:
        if obj.type == "ARMATURE":
            obj.data.pose_position = position
    bpy.context.view_layer.update()


def world_bbox(objects) -> tuple[list[float], list[float]] | None:
    """Boîte englobante monde des maillages évalués (modificateurs et pose courante)."""
    import numpy as np

    depsgraph = bpy.context.evaluated_depsgraph_get()
    mins, maxs = [], []
    for obj in objects:
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            if not len(mesh.vertices):
                continue
            coords = np.empty(len(mesh.vertices) * 3, dtype=np.float64)
            mesh.vertices.foreach_get("co", coords)
            coords = coords.reshape(-1, 3)
            matrix = np.array(evaluated.matrix_world)
            world = coords @ matrix[:3, :3].T + matrix[:3, 3]
            mins.append(world.min(axis=0))
            maxs.append(world.max(axis=0))
        finally:
            evaluated.to_mesh_clear()
    if not mins:
        return None
    return np.min(mins, axis=0).tolist(), np.max(maxs, axis=0).tolist()


def assign_action(armature, action) -> None:
    """Rend `action` active sur l'armature (actions à slots de Blender 4.4+ comprises)."""
    anim = armature.animation_data or armature.animation_data_create()
    anim.action = action
    if hasattr(anim, "action_slot") and anim.action_slot is None:
        suitable = list(getattr(anim, "action_suitable_slots", []) or [])
        if not suitable and hasattr(action, "slots"):
            suitable = list(action.slots)
        if suitable:
            anim.action_slot = suitable[0]
