"""Mémoire atomique ; intervalles SM-2 (est.), à calibrer."""

import json
import logging
import math
import os
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4


@dataclass
class Skill:
    successes_without_help: int = 0
    max_help_level_used: int = 0
    last_review: float | None = None
    due_at: float | None = None
    interval: float = 0
    ease: float = 2.5
    unlocked: bool = False


class LearnerMemory:
    def __init__(self, path: Path):
        self.path = path
        self.skills: dict[str, Skill] = {}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text())
            if not isinstance(data, dict):
                raise ValueError("Mémoire invalide")
            loaded = {}
            for key, value in data.items():
                skill = Skill(**value)
                if (not isinstance(skill.successes_without_help, int)
                        or skill.successes_without_help < 0
                        or not isinstance(skill.max_help_level_used, int)
                        or not 0 <= skill.max_help_level_used <= 4
                        or not isinstance(skill.interval, (int, float))
                        or not math.isfinite(skill.interval) or skill.interval < 0
                        or not isinstance(skill.ease, (int, float))
                        or not math.isfinite(skill.ease) or skill.ease < 1.3
                        or any(v is not None and (
                            not isinstance(v, (int, float)) or not math.isfinite(v)
                        ) for v in (skill.last_review, skill.due_at))
                        or not isinstance(skill.unlocked, bool)):
                    raise ValueError("Compétence invalide")
                loaded[key] = skill
            self.skills = loaded
        except (ValueError, TypeError):
            backup = self.path.with_name(self.path.name + ".corrupt-" + uuid4().hex)
            os.replace(self.path, backup)
            self.skills = {}
            logging.warning("Mémoire corrompue sauvegardée ; nouveau profil")

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".learner-", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump({k: asdict(v) for k, v in self.skills.items()}, stream, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def review(
        self, skill_id: str, *, passed: bool, help_level: int,
        challenge: bool = False, now: float | None = None,
    ) -> Skill:
        if not isinstance(help_level, int) or not 0 <= help_level <= 4:
            raise ValueError("Palier invalide")
        skill = self.skills.setdefault(skill_id, Skill())
        now = time.time() if now is None else now
        if not math.isfinite(now):
            raise ValueError("Date invalide")
        skill.max_help_level_used = max(skill.max_help_level_used, help_level)
        quality = 5 if passed and help_level == 0 else 3 if passed else 1
        if passed and help_level == 0:
            skill.successes_without_help += 1
            skill.unlocked |= challenge
        skill.interval = (1 if skill.interval == 0 else 6 if skill.interval == 1
                          else skill.interval * skill.ease) if quality >= 3 else 1
        skill.ease = max(1.3, skill.ease + 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        skill.last_review = now
        skill.due_at = now + skill.interval * 86400
        self.save()
        return skill

    def can_delegate(self, skill_id: str, *, confirmed: bool, wants_to_learn: bool) -> bool:
        return confirmed and (not wants_to_learn or self.skills.get(skill_id, Skill()).unlocked)