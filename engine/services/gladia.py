"""Client Gladia v2 : STT live (WebSocket, partiels + endpointing) et fichier pré-enregistré."""

from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
import json
import os
import time
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any

import httpx
import websockets
from websockets.asyncio.client import ClientConnection

from engine.services.errors import (
    InvalidResponse,
    ServiceError,
    ServiceTimeout,
    ServiceUnavailable,
    error_for_status,
)
from engine.services.latency import CallRecord, LatencyRecorder
from engine.services.profiles import AppProfile, load_profile
from engine.services.protocols import SttEvent, Transcript, Word

SERVICE = "gladia"
DEFAULT_BASE_URL = "https://api.gladia.io/v2"
DEFAULT_VOCABULARY = ()


def _words(raw: Any) -> tuple[Word, ...]:
    out = []
    for w in raw or []:
        if isinstance(w, Mapping) and "word" in w:
            out.append(
                Word(
                    word=str(w["word"]).strip(),
                    start=float(w.get("start", 0.0)),
                    end=float(w.get("end", 0.0)),
                    confidence=float(w.get("confidence", 0.0)),
                )
            )
    return tuple(out)


def _vocab_config(vocabulary: Sequence[str]) -> dict[str, Any]:
    return {"vocabulary": [v for v in dict.fromkeys(vocabulary) if v.strip()]}


def decode_audio_chunk(message: Mapping[str, Any], *, sample_rate: int = 16000) -> bytes:
    """Message desktop-ws `audio.chunk` (déjà validé par le bus) → PCM brut pour Gladia."""
    if message.get("type") != "audio.chunk":
        raise ValueError("message attendu: audio.chunk")
    payload = message["payload"]
    if payload.get("encoding") != "pcm_s16le":
        raise ValueError(f"encodage non supporté {payload.get('encoding')!r}")
    if payload.get("sample_rate") != sample_rate:
        raise ValueError(f"sample_rate {payload.get('sample_rate')} != session {sample_rate}")
    try:
        return base64.b64decode(payload["data_base64"], validate=True)
    except binascii.Error as exc:
        raise ValueError("data_base64 invalide") from exc


def parse_live_message(msg: Mapping[str, Any], received_at: float) -> SttEvent | None:
    """Message WebSocket Gladia → SttEvent (None pour les messages ignorés)."""
    mtype = msg.get("type")
    data = msg.get("data") if isinstance(msg.get("data"), Mapping) else {}
    if mtype == "transcript":
        utt = data.get("utterance") or {}
        return SttEvent(
            kind="final" if data.get("is_final") else "partial",
            utterance_id=data.get("id"),
            text=str(utt.get("text", "")).strip(),
            words=_words(utt.get("words")),
            start=utt.get("start"),
            end=utt.get("end"),
            language=utt.get("language"),
            received_at=received_at,
            raw_type=mtype,
        )
    if mtype in ("speech_start", "speech_end"):
        return SttEvent(
            kind=mtype,
            start=data.get("time"),
            received_at=received_at,
            raw_type=mtype,
        )
    if mtype == "end_session":
        return SttEvent(kind="ended", received_at=received_at, raw_type=mtype)
    if mtype == "error" or msg.get("error"):
        return SttEvent(
            kind="error", text=json.dumps(msg)[:500], received_at=received_at, raw_type=str(mtype)
        )
    return None


class GladiaLiveSession:
    """Session live : `send_audio` (PCM 16 bits mono) → `events()` (partiels, finals, VAD).

    Mesure par énoncé : délai entre le dernier chunk envoyé avant `speech_end` et le final.
    """

    def __init__(self, ws: ClientConnection, session_id: str, recorder: LatencyRecorder) -> None:
        self.session_id = session_id
        self._ws = ws
        self._recorder = recorder
        self._queue: asyncio.Queue[SttEvent | None] = asyncio.Queue()
        self._last_audio_at: float | None = None
        self._first_partial_pending = True
        self._stopped = False
        self._closing: asyncio.Task | None = None
        self._utterance_audio_start: float | None = None
        self._reader = asyncio.create_task(self._read())

    async def _read(self) -> None:
        try:
            async for raw in self._ws:
                if isinstance(raw, bytes):
                    continue
                now = time.perf_counter()
                event = parse_live_message(json.loads(raw), now)
                if event is None:
                    continue
                self._observe(event)
                await self._queue.put(event)
                if event.kind == "ended":
                    break
        except websockets.ConnectionClosed:
            pass
        finally:
            await self._queue.put(None)

    def _observe(self, event: SttEvent) -> None:
        if event.kind == "speech_start":
            self._utterance_audio_start = self._last_audio_at
            self._first_partial_pending = True
        elif event.kind == "partial" and self._first_partial_pending and self._last_audio_at:
            self._first_partial_pending = False
        elif event.kind == "final" and self._last_audio_at is not None:
            self._recorder.add(
                CallRecord(
                    SERVICE,
                    "live_final_after_last_chunk",
                    round((event.received_at - self._last_audio_at) * 1000, 2),
                    "ok",
                    request_id=self.session_id,
                )
            )

    async def send_audio(self, chunk: bytes) -> None:
        if chunk:
            await self._ws.send(chunk)
            self._last_audio_at = time.perf_counter()

    @property
    def closed(self) -> bool:
        return self._reader.done()

    async def stop(self) -> None:
        """Demande la fin d'enregistrement ; les derniers finals arrivent ensuite."""
        if self._stopped:
            return
        self._stopped = True
        with contextlib.suppress(websockets.ConnectionClosed):
            await self._ws.send(json.dumps({"type": "stop_recording"}))

    async def events(self) -> AsyncIterator[SttEvent]:
        while True:
            event = await self._queue.get()
            if event is None:
                return
            yield event
            if event.kind == "ended":
                return

    async def aclose(self) -> None:
        if self._closing is None:
            self._closing = asyncio.create_task(self._close())
        try:
            await asyncio.shield(self._closing)
        except asyncio.CancelledError:
            await self._closing
            raise

    async def _close(self) -> None:
        try:
            try:
                await self.stop()
            finally:
                await self._ws.close()
        finally:
            self._reader.cancel()
            await asyncio.gather(self._reader, return_exceptions=True)


class GladiaSttClient:
    """SttClient réel Gladia v2."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        profile: AppProfile | None = None,
        base_url: str = DEFAULT_BASE_URL,
        recorder: LatencyRecorder | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        poll_interval_s: float = 0.5,
        file_timeout_s: float = 120.0,
    ) -> None:
        key = api_key or os.environ.get("GLADIA_API_KEY")
        if not key:
            raise ServiceUnavailable(SERVICE, "GLADIA_API_KEY absent")
        self.recorder = recorder or LatencyRecorder()
        self.profile = profile or load_profile(None)
        self.poll_interval_s = poll_interval_s
        self.file_timeout_s = file_timeout_s
        self._http = httpx.AsyncClient(
            base_url=base_url,
            transport=transport,
            headers={"x-gladia-key": key},
            timeout=httpx.Timeout(30.0, connect=10.0),
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> GladiaSttClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def _request(self, op: str, method: str, url: str, **kw: Any) -> dict[str, Any]:
        with self.recorder.measure(SERVICE, op) as ctx:
            try:
                resp = await self._http.request(method, url, **kw)
            except httpx.TimeoutException as exc:
                raise ServiceTimeout(SERVICE, f"{op} trop long") from exc
            except httpx.TransportError as exc:
                raise ServiceUnavailable(SERVICE, f"transport: {exc}") from exc
            ctx.request_id = resp.headers.get("x-request-id")
            if resp.status_code not in (200, 201):
                error = error_for_status(
                    SERVICE, resp.status_code, resp.text, request_id=ctx.request_id
                )
                try:
                    error.retry_after = max(0, float(resp.headers.get("retry-after", "0")))
                except ValueError:
                    pass
                raise error
            try:
                body = resp.json()
            except ValueError as exc:
                raise InvalidResponse(SERVICE, f"{op}: JSON invalide") from exc
            if not isinstance(body, dict):
                raise InvalidResponse(SERVICE, f"{op}: réponse non objet")
            ctx.request_id = ctx.request_id or body.get("id")
            return body

    def live_config(
        self,
        *,
        language: str = "fr",
        vocabulary: Sequence[str] | None = None,
        endpointing_s: float = 0.3,
        max_without_endpointing_s: float = 8.0,
        sample_rate: int = 16000,
    ) -> dict[str, Any]:
        vocabulary = self.profile.vocabulary if vocabulary is None else vocabulary
        config: dict[str, Any] = {
            "encoding": "wav/pcm",
            "sample_rate": sample_rate,
            "bit_depth": 16,
            "channels": 1,
            "endpointing": endpointing_s,
            "maximum_duration_without_endpointing": max_without_endpointing_s,
            "language_config": {"languages": [language], "code_switching": False},
            "messages_config": {
                "receive_partial_transcripts": True,
                "receive_final_transcripts": True,
                "receive_speech_events": True,
                "receive_lifecycle_events": True,
            },
        }
        if vocabulary:
            config["realtime_processing"] = {
                "custom_vocabulary": True,
                "custom_vocabulary_config": _vocab_config(vocabulary),
            }
        return config

    async def open_live(self, **config_kw: Any) -> GladiaLiveSession:
        """`POST /v2/live` puis connexion WebSocket à l'URL renvoyée."""
        init = await self._request("live_init", "POST", "/live", json=self.live_config(**config_kw))
        url, sid = init.get("url"), init.get("id")
        if not url or not sid:
            raise InvalidResponse(SERVICE, "live: url/id absents")
        with self.recorder.measure(SERVICE, "live_ws_connect") as ctx:
            ctx.request_id = sid
            try:
                ws = await asyncio.wait_for(websockets.connect(url, max_size=2**22), 10)
            except (OSError, TimeoutError, websockets.InvalidHandshake) as exc:
                raise ServiceUnavailable(SERVICE, f"websocket: {exc}") from exc
        return GladiaLiveSession(ws, sid, self.recorder)

    async def transcribe_file(
        self,
        audio: bytes,
        *,
        filename: str,
        vocabulary: Sequence[str] | None = None,
        language: str = "fr",
        content_type: str = "audio/wav",
    ) -> Transcript:
        """Upload → job pré-enregistré → polling ; renvoie texte + timestamps par mot."""
        if not audio:
            raise ValueError("audio vide")
        vocabulary = self.profile.vocabulary if vocabulary is None else vocabulary
        start = time.perf_counter()
        upload = await self._request(
            "upload", "POST", "/upload", files={"audio": (filename, audio, content_type)}
        )
        audio_url = upload.get("audio_url")
        if not audio_url:
            raise InvalidResponse(SERVICE, "upload: audio_url absent")
        body: dict[str, Any] = {
            "audio_url": audio_url,
            "language_config": {"languages": [language], "code_switching": False},
        }
        if vocabulary:
            body["custom_vocabulary"] = True
            body["custom_vocabulary_config"] = _vocab_config(vocabulary)
        job = await self._request("prerecorded_create", "POST", "/pre-recorded", json=body)
        job_id = job.get("id")
        if not job_id:
            raise InvalidResponse(SERVICE, "pre-recorded: id absent")
        deadline = start + self.file_timeout_s
        while True:
            result = await self._request("prerecorded_poll", "GET", f"/pre-recorded/{job_id}")
            status = result.get("status")
            if status == "done":
                break
            if status == "error":
                raise ServiceError(
                    SERVICE,
                    f"job {job_id} en erreur: {result.get('error_code')}",
                    request_id=job_id,
                )
            if time.perf_counter() > deadline:
                raise ServiceTimeout(
                    SERVICE, f"job {job_id} > {self.file_timeout_s}s", request_id=job_id
                )
            await asyncio.sleep(self.poll_interval_s)
        self.recorder.add(
            CallRecord(
                SERVICE,
                "transcribe_file_total",
                round((time.perf_counter() - start) * 1000, 2),
                "ok",
                request_id=job_id,
            )
        )
        return parse_prerecorded(result, job_id)


def parse_prerecorded(result: Mapping[str, Any], job_id: str | None = None) -> Transcript:
    transcription = ((result.get("result") or {}).get("transcription")) or {}
    utterances = transcription.get("utterances") or []
    words: list[Word] = []
    for utt in utterances:
        words.extend(_words(utt.get("words")))
    text = str(
        transcription.get("full_transcript")
        or " ".join(str(u.get("text", "")).strip() for u in utterances)
    ).strip()
    languages = transcription.get("languages") or []
    metadata = (result.get("result") or {}).get("metadata") or {}
    return Transcript(
        text=text,
        words=tuple(words),
        language=languages[0] if languages else None,
        job_id=job_id,
        duration_s=metadata.get("audio_duration"),
    )
