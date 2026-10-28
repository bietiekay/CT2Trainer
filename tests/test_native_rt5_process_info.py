"""RT-5 item C: bounded process-info Lua API family (11 APIs).

Covers, for independently authored synthetic fixtures (no corpus files are
loaded; the fixtures reproduce the corpus usage shapes):

- getProcessIDFromProcessName: exact and casefold match against the plan's
  process binding answer the attached target pid, a mismatch answers 0
  (documented deviation from CE 7.5, which answers nil; the corpus
  tolerates both), and the named argument refusals;
- getProcessList: the single-entry pid->name map (pl[pid] -> name,
  'for pid, name in pairs(...)' iteration, unknown pid -> nil) against the
  bounded single-target model;
- getOpenedProcessID: alias of getOpenProcessID (byte-exact pid);
- targetIs64Bit: architecture from the attached target's pointer width
  (8 -> true, 4 -> false) and the named no-argument refusal;
- enumModules: the single-module answer with Name/Address/Size/Is64Bit/
  PathToFile (PathToFile falls back to the EXE name when the memory
  backend reports no image path - documented deviation), the GoW
  'for i=1,#modList' shape and the per-pointer-size Is64Bit flag;
- disassemble: the bounded iced-x86 exposure - the exact CE-shaped
  instruction line '<8-digit hex address> - <hex bytes> - <opcode
  operands>' (Intel syntax from the pinned iced-x86 formatter; documented
  deviation from CE's own uppercase style), the 32/64-bit mnemonic
  distinction, the bounded count extension (second argument, 1..4096,
  list of lines - clean-room extension with no corpus usage), the
  address-expression input, and the named refusals (argument count, count
  bounds, invalid instruction, bounded read ending first, out-of-range
  address) with zero memory writes;
- the pure-Lua globals: getCEVersion (the pinned constant string '7.5' -
  documented deviation from CE's number return), getAutoAttachList (inert
  per-scope singleton stringlist), getSettings (inert settings object
  whose Value answers '' for any missing key - CE parity for a missing
  registry value; non-string section refused), integerToUserData
  (identity - addresses are plain integers in the host value model),
  stringlist_add (the CE strings_add startup alias, list-first argument
  order, 0-based ordinal).

Every refusal surfaces as a named entry error with zero memory writes and
no applied record; every positive test writes a byte-exact marker the
host reads back, and the table-scope allowlist is pinned to admit the
five dispatched names.
"""
import tempfile
import unittest
import xml.sax.saxutils
from pathlib import Path

from test_native_engine import FakeMemory
from test_native_engine_code import Coordinator
from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import NativeRuntimeError, TrainerEngine


PROCESS = "FixtureTarget.exe"
PID = 123
MARKER = 0x1050


def table_xml(body: str, lua_script: str = "") -> str:
    return ('<CheatTable CheatEngineTableVersion="45"><LuaScript>'
            + lua_script + '</LuaScript><CheatEntries>' + body
            + '</CheatEntries></CheatTable>')


def value_record(entry_id: int, address: str = "1000") -> str:
    return (f'<CheatEntry><ID>{entry_id}</ID><Description>Value {entry_id}</Description>'
            f'<VariableType>4 Bytes</VariableType><Address>{address}</Address></CheatEntry>')


def lua_record(entry_id: int, script: str) -> str:
    return (f'<CheatEntry><ID>{entry_id}</ID><Description>"Record {entry_id}"</Description>'
            f'<VariableType>Auto Assembler Script</VariableType>'
            f'<AssemblerScript>{xml.sax.saxutils.escape(script)}</AssemblerScript></CheatEntry>')


def enable_lua_record(entry_id: int, enable_lua: str) -> str:
    """An AA record whose enable phase is one Lua chunk (the corpus shape)."""
    enable = "[ENABLE]\n{$lua}\n" + enable_lua + "\n{$asm}\n"
    return lua_record(entry_id, enable + "[DISABLE]\n{$asm}\n")


class Memory(FakeMemory):
    @property
    def identity(self):
        return self.pid, self.creation_time

    def _range(self, address, size):
        if not self.base <= address or address + size > self.base + len(self.data):
            raise ValueError('Outside owned fixture memory')

    def is_executable(self, address, size):
        return False


class Memory32(Memory):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pointer_size = 4


class ProcessInfoRuntimeTests(unittest.TestCase):
    """The process-info family through the full engine/Lua host path."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.memories = []
        self.engines = []

    def tearDown(self):
        for memory in self.memories:
            if not memory.closed:
                memory.alive = False
        for engine in self.engines:
            if not engine.closed:
                engine.poll()
                engine.close()

    def attach(self, body: str, *, architecture: str = "x64") -> TrainerEngine:
        path = self.root / "rt5c.CT"
        path.write_text(table_xml(body), encoding="utf-8")
        plan = compile_table(str(path), PROCESS, architecture=architecture)
        memory = Memory32() if architecture == 'x86' else Memory()
        self.memories.append(memory)
        engine = TrainerEngine(plan, state_dir=self.root / f'state{len(self.engines)}',
                               process_lock_dir=self.root / f'shared{len(self.engines)}',
                               memory_factory=lambda name: memory,
                               hook_coordinator=Coordinator())
        self.engines.append(engine)
        engine.poll()
        return engine

    def attach_lua(self, lua: str, **kwargs) -> TrainerEngine:
        return self.attach(value_record(0) + enable_lua_record(1, lua), **kwargs)

    def marker(self, engine: TrainerEngine) -> int:
        return int.from_bytes(engine.memory.read(MARKER, 4), "little")

    # -- getProcessIDFromProcessName ----------------------------------------

    def test_process_id_exact_match_returns_pid(self):
        engine = self.attach_lua(
            "local pid = getProcessIDFromProcessName('FixtureTarget.exe')\n"
            "assert(pid == 123, 'pid: ' .. tostring(pid))\n"
            "writeInteger(0x1050, pid)\n")
        self.assertTrue(engine.toggle(1, True))
        self.assertIn(1, engine.applied)
        self.assertEqual(self.marker(engine), PID)
        self.assertFalse(engine.blocked)

    def test_process_id_casefold_match_returns_pid(self):
        engine = self.attach_lua(
            "local pid = getProcessIDFromProcessName('fIxTuReTaRgEt.EXE')\n"
            "assert(pid == 123, 'pid: ' .. tostring(pid))\n"
            "writeInteger(0x1050, pid)\n")
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.marker(engine), PID)

    def test_process_id_mismatch_returns_zero(self):
        engine = self.attach_lua(
            "local pid = getProcessIDFromProcessName('OtherGame.exe')\n"
            "assert(pid == 0, 'expected 0, got ' .. tostring(pid))\n"
            "writeInteger(0x1050, pid + 1)\n")
        self.assertTrue(engine.toggle(1, True))
        # pid + 1 distinguishes the 0 answer from any failed lookup.
        self.assertEqual(self.marker(engine), 1)

    # -- getProcessList ------------------------------------------------------

    def test_process_list_single_entry_shapes(self):
        engine = self.attach_lua(
            "local pl = getProcessList()\n"
            "assert(pl[123] == 'FixtureTarget.exe', 'pl[123]: ' .. tostring(pl[123]))\n"
            "assert(pl[999999] == nil, 'unknown pid must be nil')\n"
            "local seen = 0\n"
            "for pid, name in pairs(pl) do\n"
            "  seen = seen + 1\n"
            "  assert(pid == 123 and name == 'FixtureTarget.exe',\n"
            "         'entry: ' .. tostring(pid) .. '/' .. tostring(name))\n"
            "end\n"
            "assert(seen == 1, 'entries: ' .. seen)\n"
            "writeInteger(0x1050, seen)\n")
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.marker(engine), 1)

    # -- getOpenedProcessID ----------------------------------------------------

    def test_get_opened_process_id_is_get_open_process_id_alias(self):
        engine = self.attach_lua(
            "local direct = getOpenProcessID()\n"
            "local alias = getOpenedProcessID()\n"
            "assert(direct == 123, 'direct: ' .. tostring(direct))\n"
            "assert(alias == direct, 'alias: ' .. tostring(alias))\n"
            "writeInteger(0x1050, alias)\n")
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.marker(engine), PID)

    # -- targetIs64Bit ----------------------------------------------------------

    def test_target_is_64bit_follows_pointer_width(self):
        engine64 = self.attach_lua(
            "assert(targetIs64Bit() == true, '64-bit target must answer true')\n"
            "writeInteger(0x1050, 1)\n")
        self.assertTrue(engine64.toggle(1, True))
        self.assertEqual(self.marker(engine64), 1)
        engine32 = self.attach_lua(
            "assert(targetIs64Bit() == false, '32-bit target must answer false')\n"
            "writeInteger(0x1050, 1)\n", architecture="x86")
        self.assertTrue(engine32.toggle(1, True))
        self.assertEqual(self.marker(engine32), 1)

    # -- enumModules --------------------------------------------------------------

    def test_enum_modules_single_module_fields(self):
        engine = self.attach_lua(
            "local mods = enumModules()\n"
            "assert(#mods == 1, 'modules: ' .. #mods)\n"
            "assert(mods[1].Name == 'FixtureTarget.exe', mods[1].Name)\n"
            "assert(mods[1].Address == 0x1000, 'addr: ' .. tostring(mods[1].Address))\n"
            "assert(mods[1].Size == 256, 'size: ' .. tostring(mods[1].Size))\n"
            "assert(mods[1].Is64Bit == true, 'Is64Bit must be true')\n"
            "assert(mods[1].PathToFile == 'FixtureTarget.exe', mods[1].PathToFile)\n"
            "local seen = 0\n"
            "for i = 1, #mods do seen = seen + 1 end\n"
            "assert(seen == 1, 'loop: ' .. seen)\n"
            "writeInteger(0x1050, seen)\n")
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.marker(engine), 1)

    def test_enum_modules_32bit_flag(self):
        engine = self.attach_lua(
            "local mods = enumModules()\n"
            "assert(#mods == 1, 'modules: ' .. #mods)\n"
            "assert(mods[1].Is64Bit == false, 'Is64Bit must be false')\n"
            "writeInteger(0x1050, 1)\n", architecture="x86")
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.marker(engine), 1)

    # -- disassemble ---------------------------------------------------------------

    def test_disassemble_single_line_64bit_and_expression_address(self):
        engine = self.attach_lua(
            "local line1 = disassemble(0x1040)\n"
            "assert(line1 == '00001040 - 55 - push rbp', line1)\n"
            "local line2 = disassemble('0x1040')\n"
            "assert(line2 == line1, 'expression address: ' .. tostring(line2))\n"
            "writeInteger(0x1050, 1)\n")
        engine.memory.data[0x40:0x42] = b"\x55\xC3"
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.marker(engine), 1)

    def test_disassemble_single_line_32bit(self):
        engine = self.attach_lua(
            "local line1 = disassemble(0x1040)\n"
            "assert(line1 == '00001040 - 55 - push ebp', line1)\n"
            "writeInteger(0x1050, 1)\n", architecture="x86")
        engine.memory.data[0x40] = 0x55
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.marker(engine), 1)

    def test_disassemble_count_extension_returns_line_list(self):
        engine = self.attach_lua(
            "local lines = disassemble(0x1040, 2)\n"
            "assert(#lines == 2, 'lines: ' .. #lines)\n"
            "assert(lines[1] == '00001040 - 55 - push rbp', lines[1])\n"
            "assert(lines[2] == '00001041 - C3 - ret', lines[2])\n"
            "writeInteger(0x1050, #lines)\n")
        engine.memory.data[0x40:0x42] = b"\x55\xC3"
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.marker(engine), 2)

    def test_disassemble_multibyte_instruction(self):
        engine = self.attach_lua(
            "local line1 = disassemble(0x1040)\n"
            "assert(line1 == '00001040 - 48 8B 44 24 28 - mov rax,[rsp+28h]', line1)\n"
            "writeInteger(0x1050, 1)\n")
        engine.memory.data[0x40:0x45] = b"\x48\x8B\x44\x24\x28"
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.marker(engine), 1)

    def test_disassemble_and_process_api_refusal_matrix(self):
        cases = (
            ("disassemble()",
             "disassemble takes an address and an optional count"),
            ("disassemble(0x1040, 2, 3)",
             "disassemble takes an address and an optional count"),
            ("disassemble(0x1040, 0)",
             "disassemble count must be an integer within 1..4096"),
            ("disassemble(0x1040, 4097)",
             "disassemble count must be an integer within 1..4096"),
            ("disassemble(0x1040, 'x')",
             "disassemble count must be an integer within 1..4096"),
            ("getProcessIDFromProcessName()",
             "getProcessIDFromProcessName requires exactly one non-empty process name"),
            ("getProcessIDFromProcessName('')",
             "getProcessIDFromProcessName requires exactly one non-empty process name"),
            ("getProcessIDFromProcessName(42)",
             "getProcessIDFromProcessName requires exactly one non-empty process name"),
            ("getProcessList(1)", "getProcessList takes no arguments"),
            ("targetIs64Bit(1)", "targetIs64Bit takes no arguments"),
            ("enumModules(1)", "enumModules takes no arguments (single-target model)"),
            ("getSettings(42)", "getSettings requires a section name"),
            ("stringlist_add({}, 'x')",
             "stringlist_add requires a string list object"),
            ("local sl = createStringlist()\nsl:destroy()\nstringlist_add(sl, 'x')",
             "String list is destroyed"),
        )
        for source, expected in cases:
            with self.subTest(case=expected):
                engine = self.attach_lua(source)
                with self.assertRaises(NativeRuntimeError):
                    engine.toggle(1, True)
                self.assertIn(1, engine.entry_errors)
                self.assertIn(expected, engine.entry_errors[1])
                self.assertNotIn(1, engine.applied)
                self.assertEqual(engine.memory.writes, [])
                self.assertFalse(engine.blocked)

    def test_disassemble_invalid_instruction_is_refused(self):
        engine = self.attach_lua("disassemble(0x1040)\n")
        engine.memory.data[0x40] = 0x60
        with self.assertRaises(NativeRuntimeError):
            engine.toggle(1, True)
        self.assertIn("disassemble invalid instruction at 0x1040",
                      engine.entry_errors[1])
        self.assertNotIn(1, engine.applied)
        self.assertEqual(engine.memory.writes, [])
        self.assertFalse(engine.blocked)

    def test_disassemble_bounded_read_ends_first(self):
        engine = self.attach_lua("disassemble(0x10FF, 2)\n")
        engine.memory.data[0xFF] = 0x55
        with self.assertRaises(NativeRuntimeError):
            engine.toggle(1, True)
        self.assertIn("disassemble could not decode 2 instruction(s) at 0x10FF "
                      "(bounded read ends first)",
                      engine.entry_errors[1])
        self.assertNotIn(1, engine.applied)
        self.assertEqual(engine.memory.writes, [])
        self.assertFalse(engine.blocked)

    def test_disassemble_out_of_range_address_is_refused(self):
        # The fixture memory backend guards its own range; the named
        # backend refusal must surface as the entry error.
        engine = self.attach_lua("disassemble(0x2000)\n")
        with self.assertRaises(NativeRuntimeError):
            engine.toggle(1, True)
        self.assertIn("Outside owned fixture memory", engine.entry_errors[1])
        self.assertNotIn(1, engine.applied)
        self.assertEqual(engine.memory.writes, [])
        self.assertFalse(engine.blocked)

    # -- pure-Lua globals -------------------------------------------------------------

    def test_get_ce_version_is_the_pinned_constant(self):
        engine = self.attach_lua(
            "local v = getCEVersion()\n"
            "assert(v == '7.5', 'version: ' .. tostring(v))\n"
            "local gate = 'CE ' .. v\n"
            "assert(gate == 'CE 7.5', gate)\n"
            "writeInteger(0x1050, #gate)\n")
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.marker(engine), 6)

    def test_get_auto_attach_list_is_inert_singleton(self):
        engine = self.attach_lua(
            "local al1 = getAutoAttachList()\n"
            "local al2 = getAutoAttachList()\n"
            "assert(al1 == al2, 'must return the same list')\n"
            "assert(al1.Count == 0, 'fresh list must be empty')\n"
            "local idx = stringlist_add(al1, 'fixturetarget.exe')\n"
            "assert(idx == 0, 'ordinal: ' .. tostring(idx))\n"
            "assert(al1.Count == 1, 'count: ' .. al1.Count)\n"
            "assert(al1[0] == 'fixturetarget.exe', al1[0])\n"
            "writeInteger(0x1050, al1.Count)\n")
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.marker(engine), 1)

    def test_stringlist_add_returns_0based_ordinals(self):
        engine = self.attach_lua(
            "local sl = createStringlist()\n"
            "local i0 = stringlist_add(sl, 'a.exe')\n"
            "local i1 = stringlist_add(sl, 'b.exe')\n"
            "assert(i0 == 0, 'first: ' .. tostring(i0))\n"
            "assert(i1 == 1, 'second: ' .. tostring(i1))\n"
            "assert(sl.Count == 2, 'count: ' .. sl.Count)\n"
            "assert(sl[0] == 'a.exe' and sl[1] == 'b.exe', 'items')\n"
            "writeInteger(0x1050, sl.Count)\n")
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.marker(engine), 2)

    def test_get_settings_answers_empty_string_for_missing_keys(self):
        engine = self.attach_lua(
            "local s = getSettings('Trainer')\n"
            "assert(s.Value['Speed'] == '', 'missing key: ' .. tostring(s.Value['Speed']))\n"
            "assert(s.Value['AnyOtherKey'] == '', 'second key')\n"
            "s.Value['Speed'] = '2.0'\n"
            "assert(s.Value['Speed'] == '2.0', 'stored write: ' .. tostring(s.Value['Speed']))\n"
            "writeInteger(0x1050, 1)\n")
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.marker(engine), 1)

    def test_integer_to_userdata_is_the_identity(self):
        engine = self.attach_lua(
            "local addr = integerToUserData(0x1010)\n"
            "assert(addr == 0x1010, 'addr: ' .. tostring(addr))\n"
            "assert(readInteger(integerToUserData(0x1010)) == 1234, 'readback')\n"
            "writeInteger(0x1050, 1)\n")
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.marker(engine), 1)

    def test_out_of_scope_names_stay_refused(self):
        for source in ("createMemoryRecord()",
                       "registerAutoAssemblerCommand('a', 'b')",
                       "messageDialog('x')"):
            with self.subTest(case=source):
                engine = self.attach_lua(source)
                with self.assertRaises(NativeRuntimeError):
                    engine.toggle(1, True)
                self.assertIn(1, engine.entry_errors)
                self.assertNotIn(1, engine.applied)
                self.assertEqual(engine.memory.writes, [])
                self.assertFalse(engine.blocked)

    # -- table scope -------------------------------------------------------------------

    def test_table_scope_admits_the_process_info_reads(self):
        table_lua = (
            "PINFO_PID = getProcessIDFromProcessName('FixtureTarget.exe')\n"
            "assert(PINFO_PID == 123, 'table-scope pid: ' .. tostring(PINFO_PID))\n"
            "PINFO_IS64 = targetIs64Bit()\n"
            "assert(PINFO_IS64 == true, 'table-scope arch')\n"
            "PINFO_MODS = enumModules()\n"
            "assert(#PINFO_MODS == 1, 'table-scope modules')\n"
            "PINFO_LIST = getProcessList()\n"
            "assert(PINFO_LIST[123] == 'FixtureTarget.exe', 'table-scope list')\n")
        path = self.root / "rt5c-table.CT"
        path.write_text(table_xml(value_record(0), table_lua), encoding="utf-8")
        plan = compile_table(str(path), PROCESS)
        memory = Memory()
        self.memories.append(memory)
        engine = TrainerEngine(plan, state_dir=self.root / f'state{len(self.engines)}',
                               process_lock_dir=self.root / f'shared{len(self.engines)}',
                               memory_factory=lambda name: memory,
                               hook_coordinator=Coordinator())
        self.engines.append(engine)
        engine.poll()
        self.assertTrue(plan['table_lua']['executed'])
        self.assertEqual(plan['table_lua']['reasons'], [])


if __name__ == "__main__":
    unittest.main()
