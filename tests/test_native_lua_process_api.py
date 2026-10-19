import unittest
from types import SimpleNamespace

from ct2trainer.native.lua_host import (
    EngineLuaBroker,
    LuaHost,
    LuaHostError,
)

try:
    import lupa.lua53  # noqa: F401
    _LUPA = True
except ImportError:
    _LUPA = False


class _Memory:
    identity = (123, 456)
    pointer_size = 8
    pid = 4242
    process_handle = 0x11121314


def _make_engine():
    engine = SimpleNamespace(memory=_Memory(),
                             plan={'process_name': 'fixture.exe'},
                             symbols={},
                             _guard=lambda: None)
    return engine


class NativeLuaProcessApiEngineTests(unittest.TestCase):
    """Broker-level contract: getProcHandle / getOpenProcessID."""

    def _broker(self):
        broker = EngineLuaBroker(_make_engine(), input_handler=object())
        return _Memory, broker

    def test_proc_handle_returns_owned_handle(self):
        memory, broker = self._broker()
        value = broker.call('getProcHandle', (), generation=0, syntaxcheck=False)
        self.assertEqual(value, 0x11121314)
        self.assertIsInstance(value, int)

    def test_open_process_id_returns_pid(self):
        memory, broker = self._broker()
        value = broker.call('getOpenProcessID', (), generation=0, syntaxcheck=False)
        self.assertEqual(value, 4242)

    def test_process_api_rejects_arguments(self):
        memory, broker = self._broker()
        for name in ('getProcHandle', 'getOpenProcessID'):
            with self.assertRaisesRegex(LuaHostError,
                                        'Process API takes no arguments'):
                broker.call(name, (1,), generation=0, syntaxcheck=False)

    def test_process_api_is_read_only_during_syntaxcheck(self):
        memory, broker = self._broker()
        self.assertEqual(broker.call('getProcHandle', (),
                                     generation=0, syntaxcheck=True),
                         0x11121314)
        self.assertEqual(broker.call('getOpenProcessID', (),
                                     generation=0, syntaxcheck=True),
                         4242)

    def test_stale_generation_refused_before_process_api(self):
        memory, broker = self._broker()
        broker.invalidate()
        with self.assertRaisesRegex(LuaHostError,
                                    'Stale Lua session generation'):
            broker.call('getProcHandle', (), generation=0, syntaxcheck=False)

    def test_target_identity_change_refuses_process_api(self):
        memory, broker = self._broker()
        memory.identity = (999, 999)
        with self.assertRaisesRegex(LuaHostError,
                                    'Lua target identity changed'):
            broker.call('getOpenProcessID', (), generation=0, syntaxcheck=False)


class NativeLuaProcessApiHostTests(unittest.TestCase):
    """Full host path: injected process API over the broker."""

    def setUp(self):
        if not _LUPA:
            self.skipTest('pinned MIT Lupa Lua53 dependency is not installed')
        self.engine = _make_engine()
        self.broker = EngineLuaBroker(self.engine, input_handler=object())
        self.host = LuaHost(self.broker)

    def tearDown(self):
        if self.host is not None:
            self.host.cancel()

    def test_host_reads_proc_handle_and_pid(self):
        self.assertEqual(self.host.execute('return getProcHandle()'), 0x11121314)
        self.assertEqual(self.host.execute('return getOpenProcessID()'), 4242)

    def test_host_argument_errors_cross_the_lua_boundary(self):
        with self.assertRaisesRegex(LuaHostError,
                                    'Process API takes no arguments'):
            self.host.execute('return getProcHandle(0)')
        with self.assertRaisesRegex(LuaHostError,
                                    'Process API takes no arguments'):
            self.host.execute('return getOpenProcessID("x")')

    def test_open_process_verifies_the_attached_process_identity(self):
        # WP-56 (Sinking City 2 attach record): the native trainer is attached
        # before record Lua ever runs, so OpenProcess is a truthy no-op that
        # verifies the requested identity (case-insensitive, both CE
        # spellings).  A mismatch is a named refusal.
        self.assertIs(self.host.execute('return OpenProcess("fixture.exe")'), True)
        self.assertIs(self.host.execute('return openProcess("FIXTURE.EXE")'), True)
        with self.assertRaisesRegex(LuaHostError,
                                    "openProcess target does not match the attached process: other.exe"):
            self.host.execute('return OpenProcess("other.exe")')

    def test_open_process_is_a_pure_read_during_syntaxcheck(self):
        # WP-56: the identity check performs no live mutation, so the call
        # succeeds in check-only mode as well.
        self.assertIs(self.host.execute('return OpenProcess("fixture.exe")',
                                        syntaxcheck=True), True)

    def test_syntaxcheck_reads_process_surface(self):
        self.assertEqual(self.host.execute('return getProcHandle()',
                                           syntaxcheck=True),
                         0x11121314)

    def test_helper_bootstrap_may_read_process_surface(self):
        self.host.install_helpers(
            'function probe() return getOpenProcessID() end')
        self.assertEqual(self.host.execute('return probe()'), 4242)


if __name__ == '__main__':
    unittest.main()
