"""AP-02 lane (Frozen-Global-Gates): unit tests for the owned Global probe gate.

The real gate (ct2trainer.native.global_probe.run_probe) spawns the
byte-pinned NativeGlobalFixture targets. These tests pin the gate's
admission, validation and cleanup contracts without spawning targets:
plan/pin binding, PE admission, metadata/status contracts, bounded JSON
receive, owned-child cleanup authority and the failed-report guarantees.
No CE implementation input is used; the pinned CT/target/source files are
verified against the module pins.
"""
import copy
import hashlib
import io
import json
import shutil
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

_TESTS_DIR = str(Path(__file__).resolve().parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

import xml.etree.ElementTree as ET

from ct2trainer.native import global_probe as gp
from ct2trainer.native.compiler import NativeCompileError, compile_table, validate_plan
from ct2trainer.native.engine import NativeRuntimeError, validate_plan as validate_plan_engine

FIXTURE_DIR = Path(__file__).resolve().parent / 'fixtures' / 'global_alloc'
X64_CT = FIXTURE_DIR / 'global_alloc_x64.ct'
X86_CT = FIXTURE_DIR / 'global_alloc_x86.ct'
TARGET_C = Path(__file__).resolve().parent / 'windows' / 'global_fixture' / 'global_target.c'

X64_META = {'base': 140698509246464, 'module_bytes': 167936,
            'marker_rva': 99152, 'probe_rva': 4448, 'bits': 64, 'machine': 0x8664}
X86_META = {'base': 9699328, 'module_bytes': 139264,
            'marker_rva': 90512, 'probe_rva': 4400, 'bits': 32, 'machine': 0x14C}


def _sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _synthetic_pe(machine=0x8664, magic=0x20B, *, dos=b'MZ', e_lfanew=0x40, size=None):
    """Minimal bounded PE stub: 64-byte DOS header, PE header at e_lfanew."""
    if size is None:
        size = e_lfanew + 26 + 16
    data = bytearray(size)
    data[:2] = dos
    struct.pack_into('<I', data, 60, e_lfanew)
    pe = bytearray(26)
    pe[0:4] = b'PE\0\0'
    struct.pack_into('<H', pe, 4, machine)
    struct.pack_into('<H', pe, 24, magic)
    copied = min(len(pe), size - e_lfanew)
    data[e_lfanew:e_lfanew + copied] = pe[:copied]
    return bytes(data)


def _x64_plan():
    return compile_table(X64_CT, gp.PROCESS_NAME, architecture='x64')


def _valid_metadata(meta, pid):
    arch = 'x64' if meta['bits'] == 64 else 'x86'
    return {
        'schema': gp.METADATA_SCHEMA, 'pid': pid,
        'pointer_bits': meta['bits'], 'pe_machine': meta['machine'],
        'process_name': gp.PROCESS_NAME, 'module_base': meta['base'],
        'module_bytes': meta['module_bytes'], 'page_bytes': 4096,
        'marker_rva': meta['marker_rva'], 'marker_bytes': gp.MARKER_BYTES.hex(),
        'probe_rva': meta['probe_rva'], 'probe_bytes': gp.PROBE_PROLOGUE[arch].hex(),
        'original_value': gp.ORIGINAL_PROBE_VALUE,
    }


class PlanPinTests(unittest.TestCase):
    """The two pinned CTs compile to the pinned canonical plans."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.plan = _x64_plan()
        cls.plan_x86 = compile_table(X86_CT, gp.PROCESS_NAME, architecture='x86')

    def test_pinned_cts_compile_to_pinned_canonical_plans(self):
        for arch, plan, ct in (('x64', self.plan, X64_CT),
                               ('x86', self.plan_x86, X86_CT)):
            with self.subTest(architecture=arch):
                self.assertEqual(_sha256_file(ct), gp.CT_SHA256[arch])
                self.assertEqual(gp.plan_fingerprint(plan), gp.PLAN_SHA256[arch])
                self.assertEqual(gp.validate_fixture_plan(plan), arch)
                self.assertEqual(plan['table_sha256'], gp.CT_SHA256[arch])
                self.assertEqual(plan['process_name'], gp.PROCESS_NAME)
                self.assertEqual(plan['schema'], 2)
                self.assertEqual(plan['selected_ids'], [1, 2])
                self.assertEqual(len(plan['entries']), 2)
                entry1, entry2 = plan['entries']
                self.assertEqual(entry1['kind'], 'script')
                self.assertTrue(entry1['supported'])
                self.assertTrue(entry1['selected'])
                self.assertIn('global_program', entry1)
                self.assertEqual(entry2['kind'], 'value')
                self.assertEqual(entry2['address'], 'globalvalue')
                self.assertEqual(entry2['variable_type'], '4 Bytes')

    def test_fixture_source_is_byte_pinned(self):
        self.assertEqual(_sha256_file(TARGET_C), gp.FIXTURE_SOURCE_SHA256)

    def test_display_only_plan_changes_are_admitted_and_entry_changes_are_not(self):
        changed = copy.deepcopy(self.plan)
        changed['title'] = 'Changed title'
        changed['source_name'] = 'changed.ct'
        self.assertEqual(gp.validate_fixture_plan(changed), 'x64')
        mutated = copy.deepcopy(self.plan)
        mutated['entries'][0]['label'] = 'Changed label'
        with self.assertRaisesRegex(ValueError, 'canonical two-record plan'):
            gp.validate_fixture_plan(mutated)

    def test_identity_selection_and_architecture_mutations_are_refused(self):
        cases = [
            ('table_sha256',
             lambda p: p.update(table_sha256='0' * 64),
             NativeRuntimeError,
             'Trainer identity differs from its source, selection or target architecture.'),
            ('process_name',
             lambda p: p.update(process_name='other.exe'),
             NativeRuntimeError,
             'Global metadata differs from its original source and target context.'),
            ('selected_ids',
             lambda p: p.update(selected_ids=[1]),
             NativeRuntimeError,
             'Selected record flags do not match selected IDs.'),
            ('selected_flag',
             lambda p: p['entries'][1].update(selected=False),
             NativeRuntimeError,
             'Selected record flags do not match selected IDs.'),
            ('schema_1',
             lambda p: p.update(schema=1),
             NativeRuntimeError,
             'Legacy schema 1 cannot override its x64 target architecture.'),
            ('foreign_architecture',
             lambda p: p['target_architecture'].update(machine='arm64'),
             NativeRuntimeError,
             'Target architecture must be explicitly x86 or x64.'),
            ('untrusted_extra_authority',
             lambda p: p.update(untrusted_extra_authority=True),
             ValueError,
             'Global gate requires its exact owned CT and canonical two-record plan'),
            ('trainer_id',
             lambda p: p.update(trainer_id='f' * 16),
             NativeRuntimeError,
             'Trainer identity differs from its source, selection or target architecture.'),
            ('counts',
             lambda p: p['counts'].update(total=99),
             ValueError,
             'Global gate requires its exact owned CT and canonical two-record plan'),
        ]
        for name, mutate, exc_type, message in cases:
            with self.subTest(mutation=name):
                mutated = copy.deepcopy(self.plan)
                mutate(mutated)
                with self.assertRaises(exc_type) as ctx:
                    gp.validate_fixture_plan(mutated)
                self.assertIn(message, str(ctx.exception))

    def test_plan_fingerprint_ignores_only_display_fields(self):
        base = gp.plan_fingerprint(self.plan)
        changed = copy.deepcopy(self.plan)
        changed['title'] = 'X'
        changed['source_name'] = 'Y.ct'
        self.assertEqual(gp.plan_fingerprint(changed), base)
        with self.assertRaisesRegex(ValueError, 'canonical owned plan'):
            gp.plan_fingerprint(['not', 'a', 'dict'])


class ReportGuaranteeTests(unittest.TestCase):
    """run_probe reserves a failed report before anything may be spawned."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='native-global-probe-r-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.report = self.root / 'probe-report.json'
        self.plan = _x64_plan()

    def _failed_evidence(self):
        return json.loads(self.report.read_text(encoding='utf-8'))

    def test_invalid_plan_writes_failed_report_before_any_child(self):
        mutated = copy.deepcopy(self.plan)
        mutated['schema'] = 1
        spawned = []

        def fake_popen(*args, **kwargs):
            spawned.append((args, kwargs))
            raise AssertionError('child must not be spawned')

        with patch.object(gp.subprocess, 'Popen', side_effect=fake_popen):
            with self.assertRaises(Exception):
                gp.run_probe(mutated, self.root / gp.PROCESS_NAME, self.report)
        self.assertEqual(spawned, [])
        evidence = self._failed_evidence()
        self.assertEqual(evidence['status'], 'failed')
        self.assertFalse(evidence['target_spawned'])
        self.assertEqual(evidence['owned_child_pids'], [])
        self.assertEqual(evidence['ce_implementation_inputs'], [])

    def test_preexisting_report_is_refused_before_validation(self):
        self.report.write_bytes(b'{"pre":1}\n')
        calls = []

        def fake_validate(plan):
            calls.append(plan)
            return 'x64'

        with patch.object(gp, 'validate_fixture_plan', side_effect=fake_validate):
            with self.assertRaises(FileExistsError):
                gp.run_probe(self.plan, self.root / gp.PROCESS_NAME, self.report)
        self.assertEqual(calls, [])
        self.assertEqual(self.report.read_bytes(), b'{"pre":1}\n')

    def test_wrong_hash_target_refused_with_failed_report_and_no_child(self):
        target = self.root / gp.PROCESS_NAME
        target.write_bytes(b'not the pinned image')
        spawned = []
        with patch.object(gp.subprocess, 'Popen',
                          side_effect=lambda *a, **k: spawned.append(1)):
            with self.assertRaisesRegex(ValueError, 'byte-pinned'):
                gp.run_probe(self.plan, target, self.report)
        self.assertEqual(spawned, [])
        evidence = self._failed_evidence()
        self.assertEqual(evidence['status'], 'failed')
        self.assertFalse(evidence['target_spawned'])

    def test_missing_target_reports_failed_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            gp.run_probe(self.plan, self.root / gp.PROCESS_NAME, self.report)
        evidence = self._failed_evidence()
        self.assertEqual(evidence['status'], 'failed')
        self.assertIn('FileNotFoundError', evidence['error'])

    def test_pe_architecture_mismatch_refused_even_with_matching_hash(self):
        target = self.root / gp.PROCESS_NAME
        target.write_bytes(_synthetic_pe(0x14C, 0x10B))  # x86 image, x64 plan
        spawned = []
        with patch.object(gp, '_hash_file', return_value=gp.TARGET_SHA256['x64']), \
             patch.object(gp.subprocess, 'Popen',
                          side_effect=lambda *a, **k: spawned.append(1)):
            with self.assertRaisesRegex(ValueError, 'architecture differs'):
                gp.run_probe(self.plan, target, self.report)
        self.assertEqual(spawned, [])
        self.assertEqual(self._failed_evidence()['status'], 'failed')


class AdmissionTests(unittest.TestCase):
    """The independent bounded PE re-check precedes any child creation."""

    def test_pe_header_bounds_and_magic_checks(self):
        cases = [
            ('valid-x64', _synthetic_pe(0x8664, 0x20B), 'x64', None),
            ('valid-x86', _synthetic_pe(0x14C, 0x10B), 'x86', None),
            ('x86-image-for-x64-plan', _synthetic_pe(0x14C, 0x10B), 'x64',
             'architecture differs'),
            ('no-mz', _synthetic_pe(0x8664, 0x20B, dos=b'XX'), 'x64',
             'no bounded PE header'),
            ('short-dos', b'MZ' + b'\x00' * 8, 'x64', 'no bounded PE header'),
            ('truncated-59', bytes(range(59)), 'x64', 'no bounded PE header'),
            ('offset-too-large', _synthetic_pe(0x8664, 0x20B, e_lfanew=0x40000000,
                                              size=0x200), 'x64',
             'PE header offset is invalid'),
            ('offset-zero', b'MZ' + b'\x00' * 58 + struct.pack('<I', 0)
             + b'\x00' * 0x3F00, 'x64', 'PE header offset is invalid'),
            ('short-pe', _synthetic_pe(0x8664, 0x20B, size=0x40 + 20), 'x64',
             'architecture differs'),
        ]
        for name, image, arch, expected in cases:
            with self.subTest(case=name):
                case_dir = Path(tempfile.gettempdir()) / (
                    'native-global-probe-pe-' + name)
                case_dir.mkdir(parents=True, exist_ok=True)
                target = case_dir / gp.PROCESS_NAME
                target.write_bytes(image)
                try:
                    with patch.object(gp, '_hash_file',
                                      return_value=gp.TARGET_SHA256[arch]):
                        try:
                            gp._admit_target(target, arch)
                        except ValueError as exc:
                            message = str(exc)
                        else:
                            message = None
                    if expected is None:
                        self.assertIsNone(message, message)
                    else:
                        self.assertIsNotNone(message, 'expected refusal for ' + name)
                        self.assertIn(expected, message)
                finally:
                    shutil.rmtree(case_dir, ignore_errors=True)

    def test_wrong_target_name_is_refused_before_any_header_check(self):
        target = Path(tempfile.gettempdir()) / 'foreign.exe'
        target.write_bytes(_synthetic_pe(0x8664, 0x20B))
        try:
            with patch.object(gp, '_hash_file', return_value=gp.TARGET_SHA256['x64']):
                with self.assertRaisesRegex(ValueError, 'byte-pinned'):
                    gp._admit_target(target, 'x64')
        finally:
            target.unlink(missing_ok=True)


class MetadataContractTests(unittest.TestCase):
    """The child metadata and status JSON are bound to the pinned contract."""

    def test_metadata_is_accepted_and_any_drift_is_refused(self):
        for meta in (X64_META, X86_META):
            arch = 'x64' if meta['bits'] == 64 else 'x86'
            with self.subTest(architecture=arch):
                valid = _valid_metadata(meta, 42)
                self.assertEqual(gp._validate_metadata(valid, 42, arch), valid)
                maximum = 0x7FFFFFFFFFFF if meta['bits'] == 64 else 0xFFFFFFFF
                mutations = [
                    ('schema', lambda d: d.update(schema='other')),
                    ('process_name', lambda d: d.update(process_name='Other.exe')),
                    ('pid-mismatch', lambda d: d.update(pid=99)),
                    ('pointer_bits',
                     lambda d: d.update(
                         pointer_bits=32 if meta['bits'] == 64 else 64)),
                    ('pe_machine', lambda d: d.update(
                        pe_machine=0x14C if meta['machine'] == 0x8664 else 0x8664)),
                    ('module_bytes-zero', lambda d: d.update(module_bytes=0)),
                    ('page_bytes', lambda d: d.update(page_bytes=8192)),
                    ('base-misaligned', lambda d: d.update(module_base=meta['base'] + 1)),
                    ('base-overflow', lambda d: d.update(
                        module_base=maximum - meta['module_bytes'] + 1)),
                    ('marker-out-of-range', lambda d: d.update(marker_rva=meta['module_bytes'])),
                    ('probe-zero', lambda d: d.update(probe_rva=0)),
                    ('marker-exceeds-image', lambda d: d.update(
                        marker_rva=meta['module_bytes'] - 4)),
                    ('marker-bytes', lambda d: d.update(marker_bytes='deadbeef')),
                    ('probe-bytes', lambda d: d.update(probe_bytes='00' * 10)),
                    ('original-value', lambda d: d.update(original_value=1)),
                    ('missing-key', lambda d: d.pop('page_bytes')),
                    ('extra-key', lambda d: d.update(extra=1)),
                    ('overlapping-sentinels', lambda d: d.update(
                        probe_rva=meta['marker_rva'] + 8)),
                    ('non-dict', lambda d: d),
                ]
                for name, mutate in mutations:
                    with self.subTest(mutation=name):
                        drifted = copy.deepcopy(valid)
                        if name == 'non-dict':
                            drifted = list(drifted)
                        else:
                            mutate(drifted)
                        with self.assertRaisesRegex(
                                ValueError,
                                'differs|sentinels exceed the module image'
                                '|marker and probe entry overlap'):
                            gp._validate_metadata(drifted, 42, arch)

    def test_status_contract_is_strict(self):
        valid = {'schema': gp.STATUS_SCHEMA, 'pid': 42, 'sequence': 7,
                 'probe_value': gp.ORIGINAL_PROBE_VALUE}
        self.assertEqual(gp._validate_status(valid, 42), valid)
        mutations = [
            ('schema', lambda d: d.update(schema='other')),
            ('pid-mismatch', lambda d: d.update(pid=43)),
            ('sequence-zero', lambda d: d.update(sequence=0)),
            ('sequence-negative', lambda d: d.update(sequence=-1)),
            ('sequence-str', lambda d: d.update(sequence='7')),
            ('probe-negative', lambda d: d.update(probe_value=-1)),
            ('probe-overflow', lambda d: d.update(probe_value=0x100000000)),
            ('probe-str', lambda d: d.update(probe_value='5')),
            ('extra-key', lambda d: d.update(extra=1)),
            ('missing-key', lambda d: d.pop('probe_value')),
        ]
        for name, mutate in mutations:
            with self.subTest(mutation=name):
                drifted = copy.deepcopy(valid)
                mutate(drifted)
                with self.assertRaisesRegex(ValueError, 'status contract differs'):
                    gp._validate_status(drifted, 42)
        with self.assertRaisesRegex(ValueError, 'status contract differs'):
            gp._validate_status([1, 2, 3], 42)


class ReceiveAndCleanupTests(unittest.TestCase):
    """Bounded JSON receive and cleanup authority for owned children only."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='native-global-probe-c-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.plan = _x64_plan()

    def _owned_run(self):
        evidence = {'target_spawned': False, 'owned_child_pids': [],
                    'forced_owned_child_exit': []}
        run = gp._OwnedRun(self.plan, self.root / gp.PROCESS_NAME, 'x64',
                           evidence, self.root / 'state')
        return run, evidence

    def test_receive_enforces_bounded_json_contract(self):
        payload = {'schema': gp.STATUS_SCHEMA, 'pid': 42, 'sequence': 1,
                   'probe_value': 5}
        child = Mock(stdout=io.StringIO(json.dumps(payload) + '\n'))
        self.assertEqual(gp._receive(child), payload)

        child = Mock(stdout=io.StringIO(''))
        with self.assertRaisesRegex(ValueError, 'bounded JSON contract'):
            gp._receive(child)

        child = Mock(stdout=io.StringIO('x' * 16385))
        with self.assertRaisesRegex(ValueError, 'bounded JSON contract'):
            gp._receive(child)

        def broken(*args):
            raise OSError('pipe broken')

        child = Mock(stdout=Mock(readline=broken))
        with self.assertRaises(OSError):
            gp._receive(child)

    def test_spawn_failure_kills_only_the_owned_child(self):
        run, evidence = self._owned_run()
        bad_meta = {'schema': gp.METADATA_SCHEMA, 'pid': 999}
        child = Mock()
        child.pid = 17
        child.stdout = io.StringIO(json.dumps(bad_meta) + '\n')
        child.poll.return_value = None
        child.wait.return_value = 0
        with patch.object(gp, '_admit_target', lambda *a, **k: None), \
             patch.object(gp.subprocess, 'Popen', return_value=child) as popen:
            with self.assertRaisesRegex(ValueError, 'metadata differs'):
                run.spawn()
        self.assertEqual(popen.call_count, 1)
        self.assertTrue(evidence['target_spawned'])
        self.assertEqual(evidence['owned_child_pids'], [17])
        self.assertIsNone(run.reader)
        self.assertIsNone(run.engine)
        with self.assertRaisesRegex(AssertionError, 'forced exit'):
            run.cleanup()
        self.assertEqual(child.kill.call_count, 1)
        self.assertEqual(child.wait.call_count, 1)
        self.assertEqual(evidence['forced_owned_child_exit'], [17])

    def test_unconfirmed_controller_close_fails_the_gate(self):
        run, _ = self._owned_run()
        engine = Mock()
        engine.close.return_value = False
        engine.error = ('Shared globals and their retired consumers remain '
                        'owned until exact target exit; retain uncertain journal')
        run.engine = engine
        with self.assertRaisesRegex(AssertionError, 'retain uncertain journal'):
            run.close_engine()
        self.assertEqual(engine.close.call_count, 1)
        self.assertIs(run.engine, engine)

    def test_cleanup_authority_is_limited_to_owned_children(self):
        run, _ = self._owned_run()
        with self.assertRaisesRegex(AssertionError, 'No owned child is available'):
            run.quit_child()
        foreign = Mock()
        run.child = foreign
        with self.assertRaisesRegex(AssertionError, 'No owned child is available'):
            run.quit_child()
        self.assertEqual(foreign.stdin.write.call_count, 0)

        empty = self.root / 'empty'
        empty.mkdir()
        gp._assert_no_files(empty, 'process lock directory')
        leftover = self.root / 'leftover'
        leftover.mkdir()
        (leftover / 'state.lock').write_bytes(b'x')
        with self.assertRaisesRegex(AssertionError,
                                    'retained ownership markers in process lock directory'):
            gp._assert_no_files(leftover, 'process lock directory')


# WP-20: per-record containment of '@@' (NASM current-address cursor) and
# AddressExpressionError-style failures in globalalloc sources.  A malformed
# record must be blocked with a named reason; it must never abort the table.
CURSOR_OK_SOURCE = (
    "[ENABLE]\n"
    "label(done)\n"
    "globalalloc(cursorval,8)\n"
    "cursorval:\n"
    "dd #7\n"
    "@@:\n"
    "dd #8\n"
    "alloc(cave,1000)\n"
    "cave:\n"
    "mov rcx,cursorval\n"
    "mov eax,[rcx]\n"
    "jmp done\n"
    "0x1000:\n"
    "jmp cave\n"
    "done:\n"
    "[DISABLE]\n"
    "0x1000:\n"
    "db B8 01 00 00 00\n"
    "dealloc(cave)\n"
    "dealloc(cursorval)\n"
)
CURSOR_BAD_SIZE_SOURCE = (
    "[ENABLE]\n"
    "globalalloc(badsize,@@)\n"
    "alloc(cave,1000)\n"
    "cave:\n"
    "mov rcx,100\n"
    "[DISABLE]\n"
    "dealloc(cave)\n"
    "dealloc(badsize)\n"
)
CURSOR_BAD_CURSOR_SOURCE = (
    "[ENABLE]\n"
    "globalalloc(badcursor,8)\n"
    "badcursor:\n"
    "dd #1\n"
    "@@+1:\n"
    "dd #2\n"
    "alloc(cave,1000)\n"
    "cave:\n"
    "mov rcx,badcursor\n"
    "[DISABLE]\n"
    "dealloc(cave)\n"
    "dealloc(badcursor)\n"
)


def _cursor_ct(path, scripts):
    """Write a minimal two-entry CT and compile it against the probe process."""
    root = ET.Element('CheatTable', CheatEngineTableVersion='45')
    entries_el = ET.SubElement(root, 'CheatEntries')
    for index, text in enumerate(scripts, 1):
        entry = ET.SubElement(entries_el, 'CheatEntry')
        for key, value in {'ID': str(index), 'Description': f'W1B {index}',
                           'VariableType': 'Auto Assembler Script',
                           'AssemblerScript': text}.items():
            ET.SubElement(entry, key).text = value
    path.write_bytes(ET.tostring(root, encoding='utf-8', xml_declaration=True))
    return compile_table(path, gp.PROCESS_NAME)


class CursorContainmentTests(unittest.TestCase):
    """WP-20: '@@' failures stay per-record; the table still compiles."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='native-global-wp20-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_mixed_table_blocks_only_the_malformed_record(self):
        for bad_source, needle in (
                (CURSOR_BAD_SIZE_SOURCE,
                 'Global declaration size is not a bounded integer'),
                (CURSOR_BAD_CURSOR_SOURCE,
                 'current-address cursor')):
            with self.subTest(reason=needle):
                plan = _cursor_ct(self.root / 'mixed.ct',
                                  (CURSOR_OK_SOURCE, bad_source))
                good = plan['entries'][0]
                bad = plan['entries'][1]
                self.assertTrue(good['supported'])
                self.assertEqual(good['kind'], 'script')
                self.assertIn('global_program', good)
                self.assertFalse(bad['supported'])
                self.assertEqual(bad['kind'], 'blocked')
                self.assertIn(needle, bad['reason'])
                self.assertNotIn('enable', bad)
                self.assertNotIn('disable', bad)
                self.assertEqual(bad['provides'], [])
                self.assertEqual(plan['counts']['blocked'], 1)
                self.assertEqual(plan['counts']['supported'], 1)
                # Both plan validators admit the mixed plan unchanged.
                validate_plan(plan)
                validate_plan_engine(plan)

    def test_cursor_record_plan_metadata_round_trips_through_validators(self):
        plan = _cursor_ct(self.root / 'cursor.ct', (CURSOR_OK_SOURCE,))
        entry = plan['entries'][0]
        self.assertTrue(entry['supported'])
        profile = entry['global_program']
        # The '@@:' line is part of the verified source and contributes the
        # second word to the initializer; no plan operation is emitted for it.
        self.assertIn('@@:', profile['source'])
        self.assertEqual(profile['globals'][0]['initializer'], '0700000008000000')
        self.assertNotIn('@@:', profile['consumer_source'])
        self.assertEqual(entry['provides'], ['cursorval'])
        validate_plan(plan)
        validate_plan_engine(plan)
        # Forged metadata in the '@@' plan is rejected by both validators.
        for tamper in (
                lambda p: p['entries'][0]['global_program']['globals'][0].__setitem__(
                    'size', 12),
                lambda p: p['entries'][0]['global_program']['globals'][0].__setitem__(
                    'initializer', '00' * 8),
                lambda p: p['entries'][0]['global_program'].__setitem__(
                    'consumer_source',
                    p['entries'][0]['global_program']['consumer_source'].replace(
                        'mov rcx,cursorval', 'mov rcx,foreign'))):
            with self.subTest():
                forged = copy.deepcopy(plan)
                tamper(forged)
                with self.assertRaises(NativeCompileError):
                    validate_plan(forged)
                with self.assertRaises(NativeRuntimeError):
                    validate_plan_engine(forged)


if __name__ == '__main__':
    unittest.main()
