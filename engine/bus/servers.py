"""Transports locaux validés, déduplication et corrélation bornées."""

import asyncio
import json
import secrets
from collections import OrderedDict, deque
from collections.abc import Awaitable, Callable
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from jsonschema import ValidationError
from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from engine.bus.validation import validate
from engine.config import EngineConfig

ORIGINS = {None, "tauri://localhost", "http://tauri.localhost"}
MAX_LINE = 1024 * 1024


class Seen:
    def __init__(self, capacity: int = 4096):
        self.capacity = capacity
        self.items: OrderedDict[str, object] = OrderedDict()

    def add(self, key: str, value: object = True) -> None:
        self.items[key] = value
        self.items.move_to_end(key)
        if len(self.items) > self.capacity:
            self.items.popitem(last=False)

    def __contains__(self, key: str) -> bool:
        return key in self.items


class Correlator:
    def __init__(self):
        self.pending: dict[str, asyncio.Future] = {}
        self.results = Seen()

    def resolve(self, result: dict) -> None:
        key = result["command_id"]
        if key not in self.pending:
            return
        self.results.add(key, result)
        future = self.pending[key]
        if not future.done():
            future.set_result(result)

    async def request(self, command: dict, send: Callable[[dict], Awaitable[None]]) -> dict:
        key = command["command_id"]
        if key in self.results:
            return self.results.items[key]
        if key in self.pending:
            return await asyncio.shield(self.pending[key])
        if len(self.pending) >= 256:
            raise RuntimeError("Trop de commandes en attente")
        future = asyncio.get_running_loop().create_future()
        self.pending[key] = future
        try:
            await send(command)
            return await asyncio.wait_for(asyncio.shield(future), command["deadline_ms"] / 1000)
        except (TimeoutError, ConnectionError):
            self.results.add(key, {"command_id": key, "status": "expired",
                                   "detail": "Résultat incertain ; resynchronisation requise",
                                   "scene_revision": command.get("expected_scene_revision") or 0})
            raise
        finally:
            self.pending.pop(key, None)
            if not future.done():
                future.cancel()
            elif not future.cancelled():
                future.exception()

    def disconnect(self) -> None:
        for future in self.pending.values():
            if not future.done():
                future.set_exception(ConnectionError("Client déconnecté"))


class EventBuffer:
    def __init__(self, capacity: int = 128):
        self.capacity = capacity
        self.events: deque[dict] = deque()
        self.condition = asyncio.Condition()

    async def put(self, event: dict) -> None:
        async with self.condition:
            if (self.events and event["type"] == self.events[-1]["type"] == "scene.changed"
                    and self.events[-1]["scene_revision"] <= event["scene_revision"]
                    <= self.events[-1]["scene_revision"] + 1
                    and event.get("connection_epoch") == self.events[-1].get("connection_epoch")):
                previous = self.events.pop()
                objects = {o["id"]: o for o in previous["payload"]["objects"] if "id" in o}
                for key in event["payload"]["changed_ids"]:
                    objects.pop(key, None)
                objects.update({o["id"]: o for o in event["payload"]["objects"] if "id" in o})
                event = {**event, "payload": {
                    "changed_ids": list(dict.fromkeys(previous["payload"]["changed_ids"]
                                                      + event["payload"]["changed_ids"])),
                    "objects": list(objects.values()),
                }, "base_revision": previous.get("base_revision", previous["scene_revision"])}
            else:
                await self.condition.wait_for(lambda: len(self.events) < self.capacity)
            self.events.append(event)
            self.condition.notify_all()

    async def get(self) -> dict:
        async with self.condition:
            await self.condition.wait_for(lambda: bool(self.events))
            event = self.events.popleft()
            self.condition.notify_all()
            return event


class AddonServer:
    def __init__(
        self, config: EngineConfig, on_event: Callable[[dict], Awaitable[None]],
        on_connect: Callable[[], Awaitable[None]],
        on_disconnect: Callable[[], Awaitable[None]], report: Callable[[dict], None],
    ):
        self.config, self.on_event = config, on_event
        self.on_connect, self.on_disconnect, self.report = on_connect, on_disconnect, report
        self.server: asyncio.Server | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.writers: set[asyncio.StreamWriter] = set()
        self.tasks: set[asyncio.Task] = set()
        self.seen = Seen()
        self.correlation = Correlator()

    async def start(self) -> None:
        self.server = await asyncio.start_server(
            self.handle, self.config.host, self.config.addon_port, limit=MAX_LINE,
        )

    @property
    def port(self) -> int:
        return self.server.sockets[0].getsockname()[1]

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        self.tasks.add(task)
        self.writers.add(writer)
        authenticated = False
        sequence: int | None = None
        try:
            while True:
                line = await asyncio.wait_for(reader.readline(), 10 if not authenticated else 60)
                if not line:
                    break
                if len(line) > MAX_LINE or not line.endswith(b"\n"):
                    raise ValueError("Ligne invalide")
                event = json.loads(line.decode("utf-8"))
                validate("addon-events", event)
                if event["session_id"] != self.config.session_id:
                    raise ValueError("Session invalide")
                if not authenticated:
                    if event["type"] != "hello":
                        raise ValueError("Hello requis")
                    if self.writer:
                        self.writer.close()
                    self.writer = writer
                    authenticated = True
                    sequence = event["seq"]
                    await self.on_connect()
                elif self.writer is not writer:
                    break
                if event["event_id"] in self.seen:
                    continue
                self.seen.add(event["event_id"])
                if event["type"] != "hello" and sequence is not None:
                    if event["seq"] <= sequence:
                        continue
                    if event["seq"] != sequence + 1:
                        self.report({"kind": "seq_gap", "expected": sequence + 1})
                        await self.on_connect()
                sequence = event["seq"]
                if event["type"] == "command.result":
                    self.correlation.resolve(event["payload"])
                await self.on_event(event)
        except (ValueError, UnicodeError, ValidationError, TimeoutError, ConnectionError):
            self.report({"kind": "invalid_addon_or_disconnect"})
        finally:
            if self.writer is writer:
                self.writer = None
                self.correlation.disconnect()
                await self.on_disconnect()
            writer.close()
            await writer.wait_closed()
            self.writers.discard(writer)
            self.tasks.discard(task)

    async def send(self, command: dict) -> None:
        validate("commands", command)
        if command["recipient"] != "addon":
            raise ValueError("Destinataire invalide")
        if not self.writer:
            raise ConnectionError("Add-on absent")
        self.writer.write((json.dumps(command, ensure_ascii=False) + "\n").encode())
        await self.writer.drain()

    async def close(self) -> None:
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        for writer in tuple(self.writers):
            writer.close()
        for task in tuple(self.tasks):
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)


class DesktopServer:
    def __init__(
        self, config: EngineConfig,
        handler: Callable[[dict, ServerConnection], Awaitable[None]],
        disconnected: Callable[[], Awaitable[None]], report: Callable[[dict], None],
    ):
        self.config, self.handler, self.disconnected, self.report = (
            config, handler, disconnected, report,
        )
        self.server = None
        self.clients: set[ServerConnection] = set()
        self.correlation = Correlator()

    def handshake(self, connection, request):
        if request.headers.get("Origin") not in ORIGINS:
            return connection.respond(403, "Origine refusée\n")
        header = request.headers.get("Authorization", "")
        query = parse_qs(urlsplit(request.path).query).get("token", [""])[0]
        token = header.removeprefix("Bearer ") if header.startswith("Bearer ") else query
        if not secrets.compare_digest(token, self.config.session_token):
            return connection.respond(401, "Authentification requise\n")
        return None

    async def start(self) -> None:
        self.server = await serve(
            self.handle, self.config.host, self.config.port, process_request=self.handshake,
            max_size=8 * MAX_LINE, close_timeout=0.2,
        )

    @property
    def port(self) -> int:
        return self.server.sockets[0].getsockname()[1]

    async def handle(self, connection: ServerConnection) -> None:
        seen = Seen()
        hello = False
        try:
            async for raw in connection:
                try:
                    message = json.loads(raw)
                    validate("desktop-ws", message)
                    if message["session_id"] != self.config.session_id:
                        raise ValueError("Session invalide")
                    if message["type"] not in {
                        "hello", "permissions", "ping", "pong", "user.intent", "input.result",
                        "capture.result", "ptt.start", "ptt.stop", "audio.chunk", "error",
                        "a11y.result", "a11y.event", "app.focus",
                    }:
                        raise ValueError("Direction invalide")
                    if not hello and message["type"] != "hello":
                        raise ValueError("Hello requis")
                    if message["message_id"] in seen:
                        continue
                    seen.add(message["message_id"])
                    hello = True
                    self.clients.add(connection)
                    if message["type"] == "input.result":
                        self.correlation.resolve(message["payload"])
                    await self.handler(message, connection)
                except (ValueError, UnicodeError, ValidationError):
                    self.report({"kind": "invalid_desktop"})
                    await self.send("error", {"code": "invalid_message",
                                    "message": "Message invalide", "retryable": True}, connection)
        except ConnectionClosed:
            pass
        finally:
            self.clients.discard(connection)
            self.correlation.disconnect()
            await self.disconnected()

    async def send(
        self, kind: str, payload: dict, connection: ServerConnection | None = None,
        reply_to: str | None = None,
    ) -> None:
        message = {"schema_version": "1.0", "session_id": self.config.session_id,
                   "message_id": str(uuid4()), "reply_to": reply_to, "type": kind,
                   "payload": payload}
        validate("desktop-ws", message)
        targets = [connection] if connection else tuple(self.clients)
        for client in targets:
            try:
                await asyncio.wait_for(client.send(json.dumps(message, ensure_ascii=False)), 0.5)
            except (ConnectionClosed, TimeoutError):
                self.clients.discard(client)

    async def close(self) -> None:
        if self.server:
            self.server.close()
            await self.server.wait_closed()
