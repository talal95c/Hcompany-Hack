"""Checks génériques sur une lecture fraîche, bornée et non ambiguë."""

import math
import re
import subprocess
import time


def matches_value(actual, expected, match="equals", tolerance=0):
    if match == "contains":
        return isinstance(actual, str) and isinstance(expected, str) and expected in actual
    if match == "regex":
        return (isinstance(actual, str) and isinstance(expected, str)
                and re.search(expected, actual) is not None)
    if match != "equals":
        raise ValueError("Comparaison inconnue")
    if isinstance(expected, bool):
        return isinstance(actual, bool) and actual == expected
    if isinstance(expected, (int, float)):
        return (isinstance(actual, (int, float)) and not isinstance(actual, bool)
                and math.isfinite(actual) and abs(actual - expected) <= tolerance)
    return isinstance(actual, str) and actual == expected


class Evaluator:
    def __init__(self, reader, visual=None):
        self.reader = reader
        self.visual = visual

    def evaluate(self, check):
        start = time.perf_counter()
        reads = []
        visual_evidence = None
        observed = None
        params = check["params"]
        deadline = start + params.get("timeout_ms", 0) / 1000
        while True:
            read_start = time.perf_counter()
            try:
                if check["name"] == "visual_assert":
                    visual_evidence = self.visual(params) if self.visual else None
                    status = self.visual_status(visual_evidence, params)
                elif check["name"] == "window_title":
                    title = self.reader.window_title()
                    observed = title
                    status = "unknown" if title is None else self.status(matches_value(
                        title, params["value"], params.get("match", "contains")))
                else:
                    nodes, complete = self.reader.read(params["target"])
                    status = self.native_status(check["name"], params, nodes, complete)
            except (RuntimeError, OSError, ValueError, re.error, NotImplementedError,
                    subprocess.TimeoutExpired):
                status = "unknown"
            reads.append(time.perf_counter() - read_start)
            if status == "pass" or time.perf_counter() >= deadline:
                break
            time.sleep(min(0.05, max(0, deadline - time.perf_counter())))
        return {"status": status, "seconds": time.perf_counter() - start,
                "read_seconds": reads, "visual": visual_evidence, "observed": observed}

    @staticmethod
    def status(value):
        return "pass" if value else "fail"

    @classmethod
    def visual_status(cls, result, params):
        if not isinstance(result, dict) or type(result.get("answer")) is not bool:
            return "unknown"
        confidence = result.get("confidence")
        if (isinstance(confidence, bool) or not isinstance(confidence, (int, float))
                or not math.isfinite(confidence) or not 0 <= confidence <= 1
                or confidence < params.get("min_confidence", 0.8)):
            return "unknown"
        return cls.status(result["answer"])

    @classmethod
    def native_status(cls, name, params, nodes, complete):
        if len(nodes) > 1 or not complete:
            return "unknown"
        if name == "element_exists":
            return cls.status(bool(nodes) == params.get("present", True))
        if not nodes:
            return "fail"
        node = nodes[0]
        if name == "element_value":
            if node.get("value") is None:
                return "unknown"
            return cls.status(matches_value(node["value"], params["value"],
                                           params.get("match", "equals"),
                                           params.get("tolerance", 0)))
        if name == "element_state":
            states = node.get("states")
            if states is None:
                return "unknown"
            required, absent = params.get("states", []), params.get("absent_states", [])
            if set(required + absent) & set(node.get("unsupported_states", [])):
                return "unknown"
            if not required and not absent:
                return "unknown"
            return cls.status(all(s in states for s in required)
                              and all(s not in states for s in absent))
        return "unknown"
