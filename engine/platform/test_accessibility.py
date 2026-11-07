import math

import pytest

from engine.platform.accessibility import AccessibilityNode, node_rect, normalized_center
from engine.platform.coordinates import Monitor, Rect, normalized_point


def test_physical_bounds_negative_origin_and_scale_two():
    node: AccessibilityNode = {"bounds": {"x": -2600, "y": 220, "w": 40, "h": 20}}
    crop = Rect(-2680, 200, 400, 200)
    assert node_rect(node) == Rect(-2600, 220, 40, 20)
    assert normalized_center(node, crop) == (250, 150)
    monitor = Monitor(Rect(-2880, 0, 2880, 1800), -1440, 0, 2)
    assert normalized_point(*normalized_center(node, crop), crop, monitor) == (-1290, 115)


def test_inside_crop_center():
    assert normalized_center(
        {"bounds": {"x": 0, "y": 0, "w": 100, "h": 100}}, Rect(0, 0, 100, 100)
    ) == (500, 500)


@pytest.mark.parametrize("x,y,w,h", [(99, 0, 2, 1), (-1, 0, 2, 1), (0, 99, 1, 2)])
def test_outside_crop(x, y, w, h):
    with pytest.raises(ValueError, match="outside"):
        normalized_center({"bounds": {"x": x, "y": y, "w": w, "h": h}}, Rect(0, 0, 100, 100))


@pytest.mark.parametrize("w", [0, -1, math.nan, math.inf])
def test_invalid_bounds(w):
    with pytest.raises(ValueError):
        node_rect({"bounds": {"x": 0, "y": 0, "w": w, "h": 1}})


def test_missing_bounds():
    with pytest.raises(KeyError):
        node_rect({})
