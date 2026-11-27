"""0.52.5 Great Circle field fix: scan-abort forensics in the debug log.

Field case 2026-11-24 (The Great Circle): the crashes land in the
steady-state idle window while the bounded rearm module scan is the
trainer's only target touch.  The 0.52.5 fix makes bounded scans abort
on the first transient read failure and record the abort context in
``memory.last_scan_diagnostics``; the engine now surfaces that context
as debug-log evidence so the next field session can show which scan
chunk died (or that no scan was in flight) when the target died:

- ``rearm-scan-start`` brackets every rearm attempt (identifier, label,
  attempt number, max, module scan range) before the attempt runs;
- the ``rearm-attempt`` end event carries ``scan_transient_abort``
  (address / offset / Win32 code / bytes read) when the attempt's own
  scan died on a read failure, or the completed scan's ``bytes_scanned``
  otherwise - restricted by an object-identity check to diagnostics
  records fresh from this attempt, so a stale abort from an earlier
  scan is never reported;
- the byte-patch ``_operations`` scan branch and the program-preflight
  scan path emit the named ``scan-transient-abort`` event for a fresh
  abort context and keep the plain ``scan-failed`` shape otherwise.

Evidence side only: no target operations, every log call is a no-op
when the plan's ``debug_log`` flag is off.
"""
from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from test_native_engine_code import Coordinator
from test_native_rearm import REARM_CT, RearmMemory
from ct2trainer.native.compiler import compile_table
from ct2trainer.native.debug_log import TrainerDebugLog
from ct2trainer.native.engine import TrainerEngine
from ct2trainer.native.memory import ProcessMemoryError

LOG_NAME = "ct2trainer-debug.log"


def read_events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    lines = [line for line in path.read_text(encoding="utf-8").splitlines()
             if line.strip()]
    return [json.loads(line) for line in lines]


def _abort_diagnostics(base: int) -> dict:
    return {
        "match_count": 0,
        "match_addresses": [],
        "module": "FixtureTarget.exe",
        "module_base": base,
        "bytes_scanned": 0x100,
        "aborted_at": hex(base + 0x100),
        "aborted_offset": "0x100",
        "aborted_win32": 299,
    }


class TransientAbortMemory(RearmMemory):
    """RearmMemory whose scan can die on a transient read (Win32 299)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.abort = False

    def scan_module(self, name, pattern):
        if self.abort:
            self.last_scan_diagnostics = _abort_diagnostics(self.base)
            raise ProcessMemoryError("ReadProcessMemory failed (Win32 error 299).")
        return super().scan_module(name, pattern)


class BytesDiagMemory(RearmMemory):
    """RearmMemory that adds the 0.52.5 ``bytes_scanned`` field to
    successful scan diagnostics (the real backend's new shape)."""

    def scan_module(self, name, pattern):
        address = super().scan_module(name, pattern)
        self.last_scan_diagnostics["bytes_scanned"] = len(self.data)
        return address


class RearmScanForensicsTests(unittest.TestCase):
    """rearm-scan-start bracket + scan_transient_abort on the end event."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.cwd = self.root / "cwd"
        self.cwd.mkdir()
        table = self.root / "rearm.ct"
        table.write_text(REARM_CT, encoding="utf-8")
        self.plan = compile_table(table, "FixtureTarget.exe", debug_log=True)
        self.memory = TransientAbortMemory()
        self.memory.plant()
        self.engine = None

    def tearDown(self):
        if self.engine is not None and not self.engine.closed:
            self.engine.close()

    def start(self):
        with patch("pathlib.Path.cwd", return_value=self.cwd):
            self.engine = TrainerEngine(
                self.plan, state_dir=self.root / "state",
                process_lock_dir=self.root / "shared",
                memory_factory=lambda name: self.memory,
                hook_coordinator=Coordinator())
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)
        return self.engine

    def arm(self, engine):
        """Arm entry 1 by failing its first enable (game still loading)."""
        engine.memory.unplant()
        try:
            engine.toggle(1, True)
            self.fail("expected the first enable to fail")
        except Exception:
            pass
        self.assertIn(1, engine.rearm)

    def test_rearm_attempt_reports_fresh_transient_abort(self):
        engine = self.start()
        self.arm(engine)
        self.memory.abort = True
        engine.rearm[1]["due"] = time.monotonic() - 1
        engine.poll()
        events = read_events(self.cwd / LOG_NAME)

        starts = [e for e in events if e["event"] == "rearm-scan-start"]
        self.assertEqual(len(starts), 1)
        start = starts[0]
        self.assertEqual(start["identifier"], 1)
        self.assertEqual(start["attempt"], 1)
        self.assertEqual(
            start["scan_range"],
            f"{hex(self.memory.base)}-{hex(self.memory.base + len(self.memory.data))}")
        # The start event precedes the matching end event.
        self.assertLess(events.index(start),
                        events.index([e for e in events
                                      if e["event"] == "rearm-attempt"][0]))

        attempts = [e for e in events if e["event"] == "rearm-attempt"]
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["result"], "ProcessMemoryError")
        self.assertEqual(
            attempts[0]["scan_transient_abort"],
            {"address": hex(self.memory.base + 0x100),
             "offset": "0x100",
             "win32": 299,
             "bytes_scanned": 0x100})

        aborts = [e for e in events if e["event"] == "scan-transient-abort"]
        self.assertEqual(len(aborts), 1)
        self.assertEqual(aborts[0]["entry_id"], 1)
        self.assertEqual(aborts[0]["transient_abort"],
                         attempts[0]["scan_transient_abort"])
        self.assertTrue(any(e["event"] == "scan-failed" for e in events))

        # The non-ScanMiss failure drops the arm and records the error.
        self.assertNotIn(1, engine.rearm)
        self.assertIn("Win32 error 299", engine.entry_errors[1])

    def test_stale_abort_diagnostics_are_not_reported(self):
        engine = self.start()
        # Simulate an abort recorded by an earlier scan; the plain
        # ScanMiss rearm must not pick it up (identity check).
        self.memory.last_scan_diagnostics = _abort_diagnostics(self.memory.base)
        self.arm(engine)
        engine.rearm[1]["due"] = time.monotonic() - 1
        engine.poll()
        events = read_events(self.cwd / LOG_NAME)
        attempts = [e for e in events if e["event"] == "rearm-attempt"]
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["result"], "ScanMiss")
        self.assertNotIn("scan_transient_abort", attempts[0])
        self.assertNotIn("bytes_scanned", attempts[0])
        self.assertFalse(any(e["event"] == "scan-transient-abort"
                             for e in events))

    def test_rearm_success_reports_bytes_scanned(self):
        engine = self.start()
        # Swap in the diagnostics-shape memory for the successful attempt.
        bytes_memory = BytesDiagMemory()
        bytes_memory.plant()
        engine.memory = bytes_memory
        engine.memory_factory = lambda name: bytes_memory
        self.arm(engine)
        # The game "finishes loading": the pattern reappears, so the
        # rearm attempt now succeeds (house pattern per
        # test_native_rearm.py).
        engine.memory.plant()
        engine.rearm[1]["due"] = time.monotonic() - 1
        engine.poll()
        events = read_events(self.cwd / LOG_NAME)
        attempts = [e for e in events if e["event"] == "rearm-attempt"]
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["result"], "ok")
        self.assertEqual(attempts[0]["bytes_scanned"], len(bytes_memory.data))
        self.assertNotIn("scan_transient_abort", attempts[0])
        self.assertEqual(
            [e["event"] for e in events
             if e["event"] in ("rearm-scan-start", "rearm-succeeded")],
            ["rearm-scan-start", "rearm-succeeded"])


class OperationsScanForensicsTests(unittest.TestCase):
    """The byte-patch _operations scan branch (unit level)."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.log_path = Path(self.temporary.name) / LOG_NAME

    def bare_engine(self):
        engine = TrainerEngine.__new__(TrainerEngine)
        engine.memory = Mock()
        engine.symbols = {}
        engine.local_symbols = {}
        engine.plan = {"trainer_id": "a" * 16, "process_name": "owned.exe"}
        engine.debug_log = TrainerDebugLog(self.log_path, enabled=True)
        return engine

    def _entry(self):
        return {"id": 1, "enable": [
            {"op": "scan", "symbol": "L", "module": "owned.exe",
             "pattern": "41 42"},
        ]}

    def test_fresh_abort_emits_the_named_event(self):
        engine = self.bare_engine()
        memory = engine.memory
        memory.last_scan_diagnostics = None

        def aborting_scan(module, pattern):
            memory.last_scan_diagnostics = {
                "match_count": 0, "match_addresses": [],
                "module": module, "module_base": 0x1000,
                "bytes_scanned": 0x100,
                "aborted_at": "0x1100", "aborted_offset": "0x100",
                "aborted_win32": 299,
            }
            raise ProcessMemoryError(
                "ReadProcessMemory failed (Win32 error 299).")

        memory.scan_module.side_effect = aborting_scan
        with self.assertRaises(ProcessMemoryError):
            engine._operations(self._entry(), "enable")
        events = read_events(self.log_path)
        aborts = [e for e in events if e["event"] == "scan-transient-abort"]
        self.assertEqual(len(aborts), 1)
        self.assertEqual(aborts[0]["entry_id"], 1)
        self.assertEqual(aborts[0]["transient_abort"],
                         {"address": "0x1100", "offset": "0x100",
                          "win32": 299, "bytes_scanned": 0x100})
        self.assertEqual(
            [e["event"] for e in events if e["event"] == "scan-failed"],
            ["scan-failed"])

    def test_stale_diagnostics_emit_no_abort_event(self):
        engine = self.bare_engine()
        memory = engine.memory
        # A success-shaped diagnostics record from an earlier scan is
        # left untouched by the failing scan below.
        memory.last_scan_diagnostics = {
            "match_count": 1, "match_addresses": [0x14000],
            "module": "owned.exe", "module_base": 0x1000,
            "bytes_scanned": 0x100,
        }
        memory.scan_module.side_effect = ProcessMemoryError(
            "ReadProcessMemory failed (Win32 error 5).")
        with self.assertRaises(ProcessMemoryError):
            engine._operations(self._entry(), "enable")
        events = read_events(self.log_path)
        self.assertFalse(any(e["event"] == "scan-transient-abort"
                             for e in events))
        self.assertEqual(
            [e["event"] for e in events if e["event"] == "scan-failed"],
            ["scan-failed"])

    def test_scan_success_log_shape_is_unchanged(self):
        engine = self.bare_engine()
        memory = engine.memory
        memory.scan_module.return_value = 0x14000
        memory.last_scan_diagnostics = {
            "match_count": 1, "match_addresses": [0x14000],
            "module": "owned.exe", "module_base": 0x1000,
        }
        memory.module.return_value = (0x1000, 4096)
        symbols, registered, patches = \
            engine._operations(self._entry(), "enable")
        self.assertEqual(symbols, {"l": 0x14000})
        self.assertEqual(registered, set())
        self.assertEqual(patches, [])
        events = [e for e in read_events(self.log_path)
                  if e["event"] == "scan"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["address"], "0x14000")
        self.assertEqual(events[0]["entry_id"], 1)


if __name__ == "__main__":
    unittest.main()
