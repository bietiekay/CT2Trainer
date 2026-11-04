"""Master Trainer 0.29: trainer-focus mode (MT-19) + discoverability (MT-20).

Covers the Tk wiring on top of the unchanged pure layers: entering the
trainer collapses the whole waiting view into a single container frame
that is destroyed on trainer entry (the trainer row grid then owns the
full window instead of sharing it with the table list) and rebuilt
whole on the way back; a trainer-view constructor failure restores the
waiting view before failing the load so the waiting loop stays
consistent.  MT-20 adds the read-only "UI flow" header button (the
in-app copy of the reviewable UI.md, single Toplevel, lifted on a
second click), the F5 re-scan shortcut (waiting mode only), the initial
table-list focus (arrow keys / Enter work immediately) and the
"Retry load" re-arm living in the status bar.  No real process is
attached (a _FakeLister stands in; TrainerEngine / TrainerWindow are
patched for the full-flow tests).
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:  # pragma: no cover - environment without Tcl/Tk
    tk = None
    ttk = None

from test_native_master_ui import (CT_GAMEA, _FakeLister, _all_widgets,
                                    _button_texts, _buttons, _make_app)

from native_tk_teardown import force_root_release

from ct2trainer.native.master_trainer.orchestrator import (STATE_ACTIVE,
                                                           STATE_WAITING)
from ct2trainer.native.master_trainer.process_watch import (
    ProcessSnapshotEntry)
from ct2trainer.native.master_trainer.master_ui import (MasterApp,
                                                        MasterWindow,
                                                        ui_flow_text)


def _is_inside(container, widget) -> bool:
    """True when ``container`` is ``widget`` or one of its ancestors."""
    node = widget
    while node is not None:
        if node is container:
            return True
        node = node.master
    return False


class _TrainerFocusBase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.folder = root / "tables"
        self.folder.mkdir()
        self.state_home = root / "state"
        self.state_home.mkdir()
        (self.folder / "zeta.ct").write_text(CT_GAMEA, encoding="utf-8")
        self.process = ProcessSnapshotEntry(7, "GameA.exe")
        self.root = tk.Tk()
        self.addCleanup(force_root_release, [self.root],
                        ((self, "root"), (self, "window"), (self, "app")))

    def _app(self):
        return _make_app(self.folder, self.state_home, [self.process])

    def _window(self, app):
        return MasterWindow(self.root, app)

    def _mock_engine(self):
        engine = MagicMock()
        engine.close.return_value = True
        return engine

    def _mock_trainer_engine(self):
        """The shape of the standalone engine the trainer view reads."""
        e = MagicMock()
        e.entries = {}
        e.status = "idle"
        e.plan = {"title": "T", "process_name": "GameA.exe",
                  "table_sha256": "ab" * 32}
        e.applied = set()
        e.desired = set()
        e.frozen = set()
        e.entry_errors = {}
        e.memory = None
        e.hotkey_warnings = []
        e.closed = False
        e.connected = False
        e.blocked = False
        return e


@unittest.skipIf(tk is None, "tkinter not available")
class WaitingContainerTests(_TrainerFocusBase):
    """MT-19 (0.29): the waiting view is one container the trainer takes."""

    def test_waiting_widgets_live_in_the_container(self):
        app = self._app()
        window = self._window(app)
        frame = window._waiting_frame
        self.assertIsNotNone(frame)
        self.assertEqual(str(frame.master), str(self.root))
        for widget in (window._folder_label, window._meta_label,
                       window._running_label, window._table_tree,
                       window._filter_entry, window._sort_btn,
                       window._view_btn, window._attach_mode_btn,
                       window._retry_btn):
            self.assertIsNotNone(widget, "widget not built")
            self.assertTrue(_is_inside(frame, widget),
                            "widget outside the container: " + str(widget))
        # The header + the Retry load control sit inside the container too.
        self.assertIn("Retry load", _button_texts(frame))
        self.assertIn("UI flow", _button_texts(frame))

    def test_retry_load_lives_in_the_status_bar(self):
        # The re-arm no longer hangs on the root below the status strip;
        # it is a child of the status frame (inside the container).
        app = self._app()
        window = self._window(app)
        retry = _buttons(window._waiting_frame, "Retry load")
        self.assertEqual(len(retry), 1)
        self.assertNotEqual(str(retry[0].master), str(self.root))

    def test_enter_trainer_collapses_the_waiting_view(self):
        app = self._app()
        window = self._window(app)
        first_frame = window._waiting_frame
        engine = self._mock_engine()
        entry = app.index.entries_for_process("GameA.exe")[0]
        with patch("ct2trainer.native.master_trainer.master_ui.TrainerEngine",
                   return_value=engine) as engine_cls, \
                patch("ct2trainer.native.master_trainer.master_ui"
                      ".TrainerWindow") as window_cls, \
                patch("ct2trainer.native.master_trainer.master_ui.messagebox"):
            window._start_load(entry, self.process)
        engine_cls.assert_called_once()
        window_cls.assert_called_once()
        # The container is gone and the widget references are dropped so
        # the poll loop never touches a destroyed widget.
        self.assertFalse(first_frame.winfo_exists())
        self.assertIsNone(window._waiting_frame)
        self.assertIsNone(window._table_tree)
        self.assertIsNone(window._folder_label)
        self.assertIsNone(window._status_var)
        self.assertIsNone(window._retry_btn)
        # The trainer took over: engine + trainer window are live and the
        # orchestrator is active.
        self.assertIs(window.engine, engine)
        self.assertIsNotNone(window.trainer_window)
        self.assertEqual(app.orchestrator.state, STATE_ACTIVE)
        # The destroyed container is no longer a root child.
        self.assertNotIn(str(first_frame),
                         [str(w) for w in self.root.winfo_children()])

    def test_trainer_constructor_failure_rebuilds_the_waiting_view(self):
        # The engine is up but the trainer view could not be built: the
        # engine is closed, the waiting view (torn down for trainer
        # entry) is restored and the load fails so the waiting loop and
        # its loop guard stay consistent.
        app = self._app()
        window = self._window(app)
        first_frame = window._waiting_frame
        engine = self._mock_engine()
        entry = app.index.entries_for_process("GameA.exe")[0]
        with patch("ct2trainer.native.master_trainer.master_ui.TrainerEngine",
                   return_value=engine) as engine_cls, \
                patch("ct2trainer.native.master_trainer.master_ui"
                      ".TrainerWindow",
                      side_effect=RuntimeError("no canvas")) as window_cls, \
                patch("ct2trainer.native.master_trainer.master_ui"
                      ".messagebox") as box:
            window._start_load(entry, self.process)
        window_cls.assert_called_once()
        engine.close.assert_called_once()
        box.showerror.assert_called_once()
        self.assertIn("Trainer cannot start", str(box.showerror.call_args))
        # Back in waiting mode with a fresh container.
        self.assertIsNone(window.engine)
        self.assertIsNone(window.trainer_window)
        self.assertFalse(first_frame.winfo_exists())
        self.assertIsNotNone(window._waiting_frame)
        self.assertIsNot(window._waiting_frame, first_frame)
        self.assertIsNotNone(window._table_tree)
        self.assertEqual(app.orchestrator.state, STATE_WAITING)
        self.assertIn("Trainer start failed", window._status_var.get())

    def test_back_to_master_rebuilds_a_fresh_waiting_frame(self):
        app = self._app()
        window = self._window(app)
        first_frame = window._waiting_frame
        engine = self._mock_engine()
        entry = app.index.entries_for_process("GameA.exe")[0]
        with patch("ct2trainer.native.master_trainer.master_ui.TrainerEngine",
                   return_value=engine), \
                patch("ct2trainer.native.master_trainer.master_ui"
                      ".TrainerWindow"), \
                patch("ct2trainer.native.master_trainer.master_ui.messagebox"):
            window._start_load(entry, self.process)
        self.assertIsNone(window._waiting_frame)
        window._back_to_master()
        engine.close.assert_called_once()
        self.assertIsNone(window.engine)
        self.assertEqual(app.orchestrator.state, STATE_WAITING)
        self.assertFalse(first_frame.winfo_exists())
        self.assertIsNotNone(window._waiting_frame)
        self.assertIsNot(window._waiting_frame, first_frame)
        self.assertIsNotNone(window._table_tree)
        self.assertEqual(window._status_var.get(), "Back to Master wait mode.")

    def test_real_trainer_window_owns_the_root_after_teardown(self):
        # One real TrainerWindow on the shared root: after the teardown
        # the trainer grid (with its "⬅ Master" button) owns the window
        # and the waiting container is gone.
        from ct2trainer.native.ui import TrainerWindow
        engine = self._mock_trainer_engine()
        app = self._app()
        window = self._window(app)
        first_frame = window._waiting_frame
        window.engine = engine
        window._teardown_waiting_view()
        self.assertFalse(first_frame.winfo_exists())
        trainer = TrainerWindow(self.root, engine,
                                master_back=window._back_to_master,
                                detach_cb=window._detach_or_attach)
        self.assertIn("\u2b05 Master", _button_texts(trainer.header))
        self.assertIsNone(window._waiting_frame)
        self.assertNotIn(str(first_frame),
                         [str(w) for w in self.root.winfo_children()])


@unittest.skipIf(tk is None, "tkinter not available")
class DiscoverabilityTests(_TrainerFocusBase):
    """MT-20 (0.29): the in-app UI-flow reference + keyboard discoverability."""

    def test_ui_flow_text_is_the_reviewable_document(self):
        text = ui_flow_text()
        self.assertIsInstance(text, str)
        for section in ("WAITING MODE", "LOADING A TABLE", "TRAINER MODE",
                        "BACK TO MASTER", "WHAT IS REMEMBERED",
                        "FAILURE STATES"):
            self.assertIn(section, text)
        # The MT-19 / MT-20 additions are named in the flow.
        self.assertIn("UI flow", text)
        self.assertIn("Retry load", text)
        self.assertIn("F5", text)
        self.assertIn("collapses", text)

    def test_ui_flow_button_opens_a_read_only_toplevel(self):
        app = self._app()
        window = self._window(app)
        window._open_ui_flow()
        win = window._ui_flow_win
        self.assertIsNotNone(win)
        self.assertTrue(win.winfo_exists())
        self.addCleanup(win.destroy)
        # A read-only Text widget carrying the flow document.
        texts = [w for w in _all_widgets(win) if isinstance(w, tk.Text)]
        self.assertEqual(len(texts), 1)
        content = texts[0].get("1.0", "end")
        self.assertIn("WAITING MODE", content)
        self.assertEqual(texts[0].cget("state"), "disabled")

    def test_ui_flow_button_lifts_the_existing_window(self):
        app = self._app()
        window = self._window(app)
        window._open_ui_flow()
        first = window._ui_flow_win
        window._open_ui_flow()
        # A second click lifts the open window, never opens a duplicate.
        self.assertIs(first, window._ui_flow_win)
        self.assertTrue(first.winfo_exists())
        self.addCleanup(first.destroy)

    def test_ui_flow_window_closes_on_trainer_entry(self):
        app = self._app()
        window = self._window(app)
        window._open_ui_flow()
        win = window._ui_flow_win
        self.assertTrue(win.winfo_exists())
        engine = self._mock_engine()
        entry = app.index.entries_for_process("GameA.exe")[0]
        with patch("ct2trainer.native.master_trainer.master_ui.TrainerEngine",
                   return_value=engine), \
                patch("ct2trainer.native.master_trainer.master_ui"
                      ".TrainerWindow"), \
                patch("ct2trainer.native.master_trainer.master_ui.messagebox"):
            window._start_load(entry, self.process)
        self.assertFalse(win.winfo_exists())
        self.assertIsNone(window._ui_flow_win)

    def test_f5_is_bound_to_the_root(self):
        app = self._app()
        window = self._window(app)
        self.assertTrue(self.root.bind("<F5>"))

    def test_f5_rescans_in_waiting_mode_only(self):
        app = self._app()
        window = self._window(app)
        with patch.object(window, "_rescan") as rescan:
            window._on_f5(None)
            rescan.assert_called_once()
            # In trainer mode the keys belong to the trainer UI.
            window.engine = self._mock_engine()
            window._on_f5(None)
            rescan.assert_called_once()

    def test_initial_focus_is_on_the_table_tree(self):
        # The build requests focus for the table tree (arrow keys /
        # Enter work immediately without a first click).  Spy on
        # focus_set rather than pumping the event loop, which can block
        # in a headless test environment.
        app = self._app()
        calls = []
        original = ttk.Treeview.focus_set

        def spy(instance):
            calls.append(instance)
            return original(instance)

        with patch.object(ttk.Treeview, "focus_set", spy, create=True):
            window = self._window(app)
        self.assertEqual(calls, [window._table_tree])
