"""Types et Protocols des services cloud consommés par l'engine.

engine/interfaces.py n'existe pas encore sur dev : les noms ci-dessous sont ceux attendus
(HoloClient, JevClient, SttClient, SearchClient) et seront réexportés depuis là.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal, Protocol, runtime_checkable

NORMALIZED_MAX = 1000


@dataclass(frozen=True, slots=True)
class Region:
    """Zone d'une capture en coordonnées normalisées [0, 1000] de l'image complète."""

    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self) -> None:
        coords = (self.x0, self.y0, self.x1, self.y1)
        if not all(0 <= c <= NORMALIZED_MAX for c in coords):
            raise ValueError("Region hors bornes [0, 1000]")
        if self.x1 <= self.x0 or self.y1 <= self.y0:
            raise ValueError("Region vide")

    def to_full(self, x: float, y: float) -> tuple[float, float]:
        """Point normalisé dans la région recadrée → point normalisé de la capture complète."""
        return (
            self.x0 + x * (self.x1 - self.x0) / NORMALIZED_MAX,
            self.y0 + y * (self.y1 - self.y0) / NORMALIZED_MAX,
        )


@dataclass(frozen=True, slots=True)
class Location:
    x: float
    y: float
    confidence: float
    request_id: str | None = None

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.confidence)

    def pointer_payload(self, capture_id: str, ui_revision: int) -> dict[str, Any]:
        """Payload de l'ordre `pointer` (contracts/commands.schema.json)."""
        return {"capture_id": capture_id, "ui_revision": ui_revision, "x": self.x, "y": self.y}


ActionType = Literal["click", "type", "key", "done"]


@dataclass(frozen=True, slots=True)
class HoloAction:
    """Une action structurée proposée par Holo pour un tour de computer use."""

    type: ActionType
    x: float | None = None
    y: float | None = None
    text: str | None = None
    keys: tuple[str, ...] = ()
    button: Literal["left", "right", "middle"] = "left"
    reason: str | None = None
    request_id: str | None = None

    def native(self) -> dict[str, Any]:
        """Objet `payload.action` de l'ordre `input.action` (sans champ None)."""
        if self.type == "click":
            return {"type": "click", "x": self.x, "y": self.y, "button": self.button}
        if self.type == "type":
            return {"type": "type", "text": self.text}
        if self.type == "key":
            return {"type": "key", "keys": list(self.keys)}
        raise ValueError("`done` n'est pas une action native")

    def input_action_payload(self, capture_id: str, consent_token: str) -> dict[str, Any]:
        return {"action": self.native(), "consent_token": consent_token, "capture_id": capture_id}


@dataclass(frozen=True, slots=True)
class ActTurn:
    """Historique d'un tour déjà exécuté, renvoyé à Holo comme contexte."""

    action: HoloAction
    outcome: str = "executed"


class Intent(StrEnum):
    QUESTION = "question"
    FAIS_LE = "fais_le"
    FRUSTRATION = "frustration"
    CHUT = "chut"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class JevDecision:
    """Choix retenu par Jev et sa probabilité, plus la distribution complète."""

    question_id: str
    choice: str
    probability: float
    probabilities: Mapping[str, float]
    confidence: float | None = None
    request_id: str | None = None


@dataclass(frozen=True, slots=True)
class JevQuestion:
    """Question typée Codiv System One : choice, noul ou score."""

    type: Literal["choice", "noul", "score"]
    instructions: str
    criteria: Mapping[str, str | None] | Sequence[str] | None = None

    def to_api(self) -> dict[str, Any]:
        body: dict[str, Any] = {"type": self.type, "instructions": self.instructions}
        if self.criteria is not None:
            body["criteria"] = (
                dict(self.criteria) if isinstance(self.criteria, Mapping) else list(self.criteria)
            )
        return body


@dataclass(frozen=True, slots=True)
class Word:
    word: str
    start: float
    end: float
    confidence: float


@dataclass(frozen=True, slots=True)
class Transcript:
    text: str
    words: tuple[Word, ...]
    language: str | None = None
    job_id: str | None = None
    duration_s: float | None = None


SttEventKind = Literal["partial", "final", "speech_start", "speech_end", "ended", "error"]


@dataclass(frozen=True, slots=True)
class SttEvent:
    kind: SttEventKind
    utterance_id: str | None = None
    text: str = ""
    words: tuple[Word, ...] = ()
    start: float | None = None
    end: float | None = None
    language: str | None = None
    received_at: float = 0.0
    raw_type: str | None = None


@dataclass(frozen=True, slots=True)
class SearchSource:
    name: str
    url: str
    snippet: str = ""


@dataclass(frozen=True, slots=True)
class SearchResult:
    """Résultat Linkup : candidat non fiable tant qu'il n'est pas prouvé en sandbox."""

    query: str
    data: Mapping[str, Any] | None
    answer: str | None
    sources: tuple[SearchSource, ...] = field(default_factory=tuple)


@runtime_checkable
class HoloClient(Protocol):
    async def locate(
        self, image_png: bytes, target_description: str, *, region: Region | None = None
    ) -> tuple[float, float, float]: ...

    async def act(
        self,
        image_png: bytes,
        goal: str,
        *,
        lesson_context: str = "",
        history: Sequence[ActTurn] = (),
    ) -> HoloAction: ...


@runtime_checkable
class JevClient(Protocol):
    async def decide(
        self, state: Any, questions: Mapping[str, JevQuestion], *, timeout_s: float | None = None
    ) -> dict[str, JevDecision]: ...

    async def classify_intent(self, utterance: str, *, context: str = "") -> JevDecision: ...


@runtime_checkable
class SttSession(Protocol):
    async def send_audio(self, chunk: bytes) -> None: ...

    async def stop(self) -> None: ...

    def events(self) -> AsyncIterator[SttEvent]: ...


@runtime_checkable
class SttClient(Protocol):
    async def transcribe_file(
        self, audio: bytes, *, filename: str, vocabulary: Sequence[str] = (), language: str = "fr"
    ) -> Transcript: ...


@runtime_checkable
class SearchClient(Protocol):
    async def search(
        self,
        query: str,
        *,
        schema: Mapping[str, Any] | None = None,
        domains: Sequence[str] = (),
        depth: str = "standard",
    ) -> SearchResult: ...
