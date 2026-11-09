"""Master Trainer 0.25 user control wiring (MT-10/11/12).

Covers the Tk wiring on top of the pure layers: the master-state
preferences loaded at start (last explicit table, attach mode) and
their persistence (set_attach_mode / remember_last_table), the waiting
view affordances (Load table header button, row context menu binding,
the attach-mode toggle button), the explicit table load flow (loads
even while the bound process is not running; named refusals land in
the status line + dialog), the process picker flows (ask-mode
auto-load, explicit load, cancel semantics per origin) and the
detach/attach handler wiring (pause + reattach on detach; ask-mode
process picker / plain resume on attach).

``TrainerEngine`` / ``TrainerWindow`` / ``messagebox`` are patched for
the full-flow tests (the same pattern as ``test_native_master_ui.py``);
no real process is attached.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

try:
    import tkinter as tk
except ImportError:  # pragma: no cover - environment without Tcl/Tk
    tk = None

from test_native_master_ui import (
    CT_GAMEA,
    _FakeLister,
    _all_widgets,
    _buttons,
    _button_texts,
)
from native_tk_teardown import force_root_release

from ct2trainer.native.master_trainer.master_ui import (MasterApp,
                                                        MasterWindow)
from ct2trainer.native.master_trainer.master_state import (
    ATTACH_MODE_ASK,
    ATTACH_MODE_AUTO,
    MASTER_STATE_FILENAME,
    MASTER_STATE_SCHEMA,
    MasterState,
    load_master_state,
    save_master_state,
)
from ct2trainer.native.master_trainer.orchestrator import (
    STATE_ACTIVE,
    STATE_WAITING,
)
from ct2trainer.native.master_trainer.process_watch import ProcessSnapshotEntry


@unittest.skipIf(tk is None, "tkinter not available")
class MasterPreferencesTests(unittest.TestCase):
    """MasterApp loads/persists the MT-10/11 preferences (no Tk needed)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(self._rmtree)
        self.folder = self.tmp / "tables"
        self.folder.mkdir()
        self.state_home = self.tmp / "state"
        self.state_home.mkdir()
        (self.folder / "a.ct").write_text(CT_GAMEA, encoding="utf-8")

    def _rmtree(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _state_path(self):
        return self.state_home / MASTER_STATE_FILENAME

    def test_defaults_without_a_stored_state(self):
        app = MasterApp(self.folder, state_home=self.state_home,
                        poll_ms=50, lister=_FakeLister(),
                        plan_compiler=lambda e, n: {})
        self.assertIsNone(app.last_table)
        self.assertEqual(app.attach_mode, ATTACH_MODE_AUTO)

    def test_stored_preferences_are_loaded(self):
        save_master_state(
            MasterState(MASTER_STATE_SCHEMA, str(self.folder),
                        last_table="a.ct", attach_mode=ATTACH_MODE_ASK),
            self._state_path())
        app = MasterApp(self.folder, state_home=self.state_home,
                        poll_ms=50, lister=_FakeLister(),
                        plan_compiler=lambda e, n: {})
        self.assertEqual(app.last_table, "a.ct")
        self.assertEqual(app.attach_mode, ATTACH_MODE_ASK)

    def test_set_attach_mode_persists_and_refuses_bogus(self):
        app = MasterApp(self.folder, state_home=self.state_home,
                        poll_ms=50, lister=_FakeLister(),
                        plan_compiler=lambda e, n: {})
        app.set_attach_mode(ATTACH_MODE_ASK)
        self.assertEqual(app.attach_mode, ATTACH_MODE_ASK)
        stored = load_master_state(self._state_path())
        self.assertEqual(stored.attach_mode, ATTACH_MODE_ASK)
        with self.assertRaises(ValueError):
            app.set_attach_mode("sometimes")
        self.assertEqual(app.attach_mode, ATTACH_MODE_ASK)  # unchanged

    def test_remember_last_table_persists(self):
        app = MasterApp(self.folder, state_home=self.state_home,
                        poll_ms=50, lister=_FakeLister(),
                        plan_compiler=lambda e, n: {})
        app.remember_last_table("a.ct")
        self.assertEqual(app.last_table, "a.ct")
        stored = load_master_state(self._state_path())
        self.assertEqual(stored.last_table, "a.ct")
        self.assertEqual(stored.schema, MASTER_STATE_SCHEMA)

    def test_persist_state_writes_all_three_fields(self):
        app = MasterApp(self.folder, state_home=self.state_home,
                        poll_ms=50, lister=_FakeLister(),
                        plan_compiler=lambda e, n: {})
        app.attach_mode = ATTACH_MODE_ASK
        app.last_table = "a.ct"
        app.persist_state()
        stored = load_master_state(self._state_path())
        self.assertEqual(stored.last_folder, app.folder)
        self.assertEqual(stored.last_table, "a.ct")
        self.assertEqual(stored.attach_mode, ATTACH_MODE_ASK)


@unittest.skipIf(tk is None, "tkinter not available")
class WaitingViewAffordanceTests(unittest.TestCase):
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

    def _app(self, entries=()):
        return MasterApp(self.folder, state_home=self.state_home,
                         poll_ms=50, lister=_FakeLister(entries),
                         plan_compiler=lambda e, n:
                         {"title": "T", "relative_path": e.relative_path})

    def _window(self, app):
        # The poll loop is scheduled but never fired (no mainloop); the
        # tests drive _poll manually.
        return MasterWindow(self.root, app)

    def test_waiting_view_carries_the_new_affordances(self):
        window = self._window(self._app())
        texts = _button_texts(self.root)
        self.assertIn("Load table", texts)
        self.assertIn("Attach: auto", texts)
        self.assertNotIn("Attach: ask", texts)
        # The row context menu binding is in place.
        self.assertTrue(str(window._table_tree.bind("<Button-3>")))

    def test_attach_mode_toggle_flips_and_persists(self):
        window = self._window(self._app())
        window._toggle_attach_mode()
        self.assertEqual(window.app.attach_mode, ATTACH_MODE_ASK)
        self.assertEqual(_button_texts(self.root) & {"Attach: ask"},
                         {"Attach: ask"})
        stored = load_master_state(
            self.state_home / MASTER_STATE_FILENAME)
        self.assertEqual(stored.attach_mode, ATTACH_MODE_ASK)
        # The meta line shows the mode.
        self.assertIn("attach mode: ask",
                      str(window._meta_label.cget("text")))
        # Toggling back restores auto.
        window._toggle_attach_mode()
        self.assertEqual(window.app.attach_mode, ATTACH_MODE_AUTO)


@unittest.skipIf(tk is None, "tkinter not available")
class ExplicitLoadUiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.folder = root / "tables"
        self.folder.mkdir()
        self.state_home = root / "state"
        self.state_home.mkdir()
        (self.folder / "a.ct").write_text(CT_GAMEA, encoding="utf-8")
        (self.folder / "broken.ct").write_text("not a table",
                                               encoding="utf-8")
        self.root = tk.Tk()
        self.addCleanup(force_root_release, [self.root],
                        ((self, "root"), (self, "window"), (self, "app")))
        self.app = self._app()
        self.window = MasterWindow(self.root, self.app)

    def _app(self):
        return MasterApp(self.folder, state_home=self.state_home,
                         poll_ms=50, lister=_FakeLister(),
                         plan_compiler=lambda e, n:
                         {"title": "T", "relative_path": e.relative_path})

    def test_explicit_load_without_running_process_enters_trainer(self):
        with patch("ct2trainer.native.master_trainer.master_ui"
                   ".TrainerEngine") as engine_cls, \
                patch("ct2trainer.native.master_trainer.master_ui"
                      ".TrainerWindow") as window_cls:
            self.window._load_selected_table("a.ct")
        self.assertIs(self.window.engine, engine_cls.return_value)
        self.assertEqual(self.app.orchestrator.state, STATE_ACTIVE)
        # The explicit load is remembered and persisted.
        self.assertEqual(self.app.last_table, "a.ct")
        stored = load_master_state(self.state_home / MASTER_STATE_FILENAME)
        self.assertEqual(stored.last_table, "a.ct")
        # The session pin starts un-pinned (the engine waits).
        self.assertEqual(self.window._attach_pin, {"pid": None})

    def test_explicit_load_refusal_not_in_index(self):
        with patch("ct2trainer.native.master_trainer.master_ui"
                   ".messagebox") as box:
            self.window._load_selected_table("missing.ct")
        self.assertIn("not part of the index",
                      str(box.showerror.call_args))
        self.assertIn("Explicit load refused",
                      str(self.window._status_var.get()))
        self.assertIsNone(self.window.engine)
        self.assertEqual(self.app.orchestrator.state, STATE_WAITING)

    def test_explicit_load_refusal_unreadable_table(self):
        with patch("ct2trainer.native.master_trainer.master_ui"
                   ".messagebox") as box:
            self.window._load_selected_table("broken.ct")
        self.assertIn("unreadable", str(box.showerror.call_args))
        self.assertIsNone(self.window.engine)

    def test_table_load_picker_lists_only_ok_tables(self):
        self.window._open_table_load_picker()
        self.assertIsNotNone(self.window._table_load_picker)
        listbox = self.window._table_load_listbox
        items = [listbox.get(i) for i in range(listbox.size())]
        self.assertEqual(items, ["a.ct"])  # broken.ct is unreadable
        self.window._close_table_load_picker()
        self.assertIsNone(self.window._table_load_picker)

    def test_table_load_picker_no_ok_tables_warns(self):
        self.app.index.indexes[0].entries = {rel: e for rel, e in
                                  self.app.index.entries.items()
                                  if e.status != "ok"}
        with patch("ct2trainer.native.master_trainer.master_ui"
                   ".messagebox") as box:
            self.window._open_table_load_picker()
        box.showwarning.assert_called_once()
        self.assertIsNone(self.window._table_load_picker)


@unittest.skipIf(tk is None, "tkinter not available")
class ProcessPickerUiTests(unittest.TestCase):
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
        self.process = ProcessSnapshotEntry(7, "GameA.exe")

    def _app(self, mode=ATTACH_MODE_AUTO):
        app = MasterApp(self.folder, state_home=self.state_home,
                        poll_ms=50,
                        lister=_FakeLister([self.process]),
                        plan_compiler=lambda e, n:
                        {"title": "T", "relative_path": e.relative_path})
        app.attach_mode = mode
        return app

    def _window(self, app):
        return MasterWindow(self.root, app)

    def test_ask_mode_auto_load_opens_the_process_picker(self):
        app = self._app(ATTACH_MODE_ASK)
        window = self._window(app)
        window._poll()
        self.assertIsNotNone(window._proc_picker)
        listbox = window._proc_picker_listbox
        self.assertEqual(listbox.get(0), "GameA.exe  (PID 7)")
        self.assertEqual(window._proc_picker_origin, "auto-load")
        # No load happened while the picker is open.
        self.assertIsNone(window.engine)
        self.assertEqual(app.orchestrator.state, STATE_WAITING)
        window._close_proc_picker()

    def test_ask_mode_picker_choice_loads_and_pins(self):
        app = self._app(ATTACH_MODE_ASK)
        window = self._window(app)
        window._poll()
        self.assertIsNotNone(window._proc_picker)
        with patch("ct2trainer.native.master_trainer.master_ui"
                   ".TrainerEngine") as engine_cls, \
                patch("ct2trainer.native.master_trainer.master_ui"
                      ".TrainerWindow"):
            window._proc_picker_chosen(0)
        self.assertEqual(window._attach_pin, {"pid": 7})
        self.assertIs(window.engine, engine_cls.return_value)
        self.assertEqual(app.orchestrator.state, STATE_ACTIVE)

    def test_ask_mode_picker_cancel_defers_the_auto_load(self):
        app = self._app(ATTACH_MODE_ASK)
        window = self._window(app)
        window._poll()
        self.assertIsNotNone(window._proc_picker)
        window._proc_picker_cancel()
        self.assertIsNone(window._proc_picker)
        self.assertIsNone(window.engine)
        self.assertIn("Process choice deferred",
                      str(window._status_var.get()))
        # The next tick is deferred for the exact pair (loop guard).
        window._poll()
        self.assertIn("auto-load deferred",
                      str(window._status_var.get()))

    def test_auto_mode_auto_loads_without_a_picker(self):
        app = self._app(ATTACH_MODE_AUTO)
        window = self._window(app)
        with patch("ct2trainer.native.master_trainer.master_ui"
                   ".TrainerEngine") as engine_cls, \
                patch("ct2trainer.native.master_trainer.master_ui"
                      ".TrainerWindow"):
            window._poll()
        self.assertIsNone(window._proc_picker)
        self.assertEqual(app.orchestrator.state, STATE_ACTIVE)
        self.assertEqual(window._attach_pin, {"pid": 7})


@unittest.skipIf(tk is None, "tkinter not available")
class DetachAttachUiTests(unittest.TestCase):
    """The MT-12 header handler: detach / attach routing (mock engine)."""

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

    def _window(self, mode=ATTACH_MODE_AUTO, running=()):
        app = MasterApp(self.folder, state_home=self.state_home,
                        poll_ms=50,
                        lister=_FakeLister(running),
                        plan_compiler=lambda e, n: {})
        app.attach_mode = mode
        return MasterWindow(self.root, app)

    def test_no_engine_is_a_noop(self):
        window = self._window()
        window._detach_or_attach()
        self.assertIsNone(window.engine)

    def test_detach_pauses_and_reattaches(self):
        window = self._window()
        engine = MagicMock()
        engine.memory = object()
        window.engine = engine
        window._detach_or_attach()
        engine.pause_attach.assert_called_once_with()
        engine.reattach.assert_called_once_with()

    def test_detach_pause_failure_shows_error(self):
        window = self._window()
        engine = MagicMock()
        engine.memory = object()
        engine.pause_attach.side_effect = RuntimeError("busy")
        window.engine = engine
        with patch("ct2trainer.native.master_trainer.master_ui"
                   ".messagebox") as box:
            window._detach_or_attach()
        box.showerror.assert_called_once()
        engine.reattach.assert_not_called()

    def test_attach_auto_mode_resumes(self):
        window = self._window(ATTACH_MODE_AUTO)
        engine = MagicMock()
        engine.memory = None
        engine.attach_paused = True
        window.engine = engine
        window._detach_or_attach()
        engine.resume_attach.assert_called_once_with()
        self.assertIsNone(window._proc_picker)

    def test_attach_target_exit_detach_is_a_noop(self):
        # Detached by the target exit, not by the user: the ordinary
        # wait already runs; nothing to resume, no picker.
        window = self._window(ATTACH_MODE_ASK)
        engine = MagicMock()
        engine.memory = None
        engine.attach_paused = False
        window.engine = engine
        window._detach_or_attach()
        engine.resume_attach.assert_not_called()
        self.assertIsNone(window._proc_picker)

    def test_attach_ask_mode_with_candidates_opens_the_picker(self):
        window = self._window(ATTACH_MODE_ASK,
                              running=[ProcessSnapshotEntry(7, "GameA.exe")])
        engine = MagicMock()
        engine.memory = None
        engine.attach_paused = True
        engine.plan = {"process_name": "GameA.exe"}
        window.engine = engine
        window._detach_or_attach()
        self.assertIsNotNone(window._proc_picker)
        self.assertEqual(window._proc_picker_origin, "attach")
        engine.resume_attach.assert_not_called()
        # Choosing the candidate pins it and resumes the hold.
        window._proc_picker_chosen(0)
        self.assertEqual(window._attach_pin, {"pid": 7})
        engine.resume_attach.assert_called_once_with()

    def test_attach_ask_mode_picker_cancel_stays_detached(self):
        window = self._window(ATTACH_MODE_ASK,
                              running=[ProcessSnapshotEntry(7, "GameA.exe")])
        engine = MagicMock()
        engine.memory = None
        engine.attach_paused = True
        engine.plan = {"process_name": "GameA.exe"}
        window.engine = engine
        window._detach_or_attach()
        self.assertIsNotNone(window._proc_picker)
        window._proc_picker_cancel()
        self.assertIsNone(window._proc_picker)
        engine.resume_attach.assert_not_called()

    def test_lifecycle_cleanup_closes_the_proc_picker(self):
        # The "⬅ Master" transition and window close both drop the
        # process picker (it is a child of the root that gets rebuilt /
        # destroyed).
        window = self._window(ATTACH_MODE_ASK,
                              running=[ProcessSnapshotEntry(7, "GameA.exe")])
        engine = MagicMock()
        engine.memory = None
        engine.attach_paused = True
        engine.plan = {"process_name": "GameA.exe"}
        window.engine = engine
        window._detach_or_attach()
        self.assertIsNotNone(window._proc_picker)
        window._close_proc_picker()
        self.assertIsNone(window._proc_picker)


if __name__ == "__main__":
    unittest.main()
