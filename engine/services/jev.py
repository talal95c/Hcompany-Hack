"""Client Jev via Codiv System One : décisions typées batchées, HTTP/2 persistant."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping
from typing import Any

import httpx

from engine.services._retry import TokenBucket, hedged
from engine.services.errors import (
    InvalidResponse,
    QuotaExceeded,
    ServiceTimeout,
    ServiceUnavailable,
    error_for_status,
)
from engine.services.latency import LatencyRecorder
from engine.services.profiles import AppProfile, load_profile
from engine.services.protocols import Intent, JevDecision, JevQuestion

SERVICE = "jev"
DEFAULT_BASE_URL = "https://api.codiv.ai"
DEFAULT_MODEL = "openjev-latest"
DEFAULT_TIMEOUT_S = 0.8


def intent_question(profile: AppProfile) -> JevQuestion:
    return JevQuestion(
        type="choice",
        instructions=(
            f"{profile.name}: {profile.jev_context} "
            f"The learner is following a {profile.name} tutorial with a voice tutor. "
            "Classify what the "
            "learner's French utterance asks of the tutor."
        ),
        criteria={
            Intent.QUESTION.value: "asks a question, an explanation or a clarification",
            Intent.FAIS_LE.value: (
                "asks the tutor to perform the action or step for them (fais-le, vas-y, montre-moi "
                "en le faisant)"
            ),
            Intent.FRUSTRATION.value: "expresses frustration, annoyance or discouragement",
            Intent.CHUT.value: "asks the tutor to be quiet, stop talking or pause (chut, tais-toi)",
            Intent.OTHER.value: "anything else: small talk, thinking aloud, unrelated remarks",
        },
    )


def stuck_question(profile: AppProfile) -> JevQuestion:
    return JevQuestion(
        type="choice",
        instructions=(
            f"{profile.name}: {profile.jev_context} "
            f"Given the learner's recent activity in {profile.name}, "
            "decide whether the learner is stuck "
            "and needs help, or is still thinking and should be left alone."
        ),
        criteria={
            "stuck": (
                "repeated failed attempts, aimless navigation or a long idle time after errors"
            ),
            "thinking": "recent progress, deliberate exploration or a short pause",
        },
    )


def deviation_question(profile: AppProfile) -> JevQuestion:
    return JevQuestion(
        type="choice",
        instructions=(
            f"{profile.name}: {profile.jev_context} "
            "The learner deviated from the expected lesson step. Judge how severe the deviation is "
            "for the lesson goal."
        ),
        criteria={
            "none": "no real deviation, equivalent result",
            "minor": "cosmetic or easily recoverable, lesson can continue",
            "major": "blocks the next steps or breaks the expected document/app state",
        },
    )


INTENT_QUESTION = intent_question(load_profile(None))
STUCK_QUESTION = stuck_question(load_profile(None))
DEVIATION_QUESTION = deviation_question(load_profile(None))


class CodivJevClient:
    """JevClient réel sur `POST /v1/systemone`.

    Une seule connexion HTTP/2 réutilisée ; plusieurs questions par requête ; les appels
    spéculatifs puisent dans le même seau que les finals mais sans entamer la réserve.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        profile: AppProfile | None = None,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        rate_per_minute: float = 60,
        speculative_reserve: int = 10,
        recorder: LatencyRecorder | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        key = api_key or os.environ.get("CODIV_API_KEY")
        if not key:
            raise ServiceUnavailable(SERVICE, "CODIV_API_KEY absent")
        self.profile = profile or load_profile(None)
        self.model = model
        self.timeout_s = timeout_s
        self.recorder = recorder or LatencyRecorder()
        self.bucket = TokenBucket(rate_per_minute)
        self.speculative_reserve = speculative_reserve
        self._custom_transport = transport is not None
        self._http = httpx.AsyncClient(
            base_url=base_url,
            http2=transport is None,
            transport=transport,
            headers={"Authorization": f"Bearer {key}"},
            timeout=httpx.Timeout(timeout_s, connect=5.0),
            limits=httpx.Limits(max_keepalive_connections=2, keepalive_expiry=300),
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> CodivJevClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def warm_up(self) -> str:
        """Ouvre la connexion TLS/HTTP2 à l'avance (au démarrage de session)."""
        resp = await self._http.get("/v1/models", timeout=5.0)
        if resp.status_code != 200:
            raise error_for_status(SERVICE, resp.status_code, resp.text)
        return resp.http_version

    async def decide(
        self,
        state: Any,
        questions: Mapping[str, JevQuestion],
        *,
        timeout_s: float | None = None,
        speculative: bool = False,
    ) -> dict[str, JevDecision]:
        """Pose un lot de questions sur un même état ; une décision par question."""
        if not questions:
            raise ValueError("au moins une question")
        if speculative:
            if not self.bucket.try_acquire(reserve=self.speculative_reserve):
                raise QuotaExceeded(SERVICE, "budget spéculatif épuisé")
        else:
            await self.bucket.acquire()
        limit = self.timeout_s if timeout_s is None else timeout_s
        body = {
            "model": self.model,
            "state": state,
            "samples": 1,
            "questions": {qid: q.to_api() for qid, q in questions.items()},
        }
        op = "decide_speculative" if speculative else "decide"
        with self.recorder.measure(SERVICE, op) as ctx:
            attempt_number = 0

            async def post():
                nonlocal attempt_number
                attempt_number += 1
                if attempt_number > 1 and not self.bucket.try_acquire():
                    raise QuotaExceeded(SERVICE, "budget de duplication épuisé")
                if attempt_number > 1 and not self._custom_transport:
                    async with httpx.AsyncClient(
                        base_url=self._http.base_url,
                        headers=self._http.headers,
                        http2=True,
                        timeout=limit,
                    ) as fresh:
                        return await fresh.post("/v1/systemone", json=body)
                return await self._http.post("/v1/systemone", json=body, timeout=limit)

            try:
                resp = await asyncio.wait_for(hedged(post, min(0.375, limit / 2)), timeout=limit)
            except (TimeoutError, httpx.TimeoutException) as exc:
                raise ServiceTimeout(SERVICE, f"décision > {limit * 1000:.0f} ms") from exc
            except httpx.TransportError as exc:
                raise ServiceUnavailable(SERVICE, f"transport: {exc}") from exc
            ctx.request_id = resp.headers.get("x-request-id")
            if resp.status_code != 200:
                raise error_for_status(
                    SERVICE, resp.status_code, resp.text, request_id=ctx.request_id
                )
            try:
                payload = resp.json()
            except ValueError as exc:
                raise InvalidResponse(SERVICE, "JSON invalide", request_id=ctx.request_id) from exc
            ctx.request_id = ctx.request_id or payload.get("id")
            usage = payload.get("usage") or {}
            ctx.input_tokens = usage.get("input_tokens") or usage.get("prompt_tokens")
            ctx.output_tokens = usage.get("output_tokens") or usage.get("completion_tokens")
            return parse_answers(payload, questions, ctx.request_id)

    async def classify_intent(
        self, utterance: str, *, context: str = "", profile: AppProfile | None = None
    ) -> JevDecision:
        state: dict[str, Any] = {"utterance": utterance}
        if context:
            state["lesson_context"] = context
        return (await self.decide(state, {"intent": intent_question(profile or self.profile)}))[
            "intent"
        ]

    async def assess(
        self,
        state: Mapping[str, Any],
        *,
        include_intent: bool = False,
        profile: AppProfile | None = None,
    ) -> dict[str, JevDecision]:
        """Batch blocage + sévérité de déviation (+ intention si un énoncé est présent)."""
        profile = profile or self.profile
        questions = {
            "stuck_or_thinking": stuck_question(profile),
            "deviation": deviation_question(profile),
        }
        if include_intent:
            questions["intent"] = intent_question(profile)
        return await self.decide(dict(state), questions)


def parse_answers(
    payload: Mapping[str, Any], questions: Mapping[str, JevQuestion], request_id: str | None
) -> dict[str, JevDecision]:
    answers = payload.get("answers")
    if not isinstance(answers, Mapping):
        raise InvalidResponse(SERVICE, "champ answers absent", request_id=request_id)
    out: dict[str, JevDecision] = {}
    for qid, question in questions.items():
        ans = answers.get(qid)
        if not isinstance(ans, Mapping) or "choice" not in ans:
            raise InvalidResponse(SERVICE, f"réponse manquante pour {qid}", request_id=request_id)
        choice = str(ans["choice"])
        probs_raw = ans.get("probabilities") or {}
        if not isinstance(probs_raw, Mapping):
            raise InvalidResponse(SERVICE, f"probabilities invalide ({qid})", request_id=request_id)
        probs = {str(k): float(v) for k, v in probs_raw.items()}
        if question.type == "choice" and isinstance(question.criteria, Mapping):
            allowed = set(question.criteria)
            if choice not in allowed:
                raise InvalidResponse(
                    SERVICE, f"choix hors liste {choice!r}", request_id=request_id
                )
        conf = ans.get("confidence")
        out[qid] = JevDecision(
            question_id=qid,
            choice=choice,
            probability=probs.get(choice, float(conf) if conf is not None else 0.0),
            probabilities=probs,
            confidence=float(conf) if conf is not None else None,
            request_id=request_id,
        )
    return out
