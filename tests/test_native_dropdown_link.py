"""Cross-record DropDownListLink runtime wiring.

Corpus semantics (pinned rml table, P5-style tables): a linked record keeps
its own address and value type; the dropdown choices are borrowed from the
named target record (group or value). Setting the value writes the choice
literal to the linked record's own address, never to the target. The plan
records the target explicitly via dropdown.link_target_id, and both plan
validators refuse forged target references.
"""
from pathlib import Path
import tempfile
import unittest

from test_native_engine_code import Coordinator
from test_native_lua_activation import Memory
from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import TrainerEngine, NativeRuntimeError

CT_BODY = '''<CheatTable CheatEngineTableVersion="45"><CheatEntries>
<CheatEntry><ID>2000</ID><Description>"Achievement Related"</Description><GroupHeader>1</GroupHeader><Address>1040</Address>
<CheatEntries>
<CheatEntry NoCheckbox="1"><ID>2001</ID><Description>"-"</Description><GroupHeader>1</GroupHeader>
<CheatEntries>
<CheatEntry><ID>2002</ID><Description>"Scored Kill By Bottle"</Description><DropDownListLink>Achievement Related</DropDownListLink><VariableType>Byte</VariableType><Address>+1</Address></CheatEntry>
<CheatEntry><ID>2003</ID><Description>"Skill Slot"</Description><DropDownListLink>Choices</DropDownListLink><VariableType>4 Bytes</VariableType><Address>+4</Address></CheatEntry>
<CheatEntry><ID>2004</ID><Description>"Locked Slot"</Description><DropDownListLink>Choices RO</DropDownListLink><VariableType>Byte</VariableType><Address>+8</Address></CheatEntry>
</CheatEntries>
</CheatEntry>
</CheatEntries>
</CheatEntry>
<CheatEntry><ID>2010</ID><Description>"Choices"</Description><VariableType>Byte</VariableType><Address>1050</Address><DropDownList>
0:Off
1:On
2:Both
</DropDownList></CheatEntry>
<CheatEntry><ID>2011</ID><Description>"Choices RO"</Description><VariableType>Byte</VariableType><Address>1060</Address><DropDownList ReadOnly="1">
0:Off
1:On
</DropDownList></CheatEntry>
</CheatEntries></CheatTable>'''


class DropdownLinkRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.table = self.root / "dropdown.ct"
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

    def test_plan_carries_explicit_link_targets(self):
        by_id = {entry["id"]: entry for entry in self.engine.plan["entries"]}
        self.assertEqual(by_id[2002]["dropdown"],
                         {"choices": [], "read_only": False, "link_target_id": 2000})
        self.assertEqual(by_id[2003]["dropdown"]["link_target_id"], 2010)
        self.assertEqual(by_id[2004]["dropdown"]["link_target_id"], 2011)
        self.assertTrue(by_id[2004]["dropdown"]["read_only"])
        self.assertNotIn("link_target_id", by_id[2010]["dropdown"])

    def test_choiceless_group_link_stays_a_free_value_at_own_address(self):
        self.assertEqual(self.engine.set_value(2002, "7"), "7")
        self.assertEqual(self.memory.read(0x1041, 1), b"\x07")
        self.assertEqual(self.engine.read_value(2002), "7")

    def test_borrowed_dropdown_writes_the_choice_value_to_own_address(self):
        self.assertEqual(self.engine.set_value(2003, "2"), "2")
        self.assertEqual(self.memory.read(0x1044, 4), b"\x02\x00\x00\x00")
        self.assertEqual(self.memory.read(0x1050, 1), b"\x00")
        self.assertEqual(self.engine.read_value(2003), "2")

    def test_read_only_borrowed_dropdown_rejects_values_outside_choices(self):
        with self.assertRaisesRegex(NativeRuntimeError, "Choose a value from the supplied list"):
            self.engine.set_value(2004, "5")
        self.assertFalse(self.memory.writes)
        self.assertEqual(self.engine.set_value(2004, "1"), "1")
        self.assertEqual(self.memory.read(0x1048, 1), b"\x01")

    def test_link_record_freeze_restores_its_own_address(self):
        self.engine.set_value(2003, "3")
        self.engine.set_freeze(2003, True)
        self.memory.data[0x44] = 0xFF
        self.engine.poll()
        self.assertFalse(self.engine.blocked, self.engine.error)
        self.assertEqual(self.memory.read(0x1044, 4), b"\x03\x00\x00\x00")

    def test_forged_link_target_metadata_is_rejected_before_attach(self):
        plan = compile_table(self.table, "FixtureTarget.exe")
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        by_id[2002]["dropdown"]["link_target_id"] = 9999
        with self.assertRaises(NativeRuntimeError):
            TrainerEngine(plan, state_dir=self.root / "state2",
                          process_lock_dir=self.root / "shared2",
                          memory_factory=lambda name: self.memory,
                          hook_coordinator=self.coordinator)
