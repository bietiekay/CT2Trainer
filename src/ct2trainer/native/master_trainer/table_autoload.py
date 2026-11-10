"""Pure per-table auto-load policy layer for the Master Trainer (MT-29).

MT-29 (0.39): the Master Trainer's documented default is the
auto-load - a matched game process loads its bound table on its own
(MT-3).  The use case ("choose which table runs against which
process - remember the configuration") adds the other direction:
some tables should NEVER auto-load; the user loads them explicitly
(the double-click / Enter keyboard flow, the "Load this table" row
menu item, the "Load table" header picker - the MT-10 path, which is
never affected by the policy).

The persisted ``table-autoload.json`` document (schema 1, under the
state home) is keyed by the table **content sha256** - the same
identity the MT-24 analysis, the MT-27 notes and the MT-28 attach
documents use - so a policy survives a rename within a root and
follows a content-identical file to another root.  A table whose
index entry has no content sha (unreadable, never scanned) cannot
carry a policy: the store simply does not persist one (documented,
never a crash, the table auto-loads by the documented default).

Only the non-default policy is persisted: one entry per manual-only
table - ``{"policy", "updated_at"}`` with ``policy`` =
:data:`AUTOLOAD_MANUAL_ONLY`.  The absence of an entry (and a
refused document, treated as absent) is the documented default
:data:`AUTOLOAD_AUTO` - the same discipline as the MT-28 binding
document (no entry = no remembered choice).

This module is the pure decision + document layer:

- ``autoload_entry`` builds one persisted entry (strict key set);
- the persisted document carries one entry per manual-only table
  with the strict key-set / field validation of the master-state
  discipline (an unknown field is a named refusal, never a silent
  drop);
- ``evict_oldest`` bounds the document at ``AUTOLOAD_ENTRIES_LIMIT``
  entries (oldest by ``updated_at``; ties by sha256 - deterministic);
- ``AutoLoadStore`` is the small persistent cache under the state
  home; ``policy`` resolves the effective policy of one table
  (absent entry = :data:`AUTOLOAD_AUTO`);
- ``details_autoload_lines`` renders the MT-22 details-window row.

No index mutation, no table-file access, no OS access in this module
- the document I/O goes through the pure byte functions plus the
small :class:`AutoLoadStore`; every decision is testable headless.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

AUTOLOAD_DOC_NAME = "table-autoload.json"
AUTOLOAD_SCHEMA = 1

# The effective auto-load policies.  ``AUTOLOAD_AUTO`` is the
# documented default (no persisted entry); ``AUTOLOAD_MANUAL_ONLY``
# is the only persisted entry - the table is never auto-loaded, the
# user loads it explicitly (the MT-10 path, never affected by the
# policy).
AUTOLOAD_AUTO = "auto"
AUTOLOAD_MANUAL_ONLY = "manual-only"
AUTOLOAD_POLICIES = (AUTOLOAD_AUTO, AUTOLOAD_MANUAL_ONLY)

# The persisted document is bounded: one entry per manual-only table
# content sha, oldest evicted first, so a folder churn cannot grow
# it without bound (the state home stays small and readable).
AUTOLOAD_ENTRIES_LIMIT = 1024

_ENTRY_KEYS = ("policy", "updated_at")

_TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


class AutoLoadRefusal(ValueError):
    """A stored table-autoload document (or entry) that is refused.

    Carries the displayable refusal reasons; the store treats a
    refused document as absent (documented, never silent - the
    policies simply re-enter through the next toggle).
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

def autoload_entry(policy: str, now: str) -> dict:
    """The persisted entry for one manual-only table.

    ``policy`` must be one of :data:`AUTOLOAD_POLICIES` (the persisted
    document carries the ``AUTOLOAD_MANUAL_ONLY`` entry; an explicit
    ``AUTOLOAD_AUTO`` entry is format-legal but semantically the
    default - :meth:`AutoLoadStore.policy` resolves it to
    :data:`AUTOLOAD_AUTO` anyway, and the store never writes one).
    An out-of-bounds policy is a named refusal (fail-closed - the
    store never persists what the validator refuses).
    """
    if not isinstance(policy, str) or policy not in AUTOLOAD_POLICIES:
        raise AutoLoadRefusal([
            "policy is not one of " + ", ".join(AUTOLOAD_POLICIES)
            + " (got " + repr(policy)[:40] + ")"])
    return {"policy": policy, "updated_at": now}


# ---------------------------------------------------------------------
# document validation
# ---------------------------------------------------------------------

def _validate_entry(sha: str, entry) -> None:
    if not isinstance(entry, dict):
        raise AutoLoadRefusal(["autoload entry is not an object"])
    if set(entry) != set(_ENTRY_KEYS):
        raise AutoLoadRefusal([
            "autoload entry " + sha[:12] + ".. has unknown fields"])
    if (not isinstance(entry["policy"], str)
            or entry["policy"] not in AUTOLOAD_POLICIES):
        raise AutoLoadRefusal([
            "autoload entry " + sha[:12]
            + ".. has an invalid policy (not " + ", ".join(AUTOLOAD_POLICIES)
            + ")"])
    if not _timestamp_ok(entry.get("updated_at")):
        raise AutoLoadRefusal([
            "autoload entry " + sha[:12] + ".. has an invalid updated_at"])


def _validate_autoload_dict(payload) -> None:
    if (not isinstance(payload, dict)
            or set(payload) != {"schema", "tables"}):
        raise AutoLoadRefusal(["table-autoload document fields mismatch"])
    if payload["schema"] != AUTOLOAD_SCHEMA:
        raise AutoLoadRefusal([
            "unsupported table-autoload schema "
            + repr(payload["schema"])])
    tables = payload["tables"]
    if not isinstance(tables, dict):
        raise AutoLoadRefusal(["table-autoload tables are not an object"])
    if len(tables) > AUTOLOAD_ENTRIES_LIMIT:
        raise AutoLoadRefusal([
            "table-autoload exceeds the " + str(AUTOLOAD_ENTRIES_LIMIT)
            + "-entry limit"])
    for sha, entry in tables.items():
        if not sha256_key_ok(sha):
            raise AutoLoadRefusal(["table-autoload table key is not a sha256"])
        _validate_entry(sha, entry)


# ---------------------------------------------------------------------
# document bytes / load / save (the master-state envelope discipline)
# ---------------------------------------------------------------------

def autoload_document_to_bytes(payload: dict) -> bytes:
    """Canonical, deterministic JSON bytes for one autoload document.

    The envelope mirrors the master-state document:
    ``{"payload": …, "sha256": …}`` + trailing newline, the digest
    over the canonical payload serialization.
    """
    _validate_autoload_dict(payload)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           allow_nan=False, ensure_ascii=True).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    return json.dumps({"payload": payload, "sha256": digest},
                      sort_keys=True, separators=(",", ":"),
                      allow_nan=False, ensure_ascii=True).encode("utf-8") \
        + b"\n"


def autoload_document_from_bytes(raw: bytes) -> dict:
    """Parse one autoload document; refusal raises AutoLoadRefusal."""
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise AutoLoadRefusal(
            ["table-autoload document is not valid JSON"]) from None
    if (not isinstance(document, dict)
            or set(document) != {"payload", "sha256"}):
        raise AutoLoadRefusal(["table-autoload document fields mismatch"])
    payload = document["payload"]
    if not isinstance(payload, dict):
        raise AutoLoadRefusal(["table-autoload payload is not an object"])
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           allow_nan=False, ensure_ascii=True).encode("utf-8")
    if hashlib.sha256(canonical).hexdigest() != document.get("sha256"):
        raise AutoLoadRefusal(["table-autoload checksum does not match"])
    _validate_autoload_dict(payload)
    return payload


def load_autoload_document(path) -> dict | None:
    """Load the stored document; absent file -> None, refusal -> None.

    The store treats a refused document as absent (documented, never
    a silent reset of the waiting view).
    """
    path = Path(path)
    if not path.is_file():
        return None
    try:
        return autoload_document_from_bytes(path.read_bytes())
    except AutoLoadRefusal:
        return None


def save_autoload_document(payload: dict, path) -> None:
    """Persist one document; the state home directory is created if
    needed (the master-state save discipline)."""
    _validate_autoload_dict(payload)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(autoload_document_to_bytes(payload))


# ---------------------------------------------------------------------
# bounded store helpers
# ---------------------------------------------------------------------

def evict_oldest(tables: dict,
                 limit: int = AUTOLOAD_ENTRIES_LIMIT) -> dict:
    """Drop the oldest entries until the mapping fits the limit.

    Oldest by ``updated_at`` (string order = time order for the
    fixed timestamp format), ties by the sha256 key (deterministic).
    The mapping is mutated in place and returned.
    """
    while len(tables) > limit:
        oldest_key = min(tables,
                         key=lambda k: (tables[k].get("updated_at") or "",
                                        k))
        del tables[oldest_key]
    return tables


class AutoLoadStore:
    """The persistent per-sha auto-load policy cache under the state
    home.

    One document (``table-autoload.json``) next to the master-state
    document; an absent or refused document means the documented
    empty state (every table auto-loads).
    """

    def __init__(self, state_home: str | Path):
        self.state_home = str(Path(state_home))
        self.path = Path(self.state_home) / AUTOLOAD_DOC_NAME

    def document(self) -> dict:
        """The current document (absent / refused -> the empty one)."""
        payload = load_autoload_document(self.path)
        if payload is None:
            return {"schema": AUTOLOAD_SCHEMA, "tables": {}}
        return payload

    def get(self, sha256: str):
        """The persisted entry for one table content sha (or None)."""
        return self.document()["tables"].get(sha256)

    def has(self, sha256: str) -> bool:
        return self.get(sha256) is not None

    def policy(self, sha256: str) -> str:
        """The effective auto-load policy of one table.

        Absent entry (or a format-legal explicit ``auto`` entry) ->
        :data:`AUTOLOAD_AUTO`, the documented default; a persisted
        ``manual-only`` entry -> :data:`AUTOLOAD_MANUAL_ONLY`.
        """
        entry = self.get(sha256)
        if entry is None:
            return AUTOLOAD_AUTO
        if entry.get("policy") == AUTOLOAD_MANUAL_ONLY:
            return AUTOLOAD_MANUAL_ONLY
        return AUTOLOAD_AUTO

    def set_policy(self, sha256: str, policy: str) -> None:
        """Persist one table's auto-load policy (immediate save).

        ``policy`` must be one of :data:`AUTOLOAD_POLICIES`.  The
        documented default (``AUTOLOAD_AUTO``) is persisted as the
        ABSENCE of the entry (the same discipline as the MT-28
        binding document) - setting it drops a persisted
        manual-only entry.  A malformed key or an out-of-bounds
        policy is a named refusal (fail-closed - the store never
        persists what the validator refuses; the toggle simply does
        not apply).
        """
        if not sha256_key_ok(sha256):
            raise AutoLoadRefusal(["autoload save needs a sha256 key"])
        if policy not in AUTOLOAD_POLICIES:
            raise AutoLoadRefusal([
                "policy is not one of " + ", ".join(AUTOLOAD_POLICIES)
                + " (got " + repr(policy)[:40] + ")"])
        payload = self.document()
        if policy == AUTOLOAD_AUTO:
            if sha256 in payload["tables"]:
                del payload["tables"][sha256]
        else:
            payload["tables"][sha256] = autoload_entry(policy, utc_now())
            evict_oldest(payload["tables"])
        save_autoload_document(payload, self.path)

    def clear_policy(self, sha256: str) -> bool:
        """Drop one table's policy entry (persists the removal).

        ``False`` when the key is malformed or no entry exists
        (documented, never a silent document reset).
        """
        if not sha256_key_ok(sha256):
            return False
        payload = self.document()
        if sha256 not in payload["tables"]:
            return False
        del payload["tables"][sha256]
        save_autoload_document(payload, self.path)
        return True

    def clear(self) -> None:
        """Reset the document to the empty state (persists the reset)."""
        save_autoload_document({"schema": AUTOLOAD_SCHEMA, "tables": {}},
                               self.path)


# ---------------------------------------------------------------------
# display helpers
# ---------------------------------------------------------------------

def details_autoload_lines(entry) -> list:
    """Ordered ``(label, value)`` rows for the details window.

    ``entry`` is the persisted auto-load policy entry for the
    table's content sha (or None while the table carries the
    documented default).  The default shows "automatic (the
    documented default)"; a persisted manual-only entry shows the
    effective policy plus the user-facing consequence.
    """
    if entry is not None and entry.get("policy") == AUTOLOAD_MANUAL_ONLY:
        return [("Auto-load policy",
                 "manual only (never auto-loaded; load it explicitly)")]
    return [("Auto-load policy", "automatic (the documented default)")]
