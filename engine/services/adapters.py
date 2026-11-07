"""Adaptation des clients cloud aux interfaces du moteur de direct."""

import asyncio
import io
import json
import math
import os
import time
import wave

from engine.config import EngineConfig
from engine.interfaces import JevDecision, LocalizeResult, SearchHit, Transcript
from engine.pointer import verify_point
from engine.services.profiles import AppProfile, load_profile, profile_for_lesson


class HoloAdapter:
    def __init__(self, client):
        self.client = client

    async def verify_point(self, image_png, description, point, *, timeout_s):
        return await verify_point(self.client, image_png, description, point, timeout_s=timeout_s)

    async def localize(self, image_png, description, *, timeout_s):
        start = time.perf_counter()
        if not hasattr(self.client, "locate_detailed"):
            x, y, confidence = await asyncio.wait_for(
                self.client.locate(image_png, description), timeout_s
            )
            return LocalizeResult(
                round(x),
                round(y),
                confidence if math.isfinite(confidence) else None,
                (time.perf_counter() - start) * 1000,
            )
        point = await asyncio.wait_for(
            self.client.locate_detailed(image_png, description), timeout_s
        )
        return LocalizeResult(
            round(point.x),
            round(point.y),
            point.confidence if math.isfinite(point.confidence) else None,
            (time.perf_counter() - start) * 1000,
            point.target_visible,
        )

    async def aclose(self):
        await self.client.aclose()


class JevAdapter:
    def __init__(self, client, profile: AppProfile | None = None):
        self.client = client
        self.profile = profile or getattr(client, "profile", None) or load_profile(None)

    async def decide(self, context, *, timeout_s):
        from engine.services.protocols import JevQuestion

        start = time.perf_counter()
        if "utterance" in context:
            result = await asyncio.wait_for(
                self.client.classify_intent(
                    context["utterance"],
                    context=context.get("instruction", ""),
                    profile=self.profile,
                ),
                timeout_s,
            )
        else:
            criteria = {
                "intervene": "The learner needs help now",
                "wait": "Recent progress; let the learner think",
            }
            criteria.update(
                {"error_code:" + code: code for code in context.get("known_errors", [])}
            )
            result = (
                await self.client.decide(
                    context,
                    {
                        "action": JevQuestion(
                            "choice",
                            f"Choose whether to help the {self.profile.name} learner. "
                            f"{self.profile.jev_context}",
                            criteria,
                        )
                    },
                    timeout_s=timeout_s,
                )
            )["action"]
        return JevDecision(result.choice, None, (time.perf_counter() - start) * 1000)

    async def aclose(self):
        await self.client.aclose()


class SttAdapter:
    def __init__(self, client, profile: AppProfile | None = None):
        self.client = client
        self.profile = profile or getattr(client, "profile", None) or load_profile(None)

    async def open_live(self, **config):
        config.setdefault("vocabulary", self.profile.vocabulary)
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
        result = await self.client.transcribe_file(
            audio, filename="utterance.wav", language=language, vocabulary=self.profile.vocabulary
        )
        return Transcript(result.text, (time.perf_counter() - start) * 1000)

    async def aclose(self):
        await self.client.aclose()


class SearchAdapter:
    def __init__(self, client, profile: AppProfile | None = None):
        self.client = client
        self.profile = profile or getattr(client, "profile", None) or load_profile(None)

    async def search(self, query, *, depth="standard"):
        result = await self.client.search(query, depth=depth, profile=self.profile)
        return [SearchHit(s.name, s.url, s.snippet) for s in result.sources]

    async def aclose(self):
        await self.client.aclose()


def build_clients(config: EngineConfig, lesson: dict | None = None) -> dict:
    if lesson is None and config.lesson is not None:
        lesson = json.loads(config.lesson.read_text(encoding="utf-8"))
    profile = profile_for_lesson(lesson or {})
    clients = {}
    if os.getenv("HAI_API_KEY"):
        from engine.services.holo import HoloCloudClient

        clients["holo"] = HoloAdapter(HoloCloudClient(model=config.holo_model))
    if os.getenv("CODIV_API_KEY"):
        from engine.services.jev import CodivJevClient

        clients["jev"] = JevAdapter(CodivJevClient(profile=profile), profile=profile)
    if os.getenv("GLADIA_API_KEY"):
        from engine.services.gladia import GladiaSttClient

        clients["stt"] = SttAdapter(GladiaSttClient(profile=profile), profile=profile)
    if os.getenv("LINKUP_API_KEY"):
        from engine.services.linkup import LinkupSearchClient

        clients["search"] = SearchAdapter(LinkupSearchClient(profile=profile), profile=profile)
    return clients
