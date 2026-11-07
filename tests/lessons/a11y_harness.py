"""Pilote AT-SPI : lectures natives et gestes xdotool dans une session privée."""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pyatspi
from generic_evaluator import Evaluator
from gi.repository import GLib
from odf_evidence import inspect_document
from visual_capture import prepare_image

HERE = Path(__file__).resolve().parent
STATES = {
    name: getattr(pyatspi, "STATE_" + name.upper())
    for name in (
        "focused",
        "selected",
        "checked",
        "enabled",
        "expanded",
        "visible",
        "editable",
        "pressed",
        "busy",
    )
}


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def children(node):
    node.clearCache()
    if node.childCount > 300:
        raise RuntimeError("Sous-arbre trop grand : résolution ciblée requise")
    return [node[i] for i in range(node.childCount)]


def descriptor(node):
    return node.getRoleName() + ":" + node.name


class Reader:
    def __init__(self, frame):
        self.frame = frame

    def window_title(self):
        frames = [
            node for node in children(self.frame.getApplication()) if node.getRoleName() == "frame"
        ]
        if len(frames) != 1:
            return None
        self.frame = frames[0]
        self.frame.clearCache()
        return self.frame.name

    def resolve(self, target):
        self.frame.clearCache()
        path = target.get("path")
        if not path or path[0] != descriptor(self.frame):
            return [], False
        if target.get("app_region") and target["app_region"] not in path:
            return [], False
        nodes = [self.frame]
        for ancestor in path[1:]:
            nodes = [
                child for node in nodes for child in children(node) if descriptor(child) == ancestor
            ]
        results = []
        complete = True
        for node in nodes:
            if node.getRoleName() == "table" and target.get("role") == "table cell":
                coordinate = re.fullmatch(r"([A-Z]+)([1-9][0-9]*)", target.get("name", ""))
                if not coordinate:
                    complete = False
                    continue
                column = 0
                for letter in coordinate[1]:
                    column = column * 26 + ord(letter) - ord("A") + 1
                row = int(coordinate[2]) - 1
                table = node.queryTable()
                if row >= table.nRows or column > table.nColumns:
                    continue
                child = table.getAccessibleAt(row, column - 1)
                if child is not None and child.name == target["name"]:
                    results.append((child, (table, row, column - 1)))
                else:
                    complete = False
            else:
                results.extend(
                    (child, None)
                    for child in children(node)
                    if (not target.get("role") or child.getRoleName() == target["role"])
                    and (not target.get("name") or child.name == target["name"])
                )
        return results, complete

    def read(self, target):
        try:
            return self._read(target)
        except GLib.Error as exc:
            raise RuntimeError("Lecture AT-SPI indisponible") from exc

    def _read(self, target):
        resolved, complete = self.resolve(target)
        records = []
        for node, table_cell in resolved:
            node.clearCache()
            state = node.getState()
            if state.contains(pyatspi.STATE_DEFUNCT):
                return [], False
            states = [name for name, code in STATES.items() if state.contains(code)]
            try:
                value = node.queryText().getText(0, -1)
            except NotImplementedError:
                try:
                    value = node.queryValue().currentValue
                except NotImplementedError:
                    value = None
            records.append(
                {
                    "role": node.getRoleName(),
                    "name": node.name,
                    "value": value,
                    "states": sorted(states),
                    "unsupported_states": ["selected"] if table_cell else [],
                }
            )
        return records, complete


class Driver:
    def __init__(self, app, proof_dir):
        self.app = app
        self.proof_dir = proof_dir
        self.process = None
        self.reader = None
        self.starts = []
        self.visual_index = 0
        self.last_request = 0
        self.workspace = None

    def close(self):
        if self.process is not None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
            self.process = None
        self.reader = None
        if self.workspace is not None:
            self.workspace.cleanup()
            self.workspace = None

    def fresh(self):
        self.close()
        self.workspace = tempfile.TemporaryDirectory(dir=os.environ["XDG_RUNTIME_DIR"])
        start = time.perf_counter()
        if not re.fullmatch(r"libreoffice-[a-z]+", self.app["id"]):
            raise ValueError("Famille d'application non prise en charge")
        self.process = subprocess.Popen(
            [
                "soffice",
                "-env:UserInstallation=file://" + os.environ["LESSON_PROFILE"],
                "--norestore",
                "--nologo",
                "--" + self.app["id"].split("-")[-1],
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = start + 35
        while time.perf_counter() < deadline:
            desktop = pyatspi.Registry.getDesktop(0)
            frames = [
                frame
                for app in children(desktop)
                if app.name == "soffice"
                for frame in children(app)
                if frame.getRoleName() == "frame"
            ]
            if len(frames) == 1 and frames[0].name.endswith(self.app["name"]):
                self.reader = Reader(frames[0])
                windows = subprocess.run(
                    [
                        "xdotool",
                        "search",
                        "--onlyvisible",
                        "--name",
                        "^" + re.escape(frames[0].name) + "$",
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if windows.returncode == 0 and len(windows.stdout.split()) == 1:
                    self.window = windows.stdout.strip()
                    self.xdo("windowmove", self.window, "0", "0")
                    self.xdo("windowsize", self.window, "1500", "900")
                    self.xdo("windowfocus", self.window)
                    time.sleep(0.7)
                    self.starts.append(time.perf_counter() - start)
                    return
            time.sleep(0.2)
        raise RuntimeError("Fenêtre accessible absente après 35 s")

    @staticmethod
    def xdo(*args):
        subprocess.run(["xdotool", *args], check=True, timeout=10)

    def action(self, action):
        kind = action["kind"]
        if kind == "key":
            self.xdo("key", "--clearmodifiers", action["keys"])
        elif kind == "type":
            text = action["text"].replace("{output_dir}", self.workspace.name)
            self.xdo("type", "--clearmodifiers", "--delay", "30", "--", text)
        elif kind == "click":
            nodes, complete = self.reader.resolve(action["target"])
            if not complete or len(nodes) != 1:
                raise RuntimeError("Cible absente ou ambiguë : " + action["target"]["description"])
            node = nodes[0][0]
            if not node.getState().contains(pyatspi.STATE_SHOWING):
                raise RuntimeError("Cible non affichée")
            rect = node.queryComponent().getExtents(pyatspi.DESKTOP_COORDS)
            if rect.width <= 0 or rect.height <= 0:
                raise RuntimeError("Rectangle cible invalide")
            modifiers = action.get("modifiers", [])
            try:
                for modifier in modifiers:
                    self.xdo("keydown", modifier)
                self.xdo(
                    "mousemove",
                    str(rect.x + min(8, rect.width // 2)),
                    str(rect.y + rect.height // 2),
                    "click",
                    "1",
                )
            finally:
                for modifier in reversed(modifiers):
                    self.xdo("keyup", modifier)
        else:
            raise ValueError("Action inconnue")
        time.sleep(0.25)
        context = GLib.MainContext.default()
        while context.pending():
            context.iteration(False)

    def actions(self, actions):
        for action in actions:
            self.action(action)

    def visual(self, params):
        if not os.environ.get("HAI_API_KEY"):
            return None
        time.sleep(max(0, self.last_request + 2.5 - time.monotonic()))
        self.visual_index += 1
        image = self.proof_dir / f"capture-{self.visual_index:03}.png"
        rect = self.reader.frame.queryComponent().getExtents(pyatspi.DESKTOP_COORDS)
        x, y, width, height = rect.x, rect.y, rect.width, rect.height
        region = params.get("region")
        if region:
            if region["x"] + region["w"] > 1000 or region["y"] + region["h"] > 1000:
                raise ValueError("Zone hors fenêtre")
            x += round(rect.width * region["x"] / 1000)
            y += round(rect.height * region["y"] / 1000)
            width = round(rect.width * region["w"] / 1000)
            height = round(rect.height * region["h"] / 1000)
        if min(width, height) <= 0:
            raise ValueError("Capture vide")
        subprocess.run(
            [
                "import",
                "-window",
                "root",
                "-crop",
                f"{width}x{height}+{x}+{y}",
                "+repage",
                str(image),
            ],
            check=True,
            timeout=15,
        )
        sent = image.with_stem(image.stem + "-sent")
        metadata = prepare_image(image, sent)
        metadata["original_image"] = str(image.relative_to(self.proof_dir.parent))
        metadata["image"] = str(sent.relative_to(self.proof_dir.parent))
        self.last_request = time.monotonic()
        clock = time.perf_counter()
        try:
            process = subprocess.run(
                [
                    os.environ["LESSON_API_PYTHON"],
                    str(HERE / "holo_assert.py"),
                ],
                input=json.dumps({"image": str(sent), "assertion": params["assertion"]}),
                capture_output=True,
                text=True,
                timeout=125,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {
                **metadata,
                "answer": None,
                "confidence": 0,
                "error": "timeout",
                "seconds": time.perf_counter() - clock,
            }
        finally:
            self.last_request = time.monotonic()
        if process.returncode:
            return {
                **metadata,
                "answer": None,
                "confidence": 0,
                "error": "unavailable",
                "seconds": time.perf_counter() - clock,
            }
        result = json.loads(process.stdout)
        return {**result, **metadata}


def statuses(results):
    return [result["status"] for result in results]


def proof_results(proof):
    results = [*proof["before_results"], *proof["after_results"]]
    for error in proof["error_proofs"]:
        results += [
            error["mistake_result"],
            error["correct_result"],
            *error["step_check_results"],
            *error["other_error_results"].values(),
        ]
    return results


def prove(directory, output, native_only=False):
    lesson = json.loads((directory / "lesson.json").read_text())
    companion = json.loads((directory / "steps.json").read_text())
    lesson["status"] = "draft"
    lesson["proof"]["ui_path_verified"] = False
    for step in lesson["steps"]:
        step["proof"]["status"] = "draft"
        step["proof"]["ui_path_verified"] = False
    write(directory / "lesson.json", lesson)
    version = subprocess.check_output(["soffice", "--version"], text=True).strip()
    if not version.startswith("LibreOffice " + lesson["app"]["version"] + "."):
        raise RuntimeError("Version de l'application incompatible : " + version)
    proof_dir = directory / "proof"
    proof_dir.mkdir(exist_ok=True)
    driver = Driver(lesson["app"], proof_dir)
    start = time.perf_counter()
    results = []
    targets = {}
    for step in lesson["steps"]:
        targets[json.dumps(step["target"], sort_keys=True)] = step["target"]
        for c in [step["check"], *companion[step["id"]]["checks"]]:
            if "target" in c["params"]:
                t = c["params"]["target"]
                targets[json.dumps(t, sort_keys=True)] = t
        for error in step["known_errors"]:
            if "target" in error["check"]["params"]:
                t = error["check"]["params"]["target"]
                targets[json.dumps(t, sort_keys=True)] = t

    def summary():
        return [
            {"target": target, "nodes": driver.reader.read(target)[0]}
            for target in targets.values()
        ]

    def checkpoint(index):
        driver.fresh()
        for previous in lesson["steps"][:index]:
            driver.actions(companion[previous["id"]]["expected_actions"])

    try:
        for index, step in enumerate(lesson["steps"]):
            if native_only and step["check"]["name"] == "visual_assert":
                break
            clock = time.perf_counter()
            extra = companion[step["id"]]
            checks = [step["check"], *extra["checks"]]
            error_specs = [*step["known_errors"], *extra["known_errors_extra"]]
            if native_only:
                error_specs = [
                    error for error in error_specs if error["check"]["name"] != "visual_assert"
                ]
            error_proofs = []
            for error in error_specs:
                checkpoint(index)
                evaluator = Evaluator(driver.reader, driver.visual)
                before = summary()
                artifact_before = [
                    inspect_document(Path(driver.workspace.name), specification)
                    for specification in extra.get("artifact_checks", [])
                ]
                actions = error.get("mistake_actions", extra["mistake_actions"].get(error["code"]))
                if not actions:
                    raise RuntimeError("Gestes d'erreur absents")
                driver.actions(actions)
                mistake = evaluator.evaluate(error["check"])
                discriminators = {
                    other["code"]: evaluator.evaluate(other["check"])
                    for other in error_specs
                    if other["code"] != error["code"]
                }
                assert all(r["status"] == "fail" for r in discriminators.values()), discriminators
                wrong_checks = [evaluator.evaluate(c) for c in checks]
                artifact_mistake = [
                    inspect_document(Path(driver.workspace.name), specification)
                    for specification in extra.get("artifact_checks", [])
                ]
                assert mistake["status"] == "pass", (step["id"], error["code"], mistake, summary())
                assert not all(s == "pass" for s in statuses(wrong_checks)), wrong_checks
                error_proofs.append(
                    {
                        "code": error["code"],
                        "check": error["check"],
                        "actions": actions,
                        "before": before,
                        "after": summary(),
                        "on_mistake": mistake["status"],
                        "mistake_result": mistake,
                        "other_error_results": discriminators,
                        "artifact_before": artifact_before,
                        "artifact_on_mistake": artifact_mistake,
                        "step_checks_on_mistake": statuses(wrong_checks),
                        "step_check_results": wrong_checks,
                    }
                )
            checkpoint(index)
            evaluator = Evaluator(driver.reader, driver.visual)
            before = summary()
            assert all(e["before"] == before for e in error_proofs), "Checkpoints différents"
            before_results = [evaluator.evaluate(c) for c in checks]
            assert not all(s == "pass" for s in statuses(before_results))
            driver.actions(extra["expected_actions"])
            after_results = [evaluator.evaluate(c) for c in checks]
            assert all(s == "pass" for s in statuses(after_results)), (step["id"], after_results)
            artifacts = []
            for specification in extra.get("artifact_checks", []):
                evidence = inspect_document(Path(driver.workspace.name), specification)
                assert evidence["status"] == "pass", evidence
                destination = proof_dir / (step["id"] + "-" + specification["filename"])
                destination.write_bytes(
                    (Path(driver.workspace.name) / specification["filename"]).read_bytes()
                )
                evidence["evidence_ref"] = str(destination.relative_to(directory))
                artifacts.append(evidence)
            correct_errors = [evaluator.evaluate(e["check"]) for e in error_specs]
            assert all(status == "fail" for status in statuses(correct_errors)), correct_errors
            for error, correct in zip(error_proofs, correct_errors):
                error["on_correct_path"] = correct["status"]
                error["correct_result"] = correct
                print(
                    f"ERROR {step['id']} {error['code']} "
                    f"{error['on_mistake']} / {correct['status']}",
                    flush=True,
                )
            proof = {
                "step_id": step["id"],
                "app_version": version,
                "ui_path_verified": True,
                "before": before,
                "after": summary(),
                "actions": extra["expected_actions"],
                "checks": checks,
                "before_checks": statuses(before_results),
                "after_checks": statuses(after_results),
                "before_results": before_results,
                "after_results": after_results,
                "known_errors": statuses(correct_errors),
                "error_proofs": error_proofs,
                "seconds": time.perf_counter() - clock,
            }
            proof["artifact_results"] = artifacts
            write(proof_dir / f"{step['id']}.json", proof)
            results.append(proof)
            print(
                f"STEP {step['id']} before={proof['before_checks']} "
                f"after={proof['after_checks']} wall={proof['seconds']:.6f}s",
                flush=True,
            )
            measurements = proof_results(proof)
            native = [
                duration
                for result in measurements
                if result["visual"] is None
                for duration in result["read_seconds"]
            ]
            cloud = [result["visual"]["seconds"] for result in measurements if result["visual"]]
            print(f"LATENCY {step['id']} atspi_seconds={native} holo_seconds={cloud}", flush=True)
        if not native_only:
            lesson["status"] = "proven"
            lesson["proof"]["ui_path_verified"] = True
            for step in lesson["steps"]:
                step["proof"]["status"] = "proven"
                step["proof"]["ui_path_verified"] = True
                step["proof"]["method"] = (
                    "visual" if step["check"]["name"] == "visual_assert" else "accessibility"
                )
            write(directory / "lesson.json", lesson)
        images = {
            result["visual"][key]
            for proof in results
            for result in proof_results(proof)
            if result["visual"]
            for key in ("original_image", "image")
        }
        files = [
            directory / "lesson.json",
            directory / "steps.json",
            directory / "SOURCE.md",
            *[proof_dir / f"{p['step_id']}.json" for p in results],
            *[directory / name for name in sorted(images)],
            *[
                directory / artifact["evidence_ref"]
                for proof in results
                for artifact in proof["artifact_results"]
            ],
        ]
        manifest = {
            "lesson_id": lesson["lesson_id"],
            "app_version": version,
            "ui_path_verified": not native_only,
            "native_only": native_only,
            "app_start_seconds": driver.starts,
            "seconds": time.perf_counter() - start,
            "sha256": {
                str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in files
            },
        }
        write(proof_dir / "manifest.json", manifest)
        write(output, {"steps": results, **manifest})
        print(
            f"TOTAL {len(results)} steps; start_seconds={driver.starts}; "
            f"wall={manifest['seconds']:.6f}s",
            flush=True,
        )
    finally:
        driver.close()


if __name__ == "__main__":
    prove(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), "--native-only" in sys.argv)
