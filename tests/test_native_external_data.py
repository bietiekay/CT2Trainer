"""Canonical literal capabilities and actual last-WPM admission, owned models only."""
from contextlib import contextmanager
from copy import deepcopy
import ctypes
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from ct2trainer.native.aa_program import prepare_program, link_program, ProgramError, validate_program
from ct2trainer.native.hooks import HookManager, HookError, HookUncertain, QuiescenceProof, validate_instruction_boundary
from ct2trainer.native.memory import ProcessMemory, ProcessMemoryError, _checked_write
from ct2trainer.native.lua_work_budget import WorkLimits, WorkBudgetError, work_slice, controller_cleanup
from ct2trainer.native import recovery
from test_native_memory import _memory, _region
from test_native_lua_work_budget import Clock

SOURCE='''[ENABLE]
3000:
 dd #1432778632
[DISABLE]
3000:
 dd #287454020
'''
ORIGINAL=bytes.fromhex('44332211')
REPLACEMENT=bytes.fromhex('88776655')


def kernel_memory():
    memory=_memory()
    memory.data=bytearray(ORIGINAL + b'\xAB'*252)
    memory.protection=0x04
    memory.region_type=0x20000
    memory.write_calls=[]
    memory.query_hook=None
    memory.alive_hook=None
    memory.read_hook=None
    memory.in_write=False
    memory.write_alive_calls=0
    def query(address):
        if memory.query_hook: memory.query_hook(address)
        region=_region(0x3000,256,memory.protection)
        region.AllocationBase=0x3000
        region.Type=memory.region_type
        return region
    def read(handle,address,buffer,size,transferred):
        data=memory.data[address-0x3000:address-0x3000+size]
        ctypes.memmove(buffer,bytes(data),size)
        ctypes.cast(transferred,ctypes.POINTER(ctypes.c_size_t)).contents.value=size
        if memory.read_hook: memory.read_hook(address,size)
        return True
    def write(handle,address,buffer,size,transferred):
        data=ctypes.string_at(buffer,size)
        memory.data[address-0x3000:address-0x3000+size]=data
        memory.write_calls.append((address,data))
        ctypes.cast(transferred,ctypes.POINTER(ctypes.c_size_t)).contents.value=size
        return True
    def protect(handle,address,size,value,previous):
        ctypes.cast(previous,ctypes.POINTER(ctypes.c_uint32)).contents.value=memory.protection
        memory.protection=value
        return True
    old_alive=memory._require_alive
    def alive():
        if memory.in_write:
            memory.write_alive_calls+=1
            if memory.alive_hook: memory.alive_hook(memory.write_alive_calls)
        old_alive()
    old_write=memory._write_checked
    def checked(*args,**options):
        memory.in_write=True; memory.write_alive_calls=0
        try: return old_write(*args,**options)
        finally: memory.in_write=False
    memory._query=query
    memory._require_alive=alive
    memory._write_checked=checked
    memory._kernel.ReadProcessMemory=Mock(side_effect=read)
    memory._kernel.WriteProcessMemory=Mock(side_effect=write)
    memory._kernel.VirtualProtectEx=Mock(side_effect=protect)
    memory._kernel.FlushInstructionCache=Mock(return_value=True)
    return memory


class DataCoordinator:
    def __init__(self):
        self.held=False; self.calls=0; self.enter=None
    @contextmanager
    def hold_data(self,memory,ranges):
        self.held=True; self.calls+=1
        if self.enter: self.enter()
        try:
            yield QuiescenceProof(memory.identity,tuple(ranges),'owned-model-held-event',lambda:self.held)
        finally: self.held=False
    def hold_entries(self,*args,**kwargs):
        raise AssertionError('External data must never enter the instruction coordinator')


class ExternalLiteralTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.memory=kernel_memory();self.coordinator=DataCoordinator()
        self.program=prepare_program(SOURCE,'owned.exe')
        self.path=Path(self.tmp.name)/'hook.json'
    def linked(self,program=None):
        return link_program(program or self.program,self.memory,_allow_external_literals=True)
    def staged(self):
        linked=self.linked()
        manager=HookManager(self.memory,self.path,self.coordinator,'a'*16+':owned')
        manager.stage(linked['blocks'],_external_literal_permits=linked['_external_literal_permits'])
        return manager
    def test_invalid_instruction_data_uses_held_data_and_restores_exactly(self):
        for bits in (32,64):
            with self.assertRaises(HookError): validate_instruction_boundary(0x3000,ORIGINAL,bits)
        manager=self.staged(); receipt=manager.publish()
        self.assertEqual(bytes(self.memory.data[:4]),REPLACEMENT)
        self.assertTrue(receipt['entries'][0]['external_data'])
        self.assertFalse(receipt['entries'][0]['executable'])
        self.assertEqual(receipt['external_data_program'],self.program)
        self.assertEqual(recovery._hook(receipt,'a'*16),recovery.ProcessIdentity(*self.memory.identity))
        manager.disable()
        self.assertEqual(bytes(self.memory.data),ORIGINAL+b'\xAB'*252)
        self.assertEqual(manager.state,'abandoned')
        self.assertEqual(self.coordinator.calls,2)
        self.assertEqual([raw for _,raw in self.memory.write_calls],[REPLACEMENT,ORIGINAL])
        self.assertEqual(recovery._hook(manager.receipt(),'a'*16),recovery.ProcessIdentity(*self.memory.identity))
    def test_public_diagnostic_link_does_not_mint_capabilities(self):
        linked=link_program(self.program,self.memory)
        self.assertNotIn('_external_literal_permits',linked)
        self.assertTrue(linked['blocks'][0]['executable'])
        json.dumps(linked)
    def test_flag_or_receipt_cannot_reconstruct_live_capability(self):
        linked=self.linked()
        manager=HookManager(self.memory,self.path,self.coordinator)
        block=dict(linked['blocks'][0],external_data=True,external_source_sha256=self.program['source_sha256'])
        with self.assertRaisesRegex(HookError,'Serialized'): manager.stage([block])
        self.assertEqual(self.memory.write_calls,[])
    def test_sealed_permit_rejects_changed_bytes_target_or_foreign_model(self):
        linked=self.linked();block=dict(linked['blocks'][0],bytes='01020304')
        manager=HookManager(self.memory,self.path,self.coordinator)
        with self.assertRaisesRegex(HookError,'sealed'): manager.stage([block],_external_literal_permits=linked['_external_literal_permits'])
        self.assertEqual(self.memory.write_calls,[])
        permit=linked['_external_literal_permits'][0]
        with self.assertRaises(HookError): permit.verify(kernel_memory())
        self.memory._creation_time+=1
        with self.assertRaises(HookError): permit.verify(self.memory)
    def test_mixed_code_data_and_executable_allocations_are_refused(self):
        for body in ('3004:\n nop', 'align 8', 'readmem(3004,1)', 'alloc(cave,32)\ncave:\n nop'):
            source=SOURCE.replace('[DISABLE]',body+'\n[DISABLE]')
            program=prepare_program(source,'owned.exe')
            with self.assertRaises((HookError,ProgramError)): self.linked(program)
        self.assertEqual(self.memory.write_calls,[])
    def test_nonliteral_symbol_data_does_not_mint_permit(self):
        source=SOURCE.replace('dd #1432778632','dd owned')
        linked=link_program(prepare_program(source,'owned.exe'),self.memory,{'owned':0x3004},_allow_external_literals=True)
        self.assertEqual(linked['_external_literal_permits'],())
        self.assertTrue(linked['blocks'][0]['executable'])
    def test_protection_changed_on_acquiring_held_event_refuses_before_write(self):
        manager=self.staged()
        self.coordinator.enter=lambda:setattr(self.memory,'protection',0x40)
        with self.assertRaises(HookError): manager.publish()
        self.assertEqual(self.memory.write_calls,[])
        self.assertFalse(self.memory._write_uncertain)
    def test_protection_changed_during_backend_final_identity_refuses_before_wpm(self):
        manager=self.staged()
        self.memory.alive_hook=lambda n:setattr(self.memory,'protection',0x40) if n==2 else None
        with self.assertRaises(HookError): manager.publish()
        self.assertEqual(self.memory.write_calls,[])
        self.assertFalse(self.memory._write_uncertain)
    def test_protection_change_before_undo_preserves_active_bytes(self):
        manager=self.staged();manager.publish()
        self.memory.protection=0x40
        with self.assertRaises(HookError): manager.disable()
        self.assertEqual(bytes(self.memory.data[:4]),REPLACEMENT)
        self.assertEqual(len(self.memory.write_calls),1)
    def test_region_identity_change_refuses_even_if_rw_stays_rw(self):
        manager=self.staged();self.memory.region_type=0x1000000
        with self.assertRaises(HookError): manager.publish()
        self.assertEqual(self.memory.write_calls,[])
    def test_held_lease_and_foreign_bytes_are_rechecked_after_backend_guards(self):
        for mode in ('lease','bytes'):
            with self.subTest(mode=mode):
                manager=self.staged()
                def changed(n):
                    if n==2:
                        if mode=='lease':self.coordinator.held=False
                        else:self.memory.data[0]=0xFE
                self.memory.alive_hook=changed
                with self.assertRaises(HookError):manager.publish()
                self.assertEqual(self.memory.write_calls,[])
                self.assertFalse(self.memory._write_uncertain)
                self.memory=kernel_memory();self.coordinator=DataCoordinator()
                self.path=Path(self.tmp.name)/(mode+'-next.json')

    def test_post_success_deadline_exact_rollback_keeps_permit_and_proof_guards(self):
        clock=Clock();manager=self.staged();save=manager._save
        def delayed_save(*args,**options):
            save(*args,**options)
            if manager.state=='enabled':clock.advance(.6)
        manager._save=delayed_save
        with self.assertRaises((WorkBudgetError,HookError)):
            with work_slice(WorkLimits(lua_seconds=1,instructions=10000,broker_call_seconds=.5,broker_seconds=1,wall_seconds=2),lambda:None,clock) as budget:
                with budget.dispatch():manager.publish()
        self.assertEqual(bytes(self.memory.data),ORIGINAL+b'\xAB'*252)
        self.assertEqual([raw for _,raw in self.memory.write_calls],[REPLACEMENT,ORIGINAL])
        self.assertFalse(manager.uncertain)
        self.assertEqual(manager.state,'abandoned')
        self.assertFalse(self.memory._write_uncertain)

    def test_forged_recovery_program_or_classification_is_rejected(self):
        manager=self.staged();manager.publish();receipt=manager.receipt()
        variants=[]
        wrong=deepcopy(receipt);wrong['entries'][0]['external_source_sha256']='b'*64;variants.append(wrong)
        wrong=deepcopy(receipt);wrong['external_data_program']['source']+='\n';variants.append(wrong)
        wrong=deepcopy(receipt);wrong['entries'][0]['external_data']=1;variants.append(wrong)
        wrong=deepcopy(receipt);wrong.pop('external_data_program');variants.append(wrong)
        wrong=deepcopy(receipt);wrong['external_data_program']=None;variants.append(wrong)
        wrong=deepcopy(receipt);wrong['external_data_program']['external_data']=True;variants.append(wrong)
        for value in variants:
            with self.assertRaises(recovery._AssessmentError): recovery._hook(value,'a'*16)
    def test_scalar_float_string_emission_is_independently_byte_bound(self):
        source='''[ENABLE]\n3000:\n db "AB"\n dw -1\n dd (float)1.0\n dq #123\n[DISABLE]\n3000:\n db 44 33 22 11 AB AB AB AB AB AB AB AB AB AB AB AB\n'''
        linked=self.linked(prepare_program(source,'owned.exe'))
        self.assertEqual(bytes.fromhex(linked['blocks'][0]['bytes']),b'AB\xff\xff\0\0\x80?'+(123).to_bytes(8,'little'))
        self.assertEqual(len(linked['_external_literal_permits']),1)


class LastKernelBudgetTests(unittest.TestCase):
    def test_slow_query_and_last_alive_refuse_default_write_without_uncertainty(self):
        for mode in ('query','identity'):
            memory=kernel_memory();clock=Clock()
            if mode=='query': memory.query_hook=lambda a:clock.advance(.6) if memory.in_write else None
            else: memory.alive_hook=lambda n:clock.advance(.6) if n==2 else None
            with self.subTest(mode=mode),self.assertRaises(WorkBudgetError):
                with work_slice(WorkLimits(lua_seconds=1,instructions=10000,broker_call_seconds=.5,broker_seconds=1,wall_seconds=2),lambda:None,clock) as budget:
                    with budget.dispatch(): memory.write(0x3000,REPLACEMENT)
            self.assertEqual(memory.write_calls,[])
            self.assertFalse(memory._write_uncertain)
            self.assertEqual(bytes(memory.data[:4]),ORIGINAL)
    def test_clean_refusal_restores_protection_but_restore_failure_is_uncertain(self):
        for fail_restore in (False,True):
            memory=kernel_memory();memory.protection=0x02
            old=memory._kernel.VirtualProtectEx.side_effect
            memory._kernel.VirtualProtectEx.side_effect=lambda h,a,n,v,p:False if fail_restore and v==0x02 else old(h,a,n,v,p)
            def reject(): raise HookError('admission refused')
            with self.subTest(fail_restore=fail_restore),self.assertRaises((HookError,ProcessMemoryError)):
                memory._write_checked(0x3000,REPLACEMENT,before_kernel=reject)
            self.assertEqual(memory.write_calls,[])
            self.assertEqual(memory._write_uncertain,fail_restore)
            if not fail_restore:self.assertEqual(memory.protection,0x02)
    def test_engine_clean_kernel_refusal_does_not_issue_rollback_write(self):
        from ct2trainer.native.engine import TrainerEngine, _Patch, NativeRuntimeError
        memory=kernel_memory();clock=Clock()
        engine=object.__new__(TrainerEngine)
        engine.memory=memory;engine._guard=Mock();engine._is_executable=Mock(return_value=False);engine._block=Mock()
        memory.query_hook=lambda a:clock.advance(.6) if memory.in_write else None
        with self.assertRaises((WorkBudgetError,NativeRuntimeError)):
            with work_slice(WorkLimits(lua_seconds=1,instructions=10000,broker_call_seconds=.5,broker_seconds=1,wall_seconds=2),lambda:None,clock) as budget:
                with budget.dispatch():engine._write_transaction([_Patch(0x3000,ORIGINAL,REPLACEMENT)])
        self.assertEqual(memory.write_calls,[])
        self.assertFalse(memory._write_uncertain)
        self.assertEqual(bytes(memory.data[:4]),ORIGINAL)

    def test_exact_emergency_rollback_can_bypass_expired_normal_context(self):
        memory=kernel_memory();clock=Clock()
        with self.assertRaises(WorkBudgetError):
            with work_slice(WorkLimits(lua_seconds=1,instructions=10000,broker_call_seconds=.5,broker_seconds=1,wall_seconds=2),lambda:None,clock) as budget:
                with budget.dispatch():
                    memory.write(0x3000,REPLACEMENT)
                    clock.advance(.6)
                    with controller_cleanup(lambda:None,clock):
                        _checked_write(memory,0x3000,ORIGINAL,before_kernel=lambda:self.assertEqual(memory.read(0x3000,4),REPLACEMENT),rollback=True)
        self.assertEqual(bytes(memory.data[:4]),ORIGINAL)
        self.assertEqual(len(memory.write_calls),2)
    def test_slow_last_proof_predicate_is_charged_before_actual_wpm(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        memory=kernel_memory();clock=Clock()
        class SlowProofCoordinator(DataCoordinator):
            @contextmanager
            def hold_data(self,memory,ranges):
                self.held=True
                def check():
                    if memory.in_write:clock.advance(.6)
                    return self.held
                try:yield QuiescenceProof(memory.identity,tuple(ranges),'owned-slow-proof',check)
                finally:self.held=False
        program=prepare_program(SOURCE,'owned.exe');linked=link_program(program,memory,_allow_external_literals=True)
        manager=HookManager(memory,Path(tmp.name)/'hook.json',SlowProofCoordinator())
        manager.stage(linked['blocks'],_external_literal_permits=linked['_external_literal_permits'])
        with self.assertRaises((WorkBudgetError,HookError)):
            with work_slice(WorkLimits(lua_seconds=1,instructions=10000,broker_call_seconds=.5,broker_seconds=1,wall_seconds=2),lambda:None,clock) as budget:
                with budget.dispatch():manager.publish()
        self.assertEqual(memory.write_calls,[])
        self.assertFalse(memory._write_uncertain)

    def test_proof_lease_clock_is_checked_after_slow_identity(self):
        memory=kernel_memory();clock=Clock()
        proof=QuiescenceProof(memory.identity,((0x3000,4),),'owned-lease',lambda:clock.value <=100.5)
        memory.is_alive=lambda:(clock.advance(.6) or True)
        with self.assertRaises(HookError):proof.verify(memory,((0x3000,4),))

    def test_external_held_backend_delay_does_not_begin_wpm(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        memory=kernel_memory();clock=Clock()
        program=prepare_program(SOURCE,'owned.exe')
        linked=link_program(program,memory,_allow_external_literals=True)
        manager=HookManager(memory,Path(tmp.name)/'hook.json',DataCoordinator())
        manager.stage(linked['blocks'],_external_literal_permits=linked['_external_literal_permits'])
        memory.query_hook=lambda a:clock.advance(.6) if memory.in_write else None
        with self.assertRaises((WorkBudgetError,HookError)):
            with work_slice(WorkLimits(lua_seconds=1,instructions=10000,broker_call_seconds=.5,broker_seconds=1,wall_seconds=2),lambda:None,clock) as budget:
                with budget.dispatch():manager.publish()
        self.assertEqual(memory.write_calls,[])
        self.assertFalse(memory._write_uncertain)
        self.assertEqual(bytes(memory.data[:4]),ORIGINAL)

if __name__=='__main__': unittest.main()
