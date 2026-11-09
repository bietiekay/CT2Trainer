"""Master Trainer 0.28: pinned / favorite tables (MT-18) wiring.

Covers the Tk wiring on top of the pure layers: the pin set persists in
the master-state document (schema 5, ``pinned_tables`` - relative paths,
most recent pin first), is restored at construction and re-persisted on
every toggle; a pinned table floats to the top of the waiting view
(list view) and to the top of its process group (process view) through
the pure ``table_filter.pin_tables``; the pin marker lives in the
detail column (the first column stays the bare row identity); the row
context menu offers "Pin to top" / "Unpin"; named refusals (cap,
already pinned, not pinned) land in the status line without a state
change or a crash.  No real process is attached (a _FakeLister stands
in).
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
    PINNED_TABLES_LIMIT,
    load_master_state,
)
from ct2trainer.native.master_trainer.table_index import TableEntry
from ct2trainer.native.master_trainer.master_ui import MasterApp, MasterWindow


def _entries():
    """A deterministic entry set (the shape of the reconciled index)."""
    return {
        "zeta.ct": TableEntry("zeta.ct", 512, 0, "a" * 64,
                              ("ZGame.exe",), "ok", None),
        "alpha.ct": TableEntry("alpha.ct", 128, 0, "b" * 64,
                               ("aGame.exe",), "ok", None),
        "rdr2.ct": TableEntry("rdr2.ct", 64, 0, "c" * 64,
                              ("RDR2.exe",), "ok", None),
        "empty.ct": TableEntry("empty.ct", 32, 0, "d" * 64,
                               (), "ok", None),
    }


def _entries_shared():
    """Two tables bound to the SAME process name (group float test)."""
    return {
        "bbb.ct": TableEntry("bbb.ct", 512, 0, "a" * 64,
                             ("Same.exe",), "ok", None),
        "aaa.ct": TableEntry("aaa.ct", 128, 0, "b" * 64,
                             ("Same.exe",), "ok", None),
        "solo.ct": TableEntry("solo.ct", 64, 0, "c" * 64,
                              ("Solo.exe",), "ok", None),
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

    def _stored(self):
        return load_master_state(
            Path(self.state_home) / MASTER_STATE_FILENAME)


@unittest.skipIf(tk is None, "tkinter not available")
class PinPersistTests(_WaitingViewBase):
    """MT-18 (0.28): the pin set persists in schema 5."""

    def test_fresh_state_home_takes_no_pins(self):
        app = self._app()
        self.assertEqual(app.pinned_tables, ())
        self.assertFalse(app.is_table_pinned("zeta.ct"))

    def test_pin_toggles_via_window_and_persists(self):
        app = self._app()
        app.index.indexes[0].entries = _entries()
        window = self._window(app)
        # Default name order: alpha, empty, rdr2, zeta.
        self.assertEqual(
            [tuple(window._table_tree.item(i, "values"))[0]
             for i in window._table_tree.get_children("")],
            ["alpha.ct", "empty.ct", "rdr2.ct", "zeta.ct"])
        window._toggle_table_pin("zeta.ct", True)
        self.assertEqual(app.pinned_tables, ("zeta.ct",))
        self.assertEqual(self._stored().pinned_tables, ("zeta.ct",))
        self.assertIn("Pinned zeta.ct", window._status_var.get())
        # The pinned row floats to the top with the detail-column
        # marker (MT-26 (0.34): the Folder column shifted it to 4).
        first = window._table_tree.get_children("")[0]
        values = tuple(window._table_tree.item(first, "values"))
        self.assertEqual(values[0], "zeta.ct")
        self.assertTrue(values[4].startswith("pinned"))
        # The first column stays the bare relative path (row identity).
        self.assertEqual(values[0].casefold(), "zeta.ct")
        # Most recent pin first: pinning alpha now puts it above zeta.
        app.set_table_pinned("alpha.ct", True)
        window._render_tables()
        self.assertEqual(app.pinned_tables, ("alpha.ct", "zeta.ct"))
        top = [tuple(window._table_tree.item(i, "values"))[0]
               for i in window._table_tree.get_children("")]
        self.assertEqual(top[:2], ["alpha.ct", "zeta.ct"])

    def test_unpin_restores_order_and_clears_state(self):
        app = self._app()
        app.index.indexes[0].entries = _entries()
        window = self._window(app)
        window._toggle_table_pin("zeta.ct", True)
        window._toggle_table_pin("zeta.ct", False)
        self.assertEqual(app.pinned_tables, ())
        self.assertEqual(self._stored().pinned_tables, ())
        self.assertIn("Unpinned zeta.ct", window._status_var.get())
        self.assertEqual(
            [tuple(window._table_tree.item(i, "values"))[0]
             for i in window._table_tree.get_children("")],
            ["alpha.ct", "empty.ct", "rdr2.ct", "zeta.ct"])

    def test_named_refusals_land_in_status_without_state_change(self):
        app = self._app()
        app.index.indexes[0].entries = _entries()
        window = self._window(app)
        # Cap: PINNED_TABLES_LIMIT pins, then the next one is refused.
        for i in range(PINNED_TABLES_LIMIT):
            app.set_table_pinned("t%02d.ct" % i, True)
        with self.assertRaises(ValueError) as ctx:
            app.set_table_pinned("overflow.ct", True)
        self.assertIn(str(PINNED_TABLES_LIMIT), str(ctx.exception))
        self.assertEqual(len(app.pinned_tables), PINNED_TABLES_LIMIT)
        # Already pinned / not pinned: named refusals, no state change.
        with self.assertRaises(ValueError) as ctx:
            app.set_table_pinned("t00.ct", True)
        self.assertIn("already pinned", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            app.set_table_pinned("never.ct", False)
        self.assertIn("not pinned", str(ctx.exception))
        self.assertEqual(self._stored().pinned_tables,
                         app.pinned_tables)
        # The window surfaces the refusal in the status line and keeps
        # the rendered tree (no crash, no hot-retry).
        window._toggle_table_pin("overflow.ct", True)
        self.assertIn(str(PINNED_TABLES_LIMIT),
                      window._status_var.get())
        self.assertEqual(len(app.pinned_tables), PINNED_TABLES_LIMIT)

    def test_pinned_table_filtered_out_is_ignored(self):
        app = self._app()
        app.index.indexes[0].entries = _entries()
        window = self._window(app)
        window._toggle_table_pin("zeta.ct", True)
        window._filter_entry.insert(0, "alpha")
        window._on_filter_edit(None)
        visible = [tuple(window._table_tree.item(i, "values"))[0]
                   for i in window._table_tree.get_children("")]
        self.assertEqual(visible, ["alpha.ct"])
        # The pin stays persisted; only the filtered row set is reshaped.
        self.assertEqual(app.pinned_tables, ("zeta.ct",))
        window._on_filter_escape(None)
        self.assertEqual(
            [tuple(window._table_tree.item(i, "values"))[0]
             for i in window._table_tree.get_children("")],
            ["zeta.ct", "alpha.ct", "empty.ct", "rdr2.ct"])


@unittest.skipIf(tk is None, "tkinter not available")
class PinProcessGroupTests(_WaitingViewBase):
    """MT-18 (0.28): a pinned table floats to the top of its group."""

    def test_pin_floats_to_top_of_its_process_group(self):
        app = self._app()
        app.index.indexes[0].entries = _entries_shared()
        window = self._window(app, view_mode="process")
        tree = window._table_tree
        # Default within-group order (name sort): aaa before bbb.
        groups = {tuple(tree.item(i, "values"))[0]:
                  [tuple(tree.item(j, "values"))[0]
                   for j in tree.get_children(i)]
                  for i in tree.get_children("")}
        self.assertEqual(groups["same.exe"], ["aaa.ct", "bbb.ct"])
        app.set_table_pinned("bbb.ct", True)
        window._render_tables()
        groups = {tuple(tree.item(i, "values"))[0]:
                  [tuple(tree.item(j, "values"))[0]
                   for j in tree.get_children(i)]
                  for i in tree.get_children("")}
        self.assertEqual(groups["same.exe"], ["bbb.ct", "aaa.ct"])
        # The pin never adds or drops rows: the other groups are
        # untouched and the group count is unchanged.
        self.assertEqual(groups["solo.exe"], ["solo.ct"])
        self.assertEqual(len(tree.get_children("")), 2)

    def test_pin_marker_is_visible_in_the_group_child(self):
        app = self._app()
        app.index.indexes[0].entries = _entries_shared()
        window = self._window(app, view_mode="process")
        app.set_table_pinned("bbb.ct", True)
        window._render_tables()
        tree = window._table_tree
        group = tree.get_children("")[0]
        child = tree.get_children(group)[0]
        values = tuple(tree.item(child, "values"))
        self.assertEqual(values[0], "bbb.ct")
        # MT-26 (0.34): the detail column shifted right of the Folder
        # column.
        self.assertTrue(values[4].startswith("pinned"))


if __name__ == "__main__":
    unittest.main()
