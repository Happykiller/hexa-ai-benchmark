"""Silhouettes, colorimétrie et qualité de rendu sur des images synthétiques."""

import numpy as np
from PIL import Image

from blender_bench.analysis.color import hex_to_rgb, nearest_delta_e, palette_lab, srgb_to_lab
from blender_bench.analysis.imagery import (
    concept_silhouette,
    iou,
    normalize_mask,
    remove_small_components,
    render_palette_delta_e,
    silhouette_scores,
)
from blender_bench.challenge import load_challenge


def test_iou_on_known_masks():
    a = np.zeros((10, 10), dtype=bool)
    b = np.zeros((10, 10), dtype=bool)
    a[:, :5] = True
    b[:, 2:7] = True
    assert iou(a, b) == 30 / 70
    assert iou(a, a) == 1.0


def test_normalization_is_scale_and_position_invariant():
    small = np.zeros((100, 100), dtype=bool)
    small[10:50, 20:40] = True
    big = np.zeros((600, 400), dtype=bool)
    big[200:400, 50:150] = True
    assert iou(normalize_mask(small), normalize_mask(big)) > 0.98


def test_small_components_are_removed():
    mask = np.zeros((100, 100), dtype=bool)
    mask[10:60, 10:60] = True
    mask[90, 90] = True
    cleaned = remove_small_components(mask)
    assert cleaned[30, 30] and not cleaned[90, 90]


def test_concept_silhouettes_are_plausible(spec):
    challenge = load_challenge()
    for view in spec["turnaround"]["views"].values():
        mask = concept_silhouette(challenge.concept_path, view, spec["turnaround"])
        assert 0.3 < mask.mean() < 0.6
        ys, xs = np.nonzero(mask)
        assert (ys.max() - ys.min()) > 1.5 * (xs.max() - xs.min())  # créature plus haute que large


def test_perfect_render_matches_concept(tmp_path, spec):
    """Un rendu dont l'alpha EST la silhouette du concept obtient un IoU ~1, miroir compris."""
    challenge = load_challenge()
    turnaround = spec["turnaround"]
    renders = {}
    for view_id, view in turnaround["views"].items():
        mask = concept_silhouette(challenge.concept_path, view, turnaround)
        if view_id == "side":
            mask = mask[:, ::-1]  # profil rendu du mauvais côté : toléré
        rgba = np.zeros((*mask.shape, 4), dtype=np.uint8)
        rgba[..., 3] = mask * 255
        path = tmp_path / f"{view['camera']}.png"
        Image.fromarray(rgba).resize((mask.shape[1] * 3, mask.shape[0] * 3), Image.NEAREST).save(
            path
        )
        renders[view["camera"]] = path
    scores = silhouette_scores(challenge.concept_path, turnaround, renders, tmp_path / "overlays")
    assert all(result["iou"] > 0.95 for result in scores.values()), scores
    assert scores["side"]["mirrored"] is True
    assert (tmp_path / "overlays" / "silhouette_front.png").exists()


def test_lab_conversion_reference_values():
    assert np.allclose(srgb_to_lab(np.array([1.0, 1.0, 1.0])), [100, 0, 0], atol=0.01)
    assert np.allclose(srgb_to_lab(np.array([0.0, 0.0, 0.0])), [0, 0, 0], atol=0.01)


def test_render_made_of_palette_colors_has_zero_delta_e(tmp_path, spec):
    names, reference = palette_lab(spec["palette"])
    rgba = np.zeros((8, 8, 4), dtype=np.uint8)
    for index, name in enumerate(names):
        rgba[index, :, :3] = np.round(hex_to_rgb(spec["palette"][name]) * 255)
    rgba[..., 3] = 255
    path = tmp_path / "flat.png"
    Image.fromarray(rgba).save(path)
    result = render_palette_delta_e([path], spec["palette"])
    assert result["mean_delta_e"] < 0.5
    assert all(abs(share - 1 / 8) < 1e-6 for share in result["shares"].values())
    distances, _ = nearest_delta_e(reference, reference)
    assert np.allclose(distances, 0)
