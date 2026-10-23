"""RT-4.4 (O6/O7/O8/O26): engine-level value semantics for the reference
table dropdown gap classes.

O6  Integer dropdown choices outside the record's width are staged and
    stored truncated to the low width bits (CE SetValue typed-pointer
    parity); decimal-mode records also accept hex-style literals of the
    alternate base (corpus P4G shape).
O7  String records with ShowAsHex expose their bounded byte buffer as a
    byte-array value (roadmap O7 row); writes accept exact hex byte pairs
    over the full buffer and the display is the raw byte view.
    ShowAsBinary remains refused with the named WP-34 message.
O8  Unparseable rows of a read-only (description-only) list stage as
    non-writable display sentinels (corpus '??' marker); bracketed choices
    on simple-numeric records are address expressions resolved against
    the live symbol table at write time (named refusal, no partial
    write, pre-attach refusal).
O26 A read-only dropdown without writable choices stages as an empty
    display view instead of a refusal; the record keeps its normal value
    semantics and every write is refused against the (possibly empty)
    writable choice set.

All writes are asserted byte-exact against the owned fixture memory.
"""
import tempfile
import unittest
from pathlib import Path

from test_native_engine_code import Coordinator
from test_native_lua_activation import Memory
from ct2trainer.native.compiler import (compile_table, validate_plan)
from ct2trainer.native.engine import (NativeRuntimeError, TrainerEngine,
                                      validate_plan as validate_runtime_plan)


def _table_xml(entries):
    return ('<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
            + "".join(entries) + "</CheatEntries></CheatTable>")


def _entry(entry_id, variable_type, address, extra=""):
    return (f'<CheatEntry><ID>{entry_id}</ID><Description>RS{entry_id}</Description>'
            f'<VariableType>{variable_type}</VariableType><Address>{address}</Address>'
            f'{extra}</CheatEntry>')


class IntegerTruncationSemanticsTests(unittest.TestCase):
    """O6: out-of-width integer choices store the low width bits."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        body = _table_xml((
            _entry(7000, "Byte", "1090", "<DropDownList>314:Big</DropDownList>"),
            _entry(7001, "2 Bytes", "1091", "<DropDownList>70000:Big</DropDownList>"),
            _entry(7002, "4 Bytes", "1093", "<DropDownList>-1:Neg</DropDownList>"),
            _entry(7003, "4 Bytes", "1097",
                   "<ShowAsSigned>1</ShowAsSigned>"
                   "<DropDownList>-2147483649:Neg</DropDownList>"),
            _entry(7004, "4 Bytes", "109B",
                   "<ShowAsSigned>1</ShowAsSigned>"
                   "<DropDownList>2147483648:Pos</DropDownList>"),
            _entry(7005, "4 Bytes", "109F",
                   "<ShowAsHex>1</ShowAsHex><DropDownList>100000000:Big</DropDownList>"),
            _entry(7006, "8 Bytes", "10A3",
                   "<DropDownList>18446744073709551616:Max</DropDownList>"),
            # RT-4.4 (O8): hex-style choice on a decimal-mode record
            # (corpus P4G shape) parses in the alternate base.
            _entry(7007, "2 Bytes", "10AB", "<DropDownList>01E7:Hex</DropDownList>"),
        ))
        self.table = self.root / "o6.ct"
        self.table.write_text(body, encoding="utf-8")
        self.memory = Memory()
        self.coordinator = Coordinator()
        self.plan = compile_table(self.table, "FixtureTarget.exe")
        for entry in self.plan["entries"]:
            self.assertTrue(entry["supported"], entry["reason"])
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

    def _entry(self, entry_id):
        return next(e for e in self.plan["entries"] if e["id"] == entry_id)

    def test_out_of_width_integer_choices_store_the_low_bits(self):
        # (entry id, absolute address, literal, read size, expected bytes,
        #  expected set_value display)
        cases = (
            (7000, 0x1090, "314", 1, b"\x3a", "58"),
            (7001, 0x1091, "70000", 2, b"\x70\x11", "4464"),
            (7002, 0x1093, "-1", 4, b"\xff\xff\xff\xff", "4294967295"),
            (7003, 0x1097, "-2147483649", 4, b"\xff\xff\xff\x7f", "2147483647"),
            (7004, 0x109B, "2147483648", 4, b"\x00\x00\x00\x80", "-2147483648"),
            # hex literal 0x100000000 == 2**32 truncates to zero
            (7005, 0x109F, "100000000", 4, b"\x00\x00\x00\x00", "0"),
            (7006, 0x10A3, "18446744073709551616", 8, b"\x00" * 8, "0"),
            (7007, 0x10AB, "01E7", 2, b"\xe7\x01", "487"),
        )
        for entry_id, address, literal, size, expected_bytes, display in cases:
            with self.subTest(entry=entry_id, literal=literal):
                before = list(self.memory.writes)
                self.assertEqual(self.engine.set_value(entry_id, literal), display)
                self.assertEqual(self.memory.read(address, size), expected_bytes)
                self.assertEqual(self.memory.writes[len(before):],
                                 [(address, expected_bytes)])

    def test_staged_choices_keep_the_source_literal(self):
        # The plan stores the literal as written (no base rewrite), the
        # alternate-base choice included (P4G: '01E7' stays '01E7').
        choices = {c["value"] for c in self._entry(7007)["dropdown"]["choices"]}
        self.assertEqual(choices, {"01E7"})
        choices = {c["value"] for c in self._entry(7005)["dropdown"]["choices"]}
        self.assertEqual(choices, {"100000000"})

    def test_decimal_record_rejects_non_numeric_input(self):
        before = list(self.memory.writes)
        with self.assertRaisesRegex(NativeRuntimeError,
                                    "Enter a whole decimal number"):
            self.engine.set_value(7000, "3,5")
        self.assertEqual(self.memory.writes, before)


class ExpressionAndSentinelSemanticsTests(unittest.TestCase):
    """O8: bracketed expression choices and read-only display sentinels."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        body = _table_xml((
            _entry(7100, "Float", "1090",
                   '<DropDownList ReadOnly="1">\n0:None\n??:Unknown\n'
                   '</DropDownList>'),
            _entry(7101, "4 Bytes", "1094",
                   "<DropDownList>[sym]:Computed</DropDownList>"),
            _entry(7102, "4 Bytes", "1098",
                   "<DropDownList>[nosym]:Missing</DropDownList>"),
            # corpus P4G shape: hex IDs listed on a decimal-mode record
            _entry(7103, "2 Bytes", "109C",
                   "<DropDownList>01E7:Hex\n2:Two</DropDownList>"),
        ))
        self.table = self.root / "o8.ct"
        self.table.write_text(body, encoding="utf-8")
        self.memory = Memory()
        self.coordinator = Coordinator()
        self.plan = compile_table(self.table, "FixtureTarget.exe")
        for entry in self.plan["entries"]:
            self.assertTrue(entry["supported"], entry["reason"])
        validate_plan(self.plan)
        validate_runtime_plan(self.plan)
        # [sym]+4 dereferences the pointer stored at 0x1010.
        self.memory.data[0x10:0x18] = (0x2000).to_bytes(8, "little")
        self.engine = TrainerEngine(self.plan,
                                    state_dir=self.root / "state",
                                    process_lock_dir=self.root / "shared",
                                    memory_factory=lambda name: self.memory,
                                    hook_coordinator=self.coordinator)
        self.engine.poll()
        self.engine.symbols["sym"] = 0x1010

    def tearDown(self):
        self.engine.close()

    def _entry(self, entry_id):
        return next(e for e in self.plan["entries"] if e["id"] == entry_id)

    def test_read_only_sentinel_row_is_display_only(self):
        entry = self._entry(7100)
        self.assertTrue(entry["dropdown"]["read_only"])
        self.assertEqual(entry["dropdown"]["choices"],
                         [{"value": "0", "description": "None"},
                          {"value": "??", "description": "Unknown",
                           "writable": False}])
        before = list(self.memory.writes)
        # The sentinel literal itself is not a finite number; refused at
        # parse time, never treated as a selectable row.
        with self.assertRaisesRegex(NativeRuntimeError,
                                    "Enter a finite decimal number"):
            self.engine.set_value(7100, "??")
        # A value outside the writable choice set is refused by the
        # read-only allowed-set check; the display row is not in it.
        with self.assertRaisesRegex(NativeRuntimeError, "supplied list"):
            self.engine.set_value(7100, "0.5")
        self.assertEqual(self.memory.writes, before)
        # The one writable literal still writes byte-exactly.
        self.engine.set_value(7100, "0")
        self.assertEqual(self.memory.read(0x1090, 4), b"\x00\x00\x00\x00")

    def test_expression_choice_resolves_against_live_symbols(self):
        # [sym] dereferences the 8-byte pointer stored at 0x1010 (0x2000);
        # the resolved address is stored as the record's value.
        before = list(self.memory.writes)
        self.assertEqual(self.engine.set_value(7101, "[sym]"), "8192")
        self.assertEqual(self.memory.read(0x1094, 4), b"\x00\x20\x00\x00")
        self.assertEqual(self.memory.writes[len(before):],
                         [(0x1094, b"\x00\x20\x00\x00")])

    def test_expression_choice_with_unknown_symbol_is_refused_without_write(self):
        before = list(self.memory.writes)
        with self.assertRaisesRegex(NativeRuntimeError,
                                    "Unresolved symbol: nosym\\.$"):
            self.engine.set_value(7102, "[nosym]")
        self.assertEqual(self.memory.writes, before)

    def test_expression_choice_pre_attach_is_refused_named(self):
        pending = TrainerEngine(self.plan, state_dir=self.root / "state_pre",
                                process_lock_dir=self.root / "shared_pre",
                                memory_factory=lambda name: self.memory,
                                hook_coordinator=self.coordinator)
        self.addCleanup(pending.close)
        with self.assertRaisesRegex(NativeRuntimeError,
                                    "Expression dropdown choices require an attached target\\.$"):
            pending.set_value(7101, "[sym]")

    def test_alternate_base_choices_write_as_their_number(self):
        before = list(self.memory.writes)
        self.assertEqual(self.engine.set_value(7103, "01E7"), "487")
        self.assertEqual(self.memory.read(0x109C, 2), b"\xe7\x01")
        self.assertEqual(self.memory.writes[len(before):],
                         [(0x109C, b"\xe7\x01")])
        self.assertEqual(self.engine.set_value(7103, "2"), "2")
        self.assertEqual(self.memory.read(0x109C, 2), b"\x02\x00")

    def test_malformed_bracket_choice_blocks_the_record(self):
        standalone = self.root / "bad_expr.ct"
        standalone.write_text(
            _table_xml((_entry(7110, "4 Bytes", "1090",
                               "<DropDownList>[1+2*]:Broken</DropDownList>"),)),
            encoding="utf-8")
        entry = compile_table(standalone, "FixtureTarget.exe")["entries"][0]
        self.assertFalse(entry["supported"])
        self.assertEqual(
            entry["reason"],
            "Dropdown expression choice '[1+2*]' is not a valid address "
            "expression: Unexpected address expression token.")

    def test_unclosed_bracket_choice_keeps_the_generic_refusal(self):
        # CE evaluates bracket values only when the trimmed value both
        # opens and closes with '[' / ']'; an unclosed form is not an
        # expression, so a writable record keeps the pre-RT-4.4 generic
        # refusal (and a read-only list stages it as a display row).
        standalone = self.root / "bad_expr2.ct"
        standalone.write_text(
            _table_xml((_entry(7111, "4 Bytes", "1090",
                               "<DropDownList>[sym:Open</DropDownList>"),)),
            encoding="utf-8")
        entry = compile_table(standalone, "FixtureTarget.exe")["entries"][0]
        self.assertFalse(entry["supported"])
        self.assertEqual(entry["reason"],
                         "Dropdown contains an unsupported value expression.")

    def test_plan_validator_tamper_cases_match_the_compiler(self):
        # The two plan validators must agree byte-for-byte on the RT-4.4
        # marker rules; the separators file covers the writable-list
        # marker cases, this covers the profile-record expression case.
        profile_table = self.root / "o8_profile.ct"
        profile_table.write_text(
            _table_xml((
                _entry(7120, "Binary", "1090",
                       '<BitStart>0</BitStart><BitLength>2</BitLength>'
                       '<DropDownList>0:Off\n1:On</DropDownList>'),
            )),
            encoding="utf-8")
        plan = compile_table(profile_table, "FixtureTarget.exe")
        tampered = {
            "id": 7120,
            "dropdown": {
                "choices": [
                    {"value": "0", "description": "Off", "expression": True},
                ],
                "read_only": False,
            },
        }
        plan["entries"][0] = dict(plan["entries"][0], **tampered)
        for validator, expected_type in (
            (validate_plan, "compiler"),
            (validate_runtime_plan, "runtime"),
        ):
            with self.subTest(validator=expected_type):
                with self.assertRaises(Exception) as caught:
                    validator(plan)
                self.assertEqual(
                    str(caught.exception),
                    "Dropdown expression choices require a simple numeric record.")

    def test_writable_record_still_refuses_unparseable_choices(self):
        # The pre-RT-4.4 generic-expression pins ('???' and '2+2') are
        # preserved byte-identical on writable records.
        for literal in ("???", "2+2"):
            with self.subTest(literal=literal):
                standalone = self.root / "writable_unparseable.ct"
                standalone.write_text(
                    _table_xml((_entry(7130, "Byte", "1090",
                                       f"<DropDownList>{literal}:X</DropDownList>"),)),
                    encoding="utf-8")
                entry = compile_table(standalone, "FixtureTarget.exe")["entries"][0]
                self.assertFalse(entry["supported"])
                self.assertEqual(entry["reason"],
                                 "Dropdown contains an unsupported value expression.")


class ShowAsHexStringSemanticsTests(unittest.TestCase):
    """O7: ShowAsHex string records stage a bounded byte-array value."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        body = _table_xml((
            _entry(7200, "String", "1090",
                   "<Length>8</Length><ZeroTerminate>1</ZeroTerminate>"
                   "<ShowAsHex>1</ShowAsHex>"),
            _entry(7201, "String", "10A0",
                   "<Length>4</Length><ZeroTerminate>1</ZeroTerminate>"
                   "<Unicode>1</Unicode><ShowAsHex>1</ShowAsHex>"),
        ))
        self.table = self.root / "o7.ct"
        self.table.write_text(body, encoding="utf-8")
        self.memory = Memory()
        self.coordinator = Coordinator()
        self.plan = compile_table(self.table, "FixtureTarget.exe")
        for entry in self.plan["entries"]:
            self.assertTrue(entry["supported"], entry["reason"])
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

    def _entry(self, entry_id):
        return next(e for e in self.plan["entries"] if e["id"] == entry_id)

    def test_show_as_hex_profile_shape_and_round_trip(self):
        profile = self._entry(7200)["value_profile"]
        self.assertEqual(profile["kind"], "byte_array")
        self.assertEqual(profile["size"], 8)
        self.assertEqual(profile["display"], "hex_bytes")
        self.assertEqual(profile["byte_order"], "address")
        self.assertFalse(profile["signed"])
        self.assertTrue(profile["actionable"])
        self.assertFalse(profile["read_only"])
        self.assertEqual(profile["variable_type"], "String")
        self.assertTrue(profile["properties"]["ShowAsHex"])
        self.assertTrue(profile["properties"]["ZeroTerminate"])
        from ct2trainer.native.value_types import (parse_profile_value,
                                                   format_profile_value,
                                                   validate_value_profile)
        validate_value_profile(profile)
        self.assertEqual(parse_profile_value(profile, "01 02 03 04 05 06 07 08"),
                         b"\x01\x02\x03\x04\x05\x06\x07\x08")
        self.assertEqual(format_profile_value(profile, b"\x01\x02\x03\x04\x05\x06\x07\x08"),
                         "01 02 03 04 05 06 07 08")

    def test_show_as_hex_writes_byte_exact(self):
        before = list(self.memory.writes)
        display = self.engine.set_value(7200, "01 02 03 04 05 06 07 08")
        self.assertEqual(display, "01 02 03 04 05 06 07 08")
        self.assertEqual(self.memory.read(0x1090, 8),
                         b"\x01\x02\x03\x04\x05\x06\x07\x08")
        self.assertEqual(self.memory.writes[len(before):],
                         [(0x1090, b"\x01\x02\x03\x04\x05\x06\x07\x08")])
        # The Unicode variant sizes the buffer at Length * 2 bytes.
        self.engine.set_value(7201, "00 01 00 02 00 03 00 04")
        self.assertEqual(self.memory.read(0x10A0, 8),
                         b"\x00\x01\x00\x02\x00\x03\x00\x04")

    def test_show_as_hex_refuses_out_of_contract_literals(self):
        before = list(self.memory.writes)
        with self.assertRaisesRegex(NativeRuntimeError,
                                    "Byte array must contain exactly ByteLength hex bytes"):
            self.engine.set_value(7200, "01 02")
        with self.assertRaisesRegex(NativeRuntimeError,
                                    "Enter exact hex byte pairs without wildcards"):
            self.engine.set_value(7200, "GG GG GG GG GG GG GG GG")
        self.assertEqual(self.memory.writes, before)

    def test_show_as_binary_stays_refused(self):
        # WP-34 pin: the ShowAsBinary byte view is still refused with the
        # named flag, byte-identical to the pre-RT-4.4 message.
        standalone = self.root / "o7_binary.ct"
        standalone.write_text(
            _table_xml((_entry(7210, "String", "1090",
                               "<Length>8</Length><ZeroTerminate>1</ZeroTerminate>"
                               "<ShowAsBinary>1</ShowAsBinary>"),)),
            encoding="utf-8")
        entry = compile_table(standalone, "FixtureTarget.exe")["entries"][0]
        self.assertFalse(entry["supported"])
        self.assertEqual(entry["reason"],
                         "Strings require literal text display; the "
                         "ShowAsBinary byte view is unsupported.")


class EmptyReadOnlyDropdownSemanticsTests(unittest.TestCase):
    """O26: read-only dropdowns without writable choices stage as views."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        body = _table_xml((
            _entry(7300, "Byte", "1090",
                   '<DropDownList ReadOnly="1"></DropDownList>'),
            _entry(7301, "Byte", "1091",
                   '<DropDownList ReadOnly="1">\n:Only:\n:Nothing:\n'
                   '</DropDownList>'),
        ))
        self.table = self.root / "o26.ct"
        self.table.write_text(body, encoding="utf-8")
        self.memory = Memory()
        self.coordinator = Coordinator()
        self.plan = compile_table(self.table, "FixtureTarget.exe")
        for entry in self.plan["entries"]:
            self.assertTrue(entry["supported"], entry["reason"])
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

    def _entry(self, entry_id):
        return next(e for e in self.plan["entries"] if e["id"] == entry_id)

    def test_empty_and_display_only_read_only_lists_are_supported(self):
        empty = self._entry(7300)
        self.assertEqual(empty["dropdown"], {"choices": [], "read_only": True})
        separator = self._entry(7301)
        self.assertEqual(
            separator["dropdown"]["choices"],
            [{"value": "", "description": "Only:", "separator": True},
             {"value": "", "description": "Nothing:", "separator": True}])
        self.assertTrue(separator["dropdown"]["read_only"])

    def test_every_write_is_refused_against_the_empty_writable_set(self):
        engine = self.engine
        for entry_id in (7300, 7301):
            with self.subTest(entry=entry_id):
                before = list(self.memory.writes)
                with self.assertRaisesRegex(NativeRuntimeError,
                                            "supplied list"):
                    engine.set_value(entry_id, "1")
                self.assertEqual(self.memory.writes, before)


if __name__ == "__main__":
    unittest.main()
