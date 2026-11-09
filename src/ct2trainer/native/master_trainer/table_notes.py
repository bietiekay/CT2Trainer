"""Pure per-table notes/tags layer for the Master Trainer (MT-27).

MT-27 (0.35): the waiting view gains a Note column - free-form
organization metadata per table (a note plus a bounded tag list),
edited from the row context menu ("Edit note...") and searchable
through the waiting-view filter.  The persisted ``table-notes.json``
document (schema 1, under the state home) is keyed by the table
content sha256 - the same identity the MT-24 analysis document uses,
so a note survives table renames within a root and follows a
content-identical file to another root.  A table whose index entry
has no content sha (unreadable, never scanned) cannot carry a note:
the named refusal is surfaced in the status line, never a crash.

This module is the pure decision + document layer:

- ``note_entry`` builds one persisted entry (strict key set);
- the persisted ``table-notes.json`` document (schema 1) carries one
  entry per noted table - ``{"note", "tags", "updated_at"}`` - with
  the strict key-set / field validation of the master-state
  discipline (an unknown field is a named refusal, never a silent
  drop);
- ``evict_oldest`` bounds the document at ``NOTES_ENTRIES_LIMIT``
  entries (oldest by ``updated_at``; ties by sha256 - deterministic);
- ``parse_tags`` turns the editor's comma-separated tag string into
  the bounded persisted tag list (stripped, casefold-deduped, capped
  at ``TAGS_LIMIT``, each tag at most ``TAG_MAX_LEN`` characters);
- the column / details text helpers map a document entry to the
  waiting-view cell and the MT-22 details-window rows.

No index mutation, no table-file access in this module - the
document I/O goes through the pure byte functions plus the small
:class:`NotesStore`; every decision is testable headless.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

NOTES_DOC_NAME = "table-notes.json"
NOTES_SCHEMA = 1

# The persisted document is bounded: one entry per table content
# sha, oldest evicted first, so a folder churn cannot grow it
# without bound (the state home stays small and readable).
NOTES_ENTRIES_LIMIT = 1024

# The note text is bounded (displayable in the details window; the
# column truncates it further).
NOTE_MAX_LEN = 500

# The tag list is bounded: a small number of short tags, so the Note
# column and the filter stay readable and the document stays small.
TAGS_LIMIT = 8
TAG_MAX_LEN = 40

# The waiting-view Note column truncation (single line).
NOTE_COLUMN_MAX = 60

_ENTRY_KEYS = ("note", "tags", "updated_at")

_TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


class NotesRefusal(ValueError):
    """A stored table-notes document (or entry) that is refused.

    Carries the displayable refusal reasons; the store treats a
    refused document as absent (documented, never silent - the notes
    simply re-enter through the next save).
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

def note_entry(note: str, tags: list, now: str) -> dict:
    """The persisted entry for one noted table.

    ``note`` is the note text (may be empty); ``tags`` is the bounded
    tag list (see :func:`parse_tags`).  Both are validated: a too-long
    note or an out-of-bounds tag list is a named refusal (fail-closed
    - the store never persists what the validator refuses).
    """
    if not isinstance(note, str):
        raise NotesRefusal(["note text is not a string"])
    if len(note) > NOTE_MAX_LEN:
        raise NotesRefusal([
            "note exceeds " + str(NOTE_MAX_LEN) + " characters"])
    if not isinstance(tags, list):
        raise NotesRefusal(["tags are not a list"])
    if len(tags) > TAGS_LIMIT:
        raise NotesRefusal([
            "tags exceed the " + str(TAGS_LIMIT) + "-tag limit"])
    for tag in tags:
        if (not isinstance(tag, str) or not tag.strip()
                or len(tag) > TAG_MAX_LEN):
            raise NotesRefusal([
                "invalid tag: " + repr(tag)[:40] + " (empty, not a "
                "string, or over " + str(TAG_MAX_LEN) + " characters)"])
    return {"note": note, "tags": list(tags), "updated_at": now}


def parse_tags(raw: str) -> list:
    """The editor's comma-separated tag string -> the bounded list.

    Split on commas, stripped, empty pieces dropped, casefold-deduped
    (first spelling kept, first-seen order), capped at
    :data:`TAGS_LIMIT`.  A single tag longer than
    :data:`TAG_MAX_LEN` characters is a named refusal (fail-closed -
    the editor keeps the text visible and the status line names the
    cause; no silent truncation of user input).
    """
    if raw is None:
        return []
    if not isinstance(raw, str):
        raise NotesRefusal(["tag text is not a string"])
    tags: list[str] = []
    seen: set[str] = set()
    for piece in raw.split(","):
        tag = piece.strip()
        if not tag:
            continue
        if len(tag) > TAG_MAX_LEN:
            raise NotesRefusal([
                "tag " + repr(tag) + " exceeds " + str(TAG_MAX_LEN)
                + " characters"])
        key = tag.casefold()
        if key in seen:
            continue
        seen.add(key)
        tags.append(tag)
        if len(tags) == TAGS_LIMIT:
            break
    return tags


# ---------------------------------------------------------------------
# document validation
# ---------------------------------------------------------------------

def _validate_entry(sha: str, entry) -> None:
    if not isinstance(entry, dict):
        raise NotesRefusal(["notes entry is not an object"])
    if set(entry) != set(_ENTRY_KEYS):
        raise NotesRefusal([
            "notes entry " + sha[:12] + ".. has unknown fields"])
    if not isinstance(entry["note"], str) \
            or len(entry["note"]) > NOTE_MAX_LEN:
        raise NotesRefusal([
            "notes entry " + sha[:12]
            + ".. has an invalid note (not a string or over "
            + str(NOTE_MAX_LEN) + " characters)"])
    tags = entry["tags"]
    if not isinstance(tags, list) or len(tags) > TAGS_LIMIT:
        raise NotesRefusal([
            "notes entry " + sha[:12]
            + ".. has an invalid tag list (not a list or over the "
            + str(TAGS_LIMIT) + "-tag limit)"])
    for tag in tags:
        if (not isinstance(tag, str) or not tag.strip()
                or len(tag) > TAG_MAX_LEN):
            raise NotesRefusal([
                "notes entry " + sha[:12] + ".. has an invalid tag"])
    if not _timestamp_ok(entry.get("updated_at")):
        raise NotesRefusal([
            "notes entry " + sha[:12] + ".. has an invalid updated_at"])


def _validate_notes_dict(payload) -> None:
    if (not isinstance(payload, dict)
            or set(payload) != {"schema", "tables"}):
        raise NotesRefusal(["table-notes document fields mismatch"])
    if payload["schema"] != NOTES_SCHEMA:
        raise NotesRefusal([
            "unsupported table-notes schema "
            + repr(payload["schema"])])
    tables = payload["tables"]
    if not isinstance(tables, dict):
        raise NotesRefusal(["table-notes tables are not an object"])
    if len(tables) > NOTES_ENTRIES_LIMIT:
        raise NotesRefusal([
            "table-notes exceeds the " + str(NOTES_ENTRIES_LIMIT)
            + "-entry limit"])
    for sha, entry in tables.items():
        if not sha256_key_ok(sha):
            raise NotesRefusal(["table-notes table key is not a sha256"])
        _validate_entry(sha, entry)


# ---------------------------------------------------------------------
# document bytes / load / save (the master-state envelope discipline)
# ---------------------------------------------------------------------

def notes_document_to_bytes(payload: dict) -> bytes:
    """Canonical, deterministic JSON bytes for one notes document.

    The envelope mirrors the master-state document:
    ``{"payload": …, "sha256": …}`` + trailing newline, the digest
    over the canonical payload serialization.
    """
    _validate_notes_dict(payload)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           allow_nan=False, ensure_ascii=True).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    return json.dumps({"payload": payload, "sha256": digest},
                      sort_keys=True, separators=(",", ":"),
                      allow_nan=False, ensure_ascii=True).encode("utf-8") \
        + b"\n"


def notes_document_from_bytes(raw: bytes) -> dict:
    """Parse one notes document; refusal raises NotesRefusal."""
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise NotesRefusal(
            ["table-notes document is not valid JSON"]) from None
    if (not isinstance(document, dict)
            or set(document) != {"payload", "sha256"}):
        raise NotesRefusal(["table-notes document fields mismatch"])
    payload = document["payload"]
    if not isinstance(payload, dict):
        raise NotesRefusal(["table-notes payload is not an object"])
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           allow_nan=False, ensure_ascii=True).encode("utf-8")
    if hashlib.sha256(canonical).hexdigest() != document.get("sha256"):
        raise NotesRefusal(["table-notes checksum does not match"])
    _validate_notes_dict(payload)
    return payload


def load_notes_document(path) -> dict | None:
    """Load the stored document; absent file -> None, refusal -> None.

    The store treats a refused document as absent (documented, never
    a silent reset of the waiting view).
    """
    path = Path(path)
    if not path.is_file():
        return None
    try:
        return notes_document_from_bytes(path.read_bytes())
    except NotesRefusal:
        return None


def save_notes_document(payload: dict, path) -> None:
    """Persist one document; the state home directory is created if
    needed (the master-state save discipline)."""
    _validate_notes_dict(payload)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(notes_document_to_bytes(payload))


# ---------------------------------------------------------------------
# bounded store helpers
# ---------------------------------------------------------------------

def evict_oldest(tables: dict,
                 limit: int = NOTES_ENTRIES_LIMIT) -> dict:
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


class NotesStore:
    """The persistent per-sha notes/tags cache under the state home.

    One document (``table-notes.json``) next to the master-state
    document; an absent or refused document means the documented
    empty state (no notes).
    """

    def __init__(self, state_home: str | Path):
        self.state_home = str(Path(state_home))
        self.path = Path(self.state_home) / NOTES_DOC_NAME

    def document(self) -> dict:
        """The current document (absent / refused -> the empty one)."""
        payload = load_notes_document(self.path)
        if payload is None:
            return {"schema": NOTES_SCHEMA, "tables": {}}
        return payload

    def get(self, sha256: str):
        """The persisted entry for one table content sha (or None)."""
        return self.document()["tables"].get(sha256)

    def has(self, sha256: str) -> bool:
        return self.get(sha256) is not None

    def set_note(self, sha256: str, note: str, tags: list) -> None:
        """Insert/replace one table's note, evict over the limit, save.

        A malformed key or an out-of-bounds note / tag list is a named
        refusal (fail-closed - the store never persists what the
        validator refuses; the dialog stays open and the status line
        names the cause).
        """
        if not sha256_key_ok(sha256):
            raise NotesRefusal(["note save needs a sha256 key"])
        entry = note_entry(note, tags, utc_now())
        payload = self.document()
        payload["tables"][sha256] = entry
        evict_oldest(payload["tables"])
        save_notes_document(payload, self.path)

    def clear_note(self, sha256: str) -> None:
        """Drop one table's note entry (persists the removal).

        ``False`` when the key is malformed or no entry exists
        (documented, never a silent document reset).
        """
        if not sha256_key_ok(sha256):
            return False
        payload = self.document()
        if sha256 not in payload["tables"]:
            return False
        del payload["tables"][sha256]
        save_notes_document(payload, self.path)
        return True

    def clear(self) -> None:
        """Reset the document to the empty state (persists the reset)."""
        save_notes_document({"schema": NOTES_SCHEMA, "tables": {}},
                            self.path)


# ---------------------------------------------------------------------
# waiting-view text helpers
# ---------------------------------------------------------------------

def _column_single_line(note: str) -> str:
    """One line for the tree cell: newlines become spaces."""
    return note.replace("\n", " ").replace("\r", " ").strip()


def note_column_text(entry) -> str:
    """The Note-column value for one table row.

    "" while no note entry exists; otherwise the note text truncated
    to :data:`NOTE_COLUMN_MAX` characters (an ellipsis marks a cut)
    plus the tag list in brackets when present.  Note-only and
    tag-only entries both render (an empty note shows the tags, a
    tag-less note shows the text).
    """
    if entry is None:
        return ""
    text = _column_single_line(entry.get("note") or "")
    if len(text) > NOTE_COLUMN_MAX:
        text = text[:NOTE_COLUMN_MAX - 1].rstrip() + "…"
    tags = entry.get("tags") or ()
    if tags:
        suffix = "[" + ", ".join(tags) + "]"
        room = NOTE_COLUMN_MAX - len(suffix) - 1
        if len(text) > max(room, 0):
            text = text[:max(room, 0)].rstrip() + "…"
        text = (text + " " if text else "") + suffix
    return text


def details_note_lines(entry) -> list:
    """Ordered ``(label, value)`` rows for the details window.

    ``entry`` is the persisted notes entry for the table's content
    sha (or None when the table has no note).  A note entry adds the
    note line (or the "none" placeholder) and the tags line; None
    adds the single "none" line (the details window then shows the
    table carries no organization metadata).
    """
    if entry is None:
        return [("Note", "none"), ("Tags", "none")]
    lines = [("Note", entry.get("note") or "none")]
    tags = entry.get("tags") or ()
    lines.append(("Tags", ", ".join(tags) if tags else "none"))
    return lines
