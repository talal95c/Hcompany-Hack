import math

import pytest

from engine.platform import Monitor, Rect, blender_region, normalized_point


def test_retina_negative_origin_and_last_pixel():
    monitor = Monitor(Rect(-2880, 0, 2880, 1800), -1440, 0, 2)
    crop = Rect(-2680, 200, 400, 200)
    assert normalized_point(500, 500, crop, monitor) == (-1240, 150)
    assert normalized_point(1000, 1000, crop, monitor) == (-1140.5, 199.5)


def test_blender_y_flipped_once():
    assert blender_region(10, 20, 100, 50, Rect(200, 100, 1000, 800), 2) == Rect(
        220, 760, 200, 100
    )


@pytest.mark.parametrize("u", [-1, 1001, math.nan, math.inf])
def test_reject_invalid_point(u):
    with pytest.raises(ValueError):
        normalized_point(u, 0, Rect(0, 0, 10, 10), Monitor(Rect(0, 0, 100, 100), 0, 0, 1))


def test_reject_cross_monitor():
    with pytest.raises(ValueError, match="boundary"):
        normalized_point(0, 0, Rect(90, 0, 20, 20), Monitor(Rect(0, 0, 100, 100), 0, 0, 1))


@pytest.mark.parametrize("scale", [0, -1, math.nan])
def test_reject_scale(scale):
    with pytest.raises(ValueError):
        Monitor(Rect(0, 0, 100, 100), 0, 0, scale)
