"""Cartes UI exactes et comparaison conservative."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from prep.sandbox import BlenderSandbox


async def dump_ui_map(sandbox: BlenderSandbox, cache_dir: Path | None = None) -> dict:
    started = time.perf_counter()
    result = await sandbox.invoke("ui_map")
    root = cache_dir or Path.home() / ".cache/hcompany-prep/ui_maps"
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{result['blender_version']}.json").write_text(json.dumps(result, indent=2))
    logging.getLogger(__name__).info("Carte UI : %.3f s", time.perf_counter() - started)
    return result


def step_signature(ui_map: dict | None, operator_id: str) -> dict | None:
    if not ui_map or operator_id not in ui_map.get("operators", {}):
        return None
    menus = ui_map.get("menus", {})

    def walk(menu_id: str, seen: set, labels: list) -> list:
        if menu_id in seen or menu_id not in menus:
            return []
        menu = menus[menu_id]
        paths = []
        for entry in menu["entries"]:
            if entry["kind"] == "operator" and entry["id"] == operator_id:
                label = entry["label"] or ui_map["operators"][operator_id]["name"]
                paths.append(" › ".join([*labels, menu["label"], label]))
            elif entry["kind"] == "menu":
                paths.extend(walk(entry["id"], seen | {menu_id}, [*labels, menu["label"]]))
        return paths

    roots = [key for key in menus if key == "VIEW3D_MT_add"]
    paths = sorted({path for root in roots for path in walk(root, set(), [])})
    if not paths:
        paths = sorted({path for root in menus for path in walk(root, set(), [])})
    if not paths:
        return None
    return {"operator": ui_map["operators"][operator_id], "ui_paths": paths}


def diff_ui_maps(a: dict, b: dict) -> dict:
    left, right = a.get("operators", {}), b.get("operators", {})
    return {
        "added_operators": sorted(right.keys() - left.keys()),
        "removed_operators": sorted(left.keys() - right.keys()),
        "changed_operators": sorted(k for k in left.keys() & right.keys() if left[k] != right[k]),
        "changed_menu_paths": sorted(
            k
            for k in a.get("menus", {}).keys() | b.get("menus", {}).keys()
            if a.get("menus", {}).get(k) != b.get("menus", {}).get(k)
        ),
    }


def operator_menu(ui_map: dict, operator_id: str) -> str | None:
    candidates = [
        key
        for key, menu in ui_map.get("menus", {}).items()
        if any(
            entry.get("kind") == "operator" and entry.get("id") == operator_id
            for entry in menu.get("entries", [])
        )
    ]
    preferred = [key for key in candidates if key.startswith("VIEW3D_MT_")]
    return min(
        preferred or candidates,
        key=lambda key: (len(ui_map["menus"][key].get("entries", [])), key),
        default=None,
    )
