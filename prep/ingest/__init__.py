"""Ingestion bornée et transcription Gladia v2."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    import httpx

LOGGER = logging.getLogger(__name__)
DEFAULT_VOCABULARY = (
    "Blender",
    "Add",
    "Mesh",
    "Torus",
    "Cube",
    "UV Sphere",
    "Icosphere",
    "Cylinder",
    "Cone",
    "Plane",
    "Monkey",
    "Circle",
    "Grid",
    "Ajouter",
    "Maillage",
    "Tore",
    "Sphère UV",
    "Cylindre",
    "Plan",
)


@dataclass
class Transcript:
    text: str
    language: str
    segments: list[dict]
    source_uri: str
    sha256: str
    gladia_job_id: str | None
    latencies: dict[str, float]

    def to_dict(self) -> dict:
        return asdict(self)


class TranscriptionTimeout(TimeoutError):
    def __init__(self, job_id: str | None) -> None:
        self.job_id = job_id
        super().__init__(f"Transcription Gladia : délai dépassé (job {job_id or 'non créé'})")


def vocabulary_from_ui_map(ui_map: dict | None) -> list[str]:
    labels = set(DEFAULT_VOCABULARY)
    if ui_map:
        for menu in ui_map.get("menus", {}).values():
            labels.add(menu.get("label", ""))
            labels.update(entry.get("label", "") for entry in menu.get("entries", []))
    extra = sorted(
        label
        for label in labels - set(DEFAULT_VOCABULARY)
        if isinstance(label, str) and label.strip()
    )
    return [*DEFAULT_VOCABULARY, *extra[: 500 - len(DEFAULT_VOCABULARY)]]


async def convert_audio(source: Path, target: Path, *, timeout: float = 60) -> None:
    process = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-y",
        "-i",
        str(source),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        str(target),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, error = await asyncio.wait_for(process.communicate(), timeout)
    except (TimeoutError, asyncio.CancelledError):
        process.kill()
        await process.wait()
        raise
    if process.returncode:
        raise ValueError(f"Conversion audio impossible : {error.decode()[-1000:]}")


async def ingest(
    source: str | Path,
    *,
    work_dir: Path,
    language: str | None = None,
    ui_map: dict | None = None,
    client: httpx.AsyncClient | None = None,
    max_bytes: int = 100 * 1024 * 1024,
    download_timeout: float = 30,
    transcription_timeout: float = 120,
    poll_interval: float = 1,
) -> Transcript:
    import httpx

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    if client is None:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as session:
            return await ingest(
                source,
                work_dir=work_dir,
                language=language,
                ui_map=ui_map,
                client=session,
                max_bytes=max_bytes,
                download_timeout=download_timeout,
                transcription_timeout=transcription_timeout,
                poll_interval=poll_interval,
            )
    uri = str(source)
    parsed = urlparse(uri)
    if parsed.scheme in {"http", "https"}:
        path = work_dir / ("source" + Path(parsed.path).suffix.lower())
        size = 0
        try:
            async with asyncio.timeout(download_timeout):
                async with client.stream("GET", uri) as response:
                    response.raise_for_status()
                    with path.open("wb") as handle:
                        async for chunk in response.aiter_bytes():
                            size += len(chunk)
                            if size > max_bytes:
                                raise ValueError("Source trop volumineuse")
                            handle.write(chunk)
        except (httpx.TimeoutException, TimeoutError) as exc:
            path.unlink(missing_ok=True)
            raise TimeoutError("Téléchargement : délai dépassé") from exc
        except BaseException:
            path.unlink(missing_ok=True)
            raise
    else:
        path = Path(source).resolve()
        uri = path.as_uri()
    if path.stat().st_size > max_bytes:
        raise ValueError("Source trop volumineuse")
    data = path.read_bytes()
    if not data:
        raise ValueError("Source vide")
    sha256 = hashlib.sha256(data).hexdigest()
    if path.suffix.lower() in {".txt", ".md"}:
        text = data.decode("utf-8-sig").strip()
        if not text:
            raise ValueError("Texte vide")
        return Transcript(
            text,
            language or "und",
            [
                {"text": text, "start": 0.0, "end": 0.0, "words": []},
            ],
            uri,
            sha256,
            None,
            {},
        )
    key = os.environ.get("GLADIA_API_KEY")
    if not key:
        raise RuntimeError("Clé Gladia absente")
    wav = work_dir / "audio-16khz.wav"
    await convert_audio(path, wav)
    headers = {"x-gladia-key": key}
    started = time.perf_counter()
    with wav.open("rb") as audio:
        response = await client.post(
            "https://api.gladia.io/v2/upload",
            headers=headers,
            files={"audio": (wav.name, audio, "audio/wav")},
            timeout=30,
        )
    response.raise_for_status()
    latencies = {"upload": time.perf_counter() - started}
    LOGGER.info("Gladia upload : %.3f s", latencies["upload"])
    payload = {
        "audio_url": response.json()["audio_url"],
        "custom_vocabulary": True,
        "custom_vocabulary_config": {"vocabulary": vocabulary_from_ui_map(ui_map)},
        "language_config": {"languages": [language] if language else [], "code_switching": False},
    }
    started = time.perf_counter()
    job_id = None
    try:
        async with asyncio.timeout(transcription_timeout):
            response = await client.post(
                "https://api.gladia.io/v2/pre-recorded",
                headers=headers,
                json=payload,
                timeout=15,
            )
            response.raise_for_status()
            job = response.json()
            job_id = job["id"]
            (work_dir / "gladia-job.json").write_text(json.dumps(job, indent=2))
            result_url = job["result_url"]
            result_host = urlparse(result_url)
            if result_host.scheme != "https" or result_host.hostname != "api.gladia.io":
                raise ValueError("URL de résultat Gladia non autorisée")
            while True:
                response = await client.get(result_url, headers=headers, timeout=15)
                response.raise_for_status()
                result = response.json()
                if result["status"] == "done":
                    break
                if result["status"] == "error":
                    raise RuntimeError(f"Transcription Gladia échouée (job {job_id})")
                await asyncio.sleep(poll_interval)
    except (TimeoutError, httpx.TimeoutException) as exc:
        raise TranscriptionTimeout(job_id) from exc
    finally:
        latencies["transcription"] = time.perf_counter() - started
        LOGGER.info("Gladia transcription : %.3f s ; job %s", latencies["transcription"], job_id)
    transcription = result["result"]["transcription"]
    text = transcription["full_transcript"].strip()
    if not text:
        raise ValueError(f"Aucune parole détectée (job {job_id})")
    segments = [
        {k: utterance[k] for k in ("text", "start", "end", "words")}
        for utterance in transcription["utterances"]
    ]
    detected = transcription.get("languages", [])
    if not language:
        LOGGER.warning(
            "Langue Gladia détectée non vérifiée (%s) ; préciser --language pour la fixer",
            detected[0] if detected else "und",
        )
    return Transcript(
        text,
        language or (detected[0] if detected else "und"),
        segments,
        uri,
        sha256,
        job_id,
        latencies,
    )
