"""Inspection bornée d'une fenêtre privée pour décrire les cibles."""

import json
import sys
from pathlib import Path

import pyatspi
from a11y_harness import Driver, children, descriptor


def dump(node, path, depth=0):
    if depth > 25:
        return
    current = path + [descriptor(node)]
    try:
        text = node.queryText().getText(0, -1)
    except NotImplementedError:
        text = None
    if text is not None or node.getRoleName() in ("frame", "combo box", "text", "entry",
                                                 "paragraph", "heading", "document text", "dialog"):
        print(json.dumps({"path": current, "value": text}, ensure_ascii=False), flush=True)
    if node.getRoleName() in ("menu bar", "menu"):
        return
    if node.childCount > 300:
        return
    for child in children(node):
        dump(child, current, depth + 1)


if __name__ == "__main__":
    driver = Driver({"id": "libreoffice-writer", "name": "LibreOffice Writer"}, None)
    try:
        driver.fresh()
        if len(sys.argv) > 1:
            driver.actions(json.loads(sys.argv[1]))
        for app in children(pyatspi.Registry.getDesktop(0)):
            if app.name == "soffice":
                for frame in children(app):
                    dump(frame, [])
        print("OUTPUT", [p.name for p in Path(driver.workspace.name).iterdir()], flush=True)
    finally:
        driver.close()
