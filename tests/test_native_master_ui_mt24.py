"""Master Trainer 0.32: per-table entry count + blocked count (MT-24).

Covers the Tk wiring of the background plan analysis on top of the
pure ``table_analysis`` layer: the Entries / Blocked columns (the
pending "…" marker, the counts after the worker finishes, the failed
marker "–", the "N blocked" detail note after the pin marker), the
process-group parent row shape (9 values), the meta line's
"analyzing N table(s)" figure (present while the queue has work,
gone after the poll drain), the queue discipline (known content shas
are skipped, unbound tables are never queued, a rescan re-queues a
changed table), the pause on trainer entry, the worker stop on
close, the window-created default worker (the real ``compile_table``
path), and the details-window analysis rows.  The deterministic
tests inject a fake plan compiler; only the default-worker test
compiles a real (tiny) fixture.  No real process is attached.
"""
from __future__ import annotations

import hashlib
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import tkinter as tk
except ImportError:  # pragma: no cover - environment without Tcl/Tk
    tk = None

from test_native_master_ui import CT_GAMEA, _all_widgets, _make_app

from native_tk_teardown import force_root_release

from ct2trainer.native.master_trainer.analysis_worker import AnalysisWorker
from ct2trainer.native.master_trainer.master_ui import MasterWindow
from ct2trainer.native.master_trainer.process_watch import (
    ProcessSnapshotEntry)
from ct2trainer.native.master_trainer.table_analysis import (
    failed_analysis, ok_analysis)

# A readable table without a single EXE token: the index binds no
# process name to it, so it has nothing to compile against and its
# columns keep the pending marker.
CT_UNBOUND = ('<CheatTable CheatEngineTableVersion="46"><CheatEntries>'
              '<CheatEntry><ID>1</ID><Description>"X"</Description>'
              '<VariableType>4</VariableType><Address>12345678</Address>'
              '<Value>5</Value></CheatEntry>'
              '</CheatEntries></CheatTable>')


def _plan(sha: str) -> dict:
    """One deterministic plan: 6 records - 2 actionable (value /
    script), 1 heading, 3 blocked (r-one x2, r-two x1)."""
    return {"schema": 2, "table_sha256": sha, "entries": [
        {"id": 1, "supported": True, "kind": "value", "reason": ""},
        {"id": 2, "supported": True, "kind": "script", "reason": ""},
        {"id": 3, "supported": True, "kind": "heading", "reason": ""},
        {"id": 4, "supported": False, "kind": "value", "reason": "r-one"},
        {"id": 5, "supported": False, "kind": "script", "reason": "r-two"},
        {"id": 6, "supported": False, "kind": "value", "reason": "r-one"},
    ]}


def _file_sha(folder: Path, rel: str) -> str:
    return hashlib.sha256((folder / rel).read_bytes()).hexdigest()


def _wait_store(app, sha: str, timeout: float = 15.0):
    """The persisted analysis entry for one sha (the worker writes it
    from its own thread); None when the timeout is up."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        entry = app.analysis_store.get(sha)
        if entry is not None:
            return entry
        time.sleep(0.02)
    return app.analysis_store.get(sha)


@unittest.skipIf(tk is None, "tkinter not available")
class _Mt24Base(unittest.TestCase):
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
        return _make_app(self.folder, self.state_home, list(entries))

    def _window(self, app, compiler=None):
        """One waiting-view window; a pre-seeded analysis worker is
        respected (the window resumes + queues, never double-starts)."""
        if app.analysis_worker is None:
            app.analysis_worker = AnalysisWorker(app, compiler=compiler)
        self.addCleanup(self._stop_worker, app)
        app.analysis_worker.start()
        self.window = MasterWindow(self.root, app)
        self.app = app
        return self.window

    @staticmethod
    def _stop_worker(app):
        worker = getattr(app, "analysis_worker", None)
        if worker is not None:
            worker.stop()

    def _row_values(self, rel: str):
        tree = self.window._table_tree
        for child in tree.get_children():
            values = tree.item(child, "values")
            if values and values[0] == rel:
                return list(values)
        self.fail("row for " + rel + " not found in the table tree")

    def _value_rows(self, win):
        """The details value column (the labels carry wraplength=520)."""
        labels = [w for w in _all_widgets(win) if isinstance(w, tk.Label)]
        return [str(w.cget("text"))
                for w in labels if w.cget("wraplength") == 520]


@unittest.skipIf(tk is None, "tkinter not available")
class AnalysisColumnsTests(_Mt24Base):
    """MT-24 (0.32): the Entries / Blocked columns of the waiting view."""

    def test_the_columns_are_there_and_pending_until_analyzed(self):
        gate = threading.Event()
        sha = _file_sha(self.folder, "a.ct")

        def compiler(rel, name):
            gate.wait(timeout=10)
            return _plan(sha)

        window = self._window(self._app(), compiler)
        tree = window._table_tree
        self.assertEqual(list(tree["columns"]), [
            "table", "processes", "status", "detail",
            "entries", "blocked", "size", "modified", "last_used"])
        self.assertEqual(tree.heading("entries")["text"], "Entries")
        self.assertEqual(tree.heading("blocked")["text"], "Blocked")
        self.assertEqual(int(tree.column("entries", "width")), 70)
        self.assertEqual(int(tree.column("blocked", "width")), 70)
        # The worker holds the item behind the gate: both columns
        # carry the pending marker, and the meta line counts the
        # analysis in flight.
        values = self._row_values("a.ct")
        self.assertEqual(values[4:6], ["…", "…"])
        self.assertIn("analyzing 1 table(s)",
                      str(window._meta_label.cget("text")))
        gate.set()
        entry = _wait_store(self.app, sha)
        self.assertEqual(entry["status"], "ok")
        window._poll()
        values = self._row_values("a.ct")
        self.assertEqual(values[4], "2")
        self.assertEqual(values[5], "3")
        # A blocked count > 0 adds the bounded note to the detail
        # column; the counts themselves live in the columns.
        self.assertEqual(values[3], "3 blocked")
        self.assertNotIn("analyzing",
                         str(window._meta_label.cget("text")))

    def test_a_failed_analysis_shows_the_failed_markers(self):
        def compiler(rel, name):
            raise ValueError("boom")

        window = self._window(self._app(), compiler)
        sha = _file_sha(self.folder, "a.ct")
        entry = _wait_store(self.app, sha)
        self.assertEqual(entry["status"], "failed")
        self.assertEqual(entry["error"], "ValueError: boom")
        window._poll()
        values = self._row_values("a.ct")
        # A failed analysis keeps the counts unknown on purpose: the
        # failed marker, never stale numbers - and no blocked note.
        self.assertEqual(values[4:6], ["–", "–"])
        self.assertEqual(values[3], "")

    def test_the_pinned_row_keeps_the_pin_marker_before_the_note(self):
        app = self._app()
        app.set_table_pinned("a.ct", True)
        sha = _file_sha(self.folder, "a.ct")

        def compiler(rel, name):
            return _plan(sha)

        window = self._window(app, compiler)
        entry = _wait_store(app, sha)
        self.assertEqual(entry["status"], "ok")
        window._poll()
        values = self._row_values("a.ct")
        self.assertEqual(values[3], "pinned - 3 blocked")
        self.assertEqual(values[4:6], ["2", "3"])

    def test_the_process_group_parent_row_has_nine_values(self):
        app = self._app()
        app.view_mode = "process"
        sha = _file_sha(self.folder, "a.ct")

        def compiler(rel, name):
            return _plan(sha)

        window = self._window(app, compiler)
        tree = window._table_tree
        parents = tree.get_children()
        self.assertEqual(len(parents), 1)
        values = tree.item(parents[0], "values")
        self.assertEqual(len(values), 9)
        # The display-only group row carries the casefolded bound
        # process name (the MT-17 group identity) and the count -
        # but no Entries / Blocked figures.
        self.assertEqual(values[0], "gamea.exe")
        self.assertEqual(values[1], "1 table(s)")
        self.assertEqual(values[4:6], ("", ""))
        self.assertEqual(len(tree.get_children(parents[0])), 1)


@unittest.skipIf(tk is None, "tkinter not available")
class QueueDisciplineTests(_Mt24Base):
    """MT-24 (0.32): what the waiting view feeds into the worker."""

    def test_unbound_tables_are_never_queued(self):
        (self.folder / "unbound.ct").write_text(CT_UNBOUND,
                                                encoding="utf-8")
        calls = []

        def compiler(rel, name):
            calls.append(rel)
            return _plan(_file_sha(self.folder, rel))

        window = self._window(self._app(), compiler)
        app = self.app
        # The index sees both tables; only the bound one carries names.
        self.assertEqual(app.index.get("unbound.ct").process_names, ())
        entry = _wait_store(app, _file_sha(self.folder, "a.ct"))
        self.assertEqual(entry["status"], "ok")
        window._poll()
        # The compiler only ever sees the bound table.
        self.assertEqual(calls, ["a.ct"])
        self.assertIsNone(
            app.analysis_store.get(_file_sha(self.folder, "unbound.ct")))
        # The unbound row keeps the pending marker (nothing to run).
        values = self._row_values("unbound.ct")
        self.assertEqual(values[4:6], ["…", "…"])

    def test_a_rescan_does_not_requeue_a_known_sha(self):
        calls = []

        def compiler(rel, name):
            calls.append(rel)
            return _plan(_file_sha(self.folder, rel))

        window = self._window(self._app(), compiler)
        app = self.app
        entry = _wait_store(app, _file_sha(self.folder, "a.ct"))
        self.assertEqual(entry["status"], "ok")
        window._rescan()
        # The content did not change: the persisted entry is still
        # valid, so nothing new is queued.
        self.assertEqual(app.analysis_worker.pending_count(), 0)
        time.sleep(0.2)
        self.assertEqual(calls, ["a.ct"])

    def test_a_rescan_requeues_a_changed_table(self):
        calls = []

        def compiler(rel, name):
            calls.append(rel)
            return _plan(_file_sha(self.folder, rel))

        window = self._window(self._app(), compiler)
        app = self.app
        old_sha = _file_sha(self.folder, "a.ct")
        _wait_store(app, old_sha)
        window._poll()
        # An XML comment changes the content (and the sha) without
        # changing the table semantics.
        content = (self.folder / "a.ct").read_text(encoding="utf-8")
        (self.folder / "a.ct").write_text("<!-- c -->\n" + content,
                                          encoding="utf-8")
        new_sha = _file_sha(self.folder, "a.ct")
        self.assertNotEqual(new_sha, old_sha)
        window._rescan()
        entry = _wait_store(app, new_sha)
        self.assertEqual(entry["status"], "ok")
        self.assertEqual(calls.count("a.ct"), 2)
        window._poll()
        values = self._row_values("a.ct")
        self.assertEqual(values[4:6], ["2", "3"])


@unittest.skipIf(tk is None, "tkinter not available")
class DetailsAnalysisRowsTests(_Mt24Base):
    """MT-24 (0.32): the details-window analysis block."""

    def _seed(self, entry):
        app = self._app()
        # Seeded before the window build: the queue pass sees the
        # known sha and never compiles (deterministic rows).
        app.analysis_store.update(_file_sha(self.folder, "a.ct"), entry)
        return app

    def test_the_ok_entry_adds_counts_and_the_top_reasons(self):
        app = self._seed(ok_analysis(
            {"total": 6, "supported": 3, "actionable": 2, "blocked": 3,
             "headings": 1},
            {"r-one": 2, "r-two": 1}, "2026-11-05T00:00:00Z"))
        window = self._window(app)
        window._open_table_details("a.ct")
        win = window._details_win
        self.assertIsNotNone(win)
        self.addCleanup(win.destroy)
        rows = self._value_rows(win)
        self.assertEqual(len(rows), 13)
        self.assertEqual(rows[11], "2 entries (3 blocked) of 6 records")
        self.assertEqual(rows[12], "r-one × 2, r-two × 1")

    def test_the_failed_entry_shows_the_named_error(self):
        app = self._seed(failed_analysis("ValueError: boom",
                                         "2026-11-05T00:00:00Z"))
        window = self._window(app)
        window._open_table_details("a.ct")
        win = window._details_win
        self.assertIsNotNone(win)
        self.addCleanup(win.destroy)
        rows = self._value_rows(win)
        self.assertEqual(len(rows), 12)
        self.assertEqual(rows[11], "failed: ValueError: boom")


@unittest.skipIf(tk is None, "tkinter not available")
class WorkerLifecycleTests(_Mt24Base):
    """MT-24 (0.32): the worker follows the window's modes."""

    def test_trainer_entry_pauses_the_worker(self):
        process = ProcessSnapshotEntry(7, "GameA.exe")
        app = self._app([process])
        sha = _file_sha(self.folder, "a.ct")

        def compiler(rel, name):
            return _plan(sha)

        window = self._window(app, compiler)
        with patch("ct2trainer.native.master_trainer.master_ui"
                   ".TrainerEngine") as engine_cls, \
              patch("ct2trainer.native.master_trainer.master_ui"
                    ".TrainerWindow"), \
              patch("ct2trainer.native.master_trainer.master_ui"
                    ".messagebox"):
            entry = app.index.entries_for_process("GameA.exe")[0]
            window._start_load(entry, process, explicit=True)
        self.assertIs(window.engine, engine_cls.return_value)
        # The window owns the CPU in trainer mode: the background
        # analysis pauses until the waiting view is rebuilt.
        self.assertTrue(app.analysis_worker.paused)

    def test_close_stops_the_worker_and_clears_the_reference(self):
        app = self._app()
        sha = _file_sha(self.folder, "a.ct")

        def compiler(rel, name):
            return _plan(sha)

        window = self._window(app, compiler)
        _wait_store(app, sha)
        window._poll()
        window.close()
        self.assertTrue(app.closed)
        self.assertIsNone(app.analysis_worker)

    def test_the_window_starts_the_default_worker_when_none(self):
        app = self._app()
        self.assertIsNone(app.analysis_worker)
        window = MasterWindow(self.root, app)
        self.window = window
        self.app = app
        self.addCleanup(self._stop_worker, app)
        worker = app.analysis_worker
        self.assertIsInstance(worker, AnalysisWorker)
        self.assertTrue(worker._thread.is_alive())
        # The default path runs the real (tested) compile_table on
        # the fixture: one supported script entry, nothing blocked.
        sha = _file_sha(self.folder, "a.ct")
        entry = _wait_store(app, sha, timeout=30.0)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["status"], "ok")
        self.assertEqual(entry["counts"]["actionable"], 1)
        self.assertEqual(entry["counts"]["blocked"], 0)
        window._poll()
        values = self._row_values("a.ct")
        self.assertEqual(values[4], "1")
        self.assertEqual(values[5], "0")


if __name__ == "__main__":
    unittest.main()
