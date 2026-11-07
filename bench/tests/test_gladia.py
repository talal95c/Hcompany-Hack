import json
import struct

import httpx
import pytest
from websockets.asyncio.server import serve

from bench.common import ROOT
from bench.gladia import (
    audio,
    chunks,
    errors,
    normalize,
    parse_message,
    session,
    speech_onset,
    stream,
)


def transcript(final: bool, text: str = "Bonjour") -> str:
    return json.dumps(
        {
            "type": "transcript",
            "data": {"id": "one", "is_final": final, "utterance": {"text": text}},
        }
    )


def test_error_math() -> None:
    assert normalize("L’EXTRUDE, ça marche !") == "l extrude ça marche"
    assert errors("Salut !", "salut")["wer"] == 0
    assert errors("un cube bleu", "un cube rouge")["wer"] == 1 / 3
    assert errors("un cube", "un beau cube")["wer"] == 0.5
    assert errors("un cube", "cube")["wer"] == 0.5
    assert errors("abc", "adc")["cer"] == 1 / 3
    assert errors("", "")["wer"] == 0
    assert errors("", "bonjour")["wer"] is None


@pytest.mark.parametrize(
    "raw",
    ["", "not json", "[]", "{}", '{"type":"transcript"}', '{"type":"transcript","data":null}'],
)
def test_invalid_message(raw: str) -> None:
    assert parse_message(raw) is None


def test_message_and_chunks() -> None:
    assert parse_message(transcript(False))["is_final"] is False
    assert parse_message(transcript(True))["text"] == "Bonjour"
    assert parse_message('{"type":"end_session"}')["type"] == "end_session"
    assert parse_message('{"type":"error"}')["error"]
    pcm = b"\0" * 6400 + struct.pack("<h", 1000)
    blocks = chunks(pcm)
    assert [offset for offset, _ in blocks] == [0, 0.1, 0.2]
    assert [len(block) for _, block in blocks] == [3200, 3200, 2]
    assert b"".join(block for _, block in blocks) == pcm
    assert speech_onset(pcm) == 0.2
    assert speech_onset(b"\0" * 3200) is None
    assert chunks(b"") == []
    with pytest.raises(ValueError):
        chunks(b"x")
    for row in json.loads((ROOT / "bench/data/gladia_references.json").read_text()):
        assert len(audio(row)) > 32000


async def test_stream_nominal() -> None:
    async def handler(socket) -> None:
        assert len(await socket.recv()) == 3200
        await socket.send(transcript(False))
        assert len(await socket.recv()) == 3200
        assert json.loads(await socket.recv())["type"] == "stop_recording"
        await socket.send(transcript(True))
        await socket.send(transcript(True))
        await socket.send('{"type":"end_session"}')

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        result = await stream(f"ws://127.0.0.1:{port}", struct.pack("<h", 1000) * 3200, 2)
    assert result["transcript"] == "Bonjour"
    assert result["first_audio_to_partial_ms"] is not None
    assert result["audio_end_to_final_ms"] > 0
    sends = result["chunks"]
    assert sends[1]["sent_monotonic_s"] - sends[0]["sent_monotonic_s"] >= 0.09


async def test_silent_socket_timeout() -> None:
    async def handler(socket) -> None:
        await socket.wait_closed()

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        with pytest.raises(TimeoutError):
            await stream(f"ws://127.0.0.1:{port}", b"\0" * 3200, 0.15)


@pytest.mark.live
async def test_gladia_live() -> None:
    row = json.loads((ROOT / "bench/data/gladia_references.json").read_text())[1]
    async with httpx.AsyncClient(timeout=30) as http:
        result = await session(http, row, 30)
    print(
        "Gladia live:",
        result["transcript"],
        "audio_seconds:",
        result["audio_seconds"],
        "partial_ms:",
        result["first_audio_to_partial_ms"],
    )
    assert result["transcript"]
    assert result["audio_end_to_session_end_ms"] is not None
