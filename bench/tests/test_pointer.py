import os

import pytest

from bench import pointer


def test_coordinates_offset_and_scale():
    capture = [57, 75, 1600, 1000]
    assert pointer.normalize((857, 575), capture) == (500, 500)
    assert pointer.physical((500, 500), capture) == (857, 575)
    assert pointer.physical(pointer.normalize((401.5, 133.5), capture), capture) == (402, 134)
    result = pointer.evaluate((500, 500), [847, 565, 20, 20], capture)
    assert result["hit"] and result["distance_px"] == 0
    assert not pointer.evaluate((0, 0), [847, 565, 20, 20], capture)["hit"]
    assert not pointer.evaluate((1000, 1000), capture, capture)["hit"]


@pytest.mark.parametrize(
    "point,capture",
    [
        ((500, 500), [0, 0, 0, 1]),
        ((500, 500), [0, 0, 1, -1]),
        ((-1, 0), [0, 0, 10, 10]),
        ((1001, 0), [0, 0, 10, 10]),
        ((float("nan"), 0), [0, 0, 10, 10]),
    ],
)
def test_invalid_coordinates(point, capture):
    with pytest.raises(ValueError):
        pointer.physical(point, capture)


def test_invalid_normalize():
    with pytest.raises(ValueError):
        pointer.normalize((1, 1), [0, 0, 0, 10])


def test_metrics_normal_empty_failure():
    samples = [
        {
            "hit": True,
            "distance_px": 0,
            "functional_eligible": True,
            "functional_success": True,
            "latency_ms": 1,
            "wall_time_ms": 2,
            "failure": None,
        },
        {
            "hit": False,
            "distance_px": 20,
            "functional_eligible": True,
            "functional_success": False,
            "latency_ms": 3,
            "wall_time_ms": 4,
            "failure": None,
        },
        {
            "functional_eligible": True,
            "latency_ms": None,
            "wall_time_ms": 9,
            "failure": "invalid_pointer",
        },
        {
            "hit": True,
            "distance_px": 1,
            "functional_eligible": False,
            "latency_ms": 5,
            "wall_time_ms": 6,
            "failure": None,
        },
    ]
    result = pointer.aggregate(samples)
    assert result["hit_rate"] == 0.5
    assert result["functional_trials"] == 3
    assert result["functional_click_success_rate"] == 1 / 3
    assert result["functional_failures"] == 2
    assert result["failures"] == 1
    assert result["distance_px"] == {"count": 3, "p50": 1, "p95": 20}
    assert result["latency"]["p50_ms"] == 3
    assert result["wall_latency"]["p95_ms"] == 9
    empty = pointer.aggregate([])
    assert empty["hit_rate"] is empty["functional_click_success_rate"] is None
    assert empty["distance_px"]["p50"] is None
    assert pointer.summarize([])["summary"] == {"calls": 0, "failures": 0}


@pytest.mark.parametrize(
    "options",
    [{"repeats": 0}, {"timeout": 0}, {"models": ["invalid"]}, {"limit": 0}, {"limit": 10}],
)
async def test_invalid_options(tmp_path, options):
    with pytest.raises(ValueError):
        await pointer.run(tmp_path, **options)


def test_targets():
    assert len(pointer.TARGETS) >= 8
    assert len({name for name, _, _ in pointer.TARGETS}) == len(pointer.TARGETS)
    for name, prompt, _ in pointer.TARGETS:
        assert name.casefold() != prompt.casefold()


@pytest.mark.live
async def test_pointer_live(tmp_path):
    if not os.environ.get("HAI_API_KEY"):
        pytest.skip("HAI_API_KEY absente")
    report = await pointer.run(tmp_path, repeats=1, limit=2)
    assert report["summary"]["failures"] == 0
    assert report["by_method"]["a11y"]["hit_rate"] == 1
    assert report["by_method"]["a11y"]["functional_click_success_rate"] == 1
    assert report["by_method"]["holo:holo4-27b"]["functional_trials"] == 2
