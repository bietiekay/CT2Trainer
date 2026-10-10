"""lua_debugger_api: the Lua-facing attachProcess/detachProcess surface.

The engine owns at most one debugger session binding per attached target,
created on demand through the injected ``debugger_factory`` and retired on
confirmed target exit and close. The default route (no factory) refuses
visibly fail-closed because the persistent owned Windows debug attach route
is still open (AP-11). The tested
:class:`~ct2trainer.native.debug_coordinator.DebugEventCoordinator`
remains the scoped quiescence owner and is not touched by this surface.
"""
import tempfile
import unittest
from pathlib import Path

from test_native_engine_code import Coordinator
from test_native_lua_activation import Memory

from ct2trainer.native.compiler import compile_table
from ct2trainer.native.debugger_session import (
    DebuggerAlreadyAttached, DebuggerBadPid, DebuggerNotAttached)
from ct2trainer.native.engine import TrainerEngine
from ct2trainer.native.lua_host import EngineLuaBroker, LuaHostError

PROCESS = "FixtureTarget.exe"


def write_debugger_table(root: Path) -> Path:
    path = root / "debugger_fixture.ct"
    path.write_text(
        '<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
        '<CheatEntry><ID>1</ID><Description>Int</Description>'
        '<VariableType>4 Bytes</VariableType><Address>1020</Address>'
        '</CheatEntry>'
        '</CheatEntries></CheatTable>',
        encoding='utf-8')
    return path


class ScriptedDebuggerSession:
    """Scripted session binding; records detach calls."""

    def __init__(self, pid, recorder):
        self.pid = pid
        self.recorder = recorder
        self.attached = True
        self.detach_calls = 0

    def detach(self):
        self.detach_calls += 1
        self.attached = False
        self.recorder.append('detach')


class DebuggerEngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.table = write_debugger_table(self.root)
        self.memory = Memory()
        self.recorder = []
        self.sessions = []
        self.engine = TrainerEngine(
            compile_table(self.table, PROCESS),
            state_dir=self.root / 'state',
            process_lock_dir=self.root / 'shared',
            memory_factory=lambda name: self.memory,
            hook_coordinator=Coordinator(),
            debugger_factory=self._make_session)
        self.engine.poll()
        self.assertTrue(self.engine.connected)
        self.addCleanup(self._close_engine)

    def _make_session(self, engine, memory):
        session = ScriptedDebuggerSession(memory.pid, self.recorder)
        self.sessions.append(session)
        return session

    def _close_engine(self):
        if not self.engine.closed:
            self.engine.close()

    def _fresh_engine(self, name, **kwargs):
        return TrainerEngine(
            compile_table(self.table, PROCESS),
            state_dir=self.root / (name + '_state'),
            process_lock_dir=self.root / (name + '_shared'),
            memory_factory=lambda nm: Memory(),
            hook_coordinator=Coordinator(),
            **kwargs)

    def test_attach_refused_before_target_session(self):
        engine2 = self._fresh_engine('pre')
        self.assertFalse(engine2.debugger_attached)
        with self.assertRaisesRegex(DebuggerNotAttached, 'not connected'):
            engine2.debugger_attach()
        with self.assertRaisesRegex(DebuggerNotAttached, 'No debugger session'):
            engine2.debugger_detach()

    def test_default_route_refuses_visibly_without_side_effects(self):
        engine2 = self._fresh_engine('default')
        engine2.poll()
        self.assertTrue(engine2.connected)
        try:
            with self.assertRaisesRegex(DebuggerNotAttached,
                                        'no debugger binding was provided'):
                engine2.debugger_attach(123)
            with self.assertRaisesRegex(DebuggerNotAttached, 'No debugger session'):
                engine2.debugger_detach()
            self.assertFalse(engine2.debugger_attached)
        finally:
            engine2.close()

    def test_attach_creates_session_and_single_detach(self):
        self.engine.debugger_attach(self.memory.pid)
        self.assertTrue(self.engine.debugger_attached)
        self.assertIs(self.engine.debugger_session, self.sessions[-1])
        self.engine.debugger_detach()
        self.assertFalse(self.engine.debugger_attached)
        self.assertIsNone(self.engine.debugger_session)
        self.assertEqual(self.recorder, ['detach'])
        self.assertEqual(self.sessions[-1].detach_calls, 1)
        with self.assertRaisesRegex(DebuggerNotAttached, 'No debugger session'):
            self.engine.debugger_detach()

    def test_double_attach_refused_visibly(self):
        self.engine.debugger_attach(self.memory.pid)
        with self.assertRaisesRegex(DebuggerAlreadyAttached, 'already attached'):
            self.engine.debugger_attach(self.memory.pid)
        self.assertEqual(len(self.sessions), 1)

    def test_attach_requires_exact_target_pid(self):
        with self.assertRaisesRegex(DebuggerBadPid, 'must target the attached'):
            self.engine.debugger_attach(999)
        self.assertFalse(self.engine.debugger_attached)
        self.assertEqual(len(self.sessions), 0)
        with self.assertRaisesRegex(DebuggerBadPid, 'integer PID'):
            self.engine.debugger_attach('123')
        self.assertEqual(len(self.sessions), 0)

    def test_factory_identity_mismatch_refused(self):
        def foreign_factory(engine, memory):
            self.sessions.append(ScriptedDebuggerSession(999, self.recorder))
            return self.sessions[-1]
        self.engine.debugger_factory = foreign_factory
        with self.assertRaisesRegex(DebuggerBadPid, 'different target identity'):
            self.engine.debugger_attach(self.memory.pid)
        self.assertFalse(self.engine.debugger_attached)
        self.assertIsNone(self.engine.debugger_session)

    def test_factory_none_session_refused(self):
        self.engine.debugger_factory = lambda engine, memory: None
        with self.assertRaisesRegex(DebuggerNotAttached, 'produced no session'):
            self.engine.debugger_attach(self.memory.pid)
        self.assertFalse(self.engine.debugger_attached)

    def test_target_exit_retires_session_and_reattach_creates_fresh_one(self):
        self.engine.debugger_attach(self.memory.pid)
        self.memory.alive = False
        self.engine.poll()
        self.assertFalse(self.engine.debugger_attached)
        self.assertEqual(self.recorder, ['detach'])
        self.memory.alive = True
        self.engine.poll()
        self.assertTrue(self.engine.connected)
        self.engine.debugger_attach(self.memory.pid)
        self.assertEqual(len(self.sessions), 2)
        self.assertEqual(self.recorder, ['detach'])

    def test_close_retires_session(self):
        self.engine.debugger_attach(self.memory.pid)
        self.engine.close()
        self.assertEqual(self.recorder, ['detach'])
        self.assertIsNone(self.engine.debugger_session)
        with self.assertRaisesRegex(DebuggerNotAttached, 'closed'):
            self.engine.debugger_attach(self.memory.pid)


class DebuggerLuaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.table = write_debugger_table(self.root)
        self.memory = Memory()
        self.recorder = []
        self.engine = TrainerEngine(
            compile_table(self.table, PROCESS),
            state_dir=self.root / 'state',
            process_lock_dir=self.root / 'shared',
            memory_factory=lambda name: self.memory,
            hook_coordinator=Coordinator(),
            debugger_factory=lambda e, m: ScriptedDebuggerSession(m.pid, self.recorder))
        self.engine.poll()
        self.addCleanup(self._close_engine)

    def _close_engine(self):
        if not self.engine.closed:
            self.engine.close()

    def test_lua_attach_and_detach_roundtrip(self):
        host = self.engine.open_lua_session()
        self.assertIsNone(host.execute('attachProcess(123)'))
        self.assertTrue(self.engine.debugger_attached)
        self.assertIsNone(host.execute('detachProcess()'))
        self.assertFalse(self.engine.debugger_attached)
        self.assertEqual(self.recorder, ['detach'])

    def test_lua_wrong_pid_refused_without_side_effect(self):
        host = self.engine.open_lua_session()
        with self.assertRaisesRegex(LuaHostError, 'must target the attached game process'):
            host.execute('attachProcess(999)')
        self.assertFalse(self.engine.debugger_attached)

    def test_lua_argument_shape_refusals(self):
        host = self.engine.open_lua_session()
        with self.assertRaisesRegex(LuaHostError, 'exactly one integer PID'):
            host.execute('attachProcess()')
        with self.assertRaisesRegex(LuaHostError, 'exactly one integer PID'):
            host.execute('attachProcess("123")')
        with self.assertRaisesRegex(LuaHostError, 'exactly one integer PID'):
            host.execute('attachProcess(123, 42)')
        with self.assertRaisesRegex(LuaHostError, 'takes no arguments'):
            host.execute('detachProcess(1)')
        self.assertFalse(self.engine.debugger_attached)

    def test_lua_detaching_without_session_refused(self):
        host = self.engine.open_lua_session()
        with self.assertRaisesRegex(LuaHostError, 'No debugger session'):
            host.execute('detachProcess()')

    def test_lua_default_route_refuses_visibly(self):
        engine2 = TrainerEngine(
            compile_table(self.table, PROCESS),
            state_dir=self.root / 'def_state',
            process_lock_dir=self.root / 'def_shared',
            memory_factory=lambda nm: Memory(),
            hook_coordinator=Coordinator())
        engine2.poll()
        host = engine2.open_lua_session()
        try:
            with self.assertRaisesRegex(LuaHostError, 'no debugger binding was provided'):
                host.execute('attachProcess(123)')
        finally:
            engine2.close()

    def test_syntaxcheck_refuses_live_debugger_calls(self):
        broker = EngineLuaBroker(self.engine)
        with self.assertRaisesRegex(LuaHostError, 'live activation'):
            broker.call('attachProcess', (123,), generation=0, syntaxcheck=True)
        with self.assertRaisesRegex(LuaHostError, 'live activation'):
            broker.call('detachProcess', (), generation=0, syntaxcheck=True)


if __name__ == '__main__':
    unittest.main()
