"""Mesure des appels : durée, statut, request_id et tokens, sans contenu privé."""

from __future__ import annotations

import json
import logging
import math
import os
import platform
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("engine.services")


@dataclass(slots=True)
class CallRecord:
    service: str
    operation: str
    duration_ms: float
    status: str
    request_id: str | None = None
    input_tokens: int | None = None
    cached_tokens: int | None = None
    output_tokens: int | None = None
    start_offset_ms: float | None = None
    path: str | None = None
    retry_after: float | None = None
    winner: bool = False


@dataclass(slots=True)
class CallContext:
    request_id: str | None = None
    input_tokens: int | None = None
    cached_tokens: int | None = None
    output_tokens: int | None = None
    status: str = "ok"
    start_offset_ms: float | None = None
    path: str | None = None
    retry_after: float | None = None


def percentile(values: list[float], q: float) -> float:
    """Percentile par interpolation linéaire (q dans [0, 100])."""
    if not values:
        return math.nan
    ordered = sorted(values)
    rank = (len(ordered) - 1) * q / 100
    low, high = math.floor(rank), math.ceil(rank)
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


@dataclass
class LatencyRecorder:
    """Collecte les appels réels ; partagé entre clients pour produire un bench JSON."""

    records: list[CallRecord] = field(default_factory=list)

    @contextmanager
    def measure(self, service: str, operation: str) -> Iterator[CallContext]:
        ctx = CallContext()
        start = time.perf_counter()
        try:
            yield ctx
        except BaseException as exc:
            ctx.status = getattr(exc, "kind", type(exc).__name__)
            raise
        finally:
            record = CallRecord(
                service=service,
                operation=operation,
                duration_ms=round((time.perf_counter() - start) * 1000, 2),
                status=ctx.status,
                request_id=ctx.request_id,
                input_tokens=ctx.input_tokens,
                cached_tokens=ctx.cached_tokens,
                output_tokens=ctx.output_tokens,
                start_offset_ms=ctx.start_offset_ms,
                path=ctx.path,
                retry_after=ctx.retry_after,
            )
            self.records.append(record)
            logger.info(
                "service=%s op=%s status=%s duration_ms=%.1f request_id=%s tokens_in=%s "
                "tokens_cached=%s tokens_out=%s",
                record.service,
                record.operation,
                record.status,
                record.duration_ms,
                record.request_id,
                record.input_tokens,
                record.cached_tokens,
                record.output_tokens,
            )

    def add(self, record: CallRecord) -> None:
        self.records.append(record)

    def trace(self, records: list[CallRecord]) -> None:
        path = os.getenv("HCOMPANY_ATTEMPT_LOG")
        if path:
            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("a", encoding="utf-8") as output:
                for record in records:
                    output.write(json.dumps(asdict(record)) + "\n")

    def summary(self, service: str | None = None) -> dict[str, dict[str, Any]]:
        groups: dict[str, list[CallRecord]] = {}
        for rec in self.records:
            if service is None or rec.service == service:
                groups.setdefault(f"{rec.service}.{rec.operation}", []).append(rec)
        out: dict[str, dict[str, Any]] = {}
        for key, recs in sorted(groups.items()):
            ok = [r.duration_ms for r in recs if r.status == "ok"]
            durations = [r.duration_ms for r in recs]
            out[key] = {
                "n": len(recs),
                "n_ok": len(ok),
                "n_timeout": sum(r.status == "timeout" for r in recs),
                "n_error": sum(r.status not in ("ok", "timeout") for r in recs),
                "failures": {
                    s: sum(1 for r in recs if r.status == s)
                    for s in {r.status for r in recs}
                    if s != "ok"
                },
                "p50_ms": round(percentile(durations, 50), 1),
                "p95_ms": round(percentile(durations, 95), 1),
                "min_ms": round(min(ok), 1) if ok else None,
                "max_ms": round(max(ok), 1) if ok else None,
            }
        return out

    def write_bench(
        self, path: Path, *, service: str | None = None, extra: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "date": datetime.now(UTC).isoformat(timespec="seconds"),
            "host": {"os": platform.platform(), "python": platform.python_version()},
            "measured": True,
            "summary": self.summary(service),
            "calls": [asdict(r) for r in self.records if service is None or r.service == service],
        }
        if extra:
            payload.update(extra)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        return payload
