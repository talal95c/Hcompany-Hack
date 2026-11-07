"""Choix du capteur : plugin, accessibilité puis vision, selon `lesson.app.sensor`."""

from collections.abc import Mapping
from dataclasses import dataclass

ORDER = {
    "auto": ("addon", "accessibility", "vision"),
    "addon": ("addon",),
    "accessibility": ("accessibility", "vision"),
    "vision": ("vision",),
}
# Erreurs a11y qui rendent l'arbre inexploitable pour la fenêtre : on bascule en vision.
FALLBACK_ERRORS = frozenset({"APP_NOT_FOUND", "PERMISSION_DENIED", "TIMEOUT"})


@dataclass(frozen=True)
class Route:
    sensor: str | None
    reason: str


class SensorRouter:
    def __init__(self, requested: str):
        if requested not in ORDER:
            raise ValueError(f"Capteur inconnu : {requested}")
        self.requested = requested
        self.degraded: set[str] = set()

    def choose(self, available: Mapping[str, bool]) -> Route:
        for sensor in ORDER[self.requested]:
            if sensor in self.degraded:
                continue
            if available.get(sensor):
                primary = ORDER[self.requested][0]
                return Route(sensor, "nominal" if sensor == primary else "fallback")
        return Route(None, "unavailable")

    def report_error(self, sensor: str, code: str) -> bool:
        """Mémorise une panne de capteur ; True si un repli est désormais possible."""
        if sensor == "accessibility" and code in FALLBACK_ERRORS:
            self.degraded.add(sensor)
            return "vision" in ORDER[self.requested]
        return False

    def recover(self, sensor: str) -> None:
        self.degraded.discard(sensor)
