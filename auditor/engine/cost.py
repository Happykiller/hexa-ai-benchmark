"""Coût de session : tokens auto-déclarés × table de prix (commun à tous les benchmarks)."""

import re
from typing import Any

from engine.indicators import _append_indicator, _score_from_bands
from scoring_config import (
    COST_SCORE_PHASE,
    COST_SCORE_PHASE_LABEL,
    COST_SCORE_STEP_LABEL,
    COST_USD_BANDS,
    MODEL_PRICING,
    PRICING_UPDATED,
    TOTAL_TOKENS_BANDS,
)


def _normalize_model_id(model_id: str | None) -> str | None:
    """Map a free-form meta.model string to a MODEL_PRICING key (best-effort)."""
    if not model_id:
        return None
    s = str(model_id).lower()
    # Versioned entries first: a successor priced differently from its family must not
    # fall into the generic family key (Opus 5.5 ≠ Opus 5, Fable 5.1 cache ≠ Fable 5).
    if "fable" in s and re.search(r"fable[-_ ]?5[-_.]1", s):
        return "claude-fable-5-1"
    if "fable" in s:
        return "claude-fable"
    if "opus" in s and re.search(r"opus[-_ ]?5[-_.]5", s):
        return "claude-opus-5-5"
    if "opus" in s:
        return "claude-opus"
    if "sonnet" in s:
        return "claude-sonnet"
    if "haiku" in s:
        return "claude-haiku"
    if "gpt" in s and "5.5" in s:
        return "gpt-5.5"
    if ("gpt" in s and "5" in s) or "codex" in s:  # Codex CLI is GPT-5-based
        return "gpt-5"
    if "gemini" in s and "pro" in s:
        return "gemini-pro"
    if "gemini" in s:
        return "gemini-flash"
    return None


def _compute_session_cost(
    trace_metrics: dict[str, Any],
    model_id: str | None,
    pricing_table: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    """Compute session cost from agent-reported tokens × the per-model price table.
    Returns cost_usd=None when the model isn't priced or no tokens were reported."""
    inp = trace_metrics.get("total_input_tokens")
    out = trace_metrics.get("total_output_tokens")
    cached = trace_metrics.get("total_cached_input_tokens") or 0
    total_tokens = None
    if inp is not None or out is not None:
        total_tokens = (inp or 0) + (out or 0)

    key = _normalize_model_id(model_id)
    table = MODEL_PRICING if pricing_table is None else pricing_table
    pricing = table.get(key) if key else None
    cost_usd = None
    if pricing and total_tokens is not None:
        # Cached input tokens are a *subset* of total input, billed at the cheaper
        # cached rate; the rest of the input is billed at the full rate.
        non_cached_input = max(0.0, (inp or 0) - cached)
        cost_usd = round(
            non_cached_input / 1e6 * pricing["input"]
            + cached / 1e6 * pricing.get("cached_input", 0)
            + (out or 0) / 1e6 * pricing["output"],
            4,
        )
    return {
        "model_id": model_id,
        "model_key": key,
        "priced": pricing is not None,
        "pricing_updated": PRICING_UPDATED,
        "input_tokens": inp,
        "output_tokens": out,
        "cached_input_tokens": cached,
        "total_tokens": total_tokens,
        "cost_usd": cost_usd,
    }


def emit_cost_indicators(audit_db: dict[str, Any], trace_metrics: dict[str, Any]) -> dict[str, Any]:
    """Phase 6 — Coût : émet les indicateurs et renvoie cost_info (pour meta.cost)."""
    # Phase 6 — Cost pillar (scoring v2). Cost is computed from agent-reported tokens ×
    # the price table. Scored on $ when the model is priced; on raw tokens as a
    # model-agnostic fallback otherwise; SKIPPED (0) only when no tokens were reported.
    cost_info = _compute_session_cost(trace_metrics, trace_metrics.get("model"))
    if cost_info["cost_usd"] is not None:
        band = _score_from_bands(cost_info["cost_usd"], COST_USD_BANDS)
        _append_indicator(
            audit_db,
            COST_SCORE_PHASE,
            COST_SCORE_PHASE_LABEL,
            1,
            COST_SCORE_STEP_LABEL,
            "Coût total de la session ($)",
            band["score_ratio"] > 0,  # graduated: any scoring band earns weight×ratio
            f"cost_usd={cost_info['cost_usd']} (modèle={cost_info['model_key']}, prix {PRICING_UPDATED}); {band['remarks']}",
            score_ratio=band["score_ratio"],
            status=band["status"],
            weight=10,
            details=cost_info,
        )
    elif cost_info["total_tokens"] is not None:
        band = _score_from_bands(cost_info["total_tokens"], TOTAL_TOKENS_BANDS)
        _append_indicator(
            audit_db,
            COST_SCORE_PHASE,
            COST_SCORE_PHASE_LABEL,
            1,
            COST_SCORE_STEP_LABEL,
            "Frugalité en tokens (modèle non tarifé)",
            band["score_ratio"] > 0,  # graduated: any scoring band earns weight×ratio
            f"total_tokens={cost_info['total_tokens']}; modèle '{cost_info['model_id']}' absent de la table de prix; {band['remarks']}",
            score_ratio=band["score_ratio"],
            status=band["status"],
            weight=10,
            details=cost_info,
        )
    else:
        _append_indicator(
            audit_db,
            COST_SCORE_PHASE,
            COST_SCORE_PHASE_LABEL,
            1,
            COST_SCORE_STEP_LABEL,
            "Coût total de la session ($)",
            False,
            "tokens absents de audit_trace.json (summary.total_input_tokens / total_output_tokens requis)",
            status="SKIPPED",
            weight=10,
            details=cost_info,
        )
    # Informational measures (not scored): total tokens and computed cost.
    _append_indicator(
        audit_db,
        COST_SCORE_PHASE,
        COST_SCORE_PHASE_LABEL,
        1,
        COST_SCORE_STEP_LABEL,
        "Tokens totaux (in+out)",
        False,
        str(cost_info["total_tokens"]),
        kind="measured",
        measured_value=cost_info["total_tokens"],
        details=cost_info,
    )
    return cost_info
