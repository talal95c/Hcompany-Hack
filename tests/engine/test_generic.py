import json
from dataclasses import replace
from pathlib import Path

import pytest

from engine.adapters import (
    AccessibilityAdapter,
    BlenderAdapter,
    Rect,
    SensorRouter,
    VisionAdapter,
    load_profile,
)
from engine.adapters.vision import HoloAssertVerifier
from engine.bus import EventBus, Topic
from engine.bus.validation import validate
from engine.cache import TargetContext
from engine.checks import (
    AppState,
    Lookup,
    SceneState,
    evaluate,
    namespace,
    progress_signature,
    require_check,
)
from engine.checks.generic import assertion_key, query_for, query_key
from engine.config import EngineConfig
from engine.interfaces import FakeClock, LocalizeResult, VerifyResult
from engine.lesson import Session, lesson_app, load_lesson
from engine.lesson.runtime import EngineRuntime
from engine.policy import HelpContext, HelpPolicy

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / "fixtures"
A1 = {"description": "Cellule A1", "role": "table cell", "name": "A1"}
WINDOW = {"x": 57, "y": 50, "w": 1485, "h": 900}


def calc_lesson():
    return load_lesson(FIXTURES / "calc_lesson.json", allow_unproven=True)


def node(name="A1", value="", states=("enabled", "visible"), bounds=None, ref="r1"):
    return {"ref": ref, "role": "table cell", "name": name, "value": value,
            "states": list(states), "bounds": bounds or {"x": 98, "y": 185, "w": 82, "h": 17}}


def state_with(nodes=(), complete=True, error=None, title="Sans nom 1 - LibreOffice Calc",
               target=A1):
    state = AppState(window_title=title, revision=3, latest_revision=3, complete=True)
    state.lookups[query_key(query_for(target))] = Lookup(tuple(nodes), complete, "snap", error)
    return state


@pytest.mark.parametrize(("nodes", "complete", "error", "present", "status"), [
    ([node()], True, None, True, "pass"),
    ([], True, None, True, "fail"),
    ([], True, None, False, "pass"),
    ([], False, None, True, "unknown"),
    ([node()], False, "TIMEOUT", True, "unknown"),
    ([node(), node(ref="r2")], True, None, True, "pass"),
])
def test_element_exists(nodes, complete, error, present, status):
    result = evaluate("element_exists", state_with(nodes, complete, error),
                      {"target": A1, "present": present})
    assert result.status == status and result.scene_revision == 3


@pytest.mark.parametrize(("value", "params", "status"), [
    ("42", {"value": 42}, "pass"),
    ("42,0", {"value": 42}, "pass"),
    ("41,99", {"value": 42, "tolerance": 0.05}, "pass"),
    ("43", {"value": 42}, "fail"),
    ("abc", {"value": 42}, "fail"),
    ("Total", {"value": "total", "match": "contains"}, "pass"),
    ("Total", {"value": "total"}, "fail"),
    ("2026-11-07", {"value": r"^\d{4}-\d{2}", "match": "regex"}, "pass"),
    ("x", {"value": "(", "match": "regex"}, "unknown"),
    ("vrai", {"value": True}, "pass"),
    ("peut-être", {"value": True}, "unknown"),
])
def test_element_value(value, params, status):
    state = state_with([node(value=value)])
    assert evaluate("element_value", state, {"target": A1, **params}).status == status


def test_element_value_ambiguous_missing_and_stale_are_never_pass():
    params = {"target": A1, "value": 42}
    assert evaluate("element_value", state_with([node(value="42"), node(value="42", ref="r2")]),
                    params).status == "unknown"
    assert evaluate("element_value", state_with([]), params).status == "fail"
    missing = node()
    missing.pop("value")
    assert evaluate("element_value", state_with([missing]), params).status == "unknown"
    stale = state_with([node(value="42")])
    stale.latest_revision += 1
    assert evaluate("element_value", stale, params).status == "unknown"
    assert evaluate("element_value", AppState(), params).status == "unknown"
    descriptive = {"target": {"description": "Bouton visible seulement"}, "value": 1}
    assert evaluate("element_value", state_with([node()]), descriptive).status == "unknown"


def test_element_state_window_title_and_visual_assert():
    state = state_with([node(states=("focused", "selected", "enabled"))])
    assert evaluate("element_state", state, {"target": A1, "states": ["focused"],
                                             "absent_states": ["busy"]}).status == "pass"
    assert evaluate("element_state", state, {"target": A1,
                                             "absent_states": ["selected"]}).status == "fail"
    assert evaluate("window_title", state, {"value": "libreoffice calc"}).status == "pass"
    assert evaluate("window_title", state, {"value": "Sans nom 1", "match": "equals"}
                    ).status == "fail"
    assert evaluate("window_title", state_with(title=None), {"value": "x"}).status == "unknown"
    params = {"assertion": "La cellule A1 affiche 42 ?"}
    assert evaluate("visual_assert", state, params).status == "unknown"
    for verdict, status in [(VerifyResult(True, 0.95, 1), "pass"),
                            (VerifyResult(False, 0.9, 1), "fail"),
                            (VerifyResult(True, 0.5, 1), "unknown"),
                            (VerifyResult(None, None, 1), "unknown"),
                            (VerifyResult(True, None, 1), "unknown")]:
        state.verdicts[assertion_key(params)] = verdict
        assert evaluate("visual_assert", state, params).status == status
    state.verdicts[assertion_key(params)] = VerifyResult(True, 0.5, 1)
    assert evaluate("visual_assert", state, {**params, "min_confidence": 0.5}).status == "pass"


def test_registry_namespaces_and_state_isolation():
    scene = SceneState()
    scene.apply({"type": "snapshot", "scene_revision": 1, "payload": {
        "mode": "OBJECT", "active": None, "objects": []}})
    assert evaluate("blender.mode_is", scene, {"mode": "OBJECT"}).status == "pass"
    assert evaluate("mode_is", scene, {"mode": "OBJECT"}).status == "pass"
    assert evaluate("blender.mode_is", state_with(), {"mode": "OBJECT"}).status == "unknown"
    assert evaluate("element_exists", scene, {"target": A1}).status == "unknown"
    assert namespace("blender.object_count") == namespace("object_count") == "blender"
    assert namespace("element_value") is None
    assert progress_signature("blender.mode_is", state_with(), {"mode": "OBJECT"}) == "null"
    assert progress_signature("element_value", state_with([node(value="1")]), {
        "target": A1, "value": 1}) != progress_signature(
        "element_value", state_with([node(value="2")]), {"target": A1, "value": 1})
    for name in ("photoshop.layer", "blender.unknown", "element"):
        with pytest.raises(ValueError):
            require_check(name)


def test_router_order_fallback_and_recovery():
    router = SensorRouter("auto")
    assert router.choose({"addon": True, "accessibility": True}).sensor == "addon"
    assert router.choose({"accessibility": True, "vision": True}).sensor == "accessibility"
    assert router.choose({"vision": True}).reason == "fallback"
    assert router.choose({}).sensor is None
    a11y = SensorRouter("accessibility")
    assert a11y.choose({"addon": True, "vision": True}).sensor == "vision"
    assert a11y.report_error("accessibility", "AMBIGUOUS_TARGET")
    assert a11y.report_error("accessibility", "PERMISSION_DENIED")
    assert a11y.choose({"accessibility": True, "vision": True}).sensor == "vision"
    a11y.recover("accessibility")
    assert a11y.choose({"accessibility": True, "vision": True}).sensor == "accessibility"
    assert SensorRouter("addon").choose({"accessibility": True}).sensor is None
    assert not SensorRouter("vision").report_error("accessibility", "TIMEOUT")
    with pytest.raises(ValueError):
        SensorRouter("plugin")


def test_lesson_loader_v1_mapping_and_v2_app():
    donut = load_lesson(ROOT / "lessons/donut/lesson.json")
    assert lesson_app(donut) == {"id": "blender", "name": "Blender", "version": "4.5.9",
                                 "sensor": "addon"}
    assert "app" not in donut
    v2 = json.loads((ROOT / "contracts/examples/lesson/valid/blender-v2-namespaced.json")
                    .read_text())
    assert lesson_app(v2)["id"] == "blender"
    calc = calc_lesson()
    assert lesson_app(calc)["sensor"] == "accessibility"
    session = Session("s", calc)
    assert not session.observe({"window_title": None})
    assert not session.observe({"window_title": "Writer"})
    assert session.observe({"window_title": "Sans nom 1 - LibreOffice Calc"})


def test_profiles_and_rect_geometry():
    calc = load_profile({"id": "libreoffice-calc", "name": "Calc"})
    assert "cellule" in calc.vocabulary and "help.libreoffice.org" in calc.docs_domains
    assert calc.matches("soffice", "LibreOffice Calc") and not calc.matches("soffice")
    assert not calc.matches("soffice", "LibreOffice Writer")
    blender = load_profile({"id": "blender", "name": "Blender"})
    assert blender.docs_domains == ("docs.blender.org",)
    other = load_profile({"id": "gimp", "name": "GIMP"})
    assert other.vocabulary == ("GIMP",) and other.docs_domains == ()
    assert "Blender" not in other.jev_context
    with pytest.raises(ValueError):
        load_profile({"id": "../blender", "name": "x"})
    frame = Rect.from_dict(WINDOW)
    cell = Rect.from_dict(node()["bounds"])
    assert cell.point_milli(frame) == (55, 159)
    assert Rect(5000, 5000, 1, 1).point_milli(frame) is None
    milli = cell.milli(frame)
    assert round(milli.x, 1) == 27.6 and round(milli.w, 1) == 55.2
    assert not Rect(0, 0, 0, 5).valid


def test_runtime_rejects_foreign_namespace(tmp_path):
    lesson = calc_lesson()
    lesson["steps"][0]["check"] = {"name": "blender.mode_is", "params": {"mode": "OBJECT"}}
    with pytest.raises(ValueError, match="hors de l'application"):
        EngineRuntime(EngineConfig(learner_path=tmp_path / "l.json"), lesson=lesson)
    runtime = EngineRuntime(EngineConfig(learner_path=tmp_path / "l.json"), lesson=calc_lesson())
    assert runtime.plugin is None and runtime.primary is runtime.a11y
    assert runtime.policy.app_context["app_id"] == "libreoffice-calc"
    assert "cellule" in runtime.vocabulary()


async def test_accessibility_adapter_requests_zone_and_errors():
    sent = []
    profile = load_profile({"id": "libreoffice-calc", "name": "Calc"})
    app = {"id": "libreoffice-calc", "name": "LibreOffice Calc", "version": "7.3",
           "sensor": "accessibility"}

    async def send(kind, payload):
        validate("desktop-ws", {"schema_version": "1.0", "session_id": "s", "message_id": "m",
                                "reply_to": None, "type": kind, "payload": payload})
        sent.append(payload)
        name = payload["query"]["name"]
        result = {"request_id": payload["request_id"], "snapshot_id": "snap-1",
                  "complete": True, "nodes": [node(name, "42" if name == "A1" else "")]}
        if name == "B1":
            result = {"request_id": payload["request_id"], "snapshot_id": None,
                      "complete": False, "nodes": [],
                      "error": {"code": "TIMEOUT", "message": "lent"}}
        adapter.resolve(result)

    adapter = AccessibilityAdapter(app, profile, send, timeout_s=0.5)
    step = calc_lesson()["steps"][0]
    assert not adapter.available()
    adapter.permission = True
    adapter.on_focus({"app_id": "soffice", "name": "LibreOffice Calc",
                      "window_title": "Sans nom 1 - LibreOffice Calc",
                      "window_bounds": WINDOW, "scale": 1, "accessibility": "available"})
    assert adapter.available()
    state = await adapter.refresh(step)
    assert {p["op"] for p in sent} == {"find"} and len(sent) == 2
    assert not state.complete
    assert evaluate("element_value", state, step["check"]["params"]).status == "unknown"
    assert adapter.last_error == "TIMEOUT"
    known = step["known_errors"][0]["check"]
    assert evaluate(known["name"], state, known["params"]).status == "unknown"
    assert adapter.zone(step) == () and adapter.expected_rect(step) is None
    step = {**step, "known_errors": []}
    await adapter.refresh(step)
    assert adapter.last_error is None and adapter.state.complete
    (zone,) = adapter.zone(step)
    assert zone[:2] == ("desktop", "highlight.rect") and zone[2]["ref"] == "r1"
    hint = adapter.expected_rect(step)
    assert hint.exact and hint.snapshot_id == "snap-1"
    assert adapter.replay(step) == () and adapter.reveal_target(step) is None
    adapter.on_focus({"app_id": "gedit", "name": "Texte", "window_title": "x",
                      "window_bounds": WINDOW, "scale": 1})
    assert not adapter.available() and not adapter.state.recent
    assert adapter.expected_rect(step) is None

    async def silent(kind, payload):
        return None

    slow = AccessibilityAdapter(app, profile, silent, timeout_s=0.01)
    assert (await slow.find(A1)).error == "TIMEOUT"


async def test_vision_adapter_verdicts_from_fresh_capture():
    captures = []

    class Verifier:
        async def verify(self, image_png, assertion, *, timeout_s):
            assert image_png == b"\x89PNG-window" and "A1" in assertion
            return VerifyResult("42" in assertion, 0.97, 12)

    async def capture():
        captures.append(1)
        return {"capture_id": "c"}, b"\x89PNG-window"

    profile = load_profile({"id": "krita", "name": "Krita"})
    app = {"id": "krita", "name": "Krita", "version": "5", "sensor": "vision"}
    adapter = VisionAdapter(app, profile, capture, Verifier())
    adapter.permission = True
    adapter.on_focus({"app_id": "krita", "name": "Krita", "window_title": "Krita",
                      "window_bounds": WINDOW, "scale": 1})
    lesson = calc_lesson()
    step = lesson["steps"][0]
    step["check"] = {"name": "visual_assert", "params": {"assertion": "A1 affiche 42 ?"}}
    step["known_errors"][0]["check"] = {"name": "visual_assert",
                                        "params": {"assertion": "A1 est vide ?"}}
    state = await adapter.refresh(step)
    assert len(captures) == 1
    assert evaluate("visual_assert", state, step["check"]["params"]).status == "pass"
    known = step["known_errors"][0]["check"]["params"]
    assert evaluate("visual_assert", state, known).status == "fail"
    assert evaluate("element_value", state, {"target": A1, "value": 1}).status == "unknown"
    assert adapter.zone(step) == () and adapter.expected_rect(step) is None


async def test_holo_assert_verifier_parses_answer_and_confidence():
    class Token:
        def __init__(self, token, logprob):
            self.token, self.logprob = token, logprob

    class Response:
        def __init__(self, content, tokens):
            message = type("M", (), {"content": content})
            logprobs = type("L", (), {"content": tokens})
            self.choices = [type("C", (), {"message": message, "logprobs": logprobs})]

    class Client:
        def __init__(self, response):
            self.response = response

        async def _complete(self, operation, timeout_s, **kwargs):
            assert operation == "verify" and kwargs["logprobs"]
            return self.response

    yes = Response('{"answer":"yes"}', [Token('{"', 0), Token("yes", -0.01)])
    result = await HoloAssertVerifier(Client(yes)).verify(b"\x89PNG\r\n\x1a\n", "q?",
                                                          timeout_s=1)
    assert result.answer is True and result.confidence > 0.98
    unsure = Response('{"answer":"unsure"}', [Token("unsure", -0.1)])
    assert (await HoloAssertVerifier(Client(unsure)).verify(
        b"\x89PNG\r\n\x1a\n", "q?", timeout_s=1)).answer is None
    broken = Response("pas du json", [])
    assert (await HoloAssertVerifier(Client(broken)).verify(
        b"\x89PNG\r\n\x1a\n", "q?", timeout_s=1)).answer is None


def blender_step():
    step = calc_lesson()["steps"][0]
    return {**step, "target": {"description": "Tore", "area_type": "VIEW_3D",
                               "region_type": "WINDOW"},
            "help": {"menu_id": "VIEW3D_MT_mesh_add", "safe_demo": True,
                     "checkpoint_id": "cp"}}


def test_blender_adapter_plans_are_addon_commands():
    class Runtime:
        addon = None

    adapter = BlenderAdapter(Runtime())
    step = blender_step()
    assert adapter.zone(step) == () and adapter.reveal(step) == ()
    adapter.regions = [{"area_id": "v", "area_type": "VIEW_3D", "region_id": "w",
                        "type": "WINDOW", "screen_rect": {"x": 0, "y": 0, "width": 10,
                                                          "height": 10}}]
    assert [c[:2] for c in adapter.zone(step)] == [("addon", "highlight")]
    assert adapter.reveal(step)[0][2]["menu_id"] == "VIEW3D_MT_mesh_add"
    assert adapter.replay(step)[0][1] == "replay"
    assert adapter.undo_replay(step) == (("addon", "undo_demo", {"checkpoint_id": "cp"}),)
    assert adapter.replay({**step, "help": {}}) == ()
    assert adapter.expected_rect(step) is None and not adapter.available()


def policy_setup(holo=None):
    bus, clock = EventBus(), FakeClock()
    config = replace(EngineConfig(), jev_timeout_s=0.01, holo_timeout_s=0.01)
    debug = []
    policy = HelpPolicy(config, bus, clock=clock, holo=holo, debug=debug.append)
    commands = bus.subscribe(Topic.COMMAND)
    policy.set_step(calc_lesson()["steps"][0], 1)
    policy.level = 2
    return policy, commands, debug


def drain(queue):
    out = []
    while not queue.empty():
        command = queue.get_nowait()
        validate("commands", command)
        out.append(command)
    return out


def calc_context(**kwargs):
    target = TargetContext("libreoffice-calc", "7.3.7", (1485, 900), 1, "Cellule A1", (57, 50),
                           "main", "fr", 1, True)
    return HelpContext(target=target, capture_id="cap", image_png=b"png",
                       app="libreoffice-calc", require_visible=True, **kwargs)


async def test_policy_pointer_uses_a11y_center_without_holo():
    class Holo:
        async def localize(self, *args, **kwargs):
            pytest.fail("Le centre a11y suffit")

    policy, commands, _ = policy_setup(Holo())
    await policy.intent("aide", calc_context(pointer=(55, 159), pointer_ref=("r1", "snap"),
                                             expected_rect=(27.6, 150, 55.2, 18.9)))
    (pointer,) = drain(commands)
    assert pointer["type"] == "pointer" and pointer["recipient"] == "desktop"
    assert (pointer["payload"]["x"], pointer["payload"]["y"]) == (55, 159)
    assert pointer["payload"]["ref"] == "r1" and pointer["payload"]["app"] == "libreoffice-calc"
    assert policy.level == 3 and not policy.targets.entries


@pytest.mark.parametrize(("point", "expected"), [((40, 160), ["pointer"]),
                                                 ((500, 500), ["say"])])
async def test_policy_holo_point_must_fall_inside_expected_rect(point, expected):
    class Holo:
        async def localize(self, image_png, description, *, timeout_s):
            return LocalizeResult(*point, 0.9, 1, True)

    policy, commands, debug = policy_setup(Holo())
    await policy.intent("aide", calc_context(expected_rect=(27.6, 150, 55.2, 18.9)))
    assert [c["type"] for c in drain(commands)] == expected
    assert any(d["kind"] == "point_rejected" for d in debug) == (expected == ["say"])


async def test_policy_zone_is_overlay_rect_for_generic_apps():
    policy, commands, _ = policy_setup()
    policy.level = 1
    zone = (("desktop", "highlight.rect", {"app": "libreoffice-calc", "rect": {
        "x": 98, "y": 185, "w": 82, "h": 17}, "color": "#ffcc00", "duration_ms": 3000}),)
    revealed = []

    async def reveal():
        revealed.append(True)

    await policy.intent("aide", HelpContext(zone=zone, reveal_target=reveal))
    assert [c["type"] for c in drain(commands)] == ["highlight.rect"] and revealed
    assert policy.level == 2
