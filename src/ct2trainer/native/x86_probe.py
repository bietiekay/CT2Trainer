"""Owned source/frozen WOW64 acceptance; never a general headless game route."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import queue
import struct
import subprocess
import sys
import threading
import time


PROCESS_NAME = 'NativeDebugHookFixture-x86.exe'
TARGET_SHA256 = '9bf7407ceabb72495f082b763f3b88e6be6a4b860ff1866312a272a667faa7c7'
CT_SHA256 = '6d04714ec6729abf00798d6736eba687c9588c5d4c457c90d9f302f5e442f7c8'
SOURCE_SHA256 = 'eacbbf87af4c98d7217a3bf0c27b783379a71bc8c0c73a932c08f7dd08553148'


def validate_fixture_plan(plan: dict) -> None:
    from .engine import validate_plan
    from .architecture import prepare_architecture
    validate_plan(plan)
    if (plan.get('schema') != 2 or plan.get('target_architecture') != prepare_architecture('x86')
            or plan.get('table_sha256') != CT_SHA256 or plan.get('process_name') != PROCESS_NAME
            or plan.get('selected_ids') != [1, 2]
            or [entry.get('id') for entry in plan.get('entries', [])] != [1, 2]):
        raise ValueError('The x86 gate requires its exact pinned owned CT and canonical x86 plan.')
    first, value = plan['entries']
    if (not first.get('supported') or first.get('kind') != 'script' or 'lua_program' in first
            or first.get('program', {}).get('bitness') != 32
            or first.get('program', {}).get('process_name') != PROCESS_NAME
            or first.get('program', {}).get('source_sha256') != SOURCE_SHA256
            or first.get('enable') != [] or first.get('disable') != []
            or not value.get('supported') or value.get('kind') != 'value'
            or value.get('address') != 'OwnedX86Data' or value.get('dependency_ids') != [1]
            or value.get('variable_type') != '4 Bytes'):
        raise ValueError('The x86 gate source profiles differ from its owned fixture contract.')


def _wait(check, message: str, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(.005)
    raise AssertionError(message)


def _spawn(target):
    child = subprocess.Popen([str(target)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    messages = queue.Queue()
    def metadata():
        try:
            messages.put(child.stdout.readline(65537))
        except Exception as exc:
            messages.put(exc)
    threading.Thread(target=metadata, daemon=True).start()
    try:
        raw = messages.get(timeout=3)
        if isinstance(raw, Exception):
            raise raw
        if len(raw) > 65536:
            raise ValueError('Owned fixture metadata exceeds its bounded line size.')
        info = json.loads(raw)
        if (info.get('pid') != child.pid or info.get('pointer_size') != 4 or info.get('entry_size') != 9
                or any(type(info.get(key)) is not int or not 0 < info[key] <= 0xFFFFFFFF
                       for key in ('entry', 'result', 'calls', 'bad', 'churn', 'stop'))):
            raise ValueError('Owned x86 fixture metadata differs from its contract.')
        return child, info
    except BaseException:
        if child.poll() is None:
            child.terminate(); child.wait(timeout=5)
        raise


def run_probe(plan: dict, target: str | Path, report: str | Path) -> dict:
    """Prove only the exact launched fixture, preserving reports before raising."""
    from .architecture import prepare_architecture
    from .compiler import validate_plan
    from .engine import TrainerEngine
    from .memory import ProcessMemory
    from .bundle import canonical_bytes

    report = Path(report).resolve()
    report.parent.mkdir(parents=True, exist_ok=True)
    # A fresh exclusive report reserves the evidence name before any target read.
    with report.open('x', encoding='utf-8') as output:
        evidence = {'schema': 'ct2trainer-owned-x86/v1', 'status': 'started',
                    'checks': [], 'ce_inputs': [], 'game_runtime_verified': False,
                    'frozen_runtime': bool(getattr(sys, 'frozen', False)),
                    'runtime_executable': str(Path(sys.executable).resolve()),
                    'runtime_executable_sha256': hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
                    'table_sha256': CT_SHA256}
        child = reader = engine = wrong = held = None
        try:
            validate_fixture_plan(plan)
            evidence['plan_sha256'] = hashlib.sha256(canonical_bytes(plan)).hexdigest()
            target = Path(target).resolve()
            if target.name != PROCESS_NAME or hashlib.sha256(target.read_bytes()).hexdigest() != TARGET_SHA256:
                raise ValueError('The x86 gate requires its exact pinned owned target binary.')
            evidence['target_sha256'] = TARGET_SHA256
            state = report.parent / (report.stem + '-state')
            shared = report.parent / (report.stem + '-shared')
            if state.exists() or shared.exists():
                raise FileExistsError('Owned x86 gate state/evidence folders must be fresh.')
            child, info = _spawn(target)
            reader = ProcessMemory(PROCESS_NAME, child.pid)
            if reader.pointer_size != 4:
                raise AssertionError('Held target is not x86.')
            evidence['target_identity'] = list(reader.identity)
            result = lambda: int.from_bytes(reader.read(info['result'], 4), 'little')
            _wait(lambda: result() == 4 and int.from_bytes(reader.read(info['calls'], 4), 'little') > 30,
                  'Owned x86 callers did not begin with result4.')
            original = bytes.fromhex('8b44240483c0019090')
            if reader.read(info['entry'], 9) != original:
                raise AssertionError('Owned x86 original instruction entry differs.')

            # Rebind the entire source-valid AA profile to x64, without changing
            # the target. The engine must refuse before a session or allocator.
            from copy import deepcopy
            from .aa_program import prepare_program
            altered = deepcopy(plan)
            altered['target_architecture'] = prepare_architecture('x64')
            original_program = plan['entries'][0]['program']
            altered['entries'][0]['program'] = prepare_program(original_program['source'], PROCESS_NAME,
                                                              bitness=64,
                                                              labels=original_program.get('external_labels'))
            identity = {'engine': 'ct2trainer', 'schema': 2, 'target_architecture': altered['target_architecture'],
                        'table_sha256': altered['table_sha256'], 'process_name': PROCESS_NAME.casefold(), 'selected_ids': [1, 2]}
            altered['trainer_id'] = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:16]
            validate_plan(altered)
            held = ProcessMemory(PROCESS_NAME, child.pid)
            wrong = TrainerEngine(altered, report.parent/(report.stem+'-mismatch-state'), lambda name: held,
                                  report.parent/(report.stem+'-mismatch-shared'))
            wrong.poll()
            if wrong.connected or wrong.blocked or 'mismatch' not in wrong.error or wrong.store.session.exists():
                raise AssertionError('Wrong-architecture attach did not give a clean pre-session refusal.')
            if held._handle or reader.read(info['entry'], 9) != original or result() != 4:
                raise AssertionError('Wrong-architecture attach left a handle or changed the target.')
            if not wrong.close():
                raise AssertionError('Read-only mismatch controller did not close cleanly.')
            evidence['checks'].append('canonical_x64_source_plan_refused_before_target_session_or_effect')

            engine = TrainerEngine(plan, state, lambda name: ProcessMemory(name, child.pid), shared)
            engine.poll()
            if not engine.connected or engine.memory.pointer_size != 4:
                raise AssertionError(engine.error or engine.status)
            if not engine.toggle(1, True):
                raise AssertionError('Owned x86 source did not activate.')
            _wait(lambda: result() == 103, 'Compiled x86 hook did not change observed result4 to103.')
            if engine.desired != {1}:
                raise AssertionError('Confirmed x86 hook was not saved as ON.')
            evidence['debugger'] = engine.hook_coordinator.last_observation
            if not evidence['debugger'].get('thread_contexts'):
                raise AssertionError('Owned x86 hook has no held thread-context evidence.')
            data = engine._value_address(engine.entries[2])
            guard = engine.symbols['ownedx86guard']
            if reader.read(data, 4) != struct.pack('<I', 1234) or reader.read(guard, 4) != bytes.fromhex('efbeadde'):
                raise AssertionError('Linked owned provider data does not match literal source.')
            evidence['checks'].append('explicit_x86_ct_nasm_pushad_pushfd_hook_confirmed_4_to103_and_saved')

            host = engine.open_lua_session()
            if host.execute(f'return readPointer({data})') != 1234:
                raise AssertionError('Lua readPointer did not use the held x86 four-byte width.')
            address = host.execute('return getAddress("kernel32.GetCurrentProcessId")')
            if address != reader.resolve_export('kernel32', 'GetCurrentProcessId') or not 0 < address <= 0xFFFFFFFF:
                raise AssertionError('Lua x86 remote export differs from independent held reader.')
            if engine.set_value(2, '4321') != '4321' or reader.read(data, 4) != struct.pack('<I', 4321):
                raise AssertionError('Owned x86 literal numeric write did not confirm.')
            if reader.read(guard, 4) != bytes.fromhex('efbeadde'):
                raise AssertionError('Owned literal write changed its adjacent sentinel.')
            host.cancel()
            evidence['checks'].append('x86_lua_pointer_remote_export_and_coordinated_literal_write_independent_readback')

            engine.toggle(1, False)
            _wait(lambda: result() == 4, 'Owned x86 disable did not restore result4.')
            if reader.read(info['entry'], 9) != original or engine.desired:
                raise AssertionError('Owned x86 disable did not restore exact entry and saved wish.')
            parent = next(manager for manager in engine.retired_hooks if manager.allocations)
            cave = next(iter(parent.allocations.values()))['address']
            if not reader.is_executable(cave, 1):
                raise AssertionError('Retired owned x86 code was released before target exit.')
            evidence['checks'].append('exact_x86_disable_and_retired_executable_retention')

            engine.toggle(1, True)
            _wait(lambda: result() == 103, 'Second x86 activation did not confirm.')
            reader.write(info['stop'], struct.pack('<I', 1))
            child.wait(timeout=5)
            if child.returncode != 0:
                raise AssertionError('Owned x86 target observed an invalid concurrent result.')
            engine.poll()
            if engine.memory is not None or engine.blocked or engine.desired != {1} or not engine.close():
                raise AssertionError('Owned x86 exit did not finalize receipts and retain saved ON.')
            reader.close(); reader = None
            evidence['checks'].append('exact_x86_target_exit_finalizes_receipts_and_preserves_saved_on')

            child, info = _spawn(target)
            reader = ProcessMemory(PROCESS_NAME, child.pid)
            if list(reader.identity) == evidence['target_identity']:
                raise AssertionError('Fresh owned x86 target did not obtain a fresh identity.')
            evidence['restarted_target_identity'] = list(reader.identity)
            engine = TrainerEngine(plan, state, lambda name: ProcessMemory(name, child.pid), shared)
            engine.poll()
            _wait(lambda: int.from_bytes(reader.read(info['result'], 4), 'little') == 103,
                  'Saved x86 ON did not restore on the fresh exact target.')
            if not engine.connected or engine.desired != {1}:
                raise AssertionError('Saved x86 restore did not confirm.')
            engine.toggle(1, False)
            _wait(lambda: int.from_bytes(reader.read(info['result'], 4), 'little') == 4,
                  'Restored owned x86 record did not disable.')
            if reader.read(info['entry'], 9) != original:
                raise AssertionError('Restored owned x86 record did not restore exact bytes.')
            reader.write(info['stop'], struct.pack('<I', 1)); child.wait(timeout=5)
            engine.poll()
            if child.returncode != 0 or engine.blocked or engine.memory is not None or not engine.close():
                raise AssertionError('Fresh target final cleanup did not confirm.')
            evidence['checks'].append('saved_x86_on_restores_on_fresh_identity_and_final_disable_closes')
            evidence['status'] = 'passed'
        except BaseException as exc:
            evidence.update(status='failed', error=repr(exc))
            raise
        finally:
            cleanup_errors = []
            try:
                if child is not None and child.poll() is None:
                    child.terminate(); child.wait(timeout=5)
            except BaseException as exc:
                cleanup_errors.append('owned child: ' + repr(exc))
            for controller in (engine, wrong):
                try:
                    if controller is not None and not controller.closed and not controller.close():
                        cleanup_errors.append('owned controller: ' + controller.error)
                except BaseException as exc:
                    cleanup_errors.append('owned controller: ' + repr(exc))
            for memory in (reader, held):
                try:
                    if memory is not None:
                        memory.close()
                except BaseException as exc:
                    cleanup_errors.append('owned reader: ' + repr(exc))
            if cleanup_errors:
                evidence.update(status='failed', cleanup_errors=cleanup_errors)
            json.dump(evidence, output, indent=2); output.write('\n'); output.flush(); os.fsync(output.fileno())
            if cleanup_errors and sys.exc_info()[0] is None:
                raise RuntimeError('Owned x86 cleanup is uncertain; evidence was retained.')
    return evidence
