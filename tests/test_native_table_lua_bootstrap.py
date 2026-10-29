"""WP-41 (phase 1): the read-only per-table Lua bootstrap contract.

Covers the static surface (top-level global extraction, record dependency
intersection, the named refusal taxonomy, strict plan metadata) and the
end-to-end runtime contract on synthetic tables: one bootstrap run per
confirmed attach, record-and-continue refusals, dependent-record gating
with the exact named reason, non-dependent records unaffected, legacy
plans derived at attach, forged metadata rejected by both plan gates, and
scope retirement on target exit and close.

No corpus files are loaded; every table is synthetic and written per test.
"""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
import xml.sax.saxutils

from test_native_engine import FIXTURE, FakeMemory
from test_native_engine_code import Coordinator
from ct2trainer.native.compiler import NativeCompileError, compile_table, validate_plan
from ct2trainer.native.engine import NativeRuntimeError, TrainerEngine
from ct2trainer.native.lua_bootstrap import (
    LuaBootstrapError,
    MAX_TABLE_LUA_REASON_CHARS,
    MAX_TABLE_LUA_REASONS,
    TABLE_LUA_TOP_LEVEL_FAILURE,
    record_table_lua_references,
    table_lua_bootstrap_gate,
    table_lua_refusal_reason,
    table_top_level_globals,
    validate_table_lua_meta,
)
from ct2trainer.native.lua_host import LuaHostError, TableLuaBroker


PROCESS = "FixtureTarget.exe"


def escape(text: str) -> str:
    return xml.sax.saxutils.escape(text)


def table_xml(body: str, lua_script: str) -> str:
    return ('<CheatTable CheatEngineTableVersion="45"><LuaScript>'
            + lua_script + '</LuaScript><CheatEntries>' + body
            + '</CheatEntries></CheatTable>')


def value_record(entry_id: int, address: str = "1000") -> str:
    return (f'<CheatEntry><ID>{entry_id}</ID><Description>Value {entry_id}</Description>'
            f'<VariableType>4 Bytes</VariableType><Address>{address}</Address></CheatEntry>')


def lua_record(entry_id: int, script: str) -> str:
    return (f'<CheatEntry><ID>{entry_id}</ID><Description>"Record {entry_id}"</Description>'
            f'<VariableType>Auto Assembler Script</VariableType>'
            f'<AssemblerScript>{escape(script)}</AssemblerScript></CheatEntry>')


class Memory(FakeMemory):
    @property
    def identity(self):
        return self.pid, self.creation_time

    def _range(self, address, size):
        if not self.base <= address or address + size > self.base + len(self.data):
            raise ValueError('Outside owned fixture memory')

    def is_executable(self, address, size):
        return False


class TableTopLevelGlobalsTests(unittest.TestCase):
    """Static extraction of the table-level globals records can depend on."""

    def test_bare_assignments_create_globals_in_order(self):
        source = "alpha = readInteger(0x1040)\nbeta, gamma = 1, 2\ndelta = 3\n"
        self.assertEqual(table_top_level_globals(source),
                         ('alpha', 'beta', 'gamma', 'delta'))

    def test_locals_and_keywords_do_not_create_globals(self):
        source = "local alpha = 1\nlocal beta, gamma = 1, 2\nend = 3\n"
        self.assertEqual(table_top_level_globals(source), ())

    def test_function_sugar_creates_a_global_but_local_sugar_does_not(self):
        source = ("function helper() return 1 end\n"
                  "local function privateHelper() return 2 end\n")
        self.assertEqual(table_top_level_globals(source), ('helper',))

    def test_dotted_function_target_is_not_a_bare_global(self):
        # 'function t.helper(...)' only writes a table field: no bare global.
        self.assertEqual(table_top_level_globals("function t.helper() end\n"), ())

    def test_colon_sugar_conservatively_records_the_object(self):
        # 'function obj:method(...)' names the object, so it is tracked.
        self.assertEqual(table_top_level_globals("function obj:method() end\n"), ('obj',))

    def test_assignments_inside_bodies_are_not_globals(self):
        source = ("function outer() local inner = 1 end\n"
                  "top = 2\n"
                  "function second()\n"
                  "  inner = 3\n"
                  "end\n")
        self.assertEqual(table_top_level_globals(source), ('outer', 'top', 'second'))

    def test_same_line_function_closes_its_own_depth(self):
        self.assertEqual(table_top_level_globals("boxed = function() end\nafter = 1\n"),
                         ('boxed', 'after'))

    def test_repeated_assignment_is_listed_once_and_comments_are_ignored(self):
        source = "alpha = 1\nalpha = 2\n-- alpha = 3\n\n"
        self.assertEqual(table_top_level_globals(source), ('alpha',))

    def test_non_string_source_is_rejected(self):
        with self.assertRaises(LuaBootstrapError):
            table_top_level_globals(7)


class RecordTableLuaReferenceTests(unittest.TestCase):
    """Case-sensitive intersection of record identifiers with table globals."""

    def test_bare_identifiers_are_intersected_and_sorted(self):
        source = "local total = tblValue + tblHelper()\nprint(total)\n"
        self.assertEqual(record_table_lua_references(source, ('tblValue', 'tblHelper')),
                         ('tblHelper', 'tblValue'))

    def test_names_only_in_comments_or_strings_do_not_count(self):
        source = '-- tblValue\nprint("tblHelper")\nreturn 1\n'
        self.assertEqual(record_table_lua_references(source, ('tblValue', 'tblHelper')), ())

    def test_case_mismatch_is_not_a_reference(self):
        self.assertEqual(record_table_lua_references('tblvalue = 1', ('tblValue',)), ())

    def test_empty_global_set_has_no_references(self):
        self.assertEqual(record_table_lua_references('tblValue = 1', ()), ())


class RefusalReasonTests(unittest.TestCase):
    """The exact WP-41 named refusal strings per API class."""

    def test_named_classes_carry_their_exact_reason(self):
        expected = {
            'writeInteger': 'Table Lua uses a write API: writeInteger.',
            'writeSmallInteger': 'Table Lua uses a write API: writeSmallInteger.',
            'writeQword': 'Table Lua uses a write API: writeQword.',
            'writeFloat': 'Table Lua uses a write API: writeFloat.',
            'writeDouble': 'Table Lua uses a write API: writeDouble.',
            'writeString': 'Table Lua uses a write API: writeString.',
            'writeBytes': 'Table Lua uses a write API: writeBytes.',
            'record.set': 'Table Lua uses a write API: record.set.',
            'registerSymbol': 'Table Lua writes the symbol table: registerSymbol.',
            'unregisterSymbol': 'Table Lua writes the symbol table: unregisterSymbol.',
            'autoAssemble': 'Table Lua executes assembler patches: autoAssemble.',
            'executeCodeEx': 'Table Lua invokes target code: executeCodeEx.',
            'mono_invoke_method': 'Table Lua invokes target code: mono_invoke_method.',
            'showMessage': 'Table Lua registers a UI callback: showMessage.',
            'luaEngine.close': 'Table Lua registers a UI callback: luaEngine.close.',
            'luaEngine.menuClick': 'Table Lua registers a UI callback: luaEngine.menuClick.',
            'attachProcess': 'Table Lua mutates host session state: attachProcess.',
            'detachProcess': 'Table Lua mutates host session state: detachProcess.',
            'LaunchMonoDataCollector': 'Table Lua mutates host session state: LaunchMonoDataCollector.',
            'speedhack_setSpeed': 'Table Lua mutates host session state: speedhack_setSpeed.',
        }
        for name, reason in expected.items():
            with self.subTest(name=name):
                self.assertEqual(table_lua_refusal_reason(name), reason)

    def test_unclassified_names_fall_back_to_the_unsupported_api_reason(self):
        for name in ('createTimer', 'createThread', 'weirdUnknownApi'):
            with self.subTest(name=name):
                self.assertEqual(
                    table_lua_refusal_reason(name),
                    'Table Lua calls an unsupported API: ' + name + '.')

    def test_empty_or_non_string_names_are_rejected(self):
        for bad in ('', None, 7):
            with self.subTest(bad=repr(bad)):
                with self.assertRaises(LuaBootstrapError):
                    table_lua_refusal_reason(bad)


class ValidateTableLuaMetaTests(unittest.TestCase):
    """Strict plan["table_lua"] shape shared by both plan gates."""

    def test_canonical_shapes_are_accepted(self):
        meta = {'executed': True, 'reasons': [], 'record_scripts_inactive': 0}
        self.assertIs(validate_table_lua_meta(meta), meta)
        meta = {'executed': False,
                'reasons': ['Table Lua uses a write API: writeInteger.'],
                'record_scripts_inactive': 2}
        self.assertIs(validate_table_lua_meta(meta), meta)

    def test_executed_bootstrap_cannot_carry_reasons(self):
        with self.assertRaises(LuaBootstrapError):
            validate_table_lua_meta(
                {'executed': True, 'reasons': ['x'], 'record_scripts_inactive': 0})

    def test_shape_violations_are_rejected(self):
        valid = {'executed': False, 'reasons': [], 'record_scripts_inactive': 0}
        bad_shapes = (
            'not a dict',                                   # non-dict
            42,                                             # non-dict
            {**valid, 'extra': 1},                          # extra key
            {k: v for k, v in valid.items() if k != 'reasons'},  # missing key
            {**valid, 'executed': 1},                       # non-bool flag
            {**valid, 'reasons': 'nope'},                    # non-list reasons
            {**valid, 'reasons': [None]},                    # non-string reason
            {**valid, 'reasons': ['']},                      # empty reason
            {**valid, 'reasons': ['x' * (MAX_TABLE_LUA_REASON_CHARS + 1)]},
            {**valid, 'reasons': ['x'] * (MAX_TABLE_LUA_REASONS + 1)},
            {**valid, 'record_scripts_inactive': -1},       # negative count
            {**valid, 'record_scripts_inactive': 1.0},      # non-int count
            {**valid, 'record_scripts_inactive': True},     # bool is not int
        )
        for bad in bad_shapes:
            with self.subTest(bad=repr(bad)[:70]):
                with self.assertRaises(LuaBootstrapError):
                    validate_table_lua_meta(bad)


class TableLuaBootstrapGateTests(unittest.TestCase):
    """The record-activation gate against the bootstrap outcome."""

    def test_clean_bootstrap_replays_into_dependent_records(self):
        self.assertEqual(table_lua_bootstrap_gate(
            'tblValue = 1\n', 'writeInteger(0x1080,tblValue)',
            {'executed': True, 'reasons': [], 'record_scripts_inactive': 1}),
            ('replay', None))

    def test_legacy_plan_without_meta_keeps_the_pre_bootstrap_replay(self):
        self.assertEqual(table_lua_bootstrap_gate('tblValue = 1\n', 'x = tblValue', None),
                         ('replay', None))
        self.assertEqual(table_lua_bootstrap_gate('', 'x = 1', None), ('skip', None))

    def test_refused_bootstrap_blocks_dependent_records_with_the_named_reason(self):
        decision, reason = table_lua_bootstrap_gate(
            'tblDefined = 7\ntblOther = 8\nwriteInteger(0x1080,1)\n',
            'writeInteger(0x1080, tblDefined + tblOther)',
            {'executed': False,
             'reasons': ['Table Lua uses a write API: writeInteger.'],
             'record_scripts_inactive': 1})
        self.assertEqual(decision, 'block')
        self.assertEqual(reason,
            'Table Lua was not executed on load; record script references '
            'table-level globals tblDefined, tblOther.')

    def test_single_reference_uses_the_singular_form(self):
        decision, reason = table_lua_bootstrap_gate(
            'tblDefined = 7\nwriteInteger(0x1080,1)\n', 'x = tblDefined',
            {'executed': False, 'reasons': ['r'], 'record_scripts_inactive': 1})
        self.assertEqual(decision, 'block')
        self.assertEqual(reason,
            'Table Lua was not executed on load; record script references '
            'table-level global tblDefined.')

    def test_non_dependent_record_skips_the_replay(self):
        self.assertEqual(table_lua_bootstrap_gate(
            'tblDefined = 7\nwriteInteger(0x1080,1)\n', 'writeInteger(0x1080, 1)',
            {'executed': False, 'reasons': ['r'], 'record_scripts_inactive': 0}),
            ('skip', None))


class TableLuaBrokerUnitTests(unittest.TestCase):
    """Direct broker level: refusals are recorded, continued, and bounded."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.memory = Memory()
        self.engine = TrainerEngine(compile_table(FIXTURE, PROCESS),
                                    state_dir=self.root / 'state',
                                    process_lock_dir=self.root / 'shared',
                                    memory_factory=lambda name: self.memory,
                                    hook_coordinator=Coordinator())
        self.engine.poll()
        self.addCleanup(self.engine.close)

    def test_refused_calls_are_recorded_in_order_and_answered_nil(self):
        broker = TableLuaBroker(self.engine)
        self.assertIsNone(broker.call('writeInteger', (0x1040, 1),
                                      generation=broker.generation, syntaxcheck=False))
        self.assertIsNone(broker.call('record.set', ('ID', 7),
                                      generation=broker.generation, syntaxcheck=False))
        self.assertEqual(broker.reasons,
                         ['Table Lua uses a write API: writeInteger.',
                          # RT-5 item C2: record.set routes to the engine
                          # dispatch; a malformed call records the exact
                          # engine named refusal (the WP-41 taxonomy reason
                          # for 'record.set' stays pinned above).
                          'MemoryRecord set requires an identifier, key and value'])

    def test_read_only_names_are_forwarded_to_the_wrapped_dispatch(self):
        broker = TableLuaBroker(self.engine)
        self.assertEqual(broker.call('readInteger', (0x1010,),
                                     generation=broker.generation, syntaxcheck=False), 1234)
        self.assertEqual(broker.reasons, [])

    def test_reasons_are_bounded(self):
        # WP-54 (b): registerSymbol/unregisterSymbol no longer produce table
        # scope refusal reasons (they are admitted); a write-API call keeps
        # pinning the bound with its exact named reason.
        broker = TableLuaBroker(self.engine)
        for _ in range(MAX_TABLE_LUA_REASONS + 5):
            broker.call('writeInteger', (0x1040, 1),
                        generation=broker.generation, syntaxcheck=False)
        self.assertEqual(len(broker.reasons), MAX_TABLE_LUA_REASONS)
        self.assertTrue(all(reason == 'Table Lua uses a write API: writeInteger.'
                          for reason in broker.reasons))

    def test_generation_and_invalidation_delegate_to_the_wrapped_dispatch(self):
        # The host compares broker.generation against its own generation, so
        # the wrapper must track the wrapped dispatch's generation exactly.
        broker = TableLuaBroker(self.engine)
        self.assertEqual(broker.generation, 0)
        self.assertEqual(broker.generation, broker.inner.generation)
        broker.invalidate()
        self.assertEqual(broker.generation, 1)
        self.assertEqual(broker.generation, broker.inner.generation)


class TableLuaBootstrapRuntimeTests(unittest.TestCase):
    """End-to-end contract on synthetic tables (no corpus files)."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.memory = None
        self.engines = []

    def tearDown(self):
        if self.memory is not None and not self.memory.closed:
            self.memory.alive = False
        for engine in self.engines:
            if not engine.closed:
                engine.poll()
                engine.close()

    def attach(self, lua_script, body=None):
        path = self.root / "bootlua.CT"
        path.write_text(table_xml(value_record(0) if body is None else body,
                                  lua_script), encoding="utf-8")
        plan = compile_table(path, PROCESS)
        self.memory = Memory()
        # A fresh state dir per engine: a subtest loop may hold several live
        # engines in one test, and the state lock is per state dir.
        engine = TrainerEngine(plan, state_dir=self.root / f'state{len(self.engines)}',
                               process_lock_dir=self.root / f'shared{len(self.engines)}',
                               memory_factory=lambda name: self.memory,
                               hook_coordinator=Coordinator())
        self.engines.append(engine)
        engine.poll()
        return engine

    INDEPENDENT_RECORD = ('[ENABLE]\n{$lua}\nif not syntaxcheck then '
                          'writeInteger(0x1080, 5) end\n{$asm}\n'
                          '[DISABLE]\n{$lua}\nassert(readInteger(0x1080)==5)\n{$asm}\n')

    def test_clean_bootstrap_executes_once_and_exposes_globals_to_records(self):
        plan_body = (value_record(0) + lua_record(1,
            '[ENABLE]\n{$lua}\nif not syntaxcheck then\n'
            '  writeInteger(0x1080, tblValue + tblHelper())\n'
            'end\n{$asm}\n'
            '[DISABLE]\n{$lua}\nassert(readInteger(0x1080)==46)\n{$asm}\n'))
        path = self.root / "bootlua.CT"
        path.write_text(table_xml(plan_body,
            'tblValue = readInteger(0x1040)\n'
            'function tblHelper() return tblValue end\n'), encoding="utf-8")
        plan = compile_table(path, PROCESS)
        self.assertEqual(plan['table_lua'],
                         {'executed': False, 'reasons': [], 'record_scripts_inactive': 1})
        self.memory = Memory()
        self.memory.data[64:68] = (23).to_bytes(4, 'little')   # 0x1040 = 23
        engine = TrainerEngine(plan, state_dir=self.root / 'state',
                               process_lock_dir=self.root / 'shared',
                               memory_factory=lambda name: self.memory,
                               hook_coordinator=Coordinator())
        self.engines.append(engine)
        engine.poll()
        # One bootstrap run per confirmed attach: the read-only source
        # executes and the scope persists for the table's lifetime.
        self.assertEqual(plan['table_lua'],
                         {'executed': True, 'reasons': [], 'record_scripts_inactive': 1})
        self.assertIsNotNone(engine.table_lua_scope)
        self.assertEqual(self.memory.read(0x1080, 4), bytes(4))
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.memory.read(0x1080, 4), (46).to_bytes(4, 'little'))
        self.assertFalse(engine.toggle(1, False))
        self.assertEqual(self.memory.read(0x1080, 4), bytes(4))
        self.assertFalse(engine.blocked)

    def test_refusal_classes_are_recorded_exactly_and_records_stay_unaffected(self):
        # WP-54 (b): the former registerSymbol case is admitted in the table
        # scope now (table-owned symbols); its admission contract is pinned
        # by tests/test_native_table_lua_phase2.py.
        cases = (
            ('writeInteger(0x1080, 42)', 'Table Lua uses a write API: writeInteger.'),
            ('autoAssemble("1000: dd 1")', 'Table Lua executes assembler patches: autoAssemble.'),
            ('executeCodeEx(0x1000, {})', 'Table Lua invokes target code: executeCodeEx.'),
            ('showMessage("hello", "title")', 'Table Lua registers a UI callback: showMessage.'),
            ('attachProcess(123)', 'Table Lua mutates host session state: attachProcess.'),
        )
        for source, reason in cases:
            with self.subTest(source=source):
                engine = self.attach(source, body=value_record(0) +
                                     lua_record(1, self.INDEPENDENT_RECORD))
                self.assertEqual(engine.plan['table_lua'],
                                 {'executed': False, 'reasons': [reason],
                                  'record_scripts_inactive': 0})
                self.assertIsNone(engine.table_lua_scope)
                self.assertEqual(self.memory.read(0x1080, 4), bytes(4))
                self.assertTrue(engine.toggle(1, True))
                self.assertEqual(self.memory.read(0x1080, 4), (5).to_bytes(4, 'little'))
                self.assertFalse(engine.toggle(1, False))
                self.assertEqual(self.memory.read(0x1080, 4), bytes(4))
                self.assertFalse(engine.blocked)

    def test_repeated_refusals_are_recorded_in_order_and_execution_continues(self):
        # Three identical write-API calls: every refusal is recorded (the
        # call is answered with nil, never raised) and the run still fails
        # soft with the ordered list.
        engine = self.attach('writeInteger(0x1040, 1)\n'
                             'writeInteger(0x1041, 2)\n'
                             'writeInteger(0x1042, 3)\n')
        reason = 'Table Lua uses a write API: writeInteger.'
        self.assertEqual(engine.plan['table_lua'],
                         {'executed': False, 'reasons': [reason] * 3,
                          'record_scripts_inactive': 0})
        self.assertIsNone(engine.table_lua_scope)
        self.assertEqual(self.memory.read(0x1040, 4), bytes(4))
        self.assertFalse(engine.blocked)

    def test_pcall_wrapped_refusal_is_recorded_and_following_statements_run(self):
        # pcall never consumes the refusal (it is answered with nil); the
        # later top-level error proves the source kept running.
        engine = self.attach('pcall(function() writeInteger(0x1080, 42) end)\n'
                             'survivor = error("survivor ran")\n')
        reasons = engine.plan['table_lua']['reasons']
        self.assertEqual(reasons[0], 'Table Lua uses a write API: writeInteger.')
        self.assertEqual(len(reasons), 2)
        self.assertTrue(reasons[1].startswith(TABLE_LUA_TOP_LEVEL_FAILURE), reasons[1])
        self.assertIn('survivor ran', reasons[1])
        self.assertFalse(engine.plan['table_lua']['executed'])
        self.assertIsNone(engine.table_lua_scope)
        self.assertEqual(self.memory.read(0x1080, 4), bytes(4))

    def test_genuine_top_level_failures_carry_the_named_prefix(self):
        for source in ('undefinedFunctionCall(1)', 'function broken( end'):
            with self.subTest(source=source):
                engine = self.attach(source)
                meta = engine.plan['table_lua']
                self.assertFalse(meta['executed'])
                self.assertEqual(len(meta['reasons']), 1)
                self.assertTrue(meta['reasons'][0].startswith(TABLE_LUA_TOP_LEVEL_FAILURE),
                                meta['reasons'][0])
                self.assertIsNone(engine.table_lua_scope)
                self.assertFalse(engine.blocked)

    def test_dependent_record_is_blocked_with_the_exact_named_reason(self):
        engine = self.attach('tblDefined = 7\nwriteInteger(0x1080, 1)\n',
                             body=value_record(0) + lua_record(1,
            '[ENABLE]\n{$lua}\nif not syntaxcheck then '
            'writeInteger(0x1080, tblDefined) end\n{$asm}\n'
            '[DISABLE]\n{$lua}\nassert(readInteger(0x1080)==7)\n{$asm}\n'))
        self.assertEqual(engine.plan['table_lua'],
                         {'executed': False,
                          'reasons': ['Table Lua uses a write API: writeInteger.'],
                          'record_scripts_inactive': 1})
        self.assertIsNone(engine.table_lua_scope)
        with self.assertRaises(NativeRuntimeError) as caught:
            engine.toggle(1, True)
        self.assertIn('Table Lua was not executed on load; record script '
                      'references table-level global tblDefined.',
                      str(caught.exception))
        self.assertEqual(self.memory.read(0x1080, 4), bytes(4))
        self.assertFalse(engine.applied)
        self.assertFalse(engine.desired)
        self.assertFalse(engine.lua_activations)
        self.assertFalse(engine.blocked)

    def test_non_dependent_record_skips_the_replay_and_runs(self):
        engine = self.attach('tblDefined = 7\nwriteInteger(0x1080, 1)\n',
                             body=value_record(0) + lua_record(1,
            '[ENABLE]\n{$lua}\nif not syntaxcheck then '
            'writeInteger(0x1080, 9) end\n{$asm}\n'
            '[DISABLE]\n{$lua}\nassert(readInteger(0x1080)==9)\n{$asm}\n'))
        self.assertEqual(engine.plan['table_lua'],
                         {'executed': False,
                          'reasons': ['Table Lua uses a write API: writeInteger.'],
                          'record_scripts_inactive': 0})
        self.assertIsNone(engine.table_lua_scope)
        self.assertTrue(engine.toggle(1, True))
        # The refused bootstrap was not replayed into the record scope: the
        # record's own write is the only write the record produced.
        self.assertEqual(self.memory.read(0x1080, 4), (9).to_bytes(4, 'little'))
        self.assertEqual(
            [raw for address, raw in self.memory.writes if address == 0x1080],
            [(9).to_bytes(4, 'little')])
        self.assertFalse(engine.toggle(1, False))
        self.assertEqual(self.memory.read(0x1080, 4), bytes(4))

    def test_bootstrap_reruns_on_each_confirmed_attach(self):
        engine = self.attach('tblValue = readInteger(0x1040)\n')
        first_scope = engine.table_lua_scope
        self.assertIsNotNone(first_scope)
        self.assertEqual(engine.plan['table_lua'],
                         {'executed': True, 'reasons': [], 'record_scripts_inactive': 0})
        self.memory.alive = False
        engine.poll()
        self.assertIsNone(engine.table_lua_scope)
        self.memory = Memory(pid=234, creation_time=567)
        engine.poll()
        self.assertIsNotNone(engine.table_lua_scope)
        self.assertIsNot(first_scope, engine.table_lua_scope)
        self.assertEqual(engine.plan['table_lua'],
                         {'executed': True, 'reasons': [], 'record_scripts_inactive': 0})

    def test_scope_is_retired_on_close(self):
        engine = self.attach('tblValue = readInteger(0x1040)\n')
        self.assertIsNotNone(engine.table_lua_scope)
        self.assertTrue(engine.close())
        self.assertIsNone(engine.table_lua_scope)

    def test_legacy_plan_without_table_lua_derives_metadata_at_attach(self):
        body = (value_record(0) + lua_record(1,
            '[ENABLE]\n{$lua}\nif not syntaxcheck then '
            'writeInteger(0x1080, tblValue) end\n{$asm}\n'
            '[DISABLE]\n{$lua}\nassert(readInteger(0x1080)==3)\n{$asm}\n'))
        path = self.root / "legacy.CT"
        path.write_text(table_xml(body, 'tblValue = 3\nweirdRuntimeCall()\n'),
                        encoding="utf-8")
        plan = compile_table(path, PROCESS)
        self.assertEqual(plan['table_lua']['record_scripts_inactive'], 1)
        del plan['table_lua']
        validate_plan(plan)  # legacy plans without the key stay tolerated
        self.memory = Memory()
        engine = TrainerEngine(plan, state_dir=self.root / 'state',
                               process_lock_dir=self.root / 'shared',
                               memory_factory=lambda name: self.memory,
                               hook_coordinator=Coordinator())
        self.engines.append(engine)
        engine.poll()
        # The engine derives the static count with the compiler's algorithm and
        # fills the runtime outcome: the undefined call fails the bootstrap.
        self.assertEqual(plan['table_lua']['record_scripts_inactive'], 1)
        self.assertFalse(plan['table_lua']['executed'])
        self.assertEqual(len(plan['table_lua']['reasons']), 1)
        reason = plan['table_lua']['reasons'][0]
        self.assertTrue(reason.startswith(TABLE_LUA_TOP_LEVEL_FAILURE), reason)
        self.assertIn('weirdRuntimeCall', reason)
        self.assertIsNone(engine.table_lua_scope)


class ForgedTableLuaMetaTests(unittest.TestCase):
    """Both plan gates reject forged plan["table_lua"] metadata."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.path = self.root / "forge.CT"
        self.memory = None
        self.engines = []

    def tearDown(self):
        if self.memory is not None and not self.memory.closed:
            self.memory.alive = False
        for engine in self.engines:
            if not engine.closed:
                engine.poll()
                engine.close()

    def plan_with_lua(self, lua_script, body=None):
        self.path.write_text(table_xml(value_record(0) if body is None else body,
                                       lua_script), encoding="utf-8")
        return compile_table(self.path, PROCESS)

    def engine_gate_rejects(self, plan):
        self.memory = Memory()
        with self.assertRaises(NativeRuntimeError):
            TrainerEngine(plan, state_dir=self.root / 'must-not-exist',
                          process_lock_dir=self.root / 'shared',
                          memory_factory=lambda name: self.memory,
                          hook_coordinator=Coordinator())
        self.assertFalse((self.root / 'must-not-exist').exists())

    def test_executed_with_reasons_is_rejected_by_both_gates(self):
        plan = self.plan_with_lua('function helper() return 1 end')
        plan['table_lua'] = {'executed': True,
                             'reasons': ['Table Lua uses a write API: writeInteger.'],
                             'record_scripts_inactive': 0}
        # Shape violations surface as the bootstrap module's own ValueError
        # at the compiler gate (same convention as validate_lua_bootstrap);
        # the engine gate wraps it into a runtime error.
        with self.assertRaises(LuaBootstrapError):
            validate_plan(plan)
        self.engine_gate_rejects(plan)

    def test_forged_inactive_count_is_rederived_and_rejected_by_both_gates(self):
        plan = self.plan_with_lua('tblValue = 3\n', body=value_record(0) +
                                  lua_record(1, '[ENABLE]\n{$lua}\nx = tblValue\n{$asm}\n'))
        self.assertEqual(plan['table_lua']['record_scripts_inactive'], 1)
        plan['table_lua']['record_scripts_inactive'] = 0
        with self.assertRaises(NativeCompileError):
            validate_plan(plan)
        self.engine_gate_rejects(plan)

    def test_extra_keys_are_rejected_by_both_gates(self):
        plan = self.plan_with_lua('function helper() return 1 end')
        plan['table_lua']['extra'] = 1
        with self.assertRaises(LuaBootstrapError):
            validate_plan(plan)
        self.engine_gate_rejects(plan)

    def test_table_lua_without_bootstrap_source_is_rejected_by_both_gates(self):
        # A table without LuaScript carries no bootstrap; claiming table-Lua
        # metadata for it is forged.
        self.path.write_text('<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
                             + value_record(0) + '</CheatEntries></CheatTable>',
                             encoding="utf-8")
        plan = compile_table(self.path, PROCESS)
        self.assertNotIn('lua_bootstrap', plan)
        self.assertNotIn('table_lua', plan)
        plan['table_lua'] = {'executed': False, 'reasons': [],
                             'record_scripts_inactive': 0}
        with self.assertRaises(NativeCompileError):
            validate_plan(plan)
        self.engine_gate_rejects(plan)

    def test_oversized_reason_list_is_rejected_by_both_gates(self):
        plan = self.plan_with_lua('function helper() return 1 end')
        plan['table_lua'] = {'executed': False,
                             'reasons': ['x'] * (MAX_TABLE_LUA_REASONS + 1),
                             'record_scripts_inactive': 0}
        with self.assertRaises(LuaBootstrapError):
            validate_plan(plan)
        self.engine_gate_rejects(plan)

    def test_non_boolean_executed_flag_is_rejected_by_both_gates(self):
        plan = self.plan_with_lua('function helper() return 1 end')
        plan['table_lua'] = {'executed': 1, 'reasons': [], 'record_scripts_inactive': 0}
        with self.assertRaises(LuaBootstrapError):
            validate_plan(plan)
        self.engine_gate_rejects(plan)


if __name__ == '__main__':
    unittest.main()
