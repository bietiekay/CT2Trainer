"""WP-55: every AOB scan path resolves to the first (lowest-address) match.

CE 7.5 parity: Cheat Engine never refuses a multi-match scan; it returns
the first/lowest-address occurrence and the user disambiguates manually.
The native scan layer must therefore return the lowest-address match
instead of failing with a "multiple matches" refusal, while still
recording the full match evidence (count + offsets) in
``last_scan_diagnostics``.

Covered scan paths:
- ``scan_module`` (``aobscanmodule``)
- ``scan_process`` (``aobscan``)
- ``scan_region`` (``aobscanregion``)

Zero-match scans keep their exact refusal messages, and the result-bound
quota still refuses before any partial result.  Engine level: an
``aobscanmodule`` record with three seeded occurrences enables against
the first occurrence, and the debug log carries ``match_count`` /
``match_offsets`` only for multi-match scans (single-match log lines keep
the 0.14 shape).
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import TrainerEngine
from ct2trainer.native.memory import ProcessMemoryError, ScanMiss
from test_native_engine import FIXTURE
from test_native_engine_code import CodeMemory, Coordinator
from test_native_memory import _memory, _region
from test_native_scan import _scan_memory

LOG_NAME = "ct2trainer-debug.log"


class ModuleScanFirstMatchTests(unittest.TestCase):
    """scan_module (aobscanmodule): first/lowest match + diagnostics."""

    def scanner(self, data):
        memory = _memory()
        memory.module = Mock(return_value=(0x1000, len(data)))
        memory._query = Mock(side_effect=lambda address: _region(0x1000, len(data)))
        memory.read = Mock(side_effect=lambda address, length:
                           data[address - 0x1000:address - 0x1000 + length])
        return memory

    def test_multi_match_picks_lowest_address_with_diagnostics(self):
        # "AB" occurs at offsets 0, 4 and 8.
        memory = self.scanner(b"ABxxAByyABzz")
        self.assertEqual(memory.scan_module("game.exe", "41 42"), 0x1000)
        self.assertEqual(memory.last_scan_diagnostics,
                         {"match_count": 3,
                          "match_addresses": [0x1000, 0x1004, 0x1008],
                          "module": "game.exe", "module_base": 0x1000})

    def test_single_match_records_count_one(self):
        memory = self.scanner(b"xxxABxxx")
        self.assertEqual(memory.scan_module("game.exe", "41 42"), 0x1003)
        self.assertEqual(memory.last_scan_diagnostics,
                         {"match_count": 1, "match_addresses": [0x1003],
                          "module": "game.exe", "module_base": 0x1000})

    def test_zero_match_keeps_exact_not_found_message(self):
        memory = self.scanner(b"xxxxxxxx")
        with self.assertRaises(ScanMiss) as ctx:
            memory.scan_module("game.exe", "41 42")
        self.assertEqual(str(ctx.exception),
                         "The module byte pattern was not found in readable committed memory.")
        self.assertEqual(memory.last_scan_diagnostics["match_count"], 0)
        self.assertEqual(memory.last_scan_diagnostics["match_addresses"], [])

    def test_module_change_during_scan_still_fails_closed(self):
        memory = self.scanner(b"ABxxxxxx")
        memory.module = Mock(side_effect=[(0x1000, 8), (0x2000, 8)])
        with self.assertRaises(ScanMiss) as ctx:
            memory.scan_module("game.exe", "41 42")
        self.assertEqual(str(ctx.exception), "The module changed while scanning.")


class ProcessRegionFirstMatchTests(unittest.TestCase):
    """scan_process (aobscan) and scan_region (aobscanregion)."""

    def test_process_scan_multi_match_picks_lowest_with_diagnostics(self):
        memory, _, _ = _scan_memory([(0x1000, b"ABxxABxxAB", 0x04, 0x1000)])
        self.assertEqual(memory.scan_process("41 42"), 0x1000)
        self.assertEqual(memory.last_scan_diagnostics,
                         {"match_count": 3,
                          "match_addresses": [0x1000, 0x1004, 0x1008]})

    def test_process_scan_zero_match_keeps_exact_message(self):
        memory, _, _ = _scan_memory([(0x1000, b"xxxx", 0x04, 0x1000)])
        with self.assertRaises(ScanMiss) as ctx:
            memory.scan_process("41 42")
        self.assertEqual(str(ctx.exception),
                         "The byte pattern was not found in readable committed memory.")
        self.assertEqual(memory.last_scan_diagnostics["match_count"], 0)
        self.assertEqual(memory.last_scan_diagnostics["match_addresses"], [])

    def test_process_scan_result_bound_still_refuses(self):
        # The quota cap is evaluated at call time, so a patched
        # MAX_SCAN_RESULTS still refuses before any partial result.
        memory, _, _ = _scan_memory([(0x1000, b"ABxxABxxAB", 0x04, 0x1000)])
        with patch("ct2trainer.native.memory.MAX_SCAN_RESULTS", 2):
            with self.assertRaisesRegex(ProcessMemoryError, "result bound"):
                memory.scan_process("41 42")

    def test_region_scan_multi_match_picks_lowest_in_range(self):
        memory, _, _ = _scan_memory([(0x1000, b"ABxxAB", 0x04, 0x1000)])
        self.assertEqual(memory.scan_region(0x1000, 0x1006, "41 42"), 0x1000)
        self.assertEqual(memory.last_scan_diagnostics,
                         {"match_count": 2, "match_addresses": [0x1000, 0x1004]})
        memory2, _, _ = _scan_memory([(0x1000, b"ABxxAB", 0x04, 0x1000)])
        self.assertEqual(memory2.scan_region(0x1004, 0x1006, "41 42"), 0x1004)
        self.assertEqual(memory2.last_scan_diagnostics,
                         {"match_count": 1, "match_addresses": [0x1004]})


MULTI_CT = '''<CheatTable CheatEngineTableVersion="45"><CheatEntries>
<CheatEntry><ID>1</ID><Description>"multi-match anchor"</Description>
<VariableType>Auto Assembler Script</VariableType><AssemblerScript>[ENABLE]
aobscanmodule(PatchAnchor,FixtureTarget.exe,AB CD EF)
registersymbol(PatchAnchor)
PatchAnchor+2:
 db 90

[DISABLE]
PatchAnchor+2:
 db EF
unregistersymbol(PatchAnchor)</AssemblerScript></CheatEntry>
</CheatEntries></CheatTable>'''


def _seed_multi_match(memory):
    """Seed AB CD EF at offsets 10, 100 and 200 of the module data."""
    anchor = bytes.fromhex("ABCDEF")
    for offset in (10, 100, 200):
        memory.data[offset:offset + 3] = anchor


class EngineAobFirstMatchTests(unittest.TestCase):
    """Engine level: an aobscanmodule record with three seeded occurrences
    enables against the first (lowest) occurrence, and preflight and link
    agree on that address (the patch lands at first-occurrence + 2)."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.cwd = self.root / "cwd"
        self.cwd.mkdir()
        table = self.root / "multi.ct"
        table.write_text(MULTI_CT, encoding="utf-8")
        self.plan = compile_table(table, "FixtureTarget.exe", debug_log=True)
        self.memory = CodeMemory()
        _seed_multi_match(self.memory)
        self.engine = None

    def tearDown(self):
        if self.engine is not None and not self.engine.closed:
            self.engine.close()

    def _start(self):
        with patch("pathlib.Path.cwd", return_value=self.cwd):
            self.engine = TrainerEngine(
                self.plan, state_dir=self.root / "state",
                process_lock_dir=self.root / "shared",
                memory_factory=lambda name: self.memory,
                hook_coordinator=Coordinator())
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)

    def test_enable_patches_first_occurrence_only_and_disable_restores(self):
        self._start()
        base = self.memory.base
        before = bytes(self.memory.data)
        self.engine.toggle(1, True)
        # Exactly one byte changed, at the first occurrence + 2.
        changed = [i for i in range(len(before))
                   if before[i] != self.memory.data[i]]
        self.assertEqual(changed, [12])
        self.assertEqual(self.memory.read(base + 12, 1), b"\x90")
        self.assertEqual(self.memory.read(base + 102, 1), before[102:103])
        self.assertEqual(self.memory.read(base + 202, 1), before[202:203])
        # Preflight and link agreed on the first (lowest) occurrence.
        self.assertEqual(self.engine.symbols.get("patchanchor"), base + 10)
        self.engine.toggle(1, False)
        after = bytes(self.memory.data)
        self.assertEqual(after, before)
        self.assertNotIn("patchanchor", self.engine.symbols)

    def test_scan_log_records_match_count_and_offsets(self):
        self._start()
        base = self.memory.base
        self.engine.toggle(1, True)
        events = [json.loads(line) for line in
                  (self.cwd / LOG_NAME).read_text(encoding="utf-8").splitlines()
                  if line.strip()]
        scans = [e for e in events if e["event"] == "scan"]
        self.assertEqual(len(scans), 1)
        self.assertEqual(scans[0]["symbol"], "PatchAnchor")
        self.assertEqual(scans[0]["address"], hex(base + 10))
        self.assertEqual(scans[0]["match_count"], 3)
        self.assertEqual(scans[0]["match_offsets"],
                         [hex(base + 10), hex(base + 100), hex(base + 200)])
        self.engine.toggle(1, False)

    def test_single_match_scan_log_keeps_0_14_shape(self):
        # The fixture anchor occurs exactly once: no match_count /
        # match_offsets keys may appear, byte-identical to the 0.14 log.
        fixture_cwd = self.root / "fixture-cwd"
        fixture_cwd.mkdir()
        fixture_memory = CodeMemory()
        with patch("pathlib.Path.cwd", return_value=fixture_cwd):
            fixture_engine = TrainerEngine(
                compile_table(FIXTURE, "FixtureTarget.exe", debug_log=True),
                state_dir=self.root / "fixture-state",
                process_lock_dir=self.root / "fixture-shared",
                memory_factory=lambda name: fixture_memory,
                hook_coordinator=Coordinator())
        try:
            fixture_engine.poll()
            self.assertTrue(fixture_engine.connected, fixture_engine.status)
            fixture_engine.toggle(1, True)
        finally:
            if not fixture_engine.closed:
                fixture_engine.close()
        events = [json.loads(line) for line in
                  (fixture_cwd / LOG_NAME).read_text(encoding="utf-8").splitlines()
                  if line.strip()]
        scans = [e for e in events if e["event"] == "scan"]
        self.assertEqual(len(scans), 1)
        self.assertEqual(scans[0]["address"], hex(fixture_memory.base))
        self.assertNotIn("match_count", scans[0])
        self.assertNotIn("match_offsets", scans[0])


if __name__ == "__main__":
    unittest.main()
