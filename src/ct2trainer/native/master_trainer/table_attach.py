"""Pure per-table process-binding layer for the Master Trainer (MT-28).

MT-28 (0.37): the Master remembers, per table, which process the user
explicitly attached it to - the "merkt sich das einmal eingestellte"
complement to the MT-11 process picker.  MT-11 persists the attach
*mode* (auto / ask), and the picker's chosen PID is honoured for the
lifetime of the session only; a restart loses the choice and the user
must re-pick.  MT-28 persists the choice against the table so the next
load re-uses it.

The persisted ``table-attach.json`` document (schema 1, under the state
home) is keyed by the table **content sha256** - the same identity the
MT-24 analysis and the MT-27 notes documents use - so a binding
survives a rename within a root and follows a content-identical file to
another root.  A table whose index entry has no content sha (unreadable,
never scanned) cannot carry a binding: the store simply does not persist
one (documented, never a crash).

Each entry is ``{"process", "pid", "updated_at"}``: the bound process
name (the snapshot's original spelling, case-insensitive on match) and
the exact PID the user picked.  The PID is a hint, not a promise: it
changes across target restarts, so the lookup only honours it while it
is one of the live candidates (see :func:`binding_target`); otherwise
the ordinary attach decision applies and the picker re-opens.

This module is the pure decision + document layer:

- ``binding_entry`` builds one persisted entry (strict key set);
- the persisted document carries one entry per bound table with the
  strict key-set / field validation of the master-state discipline
  (an unknown field is a named refusal, never a silent drop);
- ``evict_oldest`` bounds the document at ``ATTACH_ENTRIES_LIMIT``
  entries (oldest by ``updated_at``; ties by sha256 - deterministic);
- ``AttachStore`` is the small persistent cache under the state home;
- ``binding_target`` maps ``(binding, live candidates)`` to the
  candidate to honour (or None - the documented fallback);
- ``details_attach_lines`` renders the MT-22 details-window row.

No index mutation, no table-file access, no OS access in this module -
the document I/O goes through the pure byte functions plus the small
:class:`AttachStore`; every decision is testable headless.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ATTACH_DOC_NAME = "table-attach.json"
ATTACH_SCHEMA = 1

# The persisted document is bounded: one entry per table content sha,
# oldest evicted first, so a folder churn cannot grow it without bound
# (the state home stays small and readable).
ATTACH_ENTRIES_LIMIT = 1024

# The bound process name is bounded (displayable in the picker and the
# details window; the snapshot spelling is kept, at most this long).
PROCESS_NAME_MAX = 128

_ENTRY_KEYS = ("process", "pid", "updated_at")

_TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


class AttachRefusal(ValueError):
    """A stored table-attach document (or entry) that is refused.

    Carries the displayable refusal reasons; the store treats a refused
    document as absent (documented, never silent - the binding simply
    re-enters through the next explicit pick).
    """

    def __init__(self, reasons: list[str]):
        super().__init__("; ".join(reasons))
        self.reasons = tuple(reasons)


def utc_now() -> str:
    """The persisted UTC timestamp format (the state-home style)."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _timestamp_ok(value) -> bool:
    """True for the persisted ``updated_at`` timestamp format."""
    return (isinstance(value, str) and len(value) == 20
            and _TIMESTAMP_RE.fullmatch(value) is not None)


def sha256_key_ok(value) -> bool:
    """True for one table-content sha256 key (64 lowercase hex)."""
    return (isinstance(value, str) and len(value) == 64
            and all(c in "0123456789abcdef" for c in value))


# ---------------------------------------------------------------------
# entry builders
# ---------------------------------------------------------------------

def binding_entry(process_name: str, pid: int, now: str) -> dict:
    """The persisted entry for one table's explicit process choice.

    ``process_name`` is the bound process name (non-empty, at most
    :data:`PROCESS_NAME_MAX` characters after stripping); ``pid`` is
    the exact chosen PID (a positive int - a ``bool`` or any
    non-integer is refused).  Out-of-bounds values are a named refusal
    (fail-closed - the store never persists what the validator
    refuses).
    """
    if not isinstance(process_name, str) or not process_name.strip():
        raise AttachRefusal([
            "process name is empty or not a string"])
    name = process_name.strip()
    if len(name) > PROCESS_NAME_MAX:
        raise AttachRefusal([
            "process name exceeds " + str(PROCESS_NAME_MAX)
            + " characters"])
    if type(pid) is not int:
        raise AttachRefusal(["pid is not an integer"])
    if pid <= 0:
        raise AttachRefusal(["pid must be positive"])
    return {"process": name, "pid": pid, "updated_at": now}


# ---------------------------------------------------------------------
# document validation
# ---------------------------------------------------------------------

def _validate_entry(sha: str, entry) -> None:
    if not isinstance(entry, dict):
        raise AttachRefusal(["attach entry is not an object"])
    if set(entry) != set(_ENTRY_KEYS):
        raise AttachRefusal([
            "attach entry " + sha[:12] + ".. has unknown fields"])
    process = entry["process"]
    if (not isinstance(process, str) or not process.strip()
            or len(process) > PROCESS_NAME_MAX):
        raise AttachRefusal([
            "attach entry " + sha[:12]
            + ".. has an invalid process name (empty, not a string, or "
            "over " + str(PROCESS_NAME_MAX) + " characters)"])
    if type(entry["pid"]) is not int or entry["pid"] <= 0:
        raise AttachRefusal([
            "attach entry " + sha[:12] + ".. has an invalid pid"])
    if not _timestamp_ok(entry.get("updated_at")):
        raise AttachRefusal([
            "attach entry " + sha[:12] + ".. has an invalid updated_at"])


def _validate_attach_dict(payload) -> None:
    if (not isinstance(payload, dict)
            or set(payload) != {"schema", "tables"}):
        raise AttachRefusal(["table-attach document fields mismatch"])
    if payload["schema"] != ATTACH_SCHEMA:
        raise AttachRefusal([
            "unsupported table-attach schema "
            + repr(payload["schema"])])
    tables = payload["tables"]
    if not isinstance(tables, dict):
        raise AttachRefusal(["table-attach tables are not an object"])
    if len(tables) > ATTACH_ENTRIES_LIMIT:
        raise AttachRefusal([
            "table-attach exceeds the " + str(ATTACH_ENTRIES_LIMIT)
            + "-entry limit"])
    for sha, entry in tables.items():
        if not sha256_key_ok(sha):
            raise AttachRefusal(["table-attach table key is not a sha256"])
        _validate_entry(sha, entry)


# ---------------------------------------------------------------------
# document bytes / load / save (the master-state envelope discipline)
# ---------------------------------------------------------------------

def attach_document_to_bytes(payload: dict) -> bytes:
    """Canonical, deterministic JSON bytes for one attach document.

    The envelope mirrors the master-state document:
    ``{"payload": …, "sha256": …}`` + trailing newline, the digest over
    the canonical payload serialization.
    """
    _validate_attach_dict(payload)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           allow_nan=False, ensure_ascii=True).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    return json.dumps({"payload": payload, "sha256": digest},
                      sort_keys=True, separators=(",", ":"),
                      allow_nan=False, ensure_ascii=True).encode("utf-8") \
        + b"\n"


def attach_document_from_bytes(raw: bytes) -> dict:
    """Parse one attach document; refusal raises AttachRefusal."""
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise AttachRefusal(
            ["table-attach document is not valid JSON"]) from None
    if (not isinstance(document, dict)
            or set(document) != {"payload", "sha256"}):
        raise AttachRefusal(["table-attach document fields mismatch"])
    payload = document["payload"]
    if not isinstance(payload, dict):
        raise AttachRefusal(["table-attach payload is not an object"])
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           allow_nan=False, ensure_ascii=True).encode("utf-8")
    if hashlib.sha256(canonical).hexdigest() != document.get("sha256"):
        raise AttachRefusal(["table-attach checksum does not match"])
    _validate_attach_dict(payload)
    return payload


def load_attach_document(path) -> dict | None:
    """Load the stored document; absent file -> None, refusal -> None.

    The store treats a refused document as absent (documented, never a
    silent reset of the remembered choice).
    """
    path = Path(path)
    if not path.is_file():
        return None
    try:
        return attach_document_from_bytes(path.read_bytes())
    except AttachRefusal:
        return None


def save_attach_document(payload: dict, path) -> None:
    """Persist one document; the state home directory is created if
    needed (the master-state save discipline)."""
    _validate_attach_dict(payload)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(attach_document_to_bytes(payload))


# ---------------------------------------------------------------------
# bounded store helpers
# ---------------------------------------------------------------------

def evict_oldest(tables: dict,
                 limit: int = ATTACH_ENTRIES_LIMIT) -> dict:
    """Drop the oldest entries until the mapping fits the limit.

    Oldest by ``updated_at`` (string order = time order for the fixed
    timestamp format), ties by the sha256 key (deterministic).  The
    mapping is mutated in place and returned.
    """
    while len(tables) > limit:
        oldest_key = min(tables,
                         key=lambda k: (tables[k].get("updated_at") or "",
                                        k))
        del tables[oldest_key]
    return tables


class AttachStore:
    """The persistent per-sha process-binding cache under the state
    home.

    One document (``table-attach.json``) next to the master-state
    document; an absent or refused document means the documented empty
    state (no remembered choice).
    """

    def __init__(self, state_home: str | Path):
        self.state_home = str(Path(state_home))
        self.path = Path(self.state_home) / ATTACH_DOC_NAME

    def document(self) -> dict:
        """The current document (absent / refused -> the empty one)."""
        payload = load_attach_document(self.path)
        if payload is None:
            return {"schema": ATTACH_SCHEMA, "tables": {}}
        return payload

    def get(self, sha256: str):
        """The persisted entry for one table content sha (or None)."""
        return self.document()["tables"].get(sha256)

    def has(self, sha256: str) -> bool:
        return self.get(sha256) is not None

    def set_binding(self, sha256: str, process_name: str, pid: int) -> None:
        """Insert/replace one table's process choice, evict over the
        limit, save.

        A malformed key or an out-of-bounds process name / PID is a
        named refusal (fail-closed - the store never persists what the
        validator refuses; the picker's choice simply is not
        remembered).
        """
        if not sha256_key_ok(sha256):
            raise AttachRefusal(["attach save needs a sha256 key"])
        entry = binding_entry(process_name, pid, utc_now())
        payload = self.document()
        payload["tables"][sha256] = entry
        evict_oldest(payload["tables"])
        save_attach_document(payload, self.path)

    def clear_binding(self, sha256: str) -> bool:
        """Drop one table's binding entry (persists the removal).

        ``False`` when the key is malformed or no entry exists
        (documented, never a silent document reset).
        """
        if not sha256_key_ok(sha256):
            return False
        payload = self.document()
        if sha256 not in payload["tables"]:
            return False
        del payload["tables"][sha256]
        save_attach_document(payload, self.path)
        return True

    def clear(self) -> None:
        """Reset the document to the empty state (persists the reset)."""
        save_attach_document({"schema": ATTACH_SCHEMA, "tables": {}},
                             self.path)


# ---------------------------------------------------------------------
# decision + display helpers
# ---------------------------------------------------------------------

def binding_target(binding, candidates) -> "ProcessSnapshotEntry | None":
    """The candidate a persisted binding honours, or None.

    ``binding`` is one persisted entry (``{"process", "pid",
    "updated_at"}``), or None while the table carries no remembered
    choice.  ``candidates`` are the live
    :class:`process_watch.ProcessSnapshotEntry` rows for the table's
    bound names.  The binding honours its stored PID only while that
    PID is one of the live candidates whose name still matches the
    bound process (case-insensitive, the same rule the picker and the
    memory factory use); a stale or foreign PID yields None, so the
    ordinary attach decision applies (the picker re-opens in ``ask``
    mode, the documented smallest-PID rule in ``auto``).
    """
    if binding is None or not candidates:
        return None
    from .process_watch import names_match
    pid = binding.get("pid")
    process = binding.get("process")
    if type(pid) is not int or not isinstance(process, str):
        return None
    for cand in candidates:
        if cand.pid == pid and names_match(cand.name, process):
            return cand
    return None


def details_attach_lines(binding) -> list:
    """Ordered ``(label, value)`` rows for the details window.

    ``binding`` is the persisted process-binding entry for the table's
    content sha (or None while the table carries no remembered choice).
    A bound entry shows the remembered process + PID; None adds the
    single "none" line (the window then shows the table has no
    remembered process choice yet).
    """
    if binding is None:
        return [("Remembered process", "none")]
    return [("Remembered process",
             str(binding.get("process")) + " (PID "
             + str(binding.get("pid")) + ")")]
