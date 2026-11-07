import asyncio
import json
import time
from contextlib import suppress

import pytest
from websockets.asyncio.client import connect

from engine.adapters import AccessibilityAdapter, load_profile
from engine.checks import evaluate
from engine.config import EngineConfig
from engine.lesson.runtime import EngineRuntime
from tests.engine.test_generic import WINDOW, calc_lesson, node


def adapter_fixture():
    lesson = calc_lesson()
    step = {**lesson["steps"][0], "known_errors": []}
    calls = []
    values = {"value": "wrong", "stale": False, "during_read": False, "incomplete": False}

    async def send(kind, payload):
        calls.append((kind, payload))
        if kind == "a11y.cancel":
            return
        op = payload["op"]
        result = {"request_id": payload["request_id"], "snapshot_id": "s",
                  "complete": not values["incomplete"], "nodes": []}
        if op == "watch":
            result["events_supported"] = True
        else:
            result["nodes"] = [node(value=values["value"])]
        if op == "get" and values["stale"]:
            result.update(complete=False, nodes=[],
                          error={"code": "STALE_REF", "message": "retiré"})
            values["stale"] = False
        if op == "get" and values["during_read"]:
            values["during_read"] = False
            adapter.on_event(event(adapter, 2))
        adapter.resolve(result)

    adapter = AccessibilityAdapter(lesson["app"], load_profile(lesson["app"]), send)
    adapter.permission = adapter.can_watch = True
    adapter.on_focus({"app_id": "soffice", "name": "LibreOffice Calc",
                      "window_title": "Sans nom 1 - LibreOffice Calc",
                      "window_bounds": WINDOW, "scale": 1, "accessibility": "available"})
    return adapter, step, calls, values


def event(adapter, sequence=1, *, reconcile=False):
    return {"watch_id": adapter.watch_id, "sequence": sequence, "refs": ["r1"],
            "reconcile": reconcile, "events_supported": True}


async def test_event_reads_watched_refs_without_a_tree_walk():
    adapter, step, calls, values = adapter_fixture()
    await adapter.refresh(step)
    assert [p["op"] for _, p in calls] == ["find", "watch", "get"]
    assert calls[0][1]["deadline_ms"] == 1500
    values["value"] = "42"
    assert adapter.on_event(event(adapter))
    assert not adapter.state.recent
    calls.clear()
    await adapter.refresh(step)
    assert [p["op"] for _, p in calls] == ["get"]
    assert evaluate("element_value", adapter.state, step["check"]["params"]).status == "pass"
    assert not adapter.on_event(event(adapter))
    assert not adapter.on_event({**event(adapter, 3), "watch_id": "old-step"})


@pytest.mark.parametrize("reason", ["structural", "timer", "stale", "generation"])
async def test_reconciliation_and_stale_refs_resolve_descriptive_targets(reason):
    adapter, step, calls, values = adapter_fixture()
    await adapter.refresh(step)
    calls.clear()
    if reason == "structural":
        adapter.on_event(event(adapter, reconcile=True))
    elif reason == "timer":
        adapter.last_full = time.monotonic() - 5
    elif reason == "generation":
        adapter.generation += 1
    else:
        values["stale"] = True
    await adapter.refresh(step)
    assert "find" in [p["op"] for _, p in calls]
    assert "watch" in [p["op"] for _, p in calls]


async def test_event_during_read_discards_the_abandoned_state():
    adapter, step, _, values = adapter_fixture()
    await adapter.refresh(step)
    adapter.on_event(event(adapter))
    values.update(value="42", during_read=True)
    await adapter.refresh(step)
    assert not adapter.state.recent
    await adapter.refresh(step)
    assert adapter.state.recent


@pytest.mark.parametrize("reason", ["event", "generation", "focus"])
async def test_superseded_observations_cancel_pending_native_reads(reason):
    adapter, step, calls, _ = adapter_fixture()
    await adapter.refresh(step)
    started = asyncio.Event()

    async def silent(kind, payload):
        calls.append((kind, payload))
        started.set()

    adapter.send = silent
    task = asyncio.create_task(adapter.refresh(step))
    await asyncio.wait_for(started.wait(), .1)
    assert adapter.pending
    if reason == "event":
        adapter.on_event(event(adapter))
    elif reason == "generation":
        adapter.on_generation(1)
    else:
        adapter.on_focus({**adapter.focus, "window_title": "Autre fenêtre"})
    await asyncio.wait_for(task, .1)
    assert not adapter.state.recent
    assert not adapter.pending and not adapter.request_ops
    assert calls[-1][0] == "a11y.cancel"


async def test_incomplete_results_never_install_a_watch_or_pass():
    adapter, step, calls, values = adapter_fixture()
    values.update(incomplete=True, value="42")
    await adapter.refresh(step)
    assert all(p["op"] == "find" for _, p in calls)
    assert evaluate("element_value", adapter.state, step["check"]["params"]).status == "unknown"


@pytest.mark.parametrize("cancel", [False, True])
async def test_deadline_and_cancellation_stop_native_work(cancel):
    sent = []

    async def send(kind, payload):
        sent.append((kind, payload))

    lesson = calc_lesson()
    adapter = AccessibilityAdapter(lesson["app"], load_profile(lesson["app"]), send,
                                   timeout_s=.01)
    task = asyncio.create_task(adapter.request("find", query={"name": "A1"}))
    await asyncio.sleep(0)
    if cancel:
        task.cancel()
    with pytest.raises(asyncio.CancelledError if cancel else TimeoutError):
        await task
    assert sent[-1][0] == "a11y.cancel"
    assert sent[-1][1]["request_id"] == sent[0][1]["request_id"]
    assert not adapter.pending


async def test_runtime_event_wakes_observation_without_polling(tmp_path):
    runtime = EngineRuntime(EngineConfig(learner_path=tmp_path / "learner.json"),
                            lesson=calc_lesson())
    runtime.adapter = runtime.a11y
    runtime.a11y.events_supported = True
    runtime.a11y.watch_id = "watch"
    observed = asyncio.Queue()

    async def observe():
        await observed.put(True)

    runtime.observe_once = observe
    task = asyncio.create_task(runtime.observe_app())
    try:
        await asyncio.wait_for(observed.get(), .5)
        await runtime.desktop.start()
        async with connect(f"ws://127.0.0.1:{runtime.desktop.port}", origin="tauri://localhost",
                additional_headers={
                    "Authorization": "Bearer " + runtime.config.session_token}) as ws:
            def packet(kind, payload):
                return json.dumps({"schema_version": "1.0", "session_id": runtime.config.session_id,
                    "message_id": kind, "reply_to": None, "type": kind, "payload": payload})

            await ws.send(packet("hello", {"app_version": "0.1", "platform": "linux",
                                           "capabilities": ["a11y.events"]}))
            await ws.recv()
            await ws.send(packet("a11y.event", {"watch_id": "watch", "sequence": 1,
                "refs": [], "reconcile": False, "events_supported": True}))
            await asyncio.wait_for(observed.get(), .1)
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        await runtime.desktop.close()
