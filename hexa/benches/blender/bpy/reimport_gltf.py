"""Réimporte le GLB exporté par run_build.py dans une scène vide et écrit reimport.json.

Un modèle qui ne survit pas à l'aller-retour glTF n'est pas « prêt pour un moteur de jeu »
(cap gltf_not_reimportable).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy  # noqa: E402
from _common import creature_meshes, parse_args, write_json  # noqa: E402


def main() -> None:
    args = parse_args([("--glb", {"required": True}), ("--out", {"required": True})])
    result = {"status": "KO", "error": None}
    bpy.ops.wm.read_factory_settings(use_empty=True)
    try:
        bpy.ops.import_scene.gltf(filepath=args.glb)
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"{type(exc).__name__}: {exc}"[:2000]
        write_json(args.out, result)
        return
    meshes = creature_meshes()
    skinned = [
        obj
        for obj in meshes
        if any(mod.type == "ARMATURE" and mod.object for mod in obj.modifiers)
        and len(obj.vertex_groups)
    ]
    tris = 0
    for obj in meshes:
        obj.data.calc_loop_triangles()
        tris += len(obj.data.loop_triangles)
    result.update(
        {
            "status": "OK",
            "meshes": len(meshes),
            "skinned_meshes": len(skinned),
            "armatures": sum(1 for obj in bpy.context.scene.objects if obj.type == "ARMATURE"),
            "animations": sorted(action.name for action in bpy.data.actions),
            "materials": len(bpy.data.materials),
            "images": len(bpy.data.images),
            "triangles": tris,
        }
    )
    write_json(args.out, result)


main()
