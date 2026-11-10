"""Master Trainer 0.40: process identification in picker + details (MT-31).

Covers the Tk wiring on top of the pure MT-31 layers: the process
picker rows carry the bounded per-candidate identification (path /
started / bitness) rendered by ``candidate_display_text`` over the
enriched candidates; a refused or partial enrichment keeps the name +
PID row form (byte-stable against the pre-0.40 format while
unenriched); the picker choice still pins the chosen pid (the
enrichment never changes the decision fields); the table-details
"Running now" row renders the enriched candidates (and the name +
PID form while the enrichment is refused, "not running" for an empty
candidate set); and the waiting-view "Running now" line keeps its
cheap name + PID form even for enriched entries (the auto-rescan tick
never enriches).

The enrichment seam is ``master_ui.enrich_candidates`` (patched in
every full-flow test); the pure layers are covered by
``test_native_master_process_watch.py`` and
``test_native_master_process_picker.py``.  ``TrainerEngine`` /
``TrainerWindow`` are patched; no real process is attached.
"""
from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

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
from ct2trainer.native.master_trainer.master_state import ATTACH_MODE_ASK
from ct2trainer.native.master_trainer.process_picker import (
    candidate_display_text,
)
from ct2trainer.native.master_trainer.process_watch import ProcessSnapshotEntry

ENRICHMENT_PATCH = "ct2trainer.native.master_trainer.master_ui" \
    ".enrich_candidates"


def _enriched(entry: ProcessSnapshotEntry) -> ProcessSnapshotEntry:
    """The full MT-31 identification for a test candidate."""
    return replace(entry, path="C:\\games\\" + entry.name,
                   creation_time=1700000000.0, pointer_size=8)


def _partial_enricher(path_only: bool):
    """A seam enricher that proves only the path fact (the other
    facts stay refused: the row must render only what was proved)."""
    def enrich(candidates):
        return tuple(replace(e, path="C:\\games\\" + e.name)
                     if path_only else e for e in candidates)
    return enrich


@unittest.skipIf(tk is None, "tkinter not available")
class ProcessPickerIdentificationTests(unittest.TestCase):
    """The picker rows carry the bounded per-candidate identification."""

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

    def _app(self, entries=None):
        # The orchestrator takes the lister at construction, so the
        # candidate set is fixed here (never swapped later).
        if entries is None:
            entries = [self.process]
        return MasterApp(self.folder, state_home=self.state_home,
                         poll_ms=50,
                         lister=_FakeLister(entries),
                         plan_compiler=lambda e, n:
                         {"title": "T", "relative_path": e.relative_path})

    def _window(self, app):
        window = MasterWindow(self.root, app)
        # Ask mode: the picker opens on the auto-load request.
        window.app.attach_mode = ATTACH_MODE_ASK
        return window

    def test_picker_rows_carry_the_full_identification(self):
        app = self._app()
        window = self._window(app)
        with patch(ENRICHMENT_PATCH,
                   side_effect=lambda candidates:
                   tuple(_enriched(e) for e in candidates)):
            window._poll()
        self.assertIsNotNone(window._proc_picker)
        listbox = window._proc_picker_listbox
        self.assertEqual(listbox.get(0),
                         candidate_display_text(_enriched(self.process)))
        # The identification facts are visible on the row.
        self.assertIn("  -  C:\\games\\GameA.exe", listbox.get(0))
        self.assertIn("  -  64-bit", listbox.get(0))
        # The stored candidates are the enriched ones; the decision
        # fields (pid / name) are unchanged by the enrichment.
        self.assertEqual(window._proc_picker_candidates,
                         (_enriched(self.process),))
        self.assertEqual(window._proc_picker_candidates[0].pid, 7)
        window._close_proc_picker()

    def test_a_partial_enrichment_renders_only_the_proved_fact(self):
        app = self._app()
        window = self._window(app)
        with patch(ENRICHMENT_PATCH,
                   side_effect=_partial_enricher(path_only=True)):
            window._poll()
        listbox = window._proc_picker_listbox
        self.assertEqual(listbox.get(0),
                         "GameA.exe  (PID 7)  -  C:\\games\\GameA.exe")
        # The unproved facts never render.
        self.assertNotIn("started", listbox.get(0))
        self.assertNotIn("-bit", listbox.get(0))
        window._close_proc_picker()

    def test_a_refused_enrichment_keeps_the_pre_040_row_form(self):
        app = self._app()
        window = self._window(app)
        with patch(ENRICHMENT_PATCH,
                   side_effect=lambda candidates: candidates):
            window._poll()
        listbox = window._proc_picker_listbox
        self.assertEqual(listbox.get(0), "GameA.exe  (PID 7)")
        window._close_proc_picker()

    def test_several_candidates_all_get_identification_rows(self):
        second = ProcessSnapshotEntry(9, "GameA.exe")
        app = self._app(entries=[self.process, second])
        window = self._window(app)
        with patch(ENRICHMENT_PATCH,
                   side_effect=lambda candidates:
                   tuple(_enriched(e) for e in candidates)):
            window._poll()
        listbox = window._proc_picker_listbox
        self.assertEqual(listbox.get(0),
                         candidate_display_text(_enriched(self.process)))
        self.assertEqual(listbox.get(1),
                         candidate_display_text(_enriched(second)))
        window._close_proc_picker()

    def test_the_picker_choice_still_pins_the_pid_when_enriched(self):
        app = self._app()
        window = self._window(app)
        with patch(ENRICHMENT_PATCH,
                   side_effect=lambda candidates:
                   tuple(_enriched(e) for e in candidates)):
            window._poll()
        with patch("ct2trainer.native.master_trainer.master_ui"
                   ".TrainerEngine") as engine_cls, \
                patch("ct2trainer.native.master_trainer.master_ui"
                      ".TrainerWindow"):
            window._proc_picker_chosen(0)
        self.assertEqual(window._attach_pin, {"pid": 7})
        self.assertIs(window.engine, engine_cls.return_value)


@unittest.skipIf(tk is None, "tkinter not available")
class DetailsRunningNowTests(unittest.TestCase):
    """The table-details "Running now" row renders the enriched
    candidates (MT-31)."""

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

    def _app(self):
        return MasterApp(self.folder, state_home=self.state_home,
                         poll_ms=50,
                         lister=_FakeLister([self.process]),
                         plan_compiler=lambda e, n:
                         {"title": "T", "relative_path": e.relative_path})

    def _window(self, app):
        return MasterWindow(self.root, app)

    @staticmethod
    def _rows(win):
        """The details rows as a label -> value dict (the value labels
        carry wraplength=520; the row labels width=22)."""
        labels = [w for w in _all_widgets(win) if isinstance(w, tk.Label)]
        rows = {}
        label = None
        for w in labels:
            if w.cget("width") == 22:
                label = str(w.cget("text"))
            elif w.cget("wraplength") == 520 and label is not None:
                rows[label] = str(w.cget("text"))
                label = None
        return rows

    def test_running_now_renders_the_enriched_candidates(self):
        app = self._app()
        window = self._window(app)
        window._running = (self.process,)
        with patch(ENRICHMENT_PATCH,
                   side_effect=lambda candidates:
                   tuple(_enriched(e) for e in candidates)):
            window._open_table_details("a.ct")
        win = window._details_win
        self.assertIsNotNone(win)
        self.addCleanup(win.destroy)
        rows = self._rows(win)
        self.assertEqual(rows["Running now"],
                         candidate_display_text(_enriched(self.process)))
        self.assertIn("  -  C:\\games\\GameA.exe", rows["Running now"])
        self.assertIn("  -  64-bit", rows["Running now"])

    def test_running_now_refused_enrichment_keeps_the_name_pid_form(self):
        app = self._app()
        window = self._window(app)
        window._running = (self.process,)
        with patch(ENRICHMENT_PATCH,
                   side_effect=lambda candidates: candidates):
            window._open_table_details("a.ct")
        win = window._details_win
        self.assertIsNotNone(win)
        self.addCleanup(win.destroy)
        self.assertEqual(self._rows(win)["Running now"],
                         "GameA.exe  (PID 7)")

    def test_running_now_empty_candidate_set_says_not_running(self):
        app = self._app()
        window = self._window(app)
        window._running = ()  # nothing of the bound processes visible
        with patch(ENRICHMENT_PATCH,
                   side_effect=lambda candidates: candidates):
            window._open_table_details("a.ct")
        win = window._details_win
        self.assertIsNotNone(win)
        self.addCleanup(win.destroy)
        self.assertEqual(self._rows(win)["Running now"], "not running")

    def test_several_running_candidates_render_sorted_by_pid(self):
        second = ProcessSnapshotEntry(3, "GameA.exe")
        app = self._app()
        window = self._window(app)
        # The details row renders the candidates the waiting view
        # currently sees (window._running), not the lister snapshot.
        window._running = (self.process, second)
        with patch(ENRICHMENT_PATCH,
                   side_effect=lambda candidates:
                   tuple(_enriched(e) for e in candidates)):
            window._open_table_details("a.ct")
        win = window._details_win
        self.assertIsNotNone(win)
        self.addCleanup(win.destroy)
        rows = self._rows(win)
        expected = candidate_display_text(_enriched(second)) + "; " \
            + candidate_display_text(_enriched(self.process))
        self.assertEqual(rows["Running now"], expected)


@unittest.skipIf(tk is None, "tkinter not available")
class WaitingViewRunningLineTests(unittest.TestCase):
    """The waiting-view "Running now" line stays cheap (name + PID
    only) even for enriched entries - the auto-rescan tick never
    enriches (MT-31 display-side-only contract)."""

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

    def _window(self):
        app = MasterApp(self.folder, state_home=self.state_home,
                        poll_ms=50,
                        lister=_FakeLister([self.process]),
                        plan_compiler=lambda e, n:
                        {"title": "T", "relative_path": e.relative_path})
        return MasterWindow(self.root, app)

    def test_the_running_line_keeps_the_cheap_form_for_enriched_entries(self):
        window = self._window()
        enriched = _enriched(self.process)
        text = window._running_text((enriched,))
        self.assertEqual(text, "Running now: GameA.exe (PID 7)")

    def test_the_running_line_groups_same_name_pids(self):
        window = self._window()
        second = _enriched(ProcessSnapshotEntry(9, "GameA.exe"))
        text = window._running_text((_enriched(self.process), second))
        self.assertEqual(text, "Running now: GameA.exe (PID 7, 9)")

    def test_the_running_line_names_the_absent_state(self):
        window = self._window()
        self.assertEqual(
            window._running_text(()),
            "Running now: (none of the bound processes)")


if __name__ == "__main__":
    unittest.main()
