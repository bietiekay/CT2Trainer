"""Lane B: nested relative-address staging through the runtime-base
placeholder (positive proof).

Dedicated lane-contract test file proving the Octopath2
relative-address staging extension end-to-end on own synthetic
fixtures: the staging walk folds offset-carrying intermediate
levels, index-times-stride own literals and the record's own pointer
offsets through the deterministic synthetic symbol
``__ct2_rtbase_<anchor_id>`` (plan metadata, never a dependency), and
the engine injects the anchor heading's live base per activation
call - byte-exact once the table scripts have written the base,
inert and named fail-closed while it is missing, and a registered
symbol under the placeholder name is a named collision.

Covered classes:
- flat byte-stability: a chain where every level is a plain-hex
  relative literal with no pointer offsets anywhere keeps the exact
  folded signed-hex total (``+30``), never the placeholder form.
- nested pointer-offset levels: intermediate headings carrying
  ``<Offsets>`` wrap the folded expression (the 70-row Octopath2
  shape); the intermediate headings themselves stay supported
  navigation headings and are not staged.
- index-times-stride own literal (``+00*04``): the 60-row Octopath2
  shape, staged verbatim on the expression profile.
- deep chains with multiple offset slots per level, resolved
  byte-exactly level for level through a seeded pointer chain.
- expression offset slots (``Base+10``): the slot symbol rides the
  ordinary dependency machinery (``requires``), the placeholder
  does not.
- UDS collision: a user-defined symbol spelled like the placeholder
  is a named runtime refusal that outranks the missing-base
  refusal; no memory access, no write.
- forged markers: a tampered plan (wrong anchor, placeholder dropped
  from the address) is refused at both plan validators with the
  named messages.
- determinism: two compiles of the same table produce byte-identical
  entries and byte-stable nested addresses.
"""
from __future__ import annotations

import json
import struct
import tempfile
from pathlib import Path
import unittest

from test_native_engine_code import Coordinator
from test_native_lua_activation import Memory

from ct2trainer.native.compiler import (NativeCompileError, compile_table,
                                        validate_plan)
from ct2trainer.native.engine import (NativeRuntimeError, TrainerEngine,
                                      validate_plan as validate_engine_plan)

PROCESS = "FixtureTarget.exe"

BASE_FINDER_SCRIPT = (
    '<CheatEntry><ID>{id}</ID><Description>"Base finder"'
    '</Description><VariableType>Auto Assembler Script'
    '</VariableType><AssemblerScript>[ENABLE]'
    '\nassert(1010,00 00 00 00)'
    '\n1010:'
    '\ndd 1'
    '\n[DISABLE]'
    '\n1010:'
    '\ndd 0'
    '</AssemblerScript></CheatEntry>')


def heading(record_id: int, label: str, address: str = "",
            offsets=(), child_entries: str = "") -> str:
    offset_xml = "".join(f"<Offset>{slot}</Offset>" for slot in offsets)
    offsets_xml = f"<Offsets>{offset_xml}</Offsets>" if offset_xml else ""
    return (
        f'<CheatEntry><ID>{record_id}</ID><Description>"{label}"'
        f'</Description><GroupHeader>1</GroupHeader>'
        f'<VariableType>Byte</VariableType>'
        + (f"<Address>{address}</Address>" if address else "")
        + offsets_xml
        + (f"<CheatEntries>{child_entries}</CheatEntries>"
           if child_entries else "")
        + "</CheatEntry>")


def value(record_id: int, label: str, address: str,
          variable_type: str = "4 Bytes") -> str:
    return (
        f'<CheatEntry><ID>{record_id}</ID><Description>"{label}"'
        f'</Description><VariableType>{variable_type}</VariableType>'
        f'<Address>{address}</Address></CheatEntry>')


FLAT_BODY = (
    heading(1, "Group base", child_entries=(
        heading(2, "Mid", "+10", child_entries=(
            value(3, "Kid", "+20"))))
    + BASE_FINDER_SCRIPT.format(id=4)))

NESTED2_BODY = (
    heading(1, "Group base", child_entries=(
        heading(2, "Pointer mid", "+80", offsets=("0",),
                child_entries=(
                    value(3, "Nested value", "+10"))))
    + BASE_FINDER_SCRIPT.format(id=4)))

STRIDE_BODY = (
    heading(1, "Group base", child_entries=(
        heading(2, "Pointer mid", "+40", offsets=("0",),
                child_entries=(
                    heading(3, "Index mid", "+10", offsets=("0",),
                            child_entries=(
                                value(4, "Stride value", "+00*04"))))))
    + BASE_FINDER_SCRIPT.format(id=5)))

DEEP_BODY = (
    heading(1, "Group base", child_entries=(
        heading(2, "L2", "+20", offsets=("0",),
                child_entries=(
                    heading(3, "L3", "+18",
                            offsets=("0", "+08", "+10", "+00"),
                            child_entries=(
                                heading(4, "L4", "+13", offsets=("0",),
                                        child_entries=(
                                            value(5, "Deep", "+10"))))))))
    + BASE_FINDER_SCRIPT.format(id=6)))

SLOT_BODY = (
    heading(1, "Group base", child_entries=(
        heading(2, "Pointer mid", "+40", offsets=("Base+10",),
                child_entries=(
                    value(3, "Slot value", "+10"))))
    + BASE_FINDER_SCRIPT.format(id=4)))

SLOT_UDS_BODY = (
    "<UserdefinedSymbols>"
    '<SymbolEntry><Name>Base</Name><Address>8</Address>'
    "</SymbolEntry></UserdefinedSymbols>")

COLLISION_UDS_BODY = (
    "<UserdefinedSymbols>"
    '<SymbolEntry><Name>__CT2_RTBASE_1</Name>'
    "<Address>2000</Address></SymbolEntry>"
    "</UserdefinedSymbols>")


class StagedPointerChainPlanTests(unittest.TestCase):
    """Compiler side: fold shape, requires derivation, marker contract."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def _compile(self, table_body, uds_body=""):
        table = self.root / "stage.ct"
        table.write_text(
            '<CheatTable CheatEngineTableVersion="45">'
            + uds_body + '<CheatEntries>'
            + table_body + '</CheatEntries></CheatTable>',
            encoding="utf-8")
        plan = compile_table(table, PROCESS)
        validate_plan(plan)
        validate_engine_plan(plan)
        return plan

    def test_flat_chain_keeps_the_byte_stable_total(self):
        plan = self._compile(FLAT_BODY)
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        self.assertTrue(by_id[3]["supported"], by_id[3]["reason"])
        self.assertEqual(by_id[3]["address"], "+30")
        self.assertEqual(by_id[3]["address_profile"], "expression/v1")
        self.assertEqual(by_id[3]["requires"], [])
        self.assertNotIn("__ct2_rtbase", by_id[3]["address"])
        self.assertTrue(by_id[3]["runtime_base_required"])
        self.assertEqual(by_id[3]["runtime_base_anchor"], 1)
        self.assertTrue(by_id[1]["runtime_base_target"])
        # The intermediate heading is not staged: it keeps its own
        # relative address as a supported navigation heading.
        self.assertEqual(by_id[2]["kind"], "heading")
        self.assertEqual(by_id[2]["address"], "+10")
        self.assertNotIn("address_profile", by_id[2])
        self.assertNotIn("runtime_base_required", by_id[2])

    def test_nested_pointer_offset_levels_fold_through_the_placeholder(self):
        plan = self._compile(NESTED2_BODY)
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        self.assertTrue(by_id[3]["supported"], by_id[3]["reason"])
        self.assertEqual(by_id[3]["address"],
                         "([(__ct2_rtbase_1)+80])+10")
        self.assertEqual(by_id[3]["address_profile"], "expression/v1")
        self.assertEqual(by_id[3]["requires"], [])
        self.assertTrue(by_id[3]["runtime_base_required"])
        self.assertEqual(by_id[3]["runtime_base_anchor"], 1)
        self.assertEqual(by_id[3]["pointer_offsets"], [])
        self.assertTrue(by_id[1]["runtime_base_target"])
        # The offset-carrying intermediate stays a supported navigation
        # heading with its original relative address, never staged.
        self.assertEqual(by_id[2]["kind"], "heading")
        self.assertEqual(by_id[2]["address"], "+80")
        self.assertNotIn("address_profile", by_id[2])
        self.assertNotIn("runtime_base_required", by_id[2])

    def test_index_times_stride_own_literal_stages_nested(self):
        plan = self._compile(STRIDE_BODY)
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        self.assertTrue(by_id[4]["supported"], by_id[4]["reason"])
        self.assertEqual(by_id[4]["address"],
                         "([([(__ct2_rtbase_1)+40])+10])+00*04")
        self.assertEqual(by_id[4]["requires"], [])
        self.assertTrue(by_id[4]["runtime_base_required"])
        self.assertEqual(by_id[4]["runtime_base_anchor"], 1)

    def test_deep_chain_with_offset_slots_folds_level_for_level(self):
        plan = self._compile(DEEP_BODY)
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        self.assertTrue(by_id[5]["supported"], by_id[5]["reason"])
        self.assertEqual(
            by_id[5]["address"],
            "([([[[[([(__ct2_rtbase_1)+20])+18]]+10]+8])+13])+10")
        self.assertEqual(by_id[5]["requires"], [])
        self.assertTrue(by_id[5]["runtime_base_required"])
        self.assertEqual(by_id[5]["runtime_base_anchor"], 1)
        self.assertTrue(by_id[1]["runtime_base_target"])

    def test_expression_offset_slot_rides_the_dependency_machinery(self):
        plan = self._compile(SLOT_BODY, uds_body=SLOT_UDS_BODY)
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        self.assertEqual(plan["user_defined_symbols"], {"base": 0x8})
        self.assertTrue(by_id[3]["supported"], by_id[3]["reason"])
        self.assertEqual(by_id[3]["address"],
                         "([(__ct2_rtbase_1)+40]+(Base+10))+10")
        self.assertEqual(by_id[3]["requires"], ["Base"])
        self.assertTrue(by_id[3]["runtime_base_required"])
        self.assertEqual(by_id[3]["runtime_base_anchor"], 1)


class StagedPointerChainEngineTests(unittest.TestCase):
    """Engine side: inert refusal, live byte-exact resolution,
    collision, and the placeholder staying out of the symbol table."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.memory = Memory()
        self.coordinator = Coordinator()

    def _engine(self, table_body, uds_body=""):
        table = self.root / "stage.ct"
        table.write_text(
            '<CheatTable CheatEngineTableVersion="45">'
            + uds_body + '<CheatEntries>'
            + table_body + '</CheatEntries></CheatTable>',
            encoding="utf-8")
        plan = compile_table(table, PROCESS)
        validate_plan(plan)
        validate_engine_plan(plan)
        engine = TrainerEngine(
            plan, state_dir=self.root / "state",
            process_lock_dir=self.root / "shared",
            memory_factory=lambda name: self.memory,
            hook_coordinator=self.coordinator)
        engine.poll()
        self.assertTrue(engine.connected, engine.status)
        return engine

    def test_nested_chain_resolves_byte_exact_once_the_base_is_live(self):
        engine = self._engine(NESTED2_BODY)
        # Anchor base 0x1010; the pointer at 0x1010+0x80 reads 0x10A0,
        # the value sits at 0x10A0+0x10 = 0x10B0.
        self.memory.data[0x90:0x98] = struct.pack("<Q", 0x10A0)
        # Inert until the table scripts write the group base.
        with self.assertRaisesRegex(
                NativeRuntimeError,
                r"Runtime base for group record 1 \('Group base'\) is not "
                r"provided yet"):
            engine.read_value(3)
        self.assertFalse(self.memory.writes)
        engine.set_dynamic_address(1, 0x1010, scope=4)
        self.assertEqual(engine.dynamic_addresses[1], 0x1010)
        self.assertEqual(engine.read_value(3), "0")
        self.assertEqual(engine.set_value(3, "1234"), "1234")
        self.assertEqual(self.memory.read(0x10B0, 4),
                         struct.pack("<I", 1234))
        self.assertEqual(engine.read_value(3), "1234")
        # The injected placeholder never lands in the symbol table.
        self.assertNotIn("__ct2_rtbase_1", engine.symbols)
        engine.set_dynamic_address(1, None, scope=4)
        with self.assertRaisesRegex(
                NativeRuntimeError, "is not provided yet"):
            engine.read_value(3)

    def test_stride_chain_resolves_byte_exact(self):
        engine = self._engine(STRIDE_BODY)
        # Anchor base 0x1008: *(0x1008+0x40) = 0x1050,
        # *(0x1050+0x10) = 0x1068, then +00*04 keeps 0x1068.
        self.memory.data[0x48:0x50] = struct.pack("<Q", 0x1050)
        self.memory.data[0x60:0x68] = struct.pack("<Q", 0x1068)
        engine.set_dynamic_address(1, 0x1008, scope=5)
        self.assertEqual(engine.set_value(4, "7"), "7")
        self.assertEqual(self.memory.read(0x1068, 4),
                         struct.pack("<I", 7))
        self.assertEqual(engine.read_value(4), "7")

    def test_deep_chain_resolves_byte_exact_level_for_level(self):
        engine = self._engine(DEEP_BODY)
        # Anchor base 0x1000; the seeded pointer chain follows the
        # real bracket topology:
        #   *(0x1000+0x20) = 0x1030
        #   *(0x1030+0x18) = 0x1008
        #   *(0x1008+0x00) = 0x1018
        #   *(0x1018+0x10) = 0x1038
        #   *(0x1038+0x08) = 0x1000
        #   *(0x1000+0x13) = 0x1023
        #   final = 0x1023+0x10 = 0x1033
        self.memory.data[0x20:0x28] = struct.pack("<Q", 0x1030)
        self.memory.data[0x48:0x50] = struct.pack("<Q", 0x1008)
        self.memory.data[0x08:0x10] = struct.pack("<Q", 0x1018)
        self.memory.data[0x28:0x30] = struct.pack("<Q", 0x1038)
        self.memory.data[0x40:0x48] = struct.pack("<Q", 0x1000)
        self.memory.data[0x13:0x1B] = struct.pack("<Q", 0x1023)
        engine.set_dynamic_address(1, 0x1000, scope=6)
        self.assertEqual(engine.read_value(5), "0")
        # 43981 is 0xABCD in decimal; the row renders decimal.
        self.assertEqual(engine.set_value(5, "43981"), "43981")
        self.assertEqual(self.memory.read(0x1033, 4),
                         struct.pack("<I", 0xABCD))
        self.assertEqual(engine.read_value(5), "43981")

    def test_expression_offset_slot_resolves_through_the_live_symbol(self):
        engine = self._engine(SLOT_BODY, uds_body=SLOT_UDS_BODY)
        # Anchor base 0x1008: *(0x1008+0x40) = 0x1050, + (Base+10) =
        # +0x18 -> 0x1068, +0x10 -> 0x1078.
        self.memory.data[0x48:0x50] = struct.pack("<Q", 0x1050)
        self.assertEqual(engine.symbols.get("base"), 0x8)
        engine.set_dynamic_address(1, 0x1008, scope=4)
        self.assertEqual(engine.set_value(3, "9"), "9")
        self.assertEqual(self.memory.read(0x1078, 4),
                         struct.pack("<I", 9))

    def test_placeholder_name_collision_is_a_named_refusal(self):
        engine = self._engine(NESTED2_BODY, uds_body=COLLISION_UDS_BODY)
        # The collision is named even before the base is provided:
        # the engine refuses the placeholder-name collision instead
        # of the missing-base condition - and touches no memory.
        self.assertEqual(engine.symbols.get("__ct2_rtbase_1"), 0x2000)
        with self.assertRaisesRegex(
                NativeRuntimeError,
                "Staged runtime-base placeholder collides with a "
                "registered symbol"):
            engine.read_value(3)
        self.assertFalse(self.memory.writes)


class StagedPointerChainPlanForgeryTests(unittest.TestCase):
    """Tampered nested plans are refused at both plan validators."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def _plan(self):
        table = self.root / "stage.ct"
        table.write_text(
            '<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
            + NESTED2_BODY
            + '</CheatEntries></CheatTable>',
            encoding="utf-8")
        plan = compile_table(table, PROCESS)
        validate_plan(plan)
        validate_engine_plan(plan)
        return plan

    def test_tampered_anchor_is_refused_at_both_validators(self):
        plan = self._plan()
        for entry in plan["entries"]:
            if entry["id"] == 3:
                entry["runtime_base_anchor"] = 4
        with self.assertRaisesRegex(
                NativeCompileError,
                "Value symbol dependencies do not match"):
            validate_plan(plan)
        with self.assertRaisesRegex(
                NativeRuntimeError,
                "Value symbol dependencies do not match"):
            validate_engine_plan(plan)

    def test_placeholder_dropped_from_the_address_is_refused(self):
        plan = self._plan()
        for entry in plan["entries"]:
            if entry["id"] == 3:
                entry["address"] = "([1040]+80)+10"
        with self.assertRaisesRegex(
                NativeCompileError,
                "Staged relative chain must resolve through its "
                "runtime-base placeholder"):
            validate_plan(plan)
        with self.assertRaisesRegex(
                NativeRuntimeError,
                "Staged relative chain must resolve through its "
                "runtime-base placeholder"):
            validate_engine_plan(plan)


class StagedPointerChainDeterminismTests(unittest.TestCase):
    """The nested fold is a deterministic plan-level decision."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_two_compiles_are_byte_identical(self):
        table = self.root / "stage.ct"
        table.write_text(
            '<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
            + DEEP_BODY + '</CheatEntries></CheatTable>',
            encoding="utf-8")
        first = compile_table(table, PROCESS)
        second = compile_table(table, PROCESS)
        self.assertEqual(json.dumps(first["entries"], sort_keys=True),
                         json.dumps(second["entries"], sort_keys=True))
        self.assertEqual(first["table_sha256"],
                         second["table_sha256"])
        by_id = {entry["id"]: entry for entry in first["entries"]}
        self.assertEqual(
            by_id[5]["address"],
            "([([[[[([(__ct2_rtbase_1)+20])+18]]+10]+8])+13])+10")


if __name__ == "__main__":
    unittest.main()
