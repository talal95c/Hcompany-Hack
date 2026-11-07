"""Chargement prouvé et transitions atomiques de la leçon."""

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

from engine.bus.validation import validate

TRANSITIONS = {
    "READY": {"OBSERVING"},
    "OBSERVING": {"CHECKING", "ACTING"},
    "CHECKING": {"PASSED", "OBSERVING", "HELP", "PAUSED"},
    "HELP": {"OBSERVING"},
    "ACTING": {"CHECKING", "PAUSED"},
    "PASSED": {"READY", "COMPLETE"},
    "PAUSED": {"OBSERVING"},
    "COMPLETE": set(),
}


def _artifact(root: Path, reference: str) -> Path:
    path = (root / reference).resolve()
    if not path.is_relative_to(root) or not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"Artefact absent ou hors leçon : {reference}")
    return path


def load_lesson(
    path: Path, *, allow_unproven: bool = False, source_path: Path | None = None,
) -> dict:
    lesson = json.loads(path.read_text())
    validate("lesson", lesson)
    ids = [step["id"] for step in lesson["steps"]]
    if len(set(ids)) != len(ids):
        raise ValueError("Identifiants d'étape dupliqués")
    if not allow_unproven and (
        lesson["status"] != "proven"
        or any(step["proof"]["status"] != "proven" for step in lesson["steps"])
    ):
        raise ValueError("Leçon non prouvée")
    if lesson["status"] == "proven":
        root = path.resolve().parent
        _artifact(root, lesson["proof"]["evidence_ref"])
        for step in lesson["steps"]:
            _artifact(root, step["proof"]["evidence_ref"])
        digest = lesson["source"]["sha256"]
        if not re.fullmatch(r"[a-fA-F0-9]{64}", digest):
            raise ValueError("SHA256 source invalide")
        uri = urlparse(lesson["source"]["uri"])
        if source_path is None:
            if uri.scheme == "file" and uri.netloc in {"", "localhost"}:
                source_path = Path(unquote(uri.path))
            elif not uri.scheme:
                source_path = _artifact(root, unquote(uri.path))
            else:
                raise ValueError("Archive locale source requise pour vérifier le SHA256")
        if not source_path.is_file():
            raise ValueError(f"Source absente : {source_path}")
        with source_path.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != digest.lower():
            raise ValueError("SHA256 source incompatible")
    return lesson


class Session:
    def __init__(self, session_id: str, lesson: dict):
        self.session_id = session_id
        self.lesson = lesson
        self.index = 0
        self.generation = 0
        self.status = "READY"
        self.passed: set[tuple[str, int]] = set()

    @property
    def step(self) -> dict:
        return self.lesson["steps"][self.index]

    @property
    def step_id(self) -> str:
        return self.step["id"]

    def transition(self, target: str) -> None:
        if target not in TRANSITIONS[self.status]:
            raise ValueError(f"Transition interdite : {self.status} → {target}")
        self.status = target

    def observe(self, mode: str | None) -> bool:
        if self.status == "READY" and mode == self.step["preconditions"]["mode"]:
            self.transition("OBSERVING")
            return True
        return False

    def accept(self, generation: int) -> bool:
        return generation == self.generation

    def resync(self) -> None:
        self.generation += 1

    def advance(self, generation: int) -> bool:
        key = (self.step_id, generation)
        if not self.accept(generation) or key in self.passed or self.status != "PASSED":
            return False
        self.passed.add(key)
        self.generation += 1
        if self.index + 1 == len(self.lesson["steps"]):
            self.transition("COMPLETE")
        else:
            self.index += 1
            self.transition("READY")
        return True