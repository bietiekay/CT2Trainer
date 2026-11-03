"""Pure filter/sort layer for the Master Trainer waiting-view table list (MT-13).

With ~151 indexed tables the waiting-view tree needs real search and sort:
the user finds a table by table name or by the bound process name, and can
sort the list deterministically.  This module is the pure decision layer -
no OS access, no index mutation, no orchestrator or state access.  The UI
(``master_ui.py``) renders ``filter_tables(sort_tables(index.tables(), mode),
query)``; the load picker and the auto-load path keep listing/using the full
index (they are separate decision surfaces, documented).

Contract:
- ``filter_tables``: empty/whitespace query returns the input order
  unchanged; otherwise a casefolded substring match against the table's
  relative path AND any bound process name (a table matches when ANY bound
  name matches; the table name always counts).  Input order is preserved
  (stable, deterministic).
- ``sort_tables``: stable, deterministic ordering per mode, with the
  casefolded relative path as the universal tie-breaker.
"""
from __future__ import annotations

SORT_MODES = ("name", "process", "status")


def filter_tables(entries, query) -> list:
    """Casefolded substring filter over table name and bound process names.

    ``entries`` is an iterable of ``TableEntry``-shaped objects (anything
    with ``relative_path`` and ``process_names``); the result is a list in
    the same order as the input.  An empty or whitespace-only query is the
    identity (all entries, order unchanged).
    """
    text = (query or "").strip().casefold()
    if not text:
        return list(entries)
    result = []
    for entry in entries:
        if text in entry.relative_path.casefold():
            result.append(entry)
            continue
        if any(text in name.casefold() for name in entry.process_names):
            result.append(entry)
    return result


def _process_key(entry) -> tuple:
    # Tables without a bound process name sort after the named ones
    # (the documented contract); within each group the universal
    # tie-breaker applies.
    names = entry.process_names
    if not names:
        return (1, "", entry.relative_path.casefold())
    return (0, names[0].casefold(), entry.relative_path.casefold())


def sort_tables(entries, mode: str) -> list:
    """Stable, deterministic sort of the waiting-view table list.

    Modes:
    - "name":    casefolded relative path (the ordinary index order);
    - "process": casefolded first bound process name, then casefolded
      relative path (tables without a bound name sort after the named
      ones, in name order);
    - "status":  readable tables first, unreadable last, then casefolded
      relative path.
    The tie-breaker is always the casefolded relative path, so equal
    keys yield the same order on every platform and run.  An unknown mode
    raises ``ValueError`` (named refusal, never a silent fallback).
    """
    if mode not in SORT_MODES:
        raise ValueError("unknown sort mode: " + repr(mode)
                         + " (expected one of " + ", ".join(SORT_MODES) + ")")
    base = list(entries)
    if mode == "name":
        return sorted(base, key=lambda e: e.relative_path.casefold())
    if mode == "process":
        return sorted(base, key=_process_key)
    # status: readable first, unreadable last, then name order within each
    # group (the universal tie-breaker).
    return sorted(base,
                  key=lambda e: (0 if e.status == "ok" else 1,
                                 e.relative_path.casefold()))


# MT-17 (0.27): the waiting-view display modes.  "list" is the flat MT-13
# row order; "process" is the grouped view (one parent row per bound
# process name).  The master-state document (schema 4, MT-16) persists the
# user's choice with its own format-level constant; the two must stay in
# sync (mirrors the attach-mode pattern in master_state.py).
VIEW_MODES = ("list", "process")

UNBOUND_PROCESS_LABEL = "(no process binding)"


def group_tables_by_process(entries) -> list[tuple[str, list]]:
    """MT-17 (0.27): group an already-ordered entry list by process name.

    ``entries`` is the waiting-view row set the caller already sorted and
    filtered (``filter_tables(sort_tables(...), query)``); this function
    only reshapes the rows, it never adds or drops tables.  A table that
    binds several process names appears once under EACH of them (the
    table shows up in every candidate game's group); a table without a
    bound name goes under :data:`UNBOUND_PROCESS_LABEL`.  Group order:
    bound groups in casefolded name order, the unbound group last.
    Within a group the input order (the caller's sort) is preserved.
    The group labels are the casefolded bound names, so the grouped view
    keys off the same identity the running-PID markers use.
    """
    groups: dict[str, list] = {}
    for entry in entries:
        names = entry.process_names
        if not names:
            groups.setdefault(UNBOUND_PROCESS_LABEL, []).append(entry)
            continue
        for name in names:
            groups.setdefault(name.casefold(), []).append(entry)
    ordered: list[tuple[str, list]] = []
    for key in sorted(k for k in groups if k != UNBOUND_PROCESS_LABEL):
        ordered.append((key, groups[key]))
    if UNBOUND_PROCESS_LABEL in groups:
        ordered.append((UNBOUND_PROCESS_LABEL,
                        groups[UNBOUND_PROCESS_LABEL]))
    return ordered
