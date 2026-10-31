"""Bounded automatic re-arm of ScanMiss enable failures (0.21).

Field case 2026-10-31 (Fallout 4 under Proton): while the game is still
loading, the targeted code is not present in readable committed memory,
so the AOB scan fails with ScanMiss and the entry stays failed until the
user taps it again.  The engine now re-arms such entries: the same full
enable path re-runs every REARM_INTERVAL_SECONDS, up to
REARM_MAX_ATTEMPTS attempts per attach session.  The re-arm set survives
target exit -> re-attach within one trainer session; the attempt budget
resets on every confirmed (re-)attach.  Value-read and non-ScanMiss
failures are never armed (the plain-failed contract stands).  User
actions: row-menu "Try again" (immediate enable + budget reset) and the
header "Re-attach" (engine teardown + waiting attach cycle).  Debug
events: rearm-scheduled / rearm-attempt / rearm-succeeded /
rearm-exhausted and reattach-requested / reattach-detached /
reattach-done / reattach-failed.

Engine scenarios:
  1. manual toggle failure (ScanMiss) arms; budget fresh
  2. executor success: wish persisted, all failure state cleared
  3. executor ScanMiss consumes one attempt, cadence pushed
  4. budget exhaustion stops the automatic retries
  5. re-arm survives detach; budget resets on re-attach; immediate retry
  6. toggle OFF disarms; manual success clears (rearm-succeeded once)
  7. non-ScanMiss failure never arms; drops a pending arm
  8. try_again refusals, budget reset, success path
  9. wish restore failure arms without consuming the budget; no
     same-tick double attempt
 10. reattach(): teardown, events, blocked refusal, reattach-failed
     dedupe per request

UI layer (pure row model): rearm_sublabel, try_again_available,
RowSnapshot validation of the new fields, build_rows sublabel
integration.
"""
from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from test_native_engine import FakeMemory
from test_native_engine_code import Coordinator
from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import (REARM_INTERVAL_SECONDS,
                                      REARM_MAX_ATTEMPTS, NativeRuntimeError,
                                      TrainerEngine)
from ct2trainer.native.memory import ScanMiss
from ct2trainer.native.ui_rows import (ROW_SWITCH, RowModelError, RowSnapshot,
                                       build_rows, rearm_sublabel,
                                       try_again_available)

LOG_NAME = "ct2trainer-debug.log"

# Entry 1: aobscanmodule anchor (pattern AB CD EF 01 at module offset
# 0x40; the patch byte is anchor+1 = base+0x41, original byte 0xCD).
# CheatCodes record: absolute 0x1048 (offset 0x48), Before=AB, Actual=CD;
# the live byte is 0x00, so enable refuses with the named
# code-patch-target-changed refusal (non-ScanMiss, zero writes).
REARM_CT = '''<CheatTable CheatEngineTableVersion="45"><CheatEntries>
<CheatEntry><ID>1</ID><Description>"rearm aob entry"</Description>
<VariableType>Auto Assembler Script</VariableType><AssemblerScript>[ENABLE]
aobscanmodule(ReArmAnchor,FixtureTarget.exe,AB CD EF 01)
registersymbol(ReArmAnchor)
ReArmAnchor+1:
 db 90

[DISABLE]
ReArmAnchor+1:
 db CD
unregistersymbol(ReArmAnchor)</AssemblerScript></CheatEntry>
</CheatEntries>
<CheatCodes><CodeEntry><Description>code patch changed</Description><ModuleName></ModuleName><ModuleNameOffset></ModuleNameOffset><AddressString>1048</AddressString><Address></Address><Before>AB</Before><Actual>CD</Actual><After></After></CodeEntry></CheatCodes>
</CheatTable>'''


class RearmMemory(FakeMemory):
    """FakeMemory with real ScanMiss semantics and a plantable pattern.

    The engine only arms on the named ScanMiss refusal, so the fake must
    raise the real ScanMiss on a zero-match scan (the plain FakeMemory
    raises OSError).  plant()/unplant() model the game finishing or
    (re)starting its load.
    """

    PATTERN = bytes.fromhex("ABCDEF01")
    PATTERN_OFFSET = 0x40

    def __init__(self, pid=123, creation_time=456):
        super().__init__(pid=pid, creation_time=creation_time)
        self.scan_calls = 0

    @property
    def identity(self):
        return self.pid, self.creation_time

    def is_executable(self, address, size):
        return False

    def plant(self):
        """The game finished loading: the pattern is in readable memory."""
        self.data[self.PATTERN_OFFSET:self.PATTERN_OFFSET + 4] = self.PATTERN

    def unplant(self):
        """The game is (re)loading: the pattern is not readable."""
        self.data[self.PATTERN_OFFSET:self.PATTERN_OFFSET + 4] = b"\x00" * 4

    def scan_module(self, name, pattern):
        self.scan_calls += 1
        self.module(name)
        raw = bytes.fromhex(pattern.replace(" ", ""))
        offsets, cursor = [], 0
        while True:
            found = self.data.find(raw, cursor)
            if found < 0:
                break
            offsets.append(found)
            cursor = found + 1
        if not offsets:
            raise ScanMiss(
                "The module byte pattern was not found in readable committed memory.")
        self.last_scan_diagnostics = {
            "match_count": len(offsets),
            "match_addresses": [self.base + o for o in offsets],
            "module": name,
            "module_base": self.base,
        }
        return self.base + offsets[0]


class RearmEngineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.cwd = self.root / "cwd"
        self.cwd.mkdir()
        table = self.root / "rearm.ct"
        table.write_text(REARM_CT, encoding="utf-8")
        self.plan = compile_table(table, "FixtureTarget.exe", debug_log=True)
        self.memory = RearmMemory()
        self.memory.plant()
        self.engine = None

    def tearDown(self):
        if self.engine is not None and not self.engine.closed:
            self.engine.close()

    def start(self, attach=True):
        with patch("pathlib.Path.cwd", return_value=self.cwd):
            self.engine = TrainerEngine(
                self.plan, state_dir=self.root / "state",
                process_lock_dir=self.root / "shared",
                memory_factory=lambda name: self.memory,
                hook_coordinator=Coordinator())
        if attach:
            self.engine.poll()
            self.assertTrue(self.engine.connected, self.engine.status)
        return self.engine

    def detach(self, engine):
        self.memory.alive = False
        engine.poll()
        self.assertIsNone(engine.memory)

    def reattach(self, engine):
        self.memory.alive = True
        engine.poll()
        self.assertTrue(engine.connected, engine.status)

    def events(self):
        log = self.cwd / LOG_NAME
        if not log.exists():
            return []
        return [json.loads(line) for line in
                log.read_text(encoding="utf-8").splitlines() if line.strip()]

    def event(self, name, identifier=None):
        return [e for e in self.events() if e["event"] == name
                and (identifier is None or e.get("identifier") == identifier)]

    def arm(self, engine, identifier=1):
        """Arm entry 1 by failing its first enable (game still loading)."""
        self.memory.unplant()
        with self.assertRaises(NativeRuntimeError):
            engine.toggle(identifier, True)
        self.assertIn(identifier, engine.rearm)
        return engine.rearm[identifier]

    def test_scan_miss_toggle_arms_with_fresh_budget(self):
        engine = self.start()
        arm = self.arm(engine)
        self.assertEqual(arm["attempts"], 0)
        self.assertEqual(arm["max"], REARM_MAX_ATTEMPTS)
        self.assertEqual(arm["last"], "ScanMiss")
        self.assertFalse(arm["exhausted"])
        now = time.monotonic()
        self.assertGreaterEqual(arm["due"], now + REARM_INTERVAL_SECONDS - 1)
        self.assertIn(1, engine.enable_failures)
        self.assertIn(1, engine.entry_errors)
        self.assertNotIn(1, engine.applied)
        self.assertNotIn(1, engine.desired)
        self.assertFalse(engine.blocked)
        self.assertTrue(self.event("rearm-scheduled", 1))
        self.assertEqual(self.event("rearm-attempt", 1), [])

    def test_executor_success_persists_wish_and_clears_state(self):
        engine = self.start()
        self.arm(engine)
        self.memory.plant()
        engine.rearm[1]["due"] = time.monotonic() - 1
        engine.poll()
        self.assertIn(1, engine.applied)
        self.assertIn(1, engine.desired)
        self.assertNotIn(1, engine.rearm)
        self.assertNotIn(1, engine.enable_failures)
        self.assertNotIn(1, engine.entry_errors)
        self.assertEqual(self.memory.read(0x1041, 1), b"\x90")
        self.assertEqual(engine.status,
                         "rearm aob entry: re-armed and enabled (attempt 1)")
        state = json.loads(
            (self.root / "state" / "state.json").read_text(encoding="utf-8"))
        self.assertIn(1, state["payload"]["desired"])
        attempts = self.event("rearm-attempt", 1)
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["result"], "ok")
        self.assertEqual(attempts[0]["attempt"], 1)
        self.assertEqual(attempts[0]["max"], REARM_MAX_ATTEMPTS)
        self.assertTrue(self.event("rearm-succeeded", 1))

    def test_executor_scan_miss_consumes_one_attempt_and_pushes_due(self):
        engine = self.start()
        self.arm(engine)
        scans_before = self.memory.scan_calls
        engine.rearm[1]["due"] = time.monotonic() - 1
        engine.poll()
        self.assertNotIn(1, engine.applied)
        self.assertIn(1, engine.rearm)
        arm = engine.rearm[1]
        self.assertEqual(arm["attempts"], 1)
        self.assertFalse(arm["exhausted"])
        now = time.monotonic()
        self.assertGreaterEqual(arm["due"], now + REARM_INTERVAL_SECONDS - 1)
        self.assertGreater(self.memory.scan_calls, scans_before)
        self.assertIn(1, engine.enable_failures)
        self.assertNotIn(1, engine.desired)
        attempts = self.event("rearm-attempt", 1)
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["result"], "ScanMiss")
        self.assertEqual(attempts[0]["attempt"], 1)

    def test_executor_exhausts_the_budget_then_stops(self):
        engine = self.start()
        self.arm(engine)
        engine.rearm[1]["attempts"] = REARM_MAX_ATTEMPTS - 1
        engine.rearm[1]["due"] = time.monotonic() - 1
        engine.poll()
        arm = engine.rearm[1]
        self.assertEqual(arm["attempts"], REARM_MAX_ATTEMPTS)
        self.assertTrue(arm["exhausted"])
        self.assertIsNone(arm["due"])
        self.assertIn(1, engine.enable_failures)
        exhausted = self.event("rearm-exhausted", 1)
        self.assertEqual(len(exhausted), 1)
        self.assertEqual(exhausted[0]["attempts"], REARM_MAX_ATTEMPTS)
        # The exhausted budget is spent: no further automatic attempts,
        # even if the deadline is forced into the past.
        scans_before = self.memory.scan_calls
        engine.rearm[1]["due"] = time.monotonic() - 1
        engine.poll()
        self.assertEqual(self.memory.scan_calls, scans_before)
        self.assertNotIn(1, engine.applied)

    def test_rearm_survives_detach_and_budget_resets_on_reattach(self):
        engine = self.start()
        self.arm(engine)
        engine.rearm[1]["attempts"] = 3
        self.detach(engine)
        self.assertIn(1, engine.rearm)  # survives the target exit
        self.assertEqual(engine.rearm[1]["attempts"], 3)
        self.reattach(engine)
        arm = engine.rearm[1]
        self.assertEqual(arm["attempts"], 0)  # fresh budget on re-attach
        self.assertFalse(arm["exhausted"])
        # Pattern still absent: the next tick retries once with the fresh
        # budget (due was set to the attach time).
        engine.poll()
        self.assertEqual(engine.rearm[1]["attempts"], 1)
        self.assertNotIn(1, engine.applied)
        attempts = self.event("rearm-attempt", 1)
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["result"], "ScanMiss")
        # The armed state survives another detach as well.
        self.detach(engine)
        self.assertIn(1, engine.rearm)

    def test_toggle_off_disarms_and_manual_success_clears(self):
        engine = self.start()
        self.arm(engine)
        # Toggle OFF while armed disarms silently.
        self.assertFalse(engine.toggle(1, False))
        self.assertNotIn(1, engine.rearm)
        self.assertNotIn(1, engine.enable_failures)
        self.assertEqual(self.event("rearm-succeeded", 1), [])
        # Re-arm, then a manual enable success clears everything and logs
        # rearm-succeeded exactly once.
        self.arm(engine)
        self.memory.plant()
        self.assertTrue(engine.toggle(1, True))
        self.assertNotIn(1, engine.rearm)
        self.assertNotIn(1, engine.enable_failures)
        self.assertNotIn(1, engine.entry_errors)
        self.assertIn(1, engine.applied)
        self.assertEqual(self.memory.read(0x1041, 1), b"\x90")
        self.assertEqual(len(self.event("rearm-succeeded", 1)), 1)

    def test_non_scan_miss_failure_never_arms(self):
        engine = self.start()
        code_id = [entry for entry in engine.plan["entries"]
                   if entry["kind"] == "code_patch"][0]["id"]
        with self.assertRaisesRegex(NativeRuntimeError,
                                    "code-patch-target-changed"):
            engine.toggle(code_id, True)
        self.assertNotIn(code_id, engine.rearm)
        self.assertIn(code_id, engine.enable_failures)
        self.assertIn(code_id, engine.entry_errors)
        self.assertNotIn(code_id, engine.applied)
        self.assertFalse(engine.blocked)
        self.assertEqual(self.memory.writes, [])
        # The plain-failed entry still offers "Try again" (the UI
        # affordance reads enable_failures / rearm).
        snapshot = RowSnapshot(
            enable_failed=dict(engine.enable_failures),
            rearm={i: dict(s) for i, s in engine.rearm.items()})
        self.assertTrue(try_again_available(snapshot, code_id))
        self.assertEqual(
            rearm_sublabel(snapshot, code_id),
            "enable failed: " + engine.entry_errors[code_id] + " - Try again")
        # A non-ScanMiss failure also drops a pending arm on the same
        # entry (the plain-failed contract supersedes the re-arm).
        self.arm(engine)
        engine._apply_rearm_result(1, NativeRuntimeError("another refusal"),
                                   fresh_attempt=True)
        self.assertNotIn(1, engine.rearm)

    def test_try_again_refusals_budget_reset_and_success(self):
        engine = self.start(attach=False)
        # Refused while not attached.
        with self.assertRaisesRegex(NativeRuntimeError,
                                    "Target process is not connected"):
            engine.try_again(1)
        engine.poll()
        self.assertTrue(engine.connected, engine.status)
        # Refused while already enabled.
        self.assertTrue(engine.toggle(1, True))
        with self.assertRaisesRegex(NativeRuntimeError, "already enabled"):
            engine.try_again(1)
        self.assertFalse(engine.toggle(1, False))
        # Fresh failure; try-again resets the budget and consumes one
        # attempt on its immediate try.
        self.arm(engine)
        engine.rearm[1]["attempts"] = 7
        with self.assertRaisesRegex(
                NativeRuntimeError,
                "not found in readable committed memory"):
            engine.try_again(1)
        arm = engine.rearm[1]
        self.assertEqual(arm["attempts"], 1)
        self.assertFalse(arm["exhausted"])
        self.assertTrue(self.event("try-again-requested", 1))
        self.assertTrue(self.event("try-again-failed", 1))
        failed = [e for e in self.event("rearm-attempt", 1)
                  if e["result"] == "ScanMiss"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["attempt"], 1)
        # The success path: reset + immediate attempt, wish persisted.
        self.memory.plant()
        engine.try_again(1)
        self.assertIn(1, engine.applied)
        self.assertNotIn(1, engine.rearm)
        self.assertNotIn(1, engine.enable_failures)
        self.assertEqual(self.memory.read(0x1041, 1), b"\x90")
        self.assertTrue(self.event("try-again-ok", 1))
        self.assertTrue(self.event("rearm-succeeded", 1))
        self.assertTrue([e for e in self.event("rearm-attempt", 1)
                         if e["result"] == "ok"])

    def test_wish_restore_failure_arms_without_consuming_budget(self):
        engine = self.start(attach=False)
        self.memory.unplant()
        engine.request_auto_on(1)
        engine.poll()  # attach tick: the restore loop fails with ScanMiss
        self.assertTrue(engine.connected, engine.status)
        self.assertNotIn(1, engine.applied)
        self.assertIn(1, engine.rearm)
        arm = engine.rearm[1]
        self.assertEqual(arm["attempts"], 0)  # no budget consumed
        self.assertFalse(arm["exhausted"])
        scans_after_attach = self.memory.scan_calls
        self.assertGreaterEqual(scans_after_attach, 1)
        # Next tick: the executor must not double-attempt (the restore
        # failure pushed the deadline out by the interval).
        engine.poll()
        self.assertEqual(self.memory.scan_calls, scans_after_attach)
        self.assertNotIn(1, engine.applied)
        # The game finishes loading: one forced attempt succeeds.
        self.memory.plant()
        engine.rearm[1]["due"] = time.monotonic() - 1
        engine.poll()
        self.assertIn(1, engine.applied)
        self.assertNotIn(1, engine.rearm)
        self.assertEqual(self.memory.read(0x1041, 1), b"\x90")
        attempts = self.event("rearm-attempt", 1)
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["result"], "ok")

    def test_reattach_detaches_reports_and_refuses_when_blocked(self):
        engine = self.start()
        engine.reattach()
        self.assertIsNone(engine.memory)
        self.assertEqual(engine.status,
                         "Re-attaching; waiting for FixtureTarget.exe")
        self.assertTrue(self.event("reattach-requested"))
        self.assertTrue(self.event("reattach-detached"))
        # Refused while the engine is blocked.
        engine.blocked = True
        engine.error = "forced block for test"
        with self.assertRaisesRegex(NativeRuntimeError, "blocked"):
            engine.reattach()
        engine.blocked = False
        engine.error = ""
        # The re-attach completes and reattach-done carries the pid.
        self.reattach(engine)
        done = self.event("reattach-done")
        self.assertEqual(len(done), 1)
        self.assertEqual(done[0]["pid"], self.memory.pid)
        self.assertFalse(engine._reattach_pending)

    def test_reattach_failed_dedupes_per_request(self):
        def boom(_name):
            raise OSError("process not running")
        with patch("pathlib.Path.cwd", return_value=self.cwd):
            engine = TrainerEngine(
                self.plan, state_dir=self.root / "state-boom",
                process_lock_dir=self.root / "shared-boom",
                memory_factory=boom, hook_coordinator=Coordinator())
        try:
            engine.reattach()  # unattached: just re-arms the wait
            self.assertEqual(engine.status,
                             "Waiting for FixtureTarget.exe")
            engine.poll()  # attach attempt fails -> reattach-failed
            engine.poll()  # same reason: deduped
            engine.poll()
            self.assertEqual(len(self.event("reattach-failed")), 1)
            self.assertEqual(self.event("reattach-failed")[0]["reason"],
                             "process not running")
        finally:
            if not engine.closed:
                engine.close()


class RearmUiRowTests(unittest.TestCase):
    """Pure row-model checks for the re-arm status and Try-again state."""

    def plan(self) -> dict:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / "rearm.ct"
        path.write_text(REARM_CT, encoding="utf-8")
        return compile_table(str(path), "FixtureTarget.exe")

    def entries(self) -> dict:
        return {entry["id"]: entry for entry in self.plan()["entries"]}

    def test_rearm_sublabel_armed_not_exhausted(self):
        snap = RowSnapshot(rearm={1: {"attempts": 3, "max": 10,
                                      "last": "ScanMiss", "exhausted": False}})
        self.assertEqual(rearm_sublabel(snap, 1),
                         "re-arming 3/10 (last: ScanMiss)")
        self.assertEqual(rearm_sublabel(snap, 2), "")

    def test_rearm_sublabel_exhausted_arm(self):
        snap = RowSnapshot(rearm={1: {"attempts": 10, "max": 10,
                                      "last": "ScanMiss", "exhausted": True}})
        self.assertEqual(rearm_sublabel(snap, 1),
                         "enable failed: ScanMiss - Try again")

    def test_rearm_sublabel_plain_enable_failure(self):
        snap = RowSnapshot(enable_failed={
            2: "code-patch-target-changed: bytes at 0x1048 no longer match"})
        self.assertEqual(
            rearm_sublabel(snap, 2),
            "enable failed: code-patch-target-changed: bytes at 0x1048 "
            "no longer match - Try again")

    def test_try_again_available_matrix(self):
        snap = RowSnapshot(
            enable_failed={2: "some refusal"},
            rearm={3: {"attempts": 1, "max": 10, "last": "ScanMiss",
                       "exhausted": False}})
        self.assertTrue(try_again_available(snap, 2))
        self.assertTrue(try_again_available(snap, 3))
        self.assertFalse(try_again_available(snap, 4))

    def test_row_snapshot_rejects_bad_new_fields(self):
        with self.assertRaisesRegex(RowModelError, "enable_failed"):
            RowSnapshot(enable_failed={"1": "text"})
        with self.assertRaisesRegex(RowModelError, "rearm"):
            RowSnapshot(rearm={1: "not a state dict"})

    def test_build_rows_switch_carries_rearm_sublabel(self):
        entries = self.entries()
        snap = RowSnapshot(
            errors={1: "The module byte pattern was not found in readable "
                       "committed memory."},
            enable_failed={1: "The module byte pattern was not found in "
                              "readable committed memory."},
            rearm={1: {"attempts": 0, "max": 10, "last": "ScanMiss",
                       "exhausted": False}})
        rows = build_rows(entries, "Switches", "", snap, 640)
        row = next(r for r in rows if r.entry_id == 1)
        self.assertEqual(row.kind, ROW_SWITCH)
        self.assertEqual(row.sublabel, "re-arming 0/10 (last: ScanMiss)")
        # The other switch row (the code record, no failure state) keeps
        # an empty sublabel: the re-arm text is entry-specific.
        code_row = next(r for r in rows if r.entry_id != 1)
        self.assertEqual(code_row.sublabel, "")


if __name__ == "__main__":
    unittest.main()
