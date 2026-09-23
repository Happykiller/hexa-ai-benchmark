"""Phase 2 — Géométrie & Topologie (depuis inspection.json)."""

import re
from typing import Any

from engine import _score_from_bands

from blender_bench.analysis import Check, fmt, ratio_at_least, ratio_at_most
from blender_bench.bench_config import DEFAULT_OBJECT_NAME

PHASE = 2


def _sum(meshes: list[dict], key: str) -> float:
    return float(sum(mesh.get(key) or 0 for mesh in meshes))


def _area_weighted(meshes: list[dict], key: str) -> float | None:
    rows = [(mesh[key], mesh.get("area") or 0.0) for mesh in meshes if mesh.get(key) is not None]
    total = sum(area for _, area in rows)
    if not rows or total <= 0:
        return None
    return sum(value * area for value, area in rows) / total


def part_names(inspection: dict[str, Any]) -> list[str]:
    """Noms qui peuvent identifier une partie : objets, groupes de sommets, matériaux."""
    names = [mesh["name"] for mesh in inspection.get("meshes", [])]
    for mesh in inspection.get("meshes", []):
        names += mesh.get("vertex_groups", []) + mesh.get("materials", [])
    return [name.lower() for name in names]


def found_parts(inspection: dict[str, Any], required: dict[str, list[str]]) -> dict[str, bool]:
    names = part_names(inspection)
    return {
        part: any(name.startswith(prefix.lower()) for name in names for prefix in prefixes)
        for part, prefixes in required.items()
    }


def analyze_geometry(inspection: dict[str, Any], spec: dict[str, Any]) -> list[Check]:
    meshes = inspection.get("meshes", [])
    checks: list[Check] = []
    if not meshes:
        return [
            Check(
                PHASE, 1, "Intégrité des maillages", "Maillages présents", 0.0, 7, "aucun maillage"
            )
        ]

    edges = _sum(meshes, "edges") or 1.0
    faces = _sum(meshes, "faces") or 1.0
    verts = _sum(meshes, "verts") or 1.0
    step = (PHASE, 1, "Intégrité des maillages")
    non_manifold = _sum(meshes, "non_manifold_edges") / edges
    checks.append(
        Check(
            *step,
            "Arêtes non-manifold ≤ 0,1 %",
            ratio_at_most(non_manifold, 0.001, 0.01),
            5,
            f"ratio={fmt(non_manifold, 5)} ({int(_sum(meshes, 'non_manifold_edges'))} arêtes)",
            measured_value=round(non_manifold, 5),
        )
    )
    degenerate = _sum(meshes, "degenerate_faces") / faces
    checks.append(
        Check(
            *step,
            "Aucune face dégénérée",
            ratio_at_most(degenerate, 0.0, 0.001),
            4,
            f"faces dégénérées={int(_sum(meshes, 'degenerate_faces'))}",
            measured_value=int(_sum(meshes, "degenerate_faces")),
        )
    )
    loose = _sum(meshes, "loose_verts") + _sum(meshes, "wire_edges")
    checks.append(
        Check(
            *step,
            "Aucun sommet isolé ni arête libre",
            ratio_at_most(loose / verts, 0.0, 0.001),
            3,
            f"sommets isolés={int(_sum(meshes, 'loose_verts'))}; arêtes libres={int(_sum(meshes, 'wire_edges'))}",
            measured_value=int(loose),
        )
    )
    flipped = _sum(meshes, "flipped_faces") / faces
    checks.append(
        Check(
            *step,
            "Normales cohérentes (≥ 99 %)",
            ratio_at_most(flipped, 0.01, 0.05),
            5,
            f"faces à retourner={int(_sum(meshes, 'flipped_faces'))} ({fmt(flipped * 100, 2)} %)",
            measured_value=round(flipped, 5),
        )
    )

    step = (PHASE, 2, "Budget & topologie")
    tris = int(_sum(meshes, "tris"))
    band = _score_from_bands(tris, spec["budget"]["triangles_bands"])
    checks.append(
        Check(
            *step,
            "Triangles dans le budget",
            band["score_ratio"],
            5,
            band["remarks"],
            status=band["status"],
            measured_value=tris,
        )
    )
    quads = _sum(meshes, "quads") / faces
    checks.append(
        Check(
            *step,
            "Topologie à dominante de quads (≥ 70 %)",
            ratio_at_least(quads, 0.7, 0.4),
            3,
            f"quads={fmt(quads * 100, 1)} %",
            measured_value=round(quads, 4),
        )
    )
    ngons = _sum(meshes, "ngons") / faces
    checks.append(
        Check(
            *step,
            "N-gones ≤ 5 %",
            ratio_at_most(ngons, 0.05, 0.15),
            2,
            f"n-gones={fmt(ngons * 100, 1)} %",
            measured_value=round(ngons, 4),
        )
    )

    step = (PHASE, 3, "UV")
    total_area = _sum(meshes, "area") or 1.0
    uv_area = sum(mesh.get("area") or 0 for mesh in meshes if mesh.get("uv_layers"))
    uv_share = uv_area / total_area
    checks.append(
        Check(
            *step,
            "Tous les maillages ont une UV map",
            ratio_at_least(uv_share, 0.99, 0.8),
            4,
            f"surface couverte par des UV={fmt(uv_share * 100, 1)} %",
            measured_value=round(uv_share, 4),
        )
    )
    overlap = _area_weighted(meshes, "uv_overlap_ratio")
    checks.append(
        Check(
            *step,
            "Chevauchement UV ≤ 10 %",
            ratio_at_most(overlap, 0.10, 0.5),
            4,
            f"chevauchement moyen={fmt(overlap) if overlap is not None else 'n/a'}",
            measured_value=None if overlap is None else round(overlap, 4),
        )
    )
    oob = _area_weighted(meshes, "uv_oob_ratio")
    checks.append(
        Check(
            *step,
            "UV dans [0, 1]",
            ratio_at_most(oob, 0.01, 0.1),
            2,
            f"hors cadre={fmt(oob) if oob is not None else 'n/a'}",
            measured_value=None if oob is None else round(oob, 4),
        )
    )

    step = (PHASE, 4, "Échelle & anatomie")
    scale = spec["scale"]
    height = float(inspection.get("height") or 0.0)
    low, high = scale["height_range_m"]
    in_range = 1.0 if low <= height <= high else (0.5 if 0.7 * low <= height <= 1.3 * high else 0.0)
    checks.append(
        Check(
            *step,
            f"Hauteur dans [{low} ; {high}] m",
            in_range,
            4,
            f"hauteur={fmt(height)} m (cible {scale['target_height_m']} m)",
            measured_value=round(height, 3),
        )
    )
    bbox = inspection.get("bbox") or [[0, 0, 0], [0, 0, 0]]
    zmin = bbox[0][2]
    grounded = height > 0 and abs(zmin) <= scale["ground_tolerance_ratio"] * height
    checks.append(
        Check(
            *step,
            "Posée au sol (z min ≈ 0)",
            1.0 if grounded else 0.0,
            3,
            f"z min={fmt(zmin)} m",
            measured_value=round(zmin, 4),
        )
    )
    width = bbox[1][0] - bbox[0][0]
    offset = abs(bbox[0][0] + bbox[1][0]) / width if width > 0 else 1.0
    checks.append(
        Check(
            *step,
            "Centrée et symétrique en X",
            ratio_at_most(offset, 0.05, 0.15),
            3,
            f"décalage |xmin+xmax|/largeur={fmt(offset)}",
            measured_value=round(offset, 4),
        )
    )
    parts = found_parts(inspection, spec["required_parts"])
    found = sum(parts.values())
    missing = [part for part, ok in parts.items() if not ok]
    checks.append(
        Check(
            *step,
            "Parties anatomiques nommées",
            found / len(parts),
            5,
            f"{found}/{len(parts)}" + (f"; manquantes={', '.join(missing)}" if missing else ""),
            measured_value=found,
            details={"parts": parts},
        )
    )
    checks.append(_ground_check(inspection, spec, step))
    default_names = [
        o["name"] for o in inspection.get("objects", []) if re.match(DEFAULT_OBJECT_NAME, o["name"])
    ]
    checks.append(
        Check(
            *step,
            "Aucun objet au nom par défaut",
            0.0 if default_names else 1.0,
            2,
            f"noms par défaut={', '.join(default_names[:8]) or 'aucun'}",
            measured_value=len(default_names),
        )
    )

    step = (PHASE, 5, "Mesures")
    checks += [
        Check(
            *step,
            "Triangles (total, modificateurs appliqués)",
            kind="measured",
            measured_value=tris,
            remarks=str(tris),
        ),
        Check(
            *step,
            "Objets maillés",
            kind="measured",
            measured_value=len(meshes),
            remarks=str(len(meshes)),
        ),
        Check(
            *step,
            "Hauteur (m)",
            kind="measured",
            measured_value=round(height, 3),
            remarks=fmt(height),
        ),
    ]
    return checks


def _ground_check(inspection: dict[str, Any], spec: dict[str, Any], step: tuple) -> Check:
    expected = spec["limbs"]["ground_contacts_expected"]
    ground = inspection.get("ground") or {}
    limbs = ground.get("ground_limbs") or []
    if limbs:
        ratio = min(1.0, len(limbs) / expected)
        remarks = f"membres au sol={len(limbs)}/{expected} ({', '.join(limbs)})"
        value = len(limbs)
    else:
        clusters = int(ground.get("ground_clusters") or 0)
        ratio = 1.0 if clusters == expected else (0.5 if abs(clusters - expected) == 1 else 0.0)
        remarks = f"îlots de contact au sol={clusters} (attendu {expected}, sans rig identifiable)"
        value = clusters
    return Check(*step, f"{expected} appuis au sol", ratio, 5, remarks, measured_value=value)
