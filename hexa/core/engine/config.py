"""Barème COMMUN à tous les benchmarks : tarifs et coût (phase 6), bonus/malus (phase 4),
plafond du bonus, bandes d'efficacité de session (phase 3).

Un benchmark peut fournir les siens en paramètres ; ne changer ces valeurs qu'en sachant
qu'elles touchent TOUS les benchmarks (et imposent un ré-audit des runs comparables, loi n°2).
"""

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
# Tarifs revérifiés le 2026-09-22 sur la page officielle, entrées Anthropic toutes contrôlées.
# Sonnet 5 : le prix d'introduction $2/$10 est devenu le prix standard — la hausse à $3/$15
# annoncée pour le 2026-09-01 « will not occur » (le passage à $3/$15 du 2026-09-04 reposait
# sur l'échéance écrite ici et a été annulé). Les successeurs tarifés différemment de leur
# famille ont leur propre clé (voir _normalize_model_id) : Opus 5.5 est moins cher qu'Opus 5,
# et le cache de Fable 5.1 coûte 0.025x au lieu de 0.1x.
# Changer un prix n'affecte QUE les audits à venir : le coût est figé dans meta.cost du
# cr_*.json au moment de l'audit, et la KB le relit tel quel (hexa/benches/*/kb/normalizer.py).
# 2026-11-16 : ajout de Fable 5.2, Sonnet 5.5 (cache 0.05x), Haiku 5.5 et des familles
# GPT-6 / GPT-5.6, relevés sur les pages officielles (Anthropic et OpenAI, palier standard,
# contexte court). GPT 5.5 corrigé (2/12 → 5/30). Haiku 5.5 a deux paliers selon la taille
# du prompt ; une session d'agent dépasse 100k tokens, on retient donc le palier haut.
# Les runs déjà publiés gardent le coût figé à leur audit (p. ex. gpt-5.6-sol tarifé comme
# « gpt-5 », Sonnet 5.5 avec le cache de Sonnet 5) : ne pas les recalculer.
PRICING_UPDATED = "2026-11-16 (pages de tarifs officielles Anthropic et OpenAI)"
MODEL_PRICING = {
    "claude-fable-5-2": {"input": 8.0, "output": 40.0, "cached_input": 0.20},
    "claude-fable-5-1": {"input": 10.0, "output": 50.0, "cached_input": 0.25},
    "claude-fable": {"input": 10.0, "output": 50.0, "cached_input": 1.0},
    "claude-opus-5-5": {"input": 4.0, "output": 20.0, "cached_input": 0.20},
    "claude-opus": {"input": 5.0, "output": 25.0, "cached_input": 0.50},
    "claude-sonnet-5-5": {"input": 2.0, "output": 10.0, "cached_input": 0.10},
    "claude-sonnet": {"input": 2.0, "output": 10.0, "cached_input": 0.20},
    "claude-haiku-5-5": {"input": 0.50, "output": 2.50, "cached_input": 0.05},
    "claude-haiku": {"input": 1.0, "output": 5.0, "cached_input": 0.10},
    "gpt-6-astra": {"input": 10.0, "output": 50.0, "cached_input": 1.0},
    "gpt-6.1-sol": {"input": 2.0, "output": 10.0, "cached_input": 0.10},
    "gpt-6.1-terra": {"input": 1.0, "output": 5.0, "cached_input": 0.05},
    "gpt-6-sol": {"input": 2.0, "output": 10.0, "cached_input": 0.20},
    "gpt-6-luna": {"input": 0.10, "output": 0.50, "cached_input": 0.01},
    "gpt-5.6-sol": {"input": 4.0, "output": 20.0, "cached_input": 0.40},
    "gpt-5.6-terra": {"input": 2.0, "output": 12.0, "cached_input": 0.20},
    "gpt-5.6-luna": {"input": 0.20, "output": 1.20, "cached_input": 0.02},
    "gpt-5.5": {"input": 5.0, "output": 30.0, "cached_input": 0.50},
    "gpt-5": {"input": 1.25, "output": 10.0, "cached_input": 0.125},
    "gemini-flash": {"input": 0.30, "output": 2.50, "cached_input": 0.03},
    "gemini-pro": {"input": 1.25, "output": 10.0, "cached_input": 0.125},
}

# Session cost bands ($, whole session). Cheap = full marks. Ordered ascending; the
# first band whose [min,max] contains the value wins.
COST_USD_BANDS = [
    {"min": 0.0, "max": 0.50, "score_ratio": 1.0, "status": "OK", "label": "très frugal"},
    {"min": 0.0, "max": 1.50, "score_ratio": 0.75, "status": "OK", "label": "frugal"},
    {"min": 0.0, "max": 3.00, "score_ratio": 0.50, "status": "PARTIEL", "label": "modéré"},
    {"min": 0.0, "max": 6.00, "score_ratio": 0.25, "status": "PARTIEL", "label": "coûteux"},
]  # > $6 → 0

# Model-agnostic fallback when the model is absent from MODEL_PRICING (operator gap,
# not the agent's fault): score frugality on total tokens instead of $.
TOTAL_TOKENS_BANDS = [
    {"min": 0, "max": 150000, "score_ratio": 1.0, "status": "OK", "label": "très frugal"},
    {"min": 0, "max": 400000, "score_ratio": 0.75, "status": "OK", "label": "frugal"},
    {"min": 0, "max": 900000, "score_ratio": 0.50, "status": "PARTIEL", "label": "modéré"},
    {"min": 0, "max": 2000000, "score_ratio": 0.25, "status": "PARTIEL", "label": "coûteux"},
]


BONUS_MALUS_SCORE_CONFIG = {
    "phase_number": 4,
    "phase_label": "Bonus / Malus",
    "bonus_cap": 5,
    "malus_cap": -10,
}


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
            {
                "min": 300,
                "max": 3600,
                "score_ratio": 0.5,
                "status": "PARTIEL",
                "label": "tolerated",
            },
        ],
    },
}


# Scoring v3 — la session est censée être entièrement autonome (énoncé) : un seul échange
# User <-> Agent est la cible, pas une anomalie. Bandes v2 (5..15 = 100 %) laissées intactes
# pour que --scoring v2 rejoue les scores publiés.
TRACE_TURNS_BANDS_V3 = [
    {"min": 1, "max": 2, "score_ratio": 1.0, "status": "OK", "label": "autonome"},
    {"min": 3, "max": 6, "score_ratio": 0.5, "status": "PARTIEL", "label": "quelques relances"},
]
TRACE_TURNS_BANDS_LABEL_V3 = "1..2=100%, 3..6=50%, else=0%"


def trace_scoring_config(scoring_version: str) -> dict:
    """Bandes d'efficacité de session (phase 3) applicables à une version de scoring."""
    if scoring_version in ("v1", "v2"):
        return TRACE_SCORING_CONFIG
    return {
        **TRACE_SCORING_CONFIG,
        "total_turns": {
            **TRACE_SCORING_CONFIG["total_turns"],
            "bands_label": TRACE_TURNS_BANDS_LABEL_V3,
            "bands": TRACE_TURNS_BANDS_V3,
        },
    }
