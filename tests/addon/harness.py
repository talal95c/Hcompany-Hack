"""Pilote headless : Blender n'entretient pas sa boucle UI en mode background."""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.append(os.environ["ADDON_TEST_SITE"])

import bpy  # noqa: E402

import addon  # noqa: E402

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
addon.register()
runtime = addon._runtime
assert bpy.app.timers.is_registered(runtime.timer)
started = time.monotonic()
actions = [
    (0.4, "torus", lambda: bpy.ops.mesh.primitive_torus_add()),
    (0.8, "cube", lambda: bpy.ops.mesh.primitive_cube_add()),
    (1.2, "subdivision", lambda: bpy.ops.object.modifier_add(type="SUBSURF")),
    (1.6, "edit", lambda: bpy.ops.object.mode_set(mode="EDIT")),
    (1.9, "object", lambda: bpy.ops.object.mode_set(mode="OBJECT")),
]
try:
    while time.monotonic() - started < 30:
        if actions and time.monotonic() - started >= actions[0][0]:
            _, name, action = actions.pop(0)
            before = time.monotonic() * 1000
            action()
            bpy.context.view_layer.update()
            print("ACTION " + json.dumps({"name": name, "started_ms": before}), flush=True)
        runtime.tick()
        if "finish" in runtime.results:
            for _ in range(30):
                runtime.tick()
                time.sleep(0.01)
            bpy.ops.wm.save_as_mainfile(filepath=os.environ["ADDON_TEST_FILE"])
            bpy.ops.wm.open_mainfile(filepath=os.environ["ADDON_TEST_FILE"])
            assert runtime.on_graph in bpy.app.handlers.depsgraph_update_post
            assert runtime.on_load in bpy.app.handlers.load_post
            assert runtime.on_undo in bpy.app.handlers.undo_post
            assert bpy.app.timers.is_registered(runtime.timer)
            runtime.tick()
            before = runtime.snapshot()
            obj = bpy.context.active_object
            old_id = runtime.identity(obj)
            obj.name = "Objet renommé"
            assert runtime.identity(obj) == old_id
            bpy.ops.object.select_all(action="SELECT")
            bpy.ops.object.delete(use_global=False)
            bpy.context.view_layer.update()
            runtime.observe()
            assert before["objects"]
            assert runtime.snapshot()["objects"] == []
            assert runtime.selection == {"selected_ids": [], "active": None}
            runtime.emit("snapshot", runtime.snapshot())
            runtime.flush()
            break
        time.sleep(0.005)
    else:
        raise RuntimeError("Le moteur de test n'a pas terminé")
finally:
    addon.unregister()
assert not bpy.app.timers.is_registered(runtime.timer)
assert runtime.on_graph not in bpy.app.handlers.depsgraph_update_post
assert not runtime.transport.thread.is_alive()
