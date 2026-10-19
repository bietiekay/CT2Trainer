"""Decimal and signed pointer-offset literals (WP-45, GC-E5).

CE's pointer-chase ``<Offset>`` slots accept decimal literals with a
``#`` prefix in addition to the already-pinned hex constant arithmetic
(the sign may sit before or after the ``#``, per CE's
ConvertHexStrToRealStr convention).  This file pins the accepted
decimal/signed/mixed forms, the byte-stable hex forms, the exact
fail-closed refusal texts, the signed-64 bounds, and the end-to-end
engine resolution of a decimal-offset chain.
"""
from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

from test_native_engine_code import Coordinator
from test_native_lua_activation import Memory

from ct2trainer.native.compiler import compile_table, validate_plan
from ct2trainer.native.engine import (NativeRuntimeError, TrainerEngine,
                                      validate_plan as validate_engine_plan)

PROCESS = "FixtureTarget.exe"
OFFSET_REFUSAL = "Pointer offset must be a hexadecimal integer literal."
OVERFLOW_REFUSAL = "Pointer offset exceeds signed 64 bits."
INT64_MAX = 0x7FFFFFFFFFFFFFFF


def write_table(root: Path, slots: tuple[str, ...] = ()) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    table = root / "offsets.ct"
    offsets = "".join("<Offset>" + slot + "</Offset>" for slot in slots)
    if slots:
        offsets = "<Offsets>" + offsets + "</Offsets>"
    table.write_text(
        '<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
        '<CheatEntry><ID>0</ID><Description>"base"</Description>'
        '<VariableType>Auto Assembler Script</VariableType><AssemblerScript>[ENABLE]'
        '\ndefine(base,1010)'
        '\nregistersymbol(base)'
        '\n[DISABLE]'
        '\nunregistersymbol(base)'
        '</AssemblerScript></CheatEntry>'
        '<CheatEntry><ID>1</ID><Description>"chain"</Description>'
        '<VariableType>4 Bytes</VariableType><Address>base</Address>'
        + offsets + '<Value>0</Value></CheatEntry>'
        '</CheatEntries></CheatTable>',
        encoding="utf-8")
    return table


class DecimalOffsetFormTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def compile(self, slots):
        return compile_table(write_table(self.root, slots), PROCESS)

    def entry(self, plan):
        return plan["entries"][1]

    def test_decimal_offset_literals_fold_to_signed_int(self):
        for slots, expected in ((("#100",), [100]),
                                (("#-123",), [-123]),
                                (("-#123",), [-123]),
                                (("#100+#200",), [300]),
                                (("100+#20",), [276]),
                                (("#-123+5",), [-118]),
                                (("#4*#10",), [40]),
                                (("#20 (decimal note)",), [20]),
                                (("#100", "8"), [100, 8])):
            with self.subTest(slots=slots):
                plan = self.compile(slots)
                entry = self.entry(plan)
                self.assertTrue(entry["supported"], entry["reason"])
                self.assertEqual(entry["reason"], "")
                self.assertEqual(entry["pointer_offsets"], expected)
                self.assertEqual(entry["requires"], ["base"])
                self.assertEqual(entry["dependency_ids"], [0])

    def test_decimal_forms_pass_both_plan_gates(self):
        plan = self.compile(("#100+#200",))
        validate_plan(plan)
        validate_engine_plan(plan)

    def test_hex_semantics_stay_byte_stable(self):
        for slots, expected in ((("0x10",), [16]),
                                (("+28",), [40]),
                                (("-0x10",), [-16]),
                                (("4*10",), [64]),
                                (("A0+4*4",), [176]),
                                (("13A8+118",), [0x14C0]),
                                (("C00+58",), [0xC58])):
            with self.subTest(slots=slots):
                plan = self.compile(slots)
                entry = self.entry(plan)
                self.assertTrue(entry["supported"], entry["reason"])
                self.assertEqual(entry["pointer_offsets"], expected)

    def test_malformed_decimal_forms_stay_refused(self):
        for slot in ("", "#", "#12a", "12#3", "++10", "+", "0x",
                     "base+10", "a.b", "#1 (", "#(x)", "# 100", "0x10 0x20"):
            with self.subTest(slot=slot):
                plan = self.compile((slot,))
                entry = self.entry(plan)
                self.assertFalse(entry["supported"])
                self.assertEqual(entry["reason"], OFFSET_REFUSAL)
                self.assertEqual(entry["pointer_offsets"], [])

    def test_signed_64_bit_bounds(self):
        # The '#' decimal form accepts exactly signed-64 extremes; the hex
        # forms keep their own literal bounds (17 hex digits overflow).
        plan = self.compile(("#9223372036854775807",))
        entry = self.entry(plan)
        self.assertTrue(entry["supported"], entry["reason"])
        self.assertEqual(entry["pointer_offsets"], [INT64_MAX])
        for slot in ("#9223372036854775807+1",
                     "-#9223372036854775807-1",
                     "#18446744073709551616",
                     "FFFFFFFFFFFFFFFFFFF+1"):
            with self.subTest(slot=slot):
                plan = self.compile((slot,))
                entry = self.entry(plan)
                self.assertFalse(entry["supported"])
                self.assertEqual(entry["reason"], OVERFLOW_REFUSAL)


class DecimalOffsetEngineTests(unittest.TestCase):
    """End-to-end: a decimal-offset chain resolves through live memory."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.table = write_table(self.root, ("#100", "8"))
        self.memory = Memory()
        # base symbol -> 0x1010; plan offsets [100, 8] are applied by the
        # resolver in reverse (innermost first): read(0x1010) + 8 ->
        # read(0x1028) + 100 -> 0x1094.
        self.memory.data[0x1010 - 0x1000:0x1018 - 0x1000] = struct.pack("<Q", 0x1020)
        self.memory.data[0x1028 - 0x1000:0x1036 - 0x1000] = struct.pack("<Q", 0x1030)
        self.engine = TrainerEngine(compile_table(self.table, PROCESS),
                                    state_dir=self.root / "state",
                                    process_lock_dir=self.root / "shared",
                                    memory_factory=lambda name: self.memory,
                                    hook_coordinator=Coordinator())
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)

    def tearDown(self):
        if getattr(self, "engine", None) is None:
            return
        self.memory.alive = False
        self.engine.poll()
        self.engine.close()

    def test_decimal_chain_reads_and_writes_the_resolved_address(self):
        engine = self.engine
        self.assertTrue(engine.toggle(0, True))
        self.assertEqual(engine.symbols["base"], 0x1010)
        self.assertEqual(engine.read_value(1), "0")
        self.assertEqual(engine.set_value(1, "1234"), "1234")
        # The plain 4 Bytes value is decimal-displayed: "1234" writes the
        # decimal 1234 (0x4D2), not the hex value 0x1234.
        self.assertEqual(self.memory.read(0x1094, 4), struct.pack("<I", 1234))
        self.assertEqual(engine.read_value(1), "1234")
        engine.toggle(0, False)
        self.assertNotIn("base", engine.symbols)
        with self.assertRaises(NativeRuntimeError):
            engine.read_value(1)


if __name__ == "__main__":
    unittest.main()
