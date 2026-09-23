"""Livrable témoin : tente un accès réseau pendant le build (cap sandbox_violation attendu).

L'import est dynamique pour contourner le contrôle statique : seul le garde-fou
d'exécution doit l'attraper.
"""

import importlib

import bpy

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_cube_add()
network = importlib.import_module("soc" + "ket")
network.socket().connect(("192.0.2.1", 80))
