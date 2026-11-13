"""MT-34 (0.45): the per-session hotkey switch (disable-all / reset to
the table's defaults).

The trainer header gains one control, "Hotkeys: on/off", in every
trainer (standalone + Master, like "Re-attach" - no header
byte-identity test exists).  Off forces the engine's published-binding
live set to empty (every model binding and its OS mirror released,
nothing new published); on re-publishes the table-declared hotkeys of
the live records in activation order - the table's defaults, since no
per-record override surface exists.  The plan-level bindings are never
mutated, the state is session-scoped (never persisted, a fresh engine
starts on), and the ordinary toggle/dispatch paths are unaffected
while the switch is off.

Covered:
- engine: default on, off releases all model + OS bindings (named
  unbound dispatch, display rows unregistered, plan untouched),
  on restores the table defaults, activations while off publish
  nothing until on (first-wins intact), double-set no-op, the toggle
  path stays fully functional while off;
- UI (real Tk window, play_sound mocked): the header button exists
  with the "Hotkeys: on" label, a click flips the engine flag and the
  label, off/on through the control release/restore the bindings, and
  the poll tick keeps the label in sync with a direct engine call.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from test_native_engine_code import Coordinator
from test_native_lua_activation import Memory
from test_native_os_hotkeys import FakeBridge
from test_native_record_hotkeys import CT_BODY

from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import TrainerEngine
from ct2trainer.native.hotkey_model import HotKeySpec

try:
    import tkinter as tk
    from ct2trainer.native.ui import TrainerWindow
    from native_tk_teardown import force_root_release
except ImportError:  # pragma: no cover - environment without Tcl/Tk
    tk = None
    TrainerWindow = None
    force_root_release = None

# The baseline published set after one activation of record 1 (the
# staged value row 2 goes live with its provider; the profile rows 6
# and 7 register by id) - the exact order RecordHotkeyEngineTests
# proves.
BASELINE = [(1, "F1"), (2, "F2"), (2, "F3"), (2, "F11"), (2, "F12"),
            (6, "F10"), (7, "F8")]


class SessionHotkeyEngineTests(unittest.TestCase):
    """The session switch drives the published-binding live set."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        ct = root / "hotkeys.ct"
        ct.write_text(CT_BODY, encoding="utf-8")
        self.plan = compile_table(ct, "FixtureTarget.exe")
        self.memory = Memory()
        self.engine = TrainerEngine(
            self.plan, state_dir=root / "state",
            process_lock_dir=root / "shared",
            memory_factory=lambda name: self.memory,
            hook_coordinator=Coordinator())
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)
        self.bridge = FakeBridge()
        self.engine.hotkey_bridge = self.bridge

    def tearDown(self):
        if not self.engine.closed:
            self.memory.alive = False
            self.engine.poll()
            self.engine.close()
        self.directory.cleanup()

    def _registered(self):
        return [(item.record_id, item.spec.key)
                for item in self.engine.hotkey_controller.registrations()]

    def test_session_starts_with_hotkeys_enabled(self):
        self.assertTrue(self.engine.session_hotkeys_enabled)
        # A no-op set returns the current state without re-sync churn.
        self.assertTrue(self.engine.set_session_hotkeys(True))
        self.assertTrue(self.engine.session_hotkeys_enabled)

    def test_off_releases_all_model_and_os_bindings(self):
        self.assertTrue(self.engine.toggle(1, True))
        self.assertEqual(self._registered(), BASELINE)
        held = set(self.bridge.registered)
        self.assertEqual(held, {HotKeySpec.parse(k)
                                for _rid, k in BASELINE})
        self.assertFalse(self.engine.set_session_hotkeys(False))
        self.assertFalse(self.engine.session_hotkeys_enabled)
        # Model side: every published binding is gone.
        self.assertEqual(self.engine.hotkey_controller.registrations(), ())
        # OS mirror: nothing registered, exactly what was held released.
        self.assertEqual(self.bridge.registered, set())
        self.assertEqual(set(self.bridge.released), held)
        # Display rows read back unregistered.
        self.assertEqual(self.engine.hotkey_registered_keys(1),
                         (("F1", False), ("F7", False)))
        self.assertEqual(self.engine.hotkey_registered_keys(2),
                         (("F2", False), ("F3", False), ("F5", False),
                          ("F11", False), ("F12", False)))
        # Pressing a released combination is a clean unbound no-op.
        self.assertEqual(
            self.engine.dispatch_hotkey(HotKeySpec.parse("F1")).status,
            "unbound")
        # The plan-level bindings are byte-untouched.
        self.assertEqual(
            [h["keys"] for h in self.engine.entries[1]["hotkeys"]],
            [[112], [118]])  # VK codes: F1, F7
        # The ordinary activation state is unaffected by the switch.
        self.assertIn(1, self.engine.applied)

    def test_on_restores_the_table_defaults(self):
        self.assertTrue(self.engine.toggle(1, True))
        self.assertEqual(self._registered(), BASELINE)
        self.assertFalse(self.engine.set_session_hotkeys(False))
        self.assertEqual(self.engine.hotkey_controller.registrations(), ())
        self.assertTrue(self.engine.set_session_hotkeys(True))
        self.assertEqual(self._registered(), BASELINE)
        self.assertEqual(
            self.bridge.registered,
            {HotKeySpec.parse(k) for _rid, k in BASELINE})
        # The restored binding is live end-to-end again.
        self.assertEqual(
            self.engine.dispatch_hotkey(HotKeySpec.parse("F1")).status,
            "triggered")
        self.assertNotIn(1, self.engine.applied)  # toggled back off
        # Re-enable keeps it re-publishable for the still-live set.
        self.assertTrue(self.engine.set_session_hotkeys(True))

    def test_activations_while_off_publish_nothing_until_on(self):
        self.assertFalse(self.engine.set_session_hotkeys(False))
        self.assertTrue(self.engine.toggle(1, True))
        self.assertTrue(self.engine.toggle(3, True))
        # Both records are live in the model, yet nothing is published.
        self.assertIn(1, self.engine.applied)
        self.assertIn(3, self.engine.applied)
        self.assertEqual(self.engine.hotkey_controller.registrations(), ())
        self.assertEqual(self.bridge.registered, set())
        # Back on: the live set re-publishes in activation order, and
        # the first-wins policy still arbitrates the shared F1.
        self.assertTrue(self.engine.set_session_hotkeys(True))
        winner = self.engine.hotkey_controller.find(HotKeySpec.parse("F1"))
        self.assertEqual(winner.record_id, 1)
        self.assertEqual(self.engine.hotkey_registered_keys(3),
                         (("F1", False),))
        self.assertIn(
            "Record 3 ('Conflicting F1 script'): hotkey F1 not registered: "
            "key already bound to record 1 ('Hotkey anchor script') "
            "by first-wins",
            self.engine.hotkey_warnings)

    def test_off_does_not_block_the_toggle_path(self):
        self.assertFalse(self.engine.set_session_hotkeys(False))
        self.assertTrue(self.engine.toggle(1, True))
        self.assertEqual(self.memory.read(0x1014, 4), b"\x01\x00\x00\x00")
        self.assertFalse(self.engine.toggle(1, False))
        self.assertEqual(self.memory.read(0x1014, 4), b"\x00\x00\x00\x00")
        # The memory effect is byte-exact through the off session.
        self.assertEqual(
            {address for address, _ in self.memory.writes}, {0x1014})

    def test_double_set_is_a_noop_and_keeps_state(self):
        self.assertTrue(self.engine.set_session_hotkeys(True))
        self.assertTrue(self.engine.set_session_hotkeys(True))
        self.assertFalse(self.engine.set_session_hotkeys(False))
        self.assertFalse(self.engine.set_session_hotkeys(False))
        self.assertFalse(self.engine.session_hotkeys_enabled)


@unittest.skipIf(tk is None or TrainerWindow is None,
                 "tkinter required for the real trainer window")
class SessionHotkeyUiTests(unittest.TestCase):
    """The header control drives the engine switch (real Tk window)."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        ct = root / "hotkeys.ct"
        ct.write_text(CT_BODY, encoding="utf-8")
        plan = compile_table(ct, "FixtureTarget.exe")
        self.memory = Memory()
        self.engine = TrainerEngine(
            plan, state_dir=root / "state", process_lock_dir=root / "shared",
            memory_factory=lambda name: self.memory,
            hook_coordinator=Coordinator())
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)
        self.root = None

    def tearDown(self):
        if self.root is not None:
            force_root_release([self.root], ((self, "root"),))
        if not self.engine.closed:
            self.memory.alive = False
            self.engine.poll()
            self.engine.close()

    def _window(self) -> TrainerWindow:
        self.root = tk.Tk()
        self.root.withdraw()
        return TrainerWindow(self.root, self.engine)

    def test_header_button_present_with_on_label(self):
        window = self._window()
        self.assertIsNotNone(window.hotkeys_btn)
        self.assertEqual(str(window.hotkeys_btn.cget("text")),
                         "Hotkeys: on")
        self.assertTrue(self.engine.session_hotkeys_enabled)

    def test_click_toggles_engine_flag_and_label(self):
        window = self._window()
        window._toggle_session_hotkeys()
        self.assertFalse(self.engine.session_hotkeys_enabled)
        self.assertEqual(str(window.hotkeys_btn.cget("text")),
                         "Hotkeys: off")
        window._toggle_session_hotkeys()
        self.assertTrue(self.engine.session_hotkeys_enabled)
        self.assertEqual(str(window.hotkeys_btn.cget("text")),
                         "Hotkeys: on")

    def test_click_off_releases_and_click_on_restores(self):
        window = self._window()
        self.assertTrue(self.engine.toggle(1, True))
        self.assertEqual(
            [(item.record_id, item.spec.key)
             for item in self.engine.hotkey_controller.registrations()],
            BASELINE)
        window._toggle_session_hotkeys()
        self.assertEqual(self.engine.hotkey_controller.registrations(), ())
        window._toggle_session_hotkeys()
        self.assertEqual(
            [(item.record_id, item.spec.key)
             for item in self.engine.hotkey_controller.registrations()],
            BASELINE)

    def test_poll_keeps_the_label_in_sync(self):
        window = self._window()
        self.engine.set_session_hotkeys(False)
        window.poll()
        self.assertEqual(str(window.hotkeys_btn.cget("text")),
                         "Hotkeys: off")
        self.engine.set_session_hotkeys(True)
        window.poll()
        self.assertEqual(str(window.hotkeys_btn.cget("text")),
                         "Hotkeys: on")


if __name__ == "__main__":
    unittest.main()
