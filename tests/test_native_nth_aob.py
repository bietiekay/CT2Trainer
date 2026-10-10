"""Owned scan inputs prove ordering, scope ownership and read-only dry linking."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

from test_native_lua_activation import Memory
from test_native_engine_code import Coordinator
from ct2trainer.native.aa_luacall import LuaCallBinding, NthAobPort
from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import TrainerEngine, NativeRuntimeError
from ct2trainer.native.lua_activation import LuaActivation, finalized_receipt
from ct2trainer.native.lua_bootstrap import prepare_lua_bootstrap
from ct2trainer.native.lua_program import prepare_lua_program, LuaProgramError, validate_lua_program
from ct2trainer.native.nth_aob import (NthAOBError, definition_from_call, prepare_helper_contract,
                                       scan_nth, recheck_result, validate_result,
                                       REVIEWED_HELPER_SHA256, REVIEWED_BOOTSTRAP_SHA256)


SOURCE = '''[ENABLE]
luaCall(ct2trainerNthAOB("nthAnchor","FixtureTarget.exe","11 00 00 00",2))
assert(nthAnchor,11 00 00 00)
nthAnchor:
dd 2
[DISABLE]
nthAnchor:
dd 11'''


class ScanMemory(Memory):
    def __init__(self):
        super().__init__()
        self.scan_calls = []
        self.after_scan = None
        self.data[64:68] = self.data[96:100] = self.data[128:132] = bytes.fromhex('11000000')

    def scan_matches(self, pattern, *, start, end, max_results):
        self.scan_calls.append((pattern, start, end, max_results))
        tokens = pattern.split()
        matches = []
        for address in range(start, end - len(tokens) + 1):
            raw = self.read(address, len(tokens))
            if all(all(nibble == '?' or nibble == format(byte, '02X')[index]
                       for index, nibble in enumerate(token)) for token, byte in zip(tokens, raw)):
                matches.append(address)
        if self.after_scan is not None:
            self.after_scan(self)
        return list(reversed(matches))  # The adapter owns explicit ascending ordering.


class NthAOBTests(unittest.TestCase):
    def setUp(self):
        self.memory = ScanMemory()
        self.definition = definition_from_call('ct2trainerNthAOB("nthAnchor","FixtureTarget.exe","11 00 00 00",2)', 1)

    def test_occurrence_is_one_based_sorted_and_module_bounded(self):
        result = scan_nth(self.definition, self.memory, expected_identity=self.memory.identity)
        self.assertEqual(result['address'], 0x1060)
        self.assertEqual(result['match_count'], 3)
        self.assertEqual(result['bytes'], '11000000')
        self.assertEqual(self.memory.scan_calls, [('11 00 00 00', 0x1000, 0x1100, 65536)])
        validate_result(result)
        self.assertFalse(self.memory.writes)

    def test_wildcard_nibbles_are_rechecked_without_freezing_unconstrained_bits(self):
        definition = definition_from_call('ct2trainerNthAOB("owned","FixtureTarget.exe","1? 00 00 00",2)', 1)
        result = scan_nth(definition, self.memory)
        self.memory.data[96] = 0x1F
        recheck_result(result, self.memory)
        self.memory.data[96] = 0x20
        with self.assertRaisesRegex(NthAOBError, 'selected bytes changed'):
            recheck_result(result, self.memory)
        recheck_result(result, self.memory, before_publication=False)

    def test_missing_occurrence_caps_and_malformed_backend_results_fail_closed(self):
        definition = deepcopy(self.definition); definition['occurrence'] = 4
        with self.assertRaisesRegex(NthAOBError, 'occurrence was not found'):
            scan_nth(definition, self.memory)
        for matches in ([0x1060, 0x1060], [0xFFF], [0x10FF], [True], (), [0x1060] * 65537):
            with self.subTest(matches=type(matches).__name__):
                self.memory.scan_matches = lambda *args, **kw: matches
                with self.assertRaises(NthAOBError):
                    scan_nth(self.definition, self.memory)
        self.memory.scan_matches = lambda *args, **kw: (_ for _ in ()).throw(OSError('scan cap exceeded'))
        with self.assertRaisesRegex(OSError, 'scan cap exceeded'):
            scan_nth(self.definition, self.memory)
        self.assertFalse(self.memory.writes)

    def test_changed_selected_bytes_module_or_target_cannot_publish_a_result(self):
        for change in (lambda memory: memory.data.__setitem__(96, 0x20),
                       lambda memory: setattr(memory, 'creation_time', 999),
                       lambda memory: setattr(memory, 'alive', False),
                       lambda memory: setattr(memory, 'module', lambda name: (0x1000, 128))):
            with self.subTest(change=change):
                memory = ScanMemory(); memory.after_scan = change
                with self.assertRaises(NthAOBError):
                    scan_nth(self.definition, memory)
                self.assertFalse(memory.writes)

    def test_forged_receipt_cannot_change_symbol_module_pattern_or_target_bounds(self):
        receipt = scan_nth(self.definition, self.memory)
        for key, value in (('address', 0x1100), ('bytes', '22000000'), ('match_count', True),
                           ('target', [True, 456]), ('module', [0x1000, 0]), ('schema', 'foreign')):
            changed = deepcopy(receipt); changed[key] = value
            with self.subTest(key=key), self.assertRaises(NthAOBError):
                validate_result(changed)
        changed = deepcopy(receipt); changed['definition']['pattern'] = '11 00 00'
        with self.assertRaises(NthAOBError):
            validate_result(changed)

    def test_reviewed_input_provenance_is_exact_and_preserves_other_table_actions(self):
        source_path = Path(__file__).resolve().parents[1] / 'TableReferences' / 'case-06.ct'
        if not source_path.is_file():
            self.skipTest('third-party game inputs are intentionally absent from exported source')
        from ct2trainer.table import read_table
        read_table(source_path)
        source = ET.fromstring(source_path.read_bytes()).findtext('LuaScript')
        profile = prepare_lua_bootstrap(source)
        contract = prepare_helper_contract(profile)
        self.assertEqual(contract['helper_sha256'], REVIEWED_HELPER_SHA256)
        self.assertEqual(contract['bootstrap_sha256'], REVIEWED_BOOTSTRAP_SHA256)
        self.assertIn('registerCustomTypeAutoAssembler', profile['source'])
        changed = prepare_lua_bootstrap(source + '\n lua_aobscan=function() end')
        self.assertIsNone(prepare_helper_contract(changed))
        self.assertIsNone(prepare_helper_contract(prepare_lua_bootstrap('function lua_aobscan() end')))
        call = 'lua_aobscan("scanOwned","re2.exe","EB **",2)'
        self.assertIsNone(definition_from_call(call, 1))
        self.assertEqual(definition_from_call(call, 1, contract)['pattern'], 'EB ??')


class _NthPort(NthAobPort):
    def scan(self, *, symbol, module, pattern, occurrence):
        return 0x1060


class _NthBinding(LuaCallBinding):
    def function_names(self):
        return frozenset({'ct2trainerNthAOB'})

    def aob_port(self):
        return _NthPort()


class OwnedNthActivationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.memory = ScanMemory()
        self.engine = None

    def tearDown(self):
        if self.engine is not None and not self.engine.closed:
            self.memory.alive = False
            self.engine.poll()
            self.engine.close()

    def make_engine(self, source=SOURCE):
        table = self.root / 'owned.ct'
        table.write_text('<CheatTable CheatEngineTableVersion="45"><CheatEntries><CheatEntry><ID>1</ID>'
                         '<Description>Owned nth scan</Description><VariableType>Auto Assembler Script</VariableType>'
                         '<AssemblerScript><![CDATA[' + source + ']]></AssemblerScript></CheatEntry></CheatEntries></CheatTable>',
                         encoding='utf-8')
        plan = compile_table(table, 'FixtureTarget.exe')
        self.assertTrue(plan['entries'][0]['supported'], plan['entries'][0]['reason'])
        self.engine = TrainerEngine(plan, state_dir=self.root / 'state', process_lock_dir=self.root / 'shared',
                                    memory_factory=lambda name: self.memory, hook_coordinator=Coordinator(),
                                    luacall_binding_factory=lambda engine: _NthBinding())
        self.engine.poll()
        return self.engine

    def test_confirmed_activation_journals_owned_scan_and_disable_uses_captured_address(self):
        engine = self.make_engine()
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(engine.symbols['nthanchor'], 0x1060)
        self.assertEqual(self.memory.read(0x1060, 4), bytes.fromhex('02000000'))
        scope = engine.lua_activations[1]
        receipt = json.loads(scope.path.read_bytes())
        self.assertEqual(receipt['nth_aob_results'][0]['address'], 0x1060)
        self.assertEqual(receipt['symbols']['nthanchor'], 0x1060)
        scans = len(self.memory.scan_calls)
        self.memory.data[32:36] = bytes.fromhex('11000000')  # A fresh nth scan would now choose a different site.
        self.assertFalse(engine.toggle(1, False))
        self.assertEqual(len(self.memory.scan_calls), scans)
        self.assertEqual(self.memory.read(0x1060, 4), bytes.fromhex('11000000'))
        self.assertFalse(engine.symbols)
        self.assertTrue(scope.host.cancelled)

    def test_actual_dry_link_resolves_private_scan_for_lua_and_never_changes_receipts_or_memory(self):
        source = SOURCE.replace('assert(nthAnchor,', '{$lua}\nassert(getAddress("nthAnchor")==0x1060)\n'
                                'assert(readInteger("nthAnchor")==17)\n{$asm}\nassert(nthAnchor,')
        engine = self.make_engine(source)
        scope = LuaActivation(engine, 1)
        try:
            before = scope.path.read_bytes()
            diagnostic = scope.check_program(engine.entries[1]['lua_program'])
            self.assertTrue(diagnostic['dry_run'])
            self.assertFalse(diagnostic['publishable'])
            self.assertEqual(diagnostic['assembler']['enable']['blocks'][0]['address'], 0x1060)
            self.assertEqual(scope.path.read_bytes(), before)
            self.assertFalse(scope.symbols)
            self.assertFalse(scope.nth_aob_results)
            self.assertFalse(engine.symbols)
            self.assertFalse(self.memory.writes)
        finally:
            scope.close()

    def test_invalid_nasm_instruction_is_rejected_before_scan_symbol_publication(self):
        engine = self.make_engine(SOURCE.replace('dd 2', 'not_a_real_instruction rax'))
        with self.assertRaises(NativeRuntimeError):
            engine.toggle(1, True)
        self.assertFalse(engine.symbols)
        self.assertFalse(engine.desired)
        self.assertFalse(self.memory.writes)
        self.assertFalse(engine.blocked)

    def test_foreign_symbol_collision_is_refused_without_unregistering_its_owner(self):
        engine = self.make_engine()
        engine.symbols['nthanchor'] = 0x1040
        with self.assertRaisesRegex(NativeRuntimeError, 'collides|owned'):
            engine.toggle(1, True)
        self.assertEqual(engine.symbols['nthanchor'], 0x1040)
        self.assertFalse(self.memory.writes)
        self.assertFalse(engine.desired)

    def test_changed_selection_before_publication_cannot_persist_a_desired_activation(self):
        engine = self.make_engine()
        self.memory.after_scan = lambda memory: memory.data.__setitem__(96, 0x22)
        with self.assertRaisesRegex(NativeRuntimeError, 'selected bytes changed'):
            engine.toggle(1, True)
        self.assertFalse(engine.symbols)
        self.assertFalse(engine.desired)
        self.assertFalse(self.memory.writes)
        self.assertFalse(engine.blocked)

    def test_context_changed_during_staging_is_rechecked_under_publication_proof(self):
        from ct2trainer.native.hooks import HookManager
        source = SOURCE.replace('"11 00 00 00"', '"11 00 00 00 77 88 99 AA"')
        for offset in (64, 96, 128):
            self.memory.data[offset:offset + 8] = bytes.fromhex('11000000778899AA')
        engine = self.make_engine(source)
        original_stage = HookManager.stage
        def change_context(manager, *args, **kwargs):
            outcome = original_stage(manager, *args, **kwargs)
            self.memory.data[100] = 0x44  # Outside the four-byte write/entry guard.
            return outcome
        with patch.object(HookManager, 'stage', change_context):
            with self.assertRaisesRegex(NativeRuntimeError, 'selected bytes changed'):
                engine.toggle(1, True)
        self.assertFalse(engine.symbols)
        self.assertFalse(engine.desired)
        self.assertFalse(self.memory.writes)
        self.assertEqual(self.memory.read(0x1060, 4), bytes.fromhex('11000000'))
        self.assertFalse(engine.blocked)

    def test_terminal_scan_receipt_remains_bound_to_owner_source_and_exact_target(self):
        engine = self.make_engine()
        engine.toggle(1, True)
        scope = engine.lua_activations[1]
        engine.toggle(1, False)
        receipt = json.loads(scope.path.read_bytes())
        self.assertTrue(finalized_receipt(receipt, engine.plan))
        for change in (lambda doc: doc['nth_aob_results'][0]['target'].__setitem__(1, 999),
                       lambda doc: doc['nth_aob_results'][0]['definition'].update(occurrence=1),
                       lambda doc: doc['nth_aob_results'].append(deepcopy(doc['nth_aob_results'][0]))):
            altered = deepcopy(receipt); change(altered)
            with self.subTest(change=change):
                self.assertFalse(finalized_receipt(altered, engine.plan))
