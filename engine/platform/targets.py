"""Capacité optionnelle de dévoilement ; aucune connaissance applicative dans la policy."""

import asyncio
from typing import Protocol


class TargetAdapter(Protocol):
    async def reveal_target(self, step: dict, context) -> dict | None: ...


class AddonTargetAdapter:
    shortcut_hint = "F3"

    def __init__(self, runtime):
        self.runtime = runtime

    async def reveal_target(self, step: dict, context) -> dict | None:
        if not context.menu_id or not context.area_id or not context.region_id:
            return None
        runtime = self.runtime
        command = runtime.make_command("open_menu", {
            "menu_id": context.menu_id, "area_id": context.area_id,
            "region_id": context.region_id,
        })
        result = await runtime.addon.correlation.request(command, runtime.addon.send)
        if result["status"] != "ok":
            raise ValueError("Dévoilement refusé par l'application")
        await asyncio.sleep(0.15)
        region = next(r for r in runtime.regions if r["region_id"] == context.region_id)
        return region["screen_rect"]
