"""Pont AT-SPI de test (python3 système + pyatspi) : une requête JSON par ligne sur stdin.

Joue le rôle du backend natif Linux du desktop pour la recette Calc sous Xvfb.
"""

import json
import re
import subprocess
import sys
import time

import pyatspi

STATES = {
    pyatspi.STATE_FOCUSED: "focused", pyatspi.STATE_SELECTED: "selected",
    pyatspi.STATE_CHECKED: "checked", pyatspi.STATE_ENABLED: "enabled",
    pyatspi.STATE_EXPANDED: "expanded", pyatspi.STATE_SHOWING: "visible",
    pyatspi.STATE_EDITABLE: "editable", pyatspi.STATE_PRESSED: "pressed",
    pyatspi.STATE_BUSY: "busy",
}
CELL = re.compile(r"^([A-Z]{1,3})([0-9]{1,7})$")
snapshot = 0
VERSION = re.search(r"\d+\.\d+\.\d+(?:\.\d+)?", subprocess.check_output(
    ["soffice", "--version"], text=True)).group()


def frame(app_name: str):
    for app in pyatspi.Registry.getDesktop(0):
        if app is not None and app.name == app_name:
            for window in app:
                if window.getRoleName() == "frame":
                    return window
    return None


def node(accessible, ref: str) -> dict | None:
    try:
        extents = accessible.queryComponent().getExtents(pyatspi.DESKTOP_COORDS)
    except NotImplementedError:
        return None
    if extents.width <= 0 or extents.height <= 0 or extents.x < -100000:
        return None
    result = {"ref": ref, "role": accessible.getRoleName(), "name": accessible.name or "",
              "states": sorted({v for k, v in STATES.items()
                                if accessible.getState().contains(k)}),
              "bounds": {"x": extents.x, "y": extents.y, "w": extents.width,
                         "h": extents.height}}
    try:
        result["value"] = accessible.queryText().getText(0, -1)
    except NotImplementedError:
        pass
    return result


def matches(accessible, query: dict) -> bool:
    return ((not query.get("role") or accessible.getRoleName() == query["role"])
            and (not query.get("name") or (accessible.name or "") == query["name"]))


def find(root, query: dict) -> tuple[list[dict], bool]:
    found, complete, stack = [], True, [(root, "0")]
    while stack:
        accessible, path = stack.pop()
        if accessible is None:
            continue
        if matches(accessible, query):
            converted = node(accessible, f"{snapshot}:{path}")
            if converted is None:
                complete = False
            else:
                found.append(converted)
        count = accessible.childCount
        if accessible.getRoleName() in {"menu bar", "menu"}:
            continue
        if count > 500:
            # Tableur : adressage direct des cellules plutôt qu'un parcours de 2^30 enfants.
            cell = CELL.match(query.get("name", ""))
            if cell and query.get("role", "table cell") == "table cell":
                letters, row = cell.groups()
                column = 0
                for letter in letters:
                    column = column * 26 + ord(letter) - 64
                child = accessible.queryTable().getAccessibleAt(int(row) - 1, column - 1)
                stack.append((child, f"{path}/{letters}{row}"))
            continue
        stack.extend((accessible.getChildAtIndex(i), f"{path}/{i}") for i in range(count))
    return found, complete


def handle(request: dict) -> dict:
    global snapshot
    root = frame(request["app"])
    if request["op"] == "frame":
        if root is None:
            return {"error": "APP_NOT_FOUND"}
        return {"title": root.name, "bounds": node(root, "frame")["bounds"],
                "name": "LibreOffice Calc" if root.name.endswith("LibreOffice Calc") else root.name,
                "version": VERSION}
    if root is None:
        return {"snapshot_id": None, "complete": False, "nodes": [],
                "error": {"code": "APP_NOT_FOUND", "message": "Fenêtre absente"}}
    snapshot += 1
    nodes, complete = find(root, request["query"])
    return {"snapshot_id": f"atspi-{snapshot}", "complete": complete, "nodes": nodes}


for line in sys.stdin:
    request = json.loads(line)
    start = time.perf_counter()
    try:
        result = handle(request)
    except Exception as error:  # noqa: BLE001 - le pont signale toute panne AT-SPI
        result = {"snapshot_id": None, "complete": False, "nodes": [],
                  "error": {"code": "TIMEOUT", "message": type(error).__name__}}
    result["elapsed_ms"] = (time.perf_counter() - start) * 1000
    print(json.dumps({"id": request["id"], "result": result}), flush=True)
