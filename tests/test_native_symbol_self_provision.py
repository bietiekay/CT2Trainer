"""Self-provision exclusion in symbol dependency resolution (WP-49, GC-E7).

Corpus semantics (synthetic fixture, no original table content): a record
that registers a symbol AND defines the same name as its own positional
label satisfies its own reference through its own registration.  Pre-WP-49
the WP-28 label re-declaration added the symbol to the record's own
requires whenever a second record provided it, and the fixed-point pass
then emitted a self dependency edge that the DFS marked as a cycle.
Post-WP-49 the record stays supported without a self-edge; the duplicate
provider stays supported (RT-4.1, CE dupIgnore - its registration is a
runtime no-op), its consumer resolves to the kept self-provider, and
true cross-record cycles stay
fail-closed with the exact cycle reason.  A forged self-edge in the
serialized dependency_ids is still refused by both plan gates.
"""
from copy import deepcopy
from pathlib import Path
import struct
import tempfile
import unittest
from types import SimpleNamespace

from ct2trainer.native.compiler import (NativeCompileError, compile_table,
                                        validate_plan as compiler_validate_plan)
from ct2trainer.native.engine import (NativeRuntimeError, TrainerEngine,
                                      validate_plan as engine_validate_plan)
from test_native_engine_code import CodeMemory, Coordinator

CYCLE = "Symbol dependency cycle is unsupported."
SELF_EDGE = "Record dependency IDs must not contain a self-edge."

SELF_PROVISION = (
    "[ENABLE]\n"
    "alloc(SynthCycCave70, 8)\n"
    "registersymbol(SynthCycBase30)\n"
    "SynthCycBase30:\n"
    "dq 0\n"
    "[DISABLE]\n"
    "unregistersymbol(SynthCycBase30)\n"
    "dealloc(SynthCycCave70)\n")

DUPLICATE = (
    "[ENABLE]\n"
    "alloc(SynthCycDup30, 8)\n"
    "registersymbol(SynthCycBase30)\n"
    "SynthCycBase30:\n"
    "dq 0\n"
    "[DISABLE]\n"
    "unregistersymbol(SynthCycBase30)\n"
    "dealloc(SynthCycDup30)\n")

CYCLE_C = (
    "[ENABLE]\n"
    "alloc(SynthCycC30, 8)\n"
    "registersymbol(SynthCycC30)\n"
    "assert(SynthCycD30+4, 00 00 00 00)\n"
    "[DISABLE]\n"
    "unregistersymbol(SynthCycC30)\n"
    "dealloc(SynthCycC30)\n")

CYCLE_D = (
    "[ENABLE]\n"
    "alloc(SynthCycD30, 8)\n"
    "registersymbol(SynthCycD30)\n"
    "assert(SynthCycC30+4, 00 00 00 00)\n"
    "[DISABLE]\n"
    "unregistersymbol(SynthCycD30)\n"
    "dealloc(SynthCycD30)\n")

TABLE = (
    '<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
    '<CheatEntry><ID>70</ID><Description>"self-providing pointer script (kept)"'
    '</Description><VariableType>Auto Assembler Script</VariableType>'
    '<AssemblerScript>' + SELF_PROVISION + '</AssemblerScript></CheatEntry>'
    '<CheatEntry><ID>71</ID><Description>"duplicate provider (keep-first loser)"'
    '</Description><VariableType>Auto Assembler Script</VariableType>'
    '<AssemblerScript>' + DUPLICATE + '</AssemblerScript></CheatEntry>'
    '<CheatEntry><ID>72</ID><Description>"self-provision consumer int"'
    '</Description><VariableType>4 Bytes</VariableType>'
    '<Address>SynthCycBase30+4</Address></CheatEntry>'
    '<CheatEntry><ID>73</ID><Description>"cycle record C (requires D)"'
    '</Description><VariableType>Auto Assembler Script</VariableType>'
    '<AssemblerScript>' + CYCLE_C + '</AssemblerScript></CheatEntry>'
    '<CheatEntry><ID>74</ID><Description>"cycle record D (requires C)"'
    '</Description><VariableType>Auto Assembler Script</VariableType>'
    '<AssemblerScript>' + CYCLE_D + '</AssemblerScript></CheatEntry>'
    '<CheatEntry><ID>75</ID><Description>"UDS consumer int"'
    '</Description><VariableType>4 Bytes</VariableType>'
    '<Address>SynthUdsBase30+4</Address></CheatEntry>'
    '</CheatEntries>'
    '<UserdefinedSymbols>'
    '<SymbolEntry><Name>SynthUdsBase30</Name><Address>0x140006000</Address></SymbolEntry>'
    '</UserdefinedSymbols>'
    '</CheatTable>')


def write_table(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    table = root / "self_provision.ct"
    table.write_text(TABLE, encoding="utf-8")
    return table


class SelfMemory(CodeMemory):
    """CodeMemory plus the hook-manager allocation API for the cave allocs."""

    def __init__(self, pid=123, creation_time=456):
        super().__init__(pid, creation_time)
        self.data = bytearray(0x20000)
        self.allocations = {}
        self.allocation_protections = []
        self._alloc_protect = {}
        self.releases = []

    def allocate(self, size, near=None):
        address = self.base + 0x10000
        actual = (size + 4095) // 4096 * 4096
        self.allocations[address] = actual
        return address

    def allocation_size(self, address):
        return self.allocations[address]

    def protect_allocation(self, address, executable=True, writable=False):
        self.allocation_protections.append((address, executable, writable))
        self._alloc_protect[address] = (0x40 if writable else 0x20) if executable else 0x04

    def _query(self, address):
        for start, size in self.allocations.items():
            if start <= address < start + size:
                return SimpleNamespace(BaseAddress=start, AllocationBase=start,
                                       RegionSize=size, State=0x1000,
                                       Protect=self._alloc_protect.get(start, 0x04))
        if self.base <= address < self.base + len(self.data):
            return SimpleNamespace(BaseAddress=self.base, AllocationBase=self.base,
                                   RegionSize=len(self.data), State=0x1000, Protect=0x04)
        raise RuntimeError("unmapped test range")

    def release(self, address):
        self.releases.append(address)


class SelfProvisionPlanTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.table = write_table(self.root)
        self.plan = compile_table(self.table, "FixtureTarget.exe")
        self.by_id = {entry["id"]: entry for entry in self.plan["entries"]}

    def test_self_providing_record_is_kept_without_a_self_edge(self):
        row = self.by_id[70]
        self.assertTrue(row["supported"], row["reason"])
        self.assertEqual(row["kind"], "script")
        self.assertEqual(row["provides"], ["SynthCycBase30"])
        # The own registration satisfies the own reference: no require for
        # the self-provided symbol and no dependency edge onto itself.
        self.assertNotIn("SynthCycBase30", row["requires"])
        self.assertNotIn(70, row["dependency_ids"])
        self.assertEqual(row["dependency_ids"], [])

    def test_duplicate_provider_stays_supported_behind_the_kept_one(self):
        # RT-4.1 (CE dupIgnore): the duplicate provider stays supported;
        # the kept provider (70) is the only visible provider for the
        # symbol and the duplicate's registration is a runtime no-op.
        row = self.by_id[71]
        self.assertTrue(row["supported"], row["reason"])
        self.assertEqual(row["kind"], "script")

    def test_consumer_resolves_to_the_kept_self_provider(self):
        row = self.by_id[72]
        self.assertTrue(row["supported"], row["reason"])
        self.assertEqual(row["dependency_ids"], [70])
        self.assertEqual(row["requires"], ["SynthCycBase30"])

    def test_true_cross_record_cycle_stays_blocked_with_the_exact_reason(self):
        for record_id in (73, 74):
            row = self.by_id[record_id]
            self.assertFalse(row["supported"], row["reason"])
            self.assertEqual(row["kind"], "blocked")
            self.assertEqual(row["reason"], CYCLE)
        # Nothing else in the table requires the cycle symbols, so the block
        # stays local (no cascade).
        self.assertTrue(self.by_id[72]["supported"], self.by_id[72]["reason"])

    def test_user_defined_symbol_consumer_stays_supported_without_a_dependency(self):
        row = self.by_id[75]
        self.assertTrue(row["supported"], row["reason"])
        self.assertEqual(row["requires"], ["SynthUdsBase30"])
        self.assertEqual(row["dependency_ids"], [])

    def test_both_plan_gates_accept_the_valid_plan(self):
        compiler_validate_plan(self.plan)
        engine_validate_plan(self.plan)

    def _forge_self_edge(self, record_id):
        plan = deepcopy(self.plan)
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        by_id[record_id]["dependency_ids"].append(record_id)
        with self.assertRaisesRegex(NativeCompileError, SELF_EDGE):
            compiler_validate_plan(plan)
        with self.assertRaisesRegex(NativeRuntimeError, SELF_EDGE):
            engine_validate_plan(plan)

    def test_forged_self_edge_is_refused_by_both_gates(self):
        for record_id in (70, 72):
            with self.subTest(record_id=record_id):
                self._forge_self_edge(record_id)


class SelfProvisionRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.table = write_table(self.root)
        self.memory = SelfMemory()
        self.engine = TrainerEngine(compile_table(self.table, "FixtureTarget.exe"),
                                    state_dir=self.root / "state",
                                    process_lock_dir=self.root / "shared",
                                    memory_factory=lambda name: self.memory,
                                    hook_coordinator=Coordinator())
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)

    def tearDown(self):
        self.memory.alive = False
        self.engine.poll()
        self.engine.close()

    def test_self_provisioning_enable_resolves_the_consumer_and_reverses(self):
        engine = self.engine
        # The kept self-provider enables without a self-cycle refusal.
        self.assertTrue(engine.toggle(70, True))
        self.assertIn(70, engine.desired)
        cave = engine.symbols["synthcycbase30"]
        self.assertEqual(cave, self.memory.base + 0x10000)
        # The consumer follows the self-provided symbol at runtime.
        self.assertEqual(engine.read_value(72), "0")
        self.assertEqual(engine.set_value(72, "1234"), "1234")
        self.assertEqual(self.memory.read(cave + 4, 4), struct.pack("<I", 1234))
        self.assertEqual(engine.read_value(72), "1234")
        # RT-4.1 (CE dupIgnore): the duplicate provider (71) activates
        # without a collision; its registration of the already-owned
        # symbol is a silent no-op, and its disable releases nothing.
        self.assertTrue(engine.toggle(71, True), engine.error)
        self.assertEqual(engine.symbols["synthcycbase30"], cave)
        engine.toggle(71, False)
        self.assertEqual(engine.symbols["synthcycbase30"], cave)
        # The true cross-record cycle pair is still un-toggleable.
        for record_id in (73, 74):
            with self.subTest(record_id=record_id):
                with self.assertRaises(NativeRuntimeError):
                    engine.toggle(record_id, True)
                self.assertNotIn(record_id, engine.desired)
        # Disabling the provider retires the symbol; the staged consumer
        # refuses with the named staged-provider phrase.
        engine.toggle(70, False)
        self.assertNotIn("synthcycbase30", engine.symbols)
        self.assertNotIn(70, engine.desired)
        with self.assertRaisesRegex(NativeRuntimeError,
                                    "requires active provider"):
            engine.read_value(72)
        with self.assertRaisesRegex(NativeRuntimeError,
                                    "requires active provider"):
            engine.set_value(72, "1")
        self.assertIn("self-providing pointer script (kept)",
                      engine.entry_errors[72])
        self.assertFalse(engine.blocked)
        self.assertTrue(engine.close())


if __name__ == "__main__":
    unittest.main()
