"""Verify CT -> native compiler -> engine -> hook, plus real Lua host adapters."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import TrainerEngine

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests/windows/hook_fixture'))
from coordinator import OwnedFixtureCoordinator


def probe(target, report_path):
    target,report_path=Path(target).resolve(),Path(report_path).resolve()
    if report_path.exists(): raise FileExistsError(report_path)
    report={'schema':'ct2trainer-engine-hook-lua/v1','ce_inputs':[],
            'checks':[],'target_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
            'game_runtime_verified':False}
    child=subprocess.Popen([str(target)],stdout=subprocess.PIPE,text=True,creationflags=0x08000000)
    engine=None
    try:
        metadata=json.loads(child.stdout.readline())
        source=ROOT/'tests/windows/hook_fixture/hook.ct'
        table=ET.parse(source)
        node=ET.SubElement(table.getroot().find('CheatEntries'),'CheatEntry')
        for name,text in [('ID','2'),('Description','"Owned fixture result"'),('VariableType','4 Bytes'),('Address',f'{metadata["result"]:X}')]:
            ET.SubElement(node,name).text=text
        dynamic=report_path.with_suffix('.ct')
        table.write(dynamic,encoding='utf-8',xml_declaration=True)
        plan=compile_table(dynamic,'NativeHookFixture.exe')
        assert plan['counts']['actionable']==2 and 'program' in plan['entries'][0]
        coordinator=OwnedFixtureCoordinator(target,report['target_sha256'])
        engine=TrainerEngine(plan,state_dir=report_path.with_suffix('.state'),hook_coordinator=coordinator)
        engine.poll()
        assert engine.connected
        def observed(): return struct.unpack('<I',engine.memory.read(metadata['result'],4))[0]
        def await_result(expected):
            deadline=time.monotonic()+2
            while time.monotonic()<deadline:
                if observed()==expected: return
                time.sleep(0.02)
            raise AssertionError(f'Expected {expected}, observed {observed()}')
        await_result(4)
        assert engine.toggle(1,True)
        await_result(103)
        assert engine.desired=={1}
        report['checks'].append('ct_compiler_engine_nasm_hook_effect_confirmed_and_saved')
        host=engine.open_lua_session()
        assert host.execute('return getAddressList().getMemoryRecordByID(1).Active') is True
        with coordinator.hold(engine.memory,[(metadata['result'],4)]):
            engine.memory.write(metadata['result'],struct.pack('<I',1234))
            assert host.execute('return getAddressList().getMemoryRecordByID(2).Value')=='1234'
            assert host.execute('local r=getAddressList().getMemoryRecordByID(2); r.Value="4321"; return r.Value')=='4321'
            assert observed()==4321
            engine.memory.write(metadata['result'],struct.pack('<I',103))
        report['checks'].append('upstream_lua53_memoryrecord_write_uses_engine_and_independent_readback')
        assert host.execute('return getModuleSize("NativeHookFixture.exe")')>0
        report['checks'].append('lua53_held_target_module_and_active_record_api')
        assert not engine.toggle(1,False)
        await_result(4)
        assert engine.desired==set()
        report['checks'].append('ct_disable_restores_effect_and_clears_saved_switch')
        host.cancel()
        report['checks'].append('lua_activation_cancelled_before_target_exit')
        child.terminate(); child.wait(timeout=5)
        engine.poll()
        assert engine.memory is None and not engine.blocked
        report['checks'].append('target_exit_finalizes_retained_receipts')
        assert engine.close()
        report['checks'].append('controller_closes_and_releases_state_ownership')
        report['status']='passed'
    except Exception as exc:
        report['status']='failed';report['error']=repr(exc)
        raise
    finally:
        if child.poll() is None: child.terminate();child.wait(timeout=5)
        if engine and not engine.closed: engine.close()
        report_path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--target',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    print(probe(args.target,args.report)['status'])
