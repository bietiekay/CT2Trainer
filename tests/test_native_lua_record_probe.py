"""The headless Lua acceptance gate cannot accept arbitrary CTs or targets."""
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from ct2trainer.native.compiler import compile_table
from ct2trainer.native.launcher import main
from ct2trainer.native.lua_program import prepare_lua_program
from ct2trainer.native.lua_record_probe import (FLAG_SOURCE_SHA256, LUA_CT_SHA256,
                                                 LUA_SOURCE_SHA256, PROCESS_NAME,
                                                 TARGET_SHA256, _metadata,
                                                 run_probe, validate_fixture_plan)


FIXTURE = Path(__file__).resolve().parents[1] / 'tests/windows/hook_fixture/lua_trainer.ct'


class LuaFixturePlanTests(unittest.TestCase):
    def setUp(self):
        self.plan = compile_table(FIXTURE, PROCESS_NAME)

    def test_versioned_ct_has_exact_supported_source_profiles_and_dependency(self):
        validate_fixture_plan(self.plan)
        self.assertEqual(self.plan['table_sha256'], LUA_CT_SHA256)
        self.assertEqual(self.plan['counts']['blocked'], 0)
        self.assertEqual(self.plan['entries'][0]['lua_program']['source_sha256'], LUA_SOURCE_SHA256)
        self.assertEqual(self.plan['entries'][1]['program']['source_sha256'], FLAG_SOURCE_SHA256)
        self.assertEqual(self.plan['entries'][1]['dependency_ids'], [1])

    def test_forging_the_pinned_table_hash_cannot_admit_different_valid_lua(self):
        source = self.plan['entries'][0]['lua_program']['source'].replace('return 17', 'return 77')
        self.plan['entries'][0]['lua_program'] = prepare_lua_program(source, PROCESS_NAME)
        with self.assertRaisesRegex(ValueError, 'exact owned Lua'):
            validate_fixture_plan(self.plan)

    def test_ids_selection_context_and_additional_bootstrap_are_rejected(self):
        mutations = (
            lambda p: p.update(process_name='Game.exe'),
            lambda p: p.update(table_sha256='0' * 64),
            lambda p: p['entries'].reverse(),
            lambda p: p.update(selected_ids=[1]),
            lambda p: p.update(lua_bootstrap=None),
            lambda p: p['entries'][0].update(id=3),
            lambda p: p['entries'][1].update(parent_id=1),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                altered = deepcopy(self.plan)
                mutate(altered)
                with self.assertRaises((ValueError, RuntimeError)):
                    validate_fixture_plan(altered)


class LuaFixtureEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.target = self.root / PROCESS_NAME
        self.target.write_bytes(b'independently owned but unpinned image')
        self.report = self.root / 'evidence/report.json'
        self.plan = compile_table(FIXTURE, PROCESS_NAME)

    def test_target_hash_refusal_is_reported_before_any_spawn_or_state_access(self):
        with patch('ct2trainer.native.lua_record_probe.subprocess.Popen') as spawn, \
                patch('ct2trainer.native.engine.TrainerEngine') as engine:
            with self.assertRaisesRegex(ValueError, 'binary hash differs'):
                run_probe(self.plan, self.target, self.report)
        spawn.assert_not_called()
        engine.assert_not_called()
        result = json.loads(self.report.read_bytes())
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['checks'], [])
        self.assertIsNone(result['state_directory'])
        self.assertFalse(result['game_runtime_verified'])

    def test_invalid_plan_is_reported_before_target_read_or_spawn(self):
        self.plan['table_sha256'] = '1' * 64
        with patch('ct2trainer.native.lua_record_probe.subprocess.Popen') as spawn:
            with self.assertRaisesRegex((ValueError, RuntimeError), 'pinned two-record|Trainer identity'):
                run_probe(self.plan, self.root / 'missing.exe', self.report)
        spawn.assert_not_called()
        self.assertEqual(json.loads(self.report.read_bytes())['status'], 'failed')

    def test_report_is_fresh_and_never_overwrites_earlier_evidence(self):
        self.report.parent.mkdir()
        self.report.write_bytes(b'earlier evidence')
        with patch('ct2trainer.native.lua_record_probe.subprocess.Popen') as spawn:
            with self.assertRaises(FileExistsError):
                run_probe(self.plan, self.target, self.report)
        spawn.assert_not_called()
        self.assertEqual(self.report.read_bytes(), b'earlier evidence')

    def test_spawn_failure_retains_a_failed_fresh_report_and_state_location(self):
        with patch('ct2trainer.native.lua_record_probe._sha256_file', return_value=TARGET_SHA256), \
                patch('ct2trainer.native.lua_record_probe.tempfile.mkdtemp', return_value=str(self.root / 'state')), \
                patch('ct2trainer.native.lua_record_probe.subprocess.Popen', side_effect=OSError('owned spawn failed')):
            with self.assertRaisesRegex(OSError, 'owned spawn failed'):
                run_probe(self.plan, self.target, self.report)
        result = json.loads(self.report.read_bytes())
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['state_directory'], str(self.root / 'state'))
        self.assertIn('owned spawn failed', result['error'])

    def test_metadata_rejects_a_different_pid_invalid_address_and_unbounded_line(self):
        for value in ({'pid': 13, 'entry': 123, 'result': 456, 'calls': 789},
                      {'pid': 12, 'entry': 0, 'result': 456, 'calls': 789},
                      {'pid': 12, 'entry': True, 'result': 456, 'calls': 789}):
            with self.subTest(value=value):
                child = Mock(pid=12, stdout=io.StringIO(json.dumps(value)))
                with self.assertRaisesRegex(ValueError, 'metadata/PID mismatch'):
                    _metadata(child)
        with self.assertRaisesRegex(ValueError, 'exceeds'):
            _metadata(Mock(pid=12, stdout=io.StringIO('x' * 4097)))


class LuaFixtureLauncherTests(unittest.TestCase):
    def setUp(self):
        self.plan = compile_table(FIXTURE, PROCESS_NAME)

    def test_frozen_launcher_routes_exact_embedded_plan_to_owned_lua_probe(self):
        with patch('ct2trainer.native.bundle.read_embedded_plan', return_value=self.plan), \
                patch('ct2trainer.native.lua_record_probe.run_probe') as probe:
            self.assertEqual(main(['--lua-fixture-target', PROCESS_NAME, '--lua-fixture-report', 'own.json']), 0)
        probe.assert_called_once_with(self.plan, Path(PROCESS_NAME), Path('own.json'))

    def test_missing_report_and_conflicting_modes_fail_without_probe_or_gui(self):
        options = ([ '--lua-fixture-target', PROCESS_NAME ],
                   [ '--lua-fixture-report', 'own.json' ],
                   [ '--lua-fixture-target', PROCESS_NAME, '--lua-fixture-report', 'own.json', '--smoke' ],
                   [ '--lua-fixture-target', PROCESS_NAME, '--lua-fixture-report', 'own.json',
                     '--hook-fixture-target', PROCESS_NAME, '--hook-fixture-report', 'hook.json' ])
        for args in options:
            with self.subTest(args=args), \
                    patch('ct2trainer.native.bundle.read_embedded_plan', return_value=self.plan), \
                    patch('ct2trainer.native.lua_record_probe.run_probe') as probe, \
                    patch('sys.stderr', io.StringIO()):
                self.assertEqual(main(args), 2)
                probe.assert_not_called()

    def test_probe_failure_returns_status_two_and_preserves_its_fresh_failure_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'refused.json'
            altered = deepcopy(self.plan)
            altered['table_sha256'] = '0' * 64
            with patch('ct2trainer.native.bundle.read_embedded_plan', return_value=altered), \
                    patch('sys.stderr', io.StringIO()):
                self.assertEqual(main(['--lua-fixture-target', PROCESS_NAME,
                                       '--lua-fixture-report', str(output)]), 2)
            self.assertEqual(json.loads(output.read_bytes())['status'], 'failed')


if __name__ == '__main__':
    unittest.main()
