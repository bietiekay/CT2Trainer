"""Independent real Windows gate for owned scratch bitfields and byte arrays."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import xml.etree.ElementTree as ET

from ct2trainer.native.compiler import compile_table
from ct2trainer.native.debug_coordinator import DebugEventCoordinator
from ct2trainer.native.engine import NativeRuntimeError, TrainerEngine
from ct2trainer.native.memory import ProcessMemory


PROCESS = 'NativeHookFixture.exe'
TARGET_SHA256 = '948f3a77791761a9702757efad7fd2fb6708c0990f2e16392760efda3a648d1a'


class RecordedCoordinator(DebugEventCoordinator):
    def __init__(self):
        super().__init__()
        self.data_holds = []
        self.data_proof = None

    @contextmanager
    def hold_data(self, memory, ranges):
        with super().hold_data(memory, ranges) as proof:
            proof.verify(memory, ranges)
            self.data_holds.append(list(map(list, ranges)))
            self.data_proof = proof
            try:
                yield proof
                proof.verify(memory, ranges)
            finally:
                self.data_proof = None


class RecordedMemory(ProcessMemory):
    def __init__(self, name, pid, coordinator):
        super().__init__(name, pid=pid)
        self.coordinator = coordinator
        self.writes = []

    def write(self, address, raw):
        proof = self.coordinator.data_proof
        if proof is not None:
            proof.verify(self, [(address, len(raw))])
        super().write(address, raw)
        self.writes.append({'address': address, 'bytes': raw.hex(),
                            'held_data_event': proof is not None})


def _metadata(child):
    result = queue.Queue(maxsize=1)
    threading.Thread(target=lambda: result.put(child.stdout.readline(4097)), daemon=True).start()
    line = result.get(timeout=5)
    if len(line) > 4096:
        raise ValueError('Owned fixture metadata exceeds its bound')
    metadata = json.loads(line)
    if (not isinstance(metadata, dict) or set(metadata) != {'pid', 'entry', 'result', 'calls'}
            or any(type(value) is not int or not 0 < value <= 0x7FFFFFFFFFFF
                   for value in metadata.values()) or metadata['pid'] != child.pid):
        raise ValueError('Owned fixture metadata/PID mismatch')
    return metadata


def _write_table(path, scratch, entry):
    table = ET.Element('CheatTable', CheatEngineTableVersion='45')
    rows = ET.SubElement(table, 'CheatEntries')
    for identifier, label, address, kind, properties in (
            (1, 'Owned bit zero', scratch, 'Binary', {'BitStart': 0, 'BitLength': 1}),
            (2, 'Owned bit one', scratch, 'Binary', {'BitStart': 1, 'BitLength': 1}),
            (3, 'Overlapping whole byte', scratch, 'Byte', {}),
            (4, 'Exact owned array', scratch + 16, 'Array of byte', {'ByteLength': 4}),
            (5, 'Executable bit refused', entry, 'Binary', {'BitStart': 0, 'BitLength': 1}),
            (6, 'Cross-byte field', scratch, 'Binary', {'BitStart': 7, 'BitLength': 3}),
            (7, 'Disjoint upper field', scratch + 1, 'Binary', {'BitStart': 2, 'BitLength': 2}),
            (8, 'Lua-owned field', scratch + 64, 'Binary', {'BitStart': 0, 'BitLength': 1})):
        row = ET.SubElement(rows, 'CheatEntry')
        for key, value in {'ID': identifier, 'Description': label, 'VariableType': kind,
                           'Address': f'{address:X}', 'ShowAsBinary': 0, **properties}.items():
            ET.SubElement(row, key).text = str(value)
    row = ET.SubElement(rows, 'CheatEntry')
    script = (f'[ENABLE]\ndefine(profileOwner,{scratch + 64:X})\nregistersymbol(profileOwner)'
              '\n[DISABLE]\nunregistersymbol(profileOwner)')
    for key, value in {'ID': 9, 'Description': 'Owned Lua scope', 'VariableType': 'Auto Assembler Script',
                       'AssemblerScript': script}.items():
        ET.SubElement(row, key).text = str(value)
    ET.indent(table, space='  ')
    with path.open('xb') as stream:
        stream.write(ET.tostring(table, encoding='utf-8', xml_declaration=True) + b'\n')
        stream.flush()
        os.fsync(stream.fileno())


def probe(target, output):
    target, output = Path(target).resolve(), Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as evidence_stream:
        evidence = {'schema': 'ct2trainer-value-profile-fixture/v1', 'status': 'failed',
                    'ce_inputs': [], 'checks': [], 'game_runtime_verified': False,
                    'probe_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    'scratch_released': False}
        child = owner = engine = independent = None
        scratch = None
        failure, cleanup = None, []
        controller_closed = False
        try:
            if target.name != PROCESS:
                raise ValueError('This gate requires the independently owned NativeHookFixture.exe')
            raw = target.read_bytes()
            if len(raw) > 16 * 1024 * 1024:
                raise ValueError('Owned fixture image exceeds its byte bound')
            evidence['target_sha256'] = hashlib.sha256(raw).hexdigest()
            if evidence['target_sha256'] != TARGET_SHA256:
                raise ValueError('Owned fixture binary SHA-256 differs from the pin')
            child = subprocess.Popen([str(target)], stdout=subprocess.PIPE, text=True,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
            metadata = _metadata(child)
            owner = ProcessMemory(PROCESS, pid=child.pid)
            scratch = owner.allocate(4096)
            assert owner.allocation_size(scratch) == 4096 and not owner.is_executable(scratch, 4096)
            owner.write(scratch, b'\xa5' * 128)
            owner.write(scratch, b'\xd2\xc0')
            evidence.update(target_identity=list(owner.identity), scratch_address=scratch, scratch_size=4096)
            source = output.with_suffix('.ct')
            _write_table(source, scratch, metadata['entry'])
            plan = compile_table(source, PROCESS)
            assert plan['counts']['blocked'] == 0
            evidence['table_sha256'] = plan['table_sha256']
            coordinator = RecordedCoordinator()
            engine = TrainerEngine(plan, state_dir=output.with_suffix('.state'),
                                   process_lock_dir=output.with_suffix('.shared'), hook_coordinator=coordinator,
                                   memory_factory=lambda name: RecordedMemory(name, child.pid, coordinator))
            engine.poll()
            assert engine.connected and engine.memory.identity == owner.identity
            independent = ProcessMemory(PROCESS, pid=child.pid)
            assert independent.identity == owner.identity
            before_entry = independent.read(metadata['entry'], 8)
            assert before_entry == bytes.fromhex('8bc183c0019090c3')

            assert engine.set_value(1, '1') == '1'
            assert independent.read(scratch, 2) == b'\xd3\xc0'
            assert engine.set_value(2, '0') == '0'
            assert independent.read(scratch, 2) == b'\xd1\xc0'
            assert engine.set_value(2, '1') == '1'
            assert engine.set_value(6, '5') == '5'
            assert engine.set_value(7, '3') == '3'
            assert independent.read(scratch, 2) == b'\xd3\xce'
            assert all(item['held_data_event'] for item in engine.memory.writes)
            assert coordinator.last_observation['thread_contexts']
            evidence['checks'].append('real_held_debug_event_bitfield_sets_preserve_disjoint_neighbor_bits')

            for identifier in (1, 2, 6, 7):
                assert engine.set_freeze(identifier, True)
            independent.write(scratch, b'\x50\xf0')
            write_index, hold_index = len(engine.memory.writes), len(coordinator.data_holds)
            engine.poll()
            assert not engine.blocked, engine.error
            assert independent.read(scratch, 2) == b'\xd3\xfe'
            assert engine.memory.writes[write_index:] == [
                {'address': scratch, 'bytes': 'd3fe', 'held_data_event': True}]
            assert coordinator.data_holds[hold_index:] == [[[scratch, 2]]]
            evidence['checks'].append('four_disjoint_cross_byte_freezes_coalesce_into_one_fresh_masked_write')

            for operation in (lambda: engine.set_value(3, '0'), lambda: engine.set_freeze(3, True)):
                try:
                    operation()
                    raise AssertionError('Whole-byte ownership overlapped frozen fields')
                except NativeRuntimeError as exc:
                    assert 'overlaps' in str(exc)
            independent.write(scratch, b'\x93\xfe')
            host = engine.open_lua_session()
            assert host.execute('return getAddressList().getMemoryRecordByID(1).Active') is True
            assert host.execute('return getAddressList().getMemoryRecordByID(2).Active') is True
            assert not engine.blocked
            evidence['checks'].append('overlapping_whole_byte_refused_and_lua_active_ignores_unowned_neighbor_bits')
            for identifier in (1, 2, 6, 7):
                assert not engine.set_freeze(identifier, False)

            assert engine.set_value(4, '01 a2 03 FF') == '01 A2 03 FF'
            assert independent.read(scratch + 15, 6) == bytes.fromhex('a5 01 a2 03 ff a5')
            assert engine.set_freeze(4, True)
            independent.write(scratch + 16, bytes(4))
            engine.poll()
            assert not engine.blocked and independent.read(scratch + 16, 4) == bytes.fromhex('01 a2 03 ff')
            count = len(engine.memory.writes)
            for text in ('01 02', '01 ?? 03 FF', '01 02 03 04 05'):
                try:
                    engine.set_value(4, text)
                    raise AssertionError('Invalid array literal was admitted')
                except NativeRuntimeError:
                    pass
            assert len(engine.memory.writes) == count
            assert independent.read(scratch + 15, 6) == bytes.fromhex('a5 01 a2 03 ff a5')
            assert not engine.set_freeze(4, False)
            evidence['checks'].append('exact_byte_array_write_freeze_sentinels_and_invalid_length_wildcard_refusal')

            assert engine.toggle(9, True)
            activation = engine.open_lua_activation(9)
            assert activation.execute('return writeInteger("profileOwner",17)')
            assert independent.read(scratch + 64, 4) == bytes.fromhex('11 00 00 00')
            for operation in (lambda: engine.set_value(8, '0'), lambda: engine.set_freeze(8, True)):
                try:
                    operation()
                    raise AssertionError('Field operation overwrote Lua-owned undo bytes')
                except NativeRuntimeError as exc:
                    assert 'Lua-owned' in str(exc)
            assert not engine.blocked and not engine.toggle(9, False)
            assert activation.cancelled and independent.read(scratch + 64, 4) == b'\xa5' * 4
            evidence['checks'].append('lua_owned_scope_blocks_bitfield_write_and_freeze_then_restores_its_bytes')

            count, holds = len(engine.memory.writes), len(coordinator.data_holds)
            for operation in (lambda: engine.set_value(5, '1'), lambda: engine.set_freeze(5, True)):
                try:
                    operation()
                    raise AssertionError('Executable bitfield mutation was admitted')
                except NativeRuntimeError as exc:
                    assert 'executable' in str(exc)
            assert not engine.blocked and len(engine.memory.writes) == count
            assert len(coordinator.data_holds) == holds
            assert independent.read(metadata['entry'], 8) == before_entry
            evidence['checks'].append('executable_bitfield_set_and_freeze_refused_before_hold_or_write')
            evidence['data_holds'] = coordinator.data_holds
            evidence['engine_writes'] = engine.memory.writes
            evidence['debugger'] = coordinator.last_observation
            assert engine.close()
            controller_closed = True
            assert owner.identity == tuple(evidence['target_identity']) and owner.allocation_size(scratch) == 4096
            assert not owner.is_executable(scratch, 4096)
            owner.release(scratch)
            scratch = None
            evidence['scratch_released'] = True
            evidence['checks'].append('only_known_rw_scratch_released_after_controller_close')
            evidence['status'] = 'passed'
        except Exception as exc:
            failure = exc
            evidence.update(status='failed', error=repr(exc))
        finally:
            if engine is not None and not engine.closed:
                try:
                    controller_closed = engine.close()
                    if not controller_closed:
                        raise RuntimeError('Controller retained uncertain state')
                except Exception as exc:
                    cleanup.append('controller: ' + repr(exc))
            # The only explicit release is the allocation owned by this exact
            # handle, after a confirmed controller close. Failed/uncertain
            # gates retain it until terminating our own fixture process.
            if scratch is not None and owner is not None and controller_closed and failure is None:
                try:
                    owner.release(scratch)
                    evidence['scratch_released'] = True
                except Exception as exc:
                    cleanup.append('scratch: ' + repr(exc))
            for label, memory in (('reader', independent), ('owner', owner)):
                if memory is not None:
                    try:
                        memory.close()
                    except Exception as exc:
                        cleanup.append(label + ': ' + repr(exc))
            if child is not None and child.poll() is None:
                try:
                    child.terminate()
                    child.wait(timeout=5)
                except Exception as exc:
                    cleanup.append('owned target: ' + repr(exc))
            if cleanup:
                evidence.update(status='failed', cleanup_errors=cleanup)
            evidence_stream.write((json.dumps(evidence, indent=2, allow_nan=False) + '\n').encode('utf-8'))
            evidence_stream.flush()
            os.fsync(evidence_stream.fileno())
        if failure is not None:
            raise failure
        if cleanup:
            raise RuntimeError('; '.join(cleanup))
        return evidence


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--target', type=Path, required=True)
    cli.add_argument('--report', type=Path, required=True)
    arguments = cli.parse_args()
    print(probe(arguments.target, arguments.report)['status'])
