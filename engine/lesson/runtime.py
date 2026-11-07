"""Orchestration asyncio du direct et garde des actions natives."""

import asyncio
import base64
import binascii
import inspect
import json
import math
import struct
import time
from dataclasses import asdict, replace
from uuid import UUID, uuid4

from engine.adapters import (
    DEFAULT_PLUGIN_APP,
    PLUGINS,
    AccessibilityAdapter,
    HoloAssertVerifier,
    Rect,
    SensorRouter,
    VisionAdapter,
    load_profile,
)
from engine.adapters.profiles import version_matches
from engine.adapters.services import ProfileJevAdapter, ProfileSearchAdapter
from engine.adapters.vision import visual_checks
from engine.bus import EventBus, Topic
from engine.bus.servers import AddonServer, DesktopServer, EventBuffer, Seen
from engine.bus.validation import validate
from engine.cache import AudioCache, Preloader, TargetCache, TargetContext
from engine.checks import evaluate, namespace, require_check
from engine.checks.lesson_steps import evaluate_verification
from engine.config import EngineConfig
from engine.debug.server import DebugServer
from engine.fallback import Fallback
from engine.interfaces import (
    Clock,
    HoloClient,
    HoloVerifier,
    JevClient,
    SearchClient,
    SearchHit,
    SttClient,
    SystemClock,
)
from engine.learner import LearnerMemory
from engine.lesson import Session, lesson_app, load_lesson, load_verification
from engine.lesson.live_audio import LiveUtterance
from engine.policy import HelpContext, HelpPolicy
from engine.services.adapters import JevAdapter, SearchAdapter


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
        search: SearchClient | None = None, verifier: HoloVerifier | None = None,
    ):
        self.search = search
        self.config, self.clock, self.stt = config, clock or SystemClock(), stt
        self.debug = DebugServer(config.host, config.debug_port)
        self.bus = EventBus(report=self.debug.record)
        self.fallback = Fallback(self.clock, self.record)
        self.targets, self.audio, self.preloader = TargetCache(), AudioCache(), Preloader()
        self.learner = LearnerMemory(config.learner_path)
        if lesson is None and config.lesson:
            lesson = load_lesson(config.lesson)
        self.verification = load_verification(config.lesson, lesson) if config.lesson else {}
        self.session = Session(config.session_id, lesson) if lesson else None
        self.app = lesson_app(lesson) if lesson else dict(DEFAULT_PLUGIN_APP)
        self.profile = load_profile(self.app)
        if self.app["id"] not in PLUGINS:
            if isinstance(search, SearchAdapter):
                self.search = ProfileSearchAdapter(search.client, self.profile)
            if isinstance(jev, JevAdapter):
                jev = ProfileJevAdapter(jev.client, self.profile)
        if lesson:
            validate("lesson", lesson)
            for step in lesson["steps"]:
                for check in [step["check"]] + [e["check"] for e in step.get("known_errors", [])]:
                    require_check(check["name"])
                    if namespace(check["name"]) not in {None, self.app["id"]}:
                        raise ValueError(f"Check {check['name']} hors de l'application "
                                         + self.app["id"])
        self.policy = HelpPolicy(config, self.bus, clock=self.clock, holo=holo, jev=jev,
                                 fallback=self.fallback, targets=self.targets, audio=self.audio,
                                 debug=self.record, app_context=self.profile.service_context())
        if self.session:
            self.policy.set_step(self.session.step, self.session.generation)
        self.buffer = EventBuffer()
        self.addon = AddonServer(config, self.receive, self.resync, self.addon_disconnected,
                                 self.debug.record)
        self.desktop = DesktopServer(config, self.desktop_message, self.desktop_disconnected,
                                     self.debug.record)
        self.tasks: set[asyncio.Task] = set()
        self.lock = asyncio.Lock()
        self.action_lock = asyncio.Lock()
        self.action_task: asyncio.Task | None = None
        self.actions_stopped = False
        self.demo_requested: tuple[int, int] | None = None
        self.demo_undo: tuple[int, dict, str, str | None] | None = None
        self.policy.on_stop = self.stop_actions
        self.policy.on_resume = self.resume_actions
        self.ui_revision = 0
        self.permissions = {"screen": False, "accessibility": False, "microphone": False}
        self.capture: dict | None = None
        self.capture_ids = Seen()
        self.consent_tokens = Seen()
        self.consent: tuple[str, float, int] | None = None
        self.utterances: dict[str, dict] = {}
        self.live_utterances: dict[str, LiveUtterance] = {}
        self.help_context = HelpContext()
        self.max_help = 0
        self.closed = False
        self.last_desktop_state = None
        self.render_pending = {}
        self.pointer_request = None
        self.router = SensorRouter(self.app["sensor"])
        plugin = PLUGINS.get(self.app["id"])
        self.plugin = plugin(self, self.profile) if plugin else None
        if verifier is None and callable(getattr(getattr(holo, "client", None), "_complete", None)):
            verifier = HoloAssertVerifier(holo.client, app_context=self.profile.jev_context)
        self.a11y = AccessibilityAdapter(self.app, self.profile, self.desktop_send,
                                         timeout_s=config.a11y_timeout_s, metric=self.metric)
        self.vision = VisionAdapter(self.app, self.profile, self.capture_window, verifier,
                                    timeout_s=config.holo_timeout_s, metric=self.metric)
        self.adapter = None
        self.window_requests: dict[str, asyncio.Future] = {}
        self.window_epochs: dict[str, int] = {}
        self.select_adapter()
        self.connection_epoch = 0
        self.commands = self.bus.subscribe(Topic.COMMAND)
        self.diagnostics = self.bus.subscribe(Topic.DEBUG)

    @property
    def state(self):
        adapter = self.adapter or self.primary
        return adapter.snapshot() if adapter else self.a11y.snapshot()

    @property
    def primary(self):
        """Capteur nominal de la leçon, même indisponible (pour l'état et l'aide)."""
        if self.app["sensor"] in {"addon", "auto"} and self.plugin:
            return self.plugin
        return self.vision if self.app["sensor"] == "vision" else self.a11y

    @property
    def regions(self) -> list[dict]:
        return self.plugin.regions if self.plugin else []

    @regions.setter
    def regions(self, value: list[dict]) -> None:
        if self.plugin:
            self.plugin.regions = value

    def available_sensors(self) -> dict[str, bool]:
        return {"addon": bool(self.plugin and self.plugin.available()),
                "accessibility": self.a11y.available(), "vision": self.vision.available()}

    def select_adapter(self) -> None:
        route = self.router.choose(self.available_sensors())
        adapter = {"addon": self.plugin, "accessibility": self.a11y,
                   "vision": self.vision}.get(route.sensor)
        if adapter is not self.adapter:
            self.adapter = adapter
            self.debug.record({"kind": "sensor", "sensor": route.sensor, "reason": route.reason})
            if hasattr(self, "help_context"):
                self.invalidate_capture()

    def app_version(self) -> str:
        if self.plugin and self.adapter is self.plugin:
            return self.plugin.version
        return self.adapter.version if self.adapter else "unknown"

    def app_ready(self) -> bool:
        adapter = self.adapter
        if adapter is None:
            return False
        if adapter is self.plugin:
            return self.plugin.version == self.app["version"]
        return adapter.available() and version_matches(self.app["version"], adapter.version)

    async def desktop_send(self, kind: str, payload: dict) -> None:
        if not self.desktop.clients:
            raise ConnectionError("Desktop absent")
        await self.desktop.send(kind, payload)

    def vocabulary(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(self.config.stt_vocabulary + self.profile.vocabulary))

    async def docs_search(self, query: str, *, depth: str = "standard") -> list[SearchHit]:
        """Recherche documentaire restreinte aux domaines du profil d'application."""
        if not self.search:
            return []
        domains = self.profile.docs_domains
        if "domains" in inspect.signature(self.search.search).parameters:
            return await self.search.search(query, depth=depth, domains=domains)
        scoped = " OR ".join(f"site:{d}" for d in domains)
        return await self.search.search(f"{query} {scoped}".strip(), depth=depth)

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
            self.spawn(self.observe_app())
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
        if self.plugin:
            self.plugin.state.complete = False
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
        self.stop_actions()
        self.consent = None
        self.pointer_request = None
        self.invalidate_capture()

    def stop_actions(self) -> None:
        self.consent = None
        self.demo_requested = None
        if (self.action_task and not self.action_task.done()
                and self.action_task is not asyncio.current_task()):
            self.actions_stopped = True
            self.action_task.cancel()
        self.pause()

    def resume_actions(self) -> None:
        self.actions_stopped = False

    def invalidate_capture(self) -> None:
        self.policy.cancel_intervention(invalidate_capture=True)
        self.capture = None
        self.help_context = HelpContext()
        self.targets.invalidate()
        if self.preloader.task:
            self.preloader.task.cancel()

    def pause(self) -> None:
        if self.session:
            if self.session.status == "OBSERVING":
                self.session.transition("CHECKING")
            if self.session.status in {"CHECKING", "ACTING"}:
                self.session.transition("PAUSED")

    async def addon_disconnected(self) -> None:
        if self.plugin:
            self.plugin.state.complete = False
        self.invalidate_native()
        self.pause()
        await self.send_state()

    async def desktop_disconnected(self) -> None:
        self.a11y.disconnect()
        self.vision.disconnect()
        for future in self.window_requests.values():
            if not future.done():
                future.cancel()
        self.select_adapter()
        self.invalidate_native()
        self.permissions = dict.fromkeys(self.permissions, False)
        self.utterances.clear()
        await asyncio.gather(*(s.close() for s in self.live_utterances.values()))
        self.live_utterances.clear()
        self.targets.invalidate()
        self.pause()

    async def receive(self, event: dict) -> None:
        if event["type"] in {"operator.executed", "regions.changed", "scene.changed",
                             "snapshot", "mode.changed", "selection.changed", "undo"}:
            self.invalidate_capture()
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
                if event["type"] == "command.result":
                    self.debug.record({"kind": "addon_result", **event["payload"]})
                await self.bus.publish(Topic.EVENT, event)
                plugin = self.plugin
                if plugin:
                    plugin.apply(event)
                if event["type"] == "hello" and plugin:
                    self.select_adapter()
                    if self.session and plugin.version != self.app["version"]:
                        self.invalidate_native()
                        await self.error(
                            plugin.mismatch_code, plugin.describe_version()
                            + " ; version prouvée requise : " + self.app["version"],
                        )
                if event["type"] == "regions.changed":
                    self.ui_revision = event["payload"]["ui_revision"]
                    self.invalidate_capture()
                if event["type"] == "operator.executed":
                    self.invalidate_capture()
                await self.evaluate(event)

    async def tick(self) -> None:
        async with self.lock:
            await self.evaluate({"type": "heartbeat", "payload": {},
                                 "received_at": time.perf_counter()})

    async def timer(self) -> None:
        while True:
            await asyncio.sleep(0.1)
            await self.tick()

    async def observe_app(self) -> None:
        while True:
            await self.observe_once()
            await asyncio.sleep(self.config.vision_poll_s if self.adapter is self.vision
                                else self.config.a11y_poll_s)

    async def observe_once(self) -> None:
        """Relit l'application via le capteur générique actif puis évalue l'étape."""
        if self.actions_stopped:
            return
        self.select_adapter()
        adapter, session = self.adapter, self.session
        if (not session or adapter is None or adapter is self.plugin
                or session.status in {"COMPLETE", "ACTING"}):
            return
        generation, received = session.generation, time.perf_counter()
        try:
            await adapter.refresh(session.step)
        except (ConnectionError, RuntimeError):
            return
        self.metric("refresh", (time.perf_counter() - received) * 1000)
        if (adapter is self.a11y and adapter.last_error
                and self.router.report_error("accessibility", adapter.last_error)):
            self.debug.record({"kind": "sensor_fallback", "from": "accessibility",
                               "code": adapter.last_error})
            self.select_adapter()
            return
        if generation != session.generation or adapter is not self.adapter:
            return
        if adapter is self.a11y and visual_checks(session.step):
            epoch = self.a11y.focus_epoch
            self.a11y.state.verdicts.clear()
            if self.vision.available():
                visual = await self.vision.refresh(session.step)
                if epoch != self.a11y.focus_epoch or not visual.recent:
                    return
                self.a11y.state.verdicts = dict(visual.verdicts)
        async with self.lock:
            await self.evaluate({"type": "heartbeat", "payload": {}, "received_at": received})

    async def request_refresh(self) -> None:
        if self.plugin and self.adapter is self.plugin:
            await self.addon.send(self.make_command("request_snapshot", {}))
        else:
            self.spawn(self.observe_once())

    async def evaluate(self, event: dict) -> None:
        if self.actions_stopped:
            return
        session = self.session
        if not session or session.status in {"COMPLETE", "ACTING"}:
            return
        self.select_adapter()
        if not self.app_ready():
            self.pause()
            self.debug.record({"kind": "version_mismatch", "actual": self.app_version(),
                               "required": self.app["version"],
                               "sensor": getattr(self.adapter, "sensor", None)})
            return
        if not session.preconditions_hold(self.adapter.facts()):
            self.pause()
            return
        if session.status == "READY":
            if not session.observe(self.adapter.facts()):
                return
        if session.status == "PAUSED":
            if not self.state.recent:
                return
            session.transition("OBSERVING")
        if session.status != "OBSERVING":
            return
        session.transition("CHECKING")
        generation = session.generation
        focus_epoch = self.a11y.focus_epoch
        check = session.step["check"]
        result = evaluate(check["name"], self.state, check["params"])
        if self.adapter is self.plugin:
            result = evaluate_verification(
                self.verification.get(session.step_id, {}).get("checks", []), self.state, result)
        self.debug.record({"kind": "check", **asdict(result)})
        await self.bus.publish(Topic.CHECK, result)
        checked_at = time.perf_counter()
        self.metric("event→check", (checked_at - event["received_at"]) * 1000)
        self.metric("check", result.duration_ms)
        used_help = max(self.max_help, self.policy.level)
        decision = await self.policy.process(
            self.state, result, event_type=event["type"],
            undo_count=event["payload"].get("count", 1), context=self.context(),
            can_pass=lambda: self.app_ready() and session.preconditions_hold(self.adapter.facts())
            and (self.adapter is self.plugin or focus_epoch == self.a11y.focus_epoch),
        )
        if generation != session.generation or session.status != "CHECKING":
            return
        self.max_help = max(used_help, self.policy.level)
        if not self.app_ready() or not session.preconditions_hold(self.adapter.facts()):
            self.pause()
            return
        if decision:
            self.metric("check→decision", (time.perf_counter() - checked_at) * 1000)
            self.metric("event→decision", (time.perf_counter() - event["received_at"]) * 1000)
            if "ts_monotonic_ms" in event:
                self.metric("addon→decision", time.monotonic() * 1000
                            - event["ts_monotonic_ms"])
        if result.status == "pass" and decision and decision.kind == "success":
            if self.adapter is self.plugin:
                session.transition("PASSED")
            save = asyncio.create_task(asyncio.to_thread(
                self.learner.review, session.step["skill_id"], passed=True,
                help_level=self.max_help, challenge=session.step.get("challenge", False)))
            try:
                await asyncio.shield(save)
            except asyncio.CancelledError:
                await save
                raise
            if (not self.app_ready() or not session.preconditions_hold(self.adapter.facts())
                    or (self.adapter is not self.plugin and focus_epoch != self.a11y.focus_epoch)):
                self.pause()
                return
            if session.status == "CHECKING":
                session.transition("PASSED")
            session.advance(session.generation)
            self.invalidate_native()
            await self.preloader.cancel()
            self.max_help = 0
            if session.status != "COMPLETE":
                self.policy.set_step(session.step, session.generation)
                session.observe(self.adapter.facts())
        elif result.status == "unknown":
            session.transition("PAUSED")
        elif decision and decision.kind == "help":
            session.transition("HELP")
            session.transition("OBSERVING")
        else:
            session.transition("OBSERVING")
        await self.send_state(force=decision is not None)

    def metric(self, stage: str, latency_ms: float) -> None:
        self.debug.record({"kind": "latency", "stage": stage, "latency_ms": latency_ms})

    def context(self) -> HelpContext:
        step = self.session.step if self.session else {}
        adapter = self.adapter or self.primary
        context = replace(self.help_context, reveal_target=self.reveal_target,
                          shortcut_hint=adapter.shortcut_hint if adapter else None,
                          checkpoint_id=step.get("help", {}).get("checkpoint_id"),
                          app=None if adapter is self.plugin else self.app["id"])
        if adapter and step:
            context = replace(context, zone=adapter.zone(step), reveal=adapter.reveal(step),
                              demo=adapter.replay(step), demo_undo=adapter.undo_replay(step))
            if adapter is not self.plugin:
                context = replace(context, request_demo=self.request_demo)
        return context

    async def request_demo(self) -> None:
        if self.session and self.app_ready():
            self.demo_requested = (self.session.generation, self.a11y.focus_epoch)
            await self.error("consent_required", "Confirmez explicitement la démonstration")

    async def send_state(self, connection=None, *, force: bool = False,
                         transcript: str | None = None, transcript_final: bool = False) -> None:
        session = self.session
        payload = {
            "step_id": session.step_id if session and session.status != "COMPLETE" else None,
            "status": session.status if session else "READY",
            "instruction": session.step["instruction"] if session else "Aucune leçon chargée",
            "help_level": self.policy.level,
            "ui_revision": self.ui_revision,
        }
        if transcript is not None:
            payload.update(transcript=transcript, transcript_final=transcript_final)
        if force or connection is not None or payload != self.last_desktop_state:
            await self.desktop.send("lesson.state", payload, connection)
            self.last_desktop_state = payload

    async def forward_commands(self) -> None:
        while True:
            command = await self.commands.get()
            try:
                if self.session and command["generation"] != self.session.generation:
                    # La réussite est émise avant le changement d'étape.
                    if command["type"] != "success":
                        continue
                if command["recipient"] == "desktop":
                    if command["type"] == "pointer" and (
                        self.policy.muted or not self.capture or self.capture.get("consumed")
                        or command["payload"]["capture_id"] != self.capture["capture_id"]
                    ):
                        continue
                    if command["type"] == "input.action":
                        await self.error("consent_required", "Utilisez le canal d'action sécurisé")
                        continue
                    await self.desktop.send("command", command)
                    if command["type"] in {"pointer", "success"}:
                        if len(self.render_pending) >= 512:
                            self.render_pending.pop(next(iter(self.render_pending)))
                        self.render_pending[command["command_id"]] = time.perf_counter()
                    self.debug.record({"kind": "command_sent", "command_id": command["command_id"],
                                       "type": command["type"]})
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

    async def reveal_target(self) -> None:
        self.spawn(self.capture_target())

    async def capture_target(self) -> None:
        if not self.session:
            return
        generation = self.session.generation
        try:
            adapter = self.adapter or self.primary
            reveal = adapter.reveal_target(self.session.step) if adapter else None
            crop = await reveal() if reveal else None
            if generation != self.session.generation:
                return
            if crop and crop["width"] * crop["height"] > 1_048_576:
                raise ValueError("Région trop grande")
            request = {"request_id": str(uuid4()), "crop": crop,
                       "ui_revision": self.ui_revision, "generation": generation}
            if adapter is not None and adapter.window_scope:
                request.update(crop=None, scope="window", app=self.app["id"])
            self.pointer_request = {**request, "at": time.monotonic(),
                                    "epoch": self.policy.capture_epoch}
            await self.send_state(force=True)
            await self.desktop.send("capture.request", request)
            self.debug.record({"kind": "pointer_capture_requested", **request})
        except (TimeoutError, ConnectionError, ValueError, KeyError, StopIteration):
            self.pointer_request = None
            await self.error("target_unavailable", "Dévoilez la cible ; pointage indisponible")

    async def capture_window(self) -> tuple[dict, bytes] | None:
        """Capture fraîche de la fenêtre de l'application (preuve visuelle, jamais réutilisée)."""
        if not self.permissions["screen"] or not self.desktop.clients:
            return None
        if len(self.window_requests) >= 8:
            return None
        request_id = str(uuid4())
        epoch = self.vision.focus_epoch
        future = asyncio.get_running_loop().create_future()
        self.window_requests[request_id] = future
        self.window_epochs[request_id] = epoch
        start = time.perf_counter()
        try:
            await self.desktop.send("capture.request", {
                "request_id": request_id, "crop": None, "ui_revision": self.ui_revision,
                "generation": self.session.generation if self.session else 0,
                "scope": "window", "app": self.app["id"],
            })
            frame = await asyncio.wait_for(future, 3)
            if epoch != self.vision.focus_epoch:
                return None
            self.metric("capture.window", (time.perf_counter() - start) * 1000)
            return frame
        except (TimeoutError, asyncio.CancelledError, ConnectionError):
            if asyncio.current_task() and asyncio.current_task().cancelling():
                raise
            return None
        finally:
            self.window_requests.pop(request_id, None)
            self.window_epochs.pop(request_id, None)

    async def forward_diagnostics(self) -> None:
        while True:
            diagnostic = await self.diagnostics.get()
            await self.error(diagnostic["code"], diagnostic["message"])

    async def desktop_message(self, message: dict, connection) -> None:
        kind, payload = message["type"], message["payload"]
        if kind == "hello":
            self.invalidate_capture()
            await self.send_state(connection)
        elif kind == "ping":
            await self.desktop.send("pong", payload, connection, message["message_id"])
        elif kind == "app.focus":
            changed = self.a11y.on_focus(payload)
            self.vision.on_focus(payload)
            if changed:
                self.ui_revision += 1
                self.router.recover("accessibility")
                self.invalidate_native()
                self.pause()
                if self.session and self.adapter is not self.plugin:
                    self.policy.set_step(self.session.step, self.session.generation)
            self.select_adapter()
        elif kind == "a11y.result":
            self.a11y.resolve(payload)
        elif kind == "permissions":
            self.permissions = payload.copy()
            self.a11y.permission = payload["accessibility"]
            self.vision.permission = payload["screen"]
            self.select_adapter()
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
        elif kind == "input.result" and payload.get("detail") == "rendered":
            started = self.render_pending.pop(payload["command_id"], None)
            if started is not None:
                self.metric("send→render_ack", (time.perf_counter() - started) * 1000)
                self.debug.record({"kind": "render_ack", "command_id": payload["command_id"]})
        elif kind in {"ptt.start", "audio.chunk", "ptt.stop"}:
            await self.audio_message(kind, payload, connection)

    async def authorize(self, payload: dict, connection) -> None:
        try:
            intent = json.loads(payload["text"])
            token = intent["consent_token"]
            UUID(token)
            undo = intent["intent"] == "annule"
            if undo and self.adapter is self.plugin:
                raise ValueError
            if (payload["source"] != "bouton" or intent["intent"] not in {"fais-le", "annule"}
                    or not self.session
                    or not self.app_ready()):
                raise ValueError
            if token in self.consent_tokens or len(self.consent_tokens.items) >= 4096:
                raise ValueError
            allowed = self.learner.can_delegate(
                self.session.step["skill_id"], confirmed=True,
                wants_to_learn=not (intent.get("delegation_confirmed") is True
                                    and intent.get("wants_to_learn") is False),
            )
            if not allowed or (not undo and self.session.status != "OBSERVING"):
                raise ValueError
            if self.adapter is not self.plugin:
                if self.action_task and not self.action_task.done():
                    raise ValueError
                if undo:
                    if not self.demo_undo or self.demo_undo[0] != self.a11y.focus_epoch:
                        raise ValueError
                elif self.demo_requested != (self.session.generation, self.a11y.focus_epoch):
                    raise ValueError
            self.consent_tokens.add(token)
            self.consent = (token, self.clock.monotonic() + 60, self.session.generation)
            if self.session.status == "OBSERVING":
                self.session.transition("ACTING")
            if self.adapter is not self.plugin:
                self.action_task = self.spawn(self.run_generic_demo(undo=undo))
            await self.send_state(connection)
        except (ValueError, KeyError, TypeError, AttributeError):
            await self.error("consent_required", "Confirmation de délégation requise", connection)

    async def input_action(self, action: dict) -> dict | None:
        async with self.action_lock:
            return await self._input_action(action)

    async def _input_action(self, action: dict, *, refresh: bool = True) -> dict | None:
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
        self.invalidate_capture()
        try:
            result = await self.desktop.correlation.request(
                command, lambda c: self.desktop.send("command", c),
            )
            if refresh and consent == self.consent and self.session.status == "ACTING":
                self.session.transition("CHECKING")
                self.session.transition("PAUSED")
                await self.request_refresh()
            return result
        except (TimeoutError, ConnectionError):
            self.consent = None
            self.pause()
            await self.error("input_failed", "Action interrompue ; vérifiez la scène")
            return None

    async def run_generic_demo(self, *, undo: bool = False) -> None:
        consent = self.consent
        epoch = self.a11y.focus_epoch
        generation = self.session.generation
        step = self.session.step

        def authorized() -> bool:
            return bool(consent and self.consent == consent
                        and self.clock.monotonic() < consent[1]
                        and epoch == self.a11y.focus_epoch and generation == self.session.generation
                        and self.app_ready()
                        and self.session.preconditions_hold(self.adapter.facts()))

        try:
            async with self.action_lock:
                if not authorized():
                    return
                if undo or self.adapter is self.a11y:
                    if not self.permissions["accessibility"]:
                        raise ValueError("Permission accessibilité requise")
                    target = self.demo_undo[1] if undo else step["target"]
                    action_step = {**step, "target": target}
                    await self.a11y.refresh(action_step)
                    hint = self.a11y.expected_rect(action_step)
                    plan = self.a11y.demo_plan(action_step) if not undo else None
                    if not hint or (not undo and plan is None):
                        raise ValueError("Cible ou procédure indisponible")
                    if not authorized():
                        return
                    action, value = self.demo_undo[2:] if undo else (plan.action, plan.value)
                    self.a11y.invalidate()
                    result = await self.a11y.act(hint.ref, action, consent[0], value)
                    if result.get("error"):
                        raise ValueError("Action accessibilité refusée")
                    if not undo and plan.undo:
                        self.demo_undo = (epoch, target, plan.undo, plan.previous)
                else:
                    if not self.policy.holo or not self.permissions["screen"]:
                        raise ValueError("Vision indisponible")
                    frame = await self.capture_window()
                    if frame is None or not authorized():
                        return
                    payload, image = frame
                    plan = self.vision.demo_plan(step)
                    point = await self.policy.holo.localize(
                        image, step["target"]["description"], timeout_s=self.config.holo_timeout_s)
                    rect = Rect.from_dict(payload["crop"])
                    hint = self.a11y.expected_rect(step)
                    region = step["check"]["params"].get("region")
                    expected = hint.rect.milli(rect) if hint else (
                        Rect.from_dict(region) if region else Rect(0, 0, 1000, 1000))
                    if (not point or not authorized() or point.target_visible is not True
                            or point.confidence is None or not math.isfinite(point.confidence)
                            or point.confidence < 0.5 or not 0 < point.x < 1000
                            or not 0 < point.y < 1000 or not rect.valid
                            or not expected.contains(point.x, point.y)):
                        raise ValueError("Point hors de la cible attendue")
                    self.capture = {**payload, "image_png": image, "consumed": False}
                    result = await self._input_action(
                        {"type": plan.action, "x": point.x, "y": point.y, "button": "left"},
                        refresh=False)
                    if not result or result.get("status") != "ok":
                        raise ValueError("Action native refusée")
                if not authorized():
                    return
                if undo:
                    self.demo_undo = None
                if self.session.status == "ACTING":
                    self.session.transition("CHECKING")
                    self.session.transition("PAUSED")
                self.a11y.invalidate()
                self.vision.invalidate()
                if undo:
                    await self.a11y.refresh(action_step)
                else:
                    await self.observe_once()
        except (ConnectionError, TimeoutError, ValueError):
            self.pause()
            await self.error("input_failed", "Démonstration interrompue ; vérification requise")
        except asyncio.CancelledError:
            self.pause()
            raise
        finally:
            self.consent = None
            self.demo_requested = None

    async def accept_capture(self, payload: dict) -> None:
        if (not self.permissions["screen"] or payload["capture_id"] in self.capture_ids
                or len(self.capture_ids.items) >= 4096):
            raise ValueError("Capture refusée")
        image = decode_capture(payload)
        if payload["ui_revision"] != self.ui_revision:
            raise ValueError("Capture périmée")
        window = self.window_requests.get(payload.get("request_id", ""))
        if window is not None:
            if self.window_epochs.get(payload["request_id"]) != self.vision.focus_epoch:
                raise ValueError("Capture périmée")
            self.capture_ids.add(payload["capture_id"])
            if not window.done():
                window.set_result((payload, image))
            return
        if (payload.get("request_id") or (self.session and self.session.status != "ACTING"
                and self.policy.level == 2 and self.session.step.get("help", {}).get("menu_id"))):
            request = self.pointer_request
            if (not request or payload.get("request_id") != request["request_id"]
                    or (request["crop"] is not None and payload["crop"] != request["crop"])
                    or self.session.generation != request["generation"]
                    or request["epoch"] != self.policy.capture_epoch
                    or time.monotonic() - request["at"] > 10):
                raise ValueError("Capture non corrélée au menu acquitté")
        self.invalidate_capture()
        self.capture_ids.add(payload["capture_id"])
        self.capture = {**payload, "image_png": image, "consumed": False}
        if self.session:
            crop = payload["crop"]
            target = TargetContext(
                self.app["id"], self.app_version(), (crop["width"], crop["height"]),
                payload["scale"],
                self.session.step["target"]["description"], (crop["x"], crop["y"]),
                payload["monitor_id"], self.session.lesson.get("language", "fr"),
                self.ui_revision, True,
                menu_context=payload.get("request_id", ""),
            )
            self.help_context = replace(self.context(), target=target,
                                        capture_id=payload["capture_id"], image_png=image,
                                        capture_epoch=self.policy.capture_epoch,
                                        require_visible=bool(self.pointer_request
                                            and self.pointer_request["crop"] is None),
                                        **self.target_hint(Rect.from_dict(crop)))
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

    def target_hint(self, frame: Rect) -> dict:
        """Zone attendue et point exact (a11y) exprimés en millièmes de la capture."""
        adapter = self.adapter
        hint = adapter.expected_rect(self.session.step) if adapter and self.session else None
        if not hint or not hint.rect or not frame.valid:
            return {}
        fields: dict = {"expected_rect": tuple(round(v, 3) for v in (
            *hint.rect.milli(frame).__dict__.values(),))}
        point = hint.rect.point_milli(frame) if hint.exact else None
        if point:
            fields["pointer"] = point
            if hint.ref and hint.snapshot_id:
                fields["pointer_ref"] = (hint.ref, hint.snapshot_id)
        return fields

    async def audio_message(self, kind: str, payload: dict, connection) -> None:
        key = payload["utterance_id"]
        if kind == "ptt.start":
            if (not self.permissions["microphone"] or len(self.utterances) >= 4
                    or len(self.live_utterances) >= 4 or key in self.utterances):
                raise ValueError("Microphone indisponible")
            self.utterances[key] = {"chunks": {}, "size": 0, "encoding": None, "sample_rate": None}
        elif key not in self.utterances:
            raise ValueError("Énoncé inconnu")
        elif kind == "audio.chunk":
            utterance = self.utterances[key]
            data = base64.b64decode(payload["data_base64"], validate=True)
            sequence = payload["sequence"]
            if callable(getattr(self.stt, "open_live", None)):
                if payload["encoding"] != "pcm_s16le":
                    raise ValueError("Le direct exige PCM 16 bits mono")
                if key not in self.live_utterances:
                    generation = self.session.generation if self.session else 0

                    async def on_event(event):
                        if self.session and generation != self.session.generation:
                            return
                        if event.kind in {"partial", "final"}:
                            self.debug.record({"kind": "stt_" + event.kind,
                                               "utterance_id": key, "t": time.monotonic()})
                            await self.send_state(force=True, transcript=event.text,
                                                  transcript_final=event.kind == "final")
                            if event.kind == "final" and event.text:
                                await self.policy.intent(event.text, self.context())

                    async def on_error():
                        await self.error("stt_live_failed", "Transcription interrompue", connection)

                    stream = LiveUtterance(self.stt, payload["sample_rate"], on_event, on_error,
                                           vocabulary=self.vocabulary())
                    self.live_utterances[key] = stream
                    utterance["sample_rate"] = payload["sample_rate"]
                stream = self.live_utterances[key]
                if payload["sample_rate"] != utterance["sample_rate"]:
                    raise ValueError("Format audio modifié")
                try:
                    stream.feed(sequence, data)
                except ValueError:
                    await stream.close()
                    self.live_utterances.pop(key, None)
                    self.utterances.pop(key, None)
                    raise
                return
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
            if key in self.live_utterances:
                stream = self.live_utterances[key]
                stream.stop()

                async def finish():
                    await stream.task
                    self.live_utterances.pop(key, None)

                self.spawn(finish())
                return
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
        await asyncio.gather(*(s.close() for s in self.live_utterances.values()))
        self.live_utterances.clear()
        for task in tuple(self.tasks):
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        await self.preloader.cancel()
        await asyncio.gather(self.desktop.close(), self.addon.close(), self.debug.close())
        self.learner.save()
