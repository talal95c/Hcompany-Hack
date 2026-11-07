"""Résultat commun à tous les checks : pass, fail ou unknown (unknown n'est jamais pass)."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class CheckResult:
    status: Literal["pass", "fail", "unknown"]
    detail: str
    scene_revision: int
    duration_ms: float


DETAILS = {"unknown": "Preuve absente ou état incomplet", "pass": "Vérifié", "fail": "Non vérifié"}
