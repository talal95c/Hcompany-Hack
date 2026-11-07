"""Recherche documentaire éditeur avec Linkup."""

from __future__ import annotations

import logging
import os
import re
import time
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    import httpx


async def docs_search(
    query: str,
    *,
    blender_version: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> list[dict]:
    import httpx

    key = os.environ.get("LINKUP_API_KEY")
    if not key:
        raise RuntimeError("Clé Linkup absente")
    match = re.search(r"\bBlender\s+(\d+\.\d+)(?:\.\d+)?\b", query, re.IGNORECASE)
    version = blender_version or (match[1] if match else None)
    if version:
        if not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", version):
            raise ValueError("Version Blender invalide pour la recherche")
        version = ".".join(version.split(".")[:2])
    path_pattern = re.compile(rf"^/(?:manual/[^/]+|api)/{re.escape(version)}/") if version else None
    if version:
        query = (
            query.replace(match[0], f"Blender {version}") if match else f"Blender {version} {query}"
        )
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
                and urlparse(item.get("url", "")).scheme == "https"
                and (path_pattern is None or path_pattern.match(urlparse(item.get("url", "")).path))
            ]
        except httpx.TimeoutException as exc:
            raise TimeoutError("Recherche Linkup : délai de 15 s dépassé") from exc
        finally:
            logging.getLogger(__name__).info("Linkup : %.3f s", time.perf_counter() - started)

    if client is not None:
        return await search(client)
    async with httpx.AsyncClient() as session:
        return await search(session)


async def search_docs(
    query: str,
    *,
    domains: tuple[str, ...] | list[str],
    client: httpx.AsyncClient | None = None,
) -> list[dict]:
    """Recherche Linkup restreinte aux domaines officiels d'une application (HTTPS seulement)."""
    import httpx

    key = os.environ.get("LINKUP_API_KEY")
    if not key:
        raise RuntimeError("Clé Linkup absente")
    allowed = {d.lower() for d in domains if re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", d.lower())}
    if not allowed:
        raise ValueError("Aucun domaine documentaire valide")
    started = time.perf_counter()

    async def search(session: httpx.AsyncClient) -> list[dict]:
        try:
            response = await session.post(
                "https://api.linkup.so/v1/search",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "q": query,
                    "depth": "standard",
                    "outputType": "searchResults",
                    "includeDomains": sorted(allowed),
                },
                timeout=15,
            )
            response.raise_for_status()
            return [
                {k: str(item.get(k, ""))[:2000] for k in ("name", "url", "content")}
                for item in response.json().get("results", [])
                if urlparse(item.get("url", "")).scheme == "https"
                and (urlparse(item.get("url", "")).hostname or "") in allowed
            ]
        except httpx.TimeoutException as exc:
            raise TimeoutError("Recherche Linkup : délai de 15 s dépassé") from exc
        finally:
            logging.getLogger(__name__).info("Linkup : %.3f s", time.perf_counter() - started)

    if client is not None:
        return await search(client)
    async with httpx.AsyncClient() as session:
        return await search(session)
