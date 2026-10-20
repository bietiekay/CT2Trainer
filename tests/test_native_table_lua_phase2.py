"""WP-54 (GC-E17): table-Lua phase 2 — persistent scheduler + table-scoped
symbols.

Covers the design contract from plans/reference-closure-continuation.md:

- (a)  persistent ``createTimer``: the table-scope timer is live for the
       attach lifetime (ticked by the existing poll loop) and dies with the
       scope retirement;
- (a') scheduler-free record-scope replay: the table-source replay into a
       record helper scope binds createTimer/createThread to inert stubs
       (property assignment stored, destroy/terminate no-op, callbacks never
       fire) while target-memory mutation stays refused;
- (b)  table-scoped registerSymbol/unregisterSymbol: the plan field
       ``table_lua_symbols`` (casefold-sorted list, residual rule, emitted
       only when non-empty) is re-derived byte-exactly from
       ``plan["lua_bootstrap"]["source"]`` by BOTH plan gates and forged
       lists are refused;
- (c)  consumer resolution through table symbols without dependency_ids;
- (d)  inverted teardown order: record scopes retire leaves-first, the
       table scope retires last and releases its symbols exactly once
       (event-trace proof, WP-37 style);
- (e)  UDS reseed on every confirmed attach, with the table-scope
       registerSymbol keeping CE order over the UDS seed.

No corpus files are loaded; every table is synthetic and written per test,
mirroring the case-29/case-30 draft shapes (persistent table timer +
table-scoped symbol + table global, UDS residual).
"""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
import xml.sax.saxutils

from test_native_engine import FakeMemory
from test_native_engine_code import Coordinator
from ct2trainer.native.compiler import (NativeCompileError, compile_table,
                                        validate_plan)
from ct2trainer.native.engine import (NativeRuntimeError, TrainerEngine,
                                      validate_plan as validate_runtime_plan)
from ct2trainer.native.lua_host import LuaHostError
from ct2trainer.native.lua_symbol_providers import (MAX_PROVIDERS,
                                                    extract_table_lua_symbols)


PROCESS = "FixtureTarget.exe"


def escape(text: str) -> str:
    return xml.sax.saxutils.escape(text)


def table_xml(body: str, lua_script: str = "", uds: str = "") -> str:
    parts = ['<CheatTable CheatEngineTableVersion="45">']
    if lua_script:
        parts.append('<LuaScript>' + lua_script + '</LuaScript>')
    parts.append('<CheatEntries>' + body + '</CheatEntries>')
    if uds:
        parts.append(uds)
    parts.append('</CheatTable>')
    return ''.join(parts)


def value_record(entry_id: int, address: str) -> str:
    return (f'<CheatEntry><ID>{entry_id}</ID>'
            f'<Description>Value {entry_id}</Description>'
            f'<VariableType>4 Bytes</VariableType>'
            f'<Address>{escape(address)}</Address></CheatEntry>')


def script_record(entry_id: int, script: str) -> str:
    return (f'<CheatEntry><ID>{entry_id}</ID>'
            f'<Description>Script {entry_id}</Description>'
            f'<VariableType>Auto Assembler Script</VariableType>'
            f'<AssemblerScript>{escape(script)}</AssemblerScript></CheatEntry>')


def alloc_record(entry_id: int, symbol: str) -> str:
    """A supported allocation-only script record that provides one symbol."""
    script = (f'[ENABLE]\nalloc({symbol},64)\nregistersymbol({symbol})\n'
              f'[DISABLE]\nunregistersymbol({symbol})\ndealloc({symbol})')
    return script_record(entry_id, script)


def uds_section(*entries: str) -> str:
    return "<UserdefinedSymbols>" + "".join(entries) + "</UserdefinedSymbols>"


def uds_entry(name: str, address: str) -> str:
    return (f"<SymbolEntry><Name>{escape(name)}</Name>"
            f"<Address>{escape(address)}</Address></SymbolEntry>")


CASE29_LUA = ('table_timer=createTimer(nil,true)\n'
              'table_timer.OnTimer=function() '
              'table_tick_read=readInteger(0x10C0) end\n'
              'table_timer.Interval=500\n'
              "registerSymbol('SynthTableSym29', 0x1040)\n"
              "synthTableGlobal29 = 'SynthTableGlobal29'\n")


class Memory(FakeMemory):
    """FakeMemory with the engine Lua surface plus a write-event trace."""

    def __init__(self, pid: int = 123, creation_time: int = 456):
        super().__init__(pid=pid, creation_time=creation_time)
        self.events = []

    @property
    def identity(self):
        return self.pid, self.creation_time

    def _range(self, address, size):
        if not self.base <= address or address + size > self.base + len(self.data):
            raise ValueError('Outside owned fixture memory')

    def is_executable(self, address, size):
        return False

    def write(self, address, raw):
        self.events.append(('write', address))
        return super().write(address, raw)


class CountingSymbols(dict):
    """Symbol table that records every removal, for the exactly-once proof."""

    def __init__(self, events=None):
        super().__init__()
        self.removed = []
        self.events = events

    def _record(self, key):
        self.removed.append(key)
        if self.events is not None:
            self.events.append(('symbol-removed', key))

    def __delitem__(self, key):
        super().__delitem__(key)
        self._record(key)

    def pop(self, key, *default):
        try:
            value = super().pop(key)
        except KeyError:
            if default:
                return default[0]
            raise
        self._record(key)
        return value


class EngineHarness(unittest.TestCase):
    """Shared compile/attach/teardown scaffolding for the runtime tests."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="ct2-wp54-")
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

    def compile(self, body: str, lua_script: str = "", uds: str = "") -> dict:
        path = self.root / "phase2.ct"
        path.write_text(table_xml(body, lua_script, uds), encoding="utf-8")
        return compile_table(str(path), PROCESS)

    def attach(self, plan: dict) -> TrainerEngine:
        # A fresh state dir per engine: a subtest loop may hold several
        # live engines in one test, and the state lock is per state dir.
        self.memory = Memory()
        engine = TrainerEngine(plan, state_dir=self.root / f'state{len(self.engines)}',
                               process_lock_dir=self.root / f'shared{len(self.engines)}',
                               memory_factory=lambda name: self.memory,
                               hook_coordinator=Coordinator())
        self.engines.append(engine)
        engine.poll()
        return engine


class TableLuaSymbolExtractionTests(unittest.TestCase):
    """Static extraction: one-shot adoption over the unphased table text."""

    def test_register_symbol_literal_is_adopted(self):
        self.assertEqual(
            extract_table_lua_symbols("registerSymbol('SynthTableSym', 0x1040)"),
            ['SynthTableSym'])

    def test_ce_dotted_form_and_field_form_are_adopted(self):
        source = ("Register.symbol('DottedSym', addr)\n"
                  "local t = {symbol='FieldSym'}\n")
        self.assertEqual(extract_table_lua_symbols(source),
                         ['DottedSym', 'FieldSym'])

    def test_release_inside_the_source_cancels_adoption(self):
        source = ("registerSymbol('ShortLived', 0x1040)\n"
                  "unregisterSymbol('ShortLived')\n")
        self.assertEqual(extract_table_lua_symbols(source), [])

    def test_release_without_registration_is_unproven(self):
        self.assertEqual(extract_table_lua_symbols("unregisterSymbol('Nobody')"),
                         [])

    def test_non_string_source_is_refused(self):
        for bad in (None, 7, ['registerSymbol("X", 1)']):
            with self.subTest(bad=repr(bad)):
                with self.assertRaises(ValueError):
                    extract_table_lua_symbols(bad)

    def test_empty_source_is_unproven(self):
        self.assertEqual(extract_table_lua_symbols(""), [])
        self.assertEqual(extract_table_lua_symbols("   \n  "), [])

    def test_comments_do_not_count(self):
        self.assertEqual(
            extract_table_lua_symbols("-- registerSymbol('Ghost', 0x1040)"), [])

    def test_safety_valve_caps_distinct_names(self):
        names = [f"S{i:02d}x" for i in range(MAX_PROVIDERS + 1)]
        source = "\n".join(f"registerSymbol('{n}', 0x1040)" for n in names)
        self.assertEqual(extract_table_lua_symbols(source), [])

    def test_safety_valve_boundary_is_inclusive(self):
        names = [f"S{i:02d}x" for i in range(MAX_PROVIDERS)]
        source = "\n".join(f"registerSymbol('{n}', 0x1040)" for n in names)
        self.assertEqual(extract_table_lua_symbols(source),
                         sorted(names, key=str.casefold))

    def test_result_is_casefold_sorted(self):
        source = "registerSymbol('Zebra', 0x1)\nregisterSymbol('apple', 0x2)\n"
        self.assertEqual(extract_table_lua_symbols(source),
                         ['apple', 'Zebra'])


class TableLuaSymbolPlanTests(EngineHarness):
    """Compiler-level plan field: emission, residual rule, byte stability."""

    def test_field_is_emitted_casefolded_sorted_only_when_non_empty(self):
        plan = self.compile(
            value_record(1, "1000"),
            "registerSymbol('ZetaSym', 0x1040)\n"
            "registerSymbol('alphaSym', 0x1050)\n")
        self.assertEqual(plan['table_lua_symbols'], ['alphasym', 'zetasym'])
        # Byte-stable: a table without symbol evidence carries no field.
        plan = self.compile(value_record(1, "1000"),
                            'plain = readInteger(0x1040)\n')
        self.assertNotIn('table_lua_symbols', plan)
        plan = self.compile(value_record(1, "1000"))
        self.assertNotIn('table_lua_symbols', plan)

    def test_release_inside_the_table_source_excludes_the_name(self):
        plan = self.compile(
            value_record(1, "1000"),
            "registerSymbol('ShortLived', 0x1040)\n"
            "unregisterSymbol('ShortLived')\n")
        self.assertNotIn('table_lua_symbols', plan)

    def test_record_provider_wins_over_the_table_symbol(self):
        # The supported alloc-only record provides the same symbol: the
        # residual subtraction drops it from the plan field and the consumer
        # depends on the record provider instead.
        plan = self.compile(
            value_record(1, "1000") + alloc_record(2, "SharedSym")
            + value_record(3, "SharedSym"),
            "registerSymbol('SharedSym', 0x1040)\n")
        self.assertNotIn('table_lua_symbols', plan)
        by_id = {entry['id']: entry for entry in plan['entries']}
        self.assertTrue(by_id[3]['supported'])
        self.assertEqual(by_id[3]['dependency_ids'], [2])

    def test_consumer_without_record_provider_keeps_no_dependencies(self):
        plan = self.compile(
            value_record(1, "1000") + value_record(3, "SharedSym+4"),
            "registerSymbol('SharedSym', 0x1040)\n")
        self.assertEqual(plan['table_lua_symbols'], ['sharedsym'])
        by_id = {entry['id']: entry for entry in plan['entries']}
        self.assertTrue(by_id[3]['supported'])
        self.assertEqual(by_id[3]['requires'], ['SharedSym'])
        self.assertEqual(by_id[3]['dependency_ids'], [])

    def test_uds_and_table_symbol_fields_coexist(self):
        plan = self.compile(
            value_record(1, "1000") + value_record(3, "TblSym+4"),
            "registerSymbol('TblSym', 0x1040)\n",
            uds=uds_section(uds_entry("UdsSym", "1070")))
        self.assertEqual(plan['table_lua_symbols'], ['tblsym'])
        self.assertEqual(plan['user_defined_symbols'], {'udssym': 0x1070})

    def test_honest_plan_passes_both_validators(self):
        plan = self.compile(
            value_record(1, "1000") + value_record(3, "TblSym+4"),
            "registerSymbol('TblSym', 0x1040)\n")
        validate_plan(plan)
        validate_runtime_plan(plan)


class TableLuaSymbolForgeryTests(EngineHarness):
    """A forged table_lua_symbols list is refused by BOTH plan gates."""

    def setUp(self):
        super().setUp()
        self.plan = self.compile(
            value_record(1, "1000") + value_record(3, "TblSymA+4"),
            "registerSymbol('TblSymA', 0x1040)\n"
            "registerSymbol('TblSymB', 0x1050)\n")

    def mutate(self, table_symbols) -> dict:
        plan = deepcopy(self.plan)
        if table_symbols is None:
            plan.pop('table_lua_symbols', None)
        else:
            plan['table_lua_symbols'] = table_symbols
        return plan

    def _refused_by_both(self, plan: dict, pattern: str) -> None:
        with self.assertRaisesRegex(NativeCompileError, pattern):
            validate_plan(plan)
        with self.assertRaisesRegex(NativeRuntimeError, pattern):
            validate_runtime_plan(plan)

    def test_honest_field_passes_both_validators(self):
        self.assertEqual(self.plan['table_lua_symbols'],
                         ['tblsyma', 'tblsymb'])
        validate_plan(self.plan)
        validate_runtime_plan(self.plan)

    def test_dropping_the_field_passes_both_validators(self):
        # Honest omission: table Lua without any registerSymbol means the
        # field is absent from the plan, which both gates must accept.
        plan = self.compile(value_record(1, "1000"),
                            "plain = readInteger(0x1040)\n")
        self.assertNotIn("table_lua_symbols", plan)
        validate_plan(plan)
        validate_runtime_plan(plan)

    def test_forged_extra_name_is_refused_by_both_gates(self):
        self._refused_by_both(self.mutate(['tblsyma', 'tblsymb', 'forged']),
                              'does not re-derive')

    def test_forged_missing_name_is_refused_by_both_gates(self):
        self._refused_by_both(self.mutate(['tblsyma']), 'does not re-derive')

    def test_forged_swapped_order_is_refused_by_both_gates(self):
        self._refused_by_both(self.mutate(['tblsymb', 'tblsyma']),
                              'does not re-derive')

    def test_forged_duplicate_casefold_is_refused(self):
        self._refused_by_both(
            self.mutate(['TblSymA', 'tblsyma']),
            'bounded casefold-unique name list')

    def test_forged_non_list_forms_are_refused(self):
        for bad in ('tblsyma', 17, {'tblsyma': None}):
            with self.subTest(bad=repr(bad)):
                self._refused_by_both(
                    self.mutate(bad), 'bounded casefold-unique name list')

    def test_forged_empty_string_entry_is_refused(self):
        self._refused_by_both(
            self.mutate(['', 'tblsyma']),
            'bounded casefold-unique name list')

    def test_forged_unbounded_list_is_refused(self):
        self._refused_by_both(
            self.mutate([f"f{i}" for i in range(MAX_PROVIDERS + 1)]),
            'bounded casefold-unique name list')

    def test_field_without_bootstrap_source_is_refused(self):
        plan = self.mutate(['tblsyma'])
        plan.pop('lua_bootstrap')
        self._refused_by_both(plan, 'requires the table bootstrap source')


class TableLuaScopeRuntimeTests(EngineHarness):
    """End-to-end: case-29 shape on a real (fake) attach."""

    def test_table_symbol_registers_at_bootstrap_and_consumers_resolve(self):
        body = (script_record(65, '[ENABLE]\n{$lua}\n'
                                  'local g = synthTableGlobal29\n'
                                  'local present = (g ~= nil)\n'
                                  '{$asm}\n[DISABLE]\n')
                + script_record(66, '[ENABLE]\n'
                                    'assert(SynthTableSym29+8,00 00 00 00)\n'
                                    'SynthTableSym29+8:\n'
                                    'dd 7\n'
                                    '[DISABLE]\n'
                                    'assert(SynthTableSym29+8,07 00 00 00)\n'
                                    'SynthTableSym29+8:\n'
                                    'dd 0')
                + value_record(67, "SynthTableSym29+4"))
        plan = self.compile(body, CASE29_LUA)
        by_id = {entry['id']: entry for entry in plan['entries']}
        self.assertEqual(plan['table_lua_symbols'], ['synthtablesym29'])
        self.assertEqual(plan['table_lua'],
                         {'executed': False, 'reasons': [],
                          'record_scripts_inactive': 1})
        for identifier in (65, 66, 67):
            self.assertTrue(by_id[identifier]['supported'],
                            by_id[identifier].get('reason'))
        self.assertEqual(by_id[66]['requires'], ['SynthTableSym29'])
        self.assertEqual(by_id[66]['dependency_ids'], [])
        self.assertEqual(by_id[67]['requires'], ['SynthTableSym29'])
        self.assertEqual(by_id[67]['dependency_ids'], [])
        engine = self.attach(plan)
        # The table-scope bootstrap registered the symbol in the runtime
        # symbol table; consumers resolve through it without dependencies.
        self.assertEqual(engine.plan['table_lua'],
                         {'executed': True, 'reasons': [],
                          'record_scripts_inactive': 1})
        self.assertEqual(engine.symbols.get('synthtablesym29'), 0x1040)
        self.assertEqual(engine._value_address(engine.entries[67]), 0x1044)
        # Byte-exact roundtrip through the table symbol.
        self.assertTrue(engine.toggle(66, True))
        self.assertEqual(self.memory.read(0x1048, 4),
                         bytes.fromhex('07000000'))
        self.assertFalse(engine.toggle(66, False))
        self.assertEqual(self.memory.read(0x1048, 4), bytes(4))
        self.assertFalse(engine.blocked)

    def test_record_scope_replay_is_scheduler_free_and_inert(self):
        body = (script_record(65, '[ENABLE]\n{$lua}\n'
                                  'local g = synthTableGlobal29\n'
                                  '{$asm}\n[DISABLE]\n')
                + value_record(66, "SynthTableSym29+8"))
        plan = self.compile(body, CASE29_LUA)
        engine = self.attach(plan)
        table_host = engine.table_lua_scope[0]
        # The table source replayed into the record helper scope bound the
        # timer to the inert stub: the record activates normally, the stub
        # establishes as a table with its no-op destroy surface, and the
        # replayed callback never fires in the record scope.
        self.assertTrue(engine.toggle(65, True))
        scope = engine.lua_activations[65]
        scope.host.tick(10000)
        self.assertIsNone(scope.host.execute('return table_tick_read'))
        self.assertEqual(scope.host.execute('return type(table_timer)'),
                         'table')
        self.assertEqual(scope.host.execute(
            'return type(table_timer.destroy)'), 'function')
        # The real timer lives only in the table scope and keeps ticking
        # for the attach lifetime while the record scope is live.
        self.memory.data[0x10C0 - self.memory.base:0x10C4 - self.memory.base] = \
            (42).to_bytes(4, 'little')
        table_host.tick(500)
        self.assertEqual(table_host.execute('return table_tick_read'), 42)
        # One-shot record: a plain toggle-off keeps the effect and its scope
        # live until close/exit, so only the table scope is alive here.
        self.assertFalse(engine.toggle(65, False))
        self.assertFalse(scope.host.cancelled)
        self.assertFalse(table_host.cancelled)
        # Confirmed target exit retires the record scope first, then the
        # table scope (WP-54 part d); both hosts end cancelled.
        self.memory.alive = False
        engine.poll()
        self.assertTrue(scope.host.cancelled)
        self.assertTrue(table_host.cancelled)
        self.assertIsNone(engine.table_lua_scope)

    def test_persistent_table_timer_dies_with_the_scope(self):
        plan = self.compile(value_record(1, "1000"), CASE29_LUA)
        engine = self.attach(plan)
        table_host = engine.table_lua_scope[0]
        table_host.tick(500)
        self.assertEqual(table_host.execute('return table_tick_read'), 0)
        self.memory.data[0x10C0 - self.memory.base:0x10C4 - self.memory.base] = \
            (7).to_bytes(4, 'little')
        table_host.tick(500)
        self.assertEqual(table_host.execute('return table_tick_read'), 7)
        # Target exit retires the table scope: the timer dies with it and
        # the host is cancelled.
        self.memory.alive = False
        engine.poll()
        self.assertIsNone(engine.table_lua_scope)
        self.assertTrue(table_host.cancelled)
        with self.assertRaises(LuaHostError):
            table_host.tick(500)

    def test_teardown_orders_record_scopes_before_the_table_scope(self):
        body = (script_record(65, '[ENABLE]\n{$lua}\n'
                                  'local g = synthTableGlobal29\n'
                                  '{$asm}\n[DISABLE]\n')
                + script_record(66, '[ENABLE]\n'
                                    'assert(SynthTableSym29+8,00 00 00 00)\n'
                                    'SynthTableSym29+8:\n'
                                    'dd 7\n'
                                    '[DISABLE]\n'
                                    'assert(SynthTableSym29+8,07 00 00 00)\n'
                                    'SynthTableSym29+8:\n'
                                    'dd 0'))
        plan = self.compile(body, CASE29_LUA)
        engine = self.attach(plan)
        engine.toggle(65, True)
        engine.toggle(66, True)
        self.assertEqual(self.memory.read(0x1048, 4),
                         bytes.fromhex('07000000'))
        scope = engine.lua_activations[65]
        table_host, table_broker = engine.table_lua_scope
        # The WP-37-style event trace: every symbol removal is recorded and
        # both scope cancels are traced in one timeline with the writes.
        symbols = CountingSymbols(events=self.memory.events)
        symbols.update(engine.symbols)
        engine.symbols = symbols
        original_release = table_broker.owner.release
        def traced_release():
            self.memory.events.append(('table-release',))
            return original_release()
        table_broker.owner.release = traced_release
        original_table_cancel = table_host.cancel
        def traced_table_cancel():
            self.memory.events.append(('table-cancel',))
            return original_table_cancel()
        table_host.cancel = traced_table_cancel
        original_record_cancel = scope.host.cancel
        def traced_record_cancel():
            self.memory.events.append(('record-cancel',))
            return original_record_cancel()
        scope.host.cancel = traced_record_cancel
        # Confirmed target exit: record scopes retire leaves-first; the
        # table scope retires last and releases its symbol exactly once.
        # Note: a confirmed target exit does not run record disable phases
        # (the process is gone); the patched bytes in the dead fixture
        # memory are simply forgotten with `applied.clear()`.
        self.memory.alive = False
        engine.poll()
        self.assertEqual(engine.symbols, {})
        self.assertEqual(engine.symbols.removed, ['synthtablesym29'])
        self.assertEqual(self.memory.events.count(('symbol-removed',
                                                   'synthtablesym29')), 1)
        events = self.memory.events
        write_index = events.index(('write', 0x1048))
        release_index = events.index(('table-release',))
        table_cancel_index = events.index(('table-cancel',))
        first_record = min(index for index, event in enumerate(events)
                           if event == ('record-cancel',))
        self.assertLess(write_index, release_index)
        self.assertLess(first_record, release_index)
        self.assertLess(release_index, table_cancel_index)
        self.assertEqual(events.count(('table-release',)), 1)
        self.assertTrue(table_broker.owner.released)

    def test_close_retires_the_table_scope_after_the_record_scopes(self):
        body = (script_record(65, '[ENABLE]\n{$lua}\n'
                                  'local g = synthTableGlobal29\n'
                                  '{$asm}\n[DISABLE]\n')
                + value_record(66, "SynthTableSym29+8"))
        plan = self.compile(body, CASE29_LUA)
        engine = self.attach(plan)
        engine.toggle(65, True)
        self.assertEqual(engine.symbols.get('synthtablesym29'), 0x1040)
        self.assertTrue(engine.close())
        self.assertIsNone(engine.table_lua_scope)
        self.assertNotIn('synthtablesym29', engine.symbols)
        self.assertFalse(engine.lua_activations)


class TableLuaUdsReseedTests(EngineHarness):
    """UDS reseed on every confirmed attach (part e)."""

    def test_uds_resedes_on_confirmed_reattach(self):
        # Pure UDS (no table Lua): the confirmed target-exit path cleared
        # the runtime symbol table; only the attach-time reseed restores the
        # UDS symbol so the saved wish survives the re-attach.
        plan = self.compile(
            script_record(1, '[ENABLE]\n{$lua}\n'
                             'if not syntaxcheck then '
                             "writeInteger(getAddress('BaseSym+4'), 5) end\n"
                             '{$asm}\n[DISABLE]\n{$lua}\n'
                             "assert(readInteger(getAddress('BaseSym+4'))==5)\n"
                             '{$asm}\n'),
            uds=uds_section(uds_entry("BaseSym", "1070")))
        self.assertEqual(plan['user_defined_symbols'], {'basesym': 0x1070})
        engine = self.attach(plan)
        self.assertEqual(engine.symbols.get('basesym'), 0x1070)
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.memory.read(0x1074, 4),
                         (5).to_bytes(4, 'little'))
        # Confirmed target exit clears the runtime symbol table.
        self.memory.alive = False
        engine.poll()
        self.assertNotIn('basesym', engine.symbols)
        self.memory = Memory(pid=234, creation_time=567)
        engine.poll()
        # Reseeded before the wish restore: the saved record re-enables
        # against the fresh target through the re-seeded UDS symbol.
        self.assertEqual(engine.symbols.get('basesym'), 0x1070)
        self.assertIn(1, engine.applied)
        self.assertEqual(self.memory.read(0x1074, 4),
                         (5).to_bytes(4, 'little'))

    def test_table_scope_registration_keeps_ce_order_over_the_uds_seed(self):
        # The UDS map seeds the runtime table at init/attach; the table-scope
        # registerSymbol runs after the seed and keeps CE order (it wins).
        plan = self.compile(
            value_record(1, "TblUdsSym"),
            "registerSymbol('TblUdsSym', 0x1040)\n",
            uds=uds_section(uds_entry("TblUdsSym", "1070")))
        self.assertEqual(plan['user_defined_symbols'],
                         {'tbludssym': 0x1070})
        self.assertEqual(plan['table_lua_symbols'], ['tbludssym'])
        engine = self.attach(plan)
        self.assertEqual(engine.symbols.get('tbludssym'), 0x1040)
        self.memory.alive = False
        engine.poll()
        self.memory = Memory(pid=234, creation_time=567)
        engine.poll()
        # Re-attach: the seed is re-established and the table-scope
        # registration overwrites it again, in CE order.
        self.assertEqual(engine.symbols.get('tbludssym'), 0x1040)
        self.assertEqual(engine._value_address(engine.entries[1]), 0x1040)


class TableLuaSymbolRefusalTests(EngineHarness):
    """Byte-exact table-scope symbol refusals (WP-41/WP-54)."""

    def _bootstrap(self, lua: str, body: str | None = None) -> TrainerEngine:
        if body is None:
            body = value_record(1, "1000")
        plan = self.compile(body, lua)
        return self.attach(plan)

    def test_double_registration_in_the_scope_is_refused(self):
        engine = self._bootstrap(
            "registerSymbol('DupSym', 0x1040)\n"
            "registerSymbol('DupSym', 0x1050)\n")
        self.assertEqual(engine.plan['table_lua']['reasons'],
                         ['Table Lua symbol registration conflict: DupSym.'])
        self.assertFalse(engine.plan['table_lua']['executed'])
        self.assertIsNone(engine.table_lua_scope)
        self.assertNotIn('dupsym', engine.symbols)

    def test_invalid_registration_arguments_are_refused(self):
        bad_calls = (
            "registerSymbol(42, 0x1040)\n",
            "registerSymbol('SoloSym')\n",
            "unregisterSymbol()\n",
        )
        for lua in bad_calls:
            with self.subTest(lua=lua.strip()):
                engine = self._bootstrap(lua)
                self.assertEqual(engine.plan['table_lua']['reasons'],
                                 ['Table Lua symbol registration has invalid arguments.'])
                self.assertFalse(engine.plan['table_lua']['executed'])
                self.assertIsNone(engine.table_lua_scope)

    def test_out_of_range_symbol_address_is_refused(self):
        engine = self._bootstrap("registerSymbol('FarSym', 0x9999)\n")
        self.assertEqual(engine.plan['table_lua']['reasons'],
                         ['Table Lua symbol address is outside the attached target.'])
        self.assertFalse(engine.plan['table_lua']['executed'])
        self.assertIsNone(engine.table_lua_scope)
        self.assertNotIn('farsym', engine.symbols)

    def test_unregistering_a_foreign_symbol_is_refused(self):
        engine = self._bootstrap(
            "registerSymbol('KeptSym', 0x1040)\n"
            "unregisterSymbol('Nobody')\n")
        self.assertEqual(engine.plan['table_lua']['reasons'],
                         ['Table Lua unregistered a symbol it does not own: Nobody.'])
        self.assertFalse(engine.plan['table_lua']['executed'])
        self.assertIsNone(engine.table_lua_scope)
        self.assertNotIn('keptsym', engine.symbols)

    def test_record_provided_name_is_skipped_quietly_at_bootstrap(self):
        # Residual rule, runtime side: the plan field excludes the shared
        # name (record providers win), the bootstrap skips the registration
        # without recording a reason, and the table scope stays alive —
        # the record's own registration stays collision-free at activation.
        plan = self.compile(
            alloc_record(2, 'SharedSym') + value_record(3, 'SharedSym'),
            "registerSymbol('SharedSym', 0x1040)\n")
        self.assertNotIn('table_lua_symbols', plan)
        engine = self.attach(plan)
        self.assertEqual(engine.plan['table_lua'],
                         {'executed': True, 'reasons': [],
                          'record_scripts_inactive': 0})
        self.assertIsNotNone(engine.table_lua_scope)
        self.assertNotIn('sharedsym', engine.symbols)
        owner = engine.table_lua_scope[1].owner
        self.assertEqual(owner.symbols, {})
        self.assertFalse(owner.released)


if __name__ == '__main__':
    unittest.main()
