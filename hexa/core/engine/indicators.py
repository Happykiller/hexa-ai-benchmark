"""Registre d'indicateurs : phases, étapes, indicateurs pondérés (Fibonacci) et bandes.

Indépendant du défi audité : c'est la grammaire commune de tous les rapports cr_*.json.
"""

from typing import Any

from hexa.core.engine.formatting import _format_number, _to_float


def _aggregate_status(statuses: list[str]) -> str:
    if not statuses:
        return "INCONNU"
    if any(status in ("KO", "MALUS", "DETECTE") for status in statuses):
        return "KO"
    if any(status == "PARTIEL" for status in statuses):
        return "PARTIEL"
    if all(status == "SKIPPED" for status in statuses):
        return "SKIPPED"
    if any(status == "OK" for status in statuses):
        return "OK"
    return statuses[0]


def _fibonacci(index: int) -> int:
    if index <= 0:
        return 0
    if index == 1:
        return 1
    if index == 2:
        return 2
    a, b = 1, 2
    for _ in range(3, index + 1):
        a, b = b, a + b
    return b


def _score_from_bands(value: Any, bands: list[dict[str, Any]]) -> dict[str, Any]:
    numeric = _to_float(value)
    if numeric is None:
        return {
            "status": "SKIPPED",
            "score_ratio": 0.0,
            "remarks": "value is not numeric",
        }

    def in_band(min_value: float | None, max_value: float | None) -> bool:
        if min_value is not None and numeric < min_value:
            return False
        if max_value is not None and numeric > max_value:
            return False
        return True

    for band in bands:
        min_value = band.get("min")
        max_value = band.get("max")
        if in_band(min_value, max_value):
            min_text = "-inf" if min_value is None else _format_number(min_value)
            max_text = "+inf" if max_value is None else _format_number(max_value)
            return {
                "status": band["status"],
                "score_ratio": band["score_ratio"],
                "remarks": f"value={_format_number(numeric)}; tranche={min_text}..{max_text}; label={band['label']}",
            }

    return {
        "status": "KO",
        "score_ratio": 0.0,
        "remarks": f"value={_format_number(numeric)}; tranche=out_of_range",
    }


def _append_scored_indicator_from_config(
    audit_db: dict[str, Any],
    config: dict[str, Any],
    measured_value: Any,
    trace_or_stats_present: bool = True,
    as_measured: bool = False,
) -> None:
    band_result = _score_from_bands(measured_value, config["bands"])

    remarks = band_result["remarks"]
    if "description" in config:
        remarks = f"{config['description']} | {remarks}"

    _append_indicator(
        audit_db,
        config["phase_number"],
        config["phase_label"],
        config["step_number"],
        config["step_label"],
        config["name"],
        band_result["score_ratio"] > 0,
        remarks,
        polarity=config.get("polarity", "positive"),
        status="MESURE"
        if as_measured
        else (band_result["status"] if trace_or_stats_present else "SKIPPED"),
        kind="measured" if as_measured else "scored",
        details={
            "measured_value": measured_value,
            "bands": config["bands_label"],
        },
        score_ratio=band_result["score_ratio"] if trace_or_stats_present else 0.0,
        measured_value=measured_value,
        weight=config.get("weight"),
    )


def _phase_entry(audit_db: dict[str, Any], phase_number: int, phase_label: str) -> dict[str, Any]:
    for phase in audit_db["phases"]:
        if phase["number"] == phase_number:
            return phase
    phase = {
        "number": phase_number,
        "code": str(phase_number),
        "label": phase_label,
        "status": "PENDING",
        "steps": [],
        "positive_points_earned": 0,
        "positive_points_possible": 0,
        "negative_points": 0,
        "raw_total": 0,
    }
    audit_db["phases"].append(phase)
    return phase


def _step_entry(phase: dict[str, Any], step_number: int, step_label: str) -> dict[str, Any]:
    for step in phase["steps"]:
        if step["number"] == step_number and step["label"] == step_label:
            return step
    step = {
        "number": step_number,
        "code": f"{phase['number']}-{step_number}",
        "label": step_label,
        "status": "PENDING",
        "indicators": [],
        "positive_points_earned": 0,
        "positive_points_possible": 0,
        "negative_points": 0,
        "raw_total": 0,
    }
    phase["steps"].append(step)
    return step


def _append_indicator(
    audit_db: dict[str, Any],
    phase_number: int,
    phase_label: str,
    step_number: int,
    step_label: str,
    name: str,
    achieved: bool,
    remarks: str,
    polarity: str = "positive",
    status: str | None = None,
    details: dict[str, Any] | None = None,
    kind: str = "scored",
    measured_value: Any | None = None,
    score_ratio: float = 1.0,
    rank: int | None = None,
    weight: float | None = None,
) -> dict[str, Any]:
    phase = _phase_entry(audit_db, phase_number, phase_label)
    step = _step_entry(phase, step_number, step_label)
    indicator_number = len(step["indicators"]) + 1

    if weight is not None:
        actual_weight = weight
    else:
        fibonacci_rank = rank if rank is not None else indicator_number
        actual_weight = _fibonacci(fibonacci_rank)

    if kind == "measured":
        if status is None:
            status = "MESURE"
        score = None
        max_score = None
    else:
        if status is None:
            if polarity == "negative":
                status = "DETECTE" if achieved else "NON_DETECTE"
            else:
                status = "OK" if achieved else "KO"

        score = 0
        if status != "SKIPPED":
            if polarity == "negative":
                score = -round(actual_weight * score_ratio, 2) if achieved else 0
            else:
                score = round(actual_weight * score_ratio, 2) if achieved else 0
        max_score = actual_weight

    indicator = {
        "phase_number": phase_number,
        "phase_label": phase_label,
        "step_number": step_number,
        "step_label": step_label,
        "indicator_number": indicator_number,
        "code": f"{phase_number}-{step_number}-{indicator_number}",
        "name": name,
        "status": status,
        "kind": kind,
        "polarity": polarity,
        "fibonacci_rank": rank or indicator_number,
        "max_score": max_score,
        "score": score,
        "measured_value": measured_value,
        "remarks": remarks,
        "details": details or {},
    }
    step["indicators"].append(indicator)
    audit_db["indicators"].append(indicator)
    return indicator
