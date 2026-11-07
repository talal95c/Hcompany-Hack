"""Holo pour le rejeu générique : computer use (une action par tour) et jugement visuel."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import time
from collections.abc import Sequence
from typing import Any

from openai import RateLimitError

from engine.services.errors import QuotaExceeded
from engine.services.holo import HoloCloudClient
from engine.services.protocols import ActTurn, HoloAction

VISUAL_SYSTEM_PROMPT = (
    "You verify the state of a desktop application on a screenshot. The user asks one "
    "closed yes/no question. Judge only what is visible; if it cannot be seen, answer unsure. "
    'Answer as JSON {"answer": "yes"|"no"|"unsure", "confidence": number 0-1, '
    '"evidence": short string}.'
)
_VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string", "enum": ["yes", "no", "unsure"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "evidence": {"type": "string"},
    },
    "required": ["answer", "confidence", "evidence"],
    "additionalProperties": False,
}


class HoloDesktopAgent:
    """Client Holo réel ; pause minimale entre appels pour respecter le quota."""

    def __init__(
        self,
        *,
        model: str = "holo4-35b-a3b",
        act_timeout_s: float = 45,
        min_interval_s: float = 2.1,
    ) -> None:
        if not os.environ.get("HAI_API_KEY"):
            raise RuntimeError("Clé Holo absente")
        self.model = model
        self.client = HoloCloudClient(model=model, act_timeout_s=act_timeout_s)
        self.min_interval_s = min_interval_s
        self.metrics: list[dict[str, Any]] = []
        self._last = 0.0

    async def __aenter__(self) -> HoloDesktopAgent:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.client.aclose()

    async def _pace(self) -> None:
        delay = self._last + self.min_interval_s - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
        self._last = time.monotonic()

    async def _quota_retry(self, operation: str, call: Any) -> Any:
        """Réessaie un 429 (quota partagé) avec attente croissante, borné à 3 essais."""
        for attempt, delay in enumerate((5.0, 15.0, 0.0)):
            try:
                return await call()
            except (RateLimitError, QuotaExceeded) as exc:
                if not delay or "402" in str(exc):
                    raise
                self.metrics.append({"operation": f"{operation}_rate_limited", "attempt": attempt})
                await asyncio.sleep(delay)
                self._last = time.monotonic()
        raise AssertionError("inaccessible")

    async def act(
        self,
        image_png: bytes,
        goal: str,
        *,
        lesson_context: str = "",
        history: Sequence[ActTurn] = (),
    ) -> HoloAction:
        await self._pace()
        started = time.perf_counter()
        try:
            return await self._quota_retry(
                "act",
                lambda: self.client.act(
                    image_png, goal, lesson_context=lesson_context, history=history
                ),
            )
        finally:
            self.metrics.append(
                {"operation": "act", "model": self.model, "duration": time.perf_counter() - started}
            )

    async def assert_visual(
        self, image_png: bytes, assertion: str, *, region: dict | None = None
    ) -> dict[str, Any]:
        await self._pace()
        question = assertion.strip()
        if region:
            question += (
                f"\nLook only at the region x={region['x']}, y={region['y']}, "
                f"w={region['w']}, h={region['h']} (thousandths of the image)."
            )
        url = "data:image/png;base64," + base64.b64encode(image_png).decode()
        started = time.perf_counter()
        try:
            response = await self._quota_retry(
                "visual_assert",
                lambda: asyncio.wait_for(
                    self.client._client.chat.completions.create(
                        model=self.model,
                        temperature=0,
                        max_tokens=160,
                        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
                        messages=[
                            {"role": "system", "content": VISUAL_SYSTEM_PROMPT},
                            {
                                "role": "user",
                                "content": [
                                    {"type": "image_url", "image_url": {"url": url}},
                                    {"type": "text", "text": question},
                                ],
                            },
                        ],
                        response_format={
                            "type": "json_schema",
                            "json_schema": {
                                "name": "verdict",
                                "schema": _VERDICT_SCHEMA,
                                "strict": True,
                            },
                        },
                    ),
                    45,
                ),
            )
        finally:
            self.metrics.append(
                {
                    "operation": "visual_assert",
                    "model": self.model,
                    "duration": time.perf_counter() - started,
                }
            )
        try:
            verdict = json.loads(response.choices[0].message.content or "")
        except json.JSONDecodeError:
            return {"answer": "unsure", "confidence": 0.0, "evidence": "réponse non JSON"}
        if verdict.get("answer") not in {"yes", "no", "unsure"}:
            return {"answer": "unsure", "confidence": 0.0, "evidence": "réponse hors contrat"}
        return {
            "answer": verdict["answer"],
            "confidence": float(verdict.get("confidence", 0)),
            "evidence": str(verdict.get("evidence", ""))[:300],
            "request_id": response.id,
        }
