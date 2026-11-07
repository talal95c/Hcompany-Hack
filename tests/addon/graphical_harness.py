"""Graphical integration driver; Blender owns all timer scheduling."""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.append(os.environ["ADDON_TEST_SITE"])

import bpy  # noqa: E402

import addon  # noqa: E402

bpy.context.preferences.view.show_splash = False
assert not bpy.app.background
addon.register()
runtime = addon._runtime
started = time.monotonic()
measured = False
finish_after = None


def monitor() -> float | None:
    global measured, finish_after
    assert bpy.app.timers.is_registered(runtime.timer)
    if "measure_action" in runtime.results and not measured:
        measured = True
        before = time.monotonic() * 1000
        bpy.ops.mesh.primitive_cube_add()
        bpy.context.view_layer.update()
        print("ACTION " + json.dumps({"started_ms": before}), flush=True)
    if "finish" in runtime.results:
        if finish_after is None:
            finish_after = time.monotonic() + 0.5
        elif time.monotonic() >= finish_after:
            addon.unregister()
            bpy.ops.wm.quit_blender()
            return None
    if time.monotonic() - started > 60:
        raise RuntimeError("Graphical engine test timed out")
    return 0.05


bpy.app.timers.register(monitor, first_interval=0.1)
