import asyncio
import json
from dataclasses import replace
from pathlib import Path

import pytest

from engine.bus import EventBus, Topic
from engine.bus.validation import validate
from engine.cache import AudioEntry, TargetContext, TargetEntry
from engine.checks import SceneState, evaluate
from engine.config import EngineConfig
from engine.interfaces import FakeClock, JevDecision, LocalizeResult
from engine.policy import HelpContext, HelpPolicy


def context():
    return TargetContext("4.5.9", (800, 600), 2, "Tore", (0, 0), "main", "fr", 1, True)


def snapshot(objects=None):
    state = SceneState()
    state.apply({"type": "snapshot", "scene_revision": 1, "payload": {
        "mode": "OBJECT", "active": None, "objects": objects or [],
    }})
    return state


def step():
    root = Path(__file__).resolve().parents[2]
    paths = [root / "contracts/examples/lesson/valid/donut.json"]
    return next(s["steps"][0] for p in paths if (s := json.loads(p.read_text()))["steps"][0][
        "known_errors"
    ])


def setup(**kwargs):
    bus, clock = EventBus(), FakeClock()
    config = replace(EngineConfig(), jev_timeout_s=0.01, holo_timeout_s=0.01)
    debug = []
    policy = HelpPolicy(config, bus, clock=clock, debug=debug.append, **kwargs)
    commands = bus.subscribe(Topic.COMMAND)
    decisions = bus.subscribe(Topic.DECISION)
    policy.set_step(step(), 1)
    return policy, clock, commands, decisions, debug


def drain(queue):
    messages = []
    while not queue.empty():
        command = queue.get_nowait()
        validate("commands", command)
        messages.append(command)
    return messages


async def process(policy, state, **kwargs):
    check = policy.step["check"]
    return await policy.process(state, evaluate(check["name"], state, check["params"]), **kwargs)


def help_context(**kwargs):
    return HelpContext(area_id="a1", region_id="r1", menu_id="VIEW3D_MT_mesh_add",
                       target=context(), **kwargs)


async def test_known_error_once_deferred_and_progress():
    policy, clock, commands, decisions, debug = setup()
    cube = snapshot([{"id": "a", "type": "MESH", "primitive_provenance": "cube",
                      "mesh": {"verts": 8, "edges": 12, "polys": 6}}])
    decision = await process(policy, cube)
    assert decision.reason == "known_error:cube_instead_of_torus" and decision.level == 1
    assert drain(commands)[0]["payload"]["text"] == step()["known_errors"][0]["hint"]
    assert await process(policy, cube) is None
    await process(policy, snapshot())
    clock.advance(1)
    assert await process(policy, cube) is None
    assert policy.deferred.startswith("known_error:")
    assert any(d["kind"] == "deferred" for d in debug)
    clock.advance(29)
    decision = await process(policy, cube, context=help_context())
    assert decision.level == 2
    assert [c["type"] for c in drain(commands)] == ["highlight", "open_menu"]
    assert decisions.qsize() == 2


async def test_no_progress_selection_undo_mute_explicit_and_success():
    policy, clock, commands, _, _ = setup()
    state = snapshot()
    assert await process(policy, state) is None
    clock.advance(20)
    state.apply({"type": "selection.changed", "scene_revision": 1,
                 "payload": {"selected_ids": [], "active": None}})
    assert (await process(policy, state, event_type="selection.changed")).level == 1
    assert [c["type"] for c in drain(commands)] == ["say"]
    await policy.intent("chut")
    assert [c["type"] for c in drain(commands)] == ["stop"]
    clock.advance(50)
    assert await process(policy, state, event_type="undo", undo_count=3) is None
    assert commands.empty()
    assert (await policy.intent("aide", help_context())).level == 2
    drain(commands)
    await policy.intent("reprends")
    # Sans capture, le troisième palier reste au deuxième.
    assert (await process(policy, state, context=help_context())).level == 2
    assert commands.empty()
    torus = snapshot([{"id": "t", "type": "MESH", "primitive_provenance": "torus",
                       "mesh": {"verts": 576, "edges": 1152, "polys": 576}}])
    assert (await process(policy, torus)).kind == "success"
    assert [c["type"] for c in drain(commands)] == ["success"]
    assert policy.level == 0
    assert await process(policy, torus) is None


async def test_ladder_capture_pointer_safe_demo_and_audio():
    class Holo:
        async def localize(self, image_png, description, *, timeout_s):
            assert image_png == b"png" and description == "Tore"
            return LocalizeResult(123, 456, 0.9, 1)

    policy, _, commands, _, _ = setup(holo=Holo())
    hint = policy.step["why"]
    policy.audio.put(hint, AudioEntry(b"audio", "audio/hint"))
    ctx = help_context(capture_id="cap", image_png=b"png", safe_demo=True, checkpoint_id="cp")
    for expected in (1, 2, 3, 4):
        assert (await policy.intent("help", ctx)).level == expected
    messages = drain(commands)
    assert [c["type"] for c in messages] == ["say", "highlight", "open_menu", "pointer", "replay"]
    assert messages[0]["payload"]["audio_ref"] == "audio/hint"
    assert messages[3]["payload"]["x"] == 123
    await policy.finish_demo(ctx, generation=0, acknowledged=True)
    await policy.finish_demo(ctx, generation=1, acknowledged=False)
    assert commands.empty()
    await policy.finish_demo(ctx, generation=1, acknowledged=True)
    assert drain(commands)[0]["type"] == "undo_demo"
    await policy.finish_demo(ctx, generation=1, acknowledged=True)
    assert commands.empty()
    await policy.intent("help", ctx)
    assert commands.empty()


@pytest.mark.parametrize("mode", ["timeout", "error", "none"])
async def test_holo_failure_stays_level_two(mode):
    class Holo:
        async def localize(self, *args, **kwargs):
            if mode == "timeout":
                await asyncio.sleep(1)
            if mode == "error":
                raise RuntimeError
            return None

    policy, _, commands, _, debug = setup(holo=Holo())
    ctx = help_context(capture_id="cap", image_png=b"png")
    await policy.intent("aide", ctx)
    await policy.intent("aide", ctx)
    drain(commands)
    assert (await policy.intent("aide", ctx)).level == 2
    assert commands.empty()
    assert policy.fallback.health["holo"].consecutive_failures == 1
    assert any(d["kind"] == "latency" and d["service"] == "holo" for d in debug)


@pytest.mark.parametrize("action", ["wait", "intervene", "timeout", "error", "invalid"])
async def test_jev_ambiguity_and_fallback(action):
    class Jev:
        calls = 0

        async def decide(self, context, *, timeout_s):
            self.calls += 1
            if action == "timeout":
                await asyncio.sleep(1)
            if action == "error":
                raise OSError
            return JevDecision(action, None, 0)

    jev = Jev()
    policy, clock, commands, _, debug = setup(jev=jev)
    # Un maillage sans provenance rend le check ambigu.
    state = snapshot([{"id": "a", "type": "MESH"}])
    assert await process(policy, state) is None
    assert jev.calls == 0
    clock.advance(20)
    decision = await process(policy, state)
    assert jev.calls == 1
    if action == "wait":
        assert decision is None and commands.empty()
        assert await process(policy, state) is None
        assert jev.calls == 1
    else:
        assert decision.level == 1
        drain(commands)
    if action in {"timeout", "error", "invalid"}:
        assert policy.degraded
        assert sum(d["kind"] == "degraded" for d in debug) == 1


async def test_generation_change_discards_jev_and_holo():
    started, release = asyncio.Event(), asyncio.Event()

    class Jev:
        async def decide(self, *args, **kwargs):
            started.set()
            await release.wait()
            return JevDecision("intervene", None, 0)

    policy, clock, commands, _, _ = setup(jev=Jev())
    state = snapshot([{"id": "a", "type": "MESH"}])
    await process(policy, state)
    clock.advance(20)
    task = asyncio.create_task(process(policy, state))
    await started.wait()
    policy.set_step(step(), 2)
    release.set()
    assert await task is None and commands.empty()

    started.clear()
    release.clear()

    class Holo:
        async def localize(self, *args, **kwargs):
            started.set()
            await release.wait()
            return LocalizeResult(1, 2, None, 0)

    policy.holo = Holo()
    ctx = help_context(capture_id="cap", image_png=b"png")
    await policy.intent("help", ctx)
    await policy.intent("help", ctx)
    drain(commands)
    task = asyncio.create_task(policy.intent("help", ctx))
    await started.wait()
    policy.set_step(step(), 3)
    release.set()
    assert await task is None and commands.empty()


async def test_empty_policy_unknown_intent_stale_result_and_unsafe_demo():
    bus = EventBus()
    policy = HelpPolicy(EngineConfig(), bus)
    state = snapshot()
    assert await process_empty(policy, state) is None
    assert await policy.intent("bonjour") is None
    policy.set_step(step(), 0)
    stale = replace(evaluate("object_exists", state, {"primitive": "torus"}), scene_revision=0)
    assert await policy.process(state, stale) is None
    policy.level = 3
    commands = bus.subscribe(Topic.COMMAND)
    assert (await policy.intent("help", help_context())).level == 3
    assert commands.empty()


async def test_cached_pointer_does_not_call_holo():
    class Holo:
        async def localize(self, *args, **kwargs):
            pytest.fail("Un hit valide ne nécessite pas le cloud")

    policy, _, commands, _, _ = setup(holo=Holo())
    ctx = help_context()
    policy.targets.put_target(TargetEntry(context(), LocalizeResult(77, 88, None, 0), "cached"))
    await policy.intent("aide", ctx)
    await policy.intent("aide", ctx)
    drain(commands)
    assert (await policy.intent("aide", ctx)).level == 3
    pointer = drain(commands)[0]
    assert pointer["type"] == "pointer" and pointer["payload"]["capture_id"] == "cached"


async def process_empty(policy, state):
    return await policy.process(state, evaluate("object_exists", state, {}))


@pytest.mark.parametrize("invalidation", ["chut", "capture"])
async def test_inflight_spontaneous_holo_is_cancelled(invalidation):
    started, cancelled = asyncio.Event(), asyncio.Event()

    class Holo:
        async def localize(self, *args, **kwargs):
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise

    policy, clock, commands, decisions, _ = setup(holo=Holo())
    policy.config = replace(policy.config, holo_timeout_s=2)
    state = snapshot()
    await process(policy, state)
    policy.level = 2
    clock.advance(20)
    ctx = help_context(capture_id="before", image_png=b"png")
    task = asyncio.create_task(process(policy, state, context=ctx))
    await asyncio.wait_for(started.wait(), 1)
    if invalidation == "chut":
        await policy.intent("chut")
    else:
        policy.cancel_intervention(invalidate_capture=True)
    assert await asyncio.wait_for(task, 1) is None
    assert cancelled.is_set() and decisions.empty()
    assert [c["type"] for c in drain(commands)] == (["stop"] if invalidation == "chut" else [])
    assert policy.level == 2
    if invalidation == "capture":
        assert await policy.intent("aide", ctx) is None
        assert commands.empty()


async def test_chut_during_jev_cannot_start_help_after_resume():
    started, release = asyncio.Event(), asyncio.Event()

    class Jev:
        async def decide(self, *args, **kwargs):
            started.set()
            await release.wait()
            return JevDecision("intervene", None, 0)

    policy, clock, commands, decisions, _ = setup(jev=Jev())
    state = snapshot([{"id": "a", "type": "MESH"}])
    await process(policy, state)
    clock.advance(20)
    task = asyncio.create_task(process(policy, state))
    await started.wait()
    await policy.intent("chut")
    await policy.intent("reprends")
    release.set()
    assert await task is None and decisions.empty()
    assert [c["type"] for c in drain(commands)] == ["stop"]
