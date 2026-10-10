"""Run only the owned cooperative executable-hook fixture; retain evidence."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import time

from ct2trainer.native.assembler import NasmAssembler
from ct2trainer.native.hooks import HookManager, HookError
from ct2trainer.native.memory import ProcessMemory

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests/windows/hook_fixture'))
from coordinator import OwnedFixtureCoordinator


def probe(target: Path, report_path: Path):
    target=target.resolve()
    report_path=report_path.resolve()
    report_path.parent.mkdir(parents=True,exist_ok=True)
    if report_path.exists(): raise FileExistsError(report_path)
    source=ROOT/'tests/windows/hook_fixture/hook_target.c'
    digest=lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    report={'schema':'ct2trainer-hook-fixture/v1','target_sha256':digest(target),
            'fixture_source_sha256':digest(source),'ce_inputs':[], 'checks':[],
            'game_runtime_verified':False,'coordinator':'owned-cooperative-safe-point'}
    child=subprocess.Popen([str(target)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                           text=True,creationflags=0x08000000)
    memory=None
    manager=None
    try:
        metadata=json.loads(child.stdout.readline())
        if metadata['pid']!=child.pid: raise RuntimeError('Fixture PID differs from launched child')
        memory=ProcessMemory('NativeHookFixture.exe',child.pid)
        def result(): return struct.unpack('<i',memory.read(metadata['result'],4))[0]
        def await_result(expected):
            deadline=time.monotonic()+2
            while time.monotonic()<deadline:
                if result()==expected: return
                time.sleep(0.02)
            raise AssertionError(f'Expected fixture result {expected}, observed {result()}')
        await_result(4)
        report['checks'].append('unmodified_function_returns_4')
        original=memory.read(metadata['entry'],7)
        assert original==bytes.fromhex('8bc183c0019090')
        manager=HookManager(memory,report_path.with_suffix('.journal.json'),
                            OwnedFixtureCoordinator(target,report['target_sha256']))
        cave=manager.allocate('newmem',4096,near=metadata['entry'])
        assembler=NasmAssembler()
        code=assembler.assemble(f'bits 64\norg {cave}\nmov eax,ecx\nadd eax,100\njmp {metadata["entry"]+7}\n')
        entry=assembler.assemble(f'bits 64\norg {metadata["entry"]}\njmp near {cave}\nnop\nnop\n')
        assert len(entry)==7
        manager.stage([
            {'address':cave,'bytes':code.hex(),'original':memory.read(cave,len(code)).hex(),
             'is_allocation':True,'executable':True,'requires_coordinator':False},
            {'address':metadata['entry'],'bytes':entry.hex(),'original':original.hex(),
             'is_allocation':False,'executable':True,'requires_coordinator':True}],{'newmem':cave})
        report['checks'].append('near_allocation_nasm_code_staged_rx_and_verified')
        await_result(4)
        manager.publish()
        await_result(103)
        report['checks'].append('published_hook_returns_103')
        try:
            HookManager(memory,manager.path,manager.coordinator)
            raise AssertionError('A competing journal was admitted')
        except HookError:
            report['checks'].append('competing_journal_rejected')
        manager.disable()
        await_result(4)
        assert memory.read(metadata['entry'],7)==original
        report['checks'].append('disable_restores_entry_and_function_result')
        assert memory.read(cave,len(code))==code
        report['checks'].append('retired_executable_allocation_retained')
        report['target_identity']=list(memory.identity)
        report['allocation']=manager.allocation_map()
        child.terminate(); child.wait(timeout=5)
        manager.finish_after_exit()
        report['checks'].append('receipt_finalized_only_after_target_exit')
        report['status']='passed'
    except Exception as exc:
        report['status']='failed'; report['error']=repr(exc)
        raise
    finally:
        if child.poll() is None:
            child.terminate(); child.wait(timeout=5)
        if memory: memory.close()
        report_path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report


if __name__=='__main__':
    cli=argparse.ArgumentParser()
    cli.add_argument('--target',type=Path,required=True)
    cli.add_argument('--report',type=Path,required=True)
    args=cli.parse_args()
    print(probe(args.target,args.report)['status'])
