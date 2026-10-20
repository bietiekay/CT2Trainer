"""Dynamic script-parent address providers (WP-50, GC-E8).

Synthetic clean-room fixture, no original table content: a sibling
addressless script (76) computes a live base from target memory and
publishes it into the addressless heading "DynTarget30" (77) through its
own record-Lua scope, using the constant-array AddressList idiom
(``local mr = {AddressList['DynTarget30']} ... mr[1].address = ...``).
The heading's relative children (78/79) were blocked with the exact
"Relative address has no address-bearing ancestor." refusal before
WP-50 and are now adopted as expression-profile values whose base is
re-resolved fresh from the engine's live-base registry on every access.
Both plan gates re-derive the bounded static extraction from the
provider's embedded Lua source and refuse forged marker metadata with
named reasons; at runtime the record-Lua surface exposes the ID /
Description / Address read accessors (both spellings) plus the
contract-checked ``address`` setter, and the live base is cleared by a
``nil`` write, provider deactivation, target exit and trainer close.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import re
import struct
import tempfile
import unittest

from test_native_engine_code import Coordinator
from test_native_lua_activation import Memory as FixtureMemory
from ct2trainer.native.compiler import (NativeCompileError, compile_table,
                                         validate_plan as validate_source_plan)
from ct2trainer.native.engine import (NativeRuntimeError, TrainerEngine,
                                      validate_plan as validate_engine_plan)
from ct2trainer.native.lua_host import LuaHostError
from ct2trainer.native.lua_program import (MAX_DYNAMIC_ADDRESS_TARGETS,
                                           lua_dynamic_address_targets,
                                           prepare_lua_program)

ADOPTED_REASON = ("Native relative value; the inherited base is resolved "
                  "at runtime from the dynamic address provider.")
INACTIVE = "Address provider 76 is not active."
INACTIVE_RE = re.escape(INACTIVE)
NOT_WRITTEN = "Dynamic address provider does not write the target record's address."
CONTRACT = "Dynamic address write outside the planned provider contract."
RANGE = "Dynamic address must be an integer in address range."

PROVIDER_SOURCE = (
    "{$lua}\n"
    "local mr = {AddressList['DynTarget30']}\n"
    "[ENABLE]\n"
    "mr[1].address = readQword('fixturetarget.exe+8')\n"
    "[DISABLE]\n"
    "mr[1].address = nil\n")


def write_table(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    table = root / "script_parent.ct"
    table.write_text(
        '<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
        '<CheatEntry><ID>76</ID><Description>"dynamic base script (record Lua address write)"'
        '</Description><VariableType>Auto Assembler Script</VariableType>'
        '<Address/><AssemblerScript>{provider}</AssemblerScript></CheatEntry>'
        '<CheatEntry><ID>77</ID><Description>"DynTarget30"</Description>'
        '<Options moHideChildren="1"/><GroupHeader>1</GroupHeader><Address/>'
        '<CheatEntries>'
        '<CheatEntry><ID>78</ID><Description>"dyn child m_nCharacterID"</Description>'
        '<VariableType>4 Bytes</VariableType><Address>+220</Address></CheatEntry>'
        '<CheatEntry><ID>79</ID><Description>"dyn child m_cMasterParameter.HP"</Description>'
        '<VariableType>4 Bytes</VariableType><Address>+240</Address></CheatEntry>'
        '</CheatEntries>'
        '</CheatEntry>'
        '</CheatEntries></CheatTable>'.replace("{provider}", PROVIDER_SOURCE),
        encoding="utf-8")
    return table


class Memory(FixtureMemory):
    """FixtureMemory with room for the runtime base and its children."""

    def __init__(self, pid=123, creation_time=456):
        super().__init__(pid, creation_time)
        self.data = bytearray(4096)
        self.data[8:16] = struct.pack("<Q", 0x1040)


class DynamicScriptParentPlanTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.table = write_table(self.root)
        self.plan = compile_table(self.table, "FixtureTarget.exe")
        self.by_id = {entry["id"]: entry for entry in self.plan["entries"]}

    def test_target_carries_the_symbol_null_marker(self):
        target = self.by_id[77]
        self.assertEqual(target["kind"], "heading")
        self.assertTrue(target["supported"], target["reason"])
        self.assertEqual(target["address"], "")
        self.assertEqual(target["pointer_offsets"], [])
        self.assertEqual(target["address_provider"],
                         {"provider_id": 76, "symbol": None})
        provider = self.by_id[76]
        self.assertEqual(provider["kind"], "script")
        self.assertTrue(provider["supported"], provider["reason"])
        self.assertEqual(provider["address"], "")
        self.assertEqual(provider["pointer_offsets"], [])
        self.assertEqual(provider["provides"], [])
        self.assertEqual(provider["requires"], [])
        self.assertEqual(provider["dependency_ids"], [])
        self.assertIn("lua_program", provider)
        self.assertNotIn("address_provider", provider)
        for record_id, address in ((78, "+220"), (79, "+240")):
            child = self.by_id[record_id]
            self.assertEqual(child["kind"], "value", child["reason"])
            self.assertTrue(child["supported"], child["reason"])
            self.assertEqual(child["address"], address)
            self.assertEqual(child["source_address"], address)
            self.assertEqual(child["address_profile"], "expression/v1")
            self.assertEqual(child["pointer_offsets"], [])
            self.assertEqual(child["requires"], [])
            self.assertEqual(child["dependency_ids"], [])
            self.assertNotIn("staged", child)
            self.assertNotIn("address_provider", child)
            self.assertEqual(child["reason"], ADOPTED_REASON)
        # The runtime-computed base is never baked into any plan record.
        self.assertFalse(
            any(entry.get("address") == "4064"
                or entry.get("source_address") == "4064"
                for entry in self.plan["entries"]))
        self.assertEqual(self.plan["selected_ids"], [76, 77, 78, 79])

    def test_both_plan_gates_accept_the_valid_plan(self):
        validate_source_plan(self.plan)
        validate_engine_plan(self.plan)

    def _forge(self, mutate, message):
        plan = deepcopy(self.plan)
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        mutate(by_id)
        with self.assertRaisesRegex(NativeCompileError, message):
            validate_source_plan(plan)
        with self.assertRaisesRegex(NativeRuntimeError, message):
            validate_engine_plan(plan)

    def test_forged_marker_metadata_is_rejected_by_both_gates(self):
        # A non-dict marker value is refused before any cross-check.
        self._forge(lambda by_id: by_id[77].update(address_provider="DynTarget30"),
                    "Invalid dynamic address provider metadata.")
        # A symbol-null marker must ride on a supported addressless record.
        self._forge(lambda by_id: by_id[78].update(
            address_provider={"provider_id": 76, "symbol": None}),
            "Dynamic address provider requires a supported addressless target record.")
        # An unknown provider record.
        self._forge(lambda by_id: by_id[77]["address_provider"].update(provider_id=9999),
                    "Dynamic address provider references an unknown record.")
        # A provider that is not a supported addressless script record.
        self._forge(lambda by_id: by_id[77]["address_provider"].update(provider_id=78),
                    "Dynamic address provider must name a supported addressless script record.")

    def test_forged_extraction_evidence_is_rejected_by_both_gates(self):
        # The marker's extraction evidence is re-derived from the embedded
        # source: a regenerated program whose idiom names another record no
        # longer covers this target.
        self._forge(lambda by_id: by_id[76].update(lua_program=prepare_lua_program(
            "{$lua}\nlocal mr = {AddressList['OtherTarget']}\n"
            "[ENABLE]\nmr[1].address = 0x1040\n"
            "[DISABLE]\nmr[1].address = nil\n",
            "FixtureTarget.exe")),
            NOT_WRITTEN)
        # Renaming the target decouples the marker from the extraction.
        self._forge(lambda by_id: by_id[77].update(label="OtherTarget"),
                    NOT_WRITTEN)
        # A provider nested below the target it serves (base/provider cycle).
        self._forge(lambda by_id: by_id[76].update(parent_id=77),
                    "Dynamic address provider must not be a descendant of the target it serves.")
        # A target nested below the provider that serves it.
        self._forge(lambda by_id: by_id[77].update(parent_id=76),
                    "Dynamic address target must not be a descendant of its provider.")


class DynamicScriptParentRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.table = write_table(self.root)
        self.memory = Memory()
        self.engine = TrainerEngine(compile_table(self.table, "FixtureTarget.exe"),
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

    def test_children_refuse_with_the_exact_phrase_before_activation(self):
        engine = self.engine
        writes = len(self.memory.writes)
        for record_id in (78, 79):
            with self.subTest(record_id=record_id):
                with self.assertRaisesRegex(NativeRuntimeError, INACTIVE_RE):
                    engine.read_value(record_id)
                with self.assertRaisesRegex(NativeRuntimeError, INACTIVE_RE):
                    engine.set_value(record_id, "1")
                with self.assertRaisesRegex(NativeRuntimeError, INACTIVE_RE):
                    engine.set_freeze(record_id, True)
                self.assertEqual(engine.entry_errors[record_id], INACTIVE)
        self.assertEqual(len(self.memory.writes), writes)
        self.assertFalse(engine.blocked)
        self.assertNotIn(76, engine.desired)
        self.assertEqual(engine.dynamic_addresses, {})

    def test_provider_activation_writes_the_base_and_children_resolve_freshly(self):
        engine = self.engine
        self.assertTrue(engine.toggle(76, True))
        self.assertIn(76, engine.desired)
        self.assertEqual(engine.dynamic_addresses[77], 0x1040)
        self.assertEqual(engine.read_value(78), "0")
        self.assertEqual(engine.set_value(78, "1234"), "1234")
        self.assertEqual(self.memory.read(0x1040 + 0x220, 4), struct.pack("<I", 1234))
        self.assertEqual(engine.set_value(79, "7"), "7")
        self.assertEqual(self.memory.read(0x1040 + 0x240, 4), b"\x07\x00\x00\x00")
        self.assertEqual(engine.read_value(78), "1234")
        self.assertEqual(engine.read_value(79), "7")
        # Disabling the provider retires the live base; the children refuse.
        engine.toggle(76, False)
        self.assertEqual(engine.dynamic_addresses, {})
        with self.assertRaisesRegex(NativeRuntimeError, INACTIVE_RE):
            engine.read_value(78)
        self.assertFalse(engine.blocked)

    def test_record_lua_surface_read_accessors_and_contract_writes(self):
        engine = self.engine
        self.assertTrue(engine.toggle(76, True))
        # Enabling the record-Lua provider already owns its activation; the
        # record scope is reachable through that owned activation host.
        host = engine.lua_activations[76].host
        self.assertEqual(host.execute('return AddressList["DynTarget30"].ID == 77'), True)
        self.assertEqual(host.execute('return AddressList["DynTarget30"].id == 77'), True)
        self.assertEqual(host.execute('return AddressList["DynTarget30"].Description == "DynTarget30"'), True)
        self.assertEqual(host.execute('return AddressList["DynTarget30"].description == "DynTarget30"'), True)
        self.assertEqual(host.execute('return AddressList["DynTarget30"].Address == 0x1040'), True)
        self.assertEqual(host.execute('return AddressList["DynTarget30"].address == 0x1040'), True)
        # A table-defined AddressList shadows the built-in index locally.
        self.assertEqual(host.execute(
            'local AddressList = {shadowed = 1}; return AddressList.shadowed == 1'),
            True)
        # The built-in index itself stays read-only.
        with self.assertRaisesRegex(LuaHostError, "read-only index"):
            host.execute('AddressList["new entry"] = 1')
        # An out-of-contract writer: a child record is not the plan target.
        with self.assertRaisesRegex(LuaHostError, "outside the planned provider contract"):
            host.execute('AddressList["dyn child m_nCharacterID"].address = 0x1050')
        # Non-integer and out-of-range values keep the range refusal.
        with self.assertRaisesRegex(LuaHostError, RANGE):
            host.execute('AddressList["DynTarget30"].address = "x"')
        with self.assertRaisesRegex(LuaHostError, RANGE):
            host.execute('AddressList["DynTarget30"].address = 0x999999')
        # nil from the provider scope clears the live base.
        self.assertEqual(host.execute(
            'AddressList["DynTarget30"].address = nil; return AddressList["DynTarget30"].address == ""'),
            True)
        self.assertEqual(engine.dynamic_addresses, {})
        with self.assertRaisesRegex(NativeRuntimeError, INACTIVE_RE):
            engine.read_value(78)
        # Re-activation republishes the base from live memory.
        engine.toggle(76, False)
        self.assertTrue(engine.toggle(76, True))
        self.assertEqual(engine.dynamic_addresses[77], 0x1040)

    def test_direct_set_dynamic_address_contract_matrix(self):
        engine = self.engine
        # The planned provider scope writes its target.
        engine.set_dynamic_address(77, 0x1050, scope=76)
        self.assertEqual(engine.dynamic_addresses[77], 0x1050)
        # Another scope or no scope is outside the planned contract.
        for scope in (999, None):
            with self.subTest(scope=scope):
                with self.assertRaisesRegex(NativeRuntimeError, CONTRACT):
                    engine.set_dynamic_address(77, 0x1050, scope=scope)
        # A target without a symbol-null marker is not writable at all.
        with self.assertRaisesRegex(NativeRuntimeError, CONTRACT):
            engine.set_dynamic_address(78, 0x1050, scope=76)
        with self.assertRaisesRegex(NativeRuntimeError,
                                    "Dynamic address target is not a plan record."):
            engine.set_dynamic_address(999, 0x1050, scope=76)
        with self.assertRaisesRegex(NativeRuntimeError, RANGE):
            engine.set_dynamic_address(77, "x", scope=76)
        with self.assertRaisesRegex(NativeRuntimeError, RANGE):
            engine.set_dynamic_address(77, 0x99999999, scope=76)
        engine.set_dynamic_address(77, None, scope=76)
        self.assertEqual(engine.dynamic_addresses, {})

    def test_disable_enable_rebases_from_live_memory(self):
        engine = self.engine
        self.assertTrue(engine.toggle(76, True))
        self.assertEqual(engine.dynamic_addresses[77], 0x1040)
        self.memory.data[8:16] = struct.pack("<Q", 0x1080)
        engine.toggle(76, False)
        self.assertEqual(engine.dynamic_addresses, {})
        self.assertTrue(engine.toggle(76, True))
        self.assertEqual(engine.dynamic_addresses[77], 0x1080)
        self.assertEqual(engine.set_value(78, "5"), "5")
        self.assertEqual(self.memory.read(0x1080 + 0x220, 4), struct.pack("<I", 5))

    def test_target_exit_and_re_attach_rebase_from_live_memory(self):
        engine = self.engine
        self.assertTrue(engine.toggle(76, True))
        self.assertEqual(engine.dynamic_addresses[77], 0x1040)
        self.memory.alive = False
        engine.poll()
        self.assertFalse(engine.connected)
        self.assertEqual(engine.dynamic_addresses, {})
        replacement = Memory()
        replacement.data[8:16] = struct.pack("<Q", 0x1080)
        self.memory = replacement
        engine.poll()
        self.assertTrue(engine.connected, engine.status)
        # The saved wish re-enabled the provider against the re-attached
        # target; the base re-derived from the live pointer (no cache).
        self.assertEqual(engine.dynamic_addresses[77], 0x1080)
        self.assertEqual(engine.set_value(79, "9"), "9")
        self.assertEqual(replacement.read(0x1080 + 0x240, 4), b"\x09\x00\x00\x00")
        engine.poll()
        self.assertFalse(engine.blocked, engine.error)

    def test_close_clears_the_live_base_registry(self):
        engine = self.engine
        self.assertTrue(engine.toggle(76, True))
        self.assertEqual(engine.dynamic_addresses[77], 0x1040)
        self.memory.alive = False
        engine.poll()
        self.assertTrue(engine.close())
        self.assertEqual(engine.dynamic_addresses, {})
        self.engine = None


class DynamicAddressExtractionTests(unittest.TestCase):
    """The bounded pure-text extraction admits exactly the two idioms."""

    def test_direct_write_idiom(self):
        source = ("[ENABLE]\n{$lua}\n"
                  "AddressList['TargetA'].address = readQword('fixturetarget.exe+8')\n"
                  "[DISABLE]\n{$lua}\n"
                  "AddressList[\"TargetA\"].address = nil\n")
        self.assertEqual(lua_dynamic_address_targets(source), ["TargetA"])

    def test_constant_array_idiom(self):
        source = ("{$lua}\n"
                  "local mr = {AddressList['TargetB'], AddressList[\"TargetC\"]}\n"
                  "[ENABLE]\n"
                  "mr[1].address = 0x1040\n"
                  "mr[2].address = 0x1048\n"
                  "[DISABLE]\n"
                  "mr[1].address = nil\n"
                  "mr[2].address = nil\n")
        self.assertEqual(lua_dynamic_address_targets(source),
                         ["TargetB", "TargetC"])

    def test_non_constant_array_element_proves_nothing(self):
        source = ("[ENABLE]\n{$lua}\n"
                  "local mr = {AddressList[other], AddressList['TargetD']}\n"
                  "mr[2].address = 0x1040\n"
                  "[DISABLE]\n{$lua}\n"
                  "mr[2].address = nil\n")
        self.assertEqual(lua_dynamic_address_targets(source), [])

    def test_out_of_range_index_proves_nothing(self):
        source = ("[ENABLE]\n{$lua}\n"
                  "local mr = {AddressList['TargetE'], AddressList['TargetF']}\n"
                  "mr[3].address = 0x1040\n"
                  "mr[0].address = 0x1048\n"
                  "[DISABLE]\n{$lua}\n"
                  "mr[3].address = nil\n")
        self.assertEqual(lua_dynamic_address_targets(source), [])

    def test_script_without_lua_proves_nothing(self):
        source = ("[ENABLE]\nassert(1040, 00)\n1040:\ndd 1\n"
                  "[DISABLE]\n1040:\ndd 0\n")
        self.assertEqual(lua_dynamic_address_targets(source), [])

    def test_more_than_the_bound_proves_nothing(self):
        lines = ["[ENABLE]", "{$lua}"]
        lines.extend(f"AddressList['T{i:02d}'].address = 0"
                     for i in range(MAX_DYNAMIC_ADDRESS_TARGETS + 1))
        lines.extend(["[DISABLE]", "{$lua}", ""])
        source = "\n".join(lines)
        self.assertEqual(lua_dynamic_address_targets(source), [])


if __name__ == "__main__":
    unittest.main()
