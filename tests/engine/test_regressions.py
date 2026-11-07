# ruff: noqa: E402

import asyncio
import json
import shutil
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

pytest.importorskip("websockets")
pytest.importorskip("httpx")

from test_e2e import replay
from test_servers import capture, event, send_ws

from engine.checks import SceneState, evaluate
from engine.learner import LearnerMemory
from engine.lesson import load_lesson

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def lesson_file(tmp_path):
    lesson = json.loads((FIXTURES / "single_lesson.json").read_text())
    shutil.copyfile(FIXTURES / "donut_session.jsonl", tmp_path / "donut_session.jsonl")
    path = tmp_path / "lesson.json"
    path.write_text(json.dumps(lesson))
    return path


def rewrite(path, change):
    lesson = json.loads(path.read_text())
    change(lesson)
    path.write_text(json.dumps(lesson))


@pytest.mark.parametrize("defect,message", [
    ("duplicates", "dupliqués"), ("synthetic_hash", "SHA256"),
    ("wrong_hash", "SHA256"), ("missing_proof", "absent-proof.json"),
    ("missing_source", "absent-source.txt"),
])
def test_proven_loader_rejects_unverifiable_lessons(lesson_file, defect, message):
    def change(lesson):
        if defect == "duplicates":
            lesson["steps"].append(deepcopy(lesson["steps"][0]))
        elif defect == "synthetic_hash":
            lesson["source"]["sha256"] = "synthetic"
        elif defect == "wrong_hash":
            lesson["source"]["sha256"] = "0" * 64
        elif defect == "missing_proof":
            lesson["steps"][0]["proof"]["evidence_ref"] = "absent-proof.json"
        else:
            lesson["source"]["uri"] = "absent-source.txt"

    rewrite(lesson_file, change)
    with pytest.raises(ValueError, match=message):
        load_lesson(lesson_file)


def test_remote_source_requires_verified_local_archive(lesson_file):
    rewrite(lesson_file, lambda lesson: lesson["source"].update(uri="https://example.com/source"))
    with pytest.raises(ValueError, match="Archive locale"):
        load_lesson(lesson_file)
    assert load_lesson(lesson_file, source_path=lesson_file.parent / "donut_session.jsonl")


def test_proof_symlink_escape_rejected(lesson_file, tmp_path):
    (tmp_path / "external.json").symlink_to(FIXTURES / "donut_session.jsonl")
    rewrite(lesson_file, lambda lesson: lesson["proof"].update(evidence_ref="external.json"))
    with pytest.raises(ValueError, match="external.json"):
        load_lesson(lesson_file)


@pytest.fixture(scope="session")
def blender_state(tmp_path_factory):
    blender = shutil.which("blender")
    if blender is None:
        pytest.skip("Blender absent : recette bpy headless non exécutée")
    output = tmp_path_factory.mktemp("blender-state") / "snapshot.json"
    subprocess.run([blender, "-b", "--factory-startup", "--python",
                    str(FIXTURES / "blender_snapshot.py"), "--", str(output)],
                   check=True, timeout=60, capture_output=True)
    return json.loads(output.read_text())


def test_genuine_blender_primitive_geometry(blender_state):
    state = SceneState()
    payload = {k: v for k, v in blender_state.items() if k != "version"}
    state.apply(event("snapshot", 2, 0, **payload))
    for obj in blender_state["objects"]:
        params = {"primitive": obj["primitive_provenance"]}
        assert evaluate("object_exists", state, params).status == "pass"
    print("BLENDER primitive geometry:", blender_state)


@pytest.mark.parametrize("compatible", [True, False])
async def test_exact_version_and_challenge_over_tcp_ws(lesson_file, tmp_path, blender_state,
                                                       compatible):
    def change(lesson):
        lesson["blender_version"] = blender_state["version"] if compatible else "99.0.0"
        lesson["steps"][0]["challenge"] = True

    rewrite(lesson_file, change)
    async with replay(tmp_path, lesson=load_lesson(lesson_file)) as h:
        hello = event()
        hello["payload"]["blender_version"] = blender_state["version"]
        await h.row(hello, ("request_snapshot",))
        payload = {k: v for k, v in blender_state.items() if k != "version"}
        await h.row(event("snapshot", 2, 0, **payload), ("success",) if compatible else ())
        skills = LearnerMemory(h.runtime.config.learner_path).skills
        if compatible:
            assert h.runtime.session.status == "COMPLETE"
            assert skills["add_torus"].unlocked
            assert skills["add_torus"].successes_without_help == 1
        else:
            assert h.runtime.session.status != "COMPLETE" and not skills
            assert not h.seen_decisions


@pytest.mark.parametrize("name,params,obj", [
    ("modifier_present", {"modifier_type": "SUBSURF", "params": {"levels": 2}},
     {"modifiers": [{"type": "SUBSURF", "levels": 2}]}),
    ("material_color", {"color": [1, 0, 0, 1]},
     {"materials": [{"base_color": [1, 0, 0, 1]}]}),
    ("shading_smooth", {}, {"mesh": {"shading_smooth": True}}),
    ("mode_is", {"mode": "OBJECT"}, {}),
    ("selection", {"type": "MESH", "active": True}, {"type": "MESH"}),
    ("object_count", {"type": "MESH", "count": 1}, {"type": "MESH"}),
    ("object_transform", {"location": [0, 0, 0]}, {"location": [0, 0, 0]}),
])
async def test_every_extended_check_loads_and_completes_over_tcp_ws(
    lesson_file, tmp_path, name, params, obj,
):
    rewrite(lesson_file, lambda lesson: lesson["steps"][0].update(
        check={"name": name, "params": params}, known_errors=[],
    ))
    async with replay(tmp_path, lesson=load_lesson(lesson_file)) as h:
        await h.row(event(), ("request_snapshot",))
        message = event("snapshot", 2, 0, mode="OBJECT", active="a", objects=[{"id": "a", **obj}])
        await h.row(message, ("success",))
        assert h.runtime.session.status == "COMPLETE"


async def test_operator_event_invalidates_full_help_context_and_inflight_holo(tmp_path):
    started, cancelled = asyncio.Event(), asyncio.Event()

    class Holo:
        async def localize(self, *args, **kwargs):
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise

    async with replay(tmp_path, holo=Holo()) as h:
        await h.row(event(), ("request_snapshot",))
        await h.row(event("snapshot", 2, 0, mode="OBJECT", active=None, objects=[]))
        await h.intent("aide")
        await h.intent("aide")
        # No region yet, so set only the policy level under test, not any help context.
        h.runtime.policy.level = 2
        await send_ws(h.ws, "capture.result", capture(h.runtime, "before-operator"))
        await asyncio.wait_for(started.wait(), 1)
        message = event("operator.executed", 3, 1,
                        idname="MESH_OT_primitive_cube_add", properties={})
        await h.row(message)
        await h.barrier()
        assert cancelled.is_set()
        assert h.runtime.capture is None
        assert h.runtime.context().image_png is None and h.runtime.context().target is None
        assert h.runtime.context().capture_id is None
        await h.intent("aide")
        assert not any(c["type"] == "pointer" for c, _ in h.commands)
        assert not h.runtime.targets.entries
