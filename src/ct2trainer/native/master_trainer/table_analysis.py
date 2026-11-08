"""Pure per-table entry analysis layer for the Master Trainer.

MT-24 (0.32): the waiting view gains the Entries and Blocked columns -
the per-table entry counts of the plan compile (the actionable script
/ value records - the real cheat options - and the blocked records,
the ones the plan cannot load), computed in the background by one
daemon thread (``analysis_worker``) through the tested
``compile_table`` plan path.  The static plan compile executes no
Lua (the same proof the corpus audit uses) and needs no target
attach; a table the compile refuses is recorded with its named
error, so the failure is visible and bounded (the columns show the
failed marker, the details window shows the reason).

This module is the pure decision + document layer:

- ``counts_from_plan`` / ``blocked_reasons_from_plan`` extract the
  bounded counts from one compiled plan (recomputed from the entry
  list, so they always match the entries);
- the persisted ``table-analysis.json`` document (schema 1, under
  the state home, keyed by the table content sha256) carries one
  entry per analyzed table - ok (counts + the top blocked reasons)
  or failed (the named error, truncated) - with the strict
  key-set / field validation of the master-state discipline (an
  unknown field is a named refusal, never a silent drop);
- ``evict_oldest`` bounds the document at ``ANALYSIS_ENTRIES_LIMIT``
  entries (oldest by ``analyzed_at``; ties by sha256 - deterministic);
- the column text helpers map a document entry to the waiting-view
  cells: pending (no entry) -> "…", failed -> "–", ok -> the count;
- ``details_analysis_lines`` feeds the MT-22 details window (the
  "Entry analysis" row, plus the bounded top blocked reasons when
  any entry is blocked).

No worker, no index mutation, no table-file access in this module -
the document I/O goes through the pure byte functions plus the
small :class:`AnalysisStore`; every decision is testable headless.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ANALYSIS_DOC_NAME = "table-analysis.json"
ANALYSIS_SCHEMA = 1

# The persisted document is bounded: one entry per table content
# sha, oldest evicted first, so a folder churn cannot grow it
# without bound (the state home stays small and readable).
ANALYSIS_ENTRIES_LIMIT = 1024

# The per-entry blocked-reasons map is bounded too (highest counts
# first, ties by reason name) - a pathological table can never grow
# the document with thousands of distinct reasons.
BLOCKED_REASONS_LIMIT = 8

# The failed-entry error text is bounded (displayable in the
# details window; the columns only show the failed marker).
ERROR_DETAIL_LIMIT = 200

# The count keys of one plan (the compiler's own semantics):
# total (all records), supported, actionable (the supported
# script / value records - the real cheat options), blocked and
# headings (the navigation rows).
COUNTS_KEYS = ("total", "supported", "actionable", "blocked",
               "headings")

_OK_ENTRY_KEYS = ("status", "counts", "blocked_reasons", "analyzed_at")
_FAILED_ENTRY_KEYS = ("status", "error", "analyzed_at")

_TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


class AnalysisRefusal(ValueError):
    """A stored table-analysis document (or entry) that is refused.

    Carries the displayable refusal reasons; the store treats a
    refused document as absent (documented, never silent - the
    analysis simply re-runs for the affected tables).
    """

    def __init__(self, reasons: list[str]):
        super().__init__("; ".join(reasons))
        self.reasons = tuple(reasons)


def utc_now() -> str:
    """The persisted UTC timestamp format (the state-home style)."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _timestamp_ok(value) -> bool:
    """True for the persisted ``analyzed_at`` timestamp format."""
    return (isinstance(value, str) and len(value) == 20
            and _TIMESTAMP_RE.fullmatch(value) is not None)


def _sha256_key_ok(value) -> bool:
    """True for one table-content sha256 key (64 lowercase hex)."""
    return (isinstance(value, str) and len(value) == 64
            and all(c in "0123456789abcdef" for c in value))


# ---------------------------------------------------------------------
# counts extraction
# ---------------------------------------------------------------------

def counts_from_plan(plan: dict) -> dict:
    """The bounded entry counts of one compiled table plan.

    Recomputed from the plan's entry list (not copied from
    ``plan["counts"]``), so the numbers always match the entries:
    ``total`` (all records), ``supported``, ``actionable`` (the
    supported script / value records - the real cheat options),
    ``blocked`` (the unsupported records) and ``headings`` (the
    navigation rows).  A plan without a proper entry list is a
    named refusal (fail-closed; the worker records it as a failed
    analysis).
    """
    entries = plan.get("entries") if isinstance(plan, dict) else None
    if not isinstance(entries, list):
        raise AnalysisRefusal(["analysis plan has no entries list"])
    for entry in entries:
        if not isinstance(entry, dict):
            raise AnalysisRefusal(["analysis plan entry is not an object"])
    return {
        "total": len(entries),
        "supported": sum(1 for e in entries if e.get("supported")),
        "actionable": sum(
            1 for e in entries
            if e.get("supported") and e.get("kind") in ("script", "value")),
        "blocked": sum(1 for e in entries if not e.get("supported")),
        "headings": sum(1 for e in entries if e.get("kind") == "heading"),
    }


def blocked_reasons_from_plan(plan: dict) -> dict:
    """The top unsupported reasons of one compiled table plan.

    Bounded by :data:`BLOCKED_REASONS_LIMIT` entries (highest
    counts first, ties by reason name), so a pathological table
    can never grow the persisted document.  ``{}`` when nothing
    is blocked.
    """
    entries = plan.get("entries") if isinstance(plan, dict) else None
    if not isinstance(entries, list):
        raise AnalysisRefusal(["analysis plan has no entries list"])
    tally: dict[str, int] = {}
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("supported"):
            continue
        reason = entry.get("reason")
        if not isinstance(reason, str) or not reason:
            reason = "no-reason"
        tally[reason] = tally.get(reason, 0) + 1
    if not tally:
        return {}
    ordered = sorted(tally.items(), key=lambda kv: (-kv[1], kv[0]))
    return dict(ordered[:BLOCKED_REASONS_LIMIT])


# ---------------------------------------------------------------------
# entry builders
# ---------------------------------------------------------------------

def ok_analysis(counts: dict, blocked_reasons: dict, now: str) -> dict:
    """The persisted entry for one successfully analyzed table."""
    return {"status": "ok",
            "counts": dict(counts),
            "blocked_reasons": dict(blocked_reasons),
            "analyzed_at": now}


def failed_analysis(error: str, now: str) -> dict:
    """The persisted entry for one failed analysis.

    ``error`` is the displayable named cause (``ClassName: msg`` or
    the stable code), truncated to :data:`ERROR_DETAIL_LIMIT`; a
    failed entry keeps the counts unknown on purpose (the columns
    show the failed marker, never stale numbers).
    """
    text = (error or "").strip()
    if len(text) > ERROR_DETAIL_LIMIT:
        text = text[:ERROR_DETAIL_LIMIT]
    return {"status": "failed", "error": text, "analyzed_at": now}


# ---------------------------------------------------------------------
# document validation
# ---------------------------------------------------------------------

def _validate_counts(counts) -> None:
    if (not isinstance(counts, dict)
            or set(counts) != set(COUNTS_KEYS)):
        raise AnalysisRefusal(["analysis counts keys mismatch"])
    for key in COUNTS_KEYS:
        value = counts[key]
        if isinstance(value, bool) or not isinstance(value, int) \
                or value < 0:
            raise AnalysisRefusal([
                "analysis counts[" + repr(key)
                + "] is not a non-negative integer"])


def _validate_blocked_reasons(blocked_reasons) -> None:
    if not isinstance(blocked_reasons, dict):
        raise AnalysisRefusal(["analysis blocked_reasons is not an object"])
    if len(blocked_reasons) > BLOCKED_REASONS_LIMIT:
        raise AnalysisRefusal([
            "analysis blocked_reasons exceeds "
            + str(BLOCKED_REASONS_LIMIT) + " entries"])
    for reason, count in blocked_reasons.items():
        if not isinstance(reason, str) or not reason:
            raise AnalysisRefusal(
                ["analysis blocked_reasons key is not a name"])
        if isinstance(count, bool) or not isinstance(count, int) \
                or count < 1:
            raise AnalysisRefusal([
                "analysis blocked_reasons value is not a positive count"])


def _validate_entry(sha: str, entry) -> None:
    if not isinstance(entry, dict):
        raise AnalysisRefusal(["analysis entry is not an object"])
    status = entry.get("status")
    if status == "ok":
        if set(entry) != set(_OK_ENTRY_KEYS):
            raise AnalysisRefusal([
                "analysis entry " + sha[:12] + ".. has unknown ok fields"])
        _validate_counts(entry["counts"])
        _validate_blocked_reasons(entry["blocked_reasons"])
    elif status == "failed":
        if set(entry) != set(_FAILED_ENTRY_KEYS):
            raise AnalysisRefusal([
                "analysis entry " + sha[:12]
                + ".. has unknown failed fields"])
        error = entry["error"]
        if (not isinstance(error, str) or not error.strip()
                or len(error) > ERROR_DETAIL_LIMIT):
            raise AnalysisRefusal([
                "analysis entry " + sha[:12]
                + ".. has an invalid error"])
    else:
        raise AnalysisRefusal([
            "analysis entry " + sha[:12] + ".. has an unknown status"])
    if not _timestamp_ok(entry.get("analyzed_at")):
        raise AnalysisRefusal([
            "analysis entry " + sha[:12] + ".. has an invalid analyzed_at"])


def _validate_analysis_dict(payload) -> None:
    if (not isinstance(payload, dict)
            or set(payload) != {"schema", "tables"}):
        raise AnalysisRefusal(["table-analysis document fields mismatch"])
    if payload["schema"] != ANALYSIS_SCHEMA:
        raise AnalysisRefusal([
            "unsupported table-analysis schema "
            + repr(payload["schema"])])
    tables = payload["tables"]
    if not isinstance(tables, dict):
        raise AnalysisRefusal(["table-analysis tables are not an object"])
    for sha, entry in tables.items():
        if not _sha256_key_ok(sha):
            raise AnalysisRefusal(
                ["table-analysis table key is not a sha256"])
        _validate_entry(sha, entry)


# ---------------------------------------------------------------------
# document bytes / load / save (the master-state envelope discipline)
# ---------------------------------------------------------------------

def analysis_document_to_bytes(payload: dict) -> bytes:
    """Canonical, deterministic JSON bytes for one analysis document.

    The envelope mirrors the master-state document:
    ``{"payload": …, "sha256": …}`` + trailing newline, the digest
    over the canonical payload serialization.
    """
    _validate_analysis_dict(payload)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           allow_nan=False, ensure_ascii=True).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    return json.dumps({"payload": payload, "sha256": digest},
                      sort_keys=True, separators=(",", ":"),
                      allow_nan=False, ensure_ascii=True).encode("utf-8") \
        + b"\n"


def analysis_document_from_bytes(raw: bytes) -> dict:
    """Parse one analysis document; refusal raises AnalysisRefusal."""
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise AnalysisRefusal(
            ["table-analysis document is not valid JSON"]) from None
    if (not isinstance(document, dict)
            or set(document) != {"payload", "sha256"}):
        raise AnalysisRefusal(
            ["table-analysis document fields mismatch"])
    payload = document["payload"]
    if not isinstance(payload, dict):
        raise AnalysisRefusal(
            ["table-analysis payload is not an object"])
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           allow_nan=False, ensure_ascii=True).encode("utf-8")
    if hashlib.sha256(canonical).hexdigest() != document.get("sha256"):
        raise AnalysisRefusal(
            ["table-analysis checksum does not match"])
    _validate_analysis_dict(payload)
    return payload


def load_analysis_document(path) -> dict | None:
    """Load the stored document; absent file -> None, refusal -> None.

    The store treats a refused document as absent: the analysis
    simply re-runs for the affected tables (documented, never a
    silent reset of the waiting view).
    """
    path = Path(path)
    if not path.is_file():
        return None
    try:
        return analysis_document_from_bytes(path.read_bytes())
    except AnalysisRefusal:
        return None


def save_analysis_document(payload: dict, path) -> None:
    """Persist one document; the state home directory is created if
    needed (the master-state save discipline)."""
    _validate_analysis_dict(payload)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(analysis_document_to_bytes(payload))


# ---------------------------------------------------------------------
# bounded store helpers
# ---------------------------------------------------------------------

def evict_oldest(tables: dict,
                 limit: int = ANALYSIS_ENTRIES_LIMIT) -> dict:
    """Drop the oldest entries until the mapping fits the limit.

    Oldest by ``analyzed_at`` (string order = time order for the
    fixed timestamp format), ties by the sha256 key (deterministic).
    The mapping is mutated in place and returned.
    """
    while len(tables) > limit:
        oldest_key = min(tables,
                         key=lambda k: (tables[k].get("analyzed_at") or "",
                                        k))
        del tables[oldest_key]
    return tables


class AnalysisStore:
    """The persistent per-sha analysis cache under the state home.

    One document (``table-analysis.json``) next to the master-state
    document; an absent or refused document means the documented
    empty state (pending columns, the analysis re-runs).
    """

    def __init__(self, state_home: str | Path):
        self.state_home = str(Path(state_home))
        self.path = Path(self.state_home) / ANALYSIS_DOC_NAME

    def document(self) -> dict:
        """The current document (absent / refused -> the empty one)."""
        payload = load_analysis_document(self.path)
        if payload is None:
            return {"schema": ANALYSIS_SCHEMA, "tables": {}}
        return payload

    def get(self, sha256: str):
        """The persisted entry for one table content sha (or None)."""
        return self.document()["tables"].get(sha256)

    def has(self, sha256: str) -> bool:
        return self.get(sha256) is not None

    def update(self, sha256: str, entry: dict) -> None:
        """Insert/replace one table entry, evict over the limit, save.

        A malformed key or entry is a named refusal (fail-closed -
        the store never persists what the validator refuses).
        """
        if not _sha256_key_ok(sha256):
            raise AnalysisRefusal(
                ["analysis update needs a sha256 key"])
        _validate_entry(sha256, entry)
        payload = self.document()
        payload["tables"][sha256] = entry
        evict_oldest(payload["tables"])
        save_analysis_document(payload, self.path)

    def clear(self) -> None:
        """Reset the document to the empty state (persists the reset)."""
        save_analysis_document({"schema": ANALYSIS_SCHEMA, "tables": {}},
                               self.path)


# ---------------------------------------------------------------------
# waiting-view text helpers
# ---------------------------------------------------------------------

def entries_column_text(entry) -> str:
    """The Entries-column value for one table row.

    "…" while the analysis is pending (no document entry), the
    failed marker "–" for a failed analysis, the actionable count
    (the supported script / value records - the real cheat
    options) otherwise.
    """
    if entry is None:
        return "…"
    if entry.get("status") != "ok":
        return "–"
    return str(entry["counts"]["actionable"])


def blocked_column_text(entry) -> str:
    """The Blocked-column value for one table row (same markers)."""
    if entry is None:
        return "…"
    if entry.get("status") != "ok":
        return "–"
    return str(entry["counts"]["blocked"])


def details_analysis_lines(entry) -> list:
    """Ordered ``(label, value)`` rows for the details window.

    ``entry`` is the persisted analysis entry for the table's
    content sha (or None while pending).  An ok entry adds the
    entry-analysis line and - when any entry is blocked - the
    bounded top blocked-reasons line; a failed one shows the named
    error.
    """
    if entry is None:
        return [("Entry analysis",
                 "not analyzed yet (the background analysis is pending)")]
    if entry.get("status") != "ok":
        return [("Entry analysis",
                 "failed: " + (entry.get("error") or "no detail"))]
    counts = entry["counts"]
    text = str(counts["actionable"]) + " entries"
    if counts["blocked"]:
        text += " (" + str(counts["blocked"]) + " blocked)"
    text += " of " + str(counts["total"]) + " records"
    lines = [("Entry analysis", text)]
    if counts["blocked"]:
        top = ", ".join(reason + " × " + str(count)
                        for reason, count
                        in entry["blocked_reasons"].items())
        lines.append(("Top blocked reasons", top))
    return lines
