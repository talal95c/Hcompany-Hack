"""Décisions d'aide déterministes avec escalade prudente et services facultatifs."""

import asyncio
from collections.abc import Callable
from dataclasses import asdict, dataclass
from uuid import uuid4

from engine.bus import EventBus, Topic
from engine.bus.validation import validate
from engine.cache import AudioCache, TargetCache, TargetContext, TargetEntry
from engine.checks import CheckResult, SceneState, evaluate, progress_signature
from engine.config import EngineConfig
from engine.fallback import Fallback
from engine.interfaces import Clock, HoloClient, JevClient, JevDecision, SystemClock


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
    area_id: str | None = None
    region_id: str | None = None
    menu_id: str | None = None
    target: TargetContext | None = None
    capture_id: str | None = None
    image_png: bytes | None = None
    safe_demo: bool = False
    checkpoint_id: str | None = None


class HelpPolicy:
    def __init__(
        self, config: EngineConfig, bus: EventBus, *, clock: Clock | None = None,
        jev: JevClient | None = None, holo: HoloClient | None = None,
        fallback: Fallback | None = None, targets: TargetCache | None = None,
        audio: AudioCache | None = None, debug: Callable[[dict], None] | None = None,
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

    def set_step(self, step: dict, generation: int) -> None:
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
        self.debug({"kind": "decision", **asdict(decision)})
        return decision

    async def _command(self, kind: str, payload: dict, *, revision: int = 0) -> None:
        assert self.step is not None
        command = {
            "schema_version": "1.0", "session_id": self.config.session_id,
            "command_id": str(uuid4()), "step_id": self.step["id"],
            "generation": self.generation,
            "recipient": "addon" if kind in {"highlight", "open_menu", "replay", "undo_demo"}
            else "desktop", "type": kind, "deadline_ms": 1000,
            "expected_scene_revision": max(0, revision), "payload": payload,
        }
        validate("commands", command)
        await self.bus.publish(Topic.COMMAND, command)

    async def intent(self, text: str, context: HelpContext | None = None) -> Decision | None:
        text = text.strip().casefold()
        if text == "chut":
            self.muted = True
            if self.step:
                await self._command("stop", {"reason": "Silence demandé"})
            return None
        if text == "reprends":
            self.muted = False
            return None
        if text in {"aide", "help"} and self.step and not self.passed:
            async with self.lock:
                return await self._help("explicit", self.step.get("why", self.step["instruction"]),
                                        context or HelpContext(), 0)
        return None

    async def process(
        self, state: SceneState, result: CheckResult, *, event_type: str = "heartbeat",
        undo_count: int = 1, context: HelpContext | None = None,
    ) -> Decision | None:
        async with self.lock:
            if not self.step or self.passed:
                return None
            generation = self.generation
            if result.scene_revision != state.revision or not state.recent:
                return None
            if result.status == "pass":
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
                reason == "no_progress" and bool(state.objects)
            )
            if ambiguous and self.jev:
                ambiguity_key = (signature, reason, tuple(sorted(active_codes)))
                if (self.jev_wait_key == ambiguity_key
                        and self.clock.monotonic() < self.jev_wait_until):
                    return None

                def local_rule() -> JevDecision:
                    return JevDecision("intervene", "Règle locale", 0)

                async def decide() -> JevDecision:
                    answer = await self.jev.decide(
                        {"check_status": result.status, "reason": reason,
                         "known_errors": sorted(active_codes)}, timeout_s=self.config.jev_timeout_s
                    )
                    if answer.action not in {"intervene", "wait"} | {
                        "error_code:" + code for code in active_codes
                    }:
                        raise ValueError("Décision invalide")
                    return answer

                answer = await self.fallback.call(
                    "jev", decide, self.config.jev_timeout_s, local_rule,
                )
                if generation != self.generation:
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
            decision = await self._help(reason, hint, context or HelpContext(), state.revision)
            if generation != self.generation:
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
        next_level = min(4, self.level + 1)
        if next_level == 1:
            audio = self.audio.get(hint)
            await self._command("say", {"text": hint, "audio_ref": (
                audio.audio_ref if audio and not self.muted else None
            )}, revision=revision)
            self.level = 1
        elif next_level == 2:
            if context.area_id and context.region_id:
                await self._command("highlight", {
                    "area_id": context.area_id, "region_id": context.region_id,
                    "color": "#ffcc00", "duration_ms": 3000,
                }, revision=revision)
                if context.menu_id:
                    await self._command("open_menu", {
                        "menu_id": context.menu_id, "area_id": context.area_id,
                        "region_id": context.region_id,
                    }, revision=revision)
                self.level = 2
        elif next_level == 3:
            entry = self.targets.get_target(context.target) if context.target else None
            result = entry.result if entry else None
            capture_id = entry.capture_id if entry else context.capture_id
            if not result and self.holo and context.image_png and context.target:
                async def localize():
                    result = await self.holo.localize(
                        context.image_png, context.target.target,
                        timeout_s=self.config.holo_timeout_s,
                    )
                    if result is None:
                        raise ValueError("Cible introuvable")
                    return result

                result = await self.fallback.call(
                    "holo", localize, self.config.holo_timeout_s, lambda: None,
                )
            if generation != self.generation:
                return None
            if result and capture_id and context.target and context.target.visible:
                if not entry:
                    self.targets.put_target(TargetEntry(context.target, result, capture_id))
                await self._command("pointer", {
                    "capture_id": capture_id, "ui_revision": context.target.ui_revision,
                    "x": result.x, "y": result.y,
                }, revision=revision)
                self.level = 3
            else:
                self.debug({"kind": "holo_unavailable", "message": "Utilisez le menu ou F3"})
                await self.bus.publish(Topic.DEBUG, {
                    "code": "holo_unavailable", "message": "Utilisez le menu ou F3",
                    "retryable": True,
                })
        elif self.level == 3 and context.safe_demo and context.checkpoint_id:
            await self._command("replay", {
                "procedure_ref": self.step["procedure_ref"], "params": {},
            }, revision=revision)
            # L'orchestrateur attend l'acquittement et vérifie avant finish_demo.
            self.level = 4
            self.demo_checkpoint = context.checkpoint_id
        return await self._decision("help", reason)

    async def finish_demo(
        self, context: HelpContext, *, generation: int, acknowledged: bool,
    ) -> None:
        if (generation == self.generation and acknowledged and self.level == 4
                and context.safe_demo and context.checkpoint_id
                and context.checkpoint_id == self.demo_checkpoint):
            await self._command("undo_demo", {"checkpoint_id": context.checkpoint_id})
            self.demo_checkpoint = None