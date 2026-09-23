"""Agrégation du score : piliers (buckets), bonus/malus, plafond et caps éliminatoires.

Les barèmes par défaut sont ceux de la Todo List (scoring_config) ; un autre benchmark
fournit les siens en paramètres. Ne jamais changer un défaut sans ré-auditer les runs
publiés (loi n°2) — auditor/tests/test_engine_regression.py rejoue des rapports réels.
"""

from typing import Any

from engine.indicators import _aggregate_status
from scoring_config import (
    BASE_SCORE_BUCKETS,
    BASE_SCORE_BUCKETS_BY_VERSION,
    BONUS_HEADROOM_FRACTION,
    BONUS_MALUS_SCORE_CONFIG,
    SCORING_DEFAULT_VERSION,
)


def _compute_score_caps(raw_percentage: float, reasons: list[dict[str, Any]]) -> dict[str, Any]:
    applied_caps = [
        {
            "id": reason["id"],
            "applied": True,
            "max_percentage": reason["max_percentage"],
            "reason": reason["reason"],
        }
        for reason in reasons
    ]

    final_percentage = raw_percentage
    if applied_caps:
        final_percentage = min(raw_percentage, min(cap["max_percentage"] for cap in applied_caps))

    return {
        "raw_percentage": raw_percentage,
        "final_percentage": round(final_percentage, 2),
        "caps": applied_caps,
        "capped": bool(applied_caps and final_percentage < raw_percentage),
    }


def _indicator_matches_selector(indicator: dict[str, Any], selector: dict[str, Any]) -> bool:
    if indicator.get("phase_number") != selector.get("phase"):
        return False
    steps = selector.get("steps")
    if steps is None:
        return True
    return indicator.get("step_number") in steps


def _compute_bucket_score(
    indicators: list[dict[str, Any]],
    weight: float,
    selectors: list[dict[str, Any]],
) -> dict[str, Any]:
    matched = [
        indicator
        for indicator in indicators
        if indicator["kind"] == "scored"
        and any(_indicator_matches_selector(indicator, selector) for selector in selectors)
    ]

    positive_possible = sum(
        indicator["max_score"]
        for indicator in matched
        if indicator["polarity"] == "positive" and indicator["max_score"] is not None
    )
    raw_total = sum(indicator["score"] for indicator in matched if indicator["score"] is not None)
    ratio = 0.0 if not positive_possible else raw_total / positive_possible
    normalized = round(max(0.0, min(weight, ratio * weight)), 2)

    return {
        "raw_total": raw_total,
        "positive_possible": positive_possible,
        "ratio": round(ratio, 4) if positive_possible else 0.0,
        "normalized_score": normalized,
        "weight": weight,
    }


def _compute_bonus_malus_adjustment(
    audit_db: dict[str, Any], bonus_malus_config: dict[str, Any] | None = None
) -> dict[str, Any]:
    config = bonus_malus_config or BONUS_MALUS_SCORE_CONFIG
    phase_number = config["phase_number"]
    bonus_cap = config["bonus_cap"]
    malus_cap = config["malus_cap"]

    bonus_raw = 0.0
    malus_raw = 0.0
    net_raw = 0.0
    for phase in audit_db["phases"]:
        if phase["number"] == phase_number:
            bonus_raw = float(phase.get("positive_points_earned", 0) or 0)  # >= 0
            malus_raw = float(phase.get("negative_points", 0) or 0)  # <= 0
            net_raw = float(phase.get("raw_total", bonus_raw + malus_raw) or 0)
            break

    # v1 clamps the *net* adjustment to [malus_cap, bonus_cap]; kept for reproducibility.
    capped_adjustment = max(malus_cap, min(bonus_cap, net_raw))
    # v2 caps bonus and malus independently so the ceiling rule can apply them apart.
    capped_bonus = max(0.0, min(bonus_cap, bonus_raw))  # 0 .. +bonus_cap
    capped_malus = max(malus_cap, min(0.0, malus_raw))  # malus_cap .. 0
    return {
        "raw_adjustment": round(net_raw, 2),
        "capped_adjustment": round(capped_adjustment, 2),
        "bonus_raw": round(bonus_raw, 2),
        "malus_raw": round(malus_raw, 2),
        "capped_bonus": round(capped_bonus, 2),
        "capped_malus": round(capped_malus, 2),
        "bonus_cap": bonus_cap,
        "malus_cap": malus_cap,
    }


def _compute_final_score_summary(
    audit_db: dict[str, Any],
    scoring_version: str = SCORING_DEFAULT_VERSION,
    buckets: dict[str, dict[str, Any]] | None = None,
    bonus_malus_config: dict[str, Any] | None = None,
    ceiling_rule: str | None = None,
) -> dict[str, Any]:
    """Score final à partir des indicateurs.

    ``scoring_version`` est l'étiquette du barème publiée dans le rapport ; ``buckets`` et
    ``bonus_malus_config`` le décrivent (défaut : barème Todo de cette version) ;
    ``ceiling_rule`` choisit la règle de plafond du bonus (``"v1"`` saturation historique,
    ``"v2"`` plafond réservé), déduite de la version quand elle n'est pas fournie. Un autre
    benchmark passe ainsi son propre barème sans toucher aux tables de la Todo List.
    """
    bucket_scores: dict[str, dict[str, Any]] = {}
    base_score = 0.0
    base_weight_total = 0.0

    if buckets is None:
        buckets = BASE_SCORE_BUCKETS_BY_VERSION.get(scoring_version, BASE_SCORE_BUCKETS)
    if ceiling_rule is None:
        ceiling_rule = "v1" if scoring_version == "v1" else "v2"
    for key, config in buckets.items():
        bucket_score = _compute_bucket_score(
            audit_db["indicators"],
            config["weight"],
            config["selectors"],
        )
        bucket_score["label"] = config["label"]
        bucket_scores[key] = bucket_score
        base_score += bucket_score["normalized_score"]
        base_weight_total += config["weight"]

    adjustment = _compute_bonus_malus_adjustment(audit_db, bonus_malus_config)

    if ceiling_rule == "v1":
        # Legacy: net bonus/malus added to the base, then clamped. Bonus can complete
        # an imperfect base to 100% (saturation).
        effective_bonus = None
        raw_percentage = round(
            max(0.0, min(100.0, base_score + adjustment["capped_adjustment"])), 2
        )
    else:
        # v2 reserved ceiling: maluses apply fully; the bonus may only fill a fraction
        # of the remaining gap to 100, so 100% is unreachable unless the base is flawless.
        after_malus = base_score + adjustment["capped_malus"]
        headroom = max(0.0, 100.0 - after_malus)
        effective_bonus = round(
            min(adjustment["capped_bonus"], headroom * BONUS_HEADROOM_FRACTION), 2
        )
        raw_percentage = round(max(0.0, min(100.0, after_malus + effective_bonus)), 2)

    adjustment["scoring_version"] = scoring_version
    adjustment["effective_bonus"] = effective_bonus

    caps_result = _compute_score_caps(
        raw_percentage,
        audit_db["meta"].get("score_cap_reasons", []),
    )

    return {
        "scoring_version": scoring_version,
        "base_score": round(base_score, 2),
        "base_weight_total": round(base_weight_total, 2),
        "bonus_malus": adjustment,
        "bucket_scores": bucket_scores,
        "raw_percentage": caps_result["raw_percentage"],
        "final_percentage": caps_result["final_percentage"],
        "score_caps": caps_result["caps"],
        "score_capped": caps_result["capped"],
    }


def _finalize_audit_db(
    audit_db: dict[str, Any],
    scoring_version: str = SCORING_DEFAULT_VERSION,
    buckets: dict[str, dict[str, Any]] | None = None,
    bonus_malus_config: dict[str, Any] | None = None,
    ceiling_rule: str | None = None,
) -> None:
    for phase in audit_db["phases"]:
        phase_statuses: list[str] = []
        phase_positive_earned = 0
        phase_positive_possible = 0
        phase_negative_points = 0
        phase_raw_total = 0

        for step in phase["steps"]:
            step_statuses = [indicator["status"] for indicator in step["indicators"]]
            step["status"] = _aggregate_status(step_statuses)
            step["positive_points_earned"] = sum(
                indicator["score"]
                for indicator in step["indicators"]
                if indicator["kind"] == "scored"
                and indicator["polarity"] == "positive"
                and indicator["score"] > 0
            )
            step["positive_points_possible"] = sum(
                indicator["max_score"]
                for indicator in step["indicators"]
                if indicator["kind"] == "scored" and indicator["polarity"] == "positive"
            )
            step["negative_points"] = sum(
                indicator["score"]
                for indicator in step["indicators"]
                if indicator["kind"] == "scored"
                and indicator["score"] is not None
                and indicator["score"] < 0
            )
            step["raw_total"] = sum(
                indicator["score"]
                for indicator in step["indicators"]
                if indicator["kind"] == "scored" and indicator["score"] is not None
            )

            phase_statuses.append(step["status"])
            phase_positive_earned += step["positive_points_earned"]
            phase_positive_possible += step["positive_points_possible"]
            phase_negative_points += step["negative_points"]
            phase_raw_total += step["raw_total"]

        phase["status"] = _aggregate_status(phase_statuses)
        phase["positive_points_earned"] = phase_positive_earned
        phase["positive_points_possible"] = phase_positive_possible
        phase["negative_points"] = phase_negative_points
        phase["raw_total"] = phase_raw_total

    positive_points_earned = sum(
        indicator["score"]
        for indicator in audit_db["indicators"]
        if indicator["kind"] == "scored"
        and indicator["polarity"] == "positive"
        and indicator["score"] > 0
    )
    positive_points_possible = sum(
        indicator["max_score"]
        for indicator in audit_db["indicators"]
        if indicator["kind"] == "scored" and indicator["polarity"] == "positive"
    )
    negative_points = sum(
        indicator["score"]
        for indicator in audit_db["indicators"]
        if indicator["kind"] == "scored"
        and indicator["score"] is not None
        and indicator["score"] < 0
    )
    raw_total = sum(
        indicator["score"]
        for indicator in audit_db["indicators"]
        if indicator["kind"] == "scored" and indicator["score"] is not None
    )
    percentage_net = (
        round((raw_total / positive_points_possible) * 100, 2) if positive_points_possible else 0.0
    )
    final_score = _compute_final_score_summary(
        audit_db, scoring_version, buckets, bonus_malus_config, ceiling_rule
    )

    # Value metric: quality points per dollar (decision-relevant, informational only —
    # not scored, to avoid circularity with the cost bucket).
    cost_info = audit_db.get("meta", {}).get("cost", {})
    cost_usd = cost_info.get("cost_usd")
    cost_efficiency = (
        round(final_score["final_percentage"] / cost_usd, 2)
        if isinstance(cost_usd, (int, float)) and cost_usd > 0
        else None
    )

    audit_db["summary"] = {
        "raw_total_score": raw_total,
        "positive_points_earned": positive_points_earned,
        "positive_points_possible": positive_points_possible,
        "negative_points": negative_points,
        "legacy_percentage_net": percentage_net,
        "scoring_version": final_score["scoring_version"],
        "cost_usd": cost_usd,
        "total_tokens": cost_info.get("total_tokens"),
        "cost_efficiency_pct_per_usd": cost_efficiency,
        "normalized_base_score": final_score["base_score"],
        "normalized_base_weight_total": final_score["base_weight_total"],
        "bonus_malus_adjustment": final_score["bonus_malus"],
        "bucket_scores": final_score["bucket_scores"],
        "percentage_net": final_score["final_percentage"],
        "raw_percentage_net": final_score["raw_percentage"],
        "score_caps": final_score["score_caps"],
        "score_capped": final_score["score_capped"],
        "indicators_count": len(audit_db["indicators"]),
        "measured_indicators_count": sum(
            1 for indicator in audit_db["indicators"] if indicator["kind"] == "measured"
        ),
        "scored_indicators_count": sum(
            1 for indicator in audit_db["indicators"] if indicator["kind"] == "scored"
        ),
    }
    audit_db["points"] = [
        {
            "id": phase["number"],
            "label": phase["label"],
            "status": phase["status"],
            "score": phase["raw_total"],
            "max_score": phase["positive_points_possible"],
            "positive_points_earned": phase["positive_points_earned"],
            "positive_points_possible": phase["positive_points_possible"],
            "negative_points": phase["negative_points"],
        }
        for phase in audit_db["phases"]
    ]
