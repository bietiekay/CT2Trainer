"""Background plan-analysis worker for the Master Trainer (MT-24).

One daemon thread ("ct2table-analysis") compiles the indexed tables
through the tested ``compile_table`` plan path (the plain static
compile - no MT-9 gate, no target attach, no Lua execution: the
same proof the corpus audit uses) and records the per-table entry
counts + blocked reasons in the persistent ``table-analysis.json``
document (``table_analysis.AnalysisStore``).

Bounds and contract:

- only tables with at least one bound process name are enqueued
  (an unbound table has nothing to compile against; its columns
  stay the pending marker);
- dedupe by table content sha (one queue item per sha; a sha with
  a document entry - ok or failed - is skipped by the enqueuing
  UI layer, so a table is re-analyzed only after a content change
  or a document reset);
- the queue holds at most ``QUEUE_LIMIT`` items; enqueuing beyond
  the bound is a named drop (the table stays pending and is
  re-queued on the next enqueue pass - rescan / waiting-view
  build);
- ``pause()`` / ``resume()`` / ``stop()``: the worker pauses while
  a trainer session runs (the window owns the CPU then) and
  resumes with the waiting view; ``stop()`` is idempotent, sets
  the stop flag, releases a paused wait and joins the thread with
  a bounded wait - a stuck compile can never block the close (the
  thread is a daemon and exits with the process);
- results are written to the store by the worker itself; the UI
  drains ``drain_results()`` (the finished content shas since the
  last drain, in finish order) to re-render the waiting view.

The worker is NOT started by ``MasterApp`` (the window starts it -
deterministic tests); every queue operation is lock-guarded and
the UI thread never blocks on analysis work.
"""
from __future__ import annotations

import queue
import threading

from .table_analysis import (blocked_reasons_from_plan, counts_from_plan,
                             failed_analysis, ok_analysis, utc_now)

THREAD_NAME = "ct2table-analysis"
QUEUE_LIMIT = 64

# Every live AnalysisWorker registers here while its thread is running,
# so process-wide teardown (tests, the run_master exit path) can find
# and stop every instance in one bounded pass.  The set is the single
# source of truth; the registry never owns the worker - ``stop()``
# remains the only lifecycle entry point.
_ACTIVE: "set[AnalysisWorker]" = set()
_ACTIVE_LOCK = threading.Lock()


def active_workers() -> "list[AnalysisWorker]":
    """The AnalysisWorker instances whose thread is currently alive."""
    with _ACTIVE_LOCK:
        return [w for w in _ACTIVE
                if w._thread is not None and w._thread.is_alive()]


class AnalysisWorker:
    """One daemon thread analyzing indexed tables in the background."""

    def __init__(self, app, compiler=None):
        """``compiler`` (``relative_path, process_name`` -> plan)
        overrides the static plan compile (test injection); ``None``
        uses the tested ``compile_table`` path."""
        self._app = app
        self._compile_override = compiler
        self._queue: queue.Queue = queue.Queue()
        self._lock = threading.Lock()
        self._queued: set[str] = set()
        self._working = False
        self._results: list[str] = []
        self._resume_event = threading.Event()
        self._paused = False
        self._stopping = False
        self._thread: threading.Thread | None = None

    # -- lifecycle ---------------------------------------------------

    def start(self) -> None:
        """Start the daemon thread (idempotent while it is alive)."""
        if self._thread is not None and self._thread.is_alive():
            return
        thread = threading.Thread(target=self._run, name=THREAD_NAME,
                                  daemon=True)
        thread.start()
        self._thread = thread
        with _ACTIVE_LOCK:
            _ACTIVE.add(self)

    def _run(self) -> None:
        try:
            while True:
                with self._lock:
                    paused = self._paused
                    stopping = self._stopping
                if stopping:
                    return
                if paused:
                    self._resume_event.wait()
                    continue
                item = self._queue.get()
                if item is None:
                    return
                relative_path, sha, process_name = item
                with self._lock:
                    self._queued.discard(sha)
                    self._working = True
                try:
                    self._analyze_one(relative_path, sha, process_name)
                finally:
                    # The finished sha is appended atomically after the
                    # in-flight flag is cleared, so a drained result
                    # never races the pending_count() bookkeeping.
                    with self._lock:
                        self._working = False
                        self._results.append(sha)
        finally:
            with _ACTIVE_LOCK:
                _ACTIVE.discard(self)

    def pause(self) -> None:
        """Pause the worker (trainer entry): queued items wait."""
        with self._lock:
            self._paused = True

    def resume(self) -> None:
        """Resume the worker (waiting-view build)."""
        with self._lock:
            self._paused = False
        self._resume_event.set()

    def stop(self) -> None:
        """Stop the worker (idempotent, safe from any thread).

        The stop flag is set, a paused wait is released, the stop
        sentinel is queued and the thread is joined with a bounded
        wait (a compile that does not finish is left to the
        process exit - the thread is a daemon).
        """
        with self._lock:
            self._stopping = True
            self._paused = False
        self._resume_event.set()
        self._queue.put(None)
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=60)

    # -- queue -------------------------------------------------------

    def enqueue(self, table_key: str, sha: str,
                process_name: str) -> bool:
        """Queue one table for analysis.

        ``table_key`` is the table's global key (absolute path in a
        multi-root session, relative path in a single-root session).
        Returns False when the item was skipped (already queued for
        that sha, the queue is at its bound, or the worker is
        stopping) - the table then stays pending until the next
        enqueue pass (rescan / waiting-view build).
        """
        with self._lock:
            if self._stopping or sha in self._queued:
                return False
            if len(self._queued) >= QUEUE_LIMIT:
                return False
            self._queued.add(sha)
        self._queue.put((table_key, sha, process_name))
        return True

    def pending_count(self) -> int:
        """Queued + in-progress analysis items.

        The "analyzing N table(s)" figure of the meta line; bounded
        by ``QUEUE_LIMIT + 1`` (the in-progress item left the
        queue).
        """
        with self._lock:
            return len(self._queued) + (1 if self._working else 0)

    def drain_results(self) -> list[str]:
        """The content shas finished since the last drain.

        The store already carries the facts; the caller re-renders
        the waiting view when the list is non-empty (in finish
        order).
        """
        with self._lock:
            if not self._results:
                return []
            out, self._results = self._results, []
        return out

    # -- analysis ------------------------------------------------------

    @property
    def paused(self) -> bool:
        """True while the worker is paused (trainer mode)."""
        with self._lock:
            return self._paused

    def _compile(self, table_key: str, process_name: str):
        """The plan compile for one table (the injected override wins).

        MT-26 (0.34): ``table_key`` is the table's global key (the
        absolute path in a multi-root session, the relative path in a
        single-root session); an absolute key resolves directly, a
        relative key falls back to the primary table folder.
        """
        if self._compile_override is not None:
            return self._compile_override(table_key, process_name)
        from pathlib import Path
        from ..compiler import compile_table
        key = Path(table_key)
        path = key if key.is_absolute() else Path(self._app.folder) / table_key
        return compile_table(path, process_name, architecture="x64")

    def _analyze_one(self, relative_path: str, sha: str,
                     process_name: str) -> None:
        now = utc_now()
        entry = None
        try:
            plan = self._compile(relative_path, process_name)
        except Exception as exc:
            entry = failed_analysis(
                type(exc).__name__ + ": " + str(exc), now)
        else:
            if not isinstance(plan, dict) \
                    or plan.get("table_sha256") != sha:
                # The content drifted between the index scan and the
                # compile - the numbers would describe a different
                # table; a rescan re-arms the analysis.
                entry = failed_analysis("table-changed-during-analysis",
                                        now)
            else:
                entry = ok_analysis(counts_from_plan(plan),
                                    blocked_reasons_from_plan(plan), now)
        self._app.analysis_store.update(sha, entry)
