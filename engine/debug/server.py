"""Chronologie locale expurgée et métriques à mémoire bornée."""

import asyncio
import json
import math
from collections import defaultdict, deque
from dataclasses import asdict, is_dataclass
from http import HTTPStatus
from urllib.parse import urlsplit

from websockets.asyncio.server import serve
from websockets.datastructures import Headers
from websockets.exceptions import ConnectionClosed
from websockets.http11 import Response

from engine.bus.servers import ORIGINS

PAGE = """<!doctype html><html lang="fr"><meta charset="utf-8">
<title>Engine — diagnostic local</title><style>
body{background:#111827;color:#e5e7eb;font:15px monospace;margin:2rem}
pre{white-space:pre-wrap}h1{color:#fbbf24}</style>
<h1>Diagnostic du moteur</h1><p id="status">Connexion…</p><pre id="events"></pre>
<script>
const output=document.getElementById('events');
const socket=new WebSocket('ws://'+location.host+'/ws');
socket.onopen=()=>document.getElementById('status').textContent='Connecté';
socket.onclose=()=>document.getElementById('status').textContent='Déconnecté';
socket.onmessage=e=>{let lines=output.textContent.split('\\n');
lines.push(JSON.stringify(JSON.parse(e.data)));output.textContent=lines.slice(-300).join('\\n');};
</script></html>"""


def redact(value):
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, dict):
        forbidden = {"payload", "text", "instruction", "hint", "rationale", "image_png",
                     "image_ref", "audio", "data_base64", "data", "session_token",
                     "consent_token", "token", "authorization", "key", "api_key"}
        return {k: redact(v) for k, v in value.items() if k.casefold() not in forbidden
                and "token" not in k.casefold() and "secret" not in k.casefold()
                and not k.casefold().endswith("_key")}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value[:128]]
    if isinstance(value, bytes):
        return "[binaire supprimé]"
    if isinstance(value, str):
        return "[contenu supprimé]" if "data:" in value or "Bearer " in value else value[:500]
    return value


class DebugServer:
    def __init__(self, host: str, port: int, capacity: int = 512):
        self.host, self.requested_port = host, port
        self.events: deque[dict] = deque(maxlen=capacity)
        self.samples: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=capacity))
        self.queues: set[asyncio.Queue] = set()
        self.server = None

    def record(self, event: dict) -> None:
        safe = redact(event)
        self.events.append(safe)
        if event.get("kind") == "latency":
            name = event.get("service", event.get("stage", "other"))
            value = event.get("latency_ms")
            if isinstance(value, (int, float)) and math.isfinite(value) and len(self.samples) < 64:
                self.samples[name].append(value)
        for queue in tuple(self.queues):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(safe)

    def metrics(self) -> dict:
        result = {}
        for name, values in self.samples.items():
            ordered = sorted(values)
            if ordered:
                result[name] = {"count": len(ordered), "p50": ordered[(len(ordered) - 1) // 2],
                                "p95": ordered[math.ceil(len(ordered) * 0.95) - 1],
                                "max": ordered[-1]}
        return result

    def request(self, connection, request):
        if request.headers.get("Origin") not in ORIGINS | {f"http://{self.host}:{self.port}"}:
            return connection.respond(403, "Origine refusée\n")
        path = urlsplit(request.path).path
        if path == "/ws" and request.headers.get("Upgrade", "").lower() == "websocket":
            return None
        status = HTTPStatus.OK if path in {"/", "/metrics"} else HTTPStatus.NOT_FOUND
        body = PAGE if path == "/" else (
            json.dumps(self.metrics()) if path == "/metrics" else "Absent"
        )
        data = body.encode()
        return Response(status.value, status.phrase, Headers({
            "Content-Type": "text/html; charset=utf-8" if path == "/" else "application/json",
            "Content-Length": str(len(data)), "Connection": "close",
            "Cache-Control": "no-store",
        }), data)

    async def handle(self, connection) -> None:
        queue: asyncio.Queue = asyncio.Queue(128)
        self.queues.add(queue)
        try:
            for event in tuple(self.events):
                await asyncio.wait_for(connection.send(json.dumps(event)), 0.5)
            while True:
                event_task = asyncio.create_task(queue.get())
                close_task = asyncio.create_task(connection.wait_closed())
                try:
                    done, _ = await asyncio.wait(
                        [event_task, close_task], return_when=asyncio.FIRST_COMPLETED,
                    )
                    if close_task in done:
                        break
                    await asyncio.wait_for(connection.send(json.dumps(event_task.result())), 0.5)
                finally:
                    event_task.cancel()
                    close_task.cancel()
                    await asyncio.gather(event_task, close_task, return_exceptions=True)
        except (ConnectionClosed, TimeoutError):
            pass
        finally:
            self.queues.discard(queue)

    async def start(self) -> None:
        self.server = await serve(self.handle, self.host, self.requested_port,
                                  process_request=self.request, close_timeout=0.2)

    @property
    def port(self) -> int:
        return self.server.sockets[0].getsockname()[1]

    async def close(self) -> None:
        if self.server:
            self.server.close()
            await self.server.wait_closed()
