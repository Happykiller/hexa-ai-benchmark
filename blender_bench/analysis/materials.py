"""Phase 5, étape 2 — Matériaux & palette (depuis inspection.json)."""

from typing import Any

import numpy as np

from blender_bench.analysis import Check, fmt, ratio_at_least
from blender_bench.analysis.color import hex_to_rgb, nearest_delta_e, palette_lab, srgb_to_lab
from blender_bench.bench_config import (
    PALETTE_FULL_COVERAGE,
    PALETTE_MATCH_DELTA_E,
    TRANSLUCENCY_MIN,
)

PHASE, STEP, STEP_LABEL = 5, 2, "Matériaux & palette"


def creature_materials(inspection: dict[str, Any]) -> list[dict[str, Any]]:
    used = {name for mesh in inspection.get("meshes", []) for name in mesh.get("materials", [])}
    return [mat for mat in inspection.get("materials", []) if mat["name"] in used]


def palette_coverage(
    materials: list[dict[str, Any]], palette: dict[str, str]
) -> dict[str, float | None]:
    """ΔE de chaque couleur de palette à la couleur de nœud la plus proche."""
    colors = [color for mat in materials for color in mat.get("colors", [])]
    names, reference = palette_lab(palette)
    if not colors:
        return dict.fromkeys(names)
    lab = srgb_to_lab(np.array([hex_to_rgb(color) for color in colors]))
    distances, _ = nearest_delta_e(reference, lab)
    return {name: round(float(value), 2) for name, value in zip(names, distances, strict=True)}


def _is_translucent(material: dict[str, Any]) -> bool:
    return any(material.get(key, 0.0) >= minimum for key, minimum in TRANSLUCENCY_MIN.items())


def analyze_materials(inspection: dict[str, Any], spec: dict[str, Any]) -> list[Check]:
    step = (PHASE, STEP, STEP_LABEL)
    materials = creature_materials(inspection)
    checks: list[Check] = []
    principled = [mat for mat in materials if mat.get("principled")]
    share = len(principled) / len(materials) if materials else 0.0
    checks.append(
        Check(
            *step,
            "Matériaux PBR (Principled BSDF)",
            ratio_at_least(share, 0.99, 0.7),
            3,
            f"{len(principled)}/{len(materials)} matériaux",
            measured_value=len(materials),
        )
    )

    coverage = palette_coverage(materials, spec["palette"])
    covered = [
        name
        for name, delta in coverage.items()
        if delta is not None and delta <= PALETTE_MATCH_DELTA_E
    ]
    checks.append(
        Check(
            *step,
            "Palette XÉNOS dans les matériaux",
            min(1.0, len(covered) / PALETTE_FULL_COVERAGE),
            5,
            f"couleurs couvertes={len(covered)}/{len(coverage)} (ΔE ≤ {PALETTE_MATCH_DELTA_E:g}; "
            f"plein à {PALETTE_FULL_COVERAGE}); "
            + ", ".join(
                f"{name}={fmt(delta, 1) if delta is not None else 'n/a'}"
                for name, delta in coverage.items()
            ),
            measured_value=len(covered),
            details={"coverage": coverage},
        )
    )

    by_name = {mat["name"]: mat for mat in materials}
    families = spec["translucent_parts"]
    translucent = []
    for family in families:
        family_materials = [
            by_name[name]
            for mesh in inspection.get("meshes", [])
            if mesh["name"].lower().startswith(family)
            or any(group.lower().startswith(family) for group in mesh.get("vertex_groups", []))
            for name in mesh.get("materials", [])
            if name in by_name
        ] + [mat for mat in materials if mat["name"].lower().startswith(family)]
        if family_materials and all(_is_translucent(mat) for mat in family_materials):
            translucent.append(family)
    checks.append(
        Check(
            *step,
            "Sacs et membranes translucides",
            len(translucent) / len(families),
            4,
            f"translucides={', '.join(translucent) or 'aucune'} / {', '.join(families)}",
            measured_value=len(translucent),
        )
    )

    images = inspection.get("images", [])
    missing = [image["name"] for image in images if not image.get("has_data")]
    checks.append(
        Check(
            *step,
            "Aucune texture manquante",
            0.0 if missing else 1.0,
            3,
            f"images={len(images)}; manquantes={', '.join(missing) or 'aucune'}",
            measured_value=len(missing),
        )
    )
    return checks
