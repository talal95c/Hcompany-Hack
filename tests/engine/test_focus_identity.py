import asyncio

import pytest

from engine.adapters import VisionAdapter
from engine.bus import Topic
from engine.cache import TargetContext
from engine.checks import evaluate
from engine.config import EngineConfig
from engine.interfaces import VerifyResult
from engine.lesson.runtime import EngineRuntime
from tests.engine.test_generic import A1, WINDOW, calc_lesson, node, state_with


def focus(runtime, **fields):
    return {"app_id": "soffice", "name": "LibreOffice Calc", "window_title": "Required Calc",
            "version": runtime.app["version"], "window_bounds": WINDOW, "scale": 1, **fields}


def setup(tmp_path):
    lesson = calc_lesson()
    lesson["steps"] = lesson["steps"][:1]
    lesson["steps"][0]["preconditions"] = {"window_title": "Required Calc"}
    runtime = EngineRuntime(EngineConfig(learner_path=tmp_path / "l.json"), lesson=lesson)
    runtime.a11y.permission = True
    runtime.a11y.on_focus(focus(runtime))
    runtime.a11y.state = state_with([node(value="42")], title="Required Calc")
    runtime.select_adapter()
    return runtime


@pytest.mark.parametrize("status", ["OBSERVING", "PAUSED"])
@pytest.mark.parametrize("fresh", [False, True])
async def test_wrong_document_never_succeeds(tmp_path, status, fresh):
    runtime = setup(tmp_path)
    runtime.session.status = status
    runtime.capture = {"capture_id": "old"}
    runtime.consent = ("old", 100, 0)
    runtime.pointer_request = {"request_id": "old"}
    await runtime.desktop_message({"type": "app.focus", "payload": focus(
        runtime, window_title="Other Calc")}, None)
    assert runtime.capture is runtime.consent is runtime.pointer_request is None
    assert not runtime.a11y.state.recent
    if fresh:
        runtime.a11y.state = state_with([node(value="42")], title="Other Calc")
    await runtime.tick()
    assert runtime.session.status == "PAUSED"
    assert runtime.commands.empty()
    assert not runtime.targets.entries


async def test_old_find_is_discarded(tmp_path):
    runtime = setup(tmp_path)
    sent = asyncio.Queue()

    async def send(kind, payload):
        await sent.put(payload)

    runtime.a11y.send = send
    step = {**runtime.session.step, "known_errors": []}
    task = asyncio.create_task(runtime.a11y.refresh(step))
    request = await sent.get()
    runtime.a11y.on_focus(focus(runtime, window_title="Other Calc"))
    assert not runtime.a11y.resolve({"request_id": request["request_id"], "snapshot_id": "old",
                                     "complete": True, "nodes": [node(value="42")]})
    state = await task
    assert state.window_title == "Other Calc" and not state.recent and not state.lookups
    assert evaluate("element_exists", state, {"target": A1}).status == "unknown"


@pytest.mark.parametrize("phase", ["capture", "verify"])
async def test_old_visual_evidence_is_discarded(tmp_path, phase):
    runtime = setup(tmp_path)
    entered, release = asyncio.Event(), asyncio.Event()

    async def wait():
        entered.set()
        await release.wait()

    async def capture():
        if phase == "capture":
            await wait()
        return {"capture_id": "old"}, b"png"

    class Verifier:
        async def verify(self, *args, **kwargs):
            if phase == "verify":
                await wait()
            return VerifyResult(True, 1, 1)

    adapter = VisionAdapter(runtime.app, runtime.profile, capture, Verifier())
    adapter.on_focus(focus(runtime))
    step = {**runtime.session.step, "known_errors": [], "check": {
        "name": "visual_assert", "params": {"assertion": "42 ?"}}}
    task = asyncio.create_task(adapter.refresh(step))
    await entered.wait()
    adapter.on_focus(focus(runtime, window_title="Other Calc"))
    release.set()
    state = await task
    assert not state.recent and not state.verdicts and state.window_title == "Other Calc"


@pytest.mark.parametrize("version", [None, "99.0", ""])
async def test_unproven_version_is_not_ready_or_lesson_cache_key(tmp_path, version):
    runtime = setup(tmp_path)
    payload = focus(runtime)
    if version is None:
        payload.pop("version")
    else:
        payload["version"] = version
    runtime.a11y.on_focus(payload)
    runtime.a11y.state = state_with([node(value="42")], title="Required Calc")
    await runtime.tick()
    assert not runtime.app_ready() and runtime.commands.empty()
    assert runtime.app_version() == (version or "unknown")
    context = TargetContext(runtime.app["id"], runtime.app_version(), (100, 100), 1,
                            "A1", (0, 0), "main", "fr", 0, True)
    assert context.key[1] != runtime.app["version"]


def test_writer_rejected_by_both_generic_adapters(tmp_path):
    runtime = setup(tmp_path)
    for adapter in (runtime.a11y, runtime.vision):
        adapter.on_focus(focus(runtime, name="LibreOffice Writer"))
        assert not adapter.focused and adapter.version == "unknown"


async def test_matching_observed_version_and_document_can_succeed(tmp_path):
    runtime = setup(tmp_path)
    await runtime.tick()
    assert runtime.app_ready() and runtime.session.status == "COMPLETE"
    assert runtime.commands.get_nowait()["type"] == "success"


async def test_preconditions_rechecked_after_check_dispatch(tmp_path):
    runtime = setup(tmp_path)
    original = runtime.bus.publish

    async def publish(topic, value):
        await original(topic, value)
        if topic == Topic.CHECK:
            runtime.a11y.on_focus(focus(runtime, window_title="Other Calc"))

    runtime.bus.publish = publish
    await runtime.tick()
    assert runtime.commands.empty() and runtime.session.status == "PAUSED"
