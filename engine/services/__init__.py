"""Clients IA cloud : Holo (H Company), Jev (Codiv), Gladia (STT), Linkup (recherche)."""

from importlib import import_module

from engine.services.errors import (
    AuthenticationError,
    InvalidRequest,
    InvalidResponse,
    QuotaExceeded,
    ServiceError,
    ServiceTimeout,
    ServiceUnavailable,
)
from engine.services.latency import LatencyRecorder
from engine.services.profiles import AppProfile, load_profile
from engine.services.protocols import (
    HoloClient,
    JevClient,
    SearchClient,
    SttClient,
    SttSession,
)

__all__ = [
    "AppProfile",
    "load_profile",
    "AuthenticationError",
    "HoloClient",
    "InvalidRequest",
    "InvalidResponse",
    "JevClient",
    "LatencyRecorder",
    "QuotaExceeded",
    "SearchClient",
    "ServiceError",
    "ServiceTimeout",
    "ServiceUnavailable",
    "SttClient",
    "SttSession",
    "HoloVerifier",
    "Verification",
    "StepLoopResult",
    "run_steps",
    "XdotoolExecutor",
    "capture_x11",
]


def __getattr__(name: str):
    modules = {
        "HoloVerifier": "verify",
        "Verification": "verify",
        "StepLoopResult": "computer_use",
        "run_steps": "computer_use",
        "XdotoolExecutor": "x11",
        "capture_x11": "x11",
    }
    if name not in modules:
        raise AttributeError(name)
    return getattr(import_module(f"engine.services.{modules[name]}"), name)
