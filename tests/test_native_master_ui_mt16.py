"""Master Trainer 0.27: persisted waiting-view settings (MT-16) and the
process-grouped view (MT-17) wiring.

Covers the Tk wiring on top of the pure layers: the schema-4
waiting-view settings (filter query, sort mode, display mode) are
restored at construction and re-persisted on every change (sort
cycle, view cycle, filter edit, Esc clear); the MT-17 grouped view
renders one parent row per casefolded bound process name (the group
label in values[0] because the tree uses show="headings"), the unbound
group last, multi-bound tables in every bound group; group rows are
display-only (never load), children load through the ordinary MT-10
path.  No real process is attached (a _FakeLister stands in).
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    import tkinter as tk
except ImportError:  # pragma: no cover - environment without Tcl/Tk
    tk = None

from test_native_master_ui import CT_GAMEA, _FakeLister

from native_tk_teardown import force_root_release

from ct2trainer.native.master_trainer.master_state import (
    MASTER_STATE_FILENAME,
    load_master_state,
)
from ct2trainer.native.master_trainer.table_index import TableEntry
from ct2trainer.native.master_trainer.table_filter import (
    UNBOUND_PROCESS_LABEL,
)
from ct2trainer.native.master_trainer.master_ui import MasterApp, MasterWindow


def _entries():
    """A deterministic entry set (the shape of the reconciled index)."""
    return {
        "zeta.ct": TableEntry("zeta.ct", 512, 0, "a" * 64,
                              ("ZGame.exe",), "ok", None),
        "alpha.ct": TableEntry("alpha.ct", 128, 0, "b" * 64,
                               ("aGame.exe",), "ok", None),
        "rdr2.ct": TableEntry("rdr2.ct", 64, 0, "c" * 64,
                              ("RDR2.exe", "RDR2legacy.exe"), "ok", None),
        "empty.ct": TableEntry("empty.ct", 32, 0, "d" * 64,
                               (), "ok", None),
    }


class _WaitingViewBase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.folder = root / "tables"
        self.folder.mkdir()
        self.state_home = root / "state"
        self.state_home.mkdir()
        (self.folder / "zeta.ct").write_text(CT_GAMEA, encoding="utf-8")
        self.root = tk.Tk()
        self.addCleanup(force_root_release, [self.root],
                        ((self, "root"), (self, "window"), (self, "app")))

    def _app(self):
        return MasterApp(self.folder, state_home=self.state_home,
                         poll_ms=50, lister=_FakeLister(),
                         plan_compiler=lambda e, n:
                         {"title": "T", "relative_path": e.relative_path})

    def _window(self, app, view_mode=None):
        window = MasterWindow(self.root, app)
        if view_mode is not None:
            window._view_mode = view_mode
            window._render_tables()
        return window


@unittest.skipIf(tk is None, "tkinter not available")
class ViewSettingsPersistTests(_WaitingViewBase):
    """MT-16 (0.27): the waiting-view settings persist in schema 4."""

    def test_fresh_state_home_takes_the_documented_defaults(self):
        app = self._app()
        self.assertEqual((app.view_filter, app.view_sort,
                          app.view_mode), ("", "name", "list"))

    def test_set_view_settings_persists_and_restores(self):
        app = self._app()
        app.set_view_settings("zeta", "process", "process")
        stored = load_master_state(
            Path(self.state_home) / MASTER_STATE_FILENAME)
        self.assertEqual((stored.view_filter, stored.view_sort,
                          stored.view_mode), ("zeta", "process", "process"))
        again = self._app()
        self.assertEqual((again.view_filter, again.view_sort,
                          again.view_mode), ("zeta", "process", "process"))

    def test_set_view_settings_refuses_invalid_values(self):
        app = self._app()
        for args, needle in ((("", "size", "list"), "view sort mode"),
                             (("", "name", "grid"), "view mode"),
                             (("x" * 201, "name", "list"), "200")):
            with self.assertRaises(ValueError) as ctx:
                app.set_view_settings(*args)
            self.assertIn(needle, str(ctx.exception))
        self.assertEqual((app.view_filter, app.view_sort,
                          app.view_mode), ("", "name", "list"))

    def test_window_restores_the_persisted_settings(self):
        app = self._app()
        app.set_view_settings("alpha", "status", "process")
        window = self._window(app)
        self.assertEqual(window._filter_entry.get(), "alpha")
        self.assertEqual(window._sort_btn.cget("text"), "Sort: status")
        self.assertEqual(window._view_btn.cget("text"), "View: process")

    def test_every_ui_change_is_repersisted(self):
        app = self._app()
        window = self._window(app)
        window._cycle_view()
        window._cycle_sort()
        window._filter_entry.insert(0, "alpha")
        window._on_filter_edit(None)
        stored = load_master_state(
            Path(self.state_home) / MASTER_STATE_FILENAME)
        self.assertEqual((stored.view_mode, stored.view_sort,
                          stored.view_filter),
                         ("process", "process", "alpha"))
        window._on_filter_escape(None)
        self.assertEqual(load_master_state(
            Path(self.state_home) / MASTER_STATE_FILENAME).view_filter, "")


@unittest.skipIf(tk is None, "tkinter not available")
class ProcessGroupViewTests(_WaitingViewBase):
    """MT-17 (0.27): the process-grouped waiting view."""

    def _grouped_window(self, view_mode="process"):
        app = self._app()
        app.index.entries = _entries()
        return app, self._window(app, view_mode)

    def test_group_rows_carry_label_count_and_children(self):
        _, window = self._grouped_window()
        tree = window._table_tree
        parents = [(tuple(tree.item(i, "values"))[0],
                    tuple(tree.item(i, "values"))[1])
                   for i in tree.get_children("")]
        self.assertEqual(
            parents,
            [("agame.exe", "1 table(s)"),
             ("rdr2.exe", "1 table(s)"),
             ("rdr2legacy.exe", "1 table(s)"),
             ("zgame.exe", "1 table(s)"),
             (UNBOUND_PROCESS_LABEL, "1 table(s)")])
        first = tree.get_children("")[0]
        self.assertEqual(
            [tuple(tree.item(i, "values"))[0]
             for i in tree.get_children(first)],
            ["alpha.ct"])

    def test_multi_bound_table_appears_in_every_bound_group(self):
        _, window = self._grouped_window()
        tree = window._table_tree
        groups = {tuple(tree.item(i, "values"))[0]:
                  [tuple(tree.item(j, "values"))[0]
                   for j in tree.get_children(i)]
                  for i in tree.get_children("")}
        self.assertIn("rdr2.ct", groups["rdr2.exe"])
        self.assertIn("rdr2.ct", groups["rdr2legacy.exe"])

    def test_group_rows_are_display_only_children_load(self):
        _, window = self._grouped_window()
        tree = window._table_tree
        parent = tree.get_children("")[0]
        child = tree.get_children(parent)[0]
        self.assertFalse(window._is_table_row(parent))
        self.assertTrue(window._is_table_row(child))
        calls = []
        window._load_selected_table = lambda rel: calls.append(rel)

        class Event:
            y = 0

        # Double-click on the (first, top) group row: no load.
        window._table_double_click(Event())
        self.assertEqual(calls, [])
        # The group row never surfaces as a selectable table.
        tree.selection_set(parent)
        tree.focus(parent)
        self.assertIsNone(window._table_selected_rel())
        # The child loads through the ordinary MT-10 path (Enter on
        # the selected child row).
        tree.selection_set(child)
        tree.focus(child)
        window._table_return(None)
        self.assertEqual(calls, ["alpha.ct"])

    def test_flat_view_rows_are_all_table_rows(self):
        _, window = self._grouped_window(view_mode="list")
        tree = window._table_tree
        self.assertEqual(len(tree.get_children("")), 4)
        for item in tree.get_children(""):
            self.assertTrue(window._is_table_row(item))

    def test_view_cycle_toggles_back_to_flat(self):
        app = self._app()
        app.index.entries = _entries()
        window = self._window(app)
        window._cycle_view()
        self.assertEqual(window._view_mode, "process")
        self.assertEqual(len(window._table_tree.get_children("")), 5)
        self.assertEqual(window._view_btn.cget("text"), "View: process")
        window._cycle_view()
        self.assertEqual(window._view_mode, "list")
        self.assertEqual(len(window._table_tree.get_children("")), 4)
        self.assertEqual(app.view_mode, "list")


if __name__ == "__main__":
    unittest.main()
