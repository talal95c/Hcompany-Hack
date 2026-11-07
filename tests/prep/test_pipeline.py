import asyncio
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import jsonschema
import pytest
from openai import RateLimitError
from test_preparation import StubSandbox, lesson, ui_map

from prep.compile import HoloCompiler
from prep.compile.compiler import SCHEMA
from prep.ingest import Transcript, TranscriptionTimeout, ingest, vocabulary_from_ui_map
from prep.prover import prove_lesson


def transcript(text="Ajoute un cube."):
    return Transcript(text, "fr", [], Path(__file__).as_uri(), "abc", None, {})


def model_lesson():
    source = lesson(("cube",))
    step = copy.deepcopy(source["steps"][0])
    for key in ("proof", "audio_ref"):
        step.pop(key)
    return {"title": "Créer un cube", "steps": [step]}


class HoloStub:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    async def create(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        if response == "wait":
            await asyncio.Event().wait()
        return SimpleNamespace(
            usage=SimpleNamespace(model_dump=lambda: {"total_tokens": 100}),
            choices=[SimpleNamespace(message=SimpleNamespace(content=response))],
        )


async def test_compile_nominal_and_retry():
    client = HoloStub(["not json", json.dumps(model_lesson())])
    compiler = HoloCompiler(client=client)
    result = await compiler.compile(
        transcript(), ui_map(), lesson_id="cube", blender_version="4.5.9"
    )
    jsonschema.validate(result, json.loads(SCHEMA.read_text()))
    assert result["steps"][0]["target"]["description"] == "Ajouter › Cube"
    assert client.calls[0]["temperature"] == 0
    assert len(client.calls) == 2
    assert compiler.metrics[0]["usage"]["total_tokens"] == 100
    assert "Réponse invalide" in client.calls[1]["messages"][-1]["content"]


@pytest.mark.parametrize("raw", ["", "{}", '{"title":"Vide","steps":[]}'])
async def test_compile_invalid(raw):
    compiler = HoloCompiler(client=HoloStub([raw, raw]))
    with pytest.raises(ValueError, match="deux essais"):
        await compiler.compile(transcript(), ui_map(), lesson_id="cube", blender_version="4.5.9")


async def test_compile_empty_and_timeout():
    compiler = HoloCompiler(client=HoloStub(["wait"]), timeout=0.001)
    with pytest.raises(ValueError, match="vide"):
        await compiler.compile(transcript(""), {}, lesson_id="cube", blender_version="4.5.9")
    with pytest.raises(TimeoutError, match="Holo"):
        await compiler.compile(transcript(), {}, lesson_id="cube", blender_version="4.5.9")


@pytest.mark.parametrize("field", ["check", "procedure_ref"])
async def test_compile_rejected_handoff(tmp_path, field):
    raw = model_lesson()
    raw["steps"][0][field] = (
        {"name": "invented", "params": {"type": "MESH", "primitive": "cube"}}
        if field == "check"
        else "invented/procedure"
    )
    compiler = HoloCompiler(client=HoloStub([json.dumps(raw)]))
    compiled = await compiler.compile(
        transcript(),
        ui_map(),
        lesson_id="cube",
        blender_version="4.5.9",
    )
    jsonschema.validate(compiled, json.loads(SCHEMA.read_text()))
    assert compiler.rejections["cube"]["original_step"][field] == raw["steps"][0][field]
    result = await prove_lesson(
        compiled,
        StubSandbox(tmp_path),
        ui_map(),
        ui_map(),
        tmp_path,
        rejected_steps=compiler.rejections,
    )
    assert result["steps"][0]["proof"]["method"] == "handoff"
    assert result["status"] == "pending"
    request = json.loads(next((tmp_path / "repair").glob("*.json")).read_text())
    assert request["expected_result"]["original_step"][field] == raw["steps"][0][field]


async def test_reselect():
    compiler = HoloCompiler(
        client=HoloStub(
            [
                '{"procedure_ref":"add_primitive/cube"}',
                '{"procedure_ref":"unknown"}',
            ]
        )
    )
    assert await compiler.reselect({}, []) == "add_primitive/cube"
    with pytest.raises(ValueError, match="non autorisée"):
        await compiler.reselect({}, [])


async def test_compile_model_fallback():
    response = httpx.Response(429, request=httpx.Request("POST", "https://api.hcompany.ai/v1"))
    client = HoloStub(
        [RateLimitError("Quota", response=response, body={}), json.dumps(model_lesson())]
    )
    compiler = HoloCompiler(client=client)
    result = await compiler.compile(
        transcript(), ui_map(), lesson_id="cube", blender_version="4.5.9"
    )
    assert result["status"] == "draft"
    assert [call["model"] for call in client.calls] == ["holo4-35b-a3b", "holo4-27b"]
    assert compiler.metrics[0]["status_code"] == 429


async def test_ingest_text_and_download(tmp_path):
    source = tmp_path / "tutorial.md"
    source.write_text("Ajoute un cube.")
    result = await ingest(source, work_dir=tmp_path / "work", language="fr")
    assert result.text == "Ajoute un cube."
    assert result.sha256 == hashlib.sha256(source.read_bytes()).hexdigest()
    assert len(result.segments) == 1

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=b"Ajoute un tore.")
        )
    ) as client:
        result = await ingest(
            "https://docs.blender.org/tutorial.txt", work_dir=tmp_path / "url", client=client
        )
        assert result.text == "Ajoute un tore."
        with pytest.raises(ValueError, match="volumineuse"):
            await ingest(
                "https://docs.blender.org/tutorial.txt",
                work_dir=tmp_path / "large",
                client=client,
                max_bytes=2,
            )


@pytest.mark.parametrize("data", [b"", b" \n"])
async def test_ingest_empty(tmp_path, data):
    source = tmp_path / "empty.txt"
    source.write_bytes(data)
    with pytest.raises(ValueError, match="vide"):
        await ingest(source, work_dir=tmp_path / "work")


async def test_download_timeout(tmp_path):
    def handler(request):
        raise httpx.ReadTimeout("Délai")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(TimeoutError, match="Téléchargement"):
            await ingest("https://docs.blender.org/tutorial.txt", work_dir=tmp_path, client=client)


@pytest.mark.parametrize("state", ["done", "empty", "error", "timeout"])
async def test_gladia_mock(tmp_path, monkeypatch, state):
    monkeypatch.setenv("GLADIA_API_KEY", "test")
    source = tmp_path / "input.wav"
    source.write_bytes(b"audio")

    async def convert(source, target):
        target.write_bytes(b"converted")

    monkeypatch.setattr("prep.ingest.convert_audio", convert)
    calls = []

    def handler(request):
        calls.append(request)
        assert request.headers["x-gladia-key"] == "test"
        if request.url.path == "/v2/upload":
            return httpx.Response(200, json={"audio_url": "https://api.gladia.io/audio.wav"})
        if request.url.path == "/v2/pre-recorded":
            payload = json.loads(request.content)
            assert payload["custom_vocabulary"] is True
            assert "Tore" in payload["custom_vocabulary_config"]["vocabulary"]
            return httpx.Response(
                200,
                json={"id": "job-1", "result_url": "https://api.gladia.io/v2/pre-recorded/job-1"},
            )
        if state == "timeout":
            return httpx.Response(200, json={"status": "processing"})
        if state == "error":
            return httpx.Response(200, json={"status": "error"})
        return httpx.Response(
            200,
            json={
                "status": "done",
                "result": {
                    "transcription": {
                        "full_transcript": "" if state == "empty" else "Ajoute un cube.",
                        "languages": ["fr"],
                        "utterances": [
                            {
                                "text": "Ajoute un cube.",
                                "start": 0,
                                "end": 2,
                                "words": [{"word": "Ajoute", "start": 0, "end": 1}],
                            }
                        ],
                    }
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        if state == "done":
            result = await ingest(source, work_dir=tmp_path / "work", client=client)
            assert result.gladia_job_id == "job-1"
            assert result.language == "fr"
            assert result.segments[0]["words"][0]["start"] == 0
            assert result.latencies.keys() == {"upload", "transcription"}
        else:
            error = {"empty": ValueError, "error": RuntimeError, "timeout": TranscriptionTimeout}[
                state
            ]
            with pytest.raises(error) as exc:
                await ingest(
                    source,
                    work_dir=tmp_path / "work",
                    client=client,
                    transcription_timeout=0.01,
                    poll_interval=0.001,
                )
            if state == "timeout":
                assert exc.value.job_id == "job-1"
            assert json.loads((tmp_path / "work/gladia-job.json").read_text())["id"] == "job-1"


def test_vocabulary():
    words = vocabulary_from_ui_map(
        {
            "menus": {
                "menu": {
                    "label": "Libellé spécifique",
                    "entries": [{"label": "Opérateur spécifique"}],
                }
            }
        }
    )
    assert {"Tore", "UV Sphere", "Libellé spécifique", "Opérateur spécifique"} <= set(words)
