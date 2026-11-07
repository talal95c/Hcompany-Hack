"""Contrats asynchrones des services injectables."""

import time
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class LocalizeResult:
    x: int
    y: int
    confidence: float | None
    latency_ms: float
    target_visible: bool | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.x <= 1000 or not 0 <= self.y <= 1000:
            raise ValueError("Coordonnées hors limites")


@dataclass(frozen=True)
class JevDecision:
    action: str
    rationale: str | None
    latency_ms: float


@dataclass(frozen=True)
class Transcript:
    text: str
    latency_ms: float


@dataclass(frozen=True)
class SearchHit:
    title: str
    url: str
    snippet: str


@runtime_checkable
class HoloClient(Protocol):
    async def localize(
        self, image_png: bytes, description: str, *, timeout_s: float
    ) -> LocalizeResult | None: ...


@runtime_checkable
class JevClient(Protocol):
    async def decide(self, context: dict, *, timeout_s: float) -> JevDecision: ...


@runtime_checkable
class SttClient(Protocol):
    async def transcribe(
        self, audio: bytes, *, encoding: str, sample_rate: int, language: str
    ) -> Transcript: ...


@runtime_checkable
class TtsClient(Protocol):
    async def synthesize(self, text: str, *, language: str) -> bytes: ...


@runtime_checkable
class SearchClient(Protocol):
    async def search(self, query: str, *, depth: str = "standard") -> list[SearchHit]: ...


@runtime_checkable
class Clock(Protocol):
    def monotonic(self) -> float: ...


class SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()


class FakeClock:
    def __init__(self, initial: float = 0) -> None:
        self.now = initial

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("L'horloge ne peut pas reculer")
        self.now += seconds
