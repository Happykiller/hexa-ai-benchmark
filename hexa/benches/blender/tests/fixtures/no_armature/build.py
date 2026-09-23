"""Livrable témoin SANS armature (cap no_armature attendu) — dérivé de minimal_valid.

Livrable témoin du défi dreadhive_drone_mk1 : une créature en primitives.

Volontairement simple, mais conforme à TOUT le contrat de l'énoncé (nommage, 6 membres
posés au sol, armature symétrique, pondération complète, matériaux Principled aux couleurs
de la palette, sacs translucides, actions idle/walk qui bouclent). Sert de vérité terrain
aux tests d'intégration du benchmark Blender : il doit passer tous les contrôles binaires.
"""

import math

import bmesh
import bpy
from mathutils import Matrix, Vector

PALETTE = {
    "chitine": "#171318",
    "os": "#CFC0A5",
    "chair": "#5C2731",
    "necrose": "#603C70",
    "ambre": "#C7982A",
    "bile": "#657A38",
    "bleu": "#31566B",
    "ichor": "#DCFEAE",
}

# Membres : (nom, épaule, genou, pied) côté gauche (+X) ; le côté droit est en miroir.
LIMBS = [
    ("serre", (0.30, -0.45, 1.25), (0.62, -0.85, 1.05), (0.55, -0.95, 0.0)),
    ("patte_1", (0.36, -0.10, 1.00), (0.85, -0.20, 0.85), (0.92, -0.25, 0.0)),
    ("patte_2", (0.36, 0.40, 1.00), (0.85, 0.60, 0.85), (0.88, 0.75, 0.0)),
]


def srgb_to_linear(value: float) -> float:
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def hex_color(code: str) -> tuple[float, float, float, float]:
    rgb = [int(code[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    return (*[srgb_to_linear(c) for c in rgb], 1.0)


def material(name, color, roughness=0.5, transmission=0.0, subsurface=0.0, emission=None):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = hex_color(PALETTE[color])
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Transmission Weight"].default_value = transmission
    bsdf.inputs["Subsurface Weight"].default_value = subsurface
    if emission:
        bsdf.inputs["Emission Color"].default_value = hex_color(PALETTE[emission])
        bsdf.inputs["Emission Strength"].default_value = 0.4
    return mat


def mesh_object(name, bm, mat, bone):
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(mat)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    if bone:
        obj.vertex_groups.new(name=bone).add(list(range(len(mesh.vertices))), 1.0, "REPLACE")
    return obj


def new_bmesh():
    bm = bmesh.new()
    bm.loops.layers.uv.new("UVMap")  # calc_uvs n'écrit que dans une couche existante
    return bm


def ellipsoid(name, center, scale, mat, bone, subdivisions=3):
    bm = new_bmesh()
    bmesh.ops.create_icosphere(bm, subdivisions=subdivisions, radius=1.0, calc_uvs=True)
    bmesh.ops.transform(
        bm, matrix=Matrix.Translation(center) @ Matrix.Diagonal((*scale, 1.0)), verts=bm.verts
    )
    return mesh_object(name, bm, mat, bone)


def cone(name, base, tip, radius, mat, bone):
    bm = new_bmesh()
    direction = Vector(tip) - Vector(base)
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        segments=16,
        radius1=radius,
        radius2=0.0,
        depth=direction.length,
        calc_uvs=True,
    )
    matrix = Matrix.Translation((Vector(base) + Vector(tip)) / 2) @ (
        direction.to_track_quat("Z", "Y").to_matrix().to_4x4()
    )
    bmesh.ops.transform(bm, matrix=matrix, verts=bm.verts)
    return mesh_object(name, bm, mat, bone)


def limb(name, side, points, mat, bone_prefix):
    """Deux segments coniques ; chaque segment est pondéré à 100 % sur son os."""
    bm = new_bmesh()
    groups = []
    for index, (start, end, r1, r2) in enumerate(
        ((points[0], points[1], 0.09, 0.07), (points[1], points[2], 0.07, 0.015))
    ):
        direction = Vector(end) - Vector(start)
        before = set(bm.verts)
        bmesh.ops.create_cone(
            bm,
            cap_ends=True,
            segments=12,
            radius1=r1,
            radius2=r2,
            depth=direction.length,
            calc_uvs=True,
        )
        new_verts = [v for v in bm.verts if v not in before]
        matrix = Matrix.Translation((Vector(start) + Vector(end)) / 2) @ (
            direction.to_track_quat("Z", "Y").to_matrix().to_4x4()
        )
        bmesh.ops.transform(bm, matrix=matrix, verts=new_verts)
        groups.append((f"{bone_prefix}_{index + 1:02d}.{side}", new_verts))
    bm.verts.index_update()
    indices = [[v.index for v in verts] for _, verts in groups]
    obj = mesh_object(f"{name}.{side}", bm, mat, None)
    for (group_name, _), members in zip(groups, indices, strict=True):
        obj.vertex_groups.new(name=group_name).add(members, 1.0, "REPLACE")
    return obj


def mirror(point, side):
    return (point[0] if side == "L" else -point[0], point[1], point[2])


def build_armature():
    data = bpy.data.armatures.new("rig_drone")
    arm = bpy.data.objects.new("rig_drone", data)
    bpy.context.scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    root = data.edit_bones.new("racine")
    root.head, root.tail = (0, 0.1, 0.9), (0, 0.1, 1.3)
    head = data.edit_bones.new("tete")
    head.head, head.tail, head.parent = (0, -0.35, 1.3), (0, -0.75, 1.3), root
    for name, shoulder, knee, foot in LIMBS:
        for side in ("L", "R"):
            upper = data.edit_bones.new(f"{name}_01.{side}")
            upper.head, upper.tail, upper.parent = mirror(shoulder, side), mirror(knee, side), root
            lower = data.edit_bones.new(f"{name}_02.{side}")
            lower.head, lower.tail, lower.parent = mirror(knee, side), mirror(foot, side), upper
            lower.use_connect = True
    bpy.ops.object.mode_set(mode="OBJECT")
    return arm


def keyframes(arm, action_name, keys):
    """keys : {os: [(frame, (rx, ry, rz) | None, (x, y, z) | None), ...]}"""
    action = bpy.data.actions.new(action_name)
    action.use_fake_user = True
    arm.animation_data_create()
    arm.animation_data.action = action
    for bone_name, frames in keys.items():
        pbone = arm.pose.bones[bone_name]
        pbone.rotation_mode = "XYZ"
        for frame, rotation, location in frames:
            if rotation is not None:
                pbone.rotation_euler = [math.radians(v) for v in rotation]
                pbone.keyframe_insert("rotation_euler", frame=frame)
            if location is not None:
                pbone.location = location
                pbone.keyframe_insert("location", frame=frame)
    return action


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = 24

    chitine = material("chitine_noire", "chitine", roughness=0.3)
    chair = material("faisceau_musculaire_chair", "chair", roughness=0.6, subsurface=0.1)
    os_mat = material("os_griffes", "os", roughness=0.4)
    sac = material("sac_acide_ambre", "ambre", roughness=0.1, transmission=0.7, emission="bile")
    membrane = material("membrane_ventrale_voile", "necrose", roughness=0.5, subsurface=0.3)
    capteur = material("noeud_sensoriel_bleu", "bleu", roughness=0.2, emission="ichor")

    parts = [
        ellipsoid("faisceau_musculaire_corps", (0, 0.1, 1.2), (0.42, 0.65, 0.35), chair, "racine"),
        cone("carapace_dorsale", (0, 0.2, 1.35), (0, 0.35, 2.15), 0.45, chitine, "racine"),
        ellipsoid("membrane_ventrale", (0, 0.1, 0.92), (0.3, 0.5, 0.1), membrane, "racine"),
        ellipsoid("sac_acide.L", (0.38, 0.15, 1.2), (0.2, 0.28, 0.2), sac, "racine"),
        ellipsoid("sac_acide.R", (-0.38, 0.15, 1.2), (0.2, 0.28, 0.2), sac, "racine"),
        ellipsoid("tete", (0, -0.55, 1.3), (0.25, 0.3, 0.22), chitine, "tete"),
        ellipsoid("noeud_sensoriel", (0, -0.72, 1.45), (0.06, 0.06, 0.06), capteur, "tete", 2),
        cone("mandibule.L", (0.1, -0.75, 1.2), (0.16, -0.95, 0.95), 0.05, os_mat, "tete"),
        cone("mandibule.R", (-0.1, -0.75, 1.2), (-0.16, -0.95, 0.95), 0.05, os_mat, "tete"),
    ]
    for name, shoulder, knee, foot in LIMBS:
        for side in ("L", "R"):
            mat = os_mat if name == "serre" else chitine
            points = [mirror(p, side) for p in (shoulder, knee, foot)]
            parts.append(limb(name, side, points, mat, name))

    scene.frame_start, scene.frame_end = 1, 49


main()
