# ruff: noqa: E402

import base64
import io
import json
import wave

import pytest

httpx = pytest.importorskip(
    "httpx", reason="Installez les dépendances : pip install -e '.[engine]'",
)
pytest.importorskip("websockets", reason="Installez les dépendances : pip install -e '.[engine]'")

from live_clients import (
    CodivClient,
    GladiaHttpClient,
    HoloHttpClient,
    LinkupHttpClient,
    menu_png,
    silence_wav,
)

from engine.fallback import Fallback
from engine.lesson.runtime import decode_capture


def test_generated_png_and_wav():
    image = menu_png()
    assert decode_capture({"image_ref": "data:image/png;base64,"
                           + base64.b64encode(image).decode(),
                           "crop": {"width": 320, "height": 160}}) == image
    with wave.open(io.BytesIO(silence_wav())) as audio:
        assert audio.getparams()[:4] == (1, 2, 16000, 16000)


@pytest.mark.parametrize("models", [
    {"models": [{"name": "openjev-latest"}]},
    {"data": [{"id": "openjev-latest"}]},
])
async def test_codiv_discovery_and_decision(models):
    def respond(request):
        if request.method == "GET":
            assert request.url.path == "/v1/models"
            return httpx.Response(200, json=models)
        assert request.url.path == "/v1/systemone"
        body = json.loads(request.content)
        assert body["model"] == "openjev-latest"
        assert body["questions"]["action"]["type"] == "choice"
        return httpx.Response(200, json={"answers": {"action": {"choice": "wait"}}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        client = CodivClient(http)
        assert await client.discover() == ["openjev-latest"]
        assert (await client.decide({"check_status": "unknown"}, timeout_s=.8)).action == "wait"


@pytest.mark.parametrize("models", [{}, {"models": []}, {"data": [{"id": "other"}]}])
async def test_codiv_missing_model(models):
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda _: httpx.Response(200, json=models),
    )) as http:
        with pytest.raises(ValueError):
            await CodivClient(http).discover()


@pytest.mark.parametrize("content,valid", [
    ('{"x":500,"y":625}', True), ('```json\n{"x":0,"y":1000}\n```', True),
    ("", False), ('{"x":1001,"y":0}', False), ('{"x":true,"y":0}', False),
    ('{"x":0.5,"y":0}', False), ('{"y":0}', False),
])
async def test_holo_parse_and_clean_fallback(content, valid):
    def respond(request):
        body = json.loads(request.content)
        assert request.url.path == "/v1/chat/completions"
        assert body["structured_outputs"]["json"]["required"] == ["x", "y"]
        assert body["chat_template_kwargs"] == {"enable_thinking": False}
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    metrics = []
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        client = HoloHttpClient(http)
        point = await Fallback(record=metrics.append).call(
            "holo", lambda: client.localize(menu_png(), "rectangle rouge", timeout_s=5),
            5, lambda: None,
        )
        assert (point is not None) == valid
        assert metrics[-1]["status"] == ("ok" if valid else "fallback")


@pytest.mark.parametrize("text", ["", "Bonjour"])
async def test_gladia_upload_roundtrip(text):
    def respond(request):
        if request.url.path == "/v2/upload":
            assert b"silence.wav" in request.content
            return httpx.Response(200, json={"audio_url": "https://example.com/audio"})
        if request.method == "POST":
            assert json.loads(request.content)["language_config"] == {"languages": ["fr"]}
            return httpx.Response(201, json={"id": "job"})
        assert request.url.path == "/v2/pre-recorded/job"
        return httpx.Response(200, json={"status": "done", "result": {
            "transcription": {"full_transcript": text},
        }})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        client = GladiaHttpClient(http)
        transcript = await client.transcribe(silence_wav(), encoding="wav", sample_rate=16000,
                                             language="fr")
        assert transcript.text == text and transcript.latency_ms >= 0
        assert client.attempts == 3


@pytest.mark.parametrize("results, count", [
    ([], 0), ([{"type": "text", "name": "Blender", "url": "https://blender.org",
               "content": "Manuel"}], 1),
    ([{"type": "image"}], 0),
])
async def test_linkup_results_and_empty(results, count):
    def respond(request):
        assert json.loads(request.content)["outputType"] == "searchResults"
        return httpx.Response(200, json={"results": results})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        assert len(await LinkupHttpClient(http).search("tore")) == count


@pytest.mark.parametrize("client_type, status", [
    (CodivClient, 401), (HoloHttpClient, 429), (GladiaHttpClient, 500), (LinkupHttpClient, 503),
])
async def test_http_errors_use_engine_fallback(client_type, status):
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda _: httpx.Response(status, json={"error": "indisponible"}),
    )) as http:
        client = client_type(http)
        calls = {
            CodivClient: lambda: client.decide({}, timeout_s=.8),
            HoloHttpClient: lambda: client.localize(menu_png(), "rouge", timeout_s=5),
            GladiaHttpClient: lambda: client.transcribe(silence_wav(), encoding="wav",
                                                       sample_rate=16000, language="fr"),
            LinkupHttpClient: lambda: client.search("tore"),
        }
        metrics = []
        result = await Fallback(record=metrics.append).call("cloud", calls[client_type],
                                                          .8, lambda: "local")
        assert result == "local" and client.statuses == [status]
        assert metrics[-1]["status"] == "fallback"
