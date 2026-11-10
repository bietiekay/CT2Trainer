"""Master Trainer 0.39: state folder / debug log quick access (MT-30).

Covers the pure ``state_access`` layer: the named refusals of
``resolve_state_folder`` / ``resolve_debug_log`` (missing folder /
missing log, wrong kind, bad input - the status line names the cause,
never a crash), the platform opener selection (``os.startfile`` on
Windows), and ``open_path`` with its injectable opener (a failing
opener is contained as the named ``opener-failed`` refusal; an opener
that raises its own ``StateAccessRefusal`` is re-raised unchanged).

The Tk wiring covers the two waiting-view header buttons ("State
folder…" / "Debug log…", master-only - the standalone trainer header
stays byte-identical), the happy path through the (patched) platform
opener into the status line, and the named refusal in the status line
for a missing state folder / a missing debug log / a failing opener.

No real process is attached (a _FakeLister stands in); the desktop
opener is always patched, so no shell window is ever opened.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import tkinter as tk
except ImportError:  # pragma: no cover - environment without Tcl/Tk
    tk = None

from test_native_master_ui import CT_GAMEA, _FakeLister, _all_widgets
from native_tk_teardown import force_root_release

from ct2trainer.native.master_trainer import state_access
from ct2trainer.native.master_trainer.master_ui import (MasterApp,
                                                        MasterWindow)
from ct2trainer.native.master_trainer.state_access import (
    StateAccessRefusal,
    choose_opener,
    open_path,
    resolve_debug_log,
    resolve_state_folder,
)


# ---------------------------------------------------------------------
# pure resolution layer
# ---------------------------------------------------------------------


class ResolveStateFolderTests(unittest.TestCase):
    """MT-30 (0.39): the state-folder resolution (named refusals)."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name) / "state"
        self.folder.mkdir()
        self.file = Path(self.temporary.name) / "a-file.txt"
        self.file.write_text("x", encoding="utf-8")

    def test_an_existing_folder_resolves_to_the_absolute_path(self):
        self.assertEqual(resolve_state_folder(self.folder),
                         str(self.folder.resolve()))

    def test_a_missing_folder_is_a_named_refusal(self):
        missing = self.folder / "nope"
        with self.assertRaises(StateAccessRefusal) as ctx:
            resolve_state_folder(missing)
        self.assertEqual(ctx.exception.code, "state-folder-missing")
        self.assertIn(str(missing.resolve()), ctx.exception.detail)

    def test_a_file_is_not_a_state_folder(self):
        with self.assertRaises(StateAccessRefusal) as ctx:
            resolve_state_folder(self.file)
        self.assertEqual(ctx.exception.code, "state-folder-missing")

    def test_bad_inputs_are_named_refusals(self):
        for bad in (None, ""):
            with self.subTest(bad=bad), \
                    self.assertRaises(StateAccessRefusal) as ctx:
                resolve_state_folder(bad)
            self.assertEqual(ctx.exception.code, "state-folder-bad")


class ResolveDebugLogTests(unittest.TestCase):
    """MT-30 (0.39): the debug-log resolution (named refusals)."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.log = Path(self.temporary.name) / "ct2debug.log"
        self.log.write_text("log line\n", encoding="utf-8")
        self.folder = Path(self.temporary.name) / "a-folder"
        self.folder.mkdir()

    def test_an_existing_log_resolves_to_the_absolute_path(self):
        self.assertEqual(resolve_debug_log(self.log),
                         str(self.log.resolve()))

    def test_a_missing_log_is_a_named_refusal(self):
        missing = self.log.with_name("nope.log")
        with self.assertRaises(StateAccessRefusal) as ctx:
            resolve_debug_log(missing)
        self.assertEqual(ctx.exception.code, "debug-log-missing")
        self.assertIn("debug logging may be disabled", ctx.exception.detail)

    def test_a_folder_is_not_a_debug_log(self):
        with self.assertRaises(StateAccessRefusal) as ctx:
            resolve_debug_log(self.folder)
        self.assertEqual(ctx.exception.code, "debug-log-missing")

    def test_bad_inputs_are_named_refusals(self):
        for bad in (None, 12345):
            with self.subTest(bad=bad), \
                    self.assertRaises(StateAccessRefusal) as ctx:
                resolve_debug_log(bad)
            self.assertEqual(ctx.exception.code, "debug-log-bad")


# ---------------------------------------------------------------------
# opener selection + open_path
# ---------------------------------------------------------------------


@unittest.skipUnless(sys.platform == "win32",
                     "the Windows desktop opener is os.startfile")
class ChooseOpenerTests(unittest.TestCase):
    """MT-30 (0.39): the platform opener decision."""

    def test_windows_uses_the_default_shell(self):
        self.assertIs(choose_opener(), os.startfile)


class OpenPathTests(unittest.TestCase):
    """MT-30 (0.39): open_path with the injectable opener."""

    def test_the_injected_opener_receives_the_target(self):
        opened = []
        open_path("C:\\some\\path", opener=opened.append)
        self.assertEqual(opened, ["C:\\some\\path"])

    def test_a_non_string_target_is_a_named_refusal(self):
        for bad in (None, "", 12345):
            with self.subTest(bad=bad), \
                    self.assertRaises(StateAccessRefusal) as ctx:
                open_path(bad, opener=lambda p: None)
            self.assertEqual(ctx.exception.code, "bad-path")

    def test_an_opener_failure_is_contained_as_a_named_refusal(self):
        def boom(path):
            raise RuntimeError("the desktop is unavailable")

        with self.assertRaises(StateAccessRefusal) as ctx:
            open_path("C:\\some\\path", opener=boom)
        self.assertEqual(ctx.exception.code, "opener-failed")
        self.assertIn("RuntimeError", ctx.exception.detail)
        self.assertIn("the desktop is unavailable", ctx.exception.detail)

    def test_an_opener_refusal_is_re_raised_unchanged(self):
        refusal = StateAccessRefusal("state-folder-missing", "detail")
        with self.assertRaises(StateAccessRefusal) as ctx:
            open_path("C:\\some\\path",
                      opener=lambda p: (_ for _ in ()).throw(refusal))
        self.assertIs(ctx.exception, refusal)

    def test_the_default_opener_is_chosen_at_call_time(self):
        # The module-global choose_opener is the seam: patching it
        # changes the opener open_path() picks (evaluated at call
        # time, not import time).
        opened = []
        with patch.object(state_access, "choose_opener",
                          return_value=opened.append):
            open_path("C:\\state")
        self.assertEqual(opened, ["C:\\state"])


# ---------------------------------------------------------------------
# Tk wiring (the waiting-view header buttons)
# ---------------------------------------------------------------------


@unittest.skipIf(tk is None, "tkinter not available")
class StateAccessUiTests(unittest.TestCase):
    """The "State folder…" / "Debug log…" header buttons."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.folder = root / "tables"
        self.folder.mkdir()
        self.state_home = root / "state"
        self.state_home.mkdir()
        (self.folder / "a.ct").write_text(CT_GAMEA, encoding="utf-8")
        self.root = tk.Tk()
        self.addCleanup(force_root_release, [self.root],
                        ((self, "root"), (self, "window"), (self, "app")))

    def _app(self, state_home=None):
        return MasterApp(self.folder,
                         state_home=state_home or self.state_home,
                         poll_ms=50, lister=_FakeLister(),
                         plan_compiler=lambda e, n:
                         {"title": "T", "relative_path": e.relative_path})

    def _window(self, app):
        return MasterWindow(self.root, app)

    def _header_buttons(self, window):
        widgets = _all_widgets(window._waiting_frame)
        return {str(w.cget("text")): w
                for w in widgets if isinstance(w, tk.Button)}

    def test_the_waiting_header_offers_state_folder_and_debug_log(self):
        window = self._window(self._app())
        buttons = self._header_buttons(window)
        self.assertIn("State folder\u2026", buttons)
        self.assertIn("Debug log\u2026", buttons)
        # A Python callable command is registered under a Tcl name that
        # carries the method name (the registration id is not stable).
        self.assertTrue(str(buttons["State folder\u2026"].cget("command"))
                        .endswith("_open_state_folder"))
        self.assertTrue(str(buttons["Debug log\u2026"].cget("command"))
                        .endswith("_open_debug_log"))

    def test_open_state_folder_uses_the_platform_opener(self):
        window = self._window(self._app())
        opened = []
        with patch.object(state_access, "choose_opener",
                          return_value=opened.append):
            window._open_state_folder()
        self.assertEqual(opened, [str(self.state_home)])
        self.assertIn("State folder opened:", window._status_var.get())

    def test_a_missing_state_folder_is_a_named_refusal(self):
        app = self._app(state_home=self.state_home / "never-created")
        window = self._window(app)
        opened = []
        with patch.object(state_access, "choose_opener",
                          return_value=opened.append):
            window._open_state_folder()
        self.assertEqual(opened, [])
        self.assertIn("state-folder-missing", window._status_var.get())

    def test_open_debug_log_opens_the_default_log_path(self):
        window = self._window(self._app())
        log = Path(self.temporary.name) / "ct2debug.log"
        log.write_text("log line\n", encoding="utf-8")
        opened = []
        with patch("ct2trainer.native.debug_log.default_log_path",
                   return_value=log), \
                patch.object(state_access, "choose_opener",
                             return_value=opened.append):
            window._open_debug_log()
        self.assertEqual(opened, [str(log)])
        self.assertIn("Debug log opened:", window._status_var.get())

    def test_a_missing_debug_log_is_a_named_refusal(self):
        window = self._window(self._app())
        missing = Path(self.temporary.name) / "nope.ct2debug.log"
        opened = []
        with patch("ct2trainer.native.debug_log.default_log_path",
                   return_value=missing), \
                patch.object(state_access, "choose_opener",
                             return_value=opened.append):
            window._open_debug_log()
        self.assertEqual(opened, [])
        self.assertIn("debug-log-missing", window._status_var.get())

    def test_an_opener_failure_lands_in_the_status_line(self):
        window = self._window(self._app())
        with patch.object(state_access, "choose_opener",
                          return_value=lambda p: (_ for _ in ()).throw(
                              OSError("no desktop"))):
            window._open_state_folder()
        self.assertIn("opener-failed", window._status_var.get())
        self.assertIn("OSError", window._status_var.get())


if __name__ == "__main__":
    unittest.main()
