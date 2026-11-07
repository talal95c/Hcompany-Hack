import copy
import json
import struct
import zlib
from pathlib import Path
from types import SimpleNamespace

import jsonschema
import pytest

from engine.services.protocols import HoloAction
from prep.__main__ import parser, profile_for
from prep.apps import GENERIC_CHECKS, PROFILES, get_profile
from prep.compile.generic import GenericCompiler
from prep.ingest import Transcript, vocabulary_from_ui_map
from prep.prover.checks import describe_check, evaluate_check, evaluate_snapshot
from prep.prover.generic import (
    VISUAL_DIALOG_QUESTION,
    drive_step,
    file_sha256,
    open_dialogs,
    png_size,
    prove_generic_lesson,
)
from prep.sandbox.desktop import xdotool_chord
from prep.ui_map.accessibility import (
    build_ui_map,
    control_signature,
    diff_ui_maps,
    find_nodes,
    normalize_role,
    requested_cells,
)

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "contracts/lesson.schema.json").read_text())
FIXTURES = Path(__file__).with_name("fixtures")
APP = {"id": "libreoffice-calc", "name": "LibreOffice Calc", "version": "7.3.7.2"}


def snapshot():
    return json.loads((FIXTURES / "a11y/calc-snapshot.json").read_text())


def with_cell(snap, name, value):
    snap = copy.deepcopy(snap)
    for node in snap["nodes"]:
        if node["name"] == name:
            node["value"] = value
    return snap


def png(width=4, height=3):
    raw = b"".join(b"\x00" + b"\x00\x00\x00" * width for _ in range(height))

    def chunk(kind, data):
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def test_profiles():
    assert not PROFILES["blender"].generic
    calc = get_profile("libreoffice-calc")
    assert calc.generic and calc.sensor == "accessibility" and calc.checks == GENERIC_CHECKS
    custom = get_profile("gedit", command="gedit --new-window {file}")
    assert custom.command[0] == "gedit" and custom.accessible_name == "gedit"
    with pytest.raises(ValueError):
        get_profile("photoshop")
    with pytest.raises(ValueError):
        get_profile("Bad App")
    with pytest.raises(ValueError):
        get_profile("blender", command="blender {file}")


def test_cli_routing():
    args = parser().parse_args(["tuto.txt", "--out", "lessons/x"])
    assert args.app == "blender" and not profile_for(args).generic
    args = parser().parse_args(
        ["tuto.txt", "--app", "libreoffice-calc", "--out", "lessons/x", "--fixture", "a.csv"]
    )
    assert profile_for(args).generic and args.fixture == Path("a.csv")


def test_roles_are_shared_across_platforms():
    assert normalize_role("push button") == "button"
    assert normalize_role("AXButton") == "button"
    assert normalize_role("ButtonControl") == "button"
    assert normalize_role("table cell") == normalize_role("DataItemControl") == "cell"
    assert normalize_role("AXTextField") == normalize_role("entry") == "text"
    assert normalize_role("MenuItemControl") == "menu_item"


def test_ui_map_from_snapshot():
    ui_map = build_ui_map(snapshot(), app=APP)
    assert ui_map["kind"] == "accessibility" and ui_map["complete"]
    controls = {(c["role"], c["name"]): c["path"] for c in ui_map["controls"]}
    assert controls[("toggle_button", "Bold")] == ["frame", "toolbar:Formatting"]
    assert controls[("menu_item", "Chart...")] == ["frame", "menu:Insert"]
    assert not any(c["role"] == "cell" for c in ui_map["controls"])
    assert "value" not in json.dumps(ui_map["controls"])
    assert ui_map["managed_containers"][0]["name"] == "Sheet ventes"
    assert control_signature(ui_map, {"description": "x", "role": "button", "name": "Nope"}) is None
    bold = {"description": "Gras", "role": "toggle button", "name": "Bold", "path": ["frame"]}
    assert control_signature(ui_map, bold)[0]["path"] == ["frame", "toolbar:Formatting"]
    empty = build_ui_map({"complete": False, "nodes": []}, app=APP)
    assert empty["controls"] == [] and not empty["complete"]
    diff = diff_ui_maps(empty, ui_map)
    assert diff["removed"] == [] and len(diff["added"]) == len(ui_map["controls"])
    words = vocabulary_from_ui_map(ui_map)
    assert words[0] == "LibreOffice Calc" and "Bold" in words and "Blender" not in words


def test_find_nodes_and_password_value_absent():
    snap = snapshot()
    nodes = find_nodes(snap, {"role": "cell", "name": "a1"})
    assert nodes[0]["value"] == "Mois" and nodes[0]["path"][-1] == "table:Sheet ventes"
    assert find_nodes(snap, {"role": "menu_item", "name": "Chart...", "path": ["menu:Edit"]}) == []
    assert find_nodes(snap, {"description": "only words"}) == []
    assert requested_cells({"role": "cell", "name": "b6"}, None, {"role": "button"}) == ["B6"]


@pytest.mark.parametrize(
    ("check", "snap", "expected"),
    [
        (
            {
                "name": "element_value",
                "params": {
                    "target": {"description": "B6", "role": "cell", "name": "B6"},
                    "value": 465,
                },
            },  # noqa: E501
            with_cell(snapshot(), "B6", "465"),
            "pass",
        ),
        (
            {
                "name": "element_value",
                "params": {
                    "target": {"description": "B6", "role": "cell", "name": "B6"},
                    "value": "465",
                },
            },  # noqa: E501
            snapshot(),
            "fail",
        ),
        (
            {
                "name": "element_state",
                "params": {
                    "target": {"description": "Gras", "role": "toggle_button", "name": "Bold"},
                    "states": ["checked"],
                },
            },  # noqa: E501
            snapshot(),
            "fail",
        ),
        (
            {
                "name": "element_exists",
                "params": {"target": {"description": "Diagramme"}},
            },  # noqa: E501
            snapshot(),
            "unknown",
        ),
        (
            {
                "name": "element_exists",
                "params": {
                    "target": {"description": "Diagramme", "role": "embedded", "name": "OLEShape"}
                },
            },  # noqa: E501
            snapshot(),
            "fail",
        ),
        (
            {
                "name": "element_exists",
                "params": {
                    "target": {"description": "x", "role": "toggle_button", "name": "Bold"},
                    "present": False,
                },
            },  # noqa: E501
            snapshot(),
            "fail",
        ),
        ({"name": "window_title", "params": {"value": "LibreOffice Calc"}}, snapshot(), "pass"),
        ({"name": "window_title", "params": {"value": "Writer"}}, snapshot(), "fail"),
        (
            {"name": "window_title", "params": {"value": "Writer"}},
            {"complete": False, "nodes": [], "error": {"code": "APP_NOT_FOUND"}},
            "unknown",
        ),
        (
            {
                "name": "element_exists",
                "params": {"target": {"description": "x", "role": "embedded", "name": "OLEShape"}},
            },  # noqa: E501
            {**snapshot(), "complete": False},
            "unknown",
        ),
    ],
)
def test_evaluate_snapshot(check, snap, expected):
    jsonschema.validate(check, {**SCHEMA["$defs"]["check"], "$defs": SCHEMA["$defs"]})
    assert evaluate_snapshot(check, snap)["result"] == expected


def test_ambiguous_target_is_unknown():
    snap = snapshot()
    clone = copy.deepcopy(next(n for n in snap["nodes"] if n["name"] == "Bold"))
    clone.update(ref="e99", states=["checked", "enabled", "visible"])
    snap["nodes"].append(clone)
    check = {
        "name": "element_state",
        "params": {
            "target": {"description": "Gras", "role": "toggle_button", "name": "Bold"},
            "states": ["checked"],
        },
    }
    assert evaluate_snapshot(check, snap) == {**evaluate_snapshot(check, snap), "result": "unknown"}


class Judge:
    def __init__(self, answer, confidence):
        self.answer, self.confidence = answer, confidence

    async def assert_visual(self, image, assertion, *, region=None):
        return {"answer": self.answer, "confidence": self.confidence, "evidence": "-"}


class Observer:
    def __init__(self, snap):
        self.snap = snap

    async def snapshot(self, *, cells=None):
        return self.snap

    async def screenshot(self):
        return png()


async def test_visual_and_timeout_checks():
    check = {"name": "visual_assert", "params": {"assertion": "Is a chart visible?"}}
    assert (await evaluate_check(check, Observer({}), Judge("yes", 0.9)))["result"] == "pass"
    assert (await evaluate_check(check, Observer({}), Judge("yes", 0.5)))["result"] == "unknown"
    assert (await evaluate_check(check, Observer({}), Judge("no", 0.95)))["result"] == "fail"
    assert (await evaluate_check(check, Observer({}), None))["result"] == "unknown"
    waiting = {"name": "window_title", "params": {"value": "Writer"}}
    verdict = await evaluate_check(waiting, Observer(snapshot()), None, poll_interval=0.01)
    assert verdict["result"] == "fail" and verdict["duration"] >= 0
    alien = {"name": "blender.object_exists", "params": {"type": "MESH", "primitive": "cube"}}
    assert (await evaluate_check(alien, Observer(snapshot()), None))["result"] == "unknown"


def test_keys_and_png():
    assert xdotool_chord(["ctrl", "b"]) == "ctrl+b"
    assert xdotool_chord(["shift", "f10"]) == "shift+F10"
    assert xdotool_chord(["enter"]) == "Return"
    with pytest.raises(ValueError):
        xdotool_chord(["ctrl", "$(rm)"])
    with pytest.raises(ValueError):
        xdotool_chord([])
    assert png_size(png(7, 5)) == (7, 5)
    with pytest.raises(ValueError):
        png_size(b"GIF89a")


class HoloStub:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            usage=SimpleNamespace(model_dump=lambda: {"total_tokens": 1}),
            choices=[SimpleNamespace(message=SimpleNamespace(content=next(self.responses)))],
        )


def transcript():
    return Transcript("Sum column B in B6.", "en", [], "file:///tuto.txt", "abc", None, {})


def raw_lesson():
    cell = {"description": "Cellule B6", "role": "cell", "name": "b6"}
    return {
        "title": "Ventes",
        "steps": [
            {
                "id": "sum_sales",
                "skill_id": "sum_column",
                "instruction": "Tape =SUM(B2:B5) dans B6 puis Entrée.",
                "why": "Le total résume la colonne.",
                "target": cell,
                "check": {"name": "element_value", "params": {"target": cell, "value": "465"}},
                "known_errors": [
                    {
                        "code": "partial_range",
                        "check": {
                            "name": "element_value",
                            "params": {"target": cell, "value": "355"},
                        },
                        "hint": "Inclue B5 dans la plage.",
                    }
                ],
            },
            {
                "id": "bold_header",
                "skill_id": "bold",
                "instruction": "Clique sur Gras.",
                "why": "L'en-tête ressort.",
                "target": {"description": "Bouton Gras", "role": "push button", "name": "Bold"},
                "check": {
                    "name": "element_state",
                    "params": {
                        "target": {
                            "description": "Gras",
                            "role": "toggle_button",
                            "name": "Bold",
                            "path": ["frame:Untitled", "toolbar:Formatting"],
                        },
                        "states": ["checked"],
                    },
                },
                "known_errors": [],
            },
        ],
    }


async def test_generic_compiler_v2_lesson():
    client = HoloStub(["nope", json.dumps(raw_lesson())])
    compiler = GenericCompiler(get_profile("libreoffice-calc"), client=client)
    lesson = await compiler.compile(
        transcript(), build_ui_map(snapshot(), app=APP), lesson_id="ventes", app_version="7.3.7.2"
    )
    jsonschema.validate(lesson, SCHEMA)
    assert lesson["schema_version"] == "2.0" and "blender_version" not in lesson
    assert lesson["app"] == {**APP, "sensor": "accessibility"}
    first, second = lesson["steps"]
    assert first["check"]["params"]["target"]["name"] == "B6"
    assert first["procedure_ref"] == "computer_use/libreoffice-calc/sum_sales"
    assert second["target"] == {"description": "Bouton Gras"}
    assert compiler.unresolved["bold_header"][0]["reason"] == "contrôle inconnu"
    assert second["check"]["params"]["target"]["path"] == ["frame:Untitled", "toolbar:Formatting"]
    prompt = client.calls[0]["messages"][0]["content"]
    assert "toggle_button | Bold" in prompt and "Blender" not in prompt
    assert len(client.calls) == 2


async def test_generic_compiler_rejects_foreign_checks():
    raw = raw_lesson()
    raw["steps"][0]["check"] = {
        "name": "blender.object_exists",
        "params": {"type": "MESH", "primitive": "cube"},
    }
    compiler = GenericCompiler(get_profile("libreoffice-calc"), client=HoloStub([json.dumps(raw)]))
    lesson = await compiler.compile(
        transcript(), build_ui_map(snapshot(), app=APP), lesson_id="ventes", app_version="7.3.7.2"
    )
    assert "sum_sales" in compiler.rejections
    assert lesson["steps"][0]["proof"]["method"] == "handoff"
    with pytest.raises(ValueError):
        await GenericCompiler(get_profile("libreoffice-calc"), client=HoloStub([])).compile(
            Transcript(" ", "en", [], "u", "s", None, {}), {}, lesson_id="x", app_version="1"
        )


class FakeDesktop:
    """Calc simulé : B6 prend la valeur tapée après Entrée ; Bold coché après ctrl+b."""

    def __init__(self, tmp_path, version="7.3.7.2"):
        self.tmp_path, self._version = tmp_path, version
        self.typed = ""
        self.state = {}
        self.opened = []
        self.current = None

    async def version(self):
        return self._version

    async def open(self, checkpoint, *, sha256=None):
        if sha256 is not None and sha256 == self.current:
            return
        self.opened.append(Path(checkpoint).name)
        self.state = json.loads(Path(checkpoint).read_text() or "{}")
        self.current = sha256

    async def save(self, checkpoint_out):
        Path(checkpoint_out).write_text(json.dumps(self.state, sort_keys=True))
        return Path(checkpoint_out)

    def mark_current(self, sha256):
        self.current = sha256

    async def screenshot(self):
        return png(1000, 1000)

    async def snapshot(self, *, cells=None):
        snap = with_cell(snapshot(), "B6", self.state.get("B6", ""))
        if self.state.get("bold"):
            next(n for n in snap["nodes"] if n["name"] == "Bold")["states"].append("checked")
        return snap

    async def execute(self, action, *, image_size):
        if action["type"] == "type":
            self.typed += action["text"]
        elif action["type"] == "key" and action["keys"] == ["enter"]:
            self.state["B6"] = "465" if self.typed == "=SUM(B2:B5)" else "0"
        elif action["type"] == "key" and action["keys"] == ["ctrl", "b"]:
            self.state["bold"] = True


class FakeOperator:
    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    async def act(self, image, goal, *, lesson_context="", history=()):
        self.calls += 1
        return self.script.pop(0) if self.script else HoloAction("done")

    async def assert_visual(self, image, assertion, *, region=None):
        return {"answer": "unsure", "confidence": 0.0, "evidence": "-"}


async def compiled():
    compiler = GenericCompiler(
        get_profile("libreoffice-calc"), client=HoloStub([json.dumps(raw_lesson())])
    )
    return await compiler.compile(
        transcript(), build_ui_map(snapshot(), app=APP), lesson_id="ventes", app_version="7.3.7.2"
    )


def operator_script():
    return [
        HoloAction("click", x=100, y=200),
        HoloAction("type", text="=SUM(B2:B5)"),
        HoloAction("key", keys=("enter",)),
        HoloAction("key", keys=("ctrl", "b")),
    ]


async def test_generic_prover_nominal_and_reuse(tmp_path):
    lesson = await compiled()
    fixture = tmp_path / "initial.json"
    fixture.write_text("{}")
    desktop, operator = FakeDesktop(tmp_path), FakeOperator(operator_script())
    out = tmp_path / "out"
    result = await prove_generic_lesson(lesson, desktop, operator, out, fixture=fixture)
    jsonschema.validate(result, SCHEMA)
    assert result["status"] == "proven"
    assert [s["proof"]["status"] for s in result["steps"]] == ["proven", "proven"]
    assert result["steps"][0]["proof"]["ui_path_verified"]
    evidence = json.loads((out / "proof/sum_sales.json").read_text())
    assert evidence["check_before"]["result"] == "fail"
    assert evidence["known_errors_after"] == [{"code": "partial_range", "result": "fail"}]
    assert [t["action"]["type"] for t in evidence["attempts"][0]["turns"]] == [
        "click",
        "type",
        "key",
    ]
    assert evidence["attempts"][0]["turns"][1]["action"]["text"] == "=SUM(B2:B5)"
    assert evidence["checkpoint_sha256"] == file_sha256(out / "proof/sum_sales-checkpoint.json")
    manifest = json.loads((out / "proof/manifest.json").read_text())
    assert manifest["artifacts_sha256"]["proof/sum_sales.json"] == file_sha256(
        out / "proof/sum_sales.json"
    )
    assert desktop.opened == ["initial.json"]
    again = FakeOperator([])
    reused = await prove_generic_lesson(lesson, FakeDesktop(tmp_path), again, out, fixture=fixture)
    assert reused["status"] == "proven" and again.calls == 0
    assert json.loads((out / "proof/bold_header.json").read_text())["mode_trace"][0] == "REPLAY"


async def test_generic_prover_failure_blocks_and_vacuous_check(tmp_path):
    lesson = await compiled()
    fixture = tmp_path / "initial.json"
    fixture.write_text("{}")
    wrong = [HoloAction("type", text="=SUM(B2:B4)"), HoloAction("key", keys=("enter",))]
    result = await prove_generic_lesson(
        lesson,
        FakeDesktop(tmp_path),
        FakeOperator(wrong),
        tmp_path / "a",
        fixture=fixture,
        max_turns=3,
    )
    assert [s["proof"]["status"] for s in result["steps"]] == ["failed", "pending"]
    assert result["status"] == "failed"
    done_first = json.loads((tmp_path / "a/proof/sum_sales.json").read_text())
    assert done_first["mode_trace"][:3] == ["EXECUTE", "EXPLORE", "OBSERVE"]
    fixture.write_text(json.dumps({"B6": "465"}))
    vacuous = await prove_generic_lesson(
        lesson, FakeDesktop(tmp_path), FakeOperator([]), tmp_path / "b", fixture=fixture
    )
    evidence = json.loads((tmp_path / "b/proof/sum_sales.json").read_text())
    assert vacuous["steps"][0]["proof"]["status"] == "failed"
    assert "avant l'action" in evidence["reason"]


async def test_generic_prover_docs_retry_and_handoff(tmp_path):
    lesson = await compiled()
    fixture = tmp_path / "initial.json"
    fixture.write_text("{}")
    queries = []

    async def search(query):
        queries.append(query)
        return [{"name": "SUM", "url": "https://help.libreoffice.org/sum", "content": "=SUM()"}]

    script = [HoloAction("done")] * 3 + operator_script()
    result = await prove_generic_lesson(
        lesson,
        FakeDesktop(tmp_path),
        FakeOperator(script),
        tmp_path / "c",
        fixture=fixture,
        search=search,
        max_turns=3,
    )
    assert result["steps"][0]["proof"]["status"] == "proven"
    assert queries and queries[0].startswith("LibreOffice Calc 7.3.7.2")
    evidence = json.loads((tmp_path / "c/proof/sum_sales.json").read_text())
    assert len(evidence["attempts"]) == 2
    assert evidence["sources"][0]["url"] == "https://help.libreoffice.org/sum"
    lesson["steps"][1]["proof"]["method"] = "handoff"
    handed = await prove_generic_lesson(
        lesson,
        FakeDesktop(tmp_path),
        FakeOperator(operator_script()),
        tmp_path / "d",
        fixture=fixture,
    )
    assert handed["steps"][1]["proof"]["status"] == "pending"
    request = json.loads(next((tmp_path / "d/repair").iterdir()).read_text())
    assert request["app"]["id"] == "libreoffice-calc" and "blender_version" not in request
    with pytest.raises(ValueError):
        await prove_generic_lesson(
            lesson,
            FakeDesktop(tmp_path, "7.4.0"),
            FakeOperator([]),
            tmp_path / "e",
            fixture=fixture,
        )


def test_open_dialogs_blocks_completion():
    snap = snapshot()
    assert open_dialogs(snap, snap["windows"]) == []
    wizard = {**snap, "windows": [*snap["windows"], "Chart Type"]}
    assert open_dialogs(wizard, snap["windows"]) == ["Chart Type"]
    modal = copy.deepcopy(snap)
    modal["nodes"].append(
        {"ref": "e50", "role": "AXSheet", "name": "Save", "states": ["visible"], "parent_ref": "e2"}
    )
    assert open_dialogs(modal) == ["Save"]


async def test_lost_accessibility_falls_back_to_vision():
    lost = Observer({"complete": False, "nodes": [], "error": {"code": "APP_NOT_FOUND"}})
    check = {"name": "element_exists", "params": {"target": {"description": "chart"}}}
    verdict = await evaluate_check(check, lost, Judge("yes", 0.9), fallback="a chart is visible")
    assert verdict["result"] == "pass" and verdict["a11y_error"] == "APP_NOT_FOUND"
    assert verdict["sensor"] == "vision"
    assert (await evaluate_check(check, lost, Judge("yes", 0.9)))["result"] == "unknown"
    assert (await evaluate_check(check, lost, Judge("yes", 0.4), fallback="x"))["result"] == (
        "unknown"
    )
    assert describe_check(check) == "a chart is visible"


class NoA11yDesktop(FakeDesktop):
    async def snapshot(self, *, cells=None):
        raise AssertionError("étape visuelle : arbre d'accessibilité interrogé")


class ScreenJudge(FakeOperator):
    """Graphique visible ; l'assistant reste ouvert jusqu'au clic Finish."""

    def __init__(self, script):
        super().__init__(script)
        self.wizard_open = True

    async def assert_visual(self, image, assertion, *, region=None):
        if assertion == VISUAL_DIALOG_QUESTION:
            open_now, self.wizard_open = self.wizard_open, False
            return {"answer": "yes" if open_now else "no", "confidence": 0.95, "evidence": "-"}
        return {"answer": "yes", "confidence": 0.95, "evidence": "chart"}


async def test_visual_step_uses_vision_for_dialogs(tmp_path):
    step = {
        "instruction": "Insérer un graphique",
        "target": {"description": "menu Insertion > Graphique"},
        "check": {"name": "visual_assert", "params": {"assertion": "Is a chart visible?"}},
    }
    judge = ScreenJudge([HoloAction("done"), HoloAction("done")])
    result = await drive_step(NoA11yDesktop(tmp_path), judge, step, context="", max_turns=4)
    assert result["check"]["result"] == "pass" and result["check"]["sensor"] == "vision"
    assert result["turns"][0]["open_dialogs"] and "open_dialogs" not in result["turns"][1]


async def test_holo_quota_retry(monkeypatch):
    from engine.services.errors import QuotaExceeded
    from prep.prover import holo_desktop

    monkeypatch.setenv("HAI_API_KEY", "test")
    sleeps = []

    async def no_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(holo_desktop.asyncio, "sleep", no_sleep)
    agent = holo_desktop.HoloDesktopAgent()
    calls = []

    async def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise QuotaExceeded("holo", "HTTP 429 busy")
        return "ok"

    assert await agent._quota_retry("act", flaky) == "ok" and sleeps == [5.0]

    async def payment():
        raise QuotaExceeded("holo", "HTTP 402 credits")

    with pytest.raises(QuotaExceeded):
        await agent._quota_retry("act", payment)
    await agent.client.aclose()
