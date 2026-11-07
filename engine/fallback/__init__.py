"""Délais bornés, règles locales et état de santé sans boucle de requêtes."""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from engine.interfaces import Clock, SttClient, SystemClock, Transcript, TtsClient

T = TypeVar("T")


async def with_fallback(coro: Awaitable[T], timeout: float, rule: Callable[[], T]) -> T:
    try:
        return await asyncio.wait_for(coro, timeout)
    except Exception:
        return rule()


@dataclass
class ServiceHealth:
    consecutive_failures: int = 0
    retry_at: float = 0


class Fallback:
    def __init__(self, clock: Clock | None = None, record: Callable[[dict], None] | None = None):
        self.clock = clock or SystemClock()
        self.record = record or (lambda _: None)
        self.health: dict[str, ServiceHealth] = {}

    async def transcribe(
        self, client: SttClient | None, audio: bytes, *, encoding: str,
        sample_rate: int, language: str, timeout: float = 2,
    ) -> Transcript | None:
        async def invoke() -> Transcript:
            if client is None:
                raise RuntimeError("STT indisponible")
            result = await client.transcribe(
                audio, encoding=encoding, sample_rate=sample_rate, language=language,
            )
            if not result.text.strip():
                raise ValueError("Transcription vide")
            return result

        def keyboard() -> None:
            self.record({"kind": "error", "code": "stt_unavailable",
                         "message": "Transcription indisponible : utilisez le clavier",
                         "retryable": True})

        return await self.call("stt", invoke, timeout, keyboard)

    async def synthesize(
        self, client: TtsClient | None, text: str, *, language: str, timeout: float = 2,
    ) -> bytes | None:
        async def invoke() -> bytes:
            if client is None:
                raise RuntimeError("TTS indisponible")
            data = await client.synthesize(text, language=language)
            if not data:
                raise ValueError("Audio vide")
            return data

        return await self.call("tts", invoke, timeout, lambda: None)

    async def call(
        self, service: str, factory: Callable[[], Awaitable[T]], timeout: float,
        rule: Callable[[], T],
    ) -> T:
        health = self.health.setdefault(service, ServiceHealth())
        start = time.perf_counter()
        status = "backoff"
        try:
            if self.clock.monotonic() < health.retry_at:
                return rule()
            status = "ok"

            def failed() -> T:
                nonlocal status
                status = "fallback"
                health.consecutive_failures += 1
                health.retry_at = self.clock.monotonic() + min(
                    60, 2 ** min(health.consecutive_failures - 1, 6)
                )
                return rule()

            async def invoke() -> T:
                return await factory()

            result = await with_fallback(invoke(), timeout, failed)
            if status == "ok":
                health.consecutive_failures = 0
                health.retry_at = 0
            return result
        except asyncio.CancelledError:
            status = "cancelled"
            raise
        finally:
            self.record({"kind": "latency", "service": service, "status": status,
                         "latency_ms": (time.perf_counter() - start) * 1000})