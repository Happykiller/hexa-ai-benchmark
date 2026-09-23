"""Analyses côté hôte sur l'inspection réelle (figée) du livrable témoin."""

from hexa.benches.blender.auditor.analysis.bonus_malus import analyze_bonus_malus
from hexa.benches.blender.auditor.analysis.geometry import analyze_geometry, found_parts
from hexa.benches.blender.auditor.analysis.materials import analyze_materials, palette_coverage
from hexa.benches.blender.auditor.analysis.rig_animation import analyze_rig_animation, limb_bones


def by_name(checks):
    return {check.name: check for check in checks}


def test_minimal_valid_geometry_passes_binary_checks(inspection, spec):
    checks = by_name(analyze_geometry(inspection, spec))
    for name in (
        "Arêtes non-manifold ≤ 0,1 %",
        "Aucune face dégénérée",
        "Normales cohérentes (≥ 99 %)",
        "Parties anatomiques nommées",
        "6 appuis au sol",
        "Aucun objet au nom par défaut",
        "Posée au sol (z min ≈ 0)",
    ):
        assert checks[name].ratio == 1.0, (name, checks[name].remarks)
    # La fixture est volontairement pauvre : sous le budget de triangles.
    assert checks["Triangles dans le budget"].ratio == 0.0


def test_missing_parts_and_default_names_are_detected(inspection, spec):
    inspection["meshes"] = [
        m for m in inspection["meshes"] if not m["name"].startswith("mandibule")
    ]
    for mesh in inspection["meshes"]:
        mesh["materials"] = [n for n in mesh["materials"] if "mandibule" not in n]
    inspection["objects"].append({"name": "Cube.001", "type": "MESH"})
    assert found_parts(inspection, spec["required_parts"])["mandibule"] is False
    checks = by_name(analyze_geometry(inspection, spec))
    assert checks["Parties anatomiques nommées"].ratio == 7 / 8
    assert checks["Aucun objet au nom par défaut"].ratio == 0.0


def test_rig_and_animation_of_minimal_valid(inspection, spec):
    chains = limb_bones(inspection["armatures"][0], spec["limbs"]["bone_pattern"])
    assert sorted(chains) == [
        "patte_1.L",
        "patte_1.R",
        "patte_2.L",
        "patte_2.R",
        "serre.L",
        "serre.R",
    ]
    checks = analyze_rig_animation(inspection, spec)
    scored = [check for check in checks if check.kind == "scored"]
    assert all(check.ratio == 1.0 for check in scored), [
        (c.name, c.remarks) for c in scored if c.ratio < 1
    ]


def test_no_armature_and_static_actions_score_zero(inspection, spec):
    inspection["armatures"] = []
    for action in inspection["actions"]:
        action["motion"] = None
    checks = by_name(analyze_rig_animation(inspection, spec))
    assert checks["Armature présente"].ratio == 0.0
    assert checks["Mouvement réel des actions requises"].ratio == 0.0
    assert checks["Cycle de marche : les 4 pattes bougent"].ratio == 0.0


def test_non_looping_walk_is_detected(inspection, spec):
    walk = next(action for action in inspection["actions"] if action["name"] == "walk")
    walk["motion"]["loop_delta_ratio"] = 0.2
    assert by_name(analyze_rig_animation(inspection, spec))["Actions qui bouclent"].ratio == 0.5


def test_palette_and_translucency(inspection, spec):
    coverage = palette_coverage(inspection["materials"], spec["palette"])
    assert coverage["chitine_noire"] == 0.0 and coverage["os"] == 0.0
    checks = by_name(analyze_materials(inspection, spec))
    assert checks["Palette XÉNOS dans les matériaux"].ratio == 1.0
    assert checks["Sacs et membranes translucides"].ratio == 1.0
    for material in inspection["materials"]:
        material.update(transmission=0.0, subsurface=0.0, emission=0.0)
    assert (
        by_name(analyze_materials(inspection, spec))["Sacs et membranes translucides"].ratio == 0.0
    )


def test_bonus_malus(inspection, spec):
    static = {"absolute_paths": [{"file": "build.py", "line": 3, "match": "'/home/x'"}]}
    checks = by_name(analyze_bonus_malus(inspection, static, 80.0, spec))
    assert checks["Chemin absolu dans le code"].ratio == 1.0
    assert checks["Chemin absolu dans le code"].polarity == "negative"
    assert checks["GLB au-delà du budget de taille"].ratio == 1.0
    assert checks["Action supplémentaire animée"].ratio == 0.0
