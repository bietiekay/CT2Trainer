"""Lane A (shape 1): dynamic Lua symbol registration via a returned define().

A record's ENABLE ``{$lua}`` section scans the target and *returns* a
``define(<ident>, <expr>)`` string, which CE splices into the record's AA
programs as an AA ``define`` directive at activation (CE contract: the
returned Lua text is spliced into the AA program as AA text).  The record
therefore self-satisfies its references to the defined symbol (a local AA
define, never a cross-record provider), and its registered symbols become
staged providers for dependent rows.  Leading shape: the Witcher 3
"Item Pointers" record, whose Lua returns ``define(str_base, ...)``.

Plan level (synthetic fixture, module ct2synth100.exe):
- the record is supported; the defined name is removed from ``requires``
  and recorded in the deterministic ``lua_define_symbols`` marker;
- the Lua-registered symbol is the provider; the dependent row is
  supported and staged on the record;
- without the returned define the record stays blocked (the defined name
  has no provider) - proving the shape-1 detection is what unblocks it;
- both plan validators reject forged/tampered ``lua_define_symbols``
  metadata; a define that is not returned is not adopted, and an
  over-bound returned-define set is unproven (fail-closed, never
  truncated).

Engine level (fake memory, real Lua host):
- activation runs the record Lua against the fake target;
  ``AOBScanModuleUnique`` answers the unique module-relative address;
- the returned define is injected into both phase programs, the symbol
  registers, and the patch is byte-exact at the runtime-derived address;
- the dependent row resolves byte-exact; disable restores the original
  bytes and releases the owned symbol; a scan miss fails closed with the
  named refusal and no target writes.
"""
from copy import deepcopy
import tempfile
import unittest
from pathlib import Path

from test_native_compiler import script_record, value_record
from test_native_engine import FakeMemory
from test_native_engine_code import Coordinator
from ct2trainer.native.compiler import (NativeCompileError, compile_table,
                                         validate_plan)
from ct2trainer.native.engine import (TrainerEngine, NativeRuntimeError,
                                      validate_plan as validate_runtime_plan)


PROCESS = "ct2synth100.exe"
SCAN_PATTERN = "48 8B 05 11 22 33 44"

# The ENABLE Lua scans the target, registers ``dep_sym`` at the
# runtime-derived write address (provider for dependent rows, released by
# the record's own disable Lua) and returns the define ``base_sym`` at
# res+16.  The AA uses the EXPRESSION position ``base_sym+8`` (= res+24 =
# dep_sym) - never a bare ``base_sym:`` label, which would make the define
# program-owned and bypass the shape-1 detection.  The DISABLE Lua
# unregisters the symbol, re-scans and returns the same define so the
# DISABLE AA can restore at the same runtime-derived address.  The record's
# own AA never references the registered symbol (faithful to the real
# record: the define is the write address, the registered symbol serves
# the dependent rows), so there is no self-edge.
SCAN_HEAD = (
    'local res = AOBScanModuleUnique("ct2synth100.exe", "'
    + SCAN_PATTERN + '")\n'
    'if res == nil then return "AOB Error" end\n')

# The write uses a complete valid instruction sequence (four NOPs): the
# linker classifies a runtime-address entry without an owned-data proof as
# executable, so the staged bytes must satisfy the strict
# complete-instruction / control-flow contract exactly like a real code
# patch.  90 90 90 90 is the bounded byte-exact effect.
DEFINE_RECORD = (
    "[ENABLE]\n{$lua}\n" + SCAN_HEAD +
    'registerSymbol("dep_sym", res + 24)\n'
    'return string.format("define(base_sym, %X)", res + 16)\n'
    "{$asm}\n"
    "assert(base_sym+8, 00 00 00 00)\n"
    "base_sym+8:\n"
    "db 90 90 90 90\n"
    "[DISABLE]\n{$lua}\n"
    'unregisterSymbol("dep_sym")\n' + SCAN_HEAD +
    'return string.format("define(base_sym, %X)", res + 16)\n'
    "{$asm}\n"
    "base_sym+8:\n"
    "db 00 00 00 00\n")

# The same record minus the returned define: the AA still references
# base_sym (via base_sym+8), which now has no provider, so the record
# stays blocked.
NO_DEFINE_RECORD = (
    "[ENABLE]\n{$lua}\n" + SCAN_HEAD +
    "return nil\n"
    "{$asm}\n"
    "assert(base_sym+8, 00 00 00 00)\n"
    "base_sym+8:\n"
    "db 01 02 03 04\n"
    "[DISABLE]\n"
    "assert(base_sym+8, 01 02 03 04)\n"
    "base_sym+8:\n"
    "db 00 00 00 00\n")


def write_table(directory: Path, body: str) -> Path:
    path = Path(directory) / "define100.ct"
    path.write_text('<CheatTable CheatEngineTableVersion="52"><CheatEntries>'
                    + body + '</CheatEntries></CheatTable>',
                    encoding="utf-8")
    return path


def by_id(plan: dict) -> dict:
    return {entry["id"]: entry for entry in plan["entries"]}


class DefineMemory(FakeMemory):
    """FakeMemory with the unique scan target and the runtime patch site."""

    def __init__(self):
        super().__init__()
        # Unique scan target at offset 0x80 (abs base+0x80);
        # AOBScanModuleUnique answers base+0x80, so the define is
        # base+0x80+24 = base+0x98 (the patch site, zero-filled).
        self.data[0x80:0x87] = bytes.fromhex(SCAN_PATTERN.replace(" ", ""))
        self.data[0x98:0x9C] = b"\x00\x00\x00\x00"

    @property
    def identity(self):
        return self.pid, self.creation_time

    def module(self, name):
        if name.casefold() == PROCESS:
            return self.base, len(self.data)
        raise OSError("Unknown module")

    def is_executable(self, address, size):
        return False

    def _range(self, address, size):
        if not self.base <= address or address + size > self.base + len(self.data):
            raise ValueError("outside owned fixture memory")

    def scan_matches(self, pattern, start=None, end=None, **options):
        tokens = pattern.replace("*", "?").split()
        start = self.base if start is None else start
        end = self.base + len(self.data) if end is None else end
        matches = []
        for offset in range(len(self.data) - len(tokens) + 1):
            address = self.base + offset
            if not start <= address <= end:
                continue
            if all(token == "?" or self.data[offset + i] == int(token, 16)
                   for i, token in enumerate(tokens)):
                matches.append(address)
        return matches


class DefineProviderPlanTests(unittest.TestCase):
    """Plan level: the returned define self-satisfies and stages dependents."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_define_record_supported_and_dependent_staged(self):
        plan = compile_table(
            write_table(self.root, script_record(10, DEFINE_RECORD,
                                                 "define provider")
                        + value_record(20, "dep_sym")),
            PROCESS)
        e = by_id(plan)
        # The record is supported: the define (base_sym) is self-satisfied,
        # so its reference carries no external requirement.
        self.assertTrue(e[10]["supported"], e[10]["reason"])
        self.assertEqual(e[10]["lua_program"]["lua_define_symbols"],
                         ["base_sym"])
        self.assertNotIn("base_sym",
                         [name.casefold() for name in e[10]["requires"]])
        # The Lua-registered symbol is the provider; the dependent row is
        # supported and staged on the record.
        self.assertIn("dep_sym", e[10]["provides"])
        self.assertTrue(e[20]["supported"], e[20]["reason"])
        self.assertEqual(e[20]["dependency_ids"], [10])
        self.assertEqual(e[20]["staged"]["provider_ids"], [10])
        validate_plan(plan)
        validate_runtime_plan(plan)

    def test_without_returned_define_record_stays_blocked(self):
        plan = compile_table(
            write_table(self.root, script_record(10, NO_DEFINE_RECORD,
                                                 "no define")),
            PROCESS)
        e = by_id(plan)
        self.assertFalse(e[10]["supported"])
        self.assertIn("base_sym", e[10]["reason"])
        self.assertNotIn("base_sym",
                         (e[10].get("lua_program") or {})
                         .get("lua_define_symbols") or [])

    def test_forged_define_symbols_refused_by_both_gates(self):
        plan = compile_table(
            write_table(self.root, script_record(10, DEFINE_RECORD,
                                                 "define provider")
                        + value_record(20, "dep_sym")),
            PROCESS)
        program = plan["entries"][0]["lua_program"]
        for name, forge in (
                ("forged extra define symbol",
                 lambda p: p["entries"][0]["lua_program"].__setitem__(
                     "lua_define_symbols",
                     p["entries"][0]["lua_program"]["lua_define_symbols"]
                     + ["ForgedSym"])),
                ("forged emptied define symbols",
                 lambda p: p["entries"][0]["lua_program"].__setitem__(
                     "lua_define_symbols", [])),
        ):
            with self.subTest(name=name):
                forged = deepcopy(plan)
                forge(forged)
                with self.assertRaisesRegex(
                        NativeCompileError, "does not match its source"):
                    validate_plan(forged)
                with self.assertRaisesRegex(
                        NativeRuntimeError, "does not match its source"):
                    validate_runtime_plan(forged)
        self.assertEqual(program["lua_define_symbols"], ["base_sym"])

    def test_non_returned_define_not_adopted(self):
        # A define that only appears in a non-returned string is not
        # adopted: the record references base_sym with no provider and
        # stays blocked.
        record = (
            "[ENABLE]\n{$lua}\n" + SCAN_HEAD +
            'local junk = string.format("define(base_sym, %X)", res)\n'
            "return nil\n"
            "{$asm}\n"
            "assert(base_sym+8, 00)\n"
            "base_sym+8:\n"
            "db 01\n"
            "[DISABLE]\n"
            "assert(base_sym+8, 01)\n"
            "base_sym+8:\n"
            "db 00\n")
        plan = compile_table(
            write_table(self.root, script_record(10, record,
                                                 "non-returned define")),
            PROCESS)
        e = by_id(plan)
        self.assertFalse(e[10]["supported"])
        self.assertNotIn("base_sym",
                         (e[10].get("lua_program") or {})
                         .get("lua_define_symbols") or [])

    def test_over_bound_returned_defines_stay_unproven(self):
        # More than MAX_PROVIDERS distinct returned defines are unproven
        # (fail-closed, never truncated): none is adopted, so sym0 keeps
        # the named missing-provider block.
        body = "".join(
            'return string.format("define(sym%d, %X)", res)\n' % (i, 0)
            for i in range(65))
        record = (
            "[ENABLE]\n{$lua}\n" + SCAN_HEAD + body +
            "{$asm}\n"
            "assert(sym0+8, 00)\n"
            "sym0+8:\n"
            "db 01\n"
            "[DISABLE]\n"
            "assert(sym0+8, 01)\n"
            "sym0+8:\n"
            "db 00\n")
        plan = compile_table(
            write_table(self.root, script_record(10, record,
                                                 "over-bound define")),
            PROCESS)
        e = by_id(plan)
        self.assertFalse(e[10]["supported"])
        self.assertNotIn("sym0",
                         (e[10].get("lua_program") or {})
                         .get("lua_define_symbols") or [])


class DefineProviderEngineTests(unittest.TestCase):
    """Engine level: the define is injected and the effect is byte-exact."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.engine = None

    def tearDown(self):
        if self.engine is not None and not self.engine.closed:
            self.engine.close()

    def _start(self, memory, plan):
        self.engine = TrainerEngine(
            plan, state_dir=self.root / "state",
            process_lock_dir=self.root / "shared",
            memory_factory=lambda name: memory,
            hook_coordinator=Coordinator())
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)
        return self.engine

    def test_activation_injects_define_registers_symbol_and_patches(
            self):
        memory = DefineMemory()
        body = (script_record(10, DEFINE_RECORD, "define provider")
                + value_record(20, "dep_sym"))
        plan = compile_table(write_table(self.root, body), PROCESS)
        engine = self._start(memory, plan)
        base = memory.base
        # The define is base+0x90; the patch is byte-exact at
        # base_sym+8 = base+0x98 (four NOPs).
        self.assertNotIn("base_sym", engine.symbols)
        engine.toggle(10, True)
        self.assertIn(10, engine.applied)
        # The Lua-registered symbol is live at the runtime-derived address.
        self.assertEqual(engine.symbols.get("dep_sym"), base + 0x98)
        self.assertEqual(memory.read(base + 0x98, 4), b"\x90\x90\x90\x90")
        # The dependent row resolves byte-exact (dword 0x90909090).
        self.assertEqual(engine.read_value(20), str(0x90909090))
        # Disable restores the original bytes and releases the owned
        # symbol (toggle returns the resulting state; failures raise).
        self.assertFalse(engine.toggle(10, False))
        self.assertEqual(memory.read(base + 0x98, 4), bytes(4))
        self.assertNotIn("dep_sym", engine.symbols)
        self.assertNotIn(10, engine.applied)

    def test_scan_miss_fails_closed_with_named_refusal(self):
        # A target without the unique pattern: AOBScanModuleUnique answers
        # nil, the Lua returns the "AOB Error" text, and the record fails
        # to enable (no target memory is written).
        memory = DefineMemory()
        memory.data[0x80:0x87] = b"\x00\x00\x00\x00\x00\x00\x00"
        body = (script_record(10, DEFINE_RECORD, "define provider")
                + value_record(20, "dep_sym"))
        plan = compile_table(write_table(self.root, body), PROCESS)
        engine = self._start(memory, plan)
        with self.assertRaises(NativeRuntimeError):
            engine.toggle(10, True)
        self.assertNotIn(10, engine.applied)
        self.assertNotIn("dep_sym", engine.symbols)
        self.assertEqual(memory.read(memory.base + 0x98, 4), bytes(4))


if __name__ == "__main__":
    unittest.main()

