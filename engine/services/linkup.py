"""Client Linkup : recherche documentaire structurée avec sources."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from typing import Any

import httpx

from engine.services._retry import with_retry
from engine.services.errors import (
    InvalidResponse,
    ServiceTimeout,
    ServiceUnavailable,
    error_for_status,
)
from engine.services.latency import LatencyRecorder
from engine.services.profiles import AppProfile, load_profile
from engine.services.protocols import SearchResult, SearchSource

SERVICE = "linkup"
DEFAULT_BASE_URL = "https://api.linkup.so/v1"


class LinkupSearchClient:
    """SearchClient réel : `outputType=structured` + `includeSources`."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        profile: AppProfile | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout_s: float = 30.0,
        recorder: LatencyRecorder | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        key = api_key or os.environ.get("LINKUP_API_KEY")
        if not key:
            raise ServiceUnavailable(SERVICE, "LINKUP_API_KEY absent")
        self.profile = profile or load_profile(None)
        self.recorder = recorder or LatencyRecorder()
        self._http = httpx.AsyncClient(
            base_url=base_url,
            transport=transport,
            headers={"Authorization": f"Bearer {key}"},
            timeout=httpx.Timeout(timeout_s, connect=10.0),
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> LinkupSearchClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def search(
        self,
        query: str,
        *,
        schema: Mapping[str, Any] | None = None,
        domains: Sequence[str] | None = None,
        profile: AppProfile | None = None,
        depth: str = "standard",
    ) -> SearchResult:
        if not query.strip():
            raise ValueError("requête vide")
        if depth not in ("standard", "deep"):
            raise ValueError("depth doit valoir standard ou deep")
        profile = profile or self.profile
        domains = profile.docs_domains if domains is None else domains
        body: dict[str, Any] = {
            "q": query.strip(),
            "depth": depth,
            "outputType": "structured",
            "structuredOutputSchema": json.dumps(
                dict(profile.answer_schema() if schema is None else schema)
            ),
            "includeSources": True,
        }
        if domains:
            body["includeDomains"] = list(domains)

        async def call() -> SearchResult:
            with self.recorder.measure(SERVICE, "search") as ctx:
                try:
                    resp = await self._http.post("/search", json=body)
                except httpx.TimeoutException as exc:
                    raise ServiceTimeout(SERVICE, "recherche trop longue") from exc
                except httpx.TransportError as exc:
                    raise ServiceUnavailable(SERVICE, f"transport: {exc}") from exc
                ctx.request_id = resp.headers.get("x-request-id")
                if resp.status_code != 200:
                    raise error_for_status(
                        SERVICE, resp.status_code, resp.text, request_id=ctx.request_id
                    )
                try:
                    payload = resp.json()
                except ValueError as exc:
                    raise InvalidResponse(SERVICE, "JSON invalide") from exc
                return parse_search(query, payload)

        return await with_retry(call, attempts=2)


def parse_search(query: str, payload: Any) -> SearchResult:
    if not isinstance(payload, Mapping):
        raise InvalidResponse(SERVICE, "réponse non objet")
    data = payload.get("data", payload if "sources" not in payload else None)
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            data = {"answer": data}
    if data is not None and not isinstance(data, Mapping):
        raise InvalidResponse(SERVICE, "data non objet")
    sources = []
    for src in payload.get("sources") or []:
        if isinstance(src, Mapping) and src.get("url"):
            sources.append(
                SearchSource(
                    name=str(src.get("name") or ""),
                    url=str(src["url"]),
                    snippet=str(src.get("snippet") or src.get("content") or "")[:2000],
                )
            )
    answer = None
    if isinstance(data, Mapping) and isinstance(data.get("answer"), str):
        answer = data["answer"]
    elif isinstance(payload.get("answer"), str):
        answer = payload["answer"]
    return SearchResult(query=query, data=data, answer=answer, sources=tuple(sources))
