# ruff: noqa: E402

import asyncio
import json
import logging
import os
import shutil
import sys
from pathlib import Path

import jsonschema
import pytest

pytest.importorskip("httpx", reason="Installer l'extra prep pour ces tests")
pytest.importorskip("openai", reason="Installer l'extra prep pour ces tests")

from prep.compile import HoloCompiler
from prep.compile.compiler import SCHEMA
from prep.ingest import Transcript, ingest
from prep.prover import digest, prove_lesson
from prep.prover.procedures import PROCEDURE_LIBRARY
from prep.sandbox import BlenderSandbox
from prep.ui_map import dump_ui_map

NARRATION = (
    "Bonjour. Dans ce tutoriel nous allons créer trois objets dans Blender. "
    "Première étape : ajoute un cube avec le menu Ajouter, Maillage, Cube. "
    "Deuxième étape : ajoute une sphère UV avec le menu Ajouter, Maillage, Sphère UV. "
    "Troisième étape : ajoute un tore avec le menu Ajouter, Maillage, Tore."
)


@pytest.fixture
def audio_tools():
    missing = [name for name in ("espeak-ng", "ffmpeg", "blender") if not shutil.which(name)]
    assert not missing, f"Installer les outils live requis : {', '.join(missing)}"


async def command(*args: str, timeout: float = 240) -> tuple[int, str]:
    process = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        output, _ = await asyncio.wait_for(process.communicate(), timeout)
    except (TimeoutError, asyncio.CancelledError):
        process.kill()
        await process.wait()
        raise
    return process.returncode, output.decode()


async def synthesize(root: Path) -> Path:
    wav = root / "narration.wav"
    mp3 = root / "narration.mp3"
    code, output = await command("espeak-ng", "-v", "fr", "-s", "145", "-w", str(wav), NARRATION)
    assert code == 0, output
    code, output = await command("ffmpeg", "-v", "error", "-y", "-i", str(wav), str(mp3))
    assert code == 0, output
    return mp3


@pytest.mark.live
@pytest.mark.skipif(not os.environ.get("HAI_API_KEY"), reason="Clé Holo absente")
async def test_live_holo_compile(caplog):
    assert shutil.which("blender"), "Installer Blender pour le test live"
    caplog.set_level(logging.INFO)
    async with BlenderSandbox() as sandbox:
        mapping = await dump_ui_map(sandbox)
    source = Transcript(
        "Ajoute un cube avec Ajouter, Maillage, Cube.",
        "fr",
        [],
        Path(__file__).as_uri(),
        "abc",
        None,
        {},
    )
    async with HoloCompiler() as compiler:
        result = await compiler.compile(
            source, mapping, lesson_id="cube", blender_version=mapping["blender_version"]
        )
        jsonschema.validate(result, json.loads(SCHEMA.read_text()))
        assert len(result["steps"]) == 1
        assert result["steps"][0]["procedure_ref"] == "add_primitive/cube"
        assert not compiler.rejections
        assert result["steps"][0]["known_errors"]
        print("Holo metrics:", json.dumps(compiler.metrics))


@pytest.mark.live
@pytest.mark.skipif(not os.environ.get("GLADIA_API_KEY"), reason="Clé Gladia absente")
async def test_live_gladia(tmp_path, caplog, audio_tools):
    caplog.set_level(logging.INFO)
    source = await synthesize(tmp_path)
    result = await ingest(source, work_dir=tmp_path / "ingest", language="fr")
    assert "cube" in result.text.lower()
    assert result.gladia_job_id
    assert result.segments and result.segments[0]["words"]
    print("Gladia latencies:", json.dumps(result.latencies))
    print("Transcript:", result.text)


@pytest.mark.live
@pytest.mark.skipif(
    not all(os.environ.get(key) for key in ("GLADIA_API_KEY", "HAI_API_KEY")),
    reason="Clés absentes",
)
async def test_live_end_to_end(tmp_path, audio_tools):
    source = await synthesize(tmp_path)
    out = tmp_path / "lessons/demo"
    code, output = await command(
        sys.executable, "-m", "prep", str(source), "--out", str(out), "--language", "fr"
    )
    print(output)
    assert code == 0, output
    result = json.loads((out / "lesson.json").read_text())
    jsonschema.validate(result, json.loads(SCHEMA.read_text()))
    assert result["status"] == "proven"
    assert len(result["steps"]) == 3
    assert [step["procedure_ref"] for step in result["steps"]] == [
        "add_primitive/cube",
        "add_primitive/uv_sphere",
        "add_primitive/torus",
    ]
    assert all(
        step["proof"]["status"] == "proven" and step["proof"]["method"] == "bpy"
        for step in result["steps"]
    )
    assert all(step["known_errors"] for step in result["steps"])
    print("timings.json:", (out / "timings.json").read_text())


@pytest.mark.live
@pytest.mark.skipif(
    not all(os.environ.get(key) for key in ("HAI_API_KEY", "LINKUP_API_KEY")),
    reason="Clés Holo/Linkup absentes",
)
async def test_live_recovery_exports_proven_procedure(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    assert shutil.which("blender"), "Installer Blender pour le test live"
    async with BlenderSandbox() as sandbox, HoloCompiler() as compiler:
        mapping = await dump_ui_map(sandbox, tmp_path / "maps")
        source = Transcript(
            "Ajoute un singe Suzanne avec Ajouter, Maillage, Singe.",
            "fr",
            [],
            Path(__file__).as_uri(),
            "abc",
            None,
            {},
        )
        lesson = await compiler.compile(
            source,
            mapping,
            lesson_id="recovery",
            blender_version=mapping["blender_version"],
        )
        assert len(lesson["steps"]) == 1
        assert lesson["steps"][0]["check"]["params"]["primitive"] == "monkey"
        lesson["steps"][0]["procedure_ref"] = "add_primitive/cube"
        out = tmp_path / "recovery"
        proven = await prove_lesson(
            lesson, sandbox, mapping, mapping, out, reselect=compiler.reselect
        )
        exported = json.loads((out / "lesson.json").read_text())
        jsonschema.validate(exported, json.loads(SCHEMA.read_text()))
        assert exported == proven
        assert exported["status"] == "proven"
        step = exported["steps"][0]
        assert step["procedure_ref"] == "add_primitive/monkey"
        assert "Singe" in step["target"]["description"]
        evidence_path = out / step["proof"]["evidence_ref"]
        evidence = json.loads(evidence_path.read_text())
        assert [attempt["check_result"] for attempt in evidence["attempts"]] == ["fail", "pass"]
        assert evidence["selected_procedure"] == step["procedure_ref"]
        assert evidence["hashes"]["procedure"] == digest(
            {"id": step["procedure_ref"], "definition": PROCEDURE_LIBRARY[step["procedure_ref"]]}
        )
        assert all("/4.5/" in item["url"] for item in evidence["sources"])
        replay = await prove_lesson(
            exported, sandbox, mapping, mapping, out, fixture=out / "fixtures/initial.blend"
        )
        assert replay["status"] == "proven"
        assert "REPLAY" in json.loads(evidence_path.read_text())["mode_trace"]
        print("Recovery Holo metrics:", json.dumps(compiler.metrics))
        print("Recovery Blender durations:", [a["duration"] for a in evidence["attempts"]])
