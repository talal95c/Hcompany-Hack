"""Chargement prouvé et transitions atomiques de la leçon."""

import json
from pathlib import Path

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


def load_lesson(path: Path, *, allow_unproven: bool = False) -> dict:
    lesson = json.loads(path.read_text())
    validate("lesson", lesson)
    if not allow_unproven and (
        lesson["status"] != "proven"
        or any(step["proof"]["status"] != "proven" for step in lesson["steps"])
    ):
        raise ValueError("Leçon non prouvée")
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