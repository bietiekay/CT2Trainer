"""Automatic phase-selected Lua records share exact owned undo with AA."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from test_native_lua_activation import Memory
from test_native_engine import FIXTURE
from test_native_engine_code import Coordinator
from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import TrainerEngine, NativeRuntimeError, validate_plan
from ct2trainer.native.lua_host import LuaHostError
from ct2trainer.native.lua_program import prepare_lua_program
from ct2trainer.native.lua_bootstrap import prepare_lua_bootstrap


MIXED = '''{$lua}
function helper() return 23 end
{$asm}
[ENABLE]
{$lua}
assert(memrec.ID==1 and memrec.Active==false)
if not syntaxcheck then
  writeInteger(0x1080,helper())
  owned_worker=createThread(function(t) writeInteger(0x1080,helper()+1); sleep(50); writeInteger(0x1080,99) end)
end
return 'define(generated,0)'
{$asm}
assert(1040,00 00 00 00)
1040:
dd 1
[DISABLE]
{$lua}
assert(memrec.ID==1 and memrec.Active==true)
return 'assert(1040,01 00 00 00)'
{$asm}
1040:
dd 0
'''
ONLY = '''[ENABLE]
{$lua}
if not syntaxcheck then writeInteger(0x1080,17) end
{$asm}
[DISABLE]
{$lua}
assert(readInteger(0x1080)==17)
{$asm}
'''


class AutomaticLuaRecordTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.memory = Memory()
        self.engine = None

    def tearDown(self):
        if self.engine is not None and not self.engine.closed:
            self.memory.alive = False
            self.engine.poll()
            self.engine.close()

    def make_engine(self, source=MIXED, bootstrap=None, memory=None):
        plan = compile_table(FIXTURE, 'FixtureTarget.exe')
        if bootstrap is not None:
            plan['lua_bootstrap'] = prepare_lua_bootstrap(bootstrap)
        row = plan['entries'][1]
        profile = prepare_lua_program(source, 'FixtureTarget.exe')
        row.update(lua_program=profile, enable=[], disable=[], requires=profile['requires'],
                   provides=profile['provides'], dependency_ids=[],
                   one_shot=bool(profile.get('one_shot', False)))
        # WP-14: the rewritten record drops its symbol dependencies, so the
        # compiler-derived staged marker (if any) must go with them.
        row.pop('staged', None)
        validate_plan(plan)
        self.memory = memory if memory is not None else Memory()
        self.engine = TrainerEngine(plan, state_dir=self.root / 'state', process_lock_dir=self.root / 'shared',
                                    memory_factory=lambda name: self.memory, hook_coordinator=Coordinator())
        self.engine.poll()
        return self.engine

    def test_mixed_record_confirms_then_runs_worker_and_restores_all_owned_bytes(self):
        engine = self.make_engine()
        self.assertTrue(engine.toggle(1, True))
        self.assertIn(1, engine.desired)
        scope = engine.lua_activations[1]
        self.assertEqual(self.memory.read(0x1040, 4), bytes.fromhex('01000000'))
        self.assertEqual(self.memory.read(0x1080, 4), bytes.fromhex('17000000'))
        scope.host.tick(0)
        self.assertEqual(self.memory.read(0x1080, 4), bytes.fromhex('18000000'))
        self.assertFalse(engine.toggle(1, False))
        self.assertEqual(self.memory.read(0x1040, 4), bytes(4))
        self.assertEqual(self.memory.read(0x1080, 4), bytes(4))
        self.assertNotIn(1, engine.applied)
        self.assertNotIn(1, engine.desired)
        self.assertTrue(scope.host.cancelled)
        with self.assertRaises(LuaHostError):
            scope.host.tick(100)
        self.assertFalse(engine.blocked)

    def test_lua_only_record_has_confirmed_owned_data_undo(self):
        engine = self.make_engine(ONLY)
        self.assertTrue(engine.toggle(1, True))
        self.assertFalse(engine.lua_activations[1].assemblies)
        self.assertEqual(self.memory.read(0x1080, 4), bytes.fromhex('11000000'))
        self.assertFalse(engine.toggle(1, False))
        self.assertEqual(self.memory.read(0x1080, 4), bytes(4))

    def test_private_table_helpers_replay_before_record_without_load_time_writes(self):
        source = MIXED.replace('function helper() return 23 end', '-- helper comes from table Lua')
        engine = self.make_engine(source, 'function helper() return 31 end')
        self.assertEqual(self.memory.read(0x1080, 4), bytes(4))
        self.assertTrue(engine.toggle(1, True))
        first = engine.lua_activations[1]
        self.assertEqual(self.memory.read(0x1080, 4), bytes.fromhex('1f000000'))
        first.host.execute('function helper() return 99 end')
        self.assertFalse(engine.toggle(1, False))
        self.assertTrue(engine.toggle(1, True))
        self.assertIsNot(first.host, engine.lua_activations[1].host)
        self.assertEqual(self.memory.read(0x1080, 4), bytes.fromhex('1f000000'))

    def _close_subtest_engine(self):
        # Full target-exit teardown: a plain close with a live target leaves
        # the owned receipts unfinalized for the next engine.
        if self.engine is not None and not self.engine.closed:
            self.memory.alive = False
            self.engine.poll()
            self.assertTrue(self.engine.close())
        self.engine = None

    def test_refused_write_records_named_reason_without_blocking_independent_records(self):
        # WP-41: the write-API call is refused at the once-per-load bootstrap
        # (recorded with the exact reason, answered with nil so the read-only
        # remainder of the table source still runs); the MIXED record
        # references no table-level global, so it toggles as usual.
        try:
            engine = self.make_engine(bootstrap='pcall(function() writeInteger(0x1080,42) end)')
            self.assertEqual(engine.plan['table_lua'],
                             {'executed': False,
                              'reasons': ['Table Lua uses a write API: writeInteger.'],
                              'record_scripts_inactive': 0})
            self.assertIsNone(engine.table_lua_scope)
            self.assertEqual(self.memory.read(0x1080, 4), bytes(4))
            self.assertTrue(engine.toggle(1, True))
            self.assertEqual(self.memory.read(0x1040, 4), bytes.fromhex('01000000'))
            self.assertEqual(self.memory.read(0x1080, 4), bytes.fromhex('17000000'))
            self.assertFalse(engine.toggle(1, False))
            self.assertEqual(self.memory.read(0x1040, 4), bytes(4))
            self.assertEqual(self.memory.read(0x1080, 4), bytes(4))
            self.assertNotIn(1, engine.applied)
            self.assertNotIn(1, engine.desired)
            self.assertFalse(engine.blocked)
        finally:
            self._close_subtest_engine()

    def test_table_lua_scheduler_work_runs_at_load_and_replay_is_inert(self):
        # WP-41/WP-54 (a'): a table that schedules work executes it once at
        # load in the sandboxed bootstrap scope — the real timer lives in the
        # table scope for the attach lifetime and retires with it.  Record
        # activations replay the table source through the helper contract
        # with scheduler-free inert stubs, so the record activates normally
        # and the replayed scheduler objects never fire in the record scope.
        try:
            engine = self.make_engine(bootstrap='table_timer=createTimer(nil,true); '
                                               'table_timer.OnTimer=function() '
                                               'table_read=readInteger(0x10C0) end')
            self.assertEqual(engine.plan['table_lua'],
                             {'executed': True, 'reasons': [],
                              'record_scripts_inactive': 0})
            self.assertIsNotNone(engine.table_lua_scope)
            table_host = engine.table_lua_scope[0]
            self.assertEqual(self.memory.read(0x1080, 4), bytes(4))
            self.memory.data[0x10C0 - self.memory.base:0x10C4 - self.memory.base] = (42).to_bytes(4, 'little')
            table_host.tick(1000)
            self.assertEqual(table_host.execute('return table_read'), 42)
            self.assertTrue(engine.toggle(1, True))
            scope = engine.lua_activations[1]
            self.assertEqual(self.memory.read(0x1040, 4), bytes.fromhex('01000000'))
            self.assertEqual(self.memory.read(0x1080, 4), bytes.fromhex('17000000'))
            scope.host.tick(0)
            self.assertEqual(self.memory.read(0x1080, 4), bytes.fromhex('18000000'))
            # The table-scope timer keeps ticking for the attach lifetime;
            # the record-scope replay established only the inert stub.
            self.memory.data[0x10C0 - self.memory.base:0x10C4 - self.memory.base] = (43).to_bytes(4, 'little')
            table_host.tick(1000)
            self.assertEqual(table_host.execute('return table_read'), 43)
            self.assertFalse(engine.toggle(1, False))
            self.assertEqual(self.memory.read(0x1040, 4), bytes(4))
            self.assertEqual(self.memory.read(0x1080, 4), bytes(4))
            self.assertNotIn(1, engine.applied)
            self.assertNotIn(1, engine.desired)
            self.assertFalse(engine.blocked)
        finally:
            self._close_subtest_engine()

    def test_invalid_nasm_after_lua_write_compensates_without_saved_wish(self):
        engine = self.make_engine(MIXED.replace('dd 1', 'unknown_instruction eax,ecx'))
        with self.assertRaises(NativeRuntimeError):
            engine.toggle(1, True)
        self.assertEqual(self.memory.read(0x1040, 4), bytes(4))
        self.assertEqual(self.memory.read(0x1080, 4), bytes(4))
        self.assertNotIn(1, engine.applied)
        self.assertNotIn(1, engine.desired)
        self.assertFalse(engine.lua_sessions)
        self.assertFalse(engine.lua_activations)
        self.assertFalse(engine.blocked)
        self.assertTrue(engine.close())

    def test_lua_error_after_write_compensates_before_any_main_publication(self):
        source = MIXED.replace("return 'define(generated,0)'", "error('owned enable failed')")
        engine = self.make_engine(source)
        with self.assertRaisesRegex(NativeRuntimeError, 'owned enable failed'):
            engine.toggle(1, True)
        self.assertEqual(self.memory.read(0x1080, 4), bytes(4))
        self.assertEqual(self.memory.read(0x1040, 4), bytes(4))
        self.assertFalse(engine.desired)
        self.assertFalse(engine.blocked)

    def test_disable_return_cannot_add_foreign_inverse_writes(self):
        source = MIXED.replace("return 'assert(1040,01 00 00 00)'", "return '1044:\\ndd 9'")
        engine = self.make_engine(source)
        engine.toggle(1, True)
        with self.assertRaisesRegex(NativeRuntimeError, 'captured original'):
            engine.toggle(1, False)
        self.assertEqual(self.memory.read(0x1044, 4), bytes(4))
        self.assertEqual(self.memory.read(0x1040, 4), bytes.fromhex('01000000'))
        self.assertIn(1, engine.applied)
        self.assertIn(1, engine.desired)
        self.assertFalse(engine.blocked)
        # Whole-controller close uses owned undo after cancelling user callbacks.
        self.assertTrue(engine.close())
        self.assertEqual(self.memory.read(0x1040, 4), bytes(4))
        self.assertEqual(self.memory.read(0x1080, 4), bytes(4))

    def test_saved_lua_record_replays_in_fresh_state_after_exact_target_exit(self):
        engine = self.make_engine()
        engine.toggle(1, True)
        previous = engine.lua_activations[1]
        self.memory.alive = False
        engine.poll()
        self.assertTrue(previous.host.cancelled)
        self.assertEqual(previous.state, 'target-exited')
        self.memory = Memory(pid=234, creation_time=567)
        engine.poll()
        self.assertIn(1, engine.applied)
        self.assertEqual(self.memory.read(0x1080, 4), bytes.fromhex('17000000'))
        self.assertIsNot(previous.host, engine.lua_activations[1].host)
        self.assertEqual(engine.lua_activations[1].identity, (234, 567))

    def test_forged_lua_record_metadata_is_rejected_before_state_access(self):
        engine = self.make_engine()
        plan = deepcopy(engine.plan)
        plan['entries'][1]['lua_program']['source_sha256'] = '0' * 64
        with self.assertRaises(NativeRuntimeError):
            TrainerEngine(plan, state_dir=self.root / 'must-not-exist')
        self.assertFalse((self.root / 'must-not-exist').exists())

    def test_forged_bootstrap_is_rejected_before_state_access(self):
        engine = self.make_engine(bootstrap='function helper() return 23 end')
        plan = deepcopy(engine.plan)
        plan['lua_bootstrap']['source'] = 'writeInteger(0x1080,42)'
        with self.assertRaises(NativeRuntimeError):
            TrainerEngine(plan, state_dir=self.root / 'must-not-exist')
        self.assertFalse((self.root / 'must-not-exist').exists())
