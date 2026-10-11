"""Explicit architecture binding, admission, attach and frozen-overlay boundaries."""
from __future__ import annotations
from copy import deepcopy
from contextlib import redirect_stdout, redirect_stderr
from hashlib import sha256
import io
import json
import ctypes
from pathlib import Path
import struct
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from xml.sax.saxutils import escape

from ct2trainer.native.architecture import (ArchitectureError, plan_architecture,
                                              prepare_architecture, require_target_architecture)
from ct2trainer.native.compiler import NativeCompileError, compile_table, validate_plan
from ct2trainer.native.engine import NativeRuntimeError, TrainerEngine, validate_plan as runtime_validate
from ct2trainer.native.aa_program import prepare_program
from ct2trainer.native.lua_program import prepare_lua_program
from ct2trainer.native.bundle import build_trainer, read_embedded_plan
from test_native_engine import FakeMemory

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/windows/fixture_target/fixture.ct'
OWNED_SOURCE = ('[ENABLE]\nalloc(owned,100)\nowned:\npushfd\npushad\npopad\npopfd\n'
                'fld dword [esp+4]\nfsub dword [esp+4]\nret\nregistersymbol(owned)\n'
                '[DISABLE]\nunregistersymbol(owned)\ndealloc(owned)')
LUA_SOURCE = '[ENABLE]\n{$lua}\nreturn nil\n{$asm}\n' + OWNED_SOURCE.split('[ENABLE]\n', 1)[1]


class ArchitectureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def table(self, source=None, name='unrelated_64bit_name.ct'):
        path = self.directory / name
        record = ('<CheatEntry><ID>1</ID><Description>Owned</Description><VariableType>Auto Assembler Script</VariableType>'
                  '<AssemblerScript>' + escape(source) + '</AssemblerScript></CheatEntry>' if source is not None else
                  '<CheatEntry><ID>1</ID><Description>Value</Description><VariableType>4 Bytes</VariableType><Address>1000</Address></CheatEntry>')
        path.write_text('<CheatTable CheatEngineTableVersion="52"><CheatEntries>' + record + '</CheatEntries></CheatTable>', encoding='utf-8')
        return path

    def plan(self, architecture='x64', source=None):
        return compile_table(self.table(source), 'Target.exe', architecture=architecture)

    def test_architecture_is_explicit_not_filename_or_register_inference(self):
        plan = self.plan('x86', OWNED_SOURCE)
        self.assertEqual(plan['schema'], 2)
        self.assertEqual(plan['target_architecture'], prepare_architecture('x86'))
        self.assertEqual(plan['entries'][0]['program']['bitness'], 32)
        other = self.plan('x64', OWNED_SOURCE)
        self.assertEqual(other['entries'][0]['program']['bitness'], 64)
        self.assertNotEqual(plan['trainer_id'], other['trainer_id'])
        # Source structure is not a promise that PUSHAD encodes in x64; actual
        # linking remains a separate pre-publication gate.

    def test_default_is_fixed_x64(self):
        plan = compile_table(self.table(), 'Target.exe')
        self.assertEqual(plan['target_architecture'], prepare_architecture('x64'))

    def test_invalid_option_refuses_before_table_read(self):
        for value in ('auto', 'arm64', 'X86', '32', 32, True, None):
            with self.subTest(value=value), patch('ct2trainer.native.compiler.read_table', side_effect=AssertionError('table read')):
                with self.assertRaisesRegex(NativeCompileError, 'architecture'):
                    compile_table('missing.ct', 'Target.exe', architecture=value)

    def test_all_lua_static_envelope_profiles_share_selected_32bit_mode(self):
        with patch('ct2trainer.native.lua_host.LuaHost.execute', side_effect=AssertionError('Lua ran')):
            plan = self.plan('x86', LUA_SOURCE)
        self.assertTrue(plan['entries'][0]['supported'], plan['entries'][0]['reason'])
        program = plan['entries'][0]['lua_program']
        self.assertEqual(program['bitness'], 32)
        self.assertEqual(program['static_program']['bitness'], 32)
        runtime_validate(plan)

    def test_pure_lua_profile_also_uses_declared_architecture(self):
        plan = self.plan('x86', '[ENABLE]\nluacall(return nil)\n[DISABLE]\nluacall(return nil)')
        self.assertEqual(plan['entries'][0]['lua_program']['bitness'], 32)
        self.assertIsNone(plan['entries'][0]['lua_program']['static_program'])

    def test_source_valid_assembly_of_wrong_bitness_is_refused(self):
        plan = self.plan('x86', OWNED_SOURCE)
        plan['entries'][0]['program'] = prepare_program(OWNED_SOURCE, 'Target.exe', bitness=64)
        with self.assertRaisesRegex(NativeCompileError, 'declared target architecture'):
            validate_plan(plan)
        with self.assertRaisesRegex(NativeRuntimeError, 'declared target architecture'):
            runtime_validate(plan)

    def test_source_valid_lua_of_wrong_bitness_is_refused(self):
        plan = self.plan('x86', LUA_SOURCE)
        plan['entries'][0]['lua_program'] = prepare_lua_program(LUA_SOURCE, 'Target.exe', bitness=64)
        with self.assertRaisesRegex(NativeCompileError, 'declared target architecture'):
            validate_plan(plan)

    def test_target_profile_cannot_have_bool_bits_extra_fields_or_unknown_machine(self):
        for mutation in (lambda p: p.update(bitness=True), lambda p: p.update(pointer_size=4.0),
                         lambda p: p.update(machine='arm64'), lambda p: p.update(source_hint='name'),
                         lambda p: p.update(bitness=64), lambda p: p.update(schema='future')):
            plan = self.plan('x86')
            mutation(plan['target_architecture'])
            with self.subTest(profile=plan['target_architecture']), self.assertRaises(NativeCompileError):
                validate_plan(plan)

    def test_schema2_missing_architecture_and_selection_refused(self):
        for field in ('target_architecture', 'selected_ids'):
            plan = self.plan('x86')
            del plan[field]
            with self.subTest(field=field), self.assertRaises(NativeCompileError):
                validate_plan(plan)

    def test_changed_architecture_selection_or_trainer_hash_rejected_for_data_only_plan(self):
        for mutation in (lambda p: p.update(target_architecture=prepare_architecture('x64')),
                         lambda p: p.update(trainer_id='a'*16),
                         lambda p: (p.update(selected_ids=[]), p['entries'][0].update(selected=False))):
            plan = self.plan('x86')
            mutation(plan)
            with self.assertRaisesRegex(NativeCompileError, 'Trainer identity'):
                validate_plan(plan)

    def legacy(self):
        plan = self.plan('x64')
        plan['schema'] = 1
        del plan['target_architecture']
        identity = {'engine':'ct2trainer','schema':1,'table_sha256':plan['table_sha256'],
                    'process_name':plan['process_name'].casefold(),'selected_ids':plan['selected_ids']}
        plan['trainer_id'] = sha256(json.dumps(identity, sort_keys=True, separators=(',',':')).encode()).hexdigest()[:16]
        return plan

    def test_legacy_plan_remains_fixed_x64_with_old_identity(self):
        plan = self.legacy()
        runtime_validate(plan)
        self.assertEqual(plan_architecture(plan), prepare_architecture('x64'))
        self.assertNotEqual(plan['trainer_id'], self.plan('x64')['trainer_id'])
        memory = FakeMemory()
        require_target_architecture(plan, memory)
        memory.pointer_size = 4
        with self.assertRaisesRegex(ArchitectureError, 'mismatch'):
            require_target_architecture(plan, memory)

    def test_legacy_schema_cannot_assert_32bit_mode(self):
        plan = self.legacy()
        plan['target_architecture'] = prepare_architecture('x86')
        with self.assertRaisesRegex(NativeCompileError, 'Legacy schema'):
            validate_plan(plan)

    def test_schema2_downgrade_cannot_reuse_an_architecture_bound_identity(self):
        for architecture in ('x86', 'x64'):
            plan = self.plan(architecture)
            plan['schema'] = 1
            del plan['target_architecture']
            with self.subTest(architecture=architecture), self.assertRaisesRegex(NativeCompileError, 'Trainer identity'):
                validate_plan(plan)

    def test_legacy_generated_selection_and_original_identity_are_required(self):
        plan = self.legacy()
        plan['trainer_id'] = 'a' * 16
        with self.assertRaisesRegex(NativeCompileError, 'Trainer identity'):
            validate_plan(plan)
        plan = self.legacy()
        del plan['selected_ids']
        with self.assertRaisesRegex(NativeCompileError, 'exact selected record IDs'):
            validate_plan(plan)

    def test_unknown_held_bitness_never_becomes_a_write_permit(self):
        for observed in (None, True, 4.0, 16, 0):
            memory = FakeMemory()
            memory.pointer_size = observed
            with self.subTest(observed=observed), self.assertRaisesRegex(ArchitectureError, 'unavailable'):
                require_target_architecture(self.plan('x86'), memory)

    def engine(self, plan, memory):
        result = TrainerEngine(plan, self.directory/'state', lambda _name: memory, self.directory/'shared')
        self.addCleanup(result.close)
        return result

    def test_attach_mismatch_closes_held_handle_before_session_claim_or_any_memory_action(self):
        plan = compile_table(FIXTURE, 'FixtureTarget.exe', architecture='x86')
        memory = FakeMemory()
        engine = self.engine(plan, memory)
        with patch.object(engine.store, 'claim_session', side_effect=AssertionError('session claimed')), \
             patch.object(engine, '_enable', side_effect=AssertionError('activation started')):
            status = engine.poll()
        self.assertIn('mismatch', status)
        self.assertFalse(engine.connected)
        self.assertFalse(engine.blocked)
        self.assertTrue(memory.closed)
        self.assertFalse(memory.writes)
        self.assertFalse(engine.store.session.exists())
        self.assertFalse(list((self.directory/'shared').glob('*.json')))

    def test_value_only_plan_cannot_attach_wrong_architecture(self):
        memory = FakeMemory()
        engine = self.engine(self.plan('x86'), memory)
        engine.poll()
        self.assertFalse(engine.connected)
        self.assertFalse(memory.writes)

    def test_matching_x86_value_controller_uses_4byte_pointer_chain(self):
        memory = FakeMemory()
        memory.pointer_size = 4
        memory.data[0x18:0x1c] = struct.pack('<I', 0x1040)
        memory.data[0x1c:0x20] = b'\xff' * 4  # Reading an 8-byte pointer would fail.
        memory.data[0x44:0x48] = struct.pack('<I', 1234)
        path = self.directory/'pointer.ct'
        path.write_text('<CheatTable CheatEngineTableVersion="52"><CheatEntries><CheatEntry><ID>2</ID>'
                        '<Description>Pointer value</Description><VariableType>4 Bytes</VariableType>'
                        '<Address>1018</Address><Offsets><Offset>4</Offset></Offsets></CheatEntry>'
                        '</CheatEntries></CheatTable>')
        plan = compile_table(path, 'FixtureTarget.exe', architecture='x86')
        engine = self.engine(plan, memory)
        engine.poll()
        self.assertTrue(engine.connected, engine.status)
        self.assertEqual(engine.read_value(2), '1234')
        self.assertEqual(engine.set_value(2, '4321'), '4321')
        self.assertEqual(memory.read(0x1044, 4), struct.pack('<I', 4321))
        self.assertEqual(memory.read(0x101c, 4), b'\xff' * 4)

    def test_attached_bitness_change_refuses_value_write_and_retains_owner_receipts(self):
        memory = FakeMemory()
        plan = compile_table(FIXTURE, 'FixtureTarget.exe', architecture='x64')
        engine = self.engine(plan, memory)
        engine.poll()
        before = engine.store.session.read_bytes()
        memory.pointer_size = 4
        with self.assertRaisesRegex(NativeRuntimeError, 'mismatch'):
            engine.set_value(2, '999')
        self.assertTrue(engine.blocked)
        self.assertFalse(memory.writes)
        self.assertEqual(engine.store.session.read_bytes(), before)

    def test_attached_poll_bitness_change_prevents_callbacks_and_freezes(self):
        memory = FakeMemory()
        plan = compile_table(FIXTURE, 'FixtureTarget.exe', architecture='x64')
        engine = self.engine(plan, memory)
        engine.poll()
        # WP-14 (C1): value 2 is staged on the anchor provider; enable it
        # first so the freeze below is admitted.
        engine.toggle(0, True)
        engine.set_freeze(2)
        memory.pointer_size = 4
        with patch.object(engine, '_check_patches', side_effect=AssertionError('receipt read after mismatch')):
            engine.poll()
        self.assertTrue(engine.blocked)
        self.assertFalse(memory.writes)

    def test_saved_on_restore_mismatch_keeps_saved_wishes_without_mutation(self):
        plan = compile_table(FIXTURE, 'FixtureTarget.exe', architecture='x64')
        memory = FakeMemory()
        memory.pointer_size = 4
        engine = self.engine(plan, memory)
        engine.store.save({0, 1})
        engine.desired = {0, 1}
        saved = engine.store.path.read_bytes()
        with patch.object(engine, '_enable', side_effect=AssertionError('saved restore ran')):
            engine.poll()
        self.assertFalse(engine.connected)
        self.assertEqual(engine.store.path.read_bytes(), saved)
        self.assertEqual(engine.desired, {0, 1})
        self.assertFalse(memory.writes)

    def test_close_refuses_architecture_change_before_restoring_active_patches(self):
        memory = FakeMemory()
        plan = compile_table(FIXTURE, 'FixtureTarget.exe', architecture='x64')
        engine = self.engine(plan, memory)
        engine.poll()
        engine.toggle(1, True)
        writes = list(memory.writes)
        before = engine.store.session.read_bytes()
        memory.pointer_size = 4
        self.assertFalse(engine.close())
        self.assertTrue(engine.blocked)
        self.assertEqual(memory.writes, writes)
        self.assertEqual(engine.store.session.read_bytes(), before)

    def test_cli_inspect_and_prepare_bind_explicit_x86(self):
        from ct2trainer.native.__main__ import main
        path = self.table(OWNED_SOURCE)
        output = self.directory/'source.json'
        capture = io.StringIO()
        with redirect_stdout(capture):
            self.assertEqual(main(['inspect', str(path), '--process', 'Target.exe', '--architecture', 'x86']), 0)
        self.assertEqual(json.loads(capture.getvalue())['entries'][0]['program']['bitness'], 32)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(['prepare', str(path), '--process', 'Target.exe', '--architecture', 'x86', '--output', str(output)]), 0)
        self.assertEqual(json.loads(output.read_text())['target_architecture'], prepare_architecture('x86'))

    def template(self):
        path = self.directory/'template.exe'
        stub = bytearray(128)
        stub[:2] = b'MZ'
        struct.pack_into('<I', stub, 0x3c, 64)
        stub[64:68] = b'PE\0\0'
        struct.pack_into('<H', stub, 68, 0x8664)
        path.write_bytes(stub + sha256(stub).digest() + b'CT2BASE1')
        return path

    def test_x86_target_overlay_keeps_x64_controller_and_exact_target_metadata(self):
        plan = self.plan('x86')
        template = self.template()
        exe, report = build_trainer(plan, self.directory/'trainer.exe', template)
        self.assertEqual(read_embedded_plan(exe), plan)
        metadata = json.loads(report.read_text())
        self.assertEqual(metadata['target_architecture'], prepare_architecture('x86'))
        self.assertEqual(metadata['controller_architecture'], 'x64')
        self.assertTrue(exe.read_bytes().startswith(template.read_bytes()))

    def test_cli_build_propagates_architecture_and_launcher_smoke_reports_it(self):
        from ct2trainer.native.__main__ import main
        from ct2trainer.native.launcher import main as launch
        path = self.table()
        exe = self.directory/'trainer.exe'
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(['build', str(path), '--process', 'Target.exe', '--architecture', 'x86',
                                   '--template', str(self.template()), '--output', str(exe)]), 0)
        plan = read_embedded_plan(exe)
        source = self.directory/'source.json'
        source.write_text(json.dumps(plan))
        smoke = self.directory/'smoke.json'
        with redirect_stdout(io.StringIO()):
            self.assertEqual(launch(['--plan', str(source), '--smoke-output', str(smoke)]), 0)
        self.assertEqual(json.loads(smoke.read_text())['target_architecture'], prepare_architecture('x86'))


class OwnedX86GateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.fixture = ROOT/'tests/windows/debug_hook_fixture/x86_trainer.ct'
        self.plan = compile_table(self.fixture, 'NativeDebugHookFixture-x86.exe', architecture='x86')

    def test_gate_is_bound_to_exact_owned_ct_source_profile_and_x86_mode(self):
        from ct2trainer.native.x86_probe import CT_SHA256, SOURCE_SHA256, validate_fixture_plan
        self.assertEqual(sha256(self.fixture.read_bytes()).hexdigest(), CT_SHA256)
        self.assertEqual(self.plan['entries'][0]['program']['source_sha256'], SOURCE_SHA256)
        validate_fixture_plan(self.plan)
        changed = deepcopy(self.plan)
        source = changed['entries'][0]['program']['source'].replace('add eax,#100', 'add eax,#200')
        changed['entries'][0]['program'] = prepare_program(source, changed['process_name'], bitness=32)
        validate_plan(changed)  # Canonical source, but not the pinned owned test.
        with self.assertRaisesRegex(ValueError, 'source profiles'):
            validate_fixture_plan(changed)

    def test_invalid_plan_reported_before_target_read_spawn_or_state_claim(self):
        from ct2trainer.native.x86_probe import run_probe
        changed = deepcopy(self.plan)
        changed['target_architecture']['bitness'] = 64
        report = self.directory/'report.json'
        with patch('ct2trainer.native.x86_probe.subprocess.Popen') as spawn, \
             patch('ct2trainer.native.engine.TrainerEngine') as controller:
            with self.assertRaises((ValueError, RuntimeError)):
                run_probe(changed, self.directory/'missing.exe', report)
        spawn.assert_not_called()
        controller.assert_not_called()
        evidence = json.loads(report.read_text())
        self.assertEqual((evidence['status'], evidence['checks']), ('failed', []))
        self.assertFalse(evidence['game_runtime_verified'])
        self.assertFalse(list(self.directory.glob('*state')))

    def test_foreign_binary_hash_refused_before_spawn_with_fresh_failure_evidence(self):
        from ct2trainer.native.x86_probe import PROCESS_NAME, run_probe
        target = self.directory/PROCESS_NAME
        target.write_bytes(b'not the owned pinned binary')
        report = self.directory/'report.json'
        with patch('ct2trainer.native.x86_probe.subprocess.Popen') as spawn, \
             patch('ct2trainer.native.engine.TrainerEngine') as controller:
            with self.assertRaisesRegex(ValueError, 'pinned owned target binary'):
                run_probe(self.plan, target, report)
        spawn.assert_not_called()
        controller.assert_not_called()
        self.assertEqual(json.loads(report.read_text())['status'], 'failed')

    def test_prior_report_bytes_are_never_overwritten(self):
        from ct2trainer.native.x86_probe import run_probe
        report = self.directory/'report.json'
        report.write_bytes(b'earlier evidence')
        with patch('ct2trainer.native.x86_probe.subprocess.Popen') as spawn:
            with self.assertRaises(FileExistsError):
                run_probe(self.plan, self.directory/'missing.exe', report)
        spawn.assert_not_called()
        self.assertEqual(report.read_bytes(), b'earlier evidence')

    def test_launcher_fixture_flags_require_evidence_and_exclude_other_modes(self):
        from ct2trainer.native.launcher import main
        source = self.directory/'plan.json'
        source.write_text(json.dumps(self.plan))
        with patch('ct2trainer.native.x86_probe.run_probe') as probe, redirect_stderr(io.StringIO()):
            self.assertEqual(main(['--plan', str(source), '--x86-fixture-target', 'missing.exe']), 2)
            self.assertEqual(main(['--plan', str(source), '--x86-fixture-report', 'missing.json']), 2)
            self.assertEqual(main(['--plan', str(source), '--x86-fixture-target', 'missing.exe',
                                   '--x86-fixture-report', 'missing.json', '--smoke']), 2)
        probe.assert_not_called()


class ArchitectureMemoryTests(unittest.TestCase):
    def detector(self, guest=0x14c, native=0x8664):
        from ct2trainer.native.memory import ProcessMemory, _WORD
        memory = ProcessMemory.__new__(ProcessMemory)
        memory._handle = 7
        def detect(handle, guest_pointer, native_pointer):
            ctypes.cast(guest_pointer, ctypes.POINTER(_WORD)).contents.value = guest
            ctypes.cast(native_pointer, ctypes.POINTER(_WORD)).contents.value = native
            return True
        memory._kernel = SimpleNamespace(IsWow64Process2=Mock(side_effect=detect))
        return memory

    def test_exact_wow64_and_native_target_widths_use_native_amd64_machine(self):
        self.assertEqual(self.detector()._detect_pointer_size(), 4)
        self.assertEqual(self.detector(guest=0)._detect_pointer_size(), 8)
        self.assertEqual(self.detector(guest=0x8664)._detect_pointer_size(), 8)

    def test_arm64_host_and_unknown_guest_refused_even_with_x64_controller(self):
        from ct2trainer.native.memory import ProcessMemoryError
        for guest, native in ((0x14c, 0xaa64), (0x8664, 0xaa64), (0, 0xaa64), (0, 0), (0xaa64, 0x8664)):
            with self.subTest(guest=guest, native=native), self.assertRaises(ProcessMemoryError):
                self.detector(guest, native)._detect_pointer_size()

    def test_old_ambiguous_wow64_boolean_cannot_prove_host_architecture(self):
        from ct2trainer.native.memory import ProcessMemoryError
        memory = self.detector()
        memory._kernel = SimpleNamespace(IsWow64Process=Mock(return_value=True), GetNativeSystemInfo=Mock())
        with self.assertRaisesRegex(ProcessMemoryError, 'IsWow64Process2 is required'):
            memory._detect_pointer_size()
        memory._kernel.IsWow64Process.assert_not_called()
        memory._kernel.GetNativeSystemInfo.assert_not_called()

    def modules(self, records, pointer_size=4):
        from ct2trainer.native.memory import ProcessMemory, _MODULEENTRY32W
        memory = ProcessMemory.__new__(ProcessMemory)
        memory._pointer_size = pointer_size
        memory._pid = 17
        memory._lock = threading.RLock()
        memory._require_alive = Mock()
        index = -1
        def advance(snapshot, destination):
            nonlocal index
            index += 1
            if index >= len(records):
                return False
            base, size, path, machine, magic = records[index]
            entry = ctypes.cast(destination, ctypes.POINTER(_MODULEENTRY32W)).contents
            entry.szModule = 'owned.exe'
            entry.szExePath = path
            entry.modBaseAddr = base
            entry.modBaseSize = size
            return True
        memory._kernel = SimpleNamespace(CreateToolhelp32Snapshot=Mock(return_value=7),
                                          Module32FirstW=Mock(side_effect=advance),
                                          Module32NextW=Mock(side_effect=advance), CloseHandle=Mock(return_value=True))
        def metadata(address, size):
            base, length, path, machine, magic = records[index]
            if address == base and size == 64:
                dos = bytearray(64); dos[:2] = b'MZ'; dos[60:64] = (64).to_bytes(4, 'little')
                return bytes(dos)
            pe = bytearray(26); pe[:4] = b'PE\0\0'; pe[4:6] = machine.to_bytes(2, 'little'); pe[24:26] = magic.to_bytes(2, 'little')
            self.assertEqual((address, size), (base+64, 26))
            return bytes(pe)
        memory._read_host_metadata = Mock(side_effect=metadata)
        return memory

    def test_identical_wow64_snapshot_records_collapse_after_actual_pe32_check(self):
        record = (0x1000, 0x100, r'C:\owned.exe', 0x14c, 0x10b)
        memory = self.modules([record, record])
        with patch('ctypes.get_last_error', return_value=18, create=True):
            self.assertEqual(memory.module('owned.exe'), (0x1000, 0x100))
        self.assertEqual(memory._read_host_metadata.call_count, 4)
        memory._kernel.CloseHandle.assert_called_once_with(7)

    def test_conflicting_base_size_or_exact_path_remains_ambiguous(self):
        from ct2trainer.native.memory import ProcessMemoryError
        record = (0x1000, 0x100, r'C:\owned.exe', 0x14c, 0x10b)
        for other in ((0x2000, 0x100, record[2], 0x14c, 0x10b),
                      (0x1000, 0x110, record[2], 0x14c, 0x10b),
                      (0x1000, 0x100, r'D:\owned.exe', 0x14c, 0x10b)):
            memory = self.modules([record, other])
            with self.subTest(other=other), patch('ctypes.get_last_error', return_value=18, create=True):
                with self.assertRaisesRegex(ProcessMemoryError, 'found 2'):
                    memory.module('owned.exe')
            memory._kernel.CloseHandle.assert_called_once_with(7)

    def test_target_module_excludes_native64_mapping_of_same_named_image(self):
        native = (0x100000000, 0x100, r'C:\native\owned.exe', 0x8664, 0x20b)
        guest = (0x1000, 0x100, r'C:\guest\owned.exe', 0x14c, 0x10b)
        memory = self.modules([native, guest, guest])
        with patch('ctypes.get_last_error', return_value=18, create=True):
            self.assertEqual(memory.module('owned.exe'), (0x1000, 0x100))

    def test_module_scan_time_bound_closes_snapshot_without_truncated_success(self):
        from ct2trainer.native.memory import ProcessMemoryError
        memory = self.modules([(0x1000, 0x100, r'C:\owned.exe', 0x14c, 0x10b)])
        with patch('ct2trainer.native.memory.time.monotonic', side_effect=[0, 6]):
            with self.assertRaisesRegex(ProcessMemoryError, 'count/time bound'):
                memory.module('owned.exe')
        memory._read_host_metadata.assert_not_called()
        memory._kernel.CloseHandle.assert_called_once_with(7)


if __name__ == '__main__':
    unittest.main()
