"""Owned luacall binding: the production route behind the engine's gate.

Pins ``ct2trainer.native.luacall_binding`` (the owned runtime route for
records whose AA envelope carries luaCall(...) references):

- the port resolves one nth-AOB reference through the same owned scan
  route the record's activation journals through (``nth_aob.scan_nth``):
  module-bounded, 1-based occurrence-nth, identity/liveness-checked,
  bounded and read-only;
- the binding covers exactly the two reviewed nth-AOB helper function
  names and satisfies the gate's validation for plans of both spellings;
- a plan naming any other Lua function is refused by exact name and line
  (the owned route proves the reviewed helper names only - the generic
  table-Lua route remains open, AP-11);
- the production factory wires the trainer and owned-gate construction
  sites end to end: a real owned scan activates and journals the record,
  disable uses the captured address without a rescan, and a generic
  function record stays refused by its exact name.

Self-contained synthetic CT inputs (no TableReferences, no CE inputs);
the scan fixture reuses the engine test harness memory shape.
"""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from test_native_engine_code import Coordinator
from test_native_nth_aob import ScanMemory

from ct2trainer.native.aa_luacall import (AOB_FUNCTIONS, LuaCallBindingRefused,
                                          NthAobPort, analyze_luacall_program,
                                          validate_luacall_binding)
from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import TrainerEngine, NativeRuntimeError
from ct2trainer.native.luacall_binding import (OwnedLuaCallBinding,
                                              OwnedNthAobPort,
                                              owned_luacall_binding_factory)
from ct2trainer.native.nth_aob import NthAOBError


NTH_AOB_PROGRAM = ('[ENABLE]\n'
                   'luaCall(ct2trainerNthAOB("nthAnchor","FixtureTarget.exe","11 00 00 00",2))\n'
                   '[DISABLE]\n'
                   'db 00\n')
LUA_AOBSCAN_PROGRAM = ('[ENABLE]\n'
                       'luaCall(lua_aobscan("anchor","FixtureTarget.exe","EB ** 75"))\n'
                       '[DISABLE]\n'
                       'db 00\n')
GENERIC_PROGRAM = ('[ENABLE]\n'
                   'luaCall(speedhack_setSpeed(2.5))\n'
                   '[DISABLE]\n'
                   'luaCall(speedhack_setSpeed(1))\n')


class OwnedNthAobPortTests(unittest.TestCase):
    def setUp(self):
        self.memory = ScanMemory()
        self.engine = SimpleNamespace(memory=self.memory)

    def test_scan_returns_the_occurrence_nth_module_bounded_address(self):
        port = OwnedNthAobPort(self.engine)
        self.assertEqual(port.scan(symbol='nthAnchor', module='FixtureTarget.exe',
                                   pattern='11 00 00 00', occurrence=1), 0x1040)
        self.assertEqual(port.scan(symbol='nthAnchor', module='FixtureTarget.exe',
                                   pattern='11 00 00 00', occurrence=2), 0x1060)
        self.assertEqual(port.scan(symbol='nthAnchor', module='FixtureTarget.exe',
                                   pattern='11 00 00 00', occurrence=3), 0x1080)
        # The scan is confined to the module bounds (0x1000 + 256).
        self.assertEqual(self.memory.scan_calls[-1],
                         ('11 00 00 00', 0x1000, 0x1100, 65536))
        self.assertFalse(self.memory.writes)

    def test_wildcard_pattern_resolves_the_requested_occurrence(self):
        port = OwnedNthAobPort(self.engine)
        self.assertEqual(port.scan(symbol='owned', module='FixtureTarget.exe',
                                   pattern='1? 00 00 00', occurrence=2), 0x1060)
        self.assertFalse(self.memory.writes)

    def test_missing_occurrence_is_a_named_refusal(self):
        with self.assertRaisesRegex(NthAOBError, 'occurrence was not found'):
            OwnedNthAobPort(self.engine).scan(
                symbol='owned', module='FixtureTarget.exe',
                pattern='11 00 00 00', occurrence=4)
        self.assertFalse(self.memory.writes)

    def test_identity_or_liveness_change_refuses_before_publication(self):
        for change in (lambda memory: setattr(memory, 'alive', False),
                       lambda memory: setattr(memory, 'creation_time', 999)):
            with self.subTest(change=change.__name__ if hasattr(change, '__name__') else change):
                memory = ScanMemory()
                memory.after_scan = change
                with self.assertRaisesRegex(NthAOBError, 'identity/liveness changed'):
                    OwnedNthAobPort(SimpleNamespace(memory=memory)).scan(
                        symbol='owned', module='FixtureTarget.exe',
                        pattern='11 00 00 00', occurrence=1)
                self.assertFalse(memory.writes)

    def test_unknown_module_backend_error_propagates_named(self):
        with self.assertRaisesRegex(OSError, 'Unknown module'):
            OwnedNthAobPort(self.engine).scan(
                symbol='owned', module='Other.exe',
                pattern='11 00 00 00', occurrence=1)
        self.assertFalse(self.memory.writes)

    def test_no_attached_memory_is_a_named_refusal(self):
        for engine in (SimpleNamespace(memory=None), SimpleNamespace()):
            with self.subTest(engine=engine):
                with self.assertRaisesRegex(NthAOBError, 'no attached target memory'):
                    OwnedNthAobPort(engine).scan(
                        symbol='owned', module='FixtureTarget.exe',
                        pattern='11 00 00 00', occurrence=1)


class OwnedLuaCallBindingTests(unittest.TestCase):
    def setUp(self):
        self.engine = SimpleNamespace(memory=ScanMemory())

    def test_function_names_cover_exactly_the_reviewed_helper_names(self):
        binding = OwnedLuaCallBinding(self.engine)
        self.assertEqual(binding.function_names(), frozenset(AOB_FUNCTIONS))
        self.assertEqual(binding.function_names(),
                         frozenset({'lua_aobscan', 'ct2trainerNthAOB'}))

    def test_aob_port_is_stable_and_owned(self):
        binding = OwnedLuaCallBinding(self.engine)
        port = binding.aob_port()
        self.assertIsInstance(port, NthAobPort)
        self.assertIsInstance(port, OwnedNthAobPort)
        self.assertIs(port, binding.aob_port())

    def test_binding_satisfies_plans_of_both_helper_spellings(self):
        binding = OwnedLuaCallBinding(self.engine)
        for program in (NTH_AOB_PROGRAM, LUA_AOBSCAN_PROGRAM):
            with self.subTest(program=program.splitlines()[1]):
                plan = analyze_luacall_program(program)
                validate_luacall_binding(plan, binding)
                self.assertTrue(plan.aob_symbols)

    def test_generic_function_is_refused_by_exact_name_and_line(self):
        plan = analyze_luacall_program(GENERIC_PROGRAM)
        with self.assertRaisesRegex(
                LuaCallBindingRefused,
                r"binding does not provide Lua function 'speedhack_setSpeed'"):
            validate_luacall_binding(plan, OwnedLuaCallBinding(self.engine))
        self.assertIn('line 2', str(LuaCallBindingRefused(
            "binding does not provide Lua function 'speedhack_setSpeed'", line=2)))

    def test_factory_returns_fresh_covering_bindings(self):
        engine = SimpleNamespace(memory=ScanMemory())
        first = owned_luacall_binding_factory(engine)
        second = owned_luacall_binding_factory(engine)
        self.assertIsInstance(first, OwnedLuaCallBinding)
        self.assertIsNot(first, second)
        self.assertEqual(first.function_names(), second.function_names())
        validate_luacall_binding(analyze_luacall_program(NTH_AOB_PROGRAM), first)
        validate_luacall_binding(analyze_luacall_program(NTH_AOB_PROGRAM), second)


SOURCE = '''[ENABLE]
luaCall(ct2trainerNthAOB("nthAnchor","FixtureTarget.exe","11 00 00 00",2))
assert(nthAnchor,11 00 00 00)
nthAnchor:
dd 2
[DISABLE]
nthAnchor:
dd 11'''
GENERIC_RECORD = ('[ENABLE]\n'
                  'luaCall(speedhack_setSpeed(2.5))\n'
                  '[DISABLE]\n'
                  'luaCall(speedhack_setSpeed(1))\n')


class OwnedEngineRouteTests(unittest.TestCase):
    """The production factory wired at the construction sites, end to end."""

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

    def make_engine(self, source):
        table = self.root / 'owned-luacall.ct'
        table.write_text('<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
                         '<CheatEntry><ID>1</ID><Description>Owned route</Description>'
                         '<VariableType>Auto Assembler Script</VariableType>'
                         '<AssemblerScript><![CDATA[' + source + ']]></AssemblerScript>'
                         '</CheatEntry></CheatEntries></CheatTable>', encoding='utf-8')
        plan = compile_table(table, 'FixtureTarget.exe')
        self.assertTrue(plan['entries'][0]['supported'], plan['entries'][0]['reason'])
        self.engine = TrainerEngine(plan, state_dir=self.root / 'state',
                                    process_lock_dir=self.root / 'shared',
                                    memory_factory=lambda name: self.memory,
                                    hook_coordinator=Coordinator(),
                                    luacall_binding_factory=owned_luacall_binding_factory)
        self.engine.poll()
        return self.engine

    def test_owned_route_activates_journals_and_disable_uses_captured_address(self):
        engine = self.make_engine(SOURCE)
        self.assertTrue(engine.toggle(1, True))
        # The real owned scan (no fake port): the second occurrence in the module.
        self.assertEqual(engine.symbols['nthanchor'], 0x1060)
        self.assertEqual(self.memory.read(0x1060, 4), bytes.fromhex('02000000'))
        scope = engine.lua_activations[1]
        receipt = json.loads(scope.path.read_bytes())
        result = receipt['nth_aob_results'][0]
        self.assertEqual(result['address'], 0x1060)
        self.assertEqual(result['bytes'], '11000000')
        self.assertEqual(result['match_count'], 3)
        self.assertEqual(receipt['symbols']['nthanchor'], 0x1060)
        scans = len(self.memory.scan_calls)
        self.memory.data[32:36] = bytes.fromhex('11000000')
        # A fresh nth scan would now choose a different site.
        self.assertFalse(engine.toggle(1, False))
        self.assertEqual(len(self.memory.scan_calls), scans)
        self.assertEqual(self.memory.read(0x1060, 4), bytes.fromhex('11000000'))
        self.assertNotIn('nthanchor', engine.symbols)
        self.assertNotIn(1, engine.lua_activations)

    def test_owned_route_refuses_generic_function_record_by_exact_name(self):
        engine = self.make_engine(GENERIC_RECORD)
        with self.assertRaisesRegex(
                NativeRuntimeError,
                r"binding does not provide Lua function 'speedhack_setSpeed'"):
            engine.toggle(1, True)
        self.assertNotIn(1, engine.lua_activations)
        self.assertIn("line 2", engine.entry_errors[1])
        self.assertIn("binding does not provide Lua function 'speedhack_setSpeed'",
                      engine.entry_errors[1])
        self.assertFalse(engine.blocked)
        self.assertEqual(engine.desired, set())
        self.assertFalse(self.memory.writes)


if __name__ == '__main__':
    unittest.main()
