"""Holo GUI grounding benchmark using real screenshots and API requests."""

import asyncio
import base64
import hashlib
import io
import json
import math
import os
import subprocess
import time
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

import httpx
from PIL import Image

from bench.common import statistics
from bench.holo_assets import crop_box, ensure_assets, hit, map_point, probes
from bench.holo_pacing import Pacer, rate_headers

BASE_URL = "https://api.hcompany.ai/v1"
MODELS = ["holo4-35b-a3b", "holo4-27b"]
SYSTEM = "You localize GUI elements. Return only the requested normalized click coordinates."
SCHEMA = {
    "type": "object",
    "properties": {
        key: {
            "type": "integer",
            "minimum": 0,
            "maximum": 1000,
            "description": f"{key.upper()} coordinate as integer in [0, 1000]",
        }
        for key in ("x", "y")
    },
    "required": ["x", "y"],
    "additionalProperties": False,
}


def parse_point(response: dict[str, Any]) -> tuple[float, float] | None:
    try:
        message = response["choices"][0]["message"]
        content = message.get("content")
        if not content and message.get("tool_calls"):
            content = message["tool_calls"][0]["function"]["arguments"]
        if isinstance(content, str):
            content = content.strip()
            if content.startswith("```") and content.endswith("```"):
                content = "\n".join(content.splitlines()[1:-1])
            content = json.loads(content)
        values = (content["x"], content["y"])
        if any(
            isinstance(v, bool)
            or not isinstance(v, (int, float))
            or not math.isfinite(v)
            or not 0 <= v <= 1000
            for v in values
        ):
            return None
        return float(values[0]), float(values[1])
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def request_body(
    model: str, image: Image.Image, description: str, nonce: str | None = None
) -> dict[str, Any]:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    uri = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
    prompt = (
        "Localize an element on the GUI image according to the provided target "
        "and output a click position.\n"
        f" * You must output a valid JSON following the format: {json.dumps(SCHEMA)}\n"
        f" Your target is:\n{description}"
    )
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": f"{nonce or uuid.uuid4().hex}\n{SYSTEM}"},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": uri}},
                    {"type": "text", "text": prompt},
                ],
            },
        ],
        "temperature": 0.0,
        "max_tokens": 128,
        "structured_outputs": {"json": SCHEMA},
        "chat_template_kwargs": {"enable_thinking": False},
    }


class Client:
    def __init__(self, timeout: float = 30) -> None:
        key = os.environ.get("HAI_API_KEY")
        if not key:
            raise ValueError("HAI_API_KEY is required for real Holo calls")
        self.http = httpx.AsyncClient(
            base_url=BASE_URL + "/", timeout=timeout, headers={"Authorization": f"Bearer {key}"}
        )
        self.pacer = Pacer()
        self.lock = asyncio.Lock()

    async def call(self, body: dict[str, Any]) -> dict[str, Any]:
        async with self.lock:
            return await self._call(body)

    async def _call(self, body: dict[str, Any]) -> dict[str, Any]:
        attempts = []
        total = time.perf_counter()
        response_data: dict[str, Any] = {}
        pacing_wait_ms = cooldown_wait_ms = 0.0
        for attempt in range(20):
            waits = await self.pacer.acquire()
            pacing_wait_ms += waits["pacing_wait_ms"]
            cooldown_wait_ms += waits["cooldown_wait_ms"]
            started = time.perf_counter()
            try:
                response = await self.http.post("chat/completions", json=body)
                attempts.append(
                    {
                        "status": response.status_code,
                        "latency_ms": (time.perf_counter() - started) * 1000,
                        "request_id": response.headers.get("x-request-id"),
                        "rate_headers": rate_headers(response.headers),
                    }
                )
                self.pacer.observe(response.status_code, response.headers, attempt)
                if response.status_code in (401, 403):
                    raise RuntimeError(f"Holo authorization failed ({response.status_code})")
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < 19:
                        continue
                if response.is_success:
                    try:
                        response_data = response.json()
                    except ValueError:
                        response_data = {}
                break
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                attempts.append(
                    {
                        "status": type(exc).__name__,
                        "latency_ms": (time.perf_counter() - started) * 1000,
                        "request_id": None,
                        "rate_headers": {},
                    }
                )
                self.pacer.observe(0, {}, attempt)
        usage = response_data.get("usage", {})
        cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0
        prompt = usage.get("prompt_tokens", 0) or 0
        completion = usage.get("completion_tokens", 0) or 0
        return {
            "latency_ms": attempts[-1]["latency_ms"] if attempts[-1]["status"] == 200 else None,
            "wall_time_ms": (time.perf_counter() - total) * 1000,
            "pacing_wait_ms": pacing_wait_ms,
            "cooldown_wait_ms": cooldown_wait_ms,
            "retry_attempt_ms": sum(a["latency_ms"] for a in attempts[:-1]),
            "rate_limit_429_count": sum(a["status"] == 429 for a in attempts),
            "effective_interval_s": self.pacer.interval,
            "attempts": attempts,
            "status": attempts[-1]["status"],
            "request_id": attempts[-1]["request_id"] or response_data.get("id"),
            "point_normalized": parse_point(response_data),
            "usage": usage,
            "prompt_tokens": prompt,
            "cached_tokens": cached,
            "output_tokens": completion,
            "cost_usd": ((prompt - cached) * 0.30 + cached * 0.03 + completion * 2) / 1e6,
            "response": response_data,
        }


def aggregate(samples: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(samples)
    successful = [s for s in samples if s["status"] == 200]
    return {
        "calls": count,
        "hit_rate": sum(s["hit"] for s in samples) / count if count else 0,
        **statistics([s["latency_ms"] for s in successful if s["latency_ms"] is not None]),
        "mean_prompt_tokens": sum(s["prompt_tokens"] for s in samples) / count if count else 0,
        "mean_output_tokens": sum(s["output_tokens"] for s in samples) / count if count else 0,
        "cached_tokens": sum(s["cached_tokens"] for s in samples),
        "cost_usd": sum(s["cost_usd"] for s in samples),
        "parse_failures": sum(s["point_normalized"] is None for s in samples),
        "http_errors": count - len(successful),
        "http_429": sum(s["status"] == 429 for s in samples),
        "rate_limit_429_count": sum(s.get("rate_limit_429_count", 0) for s in samples),
        "pacing_wait_ms": sum(s.get("pacing_wait_ms", 0) for s in samples),
        "cooldown_wait_ms": sum(s.get("cooldown_wait_ms", 0) for s in samples),
        "hit_rate_http_200": (
            sum(s["hit"] for s in successful) / len(successful) if successful else None
        ),
    }


def markdown_tables(groups: dict[str, Any], samples: list[dict[str, Any]]) -> str:
    if not samples:
        return "Aucune mesure."

    def ms(value: float | None) -> str:
        return f"{value:.1f}" if value is not None else "—"

    lines = [
        "## Résultats Holo",
        "",
        "| Modèle / échelle / image | Hits | HTTP erreurs | p50 ms | p95 ms | "
        "Moy. entrée / sortie | Coût USD |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, group in groups.items():
        lines.append(
            f"| {name} | {group['hit_rate']:.1%} | {group['http_errors']} | "
            f"{ms(group['p50_ms'])} | "
            f"{ms(group['p95_ms'])} | {group['mean_prompt_tokens']:.0f} / "
            f"{group['mean_output_tokens']:.0f} | {group['cost_usd']:.5f} |"
        )
    lines += [
        "",
        "## Cache contrôlé : nonce unique puis répétition identique",
        "",
        "| Modèle / échelle / image | Passage | p50 ms | p95 ms | Tokens entrée | Tokens cachés |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for name in groups:
        for repeat, label in ((0, "uncached"), (1, "cached")):
            subset = [
                s
                for s in samples
                if f"{s['model']} / {s['scale']}x / {s['condition']}" == name
                and s["repeat"] == repeat
            ]
            group = aggregate(subset)
            lines.append(
                f"| {name} | {label} | {ms(group['p50_ms'])} | {ms(group['p95_ms'])} | "
                f"{sum(s['prompt_tokens'] for s in subset)} | {group['cached_tokens']} |"
            )
    errors = sum(s["status"] != 200 for s in samples)
    lines += [
        "",
        f"**Attention : {errors} requêtes en erreur HTTP sont comptées comme misses. "
        "Latence = tentative HTTP 200 seule, sans attente ni tentatives échouées. "
        "Attentes de pacing/cooldown et nombre de 429 sont comptés séparément.**",
    ]
    lines += [
        "",
        "## Échecs (point pixels, boîte pixels)",
        "",
        "| Modèle / échelle / image / cible / passage | Point prédit | Boîte attendue |",
        "|---|---|---|",
    ]
    for s in samples:
        if not s["hit"]:
            lines.append(
                f"| {s['model']} / {s['scale']} / {s['condition']} / {s['probe_id']} / "
                f"{s['repeat'] + 1} | {s['point_pixels']} | {s['box']} |"
            )
    return "\n".join(lines)


async def run(
    *,
    out: Path = Path("bench/results"),
    models: list[str] | None = None,
    blender: str = "/opt/blender/blender",
    timeout: float = 30,
    concurrency: int = 1,
) -> dict[str, Any]:
    if concurrency != 1 or timeout <= 0:
        raise ValueError("concurrency must be 1, timeout must be positive")
    models = models or MODELS
    blender_version = subprocess.check_output([blender, "--version"], text=True).splitlines()[0]
    assets = out / "holo_assets"
    await ensure_assets(assets, blender)
    client = Client(timeout)
    samples: list[dict[str, Any]] = []
    semaphore = asyncio.Semaphore(concurrency)
    try:
        response = await client.http.get("models")
        response.raise_for_status()
        catalog = response.json()
        ids = {entry["id"] for entry in catalog["data"]}
        if any(model not in ids for model in models):
            raise ValueError("Requested Holo model unavailable in /v1/models")
        out.mkdir(parents=True, exist_ok=True)
        with (out / "holo-calls.jsonl").open("w") as log:

            async def pair(
                model: str,
                scale: int,
                condition: str,
                probe: dict,
                image: Image.Image,
                box: list[int],
            ) -> None:
                async with semaphore:
                    nonce = uuid.uuid4().hex
                    body = request_body(model, image, probe["description"], nonce)
                    body_hash = hashlib.sha256(json.dumps(body).encode()).hexdigest()
                    for repeat in (0, 1):
                        sample = await client.call(body)
                        point = sample["point_normalized"]
                        pixels = map_point(point, box) if point is not None else None
                        sample.update(
                            {
                                "model": model,
                                "scale": scale,
                                "condition": condition,
                                "probe_id": probe["id"],
                                "description": probe["description"],
                                "repeat": repeat,
                                "cache_condition": "uncached" if repeat == 0 else "cached",
                                "nonce": nonce,
                                "body_sha256": body_hash,
                                "box": probe["box"],
                                "crop_box": box,
                                "point_pixels": pixels,
                                "hit": hit(pixels, probe["box"]),
                            }
                        )
                        samples.append(sample)
                        log.write(json.dumps(sample, ensure_ascii=False) + "\n")
                        log.flush()

            for model in models:
                for scale in (1, 2):
                    image = Image.open(assets / f"scale-{scale}.png").convert("RGB")
                    geometry = json.loads((assets / f"scale-{scale}.json").read_text())
                    for probe in probes(geometry):
                        for condition in ("full", "crop"):
                            box = (
                                [0, 0, *image.size]
                                if condition == "full"
                                else crop_box(probe["parent"], image.size, margin=24 * scale)
                            )
                            await pair(model, scale, condition, probe, image.crop(box), box)
    finally:
        await client.http.aclose()
    return summarize(samples, catalog, models, timeout, concurrency, blender_version)


def summarize(
    samples: list[dict[str, Any]],
    catalog: dict[str, Any],
    models: list[str],
    timeout: float,
    concurrency: int,
    blender_version: str,
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sample in samples:
        grouped[f"{sample['model']} / {sample['scale']}x / {sample['condition']}"].append(sample)
    groups = {key: aggregate(grouped[key]) for key in sorted(grouped)}
    overall = aggregate(samples)
    return {
        "summary": {
            "api_calls": sum(len(s["attempts"]) for s in samples),
            "prompt_tokens": sum(s["prompt_tokens"] for s in samples),
            "output_tokens": sum(s["output_tokens"] for s in samples),
            "cached_tokens": overall["cached_tokens"],
            "cache_observed": overall["cached_tokens"] > 0,
            "cost_usd_computed": overall["cost_usd"],
            "http_errors": overall["http_errors"],
            "http_429": overall["http_429"],
            "rate_limit_429_count": overall["rate_limit_429_count"],
            "pacing_wait_ms": overall["pacing_wait_ms"],
            "cooldown_wait_ms": overall["cooldown_wait_ms"],
            "hit_rate_http_200": overall["hit_rate_http_200"],
        },
        "blender_version": blender_version,
        "groups": groups,
        "paired_cache_comparison": {
            key: {
                label: aggregate([s for s in grouped[key] if s["repeat"] == repeat])
                for repeat, label in ((0, "uncached"), (1, "cached"))
            }
            for key in groups
        },
        "raw_samples": samples,
        "models_catalog": catalog,
        "cache_comparison": {
            label: aggregate(
                [s for s in samples if s["status"] == 200 and (s["cached_tokens"] > 0) == cached]
            )
            for label, cached in (("uncached_observed", False), ("cached_observed", True))
        },
        "configuration": {
            "timeout_s": timeout,
            "concurrency": concurrency,
            "max_attempts": 20,
            "initial_interval_s": 2,
            "token_bucket_capacity": 1,
            "cache_protocol": "unique nonce at start of system prompt, then identical repeat",
            "models": models,
            "system_message": SYSTEM,
            "coordinate_schema": SCHEMA,
        },
        "notes": [
            "Mesures réelles ; coût calculé depuis les tokens aux tarifs imposés "
            "$0.30/M entrée, $0.03/M cache, $2/M sortie, pas une facture. "
            "Le catalogue annonce un tarif plus élevé pour 27B.",
            "Passage uncached : nonce unique au tout début du système ; passage cached : "
            "corps identique répété immédiatement, seul le pacing partagé peut attendre. "
            "Les cached_tokens vérifient le cache effectivement servi.",
            "Latence = tentative réussie seule. Token bucket partagé capacité 1, intervalle "
            "initial 2 s, concurrence 1 ; Retry-After et resets respectés. Les 429 augmentent "
            "l'intervalle et déclenchent un backoff 15/30/60 s (jusqu'à 20 tentatives). "
            "Les en-têtes rate-limit reçus sont conservés par tentative ; aucun plafond "
            "fournisseur n'est inventé si ces en-têtes sont absents.",
            "12 régions distinctes × 2 échelles × full/crop × 2 passages par modèle. "
            "Hit : point à l'intérieur du rectangle RNA (bord droit/bas exclus). "
            "Les régions superposées du viewport se chevauchent selon Blender.",
            "Sources : https://hub.hcompany.ai/models-api/element-localization et "
            "https://hub.hcompany.ai/models-api/chat-completions. "
            "temperature=0, thinking off, structured_outputs JSON normalisé [0,1000].",
            markdown_tables(groups, samples),
        ],
    }
