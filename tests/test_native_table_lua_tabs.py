# -*- coding: utf-8 -*-
"""WP-16 (L5-19): named table-Lua tabs gather into the table-Lua bootstrap.

CE 7.5 table-Lua sections may hold several named script tabs as direct
child elements of <LuaScript> in addition to the direct main body; the
load-time contract combines the direct text plus every tab, in document
order.  This file pins the gather contract on synthetic tables (no corpus
files) and the end-to-end replay of a helper defined in a named tab.
"""
import tempfile
import unittest
import xml.etree.ElementTree as ET
import xml.sax.saxutils
from pathlib import Path

from test_native_engine import FakeMemory
from test_native_engine_code import Coordinator
from ct2trainer.native.compiler import compile_table, validate_plan
from ct2trainer.native.engine import NativeRuntimeError, TrainerEngine
from ct2trainer.native.lua_bootstrap import validate_lua_bootstrap


PROCESS = "FixtureTarget.exe"


def escape(text: str) -> str:
    return xml.sax.saxutils.escape(text)


def table_xml(body: str, lua_script: str) -> str:
    return ('<CheatTable CheatEngineTableVersion="45"><LuaScript>'
            + lua_script + '</LuaScript><CheatEntries>' + body
            + '</CheatEntries></CheatTable>')


def value_record(entry_id: int, address: str = "1000") -> str:
    return (f'<CheatEntry><ID>{entry_id}</ID><Description>Value {entry_id}</Description>'
            f'<VariableType>4 Bytes</VariableType><Address>{address}</Address></CheatEntry>')


def lua_record(entry_id: int, label: str, script: str) -> str:
    return (f'<CheatEntry><ID>{entry_id}</ID><Description>{label}</Description>'
            f'<VariableType>Auto Assembler Script</VariableType>'
            f'<AssemblerScript>{escape(script)}</AssemblerScript></CheatEntry>')


class Memory(FakeMemory):
    @property
    def identity(self):
        return self.pid, self.creation_time

    def _range(self, address, size):
        if not self.base <= address or address + size > self.base + len(self.data):
            raise ValueError('Outside owned fixture memory')

    def is_executable(self, address, size):
        return False


class TableLuaGatherTests(unittest.TestCase):
    """The gather contract on synthetic tables: direct text + tabs, in order."""

    MAIN = "function mainHelper() return 5 end"

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "tablua.CT"
        self.memory = None
        self.engines = []

    def tearDown(self):
        if self.memory is not None and not self.memory.closed:
            self.memory.alive = False
        for engine in self.engines:
            engine.poll()
            engine.close()

    def compile(self, lua_script, body=None):
        self.path.write_text(table_xml(value_record(0) if body is None else body,
                                       lua_script), encoding="utf-8")
        return compile_table(self.path, PROCESS)

    def test_main_body_only_table_is_byte_identical_to_findtext(self):
        plan = self.compile(self.MAIN)
        legacy = ET.fromstring(self.path.read_bytes()).findtext('LuaScript')
        self.assertEqual(plan['lua_bootstrap']['source'], self.MAIN)
        self.assertEqual(plan['lua_bootstrap']['source'], legacy)
        validate_plan(plan)
        self.assertEqual(validate_lua_bootstrap(plan['lua_bootstrap'])['source'], self.MAIN)

    def test_main_body_plus_named_tabs_join_in_document_order(self):
        lua = (self.MAIN
               + '<Tab name="first">' + escape('function firstHelper() return 6 end') + '</Tab>'
               + '<Tab name="second">' + escape('function secondHelper() return 7 end') + '</Tab>')
        plan = self.compile(lua)
        expected = ('function mainHelper() return 5 end'
                    '\nfunction firstHelper() return 6 end'
                    '\nfunction secondHelper() return 7 end')
        source = plan['lua_bootstrap']['source']
        self.assertEqual(source, expected)
        # Document order: the first tab precedes the second tab.
        self.assertLess(source.index('firstHelper'), source.index('secondHelper'))
        validate_plan(plan)
        validate_lua_bootstrap(plan['lua_bootstrap'])

    def test_tabs_only_table_builds_bootstrap_from_tabs(self):
        for main_body, label in (("", "absent main body"), ("   \n\t", "whitespace main body")):
            with self.subTest(label=label):
                lua = (main_body
                       + '<Tab name="helpers">'
                       + escape('function tabOnlyHelper() return 9 end') + '</Tab>')
                plan = self.compile(lua)
                self.assertEqual(plan['lua_bootstrap']['source'],
                                 'function tabOnlyHelper() return 9 end')
                validate_plan(plan)

    def test_whitespace_only_tab_parts_are_skipped(self):
        lua = (self.MAIN
               + '<Tab name="blank">' + escape('   \n\t  ') + '</Tab>'
               + '<Tab name="real">' + escape('function realHelper() return 11 end') + '</Tab>')
        plan = self.compile(lua)
        self.assertEqual(plan['lua_bootstrap']['source'],
                         self.MAIN + '\nfunction realHelper() return 11 end')
        validate_plan(plan)

    def test_invalid_tab_content_keeps_a_complete_plan_and_fails_closed_at_activation(self):
        invalid_tab = 'function broken( end'
        script = ('[ENABLE]\n{$lua}\nif not syntaxcheck then writeInteger(0x1080,1) end\n{$asm}\n'
                  '[DISABLE]\n{$lua}\nassert(readInteger(0x1080)==1)\n{$asm}\n')
        plan = self.compile('<Tab name="broken">' + escape(invalid_tab) + '</Tab>',
                            body=lua_record(1, '"Tab record"', script))
        # The invalid source travels verbatim in a complete plan: no partial
        # plan, and the canonical hash re-derivation still holds.
        self.assertEqual(len(plan['entries']), 1)
        self.assertTrue(plan['entries'][0]['supported'], plan['entries'][0]['reason'])
        self.assertEqual(plan['lua_bootstrap']['source'], invalid_tab)
        validate_plan(plan)
        memory = Memory()
        root = Path(self.directory.name)
        engine = TrainerEngine(plan, state_dir=root / 'state',
                               process_lock_dir=root / 'shared',
                               memory_factory=lambda name: memory,
                               hook_coordinator=Coordinator())
        self.memory = memory
        self.engines.append(engine)
        engine.poll()
        with self.assertRaises(NativeRuntimeError):
            engine.toggle(1, True)
        self.assertEqual(memory.read(0x1080, 4), bytes(4))
        self.assertFalse(engine.applied)
        self.assertFalse(engine.desired)
        self.assertFalse(engine.lua_activations)
        self.assertFalse(memory.writes)

    def test_table_lua_warning_still_visible_with_named_tabs(self):
        plan = self.compile(
            '<Tab name="helpers">' + escape('function tabHelper() return 42 end') + '</Tab>')
        self.assertTrue(any('Table Lua is not executed on load' in warning
                            for warning in plan['warnings']))


class TableLuaTabReplayTests(unittest.TestCase):
    """End-to-end: a record Lua activation can use a helper from a named tab."""

    TAB_SCRIPT = ('[ENABLE]\n{$lua}\nif not syntaxcheck then '
                 'writeInteger(0x1080,tabHelper()) end\n{$asm}\n'
                 '[DISABLE]\n{$lua}\nassert(readInteger(0x1080)==42)\n{$asm}\n')
    TAB = '<Tab name="helpers">' + escape('function tabHelper() return 42 end') + '</Tab>'

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.memory = Memory()
        self.engines = []
        self.lua_script = self.TAB

    def tearDown(self):
        self.memory.alive = False
        for engine in self.engines:
            engine.poll()
            engine.close()

    def engine(self):
        path = self.root / "tablua-replay.CT"
        path.write_text(table_xml(lua_record(1, '"Tab helper record"', self.TAB_SCRIPT),
                                  self.lua_script), encoding="utf-8")
        plan = compile_table(path, PROCESS)
        engine = TrainerEngine(plan, state_dir=self.root / 'state',
                               process_lock_dir=self.root / 'shared',
                               memory_factory=lambda name: self.memory,
                               hook_coordinator=Coordinator())
        self.engines.append(engine)
        engine.poll()
        return engine

    def test_record_lua_activation_replays_named_tab_helper_end_to_end(self):
        engine = self.engine()
        # No load-time execution: attaching does not write from the tab.
        self.assertEqual(self.memory.read(0x1080, 4), bytes(4))
        self.assertTrue(engine.toggle(1, True))
        self.assertIn(1, engine.lua_activations)
        self.assertEqual(self.memory.read(0x1080, 4), (42).to_bytes(4, 'little'))
        self.assertFalse(engine.toggle(1, False))
        self.assertEqual(self.memory.read(0x1080, 4), bytes(4))
        self.assertNotIn(1, engine.lua_activations)

    def test_combined_main_body_and_tab_helpers_both_replay(self):
        self.lua_script = 'function mainHelper() return 7 end' + '\n' + self.TAB
        engine = self.engine()
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.memory.read(0x1080, 4), (42).to_bytes(4, 'little'))
        self.assertEqual(engine.lua_activations[1].host.execute('return mainHelper()'), 7)


if __name__ == '__main__':
    unittest.main()
