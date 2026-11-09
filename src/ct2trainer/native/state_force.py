"""Forced state reclaim for the ``--force`` startup path (0.38).

Documented dead end (0.22/0.30/0.31 SteamOS field logs, Indiana Jones
and the Great Circle): an interrupted recovery transaction leaves
``recovery.lock`` behind, and once the recovery-eligibility assessment
can no longer classify the state (the recorded target process is
neither proven dead nor target-role-only), the conservative refusal
("A recovery transaction owns this state") fires on every start and
the trainer never starts again - on SteamOS the user cannot easily
delete the state folder, so the trainer stays unusable for hours.

``force_reclaim`` is the ``--force`` escape hatch.  It skips the
recovery-eligibility assessment entirely and applies one hard
data-safety boundary: a *proven-alive* trainer-side owner (the state
lock owner, the recovery fence owner, a session owner, or the owner
recorded in a matching shared process claim) is never displaced -
even under ``--force``.  Every other case - a proven-dead owner, or an
unprovable owner (transient probe failure, legacy lock without a
creation identity, unparseable document) - quarantines the blocking
artifacts into a timestamped archive under the state home and writes
a complete evidence document.  The user's saved state (``state.json``,
the saved wishes) is always preserved, so the saved toggles survive
the forced reclaim.

This module is pure decision plus bounded file moves: it never
touches target memory, never attaches, and never executes table
content.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .recovery import ProcessIdentity, ProcessObservation, WindowsProcessProbe

_EVIDENCE_SCHEMA = "ct2trainer-forced-reclaim/v1"


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_bytes())
    except (OSError, ValueError):
        return None


def _owner_from_document(document: Any) -> ProcessIdentity | None:
    """Extract the recorded trainer-side owner identity from a document.

    Accepts the state-lock shape (``{"owner_pid", "nonce"[, "schema",
    "owner_created"]}``), the recovery fence shape (the same owner
    fields), and the session / shared-claim shape (``{"schema",
    "owner": {...}, "trainer_id", ...}``).  Anything else yields
    ``None``: the artifact is still quarantined under the documented
    ``--force`` trade-off and is recorded as unprovable in the
    evidence.
    """
    if isinstance(document, dict) and isinstance(document.get("owner"), dict):
        document = document["owner"]
    if not isinstance(document, dict):
        return None
    pid = document.get("owner_pid")
    created = document.get("owner_created")
    if type(pid) is not int or not 0 < pid <= 0xFFFFFFFF:
        return None
    if created is not None and (
            type(created) is not int or not 0 < created <= 0xFFFFFFFFFFFFFFFF):
        return None
    try:
        return ProcessIdentity(pid, created)
    except ValueError:
        return None


def _archive_name(source: Path, state_dir: Path, shared_dir: Path) -> Path:
    """Archive layout: state files at the root, journals under ``hooks``,
    shared process claims under ``shared`` (their original names kept)."""
    if source.parent == shared_dir:
        return Path("shared") / source.name
    try:
        return source.parent.relative_to(state_dir) / source.name
    except ValueError:
        return source.name


def force_reclaim(state_dir, process_lock_dir, plan, process_probe=None,
                  retry_delay: float = 1.0) -> tuple[bool, str]:
    """Reclaim a held state directory for a forced (``--force``) start.

    Returns ``(completed, detail)``.  ``completed=True`` means the
    blocking artifacts were quarantined into the timestamped archive
    (or none were present) and the startup may be retried;
    ``completed=False`` is a named refusal and the state was left
    untouched.

    The one hard boundary that stays under force: every recorded
    trainer-side owner is probed (one observation, one retry on a
    transient "unknown"); a proven-alive owner refuses the reclaim.
    Proven-dead or unprovable owners are quarantined - the documented
    ``--force`` trade-off, recorded per owner in the evidence document.
    The saved ``state.json`` is always preserved.
    """
    state_dir = Path(state_dir)
    shared_dir = Path(process_lock_dir)
    trainer_id = plan["trainer_id"]
    table_sha256 = plan["table_sha256"]
    probe = process_probe
    if probe is None:
        if sys.platform != "win32":
            return (False, "exact process proof requires Windows; "
                           "--force refuses to reclaim the state without a probe")
        probe = WindowsProcessProbe()

    # ---- 1. collect the recorded trainer-side owner documents ------
    owner_documents: list[tuple[str, Path, Any]] = []
    for name, label in (("state.lock", "state lock"),
                        ("recovery.lock", "recovery fence"),
                        ("session.json", "session record")):
        path = state_dir / name
        if path.is_file():
            owner_documents.append((label, path, _load_json(path)))
    shared_claims: list[Path] = []
    if shared_dir.is_dir():
        for claim in sorted(shared_dir.glob("*.json")):
            document = _load_json(claim)
            if isinstance(document, dict) and document.get("trainer_id") == trainer_id:
                shared_claims.append(claim)
                owner_documents.append(("shared process claim", claim, document))

    # ---- 2. probe the owners; a proven-alive one is the refusal ----
    observations: dict[tuple[int, int | None], ProcessObservation] = {}
    seen: set[tuple[int, int | None]] = set()
    for label, _path, document in owner_documents:
        identity = _owner_from_document(document)
        if identity is None:
            continue
        key = (identity.pid, identity.created)
        if key in seen:
            continue
        seen.add(key)
        observation = probe(identity)
        if not isinstance(observation, ProcessObservation):
            return (False, "the process probe returned an invalid observation "
                           "for PID " + str(identity.pid))
        if observation.status == "unknown":
            time.sleep(retry_delay)
            observation = probe(identity)
            if not isinstance(observation, ProcessObservation):
                return (False, "the process probe returned an invalid observation "
                               "for PID " + str(identity.pid))
        observations[key] = observation
        if observation.status == "alive":
            return (False, "the recorded state owner (PID " + str(identity.pid)
                           + ", " + label + ") is proven alive; "
                           "--force never displaces a live trainer session")

    owners_evidence = []
    for label, path, document in owner_documents:
        identity = _owner_from_document(document)
        if identity is None:
            owners_evidence.append({
                "artifact": label,
                "path": str(path),
                "owner_pid": None,
                "owner_created": None,
                "status": "unprovable",
                "detail": "no recorded owner identity (legacy or corrupt "
                           "document); quarantined under the forced trade-off",
            })
        else:
            observation = observations[(identity.pid, identity.created)]
            owners_evidence.append({
                "artifact": label,
                "path": str(path),
                "owner_pid": identity.pid,
                "owner_created": identity.created,
                "status": observation.status,
                "detail": observation.detail,
            })

    # ---- 3. inventory the blocking artifacts -----------------------
    blocking: list[Path] = []
    for name in ("state.json.tmp", "state.lock", "recovery.lock",
                 "session.json", "oneshot.json.tmp"):
        path = state_dir / name
        if path.is_file():
            blocking.append(path)
    hooks = state_dir / "hooks"
    if hooks.is_dir():
        for journal in sorted(hooks.glob("*.json")):
            blocking.append(journal)
    blocking.extend(shared_claims)

    if not blocking:
        return (True, "no blocking state artifacts present; nothing was moved")

    # ---- 4. quarantine into the timestamped archive ----------------
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = state_dir.parent / "forced-recovery" / (stamp + "-" + trainer_id)
    try:
        archive.mkdir(parents=True)
    except FileExistsError:
        return (False, "another forced reclaim already archives this state "
                       "(" + str(archive) + "); start again in a moment")
    except OSError as exc:
        return (False, "cannot create the reclaim archive: " + str(exc))

    moved: list[dict[str, Any]] = []
    for source in blocking:
        try:
            raw = source.read_bytes()
            target = archive / _archive_name(source, state_dir, shared_dir)
            target.parent.mkdir(parents=True, exist_ok=True)
            source.replace(target)
        except OSError as exc:
            return (False, "quarantine failed on " + source.name + ": " + str(exc))
        moved.append({"path": str(source), "archive": str(target),
                      "size": len(raw),
                      "sha256": hashlib.sha256(raw).hexdigest()})
    try:
        if hooks.is_dir() and not any(hooks.iterdir()):
            hooks.rmdir()
    except OSError:
        pass

    # ---- 5. evidence -------------------------------------------------
    evidence = {
        "schema": _EVIDENCE_SCHEMA,
        "ts": stamp,
        "trainer_id": trainer_id,
        "table_sha256": table_sha256,
        "state_dir": str(state_dir),
        "process_lock_dir": str(shared_dir),
        "owners": owners_evidence,
        "moved": moved,
        "preserved": ["state.json"] if (state_dir / "state.json").is_file() else [],
    }
    try:
        (archive / "force-reclaim.json").write_text(
            json.dumps(evidence, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8")
    except OSError:
        pass
    return (True, "forced reclaim quarantined " + str(len(moved))
                + " artifact(s) into " + str(archive)
                + "; the saved state was preserved")
