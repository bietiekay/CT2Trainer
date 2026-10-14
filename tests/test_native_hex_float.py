"""WP-33: hexadecimal floating-point bit patterns (ShowAsHex Float/Double).

A ShowAsHex Float/Double record is a raw IEEE-754 bit-pattern edit: the
literal must be exactly 8 (Float) or 16 (Double) hex digits, optionally
prefixed with 0x; the bytes are written raw little-endian and the codec
round-trip is proven before the write.  The display is the raw bit pattern
in uppercase fixed width.  The plan validators accept these entries, and
runtime refusals happen with no partial write.
"""
from copy import deepcopy
from pathlib import Path
import struct
import tempfile
import unittest

from test_native_engine_code import Coordinator
from test_native_lua_activation import Memory
from ct2trainer.native.compiler import compile_table, validate_plan
from ct2trainer.native.engine import (NativeRuntimeError, TrainerEngine,
                                      format_value, parse_value,
                                      validate_plan as validate_runtime_plan)

CT_BODY = '''<CheatTable CheatEngineTableVersion="45"><CheatEntries>
<CheatEntry><ID>1</ID><Description>Hex Float</Description><VariableType>Float</VariableType><Address>1040</Address><ShowAsHex>1</ShowAsHex></CheatEntry>
<CheatEntry><ID>2</ID><Description>Hex Double</Description><VariableType>Double</VariableType><Address>1044</Address><ShowAsHex>1</ShowAsHex></CheatEntry>
<CheatEntry><ID>3</ID><Description>Plain Float</Description><VariableType>Float</VariableType><Address>1048</Address></CheatEntry>
</CheatEntries></CheatTable>'''


class HexFloatCompileTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.table = self.root / "hexfloat.ct"
        self.table.write_text(CT_BODY, encoding="utf-8")
        self.plan = compile_table(self.table, "FixtureTarget.exe")

    def test_hex_float_entries_compile_supported(self):
        by_id = {entry["id"]: entry for entry in self.plan["entries"]}
        self.assertEqual(self.plan["counts"],
                         {"total": 3, "supported": 3, "actionable": 3,
                          "blocked": 0, "headings": 0})
        for entry_id in (1, 2):
            entry = by_id[entry_id]
            self.assertTrue(entry["supported"], entry["reason"])
            self.assertEqual(entry["kind"], "value")
            self.assertTrue(entry["show_as_hex"])
            self.assertNotIn("value_profile", entry)
        validate_plan(self.plan)
        validate_runtime_plan(self.plan)

    def test_hex_float_dropdown_choice_is_a_fixed_width_literal(self):
        # A hex-float record whose choice literal is a fixed-width bit
        # pattern compiles; the comma-decimal normalization must not apply
        # while ShowAsHex is set.
        table = self.root / "dropdown.ct"
        table.write_text(
            '<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
            '<CheatEntry><ID>1</ID><Description>Hex Float Choice</Description>'
            '<VariableType>Float</VariableType><Address>1040</Address>'
            '<ShowAsHex>1</ShowAsHex><DropDownList>3F800000:One</DropDownList></CheatEntry>'
            '</CheatEntries></CheatTable>', encoding="utf-8")
        entry = compile_table(table, "FixtureTarget.exe")["entries"][0]
        self.assertTrue(entry["supported"], entry["reason"])
        self.assertEqual(entry["dropdown"]["choices"],
                         [{"value": "3F800000", "description": "One"}])
        table.write_text(
            '<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
            '<CheatEntry><ID>1</ID><Description>Hex Float Comma</Description>'
            '<VariableType>Float</VariableType><Address>1040</Address>'
            '<ShowAsHex>1</ShowAsHex><DropDownList>3,5:Comma</DropDownList></CheatEntry>'
            '</CheatEntries></CheatTable>', encoding="utf-8")
        entry = compile_table(table, "FixtureTarget.exe")["entries"][0]
        self.assertFalse(entry["supported"])
        self.assertEqual(entry["reason"],
                         "Dropdown contains an unsupported value expression.")


class HexFloatEngineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.table = self.root / "hexfloat.ct"
        self.table.write_text(CT_BODY, encoding="utf-8")
        self.memory = Memory()
        self.coordinator = Coordinator()
        self.plan = compile_table(self.table, "FixtureTarget.exe")
        validate_plan(self.plan)
        validate_runtime_plan(self.plan)
        self.engine = TrainerEngine(self.plan,
                                    state_dir=self.root / "state",
                                    process_lock_dir=self.root / "shared",
                                    memory_factory=lambda name: self.memory,
                                    hook_coordinator=self.coordinator)
        self.engine.poll()

    def tearDown(self):
        self.engine.close()

    def test_float_bit_pattern_roundtrip(self):
        # 0x40490FDB == nearest float to 3.14159274; raw little-endian
        # bytes are DB0F4940.
        self.assertEqual(self.engine.set_value(1, "40490FDB"), "40490FDB")
        raw = self.memory.read(0x1040, 4)
        self.assertEqual(raw, bytes.fromhex("DB0F4940"))
        self.assertEqual(struct.unpack("<f", raw)[0],
                         struct.unpack("<f", struct.pack("<f", 3.14159274))[0])
        self.assertEqual(self.engine.read_value(1), "40490FDB")
        # 0x prefix is accepted and indistinguishable after normalization.
        self.assertEqual(self.engine.set_value(1, "0x3F800000"), "3F800000")
        self.assertEqual(self.memory.read(0x1040, 4), struct.pack("<f", 1.0))
        # The codec round-trip is exactly the written bytes.
        self.assertEqual(struct.pack("<f", struct.unpack("<f", raw)[0]), raw)

    def test_double_bit_pattern_roundtrip(self):
        # 0xC000000000000000 == -2.0
        self.assertEqual(self.engine.set_value(2, "C000000000000000"),
                         "C000000000000000")
        raw = self.memory.read(0x1044, 8)
        self.assertEqual(raw, bytes.fromhex("00000000000000C0"))
        self.assertEqual(struct.unpack("<d", raw)[0], -2.0)
        self.assertEqual(self.engine.read_value(2), "C000000000000000")

    def test_wrong_width_and_non_hex_literals_refused_without_write(self):
        for entry_id, digits in ((1, 8), (2, 16)):
            with self.subTest(entry_id=entry_id):
                bad = ("3F8000" if digits == 8 else "C00000000000000")
                long = ("3F8000000" if digits == 8 else "C0000000000000000")
                before = list(self.memory.writes)
                for literal in (bad, long, "XYZ", "1.0", ""):
                    with self.subTest(literal=literal), \
                            self.assertRaises(NativeRuntimeError) as caught:
                        self.engine.set_value(entry_id, literal)
                    self.assertEqual(
                        str(caught.exception),
                        "Enter exactly %d hexadecimal digits for the %s bit pattern"
                        % (digits, "Float" if entry_id == 1 else "Double"))
                self.assertEqual(self.memory.writes, before)

    def test_plain_float_still_accepts_decimal_literals(self):
        self.assertEqual(self.engine.set_value(3, "3.5"), "3.5")
        self.assertEqual(self.memory.read(0x1048, 4), struct.pack("<f", 3.5))

    def test_freeze_roundtrip_on_hex_float(self):
        self.engine.set_value(1, "40490FDB")
        self.engine.set_freeze(1, True)
        self.memory.data[0x40:0x44] = b"\x00" * 4
        self.engine.poll()
        self.assertFalse(self.engine.blocked, self.engine.error)
        self.assertEqual(self.memory.read(0x1040, 4), bytes.fromhex("DB0F4940"))
        self.assertEqual(self.engine.read_value(1), "40490FDB")

    def test_parse_and_format_helpers_are_symmetric(self):
        entry = {e["id"]: e for e in self.plan["entries"]}
        for entry_id, code, pattern in (
                (1, "<f", "40490FDB"), (2, "<d", "C000000000000000")):
            # The pattern is the IEEE-754 word; the stored bytes are the raw
            # word in little-endian byte order.
            little = bytes.fromhex(pattern)[::-1]
            with self.subTest(entry_id=entry_id):
                self.assertEqual(parse_value(entry[entry_id], pattern),
                                 little)
                self.assertEqual(format_value(entry[entry_id], little),
                                 pattern)
                # Lowercase input normalizes to the uppercase display.
                self.assertEqual(parse_value(entry[entry_id],
                                             pattern.lower()), little)
                # The codec round-trip is exactly the written bytes.
                self.assertEqual(struct.pack(code, struct.unpack(code, little)[0]),
                                 little)


if __name__ == "__main__":
    unittest.main()
