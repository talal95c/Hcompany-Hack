"""Gladia v2 live : PCM réel, streaming cadencé et horloges monotones locales."""

import asyncio
import json
import os
import struct
import time
import unicodedata
import wave
from pathlib import Path
from typing import Any

import httpx
from websockets.asyncio.client import connect

from bench.common import ROOT, statistics

CONFIG = {
    "model": "solaria-1",
    "encoding": "wav/pcm",
    "sample_rate": 16000,
    "bit_depth": 16,
    "channels": 1,
    "endpointing": 0.05,
    "language_config": {"languages": ["fr", "en"], "code_switching": True},
    "messages_config": {
        "receive_partial_transcripts": True,
        "receive_final_transcripts": True,
        "receive_lifecycle_events": True,
    },
}
METRICS = (
    "init_ms",
    "connect_ms",
    "first_audio_to_partial_ms",
    "onset_to_partial_ms",
    "audio_end_to_final_ms",
    "audio_end_to_session_end_ms",
)
BYTES_PER_SECOND = 32000


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text).lower()
    return " ".join("".join(c if c.isalnum() else " " for c in text).split())


def distance(reference: list | str, hypothesis: list | str) -> int:
    previous = list(range(len(hypothesis) + 1))
    for i, left in enumerate(reference, 1):
        current = [i]
        for j, right in enumerate(hypothesis, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (left != right)))
        previous = current
    return previous[-1]


def errors(reference: str, transcript: str) -> dict[str, Any]:
    ref, hyp = normalize(reference), normalize(transcript)
    words = ref.split()
    word_edits = distance(words, hyp.split())
    char_edits = distance(ref, hyp)
    return {
        "word_edits": word_edits,
        "reference_words": len(words),
        "wer": word_edits / len(words) if words else (0 if not hyp else None),
        "char_edits": char_edits,
        "reference_chars": len(ref),
        "cer": char_edits / len(ref) if ref else (0 if not hyp else None),
    }


def chunks(pcm: bytes) -> list[tuple[float, bytes]]:
    if len(pcm) % 2:
        raise ValueError("PCM must contain complete 16-bit samples")
    return [(i / BYTES_PER_SECOND, pcm[i : i + 3200]) for i in range(0, len(pcm), 3200)]


def speech_onset(pcm: bytes, threshold: int = 500) -> float | None:
    return next(
        (
            i / 16000
            for i, (sample,) in enumerate(struct.iter_unpack("<h", pcm))
            if abs(sample) >= threshold
        ),
        None,
    )


def parse_message(raw: str | bytes) -> dict[str, Any] | None:
    try:
        event = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(event, dict) or not isinstance(event.get("type"), str):
        return None
    kind = event["type"]
    if kind == "transcript":
        data = event.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("is_final"), bool):
            return None
        utterance = data.get("utterance")
        if not isinstance(utterance, dict) or not isinstance(utterance.get("text"), str):
            return None
        if not isinstance(data.get("id"), str):
            return None
        return {
            "type": kind,
            "id": data["id"],
            "is_final": data["is_final"],
            "text": utterance["text"],
        }
    return {"type": kind, "error": bool(event.get("error")) or kind == "error"}


async def stream(url: str, pcm: bytes, timeout: float = 30) -> dict[str, Any]:
    stamps: dict[str, float] = {}
    events = []
    finals: dict[str, str] = {}
    sends = []
    invalid = 0
    connect_started = time.monotonic()
    async with connect(url, open_timeout=timeout, close_timeout=3) as socket:
        connect_ms = (time.monotonic() - connect_started) * 1000

        async def send_audio() -> None:
            start = time.monotonic()
            for offset, block in chunks(pcm):
                await asyncio.sleep(max(0, start + offset - time.monotonic()))
                sent = time.monotonic()
                stamps.setdefault("first_audio", sent)
                await socket.send(block)
                stamps["audio_end"] = time.monotonic()
                sends.append({"offset_s": offset, "sent_monotonic_s": sent, "bytes": len(block)})
            await asyncio.sleep(max(0, start + len(pcm) / BYTES_PER_SECOND - time.monotonic()))
            await socket.send(json.dumps({"type": "stop_recording"}))

        async def receive() -> None:
            nonlocal invalid
            while True:
                raw = await socket.recv()
                received = time.monotonic()
                event = parse_message(raw)
                if event is None:
                    invalid += 1
                    continue
                events.append({**event, "received_monotonic_s": received})
                if event.get("error"):
                    raise RuntimeError("Gladia reported a session error")
                if event["type"] == "transcript" and event["text"].strip():
                    if event["is_final"]:
                        finals[event["id"]] = event["text"]
                        stamps["final"] = received
                    else:
                        stamps.setdefault("partial", received)
                if event["type"] == "end_session":
                    stamps["session_end"] = received
                    return

        sender = asyncio.create_task(send_audio())
        receiver = asyncio.create_task(receive())
        try:
            async with asyncio.timeout(timeout):
                await asyncio.gather(sender, receiver)
        finally:
            for task in (sender, receiver):
                task.cancel()
            await asyncio.gather(sender, receiver, return_exceptions=True)
    onset = speech_onset(pcm)

    def delta(end: str, start: str) -> float | None:
        return (stamps[end] - stamps[start]) * 1000 if end in stamps and start in stamps else None

    partial_ms = delta("partial", "first_audio")
    return {
        "connect_ms": connect_ms,
        "first_audio_to_partial_ms": partial_ms,
        "onset_to_partial_ms": partial_ms - onset * 1000
        if partial_ms is not None and onset is not None
        else None,
        "audio_end_to_final_ms": delta("final", "audio_end"),
        "audio_end_to_session_end_ms": delta("session_end", "audio_end"),
        "speech_onset_s": onset,
        "transcript": " ".join(finals.values()),
        "events": events,
        "timestamps_monotonic_s": stamps,
        "chunks": sends,
        "malformed_messages": invalid,
    }


def audio(row: dict[str, str]) -> bytes:
    with wave.open(str(ROOT / "bench/data" / f"gladia-{row['id']}.wav"), "rb") as wav:
        if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (16000, 1, 2):
            raise ValueError("Expected 16 kHz mono 16-bit WAV")
        return wav.readframes(wav.getnframes())


async def session(http: httpx.AsyncClient, row: dict[str, str], timeout: float) -> dict[str, Any]:
    key = os.environ.get("GLADIA_API_KEY")
    if not key:
        raise ValueError("GLADIA_API_KEY is required")
    pcm = audio(row)
    started = time.monotonic()
    response = await http.post(
        "https://api.gladia.io/v2/live", json=CONFIG, headers={"x-gladia-key": key}
    )
    init_ms = (time.monotonic() - started) * 1000
    if response.status_code not in (200, 201):
        raise RuntimeError(f"Gladia init HTTP {response.status_code}")
    initialized = response.json()
    measured = await stream(initialized["url"], pcm, timeout)
    return {
        "id": row["id"],
        "reference": row["text"],
        "session_id": initialized["id"],
        "init_ms": init_ms,
        "init_status": response.status_code,
        "audio_seconds": len(pcm) / BYTES_PER_SECOND,
        **measured,
        **errors(row["text"], measured["transcript"]),
    }


def summarize(samples: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = {
        name: statistics([s[name] for s in samples if s.get(name) is not None]) for name in METRICS
    }
    seconds = sum(s["audio_seconds"] for s in samples)
    words = sum(s["reference_words"] for s in samples)
    chars = sum(s["reference_chars"] for s in samples)
    lines = ["## Latences", "", "| Mesure | N | p50 ms | p95 ms |", "|---|---:|---:|---:|"]
    lines += [
        f"| {name} | {m['count']} | {m['p50_ms']} | {m['p95_ms']} |" for name, m in metrics.items()
    ]
    lines += [
        "",
        "## Transcriptions",
        "",
        "| Clip / répétition | Référence | Final | WER | CER |",
        "|---|---|---|---:|---:|",
    ]
    lines += [
        f"| {s['id']} / {s['repeat']} | {s['reference']} | {s['transcript']} | "
        f"{s['wer']:.1%} | {s['cer']:.1%} |"
        for s in samples
    ]
    return {
        "summary": {
            "sessions": len(samples),
            "audio_seconds": seconds,
            "cost_eur_computed": seconds / 3600 * 0.68,
            "wer": sum(s["word_edits"] for s in samples) / words if words else None,
            "cer": sum(s["char_edits"] for s in samples) / chars if chars else None,
            "missing_partials": sum(s.get("first_audio_to_partial_ms") is None for s in samples),
        },
        "metrics": metrics,
        "raw_samples": samples,
        "configuration": CONFIG,
        "notes": [
            "Mesures réelles sur voix française synthétique offline Piper siwis medium, "
            "pas sur des apprenants ni un microphone réel. Coût calculé à 0,68 €/h audio, "
            "pas une facture ni une mesure de tarification/minimum fournisseur.",
            "PCM brut 16 kHz mono 16-bit, blocs 100 ms (dernier bloc éventuellement court). "
            "Horloge monotone locale ; onset = premier sample |amplitude| ≥ 500, "
            "sur la timeline audio ancrée au premier envoi. Pas une détection VAD clinique.",
            "Fin audio = retour du dernier send PCM, pas stop_recording ni fin acoustique. "
            "Final = dernier transcript final reçu ; segments dédupliqués par ID. Une valeur "
            "négative signifie un final reçu pendant l'envoi (silence de fin possible). "
            "Les partiels absents restent null, jamais remplacés par un final.",
            "WER/CER : distance de Levenshtein, Unicode NFC/minuscules, ponctuation et "
            "apostrophes remplacées par espaces, accents conservés ; CER espaces inclus. "
            "Agrégat pondéré par longueur des références, sans correction métier.",
            "\n".join(lines),
        ],
    }


async def run(*, out: Path = Path("bench/results"), timeout: float = 30) -> dict[str, Any]:
    rows = json.loads((ROOT / "bench/data/gladia_references.json").read_text())
    samples = []
    out.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=timeout) as http:
        with (out / "gladia-calls.jsonl").open("w") as log:
            for row in rows:
                for repeat in range(1, 4):
                    sample = await session(http, row, timeout)
                    sample["repeat"] = repeat
                    samples.append(sample)
                    log.write(json.dumps(sample, ensure_ascii=False) + "\n")
                    log.flush()
    return summarize(samples)
