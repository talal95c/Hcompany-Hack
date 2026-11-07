import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from engine.__main__ import warm_up_jev
from engine.adapters.blender import BlenderAdapter
from engine.adapters.holo import PacedHoloAdapter
from engine.services.adapters import HoloAdapter
from engine.services.holo import HoloCloudClient
from engine.services.holo_scheduler import HoloScheduler, StaleSpeculation, speculative_request


async def test_burst_and_sliding_window_quota():
    scheduler = HoloScheduler(requests=2, window_s=.04)
    starts = []

    async def request():
        starts.append(asyncio.get_running_loop().time())

    await asyncio.wait_for(asyncio.gather(*(scheduler.run(request) for _ in range(3))), 1)
    assert starts[1] - starts[0] < .03
    assert starts[2] - starts[0] >= .035
    assert scheduler.active == 0 and not scheduler.pending


async def test_interactive_overtakes_queued_speculation():
    scheduler = HoloScheduler(concurrency=1)
    entered, release = asyncio.Event(), asyncio.Event()
    order = []

    async def blocked():
        entered.set()
        await release.wait()

    async def request(name):
        order.append(name)

    async def speculate():
        with speculative_request(lambda: True):
            await scheduler.run(lambda: request("speculative"))

    first = asyncio.create_task(scheduler.run(blocked))
    await entered.wait()
    speculative = asyncio.create_task(speculate())
    await asyncio.sleep(0)
    interactive = asyncio.create_task(scheduler.run(lambda: request("interactive")))
    await asyncio.sleep(0)
    release.set()
    await asyncio.wait_for(asyncio.gather(first, speculative, interactive), 1)
    assert order == ["interactive", "speculative"]


@pytest.mark.parametrize("in_flight", [False, True])
async def test_stale_speculation_cancels_without_leaking_slots(in_flight):
    scheduler = HoloScheduler(requests=1, window_s=60)
    current = True
    entered, cancelled = asyncio.Event(), asyncio.Event()

    async def request():
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    async def speculate():
        with speculative_request(lambda: current):
            await scheduler.run(request)

    if not in_flight:
        async with scheduler.slot():
            pass
    task = asyncio.create_task(speculate())
    if in_flight:
        await entered.wait()
    else:
        await asyncio.sleep(0)
    current = False
    with pytest.raises(StaleSpeculation):
        await asyncio.wait_for(task, .5)
    assert cancelled.is_set() == in_flight
    assert scheduler.active == 0 and not scheduler.pending


@pytest.mark.parametrize("reset", [None, "2"])
async def test_429_recovers_without_permanent_spacing(reset):
    now = 0
    scheduler = HoloScheduler(clock=lambda: now)
    headers = {"Retry-After": "2", "X-RateLimit-Remaining": "0"}
    if reset is not None:
        headers["X-RateLimit-Reset"] = reset
    await scheduler.observe(429, headers)
    assert scheduler.blocked_until == 2
    now = 2
    calls = AsyncMock(return_value="ok")
    assert await scheduler.run(calls) == "ok"
    assert await scheduler.run(calls) == "ok"
    assert list(scheduler.starts) == [2, 2]
    assert scheduler.limit == 30


async def test_server_headers_and_cancelled_admission():
    scheduler = HoloScheduler()
    await scheduler.observe(200, {"x-ratelimit-limit-requests": "1"})
    async with scheduler.slot():
        pass
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(scheduler.run(AsyncMock()), .02)
    assert scheduler.active == 0 and not scheduler.pending
    await scheduler.observe(200, {"x-ratelimit-limit": "invalid", "retry-after": "invalid"})
    assert scheduler.limit == 1


@pytest.mark.parametrize("requests,window", [(0, 60), (30, 0), (30, float("nan"))])
def test_invalid_quota(requests, window):
    with pytest.raises(ValueError):
        HoloScheduler(requests=requests, window_s=window)


async def test_plugin_and_generic_share_the_same_admission():
    client = HoloCloudClient(client=SimpleNamespace(close=AsyncMock()))
    generic, plugin = PacedHoloAdapter(client), HoloAdapter(client)
    assert generic.requests.client.scheduler is plugin.client.scheduler
    await client.aclose()


@pytest.mark.parametrize("failure", [False, True])
async def test_warm_up_is_optional_and_failure_tolerated(failure):
    await warm_up_jev({})
    warm = AsyncMock(side_effect=RuntimeError("offline") if failure else None)
    await warm_up_jev({"jev": SimpleNamespace(client=SimpleNamespace(warm_up=warm))})
    warm.assert_awaited_once()


async def test_menu_reveal_waits_for_post_observation_ack():
    entered, ack = asyncio.Event(), asyncio.Event()
    region = {"area_id": "1", "region_id": "2", "area_type": "VIEW_3D",
              "region_type": "WINDOW", "screen_rect": {"x": 1}}

    async def request(command, send):
        entered.set()
        await ack.wait()
        region["screen_rect"] = {"x": 2}
        return {"status": "ok"}

    runtime = SimpleNamespace(make_command=lambda kind, payload: payload,
                              addon=SimpleNamespace(correlation=SimpleNamespace(request=request),
                                                    send=AsyncMock()))
    adapter = BlenderAdapter(runtime)
    adapter.regions = [region]
    reveal = adapter.reveal_target({"target": {"area_type": "VIEW_3D", "region_type": "WINDOW"},
                                    "help": {"menu_id": "VIEW3D_MT_mesh_add"}})
    task = asyncio.create_task(reveal())
    await entered.wait()
    assert not task.done()
    ack.set()
    assert await task == {"x": 2}
