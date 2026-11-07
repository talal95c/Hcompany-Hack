"""Interface commune des capteurs applicatifs : plugin, accessibilité OS ou vision seule."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

Command = tuple[str, str, dict]
"""(destinataire, type, payload) d'une commande validée par contracts/commands.schema.json."""


@dataclass(frozen=True)
class Rect:
    """Rectangle en pixels physiques écran (origine en haut à gauche)."""

    x: float
    y: float
    w: float
    h: float

    @classmethod
    def from_dict(cls, data: dict) -> "Rect":
        w, h = data.get("w", data.get("width")), data.get("h", data.get("height"))
        if w is None or h is None:
            raise ValueError("Rectangle incomplet")
        return cls(float(data["x"]), float(data["y"]), float(w), float(h))

    @property
    def valid(self) -> bool:
        return self.w > 0 and self.h > 0 and abs(self.x) < 1e6 and abs(self.y) < 1e6

    @property
    def center(self) -> tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2

    def contains(self, x: float, y: float) -> bool:
        return self.x <= x <= self.x + self.w and self.y <= y <= self.y + self.h

    def intersects(self, other: "Rect") -> bool:
        return (self.x < other.x + other.w and other.x < self.x + self.w
                and self.y < other.y + other.h and other.y < self.y + self.h)

    def px(self) -> dict:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h}

    def crop(self) -> dict:
        return {"x": self.x, "y": self.y, "width": self.w, "height": self.h}

    def milli(self, frame: "Rect") -> "Rect":
        """Ce rectangle exprimé en millièmes (0-1000) du cadre `frame`."""
        return Rect((self.x - frame.x) * 1000 / frame.w, (self.y - frame.y) * 1000 / frame.h,
                    self.w * 1000 / frame.w, self.h * 1000 / frame.h)

    def point_milli(self, frame: "Rect") -> tuple[int, int] | None:
        """Centre en millièmes du cadre, ou None s'il sort du cadre."""
        cx, cy = self.center
        if not frame.contains(cx, cy):
            return None
        return (min(999, max(1, round((cx - frame.x) * 1000 / frame.w))),
                min(999, max(1, round((cy - frame.y) * 1000 / frame.h))))


@dataclass(frozen=True)
class TargetHint:
    """Ce que le capteur sait d'une cible : zone attendue et éventuel point exact."""

    rect: Rect | None = None
    ref: str | None = None
    snapshot_id: str | None = None
    exact: bool = False


@runtime_checkable
class AppAdapter(Protocol):
    """Capacités d'un capteur d'application ; toute absence se traduit par () ou None."""

    sensor: str
    app_id: str
    shortcut_hint: str | None

    def available(self) -> bool: ...

    def snapshot(self) -> Any: ...

    async def refresh(self, step: dict) -> Any: ...

    def zone(self, step: dict) -> tuple[Command, ...]: ...

    def reveal(self, step: dict) -> tuple[Command, ...]: ...

    def reveal_target(self, step: dict) -> Callable[[], Awaitable[Rect | None]] | None: ...

    def replay(self, step: dict) -> tuple[Command, ...]: ...

    def undo_replay(self, step: dict) -> tuple[Command, ...]: ...

    def expected_rect(self, step: dict) -> TargetHint | None: ...

    def facts(self) -> dict[str, str | None]: ...
