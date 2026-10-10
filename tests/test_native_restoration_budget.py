"""Ignored draft: one allowance, exact ownership and honest partial cleanup."""
from contextlib import contextmanager
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from test_native_external_data import kernel_memory, ORIGINAL, REPLACEMENT, SOURCE, DataCoordinator
from test_native_lua_work_budget import Clock
from ct2trainer.native.restoration_budget import (
    RestorationBudgetError, restoration_operation, restoration_region,
    checkpoint, remaining,
)
from ct2trainer.native.lua_work_budget import (
    WorkLimits, WorkBudgetError, work_slice, broker_checkpoint, controller_cleanup,
)
from ct2trainer.native.memory import _checked_write, ProcessMemoryError
from ct2trainer.native.engine import TrainerEngine, NativeRuntimeError, _Patch
from ct2trainer.native.lua_host import LuaHostError
from ct2trainer.native.hooks import HookManager, HookUncertain
from ct2trainer.native.aa_program import prepare_program, link_program


class SharedLedgerTests(unittest.TestCase):
    def setUp(self):self.clock=Clock()

    def test_lazy_allowance_does_not_charge_prior_bounded_forward_work(self):
        with restoration_operation(self.clock) as ledger:
            self.clock.advance(20)
            self.assertIsNone(ledger.deadline)
            with controller_cleanup(lambda:None,self.clock):
                self.assertEqual(ledger.deadline,150)
                self.clock.advance(29)
                broker_checkpoint()

    def test_successive_scopes_cannot_reset_the_same_deadline(self):
        calls=[]
        with restoration_operation(self.clock):
            with controller_cleanup(lambda:None,self.clock):
                self.clock.advance(20);calls.append('first exact undo')
            with self.assertRaisesRegex(RestorationBudgetError,'deadline'):
                with controller_cleanup(lambda:None,self.clock):
                    self.clock.advance(11);broker_checkpoint();calls.append('late undo')
            with self.assertRaises(RestorationBudgetError):
                with controller_cleanup(lambda:None,self.clock):calls.append('reset attempt')
        self.assertEqual(calls,['first exact undo'])

    def test_nested_timeout_and_fake_child_clock_cannot_extend_parent(self):
        child=Clock()
        with restoration_operation(self.clock,timeout=1) as ledger:
            with self.assertRaises(RestorationBudgetError),controller_cleanup(lambda:None,self.clock):
                self.clock.advance(.8)
                with controller_cleanup(lambda:None,child,timeout=120):
                    self.assertEqual(ledger.deadline,101)
                    self.clock.advance(.1);broker_checkpoint()
                self.clock.advance(.2)
                with self.assertRaises(RestorationBudgetError):broker_checkpoint()

    def test_nested_child_can_tighten_from_original_start(self):
        with restoration_operation(self.clock,timeout=30):
            with self.assertRaises(RestorationBudgetError),controller_cleanup(lambda:None,self.clock):
                self.clock.advance(10)
                with restoration_operation(timeout=12):
                    self.clock.advance(3)
                    with self.assertRaises(RestorationBudgetError):checkpoint()

    def test_canceled_normal_guard_is_not_revived_by_controller_cleanup(self):
        canceled=False;lua_entries=[]
        def normal_guard():
            if canceled:raise WorkBudgetError('Canceled Lua generation')
        with restoration_operation(self.clock):
            with self.assertRaises(WorkBudgetError):
                with work_slice(WorkLimits(1,10000),normal_guard,self.clock):
                    canceled=True
                    with controller_cleanup(lambda:None,self.clock):
                        broker_checkpoint()
                        with self.assertRaisesRegex(WorkBudgetError,'Lua callbacks'):
                            with work_slice(WorkLimits(1,10000),lambda:None,self.clock):lua_entries.append(True)
        self.assertEqual(lua_entries,[])
        self.assertTrue(canceled)

    def test_guard_return_time_and_native_remaining_share_the_deadline(self):
        armed=False
        def slow_guard():
            if armed:self.clock.advance(2)
        with restoration_operation(self.clock,timeout=1):
            with self.assertRaises(RestorationBudgetError):
                with controller_cleanup(slow_guard,self.clock):
                    self.assertLessEqual(remaining(5),1)
                    armed=True;broker_checkpoint()

    def test_count_and_bytes_are_shared_between_nested_receipt_regions(self):
        for limits in ({'max_mutations':1},{'max_bytes':4}):
            with self.subTest(limits=limits):
                memory=kernel_memory()
                with restoration_operation(self.clock,**limits):
                    with controller_cleanup(lambda:None,self.clock):
                        _checked_write(memory,0x3000,REPLACEMENT,rollback=True)
                    with self.assertRaises(RestorationBudgetError):
                        with controller_cleanup(lambda:None,self.clock):
                            _checked_write(memory,0x3000,ORIGINAL,rollback=True)
                self.assertEqual(memory.write_calls,[(0x3000,REPLACEMENT)])

    def test_boolean_rollback_flag_alone_cannot_grant_a_cleanup_allowance(self):
        memory=kernel_memory()
        with self.assertRaisesRegex(RestorationBudgetError,'controller restoration'):
            _checked_write(memory,0x3000,REPLACEMENT,rollback=True)
        self.assertFalse(memory._write_uncertain)
        self.assertEqual(memory.write_calls,[])


class RealBackendModelTests(unittest.TestCase):
    def setUp(self):
        self.clock=Clock();self.memory=kernel_memory()
        self.engine=object.__new__(TrainerEngine)
        self.engine.memory=self.memory
        self.engine._is_executable=Mock(return_value=False)
        self.engine.blocked=False;self.engine.error=''
        def block(error):
            self.engine.error=str(error);self.engine.blocked=True
        self.engine._block=Mock(side_effect=block)

    def prepared_three_patches(self):
        before=[bytes([value])*4 for value in (1,2,3)]
        after=[bytes([value])*4 for value in (11,12,13)]
        self.memory.data[:12]=b''.join(before)
        raised=False
        def final_forward_failure():
            nonlocal raised
            if not raised and bytes(self.memory.data[:12])==b''.join(after):
                raised=True
                raise RuntimeError('Primary failure after all confirmed writes')
        self.engine._guard=final_forward_failure
        return [_Patch(0x3000+4*index,a,b) for index,(a,b) in enumerate(zip(before,after))]

    def test_successive_undo_calls_stop_after_first_return_crossing_shared_ceiling(self):
        patches=self.prepared_three_patches()
        write=self.memory._kernel.WriteProcessMemory.side_effect
        def delayed_restore(handle,address,buffer,size,transferred):
            import ctypes
            raw=ctypes.string_at(buffer,size)
            result=write(handle,address,buffer,size,transferred)
            if any(address==p.address and raw==p.original for p in patches):self.clock.advance(16)
            return result
        self.memory._kernel.WriteProcessMemory.side_effect=delayed_restore
        with restoration_operation(self.clock),self.assertRaisesRegex(NativeRuntimeError,'rollback is uncertain'):
            self.engine._write_transaction(patches)
        self.assertEqual([address for address,_ in self.memory.write_calls],[0x3000,0x3004,0x3008,0x3008,0x3004])
        self.assertEqual(bytes(self.memory.data[:4]),patches[0].changed)
        self.assertEqual(bytes(self.memory.data[4:12]),patches[1].original+patches[2].original)
        self.assertTrue(self.memory._write_uncertain)
        self.engine._block.assert_called_once()

    def test_slow_first_restore_read_starts_no_emergency_mutation(self):
        patches=self.prepared_three_patches();armed=False
        guard=self.engine._guard
        def failure():
            nonlocal armed
            try:guard()
            except Exception:armed=True;raise
        self.engine._guard=failure
        delayed=False
        def read_hook(address,size):
            nonlocal delayed
            if armed and not delayed:
                delayed=True;self.clock.advance(31)
        self.memory.read_hook=read_hook
        with restoration_operation(self.clock),self.assertRaisesRegex(NativeRuntimeError,'rollback is uncertain'):
            self.engine._write_transaction(patches)
        self.assertEqual(len(self.memory.write_calls),3)
        self.assertEqual(bytes(self.memory.data[:12]),b''.join(p.changed for p in patches))
        self.assertFalse(self.memory._write_uncertain)

    def test_partial_restore_keeps_unknown_backend_and_stops_further_writes(self):
        patches=self.prepared_three_patches()
        write=self.memory._kernel.WriteProcessMemory.side_effect
        def partial(handle,address,buffer,size,transferred):
            import ctypes
            raw=ctypes.string_at(buffer,size)
            if address==patches[-1].address and raw==patches[-1].original:
                self.memory.data[8:10]=raw[:2]
                self.memory.write_calls.append((address,raw[:2]))
                ctypes.cast(transferred,ctypes.POINTER(ctypes.c_size_t)).contents.value=2
                return False
            return write(handle,address,buffer,size,transferred)
        self.memory._kernel.WriteProcessMemory.side_effect=partial
        with restoration_operation(self.clock),self.assertRaises(NativeRuntimeError):self.engine._write_transaction(patches)
        self.assertEqual(len(self.memory.write_calls),4)
        self.assertTrue(self.memory._write_uncertain)
        self.assertEqual(bytes(self.memory.data[:8]),patches[0].changed+patches[1].changed)


class OwnedScopesTests(unittest.TestCase):
    def test_controller_close_shares_allowance_across_two_canceled_scopes(self):
        from test_native_lua_activation import OwnedLuaTests
        case=OwnedLuaTests('test_raw_write_symbol_and_scheduled_callback_are_retired_with_owner')
        case.setUp()
        try:
            second=case._two_scopes();clock=Clock()
            case.host._clock=second._clock=clock
            case.host.execute('writeInteger(0x1040,17)')
            second.execute('writeInteger(0x1044,19)')
            scopes=list(case.engine.lua_activations.values())
            memory=case.memory;write=memory.write
            def delayed_undo(address,raw):
                write(address,raw)
                if address in {0x1040,0x1044} and raw==bytes(4):clock.advance(16)
            memory.write=delayed_undo
            before=len(memory.writes)
            self.assertFalse(case.engine.close())
            self.assertTrue(case.engine.blocked)
            self.assertEqual([event for event in memory.writes[before:] if event[0] in {0x1040,0x1044}],
                             [(0x1040,bytes(4)),(0x1044,bytes(4))])
            self.assertTrue(all(scope.host.cancelled for scope in scopes))
            self.assertIn('uncertain',{scope.state for scope in scopes})
            for scope in scopes:
                self.assertTrue(scope.path.is_file())
                with self.assertRaises(LuaHostError):scope.host.execute('writeInteger(0x1040,99)')
        finally:case.tearDown()


class OwnedHookModelTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.clock=Clock();self.memory=kernel_memory();self.coordinator=DataCoordinator()
        source='''[ENABLE]\n3000:\ndd 55667788\n3004:\ndd #1\n3008:\ndd #2\n[DISABLE]\n3000:\ndd 11223344\n3004:\ndd ABABABAB\n3008:\ndd ABABABAB'''
        program=prepare_program(source,'owned.exe')
        linked=link_program(program,self.memory,_allow_external_literals=True)
        self.manager=HookManager(self.memory,Path(self.tmp.name)/'receipt.json',self.coordinator)
        self.manager.stage(linked['blocks'],_external_literal_permits=linked['_external_literal_permits'])
        save=self.manager._save
        def primary_failure(*args,**kwargs):
            save(*args,**kwargs)
            if self.manager.state=='enabled':raise RuntimeError('Primary controller failure after confirmed entries')
        self.manager._save=primary_failure

    def test_hook_rollback_stops_at_shared_deadline_and_retains_partial_receipt(self):
        write=self.memory._kernel.WriteProcessMemory.side_effect
        def slow_undo(handle,address,buffer,size,transferred):
            import ctypes
            raw=ctypes.string_at(buffer,size)
            result=write(handle,address,buffer,size,transferred)
            if raw in (ORIGINAL,b'\xAB'*4):self.clock.advance(16)
            return result
        self.memory._kernel.WriteProcessMemory.side_effect=slow_undo
        with restoration_operation(self.clock),self.assertRaises(HookUncertain):self.manager.publish()
        self.assertEqual([a for a,_ in self.memory.write_calls],[0x3000,0x3004,0x3008,0x3008,0x3004])
        self.assertEqual(bytes(self.memory.data[:4]),REPLACEMENT)
        self.assertEqual(self.manager.state,'uncertain')
        self.assertTrue(self.manager.path.is_file())

    def test_shared_allowance_cannot_override_lost_held_event(self):
        self.memory.alive_hook=lambda n:setattr(self.coordinator,'held',False) if n==2 and len(self.memory.write_calls)>=3 else None
        with restoration_operation(self.clock),self.assertRaises(HookUncertain):self.manager.publish()
        self.assertEqual(len(self.memory.write_calls),3)
        self.assertEqual(self.manager.state,'uncertain')
        self.assertFalse(self.memory._write_uncertain)


class UnpublishedReleaseTests(unittest.TestCase):
    def setUp(self):
        from test_native_hooks import _Memory
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clock = Clock()
        self.memory = _Memory()
        self.manager = HookManager(self.memory, Path(self.tmp.name) / 'receipt.json', None)
        for index in range(4):
            self.manager.allocate('unpublished_' + str(index), 32, executable=False)

    def test_unstarted_operation_begins_one_release_ceiling_and_retains_later_allocations(self):
        release = self.memory.release
        events = []
        def delayed(address):
            events.append((address, self.clock.value))
            release(address)
            self.clock.advance(16)
        self.memory.release = delayed
        with restoration_operation(self.clock) as ledger, self.assertRaises(HookUncertain):
            self.manager.abandon_unpublished()
        self.assertEqual(len(events), 2)
        self.assertEqual(ledger.started, 100)
        self.assertEqual(ledger.mutations, 2)
        self.assertEqual(self.manager.state, 'uncertain')
        self.assertTrue(self.manager.path.is_file())
        self.assertEqual(len(self.memory.data) - 2, 2)

    def test_prior_restoration_deadline_cannot_be_restarted_by_allocation_abandonment(self):
        events = []
        self.memory.release = lambda address: events.append(address)
        with restoration_operation(self.clock):
            with self.assertRaises(RestorationBudgetError), controller_cleanup(lambda: None, self.clock):
                self.clock.advance(31)
                with self.assertRaises(RestorationBudgetError):
                    self.manager.abandon_unpublished()
        self.assertEqual(events, [])
        self.assertEqual(self.manager.state, 'preparing')

    def test_returned_intent_save_cannot_start_late_release(self):
        save = self.manager._save
        def delayed():
            save()
            if self.manager.state == 'abandon-intent':
                self.clock.advance(31)
        self.manager._save = delayed
        with restoration_operation(self.clock), self.assertRaises(HookUncertain):
            self.manager.abandon_unpublished()
        self.assertEqual(self.memory.releases, [])
        self.assertEqual(self.manager.state, 'uncertain')
        self.assertTrue(self.manager.path.is_file())


class RealReleaseModelTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.memory = kernel_memory()
        self.memory._owned_allocations = {0x8000: {'size': 4096}}
        self.memory._kernel.VirtualFreeEx = Mock(return_value=True)

    def test_last_release_guard_return_expiry_starts_no_virtual_free(self):
        def slow_guard():
            self.clock.advance(31)
        with restoration_operation(self.clock):
            with self.assertRaises(RestorationBudgetError), controller_cleanup(lambda: None, self.clock):
                self.memory._release_checked(0x8000, slow_guard)
        self.memory._kernel.VirtualFreeEx.assert_not_called()
        self.assertIn(0x8000, self.memory._owned_allocations)
        self.assertFalse(self.memory._write_uncertain)

    def test_late_free_return_keeps_unknown_backend_and_stops_second_release(self):
        self.memory._owned_allocations[0x9000] = {'size': 4096}
        self.memory._kernel.VirtualFreeEx.side_effect = lambda *args: self.clock.advance(31) or True
        with restoration_operation(self.clock):
            with self.assertRaises(RestorationBudgetError), controller_cleanup(lambda: None, self.clock):
                self.memory._release_checked(0x8000, lambda: None)
                self.memory._release_checked(0x9000, lambda: None)
        self.memory._kernel.VirtualFreeEx.assert_called_once()
        self.assertNotIn(0x8000, self.memory._owned_allocations)
        self.assertIn(0x9000, self.memory._owned_allocations)
        self.assertTrue(self.memory._write_uncertain)


class AllocationRepairTests(unittest.TestCase):
    def setUp(self):
        from test_native_memory import _region
        from ct2trainer.native.memory import _SYSTEM_INFO
        import ctypes
        self.clock = Clock()
        self.memory = kernel_memory()
        def system_info(pointer):
            info = ctypes.cast(pointer, ctypes.POINTER(_SYSTEM_INFO)).contents
            info.page_size = 4096
            info.allocation_granularity = 65536
        self.memory._kernel.GetSystemInfo = Mock(side_effect=system_info)
        self.memory._kernel.VirtualAllocEx = Mock(return_value=0x8000)
        self.memory._kernel.VirtualFreeEx = Mock(return_value=True)
        # A failed post-allocation inventory must not claim no allocation.
        self.memory._query = Mock(return_value=_region(0x8000, 4096, 0x02))

    def test_failed_allocation_check_obeys_existing_shared_deadline(self):
        query = self.memory._query
        def late_query(address):
            self.clock.advance(2)
            return query(address)
        self.memory._query = late_query
        with restoration_operation(self.clock, timeout=1):
            with self.assertRaises(ProcessMemoryError), controller_cleanup(lambda: None, self.clock):
                self.memory.allocate(32)
        self.memory._kernel.VirtualFreeEx.assert_not_called()
        self.assertIn(0x8000, self.memory._owned_allocations)
        self.assertTrue(self.memory._write_uncertain)

    def test_failed_allocation_check_starts_shared_early_reclamation(self):
        with restoration_operation(self.clock) as ledger, self.assertRaises(ProcessMemoryError):
            self.memory.allocate(32)
        self.memory._kernel.VirtualFreeEx.assert_called_once()
        self.assertNotIn(0x8000, self.memory._owned_allocations)
        self.assertEqual(ledger.mutations, 1)
        self.assertEqual(ledger.bytes, 4096)
        self.assertFalse(self.memory._write_uncertain)


class ProtectionRepairTests(unittest.TestCase):
    def test_expired_preparation_starts_no_virtual_protect(self):
        memory = kernel_memory()
        memory.protection = 0x20
        clock = Clock()
        memory.query_hook = lambda address: clock.advance(31)
        with restoration_operation(clock):
            with self.assertRaises(RestorationBudgetError), controller_cleanup(lambda: None, clock):
                memory._write_checked(0x3000, REPLACEMENT, _rollback=True)
        memory._kernel.VirtualProtectEx.assert_not_called()
        memory._kernel.WriteProcessMemory.assert_not_called()
        self.assertFalse(memory._write_uncertain)

    def test_already_changed_page_is_repaired_after_preparation_call_returns_late(self):
        memory = kernel_memory()
        memory.protection = 0x20
        clock = Clock()
        protect = memory._kernel.VirtualProtectEx.side_effect
        def late_preparation(*args):
            result = protect(*args)
            if args[3] == 0x40:
                clock.advance(31)
            return result
        memory._kernel.VirtualProtectEx.side_effect = late_preparation
        with restoration_operation(clock):
            with self.assertRaises(RestorationBudgetError), controller_cleanup(lambda: None, clock):
                memory._write_checked(0x3000, REPLACEMENT, _rollback=True)
        self.assertEqual([call.args[3] for call in memory._kernel.VirtualProtectEx.call_args_list], [0x40, 0x20])
        memory._kernel.WriteProcessMemory.assert_not_called()
        self.assertEqual(memory.protection, 0x20)
        self.assertFalse(memory._write_uncertain)


class EngineReclamationPropagationTests(unittest.TestCase):
    def setUp(self):
        from test_native_hooks import _Memory
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clock = Clock()
        self.memory = _Memory()
        self.manager = HookManager(self.memory, Path(self.tmp.name) / 'receipt.json', None)
        self.manager.allocate('never_published', 32, executable=False)
        save = self.manager._save
        def delayed_intent():
            save()
            if self.manager.state == 'abandon-intent':
                self.clock.advance(31)
        self.manager._save = delayed_intent
        self.engine = object.__new__(TrainerEngine)
        self.engine.memory = self.memory
        self.engine.plan = {'trainer_id': 'a' * 16}
        self.engine.store = Mock(directory=Path(self.tmp.name))
        self.engine.hook_coordinator = DataCoordinator()
        self.engine.symbols = {}
        self.engine.applied = {}
        self.engine.frozen = {}
        self.engine.lua_activations = {}
        self.engine.hooks = {}
        self.engine.retired_hooks = []
        self.engine._hook_lifetime_count = self.engine._hook_lifetime_bytes = 0
        self.engine._owned_provider_data = Mock(return_value=([], []))
        self.engine._is_executable = Mock(return_value=True)
        self.engine.blocked = self.engine.closed = False
        self.engine.error = self.engine.status = ''

    def assert_retained_failure(self):
        self.assertTrue(self.engine.blocked)
        self.assertIn('Primary failure', self.engine.error)
        self.assertIn('compensation is uncertain', self.engine.error)
        self.assertEqual(self.engine.retired_hooks, [self.manager])
        self.assertEqual(self.memory.releases, [])
        self.assertEqual(self.manager.state, 'uncertain')
        self.assertTrue(self.manager.path.is_file())
        with self.assertRaises(NativeRuntimeError):
            self.engine._guard()

    def test_program_link_failure_reclamation_blocks_controller_and_keeps_manager(self):
        from unittest.mock import patch
        program = prepare_program('[ENABLE]\n3000:\ndd #1\n[DISABLE]\n3000:\ndd #0', 'owned.exe')
        with restoration_operation(self.clock), patch('ct2trainer.native.hooks.HookManager', return_value=self.manager), \
             patch('ct2trainer.native.aa_program.preflight_program', return_value={'allocation_requests': [], 'scan_results': []}), \
             patch('ct2trainer.native.aa_program.link_program', side_effect=RuntimeError('Primary failure')), \
             self.assertRaisesRegex(NativeRuntimeError, 'compensation is uncertain'):
            self.engine._install_program(program, 1)
        self.assert_retained_failure()

    def test_literal_code_stage_failure_reclamation_blocks_controller(self):
        from unittest.mock import patch
        self.manager.stage = Mock(side_effect=RuntimeError('Primary failure'))
        with restoration_operation(self.clock), patch('ct2trainer.native.hooks.HookManager', return_value=self.manager), \
             self.assertRaisesRegex(NativeRuntimeError, 'compensation is uncertain'):
            self.engine._enable_literal_code({'id': 1}, [], {})
        self.assert_retained_failure()

    def test_owned_literal_value_stage_failure_reclamation_blocks_controller(self):
        from unittest.mock import patch
        self.manager.stage = Mock(side_effect=RuntimeError('Primary failure'))
        self.engine._owned_provider_data = Mock(return_value=([], [(0x1000, 4, 0x1000, 4096)]))
        with restoration_operation(self.clock), patch('ct2trainer.native.hooks.HookManager', return_value=self.manager), \
             self.assertRaisesRegex(NativeRuntimeError, 'compensation is uncertain'):
            self.engine._write_owned_literal_values([_Patch(0x1000, b'\0' * 4, b'\1' * 4)])
        self.assert_retained_failure()


    def test_pure_external_publish_exactly_compensated_terminal_is_not_abandoned_again(self):
        from unittest.mock import patch
        self.memory = self.engine.memory = kernel_memory()
        self.manager = HookManager(self.memory, Path(self.tmp.name) / 'external.json', DataCoordinator())
        save = self.manager._save
        failed = False
        def fail_after_confirmed_publication():
            nonlocal failed
            save()
            if not failed and self.manager.state == 'enabled':
                failed = True
                raise RuntimeError('Primary failure after exact publication')
        self.manager._save = fail_after_confirmed_publication
        program = prepare_program(SOURCE, 'owned.exe')
        with restoration_operation(self.clock), patch('ct2trainer.native.hooks.HookManager', return_value=self.manager), \
             self.assertRaisesRegex(NativeRuntimeError, 'Primary failure'):
            self.engine._install_program(program, 1)
        self.assertFalse(self.engine.blocked)
        self.assertEqual(self.engine.retired_hooks, [])
        self.assertEqual(self.manager.state, 'abandoned')
        self.assertTrue(self.manager.path.is_file())
        self.assertEqual(bytes(self.memory.data[:4]), ORIGINAL)
        self.assertEqual([raw for _, raw in self.memory.write_calls], [REPLACEMENT, ORIGINAL])


class ValueRootOperationTests(unittest.TestCase):
    def exercise(self, freeze):
        from unittest.mock import patch
        from test_native_hooks import _Memory
        with tempfile.TemporaryDirectory() as directory:
            memory = _Memory()
            clock = Clock()
            engine = object.__new__(TrainerEngine)
            engine._clock = clock
            engine.memory = memory
            engine.plan = {'trainer_id': 'a' * 16}
            engine.store = Mock(directory=Path(directory))
            engine.hook_coordinator = None
            engine.symbols = {}; engine.applied = {}; engine.frozen = {}; engine.lua_activations = {}
            engine.hooks = {}; engine.retired_hooks = []
            engine._hook_lifetime_count = engine._hook_lifetime_bytes = 0
            engine._owned_provider_data = Mock(return_value=([], []))
            engine._check_patches = Mock()
            engine._guard = Mock()
            engine.blocked = engine.closed = engine.busy = False
            engine.error = engine.status = ''; engine.entry_errors = {}
            value = {'id': 2, 'label': 'Own dependent value', 'variable_type': '4 Bytes'}
            engine._entry = Mock(return_value=value)
            manager = HookManager(memory, Path(directory) / 'provider.json', None)
            save = manager._save
            failed = delayed = False
            def delayed_compensation():
                nonlocal failed, delayed
                save()
                if not failed and manager.state == 'enabled':
                    failed = True
                    raise RuntimeError('Primary provider publication failure')
                if failed and not delayed and manager.state == 'staged':
                    delayed = True
                    clock.advance(20)
            manager._save = delayed_compensation
            releases = []
            release = memory.release
            def delayed_release(address):
                releases.append(clock.value)
                release(address)
                clock.advance(15)
            memory.release = delayed_release
            program = prepare_program('[ENABLE]\nalloc(provider,#32)\nregistersymbol(provider)\nprovider:\ndd #1\n'
                                      '[DISABLE]\nunregistersymbol(provider)\ndealloc(provider)', 'owned.exe')
            engine._dependencies = lambda _: engine._install_program(program, 1)
            with patch('ct2trainer.native.hooks.HookManager', return_value=manager), \
                 self.assertRaisesRegex(NativeRuntimeError, 'compensation is uncertain'):
                if freeze:
                    engine.set_freeze(2, True)
                else:
                    engine.set_value(2, '7')
            self.assertEqual(releases, [120])
            self.assertEqual(clock.value, 135)
            self.assertTrue(engine.blocked)
            self.assertEqual(engine.retired_hooks, [manager])
            self.assertEqual(manager.state, 'uncertain')
            self.assertTrue(manager.path.is_file())
            self.assertFalse(engine.busy)
            self.assertEqual(engine.frozen, {})

    def test_direct_value_provider_compensation_uses_one_root_allowance(self):
        self.exercise(False)

    def test_direct_freeze_provider_compensation_uses_one_root_allowance(self):
        self.exercise(True)


if __name__=='__main__':unittest.main()
