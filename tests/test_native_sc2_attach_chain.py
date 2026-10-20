"""Sinking City 2 field case: the multi-step "activate" chain at runtime.

The real Sinking City 2 table (local-only input; the anonymized case-32
derivative is the cycle-end pin decision, see TRACKING.md) drives a
three-step activation:

1. a one-shot record whose only effect is the CE ``OpenProcess("<exe>")``
   attach call (record id 200, "1 Activate me! Attach game's process"):
   the native trainer attaches to the target at startup, so the call runs
   as the WP-56 identity no-op - it verifies the requested process name
   against the attached process and returns true.  A name mismatch is a
   named refusal (runtime, not plan level).
2. a two-phase AOB provider (record id 1337270331, "3 ... enable
   POINTERS"): aobscanmodule + alloc + registersymbol; the pattern has
   several matches in the real EXE - first (lowest-address) match wins at
   runtime (WP-55 CE parity), full match evidence in the scan diagnostics.
3. a staged pointer value record (record id 31, "Talents"): the address is
   a symbol registered by the provider plus one XML ``<Offset>`` slot
   (hex by CE convention); reads are refused with the named staged gate
   (WP-14 C1) while the provider is not live, and resolve byte-exact
   afterwards.

Plan level: the real table compiles 34/34 supported / 0 blocked with the
value staged on the provider (measured 2026-10-20).  This test proves the
runtime chain on owned fake memory with the real Lua host; the provider
record assembles real instructions, so the suite must run with
CT2TRAINER_NASM set (AA/nasm convention).
"""
from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from test_native_compiler import script_record, value_record
from test_native_engine import FakeMemory
from test_native_engine_code import Coordinator
from ct2trainer.native.compiler import compile_table, validate_plan
from ct2trainer.native.engine import (NativeRuntimeError, TrainerEngine,
                                      validate_plan as validate_runtime_plan)


PROCESS = "ct2synth32.exe"

# The 9-byte pattern (as in the real table).  Two occurrences are planted
# in fixture memory to exercise the multi-match first-match rule.
PATTERN = b"\x8b\x92\x80\x00\x00\x00\x48\x89\x44"

# One-shot attach record (real table id 200): pure Lua, empty DISABLE.
ATTACH_SCRIPT = (
    "[ENABLE]\n"
    "{$lua}\n"
    f'OpenProcess("{PROCESS}")\n'
    "{$asm}\n"
    "[DISABLE]\n"
)

# Two-phase pointer provider mirroring the real table id 1337270331:
# AOB scan, alloc near the match, hook code, six-byte patch at the scan
# site, wildcard cleanup.  The pointer symbol is registered from a
# define (fixed address in module memory) so the test can pre-seed the
# pointer qword and the chased value deterministically.
PROVIDER_SCRIPT = (
    "[ENABLE]\n"
    f"aobscanmodule(synthTal32, {PROCESS}, 8B 92 80 00 00 00 48 89 44)\n"
    "alloc(newmem32, $1000, synthTal32)\n"
    "  newmem32:\n"
    "  mov edx,[rdx+00000080]\n"
    "  jmp resume\n"
    "synthTal32:\n"
    "  jmp newmem32\n"
    "  nop\n"
    "resume:\n"
    "define(synthPtr32, 1020)\n"
    "registersymbol(synthTal32)\n"
    "registersymbol(synthPtr32)\n"
    "[DISABLE]\n"
    "synthTal32:\n"
    "  db 8B 92 80 00 00 00\n"
    "unregistersymbol(*)\n"
    "dealloc(*)\n"
)

# Staged pointer value (real table id 31, "Talents"): symbol address plus
# one hex <Offset> slot (CE convention: 0x80).
VALUE_EXTRA = "<Offsets><Offset>80</Offset></Offsets>"


def write_table(directory, body, sections=""):
    path = Path(directory) / "sc2chain32.ct"
    path.write_text('<CheatTable CheatEngineTableVersion="46"><CheatEntries>'
                    + body + '</CheatEntries>' + sections + '</CheatTable>',
                    encoding="utf-8")
    return path


class Sc2ChainMemory(FakeMemory):
    """FakeMemory with the identity/range/allocate surface the engine paths
    require; one cave backs the provider's allocation (pattern after
    CaveMemory in test_native_lua_assembled_programs)."""

    def __init__(self, cave=0x10000, cave_size=0x2000):
        super().__init__()
        self.cave, self.cave_size = cave, cave_size
        extended = bytearray(cave_size + cave - self.base)
        extended[:len(self.data)] = self.data
        self.data = extended
        self.allocations = {}
        self.allocation_protections = {}
        self.releases = []
        self._next = cave

    @property
    def identity(self):
        return self.pid, self.creation_time

    def module(self, name):
        if name.casefold() != PROCESS:
            raise OSError("Unknown module")
        return self.base, len(self.data)

    def _range(self, address, size):
        if not self.base <= address or address + size > self.base + len(self.data):
            raise ValueError("outside owned fixture memory")

    def is_executable(self, address, size):
        return False

    def allocate(self, size, near=None):
        base = self._next
        self._next += (size + 7) & ~7
        self.allocations[base] = size
        return base

    def allocation_size(self, address):
        return self.allocations[address]

    def protect_allocation(self, address, executable=True, writable=False):
        self.allocation_protections[address] = \
            (0x40 if writable else 0x20) if executable else 0x04

    def _query(self, address):
        for base, size in self.allocations.items():
            if base <= address < base + size:
                return SimpleNamespace(BaseAddress=base, AllocationBase=base,
                                       RegionSize=size, State=0x1000,
                                       Protect=self.allocation_protections.get(base, 0x04))
        raise ValueError("unmapped allocation range")

    def release(self, address):
        self.releases.append(address)


class Sc2AttachChainTests(unittest.TestCase):
    """The SC2 activate chain: one-shot attach record -> AOB provider ->
    staged pointer value, on owned fake memory with the real Lua host."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.memory = Sc2ChainMemory()
        base = self.memory.base
        # Pointer qword at the defined symbol address 0x1020 -> points to
        # 0x1050; the chased value lives at 0x1050 + 0x80 = 0x10D0.
        self.memory.data[0x20:0x28] = struct.pack("<Q", base + 0x50)
        self.memory.data[0xD0:0xD4] = struct.pack("<I", 0x12345678)
        # Two pattern occurrences: lowest address wins (WP-55).
        self.memory.data[0x40:0x49] = PATTERN   # match 1 -> patched
        self.memory.data[0x80:0x89] = PATTERN   # match 2 -> untouched
        self.engine = None
        self.engines = []

    def tearDown(self):
        for engine in self.engines:
            if not engine.closed:
                engine.close()

    def start_engine(self, plan):
        engine = TrainerEngine(plan, state_dir=self.root / "state",
                               process_lock_dir=self.root / "shared",
                               memory_factory=lambda name: self.memory,
                               hook_coordinator=Coordinator())
        self.engine = engine
        self.engines.append(engine)
        engine.poll()
        self.assertTrue(engine.connected, engine.status)
        return engine

    def test_attach_chain_activates_staged_value_and_reverts(self):
        body = (script_record(100, ATTACH_SCRIPT,
                              "1. Activate - attach process")
                + script_record(200, PROVIDER_SCRIPT,
                                "3. Activate - enable pointers")
                + value_record(31, "synthPtr32", extra=VALUE_EXTRA))
        plan = compile_table(write_table(self.root, body), PROCESS)
        validate_plan(plan)
        validate_runtime_plan(plan)
        e = {entry["id"]: entry for entry in plan["entries"]}
        self.assertEqual(plan["counts"],
                         {"total": 3, "supported": 3, "actionable": 3,
                          "blocked": 0, "headings": 0})
        # One-shot attach record: pure Lua, empty phases, no symbols.
        self.assertTrue(e[100]["supported"], e[100]["reason"])
        self.assertTrue(e[100]["one_shot"])
        self.assertEqual(e[100]["enable"], [])
        self.assertEqual(e[100]["disable"], [])
        self.assertEqual(e[100]["provides"], [])
        # Provider registers both symbols; the value stages on it.
        self.assertEqual({n.casefold() for n in e[200]["provides"]},
                         {"synthtal32", "synthptr32"})
        self.assertEqual(e[31]["dependency_ids"], [200])
        self.assertEqual(e[31]["staged"]["provider_ids"], [200])

        engine = self.start_engine(plan)

        # Step 1: the attach record activates cleanly - OpenProcess runs as
        # the WP-56 identity no-op (the trainer already attached), not a
        # refusal.
        engine.toggle(100, True)
        self.assertIn(100, engine.applied)
        self.assertIsNotNone(engine.lua_activations.get(100))

        # The staged value stays locked while the provider is pending.
        with self.assertRaisesRegex(NativeRuntimeError,
                                    "requires active provider"):
            engine.read_value(31)

        # Step 2: provider activation - the multi-match scan resolves to
        # the lowest address (WP-55); the patch lands there, the second
        # occurrence stays untouched, both symbols are registered.
        engine.toggle(200, True)
        base = self.memory.base
        self.assertEqual(engine.symbols.get("synthtal32"), base + 0x40)
        self.assertEqual(engine.symbols.get("synthptr32"), 0x1020)
        first = self.memory.read(base + 0x40, 6)
        self.assertNotEqual(first, PATTERN[:6])
        self.assertEqual(first[0], 0xE9)  # rel32 jmp into the allocation
        self.assertEqual(self.memory.read(base + 0x80, len(PATTERN)), PATTERN)

        # Step 3: the staged value now resolves symbol + pointer offset.
        self.assertEqual(engine.read_value(31), "305419896")

        # Provider OFF: patch restored byte-exact, symbols released, the
        # staged value is locked again.
        engine.toggle(200, False)
        self.assertEqual(self.memory.read(base + 0x40, 6), PATTERN[:6])
        self.assertNotIn("synthtal32", engine.symbols)
        self.assertNotIn("synthptr32", engine.symbols)
        with self.assertRaisesRegex(NativeRuntimeError,
                                    "requires active provider"):
            engine.read_value(31)

        # One-shot OFF: zero backend operations, the wish is cleared only.
        engine.toggle(100, False)
        self.assertNotIn(100, engine.one_shot.saved_wish_ids())
        self.assertTrue(engine.one_shot.query(100)["effect_persists"])

    def test_open_process_mismatch_is_named_refusal(self):
        # A record naming a different target than the attached process must
        # not activate: the WP-56 stub refuses with the named reason.
        memory = Sc2ChainMemory()
        self.memory = memory
        body = script_record(
            100,
            "[ENABLE]\n{$lua}\nOpenProcess(\"other.exe\")\n{$asm}\n[DISABLE]\n",
            "1. Attach wrong process")
        plan = compile_table(write_table(self.root, body), PROCESS)
        engine = self.start_engine(plan)
        with self.assertRaisesRegex(
                NativeRuntimeError,
                "openProcess target does not match the attached process: other.exe"):
            engine.toggle(100, True)
        self.assertNotIn(100, engine.applied)
        self.assertFalse(engine.blocked)


if __name__ == "__main__":
    unittest.main()
