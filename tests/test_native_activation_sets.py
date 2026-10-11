"""WP-14 (C3): static record-ID activation sets (master-toggle pattern).

Multi-step tables carry a "master toggle" record whose embedded {$lua}
section flips a known set of other records on/off by record ID.  The
converter extracts those sets purely statically (narrow, fail-closed
grammar); the engine applies the set through the ordinary per-record
activation path instead of executing the CE-coupled Lua.  Only the
master's own wish is persisted (save boundary).
"""
from copy import deepcopy
import shutil
import tempfile
import unittest
from pathlib import Path

from test_native_engine import FakeMemory

from ct2trainer.native.compiler import (NativeCompileError, compile_table,
                                        validate_plan as validate_compiler_plan)
from ct2trainer.native.engine import (NativeRuntimeError, TrainerEngine,
                                      validate_plan as validate_engine_plan)
from ct2trainer.native.lua_activation_sets import (SOURCE_TAG,
                                                   extract_activation_sets)

PROCESS = "FixtureTarget.exe"

ANCHOR = (
    "[ENABLE]\n"
    "aobscanmodule(FixtureAnchor,FixtureTarget.exe,43 54 32 54 2D 46 49 58 2D 32 30 32 36 2D 30 31)\n"
    "registersymbol(FixtureAnchor)\n"
    "\n"
    "[DISABLE]\n"
    "unregistersymbol(FixtureAnchor)\n"
)

CONSUMER = (
    # Offsets are hex (pinned address-expression contract): +40 -> 0x1040.
    "[ENABLE]\n"
    "assert(FixtureAnchor+40,00 00 00 00)\n"
    "FixtureAnchor+40:\n"
    "  dd 1\n"
    "\n"
    "[DISABLE]\n"
    "assert(FixtureAnchor+40,01 00 00 00)\n"
    "FixtureAnchor+40:\n"
    "  dd 0\n"
)

MASTER_LUA = (
    "[ENABLE]\n"
    "{$lua}\n"
    "getAddressList().getMemoryRecordByID(2).Active = true\n"
    "getAddressList().getMemoryRecordByID(6).Active = true\n"
    "[DISABLE]\n"
    "{$lua}\n"
    "getAddressList().getMemoryRecordByID(2).Active = false\n"
    "getAddressList().getMemoryRecordByID(6).Active = false\n"
)


def master_table_xml():
    master = ('<CheatEntry><ID>0</ID><Description>"Master toggle"'
              '</Description><VariableType>Auto Assembler Script'
              f'</VariableType><AssemblerScript>{MASTER_LUA}</AssemblerScript></CheatEntry>')
    v1 = ('<CheatEntry><ID>1</ID><Description>"Unrelated value"'
          '</Description><VariableType>4 Bytes</VariableType>'
          '<Address>1000</Address></CheatEntry>')
    anchor = ('<CheatEntry><ID>2</ID><Description>"Anchor provider"'
              '</Description><VariableType>Auto Assembler Script'
              f'</VariableType><AssemblerScript>{ANCHOR}</AssemblerScript></CheatEntry>')
    staged = ('<CheatEntry><ID>3</ID><Description>"Staged value"'
              '</Description><VariableType>4 Bytes</VariableType>'
              '<Address>FixtureAnchor+72</Address></CheatEntry>')
    v4 = ('<CheatEntry><ID>4</ID><Description>"Value A"'
          '</Description><VariableType>4 Bytes</VariableType>'
          '<Address>1004</Address></CheatEntry>')
    v5 = ('<CheatEntry><ID>5</ID><Description>"Value B"'
          '</Description><VariableType>4 Bytes</VariableType>'
          '<Address>1008</Address></CheatEntry>')
    consumer = ('<CheatEntry><ID>6</ID><Description>"Consumer script"'
                '</Description><VariableType>Auto Assembler Script'
                f'</VariableType><AssemblerScript>{CONSUMER}</AssemblerScript></CheatEntry>')
    return ('<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
            + master + v1 + anchor + staged + v4 + v5 + consumer
            + '</CheatEntries></CheatTable>')


class ExtractorTests(unittest.TestCase):
    """Narrow static grammar: adopt only unambiguous master-toggle Lua."""

    def test_happy_path_direct_and_bound_variable(self):
        lua = ("[ENABLE]\n"
               "getAddressList().getMemoryRecordByID(2).Active = true\n"
               "local r = getMemoryRecordByID(6)\n"
               "r.Active = true\n"
               "[DISABLE]\n"
               "getMemoryRecordByID(2).Active = false\n"
               "r.Active = false\n")
        self.assertEqual(
            extract_activation_sets(lua, {0, 1, 2, 3, 4, 5, 6}, own_id=0),
            {"enable": [2, 6], "disable": [2, 6], "source": SOURCE_TAG},
        )

    def test_ce_coupled_lines_are_ignored(self):
        lua = ("[ENABLE]\n"
               "getLuaEngine().menuItem5.doClick()\n"
               "synchronize(function() addressList.refresh() end)\n"
               "getMemoryRecordByID(2).Active = true\n"
               "[DISABLE]\n"
               "addressList.refresh()\n"
               "getMemoryRecordByID(2).Active = false\n"
               "getLuaEngine().Close()\n")
        sets = extract_activation_sets(lua, {0, 1, 2}, own_id=0)
        self.assertEqual(sets["enable"], [2])
        self.assertEqual(sets["disable"], [2])
        self.assertEqual(sets["source"], SOURCE_TAG)

    def test_missing_disable_section_refused(self):
        lua = "[ENABLE]\ngetMemoryRecordByID(2).Active = true\n"
        self.assertIsNone(extract_activation_sets(lua, {0, 1, 2}, own_id=0))

    def test_missing_enable_section_refused(self):
        lua = "[DISABLE]\ngetMemoryRecordByID(2).Active = false\n"
        self.assertIsNone(extract_activation_sets(lua, {0, 1, 2}, own_id=0))

    def test_dynamic_record_id_refused(self):
        lua = ("[ENABLE]\n"
               "for id in {2, 6} do getMemoryRecordByID(id).Active = true end\n"
               "[DISABLE]\n"
               "for id in {2, 6} do getMemoryRecordByID(id).Active = false end\n")
        self.assertIsNone(extract_activation_sets(lua, {0, 1, 2, 6}, own_id=0))

    def test_direction_mismatch_in_section_refused(self):
        lua = ("[ENABLE]\n"
               "getMemoryRecordByID(2).Active = true\n"
               "getMemoryRecordByID(6).Active = false\n"
               "[DISABLE]\n"
               "getMemoryRecordByID(2).Active = false\n")
        self.assertIsNone(extract_activation_sets(lua, {0, 1, 2, 6}, own_id=0))

    def test_unknown_record_id_refused(self):
        lua = ("[ENABLE]\ngetMemoryRecordByID(7).Active = true\n"
               "[DISABLE]\ngetMemoryRecordByID(7).Active = false\n")
        self.assertIsNone(extract_activation_sets(lua, {0, 1, 2}, own_id=0))

    def test_self_reference_refused(self):
        lua = ("[ENABLE]\n"
               "getMemoryRecordByID(0).Active = true\n"
               "getMemoryRecordByID(2).Active = true\n"
               "[DISABLE]\n"
               "getMemoryRecordByID(0).Active = false\n"
               "getMemoryRecordByID(2).Active = false\n")
        self.assertIsNone(extract_activation_sets(lua, {0, 1, 2}, own_id=0))

    def test_duplicate_assignment_in_one_phase_refused(self):
        lua = ("[ENABLE]\n"
               "getMemoryRecordByID(2).Active = true\n"
               "getMemoryRecordByID(2).Active = true\n"
               "[DISABLE]\n"
               "getMemoryRecordByID(2).Active = false\n")
        self.assertIsNone(extract_activation_sets(lua, {0, 1, 2}, own_id=0))

    def test_manipulation_before_first_phase_refused(self):
        lua = ("getMemoryRecordByID(2).Active = true\n"
               "[ENABLE]\ngetMemoryRecordByID(2).Active = true\n"
               "[DISABLE]\ngetMemoryRecordByID(2).Active = false\n")
        self.assertIsNone(extract_activation_sets(lua, {0, 1, 2}, own_id=0))

    def test_rebind_to_different_id_refused(self):
        lua = ("[ENABLE]\n"
               "local r = getMemoryRecordByID(2)\n"
               "local r = getMemoryRecordByID(6)\n"
               "r.Active = true\n"
               "[DISABLE]\n"
               "r.Active = false\n")
        self.assertIsNone(extract_activation_sets(lua, {0, 1, 2, 6}, own_id=0))

    def test_local_alias_of_address_list_refused(self):
        # A non-canonical receiver chain (local alias of getAddressList)
        # is outside the narrow grammar and fails closed.
        lua = ("[ENABLE]\n"
               "local al = getAddressList()\n"
               "al.getMemoryRecordByID(2).Active = true\n"
               "[DISABLE]\n"
               "al.getMemoryRecordByID(2).Active = false\n")
        self.assertIsNone(extract_activation_sets(lua, {0, 1, 2}, own_id=0))

    def test_empty_or_non_text_source_refused(self):
        self.assertIsNone(extract_activation_sets("", {0, 1, 2}, own_id=0))
        self.assertIsNone(extract_activation_sets(None, {0, 1, 2}, own_id=0))


class ActivationSetPlanTests(unittest.TestCase):
    """Plan metadata: extraction result attached + tamper refusal."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="native-setplan-"))
        table = self.root / "master.ct"
        table.write_text(master_table_xml(), encoding="utf-8")
        self.plan = compile_table(table, PROCESS)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def entries(self):
        return {entry["id"]: entry for entry in self.plan["entries"]}

    def test_master_toggle_gets_extraction_metadata(self):
        by_id = self.entries()
        self.assertEqual(
            by_id[0]["activation_sets"],
            {"enable": [2, 6], "disable": [2, 6], "source": SOURCE_TAG},
        )
        # Ordinary records carry no marker.
        self.assertNotIn("activation_sets", by_id[1])
        self.assertNotIn("activation_sets", by_id[2])
        self.assertNotIn("activation_sets", by_id[6])
        validate_compiler_plan(self.plan)
        validate_engine_plan(self.plan)

    def test_tampered_activation_sets_refused_by_both_validators(self):
        invalid = deepcopy(self.plan)
        by_id = {entry["id"]: entry for entry in invalid["entries"]}
        by_id[0]["activation_sets"]["enable"].append(3)
        with self.assertRaisesRegex(NativeCompileError, "Activation-set metadata"):
            validate_compiler_plan(invalid)
        with self.assertRaises(NativeRuntimeError):
            validate_engine_plan(invalid)

    def test_forged_marker_on_non_lua_record_refused(self):
        invalid = deepcopy(self.plan)
        by_id = {entry["id"]: entry for entry in invalid["entries"]}
        by_id[2]["activation_sets"] = {
            "enable": [6], "disable": [6], "source": SOURCE_TAG}
        with self.assertRaisesRegex(NativeCompileError, "requires a supported Lua script"):
            validate_compiler_plan(invalid)


class ActivationSetEngineTests(unittest.TestCase):
    """Engine: the set is applied through per-record activation, never Lua."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.shared = self.directory / "shared"
        table = self.directory / "master.ct"
        table.write_text(master_table_xml(), encoding="utf-8")
        self.plan = compile_table(table, PROCESS)
        self.memory = FakeMemory()
        self.factory = lambda _name: self.memory
        self.engine = None

    def tearDown(self):
        if self.engine is not None and not self.engine.closed:
            self.engine.close()
        self.temp.cleanup()

    def start(self):
        self.engine = TrainerEngine(self.plan, self.directory, self.factory,
                                    self.shared)
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)
        return self.engine

    def test_master_on_applies_set_without_executing_embedded_lua(self):
        engine = self.start()
        self.assertTrue(engine.toggle(0, True))
        # The CE-coupled Lua never runs: no Lua activation scope is owned.
        self.assertNotIn(0, engine.lua_activations)
        # The set is applied through the ordinary per-record paths.
        self.assertEqual(set(engine.applied), {0, 2, 6})
        self.assertEqual(self.memory.read(0x1040, 4), b"\x01\x00\x00\x00")
        # The consumer's provider (anchor 2) is live, so its staged value
        # child is accessible now.
        self.assertEqual(engine.read_value(3), "0")
        # Save boundary: only the master's own wish persists.
        self.assertEqual(engine.desired, {0})

    def test_master_off_reverts_set_and_clears_wish(self):
        engine = self.start()
        engine.toggle(0, True)
        self.assertFalse(engine.toggle(0, False))
        self.assertEqual(set(engine.applied), set())
        self.assertEqual(self.memory.read(0x1040, 4), bytes(4))
        self.assertEqual(engine.desired, set())
        self.assertFalse(engine.blocked)

    def test_partial_failure_keeps_partial_state_and_saves_nothing(self):
        engine = self.start()
        self.memory.data[0x40] = 9  # break the consumer's enable assertion
        with self.assertRaisesRegex(NativeRuntimeError, "assertion"):
            engine.toggle(0, True)
        # The anchor landed before the consumer failed: visible partial
        # state, master not confirmed, nothing saved.
        self.assertIn(2, engine.applied)
        self.assertNotIn(6, engine.applied)
        self.assertNotIn(0, engine.applied)
        self.assertEqual(engine.desired, set())
        self.assertFalse(engine.blocked)

    def test_master_wish_replays_the_set_on_attach(self):
        engine = self.start()
        engine.toggle(0, True)
        self.assertTrue(engine.close())
        self.memory = FakeMemory()
        self.engine = TrainerEngine(self.plan, self.directory, self.factory,
                                    self.shared)
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)
        self.assertEqual(self.engine.desired, {0})
        self.assertEqual(set(self.engine.applied), {0, 2, 6})
        self.assertEqual(self.memory.read(0x1040, 4), b"\x01\x00\x00\x00")
