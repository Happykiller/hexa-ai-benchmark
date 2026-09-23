"""Rejoue le build.py d'un livrable sous garde-fous, puis sauvegarde la scène et exporte le GLB.

Garde-fous : sockets, sous-processus et os.system sont remplacés par des fonctions qui
journalisent la tentative puis lèvent PermissionError. Ce n'est PAS une isolation forte
(voir docs/KB/REGLES/lois.md) : un script hostile peut s'en défaire. Il attrape en revanche
toute tentative ordinaire, qui est éliminatoire (cap sandbox_violation).

L'export est fait ici, avec des réglages identiques pour tous les livrables : c'est ce GLB
que l'auditeur réimporte et mesure, jamais un fichier produit par l'agent.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import runpy  # noqa: E402
import time  # noqa: E402
import traceback  # noqa: E402

import bpy  # noqa: E402
from _common import parse_args, write_json  # noqa: E402

VIOLATIONS: list[dict] = []


def _forbidden(label):
    def _stub(*args, **kwargs):
        frames = traceback.extract_stack(limit=6)[:-1]
        VIOLATIONS.append(
            {
                "call": label,
                "args": repr(args)[:200],
                "where": [f"{frame.filename}:{frame.lineno}" for frame in frames],
            }
        )
        raise PermissionError(f"hexa-ai-benchmark: appel interdit pendant le build ({label})")

    return _stub


def install_guards() -> None:
    import socket
    import subprocess

    socket.socket = _forbidden("socket.socket")  # type: ignore[misc]
    socket.create_connection = _forbidden("socket.create_connection")
    subprocess.Popen = _forbidden("subprocess.Popen")  # type: ignore[misc]
    for name in ("system", "popen", "execv", "execve", "execvp", "execvpe", "spawnv", "spawnve"):
        if hasattr(os, name):
            setattr(os, name, _forbidden(f"os.{name}"))


def pack_images() -> list[str]:
    """Empaquette les images générées en mémoire : sinon le .blend les perdrait."""
    packed = []
    for image in bpy.data.images:
        if image.packed_file or image.source in {"VIEWER", "MOVIE", "SEQUENCE"}:
            continue
        try:
            if image.has_data or image.is_dirty or image.source == "GENERATED":
                image.pack()
                packed.append(image.name)
        except RuntimeError:
            continue
    return packed


def main() -> None:
    args = parse_args(
        [
            ("--build", {"required": True}),
            ("--out", {"required": True}),
            ("--save", {"required": True}),
            ("--glb", {"required": True}),
            ("--log", {"required": True}),
        ]
    )
    os.makedirs(args.out, exist_ok=True)
    log = {
        "build_status": "KO",
        "build_seconds": None,
        "error": None,
        "traceback": None,
        "saved": False,
        "exported": False,
        "export_error": None,
        "packed_images": [],
        "violations": VIOLATIONS,
        "blender_version": bpy.app.version_string,
    }

    bpy.ops.wm.read_factory_settings(use_empty=True)
    install_guards()
    sys.argv = [args.build, "--", "--out", args.out]
    started = time.perf_counter()
    try:
        runpy.run_path(args.build, run_name="__main__")
        log["build_status"] = "OK"
    except SystemExit as exc:
        code = exc.code
        if code in (None, 0):
            log["build_status"] = "OK"
        else:
            log["error"] = f"SystemExit({code!r})"
    except BaseException as exc:  # noqa: BLE001 — tout échec du livrable est une donnée
        log["error"] = f"{type(exc).__name__}: {exc}"[:2000]
        log["traceback"] = traceback.format_exc()[-6000:]
    log["build_seconds"] = round(time.perf_counter() - started, 2)

    if log["build_status"] == "OK" and not VIOLATIONS:
        try:
            if bpy.context.object and bpy.context.object.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
        except RuntimeError:
            pass
        log["packed_images"] = pack_images()
        try:
            bpy.ops.wm.save_as_mainfile(filepath=args.save, compress=True, copy=True)
            log["saved"] = True
        except RuntimeError as exc:
            log["error"] = f"save failed: {exc}"[:2000]
        try:
            bpy.ops.export_scene.gltf(
                filepath=args.glb,
                export_format="GLB",
                use_selection=False,
                export_apply=True,
                export_yup=True,
                export_materials="EXPORT",
                export_cameras=False,
                export_lights=False,
                export_extras=False,
                export_animations=True,
                export_animation_mode="ACTIONS",
                export_skins=True,
            )
            log["exported"] = os.path.exists(args.glb)
        except Exception as exc:  # noqa: BLE001
            log["export_error"] = f"{type(exc).__name__}: {exc}"[:2000]

    write_json(args.log, log)


main()
