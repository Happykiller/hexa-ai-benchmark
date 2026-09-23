"""Livrable témoin : le build échoue (cap build_failed attendu)."""

import bpy

bpy.ops.wm.read_factory_settings(use_empty=True)
raise RuntimeError("échec volontaire du livrable témoin")
