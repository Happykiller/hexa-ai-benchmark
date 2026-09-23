"""Inspecte le .blend sauvé par run_build.py et écrit inspection.json.

Mesures brutes uniquement (aucun seuil ici) : la notation est faite côté hôte par
hexa/benches/blender/auditor/analysis/. Géométrie mesurée sur les maillages ÉVALUÉS (modificateurs
appliqués, armature en pose de repos), c'est-à-dire ce que l'export glTF contient.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import math  # noqa: E402
import re  # noqa: E402

import bmesh  # noqa: E402
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from _common import (  # noqa: E402
    assign_action,
    creature_meshes,
    parse_args,
    rgb_hex,
    set_pose_position,
    world_bbox,
    write_json,
)

UV_RASTER = 256
UV_MAX_TRIANGLES = 60000
MOTION_SAMPLES = 16


# --------------------------------------------------------------------------- géométrie


def _uv_metrics(bm, uv_layer) -> dict:
    """Chevauchement UV (rastérisation) et part des coordonnées hors [0, 1]."""
    tris = []
    oob = 0
    total = 0
    for face in bm.faces:
        uvs = [loop[uv_layer].uv.copy() for loop in face.loops]
        for uv in uvs:
            total += 1
            if not (-1e-4 <= uv.x <= 1.0001 and -1e-4 <= uv.y <= 1.0001):
                oob += 1
        for index in range(1, len(uvs) - 1):
            tris.append((uvs[0], uvs[index], uvs[index + 1]))
    if not tris:
        return {"uv_overlap_ratio": None, "uv_oob_ratio": None, "uv_zero_area_ratio": None}
    step = max(1, len(tris) // UV_MAX_TRIANGLES)  # échantillonnage déterministe
    counts = np.zeros((UV_RASTER, UV_RASTER), dtype=np.int32)
    zero_area = 0
    sampled = tris[::step]
    for a, b, c in sampled:
        area = (b.x - a.x) * (c.y - a.y) - (c.x - a.x) * (b.y - a.y)
        if abs(area) < 1e-12:
            zero_area += 1
            continue
        pts = np.array([[a.x, a.y], [b.x, b.y], [c.x, c.y]]) % 1.0 * UV_RASTER
        # Un triangle qui chevauche la couture du modulo est ignoré (rare, sans effet).
        if np.ptp(pts[:, 0]) > UV_RASTER / 2 or np.ptp(pts[:, 1]) > UV_RASTER / 2:
            continue
        x0, y0 = np.floor(pts.min(axis=0)).astype(int)
        x1, y1 = np.ceil(pts.max(axis=0)).astype(int)
        x1, y1 = min(x1, UV_RASTER), min(y1, UV_RASTER)
        if x1 <= x0 or y1 <= y0:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1) + 0.5, np.arange(y0, y1) + 0.5)
        (ax, ay), (bx, by), (cx, cy) = pts
        denom = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        w1 = ((by - cy) * (xs - cx) + (cx - bx) * (ys - cy)) / denom
        w2 = ((cy - ay) * (xs - cx) + (ax - cx) * (ys - cy)) / denom
        inside = (w1 >= 0) & (w2 >= 0) & (w1 + w2 <= 1)
        counts[y0:y1, x0:x1] += inside
    covered = int((counts >= 1).sum())
    return {
        "uv_overlap_ratio": round(float((counts >= 2).sum()) / covered, 4) if covered else None,
        "uv_oob_ratio": round(oob / total, 4) if total else None,
        "uv_zero_area_ratio": round(zero_area / len(sampled), 4) if sampled else None,
        "uv_coverage_ratio": round(covered / (UV_RASTER * UV_RASTER), 4),
    }


def _mesh_metrics(obj, depsgraph, deform_bones: set[str]) -> dict:
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bm.transform(evaluated.matrix_world)
        bm.normal_update()
        faces = list(bm.faces)
        sizes = [len(face.verts) for face in faces]
        edges = list(bm.edges)
        non_manifold = [edge for edge in edges if not edge.is_manifold]
        metrics = {
            "name": obj.name,
            "data_name": obj.data.name,
            "parent": obj.parent.name if obj.parent else None,
            "parent_type": obj.parent_type if obj.parent else None,
            "verts": len(bm.verts),
            "edges": len(edges),
            "faces": len(faces),
            "tris": int(sum(size - 2 for size in sizes)),
            "triangles": sizes.count(3),
            "quads": sizes.count(4),
            "ngons": sum(1 for size in sizes if size > 4),
            "non_manifold_edges": len(non_manifold),
            "boundary_edges": sum(1 for edge in edges if edge.is_boundary),
            "wire_edges": sum(1 for edge in edges if edge.is_wire),
            "loose_verts": sum(1 for vert in bm.verts if not vert.link_edges),
            "degenerate_faces": sum(1 for face in faces if face.calc_area() < 1e-10),
            "area": round(sum(face.calc_area() for face in faces), 6),
            "materials": [slot.material.name for slot in obj.material_slots if slot.material],
            "empty_material_slots": sum(1 for slot in obj.material_slots if not slot.material),
            "vertex_groups": [group.name for group in obj.vertex_groups],
            "modifiers": [modifier.type for modifier in obj.modifiers],
            "armature_modifier": any(
                modifier.type == "ARMATURE" and modifier.object is not None
                for modifier in obj.modifiers
            ),
            "shape_keys": len(obj.data.shape_keys.key_blocks) if obj.data.shape_keys else 0,
            "uv_layers": len(mesh.uv_layers),
        }
        # Normales incohérentes : on recalcule une orientation cohérente (vers l'extérieur)
        # et on compte les faces que ce recalcul retournerait.
        before = [face.normal.copy() for face in faces]
        bmesh.ops.recalc_face_normals(bm, faces=faces)
        metrics["flipped_faces"] = sum(
            1 for face, normal in zip(faces, before, strict=True) if face.normal.dot(normal) < 0
        )
        uv_layer = bm.loops.layers.uv.active
        metrics.update(_uv_metrics(bm, uv_layer) if uv_layer else {"uv_overlap_ratio": None})

        # Skinning, mesuré sur le maillage évalué (ce que l'export contient).
        group_names = {group.index: group.name for group in obj.vertex_groups}
        weighted = 0
        over4 = 0
        max_influences = 0
        dominant: list[str | None] = []
        for vert in mesh.vertices:
            influences = [
                (group_names.get(g.group), g.weight)
                for g in vert.groups
                if g.weight > 1e-4 and group_names.get(g.group) in deform_bones
            ]
            count = len(influences)
            weighted += count > 0
            over4 += count > 4
            max_influences = max(max_influences, count)
            dominant.append(max(influences, key=lambda item: item[1])[0] if influences else None)
        total = len(mesh.vertices) or 1
        metrics["weighted_ratio"] = round(weighted / total, 4)
        metrics["over4_ratio"] = round(over4 / total, 4)
        metrics["max_influences"] = max_influences

        coords = np.array([vert.co[:] for vert in bm.verts]) if bm.verts else np.zeros((0, 3))
        bm.free()
        return metrics, coords, dominant
    finally:
        evaluated.to_mesh_clear()


def _ground_contacts(points, dominant, height: float, zmin: float, bone_pattern: str) -> dict:
    """Appuis au sol : membres (via l'os dominant) et îlots spatiaux des sommets au sol."""
    if not len(points) or height <= 0:
        return {"ground_limbs": [], "ground_clusters": 0}
    near = points[:, 2] <= zmin + 0.02 * height
    ground = points[near]
    pattern = re.compile(bone_pattern)
    limbs = set()
    for bone in (d for d, flag in zip(dominant, near, strict=True) if flag and d):
        match = pattern.match(bone)
        if match:
            limbs.add(f"{match.group(1)}.{match.group(3)}")
    # Îlots : union-find sur une grille XY de pas 5 % de la hauteur.
    cell = 0.05 * height
    keys = {tuple(np.floor(point[:2] / cell).astype(int)) for point in ground}
    parent = {key: key for key in keys}

    def find(key):
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    for key in keys:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                other = (key[0] + dx, key[1] + dy)
                if other in parent:
                    parent[find(other)] = find(key)
    clusters = len({find(key) for key in keys})
    return {"ground_limbs": sorted(limbs), "ground_clusters": clusters}


# --------------------------------------------------------------------------- matériaux


def _input(node, *names):
    for name in names:
        if name in node.inputs:
            return node.inputs[name]
    return None


def _image_mean_hex(image) -> str | None:
    try:
        width, height = image.size
        if not width or not height:
            return None
        pixels = np.empty(width * height * 4, dtype=np.float32)
        image.pixels.foreach_get(pixels)
    except (RuntimeError, ValueError):
        return None
    pixels = pixels.reshape(-1, 4)
    step = max(1, len(pixels) // 250000)
    rgb = pixels[::step, :3].mean(axis=0)
    colorspace = image.colorspace_settings.name if image.colorspace_settings else ""
    if image.is_float and "sRGB" not in colorspace:
        return rgb_hex(rgb)
    return "#" + "".join(f"{round(max(0.0, min(1.0, float(c))) * 255):02X}" for c in rgb)


def _material_metrics(material) -> dict:
    info = {
        "name": material.name,
        "users": material.users,
        "use_nodes": bool(material.use_nodes),
        "principled": 0,
        "colors": [],
        "transmission": 0.0,
        "subsurface": 0.0,
        "emission": 0.0,
        "alpha_min": 1.0,
        "images": [],
        "procedural_nodes": 0,
    }
    if not material.use_nodes or not material.node_tree:
        info["colors"].append(rgb_hex(material.diffuse_color))
        return info
    procedural = {
        "TEX_NOISE",
        "TEX_VORONOI",
        "TEX_WAVE",
        "TEX_MUSGRAVE",
        "TEX_MAGIC",
        "TEX_GRADIENT",
        "TEX_BRICK",
        "TEX_CHECKER",
        "TEX_WHITE_NOISE",
        "BUMP",
        "DISPLACEMENT",
    }
    for node in material.node_tree.nodes:
        if node.type in procedural:
            info["procedural_nodes"] += 1
        if node.type == "BSDF_PRINCIPLED":
            info["principled"] += 1
            base = _input(node, "Base Color")
            if base is not None and not base.is_linked:
                info["colors"].append(rgb_hex(base.default_value))
            for key, names in (
                ("transmission", ("Transmission Weight", "Transmission")),
                ("subsurface", ("Subsurface Weight", "Subsurface")),
            ):
                socket = _input(node, *names)
                if socket is not None:
                    value = 1.0 if socket.is_linked else float(socket.default_value)
                    info[key] = max(info[key], value)
            strength = _input(node, "Emission Strength")
            color = _input(node, "Emission Color", "Emission")
            if strength is not None and color is not None:
                luminance = 1.0 if color.is_linked else max(list(color.default_value)[:3])
                value = (1.0 if strength.is_linked else float(strength.default_value)) * luminance
                info["emission"] = max(info["emission"], value)
            alpha = _input(node, "Alpha")
            if alpha is not None and not alpha.is_linked:
                info["alpha_min"] = min(info["alpha_min"], float(alpha.default_value))
        elif node.type == "VALTORGB":
            info["colors"].extend(rgb_hex(element.color) for element in node.color_ramp.elements)
        elif node.type == "RGB":
            info["colors"].append(rgb_hex(node.outputs[0].default_value))
        elif node.type == "EMISSION":
            strength = _input(node, "Strength")
            if strength is not None:
                info["emission"] = max(info["emission"], float(strength.default_value))
        elif node.type == "SUBSURFACE_SCATTERING":
            info["subsurface"] = max(info["subsurface"], 1.0)
        elif node.type in {"BSDF_TRANSPARENT", "BSDF_GLASS", "BSDF_REFRACTION"}:
            info["transmission"] = max(info["transmission"], 1.0)
        elif node.type == "TEX_IMAGE" and node.image is not None:
            image = node.image
            info["images"].append(image.name)
            mean = _image_mean_hex(image)
            if mean:
                info["colors"].append(mean)
    return info


def _image_metrics(image) -> dict:
    try:
        has_data = bool(image.has_data) or bool(image.packed_file) or image.pixels[0] is not None
    except (RuntimeError, IndexError):
        has_data = False
    return {
        "name": image.name,
        "source": image.source,
        "packed": image.packed_file is not None,
        "has_data": has_data,
        "size": list(image.size),
        "users": image.users,
    }


# --------------------------------------------------------------------------- rig & animation


def _bone_metrics(armature) -> list[dict]:
    matrix = armature.matrix_world
    return [
        {
            "name": bone.name,
            "parent": bone.parent.name if bone.parent else None,
            "head": [round(v, 5) for v in (matrix @ bone.head_local)],
            "tail": [round(v, 5) for v in (matrix @ bone.tail_local)],
            "length": round(bone.length, 5),
            "use_deform": bone.use_deform,
        }
        for bone in armature.data.bones
    ]


def _action_fcurves(action) -> list:
    try:
        return list(action.fcurves)
    except (AttributeError, RuntimeError):
        return []


def _action_metrics(action, armature, height: float, scene) -> dict:
    fcurves = _action_fcurves(action)
    keyframes = sum(len(fcurve.keyframe_points) for fcurve in fcurves)
    nan = sum(
        1
        for fcurve in fcurves
        for point in fcurve.keyframe_points
        if not all(math.isfinite(value) for value in point.co)
    )
    start, end = (float(value) for value in action.frame_range)
    info = {
        "name": action.name,
        "frame_start": start,
        "frame_end": end,
        "frames": round(end - start + 1, 3),
        "fcurves": len(fcurves),
        "keyframes": keyframes,
        "nan_keyframes": nan,
        "use_fake_user": action.use_fake_user,
        "users": action.users,
        "targets_pose_bones": any(fc.data_path.startswith("pose.bones") for fc in fcurves),
        "use_cyclic": bool(getattr(action, "use_cyclic", False)),
        "motion": None,
    }
    if armature is None or not info["targets_pose_bones"] or height <= 0:
        return info

    assign_action(armature, action)
    frames = np.linspace(start, end, MOTION_SAMPLES)
    samples = []
    for frame in frames:
        whole = int(math.floor(frame))
        scene.frame_set(whole, subframe=float(frame - whole))
        matrix = armature.matrix_world
        samples.append([list(matrix @ pbone.tail) for pbone in armature.pose.bones])
    positions = np.array(samples)  # (échantillons, os, 3)
    displacement = np.linalg.norm(positions - positions[0], axis=2).max(axis=0) / height
    loop_delta = np.linalg.norm(positions[-1] - positions[0], axis=1).max() / height
    names = [pbone.name for pbone in armature.pose.bones]
    info["motion"] = {
        "max_displacement_ratio": round(float(displacement.max()), 5),
        "per_bone": {
            name: round(float(value), 5) for name, value in zip(names, displacement, strict=True)
        },
        "loop_delta_ratio": round(float(loop_delta), 5),
    }
    return info


# --------------------------------------------------------------------------- main


def main() -> None:
    args = parse_args([("--out", {"required": True}), ("--bone-pattern", {"required": True})])
    scene = bpy.context.scene
    set_pose_position("REST")
    scene.frame_set(scene.frame_start)
    depsgraph = bpy.context.evaluated_depsgraph_get()

    armatures = [obj for obj in scene.objects if obj.type == "ARMATURE"]
    deform_bones = {bone.name for arm in armatures for bone in arm.data.bones if bone.use_deform}
    meshes = creature_meshes()
    mesh_metrics = []
    all_points = []
    all_dominant: list[str | None] = []
    for obj in meshes:
        metrics, coords, dominant = _mesh_metrics(obj, depsgraph, deform_bones)
        mesh_metrics.append(metrics)
        all_points.append(coords)
        all_dominant.extend(dominant)
    points = np.concatenate(all_points) if all_points else np.zeros((0, 3))
    bbox = world_bbox(meshes)
    height = (bbox[1][2] - bbox[0][2]) if bbox else 0.0
    ground = _ground_contacts(
        points, all_dominant, height, bbox[0][2] if bbox else 0.0, args.bone_pattern
    )

    armature_info = [
        {
            "name": arm.name,
            "bones": _bone_metrics(arm),
            "has_animation_data": arm.animation_data is not None,
            "nla_tracks": [track.name for track in arm.animation_data.nla_tracks]
            if arm.animation_data
            else [],
        }
        for arm in armatures
    ]
    main_armature = max(armatures, key=lambda arm: len(arm.data.bones)) if armatures else None
    set_pose_position("POSE")
    actions = [_action_metrics(act, main_armature, height, scene) for act in bpy.data.actions]
    set_pose_position("REST")

    write_json(
        args.out,
        {
            "blender_version": bpy.app.version_string,
            "scene": {
                "fps": round(scene.render.fps / (scene.render.fps_base or 1.0), 3),
                "frame_start": scene.frame_start,
                "frame_end": scene.frame_end,
                "unit_system": scene.unit_settings.system,
                "scale_length": scene.unit_settings.scale_length,
            },
            "objects": [
                {
                    "name": obj.name,
                    "type": obj.type,
                    "parent": obj.parent.name if obj.parent else None,
                    "hide_render": obj.hide_render,
                    "collections": [col.name for col in obj.users_collection],
                }
                for obj in scene.objects
            ],
            "collections": [col.name for col in bpy.data.collections],
            "bbox": bbox,
            "height": round(height, 5),
            "meshes": mesh_metrics,
            "ground": ground,
            "materials": [_material_metrics(mat) for mat in bpy.data.materials if mat.users],
            "images": [_image_metrics(img) for img in bpy.data.images if img.users],
            "armatures": armature_info,
            "actions": actions,
            "orphans": {
                "meshes": sum(1 for block in bpy.data.meshes if block.users == 0),
                "materials": sum(1 for block in bpy.data.materials if block.users == 0),
                "images": sum(1 for block in bpy.data.images if block.users == 0),
            },
        },
    )


main()
