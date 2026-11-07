"""Clients de recette cloud, indépendants des adaptateurs de production."""

import asyncio
import base64
import binascii
import io
import json
import struct
import time
import wave
import zlib

import httpx

from engine.interfaces import JevDecision, LocalizeResult, SearchHit, Transcript


def menu_png() -> bytes:
    width, height = 320, 160
    rows = []
    for y in range(height):
        row = bytearray(b"\0")
        for x in range(width):
            color = (210, 35, 35) if 40 <= x < 280 and 80 <= y < 120 else (
                (70, 75, 85) if 40 <= x < 280 and 30 <= y < 70 else (30, 32, 38)
            )
            row.extend(color)
        rows.append(bytes(row))

    def chunk(name: bytes, body: bytes) -> bytes:
        return struct.pack("!I", len(body)) + name + body + struct.pack(
            "!I", binascii.crc32(name + body) & 0xffffffff,
        )

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack("!IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b""))


def silence_wav() -> bytes:
    stream = io.BytesIO()
    with wave.open(stream, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\0\0" * 16000)
    return stream.getvalue()


class HttpClient:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self.attempts = 0
        self.statuses: list[int] = []

    async def request(self, method: str, url: str, **kwargs) -> dict:
        self.attempts += 1
        response = await self.client.request(method, url, **kwargs)
        self.statuses.append(response.status_code)
        response.raise_for_status()
        return response.json()


class CodivClient(HttpClient):
    model = "openjev-latest"

    async def discover(self) -> list[str]:
        data = await self.request("GET", "https://api.codiv.ai/v1/models")
        models = [m.get("name", m.get("id")) for m in data.get("models", data.get("data", []))]
        if self.model not in models:
            raise ValueError("Modèle Jev absent")
        return models

    async def decide(self, context: dict, *, timeout_s: float) -> JevDecision:
        start = time.perf_counter()
        data = await self.request("POST", "https://api.codiv.ai/v1/systemone", timeout=timeout_s,
                                  json={"model": self.model, "state": json.dumps(context),
                                        "questions": {"action": {
                                            "type": "choice",
                                            "instructions": "Faut-il aider l'apprenant bloqué ?",
                                            "criteria": {"intervene": "Blocage sans progrès",
                                                         "wait": "Progrès récent pertinent"},
                                        }}})
        action = data["answers"]["action"]["choice"]
        if action not in {"intervene", "wait"}:
            raise ValueError("Décision Jev invalide")
        return JevDecision(action, None, (time.perf_counter() - start) * 1000)


class HoloHttpClient(HttpClient):
    async def localize(
        self, image_png: bytes, description: str, *, timeout_s: float,
    ) -> LocalizeResult | None:
        start = time.perf_counter()
        schema = {"type": "object", "properties": {
            axis: {"type": "integer", "minimum": 0, "maximum": 1000} for axis in ("x", "y")
        }, "required": ["x", "y"], "additionalProperties": False}
        data = await self.request("POST", "https://api.hcompany.ai/v1/chat/completions",
                                  timeout=timeout_s, json={
                                      "model": "holo4-35b-a3b", "temperature": 0,
                                      "max_tokens": 128,
                                      "structured_outputs": {"json": schema},
                                      "chat_template_kwargs": {"enable_thinking": False},
                                      "messages": [{"role": "user", "content": [
                                          {"type": "text", "text": (
                                              "Locate the center of " + description
                                              + '. Return only JSON {"x": integer, "y": integer}'
                                              + " in normalized coordinates 0..1000."
                                          )},
                                          {"type": "image_url", "image_url": {
                                              "url": "data:image/png;base64,"
                                              + base64.b64encode(image_png).decode(),
                                          }},
                                      ]}],
                                  })
        content = data["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0]
        point = json.loads(content)
        x, y = point["x"], point["y"]
        if type(x) is not int or type(y) is not int:
            raise ValueError("Point non entier")
        return LocalizeResult(x, y, None, (time.perf_counter() - start) * 1000)


class GladiaHttpClient(HttpClient):
    async def transcribe(
        self, audio: bytes, *, encoding: str, sample_rate: int, language: str,
    ) -> Transcript:
        if encoding != "wav" or sample_rate != 16000:
            raise ValueError("Recette WAV 16 kHz requise")
        start = time.perf_counter()
        upload = await self.request("POST", "https://api.gladia.io/v2/upload",
                                    files={"audio": ("silence.wav", audio, "audio/wav")})
        job = await self.request("POST", "https://api.gladia.io/v2/pre-recorded", json={
            "audio_url": upload["audio_url"], "language_config": {"languages": [language]},
        })
        job_id = job["id"]
        for _ in range(120):
            result = await self.request("GET", f"https://api.gladia.io/v2/pre-recorded/{job_id}")
            if result["status"] == "done":
                text = result["result"]["transcription"]["full_transcript"]
                if not isinstance(text, str):
                    raise ValueError("Transcription invalide")
                return Transcript(text, (time.perf_counter() - start) * 1000)
            if result["status"] == "error":
                raise ValueError("Transcription échouée")
            await asyncio.sleep(0.5)
        raise TimeoutError("Transcription non terminée")


class LinkupHttpClient(HttpClient):
    async def search(self, query: str, *, depth: str = "standard") -> list[SearchHit]:
        data = await self.request("POST", "https://api.linkup.so/v1/search", json={
            "q": query, "depth": depth, "outputType": "searchResults", "maxResults": 2,
        })
        return [SearchHit(r["name"], r["url"], r["content"]) for r in data["results"]
                if r.get("type", "text") == "text"]
