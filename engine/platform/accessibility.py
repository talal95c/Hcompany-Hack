"""Typed physical accessibility geometry; no native actions or pedagogical decisions."""

from typing import TypedDict

from .coordinates import Rect


class PhysicalBounds(TypedDict):
    x: float
    y: float
    w: float
    h: float


class AccessibilityNode(TypedDict):
    bounds: PhysicalBounds


def node_rect(node: AccessibilityNode) -> Rect:
    bounds = node["bounds"]
    return Rect(bounds["x"], bounds["y"], bounds["w"], bounds["h"])


def normalized_center(node: AccessibilityNode, crop: Rect) -> tuple[float, float]:
    """Require the whole physical node inside the crop; never apply monitor scale twice."""
    rect = node_rect(node)
    if not (
        crop.x <= rect.x
        and crop.y <= rect.y
        and rect.x + rect.width <= crop.x + crop.width
        and rect.y + rect.height <= crop.y + crop.height
    ):
        raise ValueError("accessibility node outside capture crop")
    return (
        (rect.x + rect.width / 2 - crop.x) * 1000 / crop.width,
        (rect.y + rect.height / 2 - crop.y) * 1000 / crop.height,
    )
