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
            ("display-only marker on a writable list",
             lambda plan: by_id(plan)[5000]["dropdown"]["choices"][0].update(writable=False),
             "Display-only dropdown choices require a read-only dropdown."),
            ("writable marker as true",
             lambda plan: by_id(plan)[5000]["dropdown"]["choices"][0].update(writable=True),
             "Dropdown writable marker must be false."),
            ("unparseable choice smuggled into a RO list",
             lambda plan: by_id(plan)[5001]["dropdown"]["choices"][1].update(value="3,5"),
             "Dropdown values must be exact supported literals."),
            ("expression marker as false",
             lambda plan: by_id(plan)[5000]["dropdown"]["choices"][0].update(expression=False),
             "Dropdown expression marker must be true."),
            ("malformed expression choice",
             lambda plan: by_id(plan)[5000]["dropdown"]["choices"][0].update(value="[", expression=True),
             "Dropdown expression choice is not a valid address expression."),
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
        # RT-4.4 (O6): a separator row mixed with an over-width literal no
        # longer refuses the record; the choice is staged and the write
        # truncates to the record's width (CE typed-pointer parity).
        mixed = self.root / "mixed.ct"
        mixed.write_text(
            '<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
            '<CheatEntry><ID>6001</ID><Description>Mixed</Description>'
            '<VariableType>Byte</VariableType><Address>1090</Address>'
            '<DropDownList>\n:Section:\n300:Big\n</DropDownList></CheatEntry>'
            '</CheatEntries></CheatTable>', encoding="utf-8")
        plan = compile_table(mixed, "FixtureTarget.exe")
        entry = plan["entries"][0]
        self.assertTrue(entry["supported"], entry["reason"])
        self.assertEqual(entry["dropdown"]["choices"],
                         [{"value": "", "description": "Section:", "separator": True},
                          {"value": "300", "description": "Big"}])
        validate_plan(plan)
        validate_runtime_plan(plan)
        engine = TrainerEngine(plan, state_dir=self.root / "state_mixed",
                               process_lock_dir=self.root / "shared_mixed",
                               memory_factory=lambda name: self.memory,
                               hook_coordinator=self.coordinator)
        self.addCleanup(engine.close)
        engine.poll()
        self.assertEqual(engine.set_value(6001, "300"), "44")
        self.assertEqual(self.memory.read(0x1090, 1), b"\x2c")

    def test_integer_choices_truncate_to_the_type_width_on_write(self):
        # RT-4.4 (O6): integer dropdown choices outside the record's width
        # are no longer compile refusals; the engine stores the low
        # width bits, matching CE's typed-pointer store (SetValue).
        cases = (
            # (extra XML, value type, choice literal, expected written bytes)
            ('<DropDownList>314:Big</DropDownList>', "Byte", "314", b"\x3a"),
            ('<DropDownList>70000:Big</DropDownList>', "2 Bytes", "70000", b"\x70\x11"),
            ('<DropDownList>-1:Neg</DropDownList>', "4 Bytes", "-1", b"\xff\xff\xff\xff"),
            ('<ShowAsSigned>1</ShowAsSigned>'
             '<DropDownList>-2147483649:Neg</DropDownList>', "4 Bytes",
             "-2147483649", b"\xff\xff\xff\x7f"),
            ('<ShowAsSigned>1</ShowAsSigned>'
             '<DropDownList>2147483648:Pos</DropDownList>', "4 Bytes",
             "2147483648", b"\x00\x00\x00\x80"),
            ('<ShowAsHex>1</ShowAsHex><DropDownList>100000000:Big</DropDownList>',
             "4 Bytes", "100000000", b"\x00\x00\x00\x00"),
            # RT-4.4 (O8): hex-style choice on a decimal-mode record
            # (corpus P4G shape) parses in the alternate base.
            ('<DropDownList>01E7:Hex</DropDownList>', "2 Bytes", "01E7", b"\xe7\x01"),
        )
        for index, (extra, value_type, literal, expected_bytes) in enumerate(cases):
            with self.subTest(index=index, value_type=value_type, literal=literal):
                standalone = self.root / "width.ct"
                standalone.write_text(
                    '<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
                    f'<CheatEntry><ID>6100</ID><Description>Width</Description>'
                    f'<VariableType>{value_type}</VariableType><Address>1090</Address>'
                    f'{extra}</CheatEntry>'
                    '</CheatEntries></CheatTable>', encoding="utf-8")
                plan = compile_table(standalone, "FixtureTarget.exe")
                entry = plan["entries"][0]
                self.assertTrue(entry["supported"], entry["reason"])
                validate_plan(plan)
                validate_runtime_plan(plan)
                engine = TrainerEngine(plan, state_dir=self.root / f"state_w{index}",
                                       process_lock_dir=self.root / f"shared_w{index}",
                                       memory_factory=lambda name: self.memory,
                                       hook_coordinator=self.coordinator)
                self.addCleanup(engine.close)
                engine.poll()
                before = list(self.memory.writes)
                engine.set_value(6100, literal)
                self.assertEqual(self.memory.read(0x1090, len(expected_bytes)),
                                 expected_bytes)
                self.assertEqual(self.memory.writes[len(before):],
                                 [(0x1090, expected_bytes)])

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

    def test_read_only_display_only_lists_are_supported(self):
        # RT-4.4 (O26): a read-only dropdown without concrete writable
        # choices stages as an empty display view instead of a refusal;
        # the record keeps its normal value semantics and every write is
        # refused against the (possibly empty) writable choice set.
        bodies = (
            # separators only (previously: "Read-only dropdown has no
            # concrete literal choices.")
            ('<DropDownList ReadOnly="1">\n:Only:\n:Nothing:\n</DropDownList>',
             [{"value": "", "description": "Only:", "separator": True},
              {"value": "", "description": "Nothing:", "separator": True}]),
            # unparseable display sentinels (corpus '??' marker) staged as
            # non-writable rows on a read-only list
            ('<DropDownList ReadOnly="1">\n??:Unreadable\n1:One\n</DropDownList>',
             [{"value": "??", "description": "Unreadable", "writable": False},
              {"value": "1", "description": "One"}]),
            # a fully empty read-only list
            ('<DropDownList ReadOnly="1"></DropDownList>', []),
        )
        for index, (extra, expected_choices) in enumerate(bodies):
            with self.subTest(index=index):
                standalone = self.root / f"ro_{index}.ct"
                standalone.write_text(
                    '<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
                    f'<CheatEntry><ID>6400</ID><Description>RO View</Description>'
                    f'<VariableType>Byte</VariableType><Address>1090</Address>'
                    f'{extra}</CheatEntry>'
                    '</CheatEntries></CheatTable>', encoding="utf-8")
                plan = compile_table(standalone, "FixtureTarget.exe")
                entry = plan["entries"][0]
                self.assertTrue(entry["supported"], entry["reason"])
                self.assertTrue(entry["dropdown"]["read_only"])
                self.assertEqual(entry["dropdown"]["choices"], expected_choices)
                validate_plan(plan)
                validate_runtime_plan(plan)
                engine = TrainerEngine(plan, state_dir=self.root / f"state_ro{index}",
                                       process_lock_dir=self.root / f"shared_ro{index}",
                                       memory_factory=lambda name: self.memory,
                                       hook_coordinator=self.coordinator)
                self.addCleanup(engine.close)
                engine.poll()
                before = list(self.memory.writes)
                writable_literals = [c["value"] for c in expected_choices
                                     if "writable" not in c
                                     and c.get("separator") is not True]
                if not writable_literals:
                    # The writable set is empty (display rows only), so
                    # every write is refused against it.
                    with self.assertRaisesRegex(NativeRuntimeError,
                                                "supplied list"):
                        engine.set_value(6400, "1")
                else:
                    # A value outside the writable set is still refused.
                    with self.assertRaisesRegex(NativeRuntimeError,
                                                "supplied list"):
                        engine.set_value(6400, "0")
                    # The writable literal still writes byte-exactly.
                    engine.set_value(6400, writable_literals[0])
                    self.assertEqual(self.memory.read(0x1090, 1),
                                     bytes([int(writable_literals[0]) & 0xFF]))
                # The sentinel literal itself is not a byte at all and is
                # refused at parse time.
                with self.assertRaisesRegex(NativeRuntimeError,
                                            "Enter a whole decimal number"):
                    engine.set_value(6400, "??")

    def test_display_sentinel_rows_are_never_writable_on_read_only_lists(self):
        # RT-4.4 (O8): the '??' sentinel stays out of the writable set even
        # when sibling choices are writable literals.
        standalone = self.root / "sentinel.ct"
        standalone.write_text(
            '<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
            '<CheatEntry><ID>6500</ID><Description>Sentinel</Description>'
            '<VariableType>Float</VariableType><Address>1090</Address>'
            '<DropDownList ReadOnly="1">\n0:None\n??:Unknown\n</DropDownList>'
            '</CheatEntry>'
            '</CheatEntries></CheatTable>', encoding="utf-8")
        plan = compile_table(standalone, "FixtureTarget.exe")
        entry = plan["entries"][0]
        self.assertTrue(entry["supported"], entry["reason"])
        self.assertEqual(entry["dropdown"]["choices"],
                         [{"value": "0", "description": "None"},
                          {"value": "??", "description": "Unknown",
                           "writable": False}])
        validate_plan(plan)
        validate_runtime_plan(plan)
        engine = TrainerEngine(plan, state_dir=self.root / "state_sentinel",
                               process_lock_dir=self.root / "shared_sentinel",
                               memory_factory=lambda name: self.memory,
                               hook_coordinator=self.coordinator)
        self.addCleanup(engine.close)
        engine.poll()
        before = list(self.memory.writes)
        # The sentinel literal itself is not a finite number; it is
        # refused at parse time and never treated as a selectable row.
        with self.assertRaisesRegex(NativeRuntimeError,
                                    "Enter a finite decimal number"):
            engine.set_value(6500, "??")
        # A value outside the writable choice set is refused by the
        # read-only allowed-set check; the display row is not in it.
        with self.assertRaisesRegex(NativeRuntimeError,
                                    "supplied list"):
            engine.set_value(6500, "0.5")
        self.assertEqual(self.memory.writes, before)
        # The one writable literal still writes byte-exactly.
        engine.set_value(6500, "0")
        self.assertEqual(self.memory.read(0x1090, 4), b"\x00\x00\x00\x00")
        self.assertEqual(self.memory.writes[len(before):],
                         [(0x1090, b"\x00\x00\x00\x00")])
        # A plain writable Float record's sentinel stays a compile refusal.
        writable = self.root / "sentinel_writable.ct"
        writable.write_text(
            '<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
            '<CheatEntry><ID>6600</ID><Description>Sentinel W</Description>'
            '<VariableType>Float</VariableType><Address>1090</Address>'
            '<DropDownList>\n0:None\n??:Unknown\n</DropDownList>'
            '</CheatEntry>'
            '</CheatEntries></CheatTable>', encoding="utf-8")
        blocked = compile_table(writable, "FixtureTarget.exe")["entries"][0]
        self.assertFalse(blocked["supported"])
        self.assertEqual(blocked["reason"],
                         "Dropdown contains an unsupported value expression.")
        self.assertEqual(self.memory.writes[len(before):],
                         [(0x1090, b"\x00\x00\x00\x00")])


if __name__ == "__main__":
    unittest.main()
