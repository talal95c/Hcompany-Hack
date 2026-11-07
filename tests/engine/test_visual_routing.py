import pytest

from engine.interfaces import VerifyResult
from tests.engine.test_calc_replay import start_runtime


@pytest.mark.parametrize("answer", [True, False, None])
async def test_visual_check_uses_vision_with_accessibility_primary(tmp_path, answer):
    calls = []

    class Verifier:
        async def verify(self, image, assertion, *, timeout_s):
            calls.append((image, assertion))
            return VerifyResult(answer, 0.99 if answer is not None else None, 1)

    runtime, desktop = await start_runtime(tmp_path, verifier=Verifier())
    try:
        runtime.router.requested = "auto"
        runtime.session.lesson["steps"] = runtime.session.lesson["steps"][:1]
        runtime.session.step["check"] = {"name": "visual_assert", "params": {
            "assertion": "La cellule A1 affiche 42 ?"}}
        runtime.policy.set_step(runtime.session.step, runtime.session.generation)
        await runtime.observe_once()
        await desktop.barrier()
        assert runtime.adapter is runtime.a11y
        assert len(calls) == 1 and calls[0][0].startswith(b"\x89PNG")
        assert (runtime.session.status == "COMPLETE") is (answer is True)
        assert any(c["type"] == "success" for c in desktop.commands) is (answer is True)
        if answer is None:
            assert runtime.session.status == "PAUSED"
    finally:
        await desktop.close()
        await runtime.close()
