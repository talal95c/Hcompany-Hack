"""Toutes les lectures et mutations bpy s'exécutent sur le thread principal."""

import json
import math
import os
import queue
import re
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any

import bpy
from bpy.app.handlers import persistent
from jsonschema import Draft202012Validator, ValidationError

from .transport import Transport


class Refused(Exception):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(detail)


class Runtime:
    def __init__(self, port: int, session: str) -> None:
        if not session:
            raise ValueError("Jeton de session manquant")
        self.session = session
        self.transport = Transport(port)
        root = Path(__file__).resolve().parents[1] / "contracts"
        self.commands = Draft202012Validator(
            json.loads((root / "commands.schema.json").read_text())
        )
        self.events = Draft202012Validator(
            json.loads((root / "addon-events.schema.json").read_text())
        )
        self.revision = 0
        self.seq = 0
        self.ui_revision = 0
        self.connection = 0
        self.started = time.monotonic()
        self.heartbeat = 0.0
        self.last_poll = 0.0
        self.dirty = True
        self.updated: set[int] = set()
        self.previous: dict[str, dict[str, Any]] = {}
        self.mode = ""
        self.selection: Any = None
        self.regions: Any = None
        self.operators: set[int] = set()
        self.results: dict[str, dict[str, Any]] = {}
        self.pending: deque[tuple[str, dict[str, Any]]] = deque()
        self.handles: list[tuple[Any, Any, str, Any, float]] = []
        self.owner = object()
        self.checkpoint: tuple[str, int] | None = None
        self.running = False
        self.timer = self.tick
        self.on_notify = lambda: self.notify()
        self.on_graph = persistent(lambda scene, graph: self._graph(scene, graph))
        self.on_load = persistent(lambda *args: self._load(*args))
        self.on_undo = persistent(lambda *args: self._undo(*args))

    @classmethod
    def from_environment(cls) -> "Runtime":
        return cls(int(os.environ["ADDON_ENGINE_PORT"]), os.environ["ADDON_SESSION_TOKEN"])

    def start(self) -> None:
        self.running = True
        bpy.app.handlers.depsgraph_update_post.append(self.on_graph)
        bpy.app.handlers.load_post.append(self.on_load)
        bpy.app.handlers.undo_post.append(self.on_undo)
        self.subscribe()
        self.transport.start()
        bpy.app.timers.register(self.timer, first_interval=0.01, persistent=True)

    def stop(self) -> None:
        self.running = False
        if bpy.app.timers.is_registered(self.timer):
            bpy.app.timers.unregister(self.timer)
        for handlers, callback in (
            (bpy.app.handlers.depsgraph_update_post, self.on_graph),
            (bpy.app.handlers.load_post, self.on_load),
            (bpy.app.handlers.undo_post, self.on_undo),
        ):
            if callback in handlers:
                handlers.remove(callback)
        bpy.msgbus.clear_by_owner(self.owner)
        self.clear_highlights()
        self.transport.stop()

    def subscribe(self) -> None:
        bpy.msgbus.clear_by_owner(self.owner)
        for key in ((bpy.types.Object, "mode"), (bpy.types.LayerObjects, "active")):
            bpy.msgbus.subscribe_rna(key=key, owner=self.owner, args=(), notify=self.on_notify)

    def notify(self) -> None:
        self.dirty = True

    def _graph(self, scene: Any, graph: Any) -> None:
        self.dirty = True
        self.updated.update(update.id.original.as_pointer() for update in graph.updates)

    def _load(self, *_: Any) -> None:
        self.clear_highlights()
        self.previous.clear()
        self.updated.clear()
        self.operators.clear()
        self.regions = None
        self.checkpoint = None
        for obj in bpy.data.objects:
            if "_lesson_id" in obj:
                del obj["_lesson_id"]
        self.subscribe()
        self.dirty = True
        self.emit("snapshot", self.snapshot())

    def _undo(self, *_: Any) -> None:
        self.dirty = True
        self.checkpoint = None
        self.emit("undo", {"count": 1})

    def identity(self, obj: Any) -> str:
        value = obj.get("_lesson_id")
        if not isinstance(value, str) or not value:
            value = uuid.uuid4().hex
            obj["_lesson_id"] = value
        return value

    def objects(self) -> list[dict[str, Any]]:
        result = []
        used = set()
        for obj in bpy.context.scene.objects:
            identity = self.identity(obj)
            if identity in used:
                obj["_lesson_id"] = uuid.uuid4().hex
                identity = obj["_lesson_id"]
            used.add(identity)
            data = {
                "id": identity,
                "name": obj.name,
                "type": obj.type,
                "location": list(obj.location),
                "rotation_euler": list(obj.rotation_euler),
                "scale": list(obj.scale),
                "selected": obj.select_get(),
                "modifiers": [
                    {
                        "name": m.name,
                        "type": m.type,
                        **({"levels": m.levels} if m.type == "SUBSURF" else {}),
                    }
                    for m in obj.modifiers
                ],
                "materials": [m.name if m else None for m in getattr(obj.data, "materials", [])],
            }
            if obj.type == "MESH":
                data["mesh"] = {"verts": len(obj.data.vertices), "polys": len(obj.data.polygons)}
            if obj.get("_lesson_primitive"):
                data["primitive_provenance"] = obj["_lesson_primitive"]
            result.append(data)
        return result

    def active(self) -> str | None:
        obj = bpy.context.view_layer.objects.active
        return self.identity(obj) if obj else None

    def snapshot(self) -> dict[str, Any]:
        return {"mode": bpy.context.mode, "active": self.active(), "objects": self.objects()}

    def emit(self, kind: str, payload: dict[str, Any]) -> None:
        if kind == "scene.changed":
            changed = set(payload["changed_ids"])
            for previous_kind, previous_payload in self.pending:
                if previous_kind == kind:
                    changed.update(previous_payload["changed_ids"])
            current = {o["id"]: o for o in self.objects()}
            payload = {
                "changed_ids": sorted(changed),
                "objects": [current[key] for key in changed if key in current],
            }
            self.pending = deque((k, p) for k, p in self.pending if k != kind)
        self.pending.append((kind, payload))

    def flush(self) -> None:
        while self.pending and not self.transport.outgoing.full():
            kind, payload = self.pending.popleft()
            self.seq += 1
            event = {
                "schema_version": "1.0",
                "session_id": self.session,
                "event_id": uuid.uuid4().hex,
                "seq": self.seq,
                "type": kind,
                "ts_monotonic_ms": time.monotonic() * 1000,
                "scene_revision": self.revision,
                "payload": payload,
            }
            self.events.validate(event)
            self.transport.outgoing.put_nowait(event)

    def observe(self) -> None:
        operators = list(bpy.context.window_manager.operators)
        for operator in operators:
            if operator.as_pointer() in self.operators:
                continue
            properties = {}
            for prop in operator.properties.bl_rna.properties:
                if prop.identifier == "rna_type":
                    continue
                value = getattr(operator.properties, prop.identifier, None)
                if isinstance(value, (str, int, float, bool)):
                    properties[prop.identifier] = value
            self.emit("operator.executed", {"idname": operator.bl_idname, "properties": properties})
            primitive = {
                "MESH_OT_primitive_torus_add": "torus",
                "MESH_OT_primitive_cube_add": "cube",
            }.get(operator.bl_idname)
            obj = bpy.context.active_object
            if primitive and operator == operators[-1] and obj and obj.type == "MESH":
                if self.identity(obj) not in self.previous:
                    obj["_lesson_primitive"] = primitive
        self.operators = {o.as_pointer() for o in operators}
        objects = self.objects()
        current = {o["id"]: o for o in objects}
        mode = bpy.context.mode
        selection = {
            "selected_ids": sorted(o["id"] for o in objects if o["selected"]),
            "active": self.active(),
        }
        updated = {
            self.identity(o)
            for o in bpy.context.scene.objects
            if o.as_pointer() in self.updated or (o.data and o.data.as_pointer() in self.updated)
        }
        self.updated.clear()
        if current != self.previous or updated or mode != self.mode or selection != self.selection:
            changed = [
                key
                for key in current.keys() | self.previous.keys()
                if current.get(key) != self.previous.get(key) or key in updated
            ]
            self.revision += 1
            self.emit(
                "scene.changed",
                {"changed_ids": changed, "objects": [current[k] for k in changed if k in current]},
            )
            self.previous = current
        if mode != self.mode:
            self.emit("mode.changed", {"previous": self.mode or mode, "current": mode})
            self.mode = mode
        if selection != self.selection:
            self.emit("selection.changed", selection)
            self.selection = selection
        regions = self.region_data()
        if regions != self.regions:
            self.ui_revision += 1
            self.emit("regions.changed", {"ui_revision": self.ui_revision, "regions": regions})
            self.regions = regions
        self.dirty = False

    def region_contexts(self) -> list[tuple[Any, Any, Any]]:
        if bpy.app.background:
            return []
        return [
            (w, a, r)
            for w in bpy.context.window_manager.windows
            for a in w.screen.areas
            for r in a.regions
            if r.width > 0 and r.height > 0
        ]

    def region_data(self) -> list[dict[str, Any]]:
        return [
            {
                "area_id": str(a.as_pointer()),
                "region_id": str(r.as_pointer()),
                "type": r.type,
                "rect": {"x": r.x, "y": r.y, "width": r.width, "height": r.height},
                "scale": bpy.context.preferences.system.ui_scale,
                "monitor_id": str(w.as_pointer()),
            }
            for w, a, r in self.region_contexts()
        ]

    def tick(self) -> float | None:
        if not self.running:
            return None
        now = time.monotonic()
        if self.transport.connected.is_set() and self.connection != self.transport.generation:
            self.connection = self.transport.generation
            while not self.transport.outgoing.empty():
                self.transport.outgoing.get_nowait()
            while not self.transport.incoming.empty():
                self.transport.incoming.get_nowait()
            self.pending.clear()
            self.seq = 0
            self.checkpoint = None
            self.emit(
                "hello",
                {
                    "blender_version": bpy.app.version_string,
                    "capabilities": ["snapshot", "replay", "regions", "highlight"],
                },
            )
            self.observe()
            self.emit("snapshot", self.snapshot())
            self.flush()
            self.transport.ready.set()
        if self.transport.connected.is_set():
            if now - self.last_poll >= 0.1 and len(self.pending) < 128:
                self.observe()
                self.last_poll = now
            for _ in range(16):
                if len(self.pending) >= 128:
                    break
                try:
                    received, command = self.transport.incoming.get_nowait()
                except queue.Empty:
                    break
                self.command(command, received)
            if now - self.heartbeat >= 1 and len(self.pending) < 128:
                self.emit("heartbeat", {"uptime_ms": (now - self.started) * 1000})
                self.heartbeat = now
            self.flush()
        self.expire_highlights(now)
        return 0.01

    def command(self, command: dict[str, Any], received: float) -> None:
        try:
            self.commands.validate(command)
        except ValidationError:
            return
        if command["session_id"] != self.session or command["recipient"] != "addon":
            return
        identifier = command["command_id"]
        if identifier in self.results:
            self.emit("command.result", self.results[identifier])
            return
        result = {
            "command_id": identifier,
            "status": "ok",
            "detail": "Commande exécutée",
            "scene_revision": self.revision,
        }
        try:
            self.observe()
            if (time.monotonic() - received) * 1000 >= command["deadline_ms"]:
                result.update(status="expired", detail="Délai dépassé")
            elif command["expected_scene_revision"] not in (None, self.revision):
                raise Refused("stale_state", "La scène a changé")
            else:
                self.execute(command)
                bpy.context.view_layer.update()
                self.observe()
        except Refused as exc:
            result.update(status="rejected", detail=str(exc), error_code=exc.code)
        except (RuntimeError, ValueError, TypeError) as exc:
            result.update(status="failed", detail=str(exc), error_code="bad_context")
        result["scene_revision"] = self.revision
        self.results[identifier] = result
        self.emit("command.result", result)

    def execute(self, command: dict[str, Any]) -> None:
        kind, payload = command["type"], command["payload"]
        if kind == "request_snapshot":
            self.emit("snapshot", self.snapshot())
        elif kind == "clear_highlight":
            self.clear_highlights()
        elif kind in ("highlight", "open_menu"):
            context = next(
                (
                    (w, a, r)
                    for w, a, r in self.region_contexts()
                    if str(a.as_pointer()) == payload["area_id"]
                    and str(r.as_pointer()) == payload["region_id"]
                ),
                None,
            )
            if context is None:
                raise Refused("bad_context", "Région indisponible")
            window, area, region = context
            if kind == "highlight":
                self.highlight(area, region, payload)
            else:
                if payload["menu_id"] not in {"VIEW3D_MT_mesh_add", "VIEW3D_MT_add"}:
                    raise Refused("permission_denied", "Menu non autorisé")
                with bpy.context.temp_override(window=window, area=area, region=region):
                    if "FINISHED" not in bpy.ops.wm.call_menu(name=payload["menu_id"]):
                        raise Refused("bad_context", "Menu indisponible")
        elif kind == "replay":
            self.replay(payload, command["command_id"])
        elif kind == "undo_demo":
            if self.checkpoint != (payload["checkpoint_id"], self.revision):
                raise Refused("stale_state", "Checkpoint absent ou modifié")
            if bpy.app.background or not bpy.ops.ed.undo.poll():
                raise Refused("bad_context", "Annulation indisponible")
            if "FINISHED" not in bpy.ops.ed.undo():
                raise Refused("bad_context", "Annulation refusée")
            self.checkpoint = None

    def replay(self, payload: dict[str, Any], identifier: str) -> None:
        procedure, params = payload["procedure_ref"], payload["params"]
        procedures = {
            "add_torus": (
                bpy.ops.mesh.primitive_torus_add,
                {"major_radius", "minor_radius", "major_segments", "minor_segments"},
            ),
            "add_cube": (bpy.ops.mesh.primitive_cube_add, {"size"}),
            "add_subdivision_modifier": (bpy.ops.object.modifier_add, set()),
        }
        if procedure not in procedures:
            raise Refused("unknown_procedure", "Procédure non autorisée")
        operation, allowed = procedures[procedure]
        if set(params) - allowed or any(
            not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or v <= 0
            for v in params.values()
        ):
            raise Refused("bad_context", "Paramètres invalides")
        if bpy.context.mode != "OBJECT" or not operation.poll():
            raise Refused("bad_context", "Mode ou objet actif incompatible")
        if any(w.modal_operators for w in bpy.context.window_manager.windows):
            raise Refused("busy", "Opérateur modal actif")
        if not bpy.app.background:
            bpy.ops.ed.undo_push(message="Début démonstration")
        arguments = {"type": "SUBSURF"} if procedure == "add_subdivision_modifier" else params
        if "FINISHED" not in operation(**arguments):
            raise Refused("bad_context", "Opération annulée")
        if procedure in ("add_cube", "add_torus"):
            bpy.context.active_object["_lesson_primitive"] = procedure.removeprefix("add_")
        bpy.context.view_layer.update()
        self.observe()
        if not bpy.app.background:
            bpy.ops.ed.undo_push(message="Fin démonstration")
            self.checkpoint = (identifier, self.revision)

    def highlight(self, area: Any, region: Any, payload: dict[str, Any]) -> None:
        import gpu
        from gpu_extras.batch import batch_for_shader

        color = payload["color"]
        if not re.fullmatch(r"#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?", color):
            raise Refused("bad_context", "Couleur hexadécimale attendue")
        rgba = tuple(int(color[i : i + 2], 16) / 255 for i in (1, 3, 5))
        rgba += (int(color[7:9], 16) / 255 if len(color) == 9 else 0.25,)
        shader = gpu.shader.from_builtin("UNIFORM_COLOR")

        def draw() -> None:
            if bpy.context.area != area or bpy.context.region != region:
                return
            vertices = [
                (0, 0),
                (region.width, 0),
                (region.width, region.height),
                (0, region.height),
            ]
            batch = batch_for_shader(shader, "TRI_FAN", {"pos": vertices})
            gpu.state.blend_set("ALPHA")
            try:
                shader.bind()
                shader.uniform_float("color", rgba)
                batch.draw(shader)
            finally:
                gpu.state.blend_set("NONE")

        space = type(area.spaces.active)
        try:
            handle = space.draw_handler_add(draw, (), region.type, "POST_PIXEL")
        except (TypeError, RuntimeError, ValueError) as exc:
            raise Refused("bad_context", "Dessin non supporté") from exc
        self.handles.append(
            (space, handle, region.type, area, time.monotonic() + payload["duration_ms"] / 1000)
        )
        area.tag_redraw()

    def expire_highlights(self, now: float) -> None:
        remaining = []
        for space, handle, region, area, deadline in self.handles:
            if now >= deadline:
                space.draw_handler_remove(handle, region)
                try:
                    area.tag_redraw()
                except ReferenceError:
                    pass
            else:
                remaining.append((space, handle, region, area, deadline))
        self.handles = remaining

    def clear_highlights(self) -> None:
        self.expire_highlights(float("inf"))
