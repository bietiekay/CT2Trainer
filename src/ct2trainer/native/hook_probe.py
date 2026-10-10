"""Source/frozen integration gate for the byte-pinned owned hook trainer CT."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import time


# Re-pinned 2026-10-02 after the CRLF->LF fixture normalization (a7991d0): the
# old pin cb951dcb... is exactly the CRLF byte variant of this LF file, and the
# 0.7 HookTrainer plan differs from the fresh plan only in table_sha256 and the
# derived trainer_id (record contents byte-identical).
HOOK_CT_SHA256='41f98a015e72244e55e82cf7c2e09c26e87330f6ce800557a7362b409d1eff56'


def run_probe(plan: dict,target: str|Path,report: str|Path) -> dict:
    from .engine import TrainerEngine
    from .memory import ProcessMemory
    target,report=Path(target).resolve(),Path(report).resolve()
    if (plan.get('table_sha256')!=HOOK_CT_SHA256 or target.name!='NativeHookFixture.exe'
            or plan.get('process_name')!=target.name or report.exists()):
        raise ValueError('Hook gate requires its pinned owned CT, NativeHookFixture.exe and a new report path')
    evidence={'schema':'ct2trainer-frozen-hook/v1','ce_inputs':[],
              'frozen_runtime':bool(getattr(sys,'frozen',False)),
              'runtime_executable':str(Path(sys.executable).resolve()),
              'runtime_executable_sha256':hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
              'target_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
              'table_sha256':HOOK_CT_SHA256,'checks':[], 'game_unverified':True}
    child=subprocess.Popen([str(target)],stdout=subprocess.PIPE,text=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)
    engine=reader=None
    state=Path(tempfile.mkdtemp(prefix='ct2trainer-hook-'))
    def note(check): evidence['checks'].append(check)
    try:
        metadata=json.loads(child.stdout.readline())
        if metadata['pid']!=child.pid: raise ValueError('Owned hook fixture PID mismatch')
        engine=TrainerEngine(plan,state_dir=state)
        engine.poll()
        if not engine.connected: raise AssertionError(engine.error or engine.status)
        reader=ProcessMemory(target.name,pid=child.pid)
        entry=metadata['entry']
        if reader.read(entry,8)!=bytes.fromhex('8bc183c0019090c3'):
            raise ValueError('Owned fixture entry bytes differ')
        def observed(): return struct.unpack('<I',reader.read(metadata['result'],4))[0]
        def await_result(value):
            deadline=time.monotonic()+2
            while time.monotonic()<deadline:
                if observed()==value: return
                time.sleep(.01)
            raise AssertionError(f'Fixture result {observed()}, expected {value}')
        await_result(4)
        if engine._value_address(engine.entries[2])!=metadata['result']:
            raise AssertionError('Remote fixture export resolves to the wrong address')
        note('remote-export-value-address-and-original-effect')
        assert engine.toggle(1,True)
        await_result(103)
        assert engine.desired=={1}
        note('embedded-ct-nasm-iced-debugger-hook-confirmed-and-saved')
        observation=engine.hook_coordinator.last_observation
        if not observation.get('thread_contexts'): raise AssertionError('No real debugger context evidence')
        evidence['debugger']=observation
        host=engine.open_lua_session()
        assert host.execute('return _VERSION')=='Lua 5.3'
        assert host.execute('return getAddressList().getMemoryRecordByID(1).Active') is True
        with engine.hook_coordinator.hold(engine.memory,[(entry,7)]):
            engine.memory.write(metadata['result'],struct.pack('<I',1234))
            assert host.execute('return getAddressList().getMemoryRecordByID(2).Value')=='1234'
            host.execute('getAddressList().getMemoryRecordByID(2).Value="4321"')
            assert observed()==4321
            engine.memory.write(metadata['result'],struct.pack('<I',103))
        note('embedded-upstream-lua53-record-write-independent-readback')
        assert not engine.toggle(1,False)
        await_result(4)
        assert not engine.desired and reader.read(entry,7)==bytes.fromhex('8bc183c0019090')
        note('exact-disable-effect-and-saved-wish-cleared')
        receipt=engine.retired_hooks[0].receipt()
        assert receipt['state']=='retired'
        for block in receipt['blocks']:
            assert reader.read(block['address'],len(bytes.fromhex(block['bytes'])))==bytes.fromhex(block['bytes'])
        note('retired-cave-remains-readable-before-target-exit')
        child.terminate(); child.wait(timeout=5)
        engine.poll()
        assert engine.memory is None and not engine.blocked
        note('exact-target-exit-finalizes-retained-code')
        assert engine.close()
        note('controller-state-ownership-released')
        evidence['status']='passed'
    except Exception as exc:
        evidence.update(status='failed',error=repr(exc))
        raise
    finally:
        if child.poll() is None: child.terminate();child.wait(timeout=5)
        if engine and not engine.closed: engine.close()
        if reader: reader.close()
        report.parent.mkdir(parents=True,exist_ok=True)
        report.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8')
    return evidence
