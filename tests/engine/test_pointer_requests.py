import time

import pytest

from engine.config import EngineConfig
from engine.lesson import load_lesson
from engine.lesson.runtime import EngineRuntime

from .test_e2e import FIXTURES
from .test_servers import capture


@pytest.mark.parametrize("invalid", ["missing", "id", "crop", "generation", "epoch", "expired"])
async def test_pointer_capture_requires_fresh_matching_menu_request(tmp_path, invalid):
    runtime = EngineRuntime(EngineConfig(learner_path=tmp_path / "learner.json"),
                            lesson=load_lesson(FIXTURES / "single_lesson.json"))
    runtime.permissions["screen"] = True
    runtime.policy.level = 2
    payload = capture(runtime)
    request = runtime.pointer_request
    if invalid == "missing":
        runtime.pointer_request = None
    elif invalid == "id":
        payload["request_id"] = "other"
    elif invalid == "crop":
        request["crop"] = {**request["crop"], "x": 50}
    elif invalid == "generation":
        request["generation"] += 1
    elif invalid == "epoch":
        request["epoch"] += 1
    else:
        request["at"] = time.monotonic() - 11
    with pytest.raises(ValueError, match="Capture non corrélée"):
        await runtime.accept_capture(payload)
    assert runtime.capture is None
