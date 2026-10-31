"""Record-Lua CE global stubs (WP-56, GC-E19).

Sinking City 2 field case (anonymized; corpus-wide counts: getMainForm
226/41, createMenuItem 110/36, addCompactMenu 80/29, OpenProcess attach
record, ShellExecute support record): record Lua in the reference corpus
calls CE globals the native trainer has no equivalent for.  The stubs are
faithful no-ops, not silence: ``OpenProcess`` is a truthy identity check
against the attached process name (case-insensitive, both CE first-letter
spellings) whose mismatch is a named refusal; ``ShellExecute`` performs no
external launch and is accepted up to four arguments; ``getMainForm`` /
``createMenuItem`` / ``addCompactMenu`` (both spellings each) return inert
menu proxies whose property writes are stored (caption-based toggle logic
reads back what it set) and whose method calls are accepted and discarded.
``syntaxcheck`` stays false at runtime and true in check-only mode, and any
remaining undefined CE global fails closed with the exact named refusal
``Unsupported CE Lua API: <name>`` (the pre-existing taxonomy, no trailing
period).
"""
import unittest
from types import SimpleNamespace

from ct2trainer.native.lua_host import (EngineLuaBroker, LuaHost,
                                        LuaHostError)

try:
    import lupa.lua53  # noqa: F401
    _LUPA = True
except ImportError:
    _LUPA = False


class _RecordingMemory:
    identity = (123, 456)
    pointer_size = 8
    pid = 4242
    process_handle = 0x11121314

    def __init__(self):
        self.ops = []

    def _range(self, address, size):
        self.ops.append(('range', address, size))

    def read(self, address, size):
        self.ops.append(('read', address, size))
        return b'\x00' * size

    def write(self, address, data):
        self.ops.append(('write', address, bytes(data)))
        return True


def _broker(process_name='fixture.exe'):
    memory = _RecordingMemory()
    engine = SimpleNamespace(memory=memory,
                             plan={'process_name': process_name},
                             symbols={},
                             _guard=lambda: None)
    return memory, EngineLuaBroker(engine, input_handler=object())


class OpenProcessBrokerTests(unittest.TestCase):
    """openProcess: truthy identity check, named mismatch/argument refusals."""

    def test_matching_process_name_returns_true(self):
        _memory, broker = _broker()
        for call in (('fixture.exe',), ('FIXTURE.EXE',), ('Fixture.exe',)):
            with self.subTest(call=call):
                self.assertIs(
                    broker.call('openProcess', call, generation=0,
                                syntaxcheck=False), True)

    def test_mismatched_process_name_is_a_named_refusal(self):
        _memory, broker = _broker()
        with self.assertRaisesRegex(
                LuaHostError,
                "openProcess target does not match the attached process: other.exe"):
            broker.call('openProcess', ('other.exe',), generation=0,
                        syntaxcheck=False)

    def test_argument_shape_refusals(self):
        _memory, broker = _broker()
        for call in ((), ('',), (123,), ('a', 'b')):
            with self.subTest(call=call):
                with self.assertRaisesRegex(
                        LuaHostError,
                        'openProcess requires one non-empty process name'):
                    broker.call('openProcess', call, generation=0,
                                syntaxcheck=False)


class ShellExecuteBrokerTests(unittest.TestCase):
    """shellExecute: safe no-op, bounded argument shape, named refusals."""

    def test_no_op_with_up_to_four_arguments(self):
        _memory, broker = _broker()
        for call in (('https://ko-fi.com/lioboss',),
                     ('url', 'params', 'folder', 0)):
            with self.subTest(call=call):
                self.assertIsNone(
                    broker.call('shellExecute', call, generation=0,
                                syntaxcheck=False))

    def test_argument_shape_refusals(self):
        _memory, broker = _broker()
        with self.assertRaisesRegex(
                LuaHostError, 'shellExecute takes at most four arguments'):
            broker.call('shellExecute', (1, 2, 3, 4, 5), generation=0,
                        syntaxcheck=False)
        for call in ((), ('',), (123,)):
            with self.subTest(call=call):
                with self.assertRaisesRegex(
                        LuaHostError,
                        'shellExecute requires a non-empty command'):
                    broker.call('shellExecute', call, generation=0,
                                syntaxcheck=False)

    def test_both_stubs_are_syntaxcheck_safe(self):
        # The record scripts may call the stubs during a disposable syntax
        # check; both are pure reads/no-ops, so they succeed there too.
        _memory, broker = _broker()
        self.assertIs(broker.call('openProcess', ('fixture.exe',),
                                  generation=0, syntaxcheck=True), True)
        self.assertIsNone(broker.call('shellExecute', ('url',),
                                      generation=0, syntaxcheck=True))

    def test_unknown_ce_global_keeps_the_named_refusal(self):
        _memory, broker = _broker()
        with self.assertRaisesRegex(LuaHostError,
                                    'Unsupported CE Lua API: unknownApi'):
            broker.call('unknownApi', (), generation=0, syntaxcheck=False)
        # The taxonomy has no trailing period (pre-existing contract).
        try:
            broker.call('unknownApi', (), generation=0, syntaxcheck=False)
        except LuaHostError as exc:
            self.assertEqual(str(exc), 'Unsupported CE Lua API: unknownApi')


class OpenProcessHostTests(unittest.TestCase):
    """Full host path: both CE spellings reach the identity check."""

    def setUp(self):
        if not _LUPA:
            self.skipTest('pinned MIT Lupa Lua53 dependency is not installed')
        self.memory, self.broker = _broker()
        self.host = LuaHost(self.broker)

    def tearDown(self):
        self.host.cancel()

    def test_open_process_verifies_the_attached_process_identity(self):
        self.assertIs(self.host.execute('return OpenProcess("fixture.exe")'), True)
        self.assertIs(self.host.execute('return openProcess("FIXTURE.EXE")'), True)
        with self.assertRaisesRegex(
                LuaHostError,
                "openProcess target does not match the attached process: other.exe"):
            self.host.execute('return OpenProcess("other.exe")')
        with self.assertRaisesRegex(
                LuaHostError, 'openProcess requires one non-empty process name'):
            self.host.execute('return OpenProcess()')

    def test_open_process_is_a_pure_read_during_syntaxcheck(self):
        self.assertIs(self.host.execute('return OpenProcess("fixture.exe")',
                                        syntaxcheck=True), True)

    def test_shell_execute_is_a_no_op_on_the_live_path(self):
        self.assertIsNone(
            self.host.execute('return ShellExecute("https://ko-fi.com/lioboss")'))
        self.assertIsNone(
            self.host.execute('return shellExecute("u", "p", "f", 0)'))
        with self.assertRaisesRegex(
                LuaHostError, 'shellExecute takes at most four arguments'):
            self.host.execute('return ShellExecute(1, 2, 3, 4, 5)')
        with self.assertRaisesRegex(
                LuaHostError, 'shellExecute requires a non-empty command'):
            self.host.execute('return ShellExecute()')
        # Record 231 shape: the guard skips the call in check mode and the
        # live path performs the safe no-op.
        script = ('if syntaxcheck then return end\n'
                  'ShellExecute("https://ko-fi.com/lioboss")')
        self.assertIsNone(self.host.execute(script))
        self.assertIsNone(self.host.execute(script, syntaxcheck=True))
        self.assertEqual(self.memory.ops, [])


class InertMenuSurfaceHostTests(unittest.TestCase):
    """getMainForm/createMenuItem/addCompactMenu inert proxies (record 198)."""

    def setUp(self):
        if not _LUPA:
            self.skipTest('pinned MIT Lupa Lua53 dependency is not installed')
        self.memory, self.broker = _broker()
        self.host = LuaHost(self.broker)

    def tearDown(self):
        self.host.cancel()

    def test_proxies_are_fresh_and_inert(self):
        self.assertFalse(self.host.execute(
            'local a = getMainForm()\n'
            'local b = getMainForm()\n'
            'return a == b'))
        self.assertTrue(self.host.execute('return getMainForm().Splitter1.Visible'))
        self.assertTrue(self.host.execute('return GetMainForm().Menu.Items'))
        self.assertTrue(self.host.execute('return createMenuItem("parent")'))
        self.assertTrue(self.host.execute('return AddCompactMenu({})'))

    def test_property_writes_are_stored_and_read_back(self):
        self.assertEqual(self.host.execute(
            'local item = createMenuItem("parent")\n'
            'item.Caption = "Full View Mode"\n'
            'return item.Caption'), "Full View Mode")
        self.assertEqual(self.host.execute(
            'local item = CreateMenuItem("x")\n'
            'item.Caption = "C"\n'
            'return item.Caption'), "C")
        # Method calls are accepted and discarded (parent.add(item));
        # the inert proxy returns a fresh inert object, never an error.
        self.assertTrue(self.host.execute(
            'local parent = getMainForm().Menu.Items\n'
            'local item = createMenuItem(parent)\n'
            'return parent.add(item) ~= nil'))

    def test_record_198_toggle_pattern_across_execute_calls(self):
        # Sinking City 2 record 198 shape (verbatim structure): global
        # toggle function plus global addCompactMenu (which shadows the
        # inert stub global), global state variables; the DISABLE phase
        # executes separately on the same activation and reads back the
        # caption stored on the persistent proxy.
        enable = (
            "function cycleFullCompact(sender, force)\n"
            "  local state = not(compactmenuitem.Caption == 'Compact View Mode')\n"
            "  if force ~= nil then state = not force end\n"
            "  compactmenuitem.Caption = state and 'Compact View Mode' or 'Full View Mode'\n"
            "  getMainForm().Splitter1.Visible = state\n"
            "  getMainForm().Panel4.Visible = state\n"
            "  getMainForm().Panel5.Visible = state\n"
            "end\n"
            "function addCompactMenu()\n"
            "  if compactmenualreadyexists then return end\n"
            "  local parent = getMainForm().Menu.Items\n"
            "  compactmenuitem = createMenuItem(parent)\n"
            "  parent.add(compactmenuitem)\n"
            "  compactmenuitem.Caption = 'Compact View Mode'\n"
            "  compactmenuitem.OnClick = cycleFullCompact\n"
            "  compactmenualreadyexists = 'yes'\n"
            "end\n"
            "addCompactMenu()\n"
            "cycleFullCompact(nil, true)\n"
            "return compactmenuitem.Caption")
        self.assertEqual(self.host.execute(enable), "Full View Mode")
        self.assertEqual(
            self.host.execute("cycleFullCompact(nil, false)\n"
                              "return compactmenuitem.Caption"),
            "Compact View Mode")
        self.assertEqual(self.memory.ops, [])


class SyntaxCheckGlobalHostTests(unittest.TestCase):
    """syntaxcheck: false at runtime, true in check-only mode."""

    def setUp(self):
        if not _LUPA:
            self.skipTest('pinned MIT Lupa Lua53 dependency is not installed')
        _memory, self.broker = _broker()
        self.host = LuaHost(self.broker)
        _memory2, checker_broker = _broker()
        self.checker = LuaHost(checker_broker, _check_only=True)

    def tearDown(self):
        self.host.cancel()
        self.checker.cancel()

    def test_runtime_syntaxcheck_is_false_and_check_mode_is_true(self):
        script = 'if syntaxcheck then return "checked" end; return "live"'
        self.assertEqual(self.host.execute(script), "live")
        self.assertEqual(self.checker.execute(script), "checked")


class NamedApiRefusalHostTests(unittest.TestCase):
    """Undefined CE globals fail closed with the exact named refusal."""

    def setUp(self):
        if not _LUPA:
            self.skipTest('pinned MIT Lupa Lua53 dependency is not installed')
        self.memory, self.broker = _broker()
        self.host = LuaHost(self.broker)

    def tearDown(self):
        self.host.cancel()

    def test_unknown_global_call_gets_the_named_refusal(self):
        # RT-5 item E moved messageDialog out of the unknown set (it is now
        # a safe no-op, pinned in tests/test_native_rt5_message_dialog.py);
        # this test keeps the exact named-refusal contract on an arbitrary
        # undefined CE global.
        with self.assertRaisesRegex(LuaHostError,
                                    'Unsupported CE Lua API: totallyUnknownCeApi'):
            self.host.execute('return totallyUnknownCeApi("x")')

    def test_nil_field_and_local_calls_keep_the_raw_lua_text(self):
        # The mapping only rewrites nil *global* calls; a nil field or local
        # stays the ordinary Lua error so script state bugs stay visible.
        with self.assertRaisesRegex(LuaHostError,
                                    "attempt to call a nil value"):
            self.host.execute('local t = {}\nreturn t.missing()')
        with self.assertRaisesRegex(LuaHostError,
                                    "attempt to call a nil value"):
            self.host.execute('local missing\nreturn missing()')

    def test_plain_nil_state_reads_stay_silent(self):
        self.assertEqual(self.host.execute(
            'if not someUnsetFlag then return 42 end'), 42)


if __name__ == "__main__":
    unittest.main()
