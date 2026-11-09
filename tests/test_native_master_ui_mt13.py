"""Master Trainer 0.26 waiting-view usability wiring (MT-13/14/15).

Covers the Tk wiring on top of the pure layers: the waiting-view
filter entry + sort cycle button (live filtering over table name and
bound process names, the meta line counter, Esc clear, "/" focus),
the keyboard load flow (double-click / Enter through the MT-10
explicit path), the Size / Modified / Last-used columns (fed by the
index and the recent list), the "Recent:" one-click load button, and
the recent-list feed on successful load (auto and explicit paths).

``TrainerEngine`` / ``TrainerWindow`` / ``messagebox`` are patched for
the load-flow tests (the same pattern as the MT-12 test file); no real
process is attached.
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

from test_native_master_ui import CT_GAMEA, _FakeLister

from native_tk_teardown import force_root_release

from ct2trainer.native.master_trainer.master_state import (
    MASTER_STATE_FILENAME,
    MASTER_STATE_SCHEMA,
    MasterState,
    load_master_state,
    save_master_state,
)
from ct2trainer.native.master_trainer.orchestrator import STATE_ACTIVE
from ct2trainer.native.master_trainer.process_watch import ProcessSnapshotEntry
from ct2trainer.native.master_trainer.table_index import TableEntry
from ct2trainer.native.master_trainer.master_ui import MasterApp, MasterWindow


@unittest.skipIf(tk is None, "tkinter not available")
class WaitingViewFilterSortTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.folder = root / "tables"
        self.folder.mkdir()
        self.state_home = root / "state"
        self.state_home.mkdir()
        (self.folder / "zeta.ct").write_text(CT_GAMEA, encoding="utf-8")
        (self.folder / "alpha.ct").write_text(
            CT_GAMEA.replace("GameA", "AlphaGame"), encoding="utf-8")
        (self.folder / "broken.ct").write_text("not a table",
                                               encoding="utf-8")
        self.root = tk.Tk()
        self.addCleanup(force_root_release, [self.root],
                         ((self, "root"), (self, "window"), (self, "app")))

    def _app(self):
        return MasterApp(self.folder, state_home=self.state_home,
                         poll_ms=50, lister=_FakeLister(),
                         plan_compiler=lambda e, n:
                         {"title": "T", "relative_path": e.relative_path})

    def _window(self, app):
        return MasterWindow(self.root, app)

    def _visible_rows(self, window):
        tree = window._table_tree
        return [tuple(tree.item(i, "values"))[0]
                for i in tree.get_children()]

    def _inject_entries(self, app):
        # Deterministic entry set (the reconciled one carries real
        # fingerprints; the shape is identical).
        app.index.indexes[0].entries = {
            "Sub/Gamma (Legacy).ct": TableEntry(
                "Sub/Gamma (Legacy).ct", 2048, 0, "c" * 64,
                ("Gamma.exe", "GammaLegacy.exe"), "ok", None),
            "zeta.ct": TableEntry("zeta.ct", 512, 0, "a" * 64,
                                  ("ZGame.exe",), "ok", None),
            "alpha.ct": TableEntry("alpha.ct", 128, 0, "b" * 64,
                                   ("aGame.exe",), "ok", None),
            "broken.ct": TableEntry("broken.ct", 11, 0, "d" * 64, (),
                                    "unreadable", "parse failed"),
        }
        # MT-26 (0.34): the entries live in the per-root index; the
        # merged set (and the orchestrator reference) are unchanged.
        app.orchestrator.index = app.index

    def test_filter_entry_filters_the_tree_live(self):
        app = self._app()
        window = self._window(app)
        self._inject_entries(app)
        window._render_tables()
        self.assertEqual(len(window._visible_tables()), 4)
        # Filter by table name (casefolded).
        window._filter_entry.insert(0, "ZETA")
        window._on_filter_edit(None)
        self.assertEqual(self._visible_rows(window), ["zeta.ct"])
        # The meta line carries the counter while a query is active.
        self.assertIn("filtered: 1/4", str(window._meta_label.cget("text")))
        # Filter by a bound process name.
        window._filter_entry.delete(0, "end")
        window._filter_entry.insert(0, "gamma")
        window._on_filter_edit(None)
        self.assertEqual(self._visible_rows(window),
                         ["Sub/Gamma (Legacy).ct"])
        # No match: empty result, counter visible.
        window._filter_entry.delete(0, "end")
        window._filter_entry.insert(0, "nomatch")
        window._on_filter_edit(None)
        self.assertEqual(self._visible_rows(window), [])
        self.assertIn("filtered: 0/4", str(window._meta_label.cget("text")))
        # Esc clears and restores the full list order.
        window._on_filter_escape(None)
        self.assertEqual(window._filter_query, "")
        self.assertEqual(window._filter_entry.get(), "")
        self.assertEqual(len(self._visible_rows(window)), 4)
        self.assertNotIn("filtered:", str(window._meta_label.cget("text")))

    def test_sort_cycle_button_covers_the_three_modes(self):
        app = self._app()
        window = self._window(app)
        self._inject_entries(app)
        window._render_tables()
        # name (default): alpha, broken, Gamma, zeta (casefolded).
        self.assertEqual(self._visible_rows(window),
                         ["alpha.ct", "broken.ct",
                          "Sub/Gamma (Legacy).ct", "zeta.ct"])
        window._cycle_sort()
        self.assertEqual(window._sort_mode, "process")
        self.assertEqual(window._sort_btn.cget("text"), "Sort: process")
        # process: aGame, Gamma.exe, ZGame, then the unbound by name.
        self.assertEqual(self._visible_rows(window),
                         ["alpha.ct", "Sub/Gamma (Legacy).ct", "zeta.ct",
                          "broken.ct"])
        window._cycle_sort()
        self.assertEqual(window._sort_mode, "status")
        # status: readable by name, unreadable last.
        self.assertEqual(self._visible_rows(window),
                         ["alpha.ct", "Sub/Gamma (Legacy).ct", "zeta.ct",
                          "broken.ct"])
        window._cycle_sort()
        self.assertEqual(window._sort_mode, "name")

    def test_filter_survives_a_rescan(self):
        app = self._app()
        window = self._window(app)
        self._inject_entries(app)
        window._render_tables()
        window._filter_entry.insert(0, "alpha")
        window._on_filter_edit(None)
        with patch("ct2trainer.native.master_trainer.master_ui"
                   ".messagebox"):
            window._rescan()
        # The index rebuilds; the query stays active and re-renders.
        self.assertEqual(window._filter_query, "alpha")
        self.assertEqual(window._filter_entry.get(), "alpha")
        self.assertEqual(self._visible_rows(window), ["alpha.ct"])

    def test_slash_focuses_the_filter_only_in_waiting_mode(self):
        # The handler contract is focus-the-entry in waiting mode and a
        # no-op in trainer mode (Tk focus allocation on an unmapped
        # window is environment-dependent, so the call itself is the
        # deterministic evidence).
        app = self._app()
        window = self._window(app)
        calls = []
        real_focus = window._filter_entry.focus_set
        window._filter_entry.focus_set = (
            lambda *args: calls.append(1) or real_focus(*args))
        window._on_slash(None)
        self.assertEqual(calls, [1])
        # In trainer mode the keys belong to the trainer UI.
        window.engine = object()
        calls.clear()
        window._on_slash(None)
        self.assertEqual(calls, [])


@unittest.skipIf(tk is None, "tkinter not available")
class KeyboardLoadFlowTests(unittest.TestCase):
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
        self.app = MasterApp(self.folder, state_home=self.state_home,
                             poll_ms=50, lister=_FakeLister(),
                             plan_compiler=lambda e, n:
                             {"title": "T", "relative_path": e.relative_path})
        self.window = MasterWindow(self.root, self.app)

    def test_return_loads_the_selected_row(self):
        with patch("ct2trainer.native.master_trainer.master_ui"
                   ".TrainerEngine") as engine_cls, \
                 patch("ct2trainer.native.master_trainer.master_ui"
                       ".TrainerWindow"):
            self.window._table_tree.selection_set(
                self.window._table_tree.get_children()[0])
            self.window._table_tree.focus(
                self.window._table_tree.get_children()[0])
            self.window._table_return(None)
        self.assertIs(self.window.engine, engine_cls.return_value)
        self.assertEqual(self.app.orchestrator.state, STATE_ACTIVE)

    def test_return_without_a_selection_is_a_no_op(self):
        with patch("ct2trainer.native.master_trainer.master_ui"
                   ".TrainerEngine") as engine_cls, \
                 patch("ct2trainer.native.master_trainer.master_ui"
                       ".messagebox") as box:
            self.window._table_return(None)
        self.assertIsNone(self.window.engine)
        box.assert_not_called()

    def test_double_click_loads_the_clicked_row(self):
        with patch("ct2trainer.native.master_trainer.master_ui"
                   ".TrainerEngine") as engine_cls, \
                 patch("ct2trainer.native.master_trainer.master_ui"
                       ".TrainerWindow"):
            self.window._table_tree.selection_set(
                self.window._table_tree.get_children()[0])
            # Allocate the real geometry so identify_row(event.y)
            # resolves to the clicked row.
            self.root.update()
            # MT-24 (0.32): the update pump may have fired a waiting
            # tick that re-rendered the table rows (the background plan
            # analysis finished) - re-resolve the row identity.
            child = self.window._table_tree.get_children()[0]
            self.window._table_tree.selection_set(child)
            bbox = self.window._table_tree.bbox(child)
            self.assertIsNotNone(bbox)
            event = MagicMock()
            event.y = bbox[1] + bbox[3] // 2
            self.window._table_double_click(event)
        self.assertIs(self.window.engine, engine_cls.return_value)


@unittest.skipIf(tk is None, "tkinter not available")
class RecentAndMetadataColumnsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.folder = root / "tables"
        self.folder.mkdir()
        self.state_home = root / "state"
        self.state_home.mkdir()
        (self.folder / "a.ct").write_text(CT_GAMEA, encoding="utf-8")
        (self.folder / "b.ct").write_text(CT_GAMEA.replace("GameA", "GameB"),
                                          encoding="utf-8")
        self.root = tk.Tk()
        self.addCleanup(force_root_release, [self.root],
                         ((self, "root"), (self, "window"), (self, "app")))

    def _app(self):
        return MasterApp(self.folder, state_home=self.state_home,
                         poll_ms=50, lister=_FakeLister(),
                         plan_compiler=lambda e, n:
                         {"title": "T", "relative_path": e.relative_path})

    def test_columns_carry_size_modified_and_last_used(self):
        app = self._app()
        window = MasterWindow(self.root, app)
        window._render_tables()
        tree = window._table_tree
        child = tree.get_children()[0]
        values = tree.item(child, "values")
        # MT-24 (0.32): the Entries / Blocked columns sit between
        # Detail and Size (pending "…" until the background plan
        # analysis re-renders the row); MT-26 (0.34): the Folder
        # column after Table shifts them right by one.
        self.assertEqual(values[5:7], ("…", "…"))
        self.assertEqual(len(values), 10)
        # Size is the compact human-readable byte size.
        self.assertTrue(values[7].endswith((" B", " KB", " MB")))
        # Modified is a local timestamp of the documented shape.
        import re
        self.assertTrue(re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}",
                                     values[8]), values[8])
        # Last used starts empty (no recent entry yet).
        self.assertEqual(values[9], "")

    def test_recent_button_and_last_used_column_feed_the_recent_list(self):
        app = self._app()
        app.remember_recent_table("a.ct")
        window = MasterWindow(self.root, app)
        # The one-click Recent button is present and named after the
        # most recent table.
        self.assertIsNotNone(window._recent_btn)
        self.assertEqual(str(window._recent_btn.cget("text")), "Recent: a.ct")
        window._render_tables()
        tree = window._table_tree
        by_name = {tree.item(i, "values")[0]: tree.item(i, "values")
                   for i in tree.get_children()}
        # MT-15/MT-24 (0.26/0.32): Last used is the last column (after
        # the Entries / Blocked columns); MT-26 (0.34): shifted right
        # by the Folder column.
        self.assertTrue(by_name["a.ct"][9].endswith("Z"))
        self.assertEqual(by_name["b.ct"][9], "")
        # The meta line lists the recent table.
        self.assertIn("recent: a.ct", str(window._meta_label.cget("text")))

    def test_recent_button_loads_the_most_recent_table(self):
        app = self._app()
        app.remember_recent_table("a.ct")
        app.remember_recent_table("b.ct")
        window = MasterWindow(self.root, app)
        with patch("ct2trainer.native.master_trainer.master_ui"
                   ".TrainerEngine") as engine_cls, \
                 patch("ct2trainer.native.master_trainer.master_ui"
                       ".TrainerWindow"):
            window._load_recent_table()
        self.assertEqual(app.last_table, "b.ct")
        self.assertEqual([p for p, _at in app.recent_tables],
                         ["b.ct", "a.ct"])
        self.assertEqual(app.recent_tables[0][0], "b.ct")

    def test_successful_load_feeds_the_recent_list(self):
        app = self._app()
        window = MasterWindow(self.root, app)
        with patch("ct2trainer.native.master_trainer.master_ui"
                   ".TrainerEngine"), \
                 patch("ct2trainer.native.master_trainer.master_ui"
                       ".TrainerWindow"):
            window._load_selected_table("a.ct")
        self.assertEqual(app.recent_tables[0][0], "a.ct")
        stored = load_master_state(self.state_home / MASTER_STATE_FILENAME)
        self.assertEqual(stored.schema, MASTER_STATE_SCHEMA)
        self.assertEqual([p for p, _at in stored.recent_tables], ["a.ct"])

    def test_stored_recent_survives_rebuild(self):
        app = self._app()
        app.remember_recent_table("a.ct")
        window = MasterWindow(self.root, app)
        # Simulate the back-to-master rebuild (the waiting view is
        # rebuilt from the session state).
        window._build_waiting_view()
        self.assertIsNotNone(window._recent_btn)
        self.assertEqual(str(window._recent_btn.cget("text")),
                         "Recent: a.ct")


if __name__ == "__main__":
    unittest.main()
