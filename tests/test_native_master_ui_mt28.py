"""Master Trainer 0.37: per-table process binding wiring (MT-28).

Covers the Tk wiring on top of the pure ``table_attach`` layer: the
``MasterApp.attach_store`` sidecar (fresh home empty), the process
picker's remembered-branch preselect (``ask`` mode still opens the
picker - the documented contract - with the remembered row
preselected), the persistence of an explicit process choice
(``_proc_picker_chosen`` for every origin: auto-load, explicit,
choice, attach - the attach origin addresses the loaded table through
the sidecar sha), the remembered-choice honouring in ``auto`` mode
(live binding outranks the documented smallest-PID rule; a stale or
missing binding keeps the pre-0.37 behavior), and the "Remembered
process" row of the MT-22 table-details window.

``TrainerEngine`` / ``TrainerWindow`` / ``messagebox`` are patched for
the full-flow tests (the same pattern as ``test_native_master_ui_mt12.py``);
no real process is attached.
"""
from __future__ import annotations

import hashlib
import tempfile
import types
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
)
from native_tk_teardown import force_root_release

from ct2trainer.native.master_trainer.master_ui import (MasterApp,
                                                         MasterWindow)
from ct2trainer.native.master_trainer.master_state import (
    ATTACH_MODE_ASK,
    ATTACH_MODE_AUTO,
)
from ct2trainer.native.master_trainer.orchestrator import (
    STATE_ACTIVE,
    STATE_WAITING,
)
from ct2trainer.native.master_trainer.process_watch import ProcessSnapshotEntry
from ct2trainer.native.master_trainer.table_attach import (
    ATTACH_SCHEMA,
    AttachStore,
    _timestamp_ok,
)

def _cand(pid):
    return ProcessSnapshotEntry(pid, "GameA.exe")


@unittest.skipIf(tk is None, "tkinter not available")
class AttachStoreWiringTests(unittest.TestCase):
    """MasterApp owns the per-table process-binding sidecar."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.folder = root / "tables"
        self.folder.mkdir()
        self.state_home = root / "state"
        self.state_home.mkdir()
        (self.folder / "a.ct").write_text(CT_GAMEA, encoding="utf-8")
        # The index keys by the content sha of the on-disk bytes (the
        # platform line endings write_text applies), so compute the
        # key from the file, not from the source string.
        self.table_sha = hashlib.sha256(
            (self.folder / "a.ct").read_bytes()).hexdigest()

    def _app(self, mode=ATTACH_MODE_AUTO, running=()):
        return MasterApp(self.folder, state_home=self.state_home,
                         poll_ms=50, lister=_FakeLister(running),
                         plan_compiler=lambda e, n:
                         {"title": "T", "relative_path": e.relative_path})

    def test_app_has_attach_store_fresh_home_empty(self):
        app = self._app()
        self.assertIsInstance(app.attach_store, AttachStore)
        self.assertEqual(app.attach_store.document(),
                         {"schema": ATTACH_SCHEMA, "tables": {}})
        self.assertIsNone(app.attach_store.get(self.table_sha))

    def test_binding_survives_a_new_app_over_the_same_home(self):
        app = self._app()
        app.attach_store.set_binding(self.table_sha, "GameA.exe", 9)
        other = self._app()
        self.assertEqual(other.attach_store.get(self.table_sha)["pid"], 9)


@unittest.skipIf(tk is None, "tkinter not available")
class AttachBindingUiTests(unittest.TestCase):
    """The remembered process choice through the waiting-view flows."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.folder = root / "tables"
        self.folder.mkdir()
        self.state_home = root / "state"
        self.state_home.mkdir()
        (self.folder / "a.ct").write_text(CT_GAMEA, encoding="utf-8")
        self.table_sha = hashlib.sha256(
            (self.folder / "a.ct").read_bytes()).hexdigest()
        self.root = tk.Tk()
        self.addCleanup(force_root_release, [self.root],
                        ((self, "root"), (self, "window"), (self, "app")))

    def _app(self, mode, running):
        app = MasterApp(self.folder, state_home=self.state_home,
                        poll_ms=50, lister=_FakeLister(running),
                        plan_compiler=lambda e, n:
                        {"title": "T", "relative_path": e.relative_path})
        app.attach_mode = mode
        return app

    def _window(self, mode, running):
        return MasterWindow(self.root, self._app(mode, running))

    def test_ask_mode_picker_preselects_remembered_pid(self):
        window = self._window(ATTACH_MODE_ASK, [_cand(7), _cand(9)])
        window.app.attach_store.set_binding(self.table_sha, "GameA.exe", 9)
        window._poll()
        self.assertIsNotNone(window._proc_picker)
        self.assertEqual(window._proc_picker_origin, "auto-load")
        listbox = window._proc_picker_listbox
        self.assertEqual(listbox.get(0), "GameA.exe  (PID 7)")
        self.assertEqual(listbox.get(1), "GameA.exe  (PID 9)")
        # The remembered row (PID 9) is preselected - the picker still
        # opened (the documented 'ask' contract).
        self.assertEqual(listbox.curselection(), (1,))
        # No load happened while the picker is open.
        self.assertIsNone(window.engine)
        self.assertEqual(window.app.orchestrator.state, STATE_WAITING)
        window._close_proc_picker()

    def test_ask_mode_picker_preselects_first_without_binding(self):
        window = self._window(ATTACH_MODE_ASK, [_cand(7), _cand(9)])
        window._poll()
        self.assertIsNotNone(window._proc_picker)
        # Pre-0.37 behavior: the first candidate is preselected.
        self.assertEqual(window._proc_picker_listbox.curselection(), (0,))
        window._close_proc_picker()

    def test_ask_mode_stale_binding_preselects_first(self):
        # The remembered PID (9) is not running anymore: the picker
        # still opens, the first live candidate is preselected.
        window = self._window(ATTACH_MODE_ASK, [_cand(7)])
        window.app.attach_store.set_binding(self.table_sha, "GameA.exe", 9)
        window._poll()
        self.assertIsNotNone(window._proc_picker)
        self.assertEqual(window._proc_picker_listbox.curselection(), (0,))
        window._close_proc_picker()

    def test_proc_picker_chosen_persists_the_binding(self):
        window = self._window(ATTACH_MODE_ASK, [_cand(7)])
        window._poll()
        self.assertIsNotNone(window._proc_picker)
        with patch("ct2trainer.native.master_trainer.master_ui"
                    ".TrainerEngine") as engine_cls, \
                patch("ct2trainer.native.master_trainer.master_ui"
                      ".TrainerWindow"):
            window._proc_picker_chosen(0)
        binding = window.app.attach_store.get(self.table_sha)
        self.assertEqual(binding["process"], "GameA.exe")
        self.assertEqual(binding["pid"], 7)
        self.assertTrue(_timestamp_ok(binding["updated_at"]))
        # The ordinary session pin + the load still happen.
        self.assertEqual(window._attach_pin, {"pid": 7})
        self.assertIs(window.engine, engine_cls.return_value)
        self.assertEqual(window.app.orchestrator.state, STATE_ACTIVE)

    def test_auto_mode_honours_live_binding_over_smallest_pid(self):
        window = self._window(ATTACH_MODE_AUTO, [_cand(7), _cand(9)])
        window.app.attach_store.set_binding(self.table_sha, "GameA.exe", 9)
        with patch("ct2trainer.native.master_trainer.master_ui"
                    ".TrainerEngine") as engine_cls, \
                patch("ct2trainer.native.master_trainer.master_ui"
                      ".TrainerWindow"):
            window._poll()
        # The remembered PID (9) outranks the documented smallest-PID
        # rule (7) - no picker in auto mode.
        self.assertIsNone(window._proc_picker)
        self.assertEqual(window._attach_pin, {"pid": 9})
        self.assertIs(window.engine, engine_cls.return_value)
        self.assertEqual(window.app.orchestrator.state, STATE_ACTIVE)

    def test_auto_mode_stale_binding_keeps_smallest_pid(self):
        # The remembered PID (7) exited; the live smallest-PID rule
        # applies (the only candidate is 9).
        window = self._window(ATTACH_MODE_AUTO, [_cand(9)])
        window.app.attach_store.set_binding(self.table_sha, "GameA.exe", 7)
        with patch("ct2trainer.native.master_trainer.master_ui"
                    ".TrainerEngine"), \
                patch("ct2trainer.native.master_trainer.master_ui"
                      ".TrainerWindow"):
            window._poll()
        self.assertEqual(window._attach_pin, {"pid": 9})

    def test_auto_mode_without_binding_keeps_smallest_pid(self):
        window = self._window(ATTACH_MODE_AUTO, [_cand(7), _cand(9)])
        with patch("ct2trainer.native.master_trainer.master_ui"
                    ".TrainerEngine"), \
                patch("ct2trainer.native.master_trainer.master_ui"
                      ".TrainerWindow"):
            window._poll()
        # Pre-0.37 behavior: the documented smallest-PID rule.
        self.assertEqual(window._attach_pin, {"pid": 7})

    def test_explicit_load_auto_mode_honours_binding(self):
        window = self._window(ATTACH_MODE_AUTO, [_cand(7), _cand(9)])
        window.app.attach_store.set_binding(self.table_sha, "GameA.exe", 9)
        with patch("ct2trainer.native.master_trainer.master_ui"
                    ".TrainerEngine") as engine_cls, \
                patch("ct2trainer.native.master_trainer.master_ui"
                      ".TrainerWindow"):
            window._load_selected_table("a.ct")
        self.assertIsNone(window._proc_picker)
        self.assertEqual(window._attach_pin, {"pid": 9})
        self.assertIs(window.engine, engine_cls.return_value)
        self.assertEqual(window.app.orchestrator.state, STATE_ACTIVE)

    def test_explicit_load_ask_mode_preselects(self):
        window = self._window(ATTACH_MODE_ASK, [_cand(7), _cand(9)])
        window.app.attach_store.set_binding(self.table_sha, "GameA.exe", 9)
        window._load_selected_table("a.ct")
        self.assertIsNotNone(window._proc_picker)
        self.assertEqual(window._proc_picker_origin, "explicit")
        self.assertEqual(window._proc_picker_listbox.curselection(), (1,))
        window._close_proc_picker()

    def test_attach_origin_persists_via_sidecar_sha(self):
        window = self._window(ATTACH_MODE_ASK, [_cand(7)])
        engine = MagicMock()
        engine.memory = None
        engine.attach_paused = True
        engine.plan = {"process_name": "GameA.exe"}
        window.engine = engine
        # The trainer entry set the sidecar sha (the attach origin
        # carries no table argument).
        window._sidecar_sha = self.table_sha
        window._detach_or_attach()
        self.assertIsNotNone(window._proc_picker)
        self.assertEqual(window._proc_picker_origin, "attach")
        window._proc_picker_chosen(0)
        self.assertEqual(window.app.attach_store.get(self.table_sha)["pid"], 7)
        engine.resume_attach.assert_called_once_with()

    def test_no_content_sha_persists_nothing(self):
        window = self._window(ATTACH_MODE_ASK, [_cand(7)])
        entry = types.SimpleNamespace(sha256=None, relative_path="a.ct")
        window._remember_attach_choice(entry, _cand(7), "auto-load")
        self.assertEqual(window.app.attach_store.document()["tables"], {})
        # The attach origin without a sidecar sha: likewise nothing.
        window._remember_attach_choice(None, _cand(7), "attach")
        self.assertEqual(window.app.attach_store.document()["tables"], {})


@unittest.skipIf(tk is None, "tkinter not available")
class AttachDetailsUiTests(unittest.TestCase):
    """The MT-22 details window shows the remembered process row."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.folder = root / "tables"
        self.folder.mkdir()
        self.state_home = root / "state"
        self.state_home.mkdir()
        (self.folder / "a.ct").write_text(CT_GAMEA, encoding="utf-8")
        self.table_sha = hashlib.sha256(
            (self.folder / "a.ct").read_bytes()).hexdigest()
        self.root = tk.Tk()
        self.addCleanup(force_root_release, [self.root],
                        ((self, "root"), (self, "window"), (self, "app")))
        app = MasterApp(self.folder, state_home=self.state_home,
                        poll_ms=50, lister=_FakeLister(),
                        plan_compiler=lambda e, n:
                        {"title": "T", "relative_path": e.relative_path})
        self.window = MasterWindow(self.root, app)

    def _detail_texts(self):
        self.window.root.update_idletasks()
        return [w.cget("text") for w in _all_widgets(self.window._details_win)
                if w.winfo_class() == "Label"]

    def test_details_show_the_remembered_process(self):
        self.window.app.attach_store.set_binding(self.table_sha, "GameA.exe", 9)
        self.window._open_table_details("a.ct")
        texts = self._detail_texts()
        self.assertIn("Remembered process", texts)
        self.assertIn("GameA.exe (PID 9)", texts)

    def test_details_show_none_without_a_binding(self):
        self.window._open_table_details("a.ct")
        texts = self._detail_texts()
        self.assertIn("Remembered process", texts)
        self.assertIn("none", texts)


if __name__ == "__main__":
    unittest.main()
