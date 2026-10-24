"""Regression: trainer crash observability (Sinking City 2 field case, 0.16.3 -> 0.16.4).

Field evidence (2026-10-23, TheSinkingCity2.CT, build 0.16.3): the trainer
process died mid wish-restore (last event: the TALENTPTR aobscan at
18:49:31) and left **zero** follow-up events in the debug log - no
engine-close, no engine-blocked, no crash record.  In a windowed build
stderr is unattached, so an uncaught exception escaping the Tk event loop
(or a native fatal signal) leaves no evidence at all, and the next launch
was blocked by the (correct) state-lock refusal while the target was still
alive.

0.16.4 arms three independent, best-effort sinks:

- ``TrainerDebugLog.arm_crash_reporting`` installs one process-wide
  ``sys.excepthook`` wrapper (``trainer-crashed`` JSON event with the full
  traceback), one ``threading.excepthook`` wrapper
  (``trainer-thread-crashed``), and enables ``faulthandler`` on a dedicated
  append handle so native fatal signals (access violation, stack overflow,
  abort) dump every thread's Python stacks into the same log file.  The
  crash handle is independent of ``close()``, so evidence is still written
  after the engine has torn the session log down.  ``run_trainer`` arms the
  hooks for both entry points (frozen launcher and source CLI) once the
  final engine exists.
- ``TrainerWindow.poll`` wraps ``engine.poll()`` fail-closed: the failure
  is logged as ``poll-crashed``, the engine is blocked (writes refuse, the
  status line names the cause), and the 250 ms tick keeps scheduling so the
  window stays observable and recoverable instead of the exception
  propagating out of the Tk after-callback and killing the process.
- The restore loop logs ``restore-entry-start`` before each record's
  dependencies/enable, so a hard process exit mid-restore leaves the last
  in-progress entry identifiable.
"""
from __future__ import annotations

import faulthandler
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from test_native_debug_log import read_events
from test_native_engine import FakeMemory
from ct2trainer.native.compiler import compile_table
from ct2trainer.native.debug_log import (TrainerDebugLog, _crash,
                                         _crash_excepthook,
                                         _crash_thread_excepthook)
from ct2trainer.native.engine import TrainerEngine

try:
    import tkinter as tk
    from ct2trainer.native.ui import TrainerWindow
except ImportError:  # pragma: no cover - environment without Tcl/Tk
    tk = None
    TrainerWindow = None

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "windows" / "fixture_target" / "fixture.ct"
PROCESS = "FixtureTarget.exe"
LOG_NAME = "ct2trainer-debug.log"


def _release_crash_handles() -> None:
    """Close the process-wide crash append handle (test hygiene)."""
    fh = _crash.get("fh")
    if fh is not None:
        try:
            fh.close()
        except Exception:
            pass


class CrashReportingTests(unittest.TestCase):
    """Process-wide crash hooks: excepthook, threading hook, faulthandler."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "crash.log"
        self._orig_excepthook = sys.excepthook
        self._orig_thread_hook = threading.excepthook
        self._crash_backup = dict(_crash)

    def tearDown(self):
        _release_crash_handles()
        sys.excepthook = self._orig_excepthook
        threading.excepthook = self._orig_thread_hook
        faulthandler.disable()
        _crash.clear()
        _crash.update(self._crash_backup)

    def test_excepthook_writes_trainer_crashed_event(self):
        log = TrainerDebugLog(self.path, enabled=True, header={"pid": os.getpid()})
        log.arm_crash_reporting()
        self.assertIs(sys.excepthook, _crash_excepthook)
        self.assertIs(threading.excepthook, _crash_thread_excepthook)
        self.assertIs(_crash["hooks"][0], self._orig_excepthook)
        self.assertIs(_crash["hooks"][1], self._orig_thread_hook)
        try:
            raise ValueError("synthetic main-thread escape")
        except ValueError as exc:
            sys.excepthook(type(exc), exc, exc.__traceback__)
        log.close()
        events = read_events(self.path)
        crashed = [e for e in events if e["event"] == "trainer-crashed"]
        self.assertEqual(len(crashed), 1)
        self.assertIn("ValueError", crashed[0]["error"])
        self.assertIn("synthetic main-thread escape", crashed[0]["error"])
        self.assertIn("Traceback", crashed[0]["traceback"])
        self.assertEqual(crashed[0]["pid"], os.getpid())

    def test_threading_excepthook_writes_thread_crashed_event(self):
        log = TrainerDebugLog(self.path, enabled=True, header={})
        log.arm_crash_reporting()

        def boom():
            raise RuntimeError("synthetic background-thread failure")

        worker = threading.Thread(target=boom, name="CT2Trainer-test-thread")
        worker.start()
        worker.join()
        log.close()
        events = read_events(self.path)
        crashed = [e for e in events if e["event"] == "trainer-thread-crashed"]
        self.assertEqual(len(crashed), 1)
        self.assertIn("synthetic background-thread failure", crashed[0]["error"])
        self.assertIn("Traceback", crashed[0]["traceback"])
        self.assertEqual(crashed[0]["thread"], "CT2Trainer-test-thread")

    def test_faulthandler_is_armed_on_the_log(self):
        log = TrainerDebugLog(self.path, enabled=True, header={})
        log.arm_crash_reporting()
        self.assertTrue(faulthandler.is_enabled())
        # A native fatal signal would write to the same file; the session
        # close must not drop that sink.
        log.close()
        self.assertTrue(faulthandler.is_enabled())

    def test_crash_evidence_survives_session_close(self):
        # Field case: the session log is closed (engine torn down) and only
        # then the fatal event surfaces - the crash handle stays open.
        log = TrainerDebugLog(self.path, enabled=True, header={})
        log.arm_crash_reporting()
        log.close()
        try:
            raise ValueError("late escape after close")
        except ValueError as exc:
            sys.excepthook(type(exc), exc, exc.__traceback__)
        log.log("late-normal-event")  # must stay a no-op after close
        events = read_events(self.path)
        self.assertNotIn("late-normal-event", [e["event"] for e in events])
        crashed = [e for e in events if e["event"] == "trainer-crashed"]
        self.assertEqual(len(crashed), 1)
        self.assertIn("late escape after close", crashed[0]["error"])

    def test_hooks_installed_once_across_instances(self):
        first = TrainerDebugLog(self.path, enabled=True, header={})
        first.arm_crash_reporting()
        installed = sys.excepthook
        self.assertIsNot(installed, self._orig_excepthook)
        second = TrainerDebugLog(self.path, enabled=True, header={})
        second.arm_crash_reporting()
        self.assertIs(sys.excepthook, installed)  # not re-chained
        try:
            raise ValueError("after re-arm")
        except ValueError as exc:
            sys.excepthook(type(exc), exc, exc.__traceback__)
        events = read_events(self.path)
        self.assertEqual(
            len([e for e in events if e["event"] == "trainer-crashed"]), 1)
        first.close()
        second.close()

    def test_disabled_log_does_not_arm(self):
        log = TrainerDebugLog(self.path, enabled=False, header={})
        log.arm_crash_reporting()
        self.assertIs(sys.excepthook, self._orig_excepthook)
        self.assertIs(threading.excepthook, self._orig_thread_hook)
        self.assertFalse(self.path.exists())


@unittest.skipIf(tk is None or TrainerWindow is None,
                 'tkinter required for the real trainer window')
class PollGuardTests(unittest.TestCase):
    """The 250 ms poll tick must fail closed, never kill the process."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.shared = self.directory / "shared"
        self.cwd_dir = self.directory / "cwd"
        self.cwd_dir.mkdir()
        self.memory = FakeMemory()
        self.engine = None
        self.root = None

    def tearDown(self):
        if self.root is not None:
            try:
                self.root.destroy()
            except tk.TclError:
                pass
        if self.engine is not None and not self.engine.closed:
            try:
                self.engine.close()
            except Exception:
                pass

    def _start(self, plan: dict) -> TrainerEngine:
        with patch("pathlib.Path.cwd", return_value=self.cwd_dir):
            self.engine = TrainerEngine(plan, self.directory,
                                        lambda _n: self.memory, self.shared)
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)
        return self.engine

    @property
    def log_path(self) -> Path:
        return self.cwd_dir / LOG_NAME

    def test_poll_exception_blocks_and_keeps_window_alive(self):
        plan = compile_table(FIXTURE, PROCESS, debug_log=True)
        self._start(plan)
        self.root = tk.Tk()
        self.root.withdraw()
        window = TrainerWindow(self.root, self.engine)

        real_poll = self.engine.poll
        calls = {"n": 0}

        def boom_once():
            calls["n"] += 1
            if calls["n"] == 1:
                raise ValueError("synthetic poll escape")
            return real_poll()

        self.engine.poll = boom_once
        # Before 0.16.4 the ValueError propagated out of the Tk
        # after-callback and killed the windowed process without a single
        # log event.  Now the first tick fails closed:
        window.poll()
        self.assertTrue(self.engine.blocked, self.engine.status)
        self.assertTrue(self.engine.status.startswith("Writes blocked"))
        # The follow-up tick sees the blocked engine and stays quiet (the
        # engine's own early return, not another crash):
        window.poll()
        events = read_events(self.log_path)
        crashed = [e for e in events if e["event"] == "poll-crashed"]
        self.assertEqual(len(crashed), 1)
        self.assertIn("synthetic poll escape", crashed[0]["error"])
        self.assertIn("Traceback", crashed[0]["traceback"])
        blocked = [e for e in events if e["event"] == "engine-blocked"]
        self.assertEqual(len(blocked), 1)


class RestoreEntryStartTests(unittest.TestCase):
    """restore-entry-start marks the in-progress wish before its enable."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.shared = self.directory / "shared"
        self.cwd_dir = self.directory / "cwd"
        self.cwd_dir.mkdir()
        self.engines = []
        self.memory = None

    def tearDown(self):
        for engine in self.engines:
            if not engine.closed:
                try:
                    engine.close()
                except Exception:
                    pass

    def _start(self, plan: dict, memory: FakeMemory) -> TrainerEngine:
        with patch("pathlib.Path.cwd", return_value=self.cwd_dir):
            engine = TrainerEngine(plan, self.directory,
                                   lambda _n: memory, self.shared)
        self.engines.append(engine)
        engine.poll()
        self.assertTrue(engine.connected, engine.status)
        return engine

    def test_restore_marks_each_wish_start_before_enable(self):
        plan = compile_table(FIXTURE, PROCESS, debug_log=True)
        first = self._start(plan, FakeMemory())
        # Entry 0 registers the anchor (no byte change); entry 1 asserts and
        # writes at FixtureAnchor+0x14.  Both are persisted as saved wishes.
        first.toggle(0, True)
        first.toggle(1, True)
        self.assertTrue(first.close())
        self.memory = FakeMemory()
        second = self._start(plan, self.memory)
        # The saved wishes restored on the fresh attach: entry 1's byte is
        # rewritten exactly as the first session left it.
        self.assertEqual(self.memory.read(0x1014, 4), b"\x01\x00\x00\x00")

        events = read_events(self.cwd_dir / LOG_NAME)
        # Restrict to the second session (the second log-start header).
        starts = [i for i, e in enumerate(events)
                  if e["event"] == "log-start"]
        self.assertEqual(len(starts), 2)
        second_events = events[starts[1]:]
        entry_starts = {e["identifier"]: i for i, e in enumerate(second_events)
                        if e["event"] == "restore-entry-start"}
        restored = {e["identifier"]: i for i, e in enumerate(second_events)
                    if e["event"] == "wish-restored"}
        self.assertEqual(set(entry_starts), set(restored))
        for ident in restored:
            self.assertLess(entry_starts[ident], restored[ident])
        self.assertIn(1, entry_starts)
        self.assertEqual(second_events[entry_starts[1]]["label"],
                         "Pause ticks (disable to resume)")


if __name__ == "__main__":
    unittest.main()
