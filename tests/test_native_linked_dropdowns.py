"""WP-27: linked dropdowns against profile value records (byte arrays, bit fields).

Corpus semantics: a DropDownListLink record borrows the choice rows of the
named target record, keeps its own address and value type, and writes each
choice literal to its OWN address under its OWN value profile (simple
literal policy or byte-array/bit-field profile).  Every borrowed choice is
validated against the linked record's own type at compile time; per-choice
refusals name the offending literal.  The engine writes byte-exact raw
bytes, never touches the source list address, preserves unowned bit-field
bits, and freeze restore covers linked profile records.  Both plan
validators refuse forged choice metadata (the compiler layer keeps the
generic tamper message; the runtime layer surfaces the underlying
profile error).
"""
from contextlib import contextmanager
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
from ct2trainer.native.hooks import QuiescenceProof


class DataCoordinator(Coordinator):
    def __init__(self):
        super().__init__()
        self.data_holds = []

    @contextmanager
    def hold_data(self, memory, ranges):
        self.data_holds.append(tuple(ranges))
        yield QuiescenceProof(memory.identity, tuple(ranges), 'owned-data-unit',
                              lambda: True)


CT_BODY = '''<CheatTable CheatEngineTableVersion="45"><CheatEntries>
<CheatEntry><ID>7000</ID><Description>ByteArray Source</Description><VariableType>Array of byte</VariableType><Address>1040</Address><ByteLength>2</ByteLength><ShowAsHex>1</ShowAsHex><DropDownList>
00 01:Alpha
AB CD:Beta
</DropDownList></CheatEntry>
<CheatEntry><ID>7001</ID><Description>ByteArray Link</Description><VariableType>Array of byte</VariableType><Address>1044</Address><ByteLength>2</ByteLength><ShowAsHex>1</ShowAsHex><DropDownListLink>ByteArray Source</DropDownListLink></CheatEntry>
<CheatEntry><ID>7002</ID><Description>Bitfield Source</Description><VariableType>Binary</VariableType><Address>1048</Address><BitStart>0</BitStart><BitLength>4</BitLength><DropDownList>
0:Off
3:All
</DropDownList></CheatEntry>
<CheatEntry><ID>7003</ID><Description>Bitfield Link</Description><VariableType>Binary</VariableType><Address>104C</Address><BitStart>4</BitStart><BitLength>4</BitLength><DropDownListLink>Bitfield Source</DropDownListLink></CheatEntry>
<CheatEntry><ID>7004</ID><Description>Byte Source</Description><VariableType>Byte</VariableType><Address>1050</Address><DropDownList>
1:Low
2:High
</DropDownList></CheatEntry>
<CheatEntry><ID>7005</ID><Description>Byte Link</Description><VariableType>Byte</VariableType><Address>1054</Address><DropDownListLink>Byte Source</DropDownListLink></CheatEntry>
<CheatEntry><ID>7006</ID><Description>RO Source</Description><VariableType>Byte</VariableType><Address>1058</Address><DropDownList ReadOnly="1">
5:Five
6:Six
</DropDownList></CheatEntry>
<CheatEntry><ID>7007</ID><Description>RO Link</Description><VariableType>Byte</VariableType><Address>105C</Address><DropDownListLink>RO Source</DropDownListLink></CheatEntry>
</CheatEntries></CheatTable>'''

ARRAY_CHOICES = [{"value": "00 01", "description": "Alpha"},
                 {"value": "AB CD", "description": "Beta"}]
FIELD_CHOICES = [{"value": "0", "description": "Off"},
                 {"value": "3", "description": "All"}]
BYTE_CHOICES = [{"value": "1", "description": "Low"},
                {"value": "2", "description": "High"}]


class LinkedDropdownCompileTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.table = self.root / "linked.ct"
        self.table.write_text(CT_BODY, encoding="utf-8")
        self.plan = compile_table(self.table, "FixtureTarget.exe")
        self.by_id = {entry["id"]: entry for entry in self.plan["entries"]}

    def test_linked_profile_records_compile_supported_with_borrowed_choices(self):
        self.assertEqual(self.plan["counts"],
                         {"total": 8, "supported": 8, "actionable": 8,
                          "blocked": 0, "headings": 0})
        array_link = self.by_id[7001]
        self.assertEqual(array_link["dropdown"]["choices"], ARRAY_CHOICES)
        self.assertEqual(array_link["dropdown"]["link_target_id"], 7000)
        self.assertFalse(array_link["dropdown"]["read_only"])
        field_link = self.by_id[7003]
        self.assertEqual(field_link["dropdown"]["choices"], FIELD_CHOICES)
        self.assertEqual(field_link["dropdown"]["link_target_id"], 7002)
        byte_link = self.by_id[7005]
        self.assertEqual(byte_link["dropdown"]["choices"], BYTE_CHOICES)
        self.assertEqual(byte_link["dropdown"]["link_target_id"], 7004)
        ro_link = self.by_id[7007]
        self.assertEqual(ro_link["dropdown"]["choices"],
                         [{"value": "5", "description": "Five"},
                          {"value": "6", "description": "Six"}])
        self.assertTrue(ro_link["dropdown"]["read_only"])
        # The source lists keep their own choices and carry no link marker.
        self.assertEqual(self.by_id[7000]["dropdown"]["choices"], ARRAY_CHOICES)
        self.assertNotIn("link_target_id", self.by_id[7000]["dropdown"])
        # The linked records keep their own value profiles.
        self.assertEqual(array_link["value_profile"]["kind"], "byte_array")
        self.assertEqual(array_link["value_profile"]["size"], 2)
        self.assertEqual(field_link["value_profile"]["kind"], "bitfield")
        self.assertEqual(field_link["value_profile"]["properties"]["BitStart"], 4)

    def test_linked_profile_plan_passes_both_validators(self):
        validate_plan(self.plan)
        validate_runtime_plan(self.plan)

    def test_forged_choice_metadata_rejected_by_both_validators(self):
        # Wrong byte count on the linked byte array (compiler: generic
        # tamper message; runtime: the profile's own error).
        tampered = deepcopy(self.plan)
        by_id = {entry["id"]: entry for entry in tampered["entries"]}
        by_id[7001]["dropdown"]["choices"][0]["value"] = "AB"
        with self.assertRaises(NativeCompileError) as compile_error:
            validate_plan(deepcopy(tampered))
        self.assertEqual(str(compile_error.exception),
                         "Dropdown values must be exact supported literals.")
        with self.assertRaises(NativeRuntimeError) as runtime_error:
            validate_runtime_plan(deepcopy(tampered))
        # The runtime validator delegates to the compiler validator first, so
        # the same generic tamper refusal is surfaced.
        self.assertEqual(str(runtime_error.exception),
                         "Dropdown values must be exact supported literals.")
        # Out-of-range choice on the linked bit field.
        tampered = deepcopy(self.plan)
        by_id = {entry["id"]: entry for entry in tampered["entries"]}
        by_id[7003]["dropdown"]["choices"][1]["value"] = "16"
        with self.assertRaises(NativeCompileError) as compile_error:
            validate_plan(deepcopy(tampered))
        self.assertEqual(str(compile_error.exception),
                         "Dropdown values must be exact supported literals.")
        with self.assertRaises(NativeRuntimeError) as runtime_error:
            validate_runtime_plan(deepcopy(tampered))
        self.assertEqual(str(runtime_error.exception),
                         "Dropdown values must be exact supported literals.")


class LinkedDropdownCompileRefusalTests(unittest.TestCase):
    """Per-choice compile-time refusals name the offending literal."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def compile(self, body):
        table = self.root / "refusal.ct"
        table.write_text('<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
                         + body + '</CheatEntries></CheatTable>', encoding="utf-8")
        return compile_table(table, "FixtureTarget.exe")

    def test_byte_array_mixed_length_choice_refused_with_named_choice(self):
        body = ('<CheatEntry><ID>7100</ID><Description>Array Mixed</Description>'
                '<VariableType>Array of byte</VariableType><Address>1040</Address>'
                '<ByteLength>2</ByteLength><ShowAsHex>1</ShowAsHex>'
                '<DropDownList>01:Short\n01 02:Full</DropDownList></CheatEntry>')
        entry = self.compile(body)["entries"][0]
        self.assertFalse(entry["supported"])
        self.assertEqual(entry["reason"],
                         "Dropdown choice '01' must contain exactly 2 hex bytes "
                         "for this byte array record.")

    def test_bit_field_out_of_range_choice_refused_with_named_choice(self):
        body = ('<CheatEntry><ID>7101</ID><Description>Field Range</Description>'
                '<VariableType>Binary</VariableType><Address>1040</Address>'
                '<BitStart>0</BitStart><BitLength>4</BitLength>'
                '<DropDownList>0:Off\n16:Big</DropDownList></CheatEntry>')
        entry = self.compile(body)["entries"][0]
        self.assertFalse(entry["supported"])
        self.assertEqual(entry["reason"],
                         "Dropdown choice '16' is outside the bit-field value "
                         "range (must be between 0 and 15).")

    def test_linked_byte_array_borrowing_mismatched_choices_refused(self):
        # The source choices are valid for the source (2-byte array) but not
        # for the linked record's own 1-byte profile: the refusal names the
        # first offending choice.
        body = ('<CheatEntry><ID>7102</ID><Description>Wide Source</Description>'
                '<VariableType>Array of byte</VariableType><Address>1040</Address>'
                '<ByteLength>2</ByteLength><ShowAsHex>1</ShowAsHex>'
                '<DropDownList>00 01:Alpha</DropDownList></CheatEntry>'
                '<CheatEntry><ID>7103</ID><Description>Narrow Link</Description>'
                '<VariableType>Array of byte</VariableType><Address>1044</Address>'
                '<ByteLength>1</ByteLength><ShowAsHex>1</ShowAsHex>'
                '<DropDownListLink>Wide Source</DropDownListLink></CheatEntry>')
        entries = self.compile(body)["entries"]
        self.assertTrue(entries[0]["supported"], entries[0]["reason"])
        self.assertFalse(entries[1]["supported"])
        self.assertEqual(entries[1]["reason"],
                         "Dropdown choice '00 01' must contain exactly 1 hex bytes "
                         "for this byte array record.")


class CorpusLinkDiagnosticShapeTests(unittest.TestCase):
    def test_corpus_link_refusals_use_the_split_messages(self):
        # WP-34 (FLAG-2 follow-up 1a): catalog shape over the pinned corpus —
        # the old generic "missing or ambiguous" refusal is gone; every
        # link-target refusal is either the exact missing message or the
        # ambiguous message carrying a candidate count of at least two.
        corpus = Path(__file__).resolve().parents[1] / "TableReferences"
        if not corpus.exists():
            self.skipTest(
                "The synthetic clean-room corpus is intentionally excluded "
                "from the Native source distribution.")
        paths = sorted(corpus.glob("*.ct"))
        self.assertEqual(len(paths), 24, "The repository compatibility corpus "
                                         "must retain all 24 case tables.")
        missing = ambiguous = 0
        for path in paths:
            with self.subTest(path=path.name):
                plan = compile_table(path, "Target.exe")
                for entry in plan["entries"]:
                    reason = entry.get("reason") or ""
                    if not reason.startswith("Dropdown link target is"):
                        continue
                    if reason.endswith("matches no record label."):
                        missing += 1
                    elif reason.endswith(" record labels."):
                        count = int(reason.split("matches ", 1)[1].split(" ", 1)[0])
                        self.assertGreaterEqual(count, 2, reason)
                        ambiguous += 1
                    else:
                        self.fail("unexpected link-target refusal shape: " + reason)
        # The pinned corpus carries exactly one unresolvable link target:
        # case-16 part 2's dangling link (record 14, "no such list").
        self.assertEqual((missing, ambiguous), (1, 0))


class LinkedDropdownEngineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.table = self.root / "linked.ct"
        self.table.write_text(CT_BODY, encoding="utf-8")
        self.memory = Memory()
        self.coordinator = DataCoordinator()
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

    def test_linked_byte_array_writes_exact_bytes_to_own_address(self):
        self.assertEqual(self.engine.set_value(7001, "AB CD"), "AB CD")
        self.assertEqual(self.memory.read(0x1044, 2), b"\xab\xcd")
        # The source list address is never written.
        self.assertEqual(self.memory.read(0x1040, 2), b"\x00\x00")
        self.assertEqual(self.engine.read_value(7001), "AB CD")
        self.assertEqual(self.engine.set_value(7001, "00 01"), "00 01")
        self.assertEqual(self.memory.read(0x1044, 2), b"\x00\x01")

    def test_linked_bit_field_preserves_unowned_bits(self):
        # Unowned low nibble pre-set: a linked field write must keep it.
        self.memory.data[0x4C] = 0x0F
        self.assertEqual(self.engine.set_value(7003, "3"), "3")
        self.assertEqual(self.memory.read(0x104C, 1), b"\x3f")
        self.assertEqual(self.engine.read_value(7003), "3")
        self.assertEqual(self.engine.set_value(7003, "0"), "0")
        self.assertEqual(self.memory.read(0x104C, 1), b"\x0f")
        # The source field address is untouched by the linked write.
        self.assertEqual(self.memory.read(0x1048, 1), b"\x00")

    def test_linked_simple_byte_still_writes_own_address(self):
        self.assertEqual(self.engine.set_value(7005, "2"), "2")
        self.assertEqual(self.memory.read(0x1054, 1), b"\x02")
        self.assertEqual(self.memory.read(0x1050, 1), b"\x00")

    def test_read_only_linked_list_accepts_only_concrete_choices(self):
        before = list(self.memory.writes)
        with self.assertRaisesRegex(NativeRuntimeError,
                                    "Choose a value from the supplied list"):
            self.engine.set_value(7007, "9")
        self.assertEqual(self.memory.writes, before)
        self.assertEqual(self.engine.set_value(7007, "5"), "5")
        self.assertEqual(self.memory.read(0x105C, 1), b"\x05")
        # The source RO list address is untouched.
        self.assertEqual(self.memory.read(0x1058, 1), b"\x00")

    def test_freeze_roundtrip_on_linked_byte_array(self):
        self.engine.set_value(7001, "AB CD")
        self.engine.set_freeze(7001, True)
        self.memory.data[0x44:0x46] = b"\x00\x00"
        self.engine.poll()
        self.assertFalse(self.engine.blocked, self.engine.error)
        self.assertEqual(self.memory.read(0x1044, 2), b"\xab\xcd")


if __name__ == "__main__":
    unittest.main()
