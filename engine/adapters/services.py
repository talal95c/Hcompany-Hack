"""Adaptation des services cloud au profil d'une application de bureau."""

import time

from engine.adapters.profiles import AppProfile
from engine.interfaces import JevDecision, SearchHit
from engine.services.adapters import JevAdapter, SearchAdapter
from engine.services.protocols import JevQuestion


class ProfileSearchAdapter(SearchAdapter):
    def __init__(self, client, profile: AppProfile):
        super().__init__(client)
        self.profile = profile

    async def search(self, query: str, *, depth: str = "standard",
                     domains: tuple[str, ...] | None = None) -> list[SearchHit]:
        schema = {
            "type": "object",
            "properties": {
                "answer": {"type": "string", "description": f"Aide pour {self.profile.name}"},
                "menu_path": {"type": "string"},
                "shortcut": {"type": "string"},
                "app_version": {"type": "string"},
            },
            "required": ["answer"],
        }
        result = await self.client.search(
            query, depth=depth, schema=schema,
            domains=self.profile.docs_domains if domains is None else domains)
        return [SearchHit(s.name, s.url, s.snippet) for s in result.sources]


class ProfileJevAdapter(JevAdapter):
    def __init__(self, client, profile: AppProfile):
        super().__init__(client)
        self.profile = profile

    async def decide(self, context: dict, *, timeout_s: float) -> JevDecision:
        return await self._decide(context, timeout_s=timeout_s)

    async def speculate_intent(self, context: dict, *, timeout_s: float) -> JevDecision:
        return await self._decide(context, timeout_s=timeout_s, speculative=True)

    async def _decide(self, context: dict, *, timeout_s: float,
                      speculative: bool = False) -> JevDecision:
        from engine.services.jev import INTENT_QUESTION

        start = time.perf_counter()
        state = {**context, "app": self.profile.service_context()}
        if "utterance" in context:
            key = "intent"
            question = JevQuestion(
                "choice", "Classify what the learner's French utterance asks of the tutor. "
                f"The learner is following a tutorial in {self.profile.name}.",
                INTENT_QUESTION.criteria)
        else:
            key = "action"
            criteria = {"intervene": "The learner needs help now",
                        "wait": "Recent progress; let the learner think"}
            criteria.update({"error_code:" + code: code
                             for code in context.get("known_errors", [])})
            question = JevQuestion(
                "choice", f"Choose whether to help the {self.profile.name} learner", criteria)
        result = (await self.client.decide(state, {key: question}, timeout_s=timeout_s,
                  **({"speculative": True} if speculative else {})))[key]
        return JevDecision(result.choice, None, (time.perf_counter() - start) * 1000)
