"""Own Windows CT Lua+AA record, confirmed effects and lifecycle, without CE."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import time
import xml.etree.ElementTree as ET

from native_provider_probe import PROVIDER, BUFFER
from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import TrainerEngine, NativeRuntimeError
from ct2trainer.native.lua_host import LuaHostError
from ct2trainer.native.memory import ProcessMemory


SOURCE = PROVIDER.replace('[ENABLE]', '''{$lua}
function helper() return 17 end
{$asm}
[ENABLE]
{$lua}
assert(memrec.ID==1 and memrec.Active==false)
if not syntaxcheck then
  ownedAA=[[''' + BUFFER + ''']]
  ok,receipt=autoAssemble(ownedAA)
  assert(ok and receipt)
  writeInteger("ownedbuf",helper())
  w=createThread(function(t) sleep(10); writeInteger("ownedbuf",helper()+2); sleep(1000); writeInteger("ownedbuf",99) end)
end
{$asm}''').replace('[DISABLE]\nsite:', '''[DISABLE]
{$lua}
assert(memrec.ID==1 and memrec.Active==true)
w.terminate()
assert(autoAssemble(ownedAA,false,receipt))
{$asm}
site:''')


def probe(target, report_path):
    target, output = Path(target).resolve(), Path(report_path).resolve()
    if target.name != 'NativeHookFixture.exe' or output.exists():
        raise ValueError('Use the owned target and a fresh evidence report')
    result = {'schema':'ct2trainer-automatic-lua/v1', 'ce_inputs':[], 'checks':[],
              'target_sha256':hashlib.sha256(target.read_bytes()).hexdigest(), 'game_runtime_verified':False}
    child = subprocess.Popen([str(target)], stdout=subprocess.PIPE, text=True, creationflags=0x08000000)
    engine, reader = None, None
    try:
        meta = json.loads(child.stdout.readline())
        table = ET.Element('CheatTable', CheatEngineTableVersion='45')
        rows = ET.SubElement(table,'CheatEntries')
        for identifier, label, source in ((1,'Own automatic Lua AA',SOURCE),
                (2,'Own literal flag','[ENABLE]\nflag:\ndd 1\n[DISABLE]\nflag:\ndd 0')):
            row = ET.SubElement(rows,'CheatEntry')
            for key, value in (('ID',str(identifier)),('Description',label),
                               ('VariableType','Auto Assembler Script'),('AssemblerScript',source)):
                ET.SubElement(row,key).text = value
        table_path = output.with_suffix('.ct')
        ET.ElementTree(table).write(table_path,encoding='utf-8',xml_declaration=True)
        plan = compile_table(table_path,'NativeHookFixture.exe')
        assert plan['counts']['blocked']==0 and 'lua_program' in plan['entries'][0]
        result['table_sha256']=plan['table_sha256']
        engine = TrainerEngine(plan,state_dir=output.with_suffix('.state'))
        engine.poll()
        assert engine.connected,engine.status
        reader = ProcessMemory('NativeHookFixture.exe')
        def integer(address):
            return struct.unpack('<I',reader.read(address,4))[0]
        def wait_result(expected):
            deadline=time.monotonic()+3
            while time.monotonic()<deadline:
                if integer(meta['result'])==expected:return
                time.sleep(.01)
            raise AssertionError('Own caller did not return '+str(expected))
        wait_result(4)
        assert engine.toggle(1,True)
        scope=engine.lua_activations[1]
        buffer=engine.symbols['ownedbuf']
        assert integer(buffer)==17 and 1 in engine.desired and len(scope.assemblies)==2
        scope.host.tick(0)
        scope.host.tick(10)
        assert integer(buffer)==19
        result['checks'].append('ct_compiler_to_automatic_lua_receipts_owned_write_and_cooperative_worker')
        assert engine.toggle(2,True)
        wait_result(103)
        try:
            engine.toggle(1,False)
            raise AssertionError('Provider retired under its active consumer')
        except NativeRuntimeError as exc:
            assert 'dependent' in str(exc) or 'consumer' in str(exc)
        assert not engine.blocked and not scope.host.cancelled
        result['checks'].append('scoped_code_data_provider_and_dependency_refusal_before_cancellation')
        assert not engine.toggle(2,False)
        wait_result(4)
        assert not engine.toggle(1,False)
        assert scope.host.cancelled and scope.state=='abandoned'
        assert integer(buffer)==0 and engine.symbols=={} and not engine.desired
        wait_result(4)
        assert not engine.lua_sessions
        try:
            scope.host.execute('writeInteger('+str(buffer)+',33)')
            raise AssertionError('Cancelled host wrote target')
        except LuaHostError:pass
        result['checks'].append('disable_lua_owned_receipt_main_inverse_raw_undo_and_callback_cancellation')
        # Re-enable remains a fresh scope; only confirmed ON survives target exit.
        assert engine.toggle(1,True)
        second=engine.lua_activations[1]
        assert second.host is not scope.host
        child.terminate();child.wait(timeout=5)
        engine.poll()
        assert second.state=='target-exited' and second.host.cancelled and engine.memory is None
        assert 1 in engine.desired and not engine.blocked
        assert engine.close()
        reopened=TrainerEngine(plan,state_dir=output.with_suffix('.state'))
        assert reopened.desired=={1} and reopened.close()
        result['checks'].append('fresh_activation_exact_target_exit_finalization_and_confirmed_saved_state_restart')
        result['status']='passed'
    except Exception as exc:
        result.update(status='failed',error=repr(exc))
        raise
    finally:
        if reader:reader.close()
        if child.poll() is None:
            child.terminate();child.wait(timeout=5)
        if engine and not engine.closed:engine.close()
        output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--target',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    print(probe(args.target,args.report)['status'])
