"""Adaptateur accessibilité OS : messages `a11y.*` du desktop (AX, UI Automation, AT-SPI).

Les refs sont locales à un snapshot : chaque refresh refait des `find` à partir des cibles
descriptives de la leçon, puis les checks génériques lisent l'`AppState` obtenu.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from uuid import uuid4

from engine.adapters.base import Command, Rect, TargetHint
from engine.adapters.profiles import AppProfile
from engine.checks import AppState, Lookup
from engine.checks.generic import query_for, query_key

Send = Callable[[str, dict], Awaitable[None]]
HIGHLIGHT = {"color": "#ffcc00", "duration_ms": 3000}


def step_targets(step: dict) -> list[dict]:
    """Cibles a11y lues par l'étape : check, erreurs connues et cible d'aide."""
    targets = [step["check"]["params"].get("target")]
    targets += [e["check"]["params"].get("target") for e in step.get("known_errors", [])]
    targets.append(step.get("target"))
    return [t for t in targets if isinstance(t, dict) and query_for(t)]


class AccessibilityAdapter:
    sensor = "accessibility"
    window_scope = True
    mismatch_code = "app_mismatch"

    def __init__(self, app: dict, profile: AppProfile, send: Send, *,
                 timeout_s: float = 1.5, metric: Callable[[str, float], None] | None = None):
        self.app, self.profile, self.send = app, profile, send
        self.app_id = app["id"]
        self.shortcut_hint = profile.shortcut_hint
        self.timeout_s = timeout_s
        self.metric = metric or (lambda *_: None)
        self.pending: dict[str, asyncio.Future] = {}
        self.state = AppState(app_id=self.app_id)
        self.focus: dict | None = None
        self.permission = False
        self.last_error: str | None = None
        self.focus_epoch = 0
        self.request_epochs: dict[str, int] = {}

    @property
    def version(self) -> str:
        return (self.focus.get("version") or "unknown") if self.focused else "unknown"

    @property
    def focused(self) -> bool:
        return bool(self.focus) and self.profile.matches(self.focus["app_id"], self.focus["name"])

    @property
    def window(self) -> Rect | None:
        return Rect.from_dict(self.focus["window_bounds"]) if self.focused else None

    def available(self) -> bool:
        return (self.permission and self.focused
                and self.focus.get("accessibility", "unknown") != "unavailable")

    def describe_version(self) -> str:
        return "Fenêtre attendue : " + self.profile.name

    def snapshot(self) -> AppState:
        return self.state

    def facts(self) -> dict[str, str | None]:
        return self.state.facts()

    def on_focus(self, payload: dict) -> bool:
        """Mémorise `app.focus` ; True si la fenêtre ou ses bornes ont changé."""
        changed = self.focus is None or any(
            self.focus.get(k) != payload.get(k) for k in (
                "app_id", "name", "window_title", "window_bounds", "scale", "version"))
        self.focus = payload
        self.state.window_title = payload["window_title"] if self.focused else None
        if changed:
            self.focus_epoch += 1
        if changed or not self.focused:
            self.invalidate()
        return changed

    def invalidate(self) -> None:
        self.state.complete = False
        self.state.latest_revision = self.state.revision + 1
        self.state.lookups.clear()

    def resolve(self, payload: dict) -> bool:
        future = self.pending.get(payload["request_id"])
        if future is None or future.done():
            return False
        if self.request_epochs[payload["request_id"]] != self.focus_epoch:
            future.set_exception(ConnectionError("Fenêtre modifiée"))
            return False
        future.set_result(payload)
        return True

    def disconnect(self) -> None:
        self.focus_epoch += 1
        for future in self.pending.values():
            if not future.done():
                future.set_exception(ConnectionError("Desktop déconnecté"))
        self.focus = None
        self.permission = False
        self.invalidate()

    async def request(self, op: str, **fields) -> dict:
        if len(self.pending) >= 64:
            raise RuntimeError("Trop de requêtes a11y en attente")
        request_id = str(uuid4())
        payload = {"request_id": request_id, "op": op, "app": self.app_id, **fields}
        future = asyncio.get_running_loop().create_future()
        self.pending[request_id] = future
        self.request_epochs[request_id] = self.focus_epoch
        start = time.perf_counter()
        try:
            await self.send("a11y.request", payload)
            result = await asyncio.wait_for(future, self.timeout_s)
            self.metric("a11y." + op, (time.perf_counter() - start) * 1000)
            return result
        finally:
            self.pending.pop(request_id, None)
            self.request_epochs.pop(request_id, None)

    async def find(self, target: dict) -> Lookup:
        query = query_for(target)
        if query is None:
            return Lookup((), False, None, "NO_QUERY")
        for _ in range(2):
            try:
                result = await self.request("find", query=query)
            except TimeoutError:
                return Lookup((), False, None, "TIMEOUT")
            if result.get("error", {}).get("code") != "STALE_REF":
                break
        error = result.get("error", {}).get("code")
        return Lookup(tuple(result["nodes"]), result["complete"], result["snapshot_id"], error)

    async def refresh(self, step: dict) -> AppState:
        epoch = self.focus_epoch
        targets = {query_key(query_for(t)): t for t in step_targets(step)}
        focused = self.focused
        try:
            lookups = dict(zip(targets, await asyncio.gather(
                *(self.find(t) for t in targets.values())))) if focused else {}
        except ConnectionError:
            return self.state
        if epoch != self.focus_epoch:
            return self.state
        errors = [lookup.error for lookup in lookups.values() if lookup.error]
        self.last_error = errors[0] if errors else (
            "INCOMPLETE_TREE" if any(not lookup.complete for lookup in lookups.values()) else None)
        state = self.state
        state.lookups = lookups
        state.window_title = self.focus["window_title"] if focused else None
        state.revision = max(state.revision, state.latest_revision) + 1
        state.latest_revision = state.revision
        state.complete = focused and all(
            lookup.complete and not lookup.error for lookup in lookups.values())
        return state

    def target_lookup(self, step: dict) -> Lookup | None:
        query = query_for(step.get("target"))
        return self.state.lookups.get(query_key(query)) if query else None

    def expected_rect(self, step: dict) -> TargetHint | None:
        found = self.target_lookup(step)
        node = found.unique if (found and found.complete and not found.error
                                and self.state.recent) else None
        window = self.window
        if not node or not window:
            return None
        rect = Rect.from_dict(node["bounds"])
        if not rect.valid or not window.intersects(rect):
            return None
        return TargetHint(rect, node["ref"], found.snapshot_id, exact=True)

    def zone(self, step: dict) -> tuple[Command, ...]:
        hint = self.expected_rect(step)
        if not hint:
            return ()
        payload = {"app": self.app_id, "rect": hint.rect.px(), "ref": hint.ref,
                   "snapshot_id": hint.snapshot_id, "label": step["target"]["description"][:120],
                   **HIGHLIGHT}
        return (("desktop", "highlight.rect", payload),)

    def reveal(self, step: dict) -> tuple[Command, ...]:
        return ()

    def reveal_target(self, step: dict) -> None:
        return None

    def replay(self, step: dict) -> tuple[Command, ...]:
        # Démo = action native consentie (fais-le), jamais une relecture implicite.
        return ()

    def undo_replay(self, step: dict) -> tuple[Command, ...]:
        return ()

    async def act(self, ref: str, action: str, consent_token: str, value: str | None = None,
                  ) -> dict:
        fields = {"ref": ref, "action": action, "consent_token": consent_token}
        if value is not None:
            fields["value"] = value
        return await self.request("action", **fields)
