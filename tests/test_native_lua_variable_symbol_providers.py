"""0.49 (shape 3): dynamic Lua symbol registration through a variable
that ranges over a flat literal string array.

The record's ``{$lua}`` walks a runtime table and registers each entry
under its name through a local single-index binding, the Fallout4
"Player Editor" record shape::

    local pointers = {"str","per","end","cha","int","agi","luck","xp"}
    for i = addr, size, 8 do
      local id = readInteger(i)
      local ptr = pointers[id]
      if ptr ~= nil then
        unregisterSymbol(ptr)
        registerSymbol(ptr, i + 4, true)
      end
    end

The loop index varies, so the variable ranges over every element of the
array; the bounded static derivation (flat string arrays only, string
constants only, the exact ``local var = ARRAY[i]`` single-index binding
with a variable index, one binding per variable, one array definition
per name, same part) makes the array's string constants the record's
staged provides.  Double-index bindings (``local name = X[i][k]``, the
shape-2 indirect form), row tables, numeric/identifier cells, constant
indices, unbound or re-bound variables and non-local sources stay
unproven.  An enable-phase ``unregisterSymbol(var)`` next to the
registration is the re-entrance guard, not a deactivation release:
release evidence is disable-phase only (one-shot records adopt on the
registration half alone, the owner scope releases at detach).

Plan level (synthetic fixture, module ct2synth100.exe):
- the FO4-shape one-shot record is supported; the derived names are the
  deterministic casefold-sorted ``provides`` and the dependent rows are
  staged on it (the re-entrance guard does not cancel the adoption);
- the strict-pair (non-one-shot) variant adopts only with the
  disable-phase release half; every out-of-bound shape stays unproven
  (dependents keep the named missing-provider block); both plan
  validators reject forged ``provides`` metadata.

Engine level (fake memory, real Lua host):
- activation runs the flat-array registration against the fake target
  through the hosted surface (AOBScanModuleUnique, the disassembler
  operand derivation);
- the derived symbols register at the disassembler-derived absolute
  operand address and the dependent rows read byte-exact; disable
  releases them; a scan miss fails closed with the named
  "did not confirm its declared symbol exports" refusal and no target
  writes.

Divergence from the real record, documented (an engine/lua_activation
ownership decision outside this lane's file ownership, same pin as the
shape-2 engine fixture): the real lead-case loop is re-entrancy-safe
with a pre-enable ``unregisterSymbol(var)`` before
``registerSymbol(var, ...)``; the record-scope ownership contract
refuses a release of a symbol this activation does not own (named
refusal, first enable), so the engine fixture registers directly — the
disable path carries the release, which is owned at that point (CE 7.5
reference: DeleteUserdefinedSymbol is a silent no-op on an absent
symbol).
"""
from copy import deepcopy
import struct
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

# The FO4 "Player Editor" lead-case shape: one {$lua} block, a flat
# literal string array, the single-index binding with a variable index,
# and the register/unregister calls on the bare variable in the same
# loop body (the re-entrance guard).  One-shot: no [DISABLE] content, so
# the owner scope releases at detach and the registration half alone
# adopts.  The registerSymbol address is a literal here — the static
# derivation is name-based only.
FLAT_ARRAY_RECORD = (
    "{$lua}\n"
    "[ENABLE]\n"
    "local pointers = {'str','per','end','cha','int','agi','luck','xp'}\n"
    "local base = 0x1000\n"
    "for i = 1, #pointers do\n"
    "  local id = i\n"
    "  local ptr = pointers[id]\n"
    "  if ptr ~= nil then\n"
    "    unregisterSymbol(ptr)\n"
    "    registerSymbol(ptr, base + (i - 1) * 8)\n"
    "  end\n"
    "end\n")

# The strict-pair (non-one-shot) shape: the release half is the same
# variable derivation in the [DISABLE] part.
FLAT_ARRAY_PAIRED_RECORD = (
    "{$lua}\n"
    "[ENABLE]\n"
    "local pointers = {'alphaSym','betaSym'}\n"
    "local base = 0x2000\n"
    "for i = 1, #pointers do\n"
    "  local id = i\n"
    "  local ptr = pointers[id]\n"
    "  if ptr ~= nil then\n"
    "    registerSymbol(ptr, base + (i - 1) * 8)\n"
    "  end\n"
    "end\n"
    "[DISABLE]\n"
    "local releases = {'alphaSym','betaSym'}\n"
    "for i = 1, #releases do\n"
    "  local id = i\n"
    "  local ptr = releases[id]\n"
    "  if ptr ~= nil then\n"
    "    unregisterSymbol(ptr)\n"
    "  end\n"
    "end\n")

# The shape-2 indirect form re-pinned against this lane: the name
# reaches registerSymbol through a local double-index binding — the
# statement does not end after the first bracket and the source is a
# table of row tables, so shape 3 (and shape 2) stay unproven.
DOUBLE_INDEX_RECORD = (
    "{$lua}\n"
    "[ENABLE]\n"
    "local rows = {{'p1','aobOne'},{'p2','aobTwo'}}\n"
    "for i = 1, #rows do\n"
    "  local name = rows[i][2]\n"
    "  unregisterSymbol(name)\n"
    "  registerSymbol(name, 0x3000 + i * 8)\n"
    "end\n")

# The bound variable indexes a table of row tables, not a flat string
# array — the source is not flat, unproven.
ROW_TABLE_RECORD = (
    "{$lua}\n"
    "[ENABLE]\n"
    "local rows = {{'rowOne'},{'rowTwo'}}\n"
    "for i = 1, #rows do\n"
    "  local cell = rows[i]\n"
    "  registerSymbol(cell, 0x4000 + i * 8)\n"
    "end\n")

# A flat array carrying a numeric cell — not all string constants,
# unproven.
NUMERIC_CELL_RECORD = (
    "{$lua}\n"
    "[ENABLE]\n"
    "local names = {'alphaSym', 5}\n"
    "for i = 1, #names do\n"
    "  local ptr = names[i]\n"
    "  registerSymbol(ptr, 0x5000 + i * 8)\n"
    "end\n")

# A flat array carrying an identifier cell — not a string constant,
# unproven.
IDENT_CELL_RECORD = (
    "{$lua}\n"
    "[ENABLE]\n"
    "local other = 'gammaSym'\n"
    "local names = {'alphaSym', other}\n"
    "for i = 1, #names do\n"
    "  local ptr = names[i]\n"
    "  registerSymbol(ptr, 0x5100 + i * 8)\n"
    "end\n")

# The variable is bound twice (to two different arrays) — ambiguous,
# unproven for both.
REBOUND_VAR_RECORD = (
    "{$lua}\n"
    "[ENABLE]\n"
    "local arr1 = {'alphaSym','betaSym'}\n"
    "local arr2 = {'gammaSym','deltaSym'}\n"
    "for i = 1, 2 do\n"
    "  local ptr = arr1[i]\n"
    "  registerSymbol(ptr, 0x6000)\n"
    "  local ptr = arr2[i]\n"
    "  registerSymbol(ptr, 0x7000)\n"
    "end\n")

# The bound array is never defined as a local flat literal in the part
# — unbound source, unproven.
UNBOUND_ARRAY_RECORD = (
    "{$lua}\n"
    "[ENABLE]\n"
    "for i = 1, 2 do\n"
    "  local ptr = mystery[i]\n"
    "  registerSymbol(ptr, 0x8000 + i * 8)\n"
    "end\n")

# The binding is a plain assignment, not a ``local`` — the bounded
# derivation needs the local binding, unproven.
NON_LOCAL_RECORD = (
    "{$lua}\n"
    "[ENABLE]\n"
    "local names = {'alphaSym','betaSym'}\n"
    "for i = 1, #names do\n"
    "  ptr = names[i]\n"
    "  registerSymbol(ptr, 0x9000 + i * 8)\n"
    "end\n")

# A constant index selects one element — the bounded derivation is
# variable-index only (the full array would over-prove), unproven.
CONST_INDEX_RECORD = (
    "{$lua}\n"
    "[ENABLE]\n"
    "local names = {'alphaSym','betaSym'}\n"
    "local ptr = names[1]\n"
    "registerSymbol(ptr, 0xA000)\n")

# The first argument is a call, not an identifier — the variable form
# needs the bare name, unproven.
CALL_ARG_RECORD = (
    "{$lua}\n"
    "function getFirst()\n"
    "  return 'callSym'\n"
    "end\n"
    "[ENABLE]\n"
    "registerSymbol(getFirst(), 0xB000)\n")


def over_bound_record() -> str:
    items = ",".join("'%s'" % ("sym%02d" % i) for i in range(65))
    return (
        "{$lua}\n"
        "[ENABLE]\n"
        "local names = {" + items + "}\n"
        "for i = 1, #names do\n"
        "  local ptr = names[i]\n"
        "  registerSymbol(ptr, 0xC000 + i * 8)\n"
        "end\n")


def write_table(directory: Path, body: str, name: str = "flatarray100.ct") -> Path:
    path = Path(directory) / name
    path.write_text(
        '<CheatTable CheatEngineTableVersion="52"><CheatEntries>'
        + body + '</CheatEntries></CheatTable>',
        encoding="utf-8")
    return path


def by_id(plan: dict) -> dict:
    return {entry["id"]: entry for entry in plan["entries"]}


class FlatArrayPlanTests(unittest.TestCase):
    """Plan level: the flat-array variable derives the staged providers."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_flat_array_record_supported_and_dependents_staged(self):
        # All eight stat children of the lead case, staged on the record.
        body = script_record(10, FLAT_ARRAY_RECORD, "flat array provider")
        for entry_id, name in enumerate(
                ("str", "per", "end", "cha", "int", "agi", "luck", "xp"), 20):
            body += value_record(entry_id, name)
        plan = compile_table(write_table(self.root, body), PROCESS)
        e = by_id(plan)
        self.assertTrue(e[10]["supported"], e[10]["reason"])
        # The flat array's string constants, casefold-sorted and
        # byte-stable across recompiles.  The enable-phase
        # unregisterSymbol(ptr) re-entrance guard did not cancel the
        # one-shot adoption (release evidence is disable-phase only).
        self.assertTrue(e[10]["lua_program"]["one_shot"])
        self.assertEqual(e[10]["provides"],
                         ["agi", "cha", "end", "int", "luck", "per", "str",
                          "xp"])
        self.assertEqual(e[10]["lua_program"]["provides"],
                         ["agi", "cha", "end", "int", "luck", "per", "str",
                          "xp"])
        plan_again = compile_table(
            write_table(self.root, body, "flatarray_again.ct"), PROCESS)
        e_again = by_id(plan_again)
        self.assertEqual(e_again[10]["provides"], e[10]["provides"])
        self.assertEqual(e_again[10]["lua_program"]["source_sha256"],
                         e[10]["lua_program"]["source_sha256"])
        # The dependent rows resolve through the staged provider.
        for row in range(20, 28):
            self.assertTrue(e[row]["supported"], e[row]["reason"])
            self.assertEqual(e[row]["dependency_ids"], [10])
            self.assertEqual(e[row]["staged"]["provider_ids"], [10])
        validate_plan(plan)
        validate_runtime_plan(plan)
        # The CE first-letter spellings are the same call (WP-56): the
        # derivation is case-insensitive, matching the house literal-string
        # evidence regexes.
        spelled = (FLAT_ARRAY_RECORD.replace("registerSymbol",
                                             "RegisterSymbol")
                              .replace("unregisterSymbol",
                                       "UnregisterSymbol"))
        plan_spelled = compile_table(
            write_table(self.root,
                        script_record(10, spelled, "flat array spelled")
                        + value_record(20, "str")),
            PROCESS)
        e_spelled = by_id(plan_spelled)
        self.assertTrue(e_spelled[10]["supported"], e_spelled[10]["reason"])
        self.assertEqual(e_spelled[10]["provides"],
                         ["agi", "cha", "end", "int", "luck", "per", "str",
                          "xp"])
        self.assertTrue(e_spelled[20]["supported"], e_spelled[20]["reason"])

    def test_strict_pair_flat_array_adopted(self):
        plan = compile_table(
            write_table(self.root,
                        script_record(10, FLAT_ARRAY_PAIRED_RECORD,
                                      "paired flat array")
                        + value_record(20, "alphaSym")
                        + value_record(30, "betaSym")),
            PROCESS)
        e = by_id(plan)
        self.assertTrue(e[10]["supported"], e[10]["reason"])
        self.assertFalse(e[10]["lua_program"]["one_shot"])
        self.assertEqual(e[10]["provides"], ["alphaSym", "betaSym"])
        for row in (20, 30):
            self.assertTrue(e[row]["supported"], e[row]["reason"])
            self.assertEqual(e[row]["dependency_ids"], [10])
            self.assertEqual(e[row]["staged"]["provider_ids"], [10])
        validate_plan(plan)
        validate_runtime_plan(plan)

    def _assert_dependents_blocked(self, record, names,
                                   label="flat array"):
        body = script_record(10, record, label)
        for offset, name in enumerate(names):
            body += value_record(20 + offset, name)
        plan = compile_table(write_table(self.root, body), PROCESS)
        e = by_id(plan)
        # The record itself stays supported (pure Lua, no requires); the
        # unproven derivation simply leaves the provider claim absent.
        self.assertTrue(e[10]["supported"], e[10]["reason"])
        for index, name in enumerate(names):
            row = e[20 + index]
            self.assertNotIn(name, e[10]["provides"])
            self.assertNotIn(
                name.casefold(),
                [item.casefold() for item in e[10]["provides"]])
            self.assertFalse(row["supported"])
            self.assertIn(name, row["reason"])
        return plan

    def test_double_index_binding_not_derived(self):
        # The shape-2 indirect form re-pinned: the name reaches
        # registerSymbol through a double-index local — the statement
        # does not end after the first bracket, unproven here too.
        self._assert_dependents_blocked(DOUBLE_INDEX_RECORD, ["aobOne"],
                                        "double index")

    def test_row_table_array_not_derived(self):
        self._assert_dependents_blocked(ROW_TABLE_RECORD, ["rowOne"],
                                        "row table")

    def test_numeric_cell_not_derived(self):
        self._assert_dependents_blocked(NUMERIC_CELL_RECORD, ["alphaSym"],
                                        "numeric cell")

    def test_ident_cell_not_derived(self):
        self._assert_dependents_blocked(IDENT_CELL_RECORD, ["alphaSym"],
                                        "ident cell")

    def test_rebound_variable_not_derived(self):
        self._assert_dependents_blocked(REBOUND_VAR_RECORD,
                                        ["alphaSym", "gammaSym"],
                                        "rebound variable")

    def test_unbound_array_not_derived(self):
        self._assert_dependents_blocked(UNBOUND_ARRAY_RECORD, ["alphaSym"],
                                        "unbound array")

    def test_non_local_binding_not_derived(self):
        self._assert_dependents_blocked(NON_LOCAL_RECORD, ["alphaSym"],
                                        "non-local binding")

    def test_constant_index_not_derived(self):
        self._assert_dependents_blocked(CONST_INDEX_RECORD, ["alphaSym"],
                                        "constant index")

    def test_call_argument_not_derived(self):
        self._assert_dependents_blocked(CALL_ARG_RECORD, ["callSym"],
                                        "call argument")

    def test_over_bound_flat_array_stays_unproven(self):
        # More than MAX_PROVIDERS (64) derived names: unproven, never
        # truncated — the dependent keeps the named block.
        self._assert_dependents_blocked(over_bound_record(), ["sym00"],
                                        "over-bound flat array")

    def test_forged_provides_refused_by_both_gates(self):
        plan = compile_table(
            write_table(self.root,
                        script_record(10, FLAT_ARRAY_RECORD,
                                      "flat array provider")
                        + value_record(20, "str")),
            PROCESS)
        for name, forge in (
                ("forged extra provides entry",
                 lambda p: p["entries"][0]["lua_program"].__setitem__(
                     "provides",
                     p["entries"][0]["lua_program"]["provides"]
                     + ["ForgedSym"])),
                ("forged missing provides entry",
                 lambda p: p["entries"][0]["lua_program"].__setitem__(
                     "provides",
                     [item for item in
                      p["entries"][0]["lua_program"]["provides"]
                      if item != "str"])),
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
        self.assertEqual(plan["entries"][0]["lua_program"]["provides"],
                         ["agi", "cha", "end", "int", "luck", "per", "str",
                          "xp"])


# The flat-array runtime record: the enable registers the derived names
# at the absolute memory operand of the instruction at scan+16
# (disassembler-derived, exactly like getAddressFromOpcode) through the
# variable binding; the disable releases them through the same
# derivation.  Divergence from the real lead case documented in the
# module docstring: the engine fixture registers directly (the record-
# scope ownership contract refuses a pre-enable release of a symbol the
# activation does not own; the disable path carries the release).
ENGINE_RECORD = (
    "{$lua}\n"
    "[ENABLE]\n"
    "local names = {'alphaSym','betaSym'}\n"
    "local opAddr = AOBScanModuleUnique('ct2synth100.exe', "
    "'48 8B 05 11 22 33 44')\n"
    "if opAddr == nil then return end\n"
    "local disassembler = createDisassembler()\n"
    "disassembler.disassemble(opAddr + 16)\n"
    "local disTable = disassembler.getLastDisassembleData()\n"
    "local base = disTable.modrmValue\n"
    "if base == nil or base == 0 then return end\n"
    "for i = 1, #names do\n"
    "  local id = i\n"
    "  local ptr = names[id]\n"
    "  if ptr ~= nil then\n"
    "    registerSymbol(ptr, base + (i - 1) * 8)\n"
    "  end\n"
    "end\n"
    "[DISABLE]\n"
    "local names = {'alphaSym','betaSym'}\n"
    "for i = 1, #names do\n"
    "  local id = i\n"
    "  local ptr = names[id]\n"
    "  if ptr ~= nil then\n"
    "    unregisterSymbol(ptr)\n"
    "  end\n"
    "end\n")


class FlatArrayMemory(FakeMemory):
    """FakeMemory with the unique scan target and the disassembler
    operand site.

    The scan target sits at base+0x80 (the pattern); at base+0x90 (scan
    + 16) the instruction ``48 8B 05 00 00 00 00`` (mov rax,[rip+0])
    carries the absolute memory operand base+0x97.  The dependent rows
    live at alphaSym = base+0x97 and betaSym = base+0x9F.
    """

    def __init__(self):
        super().__init__()
        self.data[0x80:0x87] = bytes.fromhex(SCAN_PATTERN.replace(" ", ""))
        self.data[0x90:0x97] = bytes.fromhex("488B0500000000")
        self.data[0x97:0x9B] = struct.pack("<I", 0x11223344)
        self.data[0x9F:0xA3] = struct.pack("<I", 0x55667788)

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


class FlatArrayEngineTests(unittest.TestCase):
    """Engine level: the flat-array registration runs and is byte-exact."""

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

    def _plan(self, body):
        return compile_table(
            write_table(self.root, body, "flat_engine.ct"), PROCESS)

    def test_activation_registers_derived_symbols_and_is_byte_exact(self):
        memory = FlatArrayMemory()
        plan = self._plan(
            script_record(10, ENGINE_RECORD, "flat provider")
            + value_record(20, "alphaSym")
            + value_record(30, "betaSym"))
        engine = self._start(memory, plan)
        base = memory.base
        self.assertNotIn("alphasym", engine.symbols)
        engine.toggle(10, True)
        self.assertIn(10, engine.applied)
        # The derived symbols register at the disassembler-derived
        # operand address (base+0x97) and its successor site.
        self.assertEqual(engine.symbols.get("alphasym"), base + 0x97)
        self.assertEqual(engine.symbols.get("betasym"), base + 0x9F)
        # The dependent rows read byte-exact through the owned symbols.
        self.assertEqual(engine.read_value(20), str(0x11223344))
        self.assertEqual(engine.read_value(30), str(0x55667788))
        # Disable releases the owned symbols (toggle returns the
        # resulting state; failures raise).
        self.assertFalse(engine.toggle(10, False))
        self.assertNotIn("alphasym", engine.symbols)
        self.assertNotIn("betasym", engine.symbols)
        self.assertNotIn(10, engine.applied)

    def test_scan_miss_fails_closed_with_named_refusal(self):
        # A target without the unique pattern: AOBScanModuleUnique
        # answers nil, the registration loop skips, and the activation
        # refuses with the named declared-exports refusal — no symbols,
        # no applied record, no target writes.
        memory = FlatArrayMemory()
        memory.data[0x80:0x87] = b"\x00" * 7
        plan = self._plan(
            script_record(10, ENGINE_RECORD, "flat provider")
            + value_record(20, "alphaSym")
            + value_record(30, "betaSym"))
        engine = self._start(memory, plan)
        with self.assertRaisesRegex(
                NativeRuntimeError,
                "did not confirm its declared symbol exports"):
            engine.toggle(10, True)
        self.assertNotIn(10, engine.applied)
        self.assertNotIn("alphasym", engine.symbols)
        self.assertNotIn("betasym", engine.symbols)
        self.assertEqual(memory.read(memory.base + 0x97, 4),
                         struct.pack("<I", 0x11223344))


if __name__ == "__main__":
    unittest.main()
