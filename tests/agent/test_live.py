import os
import time

import httpx
import pytest
from conftest import FIXTURES

from agent.catalog import Catalog
from agent.skill_export import AGENTS_URL, artifact, publish


@pytest.mark.live
@pytest.mark.skipif(not os.getenv("HAI_API_KEY"), reason="HAI_API_KEY required for live calls")
async def test_authenticated_skill_publish(tmp_path):
    key = os.environ["HAI_API_KEY"]
    async with httpx.AsyncClient(headers={"Authorization": "Bearer " + key}, timeout=30) as client:
        for url in ["https://api.hcompany.ai/v1/models", AGENTS_URL + "/skills"]:
            start = time.perf_counter()
            response = await client.get(url)
            print(
                f"H API GET {url} HTTP {response.status_code} "
                f"latency_ms={(time.perf_counter() - start) * 1000:.3f}"
            )
            assert response.status_code == 200
    record = Catalog(FIXTURES, tmp_path).get("proven", 1, "5.2.3")
    skill = artifact(record)
    # A private integration fixture, never presented as a real Blender proof.
    skill["description"] = "Integration fixture only — not a validated Blender lesson"
    start = time.perf_counter()
    result = await publish(skill, key)
    print(f"H API publish latency_ms={(time.perf_counter() - start) * 1000:.3f}")
    assert result["name"] == skill["name"]
    assert result["body"] == skill["body"]
    assert await publish(skill, key) == result
