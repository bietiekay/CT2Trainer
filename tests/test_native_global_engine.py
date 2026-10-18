"""Source/Engine integration contracts; no original script execution."""
from contextlib import contextmanager
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from ct2trainer.native.compiler import compile_table,validate_plan,NativeCompileError
from ct2trainer.native.engine import TrainerEngine,NativeRuntimeError
from ct2trainer.native.hooks import QuiescenceProof
from ct2trainer.native.address_expression import resolve_expression
from test_native_hooks import _Memory


def source(*,initializer=True,entry=0x1000):
    init='shared:\ndd #100\n' if initializer else ''
    original='B8 01 00 00 00' if entry==0x1000 else '90 90 90 90 90'
    return f'[ENABLE]\nlabel(done)\nglobalalloc(shared,4)\n{init}alloc(cave,1000)\ncave:\nmov rcx,shared\nmov eax,[rcx]\njmp done\n0x{entry:X}:\njmp cave\ndone:\n[DISABLE]\n0x{entry:X}:\ndb {original}\ndealloc(cave)\ndealloc(shared)'


class Memory(_Memory):
    pid=123
    creation_time=456
    closed=False
    def close(self):self.closed=True
    def resolve(self,text,symbols):return resolve_expression(text,self,symbols)
    def resolve_pointer(self,text,offsets,symbols):
        if offsets:raise ValueError('No pointer chain in this fake fixture')
        return self.resolve(text,symbols)
    def _scan(self,pattern,start=0,end=1<<64):
        from ct2trainer.native.patterns import pattern_matches
        self.scan_calls=getattr(self,'scan_calls',0)+1
        size=len(pattern.split())
        found=[base+offset for base,raw in self.data.items() for offset in range(len(raw)-size+1)
               if start<=base+offset<end and pattern_matches(pattern,raw[offset:offset+size])]
        if len(found)!=1:raise ValueError('owned scan ambiguity')
        return found[0]
    def scan_process(self,pattern):return self._scan(pattern)
    def scan_region(self,start,end,pattern):return self._scan(pattern,start,end)
    def scan_module(self,module,pattern):return self._scan(pattern)
    def module(self,name):return 0x1000,0x2000


class Coordinator:
    @contextmanager
    def hold(self,memory,ranges):
        held=[True]
        try:yield QuiescenceProof(memory.identity,tuple(ranges),'owned-fake-integration',lambda:held[0])
        finally:held[0]=False


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir=Path(self.tmp.name)
        self.memory=Memory()

    def table(self,scripts=(source(),),values=(),*,selected=None):
        root=ET.Element('CheatTable',CheatEngineTableVersion='45')
        entries=ET.SubElement(root,'CheatEntries')
        for index,text in enumerate(scripts,1):
            entry=ET.SubElement(entries,'CheatEntry')
            for k,v in {'ID':str(index),'Description':f'Own {index}','VariableType':'Auto Assembler Script','AssemblerScript':text}.items():
                ET.SubElement(entry,k).text=v
        for index,address in enumerate(values,len(scripts)+1):
            entry=ET.SubElement(entries,'CheatEntry')
            for k,v in {'ID':str(index),'Description':f'Own value {index}','VariableType':'4 Bytes','Address':address}.items():
                ET.SubElement(entry,k).text=v
        path=self.dir/'own.ct'
        path.write_bytes(ET.tostring(root,encoding='utf-8',xml_declaration=True))
        return compile_table(path,'Owned.exe',selected_ids=selected)

    def engine(self,plan,coordinator='owned'):
        e=TrainerEngine(plan,self.dir/'state',lambda name:self.memory,self.dir/'shared',
                        hook_coordinator=Coordinator() if coordinator=='owned' else coordinator)
        e.poll()
        self.assertTrue(e.connected,e.error)
        return e

    def test_canonical_source_context_regeneration_rejects_forged_globals(self):
        p=self.table(values=('shared',))
        self.assertTrue(p['entries'][0]['supported'])
        self.assertEqual(p['entries'][0]['provides'],['shared'])
        self.assertEqual(p['entries'][1]['dependency_ids'],[1])
        validate_plan(p)
        for change in ('size','process','address','mixed'):
            q=copy.deepcopy(p)
            if change=='size':q['entries'][0]['global_program']['globals'][0]['size']=8
            elif change=='process':q['entries'][0]['global_program']['process_name']='Foreign.exe'
            elif change=='address':q['entries'][0]['global_program']['globals'][0]['address']=0x10000
            else:q['entries'][0]['program']={}
            with self.assertRaises((NativeCompileError,ValueError)):
                validate_plan(q)
        self.assertFalse((self.dir/'state').exists())

    def test_enable_value_write_OFF_hides_symbol_but_retains_owned_storage(self):
        e=self.engine(self.table(values=('shared',)))
        e.toggle(1,True)
        base=e.symbols['shared']
        self.assertEqual(e.read_value(2),'100')
        e.set_value(2,'1')
        self.assertEqual(self.memory.read(base,4),(1).to_bytes(4,'little'))
        e.toggle(1,False)
        self.assertNotIn('shared',e.symbols)
        self.assertEqual(self.memory.read(base,4),(1).to_bytes(4,'little'))
        self.assertEqual(self.memory.releases,[])
        with self.assertRaises(Exception):e.read_value(2)
        with self.assertRaisesRegex(NativeRuntimeError,'Changed global reinitialization'):e.toggle(1,True)
        self.assertFalse(e.blocked,e.error)
        self.assertEqual(e.desired,set())

    def test_compatible_duplicate_declarers_share_without_ambiguous_external_admission(self):
        p=self.table((source(),source(initializer=False,entry=0x2000)),('shared',))
        self.assertTrue(p['entries'][0]['supported'])
        self.assertTrue(p['entries'][1]['supported'])
        self.assertFalse(p['entries'][2]['supported'])
        e=self.engine(p)
        e.toggle(1,True)
        base=e.symbols['shared']
        e.toggle(2,True)
        self.assertEqual(e.symbols['shared'],base)
        e.toggle(1,False)
        self.assertEqual(e.symbols['shared'],base)
        e.toggle(2,False)
        self.assertNotIn('shared',e.symbols)
        self.assertEqual(len(e.global_pool.members),1)

    def test_explicit_global_selection_excludes_ordinary_alternative_and_both_selected_keep_first(self):
        ordinary=source(entry=0x2000).replace('globalalloc(shared,4)','alloc(shared,4)\nregistersymbol(shared)')
        ordinary=ordinary.replace('[DISABLE]','[DISABLE]\nunregistersymbol(shared)')
        p=self.table((source(),ordinary),('shared',),selected=[1,3])
        self.assertTrue(p['entries'][0]['supported'])
        self.assertFalse(p['entries'][1]['supported'])
        self.assertFalse(p['entries'][1]['selected'])
        self.assertIn('Unselected symbol provider conflicts',p['entries'][1]['reason'])
        self.assertEqual(p['entries'][2]['dependency_ids'],[1])
        validate_plan(p)
        both=self.table((source(),ordinary),('shared',),selected=[1,2,3])
        # WP-37 keep-first: the document-order-first supported provider (the
        # global one) stays; the later ordinary duplicate is blocked with
        # the named reason and the consumer binds to the kept provider.
        self.assertTrue(both['entries'][0]['supported'])
        self.assertFalse(both['entries'][1]['supported'])
        self.assertIn('Symbol provider duplicate: shared (kept provider 1)',both['entries'][1]['reason'])
        self.assertTrue(both['entries'][2]['supported'])
        self.assertEqual(both['entries'][2]['dependency_ids'],[1])
        validate_plan(both)

    def test_frozen_child_must_release_before_implicit_global_provider(self):
        e=self.engine(self.table(values=('shared',)))
        e.toggle(1,True)
        e.set_freeze(2,True)
        with self.assertRaisesRegex(NativeRuntimeError,'dependent entries first'):e.toggle(1,False)
        self.assertIn(1,e.applied)
        e.set_freeze(2,False)
        e.toggle(1,False)
        self.assertNotIn('shared',e.symbols)

    def test_missing_coordinator_refuses_before_global_allocation_or_journal(self):
        e=self.engine(self.table(),coordinator=None)
        with self.assertRaisesRegex(NativeRuntimeError,'before allocation'):e.toggle(1,True)
        self.assertEqual(self.memory.allocations,{})
        self.assertIsNone(e.global_pool)
        self.assertFalse((self.dir/'state'/'hooks'/'global-pool.json').exists())

    def test_known_failed_enable_abandons_private_cave_and_only_releases_lease(self):
        e=self.engine(self.table())
        original=e._install_program
        def fail(program,owner,**kwargs):
            manager=kwargs['manager_factory'](self.dir/'state'/'hooks'/'failed-consumer.json',coordinator=e.hook_coordinator,
                owned_data_ranges=(),owned_executable_data_ranges=(),publication_guard=lambda:None)
            manager.abandon_unpublished()
            raise NativeRuntimeError('Owned prepublication linker refusal')
        e._install_program=fail
        with self.assertRaisesRegex(NativeRuntimeError,'linker refusal'):e.toggle(1,True)
        self.assertFalse(e.blocked,e.error)
        self.assertEqual(e.desired,set())
        self.assertEqual(e.global_leases,{})
        self.assertEqual(len(e.global_pool.members),1)
        self.assertEqual(self.memory.releases,[])

    def test_external_literal_consumer_without_coordinator_refuses_before_global_claim(self):
        text='[ENABLE]\nglobalalloc(shared,4)\nshared:\ndd #100\n0x1000:\ndb 90 90 90 90 90\n[DISABLE]\n0x1000:\ndb B8 01 00 00 00\ndealloc(shared)'
        p=self.table((text,))
        self.assertTrue(p['entries'][0]['supported'])
        self.assertTrue(p['entries'][0]['global_program']['consumer_shape']['requires_coordinator'])
        e=self.engine(p,coordinator=None)
        with self.assertRaisesRegex(NativeRuntimeError,'before allocation'):e.toggle(1,True)
        self.assertEqual(self.memory.allocations,{})
        self.assertIsNone(e.global_pool)

    def test_partial_pool_claim_blocks_without_allocating_or_reconstructing_json(self):
        e=self.engine(self.table())
        from ct2trainer.native.global_alloc import GlobalPool
        with patch.object(GlobalPool,'_save',side_effect=OSError('owned first journal flush fault')):
            with self.assertRaisesRegex(NativeRuntimeError,'flush fault'):e.toggle(1,True)
        self.assertTrue(e.blocked)
        journal=self.dir/'state'/'hooks'/'global-pool.json'
        self.assertTrue(journal.exists())
        self.assertEqual(journal.read_bytes(),b'')
        self.assertEqual(self.memory.allocations,{})
        self.assertEqual(e.desired,set())
        with self.assertRaises(NativeRuntimeError):e.toggle(1,True)
        self.assertEqual(journal.read_bytes(),b'')

    def test_combined_global_consumer_budget_refuses_before_pool_claim_and_close_restarts(self):
        p=self.table()
        e=self.engine(p)
        e._hook_lifetime_count=127 # one global plus one cave cannot fit
        with self.assertRaisesRegex(NativeRuntimeError,'before pool claim'):e.toggle(1,True)
        self.assertFalse(e.blocked,e.error)
        self.assertIsNone(e.global_pool)
        self.assertEqual(self.memory.allocations,{})
        self.assertFalse((self.dir/'state'/'hooks'/'global-pool.json').exists())
        self.assertTrue(e.close(),e.error)
        reopened=self.engine(p)
        self.assertTrue(reopened.close(),reopened.error)

    def test_exact_empty_pool_claim_closes_without_stranding_a_restart_fence(self):
        e=self.engine(self.table())
        from ct2trainer.native.global_alloc import GlobalPool
        e.global_pool=GlobalPool(self.memory,self.dir/'state'/'hooks',trainer_id=e.plan['trainer_id'],
            table_sha256=e.plan['table_sha256'],controller_guard=e._global_controller_guard,
            external_symbols=e._global_external_symbols)
        old=e.global_pool
        self.assertTrue(e.close(),e.error)
        self.assertEqual(old.state,'unexposed-closed')
        self.assertFalse(old.path.exists())
        self.assertEqual(self.memory.writes,[])
        self.assertEqual(self.memory.releases,[])

    def test_postpublication_confirmation_fault_retains_exact_manager_and_lease(self):
        e=self.engine(self.table())
        from ct2trainer.native.global_alloc import GlobalPool
        with patch.object(GlobalPool,'confirm_enabled',side_effect=OSError('owned confirmation receipt fault')):
            with self.assertRaisesRegex(NativeRuntimeError,'confirmation receipt fault'):e.toggle(1,True)
        self.assertTrue(e.blocked)
        self.assertEqual(e.desired,set())
        lease=e.global_leases[1]
        self.assertEqual(lease._manager.state,'enabled')
        self.assertIn(lease._manager,e.retired_hooks)
        self.assertTrue(lease._manager.path.exists())
        self.assertNotEqual(self.memory.read(0x1000,5),bytes.fromhex('B8 01 00 00 00'))
        self.assertEqual(self.memory.releases,[])
        # No false OFF or retry succeeds while the actual consumer is uncertain.
        with self.assertRaises(NativeRuntimeError):e.toggle(1,False)
        self.assertIs(e.global_leases[1]._manager,lease._manager)

    def scanned_source(self,scan):
        text=source().replace('globalalloc(shared,4)','globalalloc(shared,8,hitOwn)')
        text=text.replace('dd #100','db B8 01 00 00 00').replace('0x1000:','hitOwn:')
        return text.replace('[ENABLE]','[ENABLE]\n'+scan)

    def test_original_process_module_region_captures_survive_initializer_duplicate(self):
        for scan in ('aobscan(hitOwn,B8 01 00 00 00)',
                     'aobscanmodule(hitOwn,Owned.exe,B8 01 00 00 00)',
                     'aobscanregion(hitOwn,1000,30000,B8 01 00 00 00)'):
            with self.subTest(scan=scan):
                # Distinct fresh controller/session to isolate each capture.
                self.memory=Memory()
                p=self.table((self.scanned_source(scan),))
                state=self.dir/('case-'+str(len(list(self.dir.glob('case-*')))));state.mkdir()
                e=TrainerEngine(p,state,lambda name:self.memory,state/'shared',hook_coordinator=Coordinator())
                e.poll();self.assertTrue(e.connected,e.error)
                e.toggle(1,True)
                self.assertEqual(self.memory.scan_calls,1)
                self.assertEqual(e.applied[1][0].address,0x1000)
                self.assertEqual(self.memory.read(e.symbols['shared'],5),bytes.fromhex('B8 01 00 00 00'))
                e.toggle(1,False)
                self.assertEqual(self.memory.scan_calls,1)
                self.assertEqual(self.memory.read(0x1000,5),bytes.fromhex('B8 01 00 00 00'))
                self.memory.alive=False;e.poll();self.assertTrue(e.close(),e.error)

    def test_changed_original_scan_during_global_allocation_refuses_rebinding_and_entry_write(self):
        p=self.table((self.scanned_source('aobscan(hitOwn,B8 ?? 00 00 00)'),))
        e=self.engine(p)
        original=self.memory.allocate
        def allocate(size,near=None):
            result=original(size,near)
            self.memory.data[0x1000]=bytes.fromhex('B8 02 00 00 00')
            return result
        self.memory.allocate=allocate
        with self.assertRaisesRegex(NativeRuntimeError,'Original shared scan bytes changed'):e.toggle(1,True)
        self.assertEqual(self.memory.scan_calls,1)
        self.assertEqual(e.applied,{})
        self.assertEqual(e.desired,set())
        self.assertFalse(any(address==0x1000 for address,raw in self.memory.writes))
        self.assertEqual(self.memory.releases,[])

    def test_scan_bounds_cannot_refer_to_new_global_and_json_cannot_issue_capture(self):
        p=self.table((self.scanned_source('aobscanregion(hitOwn,shared,shared+100,B8 01 00 00 00)'),))
        self.assertFalse(p['entries'][0]['supported'])
        self.assertIn('scan bounds',p['entries'][0]['reason'])
        from ct2trainer.native.global_alloc import GlobalScanCapture,GlobalError
        with self.assertRaisesRegex(GlobalError,'controller-only'):
            GlobalScanCapture({},self.table()['entries'][0]['global_program'],self.memory,lambda:True)

    def test_target_exit_retires_pool_then_saved_on_uses_fresh_target_identity(self):
        e=self.engine(self.table())
        e.toggle(1,True)
        old=e.symbols['shared']
        self.memory.alive=False
        e.poll()
        self.assertIsNone(e.global_pool)
        self.assertIsNone(e.memory)
        self.assertEqual(e.desired,{1})
        self.assertFalse((self.dir/'state'/'hooks'/'global-pool.json').exists())
        fresh=Memory();fresh.identity=(124,457);fresh.pid=124;fresh.creation_time=457
        e.memory_factory=lambda name:fresh
        e.poll()
        self.assertTrue(e.connected,e.error)
        self.assertIn(1,e.applied)
        self.assertEqual(e.global_pool.identity,(124,457))
        self.assertEqual(fresh.read(e.symbols['shared'],4),(100).to_bytes(4,'little'))
        fresh.alive=False;e.poll()
        self.assertTrue(e.close(),e.error)

    def test_live_close_restores_entries_but_preserves_pool_and_restart_fence(self):
        p=self.table()
        e=self.engine(p)
        e.toggle(1,True)
        self.assertFalse(e.close())
        self.assertEqual(self.memory.read(0x1000,5),bytes.fromhex('b801000000'))
        self.assertTrue((self.dir/'state'/'state.lock').exists())
        self.assertTrue((self.dir/'state'/'session.json').exists())
        self.assertTrue((self.dir/'state'/'hooks'/'global-pool.json').exists())
        self.assertEqual(self.memory.releases,[])
        with self.assertRaises(Exception):
            TrainerEngine(p,self.dir/'state',lambda name:Memory(),self.dir/'shared')

    def test_readmem_backed_original_inputs_stay_visible_refusals(self):
        p=self.table((source().replace('dd #100','readmem(0x1000,4)'),))
        self.assertFalse(p['entries'][0]['supported'])
        self.assertIn('blocked',p['entries'][0]['kind'])


if __name__=='__main__':unittest.main()
