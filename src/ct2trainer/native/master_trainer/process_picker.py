"""Process-selection decision logic for the Master Trainer (MT-11).

The Master Trainer binds a table to a running target by name, but a name
can match several live processes (multiple game instances, a second
monitoring tool, ...).  This module holds the pure decision logic so the
picker UI only renders it:

- :func:`candidate_processes` collects the snapshot entries matching any
  of a table's bound process names, in a deterministic order.
- :func:`attach_decision` maps ``(candidates, attach_mode)`` to a single
  decision: ``attach-direct`` (no picker needed), ``pick`` (the user must
  choose one PID) or ``wait`` (nothing is running; the trainer loads and
  waits for the process to start).

``attach_mode`` semantics (persisted in ``master-settings.json``, MT-11):

- ``auto`` (default, legacy behavior): never shows a picker.  A single
  candidate attaches directly; several candidates attach to the smallest
  PID (the deterministic rule the orchestrator already applied).  No
  picker ever appears.
- ``ask``: whenever at least one candidate is running, the user is asked
  to pick the exact PID before anything attaches - even the single one.
  The user can still cancel and let the trainer wait.

Nothing in this module touches the OS; the process lister and the
``ProcessMemory`` factory are injected.  :func:`make_pinned_memory_factory`
produces the ``memory_factory`` the Master injects into ``TrainerEngine``
so that a user-chosen PID is honoured for the lifetime of the session,
falling back to name-based attach (smallest PID) once that process exits.
"""
from __future__ import annotations

from typing import Any, Callable

from .master_state import (ATTACH_MODE_ASK, ATTACH_MODE_AUTO,
                          ATTACH_MODES)
from .process_watch import ProcessSnapshotEntry, ProcessLister, names_match

DECISION_ATTACH_DIRECT = "attach-direct"
DECISION_PICK = "pick"
DECISION_WAIT = "wait"


def candidate_processes(
    snapshot: list[ProcessSnapshotEntry],
    process_names: list[str] | tuple[str, ...],
) -> tuple[ProcessSnapshotEntry, ...]:
    """Running processes matching any bound name, deterministically ordered.

    Sorted by (casefolded name, PID).  The original snapshot spelling of
    the name is kept for display.
    """
    out = [
        entry
        for entry in snapshot
        if any(names_match(entry.name, name) for name in process_names)
    ]
    return tuple(sorted(out, key=lambda e: (e.name.casefold(), e.pid)))


def attach_decision(
    candidates: tuple[ProcessSnapshotEntry, ...],
    attach_mode: str = ATTACH_MODE_AUTO,
) -> tuple[str, ProcessSnapshotEntry | None]:
    """Decide how a load should attach.

    Returns ``(decision, entry)``:

    - ``("wait", None)`` - no candidate runs; the trainer loads and the
      engine waits for the process to start.
    - ``("pick", None)`` - at least one candidate runs and the user must
      choose (``ask`` mode, any candidate count).
    - ``("attach-direct", entry)`` - no picker: the single candidate in
      ``auto`` mode, or the smallest-PID candidate in ``auto`` mode with
      several candidates (the documented determinism rule).

    Raises ``ValueError`` for an unknown attach mode.
    """
    if attach_mode not in ATTACH_MODES:
        raise ValueError("attach_mode must be one of " + repr(list(ATTACH_MODES)))
    if not candidates:
        return (DECISION_WAIT, None)
    if attach_mode == ATTACH_MODE_ASK:
        return (DECISION_PICK, None)
    if len(candidates) == 1:
        return (DECISION_ATTACH_DIRECT, candidates[0])
    return (DECISION_ATTACH_DIRECT, min(candidates, key=lambda e: e.pid))


def make_pinned_memory_factory(
    lister: ProcessLister,
    pin: dict[str, Any],
) -> Callable[[str], Any]:
    """Build the ``memory_factory`` the Master injects into the engine.

    ``pin`` is a mutable dict owned by the UI, initially ``{"pid": None}``.
    Resolution order per attach attempt:

    1. ``pin["pid"]`` set -> attach to exactly that PID (the native layer
       still re-proves name match and image identity, so a recycled PID
       cannot be attached to).
    2. The pinned PID is gone (or was never set) -> fall back to the
       ordinary name-based attach: exactly one matching instance attaches
       directly; several instances resolve to the smallest PID (the
       documented determinism rule, and the same rule the engine would
       use for a single-instance game).

    The pin clears itself when its PID no longer matches, so a later
    (re-)attach of the session never silently binds a different process
    to a stale selection.
    """

    def factory(process_name: str):
        from ..memory import ProcessMemory, ProcessMemoryError

        pid = pin.get("pid")
        if pid is not None:
            try:
                return ProcessMemory(process_name, pid=pid)
            except ProcessMemoryError:
                pin["pid"] = None
        try:
            return ProcessMemory(process_name)
        except ProcessMemoryError:
            candidates = [
                e
                for e in lister.list_processes()
                if names_match(e.name, process_name)
            ]
            if not candidates:
                raise
            return ProcessMemory(
                process_name, pid=min(e.pid for e in candidates))

    return factory
