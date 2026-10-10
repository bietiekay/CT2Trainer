"""Acceptance gate for two byte-pinned, independently owned String fixtures.

This controller-only gate never accepts a game CT or an arbitrary target image.
It checks source-runtime and frozen execution separately in its retained report.
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

# Re-pinned 2026-10-07 after the CT2Trainer rename (schema strings) and the
# fixture rebuild: MSVC 19.44.35229,
# evidence build/runs/fixture-repin-20261007T115729Z.
PROCESS_NAME = 'NativeStringFixture.exe'
FIXTURE_SOURCE_SHA256 = '9c69ea3549387956551e96d501a5184765d59df36cae2cc32936ca81b0877652'
CT_SHA256 = {
    'x64': '97e36a533db823542bed0830cd07a0eaedc8b1f34ff36d108c2c3edf69e3c10e',
    'x86': '63758a2d45765a002b2f7618515b0aac23e75d4baf736bbe85525a998f0d7d1c',
}
TARGET_SHA256 = {
    'x64': 'a997bd3775cd76e40b08089ad6fcddc6f0f873fcc660901f278bffedbae49984',
    'x86': '842525b1f9b881cee8f43e07d3545bee183514f1dfb9f2294eb0ea86ca0a8274',
}
PLAN_SHA256 = {
    'x64': 'fc1ff36bcfa1bba926cf792a0e62ec619aaaa21866f424a19cbe4d2bb07c59f8',
    'x86': 'cb58065844546c757aba77fcb6b23b4fc6532196aa72edd2dae6bb03da93167f',
}
LAYOUT = {
    'x64': {'module_bytes': 0x2A000, 'ascii': 0x24048, 'utf16': 0x24060,
            'fixed': 0x24090, 'readonly': 0x240A0, 'executable': 0x240A8},
    'x86': {'module_bytes': 0x22000, 'ascii': 0x1DE40, 'utf16': 0x1DE58,
            'fixed': 0x1DE88, 'readonly': 0x1DE98, 'executable': 0x1DE9C},
}
_BUFFER_FORMATS = {'ascii': (8, 1, True, 4), 'utf16': (16, 2, True, 12),
                   'fixed': (8, 1, False, 8)}
_INITIAL = {'ascii': b'old\0QRST', 'utf16': bytes.fromhex(
    '4f004c0044003dd842de0000adde1733183319331a331b331c331d331e331f33'),
    'fixed': b'FI\0XED!?'}
_SCHEMA = 'ct2trainer-owned-string/v1'


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def plan_fingerprint(plan):
    """Bind all behavior and identity; only two top-level display fields vary."""
    if type(plan) is not dict:
        raise ValueError('String gate requires a canonical owned plan')
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
        raise ValueError('String gate requires its exact owned CT and canonical six-record plan')
    return architecture


def _hash_file(path, maximum=None):
    digest = hashlib.sha256()
    size = 0
    with Path(path).open('rb') as stream:
        while block := stream.read(1024 * 1024):
            size += len(block)
            if maximum is not None and size > maximum:
                raise ValueError('Owned String target image exceeds its admission bound')
            digest.update(block)
    return digest.hexdigest()


def _admit_target(target, architecture):
    if target.name != PROCESS_NAME or _hash_file(target, 32 * 1024 * 1024) != TARGET_SHA256[architecture]:
        raise ValueError('String gate requires its byte-pinned independently owned target')
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
        raise ValueError('Owned String target PE architecture differs from its plan')


def _receive(child):
    received = queue.Queue(maxsize=1)
    def get():
        try:
            received.put(child.stdout.readline(16385))
        except Exception as exc:
            received.put(exc)
    threading.Thread(target=get, daemon=True, name='owned-string-json').start()
    try:
        value = received.get(timeout=5)
    except queue.Empty as exc:
        raise ValueError('Owned String target did not publish bounded JSON') from exc
    if isinstance(value, Exception):
        raise value
    if not value or len(value) > 16384:
        raise ValueError('Owned String output exceeds its bounded JSON contract')
    return json.loads(value)


def _command(child, command):
    child.stdin.write(command + '\n')
    child.stdin.flush()
    return _receive(child)


def _validate_metadata(value, pid, architecture):
    keys = {'schema', 'pid', 'pointer_bits', 'pe_machine', 'process_name',
            'module_base', 'module_bytes', 'page_bytes', 'buffers', 'readonly', 'executable'}
    bits = 64 if architecture == 'x64' else 32
    maximum = 0x7FFFFFFFFFFF if bits == 64 else 0xFFFFFFFF
    if (type(value) is not dict or set(value) != keys
            or value['schema'] != 'ct2trainer-owned-string-target/v1'
            or value['process_name'] != PROCESS_NAME
            or any(type(value[key]) is not int for key in
                   ('pid', 'pointer_bits', 'pe_machine', 'module_base', 'module_bytes', 'page_bytes'))
            or value['pid'] != pid or value['pointer_bits'] != bits
            or value['pe_machine'] != (0x8664 if bits == 64 else 0x14C)
            or value['module_bytes'] != LAYOUT[architecture]['module_bytes']
            or value['page_bytes'] != 4096
            or not 0 < value['module_base'] <= maximum - value['module_bytes']
            or value['module_base'] % 65536):
        raise ValueError('Owned String target identity or module metadata differs')
    base, end = value['module_base'], value['module_base'] + value['module_bytes']
    if type(value['buffers']) is not dict or set(value['buffers']) != set(_BUFFER_FORMATS):
        raise ValueError('Owned String buffer set differs')
    for name, (length, unit, terminated, tail) in _BUFFER_FORMATS.items():
        rva = LAYOUT[architecture][name]
        expected = {'address': base + rva, 'rva': rva, 'length': length, 'unit_bytes': unit,
                    'read_bytes': length * unit, 'zero_terminate': terminated,
                    'full_address': base + rva - 8, 'full_rva': rva - 8,
                    'full_bytes': length * unit + 16, 'before_address': base + rva - 8,
                    'before_rva': rva - 8, 'guard_bytes': 8,
                    'after_address': base + rva + length * unit,
                    'after_rva': rva + length * unit, 'tail_offset': tail}
        item = value['buffers'][name]
        if (type(item) is not dict or set(item) != set(expected)
                or any(type(item[key]) is not type(wanted) or item[key] != wanted
                       for key, wanted in expected.items())):
            raise ValueError('Owned String buffer layout differs')
    private = []
    for name, protection in (('readonly', 2), ('executable', 0x40)):
        item = value[name]
        expected = {'pointer_address': base + LAYOUT[architecture][name],
                    'pointer_rva': LAYOUT[architecture][name], 'read_bytes': 8,
                    'allocation_bytes': 4096, 'expected_protection': protection}
        if (type(item) is not dict or set(item) != {'address', *expected}
                or any(type(item[key]) is not int or item[key] != wanted
                       for key, wanted in expected.items())
                or type(item['address']) is not int
                or not 0 < item['address'] <= maximum - 4096
                or item['address'] % 4096
                or not (item['address'] + 4096 <= base or item['address'] >= end)):
            raise ValueError('Owned String private pointer metadata differs')
        private.append(item['address'])
    if abs(private[0] - private[1]) < 4096:
        raise ValueError('Owned String private allocations overlap')
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
            raise AssertionError('Owned String child did not exit normally')
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
    from .engine import NativeRuntimeError, TrainerEngine
    from .memory import ProcessMemory
    evidence, plan = run.evidence, run.plan
    architecture = run.architecture
    bits = 64 if architecture == 'x64' else 32
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
        for name, item in metadata['buffers'].items():
            region = reader._query(item['full_address'])
            if (int(region.State) != 0x1000 or int(region.Protect) != 4
                    or int(region.Type) != 0x1000000
                    or int(region.BaseAddress) > item['full_address']
                    or item['full_address'] + item['full_bytes'] > int(region.BaseAddress) + int(region.RegionSize)):
                raise AssertionError('Owned module String span is not wholly committed PAGE_READWRITE')
        for name in ('readonly', 'executable'):
            item = metadata[name]
            pointer = int.from_bytes(reader.read(item['pointer_address'], bits // 8), 'little')
            region = reader._query(item['address'])
            if (pointer != item['address'] or int(region.State) != 0x1000
                    or int(region.Type) != 0x20000 or int(region.Protect) != item['expected_protection']
                    or int(region.BaseAddress) != item['address']
                    or int(region.RegionSize) != item['allocation_bytes']):
                raise AssertionError('Independent private pointer or protection differs')
        run.engine.poll()
        if not run.engine.connected:
            raise AssertionError(run.engine.error or run.engine.status)
        if reader.identity != run.engine.memory.identity:
            raise AssertionError('Controller attached a different process identity')
        evidence['target_instances'].append({'metadata': metadata, 'identity': list(reader.identity)})
    def guards(metadata):
        for index, name in enumerate(('ascii', 'utf16', 'fixed')):
            item = metadata['buffers'][name]
            if (run.reader.read(item['before_address'], 8) != bytes(range(0xA0 + 0x10 * index, 0xA8 + 0x10 * index))
                    or run.reader.read(item['after_address'], 8) != bytes(range(0xA8 + 0x10 * index, 0xB0 + 0x10 * index))):
                raise AssertionError('Owned String guard bytes changed')
    def raw(metadata, name):
        item = metadata['buffers'][name]
        return run.reader.read(item['address'], item['read_bytes'])
    def snapshot(metadata):
        observed = _command(run.child, 'status')
        evidence['protocol_observations'].append(observed)
        if (type(observed) is not dict or set(observed) != {'schema', 'pid', 'sequence', 'buffers', 'readonly', 'executable'}
                or observed['schema'] != 'ct2trainer-owned-string-status/v1'
                or type(observed['pid']) is not int or observed['pid'] != run.child.pid
                or type(observed['sequence']) is not int or observed['sequence'] < 0
                or type(observed['buffers']) is not dict or set(observed['buffers']) != set(_BUFFER_FORMATS)):
            raise AssertionError('Owned String status contract differs')
        for name in _BUFFER_FORMATS:
            if raw(metadata, name).hex() != observed['buffers'][name]['value']:
                raise AssertionError('Target protocol and independent String readback differ')
        guards(metadata)
        return observed

    metadata = run.spawn()
    run.engine = TrainerEngine(plan, state_dir=run.state / 'state', process_lock_dir=run.state / 'shared',
        memory_factory=lambda name: ProcessMemory(name, pid=run.child.pid))
    connect(metadata)
    engine = run.engine
    guards(metadata)
    original = {name: raw(metadata, name) for name in _BUFFER_FORMATS}
    if original != _INITIAL:
        raise AssertionError('Owned initial String bytes differ from pinned fixture source')
    note('exact-child-image-identity-architecture-regions-rvas-and-sentinels')
    if (engine.read_value(1), engine.read_value(2), engine.read_value(3)) != ('old', 'OLD\U0001f642', 'FI\0XED!?'):
        raise AssertionError('ASCII, UTF16 surrogate or fixed embedded-zero read differs')
    note('real-ascii-utf16-surrogate-and-fixed-embedded-zero-reads')
    for value in ('abcdefgh', '\u00e4', 'a\0b', '\ud800'):
        try:
            engine.set_value(1, value)
        except NativeRuntimeError:
            pass
        else:
            raise AssertionError('Invalid String literal was accepted')
    if raw(metadata, 'ascii') != original['ascii'] or engine.blocked:
        raise AssertionError('Invalid literal changed bytes or poisoned clean refusal')
    note('invalid-encoding-length-and-nul-refuse-before-effect')
    evidence['target_write_actions_started'] = True
    evidence['target_writes'] = True
    if engine.set_value(1, 'x') != 'x' or raw(metadata, 'ascii') != b'x\0' + original['ascii'][2:]:
        raise AssertionError('ASCII precise prefix write differs')
    snapshot(metadata)
    note('ascii-precise-prefix-held-write-retains-declared-tail-and-guards')
    wide = '\u00c4\U0001f642'
    wanted = (wide + '\0').encode('utf-16-le')
    if engine.set_value(2, wide) != wide or raw(metadata, 'utf16') != wanted + original['utf16'][len(wanted):]:
        raise AssertionError('UTF16 precise prefix write differs')
    snapshot(metadata)
    note('utf16-units-surrogate-and-aligned-terminator-write-preserves-tail')
    if engine.set_value(3, 'A\0BCD123') != 'A\0BCD123' or raw(metadata, 'fixed') != b'A\0BCD123':
        raise AssertionError('Fixed literal String write differs')
    snapshot(metadata)
    note('fixed-literal-exact-units-including-embedded-zero')
    negative = {name: run.reader.read(metadata[name]['address'], 8) for name in ('readonly', 'executable')}
    for identifier in (4, 5):
        try:
            engine.set_value(identifier, 'x')
        except NativeRuntimeError as exc:
            if 'PAGE_READWRITE' not in str(exc):
                raise AssertionError('Wrong-protection refusal differs') from exc
        else:
            raise AssertionError('Wrong protection accepted a String write')
    for name, value in negative.items():
        if (run.reader.read(metadata[name]['address'], 8) != value
                or int(run.reader._query(metadata[name]['address']).Protect) != metadata[name]['expected_protection']):
            raise AssertionError('Refused String write changed bytes or protection')
    if engine.blocked:
        raise AssertionError('Clean wrong-protection refusal blocked controller')
    note('read-only-and-rwx-regions-refuse-without-changing-bytes-or-protection')
    for identifier in (1, 2, 3):
        if not engine.set_freeze(identifier):
            raise AssertionError('String freeze did not enroll')
    desires = {identifier: engine.frozen[identifier][1] for identifier in (1, 2, 3)}
    if desires != {1: b'x\0', 2: wanted, 3: b'A\0BCD123'}:
        raise AssertionError('Freeze stores a declared tail rather than actual literal prefix')
    before_tail = {name: raw(metadata, name) for name in _BUFFER_FORMATS}
    evidence['protocol_observations'].append(_command(run.child, 'mutate-tail'))
    changed_tail = {name: raw(metadata, name) for name in _BUFFER_FORMATS}
    for name, (_, unit, _, _) in _BUFFER_FORMATS.items():
        expected = bytearray(before_tail[name])
        expected[-unit] ^= 1
        if changed_tail[name] != bytes(expected):
            raise AssertionError('Owned target tail command did not make its exact local mutation')
    engine.poll()
    if (engine.blocked or raw(metadata, 'ascii') != changed_tail['ascii']
            or raw(metadata, 'utf16') != changed_tail['utf16'] or raw(metadata, 'fixed') != desires[3]):
        raise AssertionError(engine.error or 'Freeze changed an unowned tail or failed fixed last-byte repair')
    snapshot(metadata)
    note('freeze-preserves-new-unowned-tails-and-restores-fixed-owned-last-byte')
    before_prefix = {name: raw(metadata, name) for name in _BUFFER_FORMATS}
    evidence['protocol_observations'].append(_command(run.child, 'mutate-prefix'))
    for name, (_, unit, _, _) in _BUFFER_FORMATS.items():
        if raw(metadata, name) != b'M' + b'\0' * (unit - 1) + before_prefix[name][unit:]:
            raise AssertionError('Owned target prefix command did not make its exact local mutation')
    engine.poll()
    if (engine.blocked or raw(metadata, 'ascii') != desires[1] + changed_tail['ascii'][len(desires[1]):]
            or raw(metadata, 'utf16') != desires[2] + changed_tail['utf16'][len(desires[2]):]
            or raw(metadata, 'fixed') != desires[3]):
        raise AssertionError(engine.error or 'Fresh held String freeze prefix repair differs')
    snapshot(metadata)
    note('fresh-held-freeze-repairs-owned-prefix-only-with-independent-readback')
    try:
        engine.set_value(6, '17')
    except NativeRuntimeError as exc:
        if 'overlaps' not in str(exc):
            raise AssertionError('Frozen prefix overlap refusal differs') from exc
    else:
        raise AssertionError('Overlapping numeric write was accepted')
    if engine.blocked or not raw(metadata, 'ascii').startswith(desires[1]):
        raise AssertionError('Overlap refusal changed prefix or blocked clean controller')
    note('frozen-prefix-overlap-refuses-before-effect')
    if engine.set_value(1, 'longer') != 'longer' or engine.frozen[1][1] != b'longer\0':
        raise AssertionError('Apply did not update variable-length freeze intent')
    new_ascii = raw(metadata, 'ascii')
    evidence['protocol_observations'].append(_command(run.child, 'mutate-prefix'))
    engine.poll()
    if engine.blocked or raw(metadata, 'ascii') != new_ascii:
        raise AssertionError(engine.error or 'Updated freeze intent replayed a stale prefix')
    snapshot(metadata)
    note('apply-updates-variable-length-freeze-intent-without-stale-tail-replay')
    for identifier in (1, 2, 3):
        if engine.set_freeze(identifier, False) is not False:
            raise AssertionError('String unfreeze did not confirm OFF')
    debug = engine.hook_coordinator.last_observation
    if not debug.get('thread_contexts'):
        raise AssertionError('No actual held debug-event evidence')
    evidence['held_debugger_evidence'] = debug
    markers = (engine.store.lock, engine.store.session, engine.store.process_lock)
    run.close_engine()
    if any(path is not None and path.exists() for path in markers):
        raise AssertionError('Normal close retained an ownership marker')
    if raw(metadata, 'ascii') != new_ascii:
        raise AssertionError('Close replayed or undid a manual String value')
    run.close_reader()
    run.engine = TrainerEngine(plan, state_dir=run.state / 'state', process_lock_dir=run.state / 'shared',
        memory_factory=lambda name: ProcessMemory(name, pid=run.child.pid))
    connect(metadata)
    engine = run.engine
    if engine.desired or engine.frozen or raw(metadata, 'ascii') != new_ascii:
        raise AssertionError('Live controller restart saved or replayed String values/freezes')
    note('live-controller-restart-drops-freeze-and-never-saves-or-replays-string-values')
    first_identity = run.reader.identity
    run.close_reader()
    run.quit_child()
    engine.poll()
    if engine.memory is not None or engine.desired or engine.frozen:
        raise AssertionError('Target death retained active String state')
    metadata = run.spawn()
    connect(metadata)
    if (run.reader.identity == first_identity or engine.frozen or engine.desired
            or any(raw(metadata, name) != _INITIAL[name] for name in _BUFFER_FORMATS)):
        raise AssertionError('Target restart reused identity or replayed String state')
    note('target-pid-creation-restart-attaches-fresh-without-value-or-freeze-replay')
    guards(metadata)
    markers = (engine.store.lock, engine.store.session, engine.store.process_lock)
    run.close_engine()
    if any(path is not None and path.exists() for path in markers):
        raise AssertionError('Final close retained an ownership marker')
    evidence['owned_markers_absent'] = True
    run.close_reader()
    run.quit_child()
    note('normal-final-close-sentinels-markers-and-owned-target-exit')


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
        state = Path(tempfile.mkdtemp(prefix='ct2trainer-owned-string-'))
        evidence['state_directory'] = str(state)
        run = _OwnedRun(plan, target, architecture, evidence, state)
        _exercise(run)
        if len(evidence['checks']) != 14:
            raise AssertionError('Owned String gate did not complete exactly fourteen checks')
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
