"""Phase 1 — Opérationnalité : contrat, rejeu du build, aller-retour glTF."""

from typing import Any

from hexa.benches.blender.auditor.analysis import Check, fmt
from hexa.benches.blender.auditor.bench_config import BUILD_SECONDS_BANDS, GLB_MB_BANDS
from hexa.benches.blender.auditor.static_checks import README_MIN_CHARS
from hexa.core.engine import _score_from_bands

PHASE = 1


def analyze_operationality(
    static: dict[str, Any],
    build: dict[str, Any] | None,
    reimport: dict[str, Any] | None,
    glb_mb: float | None,
    spec: dict[str, Any],
) -> list[Check]:
    checks: list[Check] = []
    step = (PHASE, 1, "Contrat du livrable")
    checks.append(
        Check(
            *step,
            "build.py présent",
            1.0 if static["build_present"] else 0.0,
            4,
            "build.py à la racine" if static["build_present"] else "build.py absent",
        )
    )
    readme_ok = static["readme_present"] and static["readme_chars"] >= README_MIN_CHARS
    checks.append(
        Check(
            *step,
            "README.md documenté",
            1.0 if readme_ok else (0.5 if static["readme_present"] else 0.0),
            2,
            f"caractères={static['readme_chars']} (min {README_MIN_CHARS})",
            measured_value=static["readme_chars"],
        )
    )
    hits = [hit for found in static["forbidden"].values() for hit in found]
    checks.append(
        Check(
            *step,
            "Aucun import réseau / sous-processus (statique)",
            0.0 if hits else 1.0,
            3,
            "; ".join(f"{h['file']}:{h['line']} {h['match']}" for h in hits[:5]) or "aucun",
            measured_value=len(hits),
        )
    )

    step = (PHASE, 2, "Rejeu du build")
    build = build or {}
    ran = build.get("build_status") == "OK"
    checks.append(
        Check(
            *step,
            "build.py s'exécute sans erreur",
            1.0 if ran else 0.0,
            7,
            "OK" if ran else (build.get("error") or build.get("runner_error") or "non exécuté"),
            details={"traceback": build.get("traceback")},
        )
    )
    checks.append(
        Check(
            *step,
            "Scène sauvegardée (.blend)",
            1.0 if build.get("saved") else 0.0,
            3,
            "OK" if build.get("saved") else "non sauvegardée",
        )
    )
    checks.append(
        Check(
            *step,
            "Export glTF (.glb)",
            1.0 if build.get("exported") else 0.0,
            5,
            "OK" if build.get("exported") else (build.get("export_error") or "non exporté"),
        )
    )
    seconds = build.get("build_seconds")
    band = (
        _score_from_bands(seconds, BUILD_SECONDS_BANDS)
        if ran
        else {"score_ratio": 0.0, "status": "KO", "remarks": "build en échec"}
    )
    checks.append(
        Check(
            *step,
            "Durée du build",
            band["score_ratio"],
            3,
            f"secondes={seconds}; {band['remarks']}",
            status=band["status"],
            measured_value=seconds,
        )
    )
    band = (
        _score_from_bands(glb_mb, GLB_MB_BANDS)
        if glb_mb is not None
        else {"score_ratio": 0.0, "status": "KO", "remarks": "pas de GLB"}
    )
    checks.append(
        Check(
            *step,
            "Taille du GLB",
            band["score_ratio"],
            3,
            f"Mo={fmt(glb_mb, 2) if glb_mb is not None else 'n/a'}; {band['remarks']}",
            status=band["status"],
            measured_value=None if glb_mb is None else round(glb_mb, 2),
        )
    )

    step = (PHASE, 3, "Aller-retour glTF")
    reimport = reimport or {}
    ok = reimport.get("status") == "OK"
    checks.append(
        Check(
            *step,
            "GLB réimportable",
            1.0 if ok else 0.0,
            6,
            "OK" if ok else (reimport.get("error") or "non réimporté"),
        )
    )
    checks.append(
        Check(
            *step,
            "Skin conservé au réimport",
            1.0 if ok and reimport.get("skinned_meshes") and reimport.get("armatures") else 0.0,
            4,
            f"armatures={reimport.get('armatures')}; maillages skinnés={reimport.get('skinned_meshes')}/{reimport.get('meshes')}",
        )
    )
    required = list(spec["animations"]["required"])
    animations = reimport.get("animations") or []
    present = [
        name
        for name in required
        if any(anim == name or anim.startswith(f"{name}_") for anim in animations)
    ]
    checks.append(
        Check(
            *step,
            "Animations requises conservées",
            len(present) / len(required) if ok else 0.0,
            4,
            f"animations={', '.join(animations) or 'aucune'}",
            measured_value=len(animations),
        )
    )
    return checks
