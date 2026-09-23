"""Traçabilité de session : validation de audit_trace.json et métriques auto-déclarées.

Commun à tous les benchmarks : le format de audit_trace.json ne dépend pas du défi.
"""

import json
import os
from typing import Any

from engine.formatting import _first_non_empty, _format_number, _parse_iso_datetime, _to_float
from engine.indicators import _append_indicator, _append_scored_indicator_from_config
from scoring_config import TRACE_SCORING_CONFIG


def _build_trace_metrics(traceability: dict[str, Any]) -> dict[str, Any]:
    metrics = {
        "phases_count": traceability.get("phases_count", 0),
        "total_turns": None,
        "total_tool_calls": None,
        "total_wall_time_seconds": None,
        "total_input_tokens": None,
        "total_output_tokens": None,
        "total_cached_input_tokens": None,
        "model": None,
        "trace_errors_count": len(traceability.get("errors", [])),
    }
    data = traceability.get("data", {})
    summary = data.get("summary", {})
    phases = data.get("phases", [])
    meta = data.get("meta", {})

    if isinstance(meta, dict):
        metrics["model"] = _first_non_empty(meta.get("model")) or None

    if summary:
        metrics["total_turns"] = _to_float(summary.get("total_turns"))
        metrics["total_tool_calls"] = _to_float(summary.get("total_tool_calls"))
        metrics["total_wall_time_seconds"] = _to_float(summary.get("total_wall_time_seconds"))
        metrics["total_input_tokens"] = _to_float(summary.get("total_input_tokens"))
        metrics["total_output_tokens"] = _to_float(summary.get("total_output_tokens"))
        metrics["total_cached_input_tokens"] = _to_float(summary.get("total_cached_input_tokens"))

    if not isinstance(phases, list) or not phases:
        return metrics

    durations: list[float] = []
    turns: list[float] = []
    tool_calls: list[float] = []

    for phase in phases:
        if not isinstance(phase, dict):
            continue

        start_dt = _parse_iso_datetime(phase.get("start_time", ""))
        end_dt = _parse_iso_datetime(phase.get("end_time", ""))
        if start_dt and end_dt:
            durations.append((end_dt - start_dt).total_seconds())

        # Support both new field names (turns_in_phase) and legacy (turns_in_step)
        p_turns = _to_float(phase.get("turns_in_phase") or phase.get("turns_in_step"))
        if p_turns is not None:
            turns.append(p_turns)

        p_tools = _to_float(phase.get("tool_calls_in_phase") or phase.get("tool_calls_in_step"))
        if p_tools is not None:
            tool_calls.append(p_tools)

    if metrics["total_turns"] is None and turns:
        metrics["total_turns"] = sum(turns)
    if metrics["total_tool_calls"] is None and tool_calls:
        metrics["total_tool_calls"] = sum(tool_calls)
    if metrics["total_wall_time_seconds"] is None and durations:
        metrics["total_wall_time_seconds"] = sum(durations)

    return metrics


def emit_trace_indicators(
    audit_db: dict[str, Any], traceability: dict[str, Any], trace_metrics: dict[str, Any]
) -> None:
    """Phase 3 — Traçabilité : validité de audit_trace.json puis efficacité en bandes.

    Les valeurs viennent de l'agent audité (loi n°4) : elles sont validées, pas mesurées.
    """
    trace_valid = traceability["status"] == "OK"
    _append_indicator(
        audit_db,
        3,
        "Traçabilité",
        1,
        "Validation audit_trace.json",
        "Validation audit_trace.json",
        trace_valid,
        _first_non_empty(
            f"phases_count={traceability.get('phases_count', 0)}" if trace_valid else None,
            traceability.get("error"),
            traceability.get("status"),
        ),
        details=traceability,
        weight=1,
    )
    _append_indicator(
        audit_db,
        3,
        "Traçabilité",
        1,
        "Validation audit_trace.json",
        "Nombre de phases tracées >= 1",
        traceability.get("phases_count", 0) >= 1,
        f"phases_count={traceability.get('phases_count', 0)}",
        details=traceability,
        weight=2,
    )
    wall_time_consistency = traceability.get("wall_time_consistency", {})
    wall_time_status = wall_time_consistency.get("status")
    _append_indicator(
        audit_db,
        3,
        "Traçabilité",
        1,
        "Validation audit_trace.json",
        "Cohérence wall time",
        wall_time_status == "OK",
        wall_time_consistency.get("remarks", "not enough valid timing data"),
        status="SKIPPED" if wall_time_status == "SKIPPED" else None,
        details=wall_time_consistency,
        weight=2,
    )
    for metric_key, config in TRACE_SCORING_CONFIG.items():
        _append_scored_indicator_from_config(
            audit_db,
            config,
            trace_metrics.get(metric_key),
            trace_or_stats_present=trace_metrics.get(metric_key) is not None,
        )


class TraceabilityValidator:
    def __init__(self, target_path: str):
        self.target_path = target_path
        self.trace_file = os.path.join(target_path, "audit_trace.json")

    def validate(self) -> dict[str, Any]:
        if not os.path.exists(self.trace_file):
            return {"status": "KO", "error": "audit_trace.json not found", "phases_count": 0}
        try:
            with open(self.trace_file, encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                return {
                    "status": "KO",
                    "error": "audit_trace.json root must be an object",
                    "phases_count": 0,
                }

            errors: list[str] = []
            wall_time_consistency: dict[str, Any] = {
                "status": "SKIPPED",
                "summary_total_wall_time_seconds": None,
                "phases_total_wall_time_seconds": None,
                "delta_ratio": None,
                "remarks": "not enough valid timing data",
            }
            phases = data.get("phases", [])
            summary = data.get("summary")
            meta = data.get("meta")

            if not isinstance(meta, dict):
                errors.append("meta must be an object")
            else:
                if not _first_non_empty(meta.get("prompt_version")):
                    errors.append("meta.prompt_version is required")
                if not _first_non_empty(meta.get("model")):
                    errors.append("meta.model is required")

            if not isinstance(summary, dict):
                errors.append("summary must be an object")
            else:
                for key in ("total_turns", "total_tool_calls", "total_wall_time_seconds"):
                    value = _to_float(summary.get(key))
                    if value is None or value <= 0:
                        errors.append(f"summary.{key} must be a positive number")

            if not isinstance(phases, list) or not phases:
                errors.append("phases must be a non-empty array")
                phases = []

            for index, phase in enumerate(phases, start=1):
                if not isinstance(phase, dict):
                    errors.append(f"phases[{index}] must be an object")
                    continue

                start_dt = _parse_iso_datetime(str(phase.get("start_time", "")))
                end_dt = _parse_iso_datetime(str(phase.get("end_time", "")))
                if not start_dt:
                    errors.append(f"phases[{index}].start_time must be ISO-8601")
                if not end_dt:
                    errors.append(f"phases[{index}].end_time must be ISO-8601")
                if start_dt and end_dt and end_dt < start_dt:
                    errors.append(f"phases[{index}].end_time must be >= start_time")

                for key in ("turns_in_phase", "tool_calls_in_phase"):
                    value = _to_float(phase.get(key))
                    if value is None or value < 0:
                        errors.append(f"phases[{index}].{key} must be a non-negative number")

            if not errors and isinstance(summary, dict) and phases:
                phase_turns_total = sum(
                    _to_float(phase.get("turns_in_phase")) or 0.0 for phase in phases
                )
                phase_tools_total = sum(
                    _to_float(phase.get("tool_calls_in_phase")) or 0.0 for phase in phases
                )
                phase_wall_time_total = 0.0
                for phase in phases:
                    start_dt = _parse_iso_datetime(str(phase.get("start_time", "")))
                    end_dt = _parse_iso_datetime(str(phase.get("end_time", "")))
                    if start_dt and end_dt:
                        phase_wall_time_total += (end_dt - start_dt).total_seconds()

                consistency_checks = [
                    (
                        "summary.total_turns",
                        _to_float(summary.get("total_turns")),
                        phase_turns_total,
                    ),
                    (
                        "summary.total_tool_calls",
                        _to_float(summary.get("total_tool_calls")),
                        phase_tools_total,
                    ),
                ]
                for label, summary_value, phase_total in consistency_checks:
                    if summary_value is None:
                        continue
                    if phase_total <= 0:
                        continue
                    delta_ratio = abs(summary_value - phase_total) / phase_total
                    if delta_ratio > 0.10:
                        errors.append(
                            f"{label} differs from summed phases by more than 10% "
                            f"(summary={_format_number(summary_value)}, phases={_format_number(phase_total)})"
                        )

                summary_wall_time = _to_float(summary.get("total_wall_time_seconds"))
                wall_time_consistency = {
                    "status": "SKIPPED",
                    "summary_total_wall_time_seconds": summary_wall_time,
                    "phases_total_wall_time_seconds": phase_wall_time_total,
                    "delta_ratio": None,
                    "remarks": "not enough valid timing data",
                }
                if summary_wall_time is not None and phase_wall_time_total > 0:
                    delta_ratio = (
                        abs(summary_wall_time - phase_wall_time_total) / phase_wall_time_total
                    )
                    ok = delta_ratio <= 0.10
                    wall_time_consistency = {
                        "status": "OK" if ok else "KO",
                        "summary_total_wall_time_seconds": summary_wall_time,
                        "phases_total_wall_time_seconds": phase_wall_time_total,
                        "delta_ratio": delta_ratio,
                        "remarks": (
                            "summary.total_wall_time_seconds coherent with summed phases"
                            if ok
                            else (
                                "summary.total_wall_time_seconds differs from summed phases by more than 10% "
                                f"(summary={_format_number(summary_wall_time)}, phases={_format_number(phase_wall_time_total)})"
                            )
                        ),
                    }

            if errors:
                return {
                    "status": "KO",
                    "error": "; ".join(errors),
                    "errors": errors,
                    "phases_count": len(phases),
                    "data": data,
                    "wall_time_consistency": wall_time_consistency,
                }

            return {
                "status": "OK",
                "phases_count": len(phases),
                "data": data,
                "errors": [],
                "wall_time_consistency": wall_time_consistency,
            }
        except Exception as e:
            return {"status": "KO", "error": str(e), "phases_count": 0}
