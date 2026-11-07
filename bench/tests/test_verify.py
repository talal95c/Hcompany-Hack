import copy
import hashlib
import json
import os

import httpx
import pytest
from openai import AsyncOpenAI
from PIL import Image

from bench import verify
from bench.common import ROOT
from bench.verify_assets import ensure_assets, validate_manifest


def completion(value):
    return {"choices": [{"message": {"content": json.dumps(value)}}]}


@pytest.mark.parametrize("verdict", ["yes", "no", "unknown"])
def test_parse_verdict(verdict):
    value = {"verdict": verdict, "confidence": 0.8}
    assert verify.parse_verdict(completion(value)) == value
    assert (
        verify.parse_verdict(
            {
                "choices": [
                    {"message": {"tool_calls": [{"function": {"arguments": json.dumps(value)}}]}}
                ]
            }
        )
        == value
    )
    assert (
        verify.parse_verdict(
            {"choices": [{"message": {"content": "```json\n" + json.dumps(value) + "\n```"}}]}
        )
        == value
    )


@pytest.mark.parametrize(
    "value",
    [
        {},
        [],
        None,
        {"verdict": "true", "confidence": 1},
        {"verdict": "yes", "confidence": True},
        {"verdict": "yes", "confidence": "1"},
        {"verdict": "yes", "confidence": -1},
        {"verdict": "yes", "confidence": 1.1},
        {"verdict": "yes", "confidence": float("nan")},
        {"verdict": "yes", "confidence": float("inf")},
        {"verdict": "yes", "confidence": 1, "extra": "not allowed"},
    ],
)
def test_invalid_verdict(value):
    assert verify.parse_verdict(completion(value)) is None


@pytest.mark.parametrize(
    "response",
    [{}, {"choices": []}, {"choices": None}, {"choices": [{"message": {"content": "bad"}}]}],
)
def test_empty_verdict(response):
    assert verify.parse_verdict(response) is None


def sample(expected, verdict, confidence=1):
    return {
        "expected": expected,
        "result": {"verdict": verdict, "confidence": confidence} if verdict else None,
        "failure": None if verdict else "invalid_output",
        "latency_ms": 10,
        "request_latency_ms": 5,
        "attempts": [{"status": 200}],
    }


def test_metrics():
    data = [
        sample("yes", "yes"),
        sample("no", "no"),
        sample("no", "yes"),
        sample("yes", "unknown"),
        sample("yes", "yes", 0.79),
        sample("no", None),
    ]
    result = verify.aggregate(data)
    assert result["accuracy"] == 2 / 6
    assert result["yes_precision"] == 1 / 2
    assert result["yes_recall"] == 1 / 3
    assert result["unknown_rate"] == 2 / 6
    assert result["failures"] == 1
    assert result["confusion"] == {
        "yes": {"yes": 1, "no": 0, "unknown": 2, "failure": 0},
        "no": {"yes": 1, "no": 1, "unknown": 0, "failure": 1},
    }
    assert result["latency"]["p95_ms"] == 10
    assert verify.aggregate([sample("yes", "no")])["yes_precision"] is None
    assert verify.aggregate([])["accuracy"] is None
    assert verify.aggregate([])["latency"]["count"] == 0


@pytest.fixture
def manifest(tmp_path):
    image = tmp_path / "image.png"
    Image.new("RGB", (100, 80), "white").save(image)
    scenes = []
    for app in ("calc", "blender"):
        for index in range(10):
            identifier = f"{app}-{index}"
            scenes.append(
                {
                    "id": identifier,
                    "app": app,
                    "sensor": "accessibility" if app == "calc" else "bpy",
                    "image": "image.png",
                    "image_size": [100, 80],
                    "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                    "evidence": {"facts": {"positive": True, "negative": False}},
                    "questions": [
                        {
                            "id": identifier + suffix,
                            "assertion": "Question ?",
                            "expected": gold,
                            "fact": fact,
                        }
                        for suffix, gold, fact in [
                            ("-yes", "yes", "positive"),
                            ("-no", "no", "negative"),
                        ]
                    ],
                }
            )
    return {"version": 1, "scenes": scenes}, tmp_path


async def test_manifest_reuse_and_region(manifest):
    data, root = manifest
    validate_manifest(data, root)
    (root / "manifest.json").write_text(json.dumps(data))
    assert await ensure_assets(root, "/does-not-exist", reuse=True) == data
    data["scenes"][0]["questions"][0]["region"] = {"x": 500, "y": 0, "w": 500, "h": 500}
    validate_manifest(data, root)
    assert verify.question_image(
        root / "image.png", data["scenes"][0]["questions"][0]["region"]
    ).size == (50, 40)


@pytest.mark.parametrize(
    "mutation",
    ["empty", "hash", "path", "sensor", "labels", "fact", "duplicate", "region", "size", "missing"],
)
def test_invalid_manifest(manifest, mutation):
    data, root = manifest
    scene = data["scenes"][0]
    if mutation == "empty":
        data["scenes"] = []
    elif mutation == "hash":
        scene["sha256"] = "invalid"
    elif mutation == "path":
        scene["image"] = "../image.png"
    elif mutation == "sensor":
        scene["sensor"] = "visual"
    elif mutation == "labels":
        scene["questions"][0]["expected"] = "no"
    elif mutation == "fact":
        scene["evidence"]["facts"]["positive"] = False
    elif mutation == "duplicate":
        data["scenes"][1] = copy.deepcopy(scene)
    elif mutation == "region":
        scene["questions"][0]["region"] = {"x": 999, "y": 0, "w": 2, "h": 1000}
    elif mutation == "size":
        scene["image_size"] = [1, 1]
    else:
        del scene["evidence"]
    with pytest.raises(ValueError):
        validate_manifest(data, root)


async def test_missing_manifest(tmp_path):
    with pytest.raises(FileNotFoundError):
        await ensure_assets(tmp_path, "/unused", reuse=True)


def test_request():
    body = verify.request_body("holo4-27b", Image.new("RGB", (10, 10)), "Question ?")
    assert body["extra_body"] == {
        "structured_outputs": {"json": verify.SCHEMA},
        "chat_template_kwargs": {"enable_thinking": False},
    }
    assert body["messages"][1]["content"][1]["text"] == "Question ?"
    assert "expected" not in json.dumps(body)


async def test_client_retry_and_invalid_output(monkeypatch):
    monkeypatch.setenv("HAI_API_KEY", "unit-test")
    responses = [429, 503, 200, 400, 200]
    sent = []

    async def handler(request):
        sent.append(json.loads(request.content))
        code = responses.pop(0)
        payload = {
            "id": "unit",
            "object": "chat.completion",
            "created": 0,
            "model": "holo4-27b",
            **completion({"verdict": "yes", "confidence": 0.9}),
        }
        if len(sent) == 5:
            payload["choices"][0]["message"]["content"] = "invalid"
        return httpx.Response(
            code, json=payload, headers={"retry-after": "2"} if code == 429 else {}
        )

    client = verify.Client()
    await client.api.close()
    client.api = AsyncOpenAI(
        api_key="unit-test",
        base_url="https://unit.invalid/v1",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    class Pacer:
        def __init__(self):
            self.observed = []

        async def acquire(self):
            return {"pacing_wait_ms": 0, "cooldown_wait_ms": 0}

        def observe(self, status, headers, retry):
            self.observed.append(status)

    client.pacer = Pacer()
    try:
        body = verify.request_body("holo4-27b", Image.new("RGB", (10, 10)), "Question ?")
        result = await client.call(body)
        assert result["failure"] is None
        assert [attempt["status"] for attempt in result["attempts"]] == [429, 503, 200]
        assert sent[0]["chat_template_kwargs"] == {"enable_thinking": False}
        assert sent[0]["structured_outputs"]["json"] == verify.SCHEMA
        assert (await client.call(body))["failure"] == "http_or_transport"
        assert (await client.call(body))["failure"] == "invalid_output"
        assert client.pacer.observed == [429, 503, 200, 400, 200]
    finally:
        await client.api.close()


@pytest.mark.parametrize(
    "options",
    [
        {"repeats": 0},
        {"timeout": 0},
        {"models": ["invalid"]},
        {"min_confidence": 1.1},
        {"limit": 0},
    ],
)
async def test_invalid_options(tmp_path, options):
    with pytest.raises(ValueError):
        await verify.run(tmp_path, **options)


@pytest.mark.live
async def test_verify_live(tmp_path):
    if not os.environ.get("HAI_API_KEY"):
        pytest.skip("HAI_API_KEY absente")
    root = ROOT / "bench/results/verify_assets"
    data = await ensure_assets(
        root, "/opt/blender/blender", reuse=(root / "manifest.json").exists()
    )
    validate_manifest(data, root)
    client = verify.Client()
    try:
        for app in ("calc", "blender"):
            scene = next(s for s in data["scenes"] if s["app"] == app)
            for question in scene["questions"]:
                image = verify.question_image(root / scene["image"], question.get("region"))
                result = await client.call(
                    verify.request_body("holo4-27b", image, question["assertion"])
                )
                assert result["failure"] is None, result
                assert result["result"]["verdict"] in ("yes", "no", "unknown")
                assert result["latency_ms"] > 0
    finally:
        await client.api.close()
