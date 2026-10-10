"""Recursive parent value (moRecursiveSetValue) end-to-end wiring.

Corpus semantics (pinned re2.CT, read-only): a value record carrying
``<Options moRecursiveSetValue="1"/>`` propagates one value write to every
value descendant, deepest records first (ties by ascending record id, the
target itself last). The compiler emits the deterministic write closure as
entry-level ``recursive_value.write_ids`` plan metadata; both plan
validators re-derive the closure and refuse forged, reordered, unknown,
self-referential or wrong-kind metadata fail-closed. The engine replays the
tested RecursiveSetValueModel byte-exact write plan through the ordinary
value runtime (ownership checks, one all-or-nothing transaction, frozen
state updates).

Fixtures are own synthetic CT bodies in a temp directory; the shapes mirror
the pinned corpus (Float parent with nested value children, a 4-Bytes parent
with a Byte child, childless flagged leaves, a non-flagged sibling, a group
heading).  No TableReferences, no game inputs, no CE data.
"""
import struct
import tempfile
import unittest
from pathlib import Path

from test_native_engine_code import Coordinator
from test_native_lua_activation import Memory
from ct2trainer.native.compiler import compile_table, validate_plan
from ct2trainer.native.compiler import NativeCompileError
from ct2trainer.native.engine import TrainerEngine, NativeRuntimeError

CT_BODY = '''<CheatTable CheatEngineTableVersion="45"><CheatEntries>
<CheatEntry>
<ID>3000</ID>
<Description>"Health Parent"</Description>
<Options moRecursiveSetValue="1"/>
<VariableType>Float</VariableType>
<Address>1020</Address>
<CheatEntries>
<CheatEntry>
<ID>3001</ID>
<Description>"Primary"</Description>
<VariableType>Float</VariableType>
<Address>+8</Address>
<CheatEntries>
<CheatEntry>
<ID>3002</ID>
<Description>"Nested"</Description>
<VariableType>Float</VariableType>
<Address>+4</Address>
</CheatEntry>
</CheatEntries>
</CheatEntry>
<CheatEntry>
<ID>3003</ID>
<Description>"Tertiary"</Description>
<VariableType>Float</VariableType>
<Address>+16</Address>
</CheatEntry>
</CheatEntries>
</CheatEntry>
<CheatEntry>
<ID>3020</ID>
<Description>"Mixed Parent"</Description>
<Options moRecursiveSetValue="1"/>
<VariableType>4 Bytes</VariableType>
<Address>1050</Address>
<CheatEntries>
<CheatEntry>
<ID>3021</ID>
<Description>"Byte Kid"</Description>
<VariableType>Byte</VariableType>
<Address>+4</Address>
</CheatEntry>
</CheatEntries>
</CheatEntry>
<CheatEntry><ID>3010</ID><Description>"Leaf Flagged"</Description><Options moRecursiveSetValue="1"/><VariableType>2 Bytes</VariableType><Address>1040</Address></CheatEntry>
<CheatEntry><ID>3011</ID><Description>"Plain Sibling"</Description><VariableType>4 Bytes</VariableType><Address>1060</Address></CheatEntry>
<CheatEntry><ID>3050</ID><Description>"Heading"</Description><GroupHeader>1</GroupHeader><Address>1070</Address></CheatEntry>
</CheatEntries></CheatTable>'''


def float_bytes(value):
    return struct.pack("<f", value)


class RecursiveParentValueTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.table = self.root / "recursive.ct"
        self.table.write_text(CT_BODY, encoding="utf-8")
        self.memory = Memory()
        self.coordinator = Coordinator()
        self.engine = TrainerEngine(compile_table(self.table, "FixtureTarget.exe"),
                                    state_dir=self.root / "state",
                                    process_lock_dir=self.root / "shared",
                                    memory_factory=lambda name: self.memory,
                                    hook_coordinator=self.coordinator)
        self.engine.poll()

    def tearDown(self):
        self.engine.close()

    def fresh_engine(self, plan, suffix):
        return TrainerEngine(plan, state_dir=self.root / ("state" + suffix),
                             process_lock_dir=self.root / ("shared" + suffix),
                             memory_factory=lambda name: self.memory,
                             hook_coordinator=self.coordinator)

    # -- plan metadata ------------------------------------------------------

    def test_plan_carries_deterministic_write_closures(self):
        by_id = {entry["id"]: entry for entry in self.engine.plan["entries"]}
        self.assertEqual(by_id[3000]["recursive_value"],
                         {"write_ids": [3002, 3001, 3003, 3000]})
        self.assertEqual(by_id[3020]["recursive_value"],
                         {"write_ids": [3021, 3020]})
        self.assertEqual(by_id[3010]["recursive_value"], {"write_ids": [3010]})
        for identifier in (3001, 3002, 3003, 3021, 3011, 3050):
            self.assertNotIn("recursive_value", by_id[identifier],
                             f"record {identifier} must not carry metadata")

    # -- runtime effect -----------------------------------------------------

    def test_recursive_set_writes_closure_deepest_first_byte_exact(self):
        payload = float_bytes(1.5)
        self.assertEqual(self.engine.set_value(3000, "1.5"), "1.5")
        self.assertEqual(self.memory.read(0x102C, 4), payload)  # 3002
        self.assertEqual(self.memory.read(0x1028, 4), payload)  # 3001
        self.assertEqual(self.memory.read(0x1036, 4), payload)  # 3003 (0x1020+0x16)
        self.assertEqual(self.memory.read(0x1020, 4), payload)  # 3000
        self.assertEqual(self.memory.writes,
                         [(0x102C, payload), (0x1028, payload),
                          (0x1036, payload), (0x1020, payload)])
        self.assertEqual(self.engine.read_value(3000), "1.5")
        self.assertEqual(self.engine.read_value(3002), "1.5")

    def test_mixed_type_closure_writes_valid_range_deepest_first(self):
        self.assertEqual(self.engine.set_value(3020, "7"), "7")
        self.assertEqual(self.memory.read(0x1054, 1), b"\x07")
        self.assertEqual(self.memory.read(0x1050, 4), b"\x07\x00\x00\x00")
        self.assertEqual(self.memory.writes,
                         [(0x1054, b"\x07"), (0x1050, b"\x07\x00\x00\x00")])
        self.assertEqual(self.engine.read_value(3021), "7")

    def test_leaf_flagged_record_writes_only_itself(self):
        self.assertEqual(self.engine.set_value(3010, "42"), "42")
        self.assertEqual(self.memory.read(0x1040, 2), b"\x2a\x00")
        self.assertEqual(self.memory.writes, [(0x1040, b"\x2a\x00")])

    # -- refusals (no writes) -------------------------------------------------

    def test_mixed_closure_rejects_value_outside_child_range_without_writes(self):
        with self.assertRaisesRegex(NativeRuntimeError,
                                    "3021.*exceeds Byte range"):
            self.engine.set_value(3020, "300")
        self.assertFalse(self.memory.writes)
        self.assertEqual(self.memory.read(0x1050, 4), b"\x00\x00\x00\x00")
        self.assertEqual(self.memory.read(0x1054, 1), b"\x00")
        self.assertIn(3020, self.engine.entry_errors)

    def test_non_recursive_sibling_stays_a_plain_write(self):
        self.assertEqual(self.engine.set_value(3011, "9"), "9")
        self.assertEqual(self.memory.read(0x1060, 4), b"\x09\x00\x00\x00")
        self.assertEqual(self.memory.writes, [(0x1060, b"\x09\x00\x00\x00")])

    # -- freeze interaction ---------------------------------------------------

    def test_freeze_keeps_recursive_children_on_later_value_writes(self):
        self.engine.set_value(3000, "1.0")
        self.engine.set_freeze(3001, True)
        self.engine.set_freeze(3000, True)
        self.engine.set_value(3000, "3.0")
        payload = float_bytes(3.0)
        self.memory.data[0x28] = 0xFF  # drift 3001 at 0x1028
        self.memory.data[0x20] = 0xFF  # drift 3000 at 0x1020
        self.engine.poll()
        self.assertFalse(self.engine.blocked, self.engine.error)
        self.assertEqual(self.memory.read(0x1028, 4), payload)
        self.assertEqual(self.memory.read(0x1020, 4), payload)
        # Unfrozen closure members keep the latest recursive write.
        self.assertEqual(self.memory.read(0x102C, 4), payload)
        self.assertEqual(self.memory.read(0x1036, 4), payload)

    # -- forged metadata: engine validator -------------------------------------

    def _reject(self, plan, suffix):
        with self.assertRaises(NativeRuntimeError):
            self.fresh_engine(plan, suffix)

    def test_forged_closure_missing_descendant_rejected(self):
        plan = compile_table(self.table, "FixtureTarget.exe")
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        by_id[3000]["recursive_value"]["write_ids"] = [3001, 3003, 3000]
        self._reject(plan, "-forged1")

    def test_forged_closure_wrong_order_rejected(self):
        plan = compile_table(self.table, "FixtureTarget.exe")
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        by_id[3000]["recursive_value"]["write_ids"] = [3000, 3002, 3001, 3003]
        self._reject(plan, "-forged2")

    def test_forged_closure_unknown_record_rejected(self):
        plan = compile_table(self.table, "FixtureTarget.exe")
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        by_id[3000]["recursive_value"]["write_ids"] = [3002, 3001, 3003, 9999]
        self._reject(plan, "-forged3")

    def test_forged_closure_missing_target_rejected(self):
        plan = compile_table(self.table, "FixtureTarget.exe")
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        by_id[3000]["recursive_value"]["write_ids"] = [3002, 3001, 3003]
        self._reject(plan, "-forged4")

    def test_forged_metadata_on_plain_entry_rejected(self):
        plan = compile_table(self.table, "FixtureTarget.exe")
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        del by_id[3000]["recursive_value"]
        by_id[3011]["recursive_value"] = {"write_ids": [3002, 3001, 3003, 3000]}
        self._reject(plan, "-forged5")

    def test_forged_metadata_on_heading_rejected(self):
        plan = compile_table(self.table, "FixtureTarget.exe")
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        by_id[3050]["recursive_value"] = {"write_ids": [3050]}
        self._reject(plan, "-forged6")

    def test_unselected_flagged_record_carries_no_metadata(self):
        plan = compile_table(self.table, "FixtureTarget.exe", selected_ids=[3000])
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        flagged = [entry["id"] for entry in plan["entries"]
                   if entry.get("recursive_value")]
        self.assertEqual(flagged, [3000])
        self.assertFalse(by_id[3010]["selected"])
        self.assertNotIn("recursive_value", by_id[3010])

    # -- forged metadata: compiler validator ------------------------------------

    def test_compiler_validator_rejects_forged_metadata(self):
        plan = compile_table(self.table, "FixtureTarget.exe")
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        by_id[3000]["recursive_value"]["write_ids"] = [3002, 3001, 3003]
        with self.assertRaises(NativeCompileError):
            validate_plan(plan)
        plan = compile_table(self.table, "FixtureTarget.exe")
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        by_id[3020]["recursive_value"]["write_ids"] = [9999]
        with self.assertRaises(NativeCompileError):
            validate_plan(plan)
        plan = compile_table(self.table, "FixtureTarget.exe")
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        by_id[3050]["recursive_value"] = {"write_ids": [3050]}
        with self.assertRaises(NativeCompileError):
            validate_plan(plan)
