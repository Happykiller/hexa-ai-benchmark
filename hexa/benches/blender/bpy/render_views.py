"""Rendus imposés par l'auditeur, identiques pour tous les livrables.

Modes :
  normalized  vues FACE / PROFIL / DOS en caméra orthographique, pose de repos :
              - `flat`   : passe ALBÉDO (Diffuse Color + Transmission Color de Cycles,
                           composées) → couleurs de base sans éclairage ni reflets, pour
                           la palette ; l'alpha donne la silhouette ;
              - `beauty` : éclairage trois points lié à la caméra (visuels KB, netteté).
  turntable   N images en orbite autour de la créature (pose de repos).
  animation   chaque image de chaque action (plafonnée à max_frames), caméra 3/4 fixe.

Déterminisme : Cycles CPU, échantillons / seed / threads figés, échantillonnage adaptatif,
débruitage et path guiding désactivés. Caméras, lumières et monde du livrable sont retirés.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json  # noqa: E402
import math  # noqa: E402

import bpy  # noqa: E402
from _common import (  # noqa: E402
    assign_action,
    creature_meshes,
    parse_args,
    set_pose_position,
    world_bbox,
    write_json,
)
from mathutils import Vector  # noqa: E402

# Caméra orthographique : (position relative au centre, rotation euler en degrés).
# La créature regarde -Y ; la caméra "left" (en -X) montre la tête à droite de l'image,
# comme la vignette PROFIL de la planche.
VIEWS = {
    "front": ((0.0, -1.0, 0.0), (90.0, 0.0, 0.0)),
    "back": ((0.0, 1.0, 0.0), (90.0, 0.0, 180.0)),
    "left": ((-1.0, 0.0, 0.0), (90.0, 0.0, -90.0)),
    "right": ((1.0, 0.0, 0.0), (90.0, 0.0, 90.0)),
}


def configure_render(scene, resolution, samples: int, seed: int, threads: int) -> None:
    scene.render.engine = "CYCLES"
    cycles = scene.cycles
    cycles.device = "CPU"
    cycles.samples = samples
    cycles.seed = seed
    cycles.use_animated_seed = False
    cycles.use_adaptive_sampling = False
    cycles.use_denoising = False
    if hasattr(cycles, "use_guiding"):
        cycles.use_guiding = False
    cycles.max_bounces = 6
    scene.render.threads_mode = "FIXED"
    scene.render.threads = threads
    scene.render.resolution_x, scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.use_motion_blur = False
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
    # Pas de tampons Blender (date, nom de machine…). Cycles ajoute tout de même ses temps de
    # rendu en métadonnées PNG : le déterminisme se juge donc sur les PIXELS, et les images
    # publiées dans la KB sont ré-encodées sans métadonnées (auditor/media.py).
    for attribute in dir(scene.render):
        if attribute.startswith("use_stamp"):
            setattr(scene.render, attribute, False)
    image = scene.render.image_settings
    image.file_format = "PNG"
    image.color_mode = "RGBA"
    image.color_depth = "8"
    image.compression = 15


def set_albedo_output(scene, enabled: bool) -> None:
    """Sortie = albédo (DiffCol + TransCol) avec l'alpha du rendu, ou l'image normale.

    Mesurer la couleur sur l'image éclairée confondrait la teinte des matériaux avec les
    reflets : une chitine noire brillante y paraît grise. L'albédo est la couleur peinte.
    """
    view_layer = scene.view_layers[0]
    view_layer.use_pass_diffuse_color = enabled
    view_layer.use_pass_transmission_color = enabled
    scene.use_nodes = enabled
    if not enabled:
        return
    tree = scene.node_tree
    for node in list(tree.nodes):
        if node.type not in {"R_LAYERS", "COMPOSITE"}:
            tree.nodes.remove(node)
    layers = next(node for node in tree.nodes if node.type == "R_LAYERS")
    composite = next(node for node in tree.nodes if node.type == "COMPOSITE")
    add = tree.nodes.new("CompositorNodeMixRGB")
    add.blend_type = "ADD"
    add.inputs[0].default_value = 1.0
    tree.links.new(layers.outputs["DiffCol"], add.inputs[1])
    tree.links.new(layers.outputs["TransCol"], add.inputs[2])
    alpha = tree.nodes.new("CompositorNodeSetAlpha")
    alpha.mode = "REPLACE_ALPHA"
    tree.links.new(add.outputs[0], alpha.inputs["Image"])
    tree.links.new(layers.outputs["Alpha"], alpha.inputs["Alpha"])
    tree.links.new(alpha.outputs[0], composite.inputs["Image"])


def strip_scene(scene) -> None:
    """Retire caméras, lumières et monde du livrable : l'auditeur impose les siens."""
    for obj in list(scene.objects):
        if obj.type in {"CAMERA", "LIGHT", "LIGHT_PROBE"}:
            bpy.data.objects.remove(obj, do_unlink=True)
    world = bpy.data.worlds.new("hexa_world")
    world.use_nodes = True
    scene.world = world


def set_world(scene, color, strength: float) -> None:
    background = scene.world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (*color, 1.0)
    background.inputs["Strength"].default_value = strength


def new_camera(scene, name: str, ortho: bool):
    data = bpy.data.cameras.new(name)
    data.type = "ORTHO" if ortho else "PERSP"
    data.clip_start = 0.01
    data.clip_end = 1000.0
    camera = bpy.data.objects.new(name, data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    return camera


def add_rig_lights(scene, camera) -> list:
    """Éclairage trois points attaché à la caméra (même lumière relative pour chaque vue)."""
    lights = []
    for name, energy, rotation in (
        ("hexa_key", 3.5, (-35.0, -40.0, 0.0)),
        ("hexa_fill", 1.2, (-20.0, 45.0, 0.0)),
        ("hexa_rim", 4.0, (150.0, 0.0, 0.0)),
    ):
        data = bpy.data.lights.new(name, "SUN")
        data.energy = energy
        data.angle = math.radians(8.0)
        light = bpy.data.objects.new(name, data)
        scene.collection.objects.link(light)
        light.parent = camera
        light.rotation_euler = [math.radians(v) for v in rotation]
        lights.append(light)
    return lights


def remove(objects) -> None:
    for obj in objects:
        bpy.data.objects.remove(obj, do_unlink=True)


def render_to(scene, path: str) -> None:
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def frame_ortho(camera, bbox, view: str, aspect: float) -> None:
    mins, maxs = Vector(bbox[0]), Vector(bbox[1])
    center = (mins + maxs) / 2
    size = maxs - mins
    direction, rotation = VIEWS[view]
    horizontal = size.x if view in {"front", "back"} else size.y
    # ortho_scale couvre la plus grande dimension de l'image (ici la hauteur).
    camera.data.ortho_scale = 1.1 * max(size.z, horizontal / aspect)
    distance = 2.0 * max(size) + 1.0
    camera.location = center + Vector(direction) * distance
    camera.rotation_euler = [math.radians(v) for v in rotation]


def frame_orbit(camera, bbox, azimuth_deg: float, elevation_deg: float = 15.0) -> None:
    mins, maxs = Vector(bbox[0]), Vector(bbox[1])
    center = (mins + maxs) / 2
    radius = (maxs - mins).length / 2
    camera.data.lens = 50.0
    fov = 2 * math.atan(camera.data.sensor_width / (2 * camera.data.lens))
    distance = 0.95 * radius / math.sin(fov / 2)
    azimuth, elevation = math.radians(azimuth_deg), math.radians(elevation_deg)
    offset = Vector(
        (
            math.sin(azimuth) * math.cos(elevation),
            -math.cos(azimuth) * math.cos(elevation),
            math.sin(elevation),
        )
    )
    camera.location = center + offset * distance
    look = center - camera.location
    camera.rotation_euler = look.to_track_quat("-Z", "Y").to_euler()


def main() -> None:
    args = parse_args(
        [
            ("--mode", {"required": True, "choices": ["normalized", "turntable", "animation"]}),
            ("--out-dir", {"required": True}),
            ("--profile", {"required": True, "help": "JSON: bloc render de spec.json"}),
            ("--views", {"default": "front,left,back"}),
            ("--actions", {"default": ""}),
            ("--log", {"required": True}),
        ]
    )
    profile = json.loads(args.profile)
    scene = bpy.context.scene
    os.makedirs(args.out_dir, exist_ok=True)
    strip_scene(scene)
    seed, threads = profile["seed"], profile["threads"]
    outputs: list[str] = []
    log = {"mode": args.mode, "outputs": outputs, "error": None}

    set_pose_position("REST")
    scene.frame_set(scene.frame_start)
    meshes = creature_meshes()
    bbox = world_bbox(meshes)
    if bbox is None:
        log["error"] = "aucun maillage à rendre"
        write_json(args.log, log)
        return
    log["bbox"] = bbox

    if args.mode == "normalized":
        camera = new_camera(scene, "hexa_cam", ortho=True)
        for view in args.views.split(","):
            for variant in ("flat", "beauty"):
                settings = profile[variant]
                configure_render(scene, settings["resolution"], settings["samples"], seed, threads)
                aspect = settings["resolution"][0] / settings["resolution"][1]
                frame_ortho(camera, bbox, view, aspect)
                lights = []
                set_albedo_output(scene, variant == "flat")
                if variant == "flat":
                    set_world(scene, (1.0, 1.0, 1.0), 1.0)
                else:
                    set_world(scene, (0.75, 0.78, 0.85), 0.35)
                    lights = add_rig_lights(scene, camera)
                path = os.path.join(args.out_dir, f"view_{view}_{variant}.png")
                render_to(scene, path)
                outputs.append(path)
                remove(lights)

    elif args.mode == "turntable":
        settings = profile["turntable"]
        configure_render(scene, settings["resolution"], settings["samples"], seed, threads)
        set_world(scene, (0.75, 0.78, 0.85), 0.35)
        camera = new_camera(scene, "hexa_cam", ortho=False)
        add_rig_lights(scene, camera)
        frames = settings["frames"]
        for index in range(frames):
            frame_orbit(camera, bbox, 360.0 * index / frames)
            path = os.path.join(args.out_dir, f"turntable_{index:03d}.png")
            render_to(scene, path)
            outputs.append(path)

    else:
        settings = profile["animation"]
        configure_render(scene, settings["resolution"], settings["samples"], seed, threads)
        set_world(scene, (0.75, 0.78, 0.85), 0.35)
        camera = new_camera(scene, "hexa_cam", ortho=False)
        add_rig_lights(scene, camera)
        # Cadrage fixe sur la boîte de repos élargie : le mouvement reste visible.
        mins, maxs = Vector(bbox[0]), Vector(bbox[1])
        pad = (maxs - mins) * 0.08
        frame_orbit(camera, [list(mins - pad), list(maxs + pad)], 35.0, 12.0)
        armatures = [obj for obj in scene.objects if obj.type == "ARMATURE"]
        armature = max(armatures, key=lambda arm: len(arm.data.bones)) if armatures else None
        set_pose_position("POSE")
        log["actions"] = {}
        for name in [name for name in args.actions.split(",") if name]:
            action = bpy.data.actions.get(name)
            if action is None or armature is None:
                continue
            assign_action(armature, action)
            start, end = (int(round(value)) for value in action.frame_range)
            frames = list(range(start, end + 1))
            if len(frames) > settings["max_frames"]:  # sous-échantillonnage régulier
                step = len(frames) / settings["max_frames"]
                frames = [frames[int(index * step)] for index in range(settings["max_frames"])]
            for index, frame in enumerate(frames):
                scene.frame_set(frame)
                path = os.path.join(args.out_dir, f"anim_{name}_{index:03d}.png")
                render_to(scene, path)
                outputs.append(path)
            fps = scene.render.fps / (scene.render.fps_base or 1.0)
            duration = (end - start + 1) / fps
            # Cadence de lecture qui restitue la durée réelle de l'action.
            log["actions"][name] = {
                "frames": len(frames),
                "duration_s": round(duration, 3),
                "fps": round(len(frames) / duration, 3) if duration > 0 else 24,
            }

    write_json(args.log, log)


main()
