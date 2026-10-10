"""Acceptance gate restricted to the independently owned two-record scan CT."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import queue
import struct
import subprocess
import sys
import tempfile
import threading

# Re-pinned 2026-10-07 after the CT2Trainer rename (CT lua helper name,
# schema strings) and the fixture rebuild: MSVC 19.44.35229,
# evidence build/runs/fixture-repin-20261007T115729Z.
PROCESS_NAME = 'NativeScanFixture.exe'
CT_SHA256 = '440a5bf3fdaaae5e2756eed16f8728efd3c65c7c40084e2a0685f2e2c83366db'
SOURCE_SHA256 = {
    1: 'a78b5e66e44d058c3e6c704395ccccfb2cbcca661b4cd1a141a5f1e97b33f69b',
    2: 'fc233329b1d143b7687f10a365d9de00eca5fb5933d4b8de49307f81cb336080'}
TARGET_SHA256 = {
    'x64': 'c9ef4645e2a4153db9beec9921f21a26d05f2bb120b55476a2a0e97f2070481c',
    'x86': '43556035fda3298950ca6fee41512143caa40cd1188cd6d494d127a8e2fc5fe2'}
PRIVATE_PATTERN = bytes.fromhex('44 33 22 11 78 49 9A EB 3C 0D 5E AF F0 C1 12 63 B4 85 D6 27 08 59 AA FB CC 1D 6E BF 80 D1 22 73')
NTH_PATTERN = bytes.fromhex('11 00 00 00 11 32 D7 C8 ED 8E A3 44 79 1A 3F D0')


def validate_fixture_plan(plan):
    from .architecture import plan_architecture
    from .engine import validate_plan
    validate_plan(plan)
    architecture = plan_architecture(plan)['machine']
    if (plan.get('schema') != 2 or plan.get('table_sha256') != CT_SHA256
            or plan.get('process_name') != PROCESS_NAME or plan.get('selected_ids') != [1, 2]
            or 'lua_bootstrap' in plan or [row['id'] for row in plan['entries']] != [1, 2]):
        raise ValueError('Scan gate requires its exact owned CT, architecture and two selected records')
    for row in plan['entries']:
        if (row.get('kind') != 'script' or row.get('supported') is not True
                or row.get('selected') is not True or row.get('parent_id') is not None
                or row.get('dependency_ids') != []):
            raise ValueError('Scan gate requires two independent supported source records')
        key = 'program' if row['id'] == 1 else 'lua_program'
        profile = row.get(key, {})
        if (profile.get('source_sha256') != SOURCE_SHA256[row['id']]
                or profile.get('process_name') != PROCESS_NAME
                or profile.get('bitness') != (64 if architecture == 'x64' else 32)):
            raise ValueError('Scan gate source or architecture differs from the owned fixture')
    return architecture


def _receive(child):
    received = queue.Queue(maxsize=1)
    def get():
        try: received.put(child.stdout.readline(4097))
        except Exception as exc: received.put(exc)
    threading.Thread(target=get, daemon=True, name='owned-scan-metadata').start()
    try:
        value = received.get(timeout=5)
    except queue.Empty as exc:
        raise ValueError('Owned scan target did not publish bounded JSON') from exc
    if isinstance(value, Exception): raise value
    if len(value) > 4096: raise ValueError('Owned scan output exceeds its bound')
    return json.loads(value)


def _command(child, command):
    child.stdin.write(command + '\n')
    child.stdin.flush()
    return _receive(child)


def _metadata(child, architecture):
    value = _receive(child)
    if (type(value) is not dict or set(value) != {'schema', 'pid', 'pointer_bits', 'private', 'nth'}
            or value['schema'] != 'ct2trainer-owned-scan-target/v1'
            or type(value['pid']) is not int or value['pid'] != child.pid
            or type(value['pointer_bits']) is not int
            or value['pointer_bits'] != (64 if architecture == 'x64' else 32)
            or type(value['nth']) is not list or len(value['nth']) != 4):
        raise ValueError('Owned scan target metadata differs from its contract')
    maximum = 0xFFFFFFFF if architecture == 'x86' else 0x7FFFFFFFFFFF
    addresses = [value['private'], *value['nth']]
    if (any(type(address) is not int or not 0 < address <= maximum - 64 for address in addresses)
            or len(set(addresses)) != 5 or value['nth'] != sorted(value['nth'])
            or any(value['nth'][i+1] - value['nth'][i] != 32 for i in range(3))):
        raise ValueError('Owned scan target address metadata is invalid')
    return value


def run_probe(plan, target: str | Path, report: str | Path):
    from .engine import TrainerEngine
    from .memory import ProcessMemory
    target, report = Path(target).resolve(), Path(report).resolve()
    report.parent.mkdir(parents=True, exist_ok=True)
    with report.open('x', encoding='utf-8') as stream:
        stream.write('{"status":"running","schema":"ct2trainer-owned-scan/v1"}\n')
    try:
        architecture = validate_fixture_plan(plan)
        if (target.name != PROCESS_NAME or hashlib.sha256(target.read_bytes()).hexdigest() != TARGET_SHA256[architecture]):
            raise ValueError('Scan gate requires its byte-pinned independently owned target')
    except Exception as exc:
        report.write_text(json.dumps({'schema':'ct2trainer-owned-scan/v1',
            'status':'failed','error':repr(exc),'ce_inputs':[],
            'target_spawned':False,'target_writes':False},indent=2)+'\n',encoding='utf-8')
        raise
    evidence = {'schema':'ct2trainer-owned-scan/v1', 'status':'running',
        'ce_inputs':[], 'game_runtime_verified':False, 'target_architecture':architecture,
        'frozen_runtime':bool(getattr(sys, 'frozen', False)),
        'runtime_executable':str(Path(sys.executable).resolve()),
        'runtime_executable_sha256':hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
        'target_sha256':TARGET_SHA256[architecture], 'table_sha256':CT_SHA256,
        'plan_sha256':hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest(),
        'checks':[], 'targets':[], 'scan_calls':[], 'receipts':[]}
    with report.open('w', encoding='utf-8') as stream:
        stream.write(json.dumps(evidence))
    state = Path(tempfile.mkdtemp(prefix='ct2trainer-owned-scan-'))
    evidence['state_directory'] = str(state)
    child = engine = reader = None
    receipt_paths, ownership_paths = set(), set()
    def note(name): evidence['checks'].append({'check':name, 'passed':True})
    def spawn():
        new_child = subprocess.Popen([str(target)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        try: metadata = _metadata(new_child, architecture)
        except Exception:
            if new_child.poll() is None: new_child.kill()
            new_child.wait(timeout=5)
            raise
        return new_child, metadata
    def connect(metadata):
        nonlocal reader
        engine.poll()
        if not engine.connected: raise AssertionError(engine.error or engine.status)
        reader = ProcessMemory(PROCESS_NAME, pid=child.pid)
        if engine.memory.identity != reader.identity: raise AssertionError('Independent readback target differs')
        if reader.pointer_size * 8 != metadata['pointer_bits']: raise AssertionError('Pointer width differs')
        evidence['targets'].append({'identity':list(reader.identity), 'metadata':metadata})
        ownership_paths.update((engine.store.lock, engine.store.session, engine.store.process_lock))
    def observed_private(metadata, patched):
        expected = struct.pack('<I', 0x55667788 if patched else 0x11223344) + PRIVATE_PATTERN[4:]
        if reader.read(metadata['private'],32) != expected: raise AssertionError('Private scan patch/readback differs')
        if (reader.read(metadata['private']-16,16) != b'\xab'*16
                or reader.read(metadata['private']+32,16) != b'\xab'*16):
            raise AssertionError('Private scan changed a sentinel')
    def captured_metadata():
        for scope in engine.lua_activations.values():
            receipt_paths.add(scope.path)
            evidence['receipts'].append({'path':str(scope.path),
                'sha256':hashlib.sha256(scope.path.read_bytes()).hexdigest()})
    def observed_nth_original(metadata):
        for index in (1,2,3):
            if reader.read(metadata['nth'][index],32) != NTH_PATTERN + bytes([0xe0+index])*16:
                raise AssertionError('Nth pattern or module sentinel differs')
    try:
        child, metadata = spawn()
        engine = TrainerEngine(plan, state_dir=state)
        connect(metadata)
        module = reader.module(PROCESS_NAME)
        if module[0] <= metadata['private'] < sum(module): raise AssertionError('Private pattern is in the image')
        observed_private(metadata, False)
        observed_nth_original(metadata)
        matches = reader.scan_matches(NTH_PATTERN.hex(' '),start=module[0],end=sum(module),max_results=5)
        if matches != metadata['nth'][1:]: raise AssertionError('Original nth module occurrences differ')
        note('exact-architecture-target-and-three-module-patterns-with-private-buffer')
        count = [0]
        scanner = engine.memory.scan_matches
        def counted(*args, **kwargs):
            count[0] += 1
            evidence['scan_calls'].append({'pattern':args[0], 'options':kwargs})
            return scanner(*args, **kwargs)
        engine.memory.scan_matches = counted
        if not engine.toggle(1, True): raise AssertionError('Process record did not confirm ON')
        observed_private(metadata, True)
        if engine.symbols['privateanchor'] != metadata['private']: raise AssertionError('Process capture symbol differs')
        note('compact-process-scan-real-held-publication-and-independent-readback')
        if not engine.toggle(2, True): raise AssertionError('Nth record did not confirm ON')
        if reader.read(metadata['nth'][2],4) != struct.pack('<I',2): raise AssertionError('Nth result did not use occurrence two')
        scope = engine.lua_activations[2]
        if scope.nth_aob_results[0]['address'] != metadata['nth'][2]: raise AssertionError('Nth capture is wrong')
        if engine.desired != {1,2}: raise AssertionError('Confirmed wishes were not saved')
        captured_metadata()
        note('nth-module-source-adapter-confirmed-and-journaled')
        if _command(child, 'add-first')['nth_values'] != [17,17,2,17]: raise AssertionError('Earlier nth pattern did not appear')
        before_disable = count[0]
        if engine.toggle(2, False) or engine.toggle(1, False): raise AssertionError('OFF did not confirm')
        if count[0] != before_disable: raise AssertionError('Disable rescanned a captured address')
        if reader.read(metadata['nth'][2],16) != NTH_PATTERN: raise AssertionError('Nth disable restored wrong bytes')
        observed_private(metadata, False)
        observed_nth_original(metadata)
        if engine.symbols or engine.desired: raise AssertionError('Disabled records retain live symbols/wishes')
        note('earlier-new-match-does-not-rebind-disable-and-both-scopes-restore-exactly')
        if not engine.toggle(1,True) or not engine.toggle(2,True): raise AssertionError('Fresh ON failed')
        if reader.read(metadata['nth'][1],4) != struct.pack('<I',2): raise AssertionError('Fresh activation did not select new nth occurrence')
        observed_private(metadata, True)
        captured_metadata()
        note('fresh-reactivation-rescans-and-saves-current-occurrence')
        identity = reader.identity
        reader.close(); reader = None
        child.stdin.write('quit\n'); child.stdin.flush()
        if child.wait(timeout=5) != 0: raise AssertionError('First own target exit failed')
        child = None
        engine.poll()
        if engine.connected or engine.desired != {1,2}: raise AssertionError('Target exit changed confirmed wishes')
        child, metadata = spawn()
        connect(metadata)
        if reader.identity == identity: raise AssertionError('Target restart reused an old identity')
        observed_private(metadata, True)
        if reader.read(metadata['nth'][2],4) != struct.pack('<I',2): raise AssertionError('Saved nth reapply used old address')
        captured_metadata()
        note('target-restart-reapplies-confirmed-wishes-to-fresh-captured-addresses')
        if not engine.close(): raise AssertionError('Controller close did not confirm exact cleanup')
        engine = None
        observed_private(metadata, False)
        observed_nth_original(metadata)
        reader.close(); reader = None
        engine = TrainerEngine(plan, state_dir=state)
        connect(metadata)
        observed_private(metadata, True)
        if reader.read(metadata['nth'][2],4) != struct.pack('<I',2): raise AssertionError('Controller restart failed nth reapply')
        captured_metadata()
        note('controller-restart-restores-saved-confirmed-records')
        if engine.toggle(2,False) or engine.toggle(1,False): raise AssertionError('Final OFF failed')
        observed_private(metadata, False)
        observed_nth_original(metadata)
        evidence['debugger'] = engine.hook_coordinator.last_observation
        if not evidence['debugger'].get('thread_contexts'): raise AssertionError('No real held-debugger evidence')
        if not engine.close(): raise AssertionError('Final close did not release ownership')
        engine = None
        if any(path is not None and path.exists() for path in ownership_paths):
            raise AssertionError('Normal final close retained an owned state/session marker')
        from .lua_activation import finalized_receipt
        evidence['terminal_receipts'] = []
        for path in sorted(receipt_paths):
            raw = path.read_bytes()
            receipt = json.loads(raw)
            if not finalized_receipt(receipt, plan): raise AssertionError('Lua scan receipt is not exact and terminal')
            evidence['terminal_receipts'].append({'path':str(path),'state':receipt['state'],
                'sha256':hashlib.sha256(raw).hexdigest()})
        evidence['owned_markers_absent'] = True
        reader.close(); reader = None
        child.stdin.write('quit\n'); child.stdin.flush()
        if child.wait(timeout=5) != 0: raise AssertionError('Final own target exit failed')
        child = None
        note('final-off-and-normal-target-cleanup')
        evidence['status'] = 'passed'
        return evidence
    except Exception as exc:
        evidence['status'] = 'failed'
        evidence['error'] = repr(exc)
        raise
    finally:
        if engine is not None:
            try:
                if not engine.close(): evidence['cleanup_error'] = engine.error or 'Unconfirmed cleanup; owned journals retained'
            except Exception as exc: evidence['cleanup_error'] = repr(exc)
        if reader is not None: reader.close()
        if child is not None and child.poll() is None:
            child.kill(); child.wait(timeout=5)
        report.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8')
