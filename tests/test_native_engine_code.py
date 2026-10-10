"""Executable literal patches share durable hook coordination, never data writes."""
from contextlib import contextmanager
from pathlib import Path
import tempfile
import unittest

from test_native_engine import FakeMemory
from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import TrainerEngine,NativeRuntimeError
from ct2trainer.native.hooks import QuiescenceProof


class CodeMemory(FakeMemory):
    @property
    def identity(self): return self.pid,self.creation_time
    def is_executable(self,address,size): return self.base+96<=address<self.base+112


class Coordinator:
    def __init__(self): self.holds=[]
    @contextmanager
    def hold(self,memory,ranges):
        self.holds.append(tuple(ranges))
        yield QuiescenceProof(memory.identity,tuple(ranges),'owned-unit-safe-point',lambda: True)


class LiteralCodeTests(unittest.TestCase):
    def test_code_patch_coordination_disable_and_numeric_refusal(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            table=root/'owned.ct'
            table.write_text('''<CheatTable CheatEngineTableVersion="45"><CheatEntries>
<CheatEntry><ID>1</ID><Description>"Owned literal code"</Description><VariableType>Auto Assembler Script</VariableType><AssemblerScript>[ENABLE]
assert(FixtureTarget.exe+60,8B C1 83 C0 01 90 90)
FixtureTarget.exe+60:
db B8 65 00 00 00 90 90
[DISABLE]
assert(FixtureTarget.exe+60,B8 65 00 00 00 90 90)
FixtureTarget.exe+60:
db 8B C1 83 C0 01 90 90
</AssemblerScript></CheatEntry>
<CheatEntry><ID>2</ID><Description>"Executable value refused"</Description><VariableType>4 Bytes</VariableType><Address>FixtureTarget.exe+60</Address></CheatEntry>
</CheatEntries></CheatTable>''',encoding='utf-8')
            plan=compile_table(table,'FixtureTarget.exe')
            memory=CodeMemory(); memory.data[96:104]=bytes.fromhex('8bc183c0019090c3')
            first=TrainerEngine(plan,state_dir=root/'denied',process_lock_dir=root/'shared',
                                memory_factory=lambda name:memory,hook_coordinator=None)
            first.poll()
            with self.assertRaisesRegex(NativeRuntimeError,'coordinator'): first.toggle(1,True)
            self.assertFalse(memory.writes); self.assertTrue(first.close())
            memory.closed=False
            coordinator=Coordinator()
            engine=TrainerEngine(plan,state_dir=root/'allowed',process_lock_dir=root/'shared',
                                 memory_factory=lambda name:memory,hook_coordinator=coordinator)
            engine.poll()
            for operation in (lambda:engine.set_value(2,'1'),lambda:engine.set_freeze(2,True)):
                with self.assertRaisesRegex(NativeRuntimeError,'executable pages'): operation()
            self.assertFalse(memory.writes)
            self.assertTrue(engine.toggle(1,True))
            self.assertEqual(memory.read(memory.base+96,7),bytes.fromhex('b8650000009090'))
            self.assertEqual(len(coordinator.holds),1)
            self.assertEqual(engine.hooks[1].receipt()['state'],'enabled')
            self.assertFalse(engine.toggle(1,False))
            self.assertEqual(memory.read(memory.base+96,7),bytes.fromhex('8bc183c0019090'))
            self.assertEqual(len(coordinator.holds),2)
            memory.alive=False;engine.poll();self.assertTrue(engine.close())
