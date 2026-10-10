"""lua_managed_runtime: the Lua-facing LaunchMonoDataCollector/mono_* surface.

The engine owns at most one managed-runtime session per attached target,
created on demand through the injected ``managed_runtime_factory`` and retired
on confirmed target exit and close (mirroring the call-broker/debugger
lifecycles). The default route (no factory) refuses visibly fail-closed.
The reference session :class:`ManagedRuntimeSession` drives the tested
``mono_runtime``/``mono_broker`` stack: one frozen bootstrap per route,
fresh one-shot CAS tokens per invocation, reversible-contract undo receipts,
and terminal unknown/failure states that are never retried.
"""
import tempfile
import unittest
from pathlib import Path

from test_native_engine_code import Coordinator
from test_native_lua_activation import Memory

from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import TrainerEngine
from ct2trainer.native import managed_session as ms
from ct2trainer.native import mono_broker
from ct2trainer.native import mono_runtime as m
from ct2trainer.native.mono_broker import (
    ARG_INSTANCE_REF,
    ARG_STRING,
)
from ct2trainer.native.lua_host import EngineLuaBroker, LuaHostError

PROCESS = "FixtureTarget.exe"
TOKEN = 0x60010001
SHA = 'ab' * 32


def write_managed_table(root: Path) -> Path:
    path = root / "managed_fixture.ct"
    path.write_text(
        '<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
        '<CheatEntry><ID>1</ID><Description>Int</Description>'
        '<VariableType>4 Bytes</VariableType><Address>1020</Address>'
        '</CheatEntry>'
        '</CheatEntries></CheatTable>',
        encoding='utf-8')
    return path


class ScriptedManagedSession:
    """Scripted session binding; records contract calls and kwargs."""

    def __init__(self, pid, recorder, domains=()):
        self.pid = pid
        self.recorder = recorder
        self.domains_result = list(domains)
        self.method_token = TOKEN
        self.invoke_calls = []
        self.find_calls = []
        self.release_calls = 0
        self.ended_calls = 0
        self.bootstrapped = True

    def domains(self):
        self.recorder.append('domains')
        return list(self.domains_result)

    def find_method(self, namespace, class_name, method_name):
        self.find_calls.append((namespace, class_name, method_name))
        return self.method_token

    def invoke(self, *, domain_id, method_token, is_static, arguments):
        self.invoke_calls.append((domain_id, method_token, is_static,
                                 tuple(arguments)))
        return True

    def target_ended(self):
        self.ended_calls += 1
        self.recorder.append('target_ended')

    def release(self):
        self.release_calls += 1
        self.recorder.append('release')


class ManagedEngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.table = write_managed_table(self.root)
        self.memory = Memory()
        self.recorder = []
        self.sessions = []
        self.engine = TrainerEngine(
            compile_table(self.table, PROCESS),
            state_dir=self.root / 'state',
            process_lock_dir=self.root / 'shared',
            memory_factory=lambda name: self.memory,
            hook_coordinator=Coordinator(),
            managed_runtime_factory=self._make_session)
        self.engine.poll()
        self.assertTrue(self.engine.connected)
        self.addCleanup(self._close_engine)

    def _make_session(self, engine, memory):
        session = ScriptedManagedSession(
            memory.pid, self.recorder,
            domains=[{'id': 0, 'ptr': 0x1000, 'generation': 1}])
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

    def test_managed_attach_refused_before_target_session(self):
        engine2 = self._fresh_engine('pre')
        self.assertFalse(engine2.managed_attached)
        with self.assertRaisesRegex(ms.ManagedSessionNotAttached, 'not connected'):
            engine2.managed_attach()
        with self.assertRaisesRegex(ms.ManagedSessionNotAttached,
                                    'No managed runtime session'):
            engine2.managed_detach()

    def test_managed_attach_refused_on_closed_engine(self):
        self.engine.close()
        with self.assertRaisesRegex(ms.ManagedSessionNotAttached, 'closed'):
            self.engine.managed_attach()
        with self.assertRaisesRegex(ms.ManagedSessionNotAttached, 'closed'):
            self.engine.managed_detach()

    def test_managed_attach_default_route_refuses_visibly(self):
        engine2 = self._fresh_engine('default')
        engine2.poll()
        self.assertTrue(engine2.connected)
        try:
            with self.assertRaisesRegex(ms.ManagedSessionNotAttached,
                                        'no binding was provided'):
                engine2.managed_attach()
            with self.assertRaisesRegex(ms.ManagedSessionNotAttached,
                                        'No managed runtime session'):
                engine2.managed_detach()
            self.assertFalse(engine2.managed_attached)
        finally:
            engine2.close()

    def test_managed_factory_none_session_refused(self):
        self.engine.managed_runtime_factory = lambda engine, memory: None
        with self.assertRaisesRegex(ms.ManagedSessionNotAttached,
                                    'produced no session'):
            self.engine.managed_attach()
        self.assertFalse(self.engine.managed_attached)

    def test_managed_factory_pid_mismatch_refused(self):
        def foreign_factory(engine, memory):
            self.sessions.append(ScriptedManagedSession(999, self.recorder))
            return self.sessions[-1]
        self.engine.managed_runtime_factory = foreign_factory
        with self.assertRaisesRegex(ms.ManagedSessionBadPid,
                                    'different target identity'):
            self.engine.managed_attach()
        self.assertFalse(self.engine.managed_attached)
        self.assertIsNone(self.engine.managed_session)

    def test_managed_attach_creates_session(self):
        self.engine.managed_attach()
        self.assertTrue(self.engine.managed_attached)
        self.assertIs(self.engine.managed_session, self.sessions[-1])
        self.assertEqual(len(self.sessions), 1)

    def test_managed_double_attach_idempotent_factory_called_once(self):
        self.engine.managed_attach()
        self.engine.managed_attach()
        self.assertTrue(self.engine.managed_attached)
        self.assertEqual(len(self.sessions), 1)

    def test_managed_detach_without_session(self):
        with self.assertRaisesRegex(ms.ManagedSessionNotAttached,
                                    'No managed runtime session'):
            self.engine.managed_detach()

    def test_managed_detach_releases_session(self):
        self.engine.managed_attach()
        self.engine.managed_detach()
        self.assertFalse(self.engine.managed_attached)
        self.assertIsNone(self.engine.managed_session)
        self.assertEqual(self.sessions[-1].release_calls, 1)
        self.assertEqual(self.recorder, ['release'])
        with self.assertRaisesRegex(ms.ManagedSessionNotAttached,
                                    'No managed runtime session'):
            self.engine.managed_detach()

    def test_managed_domains_without_session(self):
        with self.assertRaisesRegex(ms.ManagedSessionNotAttached,
                                    'No managed runtime session'):
            self.engine.managed_domains()

    def test_managed_find_and_invoke_without_session(self):
        with self.assertRaisesRegex(ms.ManagedSessionNotAttached,
                                    'No managed runtime session'):
            self.engine.managed_find_method('Yooka', 'Laylee', 'SetFlag')
        with self.assertRaisesRegex(ms.ManagedSessionNotAttached,
                                    'No managed runtime session'):
            self.engine.managed_invoke(0, TOKEN, 0, ())

    def test_managed_find_method_type_refusals(self):
        self.engine.managed_attach()
        with self.assertRaisesRegex(ms.ManagedValueRefused, 'non-empty text'):
            self.engine.managed_find_method('', 'Laylee', 'SetFlag')
        with self.assertRaisesRegex(ms.ManagedValueRefused, 'non-empty text'):
            self.engine.managed_find_method('Yooka', None, 'SetFlag')
        self.engine.managed_detach()

    def test_managed_invoke_routed_with_exact_kwargs(self):
        self.engine.managed_attach()
        session = self.engine.managed_session
        self.assertTrue(self.engine.managed_invoke(0, TOKEN, 0,
                                                   [('vtByte', 1)]))
        self.assertEqual(session.invoke_calls,
                         [(0, TOKEN, False, (('vtByte', 1),))])
        self.assertEqual(self.engine.managed_find_method('Yooka', 'Laylee',
                                                         'SetFlag'), TOKEN)
        self.assertEqual(session.find_calls, [('Yooka', 'Laylee', 'SetFlag')])
        with self.assertRaisesRegex(ms.ManagedValueRefused, 'integer'):
            self.engine.managed_invoke('0', TOKEN, 0, ())
        with self.assertRaisesRegex(ms.ManagedValueRefused, 'integer'):
            self.engine.managed_invoke(0, 'x', 0, ())
        with self.assertRaisesRegex(ms.ManagedValueRefused, 'is_static'):
            self.engine.managed_invoke(0, TOKEN, 2, ())
        with self.assertRaisesRegex(ms.ManagedValueRefused,
                                    'list or tuple'):
            self.engine.managed_invoke(0, TOKEN, 0, 'nope')
        self.assertEqual(session.invoke_calls,
                         [(0, TOKEN, False, (('vtByte', 1),))])

    def test_managed_target_exit_retires_and_reattach_creates_fresh_one(self):
        self.engine.managed_attach()
        first = self.engine.managed_session
        self.memory.alive = False
        self.engine.poll()
        self.assertFalse(self.engine.managed_attached)
        self.assertEqual(first.ended_calls, 1)
        self.assertEqual(self.recorder, ['target_ended'])
        self.memory.alive = True
        self.engine.poll()
        self.assertTrue(self.engine.connected)
        self.engine.managed_attach()
        self.assertEqual(len(self.sessions), 2)
        self.assertIsNot(self.engine.managed_session, first)
        self.assertEqual(self.recorder, ['target_ended'])

    def test_managed_close_releases_session(self):
        self.engine.managed_attach()
        self.assertTrue(self.engine.close())
        self.assertEqual(self.sessions[-1].release_calls, 1)
        self.assertEqual(self.recorder, ['release'])
        self.assertIsNone(self.engine.managed_session)
        with self.assertRaisesRegex(ms.ManagedSessionNotAttached, 'closed'):
            self.engine.managed_attach()

    def test_managed_close_exception_path_releases_session(self):
        self.engine.managed_attach()
        self.engine.blocked = True
        self.engine.error = 'injected close failure'
        self.assertFalse(self.engine.close())
        self.assertEqual(self.sessions[-1].release_calls, 1)
        self.assertEqual(self.recorder, ['release'])
        self.assertIsNone(self.engine.managed_session)


class ManagedLuaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.table = write_managed_table(self.root)
        self.memory = Memory()
        self.recorder = []
        self.engine = TrainerEngine(
            compile_table(self.table, PROCESS),
            state_dir=self.root / 'state',
            process_lock_dir=self.root / 'shared',
            memory_factory=lambda name: self.memory,
            hook_coordinator=Coordinator(),
            managed_runtime_factory=lambda e, m: ScriptedManagedSession(
                m.pid, self.recorder,
                domains=[{'id': 0, 'ptr': 0x1000, 'generation': 1}]))
        self.engine.poll()
        self.addCleanup(self._close_engine)

    def _close_engine(self):
        if not self.engine.closed:
            self.engine.close()

    def test_lua_launch_returns_1(self):
        host = self.engine.open_lua_session()
        self.assertEqual(host.execute('return LaunchMonoDataCollector()'), 1)
        self.assertTrue(self.engine.managed_attached)

    def test_lua_launch_with_arguments_refused(self):
        host = self.engine.open_lua_session()
        with self.assertRaisesRegex(LuaHostError, 'takes no arguments'):
            host.execute('LaunchMonoDataCollector(1)')
        self.assertFalse(self.engine.managed_attached)

    def test_lua_enum_domains_returns_list(self):
        host = self.engine.open_lua_session()
        host.execute('LaunchMonoDataCollector()')
        self.assertTrue(host.execute(
            'local d = mono_enumDomains()\n'
            'return #d == 1 and d[1].id == 0 and d[1].ptr == 0x1000 and d[1].generation == 1'))
        self.assertEqual(host.execute('return mono_enumDomains()[1].id'), 0)

    def test_lua_find_method_three_strings_returns_int(self):
        host = self.engine.open_lua_session()
        host.execute('LaunchMonoDataCollector()')
        token = host.execute('return mono_findMethod("Yooka","Laylee","SetFlag")')
        self.assertEqual(token, TOKEN)

    def test_lua_find_method_shape_refusals(self):
        host = self.engine.open_lua_session()
        with self.assertRaisesRegex(LuaHostError, 'three non-empty text'):
            host.execute('mono_findMethod("Yooka","Laylee")')
        with self.assertRaisesRegex(LuaHostError, 'three non-empty text'):
            host.execute('mono_findMethod("Yooka","Laylee","")')
        with self.assertRaisesRegex(LuaHostError, 'three non-empty text'):
            host.execute('mono_findMethod("Yooka","Laylee",1)')
        self.assertFalse(self.engine.managed_attached)

    def test_lua_invoke_happy_path(self):
        host = self.engine.open_lua_session()
        host.execute('LaunchMonoDataCollector()')
        result = host.execute(
            'local d = mono_enumDomains()[1]\n'
            'mono_invoke_method(d, 0x60010001, 0, '
            '{{type="vtByte", value=1}})')
        self.assertIsNone(result)
        session = self.engine.managed_session
        self.assertEqual(session.invoke_calls,
                         [(0, TOKEN, False, (('vtByte', 1),))])

    def test_lua_invoke_shape_refusals(self):
        host = self.engine.open_lua_session()
        host.execute('LaunchMonoDataCollector()')
        with self.assertRaisesRegex(LuaHostError, 'exactly four arguments'):
            host.execute('mono_invoke_method(0, 5, 0)')
        with self.assertRaisesRegex(LuaHostError, 'domain must be'):
            host.execute('mono_invoke_method({ptr=8}, 5, 0, {})')
        with self.assertRaisesRegex(LuaHostError, 'integer token'):
            host.execute('mono_invoke_method({id=0}, "x", 0, {})')
        with self.assertRaisesRegex(LuaHostError, 'isStatic must be'):
            host.execute('mono_invoke_method({id=0}, 5, 2, {})')
        with self.assertRaisesRegex(LuaHostError, 'args must be a list'):
            host.execute('mono_invoke_method({id=0}, 5, 0, "nope")')
        with self.assertRaisesRegex(LuaHostError, 'args must be a list'):
            host.execute('mono_invoke_method({id=0}, 5, 0, {{type="vtByte"}})')
        with self.assertRaisesRegex(LuaHostError, 'args must be a list'):
            host.execute(
                'mono_invoke_method({id=0}, 5, 0, {{type=1, value=1}})')
        self.assertEqual(self.engine.managed_session.invoke_calls, [])

    def test_lua_syntaxcheck_refusals_for_all_four_names(self):
        broker = EngineLuaBroker(self.engine)
        for name, args in (
                ('LaunchMonoDataCollector', ()),
                ('mono_enumDomains', ()),
                ('mono_findMethod', ('Yooka', 'Laylee', 'SetFlag')),
                ('mono_invoke_method', ({'id': 0}, TOKEN, 0, [])),
        ):
            with self.subTest(name=name):
                with self.assertRaisesRegex(LuaHostError, 'live activation'):
                    broker.call(name, args, generation=0, syntaxcheck=True)

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
            with self.assertRaisesRegex(LuaHostError,
                                        'no binding was provided'):
                host.execute('LaunchMonoDataCollector()')
            self.assertFalse(engine2.managed_attached)
        finally:
            engine2.close()


class Clock:
    def __init__(self, value=1000):
        self.value = value

    def __call__(self):
        return self.value

    def advance(self, ticks):
        self.value += ticks


class FakeBackend(m.AdapterBackend):
    """Scripted adapter over the pinned 42-export table."""

    def __init__(self):
        self._exports = {pin.export for pin in m.PINNED_EXPORTS}

    def module_handle(self):
        return 1234

    def module_sha256(self):
        return SHA

    def exports(self):
        return self._exports

    def pid(self):
        return 123

    def created_time(self):
        return 456

    def bitness(self):
        return 64

    def domain_identity(self):
        return (0x1000, 0, 1)

    def jit_info(self, method_token):
        return None


def make_session(ack=(True, None, False, 'undo-1'), resolver=None,
                 clock=None, backend=None):
    clock = clock or Clock()
    backend = backend or FakeBackend()
    binding = m.AdapterBinding.for_module(SHA, 123, 456, 64)
    if resolver is None:
        resolver = lambda namespace, class_name, method_name: TOKEN
    session = ms.ManagedRuntimeSession(
        binding=binding, backend=backend, now_qpc=clock,
        method_resolver=resolver, ack_provider=lambda sid: ack)
    return session, clock, backend


def broker_sessions(session):
    return session._runtime.snapshot()['broker']['sessions']


class ManagedRuntimeSessionTests(unittest.TestCase):
    def test_bootstrap_is_one_shot_and_bound(self):
        session, clock, _ = make_session()
        snapshot = session._runtime.snapshot()
        self.assertTrue(session.bootstrapped)
        self.assertEqual(snapshot['nonces_consumed'], 1)
        self.assertEqual(session.pid, 123)
        self.assertEqual(session.domains(),
                         [{'id': 0, 'ptr': 0x1000, 'generation': 1}])
        clock.advance(1)
        replay = m.FrozenBootstrap(
            owner_module_sha256=SHA, pid=123, created_time=456,
            deadline_qpc=clock() + 30_000_000, nonce='nonce-again')
        with self.assertRaises(m.BootstrapReplayRefused):
            session._runtime.bootstrap(replay, token=9999)

    def test_invoke_success_with_vtbyte_returns_true_terminal_ack_success(self):
        session, _, _ = make_session()
        token = session.find_method('Yooka', 'Laylee', 'SetFlag')
        self.assertTrue(session.invoke(domain_id=0, method_token=token,
                                       is_static=False,
                                       arguments=(('vtByte', 1),)))
        self.assertEqual(broker_sessions(session)[-1]['state'],
                         'ack_success')

    def test_ack_failure_raises_managed_call_failed(self):
        session, _, _ = make_session(ack=(False, 'boom', False, None))
        with self.assertRaisesRegex(ms.ManagedCallFailed, 'terminal state'):
            session.invoke(domain_id=0, method_token=TOKEN, is_static=True,
                           arguments=())
        self.assertEqual(broker_sessions(session)[-1]['state'],
                         'ack_failure')

    def test_ack_lost_raises_managed_call_unknown(self):
        session, _, _ = make_session(ack=None)
        with self.assertRaisesRegex(ms.ManagedCallUnknown, 'terminal state'):
            session.invoke(domain_id=0, method_token=TOKEN, is_static=True,
                           arguments=())
        self.assertEqual(broker_sessions(session)[-1]['state'], 'ack_lost')

    def test_wrong_domain_id_raises_managed_domain_refused(self):
        session, _, _ = make_session()
        with self.assertRaisesRegex(ms.ManagedDomainRefused,
                                    'does not match the bound domain'):
            session.invoke(domain_id=5, method_token=TOKEN, is_static=True,
                           arguments=())
        with self.assertRaisesRegex(ms.ManagedDomainRefused, 'nonnegative'):
            session.invoke(domain_id=-1, method_token=TOKEN, is_static=True,
                           arguments=())
        self.assertEqual(len(broker_sessions(session)), 1)

    def test_unknown_vt_name_raises_managed_value_refused(self):
        session, _, _ = make_session()
        with self.assertRaisesRegex(ms.ManagedValueRefused,
                                    'Unknown managed value type'):
            session.invoke(domain_id=0, method_token=TOKEN, is_static=False,
                           arguments=(('vtHogehoge', 1),))
        with self.assertRaisesRegex(ms.ManagedValueRefused,
                                    'Unknown managed value type'):
            session.invoke(domain_id=0, method_token=TOKEN, is_static=False,
                           arguments=(('', 1),))
        with self.assertRaisesRegex(ms.ManagedValueRefused,
                                    'value type must be text'):
            session.invoke(domain_id=0, method_token=TOKEN, is_static=False,
                           arguments=((1, 1),))
        with self.assertRaisesRegex(ms.ManagedValueRefused,
                                    'value type must be text'):
            session.invoke(domain_id=0, method_token=TOKEN, is_static=False,
                           arguments=((None, 1),))
        with self.assertRaisesRegex(ms.ManagedValueRefused,
                                    'pairs'):
            session.invoke(domain_id=0, method_token=TOKEN, is_static=False,
                           arguments=(('vtByte',),))
        self.assertEqual(len(broker_sessions(session)), 1)

    def test_vt_object_maps_to_instance_ref(self):
        session, _, _ = make_session()
        self.assertTrue(session.invoke(
            domain_id=0, method_token=TOKEN, is_static=False,
            arguments=(('vtObject', 42), ('vtString', 'x'),
                       ('vtQWord', 7))))
        latest = broker_sessions(session)[-1]
        spec = session._runtime._broker._sessions[latest['session_id']].spec
        self.assertEqual(spec.argument_kinds,
                         (ARG_INSTANCE_REF, ARG_STRING, 'static_bytes'))
        self.assertEqual(latest['state'], 'ack_success')

    def test_vt_byref_requires_capability_token(self):
        # The mapping admits vtByRef/vtGeneric to their broker kinds, but the
        # tested broker refuses mutable kinds without an explicit capability
        # token: a named, visible refusal, no session admitted.
        session, _, _ = make_session()
        for kind in ('vtByRef', 'vtGeneric'):
            with self.subTest(kind=kind):
                with self.assertRaises(
                        mono_broker.UnsupportedSignatureRefused):
                    session.invoke(domain_id=0, method_token=TOKEN,
                                   is_static=False,
                                   arguments=((kind, 3),))
                self.assertEqual(len(broker_sessions(session)), 1)

    def test_find_method_validation(self):
        session, _, _ = make_session()
        with self.assertRaisesRegex(ms.ManagedValueRefused, 'non-empty text'):
            session.find_method('', 'Laylee', 'SetFlag')
        with self.assertRaisesRegex(ms.ManagedValueRefused, 'non-empty text'):
            session.find_method('Yooka', None, 'SetFlag')
        with self.assertRaisesRegex(ms.ManagedValueRefused, 'non-empty text'):
            session.find_method('Yooka', 'Laylee', '')
        zero, _, _ = make_session(resolver=lambda a, b, c: 0)
        with self.assertRaisesRegex(ms.ManagedValueRefused, 'invalid token'):
            zero.find_method('Yooka', 'Laylee', 'SetFlag')
        text, _, _ = make_session(resolver=lambda a, b, c: 'not-an-int')
        with self.assertRaisesRegex(ms.ManagedValueRefused, 'invalid token'):
            text.find_method('Yooka', 'Laylee', 'SetFlag')

    def test_target_ended_then_invoke_raises_released(self):
        session, _, _ = make_session()
        session.target_ended()
        self.assertTrue(session._runtime.snapshot()['target_ended'])
        self.assertIsNotNone(session.uncertainty)
        with self.assertRaisesRegex(ms.ManagedSessionReleased, 'retired'):
            session.invoke(domain_id=0, method_token=TOKEN, is_static=True,
                           arguments=())
        # Retirement is total: a second call must stay quiet.
        session.target_ended()

    def test_release_then_invoke_raises_released(self):
        session, _, _ = make_session()
        session.release()
        with self.assertRaisesRegex(ms.ManagedSessionReleased, 'retired'):
            session.invoke(domain_id=0, method_token=TOKEN, is_static=True,
                           arguments=())
        session.release()


if __name__ == '__main__':
    unittest.main()
