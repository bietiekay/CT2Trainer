"""Recovery CLI binds validated plans before read-only assessment or release."""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from ct2trainer.native.__main__ import main
from ct2trainer.native.compiler import compile_table
from ct2trainer.native import recovery, recovery_operation
from ct2trainer.native.recovery import (ProcessIdentity, ProcessObservation,
                                         WindowsProcessProbe, WAIT_OBJECT_0)


ROOT = Path(__file__).resolve().parents[1]
CT = ROOT / 'tests/windows/fixture_target/fixture.ct'


def _canonical(document):
    return json.dumps(document, sort_keys=True, separators=(',', ':')).encode()


def _dead(identity):
    return ProcessObservation(identity, 'dead', identity.created, WAIT_OBJECT_0)


class _RecoveryCliFixture:
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='native-recovery-cli-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.plan = compile_table(CT, 'FixtureTarget.exe')
        self.plan_path = self.root / 'plan.json'
        self.plan_path.write_bytes(_canonical(self.plan))
        self.state, self.shared, self.archive = self.root / 'state', self.root / '_process_sessions', self.root / 'evidence'
        self.state.mkdir()
        self.shared.mkdir()
        (self.state / 'hooks').mkdir()
        self.write_evidence(ProcessIdentity(111, 1111), ProcessIdentity(222, 2222))

    def write_evidence(self, owner, target):
        lock = {'schema': 2, 'owner_pid': owner.pid, 'owner_created': owner.created, 'nonce': 'c' * 32}
        session = {'schema': 1, 'owner': lock, 'trainer_id': self.plan['trainer_id'],
                   'target_pid': target.pid, 'target_created': target.created}
        payload = {'schema': 1, 'engine': 'ct2trainer', 'trainer_id': self.plan['trainer_id'],
                   'table_sha256': self.plan['table_sha256'], 'process_name': self.plan['process_name'], 'desired': [1]}
        state = {'payload': payload, 'sha256': hashlib.sha256(_canonical(payload)).hexdigest()}
        lua = {'schema': 'ct2trainer-lua-activation/v1', 'engine': 'ct2trainer-lua',
               'trainer_id': self.plan['trainer_id'], 'table_sha256': self.plan['table_sha256'],
               'state': 'open', 'target': [target.pid, target.created], 'owner': 1,
               'data': [], 'symbols': {}, 'assemblies': {}, 'pending': None}
        hook = {'schema': 1, 'engine': 'ct2trainer-hooks', 'owner': self.plan['trainer_id'] + ':fixture',
                'target_pid': target.pid, 'target_created': target.created, 'state': 'enabled', 'uncertain': False,
                'allocations': {}, 'blocks': [], 'entries': [], 'exports': {},
                'retirement_policy': 'retain-published-allocations-until-target-exit'}
        self.claim = self.shared / f'{target.pid}-{target.created}.json'
        for path, document in ((self.state / 'state.json', state), (self.state / 'state.lock', lock),
                               (self.state / 'session.json', session), (self.claim, session),
                               (self.state / 'hooks' / 'lua.json', lua), (self.state / 'hooks' / 'hook.json', hook)):
            path.write_bytes(_canonical(document))

    def snapshot(self):
        return {str(path): (path.read_bytes(), path.stat().st_mtime_ns) for directory in (self.state, self.shared)
                for path in directory.rglob('*') if path.is_file()}

    def invoke(self, command, *, shared=True):
        arguments = [command, str(self.plan_path), '--state-dir', str(self.state)]
        if shared:
            arguments += ['--process-lock-dir', str(self.shared)]
        if command == 'recover':
            arguments += ['--archive-dir', str(self.archive)]
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch('sys.stdout', stdout), patch('sys.stderr', stderr):
            code = main(arguments)
        return code, stdout.getvalue(), stderr.getvalue()

    def assess_with(self, probe=_dead):
        original = recovery.assess_recovery
        def assess(*arguments, **keywords):
            return original(*arguments, **keywords, process_probe=probe)
        return patch.object(recovery, 'assess_recovery', side_effect=assess)


class RecoveryCliTests(_RecoveryCliFixture, unittest.TestCase):
    def test_invalid_json_or_profile_cannot_read_or_mutate_recovery_scopes(self):
        lua_plan = compile_table(ROOT / 'tests/windows/hook_fixture/lua_trainer.ct', 'NativeHookFixture.exe')
        lua_plan['entries'][0]['lua_program']['source_sha256'] = '0' * 64
        invalid = (b'{incomplete', _canonical(dict(self.plan, schema=99)), _canonical(lua_plan))
        open_file = Path.open
        def protected(path, *args, **kwargs):
            if path == self.state or path.is_relative_to(self.state) or path == self.shared or path.is_relative_to(self.shared):
                raise AssertionError('Invalid CLI plan touched a recovery scope')
            return open_file(path, *args, **kwargs)
        for raw in invalid:
            for command in ('assess-recovery', 'recover'):
                with self.subTest(raw=raw[:30], command=command):
                    self.plan_path.write_bytes(raw)
                    before = self.snapshot()
                    with patch.object(Path, 'open', protected), \
                            patch.object(recovery, 'assess_recovery') as assess, \
                            patch.object(recovery_operation, 'recover_assessment') as recover:
                        code, stdout, stderr = self.invoke(command)
                    self.assertEqual(code, 2)
                    self.assertEqual(stdout, '')
                    self.assertIn('Error:', stderr)
                    assess.assert_not_called()
                    recover.assert_not_called()
                    self.assertEqual(before, self.snapshot())
                    self.assertFalse(self.archive.exists())

    def test_assessment_passes_exact_plan_bindings_and_changes_no_bytes_or_inventory(self):
        before = self.snapshot()
        with self.assess_with() as assess, patch.object(recovery_operation, 'recover_assessment') as recover:
            code, stdout, stderr = self.invoke('assess-recovery')
        self.assertEqual((code, stderr), (0, ''))
        assess.assert_called_once_with(self.state, self.shared,
                                       expected_trainer_id=self.plan['trainer_id'],
                                       expected_table_sha256=self.plan['table_sha256'])
        recover.assert_not_called()
        result = json.loads(stdout)
        self.assertEqual(result['status'], 'eligible-read-only')
        self.assertTrue(result['eligible'])
        self.assertTrue(result['read_only'])
        self.assertFalse(result['mutation_authorized'])
        self.assertEqual(len(result['files']), 6)
        self.assertEqual(len(result['inventory_sha256']), 64)
        self.assertNotIn(str(self.state / 'state.json'), result['candidate_paths'])
        self.assertEqual(len(result['processes']), 2)
        self.assertTrue(all(len(item['observations']) == 2 for item in result['processes']))
        self.assertEqual(before, self.snapshot())
        self.assertFalse((self.state / 'recovery.lock').exists())
        self.assertFalse(self.archive.exists())

    def test_default_process_lock_directory_remains_bound_to_the_state_parent(self):
        before = self.snapshot()
        with self.assess_with() as assess:
            code, stdout, stderr = self.invoke('assess-recovery', shared=False)
        self.assertEqual((code, stderr), (0, ''))
        assess.assert_called_once_with(self.state, None,
                                       expected_trainer_id=self.plan['trainer_id'],
                                       expected_table_sha256=self.plan['table_sha256'])
        self.assertEqual(json.loads(stdout)['process_lock_directory'], str(self.shared))
        self.assertEqual(before, self.snapshot())

    def test_foreign_saved_trainer_or_table_binding_blocks_without_releasing_files(self):
        original = json.loads((self.state / 'state.json').read_bytes())
        for key, value in (('trainer_id', 'd' * 16), ('table_sha256', 'e' * 64)):
            with self.subTest(key=key):
                changed = deepcopy(original)
                changed['payload'][key] = value
                changed['sha256'] = hashlib.sha256(_canonical(changed['payload'])).hexdigest()
                (self.state / 'state.json').write_bytes(_canonical(changed))
                before = self.snapshot()
                with self.assess_with():
                    code, stdout, stderr = self.invoke('assess-recovery')
                self.assertEqual((code, stderr), (2, ''))
                result = json.loads(stdout)
                self.assertEqual(result['status'], 'blocked')
                self.assertFalse(result['eligible'])
                self.assertTrue(result['reasons'])
                self.assertEqual(before, self.snapshot())

    def test_unknown_owner_assessment_and_explicit_recover_refusal_are_structured_json(self):
        before = self.snapshot()
        def unknown(identity):
            return ProcessObservation(identity, 'unknown', detail='Injected denied process query')
        with self.assess_with(unknown):
            code, stdout, stderr = self.invoke('assess-recovery')
        self.assertEqual((code, stderr), (2, ''))
        result = json.loads(stdout)
        self.assertEqual(result['status'], 'blocked')
        self.assertTrue(result['read_only'])
        self.assertFalse(result['mutation_authorized'])
        original = recovery_operation.recover_assessment
        with self.assess_with(unknown), \
                patch.object(recovery_operation, 'recover_assessment', wraps=original) as recover:
            code, stdout, stderr = self.invoke('recover')
        self.assertEqual((code, stderr), (2, ''))
        call = recover.call_args
        self.assertEqual(call.args[1], self.archive)
        self.assertEqual(call.kwargs, {'expected_trainer_id': self.plan['trainer_id'],
                                      'expected_table_sha256': self.plan['table_sha256']})
        self.assertEqual(call.args[0].status, 'blocked')
        result = json.loads(stdout)
        self.assertEqual(result['status'], 'refused')
        self.assertFalse(result['remote_writes'])
        self.assertEqual(result['released'], [])
        self.assertIsNone(result['archive_path'])
        self.assertFalse(result['fence_released'])
        self.assertEqual(before, self.snapshot())
        self.assertFalse(self.archive.exists())

    def test_clean_assessment_does_not_promote_saved_state_into_a_release_candidate(self):
        for path in list(self.state.rglob('*')) + list(self.shared.iterdir()):
            if path.is_file() and path.name != 'state.json':
                path.unlink()
        before = self.snapshot()
        with self.assess_with():
            code, stdout, stderr = self.invoke('assess-recovery')
        self.assertEqual((code, stderr), (0, ''))
        result = json.loads(stdout)
        self.assertEqual(result['status'], 'clean')
        self.assertFalse(result['eligible'])
        self.assertEqual(result['candidate_paths'], [])
        self.assertEqual(before, self.snapshot())


@unittest.skipUnless(sys.platform == 'win32', 'Actual Windows process proof and held local file release')
class WindowsRecoveryCliTests(_RecoveryCliFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.children = []
        self.addCleanup(self.stop_children)
        identities = []
        for _ in range(2):
            child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'],
                                     creationflags=subprocess.CREATE_NO_WINDOW)
            self.children.append(child)
            observed = WindowsProcessProbe()(ProcessIdentity(child.pid, None))
            self.assertEqual(observed.status, 'alive', observed)
            identities.append(ProcessIdentity(child.pid, observed.observed_created))
        self.stop_children()
        for path in self.shared.iterdir():
            path.unlink()
        self.write_evidence(*identities)

    def stop_children(self):
        for child in self.children:
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=5)

    def test_actual_cli_recovery_archives_local_evidence_and_preserves_committed_state(self):
        before = self.snapshot()
        with patch.object(recovery_operation, 'recover_assessment') as recover:
            code, stdout, stderr = self.invoke('assess-recovery')
        self.assertEqual((code, stderr), (0, ''))
        self.assertEqual(json.loads(stdout)['status'], 'eligible-read-only')
        recover.assert_not_called()
        self.assertEqual(before, self.snapshot())
        code, stdout, stderr = self.invoke('recover')
        self.assertEqual((code, stderr), (0, ''))
        report = json.loads(stdout)
        self.assertEqual(report['status'], 'completed')
        self.assertFalse(report['remote_writes'])
        self.assertTrue(report['fence_released'])
        self.assertEqual(report['released'][-1], str(self.state / 'state.lock'))
        self.assertFalse((self.state / 'recovery.lock').exists())
        self.assertEqual((self.state / 'state.json').read_bytes(), before[str(self.state / 'state.json')][0])
        bundle = Path(report['archive_path'])
        self.assertEqual(hashlib.sha256(bundle.read_bytes()).hexdigest(), report['archive_sha256'])
        with zipfile.ZipFile(bundle) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            for item in manifest['files']:
                self.assertEqual(archive.read(item['member']), before[item['path']][0])
        code, stdout, stderr = self.invoke('assess-recovery')
        self.assertEqual((code, stderr), (0, ''))
        self.assertEqual(json.loads(stdout)['status'], 'clean')

    def test_actual_archive_verification_failure_reports_uncertainty_and_preserves_originals(self):
        before = self.snapshot()
        read = zipfile.ZipFile.read
        def corrupted(bundle, name, *args, **kwargs):
            raw = read(bundle, name, *args, **kwargs)
            return raw + b'x' if name == 'state/state.lock' else raw
        with patch.object(zipfile.ZipFile, 'read', corrupted):
            code, stdout, stderr = self.invoke('recover')
        self.assertEqual((code, stderr), (3, ''))
        report = json.loads(stdout)
        self.assertEqual(report['status'], 'uncertain')
        self.assertFalse(report['remote_writes'])
        self.assertFalse(report['fence_released'])
        self.assertEqual(report['released'], [])
        self.assertTrue((self.state / 'recovery.lock').exists())
        self.assertTrue(Path(report['archive_path']).exists())
        self.assertTrue(Path(report['journal_path']).exists())
        self.assertTrue(any('original-byte verification failed' in reason for reason in report['reasons']))
        for path, (raw, _) in before.items():
            self.assertEqual(Path(path).read_bytes(), raw)


if __name__ == '__main__':
    unittest.main()
