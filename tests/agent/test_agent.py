import asyncio
import copy
import hashlib
import json
import shutil
from pathlib import Path

import httpx
import pytest
from conftest import FIXTURES, call, connect
from jsonschema import Draft202012Validator

from agent.catalog import AgentError, Catalog
from agent.server import create_server
from agent.skill_export import artifact, export, publish

ARGS = {"lesson_id": "proven", "revision": 1, "blender_version": "5.2.3"}
RUN = {**ARGS, "session_id": "session", "consent_token": "consent"}


def decoded(result):
    if result.structuredContent is not None:
        content = result.structuredContent
        return content["result"] if set(content) == {"result"} else content
    return json.loads(result.content[0].text)


async def test_every_tool_over_mcp(transport, tmp_path):
    state = tmp_path / "state"
    async with connect(transport, FIXTURES, state) as session:
        assert {t.name for t in (await session.list_tools()).tools} == {
            "list_apps",
            "find_procedure",
            "get_procedure",
            "run_procedure",
            "report_broken",
        }
        apps = decoded(await call(session, "list_apps"))
        assert apps["apps"][0]["lesson_count"] == 2
        assert apps["rejected_count"] == 3
        found = decoded(
            await call(
                session,
                "find_procedure",
                {"query": "donut", "blender_version": "5.2.3", "skill_id": "add_primitive"},
            )
        )
        assert len(found) == 1
        assert found[0]["lesson_id"] == "proven"
        record = decoded(await call(session, "get_procedure", ARGS))
        schema = json.loads(
            (Path(__file__).parents[2] / "contracts/lesson.schema.json").read_text()
        )
        Draft202012Validator(schema).validate(record["lesson"])
        assert record["fingerprint"] == found[0]["fingerprint"]
        assert record["proof_manifest"]
        for arguments in [
            {**ARGS, "lesson_id": "draft"},
            {**ARGS, "blender_version": "0.0.0"},
            {**ARGS, "lesson_id": "missing-evidence"},
        ]:
            assert (await call(session, "get_procedure", arguments)).isError
        assert "consent_required" in str(
            await call(session, "run_procedure", {**RUN, "consent_token": ""})
        )
        assert "engine_protocol_unavailable" in str(await call(session, "run_procedure", RUN))
        ticket = decoded(
            await call(
                session,
                "report_broken",
                {
                    "lesson_id": "proven",
                    "revision": 1,
                    "step_id": "add_torus",
                    "description": "Chemin incorrect",
                    "evidence_ref": "user/evidence.png",
                },
            )
        )
        assert not (await call(session, "get_procedure", ARGS)).isError
        Catalog(FIXTURES, state).triage(ticket["ticket_id"], True)
        assert (await call(session, "get_procedure", ARGS)).isError
        assert (
            decoded(
                await call(session, "find_procedure", {"query": "", "blender_version": "5.2.3"})
            )
            == []
        )


async def test_empty_mcp(transport, tmp_path):
    async with connect(transport, tmp_path / "empty", tmp_path / "state") as session:
        assert decoded(await call(session, "list_apps"))["apps"] == []
        assert (
            decoded(
                await call(session, "find_procedure", {"query": "", "blender_version": "5.2.3"})
            )
            == []
        )
        assert (await call(session, "get_procedure", ARGS)).isError
        assert (await call(session, "run_procedure", RUN)).isError
        assert (
            await call(
                session,
                "report_broken",
                {
                    "lesson_id": "",
                    "revision": 1,
                    "step_id": "",
                    "description": "",
                    "evidence_ref": "",
                },
            )
        ).isError


class BlockingRunner:
    def __init__(self):
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0

    async def run(self, procedure, session_id, consent_token):
        self.calls += 1
        self.entered.set()
        await self.release.wait()
        return {"run_id": "unit-run", "checks_passed": True, "progress": ["checks_passed"]}


async def test_runner_guards_and_lock(tmp_path):
    runner = BlockingRunner()
    server = create_server(Catalog(FIXTURES, tmp_path), runner)
    for arguments in [
        {**RUN, "consent_token": ""},
        {**RUN, "lesson_id": "draft"},
        {**RUN, "blender_version": "0.0.0"},
    ]:
        with pytest.raises(Exception):
            await server.call_tool("run_procedure", arguments)
    assert runner.calls == 0
    first = asyncio.create_task(server.call_tool("run_procedure", RUN))
    await asyncio.wait_for(runner.entered.wait(), 2)
    with pytest.raises(Exception, match="busy"):
        await server.call_tool("run_procedure", RUN)
    runner.release.set()
    assert "unit-run" in str(await first)
    assert runner.calls == 1


async def test_runner_failure_and_cancellation_unlock(tmp_path):
    runner = BlockingRunner()
    server = create_server(Catalog(FIXTURES, tmp_path), runner)
    task = asyncio.create_task(server.call_tool("run_procedure", RUN))
    await runner.entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    runner.release.set()
    assert "unit-run" in str(await server.call_tool("run_procedure", RUN))

    class FailedRunner:
        async def run(self, procedure, session_id, consent_token):
            return {"run_id": "bad", "checks_passed": False}

    with pytest.raises(Exception, match="checks_not_passed"):
        await create_server(Catalog(FIXTURES, tmp_path), FailedRunner()).call_tool(
            "run_procedure", RUN
        )


def test_export_and_rejections(tmp_path):
    catalog = Catalog(FIXTURES, tmp_path / "state")
    path, changed = export(catalog, **ARGS, output=tmp_path / "export")
    assert changed
    assert export(catalog, **ARGS, output=tmp_path / "export") == (path, False)
    skill = json.loads(path.read_text())
    assert '"ui_path_verified": false' in skill["body"]
    assert '"target"' in skill["body"] and '"check"' in skill["body"]
    assert '"fingerprint"' in skill["body"] and '"preconditions"' in skill["body"]
    for lesson_id in ["draft", "missing-evidence", "broken-schema", "absent"]:
        with pytest.raises(AgentError):
            export(catalog, lesson_id, 1, "5.2.3", tmp_path / "export")
    assert {r["reason"] for r in catalog.scan()[1]} == {"not_proven", "invalid_schema_or_evidence"}


def test_symlink_and_duplicate_rejected(tmp_path):
    shutil.copytree(FIXTURES / "proven", tmp_path / "one")
    shutil.copytree(FIXTURES / "proven", tmp_path / "two")
    catalog = Catalog(tmp_path, tmp_path / "state")
    assert catalog.scan()[0] == []
    shutil.rmtree(tmp_path / "two")
    evidence = tmp_path / "one/proof/manifest.json"
    evidence.unlink()
    evidence.symlink_to(FIXTURES / "proven/proof/manifest.json")
    assert catalog.scan()[0] == []


def test_pending_step_and_immutable_export(tmp_path):
    shutil.copytree(FIXTURES / "proven", tmp_path / "lessons/one")
    catalog = Catalog(tmp_path / "lessons", tmp_path / "state")
    export(catalog, **ARGS, output=tmp_path / "export")
    path = tmp_path / "lessons/one/lesson.json"
    lesson = json.loads(path.read_text())
    lesson["title"] = "Changed immutable revision"
    path.write_text(json.dumps(lesson))
    with pytest.raises(AgentError, match="immutable_revision_conflict"):
        export(catalog, **ARGS, output=tmp_path / "export")
    lesson["steps"][0]["proof"]["status"] = "pending"
    path.write_text(json.dumps(lesson))
    assert catalog.scan()[0] == []
    assert catalog.scan()[1][0]["reason"] == "not_proven"


def test_version_exports_and_empty_catalog(tmp_path):
    catalog = Catalog(FIXTURES, tmp_path / "state")
    one, _ = export(catalog, **ARGS, output=tmp_path / "export")
    two, _ = export(catalog, "proven", 1, "4.5.9", tmp_path / "export")
    assert one != two
    with pytest.raises(AgentError):
        export(
            Catalog(tmp_path / "empty", tmp_path / "state"),
            **ARGS,
            output=tmp_path / "empty-export",
        )


async def test_publish_errors_leave_catalog_unchanged(tmp_path):
    catalog = Catalog(FIXTURES, tmp_path)
    before = catalog.scan()
    skill = artifact(catalog.get(**ARGS))
    for status in [401, 403, 500]:
        with pytest.raises(AgentError, match="publisher_not_available"):
            await publish(
                skill,
                "unit-key",
                transport=httpx.MockTransport(lambda request: httpx.Response(status)),
            )
    with pytest.raises(AgentError, match="missing"):
        await publish(skill, "")
    assert before == catalog.scan()


async def test_publish_idempotent_and_create(tmp_path):
    skill = artifact(Catalog(FIXTURES, tmp_path).get(**ARGS))
    requests = []

    def handler(request):
        requests.append(request.method)
        return httpx.Response(404 if request.method == "GET" else 201, json=skill)

    assert await publish(skill, "unit-key", transport=httpx.MockTransport(handler)) == skill
    assert requests == ["GET", "POST"]
    assert (
        await publish(
            skill,
            "unit-key",
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json=skill)),
        )
        == skill
    )


def skill_revision(tmp_path, revision):
    record = copy.deepcopy(Catalog(FIXTURES, tmp_path).get(**ARGS))
    record["lesson"]["revision"] = revision
    record["fingerprint"] = hashlib.sha256(json.dumps(record["lesson"]).encode()).hexdigest()
    return artifact(record)


async def test_publish_older_revision_patched(tmp_path):
    older = skill_revision(tmp_path, 1)
    newer = skill_revision(tmp_path, 2)
    assert older["name"] == newer["name"]
    requests = []

    def handler(request):
        requests.append(request.method)
        if request.method == "GET":
            return httpx.Response(200, json=older, headers={"ETag": '"1"'})
        assert request.method == "PATCH"
        assert request.headers["If-Match"] == '"1"'
        assert json.loads(request.content) == {k: v for k, v in newer.items() if k != "name"}
        return httpx.Response(200, json=newer, headers={"ETag": '"2"'})

    assert await publish(newer, "unit-key", transport=httpx.MockTransport(handler)) == newer
    assert requests == ["GET", "PATCH"]


@pytest.mark.parametrize(
    "case",
    ["newer", "same_revision", "wrong_lesson", "wrong_version", "invalid_metadata", "missing_etag"],
)
async def test_publish_conflicting_revision_refused(tmp_path, case):
    incoming = skill_revision(tmp_path, 2)
    remote = skill_revision(tmp_path, 3 if case == "newer" else 2 if case == "same_revision" else 1)
    if case == "same_revision":
        remote["description"] = "conflicting content"
    if case == "wrong_lesson":
        remote["body"] = remote["body"].replace('"lesson_id": "proven"', '"lesson_id": "other"')
    if case == "wrong_version":
        remote["body"] = remote["body"].replace('"5.2.3"', '"4.5.9"')
    if case == "invalid_metadata":
        remote["body"] = "not an exported lesson"
    if case == "missing_etag":
        remote = skill_revision(tmp_path, 1)
    requests = []

    def handler(request):
        requests.append(request.method)
        return httpx.Response(200, json=remote)

    with pytest.raises(AgentError, match="revision"):
        await publish(incoming, "unit-key", transport=httpx.MockTransport(handler))
    assert requests == ["GET"]


@pytest.mark.parametrize("status", [409, 412, 503])
async def test_publish_failed_patch_preserves_catalog(tmp_path, status):
    catalog = Catalog(FIXTURES, tmp_path)
    before = catalog.scan()
    older, newer = skill_revision(tmp_path, 1), skill_revision(tmp_path, 2)

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json=older, headers={"ETag": '"1"'})
        return httpx.Response(status)

    with pytest.raises(AgentError, match=f"publish_failed: HTTP {status}"):
        await publish(newer, "unit-key", transport=httpx.MockTransport(handler))
    assert catalog.scan() == before


def test_local_exports_keep_revision_files_immutable(tmp_path):
    root = tmp_path / "lessons"
    shutil.copytree(FIXTURES / "proven", root / "one")
    catalog = Catalog(root, tmp_path / "state")
    first, _ = export(catalog, **ARGS, output=tmp_path / "export")
    original = first.read_bytes()
    lesson_path = root / "one/lesson.json"
    lesson = json.loads(lesson_path.read_text())
    lesson["revision"] = 2
    lesson_path.write_text(json.dumps(lesson))
    second, _ = export(catalog, "proven", 2, "5.2.3", tmp_path / "export")
    assert first != second
    assert first.read_bytes() == original
    assert json.loads(first.read_text())["name"] == json.loads(second.read_text())["name"]
