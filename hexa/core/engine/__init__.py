"""Noyau commun des auditeurs hexa-ai-benchmark.

Grammaire des rapports (phases, étapes, indicateurs Fibonacci), agrégation en piliers,
caps, traçabilité de session et coût. Ne dépend d'aucun défi : la Todo List
(hexa/benches/todo) et le benchmark Blender (hexa/benches/blender) l'importent tous deux.
"""

from hexa.core.engine.cost import _compute_session_cost, _normalize_model_id, emit_cost_indicators
from hexa.core.engine.formatting import (
    _first_non_empty,
    _format_number,
    _md_cell,
    _parse_iso_datetime,
    _to_float,
)
from hexa.core.engine.indicators import (
    _aggregate_status,
    _append_indicator,
    _append_scored_indicator_from_config,
    _fibonacci,
    _phase_entry,
    _score_from_bands,
    _step_entry,
)
from hexa.core.engine.scoring import (
    _compute_bonus_malus_adjustment,
    _compute_bucket_score,
    _compute_final_score_summary,
    _compute_score_caps,
    _finalize_audit_db,
    _indicator_matches_selector,
)
from hexa.core.engine.traceability import (
    TraceabilityValidator,
    _build_trace_metrics,
    emit_trace_indicators,
)

__all__ = [
    "TraceabilityValidator",
    "_aggregate_status",
    "_append_indicator",
    "_append_scored_indicator_from_config",
    "_build_trace_metrics",
    "_compute_bonus_malus_adjustment",
    "_compute_bucket_score",
    "_compute_final_score_summary",
    "_compute_score_caps",
    "_compute_session_cost",
    "_fibonacci",
    "_finalize_audit_db",
    "_first_non_empty",
    "_format_number",
    "_indicator_matches_selector",
    "_md_cell",
    "_normalize_model_id",
    "_parse_iso_datetime",
    "_phase_entry",
    "_score_from_bands",
    "_step_entry",
    "_to_float",
    "emit_cost_indicators",
    "emit_trace_indicators",
]
