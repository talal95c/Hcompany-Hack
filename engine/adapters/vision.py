"""Adaptateur vision seule : capture de la fenêtre et Holo (verdicts et localisation)."""

import json
import math
import time
from collections.abc import Awaitable, Callable
from typing import Any

from engine.adapters.base import Command, Rect, TargetHint
from engine.adapters.profiles import AppProfile
from engine.checks import AppState
from engine.checks.generic import assertion_key
from engine.interfaces import HoloVerifier, VerifyResult

Capture = Callable[[], Awaitable[tuple[dict, bytes] | None]]
VERIFY_PROMPT = (
    "You verify the state of a desktop application from a screenshot of its window. "
    "Answer the closed question strictly from what is visible. Reply yes or no; reply unsure "
    "when the screenshot does not show enough to decide."
)
_VERDICT_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string", "enum": ["yes", "no", "unsure"]}},
    "required": ["answer"],
    "additionalProperties": False,
}


def visual_checks(step: dict) -> list[dict]:
    checks = [step["check"]] + [e["check"] for e in step.get("known_errors", [])]
    return [c["params"] for c in checks if c["name"] == "visual_assert"]


def question(params: dict) -> str:
    text = params["assertion"].strip()
    region = params.get("region")
    if region:
        text += (" (zone de la fenêtre en millièmes : x={x}, y={y}, largeur={w}, "
                 "hauteur={h})").format(**region)
    return text


class HoloAssertVerifier:
    """HoloVerifier réel : une question fermée sur une capture, confiance par logprobs."""

    def __init__(self, client: Any, *, app_context: str = ""):
        self.client = client
        self.app_context = app_context

    async def verify(self, image_png: bytes, assertion: str, *, timeout_s: float,
                     ) -> VerifyResult:
        from engine.services.holo import _png_data_url

        start = time.perf_counter()
        system = VERIFY_PROMPT + (" Application: " + self.app_context if self.app_context else "")
        response = await self.client._complete(
            "verify", timeout_s,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": _png_data_url(image_png)}},
                {"type": "text", "text": assertion},
            ]}],
            max_tokens=16, logprobs=True,
            response_format={"type": "json_schema", "json_schema": {
                "name": "verdict", "schema": _VERDICT_SCHEMA, "strict": True}},
        )
        choice = response.choices[0]
        latency = (time.perf_counter() - start) * 1000
        try:
            answer = json.loads(choice.message.content or "")["answer"]
        except (json.JSONDecodeError, KeyError, TypeError):
            return VerifyResult(None, None, latency, "Réponse illisible")
        confidence = None
        content = getattr(getattr(choice, "logprobs", None), "content", None) or []
        for token in content:
            if token.token.strip(' "') in {"yes", "no", "unsure", "y", "n", "un"}:
                confidence = round(math.exp(token.logprob), 4)
                break
        verdict = {"yes": True, "no": False}.get(answer)
        return VerifyResult(verdict, confidence if verdict is not None else None, latency, answer)


class VisionAdapter:
    sensor = "vision"
    window_scope = True
    mismatch_code = "app_mismatch"

    def __init__(self, app: dict, profile: AppProfile, capture: Capture,
                 verifier: HoloVerifier | None, *, timeout_s: float = 5,
                 metric: Callable[[str, float], None] | None = None):
        self.app, self.profile = app, profile
        self.app_id = app["id"]
        self.shortcut_hint = profile.shortcut_hint
        self.capture, self.verifier, self.timeout_s = capture, verifier, timeout_s
        self.metric = metric or (lambda *_: None)
        self.state = AppState(app_id=self.app_id)
        self.focus: dict | None = None
        self.permission = False

    @property
    def focused(self) -> bool:
        return bool(self.focus) and self.profile.matches(self.focus["app_id"], self.focus["name"])

    def available(self) -> bool:
        return self.permission and self.focused and self.verifier is not None

    def describe_version(self) -> str:
        return "Fenêtre attendue : " + self.profile.name

    def snapshot(self) -> AppState:
        return self.state

    def facts(self) -> dict[str, str | None]:
        return self.state.facts()

    def on_focus(self, payload: dict) -> bool:
        changed = self.focus is None or any(
            self.focus.get(k) != payload.get(k) for k in ("app_id", "window_bounds", "scale"))
        self.focus = payload
        self.state.window_title = payload["window_title"] if self.focused else None
        if not self.focused:
            self.invalidate()
        return changed

    def invalidate(self) -> None:
        self.state.complete = False
        self.state.latest_revision = self.state.revision + 1

    def disconnect(self) -> None:
        self.focus = None
        self.permission = False
        self.invalidate()

    async def refresh(self, step: dict) -> AppState:
        state = self.state
        verdicts: dict[str, VerifyResult] = {}
        params_list = visual_checks(step)
        frame = await self.capture() if params_list and self.focused and self.verifier else None
        if frame is not None:
            _, image = frame
            for params in params_list:
                start = time.perf_counter()
                try:
                    verdict = await self.verifier.verify(image, question(params),
                                                         timeout_s=self.timeout_s)
                except (TimeoutError, ConnectionError, ValueError, RuntimeError) as error:
                    verdict = VerifyResult(None, None, (time.perf_counter() - start) * 1000,
                                           type(error).__name__)
                self.metric("holo.verify", (time.perf_counter() - start) * 1000)
                verdicts[assertion_key(params)] = verdict
        state.verdicts = verdicts
        state.window_title = self.focus["window_title"] if self.focused else None
        state.revision = max(state.revision, state.latest_revision) + 1
        state.latest_revision = state.revision
        state.complete = self.focused
        return state

    def expected_rect(self, step: dict) -> TargetHint | None:
        return None

    def zone(self, step: dict) -> tuple[Command, ...]:
        return ()

    def reveal(self, step: dict) -> tuple[Command, ...]:
        return ()

    def reveal_target(self, step: dict) -> None:
        return None

    def replay(self, step: dict) -> tuple[Command, ...]:
        return ()

    def undo_replay(self, step: dict) -> tuple[Command, ...]:
        return ()


def window_rect(focus: dict | None) -> Rect | None:
    return Rect.from_dict(focus["window_bounds"]) if focus else None
