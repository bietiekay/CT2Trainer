import threading
import time
import unittest
import tempfile
import subprocess
import sys
import gc
import weakref
from pathlib import Path
from unittest.mock import patch

from ct2trainer.native.lua_host import LuaHost, LuaHostError, LuaMemoryPool


class Broker:
    def __init__(self):
        self.calls = []
        self.value = 1234

    def call(self, name, args, *, generation, syntaxcheck):
        self.calls.append((name,args,generation,syntaxcheck))
        if name == 'getAddress': return 0x123456789AB
        if name == 'readInteger': return self.value
        if name == 'readBytes': return [0x12,0x34,0x56]
        if name == 'writeBytes':
            if syntaxcheck: raise LuaHostError('syntaxcheck write rejected')
            return True
        if name == 'AOBScan': return ['00001000','00002000']
        if name == 'addresslist.getMemoryRecordByID': return args[0]
        if name == 'record.get':
            return {'ID': args[0], 'Value':str(self.value), 'Active':False}[args[1]]
        if name == 'record.set':
            if syntaxcheck: raise LuaHostError('syntaxcheck write rejected')
            self.value=int(args[2]); return str(self.value)
        if name == 'print': return None
        raise LuaHostError('unsupported '+name)


class NativeLuaHelperTests(unittest.TestCase):
    def setUp(self):
        try:
            import lupa.lua53
        except ImportError:
            self.skipTest('pinned MIT Lupa Lua53 dependency is not installed')
        self.broker = Broker()
        self.host = LuaHost(self.broker)

    def test_helpers_are_live_and_replayed_into_separate_disposable_checks(self):
        source = 'counter=0; function helper() counter=counter+1; return counter,syntaxcheck end'
        self.host.install_helpers(source)
        self.assertEqual(self.host.helper_sources, (source,))
        self.assertEqual(self.host.execute('return helper()'), (1, False))
        self.assertEqual(self.host.execute('return helper()', syntaxcheck=True), (1, True))
        self.assertEqual(self.host.execute('return helper()'), (2, False))
        self.assertEqual(self.host.execute('return helper()', syntaxcheck=True), (1, True))
        self.assertEqual(self.host.check_sources(['local a=helper(); shadow=44; return a', 'return helper(),shadow']),
                         [1, (2, 44)])
        self.assertTrue(self.host.execute('return shadow==nil'))

    def test_bootstrap_reads_are_checking_and_helpers_can_read_in_live_record(self):
        self.host.install_helpers('seed=readInteger("value"); function helper() return readInteger("value")+seed end')
        self.assertTrue(self.broker.calls[-1][3])
        self.assertEqual(self.host.execute('return helper()'), 2468)
        self.assertFalse(self.broker.calls[-1][3])
        self.assertEqual(self.host.execute('return helper()', syntaxcheck=True), 2468)
        self.assertTrue(self.broker.calls[-1][3])

    def test_each_activation_has_distinct_mutable_helper_globals(self):
        other = LuaHost(self.broker, owner_record_id=2)
        source = 'shared={counter=0}; function helper() shared.counter=shared.counter+1; return shared.counter end'
        self.host.install_helpers(source)
        other.install_helpers(source)
        self.assertEqual(self.host.execute('return helper()'), 1)
        self.assertEqual(self.host.execute('return helper()'), 2)
        self.assertEqual(other.execute('return helper()'), 1)
        other.cancel()
        self.assertEqual(self.host.execute('return helper()'), 3)

    def test_raw_writes_symbols_records_and_assembly_never_reach_lax_broker(self):
        class LaxBroker(Broker):
            syntaxcheck_assembler = True
            def call(self, name, args, **options):
                if name in {'writeInteger', 'writeBytes', 'registerSymbol', 'unregisterSymbol', 'record.set', 'autoAssemble'}:
                    self.calls.append((name, args, options))
                    return True
                return super().call(name, args, **options)
        for source in ('writeInteger(4096,1)', 'writeBytes(4096,1)', 'registerSymbol("flag",4096)',
                       'unregisterSymbol("flag")', 'getAddressList().getMemoryRecordByID(1).Active=true',
                       'autoAssemble("owned")'):
            with self.subTest(source=source):
                broker = LaxBroker()
                host = LuaHost(broker)
                with self.assertRaisesRegex(LuaHostError, 'mutation API'):
                    host.install_helpers('partial=17; ' + source)
                self.assertTrue(host.cancelled)
                self.assertEqual(host.helper_sources, ())
                self.assertFalse(any(item[0] in {'writeInteger', 'writeBytes', 'registerSymbol', 'unregisterSymbol',
                                                 'record.set', 'autoAssemble'} for item in broker.calls))
                with self.assertRaisesRegex(LuaHostError, 'cancelled'):
                    host.execute('return partial')

    def test_catching_a_mutation_denial_cannot_leave_a_usable_helper_profile(self):
        with self.assertRaisesRegex(LuaHostError, 'forbidden mutation'):
            self.host.install_helpers('local ok=pcall(function() writeBytes(4096,1) end); helper=function() return ok end')
        self.assertTrue(self.host.cancelled)

    def test_invalid_arguments_cannot_hide_a_caught_forbidden_helper_api(self):
        with self.assertRaisesRegex(LuaHostError, 'forbidden mutation'):
            self.host.install_helpers('pcall(writeInteger,0x1000,function() end); function helper() return 1 end')
        self.assertTrue(self.host.cancelled)
        self.assertEqual(self.host.helper_sources, ())
        self.assertFalse(self.broker.calls)

    def test_timer_and_worker_attempts_are_fatal_even_when_caught(self):
        for source in ('createTimer(nil,false)', 'createThread(function() end)',
                       'pcall(function() createTimer(nil,true) end)', 'pcall(function() createThread(function() end) end)'):
            with self.subTest(source=source):
                host = LuaHost(self.broker)
                with self.assertRaisesRegex(LuaHostError, 'forbidden mutation or scheduler'):
                    host.install_helpers(source)
                self.assertTrue(host.cancelled)
                self.assertEqual(host.helper_sources, ())
                with self.assertRaisesRegex(LuaHostError, 'cancelled'):
                    host.tick(0)

    def test_source_failure_unknown_top_level_api_and_second_install_cancel_host(self):
        for source in ('partial=4; error("failure")', 'function(', 'registerCustomTypeLua("x",4,nil,nil)'):
            with self.subTest(source=source):
                host = LuaHost(self.broker)
                with self.assertRaises(LuaHostError):
                    host.install_helpers(source)
                self.assertTrue(host.cancelled)
                self.assertEqual(host.helper_sources, ())
        self.host.install_helpers('function helper() return 4 end')
        with self.assertRaisesRegex(LuaHostError, 'one explicit source'):
            self.host.install_helpers('function helper() return 5 end')
        self.assertTrue(self.host.cancelled)

    def test_cancelled_and_stale_hosts_cannot_install_even_pure_definitions(self):
        self.host.cancel()
        with self.assertRaisesRegex(LuaHostError, 'cancelled'):
            self.host.install_helpers('function helper() return 1 end')
        broker = Broker()
        broker.generation = 0
        host = LuaHost(broker)
        broker.generation = 1
        with self.assertRaisesRegex(LuaHostError, 'Stale'):
            host.install_helpers('function helper() return 1 end')
        self.assertTrue(host.cancelled)

    def test_generation_change_during_bootstrap_read_cancels_partial_definitions(self):
        class StaleBroker(Broker):
            generation=0
            def call(self,name,args,**options):
                result=super().call(name,args,**options)
                self.generation+=1
                return result
        host=LuaHost(StaleBroker())
        with self.assertRaisesRegex(LuaHostError,'Stale'):
            host.install_helpers('partial=readInteger("value"); function helper() return partial end')
        self.assertTrue(host.cancelled)
        self.assertEqual(host.helper_sources,())

    def test_disposable_check_cannot_spawn_recursive_checker_states(self):
        self.host.install_helpers('function helper() return 3 end')
        with self.assertRaisesRegex(LuaHostError,'Nested disposable'):
            self.host._disposable_check(lambda checker:checker.check_sources(['return helper()']))
        self.assertEqual(self.host.execute('return helper()'),3)

    def test_helper_allocation_and_checker_replay_share_the_pool_quota(self):
        pool = LuaMemoryPool(max_memory=2*1024*1024, max_states=2)
        host = LuaHost(self.broker, memory_pool=pool)
        with self.assertRaises(LuaHostError):
            host.install_helpers('keep={}; for i=1,8 do keep[i]=string.rep(tostring(i),512*1024) end')
        self.assertTrue(host.cancelled)
        self.assertLessEqual(pool.memory_used, pool.max_memory)
        second_pool = LuaMemoryPool(max_states=1)
        second = LuaHost(self.broker, memory_pool=second_pool)
        second.install_helpers('function helper() return 42 end')
        with self.assertRaisesRegex(LuaHostError, 'state limit'):
            second.execute('return helper()', syntaxcheck=True)
        self.assertEqual(second_pool.state_count, 1)
        self.assertEqual(second.execute('return helper()'), 42)

    def test_nested_installation_is_finite_and_cancels_every_partial_host(self):
        hosts = []
        class NestedBroker(Broker):
            def call(self, name, args, **options):
                if name == 'readInteger':
                    child = LuaHost(self)
                    hosts.append(child)
                    child.install_helpers('seed=readInteger("value")')
                    return 1
                return super().call(name, args, **options)
        host = LuaHost(NestedBroker())
        hosts.append(host)
        with self.assertRaisesRegex(LuaHostError, 'nesting exceeds'):
            host.install_helpers('seed=readInteger("value")')
        self.assertEqual(len(hosts), 5)
        self.assertTrue(all(item.cancelled for item in hosts))
        self.assertTrue(all(item.helper_sources == () for item in hosts))
        self.host.install_helpers('function helper() return 7 end')
        self.assertEqual(self.host.execute('return helper()'), 7)

    def test_helper_installation_is_not_exposed_as_a_lua_api(self):
        self.assertTrue(self.host.execute('return install_helpers==nil and prepare_lua_bootstrap==nil and python==nil'))


class NativeLuaTransportTests(unittest.TestCase):
    def setUp(self):
        try:
            import lupa.lua53
        except ImportError:
            self.skipTest('pinned MIT Lupa Lua53 dependency is not installed')
        self.broker = Broker()
        self.host = LuaHost(self.broker, timeout=2, instruction_limit=10_000_000)
        self.addCleanup(self.host.cancel)

    def test_compact_shared_lua_dag_cannot_expand_past_aggregate_node_limit(self):
        # Only 41 Lua table slots describe ten thousand expanded leaf values.
        source = ('local t={1}; for level=1,4 do local next={}; '
                  'for i=1,10 do next[i]=t end; t=next end; return readInteger(t)')
        with patch('ct2trainer.native.lua_host.MAX_TRANSPORT_NODES', 1024):
            with self.assertRaisesRegex(LuaHostError, 'transport expanded node'):
                self.host.execute(source)
        self.assertFalse(self.broker.calls)
        self.assertLess(self.host.lua.get_memory_used(total=True), 1024 * 1024)
        self.assertEqual(self.host.execute('return 17'), 17)

    def test_argument_payload_limit_is_shared_across_arguments(self):
        with patch('ct2trainer.native.lua_host.MAX_TRANSPORT_BYTES', 80):
            with self.assertRaisesRegex(LuaHostError, 'transport payload byte'):
                self.host.execute('return readInteger(string.rep("a",40),string.rep("b",40))')
        self.assertFalse(self.broker.calls)

    def test_payload_counts_utf8_keys_and_repeated_string_references(self):
        for source in ('return readInteger("' + ('\u00e9' * 40) + '")',
                       'return readInteger({[string.rep("k",70)]=1})',
                       'local s=string.rep("s",30); return readInteger({s,s,s})'):
            with self.subTest(source=source):
                with patch('ct2trainer.native.lua_host.MAX_TRANSPORT_BYTES', 80):
                    with self.assertRaisesRegex(LuaHostError, 'transport payload byte'):
                        self.host.execute(source)
        self.assertFalse(self.broker.calls)

    def test_container_limit_and_cycles_are_refused_before_broker_dispatch(self):
        with patch('ct2trainer.native.lua_host.MAX_TRANSPORT_ITEMS', 16):
            with self.assertRaisesRegex(LuaHostError, 'Oversized Lua broker data container'):
                self.host.execute('local t={}; for i=1,17 do t[i]=i end; return readInteger(t)')
        with self.assertRaisesRegex(LuaHostError, 'Only bounded data'):
            self.host.execute('local t={}; t[1]=t; return readInteger(t)')
        self.assertFalse(self.broker.calls)

    def test_maximum_supported_byte_array_still_crosses_the_broker(self):
        self.assertTrue(self.host.execute('local t={}; for i=1,65536 do t[i]=i%256 end; return writeBytes(4096,t)'))
        address, values = self.broker.calls[-1][1]
        self.assertEqual(address, 4096)
        self.assertEqual(len(values), 65536)
        self.assertEqual(values[:3], [1, 2, 3])
        self.assertEqual(values[-1], 0)

    def test_conversion_checkpoints_stop_cancellation_before_dispatch(self):
        table = self.host.lua.table_from(range(2048))
        checkpoint = self.host._checkpoint
        calls = []
        def cancel_during_conversion(reason=None):
            calls.append(reason)
            if len(calls) == 3:
                self.host.cancelled = True
            checkpoint(reason)
        with patch.object(self.host, '_checkpoint', cancel_during_conversion):
            with self.assertRaisesRegex(LuaHostError, 'cancelled'):
                self.host._slice(self.host._call, 'readInteger', table)
        self.assertEqual(len(calls), 3)
        self.assertFalse(self.broker.calls)

    def test_conversion_checkpoints_stop_stale_generation_before_dispatch(self):
        self.broker.generation = 0
        table = self.host.lua.table_from(range(2048))
        checkpoint = self.host._checkpoint
        calls = []
        def change_generation(reason=None):
            calls.append(reason)
            if len(calls) == 3:
                self.broker.generation = 1
            checkpoint(reason)
        with patch.object(self.host, '_checkpoint', change_generation):
            with self.assertRaisesRegex(LuaHostError, 'Stale'):
                self.host._slice(self.host._call, 'readInteger', table)
        self.assertEqual(len(calls), 3)
        self.assertFalse(self.broker.calls)

    def test_conversion_checkpoints_enforce_the_slice_deadline(self):
        table = self.host.lua.table_from(range(2048))
        checkpoint = self.host._checkpoint
        calls = []
        clock = [100.0]
        def expire_during_conversion(reason=None):
            calls.append(reason)
            if len(calls) == 3:
                clock[0] = 103.0
            checkpoint(reason)
        with patch('ct2trainer.native.lua_host.time.monotonic', lambda: clock[0]):
            with patch.object(self.host, '_checkpoint', expire_during_conversion):
                with self.assertRaisesRegex(LuaHostError, 'execution budget'):
                    self.host._slice(self.host._call, 'readInteger', table)
        self.assertEqual(len(calls), 3)
        self.assertFalse(self.broker.calls)

    def test_python_broker_return_dag_and_cycle_use_the_same_transport_bounds(self):
        shared = [1]
        for _ in range(4):
            shared = [shared] * 10
        self.broker.value = shared
        with patch('ct2trainer.native.lua_host.MAX_TRANSPORT_NODES', 1024):
            with self.assertRaisesRegex(LuaHostError, 'transport expanded node'):
                self.host.execute('return readInteger(4096)')
        self.assertEqual(len(self.broker.calls), 1)
        self.assertLess(self.host.lua.get_memory_used(total=True), 1024 * 1024)
        cycle = []
        cycle.append(cycle)
        self.broker.value = cycle
        with self.assertRaisesRegex(LuaHostError, 'unapproved or unbounded Python object'):
            self.host.execute('return readInteger(4096)')

    def test_disposable_return_dag_is_bounded_without_poisoning_live_host(self):
        source = ('checker_only=99; local t={1}; for level=1,4 do local next={}; '
                  'for i=1,10 do next[i]=t end; t=next end; return t')
        with patch('ct2trainer.native.lua_host.MAX_TRANSPORT_NODES', 1024):
            with self.assertRaisesRegex(LuaHostError, 'transport expanded node'):
                self.host.execute(source, syntaxcheck=True)
        self.assertTrue(self.host.execute('return checker_only==nil'))
        self.assertFalse(self.host.cancelled)
        self.assertFalse(self.broker.calls)

    def test_broker_return_payload_and_key_limits_are_not_lua_allocator_limits(self):
        self.broker.value = {'k' * 70: 'v' * 70}
        with patch('ct2trainer.native.lua_host.MAX_TRANSPORT_BYTES', 128):
            with self.assertRaisesRegex(LuaHostError, 'transport payload byte'):
                self.host.execute('return readInteger(4096)')
        self.assertEqual(len(self.broker.calls), 1)
        self.assertLess(self.host.lua.get_memory_used(total=True), 1024 * 1024)
        self.assertFalse(self.host.cancelled)

    def test_checker_result_budget_spans_all_sources_and_multiple_return_values(self):
        with patch('ct2trainer.native.lua_host.MAX_TRANSPORT_BYTES', 128):
            with self.assertRaisesRegex(LuaHostError, 'transport payload byte'):
                self.host.check_sources(['return string.rep("a",60)', 'return string.rep("b",60)'])
            with self.assertRaisesRegex(LuaHostError, 'transport payload byte'):
                self.host.execute('return string.rep("a",60),string.rep("b",60)', syntaxcheck=True)
        self.assertEqual(self.host.execute('return 42'), 42)


class NativeLuaTests(unittest.TestCase):
    def setUp(self):
        try:
            import lupa.lua53
        except ImportError:
            self.skipTest('pinned MIT Lupa Lua53 dependency is not installed')
        self.broker=Broker()
        self.host=LuaHost(self.broker)

    def test_real_lua53_language_and_64bit_addresses(self):
        self.assertEqual(self.host.execute('return _VERSION'), 'Lua 5.3')
        self.assertEqual(self.host.execute('return getAddress("symbol")'), 0x123456789AB)
        self.assertEqual(self.host.execute('return (0x7fffffffffffffff >> 60)'), 7)
        self.assertEqual(self.host.execute('local t={}; for i=1,5 do t[i]=i*i end; return t[5]'),25)

    def test_byte_return_values_and_zero_based_scan_list(self):
        self.assertEqual(self.host.execute('local a,b,c=readBytes(4096,3); return a+b+c'),0x9c)
        self.assertEqual(self.host.execute('return readBytes(4096,3,true)[2]'),0x34)
        self.assertEqual(self.host.execute('local r=AOBScan("12 34"); return r.Count,r[0],r[1]'),(2,'00001000','00002000'))
        with self.assertRaisesRegex(LuaHostError,'destroyed'):
            self.host.execute('local r=AOBScan("12 34"); r.destroy(); return r.Count')

    def test_memoryrecord_properties_and_writes_use_broker(self):
        self.assertEqual(self.host.execute('local m=getAddressList().getMemoryRecordByID(17); m.Value="4321"; return m.ID,m.Value'),(17,'4321'))
        self.assertTrue(any(c[0]=='record.set' for c in self.broker.calls))
        self.host.execute('writeBytes(4096,{1,2,3})')
        self.assertEqual(self.broker.calls[-1][1],(4096,[1,2,3]))
        self.host.execute('writeBytes(4096,4,5,6)')
        self.assertEqual(self.broker.calls[-1][1],(4096,[4,5,6]))

    def test_generated_aa_is_executed_not_translated(self):
        source='[ENABLE]\n{$lua}\nlocal n=2+3\nreturn "define(value,"..n..")"\n{$asm}\n[DISABLE]'
        expanded=self.host.expand_assembler(source,syntaxcheck=True,record_id=1)
        self.assertEqual(expanded,'[ENABLE]\ndefine(value,5)\n[DISABLE]')
        self.assertEqual(self.host.execute('if syntaxcheck then return "checking" end',syntaxcheck=True),'checking')
        with self.assertRaisesRegex(LuaHostError,'text or nil'):
            self.host.expand_assembler('{$lua}\nreturn 17\n{$asm}')
        with self.assertRaisesRegex(LuaHostError,'Unterminated'):
            self.host.expand_assembler('{$lua}\nreturn "x"')

    def test_syntaxcheck_context_reaches_broker(self):
        self.assertEqual(self.host.execute('return readInteger("value")',syntaxcheck=True),1234)
        self.assertTrue(self.broker.calls[-1][3])
        count=len(self.broker.calls)
        with self.assertRaisesRegex(LuaHostError,'Syntax checking cannot call mutation'):
            self.host.execute('writeBytes(4096,1)',syntaxcheck=True)
        self.assertEqual(len(self.broker.calls),count)

    def test_syntaxcheck_cannot_schedule_or_enable_live_timer(self):
        with self.assertRaisesRegex(LuaHostError,'Syntax checking'):
            self.host.execute('syntaxcheck=false; t=createTimer(nil,true)',syntaxcheck=True)
        self.host.execute('t=createTimer(nil,false); t.OnTimer=function() print("later") end')
        self.assertTrue(self.host.execute('return t==nil',syntaxcheck=True))
        self.host.tick(1000)
        self.assertFalse(self.broker.calls)

    def test_syntaxcheck_globals_and_library_mutations_are_disposable(self):
        self.host.execute('saved="live"; callback=function() return "live callback" end')
        result=self.host.execute('saved="check"; leaked=17; callback=nil; table.insert=nil; return saved,syntaxcheck',syntaxcheck=True)
        self.assertEqual(result,('check',True))
        self.assertEqual(self.host.execute('return saved,leaked,callback(),type(table.insert)'),
                         ('live',None,'live callback','function'))
        self.assertTrue(self.host.execute('return leaked==nil',syntaxcheck=True))
        self.assertEqual(self.host.execute('return saved==nil',syntaxcheck=True),True)
        with self.assertRaises(LuaHostError):
            self.host.execute('leaked=21; error("failed check")',syntaxcheck=True)
        self.assertTrue(self.host.execute('return leaked==nil'))

    def test_disposable_check_returns_only_detached_data(self):
        self.assertEqual(self.host.execute('return {answer=42,nested={1,2}}',syntaxcheck=True),
                         {'answer':42,'nested':[1,2]})
        with self.assertRaisesRegex(LuaHostError,'bounded data'):
            self.host.execute('return function() print("escaped callback") end',syntaxcheck=True)
        self.assertFalse(self.broker.calls)

    def test_check_sources_share_only_explicit_checker_bootstrap(self):
        self.assertEqual(self.host.check_sources(['function helper() return 23 end',
                                                'return helper(),syntaxcheck']),
                         [None,(23,True)])
        self.assertTrue(self.host.execute('return helper==nil'))
        self.assertEqual(self.host.execute('print("no live UI"); showMessage("no dialog"); return 4',
                                          syntaxcheck=True),4)
        self.assertFalse(self.broker.calls)

    def test_check_expansion_shares_preamble_and_selected_phase_only(self):
        source='{$lua}\nhelper=function() return 7 end\n{$asm}\n[ENABLE]\n{$lua}\nleak=helper(); return "define(value,"..leak..")"\n{$asm}\n[DISABLE]\n{$lua}\nerror("wrong phase")\n{$asm}'
        self.assertIn('define(value,7)',self.host.expand_assembler(source,syntaxcheck=True))
        self.assertTrue(self.host.execute('return helper==nil and leak==nil'))

    def test_activation_owned_scheduler_context_and_independent_cancel(self):
        one=LuaHost(self.broker,owner_record_id=17,generation=3)
        two=LuaHost(self.broker,owner_record_id=19,generation=4)
        one.execute('t=createTimer(nil,true); t.Interval=1; t.OnTimer=function() print("timer",memrec.ID) end; w=createThread(function(thread) print("worker",memrec.ID); sleep(1); print("worker later",memrec.ID) end)')
        two.execute('w=createThread(function(thread) print("other",memrec.ID); sleep(1); print("other later",memrec.ID) end)')
        one.tick(0); two.tick(0); one.tick(1)
        self.assertEqual([(item[1],item[2]) for item in self.broker.calls if item[0]=='print'],
                         [(('worker',17),3),(('other',19),4),(('timer',17),3),(('worker later',17),3)])
        self.assertTrue(one.execute('return memrec.ID==17'))
        with self.assertRaisesRegex(LuaHostError,'activation owner'):
            one.execute('return memrec.ID',record_id=19)
        one.cancel(); one.cancel()
        self.assertEqual(one.generation,4)
        with self.assertRaisesRegex(LuaHostError,'cancelled'):
            one.tick(1000)
        two.tick(1)
        self.assertEqual(self.broker.calls[-1][1],('other later',19))
        self.assertEqual(self.broker.calls[-1][2],4)
        two.cancel()

    def test_environment_has_no_python_filesystem_or_native_loader(self):
        self.assertTrue(self.host.execute('return python==nil and io==nil and os==nil and require==nil and package==nil and debug==nil and load==nil and coroutine==nil'))
        with self.assertRaises(LuaHostError): self.host.execute('getAddress.__globals__')
        with self.assertRaises(LuaHostError): self.host.execute('return readInteger.__class__')

    def test_ordinary_metatable_identity_mutation_and_weak_mode_survive(self):
        self.assertEqual(self.host.execute('mt={__index={value=7},__add=function(a,b) return a.n+b.n end}; a=setmetatable({n=2},mt); b=setmetatable({n=3},mt); mt.__index.value=9; return getmetatable(a)==mt,a.value,a+b'),
                         (True,9,5))
        self.assertTrue(self.host.execute('local weak=setmetatable({}, {__mode="kv"}); local key={}; weak[key]=a; return weak[key]==a'))
        self.assertTrue(self.host.execute('setmetatable(a,nil); return getmetatable(a)==nil and a.value==nil'))
        with self.assertRaises(LuaHostError):
            self.host.execute('setmetatable({},17)')

    def test_finalizer_registration_rejects_all_non_nil_placeholders(self):
        for finalizer in ('function() while true do end end','false','0','""',
                          'setmetatable({}, {__call=function() while true do end end})'):
            with self.subTest(finalizer=finalizer):
                with self.assertRaisesRegex(LuaHostError,'finalizer metatables'):
                    self.host.execute('return setmetatable({}, {__gc='+finalizer+'})')
        with self.assertRaisesRegex(LuaHostError,'finalizer metatables'):
            self.host.execute('return setmetatable({}, {__gc=false})',syntaxcheck=True)

    def test_private_metatable_guard_survives_global_tampering_and_scheduler(self):
        self.assertTrue(self.host.execute('safe=setmetatable; saved_type=type; rawget=function() return nil end; type=function() return "nil" end; error=function() end; local ok=pcall(safe,{}, {__gc=false}); type=saved_type; return not ok'))
        self.host.execute('setmetatable=function() return nil end; t=createTimer(nil,true); t.Interval=1; t.OnTimer=function() print("timer") end; w=createThread(function() print("worker"); sleep(1); print("later") end)')
        self.host.tick(0); self.host.tick(1)
        self.assertEqual([item[1][0] for item in self.broker.calls],['worker','timer','later'])
        self.host.cancel()
        self.assertTrue(self.host._cancel_finished)

    def test_late_finalizer_mutations_cannot_hang_disposal(self):
        # Lua53 marks an object only when assigning a metatable with non-nil
        # raw __gc. Direct/raw writes later cannot mark it; resetting the
        # metatable must pass the private guard again. A regression here hangs
        # in upstream Lua.close rather than an execution slice, so isolate it.
        source='''import gc,weakref
from ct2trainer.native.lua_host import LuaHost,LuaMemoryPool
class Broker:
 def call(self,*args,**options):raise AssertionError("GC reached broker")
loop="function() while true do end end"
cases=[]
for placeholder in (loop,"false","0",'""',"setmetatable({}, {__call="+loop+"})"):
 cases.append(["mt={__gc="+placeholder+"}; object={}; assert(not pcall(setmetatable,object,mt)); mt.__gc="+loop])
cases.extend([
 ["mt={}; object=setmetatable({},mt)","mt.__gc="+loop],
 ["mt={}; object=setmetatable({},mt)","rawset(getmetatable(object),'__gc',"+loop+")"],
 ["mt={}; object=setmetatable({},mt)","mt.__gc=false; assert(not pcall(setmetatable,object,mt)); mt.__gc="+loop],
 ["mt={}; object=setmetatable({},mt)","mt.__gc="+loop+"; assert(not pcall(setmetatable,object,mt))"],
 ["safe=setmetatable; rawget=function() return nil end; type=function() return 'nil' end; error=function() end; mt={__gc=false}; object={}; assert(not pcall(safe,object,mt)); mt.__gc="+loop],
 ["mt=setmetatable({}, {__index=function(_,key) if key=='__gc' then while true do end end end}); object=setmetatable({},mt)","rawset(mt,'__gc',"+loop+")"],
 ["mt={}; object=setmetatable({},mt); mt.__gc="+loop+"; saved=setmetatable; setmetatable=function(o,m) return saved(o,m) end; assert(not pcall(setmetatable,object,mt))"]
])
for scripts in cases:
 pool=LuaMemoryPool(); host=LuaHost(Broker(),memory_pool=pool); ref=weakref.ref(host)
 for script in scripts:host.execute(script)
 host.cancel();del host;gc.collect()
 assert ref() is None and pool.state_count==0 and pool.memory_used==0
print("late finalizer mutation disposal remained bounded",len(cases))
'''
        result=subprocess.run([sys.executable,'-c',source],capture_output=True,text=True,timeout=6)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('late finalizer mutation disposal remained bounded 12',result.stdout)

    def test_plain_infinite_loop_hits_execution_budget(self):
        start=time.monotonic()
        with self.assertRaisesRegex(LuaHostError,'budget exceeded'):
            self.host.execute('while true do end')
        self.assertLess(time.monotonic()-start,2)
        self.assertEqual(self.host.execute('return 2+2'),4)

    def test_protected_calls_cannot_swallow_slice_budget_or_cancellation(self):
        for protected in ('pcall(function() while true do end end)',
                          'xpcall(function() while true do end end,function(e) return e end)'):
            host=LuaHost(self.broker,timeout=0.02,instruction_limit=2000)
            start=time.monotonic()
            with self.assertRaisesRegex(LuaHostError,'budget exceeded'):
                host.execute('while true do '+protected+' end')
            self.assertLess(time.monotonic()-start,1)
        self.assertEqual(self.host.execute('local ok=pcall(function() error("ordinary") end); return ok'),False)

    def test_enable_disable_lua_expansion_does_not_run_other_phase(self):
        source='[ENABLE]\n{$lua}\nn=(n or 0)+1; return "define(enabled,1)"\n{$asm}\n[DISABLE]\n{$lua}\nn=n+100; return "define(disabled,1)"\n{$asm}'
        expanded=self.host.expand_assembler(source,phase='enable')
        self.assertEqual(self.host.execute('return n'),1)
        self.assertIn('define(enabled,1)',expanded)
        self.assertNotIn('define(disabled,1)',expanded)
        expanded=self.host.expand_assembler(source,phase='disable')
        self.assertEqual(self.host.execute('return n'),101)
        self.assertIn('define(disabled,1)',expanded)
        self.assertNotIn('define(enabled,1)',expanded)

    def test_memory_limit(self):
        with self.assertRaises(LuaHostError):
            self.host.execute('return string.rep("a",32*1024*1024)')

    def test_real_allocations_obey_default_aggregate_pool(self):
        pool=LuaMemoryPool()
        hosts=[LuaHost(Broker(),memory_pool=pool) for _ in range(5)]
        self.assertEqual(hosts[0].lua.get_max_memory(),16*1024*1024)
        for host in hosts[:4]:
            self.assertEqual(host.execute('keep={}; for i=1,56 do keep[i]=string.rep(string.char(64+i),256*1024) end; return #keep'),56)
        self.assertGreater(pool.memory_used,56*1024*1024)
        with self.assertRaises(LuaHostError):
            hosts[4].execute('keep={}; for i=1,48 do keep[i]=string.rep(string.char(64+i),256*1024) end')
        self.assertLessEqual(pool.memory_used,64*1024*1024)
        with self.assertRaisesRegex(LuaHostError,'startup allowance'):
            LuaHost(Broker(),memory_pool=pool)
        self.assertEqual(hosts[0].execute('return #keep[1]'),256*1024)
        for host in hosts:
            host.cancel()

    def test_pool_charges_cancelled_host_runtime_and_values_until_gc(self):
        pool=LuaMemoryPool(max_memory=2*1024*1024,max_states=1)
        host=LuaHost(Broker(),memory_pool=pool)
        value=host.execute('keep=string.rep("a",256*1024); return {value=keep}')
        runtime=host.lua
        retained=weakref.ref(host)
        host.cancel()
        charged=pool.memory_used
        self.assertGreater(charged,256*1024)
        self.assertEqual(pool.state_count,1)
        with self.assertRaisesRegex(LuaHostError,'state limit'):
            LuaHost(Broker(),memory_pool=pool)
        del host
        gc.collect()
        self.assertIsNotNone(retained())
        self.assertEqual(pool.memory_used,charged)
        del runtime
        gc.collect()
        self.assertIsNotNone(retained())
        self.assertEqual(pool.state_count,1)
        del value
        gc.collect()
        self.assertIsNone(retained())
        self.assertEqual((pool.state_count,pool.memory_used),(0,0))
        replacement=LuaHost(Broker(),memory_pool=pool)
        self.assertEqual(replacement.execute('return 42'),42)
        replacement.cancel()

    def test_disposable_check_uses_same_allocator_and_state_pool(self):
        pool=LuaMemoryPool(max_memory=4*1024*1024,max_states=2)
        class CheckingBroker(Broker):
            def call(self,name,args,**options):
                if name=='readInteger':
                    self.observed=(pool.state_count,pool.memory_used,options['syntaxcheck'])
                    return pool.state_count
                return super().call(name,args,**options)
        broker=CheckingBroker()
        host=LuaHost(broker,memory_pool=pool)
        host.execute('keep={}; for i=1,8 do keep[i]=string.rep(tostring(i),256*1024) end')
        self.assertEqual(host.execute('return readInteger("value")',syntaxcheck=True),2)
        self.assertEqual((broker.observed[0],broker.observed[2]),(2,True))
        gc.collect()
        self.assertEqual(pool.state_count,1)
        with self.assertRaises(LuaHostError):
            host.execute('keep={}; for i=1,8 do keep[i]=string.rep(tostring(i),256*1024) end',syntaxcheck=True)
        self.assertLessEqual(pool.memory_used,pool.max_memory)
        gc.collect()
        self.assertEqual(pool.state_count,1)
        self.assertEqual(host.execute('return #keep'),8)
        host.cancel()

    def test_pool_rejects_checker_start_before_source_runs(self):
        pool=LuaMemoryPool(max_states=1)
        broker=Broker()
        host=LuaHost(broker,memory_pool=pool)
        with self.assertRaisesRegex(LuaHostError,'state limit'):
            host.execute('return readInteger("value")',syntaxcheck=True)
        self.assertFalse(broker.calls)
        self.assertEqual(host.execute('return 2'),2)
        with self.assertRaises(ValueError):
            LuaMemoryPool(max_states=65)
        with self.assertRaises(ValueError):
            LuaMemoryPool(max_memory=65*1024*1024)

    def test_default_pool_allows_exactly_sixty_four_live_states(self):
        pool=LuaMemoryPool()
        hosts=[LuaHost(Broker(),memory_pool=pool) for _ in range(64)]
        self.assertEqual(pool.state_count,64)
        with self.assertRaisesRegex(LuaHostError,'state limit'):
            LuaHost(Broker(),memory_pool=pool)
        for host in hosts:
            host.cancel()

    def test_nested_host_execution_refreshes_suspended_allocator_limit(self):
        pool=LuaMemoryPool(max_memory=4*1024*1024)
        class NestedBroker(Broker):
            def call(self,name,args,**options):
                if name=='print':
                    self.other.execute('for i=5,8 do keep[i]=string.rep(tostring(i),256*1024) end')
                    return None
                return super().call(name,args,**options)
        broker=NestedBroker()
        first=LuaHost(broker,memory_pool=pool)
        second=LuaHost(Broker(),memory_pool=pool)
        broker.other=second
        for host in (first,second):
            host.execute('keep={}; for i=1,4 do keep[i]=string.rep(tostring(i),256*1024) end')
        with self.assertRaises(LuaHostError):
            first.execute('print("nested"); for i=5,8 do keep[i]=string.rep(tostring(i),256*1024) end')
        self.assertEqual(second.execute('return #keep'),8)
        self.assertLessEqual(pool.memory_used,pool.max_memory)
        first.cancel(); second.cancel()

    def test_pooled_cross_host_and_active_cancel_finish_without_deadlock(self):
        # A host-before-pool lock order would let B hold its host lock while
        # waiting for A's pool lock, and A's broker then deadlocks cancelling B.
        source='''import threading,time
from ct2trainer.native.lua_host import LuaHost,LuaHostError,LuaMemoryPool
pool=LuaMemoryPool(); entered=threading.Event(); started=threading.Event(); results=[]
class Broker:
 def call(self,name,args,**options):
  assert name=="print"
  entered.set();assert started.wait(1);time.sleep(.05);other.cancel()
first=LuaHost(Broker(),memory_pool=pool);other=LuaHost(Broker(),memory_pool=pool)
def one():
 try:results.append(first.execute('print("cancel other"); return 7'))
 except Exception as exc:results.append(exc)
def two():
 assert entered.wait(1);started.set()
 try:other.execute('return 2')
 except LuaHostError as exc:results.append(str(exc))
a=threading.Thread(target=one,daemon=True);b=threading.Thread(target=two,daemon=True)
a.start();b.start();a.join(2);b.join(2)
assert not a.is_alive() and not b.is_alive(),"cross-host cancellation deadlocked"
assert 7 in results and other._cancel_finished,results
running=LuaHost(Broker(),memory_pool=pool,timeout=10,instruction_limit=10_000_000)
def loop():
 try:running.execute('while true do end')
 except LuaHostError as exc:results.append(str(exc))
t=threading.Thread(target=loop,daemon=True);t.start();time.sleep(.01);running.cancel();t.join(2)
assert not t.is_alive() and running._cancel_finished
assert any(isinstance(item,str) and "cancelled" in item for item in results),results
print("pooled cancellation remained bounded")
'''
        result=subprocess.run([sys.executable,'-c',source],capture_output=True,text=True,timeout=6)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('pooled cancellation remained bounded',result.stdout)

    def test_timer_runs_only_on_serialized_ticks_and_cancel_stops_it(self):
        self.host.execute('t=createTimer(nil,false); t.Interval=10; t.OnTimer=function() print("tick") end; t.Enabled=true')
        self.host.tick(9)
        self.assertFalse(self.broker.calls)
        self.host.tick(1)
        self.assertEqual(self.broker.calls[-1][0],'print')
        self.host.cancel()
        with self.assertRaisesRegex(LuaHostError,'cancelled'): self.host.tick(100)

    def test_owned_worker_sleep_termination_and_cancel(self):
        self.host.execute('w=createThread(function(thread,value) print(value); sleep(10); print("second"); thread.terminate() end,"first")')
        self.assertFalse(self.broker.calls)
        self.host.tick(0)
        self.assertEqual([x[1][0] for x in self.broker.calls],['first'])
        self.host.tick(9)
        self.assertEqual(len(self.broker.calls),1)
        self.host.tick(1)
        self.assertEqual([x[1][0] for x in self.broker.calls],['first','second'])
        self.assertTrue(self.host.execute('return w.Terminated'))
        self.host.execute('w2=createThread(function() while true do print("loop"); sleep(1) end end)')
        self.host.tick(0)
        self.host.execute('w2.terminate()')
        count=len(self.broker.calls); self.host.tick(1000)
        self.assertEqual(len(self.broker.calls),count)
        with self.assertRaisesRegex(LuaHostError,'Syntax checking'):
            self.host.execute('w3=createThread(function() print("bad") end)',syntaxcheck=True)
        with self.assertRaisesRegex(LuaHostError,'cooperative worker'):
            self.host.execute('sleep(1)')
        self.host.cancel()
        with self.assertRaisesRegex(LuaHostError,'cancelled'):
            self.host.tick(1000)

    def test_non_yielding_worker_has_its_own_instruction_hook(self):
        self.host.execute('createThread(function() while true do pcall(function() while true do end end) end end)')
        start=time.monotonic()
        with self.assertRaisesRegex(LuaHostError,'budget exceeded'):
            self.host.tick(0)
        self.assertLess(time.monotonic()-start,1)
        self.assertEqual(self.host.execute('return 7'),7)
        with self.assertRaisesRegex(LuaHostError,'cooperative worker'):
            self.host.execute('sleep(1)')

    def test_autoassemble_adapts_boolean_and_disable_info_results(self):
        class AssemblerBroker(Broker):
            result={'ok':True,'disableInfo':{'token':'owned receipt'}}
            def call(self,name,args,**options):
                if name=='autoAssemble':
                    self.calls.append((name,args,options)); return self.result
                return super().call(name,args,**options)
        broker=AssemblerBroker(); host=LuaHost(broker)
        self.assertEqual(host.execute('local ok,info=autoAssemble("owned"); return ok,info.token'),
                         (True,'owned receipt'))
        broker.result={'ok':False,'disableInfo':None}
        self.assertEqual(host.execute('return autoAssemble("owned")'),(False,None))
        broker.result=True
        self.assertTrue(host.execute('return autoAssemble("owned")'))
        with self.assertRaisesRegex(LuaHostError,'mutation API'):
            host.execute('return autoAssemble("owned")',syntaxcheck=True)
        broker.syntaxcheck_assembler=True
        self.assertTrue(host.execute('return autoAssemble("owned")',syntaxcheck=True))
        self.assertTrue(broker.calls[-1][2]['syntaxcheck'])

    def test_cancel_interrupts_active_slice(self):
        host=LuaHost(self.broker,timeout=5,instruction_limit=10_000_000)
        outcomes=[]
        def run():
            try: host.execute('while true do end')
            except LuaHostError as exc: outcomes.append(str(exc))
        worker=threading.Thread(target=run)
        worker.start()
        time.sleep(0.01)
        host.cancel(); worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertTrue(outcomes)

    def _owner_self_disable_host(self, *, memory_pool=None):
        class OwnerBroker(Broker):
            active=True
            byte=1
            restored=False
            late_writes=0
            def call(self,name,args,**options):
                if name=='record.set' and args==(17,'Active',False):
                    # Model the controller's order: retire the Lua scope before
                    # its recorded write is undone and owner state is removed.
                    self.host.cancel()
                    self.byte=0; self.restored=True; self.active=False
                    return False
                if name=='writeBytes':
                    self.late_writes+=1
                return super().call(name,args,**options)
        broker=OwnerBroker()
        host=LuaHost(broker,owner_record_id=17,memory_pool=memory_pool)
        broker.host=host
        return host,broker

    def test_owner_self_disable_cleans_many_resources_before_followup_write(self):
        host,broker=self._owner_self_disable_host(memory_pool=LuaMemoryPool())
        host.execute('for i=1,512 do createTimer(nil,false) end; for i=1,128 do createThread(function() sleep(1); writeBytes(4096,9) end) end; pairs=function() error("untrusted cleanup") end')
        with self.assertRaisesRegex(LuaHostError,'cancelled'):
            host.execute('getAddressList().getMemoryRecordByID(17).Active=false; writeBytes(4096,9)')
        self.assertTrue(host._cancel_finished)
        self.assertTrue(broker.restored)
        self.assertFalse(broker.active)
        self.assertEqual(broker.byte,0)
        self.assertEqual(broker.late_writes,0)
        self.assertFalse(host._trusted_housekeeping)
        with self.assertRaisesRegex(LuaHostError,'cancelled'):
            host.tick(60000)

    def test_worker_self_disable_cleans_scope_before_followup_write(self):
        host,broker=self._owner_self_disable_host(memory_pool=LuaMemoryPool())
        host.execute('for i=1,512 do createTimer(nil,false) end; createThread(function() memrec.Active=false; writeBytes(4096,9) end); for i=1,127 do createThread(function() writeBytes(4096,8) end) end')
        with self.assertRaisesRegex(LuaHostError,'cancelled'):
            host.tick(0)
        self.assertTrue(host._cancel_finished)
        self.assertTrue(broker.restored)
        self.assertFalse(broker.active)
        self.assertEqual(broker.late_writes,0)
        self.assertFalse(host._trusted_housekeeping)

    def test_self_disable_restores_hook_for_suspended_pure_lua_loop(self):
        # A hook-restoration regression would loop forever without making a
        # broker call. Keep that assertion in a separately bounded process.
        source='''from ct2trainer.native.lua_host import LuaHost,LuaHostError
class Broker:
 def call(self,name,args,**options):
  if name=="addresslist.getMemoryRecordByID":return args[0]
  if name=="record.set":self.host.cancel();self.restored=True;return False
  raise AssertionError(name)
for worker in (False,True):
 broker=Broker();broker.restored=False;host=LuaHost(broker,owner_record_id=17);broker.host=host
 host.execute("for i=1,512 do createTimer(nil,false) end")
 try:
  if worker:
   host.execute("createThread(function() memrec.Active=false; while true do end end)");host.tick(0)
  else:host.execute("memrec.Active=false; while true do end")
 except LuaHostError as exc:assert "cancelled" in str(exc),str(exc)
 else:raise AssertionError("cancelled Lua frame completed")
 assert broker.restored and host._cancel_finished
print("suspended frames remained bounded")
'''
        result=subprocess.run([sys.executable,'-c',source],capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('suspended frames remained bounded',result.stdout)


if __name__=='__main__': unittest.main()


class NativeLuaEngineTests(unittest.TestCase):
    def test_frozen_active_uses_controller_bit_mask_and_keeps_exact_fallback(self):
        from types import SimpleNamespace
        from ct2trainer.native.lua_host import EngineLuaBroker
        class Memory:
            identity = (123, 456)
            pointer_size = 8
            data = b'\x03'
            def read(self, address, size):
                return self.data[:size]
        memory = Memory()
        engine = SimpleNamespace(memory=memory, entries={7:{'kind':'value','label':'flag'}},
                                 frozen={7:(0x1000,b'\x01')}, applied={},
                                 _guard=lambda: None, _check_patches=lambda: None)
        calls=[]
        def masked(identifier, address, desired):
            calls.append((identifier,address,desired))
            return memory.read(address,len(desired))[0]&1 == desired[0]&1
        engine._frozen_matches=masked
        broker=EngineLuaBroker(engine,input_handler=object())
        self.assertTrue(broker.call('record.get',(7,'Active'),generation=0,syntaxcheck=False))
        self.assertEqual(calls,[(7,0x1000,b'\x01')])
        memory.data=b'\x02'
        with self.assertRaisesRegex(LuaHostError,'Frozen MemoryRecord value changed'):
            broker.call('record.get',(7,'Active'),generation=0,syntaxcheck=False)
        del engine._frozen_matches
        memory.data=b'\x03'
        with self.assertRaisesRegex(LuaHostError,'Frozen MemoryRecord value changed'):
            broker.call('record.get',(7,'Active'),generation=0,syntaxcheck=False)
        memory.data=b'\x01'
        self.assertTrue(broker.call('record.get',(7,'Active'),generation=0,syntaxcheck=False))

    def test_scans_strings_signedness_and_fresh_active_confirmation(self):
        from test_native_engine import FakeMemory
        from ct2trainer.native.compiler import compile_table
        from ct2trainer.native.engine import TrainerEngine
        class Memory(FakeMemory):
            @property
            def identity(self): return self.pid,self.creation_time
            def _range(self,addr,size):
                if not self.base<=addr<=self.base+len(self.data)-size: raise ValueError('Invalid address')
            def scan_matches(self,pattern,**options):
                self.scan_options=options
                pattern=bytes.fromhex(pattern)
                start=options.get('start',self.base); end=options.get('end',self.base+len(self.data))
                return [self.base+i for i in range(len(self.data)-len(pattern)+1)
                        if self.data[i:i+len(pattern)]==pattern and start<=self.base+i<end]
        root=Path(__file__).resolve().parents[1]
        plan=compile_table(root/'tests/windows/fixture_target/fixture.ct','FixtureTarget.exe')
        memory=Memory()
        memory.data[32:36]=b'abc\0'
        memory.data[40:46]='\u00e4\u03a9\0'.encode('utf-16-le')
        memory.data[64:68]=b'\xff'*4
        memory.data[80:82]=memory.data[96:98]=b'\xaa\xbb'
        with tempfile.TemporaryDirectory() as directory:
            engine=TrainerEngine(plan,state_dir=directory,memory_factory=lambda name: memory,
                                 process_lock_dir=Path(directory)/'shared')
            engine.poll(); engine.toggle(0,True)
            writes=[]
            def mutation(action,args):
                self.assertEqual(action,'write'); writes.append(args); memory.write(*args); return True
            host=engine.open_lua_session(mutation_handler=mutation)
            self.assertEqual(host.execute('return readInteger("1040"),readInteger("1040",true)'),(0xffffffff,-1))
            self.assertEqual(host.execute('return readSmallInteger("1040"),readSmallInteger("1040",true)'),(65535,-1))
            self.assertTrue(host.execute('return writeInteger("1040",0xffffffff)'))
            self.assertEqual(writes[-1][1],b'\xff'*4)
            self.assertEqual(host.execute('return readString("1020",100),readString("1028",3,true)'),('abc','\u00e4\u03a9'))
            host.execute('writeString("1020","def")')
            self.assertEqual(writes[-1][1],b'def')
            self.assertEqual(host.execute('local s=AOBScan("AA BB"); return s.Count,s[0],s[1]'),(2,'1050','1060'))
            self.assertEqual(host.execute('local m=createMemScan(); local f=createFoundList(m); m.firstScan(soExactValue,vtByteArray,rtRounded,"AA BB",nil,getAddress("FixtureTarget.exe"),getAddress("FixtureTarget.exe")+getModuleSize("FixtureTarget.exe"),"+W-C",fsmNotAligned,"",true,false,false,false); m.waitTillDone(); f.initialize(); local n,a,b=f.Count,f.Address[0],f.Address[1]; m.destroy(); f.destroy(); return n,a,b'),(2,'1050','1060'))
            self.assertEqual(memory.scan_options['protection'],'+W-C')
            with self.assertRaisesRegex(LuaHostError,'fourteen'):
                host.execute('createMemScan().firstScan("AA BB")')
            self.assertTrue(host.execute('return getAddressList().getMemoryRecordByID(999)==nil'))
            self.assertTrue(host.execute('return getAddressList().getMemoryRecordByID(2).Type==vtDword and getAddressList().getMemoryRecordByID(1).Type==vtAutoAssembler'))
            engine.toggle(1,True)
            self.assertTrue(host.execute('return getAddressList().getMemoryRecordByID(1).Active'))
            memory.data[20:24]=bytes(4)
            with self.assertRaisesRegex(LuaHostError,'changed'):
                host.execute('return getAddressList().getMemoryRecordByID(1).Active')
            self.assertTrue(engine.blocked)
            count=len(writes)
            with self.assertRaises(LuaHostError): host.execute('writeInteger("1040",0)')
            self.assertEqual(len(writes),count)
            memory.alive=False; engine.close()

    def test_record_adapters_use_real_controller_guards_and_cancel_on_detach(self):
        try:
            import lupa.lua53
        except ImportError:
            self.skipTest('pinned MIT Lupa dependency unavailable')
        from test_native_engine import FakeMemory
        from ct2trainer.native.compiler import compile_table
        from ct2trainer.native.engine import TrainerEngine
        class IdentityMemory(FakeMemory):
            @property
            def identity(self): return self.pid,self.creation_time
        root=Path(__file__).resolve().parents[1]
        plan=compile_table(root/'tests/windows/fixture_target/fixture.ct','FixtureTarget.exe')
        memory=IdentityMemory()
        with tempfile.TemporaryDirectory() as directory:
            engine=TrainerEngine(plan,state_dir=directory,memory_factory=lambda name: memory,
                                 process_lock_dir=Path(directory)/'shared')
            engine.poll()
            host=engine.open_lua_session()
            with self.assertRaisesRegex(LuaHostError,'Unknown symbol'):
                host.execute('return getAddressList().getMemoryRecordByID(2).Value')
            self.assertFalse(engine.applied)
            engine.toggle(0,True)
            self.assertEqual(host.execute('return getAddressList().getMemoryRecordByID(2).Value'),'1234')
            host.execute('getAddressList().getMemoryRecordByID(2).Value="4321"')
            self.assertEqual(engine.read_value(2),'4321')
            self.assertTrue(memory.writes)
            with self.assertRaisesRegex(LuaHostError,'Syntax checking'):
                host.execute('getAddressList().getMemoryRecordByID(2).Value="1"',syntaxcheck=True)
            self.assertEqual(engine.read_value(2),'4321')
            memory.alive=False
            engine.poll()
            with self.assertRaisesRegex(LuaHostError,'cancelled'):
                host.execute('return readInteger("Anchor+10")')
            self.assertTrue(engine.close())
