# ruff: noqa: E402

import asyncio
import copy
import json
import logging
import os
import shutil
from pathlib import Path

import jsonschema
import pytest

httpx = pytest.importorskip("httpx", reason="Installer l'extra prep pour ces tests")

from prep.docs_search import docs_search
from prep.prover import prove_lesson
from prep.prover.planner import TRANSITIONS, Mode, next_mode
from prep.prover.procedures import PROCEDURE_LIBRARY
from prep.repair import write_repair_request
from prep.sandbox import BlenderSandbox
from prep.ui_map import diff_ui_maps, dump_ui_map, step_signature


def lesson(primitives=("cube", "uv_sphere", "torus")):
    return {
        "schema_version": "1.0",
        "lesson_id": "primitives",
        "revision": 1,
        "title": "Ajouter des primitives",
        "language": "fr-FR",
        "blender_version": "4.5.9",
        "status": "draft",
        "source": {"uri": "fixture://primitives", "sha256": "abc"},
        "skills": ["add_primitive"],
        "proof": {
            "method": "per_step",
            "evidence_ref": "proof/manifest.json",
            "ui_path_verified": False,
        },
        "steps": [
            {
                "id": name,
                "skill_id": "add_primitive",
                "instruction": f"Ajouter {name}",
                "preconditions": {"mode": "OBJECT"},
                "check": {
                    "name": "object_exists",
                    "params": {"type": "MESH", "primitive": name},
                },
                "target": {
                    "description": "Ajouter une primitive",
                    "area_type": "VIEW_3D",
                    "region_type": "WINDOW",
                },
                "why": "Construire la scène",
                "audio_ref": None,
                "known_errors": [],
                "procedure_ref": f"add_primitive/{name}",
                "proof": {
                    "status": "draft",
                    "method": "bpy",
                    "evidence_ref": f"proof/{name}.json",
                    "ui_path_verified": False,
                },
            }
            for name in primitives
        ],
    }


def ui_map():
    return {
        "blender_version": "4.5.9",
        "operators": {
            item["operator_id"]: {"name": key, "properties": []}
            for key, item in PROCEDURE_LIBRARY.items()
        },
        "menus": {
            "VIEW3D_MT_add": {
                "label": "Add",
                "entries": [
                    {"kind": "operator", "id": item["operator_id"], "label": key}
                    for key, item in PROCEDURE_LIBRARY.items()
                ],
            }
        },
    }


class StubSandbox:
    def __init__(self, root, outcomes=None):
        self.root = root
        self.outcomes = iter(outcomes or ["pass"] * 10)
        self.calls = 0

    async def version(self):
        return "4.5.9"

    async def reset(self):
        path = self.root / "empty.blend"
        path.write_bytes(b"empty")
        return path

    async def run_step(self, checkpoint, procedure, check, output):
        self.calls += 1
        outcome = next(self.outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        output.write_bytes(Path(checkpoint).read_bytes() + procedure.encode())
        return {"before": [], "after": [], "check_result": outcome, "duration": 0.01}


@pytest.mark.parametrize("pair,target", TRANSITIONS.items())
def test_transitions(pair, target):
    assert next_mode(*pair) == target


def test_illegal_transition():
    with pytest.raises(ValueError):
        next_mode(Mode.HANDOFF, "success")


def test_diff():
    a = ui_map()
    assert not any(diff_ui_maps(a, a).values())
    b = copy.deepcopy(a)
    b["operators"]["mesh.primitive_cube_add"]["name"] = "Autre"
    b["operators"]["new.op"] = {}
    del b["operators"]["mesh.primitive_torus_add"]
    b["menus"]["VIEW3D_MT_add"]["label"] = "Ajouter"
    diff = diff_ui_maps(a, b)
    assert diff["added_operators"] == ["new.op"]
    assert diff["removed_operators"] == ["mesh.primitive_torus_add"]
    assert diff["changed_operators"] == ["mesh.primitive_cube_add"]
    assert diff["changed_menu_paths"] == ["VIEW3D_MT_add"]
    assert step_signature({}, "missing") is None


def test_repair(tmp_path):
    path = write_repair_request(
        tmp_path,
        lesson_id="l",
        step_id="../x",
        reason="Check absent",
        fixture="empty.blend",
        expected_result={},
        blender_version="4.5.9",
    )
    assert path.parent == tmp_path / "repair"
    assert json.loads(path.read_text())["reason"] == "Check absent"


async def test_prover_nominal_and_reuse(tmp_path):
    sandbox = StubSandbox(tmp_path)
    result = await prove_lesson(lesson(), sandbox, ui_map(), ui_map(), tmp_path)
    assert result["status"] == "proven"
    jsonschema.validate(result, json.loads(Path("contracts/lesson.schema.json").read_text()))
    await prove_lesson(lesson(), sandbox, ui_map(), ui_map(), tmp_path)
    assert sandbox.calls == 3


async def test_empty(tmp_path):
    assert (await prove_lesson(lesson(()), StubSandbox(tmp_path), {}, {}, tmp_path))[
        "status"
    ] == "pending"


@pytest.mark.parametrize("error", [RuntimeError("Erreur"), TimeoutError("Délai")])
async def test_prover_error(tmp_path, error):
    result = await prove_lesson(
        lesson(), StubSandbox(tmp_path, [error]), ui_map(), ui_map(), tmp_path
    )
    assert result["status"] == "failed"
    assert result["steps"][1]["proof"]["status"] == "pending"


async def test_handoff_and_changed(tmp_path):
    data = lesson()
    data["steps"][0]["check"] = {}
    result = await prove_lesson(data, StubSandbox(tmp_path), None, ui_map(), tmp_path)
    assert result["steps"][0]["proof"]["method"] == "handoff"
    assert list((tmp_path / "repair").glob("*.json"))
    result = await prove_lesson(lesson(), StubSandbox(tmp_path), None, ui_map(), tmp_path)
    assert result["steps"][0]["proof"]["method"] == "holo_sandbox"
    assert (tmp_path / "sandbox_jobs/cube.json").exists()


async def test_retry(tmp_path):
    async def search(query):
        return [{"url": "https://docs.blender.org/manual/en/latest/", "name": "Manuel"}]

    async def reselect(step, docs):
        assert docs
        return "add_primitive/cube"

    sandbox = StubSandbox(tmp_path, ["fail", "pass"])
    result = await prove_lesson(
        lesson(("cube",)), sandbox, ui_map(), ui_map(), tmp_path, reselect=reselect, search=search
    )
    assert result["status"] == "proven"
    evidence = json.loads((tmp_path / "proof/cube.json").read_text())
    assert evidence["mode_trace"] == ["EXECUTE", "EXPLORE", "OBSERVE", "EXECUTE", "CONSOLIDATE"]
    assert evidence["sources"]


async def test_search_errors(monkeypatch):
    monkeypatch.delenv("LINKUP_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        await docs_search("Blender")
    monkeypatch.setenv("LINKUP_API_KEY", "test")

    def timeout(request):
        raise httpx.ReadTimeout("Délai")

    async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as client:
        with pytest.raises(TimeoutError, match="15 s"):
            await docs_search("Blender", client=client)


@pytest.mark.parametrize(
    "results",
    [
        [],
        [
            {"name": "Manuel", "url": "https://docs.blender.org/manual/", "content": "Texte"},
            {"name": "Autre", "url": "https://example.org", "content": "Ignoré"},
        ],
    ],
)
async def test_search_results(monkeypatch, results):
    monkeypatch.setenv("LINKUP_API_KEY", "test")

    def handler(request):
        assert json.loads(request.content)["includeDomains"] == ["docs.blender.org"]
        return httpx.Response(200, json={"results": results})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        found = await docs_search("Blender", client=client)
    assert len(found) == (1 if results else 0)


async def test_retry_fails(tmp_path):
    async def search(query):
        return []

    async def reselect(step, docs):
        return "add_primitive/cube"

    sandbox = StubSandbox(tmp_path, ["unknown", "fail"])
    result = await prove_lesson(
        lesson(("cube",)), sandbox, ui_map(), ui_map(), tmp_path, search=search, reselect=reselect
    )
    assert result["status"] == "failed"
    assert sandbox.calls == 2


async def test_subprocess_timeout_and_environment(monkeypatch):
    class Process:
        killed = False
        waited = False

        async def communicate(self):
            await asyncio.Event().wait()

        def kill(self):
            self.killed = True

        async def wait(self):
            self.waited = True

    process = Process()

    async def create(*args, **kwargs):
        assert not any(key.endswith("_API_KEY") for key in kwargs["env"])
        return process

    monkeypatch.setenv("TEST_API_KEY", "test")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", create)
    async with BlenderSandbox(timeout=0.001) as sandbox:
        with pytest.raises(TimeoutError):
            await sandbox.version()
    assert process.killed and process.waited


@pytest.mark.skipif(not shutil.which("blender"), reason="Blender absent")
async def test_real_blender(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    async with BlenderSandbox() as sandbox:
        assert await sandbox.version() == "4.5.9"
        empty = await sandbox.reset()
        check = lesson(("torus",))["steps"][0]["check"]
        inspected = await sandbox.invoke("inspect", checkpoint_in=str(empty), check=check)
        assert inspected["after"] == []
        assert inspected["check_result"] != "pass"
        torus = await sandbox.run_step(
            empty, "add_primitive/torus", check, tmp_path / "torus.blend"
        )
        assert torus["before"] == []
        assert torus["check_result"] == "pass"
        wrong = await sandbox.run_step(
            empty, "add_primitive/torus", lesson()["steps"][0]["check"], tmp_path / "wrong.blend"
        )
        assert wrong["check_result"] == "fail"
        mapping = await dump_ui_map(sandbox, tmp_path / "maps")
        assert any(
            entry["id"] == "mesh.primitive_torus_add"
            for entry in mapping["menus"]["VIEW3D_MT_mesh_add"]["entries"]
        )
        assert not any(diff_ui_maps(mapping, mapping).values())
        assert step_signature(mapping, "mesh.primitive_torus_add") is not None
        result = await prove_lesson(lesson(), sandbox, mapping, mapping, tmp_path / "out")
        assert result["status"] == "proven"
        jsonschema.validate(result, json.loads(Path("contracts/lesson.schema.json").read_text()))
        print(f"Blender torus duration: {torus['duration']:.3f} s")
        print(f"UI map worker duration: {mapping['duration']:.3f} s")


@pytest.mark.live
@pytest.mark.skipif(not os.environ.get("LINKUP_API_KEY"), reason="Clé Linkup absente")
async def test_live_linkup(caplog):
    caplog.set_level(logging.INFO)
    results = await docs_search("Blender manual mesh torus primitive")
    assert results
    assert all(item["url"].startswith("https://docs.blender.org/") for item in results)
    assert "Linkup :" in caplog.text
    print(caplog.text)
