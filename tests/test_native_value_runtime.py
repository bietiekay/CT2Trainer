"""Masked field writes/freeze coalesce under held data proof, arrays are exact."""
from contextlib import contextmanager
from pathlib import Path
import tempfile
import unittest

from test_native_lua_activation import Memory
from test_native_engine_code import Coordinator
from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import TrainerEngine, NativeRuntimeError
from ct2trainer.native.hooks import QuiescenceProof, HookError, HookUncertain


class DataCoordinator(Coordinator):
    def __init__(self):
        super().__init__()
        self.data_holds=[]
        self.fail=False
        self.expire=False
        self.cleanup_uncertain=False
    @contextmanager
    def hold_data(self,memory,ranges):
        if self.fail:raise HookError('Owned pre-write refusal')
        self.data_holds.append(tuple(ranges))
        yield QuiescenceProof(memory.identity,tuple(ranges),'owned-data-unit',lambda:not self.expire)
        if self.cleanup_uncertain:raise HookUncertain('Owned resume failure')


class ValueProfileRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.table=self.root/'owned.ct'
        self.table.write_text('''<CheatTable CheatEngineTableVersion="45"><CheatEntries>
<CheatEntry><ID>1</ID><Description>Bit zero</Description><VariableType>Binary</VariableType><Address>1040</Address><BitStart>0</BitStart><BitLength>1</BitLength><ShowAsBinary>0</ShowAsBinary></CheatEntry>
<CheatEntry><ID>2</ID><Description>Bit one</Description><VariableType>Binary</VariableType><Address>1040</Address><BitStart>1</BitStart><BitLength>1</BitLength><ShowAsBinary>0</ShowAsBinary></CheatEntry>
<CheatEntry><ID>3</ID><Description>Conflicting whole byte</Description><VariableType>Byte</VariableType><Address>1040</Address></CheatEntry>
<CheatEntry><ID>4</ID><Description>Exact array</Description><VariableType>Array of byte</VariableType><Address>1050</Address><ByteLength>4</ByteLength></CheatEntry>
<CheatEntry><ID>5</ID><Description>Placeholder</Description><VariableType>Array of byte</VariableType><Address>1060</Address><ByteLength>0</ByteLength><CheatEntries><CheatEntry><ID>6</ID><Description>Inherited bit</Description><VariableType>Binary</VariableType><Address>+1</Address><BitStart>7</BitStart><BitLength>1</BitLength><ShowAsBinary>1</ShowAsBinary></CheatEntry></CheatEntries></CheatEntry>
<CheatEntry><ID>7</ID><Description>Wide masked field</Description><VariableType>Binary</VariableType><Address>1040</Address><BitStart>4</BitStart><BitLength>8</BitLength></CheatEntry>
</CheatEntries></CheatTable>''',encoding='utf-8')
        self.memory=Memory()
        self.coordinator=DataCoordinator()
        self.engine=TrainerEngine(compile_table(self.table,'FixtureTarget.exe'),state_dir=self.root/'state',
                                  process_lock_dir=self.root/'shared',memory_factory=lambda name:self.memory,
                                  hook_coordinator=self.coordinator)
        self.engine.poll()
    def tearDown(self):
        self.engine.close()

    def test_bit_write_merges_with_held_snapshot_and_preserves_neighbors(self):
        self.memory.data[0x40]=0xD2
        self.assertEqual(self.engine.set_value(1,'1'),'1')
        self.assertEqual(self.memory.read(0x1040,1),b'\xd3')
        self.assertEqual(self.coordinator.data_holds,[((0x1040,1),)])
        self.assertEqual(self.engine.read_value(2),'1')
        self.assertEqual(self.engine.set_value(1,'0'),'0')
        self.assertEqual(self.memory.read(0x1040,1),b'\xd2')

    def test_disjoint_freezes_coalesce_once_and_preserve_fresh_unowned_bits(self):
        self.memory.data[0x40]=0xA3
        self.engine.set_freeze(1,True)
        self.engine.set_freeze(2,True)
        self.memory.data[0x40]=0xD0
        self.engine.poll()
        self.assertFalse(self.engine.blocked,self.engine.error)
        self.assertEqual(self.memory.read(0x1040,1),b'\xd3')
        self.assertEqual(self.coordinator.data_holds,[((0x1040,1),)])
        self.assertTrue(self.engine._frozen_matches(1,0x1040,self.engine.frozen[1][1]))
        with self.assertRaisesRegex(NativeRuntimeError,'overlaps'):
            self.engine.set_value(3,'0')
        self.assertEqual(self.engine.set_value(1,'0'),'0')
        self.memory.data[0x40]=0x80
        self.engine.poll()
        self.assertEqual(self.memory.read(0x1040,1),b'\x82')

    def test_invalid_bit_literal_has_no_provider_or_target_effect(self):
        with self.assertRaises(NativeRuntimeError):self.engine.set_value(1,'2')
        self.assertFalse(self.memory.writes)
        self.assertFalse(self.coordinator.data_holds)
        self.assertFalse(self.engine.blocked)

    def test_prewrite_data_hold_refusal_keeps_retryable_state(self):
        self.coordinator.fail=True
        with self.assertRaisesRegex(NativeRuntimeError,'pre-write'):
            self.engine.set_value(1,'1')
        self.assertFalse(self.memory.writes)
        self.assertFalse(self.engine.blocked)
        self.coordinator.fail=False
        self.assertEqual(self.engine.set_value(1,'1'),'1')

    def test_exec_bitfield_refused_before_mutation(self):
        self.memory.is_executable=lambda address,size:True
        with self.assertRaisesRegex(NativeRuntimeError,'executable provider'):
            self.engine.set_value(1,'1')
        self.assertFalse(self.memory.writes)
        self.assertFalse(self.coordinator.data_holds)

    def test_exec_bitfield_freeze_refused_before_recording_with_incomplete_permit(self):
        self.memory.is_executable=lambda address,size:True
        self.engine._owned_provider_data=lambda:([],[(0x1040,1,0x1000,256)])
        with self.assertRaisesRegex(NativeRuntimeError,'bit-field freezes'):
            self.engine.set_freeze(7,True)
        self.assertFalse(self.engine.frozen)
        self.assertFalse(self.engine.blocked)
        self.assertFalse(self.memory.writes)
        self.assertFalse(self.coordinator.data_holds)

    def test_proof_expiry_after_write_blocks_and_preserves_mutation_evidence(self):
        self.memory.data[0x40]=0xD2
        write=self.memory.write
        def expire_after_write(address,raw):
            write(address,raw)
            self.coordinator.expire=True
        self.memory.write=expire_after_write
        with self.assertRaisesRegex(NativeRuntimeError,'rollback is uncertain'):
            self.engine.set_value(1,'1')
        self.assertTrue(self.engine.blocked)
        self.assertEqual(self.memory.read(0x1040,1),b'\xd3')
        self.assertEqual(self.memory.writes,[(0x1040,b'\xd3')])
        self.assertTrue(self.engine.store.lock.exists())
        self.assertTrue(self.engine.store.session.exists())

    def test_uncertain_data_resume_blocks_after_confirmed_write(self):
        self.coordinator.cleanup_uncertain=True
        with self.assertRaisesRegex(NativeRuntimeError,'resume failure'):
            self.engine.set_value(1,'1')
        self.assertTrue(self.engine.blocked)
        self.assertEqual(self.memory.read(0x1040,1),b'\x01')
        self.assertTrue(self.engine.store.session.exists())

    def test_array_exact_write_readback_freeze_and_bad_length_rejection(self):
        self.assertEqual(self.engine.set_value(4,'01 a2 03 FF'),'01 A2 03 FF')
        self.engine.set_freeze(4,True)
        self.memory.data[0x50:0x54]=bytes(4)
        self.engine.poll()
        self.assertEqual(self.engine.read_value(4),'01 A2 03 FF')
        before=list(self.memory.writes)
        for text in ('01 02','01 ?? 03 FF','01 02 03 04 05'):
            with self.assertRaises(NativeRuntimeError):self.engine.set_value(4,text)
        self.assertEqual(before,self.memory.writes)

    def test_zero_array_has_no_actions_and_child_uses_inherited_address(self):
        self.assertEqual(self.engine.entries[5]['kind'],'heading')
        with self.assertRaises(NativeRuntimeError):self.engine.set_value(5,'')
        self.assertEqual(self.engine.set_value(6,'1'),'1')
        self.assertEqual(self.memory.read(0x1061,1),b'\x80')
