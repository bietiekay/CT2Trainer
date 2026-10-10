"""Read-only GUI assessment for Frozen recovery, mapped 1:1 to the CLI ops.

Wraps ``ct2trainer.native.recovery.assess_recovery`` (the exact read-only
assessment the ``assess-recovery`` CLI command runs) and adds per-artifact
classification for the recovery GUI: stale (owner/target identity proven
dead, reused, or absent), live, legacy, corrupted, saved-state, journal, and
unknown-artifact. The ``recover`` CLI operation
(``recovery_operation.recover_assessment``) stays the only release path and
is reported as allowed only for a fresh eligible-read-only assessment.

Contracts:
- Pure read: no file in the state or shared-lock scope is created, renamed,
  or deleted by this module; stale proofs always re-run the full assessment.
- Stale evidence is re-proven per artifact from exact (pid, created)
  identities with the injected process probe; a missing creation time, an
  alive owner/target, or an unknown query is a hard block.
- Unsafe, live, legacy, and corrupted artifacts never become recovery
  candidates and are reported with the concrete reason.
- The output is a raw, JSON-serializable assessment document for the GUI.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from pathlib import Path
import time

from .recovery import (
    ProcessIdentity,
    ProcessObservation,
    WAIT_OBJECT_0,
    assess_recovery,
)


ENGINE = "ct2trainer-recovery-assessment"
SCHEMA = 1
_HEX64 = re.compile(r"[0-9a-f]{64}")
_HEX32 = re.compile(r"[0-9a-f]{32}")


class RecoveryAssessmentError(RuntimeError):
    """Invalid assessment request or an unsupported artifact layout."""


@dataclass(frozen=True)
class ArtifactAssessment:
    path: str
    kind: str          # state-file | shared | journal
    classification: str  # stale | live | legacy | corrupted | saved-state | journal | unknown-artifact
    detail: str
    recoverable: bool
    owner: tuple[int, int | None] | None = None
    target: tuple[int, int | None] | None = None
    process_status: str | None = None


def _strict_document(raw: bytes) -> dict | None:
    """Parse evidence JSON; duplicate keys and nonfinite values fail closed."""

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    try:
        value = json.loads(raw, object_pairs_hook=pairs,
                           parse_constant=lambda item: (_ for _ in ()).throw(ValueError("nonfinite")))
    except (ValueError, UnicodeError, RecursionError):
        return None
    return value if isinstance(value, dict) else None


def _owner_identity(document: dict) -> tuple[tuple[int, int | None] | None, str]:
    """Extract the owner identity and the lock schema class from a lock document."""
    if not isinstance(document.get("owner_pid"), int) or not isinstance(document.get("nonce"), str) \
            or not _HEX32.fullmatch(str(document.get("nonce", ""))):
        return None, "corrupted"
    created = document.get("owner_created")
    if created is None:
        return None, "legacy"
    if not isinstance(created, int) or not 0 < created <= 0xFFFFFFFFFFFFFFFF:
        return None, "corrupted"
    return (document["owner_pid"], created), "schema-2"


def _target_identity(document: dict) -> tuple[int, int | None] | None:
    value = document.get("target")
    if isinstance(value, list) and len(value) == 2:
        pid, created = value[0], value[1]
        if isinstance(pid, int) and 0 < pid <= 0xFFFFFFFF and (
                created is None or (isinstance(created, int) and 0 < created <= 0xFFFFFFFFFFFFFFFF)):
            return (pid, created if isinstance(created, int) else None)
        return None
    pid = document.get("target_pid")
    created = document.get("target_created")
    if isinstance(pid, int) and 0 < pid <= 0xFFFFFFFF and (
            created is None or (isinstance(created, int) and 0 < created <= 0xFFFFFFFFFFFFFFFF)):
        return (pid, created if isinstance(created, int) else None)
    return None


def _status_for_identity(processes: tuple, identity: tuple[int, int | None] | None) -> str | None:
    if identity is None:
        return None
    for evidence in processes:
        if evidence.identity == ProcessIdentity(*identity):
            statuses = {item.status for item in evidence.observations}
            if not evidence.proven_dead:
                return next(iter(statuses), "unknown")
            return "dead" if "dead" in statuses else next(iter(statuses))
    return "unknown"


_SHARED_CLAIM_NAME = re.compile(r"\d+-\d+\.json")


def _lock_owner(document: dict) -> tuple:
    """Owner evidence from lock documents; session/shared claims nest it in 'owner'."""
    nested = document.get("owner")
    if isinstance(nested, dict):
        return _owner_identity(nested)
    return _owner_identity(document)


def _classify(path: Path, raw: bytes, kind: str, assessment) -> ArtifactAssessment:
    """Classify one artifact read-only; the assessment is the authority for proof."""
    name = path.name

    if kind == "state-file":
        if name == "state.json":
            document = _strict_document(raw)
            if document is None:
                return ArtifactAssessment(str(path), kind, "corrupted", "state.json is not valid JSON", False)
            payload = document.get("payload")
            checksum = document.get("sha256")
            if not isinstance(payload, dict) or not isinstance(checksum, str):
                return ArtifactAssessment(str(path), kind, "corrupted", "state.json lacks a payload/checksum envelope", False)
            canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
            if checksum != hashlib.sha256(canonical).hexdigest():
                return ArtifactAssessment(str(path), kind, "corrupted", "state.json checksum is invalid", False)
            return ArtifactAssessment(str(path), kind, "saved-state",
                                      "Committed state; preserved by every recovery path, never released",
                                      False)
        if name == "state.json.tmp":
            return ArtifactAssessment(str(path), kind, "corrupted",
                                      "Incomplete state snapshot from an interrupted save", False)
        if name not in {"state.lock", "session.json"}:
            return ArtifactAssessment(str(path), kind, "unknown-artifact",
                                      "File is not part of the recovery evidence set", False)
    elif kind == "shared":
        if not _SHARED_CLAIM_NAME.fullmatch(name):
            return ArtifactAssessment(str(path), kind, "unknown-artifact",
                                      "Shared lock file does not name an exact target identity", False)
    elif kind == "journal":
        document = _strict_document(raw)
        if document is None:
            return ArtifactAssessment(str(path), kind, "corrupted", "Journal is not valid JSON", False)
        engine = document.get("engine")
        if engine not in {"ct2trainer-hooks", "ct2trainer-lua"}:
            return ArtifactAssessment(str(path), kind, "corrupted", "Journal has an unknown engine or schema", False)
        target = _target_identity(document)
        target_status = _status_for_identity(assessment.processes, target)
        if target_status in {"alive", "unknown"}:
            label = "live" if target_status == "alive" else "unsafe"
            return ArtifactAssessment(str(path), kind, label,
                                      f"Journal target is {target_status}; release stays blocked",
                                      False, target=target, process_status=target_status)
        return ArtifactAssessment(str(path), kind, "journal",
                                  f"{engine} receipt bound to a dead/reused/absent target",
                                  False, target=target, process_status=target_status)
    else:
        return ArtifactAssessment(str(path), kind, "unknown-artifact",
                                  "File is not part of the recovery evidence set", False)

    document = _strict_document(raw)
    if document is None:
        return ArtifactAssessment(str(path), kind, "corrupted", "Artifact is not valid JSON", False)

    owner, lock_class = _lock_owner(document)
    if lock_class == "corrupted":
        return ArtifactAssessment(str(path), kind, "corrupted", "Owner identity is missing or invalid", False)
    target = _target_identity(document)
    if owner is None:
        owner_source = document.get("owner") if isinstance(document.get("owner"), dict) else document
        return ArtifactAssessment(str(path), kind, "legacy",
                                  "Owner lock predates the creation-time schema and cannot be proven dead",
                                  False, owner=(owner_source.get("owner_pid"), None))
    owner_status = _status_for_identity(assessment.processes, owner)
    if owner_status in {"alive", "unknown"}:
        label = "live" if owner_status == "alive" else "unsafe"
        return ArtifactAssessment(str(path), kind, label,
                                  f"Owner {owner[0]}/{owner[1]} is {owner_status}; lock stays in place",
                                  False, owner=owner, target=target, process_status=owner_status)
    if target is not None:
        target_status = _status_for_identity(assessment.processes, target)
        if target_status in {"alive", "unknown"}:
            label = "live" if target_status == "alive" else "unsafe"
            return ArtifactAssessment(str(path), kind, label,
                                      f"Target {target[0]}/{target[1]} is {target_status}; nothing may be released",
                                      False, owner=owner, target=target, process_status=target_status)
    detail = "Exact owner and target identity proven dead, reused, or absent"
    return ArtifactAssessment(str(path), kind, "stale", detail, True,
                              owner=owner, target=target, process_status=owner_status)


@dataclass(frozen=True)
class RecoveryGuiAssessment:
    state_directory: str
    process_lock_directory: str
    status: str
    eligible: bool
    reasons: tuple[str, ...]
    artifacts: tuple[ArtifactAssessment, ...]
    candidate_paths: tuple[str, ...]
    processes: tuple[dict, ...]
    inventory_sha256: str
    operation: dict

    @property
    def recovery_allowed(self) -> bool:
        return self.eligible and self.status == "eligible-read-only"


def assess_for_gui(state_directory: str | Path,
                   process_lock_directory: str | Path | None = None, *,
                   process_probe=None,
                   expected_trainer_id: str | None = None,
                   expected_table_sha256: str | None = None) -> RecoveryGuiAssessment:
    """Run the authoritative read-only assessment and classify every artifact.

    The result is safe to hand to the GUI as raw JSON. It grants no release
    authority: recovery must start from a fresh assessment and re-prove all
    process identities before releasing anything.
    """
    deadline = time.monotonic() + 15
    assessment = assess_recovery(state_directory, process_lock_directory,
                                 process_probe=process_probe,
                                 expected_trainer_id=expected_trainer_id,
                                 expected_table_sha256=expected_table_sha256)
    artifacts = []
    for snapshot in assessment.files:
        if time.monotonic() > deadline:
            raise RecoveryAssessmentError("Reassessment exceeded its elapsed-time bound")
        try:
            with snapshot.path.open("rb") as handle:
                raw = handle.read()
        except OSError:
            artifacts.append(ArtifactAssessment(str(snapshot.path), snapshot.kind, "corrupted",
                                                "Artifact could not be re-read", False))
            continue
        if snapshot.sha256 != hashlib.sha256(raw).hexdigest():
            raise RecoveryAssessmentError("Recovery file changed between assessment and classification: "
                                          + snapshot.path.name)
        artifacts.append(_classify(snapshot.path, raw, snapshot.kind, assessment))
    processes = tuple({
        "pid": evidence.identity.pid,
        "created": evidence.identity.created,
        "roles": list(evidence.roles),
        "proven_dead": evidence.proven_dead,
        "observations": [{"status": item.status, "detail": item.detail} for item in evidence.observations],
    } for evidence in assessment.processes)
    allowed = assessment.eligible and assessment.status == "eligible-read-only"
    operation = {
        "assess_command": "assess-recovery",
        "recover_command": "recover",
        "recover_operation": "recovery_operation.recover_assessment",
        "recover_allowed": allowed,
        "requires": ["fresh assessment", "read-only death proof for every owner and target",
                      "archive directory outside the state and shared-lock scopes"],
        "blocked_reasons": list(assessment.reasons) if not allowed else [],
    }
    return RecoveryGuiAssessment(str(Path(state_directory).resolve()),
                                 str(assessment.process_lock_directory),
                                 assessment.status, assessment.eligible,
                                 tuple(assessment.reasons), tuple(artifacts),
                                 tuple(str(item) for item in assessment.candidate_paths),
                                 processes, assessment.inventory_sha256, operation)


def to_json_document(result: RecoveryGuiAssessment) -> dict:
    """Raw, deterministic, JSON-serializable assessment for the GUI."""
    return {
        "schema": SCHEMA,
        "engine": ENGINE,
        "state_directory": result.state_directory,
        "process_lock_directory": result.process_lock_directory,
        "status": result.status,
        "eligible": result.eligible,
        "reasons": list(result.reasons),
        "artifacts": [{
            "path": item.path,
            "kind": item.kind,
            "classification": item.classification,
            "detail": item.detail,
            "recoverable": item.recoverable,
            "owner": list(item.owner) if item.owner else None,
            "target": list(item.target) if item.target else None,
            "process_status": item.process_status,
        } for item in result.artifacts],
        "candidate_paths": list(result.candidate_paths),
        "processes": list(result.processes),
        "inventory_sha256": result.inventory_sha256,
        "operation": dict(result.operation),
    }
