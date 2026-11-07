"""Configuration locale, sans exposition des secrets."""

import logging
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True)
class EngineConfig:
    host: str = "127.0.0.1"
    port: int = 0
    addon_port: int = 0
    session_id: str = field(default_factory=lambda: str(uuid4()))
    session_token: str = field(default_factory=lambda: secrets.token_urlsafe(32), repr=False)
    debug_port: int = 0
    lesson: Path | None = None
    learner_path: Path = field(
        default_factory=lambda: Path.home() / ".local/share/hcompany-hack/learner.json"
    )
    no_progress_s: float = 20
    undo_threshold: int = 3
    cooldown_s: float = 30
    jev_timeout_s: float = 0.8
    holo_timeout_s: float = 5
    stt_final_timeout_s: float = 2

    def __post_init__(self) -> None:
        if any(not 0 <= p <= 65535 for p in (self.port, self.addon_port, self.debug_port)):
            raise ValueError("Port invalide")
        if not self.session_id or not self.session_token:
            raise ValueError("Session vide")

    @classmethod
    def from_env(cls) -> "EngineConfig":
        token = os.environ.get("ENGINE_SESSION_TOKEN")
        if not token:
            token = secrets.token_urlsafe(32)
            logging.warning("Jeton de session absent : jeton temporaire généré")
        return cls(
            host=os.getenv("ENGINE_HOST", "127.0.0.1"),
            port=int(os.getenv("ENGINE_PORT", "0")),
            addon_port=int(os.getenv("ENGINE_ADDON_PORT", "0")),
            debug_port=int(os.getenv("ENGINE_DEBUG_PORT", "0")),
            session_id=os.getenv("ENGINE_SESSION_ID") or str(uuid4()),
            session_token=token,
            lesson=Path(os.environ["ENGINE_LESSON"]) if os.getenv("ENGINE_LESSON") else None,
            learner_path=Path(os.getenv(
                "ENGINE_LEARNER_PATH", str(Path.home() / ".local/share/hcompany-hack/learner.json")
            )).expanduser(),
        )
