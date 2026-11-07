import hashlib
import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from engine.checks import SceneState, evaluate
from engine.checks.lesson_steps import evaluate_verification
from engine.config import EngineConfig
from engine.interfaces import HoloClient, JevClient, SearchClient, SttClient
from engine.lesson import Session, load_lesson, load_verification
from engine.lesson.runtime import EngineRuntime
from engine.services.adapters import (
    HoloAdapter,
    JevAdapter,
    SearchAdapter,
    SttAdapter,
    build_clients,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("name", ["donut", "mini-cube"])
def test_proven_authored_lessons(name, tmp_path):
    path = ROOT / "lessons" / name / "lesson.json"
    lesson = load_lesson(path)
    companion = load_verification(path, lesson)
    assert set(companion) == {s["id"] for s in lesson["steps"]}
    copy = tmp_path / name
    shutil.copytree(path.parent, copy)
    (copy / "SOURCE.md").write_text("tampered")
    with pytest.raises(ValueError, match="SHA256"):
        load_lesson(copy / "lesson.json")
    (copy / "SOURCE.md").write_bytes((path.parent / "SOURCE.md").read_bytes())
    (copy / "steps.json").write_text("{}")
    with pytest.raises(ValueError, match="Preuve incompatible"):
        load_verification(copy / "lesson.json", lesson)


def test_cloud_factory_without_keys(monkeypatch):
    for key in ("HAI_API_KEY", "CODIV_API_KEY", "GLADIA_API_KEY", "LINKUP_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    assert build_clients(EngineConfig()) == {}
    assert EngineConfig().holo_model == "holo4-27b"
    monkeypatch.setenv("ENGINE_HOLO_MODEL", "another-model")
    assert EngineConfig.from_env().holo_model == "another-model"


async def test_cloud_adapters():
    holo = HoloAdapter(SimpleNamespace(locate=AsyncMock(return_value=(500.2, 700, float("nan")))))
    assert isinstance(holo, HoloClient)
    result = await holo.localize(b"image", "target", timeout_s=1)
    assert (result.x, result.y, result.confidence) == (500, 700, None)
    holo.client.locate.side_effect = ValueError("bad response")
    with pytest.raises(ValueError):
        await holo.localize(b"image", "target", timeout_s=1)
    jev = JevAdapter(SimpleNamespace(
        decide=AsyncMock(return_value={"action": SimpleNamespace(choice="intervene")}),
        classify_intent=AsyncMock(return_value=SimpleNamespace(choice="question"))))
    assert isinstance(jev, JevClient)
    assert (await jev.decide({}, timeout_s=1)).action == "intervene"
    assert (await jev.decide({"utterance": "pourquoi"}, timeout_s=1)).action == "question"
    stt = SttAdapter(SimpleNamespace(transcribe_file=AsyncMock(
        return_value=SimpleNamespace(text="bonjour"))))
    assert isinstance(stt, SttClient)
    assert (await stt.transcribe(b"\0\0", encoding="pcm_s16le", sample_rate=16000,
                                 language="fr")).text == "bonjour"
    assert stt.client.transcribe_file.call_args.args[0].startswith(b"RIFF")
    with pytest.raises(ValueError):
        await stt.transcribe(b"bad", encoding="bad", sample_rate=16000, language="fr")
    search = SearchAdapter(SimpleNamespace(search=AsyncMock(return_value=SimpleNamespace(
        sources=[SimpleNamespace(name="docs", url="https://docs.blender.org", snippet="text")]))))
    assert isinstance(search, SearchClient)
    assert (await search.search("Blender"))[0].title == "docs"


def test_companion_prevents_presence_only_success():
    state = SceneState(objects={"cube": {"type": "MESH", "primitive_provenance": "cube",
                                        "mesh": {"verts": 8, "edges": 12, "polys": 6},
                                        "modifiers": []}}, revision=1, latest_revision=1,
                       complete=True)
    base = evaluate("object_exists", state, {"type": "MESH", "primitive": "cube"})
    check = {"name": "modifier", "params": {"target": "cube", "type": "BEVEL"}}
    assert base.status == "pass"
    assert evaluate_verification([check], state, base).status == "fail"
    state.objects["cube"]["modifiers"] = [{"type": "BEVEL"}]
    assert evaluate_verification([check], state, base).status == "pass"
    assert evaluate_verification([], state, base) is base
    unknown = {"name": "shade_smooth", "params": {"target": "cube"}}
    assert evaluate_verification([unknown], state, base).status == "unknown"
    state.objects.clear()
    assert evaluate_verification([check], state, base).status == "fail"


def test_archived_source_hash():
    lesson = load_lesson(ROOT / "lessons/donut/lesson.json")
    assert lesson["source"]["sha256"] == hashlib.sha256(
        (ROOT / "lessons/donut/SOURCE.md").read_bytes()).hexdigest()
    assert json.loads((ROOT / "contracts/desktop-ws.schema.json").read_text())


def test_help_context_selects_editor_not_just_window_region(tmp_path):
    runtime = EngineRuntime(EngineConfig(lesson=ROOT / "lessons/donut/lesson.json",
                                       learner_path=tmp_path / "learner.json"))
    runtime.regions = [
        {"area_id": "properties", "area_type": "PROPERTIES", "region_id": "first",
         "type": "WINDOW"},
        {"area_id": "viewport", "area_type": "VIEW_3D", "region_id": "second",
         "type": "WINDOW"},
    ]
    assert runtime.context().area_id == "viewport"
    assert runtime.context().region_id == "second"
    runtime.regions.clear()
    assert runtime.context().area_id is None


def test_blender_edit_mesh_mode_matches_lesson_edit_precondition():
    session = Session("mode", load_lesson(ROOT / "lessons/donut/lesson.json"))
    session.index = 4
    assert not session.observe(None)
    assert not session.observe("OBJECT")
    assert session.observe("EDIT_MESH")
    assert session.status == "OBSERVING"
