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
    identity = json.dumps([lesson["lesson_id"], lesson["revision"], lesson["blender_version"]])
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
    path = output / (skill["name"] + ".json")
    serialized = json.dumps(skill, ensure_ascii=False, indent=2) + "\n"
    if path.exists():
        if path.read_text() == serialized:
            return path, False
        raise AgentError("immutable_revision_conflict")
    with path.open("x") as stream:
        stream.write(serialized)
    return path, True


async def publish(
    skill: dict[str, str],
    key: str,
    base_url: str = AGENTS_URL,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    if not key:
        raise AgentError("publisher_not_available: HAI_API_KEY missing")
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(
            base_url=base_url + "/",
            headers={"Authorization": "Bearer " + key},
            timeout=30,
            transport=transport,
        ) as client:
            endpoint = "skills/" + quote(skill["name"], safe="/")
            current = await client.get(endpoint)
            if current.status_code == 404:
                response = await client.post("skills", json=skill)
            elif current.is_success:
                if all(current.json().get(k) == v for k, v in skill.items()):
                    return current.json()
                raise AgentError("immutable_remote_revision_conflict")
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
