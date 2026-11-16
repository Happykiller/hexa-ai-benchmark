"""Aucun chemin machine dans les données publiées (docs/KB/DAT/kb-magasin-donnees.md)."""

from hexa.paths import ROOT_DIR, portable_path


def test_portable_path_strips_machine_prefix():
    assert portable_path(f"{ROOT_DIR}/runs/blender/livrables/x") == "runs/blender/livrables/x"
    # Même dépôt cloné sur une autre machine.
    assert portable_path(f"/home/autre/sandbox/{ROOT_DIR.name}/runs/todo/livrables/y") == (
        "runs/todo/livrables/y"
    )


def test_portable_path_keeps_relative_and_foreign_paths():
    assert portable_path("runs/todo/livrables/z") == "runs/todo/livrables/z"
    assert portable_path("/tmp/pytest-1/livrable") == "/tmp/pytest-1/livrable"
