"""Invariants du barème b1 et du défi dreadhive_drone_mk1."""

import re

from PIL import Image

from hexa.benches.blender.auditor.bench_config import (
    BLENDER_SCORE_BUCKETS_B1,
    BUILD_SECONDS_BANDS,
    CAPS,
    DELTA_E_BANDS,
    DETAIL_BANDS,
    GLB_MB_BANDS,
    IOU_BANDS,
    PHASES,
)
from hexa.benches.blender.auditor.challenge import available_challenges, load_challenge


def test_bucket_weights_sum_to_100():
    assert sum(bucket["weight"] for bucket in BLENDER_SCORE_BUCKETS_B1.values()) == 100


def test_every_bucket_selects_a_known_phase():
    for bucket in BLENDER_SCORE_BUCKETS_B1.values():
        for selector in bucket["selectors"]:
            assert selector["phase"] in PHASES


def test_bands_are_well_formed():
    for bands in (BUILD_SECONDS_BANDS, GLB_MB_BANDS, IOU_BANDS, DELTA_E_BANDS, DETAIL_BANDS):
        assert bands[-1]["min"] is None and bands[-1]["max"] is None, (
            "dernière bande = attrape-tout"
        )
        for band in bands:
            assert 0.0 <= band["score_ratio"] <= 1.0


def test_caps_are_percentages():
    assert all(0 < value < 100 for value in CAPS.values())


def test_default_challenge_is_consistent(spec):
    challenge = load_challenge()
    assert challenge.id in available_challenges()
    assert challenge.concept_path.exists() and challenge.enonce_path.exists()
    assert f"`{challenge.prompt_version}`" in challenge.enonce_path.read_text(encoding="utf-8")
    width, height = Image.open(challenge.concept_path).size
    for view in spec["turnaround"]["views"].values():
        x0, y0, x1, y1 = view["box_px"]
        assert 0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height
    assert len(spec["palette"]) == 8
    assert all(re.fullmatch(r"#[0-9A-F]{6}", code) for code in spec["palette"].values())
    pattern = re.compile(spec["limbs"]["bone_pattern"])
    assert pattern.match("patte_2_01.R") and not pattern.match("patte_3_01.R")
    assert set(spec["animations"]["required"]) == {"idle", "walk"}
