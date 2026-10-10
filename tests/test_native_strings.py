"""Owned bytes verify canonical String plans, held prefixes and freeze tails."""
from copy import deepcopy
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from test_native_lua_activation import Memory
from test_native_value_runtime import DataCoordinator
from ct2trainer.native.compiler import compile_table, validate_plan as compiler_validate
from ct2trainer.native.engine import TrainerEngine, NativeRuntimeError, validate_plan
from ct2trainer.native.value_types import (prepare_value_profile, parse_profile_value,
    format_profile_value, format_written_profile_value, profile_value_matches, validate_value_profile)
from ct2trainer.native.lua_work_budget import WorkLimits,WorkBudgetError,work_slice
from test_native_lua_work_budget import Clock


class StringMemory(Memory):
    def __init__(self):
        super().__init__()
        self.protection=4
        self.queries=0
        self.query_effect=None
    def _query(self,address):
        self.queries+=1
        if self.query_effect:self.query_effect(self,address)
        self._range(address,1)
        return SimpleNamespace(BaseAddress=self.base,AllocationBase=self.base,
            RegionSize=len(self.data),State=0x1000,Protect=self.protection,Type=0x20000)


class StringRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.table=self.root/'owned.ct'
        self.table.write_text('''<CheatTable CheatEngineTableVersion="45"><CheatEntries>
<CheatEntry><ID>1</ID><Description>ASCII</Description><VariableType>String</VariableType><Length>8</Length><ZeroTerminate>1</ZeroTerminate><Address>1040</Address></CheatEntry>
<CheatEntry><ID>2</ID><Description>UTF16</Description><VariableType>String</VariableType><Length>16</Length><Unicode>1</Unicode><CodePage>0</CodePage><ZeroTerminate>1</ZeroTerminate><Address>1080</Address></CheatEntry>
<CheatEntry><ID>3</ID><Description>Fixed</Description><VariableType>String</VariableType><Length>8</Length><ZeroTerminate>0</ZeroTerminate><Address>1060</Address></CheatEntry>
<CheatEntry><ID>4</ID><Description>Anchor</Description><VariableType>String</VariableType><Length>0</Length><Address>10E0</Address><CheatEntries><CheatEntry><ID>5</ID><Description>Inherited</Description><VariableType>Byte</VariableType><Address>+4</Address></CheatEntry></CheatEntries></CheatEntry>
<CheatEntry><ID>6</ID><Description>Overlap</Description><VariableType>Byte</VariableType><Address>1041</Address></CheatEntry>
<CheatEntry><ID>7</ID><Description>Codepage</Description><VariableType>String</VariableType><Length>8</Length><CodePage>1</CodePage><Address>1040</Address></CheatEntry>
</CheatEntries></CheatTable>''',encoding='utf-8')
        self.plan=compile_table(self.table,'FixtureTarget.exe')
        self.memory=StringMemory()
        self.memory.data[0x40:0x48]=b'old\0TAIL'
        self.memory.data[0x60:0x68]=b'FIX\0TURE'
        wide='OLD🙂\0'.encode('utf-16-le')
        self.memory.data[0x80:0xA0]=wide+b'\x00\xd8'*(16-len(wide)//2)
        self.coordinator=DataCoordinator()
        self.engine=TrainerEngine(self.plan,state_dir=self.root/'state',process_lock_dir=self.root/'shared',
            memory_factory=lambda name:self.memory,hook_coordinator=self.coordinator)
        self.engine.poll()
        self.addCleanup(self.engine.close)
    def test_canonical_compiler_and_runtime_plans(self):
        compiler_validate(self.plan);validate_plan(self.plan)
        entries=self.engine.entries
        self.assertEqual(entries[1]['kind'],'value')
        self.assertEqual(entries[2]['value_profile']['size'],32)
        self.assertEqual(entries[4]['kind'],'heading')
        self.assertFalse(entries[7]['supported'])
        self.assertIn('Codepage',entries[7]['reason'])
        self.assertEqual(self.engine._value_address(entries[5]),0x10E4)
    def test_ascii_prefix_preserves_exact_tail_and_held_span(self):
        self.assertEqual(self.engine.set_value(1,'x'),'x')
        self.assertEqual(self.memory.read(0x1040,8),b'x\0d\0TAIL')
        self.assertEqual(self.coordinator.data_holds,[((0x1040,2),)])
        self.assertEqual(self.memory.writes,[(0x1040,b'x\0')])
        self.assertEqual(self.engine.read_value(1),'x')
    def test_utf16_surrogate_pair_and_invalid_tail_preserved(self):
        before=self.memory.read(0x1080,32)
        self.assertEqual(self.engine.read_value(2),'OLD🙂')
        self.assertEqual(self.engine.set_value(2,' ä🙂 '),' ä🙂 ')
        wanted=' ä🙂 \0'.encode('utf-16-le')
        self.assertEqual(self.memory.read(0x1080,32),wanted+before[len(wanted):])
        self.assertEqual(self.coordinator.data_holds,[((0x1080,len(wanted)),)])
    def test_fixed_string_exact_length_and_embedded_nul(self):
        self.assertEqual(self.engine.set_value(3,'A\0BCD123'),'A\0BCD123')
        self.assertEqual(self.memory.read(0x1060,8),b'A\0BCD123')
        with self.assertRaises(NativeRuntimeError):self.engine.set_value(3,'short')
    def test_invalid_literal_has_no_hold_or_target_effect(self):
        for value in ('12345678','a\0b','ä','\ud800'):
            with self.subTest(value=repr(value)),self.assertRaises(NativeRuntimeError):
                self.engine.set_value(1,value)
        self.assertFalse(self.memory.writes)
        self.assertFalse(self.coordinator.data_holds)
        self.assertFalse(self.engine.blocked)
    def test_empty_terminated_literal_owns_only_terminator(self):
        self.engine.set_value(2,'')
        self.assertEqual(self.memory.writes[0],(0x1080,b'\0\0'))
        self.assertEqual(self.engine.read_value(2),'')
    def test_freeze_owns_only_canonical_prefix_and_preserves_new_tail(self):
        self.engine.set_freeze(1)
        self.assertEqual(self.engine.frozen[1][1],b'old\0')
        self.memory.data[0x44:0x48]=b'NEW!'
        self.engine.poll()
        self.assertFalse(self.memory.writes)
        self.assertTrue(self.engine._frozen_matches(1,0x1040,b'old\0'))
        self.memory.data[0x40:0x44]=b'BAD\0'
        self.engine.poll()
        self.assertFalse(self.engine.blocked,self.engine.error)
        self.assertEqual(self.memory.read(0x1040,8),b'old\0NEW!')
        self.assertTrue(self.engine.set_freeze(1,False)==False)
    def test_unterminated_freeze_refuses_without_write_or_state(self):
        self.memory.data[0x40:0x48]=b'abcdefgh'
        self.assertEqual(self.engine.read_value(1),'abcdefgh')
        with self.assertRaisesRegex(NativeRuntimeError,'terminator exceeds Length'):
            self.engine.set_freeze(1)
        self.assertFalse(self.engine.frozen)
        self.assertFalse(self.memory.writes)
        self.assertFalse(self.engine.blocked)
    def test_freeze_then_longer_value_replaces_exact_intent(self):
        self.engine.set_freeze(1)
        self.engine.set_value(1,'longer')
        self.assertEqual(self.engine.frozen[1][1],b'longer\0')
        self.memory.data[0x40:0x48]=b'BAD\0NEW!'
        self.engine.poll()
        self.assertEqual(self.memory.read(0x1040,8),b'longer\0!')
    def test_overlap_with_frozen_prefix_refused_before_write(self):
        self.engine.set_freeze(1)
        with self.assertRaisesRegex(NativeRuntimeError,'overlaps'):
            self.engine.set_value(6,'17')
        self.assertFalse(self.memory.writes)
    def test_readonly_and_rwx_refuse_before_write_or_hold(self):
        for protection in (2,0x40,0x104):
            self.memory.protection=protection
            with self.subTest(protection=protection),self.assertRaisesRegex(NativeRuntimeError,'PAGE_READWRITE'):
                self.engine.set_value(1,'x')
        self.assertFalse(self.memory.writes)
        self.assertFalse(self.coordinator.data_holds)
    def test_missing_coordinator_refuses_cleanly(self):
        self.engine.hook_coordinator=None
        with self.assertRaisesRegex(NativeRuntimeError,'data-only coordinator'):
            self.engine.set_value(1,'x')
        self.assertFalse(self.memory.writes)
        self.assertFalse(self.engine.blocked)
    def test_prehold_refusal_can_retry(self):
        self.coordinator.fail=True
        with self.assertRaisesRegex(NativeRuntimeError,'pre-write'):
            self.engine.set_value(1,'x')
        self.assertFalse(self.engine.blocked)
        self.coordinator.fail=False
        self.assertEqual(self.engine.set_value(1,'x'),'x')
    def test_partial_write_compensates_exact_raw_prefix(self):
        before=bytes(self.memory.data)
        self.memory.fail_once=True
        with self.assertRaisesRegex(NativeRuntimeError,'original bytes restored'):
            self.engine.set_value(1,'new')
        self.assertEqual(bytes(self.memory.data),before)
        self.assertFalse(self.engine.blocked)
        self.assertEqual(self.memory.writes[-1],(0x1040,b'old\0'))
    def test_held_cleanup_uncertainty_blocks_followup(self):
        self.coordinator.cleanup_uncertain=True
        with self.assertRaisesRegex(NativeRuntimeError,'resume failure'):
            self.engine.set_value(1,'new')
        self.assertTrue(self.engine.blocked)
        count=len(self.memory.writes)
        with self.assertRaises(NativeRuntimeError):self.engine.set_value(1,'x')
        self.assertEqual(count,len(self.memory.writes))
    def test_expired_held_proof_has_no_target_effect(self):
        self.coordinator.expire=True
        with self.assertRaises(NativeRuntimeError):self.engine.set_value(1,'x')
        self.assertFalse(self.memory.writes)
    def test_invalid_current_prefix_can_be_repaired_without_tail_clear(self):
        self.memory.data[0x40:0x48]=b'\xff\0TAIL!!'
        with self.assertRaises(ValueError):self.engine.read_value(1)
        self.assertEqual(self.engine.set_value(1,'x'),'x')
        self.assertEqual(self.memory.read(0x1040,8),b'x\0TAIL!!')
    def test_canonical_plan_metadata_rejects_forged_length_or_encoding(self):
        for change in ({'size':1},{'encoding':'utf-8'},{'unit_bytes':1}):
            forged=deepcopy(self.plan)
            forged['entries'][1]['value_profile'].update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):compiler_validate(forged)
            with self.assertRaises(NativeRuntimeError):validate_plan(forged)
    def test_controller_close_drops_freeze_without_replaying_values(self):
        self.engine.set_value(1,'new')
        self.engine.set_freeze(1)
        self.assertTrue(self.engine.close())
        self.assertEqual(self.memory.read(0x1040,8),b'new\0TAIL')
        self.assertFalse(self.engine.frozen)
        self.assertFalse(self.engine.desired)

    def test_post_transaction_confirmation_read_failure_blocks_followup(self):
        original=self.engine._write_transaction
        def completed_then_error(*args,**kw):
            original(*args,**kw)
            read=self.memory.read
            def fail_final(address,size):
                if address==0x1040 and size==4:
                    self.memory.read=read
                    raise OSError('Owned final read failed')
                return read(address,size)
            self.memory.read=fail_final
        self.engine._write_transaction=completed_then_error
        with self.assertRaisesRegex(NativeRuntimeError,'final read failed'):
            self.engine.set_value(1,'new')
        self.assertTrue(self.engine.blocked)
        self.assertEqual(self.memory.read(0x1040,8),b'new\0TAIL')
        self.assertTrue(self.engine.store.session.exists())
        count=len(self.memory.writes)
        with self.assertRaises(NativeRuntimeError):self.engine.set_value(1,'x')
        self.assertEqual(count,len(self.memory.writes))

    def test_slow_freeze_snapshot_does_not_publish_a_freeze_intent(self):
        clock=Clock();limits=WorkLimits(.25,1000000,.5,2,10,3)
        read=self.memory.read
        def delayed_read(address,size):
            result=read(address,size)
            if address==0x1040 and size==8:clock.advance(.6)
            return result
        self.memory.read=delayed_read
        with self.assertRaises(WorkBudgetError):
            with work_slice(limits,lambda:None,clock) as budget:
                with budget.dispatch():self.engine.set_freeze(1)
        self.assertFalse(self.engine.frozen)
        self.assertFalse(self.memory.writes)

    def test_slow_freeze_resume_does_not_publish_a_freeze_intent(self):
        clock=Clock();limits=WorkLimits(.25,1000000,.5,2,10,3)
        hold=self.coordinator.hold_data
        @contextmanager
        def delayed_resume(memory,ranges):
            with hold(memory,ranges) as proof:yield proof
            clock.advance(.6)
        self.coordinator.hold_data=delayed_resume
        with self.assertRaises(WorkBudgetError):
            with work_slice(limits,lambda:None,clock) as budget:
                with budget.dispatch():self.engine.set_freeze(1)
        self.assertFalse(self.engine.frozen)
        self.assertFalse(self.memory.writes)

    def test_slow_write_resume_after_effect_blocks_followup(self):
        clock=Clock();limits=WorkLimits(.25,1000000,.5,2,10,3)
        hold=self.coordinator.hold_data
        @contextmanager
        def delayed_resume(memory,ranges):
            with hold(memory,ranges) as proof:yield proof
            clock.advance(.6)
        self.coordinator.hold_data=delayed_resume
        with self.assertRaises(WorkBudgetError):
            with work_slice(limits,lambda:None,clock) as budget:
                with budget.dispatch():self.engine.set_value(1,'new')
        self.assertTrue(self.engine.blocked)
        self.assertTrue(self.engine.store.session.exists())
        self.assertEqual(self.memory.read(0x1040,8),b'new\0TAIL')

    def test_data_only_transaction_refuses_executable_dispatch_race(self):
        original=self.engine._write_transaction
        routes=[]
        def late_exec(*args,**kw):
            self.memory.is_executable=lambda address,size:True
            return original(*args,**kw)
        self.engine._write_transaction=late_exec
        self.engine._write_owned_literal_values=lambda patches:routes.append(patches)
        with self.assertRaisesRegex(NativeRuntimeError,'data-only'):
            self.engine.set_value(1,'new')
        self.assertFalse(routes)
        self.assertFalse(self.memory.writes)

    def test_freeze_count_limit_refuses_enrollment_and_keeps_existing_tick_valid(self):
        with patch('ct2trainer.native.string_runtime.MAX_ITEMS',1):
            self.engine.set_freeze(1)
            holds=len(self.coordinator.data_holds)
            with self.assertRaisesRegex(NativeRuntimeError,'enrollment.*record-count'):
                self.engine.set_freeze(2)
            self.assertEqual(set(self.engine.frozen),{1})
            self.assertEqual(holds,len(self.coordinator.data_holds))
            self.assertFalse(self.engine.blocked)
            self.memory.data[0x40]=ord('M')
            self.engine.poll()
            self.assertFalse(self.engine.blocked,self.engine.error)
            self.assertEqual(self.memory.read(0x1040,4),b'old\0')

    def test_freeze_read_byte_limit_refuses_before_a_new_snapshot(self):
        with patch('ct2trainer.native.string_runtime.MAX_BATCH_BYTES',8):
            self.engine.set_freeze(1)
            holds=len(self.coordinator.data_holds)
            with self.assertRaisesRegex(NativeRuntimeError,'enrollment.*byte'):
                self.engine.set_freeze(2)
            self.assertEqual(set(self.engine.frozen),{1})
            self.assertEqual(holds,len(self.coordinator.data_holds))
            self.engine.poll()
            self.assertFalse(self.engine.blocked,self.engine.error)

    def test_string_dropdown_preserves_padded_and_empty_literal_values(self):
        source=self.table.read_text(encoding='utf-8')
        source=source.replace('<Description>ASCII</Description>',
            '<Description>ASCII</Description><DropDownList ReadOnly="1">  a  :Padded\n:Empty</DropDownList>')
        table=self.root/'dropdown.ct';table.write_text(source,encoding='utf-8')
        plan=compile_table(table,'FixtureTarget.exe')
        entry=next(e for e in plan['entries'] if e['id']==1)
        self.assertTrue(entry['supported'])
        self.assertEqual([choice['value'] for choice in entry['dropdown']['choices']],['  a  ',''])
        from ct2trainer.native.engine import parse_value
        self.assertEqual(parse_value(entry,'  a  '),b'  a  \0')
        self.assertEqual(parse_value(entry,''),b'\0')
        with self.assertRaisesRegex(NativeRuntimeError,'supplied list'):parse_value(entry,'a')

    def test_ambiguous_star_string_dropdown_is_explicitly_blocked(self):
        source=self.table.read_text(encoding='utf-8').replace('<Description>ASCII</Description>',
            '<Description>ASCII</Description><DropDownList ReadOnly="1">*:Star\n:Empty</DropDownList>')
        table=self.root/'star.ct';table.write_text(source,encoding='utf-8')
        plan=compile_table(table,'FixtureTarget.exe')
        entry=next(e for e in plan['entries'] if e['id']==1)
        self.assertFalse(entry['supported'])
        self.assertIn('placeholder/literal',entry['reason'])


if __name__=='__main__':unittest.main()
