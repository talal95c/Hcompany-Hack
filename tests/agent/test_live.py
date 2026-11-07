import copy
import hashlib
import json
import logging
import os
from uuid import uuid4

import pytest

from .conftest import AGENT_EXTRA_INSTALLED, AGENT_EXTRA_REASON, FIXTURES

if AGENT_EXTRA_INSTALLED:
    import httpx

    from agent.catalog import VALIDATOR, Catalog
    from agent.skill_export import AGENTS_URL, artifact, measured_request, publish
else:
    pytest.skip(AGENT_EXTRA_REASON, allow_module_level=True)


@pytest.mark.live
@pytest.mark.skipif(not os.getenv("HAI_API_KEY"), reason="HAI_API_KEY required for live calls")
@pytest.mark.parametrize(
    "lesson_id,version,prefix,compatibility",
    [
        ("proven", "5.2.3", "blender-lesson-", "Blender 5.2.3"),
        ("calc-value", "24.2", "libreoffice-calc-lesson-", "LibreOffice Calc 24.2"),
    ],
)
async def test_authenticated_skill_publish(
    tmp_path, caplog, lesson_id, version, prefix, compatibility
):
    key = os.environ["HAI_API_KEY"]
    caplog.set_level(logging.INFO, logger="agent.skill_export")
    record = copy.deepcopy(Catalog(FIXTURES, tmp_path).get(lesson_id, 1, version))
    record["lesson"]["lesson_id"] = "integration-" + uuid4().hex

    def revision(number):
        record["lesson"]["revision"] = number
        VALIDATOR.validate(record["lesson"])
        record["fingerprint"] = hashlib.sha256(json.dumps(record["lesson"]).encode()).hexdigest()
        skill = artifact(record)
        skill["description"] = "Fixture d'intégration uniquement — pas une leçon réellement prouvée"
        return skill

    first = revision(1)
    second = revision(2)
    assert first["name"] == second["name"]
    assert first["name"].startswith(prefix)
    assert first["compatibility"] == compatibility
    endpoint = AGENTS_URL + "/skills/" + first["name"]
    async with httpx.AsyncClient(headers={"Authorization": "Bearer " + key}, timeout=30) as client:
        try:
            response = await measured_request(client, "GET", "https://api.hcompany.ai/v1/models")
            assert response.status_code == 200
            created = await publish(first, key)
            assert created["body"] == first["body"]
            assert created["name"].startswith(prefix)
            assert created["compatibility"] == compatibility
            updated = await publish(second, key)
            assert updated["body"] == second["body"]
            current = await measured_request(client, "GET", endpoint)
            assert current.status_code == 200
            assert current.json()["body"] == second["body"]
            revisions = await measured_request(client, "GET", endpoint + "/revisions")
            assert revisions.status_code == 200
            assert {item["number"] for item in revisions.json()["items"]} == {1, 2}
            assert revisions.json()["total"] == 2
            assert await publish(second, key) == updated
            after = await measured_request(client, "GET", endpoint + "/revisions")
            assert after.status_code == 200
            assert after.json()["total"] == 2
        finally:
            deleted = await measured_request(client, "DELETE", endpoint)
            for entry in caplog.records:
                if entry.name == "agent.skill_export":
                    print(entry.getMessage())
            assert deleted.status_code in {204, 404}
        absent = await measured_request(client, "GET", endpoint)
        assert absent.status_code == 404
