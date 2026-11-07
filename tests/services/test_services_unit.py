from __future__ import annotations

import asyncio
import base64
import json
import math
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
import websockets

from engine.services import errors
from engine.services.computer_use import run_steps
from engine.services.gladia import (
    GladiaLiveSession,
    GladiaSttClient,
    decode_audio_chunk,
    parse_live_message,
    parse_prerecorded,
)
from engine.services.holo import LOCATE_SYSTEM_PROMPT, HoloCloudClient, parse_tool_action
from engine.services.jev import INTENT_QUESTION, CodivJevClient
from engine.services.latency import LatencyRecorder, percentile
from engine.services.linkup import LinkupSearchClient, parse_search
from engine.services.profiles import list_profiles, load_profile, profile_for_lesson_app
from engine.services.protocols import (
    HoloAction,
    HoloClient,
    JevClient,
    Location,
    Region,
    SearchClient,
    SttClient,
)
from engine.services.verify import VERIFY_SYSTEM_PROMPT, HoloVerifier, Verification
from engine.services.x11 import XdotoolExecutor, capture_x11

from .conftest import FIXTURES, contract_example, validate_contract

PNG = (FIXTURES / "blender_4.5.9_layout_1600x900.png").read_bytes()


def test_profiles_validate_and_match_folders() -> None:
    from jsonschema import Draft202012Validator

    root = Path(__file__).resolve().parents[2] / "apps"
    validator = Draft202012Validator(json.loads((root / "profile.schema.json").read_text()))
    profiles = list_profiles()
    assert {p.id for p in profiles} == {
        "blender",
        "excel",
        "libreoffice-calc",
        "photoshop",
        "generic",
    }
    for path in root.glob("*/profile.json"):
        data = json.loads(path.read_text())
        validator.validate(data)
        assert data["id"] == path.parent.name
        assert load_profile(data["id"]) is load_profile(data["id"])


def test_profile_fallback_and_lesson_display_name() -> None:
    assert load_profile(None).id == "generic"
    assert load_profile("unknown").id == "generic"
    assert load_profile("../excel").id == "generic"
    assert profile_for_lesson_app({}).id == "generic"
    profile = profile_for_lesson_app({"id": "unknown", "name": "Custom App", "version": "1"})
    assert profile.id == "generic" and profile.name == "Custom App"
    assert profile_for_lesson_app({"id": "excel"}).id == "excel"


def test_invalid_profiles_rejected(tmp_path, monkeypatch) -> None:
    from jsonschema import ValidationError

    root = Path(__file__).resolve().parents[2] / "apps"
    (tmp_path / "profile.schema.json").write_text((root / "profile.schema.json").read_text())
    folder = tmp_path / "generic"
    folder.mkdir()
    data = json.loads((root / "generic/profile.json").read_text())
    path = folder / "profile.json"
    data["extra"] = True
    path.write_text(json.dumps(data))
    monkeypatch.setenv("HCOMPANY_APPS_DIR", str(tmp_path))
    with pytest.raises(ValidationError):
        load_profile(None)
    del data["extra"]
    data["id"] = "wrong"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="folder"):
        load_profile(None)
    path.unlink()
    with pytest.raises(FileNotFoundError):
        load_profile(None)


def test_generic_service_sources_and_instructions() -> None:
    from engine.services.jev import deviation_question, intent_question, stuck_question

    root = Path(__file__).resolve().parents[2]
    for path in (root / "engine/services").glob("*.py"):
        assert "blender" not in path.read_text().lower(), path
    for profile in list_profiles():
        if profile.id == "blender":
            continue
        for builder in (intent_question, stuck_question, deviation_question):
            question = builder(profile)
            assert profile.name in question.instructions
            assert profile.jev_context in question.instructions
            assert "blender" not in str(question.to_api()).lower()
        schema = profile.answer_schema()
        assert "blender" not in json.dumps(schema).lower()
        assert schema["required"] == ["answer"]
        assert "app_version" in schema["properties"]


async def test_profile_linkup_domains_and_overrides() -> None:
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"data": {"answer": "ok"}})

    async with LinkupSearchClient(
        api_key="k", profile=load_profile("excel"), transport=httpx.MockTransport(handler)
    ) as client:
        await client.search("formula")
        await client.search("formula", domains=(), schema={"type": "object"})
        await client.search("formula", profile=load_profile(None))
    assert calls[0]["includeDomains"] == ["support.microsoft.com", "learn.microsoft.com"]
    assert "formula" in json.loads(calls[0]["structuredOutputSchema"])["properties"]
    assert "includeDomains" not in calls[1]
    assert json.loads(calls[1]["structuredOutputSchema"]) == {"type": "object"}
    assert "includeDomains" not in calls[2]


async def test_profile_gladia_file_and_live_vocabulary() -> None:
    calls = []

    def handler(request):
        if request.url.path.endswith("/upload"):
            return httpx.Response(200, json={"audio_url": "https://example.test/audio"})
        if request.method == "POST":
            calls.append(json.loads(request.content))
            return httpx.Response(200, json={"id": "job"})
        return httpx.Response(200, json={"status": "done"})

    profile = load_profile("excel")
    async with GladiaSttClient(
        api_key="k", profile=profile, transport=httpx.MockTransport(handler)
    ) as client:
        await client.transcribe_file(b"RIFF", filename="a.wav")
        await client.transcribe_file(b"RIFF", filename="a.wav", vocabulary=())
        live = client.live_config()
        assert live["realtime_processing"]["custom_vocabulary_config"]["vocabulary"] == list(
            profile.vocabulary
        )
        assert "realtime_processing" not in client.live_config(vocabulary=())
        with pytest.raises(ValueError, match="vide"):
            await client.transcribe_file(b"", filename="a.wav")
    assert calls[0]["custom_vocabulary_config"]["vocabulary"] == list(profile.vocabulary)
    assert "custom_vocabulary" not in calls[1]


async def test_profile_jev_client_overrides() -> None:
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        choices = {"intent": "question", "stuck_or_thinking": "thinking", "deviation": "none"}
        return httpx.Response(
            200, json={"answers": {key: {"choice": choices[key]} for key in body["questions"]}}
        )

    async with CodivJevClient(
        api_key="k", profile=load_profile("excel"), transport=httpx.MockTransport(handler)
    ) as client:
        await client.classify_intent("Pourquoi ?")
        await client.assess({}, include_intent=True, profile=load_profile("photoshop"))
    assert "Microsoft Excel" in calls[0]["questions"]["intent"]["instructions"]
    assert all("Adobe Photoshop" in q["instructions"] for q in calls[1]["questions"].values())


# --- protocols & contrats ---------------------------------------------------------------


def test_region_maps_crop_to_full_capture() -> None:
    region = Region(500, 0, 1000, 500)
    assert region.to_full(0, 0) == (500, 0)
    assert region.to_full(1000, 1000) == (1000, 500)
    assert region.to_full(500, 500) == (750, 250)
    with pytest.raises(ValueError):
        Region(10, 10, 5, 20)
    with pytest.raises(ValueError):
        Region(0, 0, 1001, 10)


def test_pointer_and_input_action_validate_against_commands_contract() -> None:
    pointer = contract_example("commands", "pointer")
    pointer["payload"] = Location(178.0, 45.0, 0.9).pointer_payload("cap7", 3)
    validate_contract("commands", pointer)
    for action in (
        HoloAction("click", x=175, y=42),
        HoloAction("type", text="2"),
        HoloAction("key", keys=("shift", "a")),
    ):
        cmd = contract_example("commands", "input.action")
        cmd["payload"] = action.input_action_payload("cap7", "tok")
        validate_contract("commands", cmd)
    with pytest.raises(ValueError):
        HoloAction("done").native()


def test_clients_satisfy_protocols() -> None:
    holo = HoloCloudClient(client=FakeOpenAI([]))
    jev = CodivJevClient(api_key="k", transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    stt = GladiaSttClient(api_key="k", transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    search = LinkupSearchClient(
        api_key="k", transport=httpx.MockTransport(lambda r: httpx.Response(200))
    )
    assert isinstance(holo, HoloClient)
    assert isinstance(jev, JevClient)
    assert isinstance(stt, SttClient)
    assert isinstance(search, SearchClient)


def test_missing_keys_raise_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("HAI_API_KEY", "CODIV_API_KEY", "GLADIA_API_KEY", "LINKUP_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    for cls in (HoloCloudClient, CodivJevClient, GladiaSttClient, LinkupSearchClient):
        with pytest.raises(errors.ServiceUnavailable):
            cls()


# --- latence ----------------------------------------------------------------------------


def test_percentile_and_bench(tmp_path: Path) -> None:
    assert percentile([1, 2, 3, 4], 50) == 2.5
    assert percentile([10], 95) == 10
    assert math.isnan(percentile([], 50))
    rec = LatencyRecorder()
    for _ in range(3):
        with rec.measure("svc", "op") as ctx:
            ctx.request_id = "r"
    with pytest.raises(errors.ServiceTimeout), rec.measure("svc", "op"):
        raise errors.ServiceTimeout("svc", "slow")
    summary = rec.summary()["svc.op"]
    assert summary["n"] == 4 and summary["n_ok"] == 3 and summary["failures"] == {"timeout": 1}
    out = rec.write_bench(tmp_path / "b.json", extra={"note": "x"})
    assert json.loads((tmp_path / "b.json").read_text())["note"] == "x"
    assert out["measured"] is True


# --- Holo -------------------------------------------------------------------------------


def _completion(
    content: str | None = None,
    tool: tuple[str, dict[str, Any]] | None = None,
    logprobs: list[float] | None = None,
) -> SimpleNamespace:
    tool_calls = None
    if tool is not None:
        tool_calls = [
            SimpleNamespace(function=SimpleNamespace(name=tool[0], arguments=json.dumps(tool[1])))
        ]
    lp = None
    if logprobs is not None:
        lp = SimpleNamespace(
            content=[SimpleNamespace(token=str(i), logprob=v) for i, v in enumerate(logprobs)]
        )
    return SimpleNamespace(
        id="chatcmpl-test",
        usage=SimpleNamespace(
            prompt_tokens=1100,
            completion_tokens=8,
            prompt_tokens_details=SimpleNamespace(cached_tokens=1056),
        ),
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content, tool_calls=tool_calls), logprobs=lp
            )
        ],
    )


class FakeOpenAI:
    def __init__(self, responses: list[Any], delay: float = 0.0) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []
        self.delay = delay
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.delay:
            await asyncio.sleep(self.delay)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def close(self) -> None:
        return None


@pytest.mark.parametrize("verdict", ["pass", "fail", "unknown"])
async def test_verifier_shape_and_verdict(verdict) -> None:
    fake = FakeOpenAI(
        [
            _completion(
                json.dumps({"verdict": verdict, "confidence": 0.9, "reason": "visible evidence"})
            )
        ]
    )
    async with HoloVerifier(client=fake) as verifier:
        result = await verifier.verify(
            PNG,
            "The total is visible",
            region=Region(0, 0, 500, 500),
            profile=load_profile("excel"),
        )
    assert result.verdict == verdict and result.confidence == 0.9
    assert result.request_id == "chatcmpl-test" and result.latency_ms >= 0
    assert verifier.recorder.records[0].operation == "verify"
    call = fake.calls[0]
    assert call["model"] == "holo4-27b"
    assert call["temperature"] == 0 and call["logprobs"] is True
    assert call["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
    schema = call["response_format"]
    assert schema["type"] == "json_schema" and schema["json_schema"]["strict"] is True
    assert schema["json_schema"]["schema"]["properties"]["verdict"]["enum"] == [
        "pass",
        "fail",
        "unknown",
    ]
    assert call["messages"][0]["content"] == VERIFY_SYSTEM_PROMPT
    user = call["messages"][1]["content"]
    assert "Application: Microsoft Excel" in user[0]["text"]
    assert "evidence region" in user[0]["text"].lower()
    assert user[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert "Microsoft Excel" not in VERIFY_SYSTEM_PROMPT


@pytest.mark.parametrize("verdict", ["pass", "fail", "unknown"])
async def test_verifier_low_confidence(verdict) -> None:
    fake = FakeOpenAI(
        [_completion(json.dumps({"verdict": verdict, "confidence": 0.2, "reason": "unclear"}))]
    )
    result = await HoloVerifier(client=fake).verify(PNG, "The goal is reached")
    assert result.verdict == "unknown" and result.confidence == 0.2


async def test_verifier_prefers_verdict_logprobs() -> None:
    content = '{"verdict":"pass","confidence":0.99,"reason":"pass"}'
    response = _completion(content)
    response.choices[0].logprobs = SimpleNamespace(
        content=[
            SimpleNamespace(token='{"verdict":"', logprob=-10),
            SimpleNamespace(token="pa", logprob=math.log(0.5)),
            SimpleNamespace(token="ss", logprob=math.log(0.8)),
            SimpleNamespace(token='","confidence":0.99,"reason":"pass"}', logprob=-10),
        ]
    )
    result = await HoloVerifier(client=FakeOpenAI([response])).verify(PNG, "Visible")
    assert result.confidence == pytest.approx(0.4)
    assert result.verdict == "unknown"


@pytest.mark.parametrize(
    "content",
    [
        None,
        "",
        "not json",
        "[]",
        "{}",
        '{"verdict":"maybe","confidence":0.9,"reason":"x"}',
        '{"verdict":"pass","confidence":2,"reason":"x"}',
        '{"verdict":"pass","confidence":true,"reason":"x"}',
        '{"verdict":"pass","confidence":NaN,"reason":"x"}',
        '{"verdict":"pass","confidence":0.9,"reason":null}',
    ],
)
async def test_verifier_malformed_response(content) -> None:
    verifier = HoloVerifier(client=FakeOpenAI([_completion(content)]))
    with pytest.raises(errors.InvalidResponse):
        await verifier.verify(PNG, "Visible")


async def test_verifier_model_and_empty_inputs(monkeypatch) -> None:
    monkeypatch.setenv("HOLO_VERIFY_MODEL", "verify-test")
    verifier = HoloVerifier(client=FakeOpenAI([]))
    assert verifier.model == "verify-test"
    assert HoloVerifier(client=FakeOpenAI([]), model="explicit").model == "explicit"
    with pytest.raises(ValueError, match="assertion"):
        await verifier.verify(PNG, "")
    with pytest.raises(ValueError, match="PNG"):
        await verifier.verify(b"bad", "Visible")
    with pytest.raises(ValueError, match="min_confidence"):
        HoloVerifier(client=FakeOpenAI([]), min_confidence=2)


async def test_verifier_region_crops_png_pixels() -> None:
    import io

    image_module = pytest.importorskip("PIL.Image")
    fake = FakeOpenAI([_completion('{"verdict":"unknown","confidence":0.5,"reason":"test"}')])
    image = image_module.new("RGB", (200, 100), "red")
    image.paste("blue", (100, 0, 200, 100))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    await HoloVerifier(client=fake).verify(
        buffer.getvalue(), "Visible", region=Region(500, 0, 1000, 500)
    )
    url = fake.calls[0]["messages"][1]["content"][1]["image_url"]["url"]
    cropped = image_module.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1])))
    assert cropped.size == (100, 50)
    assert cropped.getpixel((0, 0)) == (0, 0, 255)


def test_holo_normalizes_return_key_to_native_enter() -> None:
    response = _completion(tool=("key", {"keys": ["Return"]}))
    action = parse_tool_action(response.choices[0].message)
    assert action.keys == ("enter",)
    assert action.native() == {"type": "key", "keys": ["enter"]}


async def test_verifier_region_without_pillow(monkeypatch) -> None:
    import builtins

    original_import = builtins.__import__

    def without_pillow(name, *args, **kwargs):
        if name == "PIL":
            raise ImportError("Pillow absent")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_pillow)
    fake = FakeOpenAI([_completion('{"verdict":"unknown","confidence":0.5,"reason":"test"}')])
    await HoloVerifier(client=fake).verify(PNG, "Visible", region=Region(0, 0, 500, 500))
    user = fake.calls[0]["messages"][1]["content"]
    assert "Evidence region (normalized" in user[0]["text"]
    assert base64.b64decode(user[1]["image_url"]["url"].split(",", 1)[1]) == PNG


async def test_step_loop_success_and_fresh_verification() -> None:
    from unittest.mock import AsyncMock

    action = HoloAction("click", x=500, y=500)
    holo = SimpleNamespace(act=AsyncMock(side_effect=[action, HoloAction("done")]))
    capture = AsyncMock(side_effect=[b"first", b"second", b"fresh"])
    execute = AsyncMock(return_value="clicked")
    verification = Verification("pass", 0.9, "visible", 1, "r")
    verifier = SimpleNamespace(verify=AsyncMock(return_value=verification))
    profile = load_profile("excel")
    result = await run_steps(
        holo,
        "Show total",
        capture=capture,
        execute=execute,
        verifier=verifier,
        success_assertion="Total visible",
        profile=profile,
        settle_s=0,
    )
    assert result.status == "success" and result.final is verification
    assert len(result.turns) == len(result.latencies_ms) == 2
    execute.assert_awaited_once_with(action)
    verifier.verify.assert_awaited_once_with(b"fresh", "Total visible", profile=profile)
    assert holo.act.call_args.kwargs["history"][0].outcome == "clicked"
    assert profile.jev_context in holo.act.call_args.kwargs["lesson_context"]


@pytest.mark.parametrize("rejected", ["fail", "unknown"])
async def test_step_loop_rejected_done_then_success(rejected) -> None:
    from unittest.mock import AsyncMock

    holo = SimpleNamespace(act=AsyncMock(return_value=HoloAction("done")))
    execute = AsyncMock()
    verifier = SimpleNamespace(
        verify=AsyncMock(
            side_effect=[
                Verification(rejected, 0.9, "not visible", 0),
                Verification("pass", 0.9, "visible", 0),
            ]
        )
    )
    result = await run_steps(
        holo,
        "goal",
        capture=AsyncMock(return_value=PNG),
        execute=execute,
        verifier=verifier,
        settle_s=0,
    )
    assert result.status == "success"
    assert holo.act.call_args.kwargs["history"][0].outcome == "done rejected: not visible"
    assert verifier.verify.call_args.args[1] == "goal"
    execute.assert_not_awaited()


async def test_step_loop_stops_without_action_and_zero_steps() -> None:
    from unittest.mock import AsyncMock

    stop = asyncio.Event()
    stop.set()
    capture, execute = AsyncMock(), AsyncMock()
    result = await run_steps(SimpleNamespace(), "goal", capture=capture, execute=execute, stop=stop)
    assert result.status == "stopped" and result.turns == result.latencies_ms == ()
    capture.assert_not_awaited()
    result = await run_steps(
        SimpleNamespace(), "goal", capture=capture, execute=execute, max_steps=0
    )
    assert result.status == "max_steps" and not result.turns
    capture.assert_not_awaited()


async def test_step_loop_stop_during_model_call() -> None:
    from unittest.mock import AsyncMock

    stop = asyncio.Event()
    cancelled = asyncio.Event()

    async def act(*args, **kwargs):
        stop.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    execute = AsyncMock()
    result = await run_steps(
        SimpleNamespace(act=act),
        "goal",
        capture=AsyncMock(return_value=PNG),
        execute=execute,
        stop=stop,
    )
    assert result.status == "stopped" and cancelled.is_set()
    execute.assert_not_awaited()


async def test_step_loop_max_steps_errors_and_cancellation() -> None:
    from unittest.mock import AsyncMock

    holo = SimpleNamespace(act=AsyncMock(return_value=HoloAction("key", keys=("tab",))))
    capture, execute = AsyncMock(return_value=PNG), AsyncMock(return_value="executed")
    result = await run_steps(
        holo, "goal", capture=capture, execute=execute, max_steps=2, settle_s=0
    )
    assert result.status == "max_steps" and len(result.turns) == 2
    assert len(result.latencies_ms) == 2
    execute.side_effect = RuntimeError("input failed")
    result = await run_steps(holo, "goal", capture=capture, execute=execute, settle_s=0)
    assert result.status == "error" and result.error == "RuntimeError: input failed"
    assert result.turns[0].outcome.startswith("error:")
    capture.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await run_steps(holo, "goal", capture=capture, execute=execute)


async def test_step_loop_unknown_never_succeeds_and_unverified_done() -> None:
    from unittest.mock import AsyncMock

    holo = SimpleNamespace(act=AsyncMock(return_value=HoloAction("done")))
    verifier = SimpleNamespace(
        verify=AsyncMock(return_value=Verification("unknown", 0.5, "ambiguous", 0))
    )
    capture, execute = AsyncMock(return_value=PNG), AsyncMock()
    result = await run_steps(
        holo, "goal", capture=capture, execute=execute, verifier=verifier, max_steps=1
    )
    assert result.status == "max_steps" and result.final.verdict == "unknown"
    result = await run_steps(holo, "goal", capture=capture, execute=execute)
    assert result.status == "success" and result.final is None
    execute.assert_not_awaited()


@pytest.mark.parametrize(
    "window_id,geometry,action,point",
    [
        (
            "42",
            b"X=100\nY=200\nWIDTH=1001\nHEIGHT=501\n",
            HoloAction("click", x=500, y=1000, button="right"),
            ("600", "700"),
        ),
        (None, b"1920 1080\n", HoloAction("click", x=1000, y=0), ("1919", "0")),
    ],
)
async def test_xdotool_coordinate_mapping(monkeypatch, window_id, geometry, action, point) -> None:
    from unittest.mock import AsyncMock

    command = AsyncMock(side_effect=[geometry, b"", b""])
    monkeypatch.setattr("engine.services.x11._command", command)
    assert await XdotoolExecutor(window_id)(action) == "executed"
    assert command.await_args_list[1].args == ("xdotool", "mousemove", "--sync", *point)
    assert command.await_args_list[2].args == (
        "xdotool",
        "click",
        "3" if action.button == "right" else "1",
    )


async def test_xdotool_text_keys_capture_and_invalid_actions(monkeypatch) -> None:
    from unittest.mock import AsyncMock

    command = AsyncMock(return_value=PNG)
    monkeypatch.setattr("engine.services.x11._command", command)
    executor = XdotoolExecutor(42)
    await executor(HoloAction("type", text="-- literal text"))
    assert command.call_args.args == (
        "xdotool",
        "type",
        "--clearmodifiers",
        "--",
        "-- literal text",
    )
    await executor(HoloAction("key", keys=("ctrl", "enter")))
    assert command.call_args.args == ("xdotool", "key", "--clearmodifiers", "ctrl+Return")
    assert await capture_x11(42) == PNG
    assert command.call_args.args == ("import", "-window", "42", "png:-")
    await capture_x11()
    assert command.call_args.args == ("import", "-window", "root", "png:-")
    for action in [
        HoloAction("done"),
        HoloAction("click", x=-1, y=0),
        HoloAction("type"),
        HoloAction("key", keys=("invalid",)),
    ]:
        with pytest.raises(ValueError):
            await executor(action)


async def test_holo_locate_request_shape_and_region() -> None:
    fake = FakeOpenAI(
        [
            _completion('{"x": 178, "y": 45}', logprobs=[-0.01, -0.02]),
            _completion('{"x": 500, "y": 500}'),
        ]
    )
    holo = HoloCloudClient(client=fake)
    x, y, conf = await holo.locate(PNG, "the Add menu")
    assert (x, y) == (178, 45) and 0.97 < conf <= 1
    loc = await holo.locate_detailed(PNG, "Cube", region=Region(800, 100, 1000, 300))
    assert (loc.x, loc.y) == (900, 200) and math.isnan(loc.confidence)
    first, second = fake.calls
    assert first["temperature"] == 0
    assert first["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
    assert (
        first["messages"][0]
        == second["messages"][0]
        == {"role": "system", "content": LOCATE_SYSTEM_PROMPT}
    )
    assert first["response_format"]["json_schema"]["strict"] is True
    assert holo.recorder.records[0].cached_tokens == 1056


@pytest.mark.parametrize("content", ['{"x": 1200, "y": 4}', "not json", "[1, 2]", '{"x": "a"}'])
async def test_holo_locate_rejects_invalid_points(content: str) -> None:
    holo = HoloCloudClient(client=FakeOpenAI([_completion(content), _completion(content)]))
    with pytest.raises(errors.InvalidResponse):
        await holo.locate(PNG, "the Add menu")


async def test_holo_input_validation_and_timeout() -> None:
    holo = HoloCloudClient(client=FakeOpenAI([]))
    with pytest.raises(ValueError):
        await holo.locate(b"GIF89a", "x")
    with pytest.raises(ValueError):
        await holo.locate(PNG, "  ")
    slow = HoloCloudClient(
        client=FakeOpenAI([_completion("{}")] * 2, delay=1), locate_timeout_s=0.05
    )
    with pytest.raises(errors.ServiceTimeout):
        await slow.locate(PNG, "the Add menu")
    assert [r.status for r in slow.recorder.records] == ["timeout", "timeout"]


async def test_holo_act_sends_tools_and_history() -> None:
    from engine.services.protocols import ActTurn

    fake = FakeOpenAI([_completion(tool=("key", {"keys": ["Shift", "A"], "reason": "add menu"}))])
    holo = HoloCloudClient(client=fake)
    action = await holo.act(PNG, "Add a torus", history=[ActTurn(HoloAction("click", x=1, y=2))])
    assert action == HoloAction(
        "key", keys=("shift", "a"), reason="add menu", request_id="chatcmpl-test"
    )
    call = fake.calls[0]
    assert {t["function"]["name"] for t in call["tools"]} == {"click", "type", "key", "done"}
    assert call["tool_choice"] == "required"
    assert '"x": 1' in call["messages"][1]["content"][0]["text"]


def _msg(name: str, args: Any) -> SimpleNamespace:
    raw = args if isinstance(args, str) else json.dumps(args)
    return SimpleNamespace(
        tool_calls=[SimpleNamespace(function=SimpleNamespace(name=name, arguments=raw))]
    )


def test_parse_tool_action_cases() -> None:
    assert parse_tool_action(_msg("click", {"x": 10, "y": 20, "button": "right"})).button == "right"
    assert parse_tool_action(_msg("type", {"text": "0.5"})).text == "0.5"
    assert parse_tool_action(_msg("key", {"keys": "ctrl+z"})).keys == ("ctrl", "z")
    assert parse_tool_action(_msg("done", {})).type == "done"
    for bad in (
        _msg("click", {"x": -1, "y": 2}),
        _msg("click", {"x": 1, "y": 2, "button": "x"}),
        _msg("type", {"text": ""}),
        _msg("key", {"keys": ["rm -rf"]}),
        _msg("drag", {}),
        _msg("click", "{oops"),
        SimpleNamespace(tool_calls=None),
    ):
        with pytest.raises(errors.InvalidResponse):
            parse_tool_action(bad)


# --- Jev --------------------------------------------------------------------------------


def _jev_answer(choices: dict[str, tuple[str, dict[str, float]]]) -> dict[str, Any]:
    return {
        "answers": {
            q: {"choice": c, "probabilities": p, "confidence": 0.9} for q, (c, p) in choices.items()
        }
    }


async def test_jev_batched_decisions() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(
            200,
            headers={"x-request-id": "req_1"},
            json=_jev_answer(
                {
                    "stuck_or_thinking": ("stuck", {"stuck": 0.8, "thinking": 0.2}),
                    "deviation": ("minor", {"none": 0.1, "minor": 0.7, "major": 0.2}),
                    "intent": ("chut", {"chut": 0.95, "other": 0.05}),
                }
            ),
        )

    async with CodivJevClient(api_key="k", transport=httpx.MockTransport(handler)) as jev:
        out = await jev.assess({"utterance": "chut", "idle_s": 40}, include_intent=True)
    assert len(seen) == 1 and set(seen[0]["questions"]) == {
        "stuck_or_thinking",
        "deviation",
        "intent",
    }
    assert seen[0]["model"] == "openjev-latest"
    assert seen[0]["questions"]["intent"]["criteria"] == dict(INTENT_QUESTION.criteria or {})
    assert out["stuck_or_thinking"].choice == "stuck" and out["deviation"].probability == 0.7
    assert out["intent"].request_id == "req_1"


@pytest.mark.parametrize(
    ("status", "body", "exc"),
    [
        (429, {}, errors.QuotaExceeded),
        (401, {}, errors.AuthenticationError),
        (503, {}, errors.ServiceUnavailable),
        (422, {}, errors.InvalidRequest),
        (200, {"answers": {}}, errors.InvalidResponse),
        (200, _jev_answer({"intent": ("maybe", {"maybe": 1.0})}), errors.InvalidResponse),
    ],
)
async def test_jev_errors(status: int, body: dict[str, Any], exc: type[Exception]) -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(status, json=body))
    async with CodivJevClient(api_key="k", transport=transport) as jev:
        with pytest.raises(exc):
            await jev.classify_intent("bonjour")


async def test_jev_800ms_timeout_and_speculative_budget() -> None:
    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(2)
        return httpx.Response(200, json={})

    async with CodivJevClient(api_key="k", transport=httpx.MockTransport(slow)) as jev:
        assert jev.timeout_s == 0.8
        loop = asyncio.get_running_loop()
        start = loop.time()
        with pytest.raises(errors.ServiceTimeout):
            await jev.classify_intent("bonjour")
        assert loop.time() - start < 1.2
        jev.bucket.tokens, jev.bucket._loop_time = 10.5, loop.time()
        with pytest.raises(errors.QuotaExceeded):
            await jev.decide({"u": 1}, {"intent": INTENT_QUESTION}, speculative=True)


# --- Linkup -----------------------------------------------------------------------------


def test_linkup_parse_variants() -> None:
    res = parse_search(
        "q",
        {
            "data": {"answer": "Shift+A"},
            "sources": [
                {"name": "Torus", "url": "https://docs.blender.org/x", "snippet": "s"},
                {"name": "no url"},
            ],
        },
    )
    assert res.answer == "Shift+A" and len(res.sources) == 1
    assert parse_search("q", {"answer": "a", "sources": []}).answer == "a"
    assert parse_search("q", {"data": '{"answer": "b"}'}).answer == "b"
    with pytest.raises(errors.InvalidResponse):
        parse_search("q", [])


async def test_linkup_request_and_retry() -> None:
    calls: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        if len(calls) == 1:
            return httpx.Response(503, text="busy")
        return httpx.Response(200, json={"data": {"answer": "ok"}, "sources": []})

    async with LinkupSearchClient(api_key="k", transport=httpx.MockTransport(handler)) as lk:
        res = await lk.search("torus")
        with pytest.raises(ValueError):
            await lk.search(" ")
    assert res.answer == "ok" and len(calls) == 2
    body = calls[0]
    assert body["outputType"] == "structured" and body["includeSources"] is True
    assert "includeDomains" not in body
    assert json.loads(body["structuredOutputSchema"])["required"] == ["answer"]
    statuses = [r.status for r in lk.recorder.records]
    assert statuses == ["unavailable", "ok"]


# --- Gladia -----------------------------------------------------------------------------

WORDS = [{"word": " Ajoute", "start": 0.19, "end": 0.49, "confidence": 0.98}]


def test_gladia_parse_live_and_prerecorded() -> None:
    partial = parse_live_message(
        {
            "type": "transcript",
            "data": {"id": "u1", "is_final": False, "utterance": {"text": " Ajou", "words": WORDS}},
        },
        1.0,
    )
    assert partial is not None and partial.kind == "partial" and partial.text == "Ajou"
    final = parse_live_message(
        {
            "type": "transcript",
            "data": {"id": "u1", "is_final": True, "utterance": {"text": "Ajoute", "words": WORDS}},
        },
        2.0,
    )
    assert final is not None and final.kind == "final" and final.words[0].word == "Ajoute"
    assert parse_live_message({"type": "speech_end", "data": {"time": 3.2}}, 0).kind == "speech_end"
    assert parse_live_message({"type": "audio_chunk", "acknowledged": True}, 0) is None
    tr = parse_prerecorded(
        {
            "result": {
                "metadata": {"audio_duration": 3.6},
                "transcription": {
                    "full_transcript": "Ajoute un tore",
                    "languages": ["fr"],
                    "utterances": [{"text": "Ajoute un tore", "words": WORDS}],
                },
            }
        },
        "job",
    )
    assert tr.text == "Ajoute un tore" and tr.language == "fr" and tr.duration_s == 3.6
    assert tr.words[0].start == 0.19


def test_decode_audio_chunk_from_contract() -> None:
    msg = contract_example("desktop-ws", "audio.chunk")
    msg["payload"]["data_base64"] = base64.b64encode(b"\x01\x00\x02\x00").decode()
    validate_contract("desktop-ws", msg)
    assert decode_audio_chunk(msg) == b"\x01\x00\x02\x00"
    msg["payload"]["sample_rate"] = 48000
    with pytest.raises(ValueError):
        decode_audio_chunk(msg)
    with pytest.raises(ValueError):
        decode_audio_chunk({"type": "ping", "payload": {}})


async def test_gladia_transcribe_file_flow() -> None:
    polls = {"n": 0}
    sent: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-gladia-key"] == "k"
        if request.url.path == "/v2/upload":
            return httpx.Response(200, json={"audio_url": "https://a/1"})
        if request.method == "POST":
            sent.update(json.loads(request.content))
            return httpx.Response(201, json={"id": "job1", "result_url": "x"})
        polls["n"] += 1
        if polls["n"] < 2:
            return httpx.Response(200, json={"id": "job1", "status": "processing"})
        return httpx.Response(
            200,
            json={
                "id": "job1",
                "status": "done",
                "result": {
                    "transcription": {"full_transcript": "Ajoute", "utterances": [{"words": WORDS}]}
                },
            },
        )

    async with GladiaSttClient(
        api_key="k", transport=httpx.MockTransport(handler), poll_interval_s=0.01
    ) as stt:
        tr = await stt.transcribe_file(b"RIFF", filename="a.wav", vocabulary=["tore", "tore"])
        with pytest.raises(ValueError):
            await stt.transcribe_file(b"", filename="a.wav")
    assert tr.text == "Ajoute" and tr.job_id == "job1" and polls["n"] == 2
    assert sent["custom_vocabulary"] is True
    assert sent["custom_vocabulary_config"] == {"vocabulary": ["tore"]}


async def test_gladia_job_error_and_timeout() -> None:
    def failing(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/upload":
            return httpx.Response(200, json={"audio_url": "u"})
        if request.method == "POST":
            return httpx.Response(201, json={"id": "j"})
        return httpx.Response(200, json={"status": "error", "error_code": 500})

    async with GladiaSttClient(api_key="k", transport=httpx.MockTransport(failing)) as stt:
        with pytest.raises(errors.ServiceError):
            await stt.transcribe_file(b"RIFF", filename="a.wav")

    def stuck(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/upload":
            return httpx.Response(200, json={"audio_url": "u"})
        if request.method == "POST":
            return httpx.Response(201, json={"id": "j"})
        return httpx.Response(200, json={"status": "queued"})

    async with GladiaSttClient(
        api_key="k", transport=httpx.MockTransport(stuck), poll_interval_s=0.01, file_timeout_s=0.05
    ) as stt:
        with pytest.raises(errors.ServiceTimeout):
            await stt.transcribe_file(b"RIFF", filename="a.wav")


def test_gladia_live_config() -> None:
    stt = GladiaSttClient(api_key="k", transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    cfg = stt.live_config(vocabulary=["tore"], endpointing_s=0.4)
    assert cfg["endpointing"] == 0.4 and cfg["sample_rate"] == 16000
    assert cfg["messages_config"]["receive_partial_transcripts"] is True
    assert cfg["realtime_processing"]["custom_vocabulary_config"] == {"vocabulary": ["tore"]}
    assert "realtime_processing" not in stt.live_config(vocabulary=())


async def test_gladia_live_session_against_local_ws() -> None:
    received: list[Any] = []

    async def server(ws: Any) -> None:
        async for msg in ws:
            received.append(msg)
            if isinstance(msg, bytes):
                await ws.send(json.dumps({"type": "speech_start", "data": {"time": 0}}))
                await ws.send(
                    json.dumps(
                        {
                            "type": "transcript",
                            "data": {"id": "u1", "is_final": False, "utterance": {"text": "Ajou"}},
                        }
                    )
                )
            elif json.loads(msg)["type"] == "stop_recording":
                await ws.send(
                    json.dumps(
                        {
                            "type": "transcript",
                            "data": {
                                "id": "u1",
                                "is_final": True,
                                "utterance": {"text": "Ajoute", "words": WORDS},
                            },
                        }
                    )
                )
                await ws.send(json.dumps({"type": "end_session", "data": {}}))
                await ws.close()

    async with websockets.serve(server, "127.0.0.1", 0) as srv:
        port = srv.sockets[0].getsockname()[1]
        ws = await websockets.connect(f"ws://127.0.0.1:{port}")
        rec = LatencyRecorder()
        session = GladiaLiveSession(ws, "sess", rec)
        await session.send_audio(b"\x00\x00" * 160)
        await session.send_audio(b"")
        kinds = []
        async for ev in session.events():
            kinds.append(ev.kind)
            if ev.kind == "partial":
                await session.stop()
        await session.aclose()
    assert kinds == ["speech_start", "partial", "final", "ended"]
    assert len(received) == 2
    assert rec.records[0].operation == "live_final_after_last_chunk"
