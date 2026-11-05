"""Pure per-table live status layer for the Master Trainer waiting view.

MT-23 (0.31): the waiting-view Status column shows the table's state
RIGHT NOW, not only the cached state of the last scan.  The folder
content may have drifted in between (a table edited, replaced or
deleted after the scan), and the MT-9 load gate would refuse such a
table with a named code at load time - MT-23 surfaces that at a
glance, with color coding, and offers a status filter:

- ``row_file_status`` derives the live file state of one indexed
  table from the index entry (last scan) plus the current on-disk
  fingerprint: ``missing`` (the file no longer exists or cannot be
  stat'ed), ``changed`` (the (size, mtime_ns) pair drifted),
  ``unreadable`` (the last scan could not read/parse it - the named
  detail is shown) or ``ok``.  Cheapest fact first, and the live
  facts outrank the cached scan state - the same order the MT-9
  gate proves at load time (missing / changed before loadability).
- ``row_status`` adds the process state: a bound process that is
  running shows as ``running`` only when the file state is ok - a
  live process cannot make a changed / missing / unreadable table
  loadable.
- ``row_tag`` maps the code to the tree color tag (default for
  ok / running, warn for changed, error for missing / unreadable).
- ``filter_rows_by_status`` reshapes the waiting-view row set per
  the persisted status-filter mode: "" (all, the identity),
  "ok" (the loadable rows, running included) or "attention" (the
  rows the gate would refuse right now).  Input order is
  preserved; the result never adds or reorders rows.

This module is the pure decision layer - no OS access, no index
mutation, no orchestrator or state access.  The only I/O the waiting
view performs for MT-23 is one bounded ``stat`` per visible row per
render (the UI layer); every decision here is testable headless.
"""
from __future__ import annotations

STATUS_OK = "ok"
STATUS_RUNNING = "running"
STATUS_CHANGED = "changed"
STATUS_MISSING = "missing"
STATUS_UNREADABLE = "unreadable"

# The rows the MT-9 load gate would refuse right now (changed /
# missing / unreadable) - the "needs attention" set of the status
# filter.  ok / running are loadable (the gate would pass the file
# checks; running only reflects the bound process state).
ATTENTION_STATUSES = frozenset(
    (STATUS_CHANGED, STATUS_MISSING, STATUS_UNREADABLE))

# The persisted waiting-view status-filter modes (mirrored by
# ``master_state.VIEW_STATUS_FILTERS`` - the view_mode pattern):
# "" (all) is the identity, "ok" keeps the loadable rows,
# "attention" keeps the attention rows.  A schema-6
# master-settings.json document carries the mode; older documents
# promote with the documented default "" (all).
VIEW_STATUS_FILTERS = ("", "ok", "attention")


def row_file_status(entry, fingerprint) -> tuple[str, str]:
    """Live file state of one indexed table: ``(code, detail)``.

    ``entry`` is the index entry from the last scan (its ``size`` /
    ``mtime_ns`` are the fingerprint then, its ``status`` /
    ``detail`` the cached scan state); ``fingerprint`` is the live
    ``(size, mtime_ns)`` pair from a stat of the current file, or
    ``None`` when the file no longer exists or cannot be stat'ed.
    The detail is displayable (Status/Detail columns, table details
    window).
    """
    if fingerprint is None:
        return STATUS_MISSING, \
            "file missing since the last scan (Rescan re-arms the load)"
    size, mtime_ns = fingerprint
    if (size, mtime_ns) != (entry.size, entry.mtime_ns):
        return STATUS_CHANGED, \
            "changed since the last scan (Rescan re-arms the load)"
    if entry.status != "ok":
        return STATUS_UNREADABLE, entry.detail or "unreadable at the last scan"
    return STATUS_OK, ""


def row_status(entry, fingerprint, running: bool) -> str:
    """The Status-column value for one waiting-view row.

    ``running`` is True when one of the table's bound processes is
    visible right now (the process watch of the latest tick).  The
    process state surfaces only for a loadable file: a running
    process cannot make a changed / missing / unreadable table
    loadable, so the attention code always wins.
    """
    code, _detail = row_file_status(entry, fingerprint)
    if code == STATUS_OK:
        return STATUS_RUNNING if running else STATUS_OK
    return code


def row_tag(code: str) -> str:
    """The tree tag for the row color coding.

    ``""`` (the default colors) for ok / running rows,
    ``"attention-warn"`` for a changed table, ``"attention-error"``
    for a missing / unreadable one.  The tree configures the two
    non-default tags (the UI layer); an unknown code falls back to
    the default colors (never an error).
    """
    if code in (STATUS_MISSING, STATUS_UNREADABLE):
        return "attention-error"
    if code == STATUS_CHANGED:
        return "attention-warn"
    return ""


def filter_rows_by_status(entries, codes, mode: str) -> list:
    """Filter an ordered row set by the live status mode.

    ``entries`` is the waiting-view row set the caller already
    sorted and filtered; ``codes`` is the parallel list of their
    Status-column values (``row_status`` per row, same order);
    ``mode`` is one of :data:`VIEW_STATUS_FILTERS`.  "" (all)
    returns the input order unchanged; "ok" keeps the ok / running
    rows; "attention" keeps the changed / missing / unreadable
    rows.  Input order is preserved; the result never adds or
    reorders rows.  An unknown mode raises ``ValueError`` (named
    refusal, never a silent fallback).
    """
    if mode not in VIEW_STATUS_FILTERS:
        raise ValueError("unknown status filter mode: " + repr(mode)
                         + " (expected one of "
                         + ", ".join(repr(m) for m in VIEW_STATUS_FILTERS)
                         + ")")
    if mode == "":
        return list(entries)
    if mode == "ok":
        wanted = (STATUS_OK, STATUS_RUNNING)
    else:
        wanted = ATTENTION_STATUSES
    return [row for row, code in zip(entries, codes) if code in wanted]
