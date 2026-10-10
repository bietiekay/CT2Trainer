"""Source/frozen acceptance gate for one independently owned Lua/AA fixture.

This is deliberately not a headless API for arbitrary trainer plans or games.
The controller, source profiles, target image, and spawned PID are all pinned.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import queue
import struct
import subprocess
import sys
import tempfile
import threading
import time


LUA_CT_SHA256 = '6779cb6ce8f7e03cc4aacf7fb18d6677ecb7e2e520e6ff64335f063c4c74654f'
TARGET_SHA256 = '948f3a77791761a9702757efad7fd2fb6708c0990f2e16392760efda3a648d1a'
LUA_SOURCE_SHA256 = '43913fc94f6cd753cbdc0a4a314b9f20bee229f82f5ea764320487332c24c84f'
STATIC_SOURCE_SHA256 = '03581aeaf748fabeb7687d9be00f9ce4e67c058441c2119f05748e47cf0655ff'
FLAG_SOURCE_SHA256 = '869d57807e8107bc65bbb8d22bf4df6bcd7bc13684280eecc0d34c091177eefa'
PROCESS_NAME = 'NativeHookFixture.exe'


def validate_fixture_plan(plan: dict) -> None:
    """Rebuild source metadata, then admit only the two exact owned profiles."""
    from .engine import validate_plan
    validate_plan(plan)
    if (plan.get('table_sha256') != LUA_CT_SHA256 or plan.get('process_name') != PROCESS_NAME
            or plan.get('selected_ids') != [1, 2] or 'lua_bootstrap' in plan
            or [row['id'] for row in plan['entries']] != [1, 2]):
        raise ValueError('Lua fixture gate requires its pinned two-record owned CT')
    provider, consumer = plan['entries']
    if any(row.get('kind') != 'script' or row.get('supported') is not True
           or row.get('selected') is not True or row.get('parent_id') is not None
           or row.get('enable') != [] or row.get('disable') != []
           for row in (provider, consumer)):
        raise ValueError('Lua fixture records differ from the owned source plan')
    lua = provider.get('lua_program', {})
    static = lua.get('static_program') or {}
    flag = consumer.get('program', {})
    if (lua.get('schema') != 'ct2trainer-lua-program/v1'
            or lua.get('source_sha256') != LUA_SOURCE_SHA256
            or static.get('schema') != 'ct2trainer-aa-program/v1'
            or static.get('source_sha256') != STATIC_SOURCE_SHA256
            or flag.get('schema') != 'ct2trainer-aa-program/v1'
            or flag.get('source_sha256') != FLAG_SOURCE_SHA256
            or any(profile.get('bitness') != 64 or profile.get('process_name') != PROCESS_NAME
                   for profile in (lua, static, flag))
            or provider.get('dependency_ids') != [] or provider.get('provides') != ['flag']
            or consumer.get('dependency_ids') != [1] or consumer.get('requires') != ['flag']):
        raise ValueError('Lua fixture gate requires exact owned Lua and AA source profiles')


def _sha256_file(path: Path, limit: int = 256 * 1024 * 1024) -> str:
    digest, size = hashlib.sha256(), 0
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            size += len(block)
            if size > limit:
                raise ValueError('Fixture evidence input exceeds its byte bound')
            digest.update(block)
    return digest.hexdigest()


def _metadata(child) -> dict:
    received = queue.Queue(maxsize=1)
    def read():
        try:
            received.put(child.stdout.readline(4097))
        except Exception as exc:
            received.put(exc)
    threading.Thread(target=read, daemon=True, name='owned-lua-fixture-metadata').start()
    try:
        line = received.get(timeout=5)
    except queue.Empty as exc:
        raise ValueError('Owned Lua fixture did not publish bounded metadata') from exc
    if isinstance(line, Exception):
        raise line
    if len(line) > 4096:
        raise ValueError('Owned Lua fixture metadata exceeds its bound')
    metadata = json.loads(line)
    if (not isinstance(metadata, dict) or set(metadata) != {'pid', 'entry', 'result', 'calls'}
            or any(type(value) is not int or not 0 < value <= 0x7FFFFFFFFFFF
                   for value in metadata.values()) or metadata['pid'] != child.pid):
        raise ValueError('Owned Lua fixture metadata/PID mismatch')
    return metadata


def run_probe(plan: dict, target: str | Path, report: str | Path) -> dict:
    """Verify live owned effects and terminal receipts; retain fresh evidence."""
    from .engine import TrainerEngine, NativeRuntimeError
    from .lua_host import LuaHostError
    from .memory import ProcessMemory

    target, report = Path(target).resolve(), Path(report).resolve()
    report.parent.mkdir(parents=True, exist_ok=True)
    # Reserve the new report before validation or launch. Failures below are
    # recorded too, and an existing evidence file is never overwritten.
    with report.open('xb') as stream:
        evidence = {'schema': 'ct2trainer-frozen-lua-record/v1', 'ce_inputs': [],
                    'status': 'failed', 'checks': [], 'game_runtime_verified': False,
                    'frozen_runtime': bool(getattr(sys, 'frozen', False)),
                    'runtime_executable': str(Path(sys.executable).resolve()),
                    'table_sha256': plan.get('table_sha256') if isinstance(plan, dict) else None,
                    'state_directory': None, 'targets': [], 'receipts': []}
        engine = reader = child = None
        failure, cleanup_errors = None, []
        try:
            validate_fixture_plan(plan)
            if target.name != PROCESS_NAME:
                raise ValueError('Lua fixture gate requires NativeHookFixture.exe')
            evidence['target_sha256'] = _sha256_file(target, 16 * 1024 * 1024)
            if evidence['target_sha256'] != TARGET_SHA256:
                raise ValueError('Owned Lua fixture target binary hash differs')
            if sys.platform != 'win32':
                raise ValueError('The owned Lua fixture gate requires Windows')
            evidence['runtime_executable_sha256'] = _sha256_file(Path(sys.executable))
            evidence['lua_source_sha256'] = LUA_SOURCE_SHA256
            evidence['flag_source_sha256'] = FLAG_SOURCE_SHA256
            state = Path(tempfile.mkdtemp(prefix='ct2trainer-lua-record-'))
            evidence['state_directory'] = str(state)

            def spawn():
                return subprocess.Popen([str(target)], stdout=subprocess.PIPE, text=True,
                                        creationflags=subprocess.CREATE_NO_WINDOW)

            child = spawn()
            metadata = _metadata(child)
            # Even if another process has the same basename, every attach and
            # saved-state replay in this gate is restricted to our exact child.
            def owned_memory(name):
                if name != PROCESS_NAME or child is None or child.poll() is not None:
                    raise ValueError('Owned fixture is unavailable for exact-PID attach')
                return ProcessMemory(name, pid=child.pid)

            engine = TrainerEngine(plan, state_dir=state, memory_factory=owned_memory,
                                   process_lock_dir=state / '_process_sessions')
            engine.poll()
            if not engine.connected or engine.memory.pid != child.pid:
                raise AssertionError(engine.error or engine.status)
            reader = ProcessMemory(PROCESS_NAME, pid=child.pid)
            if reader.identity != engine.memory.identity:
                raise ValueError('Independent reader target identity mismatch')
            evidence['targets'].append(list(reader.identity))
            entry = metadata['entry']
            if reader.read(entry, 8) != bytes.fromhex('8bc183c0019090c3'):
                raise ValueError('Owned fixture entry bytes differ')

            def integer(address):
                return struct.unpack('<I', reader.read(address, 4))[0]

            def wait_result(expected):
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    if integer(metadata['result']) == expected:
                        return
                    time.sleep(.01)
                raise AssertionError('Own caller did not return ' + str(expected))

            def receipt(scope):
                scope._journal_guard()
                document = json.loads(scope.path.read_bytes())
                evidence['receipts'].append({'path': str(scope.path), 'state': document['state'],
                                            'sha256': _sha256_file(scope.path, 8 * 1024 * 1024),
                                            'target': document['target']})

            wait_result(4)
            assert engine.toggle(1, True)
            scope = engine.lua_activations[1]
            buffer = engine.symbols['ownedbuf']
            managers = list(scope.managers())
            assert integer(buffer) == 17 and engine.desired == {1} and len(managers) == 2
            scope.host.tick(0)
            scope.host.tick(10)
            assert integer(buffer) == 19
            assert scope.host.execute('return _VERSION') == 'Lua 5.3'
            evidence['checks'].append('ct_compiler_to_automatic_lua_receipts_owned_write_and_cooperative_worker')

            assert engine.toggle(2, True)
            wait_result(103)
            try:
                engine.toggle(1, False)
                raise AssertionError('Provider retired under its active consumer')
            except NativeRuntimeError as exc:
                assert 'dependent' in str(exc) or 'consumer' in str(exc)
            assert not engine.blocked and not scope.host.cancelled
            observation = engine.hook_coordinator.last_observation
            assert observation.get('thread_contexts')
            evidence['debugger'] = observation
            evidence['checks'].append('scoped_code_data_provider_and_dependency_refusal_before_cancellation')

            assert not engine.toggle(2, False)
            wait_result(4)
            assert not engine.toggle(1, False)
            assert scope.host.cancelled and scope.state == 'abandoned'
            assert integer(buffer) == 0 and engine.symbols == {} and not engine.desired
            assert reader.read(entry, 8) == bytes.fromhex('8bc183c0019090c3')
            assert all(manager.receipt()['state'] == 'retired' for manager in managers)
            wait_result(4)
            assert not engine.lua_sessions
            try:
                scope.host.execute('writeInteger(' + str(buffer) + ',33)')
                raise AssertionError('Cancelled host wrote target')
            except LuaHostError:
                pass
            assert integer(buffer) == 0
            receipt(scope)
            evidence['checks'].append('disable_lua_owned_receipt_main_inverse_raw_undo_and_callback_cancellation')

            assert engine.toggle(1, True)
            second = engine.lua_activations[1]
            assert second.host is not scope.host
            child.terminate()
            child.wait(timeout=5)
            engine.poll()
            assert second.state == 'target-exited' and second.host.cancelled and engine.memory is None
            assert engine.desired == {1} and not engine.blocked
            receipt(second)
            assert engine.close()
            reader.close()
            reader = None
            engine = TrainerEngine(plan, state_dir=state, memory_factory=owned_memory,
                                   process_lock_dir=state / '_process_sessions')
            assert engine.desired == {1}
            assert engine.close()
            evidence['checks'].append('fresh_activation_exact_target_exit_finalization_and_confirmed_saved_state_restart')
            evidence['status'] = 'passed'
        except Exception as exc:
            failure = exc
            evidence.update(status='failed', error=repr(exc))
        finally:
            for label, operation in (
                    ('target', lambda: (child.terminate(), child.wait(timeout=5))
                     if child is not None and child.poll() is None else None),
                    ('controller', lambda: engine.close() if engine is not None and not engine.closed else None),
                    ('reader', lambda: reader.close() if reader is not None else None)):
                try:
                    result = operation()
                    if label == 'controller' and result is False:
                        raise RuntimeError('Controller cleanup retained uncertain state')
                except Exception as exc:
                    cleanup_errors.append(label + ': ' + repr(exc))
            if cleanup_errors:
                evidence.update(status='failed', cleanup_errors=cleanup_errors)
            stream.write((json.dumps(evidence, indent=2, allow_nan=False) + '\n').encode('utf-8'))
            stream.flush()
            os.fsync(stream.fileno())
        if failure is not None:
            raise failure
        if cleanup_errors:
            raise RuntimeError('; '.join(cleanup_errors))
        return evidence
