"""Acceptance gate for two byte-pinned, independently owned Global-allocation fixtures.

This controller-only gate never accepts a game CT or an arbitrary target image.
It exercises the real shared-global pool against a live owned target: scan
capture, near-marker RW allocation, NASM-linked consumer, value-record
roundtrips, disable retention, target-exit retirement, and the stale-journal
and live-close fences. It checks source-runtime and frozen execution
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

# Re-pinned 2026-10-07 after the CT2Trainer rename (schema strings,
# TFRG->CT2T marker) and the fixture rebuild: MSVC 19.44.35229,
# evidence build/runs/fixture-repin-20261007T115729Z.
PROCESS_NAME = 'NativeGlobalFixture.exe'
FIXTURE_SOURCE_SHA256 = 'c44cbe404954678ca753f81b17f6d9c1c17d16558755a79bcb982a983ebec6aa'
CT_SHA256 = {
    'x64': 'a27eb49eb76b628c7e3c3703d1018f206f00feab5d5c6e46ea032f53c28f92f6',
    'x86': '99fab3bdaa7c8beffddbad9a1345801c87127e4a5bb78f6afd3cec807b4be65c',
}
TARGET_SHA256 = {
    'x64': 'f42dfd03dfe2e703fcd87320fc30f00d825f47ef50dc58d957a38f166e620853',
    'x86': 'e66ae2b8bdc3d44d427b31fa9278dd017694ef707d352e52461c1979ec98f98c',
}
# Re-pinned 2026-10-11 for WP-14 (staged capabilities): the canonical plan
# of the unchanged pinned CTs now carries the derived 'staged' marker on
# the value record (provider liveness gating); CT bytes are unchanged.
PLAN_SHA256 = {
    'x64': 'cf8fdfbc77a91ae811ac12cc4c6e4ea797cc168948ae6298f4e473936c661c00',
    'x86': '312a753e3df1e71ec8fdb652b98c2880cc5b895febd9aff28e3a8897903b9982',
}
MARKER_BYTES = bytes.fromhex('435432542d474c422d323032362d3031')
PROBE_PROLOGUE = {
    'x64': bytes.fromhex('b85d5c5b5ac3'),
    'x86': bytes.fromhex('558becb85d5c5b5a5dc3'),
}
ORIGINAL_PROBE_VALUE = 0x5A5B5C5D
INITIAL_GLOBAL_VALUE = 333
WRITTEN_GLOBAL_VALUE = 4660
NEAR_ANCHOR_OFFSET = 16
NEAR_TOLERANCE = 0x7FFF0000
METADATA_SCHEMA = 'ct2trainer-owned-global-target/v1'
STATUS_SCHEMA = 'ct2trainer-owned-global-status/v1'
POOL_SCHEMA = 'ct2trainer-global-pool-draft/v1'
_SCHEMA = 'ct2trainer-owned-global/v1'
GLOBAL_NAME = 'globalvalue'


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def plan_fingerprint(plan):
    """Bind all behavior and identity; only two top-level display fields vary."""
    if type(plan) is not dict:
        raise ValueError('Global gate requires a canonical owned plan')
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
        raise ValueError('Global gate requires its exact owned CT and canonical two-record plan')
    return architecture


def _hash_file(path, maximum=None):
    digest = hashlib.sha256()
    size = 0
    with Path(path).open('rb') as stream:
        while block := stream.read(1024 * 1024):
            size += len(block)
            if maximum is not None and size > maximum:
                raise ValueError('Owned Global target image exceeds its admission bound')
            digest.update(block)
    return digest.hexdigest()


def _admit_target(target, architecture):
    if target.name != PROCESS_NAME or _hash_file(target, 32 * 1024 * 1024) != TARGET_SHA256[architecture]:
        raise ValueError('Global gate requires its byte-pinned independently owned target')
    # A second, independent architecture check precedes child creation.
    with target.open('rb') as stream:
        dos = stream.read(64)
        if len(dos) != 64 or dos[:2] != b'MZ':
            raise ValueError('Owned target has no bounded PE header')
        offset = struct.unpack_from('<I', dos, 60)[0]
        if not 64 <= offset <= 1024 * 1024:
            raise ValueError('Owned target PE header offset is invalid')
        stream.seek(offset)
        pe = stream.read(26)
    machine, magic = ((0x8664, 0x20B) if architecture == 'x64' else (0x14C, 0x10B))
    if (len(pe) != 26 or pe[:4] != b'PE\0\0'
            or struct.unpack_from('<H', pe, 4)[0] != machine
            or struct.unpack_from('<H', pe, 24)[0] != magic):
        raise ValueError('Owned Global target PE architecture differs from its plan')


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
    threading.Thread(target=get, daemon=True, name='owned-global-json').start()
    try:
        value = received.get(timeout=5)
    except queue.Empty as exc:
        raise ValueError('Owned Global target did not publish bounded JSON') from exc
    if isinstance(value, Exception):
        raise value
    if not value or len(value) > 16384:
        raise ValueError('Owned Global output exceeds its bounded JSON contract')
    return json.loads(value)


def _command(child, command):
    child.stdin.write(command + '\n')
    child.stdin.flush()
    return _receive(child)


def _validate_metadata(value, pid, architecture):
    keys = {'schema', 'pid', 'pointer_bits', 'pe_machine', 'process_name',
            'module_base', 'module_bytes', 'page_bytes', 'marker_rva',
            'marker_bytes', 'probe_rva', 'probe_bytes', 'original_value'}
    bits = 64 if architecture == 'x64' else 32
    maximum = 0x7FFFFFFFFFFF if bits == 64 else 0xFFFFFFFF
    prologue = PROBE_PROLOGUE[architecture]
    if (type(value) is not dict or set(value) != keys
            or value['schema'] != METADATA_SCHEMA
            or value['process_name'] != PROCESS_NAME
            or any(type(value[key]) is not int for key in
                   ('pid', 'pointer_bits', 'pe_machine', 'module_base', 'module_bytes',
                    'page_bytes', 'marker_rva', 'probe_rva', 'original_value'))
            or value['pid'] != pid or value['pointer_bits'] != bits
            or value['pe_machine'] != (0x8664 if bits == 64 else 0x14C)
            or value['module_bytes'] <= 0
            or value['page_bytes'] != 4096
            or not 0 < value['module_base'] <= maximum - value['module_bytes']
            or value['module_base'] % 65536
            or not 0 < value['marker_rva'] < value['module_bytes']
            or not 0 < value['probe_rva'] < value['module_bytes']
            or value['marker_bytes'] != MARKER_BYTES.hex()
            or value['probe_bytes'] != prologue.hex()
            or value['original_value'] != ORIGINAL_PROBE_VALUE):
        raise ValueError('Owned Global target identity or module metadata differs')
    marker_end = value['marker_rva'] + len(MARKER_BYTES)
    probe_end = value['probe_rva'] + len(prologue)
    if marker_end > value['module_bytes'] or probe_end > value['module_bytes']:
        raise ValueError('Owned Global sentinels exceed the module image')
    if not (marker_end <= value['probe_rva'] or probe_end <= value['marker_rva']):
        raise ValueError('Owned Global marker and probe entry overlap')
    return value


def _validate_status(value, pid):
    if (type(value) is not dict or set(value) != {'schema', 'pid', 'sequence', 'probe_value'}
            or value['schema'] != STATUS_SCHEMA
            or type(value['pid']) is not int or value['pid'] != pid
            or type(value['sequence']) is not int or value['sequence'] < 1
            or type(value['probe_value']) is not int
            or not 0 <= value['probe_value'] < 0x100000000):
        raise ValueError('Owned Global status contract differs')
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
            raise AssertionError('Owned Global child did not exit normally')
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
    from .engine import StateError, TrainerEngine
    from .memory import ProcessMemory
    evidence, plan = run.evidence, run.plan
    architecture = run.architecture
    bits = 64 if architecture == 'x64' else 32
    prologue = PROBE_PROLOGUE[architecture]

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
        return reader, marker_address, probe_address

    def snapshot(expected_value):
        observed = _command(run.child, 'probe')
        evidence['protocol_observations'].append(observed)
        _validate_status(observed, run.child.pid)
        if observed['probe_value'] != expected_value:
            raise AssertionError('Target protocol probed %d, expected %d'
                                 % (observed['probe_value'], expected_value))
        return observed

    def member_address(engine):
        if GLOBAL_NAME not in engine.global_pool.members:
            raise AssertionError('Shared-global pool does not own the pinned member')
        return engine.global_pool.members[GLOBAL_NAME]['address']

    def raw_global(reader, address):
        return reader.read(address, 4)

    # ---- Session 1: full lifecycle on the first owned target.
    metadata = run.spawn()
    run.engine = TrainerEngine(plan, state_dir=run.state / 'state',
                               process_lock_dir=run.state / 'shared',
                               memory_factory=lambda name: ProcessMemory(name, pid=run.child.pid))
    reader, marker_address, probe_address = connect(metadata)
    engine = run.engine
    note('exact-child-image-identity-architecture-and-module-metadata')
    snapshot(ORIGINAL_PROBE_VALUE)
    if reader.read(probe_address, len(prologue)) != prologue:
        raise AssertionError('Baseline entry bytes differ from the pinned original prologue')
    note('baseline-probe-returns-pinned-original-constant')

    if engine.toggle(1, True) is not True:
        raise AssertionError(engine.error or 'Global consumer did not enable')
    evidence['target_write_actions_started'] = True
    evidence['target_writes'] = True
    address = member_address(engine)
    anchor = marker_address + NEAR_ANCHOR_OFFSET
    if not anchor - NEAR_TOLERANCE <= address < anchor + NEAR_TOLERANCE:
        raise AssertionError('Global storage is not allocated near its pinned marker anchor')
    region = reader._query(address)
    if (int(region.State) != 0x1000 or int(region.Protect) != 4
            or int(region.Type) != 0x20000):
        raise AssertionError('Global storage is not a committed private RW allocation')
    if raw_global(reader, address) != INITIAL_GLOBAL_VALUE.to_bytes(4, 'little'):
        raise AssertionError('Global initializer did not write the pinned literal 333')
    evidence['pool_journal_sample'] = (run.state / 'state' / 'hooks' / 'global-pool.json').read_bytes().hex()
    note('global-enable-allocates-rw-storage-near-marker-and-initializes-333')

    snapshot(INITIAL_GLOBAL_VALUE)
    if engine.read_value(2) != str(INITIAL_GLOBAL_VALUE):
        raise AssertionError('Value record read differs from the held global value')
    note('patched-entry-returns-held-global-value-through-real-code-path')

    if engine.set_value(2, str(WRITTEN_GLOBAL_VALUE)) != str(WRITTEN_GLOBAL_VALUE):
        raise AssertionError('Value record write through the symbol was refused')
    if raw_global(reader, address) != WRITTEN_GLOBAL_VALUE.to_bytes(4, 'little'):
        raise AssertionError('Value record write did not land in the held global storage')
    snapshot(WRITTEN_GLOBAL_VALUE)
    note('value-record-write-through-symbol-lands-in-held-global-storage')

    if engine.toggle(1, False) is not False:
        raise AssertionError('Global consumer did not disable')
    if reader.read(probe_address, len(prologue)) != prologue:
        raise AssertionError('Disable did not restore the exact original entry bytes')
    if GLOBAL_NAME not in engine.global_pool.members:
        raise AssertionError('Disable released the shared global storage')
    if raw_global(reader, address) != WRITTEN_GLOBAL_VALUE.to_bytes(4, 'little'):
        raise AssertionError('Disable changed the retained global storage')
    note('disable-restores-entry-bytes-and-retains-global-storage')

    if GLOBAL_NAME in engine.symbols:
        raise AssertionError('Disabled consumer still exports the global symbol')
    try:
        engine.read_value(2)
    except Exception:
        pass
    else:
        raise AssertionError('Hidden global symbol still resolves a value read')
    if engine.blocked:
        raise AssertionError('Clean hidden-symbol refusal blocked the controller')
    if engine.global_pool.state != 'live':
        raise AssertionError('Pool state differs after a clean disable')
    note('value-symbol-hidden-after-disable-while-storage-remains')

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
    if engine.blocked or not engine.connected:
        raise AssertionError('Second controller attempt disturbed the live controller')
    if engine.global_pool.state != 'live':
        raise AssertionError('Second controller attempt changed the pool state')
    note('second-controller-refuses-live-state-claim')

    run.quit_child()
    engine.poll()
    if (engine.global_pool is not None or engine.global_leases or engine._global_aliases
            or engine.memory is not None or engine.applied or engine.frozen):
        raise AssertionError('Target exit did not retire the shared-global controller state')
    if (run.state / 'state' / 'hooks' / 'global-pool.json').exists():
        raise AssertionError('Target exit did not remove the terminal pool receipt')
    note('target-exit-retires-pool-and-removes-terminal-receipt')

    run.close_engine()
    for path in (run.state / 'state' / 'state.lock', run.state / 'state' / 'session.json'):
        if path.exists():
            raise AssertionError('Normal close after exit retained an ownership marker: ' + path.name)
    _assert_no_files(run.state / 'shared', 'process lock directory')
    run.close_reader()
    evidence['owned_markers_absent'] = True
    note('normal-close-after-exit-confirms-cleanup')

    # ---- Stale journal fence: a pool journal alone blocks any new controller.
    stale = run.state / 'stale'
    (stale / 'hooks').mkdir(parents=True)
    journal = stale / 'hooks' / 'global-pool.json'
    journal.write_bytes(bytes.fromhex(evidence['pool_journal_sample']))
    try:
        TrainerEngine(plan, state_dir=stale, process_lock_dir=stale / 'shared',
                      memory_factory=lambda name: ProcessMemory(name, pid=run.child.pid))
    except StateError as exc:
        if 'A prior shared-global pool cannot be revived from JSON' not in str(exc):
            raise AssertionError('Stale pool journal refusal differs: ' + str(exc))
    else:
        raise AssertionError('Stale pool journal alone did not block a new controller')
    if (stale / 'state.lock').exists():
        raise AssertionError('Blocked controller left its own lock behind')
    if journal.read_bytes().hex() != evidence['pool_journal_sample']:
        raise AssertionError('Blocked controller altered the preserved pool journal')
    note('stale-pool-journal-alone-blocks-new-controller')

    # ---- Session 2: fresh target identity, fresh pool, full roundtrip again.
    first_identity = tuple(evidence['target_instances'][0]['identity'])
    metadata = run.spawn()
    run.engine = TrainerEngine(plan, state_dir=run.state / 'state',
                               process_lock_dir=run.state / 'shared',
                               memory_factory=lambda name: ProcessMemory(name, pid=run.child.pid))
    reader, marker_address, probe_address = connect(metadata)
    engine = run.engine
    if run.reader.identity == first_identity:
        raise AssertionError('Target restart reused the previous process identity')
    if engine.desired or engine.frozen:
        raise AssertionError('Fresh session replayed saved switch state')
    snapshot(ORIGINAL_PROBE_VALUE)
    note('fresh-spawn-attaches-fresh-identity-with-original-probe')

    if engine.toggle(1, True) is not True:
        raise AssertionError(engine.error or 'Fresh session did not reallocate the global consumer')
    address = member_address(engine)
    anchor = marker_address + NEAR_ANCHOR_OFFSET
    if not anchor - NEAR_TOLERANCE <= address < anchor + NEAR_TOLERANCE:
        raise AssertionError('Fresh global storage is not allocated near its pinned marker anchor')
    if engine.global_pool.identity != tuple(run.reader.identity):
        raise AssertionError('Fresh pool is bound to a different target identity')
    if raw_global(reader, address) != INITIAL_GLOBAL_VALUE.to_bytes(4, 'little'):
        raise AssertionError('Fresh global initializer did not write the pinned literal 333')
    snapshot(INITIAL_GLOBAL_VALUE)
    if engine.set_value(2, str(WRITTEN_GLOBAL_VALUE)) != str(WRITTEN_GLOBAL_VALUE):
        raise AssertionError('Fresh session value write through the symbol was refused')
    if raw_global(reader, address) != WRITTEN_GLOBAL_VALUE.to_bytes(4, 'little'):
        raise AssertionError('Fresh session value write did not land in the held global storage')
    snapshot(WRITTEN_GLOBAL_VALUE)
    if engine.toggle(1, False) is not False:
        raise AssertionError('Fresh session did not disable the global consumer')
    if reader.read(probe_address, len(prologue)) != prologue:
        raise AssertionError('Fresh session disable did not restore the exact original entry bytes')
    note('fresh-session-enable-reallocates-global-and-roundtrip-succeeds')

    if raw_global(reader, address) != WRITTEN_GLOBAL_VALUE.to_bytes(4, 'little'):
        raise AssertionError('Final session disable changed the retained global storage')
    if reader.read(marker_address, len(MARKER_BYTES)) != MARKER_BYTES:
        raise AssertionError('Final marker sentinels changed')
    run.quit_child()
    engine.poll()
    if engine.global_pool is not None or (run.state / 'state' / 'hooks' / 'global-pool.json').exists():
        raise AssertionError('Final target exit did not retire the fresh pool')
    run.close_engine()
    for path in (run.state / 'state' / 'state.lock', run.state / 'state' / 'session.json'):
        if path.exists():
            raise AssertionError('Final close retained an ownership marker: ' + path.name)
    _assert_no_files(run.state / 'shared', 'process lock directory')
    run.close_reader()
    note('normal-final-close-sentinels-markers-and-owned-target-exit')

    # ---- Dedicated live-close fence session (recorded evidence, not one of
    # the fourteen checks): a live close with retained storage must refuse,
    # restore the entry, and preserve every receipt for later recovery.
    fence = run.state / 'fence'
    metadata = run.spawn()
    run.engine = TrainerEngine(plan, state_dir=fence, process_lock_dir=fence / 'shared',
                               memory_factory=lambda name: ProcessMemory(name, pid=run.child.pid))
    fence_reader, fence_marker, fence_probe = connect(metadata)
    fence_engine = run.engine
    if fence_engine.toggle(1, True) is not True:
        raise AssertionError(fence_engine.error or 'Fence session did not enable the global consumer')
    fence_address = member_address(fence_engine)
    fence_engine.set_value(2, str(WRITTEN_GLOBAL_VALUE))
    if not fence_engine.close():
        pass
    else:
        raise AssertionError('Live close with retained global storage returned success')
    if 'Shared globals and their retired consumers remain owned until exact target exit' not in (
            fence_engine.error or ''):
        raise AssertionError('Live-close refusal differs: ' + (fence_engine.error or ''))
    if fence_reader.read(fence_probe, len(prologue)) != prologue:
        raise AssertionError('Live close did not restore the exact original entry bytes')
    if fence_reader.read(fence_address, 4) != WRITTEN_GLOBAL_VALUE.to_bytes(4, 'little'):
        raise AssertionError('Live close changed the retained global storage')
    for path in (fence / 'state.lock', fence / 'session.json', fence / 'hooks' / 'global-pool.json'):
        if not path.exists():
            raise AssertionError('Live close did not preserve ' + path.name)
    evidence['live_close_fence'] = {
        'state_directory': str(fence),
        'refusal': fence_engine.error,
        'markers_retained': [path.name for path in
                             (fence / 'state.lock', fence / 'session.json', fence / 'hooks' / 'global-pool.json')],
        'entry_restored': True,
        'storage_retained': True,
    }
    run.detach_engine()
    run.quit_child()
    for path in (fence / 'state.lock', fence / 'session.json', fence / 'hooks' / 'global-pool.json'):
        if not path.exists():
            raise AssertionError('Receipts were cleaned up after the fenced live close: ' + path.name)
    run.close_reader()
    if len(evidence['checks']) != 14:
        raise AssertionError('Owned Global gate did not complete exactly fourteen checks')


def run_probe(plan, target: str | Path, report: str | Path):
    """Reserve fresh evidence, admit exact source/image, then run only own children."""
    report = Path(report).resolve()
    report.parent.mkdir(parents=True, exist_ok=True)
    evidence = {'schema': _SCHEMA, 'status': 'running', 'ce_implementation_inputs': [],
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
        state = Path(tempfile.mkdtemp(prefix='ct2trainer-owned-global-'))
        evidence['state_directory'] = str(state)
        run = _OwnedRun(plan, target, architecture, evidence, state)
        _exercise(run)
        if len(evidence['checks']) != 14:
            raise AssertionError('Owned Global gate did not complete exactly fourteen checks')
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
