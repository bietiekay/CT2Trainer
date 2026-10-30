"""RT-5 item E: messageDialog as a safe, logged no-op.

CE 7.5 (LuaHandler.pas:4031-4118) opens a native message box and returns the
index of the pressed button (0 = mrOk).  The CT2Trainer native trainer has no
dialog UI: the call is a safe no-op that records the fields in the engine
debug log (event 'message-dialog') and returns 0 (mbOK; truthy in Lua, so
``if messageDialog(...) then`` branches proceed as if OK was pressed).
Documented bounded deviation: branches comparing the result against a
non-OK button constant (mrYes, mrYesToAll, ...) never take the affirmative
path, because no dialog is ever shown.

Argument shapes mirror the CE parsing (argument 2 decides the split):
- messageDialog(message)
- messageDialog(title, message)          (arg 2 is a string)
- messageDialog(message, dialogtype)     (arg 2 is not a string)
- messageDialog(title, message, dialogtype, buttons)

Nil arguments are tolerated (CE's lua_tostring / lua_tointeger coerce them);
the dialogtype/button integers are ignored.  The name is registered on both
CE first-letter spellings (messageDialog / MessageDialog), admitted in the
record scope, in the table bootstrap scope (TABLE_LUA_READ_ONLY_NAMES) and
in the syntax-check allowlist.

Refusals: more than four arguments; a non-scalar argument; a message over
the shared 10,000-char bound.  Pure: no target-memory write, no state
change - the record activates and the table bootstrap completes.

All fixtures are synthetic (no corpus files, no process access).
"""
import tempfile
import unittest
import xml.sax.saxutils
from pathlib import Path
from types import SimpleNamespace

from test_native_engine import FakeMemory
from test_native_engine_code import Coordinator
from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import NativeRuntimeError, TrainerEngine
from ct2trainer.native.lua_bootstrap import TABLE_LUA_READ_ONLY_NAMES
from ct2trainer.native.lua_host import (EngineLuaBroker, LuaHost,
                                        LuaHostError)

try:
    import lupa.lua53  # noqa: F401
    _LUPA = True
except ImportError:
    _LUPA = False

PROCESS = "FixtureTarget.exe"
PID = 123
MARKER = 0x1050


def table_xml(body: str, lua_script: str = "") -> str:
    return ('<CheatTable CheatEngineTableVersion="45"><LuaScript>'
            + lua_script + '</LuaScript><CheatEntries>' + body
            + '</CheatEntries></CheatTable>')


def value_record(entry_id: int, address: str = "1000") -> str:
    return (f'<CheatEntry><ID>{entry_id}</ID><Description>Value {entry_id}</Description>'
            f'<VariableType>4 Bytes</VariableType><Address>{address}</Address></CheatEntry>')


def lua_record(entry_id: int, script: str) -> str:
    return (f'<CheatEntry><ID>{entry_id}</ID><Description>"Record {entry_id}"</Description>'
            f'<VariableType>Auto Assembler Script</VariableType>'
            f'<AssemblerScript>{xml.sax.saxutils.escape(script)}</AssemblerScript></CheatEntry>')


def enable_lua_record(entry_id: int, enable_lua: str,
                      disable_lua: str = "") -> str:
    """An AA record whose enable phase is one Lua chunk (the corpus shape)."""
    enable = "[ENABLE]\n{$lua}\n" + enable_lua + "\n{$asm}\n"
    disable = ""
    if disable_lua:
        disable = "[DISABLE]\n{$lua}\n" + disable_lua + "\n{$asm}\n"
    else:
        disable = "[DISABLE]\n{$asm}\n"
    return lua_record(entry_id, enable + disable)


class Memory(FakeMemory):
    @property
    def identity(self):
        return self.pid, self.creation_time

    def _range(self, address, size):
        if not self.base <= address or address + size > self.base + len(self.data):
            raise ValueError('Outside owned fixture memory')

    def is_executable(self, address, size):
        return False


class RecordingLog:
    """Collects debug-log events for assertion without a log file."""

    def __init__(self):
        self.events = []

    def log(self, event: str, **details) -> None:
        self.events.append((event, dict(details)))

    def error(self, event: str, exc, **details) -> None:
        self.events.append((event, dict(details, error=str(exc))))

    def events_named(self, name):
        return [d for (event, d) in self.events if event == name]


def _engine_stub(process_name=PROCESS):
    log = RecordingLog()
    engine = SimpleNamespace(
        memory=Memory(pid=PID),
        plan={"process_name": process_name},
        symbols={},
        debug_log=log,
        _guard=lambda: None,
    )
    return engine, log


def _broker(process_name=PROCESS):
    engine, log = _engine_stub(process_name)
    return EngineLuaBroker(engine, input_handler=object()), engine, log


class MessageDialogBrokerTests(unittest.TestCase):
    """Direct broker calls: CE argument shapes, bound and named refusals."""

    def test_single_message_returns_mbok_and_logs(self):
        broker, engine, log = _broker()
        self.assertEqual(
            broker.call('messageDialog', ('hi',), generation=0,
                        syntaxcheck=False), 0)
        events = log.events_named('message-dialog')
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['message'], 'hi')
        self.assertEqual(events[0]['title'], '')
        self.assertEqual(events[0]['argument_count'], 1)

    def test_title_message_shape_returns_mbok(self):
        broker, engine, log = _broker()
        self.assertEqual(
            broker.call('messageDialog', ('T', 'M'), generation=0,
                        syntaxcheck=False), 0)
        events = log.events_named('message-dialog')
        self.assertEqual(events[0]['title'], 'T')
        self.assertEqual(events[0]['message'], 'M')

    def test_message_dialogtype_shape_is_message_only(self):
        # CE: arg2 not a string -> arg1 is the message, arg2 the dialogtype
        # (ignored by the no-op).
        broker, engine, log = _broker()
        self.assertEqual(
            broker.call('messageDialog', ('msg', 2), generation=0,
                        syntaxcheck=False), 0)
        events = log.events_named('message-dialog')
        self.assertEqual(events[0]['title'], '')
        self.assertEqual(events[0]['message'], 'msg')

    def test_four_argument_shape_returns_mbok(self):
        broker, engine, log = _broker()
        self.assertEqual(
            broker.call('messageDialog', ('T', 'M', 3, 0), generation=0,
                        syntaxcheck=False), 0)
        self.assertEqual(len(log.events_named('message-dialog')), 1)

    def test_nil_arguments_are_tolerated(self):
        # CE's lua_tostring/lua_tointeger coerce nil; the corpus table Lua
        # passes undefined button constants (mtInformation, mbYes, mbNo)
        # which arrive here as None.
        broker, engine, log = _broker()
        self.assertEqual(
            broker.call('messageDialog', ('Enable Dark Mode?', None, None, None),
                        generation=0, syntaxcheck=False), 0)
        events = log.events_named('message-dialog')
        self.assertEqual(events[0]['message'], 'Enable Dark Mode?')

    def test_no_arguments_returns_mbok_without_log(self):
        broker, engine, log = _broker()
        self.assertEqual(broker.call('messageDialog', (), generation=0,
                                     syntaxcheck=False), 0)
        self.assertEqual(log.events_named('message-dialog'), [])

    def test_five_arguments_are_refused(self):
        broker, engine, log = _broker()
        with self.assertRaisesRegex(LuaHostError,
                                    'messageDialog takes at most four arguments'):
            broker.call('messageDialog', ('a', 'b', 1, 2, 3), generation=0,
                        syntaxcheck=False)

    def test_non_scalar_argument_is_refused(self):
        broker, engine, log = _broker()
        with self.assertRaisesRegex(
                LuaHostError,
                'messageDialog arguments must be text, numbers or nil'):
            broker.call('messageDialog', ({'a': 1},), generation=0,
                        syntaxcheck=False)

    def test_message_over_bound_is_refused(self):
        broker, engine, log = _broker()
        with self.assertRaisesRegex(LuaHostError,
                                    'messageDialog message exceeds its bound'):
            broker.call('messageDialog', ('x' * 10001,), generation=0,
                        syntaxcheck=False)

    def test_message_at_bound_is_admitted(self):
        broker, engine, log = _broker()
        self.assertEqual(
            broker.call('messageDialog', ('x' * 10000,), generation=0,
                        syntaxcheck=False), 0)
        events = log.events_named('message-dialog')
        # The log field is bounded to 1,000 chars; the full message was
        # accepted by the call itself.
        self.assertEqual(len(events[0]['message']), 1000)

    def test_pure_no_target_write(self):
        broker, engine, log = _broker()
        broker.call('messageDialog', ('hi',), generation=0, syntaxcheck=False)
        self.assertEqual(engine.memory.writes, [])


class MessageDialogHostTests(unittest.TestCase):
    """Record-scope Lua: both CE spellings, truthy return, syntax check."""

    def setUp(self):
        if not _LUPA:
            self.skipTest('pinned MIT Lupa Lua53 dependency is not installed')
        self.broker, _engine, _log = _broker()
        self.host = LuaHost(self.broker)

    def tearDown(self):
        self.host.cancel()

    def test_runtime_returns_zero(self):
        self.assertEqual(self.host.execute('return messageDialog("hi")'), 0)

    def test_uppercase_spelling_is_registered(self):
        self.assertEqual(self.host.execute('return MessageDialog("hi")'), 0)

    def test_return_is_truthy_in_lua(self):
        script = 'if messageDialog("confirm") then return "ok" end\n' \
                 'return "no"'
        self.assertEqual(self.host.execute(script), "ok")

    def test_button_constant_compare_never_affirmative(self):
        # Documented bounded deviation: no dialog is shown, so the result is
        # 0 (mrOk) and a compare against mrYes (6) is false - the branch the
        # corpus table Lua uses for "auto-attach?" answers the safe default.
        script = 'if messageDialog("Auto-attach to process?", 3, 0, 1) == 6 ' \
                 'then return "yes" end\nreturn "no"'
        self.assertEqual(self.host.execute(script), "no")

    def test_syntax_check_admits_message_dialog(self):
        checker = LuaHost(self.broker, _check_only=True)
        self.addCleanup(checker.cancel)
        self.assertIsNone(checker.execute("messageDialog('check')"))

    def test_unknown_global_still_gets_the_named_refusal(self):
        with self.assertRaisesRegex(
                LuaHostError, 'Unsupported CE Lua API: totallyUnknownCeApi'):
            self.host.execute('return totallyUnknownCeApi("x")')


class MessageDialogEngineTests(unittest.TestCase):
    """Full engine/Lua path: the record activates and nothing is written."""

    def setUp(self):
        if not _LUPA:
            self.skipTest('pinned MIT Lupa Lua53 dependency is not installed')
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.memories = []
        self.engines = []

    def tearDown(self):
        for memory in self.memories:
            if not memory.closed:
                memory.alive = False
        for engine in self.engines:
            if not engine.closed:
                engine.poll()
                engine.close()

    def attach(self, body: str, *, table_lua: str = "") -> TrainerEngine:
        path = self.root / "rt5e.CT"
        path.write_text(table_xml(body, table_lua), encoding="utf-8")
        plan = compile_table(str(path), PROCESS)
        memory = Memory()
        self.memories.append(memory)
        engine = TrainerEngine(plan, state_dir=self.root / f'state{len(self.engines)}',
                               process_lock_dir=self.root / f'shared{len(self.engines)}',
                               memory_factory=lambda name: memory,
                               hook_coordinator=Coordinator())
        self.engines.append(engine)
        engine.poll()
        return engine

    def attach_lua(self, lua: str, disable_lua: str = "") -> TrainerEngine:
        return self.attach(
            value_record(0) + enable_lua_record(1, lua, disable_lua))

    def marker(self, engine: TrainerEngine) -> int:
        return int.from_bytes(engine.memory.read(MARKER, 4), "little")

    def test_record_script_with_message_dialog_activates(self):
        engine = self.attach_lua(
            "messageDialog('Record notice')\n"
            "writeInteger(0x1050, 1)\n")
        self.assertTrue(engine.toggle(1, True))
        self.assertIn(1, engine.applied)
        self.assertEqual(engine.entry_errors, {})
        self.assertEqual(self.marker(engine), 1)

    def test_uppercase_spelling_in_record_script(self):
        engine = self.attach_lua(
            "MessageDialog('Record notice')\n"
            "writeInteger(0x1050, 2)\n")
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.marker(engine), 2)

    def test_message_dialog_is_pure_in_the_record_scope(self):
        # Only the marker write may hit target memory; the dialog itself
        # performs no write of any kind.
        engine = self.attach_lua(
            "messageDialog('T', 'M')\n"
            "writeInteger(0x1050, 3)\n")
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(engine.memory.writes,
                         [(MARKER, (3).to_bytes(4, 'little'))])

    def test_roundtrip_with_disable_lua(self):
        # A record with both enable and disable Lua chunks is not one-shot;
        # full roundtrip should work.
        engine = self.attach_lua(
            "messageDialog('Record notice')\n"
            "writeInteger(0x1050, 4)\n",
            disable_lua="writeInteger(0x1050, 0)\n")
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.marker(engine), 4)
        self.assertFalse(engine.toggle(1, False))
        self.assertNotIn(1, engine.applied)
        self.assertEqual(self.marker(engine), 0)

    def test_table_bootstrap_call_is_admitted(self):
        # Table-scope messageDialog goes through the read-only table
        # bootstrap scope; it must be admitted (no WP-41 refusal reason)
        # and the bootstrap must complete cleanly.
        engine = self.attach(
            value_record(0),
            table_lua="messageDialog('Table notice')\nprint('boot done')\n")
        self.assertIsNotNone(engine.table_lua_scope)
        _, broker = engine.table_lua_scope
        self.assertEqual(broker.reasons, [])
        meta = engine.plan.get('table_lua')
        self.assertIsNotNone(meta)
        self.assertTrue(meta['executed'])
        self.assertEqual(meta['reasons'], [])


if __name__ == '__main__':
    unittest.main()
