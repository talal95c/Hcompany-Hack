"""Client Holo (H Company, API OpenAI-compatible) : localisation et computer use."""

from __future__ import annotations

import asyncio
import base64
import json
import math
import os
from collections.abc import Sequence
from typing import Any

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
)

from engine.services._retry import with_retry
from engine.services.errors import (
    InvalidResponse,
    ServiceError,
    ServiceTimeout,
    ServiceUnavailable,
    error_for_status,
)
from engine.services.latency import LatencyRecorder
from engine.services.protocols import (
    NORMALIZED_MAX,
    ActTurn,
    HoloAction,
    Location,
    Region,
)

SERVICE = "holo"
DEFAULT_BASE_URL = "https://api.hcompany.ai/v1"
DEFAULT_MODEL = "holo4-35b-a3b"

# Préfixes système stables : ne pas les formater par requête, le cache de prompt en dépend.
LOCATE_SYSTEM_PROMPT = (
    "You localize user-interface elements in screenshots of desktop applications. "
    "The user gives one screenshot and a description of a single target element. "
    'Answer as JSON {"x": int, "y": int, "visible": bool}. '
    "Set visible=false and x=y=0 if the exact target is not visible. Never guess. "
    "Otherwise return its center, coordinates normalized to 0-1000 on the image."
)
ACT_SYSTEM_PROMPT = (
    "You operate a desktop application for a learner, one action per turn. "
    "You receive the goal, the lesson context, the actions already executed and a fresh "
    "screenshot. Call exactly one tool: click (x, y normalized 0-1000 on the screenshot), "
    'type (text into the focused field) or key (a shortcut such as ["shift", "a"]). '
    "Call done when the goal is visibly reached. Never invent elements that are not visible."
)

_POINT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "x": {"type": "integer", "minimum": 0, "maximum": NORMALIZED_MAX},
        "y": {"type": "integer", "minimum": 0, "maximum": NORMALIZED_MAX},
        "visible": {"type": "boolean"},
    },
    "required": ["x", "y", "visible"],
    "additionalProperties": False,
}

ACT_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "click",
            "description": "Click at a point of the screenshot, coordinates normalized 0-1000.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "minimum": 0, "maximum": NORMALIZED_MAX},
                    "y": {"type": "integer", "minimum": 0, "maximum": NORMALIZED_MAX},
                    "button": {"type": "string", "enum": ["left", "right", "middle"]},
                    "reason": {"type": "string"},
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type",
            "description": "Type text into the focused field.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}, "reason": {"type": "string"}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "key",
            "description": 'Press a key or a chord, e.g. ["shift", "a"] or ["tab"].',
            "parameters": {
                "type": "object",
                "properties": {
                    "keys": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                    "reason": {"type": "string"},
                },
                "required": ["keys"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "done",
            "description": "The goal is visibly reached; no further action.",
            "parameters": {
                "type": "object",
                "properties": {"reason": {"type": "string"}},
            },
        },
    },
]
ALLOWED_KEYS = frozenset(
    {"shift", "ctrl", "alt", "cmd", "tab", "enter", "escape", "space", "backspace", "delete"}
    | {"up", "down", "left", "right", "home", "end", "pageup", "pagedown"}
    | {f"f{i}" for i in range(1, 13)}
    | set("abcdefghijklmnopqrstuvwxyz0123456789")
    | {"numpad0", "numpad1", "numpad3", "numpad7", "numpad_period", "minus", "plus"}
)


def _png_data_url(image_png: bytes) -> str:
    if not image_png.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("image_png doit être un PNG")
    return "data:image/png;base64," + base64.b64encode(image_png).decode()


def _check_point(x: Any, y: Any, request_id: str | None) -> tuple[float, float]:
    try:
        fx, fy = float(x), float(y)
    except (TypeError, ValueError) as exc:
        raise InvalidResponse(SERVICE, f"coordonnées non numériques {x!r},{y!r}") from exc
    if not (0 <= fx <= NORMALIZED_MAX and 0 <= fy <= NORMALIZED_MAX):
        raise InvalidResponse(SERVICE, f"point hors bornes ({fx}, {fy})", request_id=request_id)
    return fx, fy


def _confidence(choice: Any) -> float:
    """Moyenne géométrique des probabilités des tokens numériques (logprobs), sinon NaN."""
    logprobs = getattr(choice, "logprobs", None)
    content = getattr(logprobs, "content", None) if logprobs else None
    if not content:
        return math.nan
    digits = [t.logprob for t in content if any(ch.isdigit() for ch in t.token)]
    if not digits:
        return math.nan
    return round(math.exp(sum(digits) / len(digits)), 4)


class HoloCloudClient:
    """HoloClient réel : un appel par localisation, une action par tour de computer use."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        locate_timeout_s: float = 5.0,
        act_timeout_s: float = 10.0,
        recorder: LatencyRecorder | None = None,
        client: AsyncOpenAI | None = None,
    ) -> None:
        key = api_key or os.environ.get("HAI_API_KEY")
        if client is None and not key:
            raise ServiceUnavailable(SERVICE, "HAI_API_KEY absent")
        self.model = model
        self.locate_timeout_s = locate_timeout_s
        self.act_timeout_s = act_timeout_s
        self.recorder = recorder or LatencyRecorder()
        self._client = client or AsyncOpenAI(api_key=key, base_url=base_url, max_retries=0)

    async def aclose(self) -> None:
        await self._client.close()

    async def __aenter__(self) -> HoloCloudClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def _complete(self, operation: str, timeout_s: float, **kwargs: Any) -> Any:
        with self.recorder.measure(SERVICE, operation) as ctx:
            try:
                resp = await asyncio.wait_for(
                    self._client.chat.completions.create(
                        model=self.model,
                        temperature=0,
                        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
                        timeout=timeout_s,
                        **kwargs,
                    ),
                    timeout=timeout_s,
                )
            except (TimeoutError, APITimeoutError) as exc:
                raise ServiceTimeout(SERVICE, f"{operation} > {timeout_s}s") from exc
            except APIStatusError as exc:
                rid = exc.response.headers.get("x-request-id") if exc.response else None
                raise error_for_status(SERVICE, exc.status_code, str(exc), request_id=rid) from exc
            except APIConnectionError as exc:
                raise ServiceUnavailable(SERVICE, f"connexion: {exc}") from exc
            ctx.request_id = resp.id
            usage = resp.usage
            if usage is not None:
                ctx.input_tokens = usage.prompt_tokens
                ctx.output_tokens = usage.completion_tokens
                details = getattr(usage, "prompt_tokens_details", None)
                ctx.cached_tokens = getattr(details, "cached_tokens", None) if details else None
            if not resp.choices:
                raise InvalidResponse(SERVICE, "aucun choix", request_id=resp.id)
            return resp

    async def locate_detailed(
        self, image_png: bytes, target_description: str, *, region: Region | None = None
    ) -> Location:
        """Localise une cible sur une capture (éventuellement recadrée sur `region`).

        Les coordonnées renvoyées sont normalisées [0, 1000] sur la capture complète.
        """
        if not target_description.strip():
            raise ValueError("description de cible vide")
        messages = [
            {"role": "system", "content": LOCATE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": _png_data_url(image_png)}},
                    {"type": "text", "text": target_description.strip()},
                ],
            },
        ]

        async def call() -> Location:
            resp = await self._complete(
                "locate",
                self.locate_timeout_s,
                messages=messages,
                max_tokens=32,
                logprobs=True,
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "point", "schema": _POINT_SCHEMA, "strict": True},
                },
            )
            choice = resp.choices[0]
            try:
                point = json.loads(choice.message.content or "")
            except json.JSONDecodeError as exc:
                raise InvalidResponse(SERVICE, "JSON invalide", request_id=resp.id) from exc
            if not isinstance(point, dict):
                raise InvalidResponse(SERVICE, "point non objet", request_id=resp.id)
            x, y = _check_point(point.get("x"), point.get("y"), resp.id)
            if region is not None:
                x, y = region.to_full(x, y)
            return Location(x=x, y=y, confidence=_confidence(choice), request_id=resp.id,
                            target_visible=point.get("visible"))

        return await with_retry(call, attempts=2)

    async def locate(
        self, image_png: bytes, target_description: str, *, region: Region | None = None
    ) -> tuple[float, float, float]:
        return (await self.locate_detailed(image_png, target_description, region=region)).as_tuple()

    async def act(
        self,
        image_png: bytes,
        goal: str,
        *,
        lesson_context: str = "",
        history: Sequence[ActTurn] = (),
    ) -> HoloAction:
        """Un tour de computer use : capture fraîche → une action validée (jamais rejouée)."""
        done = "\n".join(
            f"{i + 1}. {json.dumps(_history_entry(t.action))} -> {t.outcome}"
            for i, t in enumerate(history)
        )
        text = f"Goal: {goal.strip()}\nLesson context: {lesson_context.strip() or '-'}\n"
        text += f"Actions already executed:\n{done or '-'}"
        messages = [
            {"role": "system", "content": ACT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": text},
                    {"type": "image_url", "image_url": {"url": _png_data_url(image_png)}},
                ],
            },
        ]
        resp = await self._complete(
            "act",
            self.act_timeout_s,
            messages=messages,
            tools=ACT_TOOLS,
            tool_choice="required",
            max_tokens=256,
        )
        return parse_tool_action(resp.choices[0].message, resp.id)


def _history_entry(action: HoloAction) -> dict[str, Any]:
    return {"type": "done"} if action.type == "done" else action.native()


def parse_tool_action(message: Any, request_id: str | None = None) -> HoloAction:
    calls = getattr(message, "tool_calls", None) or []
    if len(calls) != 1:
        raise InvalidResponse(SERVICE, f"{len(calls)} appels d'outil", request_id=request_id)
    fn = calls[0].function
    try:
        args = json.loads(fn.arguments or "{}")
    except json.JSONDecodeError as exc:
        raise InvalidResponse(SERVICE, "arguments JSON invalides", request_id=request_id) from exc
    reason = args.get("reason")
    if fn.name == "click":
        x, y = _check_point(args.get("x"), args.get("y"), request_id)
        button = args.get("button", "left")
        if button not in ("left", "right", "middle"):
            raise InvalidResponse(SERVICE, f"bouton {button!r}", request_id=request_id)
        return HoloAction("click", x=x, y=y, button=button, reason=reason, request_id=request_id)
    if fn.name == "type":
        text = args.get("text")
        if not isinstance(text, str) or not text:
            raise InvalidResponse(SERVICE, "texte vide", request_id=request_id)
        return HoloAction("type", text=text, reason=reason, request_id=request_id)
    if fn.name == "key":
        keys = args.get("keys")
        if isinstance(keys, str):
            keys = [k for k in keys.replace("+", " ").split() if k]
        if not isinstance(keys, list) or not keys:
            raise InvalidResponse(SERVICE, "touches absentes", request_id=request_id)
        norm = tuple(str(k).strip().lower() for k in keys)
        bad = [k for k in norm if k not in ALLOWED_KEYS]
        if bad:
            raise InvalidResponse(SERVICE, f"touches non autorisées {bad}", request_id=request_id)
        return HoloAction("key", keys=norm, reason=reason, request_id=request_id)
    if fn.name == "done":
        return HoloAction("done", reason=reason, request_id=request_id)
    raise InvalidResponse(SERVICE, f"outil inconnu {fn.name!r}", request_id=request_id)


__all__ = [
    "ACT_TOOLS",
    "HoloCloudClient",
    "ServiceError",
    "parse_tool_action",
]
