import importlib
import json
import sys
import time
from contextlib import nullcontext
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def runtime(monkeypatch):
    bpy = ModuleType("bpy")
    handlers = ModuleType("bpy.app.handlers")
    handlers.persistent = lambda callback: callback
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    monkeypatch.setitem(sys.modules, "bpy.app.handlers", handlers)
    operation = Mock(return_value={"FINISHED"})
    operation.poll.return_value = True
    bpy.ops = SimpleNamespace(
        mesh=SimpleNamespace(primitive_cube_add=operation, primitive_torus_add=operation),
        object=SimpleNamespace(modifier_add=operation),
        wm=SimpleNamespace(call_menu=Mock(return_value={"INTERFACE"})),
    )
    bpy.context = SimpleNamespace(
        mode="OBJECT",
        view_layer=SimpleNamespace(update=Mock()),
        window_manager=SimpleNamespace(windows=[]),
        active_object={},
        temp_override=lambda **kwargs: nullcontext(),
    )
    bpy.app = SimpleNamespace(background=True, version_string="4.5.9")
    module = importlib.import_module("addon.runtime")
    instance = module.Runtime(12345, "test")
    instance.observe = Mock()
    instance.snapshot = Mock(return_value={"mode": "OBJECT", "active": None, "objects": []})
    yield instance, bpy
    sys.modules.pop("addon.runtime", None)


def command(runtime, kind="replay", payload=None, identifier="test"):
    value = json.loads((ROOT / "contracts/examples/commands/valid/replay.json").read_text())
    value.update(
        session_id=runtime.session,
        command_id=identifier,
        type=kind,
        expected_scene_revision=None,
        payload=payload if payload is not None else value["payload"],
    )
    runtime.command(value, time.monotonic())
    runtime.flush()
    events = []
    while not runtime.transport.outgoing.empty():
        event = runtime.transport.outgoing.get_nowait()
        runtime.events.validate(event)
        events.append(event)
    return events


@pytest.mark.parametrize(
    "params",
    [
        {"size": 10**400},
        {"size": float("inf")},
        {"size": float("nan")},
        {"size": 0},
        {"size": -1},
        {"size": True},
        {"size": 10001},
        {"unknown": 1},
    ],
)
def test_numeric_rejection_and_recovery(runtime, params):
    instance, bpy = runtime
    events = command(instance, payload={"procedure_ref": "add_cube", "params": params})
    assert events[-1]["payload"]["status"] == "rejected"
    bpy.ops.mesh.primitive_cube_add.assert_not_called()
    events = command(instance, "request_snapshot", {}, "next")
    assert [e["type"] for e in events] == ["snapshot", "command.result"]
    assert events[-1]["payload"]["status"] == "ok"


@pytest.mark.parametrize(
    "params, status",
    [
        ({}, "ok"),
        ({"major_segments": 3, "minor_segments": 256}, "ok"),
        ({"major_segments": 2}, "rejected"),
        ({"minor_segments": 257}, "rejected"),
        ({"major_segments": 3.5}, "rejected"),
    ],
)
def test_torus_bounds(runtime, params, status):
    instance, _ = runtime
    events = command(instance, payload={"procedure_ref": "donut/add_torus", "params": params})
    assert events[-1]["payload"]["status"] == status


@pytest.mark.parametrize("error", [OverflowError, KeyError, AssertionError, OSError])
def test_handler_exception_does_not_stop_dispatch(runtime, error):
    instance, _ = runtime
    instance.running = True
    instance.transport.connected.set()
    instance.execute = Mock(side_effect=error("handler failure"))
    value = json.loads((ROOT / "contracts/examples/commands/valid/replay.json").read_text())
    value.update(session_id=instance.session, expected_scene_revision=None)
    instance.transport.incoming.put((time.monotonic(), value))
    assert instance.tick() == 0.01
    result = instance.results[value["command_id"]]
    assert result["status"] == "failed"
    instance.execute.side_effect = None
    events = command(instance, "request_snapshot", {}, "next")
    assert events[-1]["payload"]["status"] == "ok"
    assert instance.tick() == 0.01


def test_timer_survives_observation_error(runtime):
    instance, _ = runtime
    instance.running = True
    instance.transport.connected.set()
    instance.observe.side_effect = ReferenceError("removed context")
    assert instance.tick() == 0.01
    instance.observe.side_effect = None
    assert instance.tick() == 0.01


@pytest.mark.parametrize(
    "status, expected",
    [
        ({"FINISHED"}, "ok"),
        ({"INTERFACE"}, "ok"),
        ({"RUNNING_MODAL"}, "ok"),
        ({"PASS_THROUGH"}, "ok"),
        ({"CANCELLED"}, "rejected"),
    ],
)
def test_menu_operator_results(runtime, status, expected):
    instance, bpy = runtime
    area = SimpleNamespace(as_pointer=lambda: 1)
    region = SimpleNamespace(as_pointer=lambda: 2)
    instance.region_contexts = lambda: [(object(), area, region)]
    bpy.ops.wm.call_menu.return_value = status
    events = command(
        instance,
        "open_menu",
        {
            "area_id": "1",
            "region_id": "2",
            "menu_id": "VIEW3D_MT_mesh_add",
        },
    )
    assert events[-1]["payload"]["status"] == expected


def test_reconnect_publishes_unchanged_region_ids(runtime):
    instance, bpy = runtime
    instance.running = True
    instance.transport.connected.set()
    instance.observe = type(instance).observe.__get__(instance)
    instance.objects = lambda: []
    instance.active = lambda: None
    bpy.context.window_manager.operators = []
    bpy.context.scene = SimpleNamespace(objects=[])
    regions = [
        {
            "area_id": "11",
            "region_id": "12",
            "type": "WINDOW",
            "rect": {"x": 0, "y": 0, "width": 100, "height": 100},
            "scale": 1,
            "monitor_id": "10",
        }
    ]
    instance.region_data = lambda: regions
    for generation in (1, 2):
        instance.transport.generation = generation
        assert instance.tick() == 0.01
        events = []
        while not instance.transport.outgoing.empty():
            event = instance.transport.outgoing.get_nowait()
            instance.events.validate(event)
            events.append(event)
        assert events[0]["type"] == "hello"
        event = next(e for e in events if e["type"] == "regions.changed")
        assert event["payload"] == {"ui_revision": generation, "regions": regions}
