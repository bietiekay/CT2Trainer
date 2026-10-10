"""Deterministic time accounting, real Lua53, and exact owned receipt undo."""
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ct2trainer.native.lua_host import LuaHost, LuaHostError
from ct2trainer.native.lua_work_budget import (
    WorkLimits, WorkBudgetError, work_slice, broker_checkpoint,
    remaining_seconds, controller_cleanup,
)
from ct2trainer.native.assembler import NasmAssembler


class Clock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class Broker:
    generation = 0

    def __init__(self, clock, delay=0, action=None):
        self.clock, self.delay, self.action = clock, delay, action
        self.calls = []

    def call(self, name, args, **options):
        self.calls.append((name, args, options))
        self.clock.advance(self.delay)
        if self.action is not None:
            return self.action(name, args, options)
        return 7 if name == 'readInteger' else None


class HostBudgetTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()

    def host(self, broker=None, **options):
        broker = broker or Broker(self.clock)
        options.setdefault('_clock', self.clock)
        options.setdefault('broker_call_timeout', 1.0)
        options.setdefault('broker_timeout', 2.0)
        options.setdefault('wall_timeout', 3.0)
        host = LuaHost(broker, **options)
        self.addCleanup(host.cancel)
        return host, broker

    def test_slow_success_is_excluded_only_from_lua_time(self):
        host, broker = self.host(Broker(self.clock, delay=0.4))
        self.assertEqual(host.execute('return readInteger(1),readInteger(2)'), (7, 7))
        self.assertEqual(len(broker.calls), 2)
        self.assertAlmostEqual(self.clock.value, 100.8)

    def test_per_call_expiry_is_sticky_even_when_caught(self):
        host, broker = self.host(Broker(self.clock, delay=1.1))
        with self.assertRaisesRegex(LuaHostError, 'broker call deadline'):
            host.execute('local ok=pcall(readInteger,1); return true')
        self.assertEqual(len(broker.calls), 1)
        self.assertEqual(host.execute('return 9'), 9)

    def test_cumulative_expiry_is_not_reset_between_dispatches(self):
        host, broker = self.host(Broker(self.clock, delay=0.6), broker_timeout=1)
        with self.assertRaisesRegex(LuaHostError, 'cumulative broker deadline'):
            host.execute('readInteger(1); pcall(readInteger,2); return true')
        self.assertEqual(len(broker.calls), 2)

    def test_call_count_refuses_next_broker_before_side_effect(self):
        host, broker = self.host(broker_call_limit=1)
        with self.assertRaisesRegex(LuaHostError, 'broker call budget'):
            host.execute('readInteger(1); pcall(readInteger,2); return true')
        self.assertEqual(len(broker.calls), 1)

    def test_overall_wall_ceiling_is_independent(self):
        host, broker = self.host(Broker(self.clock, delay=0.6), wall_timeout=0.5)
        with self.assertRaisesRegex(LuaHostError, 'overall wall deadline'):
            host.execute('return readInteger(1)')
        self.assertEqual(len(broker.calls), 1)

    def test_instruction_limit_is_not_inflated_by_broker_allowance(self):
        host, _ = self.host(instruction_limit=1000)
        with self.assertRaisesRegex(LuaHostError, 'execution budget'):
            host.execute('while true do end')

    def test_output_transport_keeps_lua_time_quota(self):
        host, _ = self.host(Broker(self.clock, delay=0.4))
        convert = host._to_lua
        def expensive(value, *args, **options):
            self.clock.advance(0.3)
            return convert(value, *args, **options)
        with patch.object(host, '_to_lua', expensive):
            with self.assertRaisesRegex(LuaHostError, 'execution budget'):
                host.execute('return readInteger(1)')

    def test_input_transport_keeps_lua_time_and_never_dispatches(self):
        host, broker = self.host()
        convert = host._from_lua
        def expensive(value, *args, **options):
            self.clock.advance(0.3)
            return convert(value, *args, **options)
        with patch.object(host, '_from_lua', expensive):
            with self.assertRaisesRegex(LuaHostError, 'execution budget'):
                host.execute('return readInteger(1)')
        self.assertFalse(broker.calls)

    def test_transport_resource_limits_are_not_paused(self):
        host, broker = self.host(Broker(self.clock, delay=0.4,
                                        action=lambda *args: [1] * 1000))
        with patch('ct2trainer.native.lua_host.MAX_TRANSPORT_NODES', 128):
            with self.assertRaisesRegex(LuaHostError, 'transport expanded node'):
                host.execute('return readInteger(1)')
        self.assertEqual(len(broker.calls), 1)

    def test_final_slice_check_accounts_short_python_operation(self):
        host, _ = self.host()
        def operation():
            self.clock.advance(0.3)
            return 1
        with self.assertRaisesRegex(LuaHostError, 'execution budget'):
            host._slice(operation)

    def test_child_host_lua_is_not_hidden_inside_parent_broker(self):
        child, _ = self.host(timeout=10)
        checkpoint = child._checkpoint
        def consume_lua(reason=None):
            self.clock.advance(0.3)
            checkpoint(reason)
        parent, _ = self.host(Broker(self.clock, action=lambda *args: child.execute('while true do end')))
        with patch.object(child, '_checkpoint', consume_lua):
            with self.assertRaisesRegex(LuaHostError, 'execution budget'):
                parent.execute('return readInteger(1)')

    def test_child_broker_cannot_reset_parent_cumulative_allowance(self):
        child, _ = self.host(Broker(self.clock, delay=0.4), broker_timeout=10)
        def action(*args):
            return child.execute('return readInteger(1)')
        parent, _ = self.host(Broker(self.clock, delay=0.4, action=action), broker_timeout=0.7)
        with self.assertRaisesRegex(LuaHostError, 'cumulative broker deadline'):
            parent.execute('return readInteger(1)')

    def test_reentrant_same_host_remains_refused(self):
        host, broker = self.host()
        broker.action = lambda *args: host.execute('return 7')
        with self.assertRaisesRegex(LuaHostError, 'reentrant'):
            host.execute('return readInteger(1)')

    def test_many_checker_sources_share_outer_call_count(self):
        host, broker = self.host(broker_call_limit=1)
        with self.assertRaisesRegex(LuaHostError, 'broker call budget'):
            host.check_sources(['return readInteger(1)', 'return readInteger(2)'])
        self.assertEqual(len(broker.calls), 1)

    def test_helper_replay_and_checker_execution_share_budget(self):
        host, broker = self.host(Broker(self.clock, delay=0.4), broker_timeout=0.7)
        host.install_helpers('seed=readInteger(1); function helper() return seed end')
        with self.assertRaisesRegex(LuaHostError, 'cumulative broker deadline'):
            host.execute('return readInteger(2)', syntaxcheck=True)
        self.assertEqual(host.execute('return helper()'), 7)
        self.assertFalse(host.cancelled)

    def test_helper_mutation_stays_fatal_even_with_invalid_arguments(self):
        host, broker = self.host()
        with self.assertRaisesRegex(LuaHostError, 'forbidden mutation|cannot call mutation'):
            host.install_helpers('pcall(function() writeInteger(function() end,7) end)')
        self.assertTrue(host.cancelled)
        self.assertFalse(broker.calls)

    def test_timer_callbacks_in_one_tick_share_cumulative_time(self):
        host, broker = self.host(Broker(self.clock, delay=0.4), broker_timeout=1)
        host.execute('for i=1,3 do local t=createTimer(nil,true); t.Interval=1; t.OnTimer=function() readInteger(1) end end')
        with self.assertRaisesRegex(LuaHostError, 'cumulative broker deadline'):
            host.tick(1)
        self.assertEqual(len(broker.calls), 3)

    def test_workers_in_one_tick_share_cumulative_time(self):
        host, broker = self.host(Broker(self.clock, delay=0.4), broker_timeout=1)
        host.execute('for i=1,3 do createThread(function() readInteger(1); sleep(1) end) end')
        with self.assertRaisesRegex(LuaHostError, 'cumulative broker deadline'):
            host.tick(0)
        self.assertEqual(len(broker.calls), 3)

    def test_cancellation_after_success_refuses_return_and_followup(self):
        host, broker = self.host()
        broker.action = lambda *args: (host.cancel(), 7)[1]
        with self.assertRaisesRegex(LuaHostError, 'cancelled'):
            host.execute('readInteger(1); readInteger(2)')
        self.assertEqual(len(broker.calls), 1)

    def test_generation_change_after_success_refuses_return(self):
        host, broker = self.host()
        def stale(*args):
            broker.generation = 1
            return 7
        broker.action = stale
        with self.assertRaisesRegex(LuaHostError, 'Stale'):
            host.execute('return readInteger(1)')

    def test_outer_controller_envelope_accumulates_separate_lua_chunks(self):
        host, broker = self.host(Broker(self.clock, delay=0.4), broker_timeout=0.7)
        with self.assertRaisesRegex(LuaHostError, 'cumulative broker deadline'):
            with host.controller_work():
                host.execute('readInteger(1)')
                host.execute('readInteger(2)')
        self.assertEqual(len(broker.calls), 2)

    def test_direct_controller_work_remains_bounded_without_broker_calls(self):
        host, broker = self.host(broker_timeout=0.7)
        with self.assertRaisesRegex(LuaHostError, 'cumulative broker deadline'):
            with host.controller_work():
                self.clock.advance(0.8)
                broker_checkpoint()
        self.assertFalse(broker.calls)

    def test_legacy_expansion_helper_cannot_reset_between_chunks(self):
        host, broker = self.host(Broker(self.clock, delay=0.4), broker_timeout=0.7)
        source = '[ENABLE]\n{$lua}\nreadInteger(1)\n{$asm}\n{$lua}\nreadInteger(2)\n{$asm}\n[DISABLE]'
        with self.assertRaisesRegex(LuaHostError, 'cumulative broker deadline'):
            host.expand_assembler(source)
        self.assertEqual(len(broker.calls), 2)


class PrimitiveBudgetTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.limits = WorkLimits(0.25, 1_000_000, 0.5, 1, 10, 2)

    def test_remaining_context_never_extends_primitive_timeout(self):
        with work_slice(self.limits, lambda: None, self.clock) as budget:
            with budget.dispatch():
                self.assertAlmostEqual(remaining_seconds(10), 0.5)
                self.assertEqual(remaining_seconds(0.1), 0.1)
                self.clock.advance(0.3)
                self.assertAlmostEqual(remaining_seconds(10), 0.2)
        self.assertEqual(remaining_seconds(10), 10)

    def test_nasm_consumes_remaining_context_and_checks_return(self):
        assembler = NasmAssembler()
        seen = []
        def run(command, **options):
            seen.append(options['timeout'])
            self.clock.advance(0.4)
            Path(command[command.index('-o') + 1]).write_bytes(b'\x90')
            return SimpleNamespace(returncode=0, stderr=b'')
        with work_slice(self.limits, lambda: None, self.clock) as budget:
            with budget.dispatch(), patch('ct2trainer.native.assembler.subprocess.run', run):
                self.assertEqual(assembler.assemble('bits 64\nnop\n'), b'\x90')
        self.assertAlmostEqual(seen[0], 0.5)

    def test_module_scan_observes_cooperative_context_after_read(self):
        from test_native_memory import _memory, _region
        memory = _memory()
        memory.module = lambda *args: (0x1000, 16)
        memory._query = lambda *args: _region(0x1000, 16)
        def read(*args):
            self.clock.advance(0.6)
            return bytes.fromhex('AA BB') + bytes(14)
        memory.read = read
        with self.assertRaisesRegex(WorkBudgetError, 'broker call deadline'):
            with work_slice(self.limits, lambda: None, self.clock) as budget:
                with budget.dispatch():
                    memory.scan_module('Owned.exe', 'AA BB')

    def test_publication_rechecks_before_any_live_entry_write(self):
        from test_native_hooks import HookTests
        case = HookTests('test_staging_never_changes_entry_and_publication_requires_safe_point')
        try:
            case.setUp()
            case.prepare()
            original = case.memory.read(0x1000, 5)
            case.manager.publication_guard = lambda: self.clock.advance(0.6)
            with self.assertRaisesRegex(WorkBudgetError, 'broker call deadline'):
                with work_slice(self.limits, lambda: None, self.clock) as budget:
                    with budget.dispatch():
                        case.manager.publish()
            self.assertEqual(case.memory.read(0x1000, 5), original)
            self.assertEqual(case.manager.state, 'staged')
            self.assertFalse(any(address == 0x1000 for address, _ in case.memory.writes))
        finally:
            case.doCleanups()

    def test_post_publication_expiry_keeps_exact_rollback_receipt(self):
        from test_native_hooks import HookTests
        case = HookTests('test_staging_never_changes_entry_and_publication_requires_safe_point')
        try:
            case.setUp()
            case.prepare()
            original = case.memory.read(0x1000, 5)
            case.memory.before_write = lambda *args: self.clock.advance(0.6)
            with self.assertRaisesRegex(WorkBudgetError, 'broker call deadline'):
                with work_slice(self.limits, lambda: None, self.clock) as budget:
                    with budget.dispatch():
                        case.manager.publish()
            self.assertEqual(case.memory.read(0x1000, 5), original)
            self.assertEqual(case.manager.state, 'retired')
            self.assertTrue(case.path.is_file())
        finally:
            case.doCleanups()

    def test_cleanup_has_own_bound_and_refuses_user_lua(self):
        host = LuaHost(Broker(self.clock), _clock=self.clock)
        self.addCleanup(host.cancel)
        with controller_cleanup(lambda: None, self.clock, timeout=1):
            self.clock.advance(0.4)
            broker_checkpoint()
            with self.assertRaisesRegex(LuaHostError, 'refused during controller cleanup'):
                host.execute('return 7')
        with self.assertRaisesRegex(WorkBudgetError, 'Shared restoration deadline'):
            with controller_cleanup(lambda: None, self.clock, timeout=1):
                self.clock.advance(1.1)
                broker_checkpoint()

    def test_cleanup_initial_filesystem_guard_consumes_broker_allowance(self):
        entered = []
        def guard():
            self.clock.advance(0.3)
        with controller_cleanup(guard, self.clock, timeout=30):
            entered.append(True)
            broker_checkpoint()
        self.assertEqual(entered, [True])

    def test_cleanup_guard_return_rechecks_deadline_before_mutation_admission(self):
        armed, admitted = False, []
        def guard():
            if armed:
                self.clock.advance(31)
        with self.assertRaisesRegex(WorkBudgetError, 'deadline'):
            with controller_cleanup(guard, self.clock, timeout=30):
                armed = True
                broker_checkpoint()
                admitted.append('new mutation')
        self.assertEqual(admitted, [])

    def test_publication_final_original_read_cannot_start_expired_write(self):
        from test_native_hooks import HookTests
        case = HookTests('test_staging_never_changes_entry_and_publication_requires_safe_point')
        try:
            case.setUp()
            case.prepare()
            read = case.memory.read
            delayed = False
            def final_guard(address, size):
                nonlocal delayed
                raw = read(address, size)
                if address == 0x1000 and case.manager.state == 'publication-intent' and not delayed:
                    delayed = True
                    self.clock.advance(0.6)
                return raw
            before = len(case.memory.writes)
            with patch.object(case.memory, 'read', final_guard):
                with self.assertRaisesRegex(WorkBudgetError, 'broker call deadline'):
                    with work_slice(self.limits, lambda: None, self.clock) as budget:
                        with budget.dispatch():
                            case.manager.publish()
            self.assertTrue(delayed)
            self.assertEqual(case.memory.read(0x1000, 5), bytes.fromhex('B8 01 00 00 00'))
            self.assertEqual(len(case.memory.writes), before)
            self.assertEqual(case.manager.state, 'staged')
        finally:
            case.doCleanups()

    def test_disable_final_original_read_cannot_start_expired_restore(self):
        from test_native_hooks import HookTests
        case = HookTests('test_staging_never_changes_entry_and_publication_requires_safe_point')
        try:
            case.setUp()
            case.prepare()
            case.manager.publish()
            live = case.memory.read(0x1000, 5)
            read = case.memory.read
            delayed = False
            def final_guard(address, size):
                nonlocal delayed
                raw = read(address, size)
                if address == 0x1000 and case.manager.state == 'disable-intent' and not delayed:
                    delayed = True
                    self.clock.advance(0.6)
                return raw
            before = len(case.memory.writes)
            with patch.object(case.memory, 'read', final_guard):
                with self.assertRaisesRegex(WorkBudgetError, 'broker call deadline'):
                    with work_slice(self.limits, lambda: None, self.clock) as budget:
                        with budget.dispatch():
                            case.manager.disable()
            self.assertTrue(delayed)
            self.assertEqual(case.memory.read(0x1000, 5), live)
            self.assertEqual(len(case.memory.writes), before)
            self.assertTrue(case.path.is_file())
        finally:
            case.doCleanups()

    def test_debugger_expiry_after_busy_acquisition_releases_busy(self):
        from ct2trainer.native.debug_coordinator import DebugEventCoordinator
        from test_native_debug_coordinator import _Memory
        coordinator = DebugEventCoordinator()
        clock = self.clock
        class Busy:
            released = False
            def acquire(self, **options):
                clock.advance(0.6)
                return True
            def release(self):
                self.released = True
        busy = coordinator._busy = Busy()
        def worker(memory, identity, ranges, state, *args):
            state.held = True
            state.ready.set()
            state.release.wait(1)
            state.finished.set()
        coordinator._run = worker
        with self.assertRaisesRegex(WorkBudgetError, 'broker call deadline'):
            with work_slice(self.limits, lambda: None, self.clock) as budget:
                with budget.dispatch():
                    with coordinator.hold(_Memory(), [(0x1000, 5)]):
                        self.fail('Expired acquisition cannot expose a proof')
        self.assertTrue(busy.released)


class OwnedReceiptBudgetTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()

    def _owned_case(self):
        from test_native_lua_activation import OwnedLuaTests
        case = OwnedLuaTests('test_raw_write_symbol_and_scheduled_callback_are_retired_with_owner')
        case.setUp()
        self.addCleanup(case.tearDown)
        case.host._clock = self.clock
        case.host.work_limits = WorkLimits(0.25, 1_000_000, 0.5, 2, 100, 3)
        return case

    def test_raw_data_intent_fsync_expiry_refuses_write_and_clears_pending(self):
        case = self._owned_case()
        scope = case.engine.lua_activations[1]
        save = scope._save
        def slow_intent(**options):
            save(**options)
            if scope.state == 'data-write-intent':
                self.clock.advance(0.6)
        before = len(case.memory.writes)
        with patch.object(scope, '_save', slow_intent):
            with self.assertRaisesRegex(LuaHostError, 'broker call deadline'):
                case.host.execute('return writeInteger(0x1040,17)')
        self.assertEqual(case.memory.read(0x1040, 4), bytes(4))
        self.assertEqual(len(case.memory.writes), before)
        self.assertIsNone(scope.pending)
        self.assertEqual(scope.state, 'open')
        self.assertFalse(case.engine.blocked)

    def test_final_data_byte_guard_expiry_refuses_default_engine_write(self):
        from ct2trainer.native.engine import _Patch
        case = self._owned_case()
        read, calls = case.memory.read, []
        def final_guard(address, size):
            raw = read(address, size)
            if address == 0x1040:
                calls.append(address)
                if len(calls) == 2:
                    self.clock.advance(0.6)
            return raw
        before = len(case.memory.writes)
        with patch.object(case.memory, 'read', final_guard):
            with self.assertRaisesRegex(WorkBudgetError, 'broker call deadline'):
                with work_slice(case.host.work_limits, lambda: None, self.clock) as budget:
                    with budget.dispatch():
                        case.engine._write_transaction([_Patch(0x1040, bytes(4), b'\x11\0\0\0')])
        self.assertEqual(case.memory.read(0x1040, 4), bytes(4))
        self.assertEqual(len(case.memory.writes), before)
        self.assertFalse(case.engine.blocked)

    def test_later_data_patch_expiry_retains_exact_emergency_rollback(self):
        from ct2trainer.native.engine import _Patch
        case = self._owned_case()
        read, calls = case.memory.read, []
        def final_guard(address, size):
            raw = read(address, size)
            if address == 0x1044:
                calls.append(address)
                if len(calls) == 2:
                    self.clock.advance(0.6)
            return raw
        before = len(case.memory.writes)
        patches = [_Patch(0x1040, bytes(4), b'\x11\0\0\0'),
                   _Patch(0x1044, bytes(4), b'\x13\0\0\0')]
        with patch.object(case.memory, 'read', final_guard):
            with self.assertRaisesRegex(WorkBudgetError, 'original bytes restored.*broker call deadline'):
                with work_slice(case.host.work_limits, lambda: None, self.clock) as budget:
                    with budget.dispatch():
                        case.engine._write_transaction(patches)
        self.assertEqual(case.memory.read(0x1040, 8), bytes(8))
        self.assertEqual(case.memory.writes[before:], [(0x1040, b'\x11\0\0\0'), (0x1040, bytes(4))])
        self.assertFalse(case.engine.blocked)

    def test_cleanup_first_patch_guard_expiry_starts_no_undo_write(self):
        case = self._owned_case()
        scope = case.engine.lua_activations[1]
        case.host.execute('writeInteger(0x1040,17); writeInteger(0x1044,19)')
        read = case.memory.read
        delayed = False
        def slow_guard(address, size):
            nonlocal delayed
            raw = read(address, size)
            if address in {0x1040, 0x1044} and scope.state == 'closing' and not delayed:
                delayed = True
                self.clock.advance(31)
            return raw
        before = len(case.memory.writes)
        with patch.object(case.memory, 'read', slow_guard):
            with self.assertRaisesRegex(LuaHostError, 'deadline'):
                scope.close()
        self.assertTrue(delayed)
        self.assertEqual(len(case.memory.writes), before)
        self.assertEqual(case.memory.read(0x1040, 8), b'\x11\0\0\0\x13\0\0\0')
        self.assertEqual(scope.state, 'uncertain')
        self.assertTrue(case.engine.blocked)
        self.assertTrue(scope.path.is_file())

    def test_cleanup_later_patch_expiry_stops_before_undo_of_undo(self):
        case = self._owned_case()
        scope = case.engine.lua_activations[1]
        case.host.execute('writeInteger(0x1040,17); writeInteger(0x1044,19)')
        write = case.memory.write
        delayed = False
        def slow_first_undo(address, raw):
            nonlocal delayed
            write(address, raw)
            if scope.state == 'closing' and not delayed:
                delayed = True
                self.clock.advance(31)
        before = len(case.memory.writes)
        with patch.object(case.memory, 'write', slow_first_undo):
            with self.assertRaisesRegex(LuaHostError, 'deadline'):
                scope.close()
        self.assertEqual(case.memory.writes[before:], [(0x1044, bytes(4))])
        self.assertEqual(case.memory.read(0x1040, 8), b'\x11\0\0\0' + bytes(4))
        self.assertEqual(scope.state, 'uncertain')
        self.assertTrue(case.engine.blocked)
        self.assertTrue(scope.path.is_file())

    def test_slow_success_returns_owned_receipt_and_manual_off_restores(self):
        from test_native_lua_activation import OwnedLuaTests, AA
        case = OwnedLuaTests('test_autoassembler_disable_receipt_is_scoped_and_source_bound')
        try:
            case.setUp()
            case.host._clock = self.clock
            scope = case.engine.lua_activations[1]
            actual = scope.broker.call
            def delayed(*args, **options):
                result = actual(*args, **options)
                self.clock.advance(0.4)
                return result
            with patch.object(scope.broker, 'call', delayed):
                self.assertEqual(case.host.execute('ok,receipt=autoAssemble(' + repr(AA) + '); return ok,type(receipt)'),
                                 (True, 'table'))
            self.assertEqual(len(scope.assemblies), 1)
            case.engine.toggle(1, False)
            self.assertEqual(case.memory.read(0x1040, 4), bytes(4))
            self.assertEqual(scope.state, 'abandoned')
            self.assertTrue(scope.host.cancelled)
        finally:
            case.tearDown()

    def test_true_broker_expiry_keeps_manual_receipt_for_controller_off(self):
        from test_native_lua_activation import OwnedLuaTests, AA
        case = OwnedLuaTests('test_autoassembler_disable_receipt_is_scoped_and_source_bound')
        try:
            case.setUp()
            case.host._clock = self.clock
            case.host.work_limits = WorkLimits(0.25, 1_000_000, 0.5, 2, 10, 3)
            scope = case.engine.lua_activations[1]
            actual = scope.broker.call
            def delayed(*args, **options):
                result = actual(*args, **options)
                self.clock.advance(0.6)
                return result
            with patch.object(scope.broker, 'call', delayed):
                with self.assertRaisesRegex(LuaHostError, 'broker call deadline'):
                    case.host.execute('ok,receipt=autoAssemble(' + repr(AA) + ')')
            self.assertEqual(len(scope.assemblies), 1)
            self.assertEqual(case.memory.read(0x1040, 4), bytes.fromhex('01000000'))
            case.engine.toggle(1, False)
            self.assertEqual(case.memory.read(0x1040, 4), bytes(4))
            self.assertFalse(case.engine.blocked)
        finally:
            case.tearDown()

    def test_automatic_expiry_compensates_and_saves_no_active_desire(self):
        from test_native_lua_record import AutomaticLuaRecordTests
        from test_native_lua_activation import AA
        from ct2trainer.native.lua_activation import LuaActivation
        from ct2trainer.native.engine import NativeRuntimeError
        case = AutomaticLuaRecordTests('test_lua_only_record_has_confirmed_owned_data_undo')
        initialize, assemble = LuaActivation.__init__, LuaActivation.assemble
        try:
            case.setUp()
            source = '[ENABLE]\n{$lua}\nassert(autoAssemble(' + repr(AA) + '))\n[DISABLE]\n{$lua}\nreturn nil'
            engine = case.make_engine(source)
            def construct(scope, *args, **options):
                initialize(scope, *args, **options)
                scope.host._clock = self.clock
                scope.host.work_limits = WorkLimits(0.25, 1_000_000, 0.5, 2, 10, 3)
            def delayed(scope, *args, **options):
                result = assemble(scope, *args, **options)
                self.clock.advance(0.6)
                return result
            with patch.object(LuaActivation, '__init__', construct), patch.object(LuaActivation, 'assemble', delayed):
                with self.assertRaisesRegex(NativeRuntimeError, 'broker call deadline'):
                    engine.toggle(1, True)
            self.assertEqual(case.memory.read(0x1040, 4), bytes(4))
            self.assertFalse(engine.lua_activations)
            self.assertFalse(engine.desired)
            self.assertFalse(engine.applied)
            self.assertFalse(engine.blocked)
        finally:
            case.tearDown()
            case.doCleanups()

    def test_selected_phase_chunks_share_one_automatic_activation_budget(self):
        from test_native_lua_record import AutomaticLuaRecordTests
        from ct2trainer.native.lua_activation import LuaActivation
        from ct2trainer.native.lua_host import EngineLuaBroker
        from ct2trainer.native.engine import NativeRuntimeError
        case = AutomaticLuaRecordTests('test_lua_only_record_has_confirmed_owned_data_undo')
        initialize, call = LuaActivation.__init__, EngineLuaBroker.call
        try:
            case.setUp()
            source = '[ENABLE]\n{$lua}\nreadInteger(0x1080)\n{$asm}\n{$lua}\nreadInteger(0x1080)\n{$asm}\n[DISABLE]'
            engine = case.make_engine(source)
            def construct(scope, *args, **options):
                initialize(scope, *args, **options)
                scope.host._clock = self.clock
                scope.host.work_limits = WorkLimits(0.25, 1_000_000, 1, 0.7, 10, 2)
            def delayed(broker, *args, **options):
                result = call(broker, *args, **options)
                self.clock.advance(0.4)
                return result
            with patch.object(LuaActivation, '__init__', construct), patch.object(EngineLuaBroker, 'call', delayed):
                with self.assertRaisesRegex(NativeRuntimeError, 'cumulative broker deadline'):
                    engine.toggle(1, True)
            self.assertFalse(engine.desired)
            self.assertFalse(engine.applied)
            self.assertFalse(engine.lua_activations)
            self.assertFalse(engine.blocked)
        finally:
            case.tearDown()
            case.doCleanups()

    def test_private_nth_scan_and_direct_link_share_one_readonly_check_budget(self):
        from test_native_nth_aob import OwnedNthActivationTests
        from ct2trainer.native.lua_activation import LuaActivation
        from ct2trainer.native import nth_aob, aa_program
        case = OwnedNthActivationTests('test_actual_dry_link_resolves_private_scan_for_lua_and_never_changes_receipts_or_memory')
        actual_scan, actual_link = nth_aob.scan_nth, aa_program.dry_link_program
        scope = None
        try:
            case.setUp()
            engine = case.make_engine()
            scope = LuaActivation(engine, 1)
            scope.host._clock = self.clock
            scope.host.work_limits = WorkLimits(0.25, 1_000_000, 1, 0.7, 10, 2)
            before = scope.path.read_bytes()
            def scan(*args, **options):
                result = actual_scan(*args, **options)
                self.clock.advance(0.4)
                return result
            def link(*args, **options):
                result = actual_link(*args, **options)
                self.clock.advance(0.4)
                return result
            with patch.object(nth_aob, 'scan_nth', scan), patch.object(aa_program, 'dry_link_program', link):
                with self.assertRaisesRegex(LuaHostError, 'cumulative broker deadline'):
                    scope.check_program(engine.entries[1]['lua_program'])
            self.assertEqual(scope.path.read_bytes(), before)
            self.assertFalse(engine.symbols)
            self.assertFalse(case.memory.writes)
        finally:
            if scope is not None:
                scope.close()
            case.tearDown()
            case.doCleanups()
