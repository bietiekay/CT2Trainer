"""Owned callbacks and receipts survive failures without writing foreign bytes."""
from pathlib import Path
from copy import deepcopy
from hashlib import sha256
import json
import tempfile
import unittest
from unittest.mock import patch

from test_native_engine import FakeMemory, FIXTURE
from test_native_engine_code import Coordinator
from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import TrainerEngine, NativeRuntimeError
from ct2trainer.native.lua_host import LuaHostError


class Memory(FakeMemory):
    @property
    def identity(self):
        return self.pid, self.creation_time

    def _range(self, address, size):
        if not self.base <= address or address + size > self.base + len(self.data):
            raise ValueError('Outside owned fixture memory')

    def is_executable(self, address, size):
        return False


AA = '[ENABLE]\nassert(1040,00 00 00 00)\n1040:\ndd 1\n[DISABLE]\n1040:\ndd 0'


class OwnedLuaTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.memory = Memory()
        self.engine = TrainerEngine(compile_table(FIXTURE, 'FixtureTarget.exe'),
                                    state_dir=root / 'state', process_lock_dir=root / 'shared',
                                    memory_factory=lambda name: self.memory, hook_coordinator=Coordinator())
        self.engine.poll()
        self.engine.toggle(1, True)
        self.host = self.engine.open_lua_activation(1)

    def tearDown(self):
        self.memory.alive = False
        self.engine.poll()
        self.engine.close()
        self.directory.cleanup()

    def test_raw_write_symbol_and_scheduled_callback_are_retired_with_owner(self):
        original = self.memory.read(0x1040, 4)
        self.assertTrue(self.host.execute('return writeInteger(0x1040,17)'))
        self.host.execute('registerSymbol("owned",0x1040); w=createThread(function() sleep(10); writeInteger(0x1040,19) end)')
        self.host.tick(0)
        self.host.tick(10)
        self.assertEqual(self.memory.read(0x1040, 4), b'\x13\0\0\0')
        scope = self.engine.lua_activations[1]
        self.assertIn('owned', self.engine.symbols)
        self.engine.toggle(1, False)
        self.assertEqual(self.memory.read(0x1040, 4), original)
        self.assertNotIn('owned', self.engine.symbols)
        self.assertTrue(self.host.cancelled)
        self.assertEqual(scope.state, 'abandoned')
        count = len(self.memory.writes)
        with self.assertRaisesRegex(LuaHostError, 'cancelled'):
            self.host.tick(100)
        self.assertEqual(len(self.memory.writes), count)

    def test_partial_overlaps_record_patch_and_numeric_writes_are_refused(self):
        self.host.execute('writeInteger(0x1040,7)')
        for source in ('writeSmallInteger(0x1041,2)', 'writeInteger(0x1014,0)'):
            with self.assertRaisesRegex(LuaHostError, 'overlap'):
                self.host.execute(source)
        # The ordinary value API cannot bypass a Lua scope's undo bytes.
        self.host.execute('writeInteger(0x1010,5432)')
        with self.assertRaisesRegex(NativeRuntimeError, 'Lua-owned'):
            self.engine.set_value(2, '1')

    def test_external_bytes_preserve_journal_and_block_undo(self):
        self.host.execute('writeInteger(0x1040,17)')
        scope = self.engine.lua_activations[1]
        self.memory.data[64:68] = b'\x99' * 4
        count = len(self.memory.writes)
        with self.assertRaisesRegex(NativeRuntimeError, 'changed externally'):
            self.engine.toggle(1, False)
        self.assertTrue(scope.path.is_file())
        self.assertTrue(self.engine.blocked)
        self.assertEqual(len(self.memory.writes), count)

    def test_autoassembler_disable_receipt_is_scoped_and_source_bound(self):
        self.host.execute('source=' + repr(AA))
        ok = self.host.execute('ok,receipt=autoAssemble(source); return ok,type(receipt)=="table"')
        self.assertEqual(ok, (True, True))
        self.assertEqual(self.memory.read(0x1040, 4), b'\x01\0\0\0')
        with self.assertRaisesRegex(LuaHostError, 'source-mismatched'):
            self.host.execute('autoAssemble(source.."\\n",false,receipt)')
        self.assertEqual(self.memory.read(0x1040, 4), b'\x01\0\0\0')
        self.assertEqual(self.host.execute('return autoAssemble(source,false,receipt)'), (True, None))
        self.assertEqual(self.memory.read(0x1040, 4), bytes(4))
        with self.assertRaisesRegex(LuaHostError, 'stale'):
            self.host.execute('autoAssemble(source,false,receipt)')

    def test_clean_scope_receipt_allows_same_controller_state_to_restart(self):
        self.host.execute('writeInteger(0x1040,17)')
        self.engine.toggle(1, False)
        plan, directory, shared = self.engine.plan, self.engine.store.directory, self.engine.store.process_lock_dir
        self.assertTrue(self.engine.close())
        self.memory.closed = False
        replacement = TrainerEngine(plan, state_dir=directory, process_lock_dir=shared,
                                    memory_factory=lambda name: self.memory, hook_coordinator=Coordinator())
        replacement.poll()
        self.assertTrue(replacement.connected)
        self.assertEqual(self.memory.read(0x1040, 4), bytes(4))
        self.assertTrue(replacement.close())

    def test_active_assembler_export_cannot_be_unregistered_or_rebound(self):
        source = AA.replace('assert(1040,', 'define(owned,1040)\nregistersymbol(owned)\nassert(1040,').replace('[DISABLE]', '[DISABLE]\nunregistersymbol(owned)')
        self.host.execute('ok,receipt=autoAssemble(' + repr(source) + ')')
        with self.assertRaisesRegex(LuaHostError, 'disable receipt'):
            self.host.execute('unregisterSymbol("owned")')
        with self.assertRaisesRegex(LuaHostError, 'already owned'):
            self.host.execute('registerSymbol("owned",0x1050)')
        self.assertEqual(self.engine.symbols['owned'], 0x1040)

    def test_checked_autoassembler_has_no_memory_or_receipt_effects(self):
        scope = self.engine.lua_activations[1]
        before = scope.path.read_bytes()
        result = self.host.execute('local ok,r=autoAssemble(' + repr(AA) + '); return ok,r==nil', syntaxcheck=True)
        self.assertEqual(result, (True, True))
        self.assertEqual(scope.path.read_bytes(), before)
        self.assertFalse(scope.assemblies)
        self.assertEqual(self.memory.read(0x1040, 4), bytes(4))

    def test_checked_autoassembler_rejects_unknown_nasm_instruction_without_effects(self):
        scope = self.engine.lua_activations[1]
        before = scope.path.read_bytes()
        source = AA.replace('dd 1', 'unknown_instruction eax,ecx')
        with self.assertRaises(LuaHostError):
            self.host.execute('return autoAssemble(' + repr(source) + ')', syntaxcheck=True)
        self.assertEqual(scope.path.read_bytes(), before)
        self.assertFalse(scope.assemblies)
        self.assertEqual(self.memory.read(0x1040, 4), bytes(4))

    def _two_scopes(self):
        plan = deepcopy(self.engine.plan)
        entry = deepcopy(plan['entries'][0])
        entry.update(id=10, label='Second owned scope', provides=[], requires=[], dependency_ids=[],
                     enable=[{'op': 'assert', 'address': '1080', 'bytes': '00000000'},
                             {'op': 'write', 'address': '1080', 'bytes': '01000000'}],
                     disable=[{'op': 'assert', 'address': '1080', 'bytes': '01000000'},
                              {'op': 'write', 'address': '1080', 'bytes': '00000000'}])
        entry.pop('program', None)
        plan['entries'].append(entry)
        plan['selected_ids'] = sorted(row['id'] for row in plan['entries'] if row['selected'])
        identity = {'engine': 'ct2trainer', 'schema': plan['schema'],
                    'target_architecture': plan['target_architecture'], 'table_sha256': plan['table_sha256'],
                    'process_name': plan['process_name'].casefold(), 'selected_ids': plan['selected_ids']}
        plan['trainer_id'] = sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:16]
        self.assertTrue(self.engine.close())
        self.memory.closed = False
        root = Path(self.directory.name)
        self.engine = TrainerEngine(plan, state_dir=root / 'two', process_lock_dir=root / 'shared',
                                    memory_factory=lambda name: self.memory, hook_coordinator=Coordinator())
        self.engine.poll()
        self.engine.toggle(1, True)
        self.engine.toggle(10, True)
        self.host = self.engine.open_lua_activation(1)
        return self.engine.open_lua_activation(10)

    def test_cross_scope_consumer_blocks_provider_retirement_before_cancel(self):
        second = self._two_scopes()
        self.host.execute('registerSymbol("owned",0x1040)')
        source = AA.replace('1040', 'owned+4')
        second.execute('s=' + repr(source) + '; ok,r=autoAssemble(s)')
        with self.assertRaisesRegex(NativeRuntimeError, 'consumer'):
            self.engine.toggle(1, False)
        self.assertFalse(self.host.cancelled)
        self.assertEqual(self.memory.read(0x1044, 4), b'\x01\0\0\0')
        with self.assertRaisesRegex(LuaHostError, 'consumers'):
            self.host.execute('unregisterSymbol("owned")')
        self.assertEqual(second.execute('return autoAssemble(s,false,r)'), (True, None))
        self.engine.toggle(1, False)
        self.assertEqual(self.memory.read(0x1044, 4), bytes(4))

    def test_combined_close_retires_mutually_consuming_manual_symbol_scopes(self):
        second = self._two_scopes()
        self.host.execute('registerSymbol("first",0x1040)')
        second.execute('registerSymbol("second",0x1050)')
        self.host.execute('autoAssemble(' + repr(AA.replace('1040', 'second')) + ')')
        second.execute('autoAssemble(' + repr(AA.replace('1040', 'first')) + ')')
        self.assertTrue(self.engine.close(), self.engine.error)
        self.assertEqual(self.memory.read(0x1040, 4), bytes(4))
        self.assertEqual(self.memory.read(0x1050, 4), bytes(4))

    def test_symbol_journal_failure_retains_namespace_ownership(self):
        self.host.execute('registerSymbol("owned",0x1040)')
        scope = self.engine.lua_activations[1]
        with patch.object(scope, '_save', side_effect=OSError('owned journal failure')):
            with self.assertRaisesRegex(LuaHostError, 'journal failure'):
                self.host.execute('unregisterSymbol("owned")')
        self.assertEqual(scope.symbols['owned'], 0x1040)
        self.assertEqual(self.engine.symbols['owned'], 0x1040)
        self.assertTrue(self.engine.blocked)

    def test_successful_retirement_drops_engine_references_to_lua_states(self):
        for _ in range(5):
            self.host.execute('retained=string.rep("x",1024*1024)')
            self.engine.toggle(1, False)
            self.assertFalse(self.engine.lua_sessions)
            self.engine.toggle(1, True)
            self.host = self.engine.open_lua_activation(1)
        self.assertEqual(len(self.engine.lua_sessions), 1)
