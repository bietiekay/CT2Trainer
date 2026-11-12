"""Lane A (shape 2): dynamic Lua symbol registration through a literal
name list.

A record's ``{$lua}`` preamble defines a function returning a literal
table of string tuples and registers its column through an indexed call,
the God of War "Enable" record shape::

    function getNameList()
      return {{'fnPlayer','goPlayer'},{'fnObject','ObjectPtr'}}
    end
    function registerBaseAddresses()
      local nameList = getNameList()
      for i = 1,#nameList do
        unregisterSymbol(nameList[i][2])
        registerSymbol(nameList[i][2], addr)
      end
    end
    ...
    [ENABLE]
    registerBaseAddresses()
    [DISABLE]
    unregisterBaseAddresses()

The bounded static derivation (literal tables only, string constants
only, the exact ``X[i][k]`` indexing with a constant integer column, one
function hop) makes the column's string constants the record's staged
provides.  Indirect names (``local name = X[i][k]``), non-string
columns, unbound sources and over-bound sets stay unproven.

Plan level (synthetic fixture, module ct2synth100.exe):
- the record is supported; the derived names are the deterministic
  casefold-sorted ``provides`` and the dependent rows are staged on it;
- every out-of-bound shape stays unproven (dependents keep the named
  missing-provider block); both plan validators reject forged
  ``provides`` metadata; one-shot records adopt without the unregister
  half (the owner scope releases at detach).

Engine level (fake memory, real Lua host):
- activation runs the GoW-style enable against the fake target and
  exercises the hosted surface (GetLuaEngine show/hide/Component/
  MenuItem5, getUpdateTimer, stringToByteTable, createTableFile stream,
  createDisassembler, getNameFromAddress, AOBScanModuleUnique);
- the derived symbols register at the disassembler-derived absolute
  operand address and the dependent rows read byte-exact; disable
  releases them; a scan miss fails closed with the named
  "did not confirm its declared symbol exports" refusal and no target
  writes.
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

# The GoW lead-case shape: one {$lua} block, preamble functions, the
# literal pair table (column 2 = the symbol name), indexed
# register/unregister calls, and the [ENABLE]/[DISABLE] markers inside
# the same block.  The registerSymbol address is a literal here - the
# static derivation is name-based only.
NAME_LIST_RECORD = (
    "{$lua}\n"
    "function getNameList()\n"
    "  return {{'fnPlayer','goPlayer'},{'fnObject','ObjectPtr'},"
    "{'fnList','ParamList'}}\n"
    "end\n"
    "function registerBaseAddresses()\n"
    "  local nameList = getNameList()\n"
    "  for i = 1,#nameList do\n"
    "    unregisterSymbol(nameList[i][2])\n"
    "    registerSymbol(nameList[i][2], 0x1000 + i * 8)\n"
    "  end\n"
    "end\n"
    "function unregisterBaseAddresses()\n"
    "  local nameList = getNameList()\n"
    "  for i = 1,#nameList do unregisterSymbol(nameList[i][2]) end\n"
    "end\n"
    "if syntaxcheck then return end\n"
    "[ENABLE]\n"
    "registerBaseAddresses()\n"
    "[DISABLE]\n"
    "unregisterBaseAddresses()\n")

# The GoW AOBList loop shape: the name reaches registerSymbol through a
# local, not the indexed call argument - outside the bound, unproven.
INDIRECT_RECORD = (
    "{$lua}\n"
    "function registerAOBs()\n"
    "  local AOBList = {{'p1','aobOne'},{'p2','aobTwo'}}\n"
    "  for i = 1,#AOBList do\n"
    "    local name = AOBList[i][2]\n"
    "    unregisterSymbol(name)\n"
    "    registerSymbol(name, 0x3000 + i * 8)\n"
    "  end\n"
    "end\n"
    "[ENABLE]\n"
    "registerAOBs()\n")

# A pair table whose column 2 is not all string constants (row 2 carries
# a number) - the column stays unproven.
NUMERIC_COLUMN_RECORD = (
    "{$lua}\n"
    "function getNameList()\n"
    "  return {{'fnA','alphaSym'},{'fnB',5}}\n"
    "end\n"
    "function registerAll()\n"
    "  local nameList = getNameList()\n"
    "  for i = 1,#nameList do\n"
    "    unregisterSymbol(nameList[i][2])\n"
    "    registerSymbol(nameList[i][2], 0x4000 + i * 8)\n"
    "  end\n"
    "end\n"
    "[ENABLE]\n"
    "registerAll()\n")

# The indexed source is never bound by ``local X = f()`` in the source -
# the function hop does not resolve, unproven.
UNBOUND_SOURCE_RECORD = (
    "{$lua}\n"
    "function registerAll()\n"
    "  for i = 1,#otherList do\n"
    "    unregisterSymbol(otherList[i][2])\n"
    "    registerSymbol(otherList[i][2], 0x5000 + i * 8)\n"
    "  end\n"
    "end\n"
    "[ENABLE]\n"
    "registerAll()\n")

# One-shot (no [DISABLE]): the owner scope releases at detach, so the
# registration half alone adopts the derived names.
ONE_SHOT_RECORD = (
    "{$lua}\n"
    "function getNameList()\n"
    "  return {{'fnA','alphaPtr'},{'fnB','ZetaPtr'}}\n"
    "end\n"
    "function registerAll()\n"
    "  local nameList = getNameList()\n"
    "  for i = 1,#nameList do\n"
    "    registerSymbol(nameList[i][2], 0x2000 + i * 8)\n"
    "  end\n"
    "end\n"
    "[ENABLE]\n"
    "registerAll()\n")


def over_bound_record() -> str:
    pairs = "".join("{'fn%02d','sym%02d'}" % (i, i) for i in range(65))
    return (
        "{$lua}\n"
        "function getNameList()\n"
        "  return {" + pairs + "}\n"
        "end\n"
        "function registerAll()\n"
        "  local nameList = getNameList()\n"
        "  for i = 1,#nameList do\n"
        "    unregisterSymbol(nameList[i][2])\n"
        "    registerSymbol(nameList[i][2], 0x6000 + i * 8)\n"
        "  end\n"
        "end\n"
        "[ENABLE]\n"
        "registerAll()\n")


def write_table(directory: Path, body: str, name: str = "namelist100.ct") -> Path:
    path = Path(directory) / name
    path.write_text(
        '<CheatTable CheatEngineTableVersion="52"><CheatEntries>'
        + body + '</CheatEntries></CheatTable>',
        encoding="utf-8")
    return path


def by_id(plan: dict) -> dict:
    return {entry["id"]: entry for entry in plan["entries"]}


class NameListPlanTests(unittest.TestCase):
    """Plan level: the literal name list derives the staged providers."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_name_list_record_supported_and_dependents_staged(self):
        plan = compile_table(
            write_table(self.root, script_record(10, NAME_LIST_RECORD,
                                                 "name list provider")
                        + value_record(20, "goPlayer")
                        + value_record(30, "ObjectPtr")),
            PROCESS)
        e = by_id(plan)
        self.assertTrue(e[10]["supported"], e[10]["reason"])
        # The column-2 string constants, casefold-sorted and byte-stable
        # across recompiles.
        self.assertEqual(e[10]["provides"],
                         ["goPlayer", "ObjectPtr", "ParamList"])
        self.assertEqual(e[10]["lua_program"]["provides"],
                         ["goPlayer", "ObjectPtr", "ParamList"])
        plan_again = compile_table(
            write_table(self.root, script_record(10, NAME_LIST_RECORD,
                                                 "name list provider")
                        + value_record(20, "goPlayer")
                        + value_record(30, "ObjectPtr"),
                        "namelist_again.ct"),
            PROCESS)
        e_again = by_id(plan_again)
        self.assertEqual(e_again[10]["provides"], e[10]["provides"])
        self.assertEqual(e_again[10]["lua_program"]["source_sha256"],
                         e[10]["lua_program"]["source_sha256"])
        # The dependent rows resolve through the staged provider.
        for row in (20, 30):
            self.assertTrue(e[row]["supported"], e[row]["reason"])
            self.assertEqual(e[row]["dependency_ids"], [10])
            self.assertEqual(e[row]["staged"]["provider_ids"], [10])
        validate_plan(plan)
        validate_runtime_plan(plan)
        # The CE first-letter spellings are the same call (WP-56): the
        # derivation is case-insensitive, matching the house literal-string
        # evidence regexes.
        spelled = (NAME_LIST_RECORD.replace("registerSymbol",
                                            "RegisterSymbol")
                             .replace("unregisterSymbol",
                                      "UnregisterSymbol"))
        plan_spelled = compile_table(
            write_table(self.root, script_record(10, spelled,
                                                 "name list spelled")
                        + value_record(20, "goPlayer")),
            PROCESS)
        e_spelled = by_id(plan_spelled)
        self.assertTrue(e_spelled[10]["supported"],
                        e_spelled[10]["reason"])
        self.assertEqual(e_spelled[10]["provides"],
                         ["goPlayer", "ObjectPtr", "ParamList"])
        self.assertTrue(e_spelled[20]["supported"],
                        e_spelled[20]["reason"])

    def _assert_dependents_blocked(self, record, names,
                                   label="name list"):
        plan = compile_table(
            write_table(self.root, script_record(10, record, label)
                        + value_record(20, names[0])),
            PROCESS)
        e = by_id(plan)
        # The record itself stays supported (pure Lua, no requires); the
        # unproven derivation simply leaves the provider claim absent.
        self.assertTrue(e[10]["supported"], e[10]["reason"])
        for name in names:
            self.assertNotIn(name, e[10]["provides"])
            self.assertNotIn(
                name.casefold(),
                [item.casefold() for item in e[10]["provides"]])
        self.assertFalse(e[20]["supported"])
        self.assertIn(names[0], e[20]["reason"])
        return plan

    def test_numeric_column_cells_not_derived(self):
        self._assert_dependents_blocked(NUMERIC_COLUMN_RECORD,
                                        ["alphaSym"],
                                        "numeric column")

    def test_indirect_local_name_not_derived(self):
        # The GoW AOBList loop: the name reaches registerSymbol through a
        # local - the bounded derivation is call-argument indexed only.
        self._assert_dependents_blocked(INDIRECT_RECORD, ["aobOne"],
                                        "indirect registration")

    def test_unbound_name_source_not_derived(self):
        self._assert_dependents_blocked(UNBOUND_SOURCE_RECORD, ["sym01"],
                                        "unbound source")

    def test_over_bound_name_list_stays_unproven(self):
        # More than MAX_PROVIDERS (64) derived names: unproven, never
        # truncated - the dependent keeps the named block.
        self._assert_dependents_blocked(over_bound_record(), ["sym00"],
                                        "over-bound name list")

    def test_forged_provides_refused_by_both_gates(self):
        plan = compile_table(
            write_table(self.root, script_record(10, NAME_LIST_RECORD,
                                                 "name list provider")
                        + value_record(20, "goPlayer")),
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
                      if item != "goPlayer"])),
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
                         ["goPlayer", "ObjectPtr", "ParamList"])

    def test_one_shot_name_list_adopted_without_unregister(self):
        plan = compile_table(
            write_table(self.root, script_record(10, ONE_SHOT_RECORD,
                                                 "one-shot name list")
                        + value_record(20, "alphaPtr")),
            PROCESS)
        e = by_id(plan)
        self.assertTrue(e[10]["supported"], e[10]["reason"])
        self.assertTrue(e[10]["lua_program"]["one_shot"])
        # The registration half alone adopts (owner-scope release at
        # detach); the casefold sort keeps alphaPtr before ZetaPtr.
        self.assertEqual(e[10]["provides"], ["alphaPtr", "ZetaPtr"])
        self.assertTrue(e[20]["supported"], e[20]["reason"])
        self.assertEqual(e[20]["dependency_ids"], [10])
        validate_plan(plan)
        validate_runtime_plan(plan)


# The GoW-style runtime record: the preamble registers the derived names
# at the absolute memory operand of the instruction at scan+16
# (disassembler-derived, exactly like getAddressFromOpcode); onEnable
# exercises the hosted CE surface (GetLuaEngine show/Component/hide,
# getUpdateTimer, stringToByteTable, the bounded in-memory
# createTableFile stream, createDisassembler, getNameFromAddress,
# AOBScanModuleUnique).  onDisable releases the owned symbols and slows
# the update timer back to the 1000 ms default.
#
# Divergence from the real record, documented (both are engine/lua_activation
# ownership decisions outside this lane's file ownership, residuals for
# the follow-up engine lane): (1) the real registerBaseAddresses loop is
# re-entrancy-safe with a pre-enable ``unregisterSymbol(X)`` before
# ``registerSymbol(X, ...)``; the record-scope ownership contract refuses
# a release of a symbol this activation does not own (named refusal,
# first enable), so the engine fixture registers directly - the disable
# path carries the release, which is owned at that point (CE 7.5
# reference: DeleteUserdefinedSymbol is a silent no-op on an absent
# symbol).  (2) the real record's ``luaEngine.MenuItem5.doClick()`` stays
# the pinned named refusal at runtime ("Menu item is not registered") -
# the owned engine registers no CE menu actions (UI-only, out of scope),
# and the facade doClick contract is pinned by the broker tests; the
# fixture exercises show/Component/hide instead.
ENGINE_RECORD = (
    "{$lua}\n"
    "function getNameList()\n"
    "  return {{'fnPlayer','goPlayer'},{'fnObject','ObjectPtr'}}\n"
    "end\n"
    "function registerBaseAddresses()\n"
    "  local nameList = getNameList()\n"
    "  local opAddr = AOBScanModuleUnique('ct2synth100.exe', "
    "'48 8B 05 11 22 33 44')\n"
    "  if opAddr == nil then return end\n"
    "  local disassembler = createDisassembler()\n"
    "  disassembler.disassemble(opAddr + 16)\n"
    "  local disTable = disassembler.getLastDisassembleData()\n"
    "  local base = disTable.modrmValue\n"
    "  if base == nil or base == 0 then return end\n"
    "  for i = 1,#nameList do\n"
    "    local addr = base + (i - 1) * 8\n"
    "    registerSymbol(nameList[i][2], addr)\n"
    "  end\n"
    "end\n"
    "function unregisterBaseAddresses()\n"
    "  local nameList = getNameList()\n"
    "  for i = 1,#nameList do unregisterSymbol(nameList[i][2]) end\n"
    "end\n"
    "function onEnable()\n"
    "  local luaEngine = GetLuaEngine()\n"
    "  luaEngine.show()\n"
    "  luaEngine.Component[22].Checked = false\n"
    "  luaEngine.hide()\n"
    "  getUpdateTimer().SetInterval(100)\n"
    "  local marker = stringToByteTable('CT2GOW')\n"
    "  local file = createTableFile('ct2gow')\n"
    "  file.Stream.Position = 0\n"
    "  file.Stream.write(marker, #marker)\n"
    "  if file.Stream.Size ~= 6 then error('table file size mismatch') end\n"
    "  registerBaseAddresses()\n"
    "  local opAddr = AOBScanModuleUnique('ct2synth100.exe', "
    "'48 8B 05 11 22 33 44')\n"
    "  if opAddr ~= nil then\n"
    "    local name = getNameFromAddress(opAddr + 23)\n"
    "    if name ~= 'goplayer' then error('reverse lookup failed') end\n"
    "  end\n"
    "end\n"
    "function onDisable()\n"
    "  unregisterBaseAddresses()\n"
    "  getUpdateTimer().SetInterval(1000)\n"
    "end\n"
    "if syntaxcheck then return end\n"
    "[ENABLE]\n"
    "onEnable()\n"
    "[DISABLE]\n"
    "onDisable()\n")


class NameListMemory(FakeMemory):
    """FakeMemory with the unique scan target and the disassembler
    operand site.

    The scan target sits at base+0x80 (the pattern); at base+0x90 (scan
    + 16) the instruction ``48 8B 05 00 00 00 00`` (mov rax,[rip+0])
    carries the absolute memory operand base+0x97.  The dependent rows
    live at goPlayer = base+0x97 and ObjectPtr = base+0x9F.
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


class NameListEngineTests(unittest.TestCase):
    """Engine level: the GoW-style registration runs and is byte-exact."""

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
            write_table(self.root, body, "gow_engine.ct"), PROCESS)

    def test_activation_registers_derived_symbols_and_is_byte_exact(self):
        memory = NameListMemory()
        plan = self._plan(
            script_record(10, ENGINE_RECORD, "gow provider")
            + value_record(20, "goPlayer")
            + value_record(30, "ObjectPtr"))
        engine = self._start(memory, plan)
        base = memory.base
        self.assertNotIn("goplayer", engine.symbols)
        engine.toggle(10, True)
        self.assertIn(10, engine.applied)
        # The derived symbols register at the disassembler-derived
        # operand address (base+0x97) and its successor site.
        self.assertEqual(engine.symbols.get("goplayer"), base + 0x97)
        self.assertEqual(engine.symbols.get("objectptr"), base + 0x9F)
        # The dependent rows read byte-exact through the owned symbols.
        self.assertEqual(engine.read_value(20), str(0x11223344))
        self.assertEqual(engine.read_value(30), str(0x55667788))
        # Disable releases the owned symbols (toggle returns the
        # resulting state; failures raise).
        self.assertFalse(engine.toggle(10, False))
        self.assertNotIn("goplayer", engine.symbols)
        self.assertNotIn("objectptr", engine.symbols)
        self.assertNotIn(10, engine.applied)

    def test_scan_miss_fails_closed_with_named_refusal(self):
        # A target without the unique pattern: AOBScanModuleUnique
        # answers nil, the registration loop skips, and the activation
        # refuses with the named declared-exports refusal - no symbols,
        # no applied record, no target writes.
        memory = NameListMemory()
        memory.data[0x80:0x87] = b"\x00" * 7
        plan = self._plan(
            script_record(10, ENGINE_RECORD, "gow provider")
            + value_record(20, "goPlayer")
            + value_record(30, "ObjectPtr"))
        engine = self._start(memory, plan)
        with self.assertRaisesRegex(
                NativeRuntimeError,
                "did not confirm its declared symbol exports"):
            engine.toggle(10, True)
        self.assertNotIn(10, engine.applied)
        self.assertNotIn("goplayer", engine.symbols)
        self.assertNotIn("objectptr", engine.symbols)
        self.assertEqual(memory.read(memory.base + 0x97, 4),
                         struct.pack("<I", 0x11223344))


if __name__ == "__main__":
    unittest.main()
