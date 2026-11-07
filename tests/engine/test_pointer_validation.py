import base64
import hashlib
import io
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from engine.cache import TargetEntry
from engine.interfaces import LocalizeResult
from engine.lesson.runtime import decode_capture
from engine.pointer import marked_crop, rejection, verify_point

from .test_policy import context, help_context, setup


@pytest.mark.parametrize(("point", "bounds", "reason"), [
    (None, None, "not_localized"),
    (LocalizeResult(0, 20, 1, 0, True), None, "outside_capture"),
    (LocalizeResult(50, 50, 1, 0, False), None, "not_visible"),
    (LocalizeResult(50, 50, float("nan"), 0, True), None, "confidence_invalid"),
    (LocalizeResult(50, 50, 1, 0, True), (0, 0, 0, 1), "invalid_bounds"),
    (LocalizeResult(50, 50, 1, 0, True), (60, 60, 10, 10), "outside_target_bounds"),
    (LocalizeResult(50, 50, .01, 0, True), (40, 40, 20, 20), None),
])
def test_deterministic_rejections(point, bounds, reason):
    assert rejection(point, bounds) == reason


@pytest.mark.parametrize("answer", [True, False, None])
async def test_unbounded_pointer_needs_independent_point_proof(answer):
    class Holo:
        async def verify_point(self, *args, **kwargs):
            return answer

    policy, _, _, _, debug = setup(holo=Holo())
    point = LocalizeResult(500, 500, .02, 0, True)
    result = await policy.validate_point(help_context(image_png=b"png"), point)
    assert bool(result) == (answer is True)
    rejections = [event for event in debug if event["kind"] == "point_rejected"]
    assert bool(rejections) == (answer is not True)
    assert all(set(event) == {"kind", "reason"} for event in rejections)


async def test_verified_cache_still_requires_current_visibility_and_bounds():
    policy, _, _, _, debug = setup()
    point = LocalizeResult(500, 500, .02, 0, True)
    ctx = replace(help_context(), expected_rect=(0, 0, 10, 10))
    assert await policy.validate_point(ctx, point, verified=True) is None
    assert debug[-1]["reason"] == "outside_target_bounds"
    cache = policy.targets
    entry = TargetEntry(context(), point, "capture", True)
    cache.put_target(entry)
    for changes in ({"generation": 1}, {"capture_revision": "new"}):
        assert cache.get_target(replace(context(), **changes)) is None


def png(width=800, height=600):
    output = io.BytesIO()
    Image.new("RGB", (width, height)).save(output, format="PNG")
    return output.getvalue()


@pytest.mark.parametrize("scale", [1, 2])
def test_resized_capture_preserves_physical_crop_metadata(scale):
    image = png()
    payload = {"image_ref": "data:image/png;base64," + base64.b64encode(image).decode(),
               "crop": {"x": 30, "y": 70, "width": 1600 * scale, "height": 1200 * scale},
               "image_size": {"width": 800, "height": 600}}
    assert decode_capture(payload) == image
    payload["image_size"]["width"] = 799
    with pytest.raises(ValueError):
        decode_capture(payload)


def test_point_proof_crop_is_local_and_keeps_marker_at_image_boundary():
    for point in (LocalizeResult(1, 1, 1, 0), LocalizeResult(999, 999, 1, 0)):
        with Image.open(io.BytesIO(marked_crop(png(), point))) as image:
            assert image.width <= 320 and image.height <= 192


@pytest.mark.parametrize("content,accepted", [
    ('{"answer":"yes","evidence":"direct","bounds":[0,0,1000,1000]}', True),
    ('{"answer":"yes","evidence":"direct"}', False),
    ('{"answer":"yes","evidence":"direct","bounds":[0,0,1,1]}', False),
    ('{"answer":"yes","evidence":"direct","bounds":[0,0,0,0]}', False),
    ('{"answer":"yes","evidence":"direct","bounds":[0,0,1001,1000]}', False),
    ('{"answer":"yes","evidence":"direct","bounds":null}', False),
    ('{"answer":"yes","evidence":"ambiguous"}', False),
    ('{"answer":"no","evidence":"direct"}', False),
    ('{"answer":"unsure","evidence":"direct"}', False),
    ('{}', False), ('invalid', False),
])
async def test_point_proof_is_strict_and_fail_closed(content, accepted):
    class Client:
        async def _complete(self, *args, **kwargs):
            message = SimpleNamespace(content=content)
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    result = await verify_point(Client(), png(), "A1", LocalizeResult(50, 50, 1, 0), timeout_s=1)
    assert result is accepted


async def test_recorded_real_capture_proofs_remain_fail_closed():
    root = Path(__file__).parent / "fixtures"
    data = json.loads((root / "pointer-labelled.json").read_text())
    for row in data["samples"]:
        raw = (root / row["image"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == row["sha256"]

        class Client:
            async def _complete(self, *args, **kwargs):
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
                    content=json.dumps(row["proof"])))])

        point = LocalizeResult(*row["point"], .02, 0, True)
        accepted = await verify_point(Client(), raw, row["target"], point, timeout_s=1)
        assert accepted == row["accepted"]
        assert not (accepted and not row["label"])
