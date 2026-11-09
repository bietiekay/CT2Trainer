"""Master Trainer 0.36: multi-column trainer grid (MT-21).

Covers the persisted trainer grid column count (master-state schema
9, ``grid_columns``): the documented default on a fresh or promoted
state home, the app-level setter (named refusal for a bogus value,
immediate persistence on every change), and the trainer handoff
(the trainer window receives the persisted column count plus the
header cycle callback).  The "Columns: N" header control is present
only when the Master wires the callback - the standalone trainer
header stays byte-identical - the 1 -> 2 -> 3 -> 1 cycle updates the
label, notifies the persistence callback and re-renders, and the
per-column renderer state is verified on the real window (column
offsets / widths, per-column hit-testing, the narrow-window clamp,
the standalone single-column invariant).

``TrainerEngine`` / ``TrainerWindow`` are patched for the full-flow
tests (the same pattern as ``test_native_master_ui.py``); no real
process is attached.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

try:
    import tkinter as tk
except ImportError:  # pragma: no cover - environment without Tcl/Tk
    tk = None

from ct2trainer.native.master_trainer import master_ui
from ct2trainer.native.master_trainer.master_state import (
    ATTACH_MODE_AUTO,
    MASTER_STATE_FILENAME,
    load_master_state,
)
from ct2trainer.native.master_trainer.orchestrator import STATE_ACTIVE
from ct2trainer.native.master_trainer.process_watch import ProcessSnapshotEntry
from ct2trainer.native.ui_rows import column_layout

from native_tk_teardown import force_root_release
from test_native_master_ui import CT_GAMEA, _button_texts, _make_app


class GridColumnsAppTests(unittest.TestCase):
    """The persisted grid column count on the pure ``MasterApp``."""

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

    def _app(self):
        return _make_app(self.folder, self.state_home)

    def test_fresh_state_home_defaults_to_one_column(self):
        self.assertEqual(self._app().grid_columns, 1)

    def test_persisted_grid_columns_loaded_at_start(self):
        app = self._app()
        app.set_grid_columns(3)
        stored = load_master_state(self.state_home / MASTER_STATE_FILENAME)
        self.assertEqual(stored.grid_columns, 3)
        # A fresh app over the same state home restores the preference.
        self.assertEqual(self._app().grid_columns, 3)

    def test_set_grid_columns_persists_immediately(self):
        app = self._app()
        app.set_grid_columns(2)
        stored = load_master_state(self.state_home / MASTER_STATE_FILENAME)
        self.assertEqual(stored.grid_columns, 2)

    def test_set_grid_columns_named_refusals(self):
        app = self._app()
        app.set_grid_columns(3)
        for bad in (0, 4, "2", True, None, [2]):
            with self.assertRaises(ValueError):
                app.set_grid_columns(bad)
        # The refusal neither changed the app state nor the document.
        self.assertEqual(app.grid_columns, 3)
        stored = load_master_state(self.state_home / MASTER_STATE_FILENAME)
        self.assertEqual(stored.grid_columns, 3)

    def test_schema8_document_promotes_with_default_columns(self):
        # A hand-written schema-8 document (the same checksum-bound
        # envelope discipline as master_state_to_bytes) promotes to the
        # current schema with the documented grid_columns default (1).
        payload = {"schema": 8, "last_folder": None, "last_table": None,
                   "attach_mode": ATTACH_MODE_AUTO, "recent_tables": [],
                   "view_filter": "", "view_sort": "name",
                   "view_mode": "list", "pinned_tables": [],
                   "view_status": "", "auto_rescan": True,
                   "table_folders": []}
        canonical = json.dumps(payload, sort_keys=True,
                               separators=(",", ":"), allow_nan=False,
                               ensure_ascii=True).encode("utf-8")
        document = {"payload": payload,
                    "sha256": hashlib.sha256(canonical).hexdigest()}
        (self.state_home / MASTER_STATE_FILENAME).write_bytes(
            json.dumps(document, sort_keys=True, separators=(",", ":"),
                       allow_nan=False, ensure_ascii=True).encode("utf-8"))
        app = self._app()
        self.assertEqual(app.grid_columns, 1)


@unittest.skipUnless(tk is not None, "tkinter required for real widget construction")
class GridColumnsHandoffTests(unittest.TestCase):
    """The trainer handoff carries the persisted column count."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(self._rmtree)
        self.folder = self.tmp / "tables"
        self.folder.mkdir()
        self.state_home = self.tmp / "state"
        self.state_home.mkdir()
        (self.folder / "a.ct").write_text(CT_GAMEA, encoding="utf-8")
        self.root = tk.Tk()
        self.root.withdraw()

    def _rmtree(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def tearDown(self):
        force_root_release([self.root], ((self, "root"),))

    def test_handoff_carries_persisted_columns_and_callback(self):
        app = _make_app(self.folder, self.state_home,
                        [ProcessSnapshotEntry(7, "GameA.exe")])
        window = master_ui.MasterWindow(self.root, app)
        app.set_grid_columns(2)
        with patch("ct2trainer.native.master_trainer.master_ui"
                   ".TrainerEngine") as engine_cls, \
                patch("ct2trainer.native.master_trainer.master_ui"
                      ".TrainerWindow") as window_cls:
            window._poll()
        window_cls.assert_called_once()
        _, kwargs = window_cls.call_args
        self.assertEqual(kwargs["columns"], 2)
        self.assertEqual(kwargs["on_columns_changed"],
                         window._set_trainer_grid_columns)
        self.assertIs(window.engine, engine_cls.return_value)
        self.assertEqual(app.orchestrator.state, STATE_ACTIVE)

    def test_window_handler_persists_the_cycle(self):
        app = _make_app(self.folder, self.state_home)
        window = master_ui.MasterWindow(self.root, app)
        window._set_trainer_grid_columns(2)
        self.assertEqual(app.grid_columns, 2)
        stored = load_master_state(self.state_home / MASTER_STATE_FILENAME)
        self.assertEqual(stored.grid_columns, 2)

    def test_window_handler_swallows_bogus_values(self):
        # The window can only produce 1 / 2 / 3 by construction; the
        # named app-level refusal is contained (no dialog, no raise).
        app = _make_app(self.folder, self.state_home)
        window = master_ui.MasterWindow(self.root, app)
        window._set_trainer_grid_columns(7)
        self.assertEqual(app.grid_columns, 1)


@unittest.skipUnless(tk is not None, "tkinter required for real widget construction")
class TrainerWindowColumnsControlTests(unittest.TestCase):
    """The MT-21 grid control on the real standalone ``TrainerWindow``."""

    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        force_root_release([self.root], ((self, "root"),))

    def _engine(self, entries):
        e = MagicMock()
        e.entries = entries
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
        e.parent_query = MagicMock(return_value={"active": False})
        return e

    def _grid_entries(self):
        # Section (1) with two child switches (2, 3), a top-level
        # switch (4), a value (5) and a blocked row (6).
        return {
            1: {"id": 1, "label": "Section A", "path": "Section A",
                "parent_id": None, "kind": "heading", "selected": True,
                "supported": True, "reason": "",
                "parent_activation": [2, 3]},
            2: {"id": 2, "label": "Switch One in A", "path": "a/one",
                "parent_id": 1, "kind": "script", "selected": True,
                "supported": True, "reason": ""},
            3: {"id": 3, "label": "Switch Two in A", "path": "a/two",
                "parent_id": 1, "kind": "script", "selected": True,
                "supported": True, "reason": ""},
            4: {"id": 4, "label": "Top Switch", "path": "top",
                "parent_id": None, "kind": "script", "selected": True,
                "supported": True, "reason": ""},
            5: {"id": 5, "label": "Value Row", "path": "value",
                "parent_id": None, "kind": "value", "selected": True,
                "supported": True, "reason": "",
                "variable_type": "4bytes"},
            6: {"id": 6, "label": "Blocked Row", "path": "blocked",
                "parent_id": None, "kind": "script", "selected": False,
                "supported": True, "reason": "Not selected"},
        }

    def _size(self, window, width, height):
        # A withdrawn window never maps its canvas; the renderer reads
        # the requested size through these two accessors.
        window.canvas.winfo_width = lambda: width
        window.canvas.winfo_height = lambda: height

    def test_columns_kwarg_default_and_validation(self):
        from ct2trainer.native.ui import TrainerWindow
        sig = inspect.signature(TrainerWindow.__init__)
        self.assertEqual(sig.parameters["columns"].default, 1)
        self.assertIsNone(sig.parameters["on_columns_changed"].default)
        for bad in (0, 4, "2", None):
            with self.assertRaises(ValueError):
                TrainerWindow(self.root, self._engine({}), columns=bad)

    def test_columns_button_present_only_when_wired(self):
        # The header control appears only for the Master Trainer; the
        # standalone trainer keeps its exact header.
        from ct2trainer.native.ui import TrainerWindow
        root1 = tk.Tk()
        root1.withdraw()
        self.addCleanup(force_root_release, [root1])
        wired = TrainerWindow(root1, self._engine({}),
                              on_columns_changed=lambda c: None)
        self.assertIn("Columns: 1", _button_texts(wired.header))

        root2 = tk.Tk()
        root2.withdraw()
        self.addCleanup(force_root_release, [root2])
        standalone = TrainerWindow(root2, self._engine({}))
        self.assertIsNone(standalone.columns_btn)
        self.assertNotIn("Columns: 1", _button_texts(standalone.header))

    def test_cycle_flips_label_and_notifies(self):
        from ct2trainer.native.ui import TrainerWindow
        root1 = tk.Tk()
        root1.withdraw()
        self.addCleanup(force_root_release, [root1])
        calls = []
        window = TrainerWindow(root1, self._engine({}), columns=1,
                               on_columns_changed=calls.append)
        self._size(window, 1000, 500)
        window._cycle_columns()
        self.assertEqual(window.columns, 2)
        self.assertEqual(str(window.columns_btn.cget("text")), "Columns: 2")
        self.assertEqual(calls, [2])
        window._cycle_columns()
        self.assertEqual(window.columns, 3)
        self.assertEqual(str(window.columns_btn.cget("text")), "Columns: 3")
        window._cycle_columns()
        self.assertEqual(window.columns, 1)
        self.assertEqual(str(window.columns_btn.cget("text")), "Columns: 1")
        self.assertEqual(calls, [2, 3, 1])

    def test_render_two_columns_with_per_column_hit_test(self):
        from ct2trainer.native.ui import TrainerWindow
        window = TrainerWindow(self.root, self._engine(self._grid_entries()),
                               columns=2,
                               on_columns_changed=lambda c: None)
        self._size(window, 1000, 500)
        window.view = "All"
        window.render()
        self.assertEqual(window._col_ws, [494, 494])
        self.assertEqual(window._col_xs, [0, 506])
        self.assertEqual(column_layout(1000, 2), ([494, 494], [0, 506]))
        self.assertEqual(
            [[r.entry_id for r in col] for col in window._col_rows],
            [[1, 2, 3], [4, 5, 6]])
        # Hit-testing is per-column: x picks the column, y picks the
        # row inside that column.
        self.assertEqual(window._row_at(5, 5).entry_id, 1)     # section, col 0
        self.assertEqual(window._row_at(5, 60).entry_id, 2)    # switch, col 0
        self.assertEqual(window._row_at(600, 5).entry_id, 4)   # switch, col 1
        self.assertEqual(window._row_at(600, 70).entry_id, 5)  # value, col 1
        self.assertIsNone(window._row_at(501, 5))             # column gap

    def test_render_clamps_narrow_windows(self):
        from ct2trainer.native.ui import TrainerWindow
        window = TrainerWindow(self.root, self._engine(self._grid_entries()),
                               columns=3,
                               on_columns_changed=lambda c: None)
        window.view = "All"
        self._size(window, 700, 500)
        window.render()
        # 700 px fits two columns, not three.
        self.assertEqual(len(window._col_rows), 2)
        self.assertEqual(window._col_xs, [0, 356])
        self._size(window, 320, 500)
        window.render()
        # The width floor fits exactly one column.
        self.assertEqual(len(window._col_rows), 1)
        self.assertEqual(window._col_xs, [0])
        self.assertEqual(window._col_ws, [320])

    def test_standalone_always_renders_one_column(self):
        from ct2trainer.native.ui import TrainerWindow
        window = TrainerWindow(self.root, self._engine(self._grid_entries()))
        self._size(window, 1000, 500)
        window.view = "All"
        window.render()
        self.assertEqual(len(window._col_rows), 1)
        self.assertEqual(window._col_xs, [0])
        self.assertEqual(window._col_ws, [1000])
        self.assertIsNone(window.columns_btn)


if __name__ == "__main__":
    unittest.main()
