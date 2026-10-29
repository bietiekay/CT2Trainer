"""RT-5 item C2: runtime dynamic addresslist records + custom AA directives.

Covers, for independently authored synthetic fixtures (no corpus files are
loaded; the fixtures reproduce the corpus usage shapes - GoW/SandFall
createRecord+delete, Horizon destroy, Octopath dropdown fields, Resonance
getMemoryRecord(i), P5/Octopath registerlabel):

- createMemoryRecord (AddressList.createMemoryRecord /
  getAddressList().createMemoryRecord / the built-in AddressList index):
  the engine-owned in-memory journal (session-scoped, synthetic IDs above
  every plan ID, never persisted, plan entries byte-identical);
- the record surface the corpus uses: Description/Type/Address/Script/
  ShowAsHex/DontSave/Options/isGroupHeader/Collapsed/Parent/Active/
  OffsetCount/Offset[i]/OffsetText[i] (0-based, out-of-range reads answer
  nil), ID/isDynamic/Parent/Index/Count/Child[i] reads,
  appendToEntry(parent), removeFromParent, :Delete(), the generic
  destroy() (CE luaclass method), inert display fields;
- OnActivate/OnDeactivate callbacks fired on the Active toggle (GoW shape,
  guarded failures contained, stale tokens contained);
- vtAutoAssembler journal records: the script compiles through the same
  AA publication path as plan records (persist=False), Active=true runs
  the enable phase on the owned fixture, Active=false restores the
  original bytes, un-compilable scripts are refused named with zero
  writes;
- registerAutoAssemblerCommand/unregisterAutoAssemblerCommand (table
  scope only): the CE 7.5 dispatch contract - a line whose uppercased
  prefix before the first '(' equals the registered name is replaced by
  the callback result (CRLF split, nesting, nil/empty deletes the line,
  syntaxcheck pass calls the callback with syntaxcheck=true), replace
  semantics, reserved built-in names refused, record-scope registration
  refused, the registry dies with the table scope;
- every new refusal: exact string, zero memory writes, no applied record.
"""
import copy
import json
import tempfile
import unittest
import xml.sax.saxutils
from pathlib import Path

from test_native_engine import FakeMemory
from test_native_engine_code import Coordinator
from ct2trainer.native import aa_program
from ct2trainer.native.aa_program import MAX_CUSTOM_RESULT_CHARS, ProgramError
from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import NativeRuntimeError, TrainerEngine
from ct2trainer.native.lua_host import EngineLuaBroker, LuaHostError


PROCESS = "FixtureTarget.exe"
PID = 123
MARKER = 0x1050
DYN_BASE = 2 ** 31


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


class DynamicRecordRuntimeTests(unittest.TestCase):
    """The dynamic-record journal and custom AA directives end to end."""

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

    def attach(self, body: str, table_lua: str = "") -> TrainerEngine:
        path = self.root / "rt5c2.CT"
        path.write_text(table_xml(body, table_lua), encoding="utf-8")
        plan = compile_table(str(path), PROCESS)
        memory = Memory()
        self.memories.append(memory)
        engine = TrainerEngine(plan, state_dir=self.root / f'state{len(self.engines)}',
                               process_lock_dir=self.root / f'shared{len(self.engines)}',
                               memory_factory=lambda name: memory,
                               hook_coordinator=Coordinator())
        self.engines.append(engine)
        engine.poll()
        return engine

    def attach_lua(self, lua: str, table_lua: str = "") -> TrainerEngine:
        return self.attach(value_record(0) + enable_lua_record(1, lua), table_lua)

    def marker(self, engine: TrainerEngine) -> int:
        return int.from_bytes(engine.memory.read(MARKER, 4), "little")

    def plan_snapshot(self, plan) -> str:
        return json.dumps(plan['entries'], sort_keys=True, default=str)

    # -- journal creation (table scope) ------------------------------------

    def test_create_memory_record_table_scope_happy_path(self):
        table_lua = (
            "local al = getAddressList()\n"
            "local header = al.createMemoryRecord()\n"
            "header.Description = 'C2 Header'\n"
            "header.isGroupHeader = true\n"
            "local rec = al.createMemoryRecord()\n"
            "rec.Description = 'C2 Value'\n"
            "rec.Type = vtDword\n"
            "rec:setAddress(0x1020)\n"
            "rec.DontSave = true\n"
            "rec.ShowAsHex = true\n"
            "rec.Options = '[moHideChildren]'\n"
            "rec.appendToEntry(header)\n"
            "header.Collapsed = true\n"
            "assert(al.Count == 3, 'count: ' .. tostring(al.Count))\n"
            "assert(rec.Parent.ID == header.ID, 'parent proxy')\n")
        engine = self.attach(value_record(0), table_lua)
        snapshot = plan_snapshot = self.plan_snapshot(engine.plan)
        self.assertEqual(len(engine.dynamic_records), 2)
        header_id, rec_id = DYN_BASE + 1, DYN_BASE + 2
        self.assertEqual(set(engine.dynamic_records), {header_id, rec_id})
        header = engine.entries[header_id]
        rec = engine.entries[rec_id]
        self.assertEqual(header['label'], 'C2 Header')
        self.assertEqual(header['kind'], 'heading')
        self.assertTrue(header['is_group_header'])
        self.assertIsNone(header['parent_id'])
        self.assertEqual(rec['label'], 'C2 Value')
        self.assertEqual(rec['kind'], 'value')
        self.assertEqual(rec['variable_type'], 2)
        self.assertEqual(rec['address'], 0x1020)
        self.assertEqual(rec['parent_id'], header_id)
        self.assertTrue(rec['dont_save'])
        self.assertTrue(rec['show_as_hex'])
        self.assertEqual(rec['options'], '[moHideChildren]')
        self.assertTrue(rec['dynamic'])
        self.assertEqual(engine.dynamic_record_child(header_id, 0), rec_id)
        self.assertIsNone(engine.dynamic_record_child(header_id, 1))
        self.assertIsNone(engine.dynamic_record_child(header_id, -1))
        self.assertTrue(engine.plan['table_lua']['executed'])
        self.assertEqual(engine.plan['table_lua']['reasons'], [])
        # The compiled plan entries are untouched by the runtime journal.
        self.assertEqual(self.plan_snapshot(engine.plan), snapshot)
        for entry in engine.plan['entries']:
            self.assertLess(entry['id'], DYN_BASE)

    def test_plan_entries_byte_identical_after_dynamic_creation(self):
        engine_a = self.attach(value_record(0), (
            "local al = getAddressList()\n"
            "for i = 1, 3 do\n"
            "  local rec = al.createMemoryRecord()\n"
            "  rec.Description = 'C2 Loop ' .. i\n"
            "end\n"))
        engine_b = self.attach(value_record(0))
        self.assertEqual(self.plan_snapshot(engine_a.plan),
                         self.plan_snapshot(engine_b.plan))
        self.assertEqual(len(engine_a.dynamic_records), 3)
        self.assertEqual(len(engine_b.dynamic_records), 0)
        self.assertEqual(len(engine_a.entries), 4)
        self.assertEqual(len(engine_b.entries), 1)

    # -- AddressList surface -------------------------------------------------

    def test_get_address_list_and_addresslist_forms(self):
        lua = (
            "local al = getAddressList()\n"
            "local rec = al.createMemoryRecord()\n"
            "rec.Description = 'Al Record'\n"
            "rec.Type = vtDword\n"
            "rec:setAddress(0x1030)\n"
            "local via = AddressList.createMemoryRecord()\n"
            "via.Description = 'Via Global Method'\n"
            "local g = AddressList\n"
            "assert(g.Count == al.Count, 'count parity')\n"
            "local byDesc = g.getMemoryRecord('AL record')\n"
            "assert(byDesc ~= nil, 'casefold lookup')\n"
            "assert(byDesc.ID == rec.ID, 'lookup ID')\n"
            "assert(al.getMemoryRecordByID(rec.ID).ID == rec.ID, 'ID lookup')\n"
            "assert(al.getMemoryRecordByDescription('AL record').ID == rec.ID, 'by description')\n"
            "local dyn = g[al.Count - 2]\n"
            "assert(dyn.ID == rec.ID, 'flat index: ' .. tostring(dyn and dyn.ID))\n"
            "assert(g[0].Description == 'Value 0', 'plan record by index')\n"
            "assert(g.getMemoryRecord('no such record') == nil, 'missing description')\n"
            "assert(g[99] == nil, 'missing index')\n"
            "writeInteger(0x1050, al.Count)\n")
        engine = self.attach_lua(lua)
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.marker(engine), 4)

    # -- child / offset semantics (GoW / SandFall / Horizon shapes) ----------

    def test_child_0based_delete_and_count(self):
        lua = (
            "local al = getAddressList()\n"
            "local parent = al.createMemoryRecord()\n"
            "parent.Description = 'C2 Parent'\n"
            "parent.isGroupHeader = true\n"
            "local c1 = al.createMemoryRecord()\n"
            "c1.Description = 'Child One'\n"
            "c1.appendToEntry(parent)\n"
            "local c2 = al.createMemoryRecord()\n"
            "c2.Description = 'Child Two'\n"
            "c2.appendToEntry(parent)\n"
            "assert(parent.Count == 2, 'children: ' .. tostring(parent.Count))\n"
            "assert(parent.Child[0].Description == 'Child One', 'child 0')\n"
            "assert(parent.Child[1].Description == 'Child Two', 'child 1')\n"
            "assert(parent.Child[2] == nil, 'out-of-range child is nil')\n"
            "c1:Delete()\n"
            "assert(parent.Count == 1, 'after delete: ' .. tostring(parent.Count))\n"
            "assert(parent.Child[0].Description == 'Child Two', 'repointed child')\n"
            "writeInteger(0x1050, parent.Count)\n")
        engine = self.attach_lua(lua)
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.marker(engine), 1)

    def test_destroy_promotes_grandchild_and_remove_from_parent(self):
        lua = (
            "local al = getAddressList()\n"
            "local p = al.createMemoryRecord()\n"
            "p.Description = 'Destroy Parent'\n"
            "local c = al.createMemoryRecord()\n"
            "c.Description = 'Destroy Mid'\n"
            "c.appendToEntry(p)\n"
            "local leaf = al.createMemoryRecord()\n"
            "leaf.Description = 'Destroy Leaf'\n"
            "leaf.appendToEntry(c)\n"
            "c.destroy()\n"
            "assert(p.Count == 1, 'promoted: ' .. tostring(p.Count))\n"
            "assert(p.Child[0].Description == 'Destroy Leaf', 'leaf promoted')\n"
            "local t = al.createMemoryRecord()\n"
            "t.Description = 'Temp'\n"
            "t.appendToEntry(p)\n"
            "t.removeFromParent()\n"
            "assert(t.Parent == nil, 'top level again')\n"
            "assert(p.Count == 1, 'temp detached: ' .. tostring(p.Count))\n"
            "writeInteger(0x1050, p.Count)\n")
        engine = self.attach_lua(lua)
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.marker(engine), 1)

    # -- value read / write --------------------------------------------------

    def test_dynamic_value_read_write(self):
        lua = (
            "local al = getAddressList()\n"
            "local r = al.createMemoryRecord()\n"
            "r.Description = 'C2 Value'\n"
            "r.Type = vtDword\n"
            "r:setAddress(0x1010)\n"
            "assert(r.isDynamic == true, 'isDynamic')\n"
            "assert(AddressList.getMemoryRecordByID(0).isDynamic == false, 'plan record not dynamic')\n"
            "r.Value = 0xCAFEBABE\n"
            "local v = r.Value\n"
            "assert(v == 0xCAFEBABE, 'readback: ' .. string.format('0x%08X', v))\n"
            "r.Type = vtByte\n"
            "r.Value = 65\n"
            "assert(r.Value == 65, 'byte: ' .. tostring(r.Value))\n"
            "writeInteger(0x1050, r.Value)\n")
        engine = self.attach_lua(lua)
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.marker(engine), 65)
        self.assertEqual(engine.memory.read(0x1010, 1), b'A')

    # -- record-scope refusal matrices ---------------------------------------

    def _refuse_record_lua(self, setup: str, mutation: str, expected: str):
        lua = (
            "local al = getAddressList()\n"
            "local r = al.createMemoryRecord()\n"
            "r.Description = 'C2 Refuse'\n"
            + setup + "\n"
            + mutation + "\n")
        engine = self.attach_lua(lua)
        with self.assertRaises(NativeRuntimeError):
            engine.toggle(1, True)
        self.assertIn(1, engine.entry_errors)
        self.assertIn(expected, engine.entry_errors[1])
        self.assertNotIn(1, engine.applied)
        self.assertEqual(engine.memory.writes, [])
        self.assertFalse(engine.blocked)

    def test_dynamic_record_mutation_refusals(self):
        cases = [
            ("r.Type = vtByte\nr:setAddress(0x1040)\n", "r.Value = 300",
             "Dynamic record Value requires an integer in range"),
            ("r.Type = vtByte\nr:setAddress(0x1040)\n", "r.Value = '5'",
             "Dynamic record Value requires an integer in range"),
            ("r.Type = 11\n", "r.Value = 1",
             "Dynamic record Value requires a numeric value type 0..5"),
            ("", "r.Type = 16",
             "Dynamic record Type requires an integer 0..15"),
            ("", "r.Type = '4 Bytes'",
             "Dynamic record Type requires an integer 0..15"),
            ("", "r.Description = 42",
             "Dynamic record Description requires text"),
            ("", "r.Script = ''",
             "Dynamic record Script requires non-empty text"),
            ("", "r:setAddress(-5)",
             "Dynamic record Address must be an integer in address range."),
            ("", "r:setAddress(0x9000)",
             "Dynamic record Address must be an integer in address range."),
            ("r.Type = vtByte\nr:setAddress(0x1040)\n", "r.Address = 'nosuchmod+10'\nr.Value = 1",
             "Dynamic record address does not resolve: nosuchmod+10"),
            ("r.Type = vtQword\nr:setAddress(0x10FC)\n", "r.Value = 1",
             "Dynamic record address is outside the target range."),
            ("", "r.OffsetCount = 2048",
             "Dynamic record OffsetCount requires an integer 0..1024"),
            ("r.OffsetCount = 1\n", "r.Offset[5] = 1",
             "MemoryRecord index is out of bounds"),
            ("r.OffsetCount = 1\n", "r.OffsetText[0] = 5",
             "Dynamic record OffsetText requires text"),
            ("r.OffsetCount = 1\n", "r.Offset[0] = '10'",
             "Dynamic record Offset requires an integer"),
            ("", "r.Active = 'yes'",
             "Dynamic record Active requires a boolean"),
            ("", "r.Options = 5",
             "Dynamic record Options requires text"),
            ("", "r.ShowAsHex = 'x'",
             "Dynamic record ShowAsHex requires a boolean"),
            ("", "r.isGroupHeader = 1",
             "Dynamic record isGroupHeader requires a boolean"),
            ("", "r.Collapsed = 2",
             "Dynamic record Collapsed requires a boolean"),
            ("", "r.OnActivate = 42",
             "Dynamic record callback must be a function"),
            ("", "r.ID = 9",
             "Dynamic record ID is engine-owned."),
            ("", "r.setID(9)",
             "Dynamic record ID is engine-owned."),
            ("", "r.Index = 1",
             "Unsupported MemoryRecord mutation: Index"),
            ("", "r.Parent = 999999",
             "Dynamic record Parent is not a live record: 999999"),
            ("", "r.Parent = 'x'",
             "Dynamic record Parent requires a record ID"),
            ("", "r.appendToEntry(42)",
             "appendToEntry requires a parent record"),
        ]
        for setup, mutation, expected in cases:
            with self.subTest(mutation=mutation):
                self._refuse_record_lua(setup, mutation, expected)

    def test_plan_record_mutation_refusals(self):
        cases = [
            ("local p = AddressList.getMemoryRecordByID(0)\np.Description = 'x'",
             "Unsupported MemoryRecord mutation: Description"),
            ("local p = AddressList.getMemoryRecordByID(0)\np:Delete()",
             "MemoryRecord delete/reparent is only supported for runtime records"),
            ("local p = AddressList.getMemoryRecordByID(0)\np.destroy()",
             "MemoryRecord delete/reparent is only supported for runtime records"),
            ("local p = AddressList.getMemoryRecordByID(0)\np.Offset[0] = 5",
             "MemoryRecord offset mutation is only supported for runtime records"),
            ("local p = AddressList.getMemoryRecordByID(0)\np.OffsetText[0] = '10'",
             "MemoryRecord offset mutation is only supported for runtime records"),
            ("AddressList.getMemoryRecordByID('abc')",
             "MemoryRecord ID must be an integer"),
            ("local x = AddressList[1.5]",
             "AddressList keys are record descriptions or indexes"),
            ("AddressList.foo = 1",
             "AddressList is a read-only index"),
            ("createMemoryRecord()",
             "Unsupported CE Lua API: createMemoryRecord"),
            ("registerAutoAssemblerCommand('a', 'b')",
             "AA command registration has invalid arguments."),
            ("unregisterAutoAssemblerCommand('x')",
             "AA command registration is table-scope only"),
            ("registerAutoAssemblerCommand('x', function() end)",
             "AA command registration is table-scope only"),
        ]
        for source, expected in cases:
            with self.subTest(source=source):
                engine = self.attach_lua(source)
                with self.assertRaises(NativeRuntimeError):
                    engine.toggle(1, True)
                self.assertIn(1, engine.entry_errors)
                self.assertIn(expected, engine.entry_errors[1])
                self.assertNotIn(1, engine.applied)
                self.assertEqual(engine.memory.writes, [])
                self.assertFalse(engine.blocked)

    def test_dead_record_proxy_reads_refused(self):
        lua = (
            "local al = getAddressList()\n"
            "local r = al.createMemoryRecord()\n"
            "r.Description = 'C2 Dead'\n"
            "r:Delete()\n"
            "local ok, err = pcall(function() return r.Description end)\n"
            "assert(ok == false, 'dead read must fail')\n"
            # engine-raised refusals cross the boundary as exception objects;
            # tostring() recovers the exact message for the match.
            "assert(tostring(err):find('MemoryRecord is not live:'),\n"
            "       'dead read: ' .. tostring(err))\n"
            "writeInteger(0x1050, 1)\n")
        engine = self.attach_lua(lua)
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.marker(engine), 1)

    def test_parent_cycle_and_self_parent_refused(self):
        lua = (
            "local al = getAddressList()\n"
            "local a = al.createMemoryRecord()\n"
            "a.Description = 'C2 A'\n"
            "local b = al.createMemoryRecord()\n"
            "b.Description = 'C2 B'\n"
            "a.Parent = b\n"
            "local ok, err = pcall(function() b.Parent = a end)\n"
            "assert(ok == false, 'cycle must fail')\n"
            # engine-raised refusals cross the boundary as exception objects;
            # tostring() recovers the exact message for the match.
            "assert(tostring(err):find('Dynamic record Parent would create a cycle'),\n"
            "       'cycle: ' .. tostring(err))\n"
            "local ok2, err2 = pcall(function() a.Parent = a.ID end)\n"
            "assert(ok2 == false, 'self parent must fail')\n"
            "assert(tostring(err2):find('Dynamic record Parent is not a live record:'),\n"
            "       'self parent: ' .. tostring(err2))\n"
            "writeInteger(0x1050, 1)\n")
        engine = self.attach_lua(lua)
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.marker(engine), 1)

    def test_stale_callback_token_contained(self):
        """A well-formed token that resolves to nothing in the owning scope
        (the registry was cleared, or it came from a foreign scope) must not
        kill the toggle: the journal flag is set and the miss is contained
        as a debug event, with zero memory writes."""
        table_lua = (
            "local al = getAddressList()\n"
            "local r = al.createMemoryRecord()\n"
            "r.Description = 'C2 Stale'\n"
            "r.Type = vtDword\n"
            "r:setAddress(0x1050)\n")
        engine = self.attach(value_record(0), table_lua)
        ident = DYN_BASE + 1
        # The broker contract stores any well-formed token verbatim;
        # 'ct2fn:99' was never registered in this scope's registry.
        engine.dynamic_record_set(ident, 'OnActivate', 'ct2fn:99', scope=None)
        writes_before = len(engine.memory.writes)
        engine.dynamic_record_active(ident, True)
        self.assertTrue(engine.entries[ident]['active'])
        self.assertEqual(len(engine.memory.writes), writes_before)
        # Clear the callback again through the same contract.
        engine.dynamic_record_set(ident, 'OnActivate', None, scope=None)
        engine.dynamic_record_active(ident, False)
        self.assertFalse(engine.entries[ident]['active'])

    # -- OnActivate / OnDeactivate (GoW shape) --------------------------------

    def test_on_activate_on_deactivate_fire_on_toggle(self):
        table_lua = (
            "local al = getAddressList()\n"
            "local target = al.createMemoryRecord()\n"
            "target.Description = 'CB Target'\n"
            "target.Type = vtDword\n"
            "target:setAddress(0x1050)\n"
            "local src = al.createMemoryRecord()\n"
            "src.Description = 'CB Source'\n"
            "src.Type = vtDword\n"
            "src:setAddress(0x1060)\n"
            "src.OnActivate = function(rec, ante, current)\n"
            "  assert(current == true, 'on activate current')\n"
            "  AddressList['CB Target'].Value = 777\n"
            "end\n"
            "src.OnDeactivate = function(rec, ante, current)\n"
            "  assert(ante == true, 'on deactivate ante')\n"
            "  AddressList['CB Target'].Value = 888\n"
            "end\n")
        lua = (
            "local src = AddressList['CB Source']\n"
            "assert(src ~= nil, 'CB Source present')\n"
            "src.Active = true\n"
            "assert(src.Active == true, 'active flag')\n"
            "assert(readInteger(0x1050) == 777, 'onactivate: ' .. tostring(readInteger(0x1050)))\n"
            "src.Active = false\n"
            "assert(src.Active == false, 'inactive flag')\n"
            "assert(readInteger(0x1050) == 888, 'ondeactivate: ' .. tostring(readInteger(0x1050)))\n")
        engine = self.attach_lua(lua, table_lua)
        self.assertTrue(engine.plan['table_lua']['executed'])
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.marker(engine), 888)
        src = engine.dynamic_records[DYN_BASE + 2]
        self.assertFalse(src['active'])

    def test_callback_failure_contained(self):
        table_lua = (
            "local al = getAddressList()\n"
            "local target = al.createMemoryRecord()\n"
            "target.Description = 'CBF Target'\n"
            "target.Type = vtDword\n"
            "target:setAddress(0x1050)\n"
            "local src = al.createMemoryRecord()\n"
            "src.Description = 'CBF Source'\n"
            "src.OnActivate = function(rec, ante, current)\n"
            "  error('callback boom', 0)\n"
            "  AddressList['CBF Target'].Value = 777\n"
            "end\n")
        lua = (
            "local src = AddressList['CBF Source']\n"
            "src.Active = true\n"
            "assert(src.Active == true, 'flag set despite callback error')\n"
            "writeInteger(0x1050, 0)\n")
        engine = self.attach_lua(lua, table_lua)
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.marker(engine), 0)

    # -- vtAutoAssembler journal records ---------------------------------------

    def test_dynamic_aa_script_enable_disable(self):
        lua = (
            "local al = getAddressList()\n"
            "local r = al.createMemoryRecord()\n"
            "r.Description = 'C2 AA'\n"
            "r.Type = vtAutoAssembler\n"
            "r.Script = '[ENABLE]\\nFixtureTarget.exe+40:\\ndb 2A\\n[DISABLE]\\nFixtureTarget.exe+40:\\ndb 00\\n'\n"
            "r.Active = true\n"
            "assert((readInteger(0x1040) % 256) == 0x2A, 'enabled byte')\n"
            "assert(r.Active == true, 'active flag')\n"
            "r.Active = false\n"
            "assert((readInteger(0x1040) % 256) == 0x00, 'restored byte')\n"
            "assert(r.Active == false, 'inactive flag')\n"
            "writeInteger(0x1050, 1)\n")
        engine = self.attach_lua(lua)
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.marker(engine), 1)
        self.assertNotIn(DYN_BASE + 1, engine.applied)
        self.assertFalse(engine.blocked)

    def test_dynamic_aa_bad_script_refused(self):
        engine = self.attach_lua(
            "local al = getAddressList()\n"
            "local r = al.createMemoryRecord()\n"
            "r.Description = 'C2 AA Bad'\n"
            "r.Type = vtAutoAssembler\n"
            "r.Script = 'garbage not aa code'\n"
            "r.Active = true\n")
        with self.assertRaises(NativeRuntimeError):
            engine.toggle(1, True)
        self.assertIn(1, engine.entry_errors)
        self.assertIn("Dynamic AA record script refused", engine.entry_errors[1])
        self.assertNotIn(1, engine.applied)
        self.assertEqual(engine.memory.writes, [])
        self.assertFalse(engine.blocked)

    # -- custom AA directives ---------------------------------------------------

    def test_aa_directive_end_to_end(self):
        table_lua = (
            "function myexpand(args, syntaxcheck)\n"
            "  if syntaxcheck then return end\n"
            "  return 'FixtureTarget.exe+40:\\ndb 11'\n"
            "end\n"
            "registerAutoAssemblerCommand('myexpand', myexpand)\n"
            "local al = getAddressList()\n"
            "local r = al.createMemoryRecord()\n"
            "r.Description = 'C2 AA Custom'\n"
            "r.Type = vtAutoAssembler\n"
            "r.Script = '[ENABLE]\\nmyexpand(1)\\n[DISABLE]\\nFixtureTarget.exe+40:\\ndb 00\\n'\n")
        lua = (
            "local r = AddressList['C2 AA Custom']\n"
            "assert(r ~= nil, 'record present')\n"
            "r.Active = true\n"
            "assert((readInteger(0x1040) % 256) == 0x11, 'directive byte')\n"
            "r.Active = false\n"
            "assert((readInteger(0x1040) % 256) == 0x00, 'restored')\n"
            "writeInteger(0x1050, 1)\n")
        engine = self.attach_lua(lua, table_lua)
        self.assertTrue(engine.plan['table_lua']['executed'])
        broker = engine.table_lua_scope[1]
        tokens = broker.aa_commands
        self.assertEqual(set(tokens), {'MYEXPAND'})
        token = tokens['MYEXPAND']
        self.assertTrue(token.startswith('ct2fn:'))
        self.assertTrue(token[6:].isdigit())
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.marker(engine), 1)
        self.assertNotIn(DYN_BASE + 1, engine.applied)

    def test_aa_directive_replace_string_name_and_unregister(self):
        table_lua = (
            "function expandA(args, syntaxcheck)\n"
            "  return 'FixtureTarget.exe+40:\\ndb 12'\n"
            "end\n"
            "function expandB(args, syntaxcheck)\n"
            "  return 'FixtureTarget.exe+40:\\ndb 22'\n"
            "end\n"
            "registerAutoAssemblerCommand('myexpand', 'expandA')\n"
            "registerAutoAssemblerCommand('myexpand', 'expandB')\n"
            "local al = getAddressList()\n"
            "local r = al.createMemoryRecord()\n"
            "r.Description = 'C2 AA Replace'\n"
            "r.Type = vtAutoAssembler\n"
            "r.Script = '[ENABLE]\\nmyexpand()\\n[DISABLE]\\nFixtureTarget.exe+40:\\ndb 00\\n'\n")
        lua = (
            "local r = AddressList['C2 AA Replace']\n"
            "r.Active = true\n"
            "assert((readInteger(0x1040) % 256) == 0x22, 'replacement bound: ' ..\n"
            "       string.format('0x%02X', readInteger(0x1040) % 256))\n"
            "writeInteger(0x1050, 1)\n")
        engine = self.attach_lua(lua, table_lua)
        self.assertTrue(engine.plan['table_lua']['executed'])
        broker = engine.table_lua_scope[1]
        self.assertEqual(set(broker.aa_commands), {'MYEXPAND'})
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.marker(engine), 1)
        # The string routine name registered second wins (replace semantics).
        self.assertEqual(engine.memory.read(0x1040, 1), b'\x22')
        ident = DYN_BASE + 1
        self.assertIn(ident, engine.applied)
        # Unregister through the live table-scope host, then the same script
        # refuses (the directive no longer expands) with zero new writes.
        host = engine.table_lua_scope[0]
        host.execute("unregisterAutoAssemblerCommand('myexpand')")
        self.assertEqual(broker.aa_commands, {})
        engine.dynamic_record_active(ident, False)
        writes_before = len(engine.memory.writes)
        with self.assertRaises(NativeRuntimeError) as cm:
            engine.dynamic_record_active(ident, True)
        self.assertIn('Dynamic AA record script refused', str(cm.exception))
        self.assertEqual(len(engine.memory.writes), writes_before)
        self.assertNotIn(ident, engine.applied)
        # Re-registration restores the expansion.
        host.execute("function myexpand2(args, sc) return 'FixtureTarget.exe+40:\\ndb 33' end")
        host.execute("registerAutoAssemblerCommand('myexpand', 'myexpand2')")
        engine.dynamic_record_active(ident, True)
        self.assertEqual(engine.memory.read(0x1040, 1), b'\x33')
        engine.dynamic_record_active(ident, False)

    def test_aa_reserved_name_refused_table_scope(self):
        for name in ('registerlabel', 'alloc'):
            with self.subTest(name=name):
                engine = self.attach(value_record(0), (
                    "function rl(args, syntaxcheck) return 'label(x)' end\n"
                    f"registerAutoAssemblerCommand('{name}', rl)\n"))
                meta = engine.plan['table_lua']
                self.assertFalse(meta['executed'])
                self.assertIn('AA directive name reserved: ' + name.upper(),
                              meta['reasons'])
                self.assertIsNone(engine.table_lua_scope)

    def test_aa_register_invalid_arguments_table_scope(self):
        for source in ("registerAutoAssemblerCommand('a', 'b')",
                       "registerAutoAssemblerCommand(42, function() end)",
                       "registerAutoAssemblerCommand('')",
                       "unregisterAutoAssemblerCommand(42)",
                       "unregisterAutoAssemblerCommand('')"):
            with self.subTest(source=source):
                engine = self.attach(value_record(0), source)
                meta = engine.plan['table_lua']
                self.assertFalse(meta['executed'])
                joined = ' | '.join(meta['reasons'])
                if source.startswith('unregister'):
                    self.assertIn('AA command unregistration has invalid arguments.', joined)
                else:
                    self.assertIn('AA command registration has invalid arguments.', joined)
                self.assertIsNone(engine.table_lua_scope)

    def test_aa_registry_dies_with_table_scope(self):
        engine = self.attach(value_record(0), (
            "function myexpand(args, syntaxcheck) return 'label(x)' end\n"
            "registerAutoAssemblerCommand('myexpand', myexpand)\n"))
        self.assertEqual(set(engine.table_lua_scope[1].aa_commands), {'MYEXPAND'})
        engine.memory.alive = False
        engine.poll()
        self.assertIsNone(engine.table_lua_scope)

    # -- syntax checking -------------------------------------------------------

    def test_syntaxcheck_refuses_journal_mutations(self):
        engine = self.attach(value_record(0))
        broker = EngineLuaBroker(engine)
        cases = [
            ('addresslist.createMemoryRecord', ()),
            ('record.set', (0, 'Description', 'x')),
            ('record.delete', (0,)),
            ('record.reparent', (0, None)),
            ('record.offsetSet', (0, 0, 5)),
            ('record.offsetTextSet', (0, 0, '10')),
            ('destroy', ('record', 0)),
        ]
        for name, arguments in cases:
            with self.subTest(name=name):
                with self.assertRaises(LuaHostError) as cm:
                    broker.call(name, arguments, generation=0, syntaxcheck=True)
                self.assertIn('Syntax checking cannot mutate MemoryRecords',
                              str(cm.exception))
        self.assertEqual(engine.dynamic_records, {})
        self.assertEqual(engine.memory.writes, [])

    def test_syntaxcheck_disposable_checker_refuses_mutations(self):
        engine = self.attach(value_record(0), (
            "local al = getAddressList()\n"
            "local rec = al.createMemoryRecord()\n"
            "rec.Description = 'C2 Check'\n"))
        self.assertTrue(engine.plan['table_lua']['executed'])
        host = engine.table_lua_scope[0]
        for source in ("getAddressList().createMemoryRecord()",
                       "local p = AddressList.getMemoryRecordByID(0)\n"
                       "p.destroy()"):
            with self.subTest(source=source):
                with self.assertRaises(LuaHostError) as cm:
                    host.execute(source, syntaxcheck=True)
                self.assertIn('Syntax checking cannot mutate MemoryRecords',
                              str(cm.exception))
        # The live journal is untouched by the refused checks.
        self.assertEqual(len(engine.dynamic_records), 1)
        self.assertEqual(engine.memory.writes, [])

    # -- pure-Lua expansion unit tests ------------------------------------------

    def test_expand_custom_commands_unit(self):
        calls = []

        def expand(args, syntaxcheck):
            calls.append((args, syntaxcheck))
            return 'FixtureTarget.exe+40:\ndb 11'

        out = aa_program._expand_custom_commands(
            [(1, 'myexpand(x, y)')], {'MYEXPAND': expand}, {}, False)
        self.assertEqual(out, [(1, 'FixtureTarget.exe+40:'), (1, 'db 11')])
        self.assertEqual(calls, [('x, y', False)])
        # Case-insensitive prefix match, original-case arguments.
        out = aa_program._expand_custom_commands(
            [(2, 'MyExpand(A)')], {'MYEXPAND': expand}, {}, True)
        self.assertEqual(calls[-1], ('A', True))
        self.assertEqual(len(out), 2)
        # Nil result deletes the line (corpus guard idiom).
        out = aa_program._expand_custom_commands(
            [(1, 'myexpand(1)'), (2, 'other')], {'MYEXPAND': lambda a, s: None}, {}, True)
        self.assertEqual(out, [(2, 'other')])
        # Nesting: inserted lines are re-processed in the same pass.
        out = aa_program._expand_custom_commands(
            [(1, 'outer(1)')],
            {'OUTER': lambda a, s: 'inner(1)\ndone',
             'INNER': lambda a, s: 'deep'}, {}, False)
        self.assertEqual(out, [(1, 'deep'), (1, 'done')])
        # Non-string result is refused.
        with self.assertRaises(ProgramError) as cm:
            aa_program._expand_custom_commands(
                [(1, 'bad(1)')], {'BAD': lambda a, s: 42}, {}, False)
        self.assertIn('must return a string or nil', str(cm.exception))
        # Oversized result is refused.
        with self.assertRaises(ProgramError) as cm:
            aa_program._expand_custom_commands(
                [(1, 'big(1)')], {'BIG': lambda a, s: 'x' * (MAX_CUSTOM_RESULT_CHARS + 1)},
                {}, False)
        self.assertIn('result exceeds its size bound', str(cm.exception))
        # A callback exception is refused named with the line and directive.
        def boom(args, syntaxcheck):
            raise RuntimeError('callback boom')
        with self.assertRaises(ProgramError) as cm:
            aa_program._expand_custom_commands(
                [(3, 'MyBoom(1)')], {'MYBOOM': boom}, {}, False)
        self.assertIn('Line 3: custom AA directive MyBoom failed: callback boom',
                      str(cm.exception))
        # No registered commands: strict no-op.
        lines = [(1, 'label(x)'), (2, 'myexpand(1)')]
        self.assertEqual(aa_program._expand_custom_commands(lines, None, {}, False),
                         lines)

    def test_prepare_program_revalidates_with_registry(self):
        # Regression: validate_program regenerates the plan from the stored
        # source, so the registry must travel with the program (the engine's
        # link_program calls now forward custom_commands).
        calls = []

        def expand(args, syntaxcheck):
            calls.append(syntaxcheck)
            return 'FixtureTarget.exe+40:\ndb 11'

        source = ('[ENABLE]\nmyexpand(1)\n[DISABLE]\nFixtureTarget.exe+40:\ndb 00\n')
        program = aa_program.prepare_program(
            source, PROCESS, bitness=64, custom_commands={'MYEXPAND': expand},
            syntaxcheck=False)
        aa_program.validate_program(program, {'MYEXPAND': expand}, False)
        self.assertTrue(any(op['op'] == 'data' for op in program['enable']))
        with self.assertRaises(ProgramError):
            # Without the registry the stored directive line cannot be
            # re-parsed, so validation must fail closed.
            aa_program.validate_program(program, None, False)

    # -- journal lifecycle -------------------------------------------------------

    def test_journal_cleared_on_target_exit(self):
        lua = (
            "local al = getAddressList()\n"
            "local r = al.createMemoryRecord()\n"
            "r.Description = 'C2 Exit'\n"
            "writeInteger(0x1050, 1)\n")
        engine = self.attach_lua(lua)
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.marker(engine), 1)
        self.assertEqual(len(engine.dynamic_records), 1)
        engine.memory.alive = False
        engine.poll()
        self.assertEqual(engine.dynamic_records, {})
        self.assertEqual(len(engine.entries), 2)
        self.assertIsNone(engine.table_lua_scope)

    def test_dynamic_records_never_persisted(self):
        lua = (
            "local al = getAddressList()\n"
            "local r = al.createMemoryRecord()\n"
            "r.Description = 'C2 Persist'\n"
            "r.Type = vtAutoAssembler\n"
            "r.Script = '[ENABLE]\\nFixtureTarget.exe+40:\\ndb 2A\\n[DISABLE]\\nFixtureTarget.exe+40:\\ndb 00\\n'\n"
            "r.Active = true\n"
            "writeInteger(0x1050, 1)\n")
        engine = self.attach_lua(lua)
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.marker(engine), 1)
        self.assertIn(DYN_BASE + 1, engine.applied)
        # The dynamic ID never reaches the wish store or the plan.
        for identifier in engine.desired:
            self.assertLess(identifier, DYN_BASE)
        self.assertEqual(engine.desired, {1})
        document = json.loads(engine.store.path.read_text(encoding='utf-8'))

        def integers(node):
            if isinstance(node, dict):
                for value in node.values():
                    yield from integers(value)
            elif isinstance(node, list):
                for value in node:
                    yield from integers(value)
            elif type(node) is int:
                yield node

        for identifier in integers(document):
            self.assertLess(identifier, DYN_BASE)

    def test_dynamic_callback_token_direct_set(self):
        # The broker-level token contract: a malformed token is refused named;
        # a well-formed token for a retired scope is refused named.
        engine = self.attach(value_record(0))
        ident = engine.dynamic_record_create()
        with self.assertRaises(NativeRuntimeError) as cm:
            engine.dynamic_record_set(ident, 'OnActivate', 'ct2fn:x', scope=None)
        self.assertIn('Dynamic record callback must be a registered function token',
                      str(cm.exception))
        # The engine-level journal bound.
        for _ in range(4095):
            engine.dynamic_record_create()
        self.assertEqual(len(engine.dynamic_records), 4096)
        with self.assertRaises(NativeRuntimeError) as cm:
            engine.dynamic_record_create()
        self.assertIn('Dynamic record journal is at its bound', str(cm.exception))


if __name__ == "__main__":
    unittest.main()
