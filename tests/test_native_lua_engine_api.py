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


def _make_engine(symbols=None, process='fixture.exe'):
    memory = _Memory()
    engine = SimpleNamespace(memory=memory,
                             plan={'process_name': process},
                             symbols=symbols if symbols is not None else {},
                             _guard=lambda: None)
    return engine


class NativeLuaEngineApiEngineTests(unittest.TestCase):
    """Broker-level contract for luaEngine.* (getLuaEngine facade backing)."""

    def _broker(self, **options):
        engine = _make_engine()
        options.setdefault('input_handler', object())
        broker = EngineLuaBroker(engine, **options)
        return engine, broker

    def test_snapshot_reports_attached_and_process(self):
        engine, broker = self._broker()
        snapshot = broker.call('luaEngine.snapshot', (),
                               generation=0, syntaxcheck=False)
        self.assertEqual(snapshot, {'attached': True,
                                    'process': 'fixture.exe'})

    def test_snapshot_rejects_arguments(self):
        engine, broker = self._broker()
        with self.assertRaisesRegex(LuaHostError,
                                    'Engine snapshot takes no arguments'):
            broker.call('luaEngine.snapshot', ('x',),
                        generation=0, syntaxcheck=False)

    def test_close_routes_to_owned_shutdown(self):
        calls = []
        engine, broker = self._broker(shutdown_handler=lambda: calls.append(1))
        self.assertIsNone(broker.call('luaEngine.close', (),
                                      generation=0, syntaxcheck=False))
        self.assertEqual(calls, [1])

    def test_close_refused_without_shutdown_route(self):
        engine, broker = self._broker()
        with self.assertRaisesRegex(LuaHostError,
                                    'Engine close requires an owned shutdown route'):
            broker.call('luaEngine.close', (), generation=0, syntaxcheck=False)

    def test_menu_click_routes_to_registered_action_casefolded(self):
        calls = []
        engine, broker = self._broker(
            menu_actions={'MenuItem5': lambda: calls.append('click')})
        result = broker.call('luaEngine.menuClick', ('menuitem5',),
                             generation=0, syntaxcheck=False)
        self.assertIsNone(result)
        self.assertEqual(calls, ['click'])

    def test_menu_click_unknown_item_refused_with_name(self):
        engine, broker = self._broker(menu_actions={'MenuItem5': lambda: None})
        with self.assertRaisesRegex(LuaHostError,
                                    'Menu item is not registered: MenuItem9'):
            broker.call('luaEngine.menuClick', ('MenuItem9',),
                        generation=0, syntaxcheck=False)

    def test_menu_click_argument_validation(self):
        engine, broker = self._broker(menu_actions={'MenuItem5': lambda: None})
        for arguments in ((), ('MenuItem5', 'extra'), (4096,), ('',)):
            with self.assertRaisesRegex(LuaHostError,
                                        'Menu item name must be non-empty text'):
                broker.call('luaEngine.menuClick', arguments,
                            generation=0, syntaxcheck=False)

    def test_engine_actions_refused_during_syntaxcheck(self):
        calls = []
        engine, broker = self._broker(
            shutdown_handler=lambda: calls.append(1),
            menu_actions={'MenuItem5': lambda: calls.append(2)})
        for name, arguments in (('luaEngine.close', ()),
                                ('luaEngine.menuClick', ('MenuItem5',))):
            with self.assertRaisesRegex(LuaHostError,
                                        'Trainer engine action requires a live '
                                        'activation'):
                broker.call(name, arguments, generation=0, syntaxcheck=True)
        self.assertEqual(calls, [])

    def test_stale_generation_refused_before_dispatch(self):
        engine, broker = self._broker()
        broker.invalidate()
        with self.assertRaisesRegex(LuaHostError,
                                    'Stale Lua session generation'):
            broker.call('luaEngine.snapshot', (),
                        generation=0, syntaxcheck=False)

    def test_target_identity_change_refuses_dispatch(self):
        engine, broker = self._broker()
        engine.memory.identity = (999, 999)
        with self.assertRaisesRegex(LuaHostError,
                                    'Lua target identity changed'):
            broker.call('luaEngine.snapshot', (),
                        generation=0, syntaxcheck=False)


class NativeLuaEngineApiHostTests(unittest.TestCase):
    """Full host path: injected getLuaEngine() facade over the broker."""

    def setUp(self):
        if not _LUPA:
            self.skipTest('pinned MIT Lupa Lua53 dependency is not installed')
        self.calls = []
        self.engine = _make_engine()
        self.broker = EngineLuaBroker(
            self.engine, input_handler=object(),
            shutdown_handler=lambda: self.calls.append('close'),
            menu_actions={'MenuItem5': lambda: self.calls.append('menu5')})
        self.host = LuaHost(self.broker)

    def tearDown(self):
        if self.host is not None:
            self.host.cancel()

    def test_facade_reads_attached_and_process_name(self):
        self.assertTrue(self.host.execute('return getLuaEngine().attached'))
        self.assertEqual(self.host.execute('return getLuaEngine().processName'),
                         'fixture.exe')

    def test_close_reaches_owned_shutdown_route(self):
        self.assertIsNone(self.host.execute('return getLuaEngine().close()'))
        self.assertEqual(self.calls, ['close'])

    def test_close_without_route_raises_at_lua_boundary(self):
        self.broker.shutdown_handler = None
        with self.assertRaisesRegex(LuaHostError,
                                    'Engine close requires an owned shutdown route'):
            self.host.execute('return getLuaEngine().close()')

    def test_menu_item_do_click_matches_corpus_shape(self):
        # Borderlands3 corpus usage: GetLuaEngine().MenuItem5.doClick()
        self.host.execute('GetLuaEngine().MenuItem5.doClick()')
        self.assertEqual(self.calls, ['menu5'])

    def test_click_menu_item_by_name(self):
        # The registry is keyed casefolded; the call is case-insensitive.
        self.broker.menu_actions['menuitem7'] = lambda: self.calls.append('m7')
        self.host.execute('getLuaEngine().clickMenuItem("MenuItem7")')
        self.assertEqual(self.calls, ['m7'])

    def test_unknown_menu_item_is_refused(self):
        with self.assertRaisesRegex(LuaHostError,
                                    'Menu item is not registered: MenuItem9'):
            self.host.execute('getLuaEngine().MenuItem9.doClick()')

    def test_unknown_facade_property_is_refused(self):
        with self.assertRaisesRegex(LuaHostError,
                                    'Unsupported trainer engine property'):
            self.host.execute('return getLuaEngine().bogus')

    def test_facade_is_read_only(self):
        with self.assertRaisesRegex(LuaHostError,
                                    'Trainer engine is read-only'):
            self.host.execute('getLuaEngine().attached = false')

    def test_facade_metatable_is_owned(self):
        self.assertEqual(
            self.host.execute(
                'return tostring(getmetatable(getLuaEngine()))'),
            'CT2Trainer engine facade')

    def test_syntaxcheck_reads_snapshot(self):
        self.assertEqual(
            self.host.execute('return getLuaEngine().processName',
                              syntaxcheck=True),
            'fixture.exe')

    def test_engine_actions_refused_in_syntaxcheck(self):
        # The host's read-only syntax-check guard refuses the non-read names
        # before they reach the broker dispatch.
        for source in ('getLuaEngine().close()',
                       'getLuaEngine().MenuItem5.doClick()'):
            with self.assertRaisesRegex(LuaHostError,
                                        'Syntax checking cannot call mutation API'):
                self.host.execute(source, syntaxcheck=True)
        self.assertEqual(self.calls, [])

    def test_helper_bootstrap_may_read_snapshot(self):
        self.host.install_helpers(
            'function probe() return getLuaEngine().processName end')
        self.assertEqual(self.host.execute('return probe()'), 'fixture.exe')

    def test_helper_bootstrap_cannot_close_engine(self):
        with self.assertRaisesRegex(LuaHostError,
                                    'cannot call mutation API'):
            self.host.install_helpers('getLuaEngine().close()')
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
