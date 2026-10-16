"""Tests for the optional runtime debug logging (plan flag ``debug_log``).

Covers: converter flag default/opt-in, plan validation, the log writer
(JSON lines, header, error+traceback capture, disabled no-op, close),
and engine integration (attach success/failure, scan failure, full
toggle/value/close cycle, no file without the flag).
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ct2trainer.native.compiler import (NativeCompileError, compile_table,
                                        validate_plan)
from ct2trainer.native.debug_log import (TrainerDebugLog, create_debug_log,
                                         default_log_path)
from ct2trainer.native.engine import NativeRuntimeError, TrainerEngine

from test_native_engine import FakeMemory

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "windows" / "fixture_target" / "fixture.ct"
LOG_NAME = "ct2trainer-debug.log"


def read_events(path: Path) -> list[dict]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    events = [json.loads(line) for line in lines]
    for event in events:
        self_check = isinstance(event.get("ts"), str) and isinstance(event.get("event"), str)
        if not self_check:
            raise AssertionError("malformed log line: %r" % line)
    return events


class PlanFlagTests(unittest.TestCase):
    def test_default_plan_has_no_debug_log_flag(self):
        plan = compile_table(FIXTURE, "FixtureTarget.exe")
        self.assertNotIn("debug_log", plan)

    def test_enabled_flag_is_set_and_validates(self):
        plan = compile_table(FIXTURE, "FixtureTarget.exe", debug_log=True)
        self.assertIs(plan["debug_log"], True)
        validate_plan(plan)

    def test_trainer_id_is_stable_across_the_flag(self):
        plain = compile_table(FIXTURE, "FixtureTarget.exe")
        logged = compile_table(FIXTURE, "FixtureTarget.exe", debug_log=True)
        self.assertEqual(plain["trainer_id"], logged["trainer_id"])
        self.assertEqual(plain["table_sha256"], logged["table_sha256"])

    def test_malformed_flag_is_rejected(self):
        plan = compile_table(FIXTURE, "FixtureTarget.exe", debug_log=True)
        plan["debug_log"] = "yes"
        with self.assertRaisesRegex(NativeCompileError, "debug_log"):
            validate_plan(plan)


class LogWriterTests(unittest.TestCase):
    def test_disabled_log_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "debug.log"
            log = TrainerDebugLog(path, enabled=False, header={"pid": 1})
            log.log("anything", detail="x")
            try:
                raise ValueError("injected")
            except ValueError as exc:
                log.error("boom", exc)
            log.close()
            self.assertFalse(path.exists())

    def test_enabled_log_writes_json_lines_with_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "debug.log"
            log = TrainerDebugLog(path, enabled=True,
                                  header={"pid": 42, "trainer_id": "abc123"})
            log.log("scan", address="0x1000", pattern="AA BB")
            try:
                raise ValueError("injected failure")
            except ValueError as exc:
                log.error("scan-failed", exc, pattern="AA BB")
            log.close()
            events = read_events(path)
        self.assertEqual([e["event"] for e in events],
                         ["log-start", "scan", "scan-failed"])
        self.assertEqual(events[0]["trainer_id"], "abc123")
        self.assertEqual(events[0]["pid"], 42)
        self.assertEqual(events[0]["log_path"], str(path))
        self.assertEqual(events[1]["address"], "0x1000")
        self.assertIn("ValueError", events[2]["error"])
        self.assertIn("injected failure", events[2]["error"])
        self.assertIn("Traceback", events[2]["traceback"])

    def test_closed_log_writes_nothing_more(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "debug.log"
            log = TrainerDebugLog(path, enabled=True, header={})
            before = len(path.read_text(encoding="utf-8").splitlines())
            log.close()
            log.log("late-event")
            self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()), before)
            self.assertNotIn("late-event",
                             path.read_text(encoding="utf-8"))

    def test_default_log_path_in_source_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("pathlib.Path.cwd", return_value=Path(tmp)):
                self.assertEqual(default_log_path(), Path(tmp) / LOG_NAME)


class EngineDebugLogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.shared = self.directory / "shared"
        self.cwd_dir = self.directory / "cwd"
        self.cwd_dir.mkdir()
        self.memory = FakeMemory()
        self.engine = None

    def tearDown(self):
        if self.engine is not None and not self.engine.closed:
            self.engine.close()
        self.temp.cleanup()

    def _start(self, plan: dict, attach: bool = True,
               factory=None) -> TrainerEngine:
        with patch("pathlib.Path.cwd", return_value=self.cwd_dir):
            self.engine = TrainerEngine(plan, self.directory,
                                        factory or (lambda _n: self.memory),
                                        self.shared)
        if attach:
            self.engine.poll()
        return self.engine

    @property
    def log_path(self) -> Path:
        return self.cwd_dir / LOG_NAME

    def test_full_cycle_is_logged(self):
        plan = compile_table(FIXTURE, "FixtureTarget.exe", debug_log=True)
        engine = self._start(plan)
        self.assertTrue(engine.connected, engine.status)
        engine.toggle(1, True)
        engine.set_value(2, "42")
        self.assertTrue(engine.close())
        events = read_events(self.log_path)
        names = [e["event"] for e in events]
        for expected in ("log-start", "engine-init", "attached",
                         "restore-start", "toggle", "scan",
                         "symbol-registered", "assert", "patch-planned",
                         "patch-written", "toggle-ok", "state-save",
                         "value-write", "value-write-ok", "engine-close"):
            self.assertIn(expected, names)
        self.assertEqual(events[0]["event"], "log-start")
        self.assertEqual(events[-1]["event"], "engine-close")
        scan = next(e for e in events if e["event"] == "scan")
        self.assertEqual(scan["symbol"], "FixtureAnchor")
        self.assertEqual(scan["module"], "FixtureTarget.exe")
        self.assertTrue(scan["address"].startswith("0x"))
        attached = next(e for e in events if e["event"] == "attached")
        self.assertEqual(attached["pid"], self.memory.pid)
        self.assertEqual(attached["pointer_size"], 8)
        value = next(e for e in events if e["event"] == "value-write-ok")
        self.assertEqual(value["identifier"], 2)
        self.assertIn("display", value)

    def test_no_log_file_when_flag_absent(self):
        plan = compile_table(FIXTURE, "FixtureTarget.exe")
        engine = self._start(plan)
        engine.toggle(1, True)
        self.assertTrue(engine.close())
        self.assertFalse(self.log_path.exists())

    def test_attach_failure_is_logged(self):
        plan = compile_table(FIXTURE, "FixtureTarget.exe", debug_log=True)

        def factory(name):
            raise OSError("Expected one exact FixtureTarget.exe process; found 0.")

        engine = self._start(plan, attach=False, factory=factory)
        engine.poll()
        self.assertFalse(engine.connected)
        self.assertIn("found 0", engine.status)
        events = read_events(self.log_path)
        failed = [e for e in events if e["event"] == "attach-attempt-failed"]
        self.assertEqual(len(failed), 1)
        self.assertIn("found 0", failed[0]["error"])
        self.assertIn("Traceback", failed[0]["traceback"])

    def test_scan_failure_is_logged_with_pattern(self):
        plan = compile_table(FIXTURE, "FixtureTarget.exe", debug_log=True)
        for entry in plan["entries"]:
            if entry["id"] == 0:
                for op in entry.get("enable", ()):
                    if op.get("op") == "scan":
                        op["pattern"] = "DE AD BE EF"
        engine = self._start(plan)
        with self.assertRaises(NativeRuntimeError):
            engine.toggle(1, True)
        events = read_events(self.log_path)
        failed = [e for e in events if e["event"] == "scan-failed"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["pattern"], "DE AD BE EF")
        self.assertIn("Traceback", failed[0]["traceback"])
        toggles = [e for e in events if e["event"] == "toggle-failed"]
        self.assertEqual(len(toggles), 1)
        self.assertEqual(toggles[0]["identifier"], 1)

    def test_assert_failure_logs_expected_and_actual(self):
        plan = compile_table(FIXTURE, "FixtureTarget.exe", debug_log=True)
        engine = self._start(plan)
        self.memory.data[0x14] = 0x88  # break the FixtureAnchor+14 assertion
        with self.assertRaises(NativeRuntimeError):
            engine.toggle(1, True)
        events = read_events(self.log_path)
        failed = [e for e in events if e["event"] == "assert-failed"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["expected"], "00 00 00 00")
        self.assertEqual(failed[0]["actual"], "88 00 00 00")

    def test_state_save_failure_blocks_and_logs(self):
        plan = compile_table(FIXTURE, "FixtureTarget.exe", debug_log=True)
        engine = self._start(plan)

        def broken_save(desired):
            raise OSError("state disk full")

        engine.store.save = broken_save
        with self.assertRaises(NativeRuntimeError):
            engine.toggle(1, True)
        self.assertTrue(engine.blocked)
        events = read_events(self.log_path)
        failed = [e for e in events if e["event"] == "state-save-failed"]
        self.assertEqual(len(failed), 1)
        self.assertIn("state disk full", failed[0]["error"])
        self.assertTrue(any(e["event"] == "engine-blocked" for e in events))


if __name__ == "__main__":
    unittest.main()
