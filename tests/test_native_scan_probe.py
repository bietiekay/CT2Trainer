"""Owned acceptance admission rejects substituted sources before target effects."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ct2trainer.native.compiler import compile_table
from ct2trainer.native.scan_probe import CT_SHA256, validate_fixture_plan, run_probe
from ct2trainer.native import launcher

FIXTURE = Path(__file__).resolve().parent/'windows/scan_fixture/scan_trainer.ct'


class OwnedScanAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.plan = compile_table(FIXTURE,'NativeScanFixture.exe')

    def test_owned_architectures_remain_distinct_and_admitted(self):
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),CT_SHA256)
        for architecture in ('x64','x86'):
            plan=compile_table(FIXTURE,'NativeScanFixture.exe',architecture=architecture)
            self.assertEqual(validate_fixture_plan(plan),architecture)

    def test_substitution_or_selection_cannot_enter_owned_gate(self):
        for mutate in (lambda p:p.update(table_sha256='0'*64),
                       lambda p:p.update(process_name='other.exe'),
                       lambda p:p.update(selected_ids=[1]),
                       lambda p:p['entries'][0].update(selected=False),
                       lambda p:p['entries'][1].update(parent_id=1),
                       lambda p:p['entries'][0]['program'].update(source_sha256='0'*64)):
            value=deepcopy(self.plan);mutate(value)
            with self.subTest(mutate=mutate),self.assertRaises((ValueError,RuntimeError)):
                validate_fixture_plan(value)

    def test_invalid_plan_is_retained_as_failed_without_target_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            report=Path(directory)/'failed.json'
            with patch('ct2trainer.native.scan_probe.subprocess.Popen') as launch:
                with self.assertRaises((ValueError,RuntimeError)): run_probe({},Path(directory)/'other.exe',report)
            launch.assert_not_called()
            evidence=json.loads(report.read_text())
            self.assertEqual(evidence['status'],'failed')
            self.assertFalse(evidence['target_spawned'])
            self.assertFalse(evidence['target_writes'])

    def test_wrong_target_is_refused_with_failed_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'NativeScanFixture.exe';target.write_bytes(b'owned gate substitute')
            report=Path(directory)/'failed.json'
            with patch('ct2trainer.native.scan_probe.subprocess.Popen') as launch:
                with self.assertRaisesRegex(ValueError,'byte-pinned'): run_probe(self.plan,target,report)
            launch.assert_not_called()
            self.assertEqual(json.loads(report.read_text())['status'],'failed')

    def test_old_report_is_preserved_before_any_target_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            report=Path(directory)/'old.json';report.write_bytes(b'previous evidence')
            with patch('ct2trainer.native.scan_probe.subprocess.Popen') as launch:
                with self.assertRaises(FileExistsError): run_probe({},'unavailable.exe',report)
            launch.assert_not_called()
            self.assertEqual(report.read_bytes(),b'previous evidence')

    def test_mixed_or_orphan_reports_never_route_to_a_probe(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'plan.json';source.write_text(json.dumps(self.plan))
            for extra in ('--fixture-report','--hook-fixture-report','--lua-fixture-report','--x86-fixture-report'):
                with self.subTest(extra=extra),patch('ct2trainer.native.scan_probe.run_probe') as probe:
                    result=launcher.main(['--plan',str(source),'--scan-fixture-target','owned.exe',
                        '--scan-fixture-report',str(Path(directory)/'fresh.json'),extra,'ignored.json'])
                self.assertEqual(result,2)
                probe.assert_not_called()

    def test_missing_scan_report_never_launches_target(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'plan.json';source.write_text(json.dumps(self.plan))
            with patch('ct2trainer.native.scan_probe.run_probe') as probe:
                result=launcher.main(['--plan',str(source),'--scan-fixture-target','owned.exe'])
            self.assertEqual(result,2)
            probe.assert_not_called()
