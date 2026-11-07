import asyncio
from dataclasses import replace

import pytest

from engine.cache import AudioCache, AudioEntry, Preloader, TargetCache, TargetContext, TargetEntry
from engine.interfaces import LocalizeResult


def context():
    return TargetContext("4.5.9", (800, 600), 2, "Tore", (0, 0), "main", "fr", 1, True)


@pytest.mark.parametrize("changes", [
    {"blender_version": "5.0.0"}, {"region_size": (801, 600)}, {"ui_scale": 1},
    {"target": "Cube"}, {"origin": (1, 0)}, {"monitor_id": "other"},
    {"language": "en"}, {"ui_revision": 2}, {"visible": False}, {"menu_context": "other"},
])
def test_context_mismatch(changes):
    cache, ctx = TargetCache(), context()
    assert cache.get_target(ctx) is None
    entry = TargetEntry(ctx, LocalizeResult(500, 500, None, 1), "cap")
    cache.put_target(entry)
    assert cache.get(ctx) == entry
    assert cache.get_target(ctx) == entry
    assert cache.get_target(replace(ctx, **changes)) is None
    cache.on_event({"type": "regions.changed"})
    assert cache.get_target(ctx) is None


def test_audio_lru():
    cache = AudioCache(2)
    cache.put("a", AudioEntry(b"a", "audio/a"))
    cache.put("b", AudioEntry(b"b"))
    assert cache.get("a").data == b"a"
    cache.put("c", AudioEntry())
    assert cache.get("b") is None
    with pytest.raises(ValueError):
        TargetCache(0)


async def test_preload_success_error_and_cancel():
    loader, cache = Preloader(), TargetCache()

    async def success():
        return LocalizeResult(10, 20, None, 0)

    await loader.start(1, context(), "cap", success, cache)
    await loader.task
    assert cache.get_target(context()).result.x == 10
    cache.invalidate()

    async def error():
        raise ValueError

    await loader.start(2, context(), "cap", error, cache)
    await loader.task
    assert cache.get_target(context()) is None
    await loader.start(3, context(), "cap", lambda: asyncio.sleep(10), cache)
    await loader.cancel()
    assert loader.task is None and cache.get_target(context()) is None
    await loader.start(4, context(), "cap", lambda: asyncio.sleep(1), cache, timeout_s=0.001)
    await loader.task
    assert cache.get_target(context()) is None
