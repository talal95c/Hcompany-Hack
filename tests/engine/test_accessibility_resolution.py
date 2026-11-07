import pytest

from engine.adapters import AccessibilityAdapter, Rect, SensorRouter, load_profile
from engine.checks import evaluate
from engine.config import EngineConfig
from engine.lesson.runtime import EngineRuntime
from tests.engine.test_generic import A1, WINDOW, calc_lesson, node, state_with


@pytest.mark.parametrize(("name", "params"), [
    ("element_exists", {"target": A1}),
    ("element_exists", {"target": A1, "present": False}),
    ("element_value", {"target": A1, "value": 42}),
    ("element_state", {"target": A1, "states": ["enabled"]}),
])
def test_nonempty_incomplete_lookup_is_unknown(name: str, params: dict):
    state = state_with([node(value="42")], complete=False)
    assert state.recent
    assert evaluate(name, state, params).status == "unknown"


@pytest.mark.parametrize(("errors", "complete", "expected", "requests"), [
    (["STALE_REF", None], True, None, 2),
    (["STALE_REF", "STALE_REF"], False, "STALE_REF", 2),
    (["STALE_REF", "TIMEOUT"], False, "TIMEOUT", 2),
    (["AMBIGUOUS_TARGET"], True, "AMBIGUOUS_TARGET", 1),
    ([None], False, "INCOMPLETE_TREE", 1),
    ([None], True, None, 1),
])
async def test_resolution_retry_and_degradation(errors, complete, expected, requests, tmp_path):
    lesson = calc_lesson()
    step = {**lesson["steps"][0], "known_errors": []}
    sent = []

    async def send(kind: str, payload: dict):
        assert kind == "a11y.request" and payload["op"] == "find"
        assert payload["query"] == {"role": "table cell", "name": "A1"}
        assert "snapshot_id" not in payload and "ref" not in payload
        error = errors[len(sent)]
        sent.append(payload)
        result = {"request_id": payload["request_id"], "snapshot_id": f"s{len(sent)}",
                  "nodes": [node(value="42")], "complete": complete}
        if error:
            result["error"] = {"code": error, "message": "Indisponible"}
        adapter.resolve(result)

    adapter = AccessibilityAdapter(lesson["app"], load_profile(lesson["app"]), send)
    adapter.permission = True
    adapter.on_focus({"app_id": "soffice", "name": "LibreOffice Calc",
                      "window_title": "Sans nom 1 - LibreOffice Calc",
                      "window_bounds": WINDOW, "scale": 1, "accessibility": "available"})
    state = await adapter.refresh(step)
    assert len(sent) == requests
    assert len({p["request_id"] for p in sent}) == requests
    assert adapter.last_error == expected
    assert state.complete == (expected is None)
    assert evaluate("element_value", state, step["check"]["params"]).status == (
        "pass" if expected is None else "unknown")
    router = SensorRouter("auto")
    if expected:
        assert router.report_error("accessibility", expected)
    assert router.choose({"accessibility": True, "vision": True}).sensor == (
        "vision" if expected else "accessibility")
    if expected:
        assert adapter.expected_rect(step) is None and adapter.zone(step) == ()
        runtime = EngineRuntime(EngineConfig(learner_path=tmp_path / "learner.json"),
                                lesson=lesson)
        runtime.adapter = adapter
        assert runtime.target_hint(Rect.from_dict(WINDOW)) == {}
    else:
        assert adapter.expected_rect(step).snapshot_id == f"s{requests}"
        adapter.invalidate()
        assert adapter.expected_rect(step) is None and adapter.zone(step) == ()


@pytest.mark.parametrize("error", ["STALE_REF", "AMBIGUOUS_TARGET", None])
async def test_runtime_falls_back_without_inventing_visual_checks(error, tmp_path):
    runtime = EngineRuntime(EngineConfig(learner_path=tmp_path / "learner.json"),
                            lesson=calc_lesson())
    requests = []

    async def send(kind: str, payload: dict):
        requests.append(payload)
        result = {"request_id": payload["request_id"], "snapshot_id": "s",
                  "nodes": [node(value="42")], "complete": False}
        if error:
            result["error"] = {"code": error, "message": "Indisponible"}
        runtime.a11y.resolve(result)

    async def forbidden_capture():
        pytest.fail("Aucun check visuel autorisé pour cette étape")

    runtime.a11y.send = send
    runtime.a11y.permission = runtime.vision.permission = True
    runtime.vision.verifier = object()
    runtime.vision.capture = forbidden_capture
    focus = {"app_id": "soffice", "name": "LibreOffice Calc",
             "version": runtime.app["version"],
             "window_title": "Sans nom 1 - LibreOffice Calc", "window_bounds": WINDOW,
             "scale": 1, "accessibility": "available"}
    runtime.a11y.on_focus(focus)
    runtime.vision.on_focus(focus)
    await runtime.observe_once()
    assert runtime.adapter is runtime.vision
    assert len(requests) == (4 if error == "STALE_REF" else 2)
    await runtime.observe_once()
    check = runtime.session.step["check"]
    assert evaluate(check["name"], runtime.vision.snapshot(), check["params"]).status == "unknown"
    assert runtime.session.status != "COMPLETE"
