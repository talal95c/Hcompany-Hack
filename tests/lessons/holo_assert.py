"""Assertion fermée via le transport Holo existant, sans action cloud."""

import asyncio
import base64
import json
import sys
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

from engine.services.errors import QuotaExceeded, ServiceError, ServiceTimeout
from engine.services.holo import HoloCloudClient


async def assert_image(request):
    start = time.perf_counter()
    encoded = base64.b64encode(Path(request["image"]).read_bytes()).decode("ascii")
    async with HoloCloudClient(model="holo4-27b") as client:
        response = await client._complete(
            "visual_assert",
            12,
            messages=[
                {
                    "role": "system",
                    "content": "Read only the supplied screenshot. Answer the "
                    "closed question as JSON with exactly answer (boolean) and confidence "
                    "(number 0 to 1). Check the exact named cell and literal visible formatting; "
                    "do not infer currency from a neighboring row or from the question. "
                    "If illegible use confidence 0. Do not infer hidden content.",
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{encoded}"},
                        },
                        {"type": "text", "text": request["assertion"]},
                    ],
                },
            ],
            max_tokens=180,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "visual_assertion",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "answer": {"type": "boolean"},
                            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        },
                        "required": ["answer", "confidence"],
                    },
                },
            },
        )
    content = (response.choices[0].message.content or "").strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1].rsplit("```", 1)[0]
    evidence = {
        "model": "holo4-27b",
        "request_id": response.id,
        "seconds": time.perf_counter() - start,
        "response": content,
    }
    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        result = None
    if not isinstance(result, dict):
        return {**evidence, "answer": None, "confidence": 0, "error": "invalid_response"}
    return {**evidence, "answer": result.get("answer"), "confidence": result.get("confidence")}


async def evaluate_image(request):
    start = time.perf_counter()
    attempts = []
    for index in range(5):
        clock = time.perf_counter()
        retry_after = None
        try:
            result = await asyncio.wait_for(assert_image(request), timeout=12)
            attempts.append(
                {
                    "seconds": time.perf_counter() - clock,
                    "error": result.get("error"),
                    "request_id": result.get("request_id"),
                }
            )
            return {**result, "attempts": attempts, "seconds": time.perf_counter() - start}
        except (TimeoutError, ServiceError) as exc:
            timeout = isinstance(exc, (ServiceTimeout, asyncio.TimeoutError))
            cause = exc.__cause__
            response = getattr(cause, "response", None)
            if response is not None:
                retry_after = response.headers.get("retry-after")
            result = {
                "answer": None,
                "confidence": 0,
                "error": "timeout" if timeout else exc.kind,
                "http_status": getattr(cause, "status_code", None),
                "model": "holo4-27b",
            }
            attempts.append(
                {**result, "seconds": time.perf_counter() - clock, "retry_after": retry_after}
            )
            retryable = timeout or isinstance(exc, QuotaExceeded) or result["http_status"] == 429
            delay = retry_delay(retry_after)
            if not retryable or index == 4 or time.perf_counter() - start + delay + 12 > 120:
                break
            await asyncio.sleep(delay)
    return {**result, "attempts": attempts, "seconds": time.perf_counter() - start}


def retry_delay(header):
    if header is None:
        return 2.5
    try:
        seconds = float(header)
    except ValueError:
        try:
            seconds = (parsedate_to_datetime(header) - datetime.now(UTC)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            return 2.5
    return max(2.5, seconds)


if __name__ == "__main__":
    print(json.dumps(asyncio.run(evaluate_image(json.load(sys.stdin)))))
