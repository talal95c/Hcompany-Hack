import json
from pathlib import Path

import httpx
import pytest
from PIL import Image

from bench.common import ROOT
from bench.holo import Client, aggregate, parse_point, request_body, summarize
from bench.holo_assets import crop_box, hit, map_point, probes, top_left


def response(content: str | None) -> dict:
    return {"choices": [{"message": {"content": content}}]}


def test_geometry() -> None:
    assert top_left({"x": 10, "y": 20, "width": 50, "height": 30}, 100) == [10, 50, 60, 80]
    assert crop_box([10, 20, 70, 90], (100, 100)) == [0, 0, 94, 100]
    assert map_point((500, 250), [20, 40, 120, 240]) == (70, 90)
    assert map_point((0, 1000), [20, 40, 120, 240]) == (20, 240)
    assert hit((20, 40), [20, 40, 120, 240])
    assert not hit((120, 240), [20, 40, 120, 240])
    assert not hit(None, [20, 40, 120, 240])


@pytest.mark.parametrize("content", ['{"x": 50, "y": 600}', '```json\n{"x": 50, "y": 600}\n```'])
def test_parse_nominal(content: str) -> None:
    assert parse_point(response(content)) == (50, 600)


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"choices": []},
        response(None),
        response(""),
        response("broken"),
        response("[]"),
        response('{"x": 3}'),
        response('{"x": true, "y": 2}'),
        response('{"x": -1, "y": 2}'),
        response('{"x": 1001, "y": 2}'),
        response('{"x": NaN, "y": 2}'),
    ],
)
def test_parse_invalid(data: dict) -> None:
    assert parse_point(data) is None


def test_parse_tool() -> None:
    data = {
        "choices": [
            {"message": {"tool_calls": [{"function": {"arguments": '{"x": 500, "y": 500}'}}]}}
        ]
    }
    assert parse_point(data) == (500, 500)


def test_asset_geometry() -> None:
    for scale in (1, 2):
        assets = ROOT / "bench/results/holo_assets"
        geometry = json.loads((assets / f"scale-{scale}.json").read_text())
        targets = probes(geometry)
        assert len(targets) == 12
        image = Image.open(assets / f"scale-{scale}.png")
        window = geometry["windows"][0]
        assert image.size == (window["width"], window["height"])
        for target in targets:
            x0, y0, x1, y1 = target["box"]
            assert 0 <= x0 < x1 <= image.width
            assert 0 <= y0 < y1 <= image.height
    with pytest.raises(ValueError):
        probes({"windows": [{"areas": []}]})


def test_request() -> None:
    body = request_body("model", Image.new("RGB", (10, 10)), "target")
    assert body["temperature"] == 0
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert body["messages"][0]["role"] == "system"
    assert aggregate([])["calls"] == 0
    image = Image.new("RGB", (10, 10))
    first = request_body("model", image, "target", "unique-pair")
    assert first["messages"][0]["content"].startswith("unique-pair\n")
    assert first == request_body("model", image, "target", "unique-pair")
    assert first != request_body("model", image, "target", "another-pair")
    assert request_body("model", image, "target") != request_body("model", image, "target")


def test_summary() -> None:
    samples = []
    for repeat, status in enumerate((200, 429)):
        samples.append(
            {
                "model": "unit",
                "scale": 1,
                "condition": "full",
                "hit": status == 200,
                "status": status,
                "latency_ms": 10,
                "prompt_tokens": 100,
                "output_tokens": 10,
                "cached_tokens": 20,
                "cost_usd": 0.001,
                "point_normalized": (50, 50) if status == 200 else None,
                "point_pixels": (5, 5),
                "box": [0, 0, 10, 10],
                "probe_id": "target",
                "repeat": repeat,
                "attempts": [{"status": status}],
            }
        )
    report = summarize(samples, {}, ["unit"], 30, 2, "unit-version")
    assert report["summary"]["http_errors"] == 1
    assert report["summary"]["http_429"] == 1
    assert report["summary"]["hit_rate_http_200"] == 1
    assert report["groups"]["unit / 1x / full"]["hit_rate"] == 0.5
    assert report["cache_comparison"]["cached_observed"]["calls"] == 1
    assert summarize([], {}, [], 30, 2, "unit")["summary"]["api_calls"] == 0


async def test_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAI_API_KEY", "unit-placeholder")
    client = Client()
    await client.http.aclose()
    data = {
        **response('{"x": 50, "y": 600}'),
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 10,
            "prompt_tokens_details": {"cached_tokens": 20},
        },
    }
    client.http = httpx.AsyncClient(
        base_url="https://unit.invalid/",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json=data, headers={"x-request-id": "unit"})
        ),
    )
    try:
        result = await client.call({})
    finally:
        await client.http.aclose()
    assert result["point_normalized"] == (50, 600)
    assert result["request_id"] == "unit"
    assert result["cached_tokens"] == 20
    assert result["cost_usd"] == pytest.approx((80 * 0.3 + 20 * 0.03 + 10 * 2) / 1e6)


async def test_client_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAI_API_KEY", "unit-placeholder")
    client = Client()
    await client.http.aclose()
    client.http = httpx.AsyncClient(
        base_url="https://unit.invalid/",
        transport=httpx.MockTransport(lambda _: httpx.Response(400)),
    )
    try:
        result = await client.call({})
    finally:
        await client.http.aclose()
    assert result["point_normalized"] is None
    assert result["status"] == 400


@pytest.mark.live
async def test_holo_live(tmp_path: Path) -> None:
    assets = ROOT / "bench/results/holo_assets"
    target = probes(json.loads((assets / "scale-1.json").read_text()))[0]
    image = Image.open(assets / "scale-1.png").convert("RGB")
    client = Client()
    try:
        result = await client.call(request_body("holo4-35b-a3b", image, target["description"]))
    finally:
        await client.http.aclose()
    (tmp_path / "live-call.json").write_text(json.dumps(result, indent=2))
    print("Holo live usage:", json.dumps(result["usage"]), "status:", result["status"])
    assert result["point_normalized"] is not None
