"""Frontière de délégation, bloquée tant que le contrat manque."""

from typing import Any, Protocol

from agent.catalog import AgentError


class Runner(Protocol):
    async def run(
        self, procedure: dict[str, Any], session_id: str, consent_token: str
    ) -> dict[str, Any]: ...


class EngineRunner:
    async def run(
        self, procedure: dict[str, Any], session_id: str, consent_token: str
    ) -> dict[str, Any]:
        raise AgentError(
            "engine_protocol_unavailable: "
            "engine delegation contract not yet defined in contracts/; "
            "lesson identity/revision, consent, run_id and check results not representable "
            "in desktop-ws v1"
        )
