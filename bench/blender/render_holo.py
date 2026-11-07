"""Prepare a real Blender window and export its geometry before external capture."""

import argparse
import json
import sys
from pathlib import Path

import bpy

parser = argparse.ArgumentParser()
parser.add_argument("--scale", type=float, required=True)
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
bpy.context.preferences.view.ui_scale = args.scale
bpy.context.preferences.view.show_splash = False


def prepare() -> None:
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.spaces.active.show_region_ui = True
                area.spaces.active.show_region_toolbar = True
    bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=3)
    bpy.app.timers.register(export, first_interval=3)


def export() -> None:
    windows = []
    for window in bpy.context.window_manager.windows:
        areas = []
        for area in window.screen.areas:
            areas.append(
                {
                    "type": area.type,
                    "x": area.x,
                    "y": area.y,
                    "width": area.width,
                    "height": area.height,
                    "regions": [
                        {"type": r.type, "x": r.x, "y": r.y, "width": r.width, "height": r.height}
                        for r in area.regions
                    ],
                }
            )
        windows.append({"width": window.width, "height": window.height, "areas": areas})
    args.out.write_text(json.dumps({"scale": args.scale, "windows": windows}, indent=2) + "\n")
    print("Geometry ready", flush=True)


bpy.app.timers.register(prepare, first_interval=5)
