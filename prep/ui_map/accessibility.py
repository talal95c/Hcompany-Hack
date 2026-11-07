"""Carte d'interface générique construite depuis un instantané d'accessibilité.

Entrée : nœuds normalisés `{ref, role, name, value?, states, bounds, parent_ref}` (forme
`a11y_node` de contracts/desktop-ws.schema.json), produits par AT-SPI aujourd'hui et par
les adaptateurs AX/UIA demain. Les rôles natifs sont ramenés à un vocabulaire commun ;
les refs ne sortent jamais de l'instantané : les cibles restent descriptives.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

ROLE_ALIASES = {
    "push button": "button",
    "toggle button": "toggle_button",
    "table cell": "cell",
    "dataitem": "cell",
    "menu item": "menu_item",
    "check menu item": "menu_item",
    "radio menu item": "menu_item",
    "menuitem": "menu_item",
    "document spreadsheet": "document",
    "document text": "document",
    "document frame": "document",
    "document presentation": "document",
    "page tab": "tab",
    "tabitem": "tab",
    "page tab list": "tab_list",
    "combo box": "combo_box",
    "combobox": "combo_box",
    "popupbutton": "combo_box",
    "menu bar": "menu_bar",
    "menubar": "menu_bar",
    "tool bar": "toolbar",
    "entry": "text",
    "edit": "text",
    "textfield": "text",
    "password text": "text",
    "check box": "checkbox",
    "radio button": "radio",
    "radiobutton": "radio",
    "list item": "list_item",
    "listitem": "list_item",
    "tree item": "tree_item",
    "treeitem": "tree_item",
    "spin button": "spin_button",
    "spinner": "spin_button",
    "dialog": "dialog",
    "sheet": "dialog",
    "window": "frame",
    "frame": "frame",
}
ACTIONABLE = frozenset(
    {
        "button",
        "toggle_button",
        "menu_item",
        "menu",
        "checkbox",
        "radio",
        "combo_box",
        "tab",
        "text",
        "list_item",
        "tree_item",
        "link",
        "slider",
        "spin_button",
        "document",
        "embedded",
        "cell",
    }
)
CELL_NAME = re.compile(r"^[A-Z]{1,3}[0-9]{1,7}$")
CONTAINERS = frozenset({"application", "filler", "panel", "root_pane", "scroll_pane", "viewport"})
UNNAMED_SEGMENTS = frozenset({"frame", "document"})
"""Titres de fenêtre et de document dépendent du fichier ouvert : chemin sur le rôle seul."""


def normalize_role(role: str) -> str:
    """Rôle natif (AT-SPI « push button », AX « AXButton », UIA « ButtonControl ») → commun."""
    raw = role.strip()
    if raw.startswith("AX") and raw[2:3].isupper():
        raw = raw[2:]
    if raw.endswith("Control") and raw != "Control":
        raw = raw[: -len("Control")]
    lowered = raw.lower()
    if lowered in ROLE_ALIASES:
        return ROLE_ALIASES[lowered]
    snake = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", raw).lower()
    snake = re.sub(r"[^a-z0-9]+", "_", snake).strip("_")
    return ROLE_ALIASES.get(snake.replace("_", " "), snake or "unknown")


def clean_name(name: str | None) -> str:
    return " ".join((name or "").split())


def annotate(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Nœuds avec rôle commun et chemin d'ancêtres « role:nom » depuis la fenêtre."""
    nodes = snapshot.get("nodes") or []
    by_ref = {node["ref"]: node for node in nodes}
    paths: dict[str, list[str]] = {}

    def path_of(ref: str | None, depth: int = 0) -> list[str]:
        if ref is None or ref not in by_ref or depth > 200:
            return []
        if ref in paths:
            return paths[ref]
        node = by_ref[ref]
        parent = path_of(node.get("parent_ref"), depth + 1)
        role, name = normalize_role(node.get("role", "")), clean_name(node.get("name"))
        if role in UNNAMED_SEGMENTS:
            own = [role]
        else:
            own = [f"{role}:{name}"] if name and role not in CONTAINERS else []
        paths[ref] = parent + own
        return paths[ref]

    result = []
    for node in nodes:
        parent_path = path_of(node.get("parent_ref"))
        result.append(
            {
                **node,
                "role": normalize_role(node.get("role", "")),
                "native_role": node.get("role", ""),
                "name": clean_name(node.get("name")),
                "path": parent_path,
            }
        )
    return result


def _path_matches(expected: list[str], actual: list[str]) -> bool:
    position = 0
    for entry in actual:
        if position < len(expected) and _segment(entry) == _segment(expected[position]):
            position += 1
    return position == len(expected)


def _segment(entry: str) -> tuple[str, str]:
    role, _, name = entry.partition(":")
    role = normalize_role(role)
    return role, "" if role in UNNAMED_SEGMENTS else clean_name(name).casefold()


def find_nodes(snapshot: dict[str, Any], target: dict[str, Any]) -> list[dict[str, Any]]:
    """Nœuds correspondant à une cible descriptive (rôle, nom, chemin) ; visibles d'abord."""
    role = normalize_role(target["role"]) if target.get("role") else None
    name = clean_name(target.get("name")).casefold() if target.get("name") else None
    path = list(target.get("path") or [])
    if role is None and name is None:
        return []
    matches = [
        node
        for node in annotate(snapshot)
        if (role is None or node["role"] == role)
        and (name is None or node["name"].casefold() == name)
        and _path_matches(path, node["path"])
    ]
    visible = [node for node in matches if "visible" in node.get("states", [])]
    return visible or matches


def requested_cells(*targets: dict[str, Any] | None) -> list[str]:
    cells = set()
    for target in targets:
        if target and normalize_role(target.get("role", "")) == "cell":
            name = clean_name(target.get("name")).upper()
            if CELL_NAME.fullmatch(name):
                cells.add(name)
    return sorted(cells)


def build_ui_map(snapshot: dict[str, Any], *, app: dict[str, Any]) -> dict[str, Any]:
    """Carte structurelle : contrôles actionnables nommés, sans valeurs ni refs."""
    controls: dict[tuple, dict[str, Any]] = {}
    for node in annotate(snapshot):
        if node["role"] not in ACTIONABLE or not node["name"] or node["role"] == "cell":
            continue
        key = (node["role"], node["name"], tuple(node["path"]))
        controls.setdefault(key, {"role": node["role"], "name": node["name"], "path": node["path"]})
    ordered = sorted(controls.values(), key=lambda c: (c["path"], c["role"], c["name"]))
    managed = {ref for ref in snapshot.get("managed_refs", [])}
    containers = [
        {"role": node["role"], "name": node["name"], "path": node["path"]}
        for node in annotate(snapshot)
        if node["ref"] in managed
    ]
    ui_map = {
        "kind": "accessibility",
        "app": app,
        "platform": snapshot.get("platform", "unknown"),
        "api": snapshot.get("api", "unknown"),
        "complete": bool(snapshot.get("complete")),
        "windows": [clean_name(title) for title in snapshot.get("windows", [])],
        "controls": ordered,
        "managed_containers": containers,
    }
    ui_map["sha256"] = hashlib.sha256(
        json.dumps({"controls": ordered, "app": app}, sort_keys=True).encode()
    ).hexdigest()
    return ui_map


def control_signature(ui_map: dict[str, Any] | None, target: dict[str, Any]) -> list[dict] | None:
    """Contrôles de la carte qui résolvent `target` ; None si la carte ne permet pas de conclure."""
    if not ui_map or ui_map.get("kind") != "accessibility":
        return None
    if normalize_role(target.get("role", "")) == "cell" and target.get("name"):
        return [{"role": "cell", "name": clean_name(target["name"]).upper(), "path": []}]
    found = find_nodes(
        {
            "nodes": [
                {**c, "ref": str(i), "parent_ref": None, "states": []}
                for i, c in enumerate(_flatten(ui_map["controls"]))
            ]
        },
        {**target, "path": []},
    )
    expected = list(target.get("path") or [])
    return [
        {"role": c["role"], "name": c["name"], "path": c["original_path"]}
        for c in found
        if _path_matches(expected, c["original_path"])
    ] or None


def _flatten(controls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**c, "original_path": c["path"]} for c in controls]


def diff_ui_maps(source: dict[str, Any] | None, target: dict[str, Any] | None) -> dict[str, Any]:
    def keys(ui_map: dict[str, Any] | None) -> set[tuple]:
        return {
            (c["role"], c["name"], tuple(c["path"])) for c in (ui_map or {}).get("controls", [])
        }

    old, new = keys(source), keys(target)
    return {
        "added": [list(k) for k in sorted(new - old)][:200],
        "removed": [list(k) for k in sorted(old - new)][:200],
        "unchanged": len(old & new),
    }


def control_vocabulary(ui_map: dict[str, Any] | None, limit: int = 500) -> list[str]:
    names = sorted({c["name"] for c in (ui_map or {}).get("controls", []) if len(c["name"]) < 60})
    return names[:limit]


def prompt_controls(ui_map: dict[str, Any], limit: int = 400) -> list[str]:
    """Lignes compactes « role | nom | chemin » pour le prompt du compilateur."""
    lines, seen = [], set()
    preferred = ("button", "toggle_button", "menu", "menu_item", "combo_box", "tab", "document")
    for control in sorted(
        ui_map.get("controls", []),
        key=lambda c: (
            preferred.index(c["role"]) if c["role"] in preferred else 99,
            len(c["path"]),
        ),
    ):
        key = (control["role"], control["name"])
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"{control['role']} | {control['name']} | {' > '.join(control['path'])}")
        if len(lines) >= limit:
            break
    return lines
