# -*- coding: utf-8 -*-
"""Wiring tests: aa_luacall plan model active in compiler + engine gate.

Complements the Stage-1 contract tests (tests/test_native_aa_luacall.py,
which pin the plan model itself).  This file pins that the model is ACTIVE
in the pipeline:

- compile_table embeds the deterministic luaCall plan (lua_call_plan) into
  supported pure-AA records that carry luaCall lines;
- expressions outside the pinned single-call grammar (multi-statement
  bodies, function definitions, return expressions) stay in the Lua
  program profile domain: no static plan, no binding gate, existing
  host execution behavior unchanged (the plan model itself refuses
  them deterministically, pinned here);
- records routed through {$lua} mode sections carry no luaCall plan (the
  plan model's explicit domain exclusion);
- the number grammar accepts the pinned corpus decimal shape
  (speedhack_setSpeed(2.5)) and keeps exponents/leading-dot forms refused;
- the engine requires an injected LuaCallBinding before a record with an
  embedded plan may activate: no factory / null binding / uncovered
  function / missing AOB port are refused visibly before any Lua runs,
  with no partial publish;
- a covering binding lets activation proceed through the owned Lua host
  (bootstrap helpers run, symbols register and unregister on the
  enable/disable round trip).

Self-contained synthetic CT (no TableReferences, no CE inputs); the fake
memory reuses the engine test harness shape.
"""
import tempfile
import unittest
import xml.sax.saxutils
from pathlib import Path

from test_native_engine import FakeMemory
from test_native_engine_code import Coordinator
from ct2trainer.native import aa_luacall
from ct2trainer.native.aa_luacall import (LuaCallBinding, NthAobPort,
                                            LuaCallParseError,
                                            analyze_luacall_program,
                                            parse_luacall, plan_from_report)
from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import (NativeRuntimeError, TrainerEngine,
                                        validate_plan)


PROCESS = "FixtureTarget.exe"

BOOTSTRAP = (
    "function noop() end\n"
    "function lua_aobscan(name, module, bytes, index)\n"
    "  registerSymbol(name, 0x1020)\n"
    "end\n"
)

NOOP_SCRIPT = "[ENABLE]\nluaCall(noop())\n[DISABLE]\nluaCall(noop())\n"
AOB_SCRIPT = (
    "[ENABLE]\n"
    'luaCall(lua_aobscan("anchor", "FixtureTarget.exe", "EB ** 75"))\n'
    "[DISABLE]\n"
    'luaCall(unregisterSymbol("anchor"))\n'
)
FUNCTION_DEFINITION_SCRIPT = (
    "[ENABLE]\n"
    "luaCall(function setup() end)\n"
    "[DISABLE]\n"
    "luaCall(setup())\n"
)
COMMENTED_SCRIPT = (
    "[ENABLE]\n"
    "// luaCall(fake())\n"
    "assert(FixtureTarget.exe+0x10,00)\n"
    "FixtureTarget.exe+0x10:\n"
    "db 01\n"
    "[DISABLE]\n"
    "FixtureTarget.exe+0x10:\n"
    "db 00\n"
)
MODE_SECTION_SCRIPT = (
    "[ENABLE]\n"
    "{$lua}\n"
    "return nil\n"
    "{$asm}\n"
    "assert(FixtureTarget.exe+0x20,00)\n"
    "FixtureTarget.exe+0x20:\n"
    "db 01\n"
    "[DISABLE]\n"
    "FixtureTarget.exe+0x20:\n"
    "db 00\n"
)


def escape(script: str) -> str:
    return xml.sax.saxutils.escape(script)


def record(entry_id: int, label: str, script: str) -> str:
    return (f'<CheatEntry><ID>{entry_id}</ID><Description>{label}</Description>'
            f'<VariableType>Auto Assembler Script</VariableType>'
            f'<AssemblerScript>{escape(script)}</AssemblerScript></CheatEntry>')


def table_xml(body: str, lua_script: str = "") -> str:
    return ('<CheatTable CheatEngineTableVersion="45"><LuaScript>'
            + lua_script + '</LuaScript><CheatEntries>' + body
            + '</CheatEntries></CheatTable>')


class Memory(FakeMemory):
    @property
    def identity(self):
        return self.pid, self.creation_time

    def _range(self, address, size):
        if not self.base <= address or address + size > self.base + len(self.data):
            raise ValueError('Outside owned fixture memory')

    def is_executable(self, address, size):
        return False


class _FakePort(NthAobPort):
    def scan(self, *, symbol, module, pattern, occurrence):
        return 0x1020


class _Binding(LuaCallBinding):
    def __init__(self, names, port=None):
        self._names = frozenset(names)
        self._port = port

    def function_names(self):
        return self._names

    def aob_port(self):
        return self._port


class LuacallCorpusShapeTests(unittest.TestCase):
    """Corpus shapes that must stay parseable (Alien Isolation speedhack)."""

    def test_decimal_arguments_parse_as_numbers(self):
        call = parse_luacall('speedhack_setSpeed(2.5)')
        self.assertEqual(call.function, 'speedhack_setSpeed')
        self.assertEqual([(a.kind, a.value) for a in call.arguments],
                         [('number', 2.5)])
        call = parse_luacall('speedhack_setSpeed(0.5)')
        self.assertEqual(call.arguments[0].value, 0.5)

    def test_malformed_decimal_forms_are_refused(self):
        for expression in ('x(2.)', 'x(.5)', 'x(2.5.1)', 'x(1e5)'):
            with self.subTest(expression=expression):
                with self.assertRaises(LuaCallParseError):
                    parse_luacall(expression)

    def test_decimal_plan_round_trips_through_the_report(self):
        source = ('[ENABLE]\n'
                  'luaCall(speedhack_setSpeed(2.5))\n'
                  '[DISABLE]\n'
                  'luaCall(speedhack_setSpeed(1))\n')
        plan = analyze_luacall_program(source)
        self.assertEqual(plan.operations[0].arguments[0].value, 2.5)
        self.assertEqual(plan.operations[0].expression,
                         'speedhack_setSpeed(2.5)')
        rebuilt = plan_from_report(plan.report())
        self.assertEqual(rebuilt, plan)
        self.assertEqual(plan.report(), rebuilt.report())


class LuacallCompilerWiringTests(unittest.TestCase):
    """compile_table embeds the plan (or blocks the record visibly)."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "luacall-wiring.CT"
        body = (record(100, '"Toggle noop"', NOOP_SCRIPT)
                + record(101, '"AOB toggle"', AOB_SCRIPT)
                + record(102, '"UI definition"', FUNCTION_DEFINITION_SCRIPT)
                + record(103, '"Plain AA"', COMMENTED_SCRIPT)
                + record(104, '"Lua section"', MODE_SECTION_SCRIPT))
        self.path.write_text(table_xml(body, BOOTSTRAP), encoding="utf-8")
        self.plan = compile_table(self.path, PROCESS)

    def _entry(self, entry_id: int) -> dict:
        return next(e for e in self.plan["entries"] if e["id"] == entry_id)

    def test_toggle_record_carries_deterministic_plan(self):
        entry = self._entry(100)
        self.assertTrue(entry["supported"], entry.get("reason"))
        report = entry["lua_call_plan"]
        self.assertEqual(report["schema"], aa_luacall.SCHEMA)
        self.assertFalse(report["one_shot"])
        self.assertEqual([op["phase"] for op in report["operations"]],
                         ["enable", "disable"])
        self.assertEqual([op["line"] for op in report["operations"]], [2, 4])
        self.assertEqual(report["operations"][0]["expression"], "noop()")
        self.assertEqual(report["aob_symbols"], [])

    def test_aob_record_plans_normalized_reference_and_symbols(self):
        entry = self._entry(101)
        self.assertTrue(entry["supported"], entry.get("reason"))
        report = entry["lua_call_plan"]
        enable_op = report["operations"][0]
        self.assertEqual(enable_op["function"], "lua_aobscan")
        self.assertEqual(enable_op["aob"], {
            "symbol": "anchor", "module": "FixtureTarget.exe",
            "pattern": "EB ?? 75", "occurrence": 1,
        })
        self.assertEqual(report["aob_symbols"], ["anchor"])
        disable_op = report["operations"][1]
        self.assertEqual(disable_op["function"], "unregisterSymbol")
        self.assertIsNone(disable_op["aob"])
        self.assertFalse(report["one_shot"])

    def test_luacall_outside_plan_grammar_falls_back_to_lua_profile(self):
        # Multi-statement / function-definition luaCall bodies are outside the
        # pinned single-call plan grammar. They are not blocked: they stay in
        # the Lua program profile domain and carry no static plan or gate.
        entry = self._entry(102)
        self.assertTrue(entry["supported"], entry.get("reason"))
        self.assertIn("lua_program", entry)
        self.assertNotIn("lua_call_plan", entry)
        # The plan model itself still refuses the expression with its pinned
        # fail-closed reason.
        with self.assertRaisesRegex(LuaCallParseError, "open parenthesis"):
            analyze_luacall_program(FUNCTION_DEFINITION_SCRIPT)

    def test_commented_luacall_stays_on_plain_assembly_path(self):
        entry = self._entry(103)
        self.assertTrue(entry["supported"], entry.get("reason"))
        self.assertIn("program", entry)
        self.assertNotIn("lua_call_plan", entry)
        self.assertNotIn("lua_program", entry)

    def test_mode_section_record_carries_no_luacall_plan(self):
        entry = self._entry(104)
        self.assertTrue(entry["supported"], entry.get("reason"))
        self.assertIn("lua_program", entry)
        self.assertNotIn("lua_call_plan", entry)

    def test_embedded_plan_survives_plan_validation(self):
        validate_plan(self.plan)  # canonical compiler output stays valid
        for tamper in (
            lambda entry: entry["lua_call_plan"].__setitem__("schema", "forged"),
            lambda entry: entry["lua_call_plan"]["operations"][0].pop("line"),
            lambda entry: entry["lua_call_plan"].__setitem__("one_shot", "yes"),
            lambda entry: entry["lua_call_plan"]["operations"][0].__setitem__(
                "phase", "preamble"),
        ):
            with self.subTest():
                import copy
                mutated = copy.deepcopy(self.plan)
                tamper(next(e for e in mutated["entries"] if e["id"] == 100))
                with self.assertRaises(NativeRuntimeError):
                    validate_plan(mutated)


class LuacallEngineGateTests(unittest.TestCase):
    """Activation gate: binding coverage is proven before Lua may run."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.ct_path = root / "luacall-engine.CT"
        body = (record(100, '"Toggle noop"', NOOP_SCRIPT)
                + record(101, '"AOB toggle"', AOB_SCRIPT))
        self.ct_path.write_text(table_xml(body, BOOTSTRAP), encoding="utf-8")
        self.root = root
        self.memory = Memory()
        self.engines = []

    def _engine(self, factory=None) -> TrainerEngine:
        plan = compile_table(self.ct_path, PROCESS)
        engine = TrainerEngine(
            plan,
            state_dir=self.root / "state",
            process_lock_dir=self.root / "shared",
            memory_factory=lambda name: self.memory,
            hook_coordinator=Coordinator(),
            luacall_binding_factory=factory)
        self.engines.append(engine)
        return engine

    def tearDown(self):
        self.memory.alive = False
        for engine in self.engines:
            engine.poll()
            engine.close()

    def test_gate_refuses_visibly_without_binding_factory(self):
        engine = self._engine()
        engine.poll()
        with self.assertRaisesRegex(
                NativeRuntimeError, 'no luacall binding factory'):
            engine.toggle(100, True)
        self.assertNotIn(100, engine.lua_activations)
        self.assertNotIn(100, engine.applied)
        self.assertIn('no luacall binding factory', engine.entry_errors[100])
        self.assertFalse(engine.blocked)
        self.assertEqual(engine.desired, set())

    def test_gate_refuses_when_factory_returns_none(self):
        engine = self._engine(factory=lambda _e: None)
        engine.poll()
        with self.assertRaisesRegex(
                NativeRuntimeError, 'returned no binding'):
            engine.toggle(100, True)
        self.assertNotIn(100, engine.lua_activations)

    def test_gate_refuses_uncovered_function_by_name_and_line(self):
        engine = self._engine(factory=lambda _e: _Binding({'lua_aobscan'}))
        engine.poll()
        with self.assertRaisesRegex(
                NativeRuntimeError,
                r"binding does not provide Lua function 'noop'"):
            engine.toggle(100, True)
        self.assertIn("line 2", engine.entry_errors[100])
        self.assertNotIn(100, engine.lua_activations)

    def test_gate_refuses_aob_reference_without_aob_port(self):
        engine = self._engine(factory=lambda _e: _Binding(
            {'lua_aobscan', 'unregisterSymbol'}))
        engine.poll()
        with self.assertRaisesRegex(
                NativeRuntimeError,
                r"aob_port' is required for AOB reference 'anchor'"):
            engine.toggle(101, True)
        self.assertNotIn(101, engine.lua_activations)
        self.assertNotIn('anchor', engine.symbols)

    def test_covering_binding_activates_and_round_trips_cleanly(self):
        engine = self._engine(factory=lambda _e: _Binding(
            {'noop', 'lua_aobscan', 'unregisterSymbol'}, _FakePort()))
        engine.poll()
        self.assertTrue(engine.toggle(100, True))
        self.assertIn(100, engine.lua_activations)
        self.assertTrue(engine.toggle(101, True))
        self.assertIn("anchor", engine.symbols)
        self.assertEqual(engine.symbols["anchor"], 0x1020)
        self.assertFalse(engine.toggle(101, False))
        self.assertNotIn("anchor", engine.symbols)
        self.assertNotIn(101, engine.lua_activations)
        self.assertFalse(engine.toggle(100, False))
        self.assertNotIn(100, engine.lua_activations)
        self.assertTrue(engine.close())


if __name__ == '__main__':
    unittest.main()
