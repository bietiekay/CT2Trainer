"""0.52.4 crash-forensics lane: the entry-applied debug event.

Field case 2026-11-24 (The Great Circle): every trainer build after 0.41
crashed the game ~60-77 s after attach while the trainer sat
read-only-idle; the static replay proved the 0.41 and 0.52.3 target
traffic byte-identical for the table, so the next field session must
yield a machine-cross-referenceable traffic record.  On every program
enable the engine now logs one ``entry-applied`` event with the exact
patch ranges (address / captured original / replacement bytes), the
owned cave allocations (address / size / content sha256 + content hex
below the bound) and the module base, so a crash dump's faulting
address can be matched against the patched ranges and the cave
contents.  The bounded re-arm executor gains the same lane: every
``rearm-attempt`` event carries the attempt's ``duration_ms`` and the
module ``scan_range`` so the next crash log shows which scan was in
flight when the target died.  Evidence side only: no target
operations, gated on the plan's debug_log flag for entry-applied.
"""
from __future__ import annotations

import hashlib
import json
import struct
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from test_native_sc2_attach_chain import PROCESS, Sc2ChainMemory
from test_native_engine_code import Coordinator
from test_native_rearm import REARM_CT, RearmMemory
from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import TrainerEngine

LOG_NAME = "ct2trainer-debug.log"

# AOB provider with a cave: a 6-byte patch at the scan site jumps into
# the newmem allocation, whose body resumes at the following module
# instruction - the same shape as the Great Circle entries (6-byte
# prefix-cut into a cave).
FORENSICS_CT = (
    '<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
    '<CheatEntry><ID>1</ID><Description>"cave forensics entry"'
    '</Description><VariableType>Auto Assembler Script'
    '</VariableType><AssemblerScript>[ENABLE]\n'
    f'aobscanmodule(forensicsAnchor, {PROCESS}, 8B 92 80 00 00 00 48 89 44)\n'
    'alloc(forensicsCave, $1000, forensicsAnchor)\n'
    '  forensicsCave:\n'
    '  mov eax, 0xBEEF\n'
    '  jmp resume\n'
    'forensicsAnchor:\n'
    '  jmp forensicsCave\n'
    '  nop\n'
    'resume:\n'
    'registersymbol(forensicsAnchor)\n'
    '[DISABLE]\n'
    'forensicsAnchor:\n'
    '  db 8B 92 80 00 00 00\n'
    'unregistersymbol(*)\n'
    'dealloc(*)\n'
    '</AssemblerScript></CheatEntry>'
    '</CheatEntries></CheatTable>'
)

PATTERN = bytes.fromhex("8B9280000000488944")
PATTERN_OFFSET = 0x40  # module-relative; absolute = base + 0x40 = 0x1040
PATCH_LEN = 6          # jmp forensicsCave (5) + nop (1)


def read_events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    lines = [line for line in path.read_text(encoding="utf-8").splitlines()
             if line.strip()]
    return [json.loads(line) for line in lines]


class EntryForensicsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.cwd = self.root / "cwd"
        self.cwd.mkdir()
        table = self.root / "forensics.ct"
        table.write_text(FORENSICS_CT, encoding="utf-8")
        self.memory = Sc2ChainMemory()
        self.memory.data[PATTERN_OFFSET:PATTERN_OFFSET + len(PATTERN)] = PATTERN
        self.engine = None

    def tearDown(self):
        if self.engine is not None and not self.engine.closed:
            self.engine.close()

    def start(self, *, debug_log: bool):
        plan = compile_table(self.root / "forensics.ct", PROCESS,
                            **({"debug_log": True} if debug_log else {}))
        with patch("pathlib.Path.cwd", return_value=self.cwd):
            self.engine = TrainerEngine(
                plan, state_dir=self.root / "state",
                process_lock_dir=self.root / "shared",
                memory_factory=lambda name: self.memory,
                hook_coordinator=Coordinator())
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)
        return self.engine

    def test_enable_logs_the_applied_patch_and_cave(self):
        engine = self.start(debug_log=True)
        self.assertTrue(engine.toggle(1, True), engine.error)
        events = read_events(self.cwd / LOG_NAME)
        applied = [e for e in events if e["event"] == "entry-applied"]
        self.assertEqual(len(applied), 1)
        event = applied[0]
        self.assertEqual(event["entry_id"], 1)

        # The module patch: the captured 6-byte original at the scan
        # site replaced by a rel32 jump into the cave + a nop.
        self.assertEqual(len(event["patches"]), 1)
        patch = event["patches"][0]
        patch_addr = int(patch["addr"], 16)
        self.assertEqual(patch_addr, self.memory.base + PATTERN_OFFSET)
        self.assertEqual(bytes.fromhex(patch["before"]), PATTERN[:PATCH_LEN])
        after = bytes.fromhex(patch["after"])
        self.assertEqual(len(after), PATCH_LEN)
        self.assertEqual(after[0], 0xE9)
        rel = struct.unpack_from("<i", after, 1)[0]
        cave_addr = int(event["allocations"][0]["addr"], 16)
        self.assertEqual(patch_addr + 5 + rel, cave_addr)
        self.assertEqual(after[PATCH_LEN - 1], 0x90)

        # The cave: the exact assembled body bytes at the allocation
        # address, with a matching content sha256.
        self.assertEqual(len(event["allocations"]), 1)
        cave = event["allocations"][0]
        self.assertEqual(cave_addr, self.memory.cave)
        content = bytes.fromhex(cave["content_hex"])
        self.assertEqual(cave["size"], len(content))
        self.assertEqual(hashlib.sha256(content).hexdigest(),
                         cave["content_sha256"])
        # The logged cave content is the live target content at that
        # address: the body starts with mov eax, 0xBEEF and the logged
        # size fits the allocation.
        cave_offset = cave_addr - self.memory.base
        self.assertEqual(
            self.memory.data[cave_offset:cave_offset + len(content)],
            content)
        self.assertTrue(content.startswith(bytes.fromhex("B8EFBE0000")))
        self.assertLessEqual(len(content), 0x1000)

        # The module identity for dump cross-reference.
        self.assertEqual(event["module_base"], hex(self.memory.base))
        self.assertEqual(event["module_size"], len(self.memory.data))

    def test_disable_restores_without_a_second_applied_event(self):
        engine = self.start(debug_log=True)
        self.assertTrue(engine.toggle(1, True), engine.error)
        engine.toggle(1, False)  # a clean disable returns the direction
        self.assertNotIn(1, engine.applied)
        events = read_events(self.cwd / LOG_NAME)
        applied = [e for e in events if e["event"] == "entry-applied"]
        self.assertEqual(len(applied), 1)
        # The module bytes are restored to the captured original.
        self.assertEqual(
            self.memory.read(self.memory.base + PATTERN_OFFSET,
                             len(PATTERN)), PATTERN)
        # The wish is gone from the applied set (the cave allocation is
        # held for the target lifetime by design, not freed on disable).
        self.assertNotIn(1, engine.applied)

    def test_no_forensics_event_without_the_debug_log_flag(self):
        engine = self.start(debug_log=False)
        self.assertTrue(engine.toggle(1, True), engine.error)
        self.assertFalse((self.cwd / LOG_NAME).exists())
        self.assertIn(1, engine.applied)


class RearmForensicsTests(unittest.TestCase):
    """0.52.4: every rearm-attempt event carries duration + scan range.

    The re-arm scans run while the trainer is otherwise read-only-idle;
    their timing and range are the cross-reference for a crash dump
    taken mid-scan (field case 2026-11-24, The Great Circle).
    """

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.cwd = self.root / "cwd"
        self.cwd.mkdir()
        table = self.root / "rearm.ct"
        table.write_text(REARM_CT, encoding="utf-8")
        self.plan = compile_table(table, "FixtureTarget.exe",
                                  debug_log=True)
        self.memory = RearmMemory()
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

    def test_rearm_attempt_event_carries_timing_and_range(self):
        engine = self.start()
        # Arm entry 1 by failing its first enable (game still loading).
        self.memory.unplant()
        with self.assertRaises(Exception):
            engine.toggle(1, True)
        self.assertIn(1, engine.rearm)
        engine.rearm[1]["due"] = time.monotonic() - 1
        engine.poll()
        events = read_events(self.cwd / LOG_NAME)
        attempts = [e for e in events if e["event"] == "rearm-attempt"]
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["result"], "ScanMiss")
        self.assertIsInstance(attempts[0]["duration_ms"], int)
        self.assertGreaterEqual(attempts[0]["duration_ms"], 0)
        self.assertEqual(
            attempts[0]["scan_range"],
            f"{hex(self.memory.base)}-{hex(self.memory.base + len(self.memory.data))}")

    def test_rearm_success_attempt_carries_timing_and_range(self):
        engine = self.start()
        self.memory.unplant()
        with self.assertRaises(Exception):
            engine.toggle(1, True)
        self.assertIn(1, engine.rearm)
        engine.rearm[1]["due"] = time.monotonic() - 1
        self.memory.plant()
        engine.poll()
        events = read_events(self.cwd / LOG_NAME)
        attempts = [e for e in events if e["event"] == "rearm-attempt"]
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["result"], "ok")
        self.assertIsInstance(attempts[0]["duration_ms"], int)
        self.assertEqual(attempts[0]["scan_range"],
                         f"0x{self.memory.base:x}-0x{self.memory.base + len(self.memory.data):x}")
        self.assertIn(1, engine.applied)


if __name__ == "__main__":
    unittest.main()
