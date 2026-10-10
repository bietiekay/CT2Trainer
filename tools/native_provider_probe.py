"""Owned real target: mixed code/data flags, values and scoped Lua lifecycle."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import time
import xml.etree.ElementTree as ET

from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import TrainerEngine, NativeRuntimeError
from ct2trainer.native.lua_host import LuaHostError
from ct2trainer.native.memory import ProcessMemory


PROVIDER = '''[ENABLE]
aobscanmodule(site,NativeHookFixture.exe,8B C1 83 C0 01 90 90 C3)
alloc(newmem,1000,site)
label(flag)
label(ordinary)
label(return)
registersymbol(flag)
newmem:
mov eax,ecx
cmp dword [flag],0
je ordinary
add eax,#100
jmp return
ordinary:
add eax,1
jmp return
flag:
dd 0
site:
jmp newmem
nop 2
return:
[DISABLE]
site:
db 8B C1 83 C0 01 90 90
unregistersymbol(flag)
dealloc(newmem)
'''
BUFFER = '''[ENABLE]
alloc(ownedbuf,1000)
registersymbol(ownedbuf)
ownedbuf:
dd 0
[DISABLE]
unregistersymbol(ownedbuf)
dealloc(ownedbuf)
'''


def probe(target, output):
    target, output = Path(target).resolve(), Path(output).resolve()
    if target.name != 'NativeHookFixture.exe' or output.exists():
        raise ValueError('Use the owned NativeHookFixture and a fresh report path')
    report = {'schema': 'ct2trainer-provider-lua/v1', 'ce_inputs': [], 'checks': [],
              'target_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
              'game_runtime_verified': False, 'saved_exception_contexts_verified': False}
    child = subprocess.Popen([str(target)], stdout=subprocess.PIPE, text=True, creationflags=0x08000000)
    engine, independent = None, None
    try:
        metadata = json.loads(child.stdout.readline())
        table = ET.Element('CheatTable', CheatEngineTableVersion='45')
        rows = ET.SubElement(table, 'CheatEntries')
        for identifier, name, kind, content in (
                (1, 'Owned mixed provider', 'Auto Assembler Script', PROVIDER),
                (2, 'Owned flag toggle', 'Auto Assembler Script', '[ENABLE]\nflag:\ndd 1\n[DISABLE]\nflag:\ndd 0'),
                (3, 'Owned flag value', '4 Bytes', 'flag'),
                (4, 'Out-of-span value', '4 Bytes', 'flag+1')):
            row = ET.SubElement(rows, 'CheatEntry')
            for key, value in (('ID', str(identifier)), ('Description', '"' + name + '"'), ('VariableType', kind),
                               ('AssemblerScript' if kind == 'Auto Assembler Script' else 'Address', content)):
                ET.SubElement(row, key).text = value
        source = output.with_suffix('.ct')
        ET.ElementTree(table).write(source, encoding='utf-8', xml_declaration=True)
        report['table_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
        plan = compile_table(source, 'NativeHookFixture.exe')
        engine = TrainerEngine(plan, state_dir=output.with_suffix('.state'))
        engine.poll()
        assert engine.connected
        independent = ProcessMemory('NativeHookFixture.exe')
        def value(address):
            return struct.unpack('<I', independent.read(address, 4))[0]
        def await_result(expected):
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                if value(metadata['result']) == expected:
                    return
                time.sleep(0.01)
            raise AssertionError('Owned caller result did not become ' + str(expected))
        await_result(4)
        assert engine.toggle(1, True)
        flag = engine.symbols['flag']
        assert engine.memory.is_executable(flag, 4)
        assert any(start <= flag and flag + 4 <= start + size for start, size, _, _ in engine.hooks[1].data_ranges())
        await_result(4)
        report['checks'].append('actual_nasm_mixed_rwx_provider_publishes_exact_literal_permit')
        assert engine.toggle(2, True)
        await_result(103)
        assert engine.hooks[2].entries[0]['data_semantics']
        try:
            engine.toggle(1, False)
            raise AssertionError('Provider was disabled beneath its child')
        except NativeRuntimeError as exc:
            assert 'dependent' in str(exc) or 'consumer' in str(exc)
        assert not engine.blocked
        assert not engine.toggle(2, False)
        await_result(4)
        report['checks'].append('coordinated_child_flag_effect_disable_and_provider_dependency')
        assert engine.set_value(3, '1') == '1'
        await_result(103)
        count = len(engine.retired_hooks)
        assert count and engine.retired_hooks[-1].receipt()['data_commit']
        assert engine.set_freeze(3, True)
        independent.write(flag, bytes(4))
        engine.poll()
        assert not engine.blocked and value(flag) == 1
        await_result(103)
        engine.set_freeze(3, False)
        engine.set_value(3, '0')
        await_result(4)
        report['checks'].append('numeric_rwx_literal_commit_independent_readback_and_coordinated_freeze')
        try:
            engine.set_value(4, '1')
            raise AssertionError('A partial data-span write was admitted')
        except NativeRuntimeError as exc:
            assert 'literal provenance' in str(exc)
        assert value(flag) == 0 and not engine.blocked
        report['checks'].append('shifted_out_of_span_value_refused_without_code_mutation')
        host = engine.open_lua_activation(1)
        ok, receipt = host.execute('ok,receipt=autoAssemble(' + repr(BUFFER) + '); return ok,receipt.token')
        assert ok and isinstance(receipt, str)
        buffer = engine.symbols['ownedbuf']
        assert host.execute('return writeInteger("ownedbuf",17)')
        assert value(buffer) == 17
        host.execute('w=createThread(function() sleep(10); writeInteger("ownedbuf",19) end)')
        host.tick(0)
        host.tick(10)
        assert value(buffer) == 19
        scope = engine.lua_activations[1]
        report['checks'].append('owned_lua_autoassembler_boolean_receipt_raw_undo_and_worker_effect')
        assert not engine.toggle(1, False)
        await_result(4)
        assert host.cancelled and scope.state == 'abandoned'
        assert value(buffer) == 0 and 'ownedbuf' not in engine.symbols
        try:
            host.execute('writeInteger(' + str(buffer) + ',33)')
            raise AssertionError('A retired Lua host wrote target memory')
        except LuaHostError:
            pass
        assert value(buffer) == 0
        report['checks'].append('owner_disable_cancels_callbacks_restores_lua_bytes_and_retires_children')
        child.terminate()
        child.wait(timeout=5)
        engine.poll()
        assert engine.memory is None and not engine.blocked
        assert engine.close()
        reopened = TrainerEngine(plan, state_dir=output.with_suffix('.state'))
        assert reopened.close()
        report['checks'].append('target_exit_finalization_and_same_state_controller_restart')
        report['status'] = 'passed'
    except Exception as exc:
        report.update(status='failed', error=repr(exc))
        raise
    finally:
        if independent:
            independent.close()
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=5)
        if engine and not engine.closed:
            engine.close()
        output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    print(probe(args.target, args.report)['status'])
