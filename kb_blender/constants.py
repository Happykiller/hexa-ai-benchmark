from kb.constants import ROOT_DIR

KB_DIR = ROOT_DIR / "knowledge_base_blender"
DATA_PATH = KB_DIR / "data.json"
OVERRIDES_PATH = KB_DIR / "overrides.json"
MEDIA_DIR = KB_DIR / "media"
SCAN_DIRS = [ROOT_DIR / "cr_audits_blender"]

# Le front charge ./evaluation_prompt.md : même nom que la KB Todo, contenu = énoncé du défi.
PROMPT_SRC = ROOT_DIR / "blender_bench" / "challenges" / "dreadhive_drone_mk1" / "enonce.md"
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
