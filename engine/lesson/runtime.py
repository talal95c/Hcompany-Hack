"""Orchestration asyncio du direct et garde des actions natives."""

import asyncio
import base64
import binascii
import json
import struct
import time
from dataclasses import asdict, replace
from uuid import UUID, uuid4

from engine.bus import EventBus, Topic
from engine.bus.servers import AddonServer, DesktopServer, EventBuffer, Seen
from engine.bus.validation import validate
from engine.cache import AudioCache, Preloader, TargetCache, TargetContext
from engine.checks import SceneState, evaluate, require_check
from engine.config import EngineConfig
from engine.debug.server import DebugServer
from engine.fallback import Fallback
from engine.interfaces import Clock, HoloClient, JevClient, SttClient, SystemClock
from engine.learner import LearnerMemory
from engine.lesson import Session, load_lesson
from engine.policy import HelpContext, HelpPolicy


def decode_capture(payload: dict) -> bytes:
    reference = payload["image_ref"]
    prefix = "data:image/png;base64,"
    if not reference.startswith(prefix) or len(reference) > 6 * 1024 * 1024:
        raise ValueError("Capture PNG inline requise")
    data = base64.b64decode(reference[len(prefix):], validate=True)
    if len(data) > 4 * 1024 * 1024 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("PNG invalide")
    offset, dimensions, ended = 8, None, False
    while offset + 12 <= len(data):
        size = struct.unpack_from("!I", data, offset)[0]
        chunk = data[offset + 4:offset + 8]
        end = offset + 12 + size
        if end > len(data):
            raise ValueError("PNG tronqué")
        body = data[offset + 8:offset + 8 + size]
        crc = struct.unpack_from("!I", data, end - 4)[0]
        if binascii.crc32(chunk + body) & 0xffffffff != crc:
            raise ValueError("CRC PNG invalide")
        if offset == 8:
            if chunk != b"IHDR" or size != 13:
                raise ValueError("En-tête PNG invalide")
            dimensions = struct.unpack_from("!II", body)
        offset = end
        if chunk == b"IEND":
            ended = True
            break
    crop = payload["crop"]
    if not ended or offset != len(data) or dimensions != (crop["width"], crop["height"]):
        raise ValueError("Dimensions PNG incompatibles")
    if max(dimensions) > 8192 or min(dimensions) < 1:
        raise ValueError("Capture trop grande")
    return data


class EngineRuntime:
    def __init__(
        self, config: EngineConfig, *, lesson: dict | None = None,
        clock: Clock | None = None, holo: HoloClient | None = None,
        jev: JevClient | None = None, stt: SttClient | None = None,
    ):
        self.config, self.clock, self.stt = config, clock or SystemClock(), stt
        self.debug = DebugServer(config.host, config.debug_port)
        self.bus = EventBus(report=self.debug.record)
        self.fallback = Fallback(self.clock, self.record)
        self.targets, self.audio, self.preloader = TargetCache(), AudioCache(), Preloader()
        self.learner = LearnerMemory(config.learner_path)
        if lesson is None and config.lesson:
            lesson = load_lesson(config.lesson)
        self.session = Session(config.session_id, lesson) if lesson else None
        if lesson:
            for step in lesson["steps"]:
                require_check(step["check"]["name"])
                for error in step.get("known_errors", []):
                    require_check(error["check"]["name"])
        self.policy = HelpPolicy(config, self.bus, clock=self.clock, holo=holo, jev=jev,
                                 fallback=self.fallback, targets=self.targets, audio=self.audio,
                                 debug=self.record)
        if self.session:
            self.policy.set_step(self.session.step, self.session.generation)
        self.state = SceneState()
        self.buffer = EventBuffer()
        self.addon = AddonServer(config, self.receive, self.resync, self.addon_disconnected,
                                 self.debug.record)
        self.desktop = DesktopServer(config, self.desktop_message, self.desktop_disconnected,
                                     self.debug.record)
        self.tasks: set[asyncio.Task] = set()
        self.lock = asyncio.Lock()
        self.regions: list[dict] = []
        self.ui_revision = 0
        self.blender_version = ""
        self.permissions = {"screen": False, "accessibility": False, "microphone": False}
        self.capture: dict | None = None
        self.capture_ids = Seen()
        self.consent_tokens = Seen()
        self.consent: tuple[str, float, int] | None = None
        self.utterances: dict[str, dict] = {}
        self.help_context = HelpContext()
        self.max_help = 0
        self.closed = False
        self.connection_epoch = 0
        self.commands = self.bus.subscribe(Topic.COMMAND)
        self.diagnostics = self.bus.subscribe(Topic.DEBUG)

    def record(self, event: dict) -> None:
        self.debug.record(event)
        if event.get("kind") == "error":
            self.spawn(self.error(event["code"], event["message"]))

    def spawn(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        task.add_done_callback(self.task_finished)
        return task

    def task_finished(self, task: asyncio.Task) -> None:
        if not task.cancelled() and task.exception():
            self.debug.record({"kind": "task_error", "error_type": type(task.exception()).__name__})

    async def start(self) -> None:
        try:
            await self.addon.start()
            await self.desktop.start()
            await self.debug.start()
            self.spawn(self.events())
            self.spawn(self.forward_commands())
            self.spawn(self.forward_diagnostics())
            self.spawn(self.timer())
        except BaseException:
            await self.close()
            raise

    async def error(self, code: str, message: str, connection=None) -> None:
        await self.desktop.send("error", {"code": code, "message": message, "retryable": True},
                                connection)

    def make_command(self, kind: str, payload: dict, recipient: str = "addon") -> dict:
        command = {"schema_version": "1.0", "session_id": self.config.session_id,
                   "command_id": str(uuid4()), "step_id": self.session.step_id if self.session
                   else None, "generation": self.session.generation if self.session else 0,
                   "recipient": recipient, "type": kind, "deadline_ms": 1000,
                   "expected_scene_revision": max(0, self.state.revision), "payload": payload}
        validate("commands", command)
        return command

    async def resync(self) -> None:
        self.connection_epoch += 1
        self.state.complete = False
        self.ui_revision += 1
        self.invalidate_native()
        self.targets.invalidate()
        await self.preloader.cancel()
        if self.session:
            self.session.resync()
            self.policy.set_step(self.session.step, self.session.generation)
            self.pause()
        await self.addon.send(self.make_command("request_snapshot", {}))
        await self.send_state()

    def invalidate_native(self) -> None:
        self.capture, self.consent = None, None
        self.help_context = HelpContext()

    def pause(self) -> None:
        if self.session:
            if self.session.status == "OBSERVING":
                self.session.transition("CHECKING")
            if self.session.status in {"CHECKING", "ACTING"}:
                self.session.transition("PAUSED")

    async def addon_disconnected(self) -> None:
        self.state.complete = False
        self.invalidate_native()
        self.pause()
        await self.send_state()

    async def desktop_disconnected(self) -> None:
        self.invalidate_native()
        self.permissions = dict.fromkeys(self.permissions, False)
        self.utterances.clear()
        self.targets.invalidate()
        self.pause()

    async def receive(self, event: dict) -> None:
        await self.buffer.put({**event, "received_at": time.perf_counter(),
                               "connection_epoch": self.connection_epoch})

    async def events(self) -> None:
        while True:
            event = await self.buffer.get()
            async with self.lock:
                if event["connection_epoch"] != self.connection_epoch:
                    continue
                self.debug.record({"kind": "event", "type": event["type"],
                                   "scene_revision": event["scene_revision"]})
                await self.bus.publish(Topic.EVENT, event)
                if event["type"] == "hello":
                    self.blender_version = event["payload"]["blender_version"]
                if event["type"] == "regions.changed":
                    self.regions = event["payload"]["regions"]
                    self.ui_revision = event["payload"]["ui_revision"]
                    self.capture = None
                    self.help_context = HelpContext()
                    self.targets.invalidate()
                if event["type"] == "operator.executed":
                    self.targets.invalidate()
                    self.capture = None
                if "base_revision" in event and event["base_revision"] <= self.state.revision + 1:
                    self.state.revision = event["scene_revision"] - 1
                self.state.apply(event)
                await self.evaluate(event)

    async def tick(self) -> None:
        async with self.lock:
            await self.evaluate({"type": "heartbeat", "payload": {},
                                 "received_at": time.perf_counter()})

    async def timer(self) -> None:
        while True:
            await asyncio.sleep(0.1)
            await self.tick()

    async def evaluate(self, event: dict) -> None:
        session = self.session
        if not session or session.status in {"COMPLETE", "ACTING"}:
            return
        if session.status == "READY":
            if not session.observe(self.state.mode):
                return
        if session.status == "PAUSED":
            if not self.state.recent:
                return
            session.transition("OBSERVING")
        if session.status != "OBSERVING":
            return
        session.transition("CHECKING")
        generation = session.generation
        check = session.step["check"]
        result = evaluate(check["name"], self.state, check["params"])
        self.debug.record({"kind": "check", **asdict(result)})
        await self.bus.publish(Topic.CHECK, result)
        checked_at = time.perf_counter()
        self.metric("event→check", (checked_at - event["received_at"]) * 1000)
        self.metric("check", result.duration_ms)
        used_help = max(self.max_help, self.policy.level)
        decision = await self.policy.process(
            self.state, result, event_type=event["type"],
            undo_count=event["payload"].get("count", 1), context=self.context(),
        )
        if generation != session.generation or session.status != "CHECKING":
            return
        self.max_help = max(used_help, self.policy.level)
        if decision:
            self.metric("check→decision", (time.perf_counter() - checked_at) * 1000)
        if result.status == "pass" and decision and decision.kind == "success":
            session.transition("PASSED")
            self.learner.review(session.step["skill_id"], passed=True, help_level=self.max_help,
                                challenge=session.step.get("challenge", False))
            session.advance(session.generation)
            self.invalidate_native()
            await self.preloader.cancel()
            self.max_help = 0
            if session.status != "COMPLETE":
                self.policy.set_step(session.step, session.generation)
                session.observe(self.state.mode)
        elif result.status == "unknown":
            session.transition("PAUSED")
        elif decision and decision.kind == "help":
            session.transition("HELP")
            session.transition("OBSERVING")
        else:
            session.transition("OBSERVING")
        await self.send_state()

    def metric(self, stage: str, latency_ms: float) -> None:
        self.debug.record({"kind": "latency", "stage": stage, "latency_ms": latency_ms})

    def context(self) -> HelpContext:
        context = self.help_context
        if self.regions:
            region = self.regions[0]
            context = replace(context, area_id=region["area_id"], region_id=region["region_id"])
        return context

    async def send_state(self, connection=None) -> None:
        session = self.session
        await self.desktop.send("lesson.state", {
            "step_id": session.step_id if session and session.status != "COMPLETE" else None,
            "status": session.status if session else "READY",
            "instruction": session.step["instruction"] if session else "Aucune leçon chargée",
            "help_level": self.policy.level,
        }, connection)

    async def forward_commands(self) -> None:
        while True:
            command = await self.commands.get()
            try:
                if self.session and command["generation"] != self.session.generation:
                    # La réussite est émise avant le changement d'étape.
                    if command["type"] != "success":
                        continue
                if command["recipient"] == "desktop":
                    if command["type"] == "input.action":
                        await self.error("consent_required", "Utilisez le canal d'action sécurisé")
                        continue
                    await self.desktop.send("command", command)
                elif command["type"] == "replay":
                    self.spawn(self.run_demo(command, self.context()))
                else:
                    await self.addon.send(command)
                published = self.bus.published_at.pop(command["command_id"], None)
                if published is not None:
                    self.metric("decision→send", (time.perf_counter() - published) * 1000)
            except ConnectionError:
                self.debug.record({"kind": "command_not_sent", "type": command["type"]})
            finally:
                self.commands.task_done()

    async def run_demo(self, command: dict, context: HelpContext) -> None:
        try:
            result = await self.addon.correlation.request(command, self.addon.send)
            await self.policy.finish_demo(context, generation=command["generation"],
                                          acknowledged=result["status"] == "ok")
        except (TimeoutError, ConnectionError):
            self.pause()
            await self.error("demo_failed", "Démonstration interrompue")

    async def forward_diagnostics(self) -> None:
        while True:
            diagnostic = await self.diagnostics.get()
            await self.error(diagnostic["code"], diagnostic["message"])

    async def desktop_message(self, message: dict, connection) -> None:
        kind, payload = message["type"], message["payload"]
        if kind == "hello":
            self.capture = None
            self.targets.invalidate()
            await self.send_state(connection)
        elif kind == "ping":
            await self.desktop.send("pong", payload, connection, message["message_id"])
        elif kind == "permissions":
            self.permissions = payload.copy()
            if not payload["screen"] or not payload["accessibility"]:
                self.invalidate_native()
        elif kind == "user.intent":
            if payload["text"].lstrip().startswith("{"):
                await self.authorize(payload, connection)
            else:
                if payload["text"].casefold().strip() == "chut":
                    self.consent = None
                    self.pause()
                await self.policy.intent(payload["text"], self.context())
                self.max_help = max(self.max_help, self.policy.level)
                await self.send_state(connection)
        elif kind == "capture.result":
            await self.accept_capture(payload)
        elif kind in {"ptt.start", "audio.chunk", "ptt.stop"}:
            await self.audio_message(kind, payload, connection)

    async def authorize(self, payload: dict, connection) -> None:
        try:
            intent = json.loads(payload["text"])
            token = intent["consent_token"]
            UUID(token)
            if payload["source"] != "bouton" or intent["intent"] != "fais-le" or not self.session:
                raise ValueError
            if token in self.consent_tokens or len(self.consent_tokens.items) >= 4096:
                raise ValueError
            allowed = self.learner.can_delegate(
                self.session.step["skill_id"], confirmed=True,
                wants_to_learn=not (intent.get("delegation_confirmed") is True
                                    and intent.get("wants_to_learn") is False),
            )
            if not allowed or self.session.status != "OBSERVING":
                raise ValueError
            self.consent_tokens.add(token)
            self.consent = (token, self.clock.monotonic() + 60, self.session.generation)
            self.session.transition("ACTING")
            await self.send_state(connection)
        except (ValueError, KeyError, TypeError, AttributeError):
            await self.error("consent_required", "Confirmation de délégation requise", connection)

    async def input_action(self, action: dict) -> dict | None:
        consent, capture = self.consent, self.capture
        if (not self.session or not consent or self.clock.monotonic() >= consent[1]
                or consent[2] != self.session.generation
                or self.session.status not in {"ACTING", "OBSERVING"}
                or not self.permissions["screen"] or not self.permissions["accessibility"]):
            await self.error("consent_required", "Consentement valide requis")
            return None
        if not capture or capture.get("consumed"):
            await self.error("capture_required", "Une nouvelle capture est requise")
            return None
        if self.session.status == "OBSERVING":
            self.session.transition("ACTING")
        command = self.make_command("input.action", {
            "action": action, "consent_token": consent[0], "capture_id": capture["capture_id"],
        }, "desktop")
        capture["consumed"] = True
        try:
            result = await self.desktop.correlation.request(
                command, lambda c: self.desktop.send("command", c),
            )
            if consent == self.consent and self.session.status == "ACTING":
                self.session.transition("CHECKING")
                self.session.transition("PAUSED")
                await self.addon.send(self.make_command("request_snapshot", {}))
            return result
        except (TimeoutError, ConnectionError):
            self.consent = None
            self.pause()
            await self.error("input_failed", "Action interrompue ; vérifiez la scène")
            return None

    async def accept_capture(self, payload: dict) -> None:
        if (not self.permissions["screen"] or payload["capture_id"] in self.capture_ids
                or len(self.capture_ids.items) >= 4096):
            raise ValueError("Capture refusée")
        image = decode_capture(payload)
        if payload["ui_revision"] != self.ui_revision:
            raise ValueError("Capture périmée")
        self.capture_ids.add(payload["capture_id"])
        self.capture = {**payload, "image_png": image, "consumed": False}
        if self.session:
            crop = payload["crop"]
            target = TargetContext(
                self.blender_version, (crop["width"], crop["height"]), payload["scale"],
                self.session.step["target"]["description"], (crop["x"], crop["y"]),
                payload["monitor_id"], self.session.lesson.get("language", "fr"),
                self.ui_revision, True,
            )
            self.help_context = replace(self.context(), target=target,
                                        capture_id=payload["capture_id"], image_png=image)
            if (self.policy.level == 2 and self.session.status != "COMPLETE"
                    and not self.policy.muted):
                await self.policy.intent("aide", self.context())
                self.max_help = max(self.max_help, self.policy.level)
                await self.send_state()
            elif self.policy.holo and self.session.index + 1 < len(self.session.lesson["steps"]):
                following = self.session.lesson["steps"][self.session.index + 1]
                next_target = replace(target, target=following["target"]["description"])
                generation = self.session.generation

                async def localize():
                    return await self.fallback.call(
                        "holo", lambda: self.policy.holo.localize(
                            image, next_target.target, timeout_s=self.config.holo_timeout_s,
                        ), self.config.holo_timeout_s, lambda: None,
                    )

                await self.preloader.start(generation, next_target, payload["capture_id"],
                                           localize, self.targets,
                                           timeout_s=self.config.holo_timeout_s)

    async def audio_message(self, kind: str, payload: dict, connection) -> None:
        key = payload["utterance_id"]
        if kind == "ptt.start":
            if not self.permissions["microphone"] or len(self.utterances) >= 4:
                raise ValueError("Microphone indisponible")
            self.utterances[key] = {"chunks": {}, "size": 0, "encoding": None, "sample_rate": None}
        elif key not in self.utterances:
            raise ValueError("Énoncé inconnu")
        elif kind == "audio.chunk":
            utterance = self.utterances[key]
            data = base64.b64decode(payload["data_base64"], validate=True)
            sequence = payload["sequence"]
            if sequence in utterance["chunks"]:
                return
            if utterance["size"] + len(data) > 2 * 1024 * 1024 or sequence >= 2048:
                self.utterances.pop(key)
                await self.error("audio_overflow", "Audio trop long, réessayez", connection)
                return
            for name in ("encoding", "sample_rate"):
                if utterance[name] not in {None, payload[name]}:
                    raise ValueError("Format audio modifié")
                utterance[name] = payload[name]
            utterance["chunks"][sequence] = data
            utterance["size"] += len(data)
        else:
            utterance = self.utterances.pop(key)
            chunks = utterance["chunks"]
            if not chunks or sorted(chunks) != list(range(len(chunks))):
                raise ValueError("Audio incomplet")
            generation = self.session.generation if self.session else 0
            transcript = await self.fallback.transcribe(
                self.stt, b"".join(chunks[i] for i in range(len(chunks))),
                encoding=utterance["encoding"], sample_rate=utterance["sample_rate"],
                language="fr", timeout=self.config.stt_final_timeout_s,
            )
            if transcript and (not self.session or generation == self.session.generation):
                await self.policy.intent(transcript.text, self.context())

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        for task in tuple(self.tasks):
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        await self.preloader.cancel()
        await asyncio.gather(self.desktop.close(), self.addon.close(), self.debug.close())
        self.learner.save()
