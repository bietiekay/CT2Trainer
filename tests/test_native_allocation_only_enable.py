"""WP-47: runtime enable for allocation-only programs (case-24 record 2 shape).

An allocation-only program (enable: alloc + registersymbol; disable:
unregistersymbol + dealloc) enables at runtime: the allocation is created
in target memory, the registered symbol is published into the runtime
symbol table, and ZERO bytes of game memory are written.  Disable
unregisters the symbol; the allocation is retained until the target exits
(hook-layer retention policy).

Everything else stays fail-closed:
- a scan-only program without an allocation is still refused at link time
  ("Program has no patch sections.");
- the thread-coordinator gate still applies to allocation-only enables;
- forged plan metadata (dropping OR adding the allocation_only flag) is
  refused by BOTH plan validators;
- a one-shot (empty-disable) allocation-only program is refused at
  prepare time.
"""
from copy import deepcopy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from ct2trainer.native.aa_program import (ProgramError, link_program,
                                          prepare_program, preflight_program)
from ct2trainer.native.compiler import (compile_table,
                                        validate_plan as compiler_validate_plan)
from ct2trainer.native.engine import (NativeRuntimeError, TrainerEngine,
                                      validate_plan as engine_validate_plan)
from test_native_engine_code import CodeMemory, Coordinator

ANCHOR = "43 54 32 54 2D 46 49 58 2D 32 30 32 36 2D 30 31"

ALLOC_CT = '''<CheatTable CheatEngineTableVersion="45"><CheatEntries>
<CheatEntry><ID>1</ID><Description>"allocation-only provider"</Description>
<VariableType>Auto Assembler Script</VariableType><AssemblerScript>[ENABLE]
alloc(synthAlloc,64)
registersymbol(synthAlloc)

[DISABLE]
unregistersymbol(synthAlloc)
dealloc(synthAlloc)</AssemblerScript></CheatEntry>
<CheatEntry><ID>2</ID><Description>"consumer value"</Description>
<VariableType>4 Bytes</VariableType><Address>SynthAlloc+4</Address></CheatEntry>
</CheatEntries></CheatTable>'''

CODE_CT = '''<CheatTable CheatEngineTableVersion="45"><CheatEntries>
<CheatEntry><ID>1</ID><Description>"code program"</Description>
<VariableType>Auto Assembler Script</VariableType><AssemblerScript>[ENABLE]
assert(FixtureTarget.exe+60,90 90)
FixtureTarget.exe+60:
db CC 90
[DISABLE]
FixtureTarget.exe+60:
db 90 90
</AssemblerScript></CheatEntry>
</CheatEntries></CheatTable>'''


class AllocMemory(CodeMemory):
    """CodeMemory plus the hook-manager allocation API with call tracking."""

    def __init__(self, pid=123, creation_time=456):
        super().__init__(pid, creation_time)
        self.data = bytearray(0x20000)
        self.data[:16] = bytes.fromhex(ANCHOR.replace(" ", ""))
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


class AllocationOnlyEnableTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.table = self.root / "alloc.ct"
        self.table.write_text(ALLOC_CT, encoding="utf-8")
        self.plan = compile_table(self.table, "FixtureTarget.exe")
        self.memory = AllocMemory()
        self.engine = None

    def tearDown(self):
        if self.engine is not None and not self.engine.closed:
            self.engine.close()

    def _start_engine(self, state_dir, shared_dir, coordinator, memory=None):
        memory = memory or self.memory
        engine = TrainerEngine(self.plan, state_dir=state_dir,
                               process_lock_dir=shared_dir,
                               memory_factory=lambda name: memory,
                               hook_coordinator=coordinator)
        engine.poll()
        self.assertTrue(engine.connected, engine.status)
        return engine

    def test_plan_metadata_marks_allocation_only_and_stages_consumer(self):
        provider = self.plan["entries"][0]
        consumer = self.plan["entries"][1]
        self.assertIs(provider["supported"], True)
        program = provider["program"]
        self.assertIs(program["allocation_only"], True)
        self.assertEqual(program["provides"], ["synthAlloc"])
        self.assertEqual([node["op"] for node in program["enable"]],
                         ["alloc", "register"])
        self.assertEqual([node["op"] for node in program["disable"]],
                         ["unregister", "dealloc"])
        self.assertEqual(consumer["requires"], ["SynthAlloc"])
        self.assertEqual(consumer["dependency_ids"], [1])
        self.assertEqual(consumer["staged"]["provider_ids"], [1])
        self.assertEqual(consumer["staged"]["provider_labels"],
                         ["allocation-only provider"])

    def test_enable_creates_allocation_publishes_symbol_and_writes_nothing(self):
        self.engine = self._start_engine(self.root / "state", self.root / "shared",
                                         Coordinator())
        self.engine.toggle(1, True)
        self.assertIn(1, self.engine.applied)
        address = self.memory.base + 0x10000
        allocation = self.engine.hooks[1].allocations["synthalloc"]
        self.assertEqual(allocation["address"], address)
        self.assertEqual(allocation["state"], "published")
        self.assertEqual(self.memory.allocations, {address: 0x1000})
        self.assertEqual(self.engine.symbols.get("synthalloc"), address)
        # Zero game-memory writes: only the allocation protection was applied.
        self.assertEqual(self.memory.writes, [])
        self.assertEqual(self.memory.allocation_protections,
                         [(address, True, True)])
        self.assertEqual(self.engine.hooks[1].receipt()["state"], "enabled")

    def test_consumer_value_is_gated_on_provider_then_roundtrips(self):
        self.engine = self._start_engine(self.root / "state", self.root / "shared",
                                         Coordinator())
        # Before the provider is live the consumer is staged-pending.
        with self.assertRaisesRegex(NativeRuntimeError,
                                    "requires active provider"):
            self.engine.set_value(2, "7")
        self.assertEqual(self.memory.writes, [])
        self.engine.toggle(1, True)
        address = self.memory.base + 0x10004
        self.assertEqual(self.engine.set_value(2, "7"), "7")
        self.assertEqual(self.memory.read(address, 4), b"\x07\x00\x00\x00")
        self.assertEqual(self.engine.read_value(2), "7")
        self.engine.set_value(2, "0")
        self.assertEqual(self.memory.read(address, 4), b"\x00\x00\x00\x00")

    def test_disable_unregisters_symbol_retains_allocation(self):
        self.engine = self._start_engine(self.root / "state", self.root / "shared",
                                         Coordinator())
        self.engine.toggle(1, True)
        self.engine.toggle(1, False)
        self.assertNotIn(1, self.engine.applied)
        self.assertNotIn("synthalloc", self.engine.symbols)
        manager = self.engine.retired_hooks[0]
        self.assertEqual(manager.receipt()["state"], "retired")
        self.assertEqual(manager.allocations["synthalloc"]["state"],
                         "retained")
        self.assertEqual(manager.exports, {})
        # Retention policy: no dealloc while the target is alive.
        self.assertEqual(self.memory.releases, [])
        with self.assertRaisesRegex(NativeRuntimeError,
                                    "requires active provider"):
            self.engine.set_value(2, "7")

    def test_allocation_only_enable_still_requires_thread_coordinator(self):
        plan = compile_table(self.table, "FixtureTarget.exe")
        memory = AllocMemory()
        engine = TrainerEngine(plan, state_dir=self.root / "no-coord",
                               process_lock_dir=self.root / "shared-nocoord",
                               memory_factory=lambda name: memory,
                               hook_coordinator=None)
        engine.poll()
        self.assertTrue(engine.connected, engine.status)
        with self.assertRaisesRegex(NativeRuntimeError,
                                    "verified target thread coordinator"):
            engine.toggle(1, True)
        self.assertEqual(memory.writes, [])
        self.assertEqual(memory.allocations, {})
        self.assertTrue(engine.close())

    def test_scan_only_program_without_allocation_still_needs_real_blocks(self):
        # A scan + registersymbol program has no patch sections and no
        # allocation: the link walk still refuses it (WP-47 only relaxes the
        # guard for genuine allocation-only programs).
        memory = AllocMemory()
        source = ("[ENABLE]\naobscanmodule(anchor,FixtureTarget.exe," + ANCHOR +
                  ")\nregistersymbol(anchor)\n[DISABLE]\n"
                  "unregistersymbol(anchor)")
        program = prepare_program(source, "FixtureTarget.exe")
        self.assertNotIn("allocation_only", program)
        preflight = preflight_program(program, memory)
        self.assertEqual(preflight["symbols"]["anchor"], memory.base)
        with self.assertRaisesRegex(ProgramError, "no patch sections"):
            link_program(program, memory, preflight["symbols"], {})
        self.assertEqual(memory.writes, [])

    def test_one_shot_allocation_only_is_refused_at_prepare(self):
        # An empty disable section makes the program a one-shot; the
        # allocation-only profile is not a one-shot profile.
        with self.assertRaisesRegex(ProgramError, "no executable patch or data"):
            prepare_program("[ENABLE]\nalloc(memory,0x100)\n[DISABLE]\n",
                            "FixtureTarget.exe")

    def test_forged_allocation_only_flag_is_refused_by_both_plan_validators(self):
        # Forge 1: drop the flag from a real allocation-only program.
        forged = deepcopy(self.plan)
        forged_entry = next(e for e in forged["entries"] if e["id"] == 1)
        del forged_entry["program"]["allocation_only"]
        with self.assertRaises(ValueError):
            compiler_validate_plan(forged)
        with self.assertRaises(NativeRuntimeError):
            engine_validate_plan(forged)
        with self.assertRaises(NativeRuntimeError):
            TrainerEngine(forged, state_dir=self.root / "forged1",
                          process_lock_dir=self.root / "shared-forged1",
                          memory_factory=lambda name: self.memory,
                          hook_coordinator=Coordinator())
        # Forge 2: add the flag to a program with real patch blocks.
        code_table = self.root / "code.ct"
        code_table.write_text(CODE_CT, encoding="utf-8")
        forged2 = compile_table(code_table, "FixtureTarget.exe")
        code_entry = next(e for e in forged2["entries"] if e["id"] == 1)
        self.assertIs(code_entry["program"].get("allocation_only"), None)
        code_entry["program"]["allocation_only"] = True
        with self.assertRaises(ValueError):
            compiler_validate_plan(forged2)
        with self.assertRaises(NativeRuntimeError):
            engine_validate_plan(forged2)


if __name__ == "__main__":
    unittest.main()
