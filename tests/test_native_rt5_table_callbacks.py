"""RT-5 item D: the table's onOpenProcess/onTableLoad callback dispatch.

Covers, for independently authored synthetic fixtures (no corpus files are
loaded; the fixtures reproduce the corpus usage shapes - Resonance/Sinking
City onOpenProcess + onTableLoad with the mForm getTable helper):

- CE order and arguments: onOpenProcess first with the attached target
  PID (memory.pid as a Lua number), then onTableLoad with the Lua literal
  false;
- the game-facing chain: getProcessList()[processId] answers the bound
  process name and getProcessIDFromProcessName feeds it back (item-C
  answers);
- a throwing callback is contained by the pcall-wrapped dispatch chunk,
  logged as table-callback-error, and leaves plan["table_lua"] untouched
  (executed stays True with empty reasons); the second callback still
  dispatches and record activation keeps working;
- absent callbacks (missing, or present but not a function) dispatch
  nothing and log nothing;
- idempotency across polls (one dispatch per confirmed attach) and
  re-fire on re-attach on the fresh host;
- the RT-5 item C2 dynamic addresslist surface is usable from a callback
  (createMemoryRecord + getMemoryRecord through the table-scope host);
- onTableLoad only ever sees false (the before-load phase is the
  documented bounded deviation of the once-per-attach bootstrap);
- a refused (write-API) bootstrap skips the dispatch entirely: the scope
  retires and no table-callback* event is written.

Debug-log event assertions require debug_log=True and a chdir to the
per-test log directory (the source-runtime log lives in the current
working directory as ct2trainer-debug.log, one JSON object per line).
"""
import json
import os
import tempfile
import unittest
import xml.sax.saxutils
from pathlib import Path

from test_native_engine import FakeMemory
from test_native_engine_code import Coordinator
from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import TrainerEngine


PROCESS = "FixtureTarget.exe"
PID = 123
LOG_NAME = "ct2trainer-debug.log"


def table_xml(body: str, lua_script: str = "") -> str:
    return ('<CheatTable CheatEngineTableVersion="45"><LuaScript>'
            + lua_script + '</LuaScript><CheatEntries>' + body
            + '</CheatEntries></CheatTable>')


def value_record(entry_id: int, address: str = "1000") -> str:
    return (f'<CheatEntry><ID>{entry_id}</ID><Description>Value {entry_id}</Description>'
            f'<VariableType>4 Bytes</VariableType><Address>{address}</Address></CheatEntry>')


def asm_record(entry_id: int, address: str = "1050") -> str:
    """A plain AA record: one dword write on enable, restore on disable."""
    script = ('[ENABLE]\nassert(' + address + ',00 00 00 00)\n'
              + address + ':\ndd 1\n[DISABLE]\n' + address + ':\ndd 0\n')
    return (f'<CheatEntry><ID>{entry_id}</ID><Description>"Record {entry_id}"</Description>'
            f'<VariableType>Auto Assembler Script</VariableType>'
            f'<AssemblerScript>{xml.sax.saxutils.escape(script)}</AssemblerScript></CheatEntry>')


class Memory(FakeMemory):
    @property
    def identity(self):
        return self.pid, self.creation_time

    def _range(self, address, size):
        if not self.base <= address or address + size > self.base + len(self.data):
            raise ValueError('Outside owned fixture memory')

    def is_executable(self, address, size):
        return False


class TableCallbackDispatchTests(unittest.TestCase):
    """The onOpenProcess/onTableLoad dispatch on the table-scope host."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.log_dir = self.root / 'log'
        self.log_dir.mkdir()
        self._cwd = os.getcwd()
        os.chdir(self.log_dir)
        self.addCleanup(os.chdir, self._cwd)
        self.memories = []
        self.engines = []
        self.last_memory = None

    def tearDown(self):
        for memory in self.memories:
            if not memory.closed:
                memory.alive = False
        for engine in self.engines:
            if not engine.closed:
                engine.poll()
                engine.close()

    def attach(self, body: str, table_lua: str = "",
               debug_log: bool = True) -> TrainerEngine:
        path = self.root / "rt5d.CT"
        path.write_text(table_xml(body, table_lua), encoding="utf-8")
        plan = compile_table(str(path), PROCESS, debug_log=debug_log)
        memory = Memory()
        self.memories.append(memory)
        self.last_memory = memory
        engine = TrainerEngine(plan, state_dir=self.root / f'state{len(self.engines)}',
                               process_lock_dir=self.root / f'shared{len(self.engines)}',
                               memory_factory=lambda name: memory,
                               hook_coordinator=Coordinator())
        self.engines.append(engine)
        engine.poll()
        self.assertTrue(engine.connected, engine.status)
        return engine

    def events(self, *names: str) -> list[dict]:
        path = self.log_dir / LOG_NAME
        if not path.exists():
            return []
        out = []
        for line in path.read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get('event') in names:
                out.append(record)
        return out

    def table_host(self, engine: TrainerEngine):
        self.assertIsNotNone(engine.table_lua_scope)
        return engine.table_lua_scope[0]

    # -- order and arguments -------------------------------------------------

    def test_both_callbacks_dispatch_in_ce_order_with_arguments(self):
        table_lua = (
            "cb_order = {}\n"
            "function onOpenProcess(processId)\n"
            "  cb_pid = processId\n"
            "  table.insert(cb_order, 'onOpenProcess')\n"
            "end\n"
            "function onTableLoad(before)\n"
            "  cb_loaded = before\n"
            "  table.insert(cb_order, 'onTableLoad')\n"
            "end\n")
        engine = self.attach(value_record(0), table_lua)
        self.assertTrue(engine.plan['table_lua']['executed'])
        host = self.table_host(engine)
        self.assertEqual(host.execute('return cb_pid'), PID)
        self.assertEqual(host.execute('return cb_loaded'), False)
        # The order table is read back through the Lua host (Lupa tables
        # iterate keys, so the values are pinned by Lua-side indexing).
        self.assertEqual(host.execute('return #cb_order'), 2)
        self.assertEqual(host.execute('return cb_order[1]'), 'onOpenProcess')
        self.assertEqual(host.execute('return cb_order[2]'), 'onTableLoad')
        self.assertEqual([e['callback'] for e in self.events('table-callback')],
                         ['onOpenProcess', 'onTableLoad'])
        self.assertEqual(self.events('table-callback-error'), [])

    def test_game_facing_chain_resolves(self):
        table_lua = (
            "function onOpenProcess(processId)\n"
            "  myGame = getProcessList()[processId]\n"
            "  myPid = getProcessIDFromProcessName(myGame)\n"
            "end\n")
        engine = self.attach(value_record(0), table_lua)
        host = self.table_host(engine)
        self.assertEqual(host.execute('return myGame'), PROCESS)
        self.assertEqual(host.execute('return myPid'), PID)
        # onTableLoad is absent here: the only callback event is the
        # onOpenProcess success.
        self.assertEqual([e['callback'] for e in self.events('table-callback')],
                         ['onOpenProcess'])
        self.assertEqual(self.events('table-callback-error'), [])

    # -- failure containment ---------------------------------------------------

    def test_throwing_callback_is_contained_and_logged(self):
        table_lua = (
            "local function getTable()\n"
            "  local x = mForm.OpenDialog1.FileName\n"
            "  return x\n"
            "end\n"
            "function onOpenProcess(processId)\n"
            "  getTable()\n"
            "  cb_after = true\n"
            "end\n"
            "function onTableLoad(before)\n"
            "  loaded_ran = true\n"
            "end\n")
        engine = self.attach(value_record(0), table_lua)
        meta = engine.plan['table_lua']
        self.assertTrue(meta['executed'])
        self.assertEqual(meta['reasons'], [])
        host = self.table_host(engine)
        # The failing onOpenProcess did not run past its error, and the
        # onTableLoad dispatch ran afterwards despite the failure.
        self.assertIsNone(host.execute('return cb_after'))
        self.assertEqual(host.execute('return loaded_ran'), True)
        errors = self.events('table-callback-error')
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]['callback'], 'onOpenProcess')
        self.assertIn('attempt to index a nil value', errors[0]['error'])
        self.assertEqual([e['callback'] for e in self.events('table-callback')],
                         ['onTableLoad'])
        self.assertEqual(len(self.events('table-lua-executed')), 1)
        self.assertEqual(self.events('table-lua-refused'), [])
        # Record activation keeps working: the clean bootstrap stayed
        # clean, so the value record's write path still operates on the
        # attached target.
        memory = self.last_memory
        self.assertEqual(engine.set_value(0, "7"), "7")
        self.assertEqual(memory.read(0x1000, 4), b'\x07\x00\x00\x00')
        self.assertEqual(engine.set_value(0, "0"), "0")
        self.assertEqual(memory.read(0x1000, 4), bytes(4))
        self.assertFalse(engine.blocked)

    # -- absent callbacks -------------------------------------------------------

    def test_absent_callbacks_are_not_dispatched(self):
        engine = self.attach(value_record(0), 'someGlobal = 1')
        self.assertTrue(engine.plan['table_lua']['executed'])
        self.assertEqual(self.events('table-callback', 'table-callback-error'), [])
        # Present but not a function: treated as absent (CE answers the
        # type check the same way).
        engine2 = self.attach(value_record(0), 'onOpenProcess = 42')
        self.assertTrue(engine2.plan['table_lua']['executed'])
        self.assertIsNone(engine2.table_lua_scope[0]
                          .execute('return rawget(_G, "onTableLoad")'))
        self.assertEqual(self.events('table-callback', 'table-callback-error'), [])

    # -- idempotency and re-attach ----------------------------------------------

    def test_dispatch_is_idempotent_across_polls(self):
        table_lua = (
            "counter = 0\n"
            "function onOpenProcess(processId)\n"
            "  counter = counter + 1\n"
            "end\n")
        engine = self.attach(value_record(0), table_lua)
        for _ in range(3):
            engine.poll()
        self.assertEqual(self.table_host(engine).execute('return counter'), 1)
        self.assertEqual(len(self.events('table-callback')), 1)

    def test_reattach_refires_callbacks_on_the_fresh_host(self):
        table_lua = (
            "counter = 0\n"
            "function onOpenProcess(processId)\n"
            "  counter = counter + 1\n"
            "end\n")
        engine = self.attach(value_record(0), table_lua)
        memory = self.last_memory
        memory.alive = False
        engine.poll()
        self.assertIsNone(engine.memory)
        memory.alive = True
        engine.poll()
        self.assertTrue(engine.connected, engine.status)
        # The fresh host re-ran the table source (counter reset to 0) and
        # the dispatch fired exactly once on it.
        self.assertEqual(self.table_host(engine).execute('return counter'), 1)
        opens = [e for e in self.events('table-callback')
                 if e['callback'] == 'onOpenProcess']
        self.assertEqual(len(opens), 2)

    # -- runtime record surface from a callback ----------------------------------

    def test_callback_can_use_the_dynamic_addresslist_surface(self):
        table_lua = (
            "function onOpenProcess(processId)\n"
            "  local al = getAddressList()\n"
            "  local rec = al.createMemoryRecord()\n"
            "  rec.Description = 'From callback'\n"
            "  dyn_count = al.Count\n"
            "end\n")
        engine = self.attach(value_record(0), table_lua)
        host = self.table_host(engine)
        self.assertEqual(host.execute('return dyn_count'), 2)
        self.assertEqual(host.execute('return getAddressList().Count'), 2)
        self.assertEqual(host.execute(
            "return getAddressList().getMemoryRecord('From callback').Description"),
            'From callback')
        self.assertEqual(len(engine.dynamic_records), 1)

    # -- the after-load phase only ------------------------------------------------

    def test_on_table_load_only_ever_sees_false(self):
        table_lua = (
            "loaded_args = {}\n"
            "function onTableLoad(before)\n"
            "  table.insert(loaded_args, before)\n"
            "end\n")
        engine = self.attach(value_record(0), table_lua)
        # The before-load phase has no equivalent in the once-per-attach
        # bootstrap model: one dispatch, one argument, always false.
        host = self.table_host(engine)
        self.assertEqual(host.execute('return #loaded_args'), 1)
        self.assertEqual(host.execute('return loaded_args[1]'), False)

    # -- refused bootstrap ---------------------------------------------------------

    def test_refused_bootstrap_skips_the_dispatch(self):
        table_lua = (
            "writeInteger(4096, 1)\n"
            "function onOpenProcess(processId)\n"
            "  ran = true\n"
            "end\n"
            "function onTableLoad(before)\n"
            "  ran2 = true\n"
            "end\n")
        engine = self.attach(value_record(0), table_lua)
        meta = engine.plan['table_lua']
        self.assertFalse(meta['executed'])
        self.assertEqual(meta['reasons'],
                         ['Table Lua uses a write API: writeInteger.'])
        self.assertIsNone(engine.table_lua_scope)
        self.assertEqual(self.events('table-callback', 'table-callback-error'), [])


if __name__ == '__main__':
    unittest.main()
