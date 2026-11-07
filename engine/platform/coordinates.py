"""Physical crops, normalized model output and per-monitor logical coordinates."""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        if not all(math.isfinite(v) for v in (self.x, self.y, self.width, self.height)):
            raise ValueError("non-finite rectangle")
        if self.width < 1 or self.height < 1:
            raise ValueError("rectangle smaller than a physical pixel")


@dataclass(frozen=True)
class Monitor:
    physical: Rect
    logical_x: float
    logical_y: float
    scale: float

    def __post_init__(self) -> None:
        if not all(math.isfinite(v) for v in (self.logical_x, self.logical_y, self.scale)):
            raise ValueError("non-finite monitor")
        if self.scale <= 0:
            raise ValueError("scale must be positive")

    def contains(self, crop: Rect) -> bool:
        p = self.physical
        return (p.x <= crop.x and p.y <= crop.y
                and crop.x + crop.width <= p.x + p.width
                and crop.y + crop.height <= p.y + p.height)


def normalized_point(u: float, v: float, crop: Rect, monitor: Monitor) -> tuple[float, float]:
    """Undo resizing implicitly via [0,1000], then divide by scale exactly once."""
    if not all(math.isfinite(n) and 0 <= n <= 1000 for n in (u, v)):
        raise ValueError("point outside normalized bounds")
    if not monitor.contains(crop):
        raise ValueError("crop crosses monitor boundary")
    px = crop.x + min(u * crop.width / 1000, crop.width - 1)
    py = crop.y + min(v * crop.height / 1000, crop.height - 1)
    return (monitor.logical_x + (px - monitor.physical.x) / monitor.scale,
            monitor.logical_y + (py - monitor.physical.y) / monitor.scale)


def blender_region(x: float, y: float, width: float, height: float,
                   window: Rect, scale: float) -> Rect:
    """Blender bottom-left logical region to global top-left physical crop."""
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("invalid scale")
    if min(x, y) < 0 or width <= 0 or height <= 0:
        raise ValueError("invalid region")
    if (x + width) * scale > window.width or (y + height) * scale > window.height:
        raise ValueError("region outside window")
    return Rect(window.x + x * scale, window.y + window.height - (y + height) * scale,
                width * scale, height * scale)
