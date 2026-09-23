"""Emplacements de la knowledge base Blender."""

from hexa.benches.blender.auditor.challenge import CHALLENGES_DIR, DEFAULT_CHALLENGE
from hexa.paths import cr_audits_dir, site_dir

KB_DIR = site_dir("blender")
DATA_PATH = KB_DIR / "data.json"
OVERRIDES_PATH = KB_DIR / "overrides.json"
MEDIA_DIR = KB_DIR / "media"
SCAN_DIRS = [cr_audits_dir("blender")]

# Le front charge ./evaluation_prompt.md : même nom que la KB Todo, contenu = énoncé du défi.
PROMPT_SRC = CHALLENGES_DIR / DEFAULT_CHALLENGE / "enonce.md"
PROMPT_DST = KB_DIR / "evaluation_prompt.md"

# Libellés courts des piliers pour le tableau (les libellés longs viennent du rapport).
BUCKET_SHORT = {
    "operationality": "Opé",
    "geometry": "Géo",
    "visual": "Visuel",
    "rig_animation": "Rig",
    "traceability": "Traca",
    "cost": "Coût",
}
