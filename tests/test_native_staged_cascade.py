"""Two-level provider cascade and staged-value unlock (SOM-shaped, 2026-10-30).

Field request (2026-10-30, South of Midnight table V1.2): staged value rows
must only become usable once their provider is live - and when the provider
is itself a cascade child of a flagged master record, only once the master
toggle drives the whole chain.  The real table structure:

- 26254 "3) Activate me ! ... to enable POINTERS." (script, registers the
  ``bouloches`` pointer; options moAlwaysHideChildren +
  moActivateChildrenAsWell + moDeactivateChildrenAsWell)
- 26271 "Activate me then pause game to enable Floof chapter pointers"
  (nested child, registers ``boulchap``)
- 26278 "Activate me then open collections menu to enable Floof collection
  pointers" (nested child, registers ``boultotal``)
- value entries ``bouloches``/``boulchap``/``boultotal`` (+offset) staged on
  their respective provider

This test reproduces the shape with allocation-only providers (no AOB scan
needed) and proves the two-level flow end-to-end:

- Parent (ID 1) registers symbol ``symA``; options moAlwaysHideChildren +
  moActivateChildrenAsWell + moDeactivateChildrenAsWell.
- Child (ID 2, nested under 1) registers symbol ``symB``.
- Value (ID 3) on ``symA+4`` -> staged on 1 (direct).
- Value (ID 4) on ``symB+4`` -> staged on 2 (indirect: 2 is live only
  through the 1 -> 2 cascade).

Contract:
- Before 1 is active: both values are staged-pending (read and write are
  refused by name; nothing is written).
- Toggle 1 ON: the cascade activates 2 as well, both symbols are published,
  both values read and write.
- Toggle 1 OFF: the cascade deactivates 2, both symbols are gone, both
  values are staged-pending again.
"""
import tempfile
import unittest
from pathlib import Path

from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import NativeRuntimeError, TrainerEngine
from test_native_allocation_only_enable import AllocMemory
from test_native_engine_code import Coordinator


class TwoAllocMemory(AllocMemory):
    """AllocMemory with sequential allocation addresses.

    The base AllocMemory always returns the same address; two concurrent
    allocation-only providers (the SOM shape) would then share one cave and
    the engine's immutable-cave receipt check (correctly) refuses the second
    write.  Real target memory hands out distinct addresses.
    """

    def __init__(self, pid=123, creation_time=456):
        super().__init__(pid, creation_time)
        self._next_alloc = self.base + 0x10000

    def allocate(self, size, near=None):
        address = self._next_alloc
        actual = (size + 4095) // 4096 * 4096
        self._next_alloc += actual
        self.allocations[address] = actual
        return address

SOM_LIKE_CT = '''<CheatTable CheatEngineTableVersion="45"><CheatEntries>
<CheatEntry><ID>1</ID><Description>"Master"</Description>
<Options moAlwaysHideChildren="1" moActivateChildrenAsWell="1" moDeactivateChildrenAsWell="1"/>
<VariableType>Auto Assembler Script</VariableType><AssemblerScript>[ENABLE]
alloc(symA,64)
registersymbol(symA)

[DISABLE]
unregistersymbol(symA)
dealloc(symA)</AssemblerScript>
<CheatEntries>
<CheatEntry><ID>2</ID><Description>"Chapter provider"</Description>
<VariableType>Auto Assembler Script</VariableType><AssemblerScript>[ENABLE]
alloc(symB,64)
registersymbol(symB)

[DISABLE]
unregistersymbol(symB)
dealloc(symB)</AssemblerScript></CheatEntry>
</CheatEntries></CheatEntry>
<CheatEntry><ID>3</ID><Description>"Value on A"</Description>
<VariableType>4 Bytes</VariableType><Address>symA+4</Address></CheatEntry>
<CheatEntry><ID>4</ID><Description>"Value on B"</Description>
<VariableType>4 Bytes</VariableType><Address>symB+4</Address></CheatEntry>
</CheatEntries></CheatTable>'''


class TwoLevelStagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.table = self.root / "som_like.ct"
        self.table.write_text(SOM_LIKE_CT, encoding="utf-8")
        self.plan = compile_table(self.table, "FixtureTarget.exe")
        self.engine = None

    def tearDown(self):
        if self.engine is not None and not self.engine.closed:
            self.engine.close()

    def _start(self):
        memory = TwoAllocMemory()
        engine = TrainerEngine(self.plan, state_dir=self.root / "state",
                               process_lock_dir=self.root / "shared",
                               memory_factory=lambda name: memory,
                               hook_coordinator=Coordinator())
        self.engine = engine
        engine.poll()
        self.assertTrue(engine.connected, engine.status)
        return engine, memory

    def test_plan_carries_two_level_staging(self):
        by_id = {e["id"]: e for e in self.plan["entries"]}
        self.assertEqual(by_id[1].get("parent_activation"), "required_dependency")
        # CE display parity: the flagged master's subtree is marked non-renderable.
        self.assertIs(by_id[1].get("hidden_children"), True)
        self.assertNotIn("hidden_children", by_id[2])
        self.assertEqual(by_id[3]["staged"]["provider_ids"], [1])
        self.assertEqual(by_id[3]["staged"]["provider_labels"],
                         [by_id[1]["path"]])
        self.assertEqual(by_id[4]["staged"]["provider_ids"], [2])
        self.assertEqual(by_id[4]["staged"]["provider_labels"],
                         [by_id[2]["path"]])
        rels = self.plan.get("parent_relations", {})
        self.assertEqual(rels.get("1", {}).get("2"), "required_dependency")

    def test_values_pending_unlock_via_cascade_then_repend(self):
        engine, memory = self._start()
        # Staged-pending: both values refuse read and write before the
        # master is active; nothing reaches target memory.
        for value_id in (3, 4):
            with self.subTest(value_id=value_id), \
                    self.assertRaisesRegex(NativeRuntimeError, "requires active provider"):
                engine.read_value(value_id)
            with self.subTest(value_id=value_id), \
                    self.assertRaisesRegex(NativeRuntimeError, "requires active provider"):
                engine.set_value(value_id, "7")
        self.assertEqual(memory.writes, [])

        # Master ON cascades to the child provider; both symbols are live
        # and both values (direct and indirect) unlock.
        engine.toggle(1, True)
        self.assertEqual(engine.status, "Master: enabled and saved")
        self.assertIn(1, engine.applied)
        self.assertIn(2, engine.applied)
        self.assertIn("symb", engine.symbols)
        self.assertEqual(engine.set_value(3, "7"), "7")
        self.assertEqual(engine.set_value(4, "9"), "9")
        self.assertEqual(engine.read_value(3), "7")
        self.assertEqual(engine.read_value(4), "9")

        # Master OFF cascades OFF; both values are staged-pending again.
        # (toggle returns the requested direction, not a success flag.)
        engine.toggle(1, False)
        self.assertEqual(engine.status, "Master: disabled and saved")
        self.assertNotIn(2, engine.applied)
        self.assertNotIn("symb", engine.symbols)
        for value_id in (3, 4):
            with self.subTest(value_id=value_id), \
                    self.assertRaisesRegex(NativeRuntimeError, "requires active provider"):
                engine.read_value(value_id)
