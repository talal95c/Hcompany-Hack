"""Export déterministe et publication explicite dans l'Agents API."""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from agent.catalog import AgentError, Catalog

LOG = logging.getLogger(__name__)
AGENTS_URL = "https://agp.eu.hcompany.ai/api/v2"


def artifact(record: dict[str, Any]) -> dict[str, str]:
    lesson = record["lesson"]
    identity = json.dumps([lesson["lesson_id"], lesson["blender_version"]])
    name = "blender-lesson-" + hashlib.sha256(identity.encode()).hexdigest()[:32]
    context = {
        "objective": lesson["title"],
        "lesson_id": lesson["lesson_id"],
        "revision": lesson["revision"],
        "fingerprint": record["fingerprint"],
        "execution_context": {
            "blender_version": lesson["blender_version"],
            "language": lesson["language"],
            "consent_required": True,
            "checks_required": True,
        },
        "proof_limits": lesson["proof"],
        "steps": [
            {
                k: step[k]
                for k in (
                    "id",
                    "instruction",
                    "preconditions",
                    "check",
                    "target",
                    "proof",
                    "procedure_ref",
                )
            }
            for step in lesson["steps"]
        ],
    }
    return {
        "name": name,
        "description": lesson["title"],
        "body": "# "
        + lesson["title"]
        + "\n\n```json\n"
        + json.dumps(context, ensure_ascii=False, indent=2)
        + "\n```\n",
        "compatibility": "Blender " + lesson["blender_version"],
    }


def export(
    catalog: Catalog, lesson_id: str, revision: int, blender_version: str, output: Path
) -> tuple[Path, bool]:
    record = catalog.get(lesson_id, revision, blender_version)
    skill = artifact(record)
    output.mkdir(parents=True, exist_ok=True)
    path = output / (skill["name"] + f"-r{revision}.json")
    serialized = json.dumps(skill, ensure_ascii=False, indent=2) + "\n"
    if path.exists():
        if path.read_text() == serialized:
            return path, False
        raise AgentError("immutable_revision_conflict")
    with path.open("x") as stream:
        stream.write(serialized)
    return path, True


def revision_context(skill: dict[str, Any]) -> dict[str, Any]:
    try:
        body = skill["body"]
        context = json.loads(body.split("\n\n```json\n", 1)[1].removesuffix("\n```\n"))
        if (
            not isinstance(context["lesson_id"], str)
            or not context["lesson_id"]
            or type(context["revision"]) is not int
            or context["revision"] < 1
            or not isinstance(context["fingerprint"], str)
            or len(context["fingerprint"]) != 64
            or any(c not in "0123456789abcdef" for c in context["fingerprint"])
            or not isinstance(context["execution_context"]["blender_version"], str)
        ):
            raise ValueError
        return context
    except (KeyError, IndexError, TypeError, ValueError, AttributeError) as error:
        raise AgentError("invalid_skill_revision_metadata") from error


async def measured_request(
    client: httpx.AsyncClient, method: str, endpoint: str, **kwargs: Any
) -> httpx.Response:
    start = time.perf_counter()
    try:
        response = await client.request(method, endpoint, **kwargs)
        LOG.info(
            "h_api method=%s status=%s latency_ms=%.3f",
            method,
            response.status_code,
            (time.perf_counter() - start) * 1000,
        )
        return response
    except httpx.HTTPError:
        LOG.info(
            "h_api method=%s network_error latency_ms=%.3f",
            method,
            (time.perf_counter() - start) * 1000,
        )
        raise


async def publish(
    skill: dict[str, str],
    key: str,
    base_url: str = AGENTS_URL,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    if not key:
        raise AgentError("publisher_not_available: HAI_API_KEY missing")
    incoming = revision_context(skill)
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(
            base_url=base_url + "/",
            headers={"Authorization": "Bearer " + key},
            timeout=30,
            transport=transport,
        ) as client:
            endpoint = "skills/" + quote(skill["name"], safe="/")
            current = await measured_request(client, "GET", endpoint)
            if current.status_code == 404:
                response = await measured_request(client, "POST", "skills", json=skill)
            elif current.is_success:
                remote = current.json()
                previous = revision_context(remote)
                if all(remote.get(k) == v for k, v in skill.items()):
                    return remote
                if (
                    remote.get("name") != skill["name"]
                    or previous["lesson_id"] != incoming["lesson_id"]
                    or previous["execution_context"]["blender_version"]
                    != incoming["execution_context"]["blender_version"]
                    or previous["revision"] >= incoming["revision"]
                ):
                    raise AgentError("remote_revision_conflict")
                etag = current.headers.get("etag")
                if not etag or etag == "*":
                    raise AgentError("remote_revision_conflict: missing revision ETag")
                response = await measured_request(
                    client,
                    "PATCH",
                    endpoint,
                    headers={"If-Match": etag},
                    json={k: v for k, v in skill.items() if k != "name"},
                )
            else:
                raise AgentError(f"publisher_not_available: HTTP {current.status_code}")
            if not response.is_success:
                raise AgentError(f"publish_failed: HTTP {response.status_code}")
            return response.json()
    except httpx.HTTPError as error:
        raise AgentError("publisher_not_available: network error") from error
    finally:
        LOG.info("h_api publish latency_ms=%.3f", (time.perf_counter() - start) * 1000)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("lesson_id")
    parser.add_argument("revision", type=int)
    parser.add_argument("blender_version")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    path, changed = export(
        Catalog(), args.lesson_id, args.revision, args.blender_version, args.output
    )
    if args.publish:
        asyncio.run(publish(json.loads(path.read_text()), os.getenv("HAI_API_KEY", "")))
    print(json.dumps({"file": str(path), "changed": changed}))


if __name__ == "__main__":
    main()
