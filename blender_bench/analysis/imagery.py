"""Phase 5, étapes 1 et 3 — Silhouettes contre le turnaround, palette et qualité des rendus.

Fonctions pures sur des images (numpy + Pillow) : même entrée → même score.
Limites assumées (docs/KB/DAF/blender-defi.md) : les vignettes du turnaround sont petites
et légèrement en perspective, les rendus sont orthographiques ; d'où des bandes d'IoU basses.
"""

from pathlib import Path
from typing import Any

import numpy as np
from engine import _score_from_bands
from PIL import Image

from blender_bench.analysis import Check, fmt
from blender_bench.analysis.color import nearest_delta_e, palette_lab, srgb_to_lab
from blender_bench.bench_config import (
    DELTA_E_BANDS,
    DETAIL_BANDS,
    EXPOSURE_RANGE,
    IOU_BANDS,
    NON_EMPTY_MIN_RATIO,
)

PHASE = 5
NORMALIZED_SIZE = 256
MIN_COMPONENT_RATIO = 0.005


# --------------------------------------------------------------------------- masques


def _shift(mask: np.ndarray, dy: int, dx: int, fill: bool) -> np.ndarray:
    out = np.full_like(mask, fill)
    h, w = mask.shape
    out[max(0, dy) : h + min(0, dy), max(0, dx) : w + min(0, dx)] = mask[
        max(0, -dy) : h + min(0, -dy), max(0, -dx) : w + min(0, -dx)
    ]
    return out


def erode(mask: np.ndarray) -> np.ndarray:
    out = mask.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            out &= _shift(mask, dy, dx, False)
    return out


def dilate(mask: np.ndarray) -> np.ndarray:
    out = mask.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            out |= _shift(mask, dy, dx, False)
    return out


def remove_small_components(mask: np.ndarray, min_ratio: float = MIN_COMPONENT_RATIO) -> np.ndarray:
    """Supprime les composantes 4-connexes plus petites que min_ratio × aire du masque."""
    h, w = mask.shape
    labels = np.zeros((h, w), dtype=np.int32)
    sizes = [0]
    for y, x in zip(*np.nonzero(mask), strict=True):
        if labels[y, x]:
            continue
        label = len(sizes)
        stack = [(y, x)]
        labels[y, x] = label
        size = 0
        while stack:
            cy, cx = stack.pop()
            size += 1
            for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not labels[ny, nx]:
                    labels[ny, nx] = label
                    stack.append((ny, nx))
        sizes.append(size)
    keep = np.array(sizes) >= max(1, min_ratio * h * w)
    keep[0] = False
    return keep[labels]


def concept_silhouette(
    concept: Path, view: dict[str, Any], turnaround: dict[str, Any]
) -> np.ndarray:
    """Silhouette d'une vignette du turnaround : écart au fond, ouverture, petites taches ôtées."""
    source = view.get("source")
    image = Image.open(concept.parent / source if source else concept).convert("RGB")
    if not source:
        image = image.crop(tuple(view["box_px"]))
    pixels = np.asarray(image).astype(np.int16)
    background = np.array(turnaround["background_rgb"], dtype=np.int16)
    mask = np.abs(pixels - background).max(axis=-1) > turnaround["foreground_threshold"]
    mask = dilate(erode(mask))
    return remove_small_components(mask)


def render_silhouette(render: Path) -> np.ndarray:
    return np.asarray(Image.open(render).convert("RGBA"))[..., 3] > 127


def normalize_mask(mask: np.ndarray, size: int = NORMALIZED_SIZE) -> np.ndarray:
    """Recadre sur la boîte englobante, met à la hauteur `size`, centre dans un canevas
    deux fois plus large que haut : la largeur relative reste comparée (rien n'est rogné,
    sauf une silhouette plus de deux fois plus large que haute)."""
    ys, xs = np.nonzero(mask)
    width = 2 * size
    canvas = np.zeros((size, width), dtype=bool)
    if not len(ys):
        return canvas
    crop = mask[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    h, w = crop.shape
    new_w = max(1, min(width, round(w * size / h)))
    resized = Image.fromarray((crop * 255).astype(np.uint8)).resize((new_w, size), Image.BILINEAR)
    left = (width - new_w) // 2
    canvas[:, left : left + new_w] = np.asarray(resized) >= 128
    return canvas


def iou(a: np.ndarray, b: np.ndarray) -> float:
    union = np.logical_or(a, b).sum()
    return float(np.logical_and(a, b).sum() / union) if union else 0.0


def overlay(concept: np.ndarray, render: np.ndarray) -> Image.Image:
    """Superposition pour la KB : concept seul en ambre, rendu seul en bleu, commun en gris."""
    rgb = np.full((*concept.shape, 3), 245, dtype=np.uint8)
    rgb[concept & render] = (90, 90, 90)
    rgb[concept & ~render] = (199, 152, 42)
    rgb[render & ~concept] = (49, 86, 107)
    return Image.fromarray(rgb)


def silhouette_scores(
    concept: Path, turnaround: dict[str, Any], renders: dict[str, Path], overlays_dir: Path | None
) -> dict[str, dict[str, Any]]:
    results = {}
    for view_id, view in turnaround["views"].items():
        render_path = renders.get(view["camera"])
        if render_path is None or not render_path.exists():
            results[view_id] = {"iou": None, "error": "rendu absent"}
            continue
        target = normalize_mask(concept_silhouette(concept, view, turnaround))
        candidate = normalize_mask(render_silhouette(render_path))
        score = iou(target, candidate)
        mirrored = iou(target, candidate[:, ::-1]) if view.get("allow_mirror") else None
        use_mirror = mirrored is not None and mirrored > score
        best = candidate[:, ::-1] if use_mirror else candidate
        entry = {"iou": round(max(score, mirrored or 0.0), 4), "mirrored": use_mirror}
        if overlays_dir is not None:
            overlays_dir.mkdir(parents=True, exist_ok=True)
            path = overlays_dir / f"silhouette_{view_id}.png"
            overlay(target, best).save(path, optimize=False)
            entry["overlay"] = str(path)
        results[view_id] = entry
    return results


# --------------------------------------------------------------------------- rendus


def _foreground(render: Path) -> tuple[np.ndarray, np.ndarray]:
    rgba = np.asarray(Image.open(render).convert("RGBA")).astype(np.float64) / 255.0
    return rgba[..., :3], rgba[..., 3] > 0.8


def render_palette_delta_e(renders: list[Path], palette: dict[str, str]) -> dict[str, Any]:
    names, reference = palette_lab(palette)
    pixels = []
    for render in renders:
        rgb, mask = _foreground(render)
        pixels.append(rgb[mask])
    if not pixels or not sum(len(p) for p in pixels):
        return {"mean_delta_e": None, "shares": {}}
    lab = srgb_to_lab(np.concatenate(pixels))
    distances, nearest = nearest_delta_e(lab, reference)
    shares = np.bincount(nearest, minlength=len(names)) / len(nearest)
    return {
        "mean_delta_e": round(float(distances.mean()), 2),
        "shares": {name: round(float(share), 4) for name, share in zip(names, shares, strict=True)},
    }


def luminance(rgb: np.ndarray) -> np.ndarray:
    return rgb @ np.array([0.2126, 0.7152, 0.0722])


def detail_and_exposure(render: Path) -> dict[str, Any]:
    rgb, mask = _foreground(render)
    lum = luminance(rgb)
    coverage = float(mask.mean())
    interior = erode(erode(mask))
    laplacian = (
        -4 * lum
        + np.roll(lum, 1, axis=0)
        + np.roll(lum, -1, axis=0)
        + np.roll(lum, 1, axis=1)
        + np.roll(lum, -1, axis=1)
    )
    detail = float(laplacian[interior].var()) if interior.any() else 0.0
    exposure = float(lum[mask].mean()) if mask.any() else 0.0
    return {
        "coverage": round(coverage, 4),
        "detail": round(detail, 6),
        "exposure": round(exposure, 4),
    }


def analyze_imagery(
    render_dir: Path, concept: Path, spec: dict[str, Any], overlays_dir: Path | None = None
) -> tuple[list[Check], dict[str, Any]]:
    turnaround = spec["turnaround"]
    cameras = [view["camera"] for view in turnaround["views"].values()]
    flat = {camera: render_dir / f"view_{camera}_flat.png" for camera in cameras}
    beauty = {camera: render_dir / f"view_{camera}_beauty.png" for camera in cameras}
    checks: list[Check] = []

    silhouettes = silhouette_scores(concept, turnaround, flat, overlays_dir)
    step = (PHASE, 1, "Silhouettes vs turnaround")
    labels = {"front": "FACE", "side": "PROFIL", "back": "DOS"}
    for view_id, result in silhouettes.items():
        value = result.get("iou")
        band = (
            _score_from_bands(value, IOU_BANDS)
            if value is not None
            else {"score_ratio": 0.0, "status": "KO", "remarks": result.get("error", "")}
        )
        remarks = (
            f"IoU={fmt(value, 3) if value is not None else 'n/a'}"
            + (" (miroir)" if result.get("mirrored") else "")
            + f"; {band['remarks']}"
        )
        checks.append(
            Check(
                *step,
                f"Silhouette {labels.get(view_id, view_id)}",
                band["score_ratio"],
                6,
                remarks,
                status=band["status"],
                measured_value=value,
            )
        )

    step = (PHASE, 2, "Matériaux & palette")
    existing_flat = [path for path in flat.values() if path.exists()]
    palette = render_palette_delta_e(existing_flat, spec["palette"])
    mean_de = palette["mean_delta_e"]
    band = (
        _score_from_bands(mean_de, DELTA_E_BANDS)
        if mean_de is not None
        else {"score_ratio": 0.0, "status": "KO", "remarks": "aucun pixel rendu"}
    )
    dominant = sorted(palette["shares"].items(), key=lambda item: -item[1])[:4]
    checks.append(
        Check(
            *step,
            "Couleurs rendues proches de la palette",
            band["score_ratio"],
            4,
            f"ΔE moyen={mean_de}; {band['remarks']}; dominantes="
            + ", ".join(f"{name} {fmt(share * 100, 1)} %" for name, share in dominant),
            status=band["status"],
            measured_value=mean_de,
            details=palette,
        )
    )

    step = (PHASE, 3, "Qualité des rendus")
    quality = {
        camera: detail_and_exposure(path) for camera, path in beauty.items() if path.exists()
    }
    non_empty = [camera for camera, q in quality.items() if q["coverage"] >= NON_EMPTY_MIN_RATIO]
    checks.append(
        Check(
            *step,
            "Rendus non vides (3 vues)",
            len(non_empty) / len(cameras),
            4,
            "; ".join(f"{camera}={fmt(q['coverage'] * 100, 1)} %" for camera, q in quality.items())
            or "aucun rendu",
            measured_value=len(non_empty),
        )
    )
    detail = float(np.mean([q["detail"] for q in quality.values()])) if quality else None
    band = (
        _score_from_bands(detail, DETAIL_BANDS)
        if detail is not None
        else {"score_ratio": 0.0, "status": "KO", "remarks": "aucun rendu"}
    )
    checks.append(
        Check(
            *step,
            "Détail de surface",
            band["score_ratio"],
            3,
            f"variance du laplacien={fmt(detail, 6) if detail is not None else 'n/a'}; {band['remarks']}",
            status=band["status"],
            measured_value=None if detail is None else round(detail, 6),
        )
    )
    exposure = float(np.mean([q["exposure"] for q in quality.values()])) if quality else None
    low, high = EXPOSURE_RANGE
    exposed = exposure is not None and low <= exposure <= high
    checks.append(
        Check(
            *step,
            "Exposition exploitable",
            1.0 if exposed else 0.0,
            2,
            f"luminance moyenne={fmt(exposure) if exposure is not None else 'n/a'} (attendu {low}–{high})",
            measured_value=None if exposure is None else round(exposure, 4),
        )
    )
    return checks, {"silhouettes": silhouettes, "palette": palette, "quality": quality}
