"""Adaptation des clients cloud aux interfaces du moteur de direct."""

import asyncio
import io
import math
import os
import time
import wave

from engine.config import EngineConfig
from engine.interfaces import JevDecision, LocalizeResult, SearchHit, Transcript


class HoloAdapter:
    def __init__(self, client):
        self.client = client

    async def localize(self, image_png, description, *, timeout_s):
        start = time.perf_counter()
        if not hasattr(self.client, "locate_detailed"):
            x, y, confidence = await asyncio.wait_for(
                self.client.locate(image_png, description), timeout_s)
            return LocalizeResult(round(x), round(y),
                                  confidence if math.isfinite(confidence) else None,
                                  (time.perf_counter() - start) * 1000)
        point = await asyncio.wait_for(
            self.client.locate_detailed(image_png, description), timeout_s)
        return LocalizeResult(round(point.x), round(point.y),
                              point.confidence if math.isfinite(point.confidence) else None,
                              (time.perf_counter() - start) * 1000, point.target_visible)

    async def aclose(self):
        await self.client.aclose()


class JevAdapter:
    def __init__(self, client):
        self.client = client

    async def decide(self, context, *, timeout_s):
        from engine.services.protocols import JevQuestion

        start = time.perf_counter()
        if "utterance" in context:
            result = await asyncio.wait_for(self.client.classify_intent(
                context["utterance"], context=context.get("instruction", "")), timeout_s)
        else:
            criteria = {"intervene": "The learner needs help now",
                        "wait": "Recent progress; let the learner think"}
            criteria.update({"error_code:" + code: code
                             for code in context.get("known_errors", [])})
            result = (await self.client.decide(context, {"action": JevQuestion(
                "choice", "Choose whether to help the Blender learner", criteria)},
                timeout_s=timeout_s))["action"]
        return JevDecision(result.choice, None, (time.perf_counter() - start) * 1000)

    async def aclose(self):
        await self.client.aclose()


class SttAdapter:
    def __init__(self, client):
        self.client = client

    async def open_live(self, **config):
        return await self.client.open_live(**config)

    async def transcribe(self, audio, *, encoding, sample_rate, language):
        start = time.perf_counter()
        if encoding == "pcm_s16le":
            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(sample_rate)
                output.writeframes(audio)
            audio = buffer.getvalue()
        elif encoding != "wav":
            raise ValueError("Encodage STT non pris en charge")
        result = await self.client.transcribe_file(audio, filename="utterance.wav",
                                                   language=language)
        return Transcript(result.text, (time.perf_counter() - start) * 1000)

    async def aclose(self):
        await self.client.aclose()


class SearchAdapter:
    def __init__(self, client):
        self.client = client

    async def search(self, query, *, depth="standard"):
        result = await self.client.search(query, depth=depth)
        return [SearchHit(s.name, s.url, s.snippet) for s in result.sources]

    async def aclose(self):
        await self.client.aclose()


def build_clients(config: EngineConfig) -> dict:
    clients = {}
    if os.getenv("HAI_API_KEY"):
        from engine.services.holo import HoloCloudClient

        clients["holo"] = HoloAdapter(HoloCloudClient(model=config.holo_model))
    if os.getenv("CODIV_API_KEY"):
        from engine.services.jev import CodivJevClient

        clients["jev"] = JevAdapter(CodivJevClient())
    if os.getenv("GLADIA_API_KEY"):
        from engine.services.gladia import GladiaSttClient

        clients["stt"] = SttAdapter(GladiaSttClient())
    if os.getenv("LINKUP_API_KEY"):
        from engine.services.linkup import LinkupSearchClient

        clients["search"] = SearchAdapter(LinkupSearchClient())
    return clients
