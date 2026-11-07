"""Catalogue local : aucune promotion ni recalcul de preuve."""

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from jsonschema import Draft202012Validator, ValidationError

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = Draft202012Validator(json.loads((ROOT / "contracts/lesson.schema.json").read_text()))


class AgentError(ValueError):
    pass


class Catalog:
    def __init__(self, root: Path | None = None, state: Path | None = None) -> None:
        self.root = (root or Path(os.getenv("AGENT_LESSONS_DIR", ROOT / "lessons"))).resolve()
        self.state = state or Path(
            os.getenv("AGENT_STATE_DIR", Path.home() / ".local/state/hcompany-hack/agent")
        )

    def tickets(self) -> list[dict[str, Any]]:
        return [json.loads(p.read_text()) for p in self.state.glob("*.json")]

    def scan(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        accepted, rejected = [], []
        quarantine = {
            (t["lesson_id"], t["revision"]) for t in self.tickets() if t["status"] == "confirmed"
        }
        for path in sorted(self.root.glob("**/lesson.json")):
            identity: dict[str, Any] = {"entry": str(path.relative_to(self.root))}
            try:
                if not path.resolve().is_relative_to(self.root):
                    raise AgentError("outside_root")
                raw = path.read_bytes()
                lesson = json.loads(raw)
                VALIDATOR.validate(lesson)
                identity.update(
                    {k: lesson[k] for k in ("lesson_id", "revision", "blender_version")}
                )
                if lesson["status"] != "proven" or any(
                    s["proof"]["status"] != "proven" for s in lesson["steps"]
                ):
                    raise AgentError("not_proven")
                if (lesson["lesson_id"], lesson["revision"]) in quarantine:
                    raise AgentError("quarantined")
                proofs = {}
                for proof in [lesson["proof"], *(s["proof"] for s in lesson["steps"])]:
                    evidence = (path.parent / proof["evidence_ref"]).resolve()
                    if not evidence.is_relative_to(path.parent.resolve()):
                        raise AgentError("outside_root")
                    content = evidence.read_bytes()
                    try:
                        proofs[proof["evidence_ref"]] = json.loads(content)
                    except (ValueError, UnicodeDecodeError):
                        proofs[proof["evidence_ref"]] = {
                            "encoding": "base64",
                            "content": base64.b64encode(content).decode(),
                        }
                accepted.append(
                    {
                        "lesson": lesson,
                        "proof_manifest": proofs,
                        "fingerprint": hashlib.sha256(raw).hexdigest(),
                    }
                )
            except AgentError as error:
                rejected.append({**identity, "reason": str(error)})
            except (OSError, ValueError, ValidationError):
                # Schema diagnostics can contain untrusted paths and values.
                rejected.append({**identity, "reason": "invalid_schema_or_evidence"})
                continue
        keys = [
            (r["lesson"]["lesson_id"], r["lesson"]["revision"], r["lesson"]["blender_version"])
            for r in accepted
        ]
        unique = []
        for record, key in zip(accepted, keys, strict=True):
            if keys.count(key) != 1:
                rejected.append(
                    {"lesson_id": key[0], "revision": key[1], "reason": "duplicate_revision"}
                )
            else:
                unique.append(record)
        return unique, rejected

    def get(self, lesson_id: str, revision: int, blender_version: str) -> dict[str, Any]:
        for record in self.scan()[0]:
            lesson = record["lesson"]
            if (lesson["lesson_id"], lesson["revision"], lesson["blender_version"]) == (
                lesson_id,
                revision,
                blender_version,
            ):
                return record
        raise AgentError("procedure_unavailable: absent, rejected or version mismatch")

    def report(
        self, lesson_id: str, revision: int, step_id: str, description: str, evidence_ref: str
    ) -> dict[str, str]:
        if not all((lesson_id.strip(), step_id.strip(), description.strip(), evidence_ref.strip())):
            raise AgentError("invalid_ticket")
        ticket_id = uuid4().hex
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        ticket = dict(
            ticket_id=ticket_id,
            lesson_id=lesson_id,
            revision=revision,
            step_id=step_id,
            description=description,
            evidence_ref=evidence_ref,
            status="pending",
        )
        (self.state / f"{ticket_id}.json").write_text(json.dumps(ticket, ensure_ascii=False))
        return {"ticket_id": ticket_id}

    def triage(self, ticket_id: str, confirmed: bool) -> None:
        if len(ticket_id) != 32 or any(c not in "0123456789abcdef" for c in ticket_id):
            raise AgentError("invalid_ticket_id")
        path = self.state / f"{ticket_id}.json"
        ticket = json.loads(path.read_text())
        ticket["status"] = "confirmed" if confirmed else "dismissed"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(ticket, ensure_ascii=False))
        temporary.replace(path)
