"""TGC field fix (0.43): transient target-memory reads must not block.

Field case 2026-11-11 (Indiana Jones and the Great Circle, 0.41):
  R1 - the module snapshot failed with Win32 299 (ERROR_INTERNAL_ERROR)
       immediately after the first attach while the game was still loading
       its DLLs; 299 was not in the snapshot retry set, so the engine
       blocked with no retry.
  R2 - a transient 299 read during the periodic _check_patches was wrapped
       as "hook receipt changed" -> engine blocked.  A failed read is not an
       observed change.

Fixes under test:
  F1  (memory.py): 299 joins the snapshot transient retry set; every
       _windows_error carries a machine-readable win32_code; the public
       TRANSIENT_MEMORY_ERRORS set + is_transient_memory_error classify a
       read failure as "cannot verify right now" (never "bytes changed").
  F2  (engine.py): a transient read in _check_patches skips the
       verification tick (bounded skip streak, deduped patch-verify-skipped
       event); a persistent streak blocks fail-closed; a real mismatch and a
       non-transient failure still block immediately; a confirmed (re-)
       attach resets the streak.
  F2b (hooks.py): a transient guard read re-raises instead of marking the
       manager uncertain (which would be a permanent fail-closed state).
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_native_engine import FakeMemory
from test_native_engine_code import Coordinator
from test_native_hooks import _Memory, _Coordinator, _block
from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import VERIFY_SKIP_STREAK_LIMIT, TrainerEngine
from ct2trainer.native.hooks import HookManager, HookUncertain
import ct2trainer.native.memory as memory_module
from ct2trainer.native.memory import ProcessMemoryError, ScanMiss

LOG_NAME = "ct2trainer-debug.log"

TGC_CT = '''<CheatTable CheatEngineTableVersion="45"><CheatEntries>
<CheatEntry><ID>1</ID><Description>"tgc aob entry"</Description>
<VariableType>Auto Assembler Script</VariableType><AssemblerScript>[ENABLE]
aobscanmodule(TgcAnchor,FixtureTarget.exe,AB CD EF 01)
registersymbol(TgcAnchor)
TgcAnchor+1:
 db 90

[DISABLE]
TgcAnchor+1:
 db CD
unregistersymbol(TgcAnchor)</AssemblerScript></CheatEntry>
</CheatEntries></CheatTable>'''


def _memory_error(code: int) -> ProcessMemoryError:
    exc = ProcessMemoryError(f"ReadProcessMemory failed (Win32 error {code}).")
    exc.win32_code = code
    return exc


class TransientClassificationTests(unittest.TestCase):
    def test_transient_codes_are_recognized(self):
        for code in (299, 119, 1116, 24):
            with self.subTest(code=code):
                self.assertTrue(
                    memory_module.is_transient_memory_error(_memory_error(code)))

    def test_non_transient_codes_are_not_recognized(self):
        for code in (5, 4, 0, 18):
            with self.subTest(code=code):
                self.assertFalse(
                    memory_module.is_transient_memory_error(_memory_error(code)))

    def test_error_without_win32_code_is_not_transient(self):
        self.assertFalse(memory_module.is_transient_memory_error(
            ProcessMemoryError("ReadProcessMemory returned a partial result.")))

    def test_non_memory_error_is_not_transient(self):
        self.assertFalse(memory_module.is_transient_memory_error(ValueError("x")))
        self.assertFalse(memory_module.is_transient_memory_error(OSError("y")))

    def test_scan_miss_is_not_transient(self):
        self.assertFalse(memory_module.is_transient_memory_error(
            ScanMiss("The module byte pattern was not found in readable committed memory.")))

    def test_windows_error_carries_win32_code(self):
        with patch('ctypes.get_last_error', return_value=299, create=True):
            exc = memory_module._windows_error("ReadProcessMemory")
        self.assertIsInstance(exc, ProcessMemoryError)
        self.assertEqual(exc.win32_code, 299)

    def test_transient_memory_errors_is_the_documented_set(self):
        self.assertEqual(memory_module.TRANSIENT_MEMORY_ERRORS, {299, 119, 1116, 24})


class TgcMemory(FakeMemory):
    """FakeMemory with a plantable AOB anchor and a planted read failure."""

    PATTERN = bytes.fromhex("ABCDEF01")
    PATTERN_OFFSET = 0x40

    def __init__(self, pid=123, creation_time=456):
        super().__init__(pid=pid, creation_time=creation_time)
        self.read_error = None

    @property
    def identity(self):
        return self.pid, self.creation_time

    def is_executable(self, address, size):
        return False

    def plant(self):
        self.data[self.PATTERN_OFFSET:self.PATTERN_OFFSET + 4] = self.PATTERN

    def read(self, address, size):
        if self.read_error is not None:
            raise self.read_error
        return super().read(address, size)


class TgcEngineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.cwd = self.root / "cwd"
        self.cwd.mkdir()
        table = self.root / "tgc.ct"
        table.write_text(TGC_CT, encoding="utf-8")
        self.plan = compile_table(table, "FixtureTarget.exe", debug_log=True)
        self.memory = TgcMemory()
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

    def enable(self, engine):
        self.assertTrue(engine.toggle(1, True), engine.error)

    def events(self):
        log = self.cwd / LOG_NAME
        if not log.exists():
            return []
        return [json.loads(line) for line in
                log.read_text(encoding="utf-8").splitlines() if line.strip()]

    def skipped_events(self):
        return [e for e in self.events() if e["event"] == "patch-verify-skipped"]

    def test_verified_tick_has_no_skip_streak(self):
        engine = self.start()
        self.enable(engine)
        self.assertIn(1, engine.applied)
        engine.poll()
        self.assertFalse(engine.blocked)
        self.assertEqual(engine._verify_skip_streak, 0)
        self.assertIsNone(engine._last_verify_skip)
        self.assertEqual(self.skipped_events(), [])

    def test_transient_read_skips_verification_tick_without_blocking(self):
        engine = self.start()
        self.enable(engine)
        self.memory.read_error = _memory_error(299)
        engine.poll()
        self.assertFalse(engine.blocked)
        self.assertEqual(engine._verify_skip_streak, 1)
        self.assertEqual(engine._last_verify_skip,
                         "ReadProcessMemory failed (Win32 error 299).")
        skipped = self.skipped_events()
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0]["streak"], 1)
        self.assertEqual(skipped[0]["limit"], VERIFY_SKIP_STREAK_LIMIT)
        self.assertIn("299", skipped[0]["error"])
        self.memory.read_error = None

    def test_transient_skip_is_deduped_while_the_cause_persists(self):
        engine = self.start()
        self.enable(engine)
        self.memory.read_error = _memory_error(299)
        for _ in range(5):
            engine.poll()
        self.assertEqual(engine._verify_skip_streak, 5)
        self.assertFalse(engine.blocked)
        skipped = self.skipped_events()
        # one event for the whole persistent streak (deduped by cause)
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0]["streak"], 1)
        self.memory.read_error = None

    def test_verified_tick_resets_the_skip_streak(self):
        engine = self.start()
        self.enable(engine)
        self.memory.read_error = _memory_error(299)
        engine.poll()
        self.assertEqual(engine._verify_skip_streak, 1)
        self.memory.read_error = None
        engine.poll()
        self.assertEqual(engine._verify_skip_streak, 0)
        self.assertIsNone(engine._last_verify_skip)
        # a fresh transient after the reset reports again
        self.memory.read_error = _memory_error(299)
        engine.poll()
        self.assertEqual(len(self.skipped_events()), 2)
        self.memory.read_error = None

    def test_persistent_transient_read_blocks_fail_closed(self):
        engine = self.start()
        self.enable(engine)
        self.memory.read_error = _memory_error(299)
        for i in range(VERIFY_SKIP_STREAK_LIMIT - 1):
            engine.poll()
            self.assertFalse(engine.blocked)
            self.assertEqual(engine._verify_skip_streak, i + 1)
        engine.poll()
        self.assertTrue(engine.blocked)
        self.assertIn("transient read errors for 30 consecutive ticks",
                      engine.error)

    def test_real_mismatch_blocks_immediately(self):
        engine = self.start()
        self.enable(engine)
        self.memory.data[0x41] = 0xFF  # external change of the patched byte
        engine.poll()
        self.assertTrue(engine.blocked)
        self.assertIn("changed externally", engine.error)
        self.assertEqual(engine._verify_skip_streak, 0)

    def test_non_transient_read_failure_blocks_immediately(self):
        engine = self.start()
        self.enable(engine)
        self.memory.read_error = _memory_error(5)  # access denied, not transient
        engine.poll()
        self.assertTrue(engine.blocked)
        self.assertNotIn("transient read errors", engine.error)
        self.assertIn("Win32 error 5", engine.error)
        self.assertEqual(engine._verify_skip_streak, 0)

    def test_skip_streak_resets_on_reattach(self):
        engine = self.start()
        self.enable(engine)
        self.memory.read_error = _memory_error(299)
        for _ in range(5):
            engine.poll()
        self.assertEqual(engine._verify_skip_streak, 5)
        self.memory.read_error = None
        self.memory.alive = False
        engine.poll()
        self.assertIsNone(engine.memory)
        # A fresh game process has the original byte back (the fake memory
        # persists, so simulate the restart here).
        self.memory.data[0x41] = 0xCD
        self.memory.alive = True
        engine.poll()
        self.assertTrue(engine.connected, engine.status)
        self.assertEqual(engine._verify_skip_streak, 0)
        self.assertIsNone(engine._last_verify_skip)


def _raise_error(code: int):
    def _read(address, size):
        raise _memory_error(code)
    return _read


class TgcGuardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "hook.json"
        self.memory = _Memory()
        self.coordinator = _Coordinator()
        self.manager = HookManager(self.memory, self.path, self.coordinator,
                                   "test-activation")

    def _enabled_manager(self):
        base = self.manager.allocate("newmem", 32, near=0x1000)
        blocks = [_block(base, b"\xB8\x02\x00\x00\x00\xC3", bytes(6), True),
                  _block(0x1000, b"\xE9\xFB\xEF\x00\x00", self.memory.data[0x1000])]
        self.manager.stage(blocks, {"newmem": base})
        self.manager.publish()
        self.assertEqual(self.manager.state, "enabled")

    def test_transient_guard_read_does_not_mark_manager_uncertain(self):
        self._enabled_manager()
        original_read = self.memory.read
        self.memory.read = _raise_error(299)
        try:
            with self.assertRaises(ProcessMemoryError):
                self.manager._check_allocation_guards()
        finally:
            self.memory.read = original_read
        self.assertFalse(self.manager.uncertain)
        self.assertEqual(self.manager.state, "enabled")

    def test_non_transient_guard_read_still_marks_manager_uncertain(self):
        self._enabled_manager()
        original_read = self.memory.read
        self.memory.read = _raise_error(5)
        try:
            with self.assertRaises(HookUncertain):
                self.manager._check_allocation_guards()
        finally:
            self.memory.read = original_read
        self.assertTrue(self.manager.uncertain)


if __name__ == "__main__":
    unittest.main()
