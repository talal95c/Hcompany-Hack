"""Serveur MCP, journalisation sur stderr uniquement."""

import argparse
import asyncio
import functools
import logging
import time
from collections.abc import Callable
from typing import Any

from mcp.server.fastmcp import FastMCP

from agent.catalog import AgentError, Catalog, lesson_app
from agent.runner import EngineRunner, Runner

LOG = logging.getLogger(__name__)


def app_filters(
    app_id: str | None, app_version: str | None, blender_version: str | None
) -> tuple[str | None, str | None]:
    if blender_version is not None:
        if app_id not in (None, "blender") or app_version not in (None, blender_version):
            raise AgentError("conflicting_app_filters")
        return "blender", blender_version
    return app_id, app_version


def measured(function: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(function)
    async def wrapped(*args: Any, **kwargs: Any) -> Any:
        start = time.perf_counter()
        try:
            return await function(*args, **kwargs)
        finally:
            LOG.info(
                "tool=%s latency_ms=%.3f", function.__name__, (time.perf_counter() - start) * 1000
            )

    return wrapped


def create_server(
    catalog: Catalog | None = None,
    runner: Runner | None = None,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> FastMCP:
    catalog = catalog or Catalog()
    runner = runner or EngineRunner()
    server = FastMCP("Leçons prouvées", host=host, port=port)
    lock = asyncio.Lock()

    @server.tool()
    @measured
    async def list_apps() -> dict[str, Any]:
        records, rejected = catalog.scan()
        apps: dict[str, Any] = {}
        for record in records:
            app = lesson_app(record["lesson"])
            entry = apps.setdefault(
                app["id"],
                {
                    "app": app["id"],
                    "name": app["name"],
                    "sensors": [],
                    "versions": {},
                    "lesson_count": 0,
                },
            )
            entry["lesson_count"] += 1
            if app["sensor"] not in entry["sensors"]:
                entry["sensors"].append(app["sensor"])
                entry["sensors"].sort()
            versions = entry["versions"]
            versions[app["version"]] = versions.get(app["version"], 0) + 1
        return {
            "apps": [apps[key] for key in sorted(apps)],
            "rejected_count": len(rejected),
            "rejected": rejected,
        }

    @server.tool()
    @measured
    async def find_procedure(
        query: str,
        app_id: str | None = None,
        app_version: str | None = None,
        skill_id: str | None = None,
        blender_version: str | None = None,
    ) -> list[dict[str, Any]]:
        app_id, app_version = app_filters(app_id, app_version, blender_version)
        found = []
        for record in catalog.scan()[0]:
            lesson = record["lesson"]
            app = lesson_app(lesson)
            if (app_id is not None and app["id"] != app_id) or (
                app_version is not None and app["version"] != app_version
            ):
                continue
            if skill_id is not None and skill_id not in lesson["skills"]:
                continue
            if (
                query.casefold()
                not in " ".join(
                    [lesson["title"], lesson["lesson_id"], *lesson["skills"]]
                ).casefold()
            ):
                continue
            found.append(
                {
                    **{
                        k: lesson[k]
                        for k in ("lesson_id", "revision", "title", "blender_version", "status")
                        if k in lesson
                    },
                    "app": app,
                    "summary": lesson["steps"][0]["instruction"],
                    "fingerprint": record["fingerprint"],
                }
            )
        return found

    @server.tool()
    @measured
    async def get_procedure(
        lesson_id: str,
        revision: int,
        app_version: str | None = None,
        app_id: str | None = None,
        blender_version: str | None = None,
    ) -> dict[str, Any]:
        app_id, app_version = app_filters(app_id, app_version, blender_version)
        if app_version is None:
            raise AgentError("app_version_required")
        return catalog.get(lesson_id, revision, app_version, app_id)

    @server.tool()
    @measured
    async def run_procedure(
        lesson_id: str,
        revision: int,
        app_version: str | None = None,
        session_id: str = "",
        consent_token: str = "",
        app_id: str | None = None,
        blender_version: str | None = None,
    ) -> dict[str, Any]:
        if not consent_token.strip() or not session_id.strip():
            raise AgentError("consent_required")
        if lock.locked():
            raise AgentError("busy")
        async with lock:
            procedure = await get_procedure(
                lesson_id, revision, app_version, app_id, blender_version
            )
            result = await runner.run(procedure, session_id, consent_token)
            if result.get("checks_passed") is not True or not result.get("run_id"):
                raise AgentError("checks_not_passed")
            return result

    @server.tool()
    @measured
    async def report_broken(
        lesson_id: str, revision: int, step_id: str, description: str, evidence_ref: str
    ) -> dict[str, str]:
        return catalog.report(lesson_id, revision, step_id, description, evidence_ref)

    return server


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    create_server(host=args.host, port=args.port).run(
        transport="stdio" if args.transport == "stdio" else "streamable-http"
    )


if __name__ == "__main__":
    main()
