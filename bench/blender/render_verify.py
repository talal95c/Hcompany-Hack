"""Scènes graphiques déterministes et vérité terrain bpy avant capture externe."""

import argparse
import json
import sys
from pathlib import Path

import bpy

SCENES = [
    {"kind": "cube"},
    {"kind": "empty"},
    {"kind": "torus"},
    {"kind": "sphere"},
    {"kind": "cube", "edit": True},
    {"kind": "torus", "edit": True},
    {"kind": "cube", "modifier": True},
    {"kind": "pair"},
    {"kind": "cube", "scale": 2},
    {"kind": "cube", "sidebar": True},
]
parser = argparse.ArgumentParser()
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
bpy.context.preferences.view.show_splash = False
index = 0


def prepare():
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    config = SCENES[index]
    kind = config["kind"]
    if kind in ("cube", "pair"):
        bpy.ops.mesh.primitive_cube_add(location=(-2, 0, 0) if kind == "pair" else (0, 0, 0))
        bpy.context.object.scale = (config.get("scale", 1),) * 3
    if kind in ("torus", "pair"):
        bpy.ops.mesh.primitive_torus_add(location=(2, 0, 0) if kind == "pair" else (0, 0, 0))
    if kind == "sphere":
        bpy.ops.mesh.primitive_uv_sphere_add()
    if config.get("modifier"):
        bpy.context.object.modifiers.new("Bevel", "BEVEL")
    for area in bpy.context.screen.areas:
        if area.type == "PROPERTIES":
            area.spaces.active.context = "SCENE"
        if area.type == "VIEW_3D":
            area.spaces.active.show_region_ui = config.get("sidebar", False)
            region = next(r for r in area.regions if r.type == "WINDOW")
            if kind != "empty":
                with bpy.context.temp_override(area=area, region=region):
                    bpy.ops.view3d.view_all(center=False)
    if config.get("edit"):
        bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=2)
    bpy.app.timers.register(configure_ui, first_interval=1)


def configure_ui():
    if SCENES[index].get("modifier"):
        properties = next(a for a in bpy.context.screen.areas if a.type == "PROPERTIES")
        properties.spaces.active.context = "MODIFIER"
    bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=2)
    bpy.app.timers.register(publish, first_interval=1)


def publish():
    objects = list(bpy.context.scene.objects)
    properties = next(a for a in bpy.context.screen.areas if a.type == "PROPERTIES")
    viewport = next(a for a in bpy.context.screen.areas if a.type == "VIEW_3D")
    facts = {
        "has_cube": any(o.name.startswith("Cube") for o in objects),
        "has_torus": any(o.name.startswith("Torus") for o in objects),
        "has_sphere": any(o.name.startswith("Sphere") for o in objects),
        "empty_scene": not objects,
        "editing": bpy.context.mode == "EDIT_MESH",
        "modifier_panel": properties.spaces.active.context == "MODIFIER",
        "two_meshes": len([o for o in objects if o.type == "MESH"]) == 2,
        "cube_scaled": any(
            o.name.startswith("Cube") and tuple(o.scale) == (2, 2, 2) for o in objects
        ),
        "sidebar": viewport.spaces.active.show_region_ui,
    }
    window = bpy.context.window
    evidence = {
        "facts": facts,
        "mode": bpy.context.mode,
        "objects": [{"name": o.name, "type": o.type, "scale": list(o.scale)} for o in objects],
        "version": bpy.app.version_string,
        "window_size": [window.width, window.height],
    }
    (args.out / f"blender-{index:02d}.evidence.json").write_text(json.dumps(evidence))
    bpy.app.timers.register(advance, first_interval=0.1)


def advance():
    global index
    if not (args.out / f"blender-{index:02d}.ack").exists():
        return 0.1
    index += 1
    if index == len(SCENES):
        bpy.ops.wm.quit_blender()
    else:
        bpy.app.timers.register(prepare, first_interval=0.2)


bpy.app.timers.register(prepare, first_interval=2)
