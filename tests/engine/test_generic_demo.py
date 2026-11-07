import asyncio
import json
from uuid import uuid4

import pytest

from engine.interfaces import LocalizeResult, VerifyResult
from tests.engine.test_calc_replay import start_runtime
from tests.engine.test_servers import send_ws


async def request(desktop, runtime):
    runtime.policy.level = 3
    await send_ws(desktop.ws, "user.intent", {"text": "aide", "source": "clavier"})
    await desktop.barrier()
    assert runtime.policy.level == 4 and runtime.demo_requested
    assert any(m["type"] == "error" and m["payload"]["code"] == "consent_required"
               for m in desktop.messages)


async def consent(desktop, *, intent="fais-le"):
    await send_ws(desktop.ws, "user.intent", {"source": "bouton", "text": json.dumps({
        "intent": intent, "consent_token": str(uuid4()),
        "delegation_confirmed": True, "wants_to_learn": False})})
    await desktop.barrier()


async def completed_task(runtime):
    async with asyncio.timeout(3):
        while runtime.action_task is None:
            await asyncio.sleep(0)
        await runtime.action_task


@pytest.mark.parametrize("apply", [True, False])
async def test_a11y_demo_requires_fresh_positive_postcheck(tmp_path, apply):
    runtime, desktop = await start_runtime(tmp_path)
    try:
        runtime.session.lesson["steps"] = runtime.session.lesson["steps"][:1]
        desktop.apply_actions = apply
        await runtime.observe_once()
        await request(desktop, runtime)
        assert not desktop.action_started.is_set()
        await consent(desktop)
        await completed_task(runtime)
        await desktop.barrier()
        assert desktop.action_started.is_set()
        action_index = next(i for i, r in enumerate(desktop.requests) if r["op"] == "action")
        assert any(r["op"] == "find" for r in desktop.requests[action_index + 1:])
        assert any(c["type"] == "success" for c in desktop.commands) is apply
        assert (runtime.session.status == "COMPLETE") is apply
        if apply:
            assert runtime.demo_undo
            await consent(desktop, intent="annule")
            await completed_task(runtime)
            assert desktop.values["A1"] == "" and runtime.demo_undo is None
            assert len([c for c in desktop.commands if c["type"] == "success"]) == 1
    finally:
        await desktop.close()
        await runtime.close()


async def test_no_consent_or_unrequested_consent_never_acts(tmp_path):
    runtime, desktop = await start_runtime(tmp_path)
    try:
        await runtime.observe_once()
        await consent(desktop)
        assert runtime.action_task is None
        await request(desktop, runtime)
        await runtime.tick()
        assert not desktop.action_started.is_set()
    finally:
        await desktop.close()
        await runtime.close()


async def test_stop_cancels_pending_action_and_ignores_late_ack(tmp_path):
    runtime, desktop = await start_runtime(tmp_path)
    desktop.action_release = asyncio.Event()
    try:
        await runtime.observe_once()
        await request(desktop, runtime)
        await consent(desktop)
        await asyncio.wait_for(desktop.action_started.wait(), 2)
        await consent(desktop)
        assert len([r for r in desktop.requests if r["op"] == "action"]) == 1
        task = runtime.action_task
        await send_ws(desktop.ws, "user.intent", {"text": "chut", "source": "clavier"})
        await desktop.barrier()
        await asyncio.gather(task, return_exceptions=True)
        assert task.cancelled() and runtime.consent is None
        assert not runtime.action_lock.locked()
        desktop.action_release.set()
        await desktop.barrier()
        await runtime.observe_once()
        await runtime.tick()
        assert runtime.session.status == "PAUSED"
        assert not any(c["type"] == "success" for c in desktop.commands)
    finally:
        desktop.action_release.set()
        await desktop.close()
        await runtime.close()


@pytest.mark.parametrize("point", [(500, 500), (55, 159)])
async def test_vision_demo_validates_expected_bounds_and_postchecks(tmp_path, point):
    class Holo:
        async def localize(self, image, description, *, timeout_s):
            return LocalizeResult(*point, 0.99, 1, True)

    class Verifier:
        async def verify(self, *args, **kwargs):
            return VerifyResult(True, 0.99, 1)

    runtime, desktop = await start_runtime(tmp_path, holo=Holo(), verifier=Verifier())
    try:
        await runtime.observe_once()
        runtime.session.lesson["steps"] = runtime.session.lesson["steps"][:1]
        runtime.session.step["check"] = {"name": "visual_assert", "params": {
            "assertion": "La cellule est sélectionnée ?", "region": {
                "x": 25, "y": 145, "w": 65, "h": 30}}}
        runtime.policy.set_step(runtime.session.step, runtime.session.generation)
        runtime.router.requested = "vision"
        runtime.select_adapter()
        await request(desktop, runtime)
        await consent(desktop)
        if point == (55, 159):
            async with asyncio.timeout(3), desktop.condition:
                await desktop.condition.wait_for(lambda: any(
                    c["type"] == "input.action" for c in desktop.commands))
        else:
            await completed_task(runtime)
        inputs = [c for c in desktop.commands if c["type"] == "input.action"]
        if point == (55, 159):
            assert len(inputs) == 1
            await send_ws(desktop.ws, "input.result", {
                "command_id": inputs[0]["command_id"], "status": "ok", "detail": "Action terminée"})
        else:
            assert not inputs
        await completed_task(runtime)
        await desktop.barrier()
        assert any(c["type"] == "success" for c in desktop.commands) is bool(inputs)
    finally:
        await desktop.close()
        await runtime.close()


@pytest.mark.parametrize("failure", ["permission", "empty", "timeout"])
async def test_demo_failures_never_emit_success(tmp_path, failure):
    runtime, desktop = await start_runtime(tmp_path)
    try:
        await runtime.observe_once()
        await request(desktop, runtime)
        if failure == "permission":
            runtime.permissions["accessibility"] = False
        elif failure == "empty":
            desktop.nodes = lambda query: []
        else:
            runtime.a11y.timeout_s = 0.01
            desktop.action_release = asyncio.Event()
        await consent(desktop)
        await completed_task(runtime)
        await desktop.barrier()
        assert not any(c["type"] == "success" for c in desktop.commands)
        assert runtime.session.status == "PAUSED"
        assert not runtime.action_lock.locked()
    finally:
        await desktop.close()
        await runtime.close()
