"""Master Trainer 0.31: per-table live status + color coding + status
filter (MT-23).

Covers the pure ``table_status`` layer (``row_file_status`` /
``row_status`` / ``row_tag`` / ``filter_rows_by_status`` - cheapest
fact first, live facts outrank the cached scan state, the same order
the MT-9 gate proves at load time) and the Tk wiring on top: the live
Status column (one bounded stat per visible row per render), the row
color coding (default for ok / running, amber for changed, red for
missing / unreadable), the persisted "Status: all / ok / attention"
header cycle (schema 6, view_status) and the meta-line attention
count.  No real process is attached (a _FakeLister stands in).
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    import tkinter as tk
except ImportError:  # pragma: no cover - environment without Tcl/Tk
    tk = None

from test_native_master_ui import CT_GAMEA, CT_GAMEB, _FakeLister, _make_app

from native_tk_teardown import force_root_release

from ct2trainer.native.master_trainer import table_status
from ct2trainer.native.master_trainer.master_state import (
    MASTER_STATE_FILENAME,
    load_master_state,
)
from ct2trainer.native.master_trainer.table_index import TableEntry
from ct2trainer.native.master_trainer.table_status import (
    ATTENTION_STATUSES,
    filter_rows_by_status,
    row_file_status,
    row_status,
    row_tag,
)
from ct2trainer.native.master_trainer.master_ui import MasterApp, MasterWindow


def _entry(**overrides):
    """One indexed entry with a live fingerprint of (100, 1000)."""
    base = dict(relative_path="a.ct", size=100, mtime_ns=1000,
                sha256="a" * 64, process_names=("GameA.exe",),
                status="ok", detail=None)
    base.update(overrides)
    return TableEntry(**base)


class RowFileStatusTests(unittest.TestCase):
    """MT-23 (0.31): the live file state of one indexed table."""

    def test_ok_when_the_fingerprint_matches(self):
        code, detail = row_file_status(_entry(), (100, 1000))
        self.assertEqual((code, detail), ("ok", ""))

    def test_changed_when_the_fingerprint_drifts(self):
        for fingerprint in ((101, 1000), (100, 1001)):
            code, detail = row_file_status(_entry(), fingerprint)
            self.assertEqual(code, "changed")
            self.assertIn("Rescan", detail)

    def test_missing_when_the_file_is_gone(self):
        code, detail = row_file_status(_entry(), None)
        self.assertEqual(code, "missing")
        self.assertIn("Rescan", detail)

    def test_unreadable_surfaces_the_cached_detail(self):
        entry = _entry(status="unreadable", detail="empty file")
        code, detail = row_file_status(entry, (100, 1000))
        self.assertEqual((code, detail), ("unreadable", "empty file"))

    def test_unreadable_without_a_detail_gets_a_displayable_one(self):
        entry = _entry(status="unreadable", detail=None)
        code, detail = row_file_status(entry, (100, 1000))
        self.assertEqual(code, "unreadable")
        self.assertTrue(detail)


class RowStatusTests(unittest.TestCase):
    """MT-23 (0.31): the Status-column value per row."""

    def test_running_only_for_a_loadable_file(self):
        entry = _entry()
        self.assertEqual(row_status(entry, (100, 1000), running=True),
                         "running")
        self.assertEqual(row_status(entry, (100, 1000), running=False),
                         "ok")

    def test_the_attention_code_wins_over_the_running_process(self):
        entry = _entry()
        self.assertEqual(row_status(entry, (101, 1000), running=True),
                         "changed")
        self.assertEqual(row_status(entry, None, running=True), "missing")
        stale = _entry(status="unreadable", detail="d")
        self.assertEqual(row_status(stale, (100, 1000), running=True),
                         "unreadable")


class RowTagTests(unittest.TestCase):
    """MT-23 (0.31): the row color-coding tag per code."""

    def test_the_tag_per_code(self):
        self.assertEqual(row_tag("ok"), "")
        self.assertEqual(row_tag("running"), "")
        self.assertEqual(row_tag("changed"), "attention-warn")
        self.assertEqual(row_tag("missing"), "attention-error")
        self.assertEqual(row_tag("unreadable"), "attention-error")
        self.assertEqual(row_tag("unknown-code"), "")


class FilterRowsByStatusTests(unittest.TestCase):
    """MT-23 (0.31): the pure status-filter reshaping."""

    def _rows(self):
        return ["ok.ct", "run.ct", "chg.ct", "mis.ct", "unr.ct"]

    def _codes(self):
        return ["ok", "running", "changed", "missing", "unreadable"]

    def test_all_is_the_identity(self):
        self.assertEqual(filter_rows_by_status(self._rows(),
                                               self._codes(), ""),
                         self._rows())

    def test_ok_keeps_the_loadable_rows(self):
        self.assertEqual(filter_rows_by_status(self._rows(),
                                               self._codes(), "ok"),
                         ["ok.ct", "run.ct"])

    def test_attention_keeps_the_gate_refused_rows(self):
        self.assertEqual(filter_rows_by_status(self._rows(),
                                               self._codes(), "attention"),
                         ["chg.ct", "mis.ct", "unr.ct"])

    def test_the_unknown_mode_is_refused(self):
        with self.assertRaises(ValueError) as ctx:
            filter_rows_by_status(self._rows(), self._codes(), "all")
        self.assertIn("status filter mode", str(ctx.exception))

    def test_the_constant_mirrors_the_state_schema(self):
        from ct2trainer.native.master_trainer.master_state import (
            VIEW_STATUS_FILTERS as state_filters)
        self.assertEqual(table_status.VIEW_STATUS_FILTERS, state_filters)

    def test_attention_statuses_are_the_gate_refused_set(self):
        self.assertEqual(ATTENTION_STATUSES,
                         frozenset(("changed", "missing", "unreadable")))


@unittest.skipIf(tk is None, "tkinter not available")
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

    def _window(self, app):
        return MasterWindow(self.root, app)

    def _rows(self):
        tree = self.window._table_tree
        return {list(tree.item(r)["values"])[0]:
                (list(tree.item(r)["values"]), tree.item(r)["tags"])
                for r in tree.get_children()}

    def _stop_analysis(self, app):
        # MT-24 (0.32) guard: the background plan-analysis worker reads
        # the table files on its own thread (the real compile_table);
        # Windows refuses to unlink a file a reader still holds
        # (WinError 32 - observed in the 0.32 in-build suite), so stop
        # the worker and reset the store before a test mutates or
        # removes a table file (the MT-22 / MT-16 guard pattern).  The
        # MT-23 status assertions are computed at render time and do
        # not depend on the worker.
        if app.analysis_worker is not None:
            app.analysis_worker.stop()
            app.analysis_worker = None
        app.analysis_store.clear()


@unittest.skipIf(tk is None, "tkinter not available")
class StatusFilterWiringTests(_WaitingViewBase):
    """MT-23 (0.31): the persisted status-filter cycle (schema 6)."""

    def test_the_button_starts_on_all_and_cycles(self):
        app = self._app()
        self.window = self._window(app)
        self.assertEqual(self.window._status_btn.cget("text"),
                         "Status: all")
        self.window._cycle_status_filter()
        self.assertEqual(self.window._status_btn.cget("text"), "Status: ok")
        stored = load_master_state(
            Path(self.state_home) / MASTER_STATE_FILENAME)
        self.assertEqual(stored.view_status, "ok")
        self.window._cycle_status_filter()
        self.assertEqual(self.window._status_btn.cget("text"),
                         "Status: attention")
        self.window._cycle_status_filter()
        self.assertEqual(self.window._status_btn.cget("text"), "Status: all")
        stored = load_master_state(
            Path(self.state_home) / MASTER_STATE_FILENAME)
        self.assertEqual(stored.view_status, "")

    def test_the_window_restores_the_persisted_mode(self):
        app = self._app()
        app.set_view_settings(None, "name", "list", "attention")
        self.window = self._window(app)
        self.assertEqual(self.window._status_btn.cget("text"),
                         "Status: attention")
        self.assertEqual(self.window._status_filter, "attention")

    def test_the_other_ui_changes_keep_the_status_filter(self):
        app = self._app()
        app.set_view_settings(None, "name", "list", "attention")
        self.window = self._window(app)
        self.window._cycle_sort()
        self.window._cycle_view()
        self.window._filter_entry.insert(0, "zeta")
        self.window._on_filter_edit(None)
        stored = load_master_state(
            Path(self.state_home) / MASTER_STATE_FILENAME)
        self.assertEqual(stored.view_status, "attention")

    def test_set_view_settings_refuses_an_unknown_mode(self):
        app = self._app()
        with self.assertRaises(ValueError) as ctx:
            app.set_view_settings("", "name", "list", "all")
        self.assertIn("status filter mode", str(ctx.exception))
        self.assertEqual(app.view_status, "")

    def test_the_ok_and_attention_modes_shape_the_row_set(self):
        (self.folder / "second.ct").write_text(CT_GAMEB, encoding="utf-8")
        app = self._app()
        self.window = self._window(app)
        self._stop_analysis(app)
        (self.folder / "second.ct").write_bytes(b"x" * 500)
        self.window._status_filter = "attention"
        self.window._render_tables()
        rows = self._rows()
        self.assertEqual(list(rows), ["second.ct"])
        self.window._status_filter = "ok"
        self.window._render_tables()
        rows = self._rows()
        self.assertEqual(list(rows), ["zeta.ct"])


@unittest.skipIf(tk is None, "tkinter not available")
class LiveStatusWiringTests(_WaitingViewBase):
    """MT-23 (0.31): the live Status column + color coding."""

    def test_the_attention_tags_are_configured(self):
        app = self._app()
        self.window = self._window(app)
        tree = self.window._table_tree
        # The ttk 'tag configure <tag>' query (the flat option/value
        # list) - queried through the Tcl path, so the test does not
        # depend on the Python binding exposing the subcommand.
        def foreground_of(tag):
            values = [str(v) for v in
                      tree.tk.call(tree, "tag", "configure", tag)]
            return values[values.index("-foreground") + 1]
        self.assertEqual(foreground_of("attention-warn"), "#e5c07b")
        self.assertEqual(foreground_of("attention-error"), "#ff7b72")

    def test_a_changed_table_is_flagged_live(self):
        (self.folder / "second.ct").write_text(CT_GAMEB, encoding="utf-8")
        app = self._app()
        self.window = self._window(app)
        self._stop_analysis(app)
        (self.folder / "second.ct").write_bytes(b"x" * 500)
        self.window._render_tables()
        rows = self._rows()
        values, tags = rows["second.ct"]
        # MT-26 (0.34): the Status column shifted right of the new
        # Folder column.
        self.assertEqual(values[3], "changed")
        self.assertIn("Rescan", values[4])
        self.assertIn("attention-warn", tags)
        values, tags = rows["zeta.ct"]
        self.assertEqual(values[3], "ok")
        self.assertNotIn("attention-warn", tags)
        self.assertNotIn("attention-error", tags)

    def test_a_missing_table_is_flagged_live(self):
        (self.folder / "second.ct").write_text(CT_GAMEB, encoding="utf-8")
        app = self._app()
        self.window = self._window(app)
        self._stop_analysis(app)
        (self.folder / "second.ct").unlink()
        self.window._render_tables()
        values, tags = self._rows()["second.ct"]
        self.assertEqual(values[3], "missing")
        self.assertIn("Rescan", values[4])
        self.assertIn("attention-error", tags)

    def test_a_running_process_stays_running_only_when_loadable(self):
        from ct2trainer.native.master_trainer.process_watch import (
            ProcessSnapshotEntry)
        (self.folder / "second.ct").write_text(CT_GAMEB, encoding="utf-8")
        process = ProcessSnapshotEntry(7, "GameA.exe")
        app = _make_app(self.folder, self.state_home, [process])
        app.orchestrator.suppress("gamea.exe", 7)
        self.window = self._window(app)
        self._stop_analysis(app)
        self.window._poll()
        rows = self._rows()
        self.assertEqual(rows["zeta.ct"][0][3], "running")
        # Drift the table: the running process cannot make it loadable.
        (self.folder / "zeta.ct").write_bytes(b"x" * 700)
        self.window._render_tables()
        rows = self._rows()
        self.assertEqual(rows["zeta.ct"][0][3], "changed")

    def test_the_meta_line_carries_the_status_filter_and_count(self):
        (self.folder / "second.ct").write_text(CT_GAMEB, encoding="utf-8")
        app = self._app()
        self.window = self._window(app)
        self._stop_analysis(app)
        meta = self.window._meta_text()
        self.assertNotIn("attention:", meta)
        self.assertNotIn("status filter:", meta)
        (self.folder / "second.ct").write_bytes(b"x" * 500)
        meta = self.window._meta_text()
        self.assertIn("attention: 1", meta)
        self.window._status_filter = "attention"
        meta = self.window._meta_text()
        self.assertIn("status filter: attention", meta)
