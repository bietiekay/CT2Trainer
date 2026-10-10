"""Owned String gate admission/cleanup, with no real child process or target write."""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import Mock, patch

from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import validate_plan
from ct2trainer.native.value_types import prepare_value_profile
from ct2trainer.native.string_probe import (
    CT_SHA256, FIXTURE_SOURCE_SHA256, PLAN_SHA256, PROCESS_NAME,
    _INITIAL, _OwnedRun, _admit_target, _receive, _validate_metadata,
    plan_fingerprint, run_probe, validate_fixture_plan)

FIXTURE = Path(__file__).resolve().parent / 'windows/string_fixture'


def metadata(architecture='x64', pid=17):
    # Fixed source-layout values independent of ASLR and child creation times.
    base = 0x140000000 if architecture == 'x64' else 0x400000
    rvas = ((0x24048, 0x24060, 0x24090, 0x240A0, 0x240A8)
            if architecture == 'x64' else (0x1DE40, 0x1DE58, 0x1DE88, 0x1DE98, 0x1DE9C))
    value = {'schema': 'ct2trainer-owned-string-target/v1', 'pid': pid,
        'pointer_bits': 64 if architecture == 'x64' else 32,
        'pe_machine': 0x8664 if architecture == 'x64' else 0x14C,
        'process_name': PROCESS_NAME, 'module_base': base,
        'module_bytes': 0x2A000 if architecture == 'x64' else 0x22000,
        'page_bytes': 4096, 'buffers': {}}
    for index, (name, length, unit, terminated, tail) in enumerate((
            ('ascii', 8, 1, True, 4), ('utf16', 16, 2, True, 12), ('fixed', 8, 1, False, 8))):
        rva = rvas[index]
        value['buffers'][name] = {'address': base+rva, 'rva': rva, 'length': length,
            'unit_bytes': unit, 'read_bytes': length*unit, 'zero_terminate': terminated,
            'full_address': base+rva-8, 'full_rva': rva-8, 'full_bytes': length*unit+16,
            'before_address': base+rva-8, 'before_rva': rva-8, 'guard_bytes': 8,
            'after_address': base+rva+length*unit, 'after_rva': rva+length*unit,
            'tail_offset': tail}
    for index, (name, protection) in enumerate((('readonly', 2), ('executable', 0x40))):
        value[name] = {'address': 0x20000000+index*0x10000,
            'pointer_address': base+rvas[index+3], 'pointer_rva': rvas[index+3],
            'read_bytes': 8, 'allocation_bytes': 4096, 'expected_protection': protection}
    return value


class OwnedStringAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plans = {a: compile_table(FIXTURE / ('string_'+a+'.ct'), PROCESS_NAME,
                                     architecture=a) for a in ('x64', 'x86')}

    def test_regenerate_known_source_fields_for_both_architectures(self):
        self.assertEqual(_INITIAL['utf16'], 'OLD\U0001f642'.encode('utf-16-le') + b'\0\0'
                         + b'\xad\xde' + b''.join(v.to_bytes(2,'little') for v in range(0x3317,0x3320)))
        for architecture, plan in self.plans.items():
            with self.subTest(architecture=architecture):
                self.assertEqual(hashlib.sha256((FIXTURE/('string_'+architecture+'.ct')).read_bytes()).hexdigest(), CT_SHA256[architecture])
                self.assertEqual(validate_fixture_plan(plan), architecture)
                self.assertEqual(plan_fingerprint(plan), PLAN_SHA256[architecture])
                self.assertEqual([e['id'] for e in plan['entries']], [1,2,3,4,5,6])
                self.assertEqual([e.get('variable_type') for e in plan['entries']], ['String']*5+['Byte'])
                self.assertEqual([e['value_profile']['size'] for e in plan['entries'][:5]], [8,32,8,8,8])
                self.assertEqual(plan['entries'][0]['address'], '"'+PROCESS_NAME+'"+'+('24048' if architecture=='x64' else '1DE40'))
                self.assertEqual(plan['entries'][3]['address'], '["'+PROCESS_NAME+'"+'+('240A0' if architecture=='x64' else '1DE98')+']')

    def test_pinned_owned_c_source_is_exported_exactly(self):
        self.assertEqual(hashlib.sha256((FIXTURE/'string_target.c').read_bytes()).hexdigest(), FIXTURE_SOURCE_SHA256)

    def test_only_top_level_display_title_and_source_name_may_change(self):
        plan=deepcopy(self.plans['x64'])
        plan.update(title='Owned embedded String trainer', source_name='renamed.ct')
        self.assertEqual(validate_fixture_plan(plan), 'x64')
        plan['entries'][0]['label']='Changed action label'
        with self.assertRaisesRegex(ValueError,'canonical'):
            validate_fixture_plan(plan)

    def test_source_name_remains_bounded_typed_display_metadata(self):
        for value in (None, True, 4, 'x'*261, 'a\nb'):
            plan=deepcopy(self.plans['x64']);plan['source_name']=value
            with self.subTest(value=value),self.assertRaises((ValueError,RuntimeError)):
                validate_fixture_plan(plan)

    def test_self_consistent_profile_or_address_forgery_is_still_refused(self):
        for mutate in (
                lambda p:p['entries'][0].update(value_profile=prepare_value_profile('String', {'Length':'64'})),
                lambda p:p['entries'][0].update(address='"'+PROCESS_NAME+'"+24049',source_address='"'+PROCESS_NAME+'"+24049'),
                lambda p:p['entries'][4].update(address='["'+PROCESS_NAME+'"+240A0]',source_address='["'+PROCESS_NAME+'"+240A0]'),
                lambda p:p.update(untrusted_extra_authority=True)):
            plan=deepcopy(self.plans['x64']);mutate(plan)
            # General canonical validation alone is not an original-XML proof.
            validate_plan(plan)
            with self.subTest(mutate=mutate),self.assertRaisesRegex(ValueError,'canonical'):
                validate_fixture_plan(plan)

    def test_bad_identity_selection_defaults_or_architecture_never_admitted(self):
        for mutate in (
                lambda p:p.update(table_sha256='0'*64),
                lambda p:p.update(process_name='other.exe'),
                lambda p:p.update(selected_ids=[1]),
                lambda p:p['entries'][0].update(selected=False),
                lambda p:p['entries'][0].update(parent_id=2),
                lambda p:p.update(startup_defaults={'1':True}),
                lambda p:p.update(schema=1),
                lambda p:p.update(target_architecture=deepcopy(self.plans['x86']['target_architecture']))):
            plan=deepcopy(self.plans['x64']);mutate(plan)
            with self.subTest(mutate=mutate),self.assertRaises((ValueError,RuntimeError)):
                validate_fixture_plan(plan)

    def test_invalid_plan_reserves_failed_evidence_before_any_child(self):
        with tempfile.TemporaryDirectory() as directory:
            report=Path(directory)/'failed.json'
            with patch('ct2trainer.native.string_probe.subprocess.Popen') as launch,patch('ct2trainer.native.string_probe._admit_target') as target:
                with self.assertRaises((ValueError,RuntimeError)):
                    run_probe({}, 'unavailable.exe', report)
            launch.assert_not_called();target.assert_not_called()
            evidence=json.loads(report.read_text())
            self.assertEqual(evidence['status'],'failed')
            self.assertFalse(evidence['target_spawned'])
            self.assertFalse(evidence['target_write_actions_started'])

    def test_old_report_is_untouched_before_any_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            report=Path(directory)/'old.json';report.write_bytes(b'previous retained proof')
            with patch('ct2trainer.native.string_probe.subprocess.Popen') as launch,patch('ct2trainer.native.string_probe.validate_fixture_plan') as validate:
                with self.assertRaises(FileExistsError):run_probe({}, 'unavailable.exe', report)
            launch.assert_not_called();validate.assert_not_called()
            self.assertEqual(report.read_bytes(),b'previous retained proof')

    def test_wrong_hash_or_target_name_has_fresh_failed_report_without_child(self):
        with tempfile.TemporaryDirectory() as directory:
            for index,name in enumerate((PROCESS_NAME,'other.exe')):
                target=Path(directory)/name;target.write_bytes(b'substituted image')
                report=Path(directory)/(str(index)+'.json')
                with patch('ct2trainer.native.string_probe.subprocess.Popen') as launch:
                    with self.assertRaisesRegex(ValueError,'byte-pinned'):
                        run_probe(self.plans['x64'],target,report)
                launch.assert_not_called()
                evidence=json.loads(report.read_text())
                self.assertEqual(evidence['status'],'failed')
                self.assertFalse(evidence['target_spawned'])
                self.assertFalse(evidence['target_write_actions_started'])

    def test_missing_target_keeps_failed_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            report=Path(directory)/'failed.json'
            with patch('ct2trainer.native.string_probe.subprocess.Popen') as launch:
                with self.assertRaises(FileNotFoundError):
                    run_probe(self.plans['x64'],Path(directory)/PROCESS_NAME,report)
            launch.assert_not_called()
            self.assertEqual(json.loads(report.read_text())['status'],'failed')

    def test_hash_match_cannot_override_wrong_pe_architecture(self):
        with tempfile.TemporaryDirectory() as directory:
            image=bytearray(90);image[:2]=b'MZ';struct.pack_into('<I',image,60,64)
            image[64:68]=b'PE\0\0';struct.pack_into('<H',image,68,0x14C);struct.pack_into('<H',image,88,0x10B)
            target=Path(directory)/PROCESS_NAME;target.write_bytes(image)
            from ct2trainer.native.string_probe import TARGET_SHA256
            with patch('ct2trainer.native.string_probe._hash_file',return_value=TARGET_SHA256['x64']):
                with self.assertRaisesRegex(ValueError,'architecture'):_admit_target(target,'x64')

    def test_all_setup_failures_remain_failed_without_target_start(self):
        with tempfile.TemporaryDirectory() as directory:
            report=Path(directory)/'setup.json'
            with patch('ct2trainer.native.string_probe._admit_target'),patch('ct2trainer.native.string_probe._hash_file',side_effect=OSError('runtime hash failed')),patch('ct2trainer.native.string_probe.subprocess.Popen') as launch:
                with self.assertRaisesRegex(OSError,'runtime hash'):
                    run_probe(self.plans['x64'],PROCESS_NAME,report)
            launch.assert_not_called()
            self.assertEqual(json.loads(report.read_text())['status'],'failed')

    def test_metadata_layout_identity_and_private_pointers_are_strict(self):
        for architecture in ('x64','x86'):
            value=metadata(architecture)
            self.assertEqual(_validate_metadata(value,17,architecture),value)
        for mutate in (
                lambda p:p.update(pid=True),lambda p:p.update(pid=18),lambda p:p.update(pointer_bits=32),
                lambda p:p.update(module_bytes=0x1000),lambda p:p.update(extra=True),
                lambda p:p['buffers']['ascii'].update(address=p['buffers']['ascii']['address']+1),
                lambda p:p['buffers']['utf16'].update(zero_terminate=1),
                lambda p:p['readonly'].update(pointer_rva=p['readonly']['pointer_rva']+8),
                lambda p:p['readonly'].update(address=p['module_base']),
                lambda p:p['executable'].update(address=p['readonly']['address']),
                lambda p:p['executable'].update(address=0x800000000000)):
            value=metadata();mutate(value)
            with self.subTest(mutate=mutate),self.assertRaises(ValueError):_validate_metadata(value,17,'x64')

    def test_receive_is_bounded_and_rejects_empty_or_malformed_json(self):
        for text in ('','a'*16385,'{malformed}'):
            with self.subTest(text=text[:10]),self.assertRaises(ValueError):
                _receive(Mock(stdout=io.StringIO(text)))
        self.assertEqual(_receive(Mock(stdout=io.StringIO('{"owned":true}\n'))),{'owned':True})

    def test_bad_child_metadata_never_reaches_memory_and_kills_only_owned_child(self):
        with tempfile.TemporaryDirectory() as directory:
            report=Path(directory)/'child.json'
            child=Mock(pid=17,stdout=io.StringIO('{"schema":"foreign"}\n'))
            child.poll.return_value=None;child.wait.return_value=0
            with patch('ct2trainer.native.string_probe._admit_target'),patch('ct2trainer.native.string_probe.subprocess.Popen',return_value=child),patch('ct2trainer.native.memory.ProcessMemory') as memory:
                with self.assertRaises(ValueError):run_probe(self.plans['x64'],PROCESS_NAME,report)
            memory.assert_not_called();child.kill.assert_called_once()
            evidence=json.loads(report.read_text())
            self.assertEqual(evidence['owned_child_pids'],[17])
            self.assertTrue(evidence['target_spawned'])
            self.assertFalse(evidence['target_write_actions_started'])
            self.assertEqual(evidence['status'],'failed')

    def test_unconfirmed_controller_cleanup_fails_even_completed_mock_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            report=Path(directory)/'cleanup.json'
            engine=Mock(error='retained uncertain journal');engine.close.return_value=False
            def completed(run):
                run.engine=engine
                run.evidence['checks']=[{'check':str(i),'passed':True} for i in range(14)]
            with patch('ct2trainer.native.string_probe._admit_target'),patch('ct2trainer.native.string_probe._exercise',side_effect=completed):
                with self.assertRaisesRegex(AssertionError,'retained uncertain journal'):
                    run_probe(self.plans['x64'],PROCESS_NAME,report)
            evidence=json.loads(report.read_text())
            self.assertEqual(evidence['status'],'failed')
            self.assertTrue(evidence['cleanup_errors'])
            engine.close.assert_called_once()

    def test_cleanup_has_no_authority_for_a_foreign_child(self):
        run=_OwnedRun({},Path(PROCESS_NAME),'x64',{},Path('.'))
        foreign=Mock(pid=23);foreign.poll.return_value=None;run.child=foreign
        run.cleanup()
        foreign.kill.assert_not_called();foreign.wait.assert_not_called()

    def test_nonzero_owned_exit_and_forced_cleanup_can_never_confirm_success(self):
        run=_OwnedRun({},Path(PROCESS_NAME),'x64',{},Path('.'))
        child=Mock(pid=17);child.wait.return_value=7;child.poll.return_value=7
        run.child=child;run._owned_children.add(child)
        with self.assertRaisesRegex(AssertionError,'normally'):run.quit_child()
        child.kill.assert_not_called()
        child.poll.return_value=None
        with self.assertRaisesRegex(AssertionError,'forced exit'):run.cleanup()
        child.kill.assert_called_once()


if __name__=='__main__':
    unittest.main()
