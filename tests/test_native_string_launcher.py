"""Owned String CLI admission retains failures before any target access."""
from pathlib import Path
from tempfile import TemporaryDirectory
import io
import json
import unittest
from unittest.mock import patch

from ct2trainer.native import launcher
from ct2trainer.native.compiler import compile_table
from ct2trainer.native.string_probe import PROCESS_NAME

FIXTURES = Path(__file__).resolve().parent / 'windows/string_fixture'


class StringLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / 'plan.json'
        self.report = self.root / 'fresh.json'
        self.source.write_text('{}', encoding='utf-8')
        self.arguments = ['--plan', str(self.source), '--string-fixture-target', 'owned.exe',
                          '--string-fixture-report', str(self.report)]
        self.stderr = patch('sys.stderr', io.StringIO()).start()
        self.addCleanup(patch.stopall)

    def test_exact_pair_routes_both_architectures_without_gui_or_generic_prevalidation(self):
        for architecture in ('x64', 'x86'):
            plan = compile_table(FIXTURES / ('string_' + architecture + '.ct'), PROCESS_NAME,
                                 architecture=architecture)
            self.source.write_text(json.dumps(plan), encoding='utf-8')
            with self.subTest(architecture=architecture), \
                    patch('ct2trainer.native.string_probe.run_probe') as probe, \
                    patch('ct2trainer.native.engine.validate_plan') as validate, \
                    patch('ct2trainer.native.ui.run_trainer') as gui:
                self.assertEqual(launcher.main(self.arguments), 0)
                probe.assert_called_once_with(plan, Path('owned.exe'), self.report)
                validate.assert_not_called()
                gui.assert_not_called()

    def test_invalid_owned_plan_retains_probe_refusal_before_target_start(self):
        with patch('ct2trainer.native.string_probe.subprocess.Popen') as child, \
                patch('ct2trainer.native.ui.run_trainer') as gui:
            self.assertEqual(launcher.main(self.arguments), 2)
        child.assert_not_called()
        gui.assert_not_called()
        evidence = json.loads(self.report.read_text())
        self.assertEqual(evidence['status'], 'failed')
        self.assertFalse(evidence['target_spawned'])
        self.assertFalse(evidence['target_writes'])
        self.assertTrue(evidence['source_runtime'])

    def test_orphan_string_flags_refuse_before_plan_read_probe_or_gui(self):
        self.source.write_text('invalid JSON', encoding='utf-8')
        for flag in ('--string-fixture-target', '--string-fixture-report'):
            with self.subTest(flag=flag), patch('ct2trainer.native.string_probe.run_probe') as probe, \
                    patch.object(Path, 'read_text', side_effect=AssertionError('Must not read plan')), \
                    patch('ct2trainer.native.ui.run_trainer') as gui:
                self.assertEqual(launcher.main(['--plan', str(self.source), flag, 'owned']), 2)
                probe.assert_not_called()
                gui.assert_not_called()

    def test_complete_other_pairs_and_smoke_modes_cannot_mix_with_string_gate(self):
        for prefix in ('fixture', 'hook-fixture', 'lua-fixture', 'x86-fixture', 'scan-fixture'):
            self._refuse_mixed(['--' + prefix + '-target', 'other.exe', '--' + prefix + '-report', 'other.json'])
        self._refuse_mixed(['--smoke'])
        self._refuse_mixed(['--smoke-output', 'smoke.json'])

    def test_other_orphan_targets_or_reports_cannot_mix_with_string_gate(self):
        for prefix in ('fixture', 'hook-fixture', 'lua-fixture', 'x86-fixture', 'scan-fixture'):
            for suffix in ('target', 'report'):
                self._refuse_mixed(['--' + prefix + '-' + suffix, 'other'])

    def _refuse_mixed(self, extra):
        with self.subTest(extra=extra), patch('ct2trainer.native.string_probe.run_probe') as probe, \
                patch.object(Path, 'read_text', side_effect=AssertionError('Must not read plan')), \
                patch('ct2trainer.native.ui.run_trainer') as gui:
            self.assertEqual(launcher.main(self.arguments + extra), 2)
            probe.assert_not_called()
            gui.assert_not_called()
        self.assertFalse(self.report.exists())

    def test_json_parse_and_file_read_failures_reserve_early_failed_report(self):
        for kind in ('parse', 'read'):
            with self.subTest(kind=kind):
                report = self.root / (kind + '.json')
                source = self.root / ('bad.json' if kind == 'parse' else 'missing.json')
                if kind == 'parse':
                    source.write_text('{not JSON', encoding='utf-8')
                args = ['--plan', str(source), '--string-fixture-target', 'owned.exe',
                        '--string-fixture-report', str(report)]
                with patch('ct2trainer.native.string_probe.run_probe') as probe, \
                        patch('ct2trainer.native.ui.run_trainer') as gui:
                    self.assertEqual(launcher.main(args), 2)
                probe.assert_not_called()
                gui.assert_not_called()
                evidence = json.loads(report.read_text())
                self.assertEqual(evidence['error_stage'], 'plan-load')
                self.assertEqual(evidence['status'], 'failed')
                self.assertFalse(evidence['target_spawned'])
                self.assertFalse(evidence['target_writes'])

    def test_frozen_embedded_plan_failure_retains_frozen_flag_without_source_override(self):
        with patch('sys.frozen', True, create=True), \
                patch('ct2trainer.native.bundle.read_embedded_plan', side_effect=ValueError('Bad overlay')), \
                patch('ct2trainer.native.string_probe.run_probe') as probe:
            self.assertEqual(launcher.main(self.arguments[2:]), 2)
        probe.assert_not_called()
        evidence = json.loads(self.report.read_text())
        self.assertTrue(evidence['frozen_runtime'])
        self.assertFalse(evidence['source_runtime'])
        self.assertIn('Bad overlay', evidence['error'])

    def test_existing_failed_load_report_is_never_replaced(self):
        self.report.write_bytes(b'previous proof')
        self.source.write_text('invalid JSON', encoding='utf-8')
        with patch('ct2trainer.native.string_probe.run_probe') as probe:
            self.assertEqual(launcher.main(self.arguments), 2)
        probe.assert_not_called()
        self.assertEqual(self.report.read_bytes(), b'previous proof')

    def test_orphan_reports_for_older_gates_also_refuse_without_error_dialog(self):
        for prefix in ('fixture', 'hook-fixture', 'lua-fixture', 'x86-fixture', 'scan-fixture'):
            with self.subTest(prefix=prefix), patch('tkinter.messagebox.showerror') as dialog:
                self.assertEqual(launcher.main(['--' + prefix + '-report', 'old.json']), 2)
                dialog.assert_not_called()
