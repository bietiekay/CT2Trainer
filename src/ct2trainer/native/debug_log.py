"""Optional detailed runtime debug log for the generated trainer.

Enabled by the converter option "Debug logging" (GUI checkbox / CLI flag),
which sets the plan flag ``debug_log``.  When enabled, the trainer appends
one JSON line per runtime event to a log file so later debugging of the
exact attempts, scans, writes and refusals is possible without re-running
the session:

- frozen trainer: ``<trainer exe stem>.ct2debug.log`` next to the EXE
- source runtime: ``ct2trainer-debug.log`` in the current working directory

Every line is a JSON object carrying a UTC timestamp, an event name and a
details object; error events additionally carry the exception type/message
and the full traceback.  Logging is best-effort: a failed log write never
changes trainer behavior.  Plans without the flag are byte-identical and
produce no log file at all.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sys
import threading
import traceback
from pathlib import Path
from typing import Any


def _frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def default_log_path() -> Path:
    """Where the debug log file lives for the current runtime flavor."""
    if _frozen():
        exe = Path(sys.executable)
        return exe.with_name(exe.stem + ".ct2debug.log")
    return Path.cwd() / "ct2trainer-debug.log"


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="milliseconds")


# Process-wide crash-reporting state, installed at most once.  The hooks
# always point at the most recently armed log instance (the trainer's
# startup loop may create several before the session engine is final).
_crash: dict[str, Any] = {}


def _crash_line(event: str, exc_type: type, exc_value: BaseException,
                exc_tb: Any, **details: Any) -> str | None:
    try:
        tb = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    except Exception:
        tb = ""
    record = {
        "ts": _now(),
        "event": event,
        "error": "%s: %s" % (exc_type.__name__, exc_value),
        "traceback": tb,
        "pid": os.getpid(),
    }
    record.update(details)
    try:
        return json.dumps(record, ensure_ascii=False, sort_keys=True,
                          default=str) + "\n"
    except (TypeError, ValueError):
        return None


def _crash_write(line: str | None) -> None:
    if line is None:
        return
    fh = _crash.get("fh")
    if fh is None:
        return
    try:
        fh.write(line)
        fh.flush()
    except (OSError, ValueError):
        # A crashed process cannot lose more evidence by a failed write.
        pass


def _crash_excepthook(exc_type: type, exc_value: BaseException, exc_tb: Any) -> None:
    # Field case 2026-10-23 (Sinking City 2, 0.16.3): an uncaught exception
    # escaping the Tk event loop left no trace in the debug log of a
    # windowed trainer (stderr is unattached).  The evidence goes to the
    # log file first, then to the original hook (stderr / debugger).
    _crash_write(_crash_line("trainer-crashed", exc_type, exc_value, exc_tb))
    original = _crash.get("hooks", (None, None))[0]
    if original is not None and original is not _crash_excepthook:
        try:
            original(exc_type, exc_value, exc_tb)
        except Exception:
            pass


def _crash_thread_excepthook(args: Any) -> None:
    # The hook argument is CPython's _thread._ExceptHookArgs
    # (exc_type, exc_value, exc_traceback, thread) - the thread name lives
    # on the Thread member, not on the args tuple.
    _crash_write(_crash_line("trainer-thread-crashed",
                             args.exc_type, args.exc_value,
                             args.exc_traceback,
                             thread=getattr(getattr(args, "thread", None),
                                           "name", "")))
    original = _crash.get("hooks", (None, None))[1]
    if original is not None and original is not _crash_thread_excepthook:
        try:
            original(args)
        except Exception:
            pass


class TrainerDebugLog:
    """Append-only JSON-lines debug log; disabled instances are pure no-ops."""

    def __init__(self, path: str | Path | None = None, *, enabled: bool,
                 header: dict | None = None):
        self.path = Path(path) if path is not None else None
        self.enabled = bool(enabled) and self.path is not None
        self._lock = threading.Lock()
        self._fh = None
        self._closed = False
        if enabled:
            self.log("log-start", **{**(header or {}), "log_path": str(self.path)})

    def log(self, event: str, **details: Any) -> None:
        """Append one event; no-op when logging is disabled or closed."""
        if not self.enabled or self._closed:
            return
        record = {"ts": _now(), "event": event}
        record.update(details)
        try:
            line = json.dumps(record, ensure_ascii=False, sort_keys=True, default=str) + "\n"
        except (TypeError, ValueError):
            # A non-serializable detail must never break the trainer.
            return
        self._write(line)

    def error(self, event: str, exc: BaseException, **details: Any) -> None:
        """Append a failure event with exception identity and full traceback.

        Call from within the ``except`` block so ``traceback.format_exc()``
        captures the active exception stack.
        """
        if not self.enabled or self._closed:
            return
        tb = ""
        try:
            tb = traceback.format_exc()
        except Exception:
            pass
        self.log(event, error="%s: %s" % (type(exc).__name__, exc),
                 traceback=tb, **details)

    def arm_crash_reporting(self) -> None:
        """Persist uncaught-exception and native-crash evidence in this log.

        Field case 2026-10-23 (Sinking City 2, 0.16.3): the trainer process
        died mid-restore with zero follow-up log events; a windowed build
        has no stderr, so without an explicit sink an uncaught exception
        (or a native crash) leaves no evidence at all.  This arms three
        independent, best-effort sinks into the same log file:

        - ``sys.excepthook`` wrapper: a ``trainer-crashed`` JSON event with
          the full traceback, installed once per process and always
          delegating to the previously installed hook;
        - ``threading.excepthook`` wrapper: a ``trainer-thread-crashed``
          JSON event for failures on background threads (the debug-event
          coordinator worker, async policy threads);
        - ``faulthandler`` on a dedicated append handle: native fatal
          signals (access violation, stack overflow, abort) dump the
          Python stacks of every thread into the log file.

        The crash handle is independent of :meth:`close`, so the evidence
        is still written after the engine has torn the session log down.
        Arming emits no log event of its own; only real failures do.
        """
        if not self.enabled:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fh = self.path.open("a", encoding="utf-8")
        except OSError:
            return
        previous = _crash.get("fh")
        _crash["log"] = self
        _crash["fh"] = fh
        if "hooks" not in _crash:
            _crash["hooks"] = (sys.excepthook, threading.excepthook)
            sys.excepthook = _crash_excepthook
            threading.excepthook = _crash_thread_excepthook
        try:
            import faulthandler
            if hasattr(faulthandler, "enable"):
                faulthandler.enable(file=fh)
        except Exception:
            pass
        # A re-arm (the startup loop may create several engines before the
        # session engine is final) replaces the active sink; the previous
        # append handle is no longer referenced by any mechanism - close
        # it so it does not leak for the process lifetime.
        if previous is not None:
            try:
                previous.close()
            except Exception:
                pass

    def close(self) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._closed = True
            if self._fh is not None:
                try:
                    self._fh.close()
                except OSError:
                    pass
                self._fh = None

    def _write(self, line: str) -> None:
        try:
            with self._lock:
                if self._fh is None:
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    self._fh = self.path.open("a", encoding="utf-8")
                self._fh.write(line)
                self._fh.flush()
        except OSError:
            # Best-effort logging: drop the handle, later calls retry once;
            # persistent failure stays silent on purpose.
            with self._lock:
                if self._fh is not None:
                    try:
                        self._fh.close()
                    except OSError:
                        pass
                    self._fh = None


def create_debug_log(plan: dict) -> TrainerDebugLog:
    """Create the engine's debug log from the plan's ``debug_log`` flag.

    The header records plan identity so the file is meaningful even when the
    trainer later fails before doing anything (e.g. state claim refused).
    """
    enabled = bool(plan.get("debug_log"))
    path = default_log_path()
    header = {
        "pid": os.getpid(),
        "frozen": _frozen(),
        "schema": plan.get("schema"),
        "trainer_id": plan.get("trainer_id"),
        "table_sha256": plan.get("table_sha256"),
        "process_name": plan.get("process_name"),
        "title": plan.get("title"),
        "target_architecture": plan.get("target_architecture"),
        "entries": len(plan.get("entries", ())),
        "selected_ids": plan.get("selected_ids"),
    }
    return TrainerDebugLog(path, enabled=enabled, header=header)
