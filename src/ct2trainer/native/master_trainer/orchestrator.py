"""Master Trainer session state machine (pure, UI- and engine-free).

The orchestrator owns the waiting-mode decisions:

- ``waiting``:  each tick lists the process snapshot and matches it
  against the index's bound process names.  A single-table match yields a
  direct load request (the documented auto-load policy); a multi-table
  match yields a choice request; no match stays waiting.  While a
  failed load for the exact (name, PID) pair is remembered, no load
  request and no choice re-issue goes out for that pair — the tick
  returns the named suppression instead (an explicit retry re-arms).
- ``choosing``: a multi-table match is pending; the UI offers the picker.
- ``loading``:  a table compile is in flight (side effect owned by the
  UI layer; the orchestrator tracks the attempt and failure state).
- ``active``:   the trainer UI owns the session; the orchestrator is idle
  until the session returns to the Master (``deactivate``).

Fail-closed loop guard: a failed load for one exact (process name, PID)
pair is remembered while that process identity stays visible, so a broken
table cannot hot-retry every tick.  A new PID for the same name, or an
explicit retry, re-arms the pair.  Failure is always named, never silent.

Determinism: when several bound processes are running, the first
casefold-sorted process name wins; when several PIDs match one name, the
smallest PID wins.  The rule is documented, stable across ticks and
visible in the UI.
"""
from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable

from .process_picker import candidate_processes
from .process_watch import (ProcessSnapshotEntry, ProcessLister,
                            match_targets)
from .table_index import TableEntry, TableIndex

STATE_WAITING = "waiting"
STATE_CHOOSING = "choosing"
STATE_LOADING = "loading"
STATE_ACTIVE = "active"


class ExplicitLoadRefusal(ValueError):
    """A named refusal for an explicit user table load (MT-10).

    ``code`` is the stable machine-readable reason; ``detail`` is
    displayable in the status line and dialogs.
    """

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class ExplicitLoadRequest:
    """An explicit user table load resolved against index + snapshot.

    ``plan_process`` is the process name the plan must be compiled with:
    a running bound name when one is visible, otherwise the first bound
    name in casefold order.  ``candidates`` are the running PIDs the user
    may pick (MT-11); empty means the trainer loads and the engine waits
    for the process to start.  ``process`` is the entry to hand to
    :meth:`MasterOrchestrator.load` - the chosen candidate, or a
    synthetic zero-PID entry when nothing runs yet.
    """

    table: TableEntry
    plan_process: str
    candidates: tuple
    process: ProcessSnapshotEntry


@dataclass(frozen=True)
class PendingChoice:
    """A multi-table match awaiting the user's decision."""

    process_key: str                    # casefolded running process name
    process_name: str                   # original spelling from the index
    snapshot_entries: tuple[ProcessSnapshotEntry, ...]
    tables: tuple[TableEntry, ...]      # stable order (relative path)


@dataclass(frozen=True)
class TickOutcome:
    """One orchestrator tick's decision.

    ``request`` is the auto-load candidate (single-table match);
    ``choice`` is the pending multi-table match; ``reason`` names why
    nothing was requested on a matching tick (loop guard); ``running``
    lists every bound process currently visible in the snapshot (stable
    name/PID order) so the waiting UI can show live running feedback
    independent of the load decision.
    """

    state: str
    request: TableEntry | None = None
    request_process: ProcessSnapshotEntry | None = None
    choice: PendingChoice | None = None
    reason: str | None = None
    running: tuple[ProcessSnapshotEntry, ...] = ()


@dataclass(frozen=True)
class LoadOutcome:
    """Result of one table load attempt."""

    ok: bool
    plan: dict | None = None
    error: str | None = None


class MasterOrchestrator:
    """Waiting-mode decision engine over an index and a process lister."""

    def __init__(self, index: TableIndex, lister: ProcessLister,
                 plan_compiler: Callable[[TableEntry, str], dict],
                 now: Callable[[], float] = time.monotonic):
        self.index = index
        self.lister = lister
        self.plan_compiler = plan_compiler
        self._now = now
        self.state = STATE_WAITING
        self.choice: PendingChoice | None = None
        self.last_error: str | None = None
        self.last_tick_detail: str = ""
        self._failed: dict[tuple[str, int], str] = {}
        # (process key, pid) pairs the user deferred ("Not now"): no auto
        # load and no re-asking while that exact process identity is alive.
        self._suppressed: set[tuple[str, int]] = set()
        self._load_in_flight: tuple[TableEntry, ProcessSnapshotEntry] | None = None

    # -- queries -------------------------------------------------------------

    @property
    def bound_process_names(self) -> list[str]:
        return self.index.process_names()

    def is_idle(self) -> bool:
        """True while the waiting decision engine may be ticked."""
        return self.state in (STATE_WAITING, STATE_CHOOSING)

    # -- waiting decisions -----------------------------------------------------

    def tick(self) -> TickOutcome:
        """One waiting-mode decision; only valid while waiting/choosing.

        Re-ticking an open choice is idempotent: the same pending choice is
        returned until the UI resolves it, and no other load request is
        issued while the picker is open.  When the open choice's process no
        longer matches, the choice is stale and dropped back to waiting.
        """
        if self.state not in (STATE_WAITING, STATE_CHOOSING):
            raise ValueError("tick is only valid while the Master waits")
        try:
            snapshot = self.lister.list_processes()
        except Exception as exc:
            self.last_tick_detail = ("process snapshot failed: "
                                     + exc.__class__.__name__ + ": " + str(exc))
            self.last_error = self.last_tick_detail
            return TickOutcome(self.state, reason=self.last_tick_detail)
        target_names = self.index.process_name_set()
        matches = match_targets(snapshot, target_names)
        running = tuple(sorted((e for group in matches.values() for e in group),
                               key=lambda e: (e.name.casefold(), e.pid))) \
            if matches else ()
        if not matches:
            self._drop_stale({entry.pid for entry in snapshot})
            detail = (f"scanned {len(snapshot)} processes; "
                      f"none of the {len(self.bound_process_names)} bound "
                      "target(s) is running")
            self.last_tick_detail = detail
            self.last_error = None
            if self.state == STATE_CHOOSING:
                # The matched process disappeared while the picker was
                # open: the pending choice is stale, back to waiting.
                self.choice = None
                self.state = STATE_WAITING
            return TickOutcome(self.state, running=running)
        key, entries = min(matches.items(), key=lambda item: (item[0], min(e.pid for e in item[1])))
        if self.state == STATE_CHOOSING and self.choice is not None:
            if self.choice.process_key in matches:
                # The picker is open for this process: keep the pending
                # choice stable and start no other load until it is
                # resolved.
                return TickOutcome(self.state, choice=self.choice,
                                   running=running)
            # The open choice's process no longer matches: the choice is
            # stale, drop it and re-evaluate from waiting.
            self.choice = None
            self.state = STATE_WAITING
        if any((key, entry.pid) in self._suppressed for entry in entries):
            detail = ("auto-load deferred (the user chose not to load while "
                      "this exact process is running; Retry load re-arms)")
            self.last_tick_detail = detail
            self.last_error = None
            if self.state == STATE_CHOOSING:
                self.choice = None
                self.state = STATE_WAITING
            return TickOutcome(self.state, reason=detail, running=running)
        table_entries = self.index.entries_for_process(key)
        if not table_entries:
            # A snapshot name matched a stored bound name, but every
            # corresponding table entry is unreadable: name the dead end.
            self.last_tick_detail = ("matched process '" + entries[0].name
                                     + "' but every bound table is unreadable")
            self.last_error = self.last_tick_detail
            return TickOutcome(self.state, reason=self.last_tick_detail,
                               running=running)
        if len(table_entries) == 1:
            table = table_entries[0]
            process = min(entries, key=lambda e: e.pid)
            failure = self._failed.get((key, process.pid))
            if failure is not None:
                self.last_tick_detail = ("auto-load suppressed (earlier failure for "
                                         + table.relative_path + ": " + failure + ")")
                self.last_error = failure
                return TickOutcome(self.state, reason=self.last_tick_detail,
                                   running=running)
            self.last_tick_detail = ("matched " + process.name
                                     + " (PID " + str(process.pid) + "); "
                                     "loading " + table.relative_path)
            self.last_error = None
            return TickOutcome(self.state, request=table,
                               request_process=process, running=running)
        failure = self._failed.get((key, min(e.pid for e in entries)))
        if failure is not None:
            # A load for this exact process identity already failed
            # (compile or gate refusal): do not re-issue the picker
            # while that identity stays visible — the named suppression
            # replaces the choice until an explicit retry re-arms.
            self.last_tick_detail = ("auto-load suppressed (earlier "
                                     "failure: " + failure + ")")
            self.last_error = failure
            return TickOutcome(self.state, reason=self.last_tick_detail,
                               running=running)
        original_name = next(n for n in self.index.process_names()
                             if n.casefold() == key)
        self.choice = PendingChoice(
            process_key=key, process_name=original_name,
            snapshot_entries=tuple(sorted(entries, key=lambda e: e.pid)),
            tables=tuple(table_entries))
        self.state = STATE_CHOOSING
        self.last_tick_detail = ("matched " + process_name_display(self.choice)
                                 + "; " + str(len(table_entries))
                                 + " tables bind to it - choosing")
        self.last_error = None
        return TickOutcome(self.state, choice=self.choice, running=running)

    # -- choice resolution -----------------------------------------------------

    def choose(self, relative_path: str) -> LoadOutcome:
        """Resolve the open choice with one table (compile + handoff plan)."""
        if self.state != STATE_CHOOSING or self.choice is None:
            raise ValueError("no open table choice")
        if relative_path not in [t.relative_path for t in self.choice.tables]:
            raise ValueError("chosen table is not part of the open choice")
        table = next(t for t in self.choice.tables if t.relative_path == relative_path)
        process = min(self.choice.snapshot_entries, key=lambda e: e.pid)
        return self.load(table, process)

    def cancel_choice(self) -> None:
        """Cancel the open choice; the process stays matched on the next
        tick, so the picker simply re-appears (no silent suppression)."""
        if self.state != STATE_CHOOSING:
            raise ValueError("no open table choice")
        self.choice = None
        self.state = STATE_WAITING

    # -- load attempts ----------------------------------------------------------

    def load(self, table: TableEntry, process: ProcessSnapshotEntry) -> LoadOutcome:
        """Compile the table for the matched running process name.

        A compile refusal fails the attempt and re-arms the loop guard for
        the exact (name, PID) pair.  A successful compile keeps the
        orchestrator in the loading state until the UI layer confirms the
        trainer session (``mark_active``) or reports the engine-startup
        failure (``fail_load``).
        """
        self.state = STATE_LOADING
        self._load_in_flight = (table, process)
        try:
            plan = self.plan_compiler(table, process.name)
        except Exception as exc:
            error = exc.__class__.__name__ + ": " + str(exc)
            self._failed[(process.name.casefold(), process.pid)] = error
            self.state = STATE_WAITING
            self.choice = None
            self._load_in_flight = None
            self.last_error = error
            self.last_tick_detail = ("load failed for " + table.relative_path
                                     + ": " + error)
            return LoadOutcome(False, error=error)
        return LoadOutcome(True, plan=plan)

    def fail_load(self, error: str) -> None:
        """The plan compiled but the trainer engine could not start
        (state lock, architecture refusal, ...).  Same fail-closed loop
        guard as a compile refusal."""
        if self.state != STATE_LOADING or self._load_in_flight is None:
            raise ValueError("no load is in flight")
        table, process = self._load_in_flight
        self._failed[(process.name.casefold(), process.pid)] = error
        self.state = STATE_WAITING
        self.choice = None
        self._load_in_flight = None
        self.last_error = error
        self.last_tick_detail = ("load failed for " + table.relative_path
                                 + ": " + error)

    def mark_active(self) -> None:
        """The trainer UI owns the session now."""
        if self.state != STATE_LOADING:
            raise ValueError("a load must be in flight before activation")
        self.state = STATE_ACTIVE
        self._load_in_flight = None
        self.last_tick_detail = "trainer session active"
        self.last_error = None

    def deactivate(self) -> None:
        """Return to the waiting mode after the trainer session ended."""
        if self.state != STATE_ACTIVE:
            raise ValueError("no active session to release")
        self.state = STATE_WAITING
        self._load_in_flight = None
        self.last_tick_detail = "back to Master wait mode"
        self.last_error = None

    def suppress(self, process_key: str, pid: int) -> None:
        """Remember that the user deferred this exact (name, PID) pair:
        no auto-load, no re-ask, while the process identity is alive."""
        self._suppressed.add((process_key, pid))

    def retry(self, process_key: str | None = None,
              pid: int | None = None) -> None:
        """Explicit retry: clear remembered failures and deferrals for one
        pair (or every pair when both arguments are omitted)."""
        if process_key is None and pid is None:
            self._failed.clear()
            self._suppressed.clear()
            return
        if process_key is None or pid is None:
            raise ValueError("retry needs both the process key and the PID, "
                             "or neither")
        self._failed.pop((process_key, pid), None)
        self._suppressed.discard((process_key, pid))

    # -- explicit load (MT-10) ---------------------------------------------------

    def request_load(self, relative_path: str) -> ExplicitLoadRequest:
        """Explicit user table load (MT-10): resolve one indexed table
        against the live process snapshot.

        Named refusals (:class:`ExplicitLoadRefusal` with stable ``code``):

        - ``not-in-index``: the path is not part of the index (the table
          is new or gone; Rescan re-arms the index);
        - ``table-unreadable``: the entry is visible but not loadable
          (the named scan error rides in the detail);
        - ``no-process-binding``: the entry binds no process name, so no
          target can be attached to it;
        - ``process-snapshot-failed``: the snapshot backend failed.

        Unlike the auto-load tick this path never consults the fail-
        closed loop guard: the user asked for this table, so the attempt
        runs.  A later :meth:`load` failure still records the ordinary
        (name, PID) suppression for the auto-load loop.  A running bound
        process wins the plan process name; when nothing runs the first
        bound name in casefold order is used and the engine simply waits
        for the process to start (the plan is compiled statically).
        """
        if type(relative_path) is not str or not relative_path:
            raise ExplicitLoadRefusal("not-in-index",
                                      "no table path given")
        entry = self.index.get(relative_path)
        if entry is None:
            raise ExplicitLoadRefusal(
                "not-in-index",
                "table '" + relative_path + "' is not part of the index "
                "(Rescan the folder first if the table is new)")
        if entry.status != "ok":
            raise ExplicitLoadRefusal(
                "table-unreadable",
                "table '" + relative_path + "' is unreadable: "
                + (entry.detail or "no detail"))
        if not entry.process_names:
            raise ExplicitLoadRefusal(
                "no-process-binding",
                "table '" + relative_path + "' binds no process name, so "
                "no target can be attached to it")
        try:
            snapshot = self.lister.list_processes()
        except Exception as exc:
            raise ExplicitLoadRefusal(
                "process-snapshot-failed",
                "the process snapshot failed: "
                + exc.__class__.__name__ + ": " + str(exc)) from exc
        candidates = candidate_processes(snapshot, entry.process_names)
        if candidates:
            # The smallest-PID candidate is the documented determinism
            # rule; the plan compiles against that process's name.
            process = min(candidates, key=lambda e: e.pid)
            plan_process = process.name
        else:
            plan_process = sorted(entry.process_names, key=str.casefold)[0]
            process = ProcessSnapshotEntry(0, plan_process)
        return ExplicitLoadRequest(table=entry, plan_process=plan_process,
                                   candidates=candidates, process=process)

    # -- internals ---------------------------------------------------------------

    def _drop_stale(self, live_pids: set[int]) -> None:
        # Failures and deferrals are only meaningful while the exact process
        # identity is visible; once the PID is gone the guards must not
        # block the next launch of the same game.
        for key in [k for k in self._failed if k[1] not in live_pids]:
            del self._failed[key]
        self._suppressed = {k for k in self._suppressed if k[1] in live_pids}


def process_name_display(choice: PendingChoice) -> str:
    pids = ", ".join(str(e.pid) for e in choice.snapshot_entries)
    return choice.process_name + " (PID " + pids + ")"
