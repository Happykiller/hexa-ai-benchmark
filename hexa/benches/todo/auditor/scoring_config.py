"""Barème propre à la Todo List : piliers v1/v2 et statistiques TypeScript.

Les tables communes (tarifs, coût, bonus/malus, traçabilité) vivent dans
hexa/core/engine/config.py et sont ré-exportées ici pour les importeurs historiques.
"""

from hexa.core.engine.config import (  # noqa: F401 — ré-exports
    BONUS_HEADROOM_FRACTION,
    BONUS_MALUS_SCORE_CONFIG,
    COST_SCORE_PHASE,
    COST_SCORE_PHASE_LABEL,
    COST_SCORE_STEP_LABEL,
    COST_USD_BANDS,
    MODEL_PRICING,
    PRICING_UPDATED,
    TOTAL_TOKENS_BANDS,
    TRACE_SCORING_CONFIG,
)

# Legacy bucket weights (scoring v1) — frozen so --scoring v1 reproduces the 7
# historical runs exactly.
BASE_SCORE_BUCKETS_V1 = {
    "operationality": {
        "label": "Operationnalite",
        "weight": 50,
        "selectors": [{"phase": 1}],
    },
    "architecture": {
        "label": "Architecture",
        "weight": 25,
        "selectors": [{"phase": 2, "steps": [1, 4, 5, 6]}],
    },
    "quality": {
        "label": "Qualite logicielle",
        "weight": 15,
        "selectors": [{"phase": 2, "steps": [2, 3, 7]}],
    },
    "traceability": {
        "label": "Discipline et tracabilite",
        "weight": 10,
        "selectors": [{"phase": 3}],
    },
}

# scoring v2 — rebalanced to make room for a dedicated Cost pillar (phase 6).
# Total stays 100 so the v2 ceiling rule (reserve 100% for a flawless base) holds.
BASE_SCORE_BUCKETS_V2 = {
    "operationality": {
        "label": "Operationnalite",
        "weight": 43,
        "selectors": [{"phase": 1}],
    },
    "architecture": {
        "label": "Architecture",
        "weight": 22,
        "selectors": [{"phase": 2, "steps": [1, 4, 5, 6]}],
    },
    "quality": {
        "label": "Qualite logicielle",
        "weight": 13,
        "selectors": [{"phase": 2, "steps": [2, 3, 7]}],
    },
    "traceability": {
        "label": "Discipline et tracabilite",
        "weight": 10,
        "selectors": [{"phase": 3}],
    },
    "cost": {
        "label": "Cout & Efficience",
        "weight": 12,
        "selectors": [{"phase": 6}],
    },
}

BASE_SCORE_BUCKETS_BY_VERSION = {"v1": BASE_SCORE_BUCKETS_V1, "v2": BASE_SCORE_BUCKETS_V2}

# Back-compat default (importers that don't pass a version get the legacy set).
BASE_SCORE_BUCKETS = BASE_SCORE_BUCKETS_V1


# Final-score aggregation rule (the "ceiling" applied on top of the base buckets).
# Versioned independently from the indicator weighting model so historical runs stay
# reproducible via the CLI flag ``--scoring v1``.
#   v1 — legacy: final = clamp(base + capped(bonus - malus), 0, 100). Bonus can
#        complete an imperfect base to 100% (saturation), so models cluster at 100.
#   v2 — reserved ceiling: maluses subtract fully, then bonus may only fill a
#        fraction of the *remaining* gap to 100. A non-perfect base therefore
#        approaches but never reaches 100% — 100 is reserved for a flawless base.
SCORING_DEFAULT_VERSION = "v2"


TECHNICAL_STATS_SCORING_CONFIG = {
    "total_files": {
        "phase_number": 5,
        "phase_label": "Statistiques techniques",
        "step_number": 1,
        "step_label": "Mesures du codebase",
        "name": "Nombre total de fichiers",
        "description": "count(files)",
        "bands_label": "30..120=100%, 15..160=50%, else=0%",
        "weight": 1,
        "bands": [
            {"min": 30, "max": 120, "score_ratio": 1.0, "status": "OK", "label": "target"},
            {"min": 15, "max": 160, "score_ratio": 0.5, "status": "PARTIEL", "label": "tolerated"},
        ],
    },
    "total_ts_files": {
        "phase_number": 5,
        "phase_label": "Statistiques techniques",
        "step_number": 1,
        "step_label": "Mesures du codebase",
        "name": "Nombre total de fichiers TS/TSX",
        "description": "count(.ts, .tsx)",
        "bands_label": "20..80=100%, 10..110=50%, else=0%",
        "weight": 1,
        "bands": [
            {"min": 20, "max": 80, "score_ratio": 1.0, "status": "OK", "label": "target"},
            {"min": 10, "max": 110, "score_ratio": 0.5, "status": "PARTIEL", "label": "tolerated"},
        ],
    },
    "total_lines": {
        "phase_number": 5,
        "phase_label": "Statistiques techniques",
        "step_number": 1,
        "step_label": "Mesures du codebase",
        "name": "Nombre total de lignes TS/TSX",
        "description": "sum(lines in .ts/.tsx files)",
        "bands_label": "1000..5000=100%, 500..7000=50%, else=0%",
        "weight": 1,
        "bands": [
            {"min": 1000, "max": 5000, "score_ratio": 1.0, "status": "OK", "label": "target"},
            {
                "min": 500,
                "max": 7000,
                "score_ratio": 0.5,
                "status": "PARTIEL",
                "label": "tolerated",
            },
        ],
    },
    "total_tests": {
        "phase_number": 5,
        "phase_label": "Statistiques techniques",
        "step_number": 1,
        "step_label": "Mesures du codebase",
        "name": "Nombre de fichiers de test",
        "description": "count(.test.ts, .spec.ts, or files in tests/)",
        "bands_label": "10..50=100%, 5..70=50%, else=0%",
        "weight": 1,
        "bands": [
            {"min": 10, "max": 50, "score_ratio": 1.0, "status": "OK", "label": "target"},
            {"min": 5, "max": 70, "score_ratio": 0.5, "status": "PARTIEL", "label": "tolerated"},
        ],
    },
    "total_size_kb": {
        "phase_number": 5,
        "phase_label": "Statistiques techniques",
        "step_number": 1,
        "step_label": "Mesures du codebase",
        "name": "Taille totale du projet (KB)",
        "description": "sum(file_size_bytes)/1024",
        "bands_label": "50..2048=100%, 20..3072=50%, else=0%",
        "weight": 1,
        "bands": [
            {"min": 50, "max": 2048, "score_ratio": 1.0, "status": "OK", "label": "target"},
            {"min": 20, "max": 3072, "score_ratio": 0.5, "status": "PARTIEL", "label": "tolerated"},
        ],
    },
}
