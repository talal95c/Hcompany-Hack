import json

import httpx
import pytest

from engine.config import EngineConfig
from engine.lesson.runtime import EngineRuntime
from engine.services.adapters import JevAdapter, SearchAdapter
from engine.services.errors import AuthenticationError
from engine.services.jev import CodivJevClient
from engine.services.linkup import BLENDER_ANSWER_SCHEMA, LinkupSearchClient
from tests.engine.test_generic import calc_lesson


@pytest.mark.parametrize("generic", [False, True])
@pytest.mark.parametrize("status", [200, 401])
async def test_runtime_search_real_request(tmp_path, generic, status):
    seen = []

    def transport(request):
        seen.append(json.loads(request.content))
        return httpx.Response(status, json={"data": {"answer": "Aide"}, "sources": []})

    client = LinkupSearchClient(api_key="test", transport=httpx.MockTransport(transport))
    runtime = EngineRuntime(EngineConfig(learner_path=tmp_path / "l.json"),
                            lesson=calc_lesson() if generic else None,
                            search=SearchAdapter(client))
    try:
        if status == 401:
            with pytest.raises(AuthenticationError):
                await runtime.docs_search("formule somme")
        else:
            assert await runtime.docs_search("formule somme") == []
        body = seen[0]
        assert body["includeDomains"] == list(runtime.profile.docs_domains)
        if generic:
            assert body["q"] == "formule somme"
            assert "blender" not in json.dumps(body).lower()
            assert "app_version" in json.loads(body["structuredOutputSchema"])["properties"]
        else:
            assert type(runtime.search) is SearchAdapter
            assert json.loads(body["structuredOutputSchema"]) == BLENDER_ANSWER_SCHEMA
            assert body["q"] == "formule somme site:docs.blender.org"
    finally:
        await client.aclose()
        await runtime.close()


@pytest.mark.parametrize("generic", [False, True])
@pytest.mark.parametrize("utterance", [None, "Pourquoi ?"])
async def test_runtime_jev_real_request(tmp_path, generic, utterance):
    seen = []

    def transport(request):
        body = json.loads(request.content)
        seen.append(body)
        key = "intent" if utterance else "action"
        choice = "question" if utterance else "wait"
        return httpx.Response(200, json={"answers": {
            key: {"choice": choice, "probabilities": {choice: 1.0}}}})

    client = CodivJevClient(api_key="test", transport=httpx.MockTransport(transport))
    adapter = JevAdapter(client)
    runtime = EngineRuntime(EngineConfig(learner_path=tmp_path / "l.json"),
                            lesson=calc_lesson() if generic else None, jev=adapter)
    context = {"instruction": "Saisir une valeur", "app": runtime.profile.service_context()}
    if utterance:
        context["utterance"] = utterance
    try:
        result = await runtime.policy.jev.decide(context, timeout_s=1)
        assert result.action == ("question" if utterance else "wait")
        body = seen[0]
        if generic:
            assert body["state"] == context
            assert "blender" not in json.dumps(body).lower()
        else:
            assert runtime.policy.jev is adapter
            if utterance:
                assert body["state"] == {"utterance": utterance,
                                         "lesson_context": context["instruction"]}
            assert "Blender" in json.dumps(body["questions"])
    finally:
        await client.aclose()
        await runtime.close()


async def test_unknown_profile_has_no_implicit_domain_filter(tmp_path):
    seen = []

    def transport(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"sources": []})

    lesson = calc_lesson()
    lesson["app"] = {**lesson["app"], "id": "text-editor", "name": "Text Editor"}
    client = LinkupSearchClient(api_key="test", transport=httpx.MockTransport(transport))
    runtime = EngineRuntime(EngineConfig(learner_path=tmp_path / "l.json"), lesson=lesson,
                            search=SearchAdapter(client))
    try:
        with pytest.raises(ValueError, match="vide"):
            await runtime.docs_search("")
        assert seen == []
        assert await runtime.docs_search("save") == []
        assert "includeDomains" not in seen[0]
        assert "blender" not in json.dumps(seen[0]).lower()
    finally:
        await client.aclose()
        await runtime.close()
