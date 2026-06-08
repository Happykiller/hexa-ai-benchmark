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


# --------------------------------------------------------------------------- #
# Cost pillar (scoring v2, phase 6). The agent reports token counts in
# audit_trace.json; the auditor multiplies them by this price table — so the $
# figure cannot be self-reported/gamed, only the (operator-verifiable) token counts.
# --------------------------------------------------------------------------- #
COST_SCORE_PHASE = 6
COST_SCORE_PHASE_LABEL = "Coût & Efficience"
COST_SCORE_STEP_LABEL = "Coût de la session"

# $ per 1,000,000 tokens. ESTIMATIONS (ordres de grandeur prix-liste API). Les modèles
# sont surtout consommés via abonnement (Claude Code, Codex, AGY) où le coût marginal au
# token n'est pas le prix API — ces valeurs servent de PROXY relatif pour comparer
# l'intensité/efficience entre modèles, pas de facturation exacte. Ajuster si besoin.
PRICING_UPDATED = "2026-06-08 (estimations prix-liste, proxy abonnement)"
MODEL_PRICING = {
    "claude-opus":   {"input": 15.0, "output": 75.0, "cached_input": 1.5},
    "claude-sonnet": {"input": 3.0,  "output": 15.0, "cached_input": 0.30},
    "claude-haiku":  {"input": 1.0,  "output": 5.0,  "cached_input": 0.10},
    "gpt-5.5":       {"input": 2.0,  "output": 12.0, "cached_input": 0.20},
    "gpt-5":         {"input": 1.25, "output": 10.0, "cached_input": 0.125},
    "gemini-flash":  {"input": 0.30, "output": 2.50, "cached_input": 0.03},
    "gemini-pro":    {"input": 1.25, "output": 10.0, "cached_input": 0.125},
}

# Session cost bands ($, whole session). Cheap = full marks. Ordered ascending; the
# first band whose [min,max] contains the value wins.
COST_USD_BANDS = [
    {"min": 0.0, "max": 0.50, "score_ratio": 1.0,  "status": "OK",      "label": "très frugal"},
    {"min": 0.0, "max": 1.50, "score_ratio": 0.75, "status": "OK",      "label": "frugal"},
    {"min": 0.0, "max": 3.00, "score_ratio": 0.50, "status": "PARTIEL", "label": "modéré"},
    {"min": 0.0, "max": 6.00, "score_ratio": 0.25, "status": "PARTIEL", "label": "coûteux"},
]  # > $6 → 0

# Model-agnostic fallback when the model is absent from MODEL_PRICING (operator gap,
# not the agent's fault): score frugality on total tokens instead of $.
TOTAL_TOKENS_BANDS = [
    {"min": 0, "max": 150000,  "score_ratio": 1.0,  "status": "OK",      "label": "très frugal"},
    {"min": 0, "max": 400000,  "score_ratio": 0.75, "status": "OK",      "label": "frugal"},
    {"min": 0, "max": 900000,  "score_ratio": 0.50, "status": "PARTIEL", "label": "modéré"},
    {"min": 0, "max": 2000000, "score_ratio": 0.25, "status": "PARTIEL", "label": "coûteux"},
]


BONUS_MALUS_SCORE_CONFIG = {
    "phase_number": 4,
    "phase_label": "Bonus / Malus",
    "bonus_cap": 5,
    "malus_cap": -10,
}


# Final-score aggregation rule (the "ceiling" applied on top of the base buckets).
# Versioned independently from the indicator weighting model so historical runs stay
# reproducible via the CLI flag ``--scoring v1``.
#   v1 — legacy: final = clamp(base + capped(bonus - malus), 0, 100). Bonus can
#        complete an imperfect base to 100% (saturation), so models cluster at 100.
#   v2 — reserved ceiling: maluses subtract fully, then bonus may only fill a
#        fraction of the *remaining* gap to 100. A non-perfect base therefore
#        approaches but never reaches 100% — 100 is reserved for a flawless base.
SCORING_DEFAULT_VERSION = "v2"

# v2 only: share of the remaining gap to 100 that the (capped) bonus may fill.
# 0.5 ⇒ a base of 99 with full bonus tops out at 99.5, not 100.
BONUS_HEADROOM_FRACTION = 0.5


TRACE_SCORING_CONFIG = {
    "total_turns": {
        "phase_number": 3,
        "phase_label": "Traçabilité",
        "step_number": 2,
        "step_label": "Efficacité de la session (audit_trace.json)",
        "name": "Nombre total d'échanges (turns)",
        "description": "Nombre total de tours de parole User <-> Agent",
        "bands_label": "5..15=100%, 2..25=50%, else=0%",
        "weight": 5,
        "bands": [
            {"min": 5, "max": 15, "score_ratio": 1.0, "status": "OK", "label": "excellent"},
            {"min": 2, "max": 25, "score_ratio": 0.5, "status": "PARTIEL", "label": "acceptable"},
        ],
    },
    "total_tool_calls": {
        "phase_number": 3,
        "phase_label": "Traçabilité",
        "step_number": 2,
        "step_label": "Efficacité de la session (audit_trace.json)",
        "name": "Nombre total d'appels d'outils",
        "description": "Nombre total d'actions effectuées (shell, fs, etc.)",
        "bands_label": "20..60=100%, 10..100=50%, else=0%",
        "weight": 3,
        "bands": [
            {"min": 20, "max": 60, "score_ratio": 1.0, "status": "OK", "label": "target"},
            {"min": 10, "max": 100, "score_ratio": 0.5, "status": "PARTIEL", "label": "tolerated"},
        ],
    },
    "total_wall_time_seconds": {
        "phase_number": 3,
        "phase_label": "Traçabilité",
        "step_number": 2,
        "step_label": "Efficacité de la session (audit_trace.json)",
        "name": "Temps réel total (secondes)",
        "description": "Temps total d'horloge en secondes",
        "bands_label": "600..1800=100%, 300..3600=50%, else=0%",
        "weight": 2,
        "bands": [
            {"min": 600, "max": 1800, "score_ratio": 1.0, "status": "OK", "label": "target"},
            {"min": 300, "max": 3600, "score_ratio": 0.5, "status": "PARTIEL", "label": "tolerated"},
        ],
    },
}


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
            {"min": 500, "max": 7000, "score_ratio": 0.5, "status": "PARTIEL", "label": "tolerated"},
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
