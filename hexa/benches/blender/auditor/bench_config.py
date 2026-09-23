"""Barème du benchmark Blender (version b1).

Les phases 3 (traçabilité), 4 (bonus/malus) et 6 (coût) gardent les numéros du benchmark
Todo : elles sont émises par le même code (auditor/engine), avec les mêmes bandes. Toute
modification de ce fichier change les scores : nouvelle version de barème (b2) et
ré-audit des runs comparables (loi n°2).
"""

SCORING_VERSION = "b1"
SCORING_MODEL = "blender_indicator_fibonacci_b1"
CEILING_RULE = "v2"  # plafond réservé : 100 % exige une base sans faute

PHASES = {
    1: "Opérationnalité",
    2: "Géométrie & Topologie",
    3: "Traçabilité",
    4: "Bonus / Malus",
    5: "Fidélité visuelle",
    6: "Coût & Efficience",
    7: "Rig & Animation",
}

BLENDER_SCORE_BUCKETS_B1 = {
    "operationality": {"label": "Opérationnalité", "weight": 18, "selectors": [{"phase": 1}]},
    "geometry": {"label": "Géométrie & Topologie", "weight": 18, "selectors": [{"phase": 2}]},
    "visual": {"label": "Fidélité visuelle", "weight": 24, "selectors": [{"phase": 5}]},
    "rig_animation": {"label": "Rig & Animation", "weight": 18, "selectors": [{"phase": 7}]},
    "traceability": {
        "label": "Discipline & Traçabilité",
        "weight": 10,
        "selectors": [{"phase": 3}],
    },
    "cost": {"label": "Coût & Efficience", "weight": 12, "selectors": [{"phase": 6}]},
}

BLENDER_BONUS_MALUS_CONFIG = {"phase_number": 4, "bonus_cap": 5, "malus_cap": -10}

# Caps éliminatoires (pourcentage maximal du score final).
CAPS = {
    "build_failed": 40,
    "sandbox_violation": 40,
    "gltf_not_reimportable": 40,
    "no_armature": 50,
    "no_real_animation": 60,
}


def _band(min_value, max_value, ratio, label):
    status = "OK" if ratio >= 1.0 else ("PARTIEL" if ratio > 0 else "KO")
    return {
        "min": min_value,
        "max": max_value,
        "score_ratio": ratio,
        "status": status,
        "label": label,
    }


BUILD_SECONDS_BANDS = [
    _band(None, 120, 1.0, "≤ 2 min"),
    _band(None, 300, 0.6, "≤ 5 min"),
    _band(None, None, 0.3, "> 5 min"),
]
GLB_MB_BANDS = [
    _band(None, 20, 1.0, "≤ 20 Mo"),
    _band(None, 60, 0.5, "≤ 60 Mo"),
    _band(None, None, 0.0, "> 60 Mo"),
]
# Silhouettes : vignettes du turnaround petites (~140×260 px) et en légère perspective,
# face à des rendus orthographiques → un excellent modèle plafonne vers 0,7 d'IoU.
IOU_BANDS = [
    _band(0.55, None, 1.0, "≥ 0,55"),
    _band(0.40, None, 0.6, "≥ 0,40"),
    _band(0.25, None, 0.3, "≥ 0,25"),
    _band(None, None, 0.0, "< 0,25"),
]
# ΔE76 moyen (Lab) entre les pixels du rendu « flat » et la couleur de palette la plus proche.
DELTA_E_BANDS = [
    _band(None, 12, 1.0, "≤ 12"),
    _band(None, 20, 0.6, "≤ 20"),
    _band(None, 30, 0.3, "≤ 30"),
    _band(None, None, 0.0, "> 30"),
]
# Détail de surface : variance du laplacien de la luminance (rendu beauty, avant-plan).
# Calibré sur la fixture en primitives lisses (≈ 0,003 → « lisse ») ; à recaler sur les
# premiers vrais runs (docs/KB/DAF/blender-piliers.md).
DETAIL_BANDS = [
    _band(0.012, None, 1.0, "détaillé"),
    _band(0.006, None, 0.5, "peu détaillé"),
    _band(None, None, 0.0, "lisse"),
]
EXPOSURE_RANGE = (0.03, 0.9)  # luminance moyenne de l'avant-plan (rendu beauty)
NON_EMPTY_MIN_RATIO = 0.02  # part minimale de pixels couverts par la créature

PALETTE_MATCH_DELTA_E = 15.0  # une couleur de nœud « couvre » une couleur de palette
PALETTE_FULL_COVERAGE = 6  # couleurs de palette couvertes pour le score plein
TRANSLUCENCY_MIN = {"transmission": 0.1, "subsurface": 0.05, "emission": 0.05}
BONE_SYMMETRY_TOLERANCE_RATIO = 0.02  # × hauteur

DEFAULT_OBJECT_NAME = (
    r"^(Cube|Sphere|UVSphere|Icosphere|Cylinder|Cone|Torus|Plane|Circle|Grid|Monkey|Suzanne"
    r"|Mesh|Armature|Empty|BezierCurve|NurbsPath|Text|Object)(\.\d+)?$"
)
FORBIDDEN_CODE_PATTERNS = {
    "import réseau / sous-processus": (
        r"^\s*(?:import|from)\s+(?:socket|subprocess|requests|urllib|http\.client|ftplib"
        r"|pip|ensurepip|multiprocessing)\b"
    ),
    "os.system / os.popen": r"\bos\.(?:system|popen|exec\w*|spawn\w*)\s*\(",
}
ABSOLUTE_PATH_PATTERN = r"""['"](?:/home/|/mnt/|/tmp/|/Users/|/root/|[A-Za-z]:[\\/])"""
