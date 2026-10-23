"""RT-3: legacy pre-XML binary CT tables load through a clean-room reader.

CE 5.x-era tables are not XML.  This module pins the byte-level parse of the
version-6..9 layout, the variable-type mapping, the binary -> standard-XML
conversion (sequential IDs in document order, "Group N" headers, CheatCodes),
the ``read_table`` dispatch, ``compile_table`` + plan validation, engine-level
value writes and Auto Assembler activation, and every named fail-closed
refusal (truncation, corrupt magic, too-old version, implausible counts).

All fixtures are self-authored synthetic bytes; no original table bytes
appear in this file.  The local-only version-9 reference table is exercised
by one optional test at the end that skips when the file is absent.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from test_native_engine_code import Coordinator  # noqa: E402
from test_native_lua_activation import Memory  # noqa: E402 (shared fixture memory)

from ct2trainer.legacy_ct import LegacyCTError, legacy_ct_to_xml, parse_legacy_ct
from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import TrainerEngine, validate_plan
from ct2trainer.table import TableError, read_table


PROCESS = "game.exe"

REAL_REFERENCE = Path(
    r"C:\Users\xboxl\code\reference-table-input-do-not-add-to-git\SuperMeatBoy.CT")
REAL_REFERENCE_SHA256 = (
    "6ea211241aa62707b4df8ea8fb71a67386b8482c43d32956fe6bc91d722c3ac1")
REAL_REFERENCE_LABELS = (
    "Unlimited Lives",
    "Float mode",
    "No damage from environment",
    "No damage from enemies Update",
    "Unlimited Time",
    "Fly up Update",
    "Unlimited Jumps for Flywrench",
    "Unlimited Jumps for OGMO",
    "Unlimited Jumps for Josef",
    "Unlimited Float time for Commander Video",
)


def d32(value: int) -> bytes:
    return value.to_bytes(4, "little")


def blob(text: str) -> bytes:
    return text.encode("utf-8")


def build_record(description="Record", address=0x1000, interpretable="",
                 vtype=2, unicode_flag=0, length=4, bit_length=32,
                 group=0, show_hex=0, is_pointer_flag=0, pointers=(),
                 script="") -> bytes:
    """One legacy record: desc, static address, interpretable address,
    vtype/unicode/length bytes, bit length, group/hex/is-pointer bytes,
    pointer count + pointers, script length + script."""
    parts = [
        d32(len(blob(description))) + blob(description),
        d32(address),
        d32(len(blob(interpretable))) + blob(interpretable),
        bytes((vtype & 0xFF, unicode_flag & 0xFF, length & 0xFF)),
        d32(bit_length),
        bytes((group & 0xFF, show_hex & 0xFF, is_pointer_flag & 0xFF)),
        d32(len(pointers)),
    ]
    for pointer_address, pointer_offset, pointer_interp in pointers:
        parts.append(d32(pointer_address) + d32(pointer_offset))
        parts.append(d32(len(blob(pointer_interp))) + blob(pointer_interp))
    parts.append(d32(len(blob(script))) + blob(script))
    return b"".join(parts)


def build_code_record(address=0x1100, module_name="game.exe", module_offset=0x20,
                      before=(0x90,), actual=(0xE9, 0x1B), after=(),
                      description="Code patch") -> bytes:
    """One legacy code record: address, 1-byte-length module name, module
    offset, 1-byte-length before/actual/after byte arrays, description."""
    parts = [d32(address)]
    name = blob(module_name)
    parts.append(bytes((len(name),)) + name)
    parts.append(d32(module_offset))
    for values in (before, actual, after):
        parts.append(bytes((len(values),)) + bytes(values))
    desc = blob(description)
    parts.append(bytes((len(desc),)) + desc)
    return b"".join(parts)


def build_table(version=9, records=(), code_records=(), trailer=b"") -> bytes:
    """The full legacy layout: 11-byte magic, version, records,
    code-record count + code records, optional trailer."""
    parts = [b"CHEATENGINE", d32(version), d32(len(records))]
    parts.extend(records)
    parts.append(d32(len(code_records)))
    parts.extend(code_records)
    parts.append(trailer)
    return b"".join(parts)


class ParseTests(unittest.TestCase):
    def test_fields_parse_verbatim(self):
        trailer = b"NOTES:" + b" " * 10
        table = parse_legacy_ct(build_table(
            version=9,
            records=[
                build_record("HP", address=0x1040, interpretable="HP",
                             vtype=2, length=4, bit_length=32, group=0),
                build_record("Ptr", address=0x2000, interpretable="Base",
                             vtype=3, unicode_flag=1, length=8, bit_length=64,
                             group=2, show_hex=1, is_pointer_flag=1,
                             pointers=((0x3000, 0x18, "PtrA"),
                                       (0x4000, 0x20, "game.exe+100"))),
                build_record("AA", vtype=255,
                             script="[ENABLE]\n1040:\ndb 01\n[DISABLE]\n1040:\ndb 00"),
            ],
            code_records=[build_code_record()],
            trailer=trailer,
        ))
        self.assertEqual(table.version, 9)
        self.assertEqual(len(table.records), 3)
        hp, ptr, aa = table.records
        self.assertEqual((hp.description, hp.address, hp.interpretable),
                         ("HP", 0x1040, "HP"))
        self.assertEqual(hp.variable_type, 2)
        self.assertFalse(hp.unicode)
        self.assertEqual((hp.length, hp.bit_length), (4, 32))
        self.assertEqual((hp.group, hp.show_as_hex, hp.is_pointer), (0, False, False))
        self.assertEqual(hp.pointers, ())
        self.assertEqual(hp.script, "")
        self.assertEqual((ptr.description, ptr.address, ptr.interpretable),
                         ("Ptr", 0x2000, "Base"))
        self.assertTrue(ptr.unicode)
        self.assertEqual((ptr.length, ptr.bit_length), (8, 64))
        self.assertEqual((ptr.group, ptr.show_as_hex, ptr.is_pointer), (2, True, True))
        self.assertEqual(len(ptr.pointers), 2)
        self.assertEqual(ptr.pointers[0].address, 0x3000)
        self.assertEqual(ptr.pointers[0].offset, 0x18)
        self.assertEqual(ptr.pointers[0].interpretable, "PtrA")
        self.assertEqual(ptr.pointers[1].address, 0x4000)
        self.assertEqual(ptr.pointers[1].offset, 0x20)
        self.assertEqual(ptr.pointers[1].interpretable, "game.exe+100")
        self.assertEqual(aa.variable_type, 255)
        self.assertEqual(aa.script,
                         "[ENABLE]\n1040:\ndb 01\n[DISABLE]\n1040:\ndb 00")
        self.assertEqual(len(table.code_records), 1)
        code = table.code_records[0]
        self.assertEqual(code.address, 0x1100)
        self.assertEqual(code.module_name, "game.exe")
        self.assertEqual(code.module_offset, 0x20)
        self.assertEqual(code.before, (0x90,))
        self.assertEqual(code.actual, (0xE9, 0x1B))
        self.assertEqual(code.after, ())
        self.assertEqual(code.description, "Code patch")
        self.assertEqual(table.trailing_bytes, len(trailer))

    def test_variable_type_mapping(self):
        expected = {
            0: "Byte",
            1: "2 Bytes",
            2: "4 Bytes",
            3: "Float",
            4: "Double",
            5: "Binary",
            6: "8 Bytes",
            7: "String",
            8: "Array of byte",
            10: "Custom",
            255: "Auto Assembler Script",
            42: "4 Bytes",  # unknown code falls back like the reference
        }
        for code, name in expected.items():
            parsed = parse_legacy_ct(build_table(
                records=[build_record("V", vtype=code)]))
            root = ET.fromstring(legacy_ct_to_xml(parsed))
            self.assertEqual(root.findtext(".//VariableType"), name,
                             "variable type code %d" % code)


class ConversionTests(unittest.TestCase):
    def test_sequential_ids_follow_document_order_with_groups(self):
        parsed = parse_legacy_ct(build_table(
            version=9,
            records=[
                build_record("Top One", group=0),
                build_record("In Two", group=2),
                build_record("Top Two", group=0),
                build_record("In Two B", group=2),
                build_record("In Five", group=5),
            ]))
        root = ET.fromstring(legacy_ct_to_xml(parsed))
        self.assertEqual(root.attrib.get("CheatEngineTableVersion"), "9")
        # document order over all entries (top-level + group members)
        all_entries = list(root.iter("CheatEntry"))
        self.assertEqual([e.findtext("ID") for e in all_entries],
                         ["1", "2", "3", "4", "5", "6", "7"])
        self.assertEqual([e.findtext("Description") for e in all_entries],
                         ["Top One", "Top Two", "Group 2", "In Two", "In Two B",
                          "Group 5", "In Five"])
        # top level: the two top-level records + the two "Group N" headers
        top = root.findall("./CheatEntries/CheatEntry")
        self.assertEqual([e.findtext("ID") for e in top], ["1", "2", "3", "6"])
        group2 = top[2]
        self.assertEqual(group2.findtext("Description"), "Group 2")
        self.assertEqual(group2.findtext("GroupHeader"), "1")
        self.assertEqual(
            [m.findtext("Description") for m in group2.findall(
                "./CheatEntries/CheatEntry")],
            ["In Two", "In Two B"])

    def test_group_index_above_six_stays_top_level(self):
        parsed = parse_legacy_ct(build_table(
            records=[build_record("Stray", group=7)]))
        root = ET.fromstring(legacy_ct_to_xml(parsed))
        self.assertEqual(len(root.findall("./CheatEntries/CheatEntry")), 1)
        self.assertIsNone(root.find(".//GroupHeader"))

    def test_pointer_offsets_and_last_address_survive(self):
        parsed = parse_legacy_ct(build_table(
            records=[build_record(
                "Chained", address=0x0, interpretable="",
                pointers=((0x1000, 0x0A, ""), (0x2000, 0x10, "game.exe+40")),
            )]))
        root = ET.fromstring(legacy_ct_to_xml(parsed))
        entry = root.find("./CheatEntries/CheatEntry")
        self.assertEqual(entry.findtext("Address"), "game.exe+40")
        self.assertEqual([o.text for o in entry.findall("./Offsets/Offset")],
                         ["A", "10"])

    def test_static_address_fallback_is_uppercase_hex(self):
        parsed = parse_legacy_ct(build_table(
            records=[build_record("Hex", address=0x1040, interpretable="")]))
        root = ET.fromstring(legacy_ct_to_xml(parsed))
        self.assertEqual(root.findtext(".//Address"), "00001040")

    def test_pointer_record_without_interpretable_uses_last_address(self):
        parsed = parse_legacy_ct(build_table(
            records=[build_record(
                "Chained", address=0x0, interpretable="",
                pointers=((0x1000, 0x0A, ""), (0x2000, 0x10, "")),
            )]))
        root = ET.fromstring(legacy_ct_to_xml(parsed))
        self.assertEqual(
            root.find("./CheatEntries/CheatEntry").findtext("Address"),
            "00002000")

    def test_code_records_become_cheatcodes(self):
        parsed = parse_legacy_ct(build_table(
            records=[build_record("V")],
            code_records=[build_code_record()]))
        root = ET.fromstring(legacy_ct_to_xml(parsed))
        code = root.find(".//CodeEntry")
        self.assertEqual(code.findtext("Description"), "Code patch")
        self.assertEqual(code.findtext("Address"), "00001100")
        self.assertEqual(code.findtext("ModuleName"), "game.exe")
        self.assertEqual(code.findtext("ModuleNameOffset"), "20")
        self.assertEqual([b.text for b in code.findall("./Before/Byte")], ["90"])
        self.assertEqual([b.text for b in code.findall("./Actual/Byte")],
                         ["E9", "1B"])
        self.assertEqual(code.findall("./After/Byte"), [])

    def test_minimal_table_has_no_groups_or_codes(self):
        parsed = parse_legacy_ct(build_table(
            records=[build_record("Solo", address=0x1234)]))
        root = ET.fromstring(legacy_ct_to_xml(parsed))
        self.assertEqual(len(root.findall("./CheatEntries/CheatEntry")), 1)
        self.assertIsNone(root.find("CheatCodes"))
        self.assertIsNone(root.find(".//GroupHeader"))


class ReadTableIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="ct2-rt3-read-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def write(self, name: str, data: bytes) -> Path:
        path = self.root / name
        path.write_bytes(data)
        return path

    def test_legacy_table_loads_with_binary_identity(self):
        data = build_table(
            version=9,
            records=[build_record("Lives", address=0x1040, vtype=2)])
        path = self.write("legacy.ct", data)
        table = read_table(path)
        self.assertEqual(table.table_version, 9)
        self.assertEqual(table.source_sha256, hashlib.sha256(data).hexdigest())
        self.assertIsNotNone(table.converted_xml)
        ET.fromstring(table.converted_xml)  # valid standard XML document
        self.assertEqual([e.label for e in table.entries], ["Lives"])
        self.assertEqual(table.entries[0].address, "00001040")
        self.assertEqual(table.entries[0].kind, "value")
        self.assertEqual(
            table.warnings[0],
            "Converted from the legacy binary CT format (CE 5.x era, binary "
            "format version 9); record IDs are synthesized sequentially in "
            "document order.")

    def test_xml_source_keeps_converted_xml_none(self):
        path = self.root / "xml.ct"
        path.write_text(
            '<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
            "<CheatEntry><ID>1</ID><Description>Xml</Description>"
            '<VariableType>4 Bytes</VariableType><Address>2000</Address>'
            "</CheatEntry></CheatEntries></CheatTable>",
            encoding="utf-8")
        table = read_table(path)
        self.assertIsNone(table.converted_xml)
        self.assertEqual(table.source_sha256,
                         hashlib.sha256(path.read_bytes()).hexdigest())

    def test_trailer_and_newer_version_warn(self):
        data = build_table(version=12, records=[build_record("A")],
                           trailer=b"\x00\x01\x02")
        table = read_table(self.write("newer.ct", data))
        self.assertEqual(table.table_version, 12)
        self.assertIn(
            "Legacy binary table version 12 is newer than the verified "
            "reference layout (9); the field layout is assumed unchanged.",
            table.warnings)
        self.assertIn(
            "3 trailing byte(s) after the code-record section are ignored "
            "(legacy trailer).",
            table.warnings)

    def test_grouped_records_load_as_heading_and_members(self):
        data = build_table(
            version=9,
            records=[
                build_record("Base", address=0x1040, group=0),
                build_record("Stat", address=0x1044, group=3),
            ])
        table = read_table(self.write("groups.ct", data))
        self.assertEqual([e.label for e in table.entries],
                         ["Base", "Group 3", "Stat"])
        self.assertEqual(table.entries[1].kind, "heading")
        self.assertEqual(table.entries[2].parent_id, table.entries[1].id)


class RefusalTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="ct2-rt3-ref-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def assert_legacy_error(self, data: bytes, expected: str) -> None:
        with self.assertRaises(LegacyCTError) as ctx:
            parse_legacy_ct(data)
        self.assertEqual(str(ctx.exception), expected)

    def test_missing_or_wrong_magic_is_refused_as_corrupt(self):
        for data in (b"", b"CHEAT", b"CHEATENGINX" + d32(9) + d32(0)):
            self.assert_legacy_error(
                data,
                "Legacy binary CT table has a corrupt magic header: "
                "expected the 11-byte CHEATENGINE header.")

    def test_header_truncation_is_named(self):
        self.assert_legacy_error(
            b"CHEATENGINE" + d32(9),  # 15 bytes: magic + version only
            "Legacy binary CT table is truncated: the header needs 19 "
            "bytes but only 15 are present.")

    def test_version_below_six_is_too_old(self):
        self.assert_legacy_error(
            b"CHEATENGINE" + d32(5) + d32(1),
            "Legacy binary CT table version 5 is older than 6; the "
            "pre-converter layout is not supported.")

    def test_implausible_record_count_is_refused(self):
        self.assert_legacy_error(
            b"CHEATENGINE" + d32(9) + d32(20001),
            "Legacy binary CT table holds an implausible record count "
            "20001 (bounded to 20000).")

    def test_implausible_description_length_is_refused(self):
        self.assert_legacy_error(
            b"CHEATENGINE" + d32(9) + d32(1) + d32(4097),
            "Legacy binary CT table holds an implausible record 0 "
            "description length 4097 (bounded to 4096).")

    def test_record_truncation_carries_offset_and_remaining(self):
        data = b"CHEATENGINE" + d32(9) + d32(1) + d32(5) + b"abc"
        self.assert_legacy_error(
            data,
            "Legacy binary CT table is truncated: record 0 description "
            "needs 5 byte(s) at offset 23 but only 3 remain.")

    def test_implausible_pointer_count_is_refused(self):
        data = (b"CHEATENGINE" + d32(9) + d32(1)
                + d32(3) + b"abc"        # description
                + d32(0x1000)            # static address
                + d32(0)                 # interpretable address
                + bytes((2, 0, 4))       # vtype/unicode/length
                + d32(32)                # bit length
                + bytes((0, 0, 0))       # group/show-hex/is-pointer
                + d32(257))              # implausible pointer count
        self.assert_legacy_error(
            data,
            "Legacy binary CT table record 0 holds an implausible pointer "
            "count 257 (bounded to 256).")

    def test_implausible_code_record_count_is_refused(self):
        self.assert_legacy_error(
            b"CHEATENGINE" + d32(9) + d32(0) + d32(4097),
            "Legacy binary CT table holds an implausible code-record "
            "count 4097 (bounded to 4096).")

    def test_code_record_truncation_is_named(self):
        # header (19) + code-record count (4) + code address (4) +
        # module-name length byte; the name payload starts at offset 28.
        data = (b"CHEATENGINE" + d32(9) + d32(0) + d32(1)
                + d32(0x1100)            # code record address
                + bytes((5,)) + b"gam")  # module name length 5, only 3 bytes
        self.assert_legacy_error(
            data,
            "Legacy binary CT table is truncated: code record 0 module "
            "name needs 5 byte(s) at offset 28 but only 3 remain.")

    def test_read_table_refusals_are_named_and_distinct_from_xml(self):
        path = self.root / "bad.ct"
        # legacy magic present but header truncated -> named legacy refusal
        path.write_bytes(b"CHEATENGINE" + d32(9))
        with self.assertRaises(LegacyCTError) as ctx:
            read_table(path)
        self.assertEqual(
            str(ctx.exception),
            "Legacy binary CT table is truncated: the header needs 19 "
            "bytes but only 15 are present.")
        self.assertFalse(str(ctx.exception).startswith("Invalid CT XML"))
        # payloads without the full 11-byte legacy magic keep the XML-path
        # reason (the reference treats anything not starting with the
        # magic as an XML table)
        for payload in (b"CHEAT", b"\x00\x01not xml"):
            path.write_bytes(payload)
            with self.assertRaises(TableError) as ctx:
                read_table(path)
            self.assertTrue(str(ctx.exception).startswith("Invalid CT XML:"))
            self.assertNotIsInstance(ctx.exception, LegacyCTError)


class CompileAndPlanTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="ct2-rt3-cmp-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_plan_identity_stays_binary_not_converted_xml(self):
        data = build_table(
            version=9,
            records=[build_record("Solo", address=0x1234)])
        path = self.root / "legacy.ct"
        path.write_bytes(data)
        table = read_table(path)
        plan = compile_table(str(path), PROCESS)
        # identity is pinned to the original binary bytes, never the
        # converted XML document
        self.assertNotEqual(plan["table_sha256"],
                            hashlib.sha256(table.converted_xml).hexdigest())
        self.assertEqual(plan["table_sha256"],
                         hashlib.sha256(data).hexdigest())
        # repeated compilation is byte-stable
        plan2 = compile_table(str(path), PROCESS)
        self.assertEqual(json.dumps(plan, sort_keys=True, default=str),
                         json.dumps(plan2, sort_keys=True, default=str))

    def test_compile_table_preserves_binary_identity_and_supports(self):
        data = build_table(
            version=9,
            records=[
                build_record("Lives", address=0x1040, interpretable="",
                             vtype=2, show_hex=1),
                build_record("Patch", vtype=255,
                             script="[ENABLE]\n1040:\ndb 07\n[DISABLE]\n1040:\ndb 00"),
            ])
        path = self.root / "legacy.ct"
        path.write_bytes(data)
        plan = compile_table(str(path), PROCESS)
        # plan identity is the original binary hash (matches the reference
        # manifest), not the converted XML
        self.assertEqual(plan["table_sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(plan["counts"]["total"], 2)
        self.assertEqual(plan["counts"]["supported"], 2)
        by_label = {entry["label"]: entry for entry in plan["entries"]}
        self.assertEqual(by_label["Lives"]["kind"], "value")
        self.assertEqual(by_label["Patch"]["kind"], "script")
        validate_plan(plan)

    def test_selection_by_synthetic_id_works(self):
        data = build_table(
            version=9,
            records=[
                build_record("First", address=0x1040, vtype=2),
                build_record("Second", address=0x1044, vtype=2),
            ])
        path = self.root / "legacy.ct"
        path.write_bytes(data)
        plan = compile_table(str(path), PROCESS, selected_ids=[2])
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        self.assertTrue(by_id[2]["selected"])
        self.assertFalse(by_id[1]["selected"])
        validate_plan(plan)


LEGACY_SCRIPT = "[ENABLE]\n1040:\ndd 01\n[DISABLE]\n1040:\ndd 00"


class EngineBehaviourTests(unittest.TestCase):
    """The converted legacy table drives real engine writes on fixture memory."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="ct2-rt3-eng-")
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.memory = Memory()
        data = build_table(
            version=9,
            records=[
                build_record("Lives", address=0x1040, interpretable="",
                             vtype=2, show_hex=1),
                build_record("Patch", vtype=255, script=LEGACY_SCRIPT),
            ])
        path = root / "legacy.ct"
        path.write_bytes(data)
        self.plan = compile_table(str(path), PROCESS)
        self.engine = TrainerEngine(self.plan, state_dir=root / "state",
                                    process_lock_dir=root / "shared",
                                    memory_factory=lambda name: self.memory,
                                    hook_coordinator=Coordinator())
        self.engine.poll()

    def tearDown(self):
        if self.engine is not None and not self.engine.closed:
            self.engine.close()

    def test_value_write_and_script_activation_hit_fixture_memory(self):
        self.assertTrue(self.engine.connected, self.engine.status)
        # AA record 2: [ENABLE] writes d32 01 at 0x1040, [DISABLE] reverts
        # it.  (Both 4-byte forms decode to complete x64 instructions in
        # the fixture's zero stream; a 1-byte cut would be refused
        # fail-closed.)  toggle returns the direction, so a disable
        # returns False while the restore is proven by the bytes.
        self.assertTrue(self.engine.toggle(2, True))
        self.assertEqual(self.memory.read(0x1040, 4), b"\x01\x00\x00\x00")
        self.assertFalse(self.engine.toggle(2, False))
        self.assertEqual(self.memory.read(0x1040, 4), bytes(4))
        self.assertEqual(self.engine.entry_errors, {})
        # value record 1: 4 Bytes, shown as hex, address 00001040.
        self.assertEqual(self.engine.set_value(1, "7"), "7")
        self.assertEqual(self.memory.read(0x1040, 4), b"\x07\x00\x00\x00")
        self.assertEqual(self.engine.set_value(1, "0"), "0")
        self.assertEqual(self.memory.read(0x1040, 4), bytes(4))


class RealReferenceTableTests(unittest.TestCase):
    """Optional: the local-only version-9 reference table, when present."""

    def test_supermeatboy_loads_with_reference_identity(self):
        if not REAL_REFERENCE.is_file():
            self.skipTest("local-only reference table absent")
        table = read_table(REAL_REFERENCE)
        self.assertEqual(table.source_sha256, REAL_REFERENCE_SHA256)
        self.assertEqual(table.table_version, 9)
        self.assertEqual([e.label for e in table.entries], list(REAL_REFERENCE_LABELS))
        self.assertEqual(
            [e.kind for e in table.entries], ["script"] * len(REAL_REFERENCE_LABELS))
        self.assertIn(
            "897 trailing byte(s) after the code-record section are ignored "
            "(legacy trailer).",
            table.warnings)
        plan = compile_table(str(REAL_REFERENCE), "game.exe")
        self.assertEqual(plan["table_sha256"], REAL_REFERENCE_SHA256)
        self.assertEqual(plan["counts"]["total"], 10)
        self.assertEqual(plan["counts"]["supported"], 10)
        validate_plan(plan)


if __name__ == "__main__":
    unittest.main()
