"""Décisions d'aide déterministes avec escalade prudente et services facultatifs."""

import asyncio
import math
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from typing import Any
from uuid import uuid4

from engine.adapters.base import Command
from engine.adapters.holo import localization_budget
from engine.bus import EventBus, Topic
from engine.bus.validation import validate
from engine.cache import AudioCache, TargetCache, TargetContext, TargetEntry
from engine.checks import CheckResult, evaluate, progress_signature
from engine.config import EngineConfig
from engine.fallback import Fallback
from engine.interfaces import (
    Clock,
    HoloClient,
    JevClient,
    JevDecision,
    LocalizeResult,
    SystemClock,
)


@dataclass(frozen=True)
class Decision:
    kind: str
    reason: str
    level: int
    step_id: str
    generation: int
    t: float


@dataclass(frozen=True)
class HelpContext:
    """Aide préparée par l'adaptateur actif ; la policy ne connaît aucune application."""

    zone: tuple[Command, ...] = ()
    reveal: tuple[Command, ...] = ()
    target: TargetContext | None = None
    capture_id: str | None = None
    image_png: bytes | None = None
    demo: tuple[Command, ...] = ()
    demo_undo: tuple[Command, ...] = ()
    checkpoint_id: str | None = None
    capture_epoch: int = 0
    reveal_target: Callable[[], Awaitable[None]] | None = None
    require_visible: bool = False
    shortcut_hint: str | None = None
    pointer: tuple[int, int] | None = None
    pointer_ref: tuple[str, str] | None = None
    app: str | None = None
    expected_rect: tuple[float, float, float, float] | None = None
    request_demo: Callable[[], Awaitable[None]] | None = None


def inside(rect: tuple[float, float, float, float], x: float, y: float) -> bool:
    left, top, width, height = rect
    return left <= x <= left + width and top <= y <= top + height


class HelpPolicy:
    def __init__(
        self, config: EngineConfig, bus: EventBus, *, clock: Clock | None = None,
        jev: JevClient | None = None, holo: HoloClient | None = None,
        fallback: Fallback | None = None, targets: TargetCache | None = None,
        audio: AudioCache | None = None, debug: Callable[[dict], None] | None = None,
        app_context: dict | None = None,
    ):
        self.config, self.bus = config, bus
        self.clock = clock or SystemClock()
        self.debug = debug or (lambda _: None)
        self.fallback = fallback or Fallback(self.clock, self.debug)
        self.jev, self.holo = jev, holo
        self.targets, self.audio = targets or TargetCache(), audio or AudioCache()
        self.step: dict | None = None
        self.generation = 0
        self.level = 0
        self.muted = False
        self.last_spontaneous = float("-inf")
        self.last_progress = self.clock.monotonic()
        self.signature: str | None = None
        self.undos = 0
        self.deferred: str | None = None
        self.degraded = False
        self.handled_errors: set[str] = set()
        self.passed = False
        self.demo_checkpoint: str | None = None
        self.jev_wait_key: tuple | None = None
        self.jev_wait_until = 0.0
        self.lock = asyncio.Lock()
        self.capture_epoch = 0
        self.intervention_epoch = 0
        self.localization: asyncio.Task | None = None
        self.app_context = app_context
        self.on_stop: Callable[[], None] | None = None
        self.on_resume: Callable[[], None] | None = None

    def cancel_intervention(self, *, invalidate_capture: bool = False) -> None:
        self.intervention_epoch += 1
        if invalidate_capture:
            self.capture_epoch += 1
            self.targets.invalidate()
        if self.localization:
            self.localization.cancel()

    def set_step(self, step: dict, generation: int) -> None:
        self.cancel_intervention()
        self.step, self.generation = step, generation
        self.level, self.undos = 0, 0
        self.last_progress = self.clock.monotonic()
        self.signature, self.deferred = None, None
        self.handled_errors.clear()
        self.passed = False
        self.demo_checkpoint = None
        self.jev_wait_key = None

    async def _decision(self, kind: str, reason: str) -> Decision:
        assert self.step is not None
        decision = Decision(kind, reason, self.level, self.step["id"], self.generation,
                            self.clock.monotonic())
        await self.bus.publish(Topic.DECISION, decision)
        self.debug({**asdict(decision), "kind": "decision", "decision": kind})
        return decision

    async def _command(self, kind: str, payload: dict, *, revision: int = 0,
                       recipient: str = "desktop") -> None:
        assert self.step is not None
        command = {
            "schema_version": "1.0", "session_id": self.config.session_id,
            "command_id": str(uuid4()), "step_id": self.step["id"],
            "generation": self.generation, "recipient": recipient, "type": kind,
            "deadline_ms": 1000, "expected_scene_revision": max(0, revision), "payload": payload,
        }
        validate("commands", command)
        await self.bus.publish(Topic.COMMAND, command)

    async def _emit(self, commands: tuple[Command, ...], *, revision: int = 0) -> None:
        for recipient, kind, payload in commands:
            await self._command(kind, payload, revision=revision, recipient=recipient)

    async def intent(self, text: str, context: HelpContext | None = None) -> Decision | None:
        text = text.strip().casefold()
        if text == "chut":
            if self.on_stop:
                self.on_stop()
            self.muted = True
            self.cancel_intervention()
            if self.step:
                await self._command("stop", {"reason": "Silence demandé"})
            return None
        if text == "reprends":
            if self.on_resume:
                self.on_resume()
            self.muted = False
            return None
        if text in {"aide", "help"} and self.step and not self.passed:
            async with self.lock:
                return await self._help("explicit", self.step.get("why", self.step["instruction"]),
                                        context or HelpContext(), 0)
        if text and self.step and self.jev:
            generation = self.generation
            answer = await self.fallback.call(
                "jev_intent", lambda: self.jev.decide(
                    {"utterance": text, "instruction": self.step["instruction"],
                     **({"app": self.app_context} if self.app_context else {})},
                    timeout_s=self.config.jev_timeout_s), self.config.jev_timeout_s,
                lambda: JevDecision("other", None, 0))
            if generation != self.generation or self.muted:
                return None
            if answer.action == "question":
                await self._command("say", {"text": self.step.get("why", self.step["instruction"]),
                                            "audio_ref": None})
                return await self._decision("why", "intent:question")
            if answer.action == "chut":
                return await self.intent("chut", context)
        return None

    async def process(
        self, state: Any, result: CheckResult, *, event_type: str = "heartbeat",
        undo_count: int = 1, context: HelpContext | None = None,
        can_pass: Callable[[], bool] | None = None,
    ) -> Decision | None:
        async with self.lock:
            if not self.step or self.passed:
                return None
            generation = self.generation
            epoch = self.intervention_epoch
            if result.scene_revision != state.revision or not state.recent:
                return None
            if result.status == "pass":
                if can_pass is not None and not can_pass():
                    return None
                self.passed = True
                await self._command("success", {"text": "Étape réussie"}, revision=state.revision)
                decision = await self._decision("success", "check_pass")
                self.level, self.undos, self.deferred = 0, 0, None
                return decision
            check = self.step["check"]
            signature = progress_signature(check["name"], state, check["params"])
            if self.signature is None or signature != self.signature:
                self.signature = signature
                self.last_progress = self.clock.monotonic()
                self.deferred = None
            if event_type == "undo":
                self.undos += undo_count
            elif event_type not in {"heartbeat", "selection.changed", "regions.changed"}:
                self.undos = 0
            errors = [error for error in self.step.get("known_errors", []) if evaluate(
                error["check"]["name"], state, error["check"]["params"]
            ).status == "pass"]
            active_codes = {e["code"] for e in errors}
            if errors:
                self.debug({"kind": "known_errors", "errors": [
                    {"code": e["code"], "hint": e["hint"]} for e in errors
                ]})
            self.handled_errors.intersection_update(active_codes)
            fresh_errors = [e for e in errors if e["code"] not in self.handled_errors]
            reason = ""
            hint = self.step.get("why", self.step["instruction"])
            if fresh_errors:
                reason, hint = "known_error:" + fresh_errors[0]["code"], fresh_errors[0]["hint"]
            elif self.undos >= self.config.undo_threshold:
                reason = "undos"
            elif self.clock.monotonic() - self.last_progress >= self.config.no_progress_s:
                reason = "no_progress"
            if not reason:
                self.deferred = None
                return None
            if self.muted:
                self.debug({"kind": "muted", "reason": reason})
                return None
            if self.clock.monotonic() - self.last_spontaneous < self.config.cooldown_s:
                self.deferred = reason
                self.debug({"kind": "deferred", "reason": reason})
                return None
            ambiguous = result.status == "unknown" or len(errors) > 1 or (
                reason == "no_progress" and state.has_content
            )
            if ambiguous and self.jev:
                ambiguity_key = (signature, reason, tuple(sorted(active_codes)))
                if (self.jev_wait_key == ambiguity_key
                        and self.clock.monotonic() < self.jev_wait_until):
                    return None

                def local_rule() -> JevDecision:
                    return JevDecision("intervene", "Règle locale", 0)

                async def decide() -> JevDecision:
                    jev_context = {"check_status": result.status, "reason": reason,
                                   "known_errors": sorted(active_codes)}
                    if self.app_context:
                        jev_context["app"] = self.app_context
                    answer = await self.jev.decide(jev_context,
                                                   timeout_s=self.config.jev_timeout_s)
                    if answer.action not in {"intervene", "wait"} | {
                        "error_code:" + code for code in active_codes
                    }:
                        raise ValueError("Décision invalide")
                    return answer

                answer = await self.fallback.call(
                    "jev", decide, self.config.jev_timeout_s, local_rule,
                )
                if (generation != self.generation or epoch != self.intervention_epoch
                        or self.muted):
                    return None
                if self.fallback.health["jev"].consecutive_failures and not self.degraded:
                    self.degraded = True
                    self.debug({"kind": "degraded", "service": "jev"})
                    await self.bus.publish(Topic.DEBUG, {
                        "code": "degraded", "message": "Mode dégradé : règles locales",
                        "retryable": True,
                    })
                if answer.action == "wait":
                    self.jev_wait_key = ambiguity_key
                    self.jev_wait_until = self.clock.monotonic() + self.config.cooldown_s
                    return None
                if answer.action.startswith("error_code:"):
                    code = answer.action.split(":", 1)[1]
                    hint = next(e["hint"] for e in errors if e["code"] == code)
                    reason = "known_error:" + code
            if self.muted or epoch != self.intervention_epoch:
                return None
            decision = await self._help(reason, hint, context or HelpContext(), state.revision)
            if generation != self.generation or epoch != self.intervention_epoch:
                return None
            self.last_spontaneous = self.clock.monotonic()
            self.last_progress = self.clock.monotonic()
            self.undos, self.deferred = 0, None
            if reason.startswith("known_error:"):
                self.handled_errors.add(reason.split(":", 1)[1])
            return decision

    async def _help(
        self, reason: str, hint: str, context: HelpContext, revision: int,
    ) -> Decision | None:
        generation = self.generation
        epoch = self.intervention_epoch
        next_level = min(4, self.level + 1)
        if next_level == 1:
            audio = self.audio.get(hint)
            await self._command("say", {"text": hint, "audio_ref": (
                audio.audio_ref if audio and not self.muted else None
            )}, revision=revision)
            self.level = 1
        elif next_level == 2:
            if context.reveal_target:
                await self._emit(context.zone, revision=revision)
                self.level = 2
                await context.reveal_target()
            elif context.zone:
                await self._emit(context.zone + context.reveal, revision=revision)
                self.level = 2
        elif next_level == 3:
            if context.target and context.capture_epoch != self.capture_epoch:
                return None
            entry = self.targets.get_target(context.target) if context.target else None
            result = entry.result if entry else None
            capture_id = entry.capture_id if entry else context.capture_id
            exact = bool(not result and context.pointer and capture_id)
            if exact:
                result = LocalizeResult(context.pointer[0], context.pointer[1], 1.0, 0, True)
            if not result and self.holo and context.image_png and context.target:
                async def localize():
                    result = await self.holo.localize(
                        context.image_png, context.target.target,
                        timeout_s=self.config.holo_timeout_s,
                    )
                    if result is None:
                        raise ValueError("Cible introuvable")
                    return result

                task = asyncio.create_task(self.fallback.call(
                    "holo", localize, localization_budget(self.holo, self.config.holo_timeout_s),
                    lambda: None,
                ))
                self.localization = task
                try:
                    result = await task
                except asyncio.CancelledError:
                    if epoch != self.intervention_epoch:
                        return None
                    raise
                finally:
                    if self.localization is task:
                        self.localization = None
            if (generation != self.generation or epoch != self.intervention_epoch
                    or (context.target and context.capture_epoch != self.capture_epoch)
                    or (self.muted and reason != "explicit")):
                return None
            if result and (not 0 < result.x < 1000 or not 0 < result.y < 1000
                           or result.target_visible is False
                           or (result.confidence is not None and (
                               not math.isfinite(result.confidence) or result.confidence < 0.5))
                           or (context.require_visible and (result.target_visible is not True
                               or result.confidence is None))
                           or (context.expected_rect is not None
                               and not inside(context.expected_rect, result.x, result.y))):
                if result and context.expected_rect is not None:
                    self.debug({"kind": "point_rejected", "x": result.x, "y": result.y})
                result = None
            if result and capture_id and context.target and context.target.visible:
                if not entry and not exact:
                    self.targets.put_target(TargetEntry(context.target, result, capture_id))
                payload = {"capture_id": capture_id, "ui_revision": context.target.ui_revision,
                           "x": result.x, "y": result.y}
                if context.app:
                    payload["app"] = context.app
                if exact and context.pointer_ref:
                    payload["ref"], payload["snapshot_id"] = context.pointer_ref
                await self._command("pointer", payload, revision=revision)
                self.level = 3
            else:
                self.debug({"kind": "holo_unavailable", "message": "Cible non localisée"})
                if context.image_png:
                    await self._emit(context.zone, revision=revision)
                    await self._command("say", {
                        "text": ("Utilisez " + context.shortcut_hint + " : "
                                 if context.shortcut_hint else "Recherche de commandes : ")
                                 + self.step["instruction"],
                        "audio_ref": None,
                    }, revision=revision)
                await self.bus.publish(Topic.DEBUG, {
                    "code": "holo_unavailable",
                    "message": "Cible non visible ; utilisez la recherche",
                    "retryable": True,
                })
        elif self.level == 3 and context.request_demo:
            await context.request_demo()
            self.level = 4
        elif self.level == 3 and context.demo and context.checkpoint_id:
            await self._emit(context.demo, revision=revision)
            # L'orchestrateur attend l'acquittement et vérifie avant finish_demo.
            self.level = 4
            self.demo_checkpoint = context.checkpoint_id
        return await self._decision("help", reason)

    async def finish_demo(
        self, context: HelpContext, *, generation: int, acknowledged: bool,
    ) -> None:
        if (generation == self.generation and acknowledged and self.level == 4
                and context.demo and context.checkpoint_id
                and context.checkpoint_id == self.demo_checkpoint):
            await self._emit(context.demo_undo)
            self.demo_checkpoint = None