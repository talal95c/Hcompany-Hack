"""Adaptateur accessibilité OS : messages `a11y.*` du desktop (AX, UI Automation, AT-SPI).

Les cibles descriptives sont résolues au début d'étape. Les événements déclenchent des
lectures fraîches des refs ; une réconciliation périodique refait les recherches.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from uuid import uuid4

from engine.adapters.base import Command, DemoAction, Rect, TargetHint
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
        self.request_ops: dict[str, str] = {}
        self.generation = 0
        self.changed = asyncio.Event()
        self.events_supported = False
        self.can_watch = False
        self.watch_id: str | None = None
        self.event_sequence = 0
        self.change_epoch = 0
        self.reconcile = True
        self.watched: dict[str, Lookup] = {}
        self.watch_scope = None
        self.last_full = 0.0
        self.refresh_lock = asyncio.Lock()

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
            self.interrupt_reads()
            self.reconcile = True
            self.changed.set()
        return changed

    def invalidate(self) -> None:
        self.state.complete = False
        self.state.latest_revision = self.state.revision + 1
        self.state.lookups.clear()
        self.state.verdicts.clear()

    def interrupt_reads(self) -> None:
        for request_id, future in self.pending.items():
            if (self.request_ops.get(request_id) in {"find", "get", "snapshot"}
                    and not future.done()):
                future.set_exception(ConnectionError("Observation modifiée"))

    def on_generation(self, generation: int) -> None:
        if generation != self.generation:
            self.generation = generation
            self.invalidate()
            self.interrupt_reads()
            self.reconcile = True
            self.changed.set()

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
        self.events_supported = False
        self.watch_id = None
        self.watched.clear()
        self.changed.set()

    def on_event(self, payload: dict) -> bool:
        if payload["watch_id"] != self.watch_id or payload["sequence"] <= self.event_sequence:
            return False
        self.event_sequence = payload["sequence"]
        self.events_supported = payload["events_supported"]
        self.reconcile |= payload["reconcile"] and not payload.get("scoped", False)
        self.change_epoch += 1
        self.invalidate()
        self.interrupt_reads()
        self.changed.set()
        return True

    async def request(self, op: str, **fields) -> dict:
        if len(self.pending) >= 64:
            raise RuntimeError("Trop de requêtes a11y en attente")
        request_id = str(uuid4())
        payload = {"request_id": request_id, "op": op, "app": self.app_id,
                   "deadline_ms": max(100, min(3000, int(self.timeout_s * 1000))),
                   "generation": self.generation, "focus_epoch": self.focus_epoch, **fields}
        future = asyncio.get_running_loop().create_future()
        self.pending[request_id] = future
        self.request_epochs[request_id] = self.focus_epoch
        self.request_ops[request_id] = op
        start = time.perf_counter()
        completed = False
        try:
            await self.send("a11y.request", payload)
            result = await asyncio.wait_for(future, self.timeout_s)
            completed = True
            self.metric("a11y." + op, (time.perf_counter() - start) * 1000)
            return result
        finally:
            self.pending.pop(request_id, None)
            self.request_epochs.pop(request_id, None)
            self.request_ops.pop(request_id, None)
            if not completed:
                with suppress(ConnectionError, RuntimeError):
                    await self.send("a11y.cancel", {"request_id": request_id})

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
        async with self.refresh_lock:
            return await self._refresh(step)

    async def _refresh(self, step: dict) -> AppState:
        epoch = self.focus_epoch
        generation = self.generation
        change_epoch = self.change_epoch
        targets = {query_key(query_for(t)): t for t in step_targets(step)}
        focused = self.focused
        scope = (self.generation, step.get("id"), epoch, tuple(targets))
        full = (self.reconcile or scope != self.watch_scope or not self.events_supported
                or time.monotonic() - self.last_full >= 4
                or any(not lookup.nodes for lookup in self.watched.values()))
        self.reconcile = False

        async def read(key, target, *, watched=False):
            previous = self.watched.get(key)
            if (full and not watched) or previous is None:
                return await self.find(target)
            try:
                results = await asyncio.gather(*(self.request("get", ref=node["ref"],
                    query=query_for(target)) for node in previous.nodes))
            except TimeoutError:
                return Lookup((), False, None, "TIMEOUT")
            error = next((r["error"]["code"] for r in results if r.get("error")), None)
            if error in {"STALE_REF", "AMBIGUOUS_TARGET"}:
                self.reconcile = True
                return await self.find(target)
            return Lookup(tuple(n for r in results for n in r["nodes"]),
                          all(r["complete"] for r in results), results[0]["snapshot_id"], error)

        try:
            lookups = dict(zip(targets, await asyncio.gather(
                *(read(k, t) for k, t in targets.items())))) if focused else {}
        except ConnectionError:
            return self.state
        if (epoch != self.focus_epoch or generation != self.generation
                or change_epoch != self.change_epoch):
            return self.state
        errors = [lookup.error for lookup in lookups.values() if lookup.error]
        self.last_error = errors[0] if errors else (
            "INCOMPLETE_TREE" if any(not lookup.complete for lookup in lookups.values()) else None)
        if self.can_watch and focused and not self.last_error and (full or self.reconcile):
            self.watch_scope = scope
            self.watched = dict(lookups)
            self.watch_id = str(uuid4())
            self.event_sequence = 0
            try:
                paths = [query_for(t).get("path", []) for t in targets.values()]
                common_path = []
                for parts in zip(*paths):
                    if len(set(parts)) != 1:
                        break
                    common_path.append(parts[0])
                result = await self.request("watch", watch_id=self.watch_id,
                    query={"path": common_path},
                    refs=list(dict.fromkeys(n["ref"] for v in lookups.values() for n in v.nodes)))
                self.events_supported = result.get("events_supported", False)
            except (TimeoutError, ConnectionError):
                self.events_supported = False
            self.last_full = time.monotonic()
            self.reconcile = False
            if self.events_supported:
                try:
                    lookups = dict(zip(targets, await asyncio.gather(
                        *(read(k, t, watched=True) for k, t in targets.items()))))
                except ConnectionError:
                    return self.state
                if self.reconcile:
                    self.invalidate()
                    self.changed.set()
                    return self.state
                errors = [lookup.error for lookup in lookups.values() if lookup.error]
                self.last_error = errors[0] if errors else (
                    "INCOMPLETE_TREE" if any(not v.complete for v in lookups.values()) else None)
        if (epoch != self.focus_epoch or generation != self.generation
                or change_epoch != self.change_epoch):
            return self.state
        state = self.state
        if self.events_supported and not self.last_error:
            self.watched = dict(lookups)
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

    def demo_plan(self, step: dict) -> DemoAction | None:
        hint = self.expected_rect(step)
        found = self.target_lookup(step)
        node = found.unique if found else None
        if not hint or not node or "password" in node.get("role", "").casefold():
            return None
        check = step["check"]
        params = check["params"]
        if query_for(params.get("target")) != query_for(step.get("target")):
            return None
        if check["name"] == "element_value" and params.get("match", "equals") == "equals":
            value = params.get("value")
            if isinstance(value, str | int | float | bool):
                previous = node.get("value")
                return DemoAction("set_value", str(value),
                                  "set_value" if previous is not None else None,
                                  str(previous) if previous is not None else None)
        if check["name"] == "element_state":
            states = params.get("states", [])
            if states == ["focused"]:
                return DemoAction("focus")
            if states == ["selected"]:
                return DemoAction("select")
        return None

    def undo_replay(self, step: dict) -> tuple[Command, ...]:
        return ()

    async def act(self, ref: str, action: str, consent_token: str, value: str | None = None,
                  ) -> dict:
        fields = {"ref": ref, "action": action, "consent_token": consent_token}
        if value is not None:
            fields["value"] = value
        return await self.request("action", **fields)
