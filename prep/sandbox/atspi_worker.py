"""Instantané AT-SPI exécuté par le Python système (pyatspi), hors venv.

Entrée JSON : {"app": nom accessible, "max_depth", "max_nodes", "cells": ["A1", ...]}.
Sortie JSON : nœuds au format `a11y_node` (contracts/desktop-ws.schema.json), sans valeur
de champ mot de passe, plus les titres de fenêtres et les refs dont les descendants sont gérés.
"""

import json
import re
import sys
import time

import pyatspi

STATES = {
    pyatspi.STATE_FOCUSED: "focused",
    pyatspi.STATE_SELECTED: "selected",
    pyatspi.STATE_CHECKED: "checked",
    pyatspi.STATE_ENABLED: "enabled",
    pyatspi.STATE_EXPANDED: "expanded",
    pyatspi.STATE_SHOWING: "visible",
    pyatspi.STATE_EDITABLE: "editable",
    pyatspi.STATE_PRESSED: "pressed",
    pyatspi.STATE_BUSY: "busy",
}
CELL = re.compile(r"^([A-Z]{1,3})([0-9]{1,7})$")


def cell_index(name):
    match = CELL.match(name)
    if not match:
        return None
    column = 0
    for char in match[1]:
        column = column * 26 + ord(char) - 64
    return int(match[2]) - 1, column - 1


def text_of(node):
    try:
        text = node.queryText()
    except NotImplementedError:
        text = None
    if text is not None:
        try:
            return text.getText(0, -1)
        except Exception:
            return None
    try:
        return str(node.queryValue().currentValue)
    except NotImplementedError:
        return None


def describe(node, ref, parent_ref, secret):
    state = node.getState()
    try:
        x, y, w, h = node.queryComponent().getExtents(pyatspi.DESKTOP_COORDS)
    except NotImplementedError:
        x = y = w = h = 0
    item = {
        "ref": ref,
        "role": node.getRoleName(),
        "name": node.name or "",
        "states": sorted({label for key, label in STATES.items() if state.contains(key)}),
        "bounds": {"x": int(x), "y": int(y), "w": max(int(w), 0), "h": max(int(h), 0)},
        "parent_ref": parent_ref,
    }
    if not secret:
        value = text_of(node)
        if value is not None and node.getRoleName() not in {"menu item", "menu", "push button"}:
            item["value"] = value[:2000]
    return item


def snapshot(args):
    started = time.perf_counter()
    desktop = pyatspi.Registry.getDesktop(0)
    apps = [app for app in desktop if app is not None and app.name == args["app"]]
    result = {"complete": True, "nodes": [], "windows": [], "managed_refs": [], "apps": []}
    result["apps"] = sorted({app.name for app in desktop if app is not None and app.name})
    if not apps:
        result.update(complete=False, error={"code": "APP_NOT_FOUND", "message": args["app"]})
        return result
    max_depth, max_nodes = args.get("max_depth", 30), args.get("max_nodes", 6000)
    cells = [name for name in args.get("cells", []) if cell_index(name)]
    counter = 0

    def walk(node, parent_ref, depth):
        nonlocal counter
        if node is None:
            return
        if counter >= max_nodes or depth > max_depth:
            result["complete"] = False
            return
        try:
            role = node.getRoleName()
            item = describe(node, f"e{counter + 1}", parent_ref, role == "password text")
            managed = node.getState().contains(pyatspi.STATE_MANAGES_DESCENDANTS)
            children = node.childCount
        except Exception:
            result["stale_skipped"] = result.get("stale_skipped", 0) + 1
            return
        counter += 1
        ref = item["ref"]
        bounded = item["bounds"]["w"] > 0 and item["bounds"]["h"] > 0
        if bounded:
            result["nodes"].append(item)
        else:
            ref = parent_ref
        if role in {"frame", "dialog", "alert", "file chooser"} and depth == 1:
            result["windows"].append(node.name or "")
        if managed:
            if bounded:
                result["managed_refs"].append(ref)
            if role == "table" and cells:
                table = node.queryTable()
                for name in cells:
                    row, column = cell_index(name)
                    if row < table.nRows and column < table.nColumns:
                        counter += 1
                        cell = table.getAccessibleAt(row, column)
                        cell_item = describe(cell, f"e{counter}", ref, False)
                        if cell_item["bounds"]["w"] > 0 and cell_item["bounds"]["h"] > 0:
                            result["nodes"].append(cell_item)
            return
        for index in range(children):
            try:
                child = node.getChildAtIndex(index)
            except Exception:
                result["stale_skipped"] = result.get("stale_skipped", 0) + 1
                continue
            walk(child, ref, depth + 1)

    for app in apps:
        walk(app, None, 0)
    result["duration"] = time.perf_counter() - started
    return result


def press(args):
    desktop = pyatspi.Registry.getDesktop(0)
    for app in desktop:
        if app is None or app.name != args["app"]:
            continue
        matches = []

        def walk(node, depth):
            if node is None or depth > 30:
                return
            if node.getRoleName() == args["role"] and (node.name or "") == args["name"]:
                if node.getState().contains(pyatspi.STATE_SHOWING):
                    matches.append(node)
            if node.getState().contains(pyatspi.STATE_MANAGES_DESCENDANTS):
                return
            for index in range(node.childCount):
                walk(node.getChildAtIndex(index), depth + 1)

        walk(app, 0)
        if len(matches) != 1:
            return {"ok": False, "error": "AMBIGUOUS_TARGET" if matches else "NOT_FOUND"}
        action = matches[0].queryAction()
        return {"ok": bool(action.doAction(0)), "action": action.getName(0)}
    return {"ok": False, "error": "APP_NOT_FOUND"}


if __name__ == "__main__":
    request = json.loads(sys.stdin.read())
    operation = {"snapshot": snapshot, "press": press}[request.pop("operation")]
    sys.stdout.write(json.dumps(operation(request)))
