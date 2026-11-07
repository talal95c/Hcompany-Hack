import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest

from engine.interfaces import LocalizeResult
from engine.lesson.live_audio import LiveUtterance
from prep.ui_map import operator_menu

from .test_policy import drain, help_context, setup


def test_ui_map_selects_direct_container():
    ui = {"menus": {"VIEW3D_MT_mesh_add": {"entries": [
        {"kind": "operator", "id": "MESH_OT_primitive_torus_add"}]}}}
    assert operator_menu(ui, "MESH_OT_primitive_torus_add") == "VIEW3D_MT_mesh_add"
    assert operator_menu(ui, "missing") is None
    assert operator_menu({}, "missing") is None


class Session:
    def __init__(self):
        self.audio = []
        self.queue = asyncio.Queue()
        self.closed = False

    async def send_audio(self, data):
        self.audio.append(data)
        await self.queue.put(SimpleNamespace(kind="partial", text="pourquoi"))

    async def stop(self):
        await self.queue.put(SimpleNamespace(kind="final", text="pourquoi un tore ?"))
        await self.queue.put(None)

    async def events(self):
        while event := await self.queue.get():
            yield event

    async def aclose(self):
        self.closed = True


async def test_stream_forwards_before_stop_and_drains_final():
    session, events, errors = Session(), [], []

    async def open_live(**kwargs):
        assert kwargs["endpointing_s"] == 0.05
        return session

    async def on_event(event):
        events.append(event)

    async def on_error():
        errors.append(True)

    stream = LiveUtterance(SimpleNamespace(open_live=open_live), 16000, on_event, on_error)
    try:
        stream.feed(0, b"\0\0" * 320)
        async with asyncio.timeout(1):
            while not events:
                await asyncio.sleep(0)
        assert events[0].kind == "partial" and session.audio
        stream.feed(0, b"\0\0")
        assert stream.sequence == 1
        with pytest.raises(ValueError):
            stream.feed(2, b"\0\0")
        stream.stop()
        await stream.task
        assert [event.kind for event in events] == ["partial", "final"]
        assert session.closed and not errors
    finally:
        await stream.close()


async def test_stream_service_failure_is_reported_and_cancel_safe():
    errors = []

    async def open_live(**kwargs):
        raise OSError("Unavailable")

    async def callback(*args):
        errors.append(True)

    stream = LiveUtterance(SimpleNamespace(open_live=open_live), 16000, callback, callback)
    await stream.task
    assert errors == [True]
    with pytest.raises(ValueError):
        stream.feed(0, b"\0\0")
    await stream.close()


@pytest.mark.parametrize("point", [LocalizeResult(0, 0, 1, 0),
                                 LocalizeResult(500, 500, 0.1, 0),
                                 LocalizeResult(500, 500, 1, 0, False)])
async def test_invisible_uncertain_or_boundary_point_falls_back(point):
    class Holo:
        async def localize(self, *args, **kwargs):
            return point

    policy, _, commands, _, _ = setup(holo=Holo())
    policy.level = 2
    await policy.intent("aide", help_context(capture_id="fresh", image_png=b"png"))
    assert [command["type"] for command in drain(commands)] == ["highlight", "say"]
    assert policy.level == 2


async def test_unbounded_app_capture_requires_visibility_and_gives_text_fallback():
    class Holo:
        async def localize(self, *args, **kwargs):
            return LocalizeResult(500, 500, 0.9, 0)

    policy, _, commands, _, _ = setup(holo=Holo())
    policy.level = 2
    context = replace(help_context(capture_id="app", image_png=b"png"),
                      area_id=None, region_id=None, require_visible=True)
    await policy.intent("aide", context)
    assert [command["type"] for command in drain(commands)] == ["say"]
