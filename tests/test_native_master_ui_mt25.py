"""Master Trainer 0.33: table folder auto-rescan (MT-25).

Covers the persisted auto-rescan flag (master-state schema 7) and the
Tk wiring of the interval re-scan: the status-bar toggle button
(present with the on/off text, flips the flag and persists it, a
failed change lands in the status line without a state change), and
the interval clock of ``_poll`` (a poll after one interval re-runs
the incremental reconcile so a newly added table shows up, without
the "Rescanning…" status flash; a disabled flag skips it; trainer
mode skips it; a manual rescan restarts the clock so no immediate
second pass happens).  The deterministic tests use a fake plan
compiler; no real process is attached.
"""
from __future__ import annotations

import hashlib
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

try:
    import tkinter as tk
except ImportError:  # pragma: no cover - environment without Tcl/Tk
    tk = None

from test_native_master_ui import CT_GAMEA, CT_GAMEB, _make_app

from native_tk_teardown import force_root_release

from ct2trainer.native.master_trainer.analysis_worker import AnalysisWorker
from ct2trainer.native.master_trainer.master_state import (
    MASTER_STATE_FILENAME, MASTER_STATE_SCHEMA, MasterState,
    load_master_state, save_master_state)
from ct2trainer.native.master_trainer.master_ui import (
    AUTO_RESCAN_INTERVAL_SECONDS, MasterWindow)


def _file_sha(folder: Path, rel: str) -> str:
    return hashlib.sha256((folder / rel).read_bytes()).hexdigest()


def _plan(sha: str) -> dict:
    """One deterministic plan (the worker cross-checks the table
    content sha inside it)."""
    return {"schema": 2, "table_sha256": sha, "entries": [
        {"id": 1, "supported": True, "kind": "value", "reason": ""},
    ]}


@unittest.skipIf(tk is None, "tkinter not available")
class _Mt25Base(unittest.TestCase):
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

    def _stored(self):
        return load_master_state(Path(self.state_home)
                                 / MASTER_STATE_FILENAME)

    def _fake_compiler(self):
        def compiler(rel, name):
            return _plan(_file_sha(self.folder, rel))
        return compiler

    def _expire_interval(self, window):
        window._last_auto_rescan = (time.monotonic()
                                    - AUTO_RESCAN_INTERVAL_SECONDS - 1)

    def _add_second_table(self):
        (self.folder / "b.ct").write_text(CT_GAMEB, encoding="utf-8")


@unittest.skipIf(tk is None, "tkinter not available")
class AutoRescanStateTests(_Mt25Base):
    """MT-25 (0.33): the persisted auto-rescan flag (schema 7)."""

    def test_a_fresh_state_home_defaults_to_on(self):
        app = self._app()
        self.assertTrue(app.auto_rescan)

    def test_a_stored_flag_is_restored(self):
        save_master_state(MasterState(MASTER_STATE_SCHEMA,
                                      str(self.folder),
                                      auto_rescan=False),
                          Path(self.state_home) / MASTER_STATE_FILENAME)
        app = self._app()
        self.assertFalse(app.auto_rescan)

    def test_set_auto_rescan_persists_a_schema7_document(self):
        app = self._app()
        app.set_auto_rescan(False)
        stored = self._stored()
        self.assertIsNotNone(stored)
        self.assertEqual(stored.schema, MASTER_STATE_SCHEMA)
        self.assertFalse(stored.auto_rescan)

    def test_set_auto_rescan_refuses_non_booleans(self):
        app = self._app()
        for bad in (1, 0, "on", None):
            with self.assertRaises(ValueError):
                app.set_auto_rescan(bad)
        # The refusal is fail-closed: the flag and the state home are
        # untouched (no partial write).
        self.assertTrue(app.auto_rescan)
        self.assertIsNone(self._stored())


@unittest.skipIf(tk is None, "tkinter not available")
class AutoRescanWiringTests(_Mt25Base):
    """MT-25 (0.33): the status-bar toggle and the interval re-scan."""

    def test_the_toggle_is_present_and_defaults_to_on(self):
        window = self._window(self._app())
        self.assertIsNotNone(window._auto_rescan_btn)
        self.assertEqual(str(window._auto_rescan_btn.cget("text")),
                         "Auto-rescan: on")

    def test_the_toggle_flips_the_flag_and_persists(self):
        window = self._window(self._app())
        window._auto_rescan_btn.invoke()
        self.assertFalse(self.app.auto_rescan)
        self.assertEqual(str(window._auto_rescan_btn.cget("text")),
                         "Auto-rescan: off")
        self.assertFalse(self._stored().auto_rescan)
        window._auto_rescan_btn.invoke()
        self.assertTrue(self.app.auto_rescan)
        self.assertEqual(str(window._auto_rescan_btn.cget("text")),
                         "Auto-rescan: on")
        self.assertTrue(self._stored().auto_rescan)

    def test_a_failed_toggle_lands_in_the_status_line(self):
        window = self._window(self._app())
        window.app.set_auto_rescan = MagicMock(
            side_effect=ValueError("boom"))
        window._auto_rescan_btn.invoke()
        self.assertTrue(self.app.auto_rescan)
        self.assertEqual(str(window._auto_rescan_btn.cget("text")),
                         "Auto-rescan: on")
        self.assertIn("Auto-rescan change failed: boom",
                      str(window._status_var.get()))

    def test_a_poll_after_the_interval_rescans_without_a_flash(self):
        window = self._window(self._app(), self._fake_compiler())
        self._add_second_table()
        self.assertIsNone(self.app.index.get("b.ct"))
        self._expire_interval(window)
        window._poll()
        # The incremental reconcile picked up the added table.
        self.assertIsNotNone(self.app.index.get("b.ct"))
        # The interval clock restarted with the pass.
        self.assertLess(time.monotonic() - window._last_auto_rescan, 5)
        # No status-line flash (the line keeps the waiting content).
        self.assertNotIn("Rescanning", str(window._status_var.get()))

    def test_a_poll_inside_the_interval_does_not_rescan(self):
        window = self._window(self._app(), self._fake_compiler())
        self._add_second_table()
        window._poll()  # the clock was armed at the window build
        self.assertIsNone(self.app.index.get("b.ct"))

    def test_a_disabled_flag_skips_the_auto_rescan(self):
        window = self._window(self._app(), self._fake_compiler())
        window.app.set_auto_rescan(False)
        self._add_second_table()
        self._expire_interval(window)
        window._poll()
        self.assertIsNone(self.app.index.get("b.ct"))

    def test_trainer_mode_skips_the_auto_rescan(self):
        window = self._window(self._app(), self._fake_compiler())
        self._add_second_table()
        self._expire_interval(window)
        window.engine = object()  # a trainer is attached
        window._poll()
        self.assertIsNone(self.app.index.get("b.ct"))

    def test_a_manual_rescan_resets_the_interval_clock(self):
        window = self._window(self._app(), self._fake_compiler())
        self._add_second_table()
        window._rescan()  # picks up b.ct and restarts the clock
        self.assertIsNotNone(self.app.index.get("b.ct"))
        self.assertLess(time.monotonic() - window._last_auto_rescan, 5)
        # An immediate follow-up poll must not run a second pass.
        (self.folder / "c.ct").write_text(CT_GAMEB, encoding="utf-8")
        window._poll()
        self.assertIsNone(self.app.index.get("c.ct"))


if __name__ == "__main__":
    unittest.main()
