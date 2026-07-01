"""Consistency guards for scoring_config.

These are pure-data invariants — they never touch the scoring *algorithm*, only assert
that the configuration tables stay internally coherent so an accidental edit (e.g. a
re-weighted bucket) is caught before a benchmark run rather than silently skewing scores.
"""

import pytest
from scoring_config import (
    BASE_SCORE_BUCKETS_BY_VERSION,
    BASE_SCORE_BUCKETS_V1,
    BASE_SCORE_BUCKETS_V2,
    BONUS_MALUS_SCORE_CONFIG,
    COST_USD_BANDS,
    MODEL_PRICING,
    TECHNICAL_STATS_SCORING_CONFIG,
    TOTAL_TOKENS_BANDS,
    TRACE_SCORING_CONFIG,
)


@pytest.mark.parametrize(
    "buckets",
    [BASE_SCORE_BUCKETS_V1, BASE_SCORE_BUCKETS_V2],
    ids=["v1", "v2"],
)
def test_base_bucket_weights_sum_to_100(buckets):
    total = sum(bucket["weight"] for bucket in buckets.values())
    assert total == 100, f"bucket weights must sum to 100, got {total}"


def test_bucket_versions_registry_matches_named_tables():
    assert BASE_SCORE_BUCKETS_BY_VERSION["v1"] is BASE_SCORE_BUCKETS_V1
    assert BASE_SCORE_BUCKETS_BY_VERSION["v2"] is BASE_SCORE_BUCKETS_V2


def _iter_all_bands():
    """Yield (label, band) for every band table in the scoring config."""
    for name, cfg in TRACE_SCORING_CONFIG.items():
        for band in cfg["bands"]:
            yield f"trace.{name}", band
    for name, cfg in TECHNICAL_STATS_SCORING_CONFIG.items():
        for band in cfg["bands"]:
            yield f"stats.{name}", band
    for band in COST_USD_BANDS:
        yield "cost_usd", band
    for band in TOTAL_TOKENS_BANDS:
        yield "total_tokens", band


def test_all_bands_are_well_formed():
    for label, band in _iter_all_bands():
        assert band["min"] <= band["max"], f"{label}: min > max in {band}"
        assert 0.0 <= band["score_ratio"] <= 1.0, f"{label}: score_ratio out of [0,1] in {band}"


def test_scored_configs_have_positive_weights():
    for name, cfg in {**TRACE_SCORING_CONFIG, **TECHNICAL_STATS_SCORING_CONFIG}.items():
        assert cfg["weight"] > 0, f"{name}: weight must be positive"


def test_model_pricing_entries_are_positive():
    assert MODEL_PRICING, "MODEL_PRICING must not be empty"
    for model, prices in MODEL_PRICING.items():
        for field in ("input", "output", "cached_input"):
            assert field in prices, f"{model}: missing price field {field!r}"
            assert prices[field] > 0, f"{model}: {field} price must be positive"


def test_bonus_malus_caps_have_expected_polarity():
    assert BONUS_MALUS_SCORE_CONFIG["bonus_cap"] > 0
    assert BONUS_MALUS_SCORE_CONFIG["malus_cap"] < 0
