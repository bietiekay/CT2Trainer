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


def _make_engine(symbols):
    memory = _Memory()
    engine = SimpleNamespace(memory=memory, symbols=symbols,
                             _guard=lambda: None)
    return engine


class NativeLuaSymbolApiEngineTests(unittest.TestCase):
    """Broker-level contract: getAddressOfSymbol / getAddressOfSymbolSafe."""

    def _broker(self, symbols):
        engine = _make_engine(symbols)
        broker = EngineLuaBroker(engine, input_handler=object())
        return engine, broker

    def test_registered_symbol_returns_exact_address(self):
        engine, broker = self._broker({'flag': 0x1000, 'base': 0x2000})
        value = broker.call('getAddressOfSymbol', ('flag',),
                            generation=0, syntaxcheck=False)
        self.assertEqual(value, 0x1000)
        self.assertEqual(broker.call('getAddressOfSymbol', ('base',),
                                     generation=0, syntaxcheck=False), 0x2000)

    def test_lookup_matches_registry_casefold(self):
        # The engine registry is keyed casefolded at write time.
        engine, broker = self._broker({'flag': 0x1000})
        for spelling in ('flag', 'FLAG', 'Flag', 'fLag'):
            self.assertEqual(
                broker.call('getAddressOfSymbol', (spelling,),
                            generation=0, syntaxcheck=False), 0x1000)

    def test_strict_lookup_of_unknown_symbol_refused(self):
        engine, broker = self._broker({'flag': 0x1000})
        with self.assertRaisesRegex(LuaHostError,
                                    'Symbol is not registered: missing'):
            broker.call('getAddressOfSymbol', ('missing',),
                        generation=0, syntaxcheck=False)

    def test_safe_lookup_of_unknown_symbol_is_none(self):
        engine, broker = self._broker({'flag': 0x1000})
        self.assertIsNone(broker.call('getAddressOfSymbolSafe', ('missing',),
                                      generation=0, syntaxcheck=False))
        # The safe variant never raises for an unknown name, even checking.
        self.assertIsNone(broker.call('getAddressOfSymbolSafe', ('missing',),
                                      generation=0, syntaxcheck=True))

    def test_argument_count_is_validated(self):
        engine, broker = self._broker({'flag': 0x1000})
        for name in ('getAddressOfSymbol', 'getAddressOfSymbolSafe'):
            with self.assertRaisesRegex(LuaHostError,
                                        'exactly one name'):
                broker.call(name, (), generation=0, syntaxcheck=False)
            with self.assertRaisesRegex(LuaHostError,
                                        'exactly one name'):
                broker.call(name, ('flag', 'extra'),
                            generation=0, syntaxcheck=False)

    def test_non_string_and_empty_names_refused(self):
        engine, broker = self._broker({'flag': 0x1000})
        for name in ('getAddressOfSymbol', 'getAddressOfSymbolSafe'):
            with self.assertRaisesRegex(LuaHostError,
                                        'non-empty text'):
                broker.call(name, (4096,), generation=0, syntaxcheck=False)
            with self.assertRaisesRegex(LuaHostError,
                                        'non-empty text'):
                broker.call(name, ('',), generation=0, syntaxcheck=False)

    def test_lookup_is_read_only_during_syntaxcheck(self):
        engine, broker = self._broker({'flag': 0x1000})
        # No mutation handler is present; a lookup must still succeed.
        self.assertEqual(broker.call('getAddressOfSymbol', ('flag',),
                                     generation=0, syntaxcheck=True), 0x1000)

    def test_stale_generation_still_refused_before_lookup(self):
        engine, broker = self._broker({'flag': 0x1000})
        broker.invalidate()
        with self.assertRaisesRegex(LuaHostError,
                                    'Stale Lua session generation'):
            broker.call('getAddressOfSymbol', ('flag',),
                        generation=0, syntaxcheck=False)

    def test_target_identity_change_refuses_lookup(self):
        engine, broker = self._broker({'flag': 0x1000})
        engine.memory.identity = (999, 999)
        with self.assertRaisesRegex(LuaHostError,
                                    'Lua target identity changed'):
            broker.call('getAddressOfSymbol', ('flag',),
                        generation=0, syntaxcheck=False)


class NativeLuaSymbolApiHostTests(unittest.TestCase):
    """Full host path: injected Lua functions reach the engine registry."""

    def setUp(self):
        if not _LUPA:
            self.skipTest('pinned MIT Lupa Lua53 dependency is not installed')
        engine = _make_engine({'flag': 0x123456789AB, 'base': 0x2000})
        self.engine = engine
        self.broker = EngineLuaBroker(engine, input_handler=object())
        self.host = LuaHost(self.broker)

    def tearDown(self):
        if self.host is not None:
            self.host.cancel()

    def test_host_returns_registered_symbol_address(self):
        self.assertEqual(self.host.execute('return getAddressOfSymbol("flag")'),
                         0x123456789AB)
        self.assertEqual(self.host.execute('return getAddressOfSymbol("BASE")'),
                         0x2000)

    def test_host_safe_lookup_returns_nil_for_unknown(self):
        self.assertIsNone(self.host.execute(
            'return getAddressOfSymbolSafe("missing")'))

    def test_host_strict_lookup_of_unknown_symbol_raises(self):
        with self.assertRaisesRegex(LuaHostError, 'not registered'):
            self.host.execute('return getAddressOfSymbol("missing")')

    def test_host_argument_errors_cross_the_lua_boundary(self):
        with self.assertRaisesRegex(LuaHostError, 'exactly one name'):
            self.host.execute('return getAddressOfSymbol()')
        with self.assertRaisesRegex(LuaHostError, 'exactly one name'):
            self.host.execute('return getAddressOfSymbol("flag", "extra")')
        with self.assertRaisesRegex(LuaHostError, 'non-empty text'):
            self.host.execute('return getAddressOfSymbol(42)')
        with self.assertRaisesRegex(LuaHostError, 'non-empty text'):
            self.host.execute('return getAddressOfSymbolSafe("")')

    def test_syntaxcheck_can_read_symbols(self):
        self.assertEqual(
            self.host.execute('return getAddressOfSymbol("flag")',
                              syntaxcheck=True),
            0x123456789AB)

    def test_helper_bootstrap_may_read_symbols_read_only(self):
        self.host.install_helpers('function probe_flag() '
                                  'return getAddressOfSymbol("flag") end')
        self.assertEqual(self.host.execute('return probe_flag()'),
                         0x123456789AB)

    def test_helper_bootstrap_symbol_mutation_is_inert_noop(self):
        # WP-54 (a'): registerSymbol/unregisterSymbol are inert no-ops in the
        # helper bootstrap — ownership belongs to the table scope, so a
        # record-scope replay must not claim table-owned symbols.  The
        # bootstrap still completes, establishes its helpers, and leaves the
        # engine symbol table untouched.
        self.host.install_helpers(
            'registerSymbol("owned", 0x1000)\n'
            'unregisterSymbol("owned")\n'
            'function probe_owned() '
            'return getAddressOfSymbol("flag") end')
        self.assertNotIn('owned', self.engine.symbols)
        self.assertEqual(self.host.execute('return probe_owned()'),
                         0x123456789AB)

    def test_helper_bootstrap_other_mutations_still_refused(self):
        # The still-valid refusal sub-case: every other mutation API stays
        # refused with the exact named reason.
        with self.assertRaisesRegex(LuaHostError,
                                    'cannot call mutation API'):
            self.host.install_helpers('writeInteger(0x1000, 1)')

    def test_mutation_symbol_api_still_requires_live_activation(self):
        with self.assertRaisesRegex(LuaHostError,
                                    'owned live activation'):
            self.host.execute('registerSymbol("owned", 0x1000)')

    def test_helper_source_exposes_both_symbol_apis(self):
        import ct2trainer.native.lua_host as host_module
        self.assertIn("'getAddressOfSymbol'", host_module.BOOTSTRAP)
        self.assertIn("'getAddressOfSymbolSafe'", host_module.BOOTSTRAP)


if __name__ == '__main__':
    unittest.main()
