"""Owned memory model: actual String paths consume a live N11 RW provider."""
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
from test_native_global_engine import Memory as BaseMemory, source
from test_native_value_runtime import DataCoordinator
from ct2trainer.native.compiler import compile_table,validate_plan
from ct2trainer.native.engine import TrainerEngine,NativeRuntimeError
from ct2trainer.native.address_expression import AddressExpressionError

class Memory(BaseMemory):
    def _query(self,address):
        result=super()._query(address)
        result.Type=0x20000
        return result

class GlobalStringInterop(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.memory=Memory();self.coordinator=DataCoordinator()
        owned=source().replace('globalalloc(shared,4)','globalalloc(shared,8)').replace('dd #100','db 6F 6C 64 00 54 41 49 4C')
        xml=ET.Element('CheatTable',CheatEngineTableVersion='45');entries=ET.SubElement(xml,'CheatEntries')
        rows=({'ID':'1','Description':'Own global','VariableType':'Auto Assembler Script','AssemblerScript':owned},
              {'ID':'2','Description':'Own String','VariableType':'String','Length':'8','ZeroTerminate':'1','Address':'shared','DropDownList':' xy :padded\n:empty'},
              {'ID':'3','Description':'Own adjacent byte','VariableType':'Byte','Address':'shared+1'})
        for row in rows:
            entry=ET.SubElement(entries,'CheatEntry')
            for name,value in row.items():ET.SubElement(entry,name).text=value
        ct=self.root/'own.ct';ct.write_bytes(ET.tostring(xml,encoding='utf-8',xml_declaration=True))
        self.plan=compile_table(ct,'Owned.exe');validate_plan(self.plan)
        self.engine=TrainerEngine(self.plan,self.root/'state',lambda _:self.memory,self.root/'shared',hook_coordinator=self.coordinator)
        self.engine.poll();self.engine.toggle(1,True);self.base=self.engine.symbols['shared']
    def test_literal_dropdown_and_held_prefix_preserve_pool_tail(self):
        self.assertEqual([x['value'] for x in self.plan['entries'][1]['dropdown']['choices']],[' xy ',''])
        self.assertEqual(self.plan['entries'][1]['dependency_ids'],[1])
        self.assertEqual(self.engine.read_value(2),'old')
        self.assertEqual(self.engine.set_value(2,' xy '),' xy ')
        self.assertEqual(self.memory.read(self.base,8),b' xy \0AIL')
        self.assertTrue(self.coordinator.data_holds)
        self.assertFalse(self.engine.blocked,self.engine.error)
    def test_string_freeze_blocks_provider_and_neighbor_then_keeps_fresh_tail(self):
        self.engine.set_value(2,'ab');self.engine.set_freeze(2,True)
        with self.assertRaisesRegex(NativeRuntimeError,'dependent entries first'):self.engine.toggle(1,False)
        with self.assertRaisesRegex(NativeRuntimeError,'overlaps'):self.engine.set_value(3,'1')
        self.memory.write(self.base,b'qq\0FRESH')
        self.engine.poll()
        self.assertEqual(self.memory.read(self.base,8),b'ab\0FRESH')
        self.assertTrue(self.engine._frozen_matches(2,self.base,self.engine.frozen[2][1]))
        self.engine.set_freeze(2,False);self.engine.toggle(1,False)
        # WP-14 (C1): the staged gate refuses before symbol resolution.
        with self.assertRaisesRegex(NativeRuntimeError,'requires active provider'):self.engine.read_value(2)
        self.assertEqual(self.memory.read(self.base,8),b'ab\0FRESH')
        self.assertEqual(self.memory.releases,[])
        with self.assertRaisesRegex(NativeRuntimeError,'Changed global reinitialization'):self.engine.toggle(1,True)
    def test_exposed_pool_live_close_keeps_quarantine_after_string_change(self):
        self.engine.set_value(2,'ok')
        self.assertFalse(self.engine.close())
        self.assertTrue(self.engine.closed)
        self.assertTrue((self.root/'state/state.lock').exists())
        self.assertTrue((self.root/'state/hooks/global-pool.json').exists())
        self.assertEqual(self.memory.releases,[])

if __name__=='__main__':unittest.main()
