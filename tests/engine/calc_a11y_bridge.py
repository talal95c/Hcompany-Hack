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
refs: dict[str, tuple[object, str]] = {}
consents: dict[str, float] = {}
captures: dict[str, tuple[dict, str, float]] = {}
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
                refs[converted["ref"]] = (accessible, root.name)
                if len(refs) > 256:
                    refs.pop(next(iter(refs)))
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


def require_consent(request: dict) -> None:
    if time.monotonic() >= consents.get(request.get("consent_token"), 0):
        raise ValueError("Consentement absent ou expiré")


def focused(root) -> bool:
    window = subprocess.check_output(["xdotool", "getwindowfocus"], text=True).strip()
    title = subprocess.check_output(["xdotool", "getwindowname", window], text=True).strip()
    return title == root.name


def action(root, request: dict) -> None:
    require_consent(request)
    accessible, title = refs[request["ref"]]
    if title != root.name or not focused(root):
        raise ValueError("Fenêtre modifiée")
    if accessible.getRoleName() == "password text":
        raise ValueError("Cible privée")
    kind = request["action"]
    if kind == "focus":
        accessible.queryComponent().grabFocus()
    elif kind == "set_value":
        value = request["value"]
        try:
            if accessible.queryEditableText().setTextContents(value):
                return
        except NotImplementedError:
            pass
        try:
            scalar = accessible.queryValue()
            scalar.currentValue = float(value)
            if scalar.currentValue == float(value):
                return
        except (NotImplementedError, ValueError):
            pass
        accessible.queryComponent().grabFocus()
        if not focused(root):
            raise ValueError("Fenêtre modifiée")
        bounds = node(accessible, request["ref"])["bounds"]
        window = node(root, "frame")["bounds"]
        x, y = bounds["x"] + bounds["w"] / 2, bounds["y"] + bounds["h"] / 2
        if not (window["x"] <= x < window["x"] + window["w"]
                and window["y"] <= y < window["y"] + window["h"]):
            raise ValueError("Cible hors fenêtre")
        subprocess.run(["xdotool", "mousemove", str(round(x)), str(round(y)), "click", "1"],
                       check=True)
        if value:
            subprocess.run(["xdotool", "type", "--clearmodifiers", "--", value], check=True)
        else:
            subprocess.run(["xdotool", "key", "F2", "ctrl+a", "BackSpace"], check=True)
        subprocess.run(["xdotool", "key", "Return"], check=True)
    elif kind == "select":
        parent = accessible.parent
        parent.querySelection().selectChild(accessible.getIndexInParent())
    elif kind in {"press", "toggle", "expand", "collapse"}:
        actions = accessible.queryAction()
        allowed = {kind, "click" if kind == "press" else kind}
        matches = [i for i in range(actions.nActions) if actions.getName(i) in allowed]
        if len(matches) != 1 or not actions.doAction(matches[0]):
            raise ValueError("Action indisponible")
    else:
        raise ValueError("Action non autorisée")


def input_action(root, request: dict) -> None:
    require_consent(request)
    bounds, title, captured = captures.pop(request["capture_id"])
    if (time.monotonic() - captured > 10 or title != root.name
            or bounds != node(root, "frame")["bounds"]):
        raise ValueError("Capture périmée")
    point = request["action"]
    x, y = point["x"], point["y"]
    if (point["type"] != "click" or point.get("button") != "left"
            or not 0 < x < 1000 or not 0 < y < 1000 or not focused(root)):
        raise ValueError("Point hors de la fenêtre cible")
    px = bounds["x"] + x * bounds["w"] / 1000
    py = bounds["y"] + y * bounds["h"] / 1000
    subprocess.run(["xdotool", "mousemove", str(round(px)), str(round(py)), "click", "1"],
                   check=True)


def handle(request: dict) -> dict:
    global snapshot
    root = frame(request["app"])
    if request["op"] == "consent":
        consents[request["token"]] = time.monotonic() + 60
        return {"status": "ok"}
    if request["op"] == "stop":
        consents.clear()
        captures.clear()
        return {"status": "ok"}
    if request["op"] == "frame":
        if root is None:
            return {"error": "APP_NOT_FOUND"}
        return {"title": root.name, "bounds": node(root, "frame")["bounds"],
                "name": "LibreOffice Calc" if root.name.endswith("LibreOffice Calc") else root.name,
                "version": VERSION}
    if root is None:
        return {"snapshot_id": None, "complete": False, "nodes": [],
                "error": {"code": "APP_NOT_FOUND", "message": "Fenêtre absente"}}
    if request["op"] == "capture":
        captures[request["capture_id"]] = (
            node(root, "frame")["bounds"], root.name, time.monotonic())
        return {"status": "ok"}
    if request["op"] == "input":
        input_action(root, request)
        return {"status": "ok"}
    if request["op"] == "action":
        action(root, request)
        return {"snapshot_id": f"atspi-{snapshot}", "complete": True, "nodes": []}
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
