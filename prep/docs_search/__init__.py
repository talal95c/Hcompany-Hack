"""Recherche documentaire éditeur avec Linkup."""

from __future__ import annotations

import logging
import os
import time
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    import httpx


async def docs_search(query: str, *, client: httpx.AsyncClient | None = None) -> list[dict]:
    import httpx

    key = os.environ.get("LINKUP_API_KEY")
    if not key:
        raise RuntimeError("Clé Linkup absente")
    started = time.perf_counter()

    async def search(session: httpx.AsyncClient) -> list[dict]:
        try:
            response = await session.post(
                "https://api.linkup.so/v1/search",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "q": f"site:docs.blender.org {query}",
                    "depth": "standard",
                    "outputType": "searchResults",
                    "includeDomains": ["docs.blender.org"],
                },
                timeout=15,
            )
            response.raise_for_status()
            return [
                {k: item.get(k, "") for k in ("name", "url", "content")}
                for item in response.json().get("results", [])
                if urlparse(item.get("url", "")).hostname == "docs.blender.org"
            ]
        except httpx.TimeoutException as exc:
            raise TimeoutError("Recherche Linkup : délai de 15 s dépassé") from exc
        finally:
            logging.getLogger(__name__).info("Linkup : %.3f s", time.perf_counter() - started)

    if client is not None:
        return await search(client)
    async with httpx.AsyncClient() as session:
        return await search(session)
