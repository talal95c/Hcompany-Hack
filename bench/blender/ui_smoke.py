"""Non-background Xvfb screenshot and geometry check."""

import json
from pathlib import Path

import bpy


def capture() -> None:
    output = Path(__file__).resolve().parents[1] / "results"
    output.mkdir(exist_ok=True)
    bpy.ops.screen.screenshot(filepath=str(output / "ui-smoke.png"))
    geometry = [
        {
            "type": area.type,
            "x": area.x,
            "y": area.y,
            "width": area.width,
            "height": area.height,
            "regions": [
                {
                    "type": region.type,
                    "x": region.x,
                    "y": region.y,
                    "width": region.width,
                    "height": region.height,
                }
                for region in area.regions
            ],
        }
        for area in bpy.context.screen.areas
    ]
    (output / "ui-geometry.json").write_text(json.dumps(geometry, indent=2) + "\n")
    print("UI screenshot saved; areas:", len(geometry), flush=True)
    bpy.ops.wm.quit_blender()


bpy.app.timers.register(capture, first_interval=10)
