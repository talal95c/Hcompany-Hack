"""Adaptateur Blender : canal TCP de l'add-on, régions, checks blender.* et démo sûre."""

from collections.abc import Awaitable, Callable
from typing import Any

from engine.adapters.base import Command, TargetHint
from engine.adapters.profiles import AppProfile
from engine.checks import SceneState

HIGHLIGHT = {"color": "#ffcc00", "duration_ms": 3000}


class BlenderAdapter:
    sensor = "addon"
    app_id = "blender"
    window_scope = False
    mismatch_code = "blender_version_mismatch"

    def __init__(self, runtime: Any, profile: AppProfile | None = None):
        self.runtime = runtime
        self.profile = profile
        self.shortcut_hint = profile.shortcut_hint if profile else "F3"
        self.state = SceneState()
        self.regions: list[dict] = []
        self.ui_revision = 0
        self.version = ""

    def available(self) -> bool:
        return bool(self.version) and self.runtime.addon.writer is not None

    def snapshot(self) -> SceneState:
        return self.state

    async def refresh(self, step: dict) -> SceneState:
        return self.state

    def facts(self) -> dict[str, str | None]:
        return self.state.facts()

    def describe_version(self) -> str:
        return "Version Blender incompatible : " + self.version

    def apply(self, event: dict) -> None:
        """Applique un événement add-on validé (hello, régions, scène)."""
        if event["type"] == "hello":
            self.version = event["payload"]["blender_version"]
        if event["type"] == "regions.changed":
            self.regions = event["payload"]["regions"]
            self.ui_revision = event["payload"]["ui_revision"]
        state = self.state
        if "base_revision" in event and event["base_revision"] <= state.revision + 1:
            state.revision = event["scene_revision"] - 1
        state.apply(event)

    def region(self, step: dict) -> dict | None:
        target = step.get("target", {})
        return next((r for r in self.regions if
                     r.get("area_type", target.get("area_type")) == target.get("area_type")
                     and r.get("region_type", r.get("type")) == target.get("region_type")), None)

    def zone(self, step: dict) -> tuple[Command, ...]:
        region = self.region(step)
        if not region:
            return ()
        return (("addon", "highlight", {"area_id": region["area_id"],
                                        "region_id": region["region_id"], **HIGHLIGHT}),)

    def reveal(self, step: dict) -> tuple[Command, ...]:
        region, menu = self.region(step), step.get("help", {}).get("menu_id")
        if not region or not menu:
            return ()
        return (("addon", "open_menu", {"menu_id": menu, "area_id": region["area_id"],
                                        "region_id": region["region_id"]}),)

    def replay(self, step: dict) -> tuple[Command, ...]:
        help_spec = step.get("help", {})
        if not help_spec.get("safe_demo") or not help_spec.get("checkpoint_id"):
            return ()
        return (("addon", "replay", {"procedure_ref": step["procedure_ref"], "params": {}}),)

    def undo_replay(self, step: dict) -> tuple[Command, ...]:
        checkpoint = step.get("help", {}).get("checkpoint_id")
        if not self.replay(step):
            return ()
        return (("addon", "undo_demo", {"checkpoint_id": checkpoint}),)

    def expected_rect(self, step: dict) -> TargetHint | None:
        # La capture est déjà recadrée sur la région dévoilée : pas de seconde contrainte.
        return None

    def reveal_target(self, step: dict) -> Callable[[], Awaitable[dict | None]]:
        async def reveal() -> dict | None:
            reveal_commands = self.reveal(step)
            if not reveal_commands:
                return None
            _, kind, payload = reveal_commands[0]
            runtime = self.runtime
            command = runtime.make_command(kind, payload)
            result = await runtime.addon.correlation.request(command, runtime.addon.send)
            if result["status"] != "ok":
                raise ValueError("Dévoilement refusé par l'application")
            region = next((r for r in self.regions if r["region_id"] == payload["region_id"]), None)
            if region is None:
                raise ValueError("Région absente après acquittement du menu")
            return region["screen_rect"]

        return reveal
