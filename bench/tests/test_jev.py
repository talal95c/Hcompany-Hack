import httpx
import pytest

from bench.jev import (
    Client,
    accuracy,
    dataset,
    parse_results,
    request_body,
    shuffled_rows,
    summarize,
)


def test_parse_alignment() -> None:
    data = {
        "answers": {
            "b": {"type": "choice", "choice": "stop"},
            "a": {"type": "choice", "choice": "why"},
            "extra": {"type": "choice", "choice": "help"},
        }
    }
    predictions, extras = parse_results(data, ["a", "b", "missing"])
    assert predictions == {"a": "why", "b": "stop", "missing": None}
    assert extras == ["extra"]


@pytest.mark.parametrize(
    "data",
    [
        None,
        {},
        [],
        {"answers": []},
        {"answers": {"a": {"choice": "unknown", "type": "choice"}}},
        {"answers": {"a": "why"}},
        {"answers": {"a": {"type": "score", "choice": "why"}}},
    ],
)
def test_parse_invalid(data: object) -> None:
    assert parse_results(data, ["a"])[0] == {"a": None}


def test_dataset_body_accuracy() -> None:
    rows = dataset()
    assert len(rows) == 32
    body = request_body(rows[:2])
    assert all("label" not in r for r in body["state"])
    assert set(body["questions"]) == {r["id"] for r in rows[:2]}
    assert body == request_body(rows[:2])
    assert shuffled_rows(rows) == shuffled_rows(rows)
    assert shuffled_rows(rows) != rows
    assert len({r["label"] for r in shuffled_rows(rows)[:8]}) > 1
    score = accuracy(rows[:2], {rows[0]["id"]: rows[0]["label"]})
    assert score["accuracy"] == 0.5
    assert score["parse_failures"] == 1
    assert len(score["confusions"]) == 1
    assert accuracy([], {})["accuracy"] is None
    assert summarize([], [])["summary"]["logical_calls"] == 0


async def test_client_retry_and_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODIV_API_KEY", "unit-placeholder")
    client = Client()
    await client.http.aclose()
    replies = iter(
        [
            httpx.Response(429, headers={"retry-after": "2"}),
            httpx.Response(200, json={"answers": {"why1": {"type": "choice", "choice": "why"}}}),
            httpx.Response(200, text="not JSON"),
            httpx.Response(429, json={"error": {"type": "quota_exceeded_error"}}),
        ]
    )

    async def acquire() -> dict[str, float]:
        return {"pacing_wait_ms": 0, "cooldown_wait_ms": 0}

    monkeypatch.setattr(client.pacer, "acquire", acquire)
    client.http = httpx.AsyncClient(
        base_url="https://unit.invalid/", transport=httpx.MockTransport(lambda _: next(replies))
    )
    try:
        result = await client.call(dataset()[:1])
        assert result["status"] == 200
        assert len(result["attempts"]) == 2
        assert result["latency_ms"] == result["attempts"][-1]["latency_ms"]
        assert result["predictions"] == {"why1": "why"}
        result.update(mode="single")
        report = summarize(dataset()[:1], [result, result])
        assert report["groups"]["single"]["accuracy"] == 1
        assert report["groups"]["single"]["sentences"] == 2
        assert (await client.call(dataset()[:1]))["predictions"] == {"why1": None}
        quota = await client.call(dataset()[:1])
        assert len(quota["attempts"]) == 1
        assert quota["latency_ms"] is None
    finally:
        await client.http.aclose()


@pytest.mark.live
async def test_jev_live() -> None:
    client = Client()
    try:
        result = await client.call(dataset()[:1])
    finally:
        await client.http.aclose()
    print("Jev live:", result["status"], result["usage"], result["predictions"])
    assert result["status"] == 200
    assert result["predictions"]["why1"] is not None
