"""Acceptance gate for the byte-pinned, independently owned code-patch fixtures.

This controller-only gate never accepts a game CT or an arbitrary target
image.  It exercises the real RT-5 item B code-patch record lifecycle
against a live owned target: data-page publish/capture/restore through the
ordinary transaction, overlap refusal, target-changed refusal,
already-active adoption, executable-page routing through the verified hook
coordinator, the restore-mismatch engine block with its blocked-session
close fence, target-exit finalization of the blocked session, saved-ON
replay of both routes on a fresh identity, replayed disables, and normal
close after exit.  It checks source-runtime and frozen execution
separately in its retained report.
"""
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

# Pinned 2026-11-16 for the first code-patch fixture build: MSVC
# 19.44.35229, evidence build/runs/native-codepatch-fixture-20261116T032022Z-bdd3
# (tests/windows/codepatch_fixture/Invoke-CodePatchFixtureBuild.ps1,
# /W4 /WX /Od; marker + data_a + data_b + probe prologue occurrence == 1
# each per EXE).  The x64 RVAs were measured from the live target's
# metadata line; the x86 RVAs were measured statically by a PE section
# walk cross-proven byte-exact against the x64 runtime metadata.
PROCESS_NAME = 'NativeCodePatchFixture.exe'
FIXTURE_SOURCE_SHA256 = '89f1bef4b4f59fbd6653bd9eb1ff6777d321c740bde30d2741f7af56fe7a52e9'
CT_SHA256 = {
    'x64': '3219ee42a0cab3f40a66fce762c62c6e0b49140e91fcff671759e8354d78bc31',
    'x86': 'de7be66c3ef09747a7a475539aed9afc2c77af0affb0e8d5ee4aaa50d61369d8',
}
TARGET_SHA256 = {
    'x64': '3f217da553159221216db43c6c8e83481d5da2869edcdf68ca4f66980a9b891f',
    'x86': '288855467feab361c2d27a64a4ff68bb73687923d8e3984003a3c7fe77ae6a85',
}
PLAN_SHA256 = {
    'x64': '6b0ce466529127e1497cc1e47e7ca4d3bbaba198564c1bbb701b4c57155cffa3',
    'x86': 'c67846921cafeedb36387e465efa88fdaa95e80c7526bc485df817b8d6a28061',
}
MARKER_BYTES = bytes.fromhex('435432542d4350502d323032362d3031')
BASELINE_A = bytes.fromhex('444154415f413031')
ACTUAL_A = bytes.fromhex('5041544348454430')
FOREIGN_A = bytes.fromhex('464f524549474e41')
BASELINE_B = bytes.fromhex('44415442')
ACTUAL_B = bytes.fromhex('50415442')
FOREIGN_B = bytes.fromhex('464f5245')
OVERLAP_ACTUAL = bytes.fromhex('43303033')
PROBE_PROLOGUE = {
    'x64': bytes.fromhex('b85d5c5b5ac3'),
    'x86': bytes.fromhex('558becb85d5c5b5a5dc3'),
}
PATCHED_PROLOGUE = {
    'x64': bytes.fromhex('b849484746c3'),
    'x86': bytes.fromhex('558becb8494847465dc3'),
}
ORIGINAL_PROBE_VALUE = 0x5A5B5C5D
PATCHED_PROBE_VALUE = 0x46474849
METADATA_SCHEMA = 'ct2trainer-owned-codepatch-target/v1'
STATUS_SCHEMA = 'ct2trainer-owned-codepatch-status/v1'
_SCHEME = 'ct2trainer-owned-codepatch/v1'

from .compiler import CODE_PATCH_ID_BASE

# Table order of the pinned CT's four <CodeEntry> records.
DATA_A_ID = CODE_PATCH_ID_BASE + 0
PROBE_ID = CODE_PATCH_ID_BASE + 1
DATA_B_ID = CODE_PATCH_ID_BASE + 2
OVERLAP_ID = CODE_PATCH_ID_BASE + 3


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def plan_fingerprint(plan):
    """Bind all behavior and identity; only two top-level display fields vary."""
    if type(plan) is not dict:
        raise ValueError('Code-patch gate requires a canonical owned plan')
    return hashlib.sha256(_canonical({k: v for k, v in plan.items()
                                      if k not in {'title', 'source_name'}})).hexdigest()


def validate_fixture_plan(plan):
    from .architecture import plan_architecture
    from .engine import validate_plan
    validate_plan(plan)
    architecture = plan_architecture(plan)['machine']
    if (type(plan.get('source_name')) is not str or len(plan['source_name']) > 260
            or any(ord(ch) < 32 for ch in plan['source_name'])
            or plan.get('schema') != 2 or architecture not in PLAN_SHA256
            or plan.get('table_sha256') != CT_SHA256[architecture]
            or plan.get('process_name') != PROCESS_NAME
            or plan_fingerprint(plan) != PLAN_SHA256[architecture]):
        raise ValueError('Code-patch gate requires its exact owned CT and canonical four-record plan')
    return architecture


def _hash_file(path, maximum=None):
    digest = hashlib.sha256()
    size = 0
    with Path(path).open('rb') as stream:
        while block := stream.read(1024 * 1024):
            size += len(block)
            if maximum is not None and size > maximum:
                raise ValueError('Owned code-patch target image exceeds its admission bound')
            digest.update(block)
    return digest.hexdigest()


def _admit_target(target, architecture):
    if (target.name != PROCESS_NAME
            or _hash_file(target, 32 * 1024 * 1024) != TARGET_SHA256[architecture]):
        raise ValueError('Code-patch gate requires its byte-pinned independently owned target')
    # A second, independent architecture check precedes child creation.
    with target.open('rb') as stream:
        dos = stream.read(64)
        if len(dos) != 64 or dos[:2] != b'MZ':
            raise ValueError('Owned code-patch target has no bounded PE header')
        offset = struct.unpack_from('<I', dos, 60)[0]
        if not 64 <= offset <= 1024 * 1024:
            raise ValueError('Owned code-patch target PE header offset is invalid')
        stream.seek(offset)
        pe = stream.read(26)
    machine, magic = ((0x8664, 0x20B) if architecture == 'x64' else (0x14C, 0x10B))
    if (len(pe) != 26 or pe[:4] != b'PE\0\0'
            or struct.unpack_from('<H', pe, 4)[0] != machine
            or struct.unpack_from('<H', pe, 24)[0] != magic):
        raise ValueError('Owned code-patch target PE architecture differs from its plan')


def _assert_no_files(directory, label):
    leftovers = [path.name for path in Path(directory).glob('*') if path.is_file()]
    if leftovers:
        raise AssertionError(
            'Normal close after exit retained ownership markers in ' + label + ': ' + ', '.join(leftovers))


def _receive(child):
    received = queue.Queue(maxsize=1)
    def get():
        try:
            received.put(child.stdout.readline(16385))
        except Exception as exc:
            received.put(exc)
    threading.Thread(target=get, daemon=True, name='owned-codepatch-json').start()
    try:
        value = received.get(timeout=5)
    except queue.Empty as exc:
        raise ValueError('Owned code-patch target did not publish bounded JSON') from exc
    if isinstance(value, Exception):
        raise value
    if not value or len(value) > 16384:
        raise ValueError('Owned code-patch output exceeds its bounded JSON contract')
    return json.loads(value)


def _command(child, command):
    child.stdin.write(command + '\n')
    child.stdin.flush()
    return _receive(child)


def _validate_metadata(value, pid, architecture):
    keys = {'schema', 'pid', 'pointer_bits', 'pe_machine', 'process_name',
            'module_base', 'module_bytes', 'page_bytes', 'marker_rva',
            'marker_bytes', 'data_a_rva', 'data_a_bytes', 'data_b_rva',
            'data_b_bytes', 'overlap_rva', 'overlap_bytes', 'probe_rva',
            'probe_bytes', 'original_value'}
    bits = 64 if architecture == 'x64' else 32
    maximum = 0x7FFFFFFFFFFF if bits == 64 else 0xFFFFFFFF
    prologue = PROBE_PROLOGUE[architecture]
    if (type(value) is not dict or set(value) != keys
            or value['schema'] != METADATA_SCHEMA
            or value['process_name'] != PROCESS_NAME
            or any(type(value[key]) is not int for key in
                   ('pid', 'pointer_bits', 'pe_machine', 'module_base',
                    'module_bytes', 'page_bytes', 'marker_rva', 'data_a_rva',
                    'data_b_rva', 'overlap_rva', 'probe_rva', 'original_value'))
            or value['pid'] != pid or value['pointer_bits'] != bits
            or value['pe_machine'] != (0x8664 if bits == 64 else 0x14C)
            or value['module_bytes'] <= 0
            or value['page_bytes'] != 4096
            or not 0 < value['module_base'] <= maximum - value['module_bytes']
            or value['module_base'] % 65536
            or any(not 0 < value[key] < value['module_bytes'] for key in
                   ('marker_rva', 'data_a_rva', 'data_b_rva', 'overlap_rva', 'probe_rva'))
            or value['marker_bytes'] != MARKER_BYTES.hex()
            or value['data_a_bytes'] != BASELINE_A.hex()
            or value['data_b_bytes'] != BASELINE_B.hex()
            or value['overlap_bytes'] != BASELINE_A[4:8].hex()
            or value['probe_bytes'] != prologue.hex()
            or value['original_value'] != ORIGINAL_PROBE_VALUE):
        raise ValueError('Owned code-patch target identity or module metadata differs')
    separate = {
        'marker': (value['marker_rva'], value['marker_rva'] + len(MARKER_BYTES)),
        'data_a': (value['data_a_rva'], value['data_a_rva'] + len(BASELINE_A)),
        'data_b': (value['data_b_rva'], value['data_b_rva'] + len(BASELINE_B)),
        'probe': (value['probe_rva'], value['probe_rva'] + len(prologue)),
    }
    if any(end > value['module_bytes'] for start, end in separate.values()
           if start < value['module_bytes']):
        raise ValueError('Owned code-patch sentinels exceed the module image')
    if value['overlap_rva'] != value['data_a_rva'] + 4:
        raise ValueError('Owned code-patch overlap block is not the pinned data_a tail')
    overlap_end = value['overlap_rva'] + len(OVERLAP_ACTUAL)
    if overlap_end > value['module_bytes']:
        raise ValueError('Owned code-patch sentinels exceed the module image')
    for name in separate:
        start, end = separate[name]
        for other in separate:
            if name < other:
                start2, end2 = separate[other]
                if start < end2 and start2 < end:
                    raise ValueError('Owned code-patch sentinels %s and %s overlap' % (name, other))
    return value


def _validate_status(value, pid):
    if (type(value) is not dict or set(value) != {'schema', 'pid', 'sequence', 'probe_value'}
            or value['schema'] != STATUS_SCHEMA
            or type(value['pid']) is not int or value['pid'] != pid
            or type(value['sequence']) is not int or value['sequence'] < 1
            or type(value['probe_value']) is not int
            or not 0 <= value['probe_value'] < 0x100000000):
        raise ValueError('Owned code-patch status contract differs')
    return value


class _OwnedRun:
    """Keep cleanup authority only for Popen objects created by this gate."""
    def __init__(self, plan, target, architecture, evidence, state):
        self.plan, self.target, self.architecture = plan, target, architecture
        self.evidence, self.state = evidence, state
        self.child = self.reader = self.engine = None
        self._owned_children = set()

    def spawn(self):
        _admit_target(self.target, self.architecture)
        self.child = subprocess.Popen([str(self.target)], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='ascii',
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self._owned_children.add(self.child)
        self.evidence['target_spawned'] = True
        self.evidence['owned_child_pids'].append(self.child.pid)
        return _validate_metadata(_receive(self.child), self.child.pid, self.architecture)

    def detach_engine(self):
        # A deliberately fenced engine is intentionally left owned; the gate
        # records its retained receipts instead of forcing cleanup.
        if self.engine is not None:
            self.engine = None

    def close_engine(self):
        if self.engine is not None:
            if not self.engine.close():
                raise AssertionError(self.engine.error or 'Controller close did not confirm cleanup')
            self.engine = None

    def close_reader(self):
        if self.reader is not None:
            self.reader.close()
            self.reader = None

    def quit_child(self):
        if self.child is None or self.child not in self._owned_children:
            raise AssertionError('No owned child is available for normal exit')
        self.child.stdin.write('quit\n')
        self.child.stdin.flush()
        if self.child.wait(timeout=5) != 0:
            raise AssertionError('Owned code-patch child did not exit normally')
        self._owned_children.remove(self.child)
        self.child = None

    def cleanup(self):
        errors = []
        try:
            self.close_engine()
        except Exception as exc:
            errors.append('controller: ' + repr(exc))
        try:
            self.close_reader()
        except Exception as exc:
            errors.append('reader: ' + repr(exc))
        for child in tuple(self._owned_children):
            try:
                if child.poll() is None:
                    child.kill()
                    self.evidence.setdefault('forced_owned_child_exit', []).append(child.pid)
                    errors.append('owned child required forced exit')
                child.wait(timeout=5)
            except Exception as exc:
                errors.append('owned child: ' + repr(exc))
            else:
                self._owned_children.remove(child)
        if errors:
            self.evidence['cleanup_errors'] = errors
            raise AssertionError('; '.join(errors))


def _exercise(run):
    from .engine import NativeRuntimeError, StateError, TrainerEngine
    from .memory import ProcessMemory
    evidence, plan = run.evidence, run.plan
    architecture = run.architecture
    bits = 64 if architecture == 'x64' else 32
    prologue = PROBE_PROLOGUE[architecture]
    patched = PATCHED_PROLOGUE[architecture]
    hooks_dir = run.state / 'state' / 'hooks'

    def note(name):
        evidence['checks'].append({'check': name, 'passed': True})

    def connect(metadata):
        run.reader = ProcessMemory(PROCESS_NAME, pid=run.child.pid)
        reader = run.reader
        if (reader.pointer_size * 8 != bits or reader.identity[0] != run.child.pid
                or Path(reader._image_path()).resolve() != run.target
                or reader.module(PROCESS_NAME) != (metadata['module_base'], metadata['module_bytes'])):
            raise AssertionError('Independent owned child image, module, identity or width differs')
        _admit_target(run.target, architecture)
        marker_address = metadata['module_base'] + metadata['marker_rva']
        probe_address = metadata['module_base'] + metadata['probe_rva']
        if reader.read(marker_address, len(MARKER_BYTES)) != MARKER_BYTES:
            raise AssertionError('Owned marker sentinels differ from the pinned anchor bytes')
        if reader.read(probe_address, len(prologue)) != prologue:
            raise AssertionError('Owned probe entry sentinels differ from the pinned original prologue')
        run.engine.poll()
        if not run.engine.connected:
            raise AssertionError(run.engine.error or run.engine.status)
        if reader.identity != run.engine.memory.identity:
            raise AssertionError('Controller attached a different process identity')
        evidence['target_instances'].append({'metadata': metadata, 'identity': list(reader.identity)})
        return reader

    def snapshot(expected_value):
        observed = _command(run.child, 'probe')
        evidence['protocol_observations'].append(observed)
        _validate_status(observed, run.child.pid)
        if observed['probe_value'] != expected_value:
            raise AssertionError('Target protocol probed %d, expected %d'
                                 % (observed['probe_value'], expected_value))
        return observed

    def setdata(block, payload):
        observed = _command(run.child, 'setdata ' + block + ' ' + payload.hex())
        evidence['protocol_observations'].append(observed)
        _validate_status(observed, run.child.pid)
        return observed

    def block_bytes(metadata, reader):
        base = metadata['module_base']
        return {
            'marker': reader.read(base + metadata['marker_rva'], len(MARKER_BYTES)),
            'data_a': reader.read(base + metadata['data_a_rva'], len(BASELINE_A)),
            'data_b': reader.read(base + metadata['data_b_rva'], len(BASELINE_B)),
            'probe': reader.read(base + metadata['probe_rva'], len(prologue)),
        }

    def assert_block(name, metadata, reader, expected):
        actual = block_bytes(metadata, reader)
        for key, want in expected.items():
            if actual[key] != want:
                raise AssertionError(name + ' block ' + key + ' differs: '
                                     + actual[key].hex() + ' != ' + want.hex())

    # ---- Session 1: full lifecycle on the first owned target.
    metadata = run.spawn()
    run.engine = TrainerEngine(plan, state_dir=run.state / 'state',
                               process_lock_dir=run.state / 'shared',
                               memory_factory=lambda name: ProcessMemory(name, pid=run.child.pid))
    engine = run.engine
    reader = connect(metadata)
    note('exact-child-image-identity-architecture-and-module-metadata')
    snapshot(ORIGINAL_PROBE_VALUE)
    assert_block('Baseline', metadata, reader,
                 {'marker': MARKER_BYTES, 'data_a': BASELINE_A,
                  'data_b': BASELINE_B, 'probe': prologue})
    note('baseline-data-exec-and-marker-sentinels')

    if engine.toggle(DATA_A_ID, True) is not True:
        raise AssertionError(engine.error or 'Data patch A did not enable')
    evidence['target_write_actions_started'] = True
    evidence['target_writes'] = True
    assert_block('Enabled data A', metadata, reader,
                 {'data_a': ACTUAL_A})
    patch = engine.applied[DATA_A_ID][0]
    if (patch.address != metadata['module_base'] + metadata['data_a_rva']
            or patch.original != BASELINE_A or patch.changed != ACTUAL_A):
        raise AssertionError('Data patch A did not capture the pinned baseline original')
    if DATA_A_ID not in engine.desired:
        raise AssertionError('Data patch A did not save the ON wish')
    snapshot(ORIGINAL_PROBE_VALUE)
    note('data-enable-publishes-actual-and-captures-original')

    try:
        engine.toggle(OVERLAP_ID, True)
    except NativeRuntimeError as exc:
        if 'A code patch overlaps another enabled entry' not in str(exc):
            raise AssertionError('Overlap refusal differs: ' + str(exc))
    else:
        raise AssertionError('Overlapping code patch was not refused')
    if engine.blocked:
        raise AssertionError('Overlap refusal blocked the controller')
    if OVERLAP_ID in engine.applied:
        raise AssertionError('Refused overlap recorded a live patch')
    assert_block('Overlap refusal', metadata, reader, {'data_a': ACTUAL_A})
    snapshot(ORIGINAL_PROBE_VALUE)
    note('overlapping-code-patch-refused-zero-write')

    if engine.toggle(DATA_A_ID, False) is not False:
        raise AssertionError('Data patch A did not disable')
    assert_block('Disabled data A', metadata, reader, {'data_a': BASELINE_A})
    if DATA_A_ID in engine.applied or DATA_A_ID in engine.desired:
        raise AssertionError('Data disable left a live receipt or saved wish')
    snapshot(ORIGINAL_PROBE_VALUE)
    note('data-disable-restores-captured-original')

    setdata('A', FOREIGN_A)
    assert_block('Target-side setdata A', metadata, reader, {'data_a': FOREIGN_A})
    try:
        engine.toggle(DATA_A_ID, True)
    except NativeRuntimeError as exc:
        if 'code-patch-target-changed' not in str(exc):
            raise AssertionError('Target-changed refusal differs: ' + str(exc))
    else:
        raise AssertionError('Target-changed enable was not refused')
    if engine.blocked:
        raise AssertionError('Target-changed refusal blocked the controller')
    if DATA_A_ID in engine.applied:
        raise AssertionError('Refused enable recorded a live patch')
    assert_block('Target-changed refusal', metadata, reader, {'data_a': FOREIGN_A})
    snapshot(ORIGINAL_PROBE_VALUE)
    note('target-changed-refusal-zero-write')

    setdata('A', ACTUAL_A)
    if engine.toggle(DATA_A_ID, True) is not True:
        raise AssertionError(engine.error or 'Already-active data patch A did not enable')
    if engine.applied[DATA_A_ID][0].original != ACTUAL_A:
        raise AssertionError('Adopt did not capture the live bytes as the original')
    if engine.toggle(DATA_A_ID, False) is not False:
        raise AssertionError('Adopted data patch A did not disable')
    assert_block('Adopted no-write disable', metadata, reader, {'data_a': ACTUAL_A})
    if DATA_A_ID in engine.applied or DATA_A_ID in engine.desired:
        raise AssertionError('Adopted disable left a live receipt or saved wish')
    note('already-active-adopts-and-no-write-disable')

    if engine.toggle(PROBE_ID, True) is not True:
        raise AssertionError(engine.error or 'Executable patch did not enable')
    if reader.read(metadata['module_base'] + metadata['probe_rva'], len(patched)) != patched:
        raise AssertionError('Executable patch did not publish the pinned entry bytes')
    snapshot(PATCHED_PROBE_VALUE)
    journals = sorted(p.name for p in hooks_dir.glob('*.json') if p.is_file())
    if len(journals) != 1:
        raise AssertionError('Executable code patch did not journal exactly one receipt: ' + repr(journals))
    evidence['exec_journal_file'] = journals[0]
    evidence['exec_journal_sample'] = (hooks_dir / journals[0]).read_bytes().hex()
    if PROBE_ID not in engine.applied or PROBE_ID not in engine.desired:
        raise AssertionError('Executable patch left no live receipt or saved wish')
    note('exec-enable-patches-live-function-and-target-executes')

    if engine.toggle(DATA_B_ID, True) is not True:
        raise AssertionError(engine.error or 'Data patch B did not enable')
    assert_block('Enabled data B', metadata, reader, {'data_b': ACTUAL_B})
    if engine.applied[DATA_B_ID][0].original != BASELINE_B:
        raise AssertionError('Data patch B did not capture the pinned baseline original')
    setdata('B', FOREIGN_B)
    assert_block('Target-side setdata B', metadata, reader, {'data_b': FOREIGN_B})
    try:
        engine.toggle(DATA_B_ID, False)
    except NativeRuntimeError as exc:
        if 'code-patch-restore-mismatch' not in str(exc):
            raise AssertionError('Restore-mismatch refusal differs: ' + str(exc))
    else:
        raise AssertionError('Restore mismatch did not refuse the disable')
    if not engine.blocked:
        raise AssertionError('Restore mismatch did not block the controller')
    assert_block('Restore mismatch', metadata, reader, {'data_b': FOREIGN_B})
    if DATA_B_ID not in engine.applied or DATA_B_ID not in engine.desired:
        raise AssertionError('Restore mismatch cleared the owned receipt or saved wish')
    note('restore-mismatch-keeps-record-applied-and-blocks-engine')

    try:
        engine.toggle(PROBE_ID, False)
    except NativeRuntimeError:
        pass
    else:
        raise AssertionError('Blocked engine admitted a toggle action')
    try:
        TrainerEngine(plan, state_dir=run.state / 'state', process_lock_dir=run.state / 'shared',
                      memory_factory=lambda name: ProcessMemory(name, pid=run.child.pid))
    except StateError as exc:
        message = str(exc)
        if not ('state.lock is held by live trainer process' in message
                or 'state.lock already exists' in message):
            raise AssertionError('Second controller refusal differs: ' + message)
    else:
        raise AssertionError('Second controller claimed a live state directory')
    if not engine.blocked or engine.memory is None:
        raise AssertionError('Second controller attempt disturbed the blocked controller')
    if sorted(engine.applied) != [PROBE_ID, DATA_B_ID]:
        raise AssertionError('Second controller attempt disturbed the live receipts')
    if sorted(engine.desired) != [PROBE_ID, DATA_B_ID]:
        raise AssertionError('Second controller attempt disturbed the saved wishes')
    note('blocked-engine-refuses-actions-and-second-controller')

    run.quit_child()
    if engine.close() is not True:
        raise AssertionError(engine.error or
                             'Blocked session close after target exit did not confirm cleanup')
    if engine.memory is not None or not engine.closed:
        raise AssertionError('Blocked session close left the target handle or open state')
    if any(p.is_file() for p in hooks_dir.glob('*')):
        raise AssertionError('Blocked session close did not retire the executable journal')
    for name in ('state.lock', 'session.json'):
        if (run.state / 'state' / name).exists():
            raise AssertionError('Blocked session close retained ' + name)
    document = json.loads((run.state / 'state' / 'state.json').read_text(encoding='utf-8'))
    if document.get('payload', {}).get('desired') != [PROBE_ID, DATA_B_ID]:
        raise AssertionError('Blocked session close did not persist both saved wishes: '
                             + repr(document.get('payload', {}).get('desired')))
    _assert_no_files(run.state / 'shared', 'process lock directory')
    run.close_reader()
    note('target-exit-close-finalizes-blocked-session-and-persists-wishes')

    # ---- Session 2: fresh target identity, saved-ON replay of both routes.
    first_identity = tuple(evidence['target_instances'][0]['identity'])
    metadata = run.spawn()
    run.engine = TrainerEngine(plan, state_dir=run.state / 'state',
                               process_lock_dir=run.state / 'shared',
                               memory_factory=lambda name: ProcessMemory(name, pid=run.child.pid))
    reader = connect(metadata)
    engine = run.engine
    if reader.identity == first_identity:
        raise AssertionError('Target restart reused the previous process identity')
    if engine.blocked or not engine.connected:
        raise AssertionError('Saved-ON replay did not attach the fresh controller')
    if reader.read(metadata['module_base'] + metadata['probe_rva'], len(patched)) != patched:
        raise AssertionError('Saved-ON replay did not re-patch the executable entry')
    snapshot(PATCHED_PROBE_VALUE)
    assert_block('Saved-ON replay', metadata, reader, {'data_b': ACTUAL_B})
    if PROBE_ID not in engine.applied or DATA_B_ID not in engine.applied:
        raise AssertionError('Saved-ON replay left a saved route unapplied')
    if engine.applied[DATA_B_ID][0].original != BASELINE_B:
        raise AssertionError('Saved-ON replay captured a drifted original for data block B')
    if sorted(engine.desired) != [PROBE_ID, DATA_B_ID]:
        raise AssertionError('Saved-ON replay altered the saved wish set')
    note('saved-on-replays-both-routes-on-fresh-identity')

    if engine.toggle(PROBE_ID, False) is not False:
        raise AssertionError('Replayed executable patch did not disable')
    if reader.read(metadata['module_base'] + metadata['probe_rva'], len(prologue)) != prologue:
        raise AssertionError('Replayed disable did not restore the exact original entry bytes')
    snapshot(ORIGINAL_PROBE_VALUE)
    journals = sorted(p.name for p in hooks_dir.glob('*.json') if p.is_file())
    if len(journals) != 1:
        raise AssertionError('Replayed disable did not retain the terminal executable receipt: ' + repr(journals))
    receipt = json.loads((hooks_dir / journals[0]).read_text(encoding='utf-8'))
    if (receipt.get('state') != 'retired' or receipt.get('uncertain') is not False
            or receipt.get('owner') != plan['trainer_id'] + ':' + str(PROBE_ID)
            or receipt.get('target_pid') != run.child.pid):
        raise AssertionError('Terminal executable receipt differs: '
                             + repr({key: receipt.get(key) for key in
                                    ('state', 'uncertain', 'owner', 'target_pid')}))
    if engine.toggle(DATA_B_ID, False) is not False:
        raise AssertionError('Replayed data patch B did not disable')
    assert_block('Replayed data B disable', metadata, reader, {'data_b': BASELINE_B})
    if PROBE_ID in engine.applied or DATA_B_ID in engine.applied or engine.desired:
        raise AssertionError('Replayed disables left live receipts or saved wishes')
    note('replayed-disables-restore-originals-and-target-reverts')

    setdata('A', BASELINE_A)
    assert_block('Final reset', metadata, reader,
                 {'marker': MARKER_BYTES, 'data_a': BASELINE_A,
                  'data_b': BASELINE_B, 'probe': prologue})
    snapshot(ORIGINAL_PROBE_VALUE)
    run.quit_child()
    engine.poll()
    if (engine.memory is not None or engine.applied or engine.hooks or engine.retired_hooks):
        raise AssertionError('Target exit did not detach the fresh controller state')
    run.close_engine()
    for name in ('state.lock', 'session.json'):
        if (run.state / 'state' / name).exists():
            raise AssertionError('Normal close after exit retained ' + name)
    if any(p.is_file() for p in hooks_dir.glob('*')):
        raise AssertionError('Target exit did not retire the replayed executable journal')
    _assert_no_files(run.state / 'shared', 'process lock directory')
    run.close_reader()
    evidence['owned_markers_absent'] = True
    note('normal-close-after-exit-confirms-cleanup')

    if len(evidence['checks']) != 14:
        raise AssertionError('Owned code-patch gate did not complete exactly fourteen checks')

    # ---- Dedicated live-close fence session (recorded evidence, not one of
    # the fourteen checks): a blocked live close must refuse with a False
    # return and the named mismatch reason, touch nothing in the target and
    # preserve every receipt for the verified recovery on the next start.
    fence = run.state / 'fence'
    metadata = run.spawn()
    run.engine = TrainerEngine(plan, state_dir=fence, process_lock_dir=fence / 'shared',
                               memory_factory=lambda name: ProcessMemory(name, pid=run.child.pid))
    fence_reader = connect(metadata)
    fence_engine = run.engine
    if fence_engine.toggle(PROBE_ID, True) is not True:
        raise AssertionError(fence_engine.error or 'Fence session did not enable the executable patch')
    if fence_engine.toggle(DATA_B_ID, True) is not True:
        raise AssertionError(fence_engine.error or 'Fence session did not enable data patch B')
    setdata('B', FOREIGN_B)
    assert_block('Fence target-side setdata B', metadata, fence_reader, {'data_b': FOREIGN_B})
    try:
        fence_engine.toggle(DATA_B_ID, False)
    except NativeRuntimeError as exc:
        if 'code-patch-restore-mismatch' not in str(exc):
            raise AssertionError('Fence restore mismatch differs: ' + str(exc))
    else:
        raise AssertionError('Fence restore mismatch did not refuse the disable')
    if fence_engine.close() is not False:
        raise AssertionError('Blocked live close returned success')
    if 'code-patch-restore-mismatch' not in (fence_engine.error or ''):
        raise AssertionError('Live-close refusal differs: ' + (fence_engine.error or ''))
    if not fence_engine.closed or fence_engine.memory is not None:
        raise AssertionError('Blocked live close left open state')
    for name in ('state.lock', 'session.json', 'state.json'):
        if not (fence / name).exists():
            raise AssertionError('Live close did not preserve ' + name)
    fence_document = json.loads((fence / 'state.json').read_text(encoding='utf-8'))
    if fence_document.get('payload', {}).get('desired') != [PROBE_ID, DATA_B_ID]:
        raise AssertionError('Live close did not persist both saved wishes: '
                             + repr(fence_document.get('payload', {}).get('desired')))
    if fence_reader.read(metadata['module_base'] + metadata['probe_rva'], len(patched)) != patched:
        raise AssertionError('Blocked live close changed the patched entry')
    if fence_reader.read(metadata['module_base'] + metadata['data_b_rva'], len(BASELINE_B)) != FOREIGN_B:
        raise AssertionError('Blocked live close touched the foreign data block')
    fence_journals = sorted(p.name for p in (fence / 'hooks').glob('*.json') if p.is_file())
    if len(fence_journals) != 1:
        raise AssertionError('Live close did not retain exactly one executable receipt: '
                             + repr(fence_journals))
    fence_receipt = json.loads((fence / 'hooks' / fence_journals[0]).read_text(encoding='utf-8'))
    if (fence_receipt.get('state') != 'enabled'
            or fence_receipt.get('owner') != plan['trainer_id'] + ':' + str(PROBE_ID)
            or fence_receipt.get('target_pid') != run.child.pid):
        raise AssertionError('Retained executable receipt differs: '
                             + repr({key: fence_receipt.get(key) for key in
                                    ('state', 'owner', 'target_pid')}))
    evidence['live_close_fence'] = {
        'state_directory': str(fence),
        'refusal': fence_engine.error,
        'data_retained': True,
        'markers_retained': [path.name for path in
                             (fence / 'state.lock', fence / 'session.json', fence / 'state.json',
                              fence / 'hooks' / fence_journals[0])],
    }
    run.detach_engine()
    run.quit_child()
    for name in ('state.lock', 'session.json', 'state.json', 'hooks/' + fence_journals[0]):
        if not (fence / name).exists():
            raise AssertionError('Receipts were cleaned up after the fenced live close: ' + name)
    run.close_reader()


def run_probe(plan, target: str | Path, report: str | Path):
    """Reserve fresh evidence, admit exact source/image, then run only own children."""
    report = Path(report).resolve()
    report.parent.mkdir(parents=True, exist_ok=True)
    evidence = {'schema': _SCHEME, 'status': 'running', 'ce_implementation_inputs': [],
                'target_spawned': False, 'target_write_actions_started': False,
                'target_writes': False,
                'frozen_runtime': bool(getattr(sys, 'frozen', False)),
                'source_runtime': not bool(getattr(sys, 'frozen', False)),
                'game_runtime_verified': False, 'checks': [], 'owned_child_pids': [],
                'target_instances': [], 'protocol_observations': []}
    with report.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(evidence) + '\n')
    failure = None
    run = None
    try:
        architecture = validate_fixture_plan(plan)
        target = Path(target).resolve()
        _admit_target(target, architecture)
        evidence.update({'target_architecture': architecture, 'target_path': str(target),
            'command': [str(target)], 'target_sha256': TARGET_SHA256[architecture],
            'fixture_source_sha256': FIXTURE_SOURCE_SHA256, 'table_sha256': CT_SHA256[architecture],
            'canonical_plan_sha256': plan_fingerprint(plan),
            'plan_sha256': hashlib.sha256(_canonical(plan)).hexdigest(),
            'frozen_runtime': bool(getattr(sys, 'frozen', False)),
            'source_runtime': not bool(getattr(sys, 'frozen', False)),
            'runtime_executable': str(Path(sys.executable).resolve()),
            'runtime_executable_sha256': _hash_file(sys.executable)})
        state = Path(tempfile.mkdtemp(prefix='ct2trainer-owned-codepatch-'))
        evidence['state_directory'] = str(state)
        run = _OwnedRun(plan, target, architecture, evidence, state)
        _exercise(run)
        if len(evidence['checks']) != 14:
            raise AssertionError('Owned code-patch gate did not complete exactly fourteen checks')
        evidence['status'] = 'passed'
    except Exception as exc:
        failure = exc
        evidence['status'] = 'failed'
        evidence['error'] = repr(exc)
    finally:
        if run is not None:
            try:
                run.cleanup()
            except Exception as exc:
                evidence['status'] = 'failed'
                evidence.setdefault('cleanup_errors', []).append(repr(exc))
                if failure is None:
                    failure = exc
                    evidence['error'] = repr(exc)
        report.write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
    if failure is not None:
        raise failure
    return evidence
