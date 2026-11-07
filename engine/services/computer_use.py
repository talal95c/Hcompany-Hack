"""Boucle applicative générique ; le caller garde consentement, verrou et injection."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, TypeVar

from engine.services._retry import RETRYABLE
from engine.services.profiles import AppProfile
from engine.services.protocols import ActTurn, HoloAction, HoloClient
from engine.services.verify import HoloVerifier, Verification

T = TypeVar("T")


@dataclass(frozen=True)
class StepLoopResult:
    status: Literal["success", "max_steps", "stopped", "error"]
    turns: tuple[ActTurn, ...]
    final: Verification | None
    latencies_ms: tuple[float, ...]
    error: str | None = None


class _Stopped(Exception):
    pass


async def _interruptible(work: Callable[[], Awaitable[T]], stop: asyncio.Event | None) -> T:
    if stop is None:
        return await work()
    if stop.is_set():
        raise _Stopped
    task = asyncio.ensure_future(work())
    signal = asyncio.create_task(stop.wait())
    try:
        await asyncio.wait((task, signal), return_when=asyncio.FIRST_COMPLETED)
        if stop.is_set():
            raise _Stopped
        return await task
    finally:
        task.cancel()
        signal.cancel()
        await asyncio.gather(task, signal, return_exceptions=True)


async def run_steps(
    holo: HoloClient,
    goal: str,
    *,
    capture: Callable[[], Awaitable[bytes]],
    execute: Callable[[HoloAction], Awaitable[str]],
    verifier: HoloVerifier | None = None,
    success_assertion: str | None = None,
    profile: AppProfile | None = None,
    max_steps: int = 8,
    stop: asyncio.Event | None = None,
    settle_s: float = 0.3,
) -> StepLoopResult:
    """Sans verifier, success signifie seulement que Holo a annoncé done."""
    if max_steps < 0 or settle_s < 0:
        raise ValueError("max_steps et settle_s doivent être positifs ou nuls")
    if not goal.strip():
        raise ValueError("objectif vide")
    turns: list[ActTurn] = []
    latencies: list[float] = []
    final = None
    transient_errors = 0

    def result(status, error=None):
        return StepLoopResult(status, tuple(turns), final, tuple(latencies), error)

    for _ in range(max_steps):
        if stop is not None and stop.is_set():
            return result("stopped")
        start = time.perf_counter()
        status = None
        error = None
        action = None
        try:
            image = await _interruptible(capture, stop)
            action = await _interruptible(
                lambda: holo.act(
                    image,
                    goal,
                    lesson_context=(
                        f"Application: {profile.name}. {profile.jev_context}" if profile else ""
                    ),
                    history=tuple(turns),
                ),
                stop,
            )
            if action.type == "done":
                if verifier is None:
                    turns.append(ActTurn(action, "done (unverified)"))
                    status = "success"
                else:
                    image = await _interruptible(capture, stop)
                    final = await _interruptible(
                        lambda: verifier.verify(image, success_assertion or goal, profile=profile),
                        stop,
                    )
                    if final.verdict == "pass":
                        turns.append(ActTurn(action, "done verified"))
                        status = "success"
                    else:
                        turns.append(ActTurn(action, f"done rejected: {final.reason}"))
            else:
                outcome = await _interruptible(lambda: execute(action), stop)
                turns.append(ActTurn(action, outcome))
                await _interruptible(lambda: asyncio.sleep(settle_s), stop)
        except _Stopped:
            status = "stopped"
        except asyncio.CancelledError:
            raise
        except RETRYABLE as exc:
            transient_errors += 1
            if transient_errors > 2:
                status = "error"
                error = f"{type(exc).__name__}: {exc}"
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            if action is not None and (not turns or turns[-1].action is not action):
                turns.append(ActTurn(action, f"error: {error}"))
            status = "error"
        finally:
            latencies.append((time.perf_counter() - start) * 1000)
        if status:
            return result(status, error)
    return result("stopped" if stop is not None and stop.is_set() else "max_steps")
