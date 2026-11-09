"""Master Trainer 0.30: waiting-view table details + live gate preview.

Covers the new pure builder ``table_details.py`` (the ordered
(label, value) rows for the read-only details window, the size /
mtime / gate-line formatters, the sha truncation, the named
fallbacks) and the Tk wiring on top of the unchanged layers: the row
context menu offers "Table details" first, the details Toplevel
renders the indexed facts plus the on-demand
``gate_table_for_load`` re-check (the same pass MT-9 runs at load
time - named refusal code + displayable detail), a second open lifts
the window instead of duplicating it, and the window closes on
trainer entry with the rest of the waiting view.  No real process is
attached (a _FakeLister stands in).
"""
from __future__ import annotations

import re
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

try:
    import tkinter as tk
except ImportError:  # pragma: no cover - environment without Tcl/Tk
    tk = None

from test_native_master_ui import (CT_GAMEA, _all_widgets, _make_app)

from native_tk_teardown import force_root_release

from ct2trainer.native.master_trainer import table_details
from ct2trainer.native.master_trainer.process_watch import (
    ProcessSnapshotEntry)
from ct2trainer.native.master_trainer.table_gate import TableGateResult
from ct2trainer.native.master_trainer.table_index import TableEntry


def _entry(**over) -> TableEntry:
    base = dict(
        relative_path="a/b.ct",
        size=3572,
        mtime_ns=1_760_000_000_000_000_000,
        sha256="0123456789abcdef" * 8,
        process_names=("GameA.exe", "GameB.exe"),
        status="ok",
        detail=None,
    )
    base.update(over)
    return TableEntry(**base)


class FormatTests(unittest.TestCase):
    """The pure formatters of the details window (no I/O, no Tk)."""

    def test_format_size_boundaries(self):
        self.assertEqual(table_details.format_size(0), "0 B")
        self.assertEqual(table_details.format_size(1023), "1023 B")
        self.assertEqual(table_details.format_size(1024), "1 KB")
        self.assertEqual(table_details.format_size(1536), "1 KB")
        self.assertEqual(table_details.format_size(1024 * 1024 - 1),
                         "1023 KB")
        self.assertEqual(table_details.format_size(1024 * 1024), "1.0 MB")
        self.assertEqual(table_details.format_size(15 * 1024 * 1024 + 9),
                         "15.0 MB")

    def test_format_mtime_is_local_compact(self):
        out = table_details.format_mtime(1_760_000_000_000_000_000)
        self.assertEqual(
            out,
            datetime.fromtimestamp(1_760_000_000).strftime(
                "%Y-%m-%d %H:%M"))
        self.assertRegex(out, r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}")

    def test_gate_line_states(self):
        self.assertEqual(table_details.gate_line(None), "not checked")
        self.assertEqual(
            table_details.gate_line(TableGateResult(True, size=10)),
            "OK (loadable - the file matches the last scan)")
        refusal = TableGateResult(False, code="table-empty",
                                  detail="table file is empty (0 bytes): x")
        self.assertEqual(
            table_details.gate_line(refusal),
            "table-empty: table file is empty (0 bytes): x")
        # A refusal without either part falls back to named placeholders.
        self.assertEqual(
            table_details.gate_line(TableGateResult(False)),
            "?: no detail")


class DetailLinesTests(unittest.TestCase):
    """The ordered (label, value) rows of the read-only window."""

    def test_rows_carry_all_indexed_facts_in_order(self):
        gate = TableGateResult(True, size=3572,
                               sha256="0123456789abcdef" * 8)
        lines = table_details.table_detail_lines(
            _entry(), root="C:\\tables", pinned=True,
            last_used="2026-11-04T09:00:00Z",
            running_pids=[7], gate=gate)
        labels = [label for label, _ in lines]
        self.assertEqual(labels, [
            "Table", "Folder", "Size", "Modified",
            "Bound process(es)", "Index status", "Pinned",
            "Last used", "Running now", "Content sha256 (last scan)",
            "Load gate (live re-check)",
            # MT-24 (0.32): the entry-analysis block (pending marker
            # when no analysis entry is passed).
            "Entry analysis",
            # MT-27 (0.35): the per-table note / tag rows.
            "Note", "Tags"])
        values = dict(lines)
        self.assertEqual(values["Table"], "a/b.ct")
        self.assertEqual(values["Folder"], "C:\\tables")
        self.assertEqual(values["Size"], "3 KB")
        self.assertEqual(values["Bound process(es)"],
                         "GameA.exe, GameB.exe")
        self.assertEqual(values["Index status"], "ok")
        self.assertEqual(values["Pinned"], "yes")
        self.assertEqual(values["Last used"], "2026-11-04T09:00:00Z")
        self.assertEqual(values["Running now"], "PID 7")
        self.assertEqual(
            values["Content sha256 (last scan)"], "0123456789ab" + "...")
        self.assertEqual(values["Load gate (live re-check)"],
                         "OK (loadable - the file matches the last scan)")
        self.assertEqual(values["Entry analysis"],
                         "not analyzed yet (the background analysis "
                         "is pending)")

    def test_unreadable_entry_shows_the_named_reason(self):
        lines = table_details.table_detail_lines(
            _entry(status="unreadable", detail="bad xml"),
            root="r", pinned=False, last_used=None,
            running_pids=[], gate=None)
        values = dict(lines)
        self.assertEqual(values["Index status"], "unreadable: bad xml")
        self.assertEqual(values["Pinned"], "no")
        self.assertEqual(values["Last used"], "never")
        self.assertEqual(values["Running now"], "not running")
        self.assertEqual(values["Load gate (live re-check)"],
                         "not checked")

    def test_unreadable_entry_without_detail_falls_back(self):
        lines = table_details.table_detail_lines(
            _entry(status="unreadable", detail=None),
            root="r", pinned=False, last_used=None,
            running_pids=[], gate=None)
        self.assertEqual(dict(lines)["Index status"],
                         "unreadable: no detail")

    def test_no_bound_processes_is_named(self):
        lines = table_details.table_detail_lines(
            _entry(process_names=()), root="r", pinned=False,
            last_used=None, running_pids=[], gate=None)
        self.assertEqual(dict(lines)["Bound process(es)"],
                         "(none found)")

    def test_running_pids_are_deduped_and_sorted(self):
        lines = table_details.table_detail_lines(
            _entry(), root="r", pinned=False, last_used=None,
            running_pids=[7, 3, 7], gate=None)
        self.assertEqual(dict(lines)["Running now"], "PID 3, 7")


class _DetailsBase(unittest.TestCase):
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
        from ct2trainer.native.master_trainer.master_ui import (
            MasterWindow)
        return MasterWindow(self.root, app)

    def _mock_engine(self):
        engine = MagicMock()
        engine.close.return_value = True
        return engine

    def _value_rows(self, win):
        """The details value column (the labels carry wraplength=520)."""
        labels = [w for w in _all_widgets(win) if isinstance(w, tk.Label)]
        return [str(w.cget("text"))
                for w in labels if w.cget("wraplength") == 520]


@unittest.skipIf(tk is None, "tkinter not available")
class RowMenuTests(_DetailsBase):
    """The row context menu leads with the read-only details."""

    def _row_and_menu(self, window):
        rows = [c for c in window._table_tree.get_children()
                if window._is_table_row(c)]
        self.assertTrue(rows)
        created = []

        class Rec(tk.Menu):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.commands = []

            def add_command(self, label="", command=None, **kwargs):
                self.commands.append((label, command))
                return super().add_command(label=label, command=command,
                                           **kwargs)

            def tk_popup(self, *args, **kwargs):
                pass  # never actually pop in the tests

        def factory(*args, **kwargs):
            menu = Rec(*args, **kwargs)
            created.append(menu)
            return menu

        return rows[0], created, factory

    def test_row_menu_offers_table_details_first(self):
        app = self._app()
        window = self._window(app)
        item, created, factory = self._row_and_menu(window)
        with patch("tkinter.Menu", factory), \
                patch.object(window._table_tree, "identify_row",
                             return_value=item):
            window._table_context_menu(MagicMock(y=0, x_root=0, y_root=0))
        self.assertEqual(len(created), 1)
        labels = [label for label, _ in created[0].commands]
        self.assertEqual(labels[0], "Table details")
        self.assertEqual(labels[1], "Load this table")
        self.assertEqual(labels[-1], "Pin to top")

    def test_details_command_opens_the_window_for_that_row(self):
        app = self._app()
        window = self._window(app)
        item, created, factory = self._row_and_menu(window)
        with patch("tkinter.Menu", factory), \
                patch.object(window._table_tree, "identify_row",
                             return_value=item):
            window._table_context_menu(MagicMock(y=0, x_root=0, y_root=0))
        label, command = created[0].commands[0]
        self.assertEqual(label, "Table details")
        command()
        win = window._details_win
        self.assertIsNotNone(win)
        self.assertTrue(win.winfo_exists())
        self.addCleanup(win.destroy)
        self.assertEqual(win.title(), "Table details - zeta.ct")


@unittest.skipIf(tk is None, "tkinter not available")
class DetailsWindowTests(_DetailsBase):
    """The read-only details window + the live load-gate preview."""

    def test_window_opens_with_the_indexed_facts(self):
        app = self._app()
        window = self._window(app)
        # MT-24 (0.32): keep the background plan analysis from racing
        # the assertion - stop the worker and reset the store, so the
        # entry is deterministically pending.
        if app.analysis_worker is not None:
            app.analysis_worker.stop()
            app.analysis_worker = None
        app.analysis_store.clear()
        window._running = (self.process,)
        window._open_table_details("zeta.ct")
        win = window._details_win
        self.assertIsNotNone(win)
        self.assertTrue(win.winfo_exists())
        self.addCleanup(win.destroy)
        self.assertEqual(win.title(), "Table details - zeta.ct")
        values = self._value_rows(win)
        # MT-27 (0.35): the details window gained the Note / Tags
        # rows (12 base rows + 2 note rows = 14).
        self.assertEqual(len(values), 14)
        entry = app.index.get("zeta.ct")
        self.assertEqual(values[0], "zeta.ct")
        self.assertEqual(values[1], app.folder)
        self.assertEqual(values[2], table_details.format_size(entry.size))
        self.assertRegex(values[3], r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}")
        self.assertEqual(values[4], "GameA.exe")
        self.assertEqual(values[5], "ok")
        self.assertEqual(values[6], "no")
        self.assertEqual(values[7], "never")
        self.assertEqual(values[8], "PID 7")
        self.assertEqual(values[9], entry.sha256[:12] + "...")
        self.assertEqual(
            values[10], "OK (loadable - the file matches the last scan)")
        # MT-24 (0.32): the pending analysis entry is displayed.
        self.assertEqual(values[11],
                         "not analyzed yet (the background analysis "
                         "is pending)")

    def test_window_lifts_on_second_open(self):
        app = self._app()
        window = self._window(app)
        window._open_table_details("zeta.ct")
        first = window._details_win
        window._open_table_details("zeta.ct")
        # A second open lifts the window, never opens a duplicate.
        self.assertIs(first, window._details_win)
        self.assertTrue(first.winfo_exists())
        self.addCleanup(first.destroy)

    def test_window_closes_on_trainer_entry(self):
        app = self._app()
        window = self._window(app)
        window._open_table_details("zeta.ct")
        win = window._details_win
        self.assertTrue(win.winfo_exists())
        engine = self._mock_engine()
        entry = app.index.entries_for_process("GameA.exe")[0]
        with patch("ct2trainer.native.master_trainer.master_ui"
                   ".TrainerEngine", return_value=engine), \
                patch("ct2trainer.native.master_trainer.master_ui"
                      ".TrainerWindow"), \
                patch("ct2trainer.native.master_trainer.master_ui"
                      ".messagebox"):
            window._start_load(entry, self.process)
        self.assertFalse(win.winfo_exists())
        self.assertIsNone(window._details_win)

    def test_window_missing_index_entry_leaves_no_window(self):
        app = self._app()
        window = self._window(app)
        window._open_table_details("ghost.ct")
        self.assertIsNone(window._details_win)
        self.assertIn("No index entry for ghost.ct",
                      str(window._status_var.get()))

    def test_window_shows_the_gate_refusal_code_and_detail(self):
        app = self._app()
        window = self._window(app)
        refusal = TableGateResult(
            False, code="table-file-missing",
            detail="table file is missing (deleted after the last scan)")
        with patch("ct2trainer.native.master_trainer.table_gate"
                   ".gate_table_for_load", return_value=refusal):
            window._open_table_details("zeta.ct")
        win = window._details_win
        self.assertTrue(win.winfo_exists())
        self.addCleanup(win.destroy)
        values = self._value_rows(win)
        self.assertEqual(
            values[10],
            "table-file-missing: table file is missing "
            "(deleted after the last scan)")

    def test_window_shows_the_last_used_timestamp_when_known(self):
        app = self._app()
        app.recent_tables = (("zeta.ct", "2026-11-04T09:00:00Z"),)
        window = self._window(app)
        window._open_table_details("zeta.ct")
        win = window._details_win
        self.assertTrue(win.winfo_exists())
        self.addCleanup(win.destroy)
        values = self._value_rows(win)
        self.assertEqual(values[7], "2026-11-04T09:00:00Z")


if __name__ == "__main__":
    unittest.main()
