"""WP-24: empty-value dropdown rows are non-writable separator metadata.

Corpus semantics (P5/AtomicHeart/HellPie/Scorn tables): a DropDownList row
whose value part is empty (":Section Name:") is a visual separator, not a
selectable value.  The converter keeps it as display metadata in the plan
("separator": true, empty value) so the trainer UI can render it, but it is
never writable: neither the numeric write path nor the read-only choice
check treats it as a concrete choice.  String dropdowns keep the older
contract where an empty value is a writable zero-terminated literal
(pinned by test_native_strings / test_native_global_strings).
"""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from test_native_engine_code import Coordinator
from test_native_lua_activation import Memory
from ct2trainer.native.compiler import (NativeCompileError, compile_table,
                                        validate_plan)
from ct2trainer.native.engine import (NativeRuntimeError, TrainerEngine,
                                      validate_plan as validate_runtime_plan)

CT_BODY = '''<CheatTable CheatEngineTableVersion="45"><CheatEntries>
<CheatEntry><ID>5000</ID><Description>Effect List</Description><VariableType>4 Bytes</VariableType><Address>1040</Address><DropDownList>
0:Base
1:Base B
:Afterbirth Effects:
2:Effect A
3:Effect B
:Extra:
4:Effect C
</DropDownList></CheatEntry>
<CheatEntry><ID>5001</ID><Description>RO Section List</Description><VariableType>Byte</VariableType><Address>1050</Address><DropDownList ReadOnly="1">
:Section:
10:First
11:Second
</DropDownList></CheatEntry>
<CheatEntry><ID>5002</ID><Description>Linked Item</Description><DropDownListLink>Effect List</DropDownListLink><VariableType>4 Bytes</VariableType><Address>1060</Address></CheatEntry>
<CheatEntry><ID>5003</ID><Description>RO Linked</Description><DropDownListLink>RO Section List</DropDownListLink><VariableType>Byte</VariableType><Address>1070</Address></CheatEntry>
<CheatEntry><ID>5004</ID><Description>Str List</Description><VariableType>String</VariableType><Length>4</Length><ZeroTerminate>1</ZeroTerminate><Address>1080</Address><DropDownList>
abc:Three
:Empty
</DropDownList></CheatEntry>
</CheatEntries></CheatTable>'''

EFFECT_CHOICES = [
    {"value": "0", "description": "Base"},
    {"value": "1", "description": "Base B"},
    {"value": "", "description": "Afterbirth Effects:", "separator": True},
    {"value": "2", "description": "Effect A"},
    {"value": "3", "description": "Effect B"},
    {"value": "", "description": "Extra:", "separator": True},
    {"value": "4", "description": "Effect C"},
]
SECTION_CHOICES = [
    {"value": "", "description": "Section:", "separator": True},
    {"value": "10", "description": "First"},
    {"value": "11", "description": "Second"},
]


class DropdownSeparatorRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.table = self.root / "separators.ct"
        self.table.write_text(CT_BODY, encoding="utf-8")
        self.memory = Memory()
        self.coordinator = Coordinator()
        self.plan = compile_table(self.table, "FixtureTarget.exe")
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

    def test_plan_shape_carries_separator_metadata_and_writable_count(self):
        effect = self._entry(5000)
        self.assertTrue(effect["supported"], effect["reason"])
        self.assertEqual(effect["dropdown"]["choices"], EFFECT_CHOICES)
        self.assertFalse(effect["dropdown"]["read_only"])
        # Writable count is derivable: total rows minus separator rows.
        writable = [c for c in effect["dropdown"]["choices"]
                    if c.get("separator") is not True]
        self.assertEqual(len(writable), 5)
        self.assertEqual([c["value"] for c in writable], ["0", "1", "2", "3", "4"])
        section = self._entry(5001)
        self.assertEqual(section["dropdown"]["choices"], SECTION_CHOICES)
        self.assertTrue(section["dropdown"]["read_only"])
        writable_ro = [c for c in section["dropdown"]["choices"]
                       if c.get("separator") is not True]
        self.assertEqual([c["value"] for c in writable_ro], ["10", "11"])

    def test_linked_records_borrow_choices_including_separators(self):
        linked = self._entry(5002)
        self.assertEqual(linked["dropdown"]["choices"], EFFECT_CHOICES)
        self.assertEqual(linked["dropdown"]["link_target_id"], 5000)
        self.assertFalse(linked["dropdown"]["read_only"])
        ro_linked = self._entry(5003)
        self.assertEqual(ro_linked["dropdown"]["choices"], SECTION_CHOICES)
        self.assertEqual(ro_linked["dropdown"]["link_target_id"], 5001)
        self.assertTrue(ro_linked["dropdown"]["read_only"])

    def test_writable_separator_list_writes_are_byte_exact(self):
        self.assertEqual(self.engine.set_value(5000, "2"), "2")
        self.assertEqual(self.memory.read(0x1040, 4), b"\x02\x00\x00\x00")
        # The linked record writes to its own address, never the source list.
        self.assertEqual(self.engine.set_value(5002, "3"), "3")
        self.assertEqual(self.memory.read(0x1060, 4), b"\x03\x00\x00\x00")
        self.assertEqual(self.memory.read(0x1040, 4), b"\x02\x00\x00\x00")

    def test_separator_rows_are_never_writable(self):
        before = list(self.memory.writes)
        with self.assertRaisesRegex(NativeRuntimeError, "Enter a whole decimal number"):
            self.engine.set_value(5000, "")
        self.assertEqual(self.memory.writes, before)
        # Same contract on the linked writable record.
        before = list(self.memory.writes)
        with self.assertRaisesRegex(NativeRuntimeError, "Enter a whole decimal number"):
            self.engine.set_value(5002, "")
        self.assertEqual(self.memory.writes, before)

    def test_read_only_linked_list_rejects_outside_and_empty_but_accepts_concrete(self):
        before = list(self.memory.writes)
        with self.assertRaisesRegex(NativeRuntimeError, "supplied list"):
            self.engine.set_value(5003, "5")
        self.assertEqual(self.memory.writes, before)
        before = list(self.memory.writes)
        with self.assertRaisesRegex(NativeRuntimeError, "Enter a whole decimal number"):
            self.engine.set_value(5003, "")
        self.assertEqual(self.memory.writes, before)
        self.assertEqual(self.engine.set_value(5003, "11"), "11")
        self.assertEqual(self.memory.read(0x1070, 1), b"\x0b")
        # The source list address is untouched by the linked write.
        self.assertEqual(self.memory.read(0x1050, 1), b"\x00")

    def test_freeze_roundtrip_on_linked_record_with_separators(self):
        self.engine.set_value(5002, "4")
        self.engine.set_freeze(5002, True)
        self.memory.data[0x60] = 0xFF
        self.engine.poll()
        self.assertFalse(self.engine.blocked, self.engine.error)
        self.assertEqual(self.memory.read(0x1060, 4), b"\x04\x00\x00\x00")

    def test_tampered_separator_metadata_is_rejected_by_both_validators(self):
        def by_id(tampered):
            return {e["id"]: e for e in tampered["entries"]}

        cases = [
            ("separator with non-empty value",
             lambda plan: by_id(plan)[5000]["dropdown"]["choices"][2].update(value="1"),
             "Separator dropdown choices must carry the empty value."),
            ("separator marker as string",
             lambda plan: by_id(plan)[5000]["dropdown"]["choices"][2].update(separator="yes"),
             "Dropdown separator marker must be true."),
            ("separator marker as false",
             lambda plan: by_id(plan)[5000]["dropdown"]["choices"][2].update(separator=False),
             "Dropdown separator marker must be true."),
            ("empty value without the separator marker",
             lambda plan: by_id(plan)[5000]["dropdown"]["choices"][2].pop("separator"),
             "Dropdown values must be exact supported literals."),
            ("read-only list reduced to separators only",
             lambda plan: by_id(plan)[5001]["dropdown"]["choices"].__setitem__(
                 slice(None), [
                     {"value": "", "description": "Section:", "separator": True},
                     {"value": "", "description": "First", "separator": True},
                     {"value": "", "description": "Second", "separator": True},
                 ]),
             "Read-only dropdown has no numeric choices."),
            ("out-of-range byte choice smuggled into a RO list",
             lambda plan: by_id(plan)[5001]["dropdown"]["choices"][1].update(value="300"),
             "Dropdown values must be exact supported literals."),
        ]
        for name, mutate, expected in cases:
            with self.subTest(case=name):
                tampered = deepcopy(self.plan)
                mutate(tampered)
                with self.assertRaises(NativeCompileError) as compile_error:
                    validate_plan(deepcopy(tampered))
                self.assertEqual(str(compile_error.exception), expected)
                with self.assertRaises(NativeRuntimeError) as runtime_error:
                    validate_runtime_plan(deepcopy(tampered))
                self.assertEqual(str(runtime_error.exception), expected)

    def test_string_dropdown_empty_value_stays_a_writable_literal(self):
        entry = self._entry(5004)
        self.assertTrue(entry["supported"], entry["reason"])
        self.assertEqual(entry["dropdown"]["choices"],
                         [{"value": "abc", "description": "Three"},
                          {"value": "", "description": "Empty"}])
        self.assertFalse(any("separator" in choice
                             for choice in entry["dropdown"]["choices"]))

    def test_generation_refusals_are_exact(self):
        bodies = (
            ('<DropDownList>3,5:Comma decimal</DropDownList>',
             "Dropdown contains an unsupported value expression."),
            ('<DropDownList>???:Mystery</DropDownList>',
             "Dropdown contains an unsupported value expression."),
            ('<DropDownList>2+2:Math</DropDownList>',
             "Dropdown contains an unsupported value expression."),
            ('<DropDownList ReadOnly="1">:Only: :Nothing</DropDownList>',
             "Read-only dropdown has no concrete literal choices."),
        )
        for index, (extra, expected_reason) in enumerate(bodies):
            with self.subTest(index=index):
                # Recompile a standalone table so only the candidate row
                # determines the blocked entry.
                standalone = self.root / "refusal.ct"
                standalone.write_text(
                    '<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
                    f'<CheatEntry><ID>6000</ID><Description>Candidate</Description>'
                    f'<VariableType>Byte</VariableType><Address>1090</Address>'
                    f'{extra}</CheatEntry>'
                    '</CheatEntries></CheatTable>', encoding="utf-8")
                entry = compile_table(standalone, "FixtureTarget.exe")["entries"][0]
                self.assertFalse(entry["supported"])
                self.assertEqual(entry["reason"], expected_reason)
        # A separator row mixed with a malformed literal refuses the whole
        # record with the literal reason (the separator itself is fine).
        mixed = self.root / "mixed.ct"
        mixed.write_text(
            '<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
            '<CheatEntry><ID>6001</ID><Description>Mixed</Description>'
            '<VariableType>Byte</VariableType><Address>1090</Address>'
            '<DropDownList>\n:Section:\n300:Big\n</DropDownList></CheatEntry>'
            '</CheatEntries></CheatTable>', encoding="utf-8")
        entry = compile_table(mixed, "FixtureTarget.exe")["entries"][0]
        self.assertFalse(entry["supported"])
        # WP-34 (FLAG-2 follow-up 2): the width refusal names the choice and
        # the record's value-type width.
        self.assertEqual(entry["reason"],
                         "Dropdown choice '300' exceeds the Byte value-type width (0 to 255).")

    def test_width_refusals_name_the_choice_and_the_type_width(self):
        # WP-34 (FLAG-2 follow-up 2): exact per-choice width messages for the
        # remaining simple integer types, unsigned and signed.
        cases = (
            ('<DropDownList>70000:Big</DropDownList>', "2 Bytes",
             "Dropdown choice '70000' exceeds the 2 Bytes value-type width (0 to 65535)."),
            ('<DropDownList>-1:Neg</DropDownList>', "4 Bytes",
             "Dropdown choice '-1' exceeds the 4 Bytes value-type width (0 to 4294967295)."),
            ('<ShowAsSigned>1</ShowAsSigned><DropDownList>-2147483649:Neg</DropDownList>', "4 Bytes",
             "Dropdown choice '-2147483649' exceeds the 4 Bytes value-type width (-2147483648 to 2147483647)."),
            ('<ShowAsSigned>1</ShowAsSigned><DropDownList>2147483648:Pos</DropDownList>', "4 Bytes",
             "Dropdown choice '2147483648' exceeds the 4 Bytes value-type width (-2147483648 to 2147483647)."),
            ('<ShowAsHex>1</ShowAsHex><DropDownList>100000000:Big</DropDownList>', "4 Bytes",
             "Dropdown choice '100000000' exceeds the 4 Bytes value-type width (0 to 4294967295)."),
        )
        for extra, value_type, expected_reason in cases:
            with self.subTest(value_type=value_type, extra=extra):
                standalone = self.root / "width.ct"
                standalone.write_text(
                    '<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
                    f'<CheatEntry><ID>6100</ID><Description>Width</Description>'
                    f'<VariableType>{value_type}</VariableType><Address>1090</Address>'
                    f'{extra}</CheatEntry>'
                    '</CheatEntries></CheatTable>', encoding="utf-8")
                entry = compile_table(standalone, "FixtureTarget.exe")["entries"][0]
                self.assertFalse(entry["supported"], entry["reason"])
                self.assertEqual(entry["reason"], expected_reason)

    def test_comma_decimal_float_choices_normalize_to_dot_form(self):
        # WP-34 (FLAG-2 follow-up 3): comma-decimal Float/Double choice
        # literals normalize to the canonical dot form in the plan; the
        # record stays supported and runtime-writable.
        table = self.root / "comma.ct"
        table.write_text(
            '<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
            '<CheatEntry><ID>6200</ID><Description>Comma Float</Description>'
            '<VariableType>Float</VariableType><Address>1090</Address>'
            '<DropDownList>0:None\n3,5:Weird\n-2,25:Neg</DropDownList></CheatEntry>'
            '</CheatEntries></CheatTable>', encoding="utf-8")
        plan = compile_table(table, "FixtureTarget.exe")
        entry = plan["entries"][0]
        self.assertTrue(entry["supported"], entry["reason"])
        self.assertEqual(entry["dropdown"]["choices"], [
            {"value": "0", "description": "None"},
            {"value": "3.5", "description": "Weird"},
            {"value": "-2.25", "description": "Neg"},
        ])
        validate_plan(plan)
        validate_runtime_plan(plan)
        # The normalized literal is what the runtime accepts and stores.
        engine = TrainerEngine(plan, state_dir=self.root / "state_comma",
                               process_lock_dir=self.root / "shared_comma",
                               memory_factory=lambda name: self.memory,
                               hook_coordinator=self.coordinator)
        self.addCleanup(engine.close)
        engine.poll()
        self.assertEqual(engine.set_value(6200, "3.5"), "3.5")
        self.assertEqual(self.memory.read(0x1090, 4), b"\x00\x00\x60\x40")
        # A comma on an integer record stays a generic refusal (the
        # normalization is Float/Double only).
        standalone = self.root / "comma_byte.ct"
        standalone.write_text(
            '<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
            '<CheatEntry><ID>6300</ID><Description>Comma Byte</Description>'
            '<VariableType>Byte</VariableType><Address>1090</Address>'
            '<DropDownList>1,5:Comma</DropDownList></CheatEntry>'
            '</CheatEntries></CheatTable>', encoding="utf-8")
        byte_entry = compile_table(standalone, "FixtureTarget.exe")["entries"][0]
        self.assertFalse(byte_entry["supported"])
        self.assertEqual(byte_entry["reason"],
                         "Dropdown contains an unsupported value expression.")

    def test_compiled_separator_plan_passes_both_validators(self):
        plan = compile_table(self.table, "FixtureTarget.exe")
        validate_plan(plan)
        validate_runtime_plan(plan)


if __name__ == "__main__":
    unittest.main()
