"""Unit tests for the owned code-patch probe gate.

The real gate (ct2trainer.native.codepatch_probe.run_probe) spawns the
byte-pinned NativeCodePatchFixture targets. These tests pin the gate's
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

from ct2trainer.native import codepatch_probe as cp
from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import NativeRuntimeError

FIXTURE_DIR = Path(__file__).resolve().parent / 'fixtures' / 'codepatch'
X64_CT = FIXTURE_DIR / 'codepatch_x64.ct'
X86_CT = FIXTURE_DIR / 'codepatch_x86.ct'
TARGET_C = Path(__file__).resolve().parent / 'windows' / 'codepatch_fixture' / 'codepatch_target.c'

X64_META = {'base': 140698509246464, 'module_bytes': 167936,
            'marker_rva': 99152, 'data_a_rva': 143360, 'data_b_rva': 143368,
            'overlap_rva': 143364, 'probe_rva': 4592, 'bits': 64, 'machine': 0x8664}
X86_META = {'base': 9699328, 'module_bytes': 139264,
            'marker_rva': 90512, 'data_a_rva': 118784, 'data_b_rva': 118792,
            'overlap_rva': 118788, 'probe_rva': 4512, 'bits': 32, 'machine': 0x14C}


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
    return compile_table(X64_CT, cp.PROCESS_NAME, architecture='x64')


def _valid_metadata(meta, pid):
    arch = 'x64' if meta['bits'] == 64 else 'x86'
    return {
        'schema': cp.METADATA_SCHEMA, 'pid': pid,
        'pointer_bits': meta['bits'], 'pe_machine': meta['machine'],
        'process_name': cp.PROCESS_NAME, 'module_base': meta['base'],
        'module_bytes': meta['module_bytes'], 'page_bytes': 4096,
        'marker_rva': meta['marker_rva'], 'marker_bytes': cp.MARKER_BYTES.hex(),
        'data_a_rva': meta['data_a_rva'], 'data_a_bytes': cp.BASELINE_A.hex(),
        'data_b_rva': meta['data_b_rva'], 'data_b_bytes': cp.BASELINE_B.hex(),
        'overlap_rva': meta['overlap_rva'], 'overlap_bytes': cp.BASELINE_A[4:8].hex(),
        'probe_rva': meta['probe_rva'], 'probe_bytes': cp.PROBE_PROLOGUE[arch].hex(),
        'original_value': cp.ORIGINAL_PROBE_VALUE,
    }


class PlanPinTests(unittest.TestCase):
    """The two pinned CTs compile to the pinned canonical plans."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.plan = _x64_plan()
        cls.plan_x86 = compile_table(X86_CT, cp.PROCESS_NAME, architecture='x86')

    def test_pinned_cts_compile_to_pinned_canonical_plans(self):
        for arch, plan, ct in (('x64', self.plan, X64_CT),
                               ('x86', self.plan_x86, X86_CT)):
            with self.subTest(architecture=arch):
                self.assertEqual(_sha256_file(ct), cp.CT_SHA256[arch])
                self.assertEqual(cp.plan_fingerprint(plan), cp.PLAN_SHA256[arch])
                self.assertEqual(cp.validate_fixture_plan(plan), arch)
                self.assertEqual(plan['table_sha256'], cp.CT_SHA256[arch])
                self.assertEqual(plan['process_name'], cp.PROCESS_NAME)
                self.assertEqual(plan['schema'], 2)
                self.assertEqual(plan['selected_ids'], [cp.DATA_A_ID, cp.PROBE_ID,
                                                        cp.DATA_B_ID, cp.OVERLAP_ID])
                self.assertEqual(len(plan['entries']), 4)
                addresses = {
                    'x64': ('NativeCodePatchFixture.exe+0x23000',
                            'NativeCodePatchFixture.exe+0x11F0',
                            'NativeCodePatchFixture.exe+0x23008',
                            'NativeCodePatchFixture.exe+0x23004'),
                    'x86': ('NativeCodePatchFixture.exe+0x1D000',
                            'NativeCodePatchFixture.exe+0x11A0',
                            'NativeCodePatchFixture.exe+0x1D008',
                            'NativeCodePatchFixture.exe+0x1D004'),
                }[arch]
                for entry, address in zip(plan['entries'], addresses):
                    self.assertEqual(entry['kind'], 'code_patch')
                    self.assertTrue(entry['supported'])
                    self.assertTrue(entry['selected'])
                    self.assertEqual(entry['address'], address)
                    self.assertNotIn('global_program', entry)
                self.assertEqual(plan['entries'][0]['before'], '444154415f413031')
                self.assertEqual(plan['entries'][0]['actual'], '5041544348454430')
                self.assertEqual(plan['entries'][1]['before'],
                                 'b85d5c5b5ac3' if arch == 'x64' else '558becb85d5c5b5a5dc3')
                self.assertEqual(plan['entries'][1]['actual'],
                                 'b849484746c3' if arch == 'x64' else '558becb8494847465dc3')
                self.assertEqual(plan['entries'][2]['before'], '')
                self.assertEqual(plan['entries'][2]['actual'], '50415442')
                self.assertEqual(plan['entries'][3]['before'], '')
                self.assertEqual(plan['entries'][3]['actual'], '43303033')
                self.assertEqual(plan['counts'],
                                 {'total': 4, 'supported': 4, 'actionable': 0,
                                  'blocked': 0, 'headings': 0})

    def test_fixture_source_is_byte_pinned(self):
        self.assertEqual(_sha256_file(TARGET_C), cp.FIXTURE_SOURCE_SHA256)

    def test_display_only_plan_changes_are_admitted_and_entry_changes_are_not(self):
        changed = copy.deepcopy(self.plan)
        changed['title'] = 'Changed title'
        changed['source_name'] = 'changed.ct'
        self.assertEqual(cp.validate_fixture_plan(changed), 'x64')
        mutated = copy.deepcopy(self.plan)
        mutated['entries'][0]['label'] = 'Changed label'
        with self.assertRaisesRegex(ValueError, 'canonical four-record plan'):
            cp.validate_fixture_plan(mutated)

    def test_identity_selection_and_architecture_mutations_are_refused(self):
        cases = [
            ('table_sha256',
             lambda p: p.update(table_sha256='0' * 64),
             NativeRuntimeError,
             'Trainer identity differs from its source, selection or target architecture.'),
            ('process_name',
             lambda p: p.update(process_name='other.exe'),
             NativeRuntimeError,
             'Trainer identity differs from its source, selection or target architecture.'),
            ('selected_ids',
             lambda p: p.update(selected_ids=[cp.DATA_A_ID]),
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
             'Code-patch gate requires its exact owned CT and canonical four-record plan'),
            ('trainer_id',
             lambda p: p.update(trainer_id='f' * 16),
             NativeRuntimeError,
             'Trainer identity differs from its source, selection or target architecture.'),
            ('counts',
             lambda p: p['counts'].update(total=99),
             ValueError,
             'Code-patch gate requires its exact owned CT and canonical four-record plan'),
        ]
        for name, mutate, exc_type, message in cases:
            with self.subTest(mutation=name):
                mutated = copy.deepcopy(self.plan)
                mutate(mutated)
                with self.assertRaises(exc_type) as ctx:
                    cp.validate_fixture_plan(mutated)
                self.assertIn(message, str(ctx.exception))

    def test_plan_fingerprint_ignores_only_display_fields(self):
        base = cp.plan_fingerprint(self.plan)
        changed = copy.deepcopy(self.plan)
        changed['title'] = 'X'
        changed['source_name'] = 'Y.ct'
        self.assertEqual(cp.plan_fingerprint(changed), base)
        with self.assertRaisesRegex(ValueError, 'canonical owned plan'):
            cp.plan_fingerprint(['not', 'a', 'dict'])


class ReportGuaranteeTests(unittest.TestCase):
    """run_probe reserves a failed report before anything may be spawned."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='native-codepatch-probe-r-')
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

        with patch.object(cp.subprocess, 'Popen', side_effect=fake_popen):
            with self.assertRaises(Exception):
                cp.run_probe(mutated, self.root / cp.PROCESS_NAME, self.report)
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

        with patch.object(cp, 'validate_fixture_plan', side_effect=fake_validate):
            with self.assertRaises(FileExistsError):
                cp.run_probe(self.plan, self.root / cp.PROCESS_NAME, self.report)
        self.assertEqual(calls, [])
        self.assertEqual(self.report.read_bytes(), b'{"pre":1}\n')

    def test_wrong_hash_target_refused_with_failed_report_and_no_child(self):
        target = self.root / cp.PROCESS_NAME
        target.write_bytes(b'not the pinned image')
        spawned = []
        with patch.object(cp.subprocess, 'Popen',
                          side_effect=lambda *a, **k: spawned.append(1)):
            with self.assertRaisesRegex(ValueError, 'byte-pinned'):
                cp.run_probe(self.plan, target, self.report)
        self.assertEqual(spawned, [])
        evidence = self._failed_evidence()
        self.assertEqual(evidence['status'], 'failed')
        self.assertFalse(evidence['target_spawned'])

    def test_missing_target_reports_failed_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            cp.run_probe(self.plan, self.root / cp.PROCESS_NAME, self.report)
        evidence = self._failed_evidence()
        self.assertEqual(evidence['status'], 'failed')
        self.assertIn('FileNotFoundError', evidence['error'])

    def test_pe_architecture_mismatch_refused_even_with_matching_hash(self):
        target = self.root / cp.PROCESS_NAME
        target.write_bytes(_synthetic_pe(0x14C, 0x10B))  # x86 image, x64 plan
        spawned = []
        with patch.object(cp, '_hash_file', return_value=cp.TARGET_SHA256['x64']), \
             patch.object(cp.subprocess, 'Popen',
                          side_effect=lambda *a, **k: spawned.append(1)):
            with self.assertRaisesRegex(ValueError, 'architecture differs'):
                cp.run_probe(self.plan, target, self.report)
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
                    'native-codepatch-probe-pe-' + name)
                case_dir.mkdir(parents=True, exist_ok=True)
                target = case_dir / cp.PROCESS_NAME
                target.write_bytes(image)
                try:
                    with patch.object(cp, '_hash_file',
                                      return_value=cp.TARGET_SHA256[arch]):
                        try:
                            cp._admit_target(target, arch)
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
            with patch.object(cp, '_hash_file', return_value=cp.TARGET_SHA256['x64']):
                with self.assertRaisesRegex(ValueError, 'byte-pinned'):
                    cp._admit_target(target, 'x64')
        finally:
            target.unlink(missing_ok=True)


class MetadataContractTests(unittest.TestCase):
    """The child metadata and status JSON are bound to the pinned contract."""

    def test_metadata_is_accepted_and_any_drift_is_refused(self):
        for meta in (X64_META, X86_META):
            arch = 'x64' if meta['bits'] == 64 else 'x86'
            with self.subTest(architecture=arch):
                valid = _valid_metadata(meta, 42)
                self.assertEqual(cp._validate_metadata(valid, 42, arch), valid)
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
                    ('data_a-zero', lambda d: d.update(data_a_rva=0)),
                    ('data_b-out-of-range', lambda d: d.update(data_b_rva=meta['module_bytes'])),
                    ('probe-zero', lambda d: d.update(probe_rva=0)),
                    ('marker-exceeds-image', lambda d: d.update(
                        marker_rva=meta['module_bytes'] - 4)),
                    ('data_a-exceeds-image', lambda d: d.update(
                        data_a_rva=meta['module_bytes'] - 4)),
                    ('marker-bytes', lambda d: d.update(marker_bytes='deadbeef')),
                    ('data_a-bytes', lambda d: d.update(data_a_bytes='00' * 8)),
                    ('data_b-bytes', lambda d: d.update(data_b_bytes='00' * 3)),
                    ('overlap-bytes', lambda d: d.update(overlap_bytes='00' * 4)),
                    ('probe-bytes', lambda d: d.update(probe_bytes='00' * 10)),
                    ('original-value', lambda d: d.update(original_value=1)),
                    ('missing-key', lambda d: d.pop('page_bytes')),
                    ('extra-key', lambda d: d.update(extra=1)),
                    ('overlapping-sentinels', lambda d: d.update(
                        probe_rva=meta['marker_rva'] + 8)),
                    ('overlap-not-data_a-tail', lambda d: d.update(
                        overlap_rva=meta['data_a_rva'] + 1)),
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
                                'differs|exceed|overlap'):
                            cp._validate_metadata(drifted, 42, arch)

    def test_status_contract_is_strict(self):
        valid = {'schema': cp.STATUS_SCHEMA, 'pid': 42, 'sequence': 7,
                 'probe_value': cp.ORIGINAL_PROBE_VALUE}
        self.assertEqual(cp._validate_status(valid, 42), valid)
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
                    cp._validate_status(drifted, 42)
        with self.assertRaisesRegex(ValueError, 'status contract differs'):
            cp._validate_status([1, 2, 3], 42)


class ReceiveAndCleanupTests(unittest.TestCase):
    """Bounded JSON receive and cleanup authority for owned children only."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='native-codepatch-probe-c-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.plan = _x64_plan()

    def _owned_run(self):
        evidence = {'target_spawned': False, 'owned_child_pids': [],
                    'forced_owned_child_exit': []}
        run = cp._OwnedRun(self.plan, self.root / cp.PROCESS_NAME, 'x64',
                           evidence, self.root / 'state')
        return run, evidence

    def test_receive_enforces_bounded_json_contract(self):
        payload = {'schema': cp.STATUS_SCHEMA, 'pid': 42, 'sequence': 1,
                   'probe_value': 5}
        child = Mock(stdout=io.StringIO(json.dumps(payload) + '\n'))
        self.assertEqual(cp._receive(child), payload)

        child = Mock(stdout=io.StringIO(''))
        with self.assertRaisesRegex(ValueError, 'bounded JSON contract'):
            cp._receive(child)

        child = Mock(stdout=io.StringIO('x' * 16385))
        with self.assertRaisesRegex(ValueError, 'bounded JSON contract'):
            cp._receive(child)

        def broken(*args):
            raise OSError('pipe broken')

        child = Mock(stdout=Mock(readline=broken))
        with self.assertRaises(OSError):
            cp._receive(child)

    def test_spawn_failure_kills_only_the_owned_child(self):
        run, evidence = self._owned_run()
        bad_meta = {'schema': cp.METADATA_SCHEMA, 'pid': 999}
        child = Mock()
        child.pid = 17
        child.stdout = io.StringIO(json.dumps(bad_meta) + '\n')
        child.poll.return_value = None
        child.wait.return_value = 0
        with patch.object(cp, '_admit_target', lambda *a, **k: None), \
             patch.object(cp.subprocess, 'Popen', return_value=child) as popen:
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
        engine.error = ('code-patch-restore-mismatch: bytes at 0x23008 changed '
                        'externally; refusing to overwrite foreign bytes')
        run.engine = engine
        with self.assertRaisesRegex(AssertionError, 'refusing to overwrite foreign bytes'):
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
        cp._assert_no_files(empty, 'process lock directory')
        leftover = self.root / 'leftover'
        leftover.mkdir()
        (leftover / 'state.lock').write_bytes(b'x')
        with self.assertRaisesRegex(AssertionError,
                                    'retained ownership markers in process lock directory'):
            cp._assert_no_files(leftover, 'process lock directory')


if __name__ == '__main__':
    unittest.main()
