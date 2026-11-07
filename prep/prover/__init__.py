"""Preuve ordonnée par différence et checkpoints."""

import copy
import hashlib
import json
import re
import shutil
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol

from prep.docs_search import docs_search
from prep.prover.planner import Mode, next_mode
from prep.prover.procedures import CHECK_LIBRARY, PROCEDURE_LIBRARY
from prep.repair import write_repair_request
from prep.ui_map import step_signature

try:
    from httpx import HTTPError
except ModuleNotFoundError:
    HTTP_ERRORS = ()
else:
    HTTP_ERRORS = (HTTPError,)


class Sandbox(Protocol):
    async def version(self) -> str: ...
    async def reset(self) -> Path: ...
    async def run_step(
        self,
        checkpoint_in: str | Path,
        procedure: str,
        check: dict,
        checkpoint_out: str | Path,
    ) -> dict: ...


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


async def prove_lesson(
    lesson: dict,
    sandbox: Sandbox,
    source_map: dict | None,
    target_map: dict | None,
    out: Path,
    *,
    fixture: Path | None = None,
    reselect: Callable[[dict, list[dict]], Awaitable[str | None]] | None = None,
    search: Callable[[str], Awaitable[list[dict]]] = docs_search,
    source_steps: list[dict] | None = None,
    rejected_steps: dict[str, dict] | None = None,
) -> dict:
    result = copy.deepcopy(lesson)
    proof_dir = out / "proof"
    proof_dir.mkdir(parents=True, exist_ok=True)
    version = await sandbox.version()
    if version != lesson["blender_version"]:
        raise ValueError("Version Blender différente de la version cible")
    checkpoint = fixture or await sandbox.reset()
    fixture_dir = out / "fixtures"
    fixture_dir.mkdir(exist_ok=True)
    stored_fixture = fixture_dir / "initial.blend"
    if Path(checkpoint).resolve() != stored_fixture.resolve():
        shutil.copyfile(checkpoint, stored_fixture)
    checkpoint = stored_fixture
    if len({s["id"] for s in lesson["steps"]}) != len(lesson["steps"]):
        raise ValueError("Identifiants d'étape dupliqués")
    previous_steps = {
        s["id"]: s for s in (source_steps if source_steps is not None else lesson["steps"])
    }
    blocked = False
    manifest = []
    for index, step in enumerate(result["steps"]):
        step_id = step["id"]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", step_id):
            raise ValueError("Identifiant d'étape non sûr")
        evidence_path = proof_dir / f"{step_id}.json"
        output = proof_dir / f"{step_id}.blend"
        procedure = step.get("procedure_ref")
        check = step.get("check", {})
        hashes = {
            "version": digest(version),
            "check": digest(check),
            "params": digest(
                {"check": check.get("params"), "preconditions": step.get("preconditions")}
            ),
            "procedure": digest({"id": procedure, "definition": PROCEDURE_LIBRARY.get(procedure)}),
            "fixture": hashlib.sha256(Path(checkpoint).read_bytes()).hexdigest(),
        }
        evidence = {
            "step_id": step_id,
            "blender_version": version,
            "hashes": hashes,
            "mode_trace": [],
            "sources": [],
            "ui_path_verified": False,
        }
        trace = evidence["mode_trace"]
        mode = Mode.EXECUTE

        def transition(event: str) -> None:
            nonlocal mode
            mode = next_mode(mode, event)
            trace.append(mode.value)

        status, method = "pending", "bpy"
        old = json.loads(evidence_path.read_text()) if evidence_path.exists() else {}
        rejection = (rejected_steps or {}).get(step_id)
        if (
            check.get("name") not in CHECK_LIBRARY
            or rejection
            or step.get("proof", {}).get("method") == "handoff"
        ):
            mode = Mode.OBSERVE
            trace.append(mode.value)
            transition("no_check")
            method = "handoff"
            request = write_repair_request(
                out,
                lesson_id=lesson["lesson_id"],
                step_id=step_id,
                reason=rejection["reason"]
                if rejection
                else "Check absent ou procédure non autorisée",
                fixture=str(checkpoint),
                expected_result=rejection or check,
                blender_version=version,
            )
            evidence["repair_request"] = str(request.relative_to(out))
        elif blocked:
            evidence["reason"] = "Étape précédente non prouvée"
        else:
            operator_id = PROCEDURE_LIBRARY.get(procedure, {}).get("operator_id")
            source = step_signature(source_map, operator_id)
            target = step_signature(target_map, operator_id)
            evidence["source_signature"] = source
            evidence["target_signature"] = target
            prior = previous_steps.get(step_id, {})
            unchanged = (
                source is not None
                and source == target
                and source_map.get("blender_version") is not None
                and target_map.get("blender_version") == version
                and prior.get("check") == check
                and prior.get("preconditions") == step.get("preconditions")
                and prior.get("procedure_ref") == procedure
                and step.get("preconditions")
                == PROCEDURE_LIBRARY.get(procedure, {}).get("preconditions")
            )
            trace.append(mode.value)
            if not unchanged:
                transition("divergence")
                method = "holo_sandbox"
                job = out / "sandbox_jobs" / f"{step_id}.json"
                job.parent.mkdir(parents=True, exist_ok=True)
                job.write_text(
                    json.dumps(
                        {
                            "lesson_id": lesson["lesson_id"],
                            "step": step,
                            "fixture": str(checkpoint),
                            "blender_version": version,
                        },
                        indent=2,
                    )
                )
                evidence["sandbox_job"] = str(job.relative_to(out))
            elif (
                old.get("hashes") == hashes
                and old.get("target_signature") == target
                and old.get("status") == "proven"
                and old.get("selected_procedure_hash")
                == digest(PROCEDURE_LIBRARY.get(old.get("selected_procedure", procedure)))
                and output.exists()
                and old.get("checkpoint_sha256") == hashlib.sha256(output.read_bytes()).hexdigest()
            ):
                mode = Mode.REPLAY
                trace.append(mode.value)
                evidence.update(old)
                evidence["mode_trace"] = trace
                transition("success")
                status = "proven"
            else:
                try:
                    attempt = await sandbox.run_step(checkpoint, procedure, check, output)
                    evidence["attempts"] = [attempt]
                    if attempt["check_result"] != "pass":
                        transition("divergence")
                        transition("stuck")
                        docs = await search(f"Blender {version} {step['instruction']}")
                        evidence["sources"] = docs
                        candidate = await reselect(step, docs) if reselect else None
                        if candidate is not None:
                            if candidate not in PROCEDURE_LIBRARY:
                                raise ValueError("Procédure alternative non autorisée")
                            transition("candidate")
                            attempt = await sandbox.run_step(checkpoint, candidate, check, output)
                            evidence["attempts"].append(attempt)
                            evidence["selected_procedure"] = candidate
                    if attempt["check_result"] == "pass":
                        transition("success")
                        status = "proven"
                    else:
                        status = "failed"
                except (TimeoutError, RuntimeError, ValueError, OSError, *HTTP_ERRORS) as exc:
                    evidence["error"] = str(exc)
                    status = "failed"
        evidence["status"] = status
        evidence["method"] = method
        evidence["selected_procedure_hash"] = digest(
            PROCEDURE_LIBRARY.get(evidence.get("selected_procedure", procedure))
        )
        if status == "proven":
            evidence["checkpoint_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
            checkpoint = output
            if index + 1 < len(result["steps"]):
                transition("next_execute")
        else:
            blocked = True
        evidence_path.write_text(json.dumps(evidence, indent=2))
        step["proof"] = {
            "status": status,
            "method": method,
            "evidence_ref": f"proof/{step_id}.json",
            "ui_path_verified": False,
        }
        manifest.append({"step_id": step_id, **step["proof"]})
    statuses = [entry["status"] for entry in manifest]
    result["status"] = (
        "proven"
        if statuses and all(s == "proven" for s in statuses)
        else "failed"
        if "failed" in statuses
        else "pending"
    )
    result["proof"] = {
        "method": "per_step",
        "evidence_ref": "proof/manifest.json",
        "ui_path_verified": False,
    }
    (proof_dir / "manifest.json").write_text(
        json.dumps(
            {
                "lesson_id": lesson["lesson_id"],
                "blender_version": version,
                "status": result["status"],
                "steps": manifest,
            },
            indent=2,
        )
    )
    (out / "lesson.json").write_text(json.dumps(result, indent=2))
    return result
