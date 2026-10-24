# -*- coding: utf-8 -*-
"""RT-4.5 (O20) contract tests: symbol-only static envelopes.

A binding-gated luaCall record whose static AA content is only
``unregistersymbol(<name>)`` lines in the DISABLE phase, where every
released name is one of the record's own luaCall AOB symbols, is admitted
with the deterministic ``symbol_only_disable`` marker instead of the
established no-content envelope refusal.  The marker pins the runtime
contract: no assembler receipt is created for the enable, and the
disable releases exactly the owned symbols named by the static envelope
(two-pass, fail-closed, named refusals).

Any deviation (foreign unregister name, other static directive, static
ENABLE content, malformed call grammar, real Lua sections) keeps the
existing fail-closed envelope refusal.

Self-contained synthetic CT (no TableReferences, no CE inputs); the fake
memory, coordinator, binding and AOB port reuse the engine test harness
shapes.
"""
import tempfile
import unittest
import xml.sax.saxutils
from pathlib import Path

from test_native_engine import FakeMemory
from test_native_engine_code import Coordinator
from ct2trainer.native import aa_luacall
from ct2trainer.native.aa_luacall import LuaCallBinding, NthAobPort
from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import TrainerEngine
from ct2trainer.native.lua_host import LuaHostError


PROCESS = "FixtureTarget.exe"

BOOTSTRAP = (
    "function lua_aobscan(name, module, bytes, index)\n"
    "  registerSymbol(name, 0x1020)\n"
    "end\n"
)

SYMBOL_ONLY_SCRIPT = (
    "[ENABLE]\n"
    'luaCall(lua_aobscan("aobt2", "FixtureTarget.exe", "EB ** 75", 1))\n'
    "[DISABLE]\n"
    "unregistersymbol(aobt2)\n"
)

FOREIGN_UNREGISTER_SCRIPT = (
    "[ENABLE]\n"
    'luaCall(lua_aobscan("aobt2", "FixtureTarget.exe", "EB ** 75", 1))\n'
    "[DISABLE]\n"
    "unregistersymbol(zz)\n"
)

STATIC_ENABLE_SCRIPT = (
    "[ENABLE]\n"
    'luaCall(lua_aobscan("aobt2", "FixtureTarget.exe", "EB ** 75", 1))\n'
    "FixtureTarget.exe+0x10:\n"
    "db 01\n"
    "[DISABLE]\n"
    "unregistersymbol(aobt2)\n"
    "FixtureTarget.exe+0x10:\n"
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


class SymbolOnlyCompilerTests(unittest.TestCase):
    """compile_table admits the exact shape and keeps every deviation refused."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "symbol-only.CT"
        body = (record(100, '"Symbol only"', SYMBOL_ONLY_SCRIPT)
                + record(101, '"Foreign name"', FOREIGN_UNREGISTER_SCRIPT)
                + record(102, '"Static enable"', STATIC_ENABLE_SCRIPT))
        self.path.write_text(table_xml(body, BOOTSTRAP), encoding="utf-8")
        self.plan = compile_table(self.path, PROCESS)

    def _entry(self, entry_id: int) -> dict:
        return next(e for e in self.plan["entries"] if e["id"] == entry_id)

    def test_symbol_only_record_is_admitted_with_marker_and_provider(self):
        entry = self._entry(100)
        self.assertTrue(entry["supported"], entry.get("reason"))
        self.assertIn("lua_program", entry)
        lua = entry["lua_program"]
        self.assertTrue(lua["symbol_only_disable"])
        self.assertIsNone(lua["static_program"])
        self.assertFalse(lua["one_shot"])
        self.assertEqual(lua["provides"], ["aobt2"])
        self.assertEqual(entry["provides"], ["aobt2"])
        # the deterministic luaCall plan is embedded alongside the marker
        report = entry["lua_call_plan"]
        self.assertEqual(report["schema"], aa_luacall.SCHEMA)
        self.assertEqual(report["aob_symbols"], ["aobt2"])
        self.assertEqual(report["operations"][0]["function"], "lua_aobscan")
        self.assertEqual(report["operations"][0]["aob"], {
            "symbol": "aobt2", "module": "FixtureTarget.exe",
            "pattern": "EB ?? 75", "occurrence": 1,
        })
        # Plan-level one_shot is True: the plan carries only the enable-phase
        # luaCall operation (the static disable line is not a plan operation).
        # Record-level one_shot is False and is pinned above on lua_program
        # (the [DISABLE] marker exists in the record source).
        self.assertTrue(report["one_shot"])

    def test_foreign_unregister_name_keeps_the_envelope_refusal(self):
        entry = self._entry(101)
        self.assertFalse(entry["supported"])
        self.assertEqual(entry["reason"],
                         "Static AA envelope: Enable section has no executable patch or data.")

    def test_static_enable_content_stays_on_the_static_path(self):
        # The static program is valid again, so the symbol-only admission
        # never runs; the envelope refusal comes from the static program's
        # own cleanup ownership gate.
        entry = self._entry(102)
        self.assertFalse(entry["supported"])
        self.assertEqual(
            entry["reason"],
            "Static AA envelope: Cleanup may only release symbols/allocations"
            " owned by this program.")


class SymbolOnlyEngineTests(unittest.TestCase):
    """Runtime: no assembler receipt; the static disable releases owned symbols."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.ct_path = self.root / "symbol-only-engine.CT"
        self.memory = Memory()
        self.engines = []

    def _engine(self, factory=None, bootstrap=BOOTSTRAP) -> TrainerEngine:
        self.ct_path.write_text(
            table_xml(record(100, '"Symbol only"', SYMBOL_ONLY_SCRIPT), bootstrap),
            encoding="utf-8")
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

    def test_enable_registers_and_disable_releases_the_owned_symbol(self):
        engine = self._engine(factory=lambda _e: _Binding({'lua_aobscan'}, _FakePort()))
        engine.poll()
        self.assertTrue(engine.toggle(100, True))
        self.assertIn(100, engine.lua_activations)
        self.assertNotIn(100, engine.hooks)  # no assembler receipt exists
        self.assertEqual(engine.applied[100], [])
        self.assertEqual(engine.symbols.get('aobt2'), 0x1020)
        self.assertFalse(engine.toggle(100, False))
        self.assertNotIn('aobt2', engine.symbols)
        self.assertNotIn(100, engine.lua_activations)
        self.assertFalse(engine.blocked)
        self.assertTrue(engine.close())

    # Note: the "gained executable enable content at runtime" guard in
    # LuaActivationScope._start_program_body is a defensive source-determinism
    # check only.  For the admitted pure-luaCall shape the enable chunk is a
    # bare call expression, so the chunk always returns nil and the expanded
    # enable section can never carry executable content through the engine;
    # records that could emit runtime AA (real {$lua} chunks) never pass the
    # plan model and never carry the marker.  It is therefore unpinnable at
    # engine level and documented in the RT-4.5 lane report instead.

    def test_release_owned_unregister_refusals_are_named_and_two_pass(self):
        engine = self._engine(factory=lambda _e: _Binding({'lua_aobscan'}, _FakePort()))
        engine.poll()
        self.assertTrue(engine.toggle(100, True))
        scope = engine.lua_activations[100]
        for text, message in (
                ('db 01',
                 r'Symbol-only Lua record disable must be unregistersymbol lines only\.'),
                ('unregistersymbol(other)',
                 r'Symbol-only Lua record may only release its own symbols: other'),
                ('unregistersymbol(aobt2)\nunregistersymbol(aobt2)',
                 r'Symbol-only Lua record releases the same symbol twice: aobt2'),
        ):
            with self.subTest(text=text):
                with self.assertRaisesRegex(LuaHostError, message):
                    scope._release_owned_unregister(text)
        # two-pass: the failed attempts released nothing
        self.assertIn('aobt2', scope.symbols)
        self.assertIn('aobt2', engine.symbols)
        # the real static disable still releases cleanly
        self.assertFalse(engine.toggle(100, False))
        self.assertNotIn('aobt2', engine.symbols)
        self.assertNotIn(100, engine.lua_activations)


if __name__ == '__main__':
    unittest.main()
