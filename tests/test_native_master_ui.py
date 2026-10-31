"""Master Trainer UI (MT-4): waiting view, table picker, trainer handoff.

Covers the pure ``MasterApp`` state (folder/index/orchestrator wiring, index
persistence in the state home, rescan/set_folder, corrupted-index tolerance),
the ``run_master`` entry contract, and the real-Tk window behavior: waiting
view construction, the fail-closed poll loop, the auto-load handoff into the
standalone ``TrainerWindow`` (with the ``master_back`` wiring), the startup
recovery prompts (stale state / orphaned receipts / live conflict /
non-convergence), the modal table picker (Load / Not now), the back-to-Master
transition, and the close lifecycle.

``TrainerEngine`` / ``TrainerWindow`` / ``messagebox`` are patched for the
full-flow tests (the same pattern as ``test_native_ui_recovery_flow.py``); no
real process is attached.
"""
from __future__ import annotations

import inspect
import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

try:
    import tkinter as tk
except ImportError:  # pragma: no cover - environment without Tcl/Tk
    tk = None

from ct2trainer import __version__
from ct2trainer.native.engine import (LiveStateConflict,
                                      StaleArtifactsRecoverable,
                                      StaleStateRecoverable)
from ct2trainer.native.master_trainer import master_ui
from ct2trainer.native.master_trainer.master_ui import (MasterApp,
                                                        MasterWindow,
                                                        WAIT_POLL_MS,
                                                        master_title,
                                                        run_master)
from ct2trainer.native.master_trainer.orchestrator import (STATE_ACTIVE,
                                                           STATE_WAITING)
from ct2trainer.native.master_trainer.process_watch import (ProcessLister,
                                                            ProcessSnapshotEntry)
from ct2trainer.native.master_trainer.table_index import (TableIndexRefusal,
                                                          load_index)

CT_GAMEA = '''<CheatTable CheatEngineTableVersion="46"><CheatEntries>
<CheatEntry><ID>1</ID><Description>"HP"</Description>
<VariableType>Auto Assembler Script</VariableType><AssemblerScript>[ENABLE]
assert(GameA.exe+10, 90)
GameA.exe+10:
db CC
[DISABLE]
GameA.exe+10:
db 90
</AssemblerScript></CheatEntry>
</CheatEntries></CheatTable>'''

CT_GAMEB = CT_GAMEA.replace("GameA.exe", "GameB.exe")


class _FakeLister(ProcessLister):
    def __init__(self, entries=(), error=None):
        self.entries = list(entries)
        self.error = error

    def list_processes(self):
        if self.error is not None:
            raise self.error
        return list(self.entries)


def _make_app(folder, state_home, entries=(), compiler=None, error=None):
    if compiler is None:
        def compiler(entry, name):
            return {"title": "T", "relative_path": entry.relative_path}
    return MasterApp(folder, state_home=state_home, poll_ms=50,
                     lister=_FakeLister(entries, error), plan_compiler=compiler)


def _stale_handle() -> StaleStateRecoverable:
    return StaleStateRecoverable(None, "/tmp/state", "/tmp/shared",
                                 "/tmp/archives", "a" * 16, "b" * 64)


def _live_conflict() -> LiveStateConflict:
    return LiveStateConflict(321, 999, "/tmp/state")


def _artifacts_handle() -> StaleArtifactsRecoverable:
    return StaleArtifactsRecoverable(None, "/tmp/state", "/tmp/shared",
                                     "/tmp/archives", "a" * 16, "b" * 64)


def _all_widgets(widget):
    out = []
    for child in widget.winfo_children():
        out.append(child)
        out.extend(_all_widgets(child))
    return out


def _buttons(widget, text):
    return [w for w in _all_widgets(widget)
            if isinstance(w, tk.Button) and str(w.cget("text")) == text]


def _button_texts(widget):
    return {str(b.cget("text")) for b in _all_widgets(widget)
            if isinstance(b, tk.Button)}


class PureMasterUiTests(unittest.TestCase):
    def test_master_title_carries_version(self):
        self.assertEqual(master_title(),
                         "CT2Trainer " + __version__ + " \u2014 Master Trainer")

    def test_wait_poll_ms_default(self):
        self.assertEqual(WAIT_POLL_MS, 1000)


class MasterAppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(self._rmtree)
        self.folder = self.tmp / "tables"
        self.folder.mkdir()
        self.state_home = self.tmp / "state"
        self.state_home.mkdir()
        (self.folder / "a.ct").write_text(CT_GAMEA, encoding="utf-8")
        sub = self.folder / "sub"
        sub.mkdir()
        (sub / "b.ct").write_text(CT_GAMEB, encoding="utf-8")

    def _rmtree(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_app_builds_index_and_binds_names(self):
        app = _make_app(self.folder, self.state_home)
        self.assertEqual(sorted(app.index.entries), ["a.ct", "sub/b.ct"])
        self.assertEqual(app.index.process_names(), ["GameA.exe", "GameB.exe"])
        self.assertIsNone(app.scan_error)
        self.assertEqual(app.orchestrator.bound_process_names,
                         ["GameA.exe", "GameB.exe"])

    def test_app_missing_folder_names_scan_error(self):
        app = _make_app(self.folder / "nope", self.state_home)
        self.assertIn("missing or not a directory", app.scan_error)
        self.assertEqual(app.index.entries, {})

    def test_app_tolerates_corrupt_stored_index(self):
        (self.state_home / "tables-index.json").write_bytes(b"not json at all")
        app = _make_app(self.folder, self.state_home)
        self.assertEqual(sorted(app.index.entries), ["a.ct", "sub/b.ct"])
        self.assertIsNone(app.scan_error)

    def test_tampered_checksum_index_is_refused_and_tolerated(self):
        # A stored document with a forged sha256 field must be refused by the
        # persistence layer (checksum-bound) and treated by MasterApp as "no
        # stored index": fresh scan, working state, no exception escapes.
        app = _make_app(self.folder, self.state_home)
        app.save_index()
        path = app.index_path()
        raw = json.loads(path.read_bytes())
        raw["payload"]["entries"]["a.ct"]["sha256"] = "00" * 32
        path.write_bytes(json.dumps(raw, sort_keys=True).encode("utf-8"))
        with self.assertRaises(TableIndexRefusal) as ctx:
            load_index(path)
        self.assertIn("checksum does not match", str(ctx.exception))
        app2 = _make_app(self.folder, self.state_home)
        self.assertEqual(sorted(app2.index.entries), ["a.ct", "sub/b.ct"])
        self.assertIsNone(app2.scan_error)

    def test_foreign_root_index_tolerated_full_rebuild(self):
        # Same state home, different table root: the stored document is valid
        # but foreign-rooted, so reconcile rebuilds from an empty index.
        app = _make_app(self.folder, self.state_home)
        app.save_index()
        other = self.tmp / "tables2"
        other.mkdir()
        (other / "d.ct").write_text(CT_GAMEA.replace("GameA", "GameD"),
                                    encoding="utf-8")
        app2 = _make_app(other, self.state_home)
        self.assertEqual(app2.folder, str(Path(other).resolve()))
        self.assertEqual(sorted(app2.index.entries), ["d.ct"])
        self.assertEqual(app2.index.entries["d.ct"].process_names,
                         ("GameD.exe",))
        self.assertIsNone(app2.scan_error)

    def test_app_save_index_roundtrip_and_location(self):
        app = _make_app(self.folder, self.state_home)
        app.save_index()
        path = app.index_path()
        self.assertTrue(path.is_file())
        self.assertEqual(path.parent, self.state_home)  # never in the folder
        stored = load_index(path)
        self.assertEqual(stored.entries, app.index.entries)

    def test_app_rescan_picks_up_changes(self):
        app = _make_app(self.folder, self.state_home)
        (self.folder / "c.ct").write_text(CT_GAMEB.replace("GameB", "GameC"),
                                          encoding="utf-8")
        app.rescan()
        self.assertIn("c.ct", app.index.entries)
        self.assertEqual(app.index.entries["c.ct"].process_names,
                         ("GameC.exe",))
        kinds = {c.kind for c in app.last_changes}
        self.assertEqual(kinds, {"added", "unchanged"})
        self.assertEqual(app.orchestrator.state, STATE_WAITING)

    def test_app_set_folder_switches_root_and_saves(self):
        app = _make_app(self.folder, self.state_home)
        other = self.tmp / "other"
        other.mkdir()
        (other / "d.ct").write_text(CT_GAMEA.replace("GameA", "GameD"),
                                    encoding="utf-8")
        app.set_folder(other)
        self.assertEqual(sorted(app.index.entries), ["d.ct"])
        self.assertEqual(app.orchestrator.bound_process_names, ["GameD.exe"])
        stored = load_index(app.index_path())
        self.assertEqual(stored.root, app.folder)
        self.assertEqual(sorted(stored.entries), ["d.ct"])

    def test_app_state_dir_for(self):
        app = _make_app(self.folder, self.state_home)
        self.assertIsNone(app.state_dir_for({"title": "T"}))
        app2 = MasterApp(self.folder, state_home=str(self.state_home),
                         poll_ms=50, lister=_FakeLister(),
                         plan_compiler=lambda e, n: {},
                         state_dir_factory=lambda plan: "/sd/" + plan["title"])
        self.assertEqual(app2.state_dir_for({"title": "T"}), "/sd/T")


class RunMasterTests(unittest.TestCase):
    def test_run_master_missing_folder_returns_2(self):
        missing = Path(tempfile.gettempdir()) / "ct2-master-no-such-folder"
        with redirect_stdout(io.StringIO()) as out:
            rc = run_master(missing)
        self.assertEqual(rc, 2)
        self.assertIn("Error: folder not found:", out.getvalue())

    def test_run_master_no_folder_cancelled_returns_0(self):
        with patch("ct2trainer.native.master_trainer.master_ui.tk.Tk") as tk_cls, \
                patch.object(master_ui.filedialog, "askdirectory",
                             return_value="") as ask:
            with redirect_stdout(io.StringIO()) as out:
                rc = run_master()
        self.assertEqual(rc, 0)
        self.assertIn("No folder chosen; nothing to do.", out.getvalue())
        self.assertEqual(ask.call_count, 1)
        self.assertEqual(tk_cls.call_count, 1)

    def test_run_master_success_builds_app_saves_index_and_runs_mainloop(self):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(folder, ignore_errors=True))
        (folder / "a.ct").write_text(CT_GAMEA, encoding="utf-8")
        state_home = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(state_home, ignore_errors=True))
        with patch.object(master_ui.tk, "Tk") as tk_cls, \
                patch.object(master_ui, "MasterWindow") as window_cls:
            rc = run_master(str(folder), state_home=str(state_home))
        self.assertEqual(rc, 0)
        tk_cls.return_value.mainloop.assert_called_once()
        window_cls.assert_called_once()
        app = window_cls.call_args[0][1]
        self.assertIsInstance(app, MasterApp)
        self.assertEqual(app.folder, str(folder.resolve()))
        # The app persisted its index into the given state home.
        stored = load_index(state_home / "tables-index.json")
        self.assertEqual(sorted(stored.entries), ["a.ct"])


@unittest.skipUnless(tk is not None, "tkinter required for real widget construction")
class MasterWindowTests(unittest.TestCase):
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
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _schedule_spy(self, window):
        scheduled = []
        window.root.after = lambda ms, cb=None: scheduled.append((ms, cb))
        return scheduled

    def test_waiting_view_construction(self):
        app = _make_app(self.folder, self.state_home)
        window = MasterWindow(self.root, app)
        self.assertEqual(self.root.title(), master_title())
        # Tk stores the WM_DELETE callback as an opaque Tcl command name
        # derived from the bound method; assert the naming, not identity.
        self.assertTrue(
            str(self.root.protocol("WM_DELETE_WINDOW")).endswith("close"))
        rows = window._table_tree.get_children()
        self.assertEqual(len(rows), 1)
        values = list(window._table_tree.item(rows[0])["values"])
        self.assertEqual(values[0], "a.ct")
        self.assertEqual(values[1], "GameA.exe")
        self.assertEqual(values[2], "ok")
        for text in ("Close", "Rescan", "Change folder\u2026", "Retry load"):
            self.assertTrue(_buttons(self.root, text), text)
        self.assertTrue(window._folder_label.cget("text").startswith("Folder: "))
        self.assertEqual(window._status_var.get(), "Scanning\u2026")

    def test_waiting_view_missing_folder_shows_scan_problem(self):
        app = _make_app(self.folder / "nope", self.state_home)
        window = MasterWindow(self.root, app)
        text = window._folder_label.cget("text")
        self.assertIn("scan problem:", text)
        self.assertEqual(window._table_tree.get_children(), ())

    def test_render_tables_marks_unreadable_with_detail(self):
        (self.folder / "empty.ct").write_bytes(b"")
        app = _make_app(self.folder, self.state_home)
        window = MasterWindow(self.root, app)
        rows = window._table_tree.get_children()
        by_path = {list(window._table_tree.item(r)["values"])[0]:
                   list(window._table_tree.item(r)["values"]) for r in rows}
        self.assertEqual(by_path["empty.ct"][2], "unreadable")
        self.assertEqual(by_path["empty.ct"][3], "empty file")

    def test_rescan_rerenders_after_content_change(self):
        app = _make_app(self.folder, self.state_home)
        window = MasterWindow(self.root, app)
        (self.folder / "a.ct").write_text(CT_GAMEA.replace("GameA", "GameZ"),
                                          encoding="utf-8")
        window._rescan()
        self.assertEqual(app.index.entries["a.ct"].process_names,
                         ("GameZ.exe",))
        values = list(window._table_tree.item(
            window._table_tree.get_children()[0])["values"])
        self.assertEqual(values, ["a.ct", "GameZ.exe", "ok", ""])
        # The status line is back on the (rebound) waiting line.
        self.assertEqual(window._status_var.get(),
                         window._waiting_status_line())
        self.assertIn("Waiting for one of: GameZ.exe",
                      window._status_var.get())

    def test_change_folder_cancel_keeps_current_root(self):
        app = _make_app(self.folder, self.state_home)
        window = MasterWindow(self.root, app)
        original = app.folder
        with patch.object(master_ui.filedialog, "askdirectory",
                          return_value="") as ask:
            window._change_folder()
        ask.assert_called_once()
        self.assertEqual(app.folder, original)
        self.assertEqual(sorted(app.index.entries), ["a.ct"])
        self.assertEqual(len(window._table_tree.get_children()), 1)

    def test_poll_no_match_keeps_waiting_and_reschedules(self):
        app = _make_app(self.folder, self.state_home)
        window = MasterWindow(self.root, app)
        scheduled = self._schedule_spy(window)
        window._poll()
        status = window._status_var.get()
        self.assertIn("Waiting for one of: GameA.exe", status)
        self.assertIn("scanned 0 processes", status)
        self.assertIsNone(window.engine)
        self.assertEqual(scheduled, [(app.poll_ms, window._poll)])

    def test_poll_snapshot_failure_is_named_and_loop_survives(self):
        # The lister failure is named by the orchestrator itself (tick
        # returns a reason, sets last_error); the poll loop keeps the
        # waiting line + last-error suffix and reschedules.
        app = _make_app(self.folder, self.state_home,
                        error=RuntimeError("kernel32 down"))
        window = MasterWindow(self.root, app)
        scheduled = self._schedule_spy(window)
        window._poll()
        status = window._status_var.get()
        self.assertIn("Waiting for one of: GameA.exe", status)
        self.assertIn("process snapshot failed: RuntimeError: kernel32 down",
                      status)
        self.assertEqual(scheduled, [(app.poll_ms, window._poll)])

    def test_poll_unexpected_tick_exception_is_named_and_loop_survives(self):
        # The second guard: any exception escaping tick() (the orchestrator
        # itself) is named in the status line and the loop still reschedules.
        app = _make_app(self.folder, self.state_home)
        window = MasterWindow(self.root, app)
        scheduled = self._schedule_spy(window)
        with patch.object(app.orchestrator, "tick",
                          side_effect=RuntimeError("kernel32 down")):
            window._poll()
        self.assertIn("Waiting tick failed: RuntimeError: kernel32 down",
                      window._status_var.get())
        self.assertEqual(scheduled, [(app.poll_ms, window._poll)])

    def test_poll_skips_when_engine_active_or_closed(self):
        # Trainer mode and shutdown must not double-fire the waiting tick
        # (the trainer window runs its own poll loop) and must not
        # reschedule.
        app = _make_app(self.folder, self.state_home)
        window = MasterWindow(self.root, app)
        scheduled = self._schedule_spy(window)
        with patch.object(app.orchestrator, "tick") as tick_spy:
            window.engine = MagicMock()
            window._poll()
            tick_spy.assert_not_called()
            window.engine = None
            app.closed = True
            window._poll()
            tick_spy.assert_not_called()
        self.assertEqual(scheduled, [])

    def test_poll_auto_load_success_enters_trainer(self):
        process = ProcessSnapshotEntry(7, "GameA.exe")
        app = _make_app(self.folder, self.state_home, [process])
        window = MasterWindow(self.root, app)
        scheduled = self._schedule_spy(window)
        with patch("ct2trainer.native.master_trainer.master_ui.TrainerEngine") as engine_cls, \
                patch("ct2trainer.native.master_trainer.master_ui.TrainerWindow") as window_cls:
            window._poll()
        engine = engine_cls.return_value
        window_cls.assert_called_once_with(
            self.root, engine, master_back=window._back_to_master)
        self.assertIs(window.engine, engine)
        self.assertIsNotNone(window.trainer_window)
        self.assertEqual(app.orchestrator.state, STATE_ACTIVE)
        self.assertEqual(scheduled, [])  # trainer mode: no waiting reschedule

    def test_start_load_failure_shows_error_and_arms_guard(self):
        def refuse(entry, name):
            raise ValueError("compile refused")

        process = ProcessSnapshotEntry(7, "GameA.exe")
        app = _make_app(self.folder, self.state_home, [process], compiler=refuse)
        window = MasterWindow(self.root, app)
        self._schedule_spy(window)
        entry = app.index.entries_for_process("GameA.exe")[0]
        with patch("ct2trainer.native.master_trainer.master_ui.messagebox") as box:
            window._start_load(entry, process)
        box.showerror.assert_called_once()
        self.assertIn("compile refused", str(box.showerror.call_args))
        self.assertEqual(app.orchestrator.state, STATE_WAITING)
        self.assertIsNone(window.engine)
        # The loop guard names the earlier failure on the next tick.
        outcome = app.orchestrator.tick()
        self.assertIsNone(outcome.request)
        self.assertIn("auto-load suppressed (earlier failure for a.ct: "
                      "ValueError: compile refused)", outcome.reason)
        # Retry load re-arms the pair.
        window._retry()
        self.assertIn("Retry armed", window._status_var.get())
        outcome = app.orchestrator.tick()
        self.assertIsNotNone(outcome.request)

    def test_picker_construction_lists_tables(self):
        sub = self.folder / "sub"
        sub.mkdir()
        (sub / "b.ct").write_text(CT_GAMEA.replace("GameA", "GameB"),
                                  encoding="utf-8")
        # Rebind both tables to the same process for the multi-match.
        (self.folder / "a.ct").write_text(CT_GAMEB, encoding="utf-8")
        process = ProcessSnapshotEntry(7, "GameB.exe")
        app = _make_app(self.folder, self.state_home, [process])
        window = MasterWindow(self.root, app)
        outcome = app.orchestrator.tick()
        self.assertIsNotNone(outcome.choice)
        window._open_picker(outcome.choice)
        picker = window._picker
        self.assertIsNotNone(picker)
        self.assertEqual(picker.title(), "Which table for GameB.exe?")
        label_text = "".join(str(w.cget("text"))
                             for w in _all_widgets(picker)
                             if isinstance(w, tk.Label))
        self.assertIn("GameB.exe is running (PID 7)", label_text)
        self.assertIn("2 indexed tables bind to it", label_text)
        radios = [w for w in _all_widgets(picker)
                  if isinstance(w, tk.Radiobutton)]
        self.assertEqual(sorted(str(r.cget("text")) for r in radios),
                         ["a.ct", "sub/b.ct"])
        self.assertTrue(_buttons(picker, "Load"))
        self.assertTrue(_buttons(picker, "Not now"))

    def test_picker_chosen_loads_and_activates(self):
        (self.folder / "b.ct").write_text(CT_GAMEB, encoding="utf-8")
        # Rebind both tables to the same process for the multi-match.
        (self.folder / "a.ct").write_text(CT_GAMEB, encoding="utf-8")
        process = ProcessSnapshotEntry(7, "GameB.exe")
        app = _make_app(self.folder, self.state_home, [process])
        window = MasterWindow(self.root, app)
        outcome = app.orchestrator.tick()
        window._open_picker(outcome.choice)
        with patch("ct2trainer.native.master_trainer.master_ui.TrainerEngine") as engine_cls, \
                patch("ct2trainer.native.master_trainer.master_ui.TrainerWindow") as window_cls:
            window._picker_selection.set("b.ct")
            window._picker_chosen("b.ct")
        self.assertIsNone(window._picker)
        self.assertIsNone(window._picker_selection)
        engine = engine_cls.return_value
        window_cls.assert_called_once_with(
            self.root, engine, master_back=window._back_to_master)
        self.assertEqual(app.orchestrator.state, STATE_ACTIVE)
        self.assertIs(window.engine, engine)

    def test_picker_cancel_defers_pair(self):
        (self.folder / "b.ct").write_text(CT_GAMEB, encoding="utf-8")
        # Rebind both tables to the same process for the multi-match.
        (self.folder / "a.ct").write_text(CT_GAMEB, encoding="utf-8")
        process = ProcessSnapshotEntry(7, "GameB.exe")
        app = _make_app(self.folder, self.state_home, [process])
        window = MasterWindow(self.root, app)
        outcome = app.orchestrator.tick()
        window._open_picker(outcome.choice)
        window._picker_cancel()
        self.assertIsNone(window._picker)
        self.assertEqual(app.orchestrator.state, STATE_WAITING)
        self.assertIn("Table choice deferred", window._status_var.get())
        # The deferred pair is not auto-loaded nor re-asked while it lives.
        outcome = app.orchestrator.tick()
        self.assertIsNone(outcome.request)
        self.assertIsNone(outcome.choice)
        self.assertIn("auto-load deferred", outcome.reason)

    def test_picker_chosen_none_defers_and_suppresses(self):
        # "Not now" without a selected radio: defers the exact (name, PID)
        # pair via the same suppression path as cancel.
        (self.folder / "b.ct").write_text(CT_GAMEB, encoding="utf-8")
        (self.folder / "a.ct").write_text(CT_GAMEB, encoding="utf-8")
        process = ProcessSnapshotEntry(7, "GameB.exe")
        app = _make_app(self.folder, self.state_home, [process])
        window = MasterWindow(self.root, app)
        outcome = app.orchestrator.tick()
        self.assertIsNotNone(outcome.choice)
        window._open_picker(outcome.choice)
        with patch("ct2trainer.native.master_trainer.master_ui.TrainerWindow") as window_cls, \
                patch("ct2trainer.native.master_trainer.master_ui.messagebox"):
            window._picker_chosen(None)
        self.assertIsNone(window._picker)
        self.assertIsNone(window._picker_selection)
        window_cls.assert_not_called()
        self.assertEqual(app.orchestrator.state, STATE_WAITING)
        self.assertIn("Table choice deferred", window._status_var.get())
        # The running (name, PID) pair is suppressed: a re-tick must not
        # re-open the picker nor request a load.
        retick = app.orchestrator.tick()
        self.assertIsNone(retick.request)
        self.assertIsNone(retick.choice)
        self.assertIn("auto-load deferred", retick.reason)

    def test_back_to_master_restores_waiting_view(self):
        process = ProcessSnapshotEntry(7, "GameA.exe")
        app = _make_app(self.folder, self.state_home, [process])
        window = MasterWindow(self.root, app)
        self._schedule_spy(window)
        # Drive the orchestrator through the documented load path so the
        # back transition has an active session to release.
        entry = app.index.entries_for_process("GameA.exe")[0]
        self.assertTrue(app.orchestrator.load(entry, process).ok)
        app.orchestrator.mark_active()
        engine = MagicMock()
        engine.close.return_value = True
        window.engine = engine
        window._back_to_master()
        engine.close.assert_called_once_with()
        self.assertIsNone(window.engine)
        self.assertIsNone(window.trainer_window)
        self.assertEqual(app.orchestrator.state, STATE_WAITING)
        self.assertTrue(
            str(self.root.protocol("WM_DELETE_WINDOW")).endswith("close"))
        self.assertEqual(window._status_var.get(), "Back to Master wait mode.")
        self.assertEqual(len(window._table_tree.get_children()), 1)

    def test_back_to_master_shows_warning_on_unclean_close(self):
        # engine.close() False: the journals are preserved and the user
        # gets the cleanup warning, then the waiting view still returns.
        process = ProcessSnapshotEntry(7, "GameA.exe")
        app = _make_app(self.folder, self.state_home, [process])
        window = MasterWindow(self.root, app)
        self._schedule_spy(window)
        entry = app.index.entries_for_process("GameA.exe")[0]
        self.assertTrue(app.orchestrator.load(entry, process).ok)
        app.orchestrator.mark_active()
        engine = MagicMock()
        engine.close.return_value = False
        window.engine = engine
        with patch("ct2trainer.native.master_trainer.master_ui.messagebox") as box:
            window._back_to_master()
        engine.close.assert_called_once_with()
        box.showwarning.assert_called_once()
        self.assertIn("Cleanup needs attention",
                      str(box.showwarning.call_args))
        self.assertEqual(app.orchestrator.state, STATE_WAITING)
        self.assertEqual(window._status_var.get(),
                         "Back to Master wait mode.")

    def test_back_to_master_noop_when_no_engine(self):
        # With no engine attached the back button must be a silent no-op:
        # the waiting view is untouched and the orchestrator state keeps.
        app = _make_app(self.folder, self.state_home)
        window = MasterWindow(self.root, app)
        old_tree = window._table_tree
        window._back_to_master()
        self.assertIs(old_tree, window._table_tree)
        self.assertEqual(app.orchestrator.state, STATE_WAITING)

    def test_close_without_engine(self):
        app = _make_app(self.folder, self.state_home)
        window = MasterWindow(self.root, app)
        window.close()
        self.assertTrue(app.closed)

    def test_close_with_clean_engine_no_warning(self):
        app = _make_app(self.folder, self.state_home)
        window = MasterWindow(self.root, app)
        window.engine = MagicMock(close=MagicMock(return_value=True))
        with patch("ct2trainer.native.master_trainer.master_ui.messagebox") as box:
            window.close()
        self.assertTrue(app.closed)
        box.showwarning.assert_not_called()

    def test_close_with_unclean_engine_warns(self):
        app = _make_app(self.folder, self.state_home)
        window = MasterWindow(self.root, app)
        window.engine = MagicMock(close=MagicMock(return_value=False))
        with patch("ct2trainer.native.master_trainer.master_ui.messagebox") as box:
            window.close()
        box.showwarning.assert_called_once()
        self.assertIn("Cleanup needs attention",
                      str(box.showwarning.call_args))


@unittest.skipUnless(tk is not None, "tkinter required for real widget construction")
class TrainerHandoffTests(unittest.TestCase):
    """Startup recovery + handoff flows with the patched engine seam."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(self._rmtree)
        self.folder = self.tmp / "tables"
        self.folder.mkdir()
        self.state_home = self.tmp / "state"
        self.state_home.mkdir()
        (self.folder / "a.ct").write_text(CT_GAMEA, encoding="utf-8")
        self.process = ProcessSnapshotEntry(7, "GameA.exe")
        self.root = tk.Tk()
        self.root.withdraw()

    def _rmtree(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _window_with_engine(self, engine_side_effect, askyesno=True,
                            recover=(True, "Archived stale state")):
        app = _make_app(self.folder, self.state_home, [self.process])
        window = MasterWindow(self.root, app)
        with patch("ct2trainer.native.master_trainer.master_ui.TrainerEngine",
                   side_effect=engine_side_effect) as engine_cls, \
                patch("ct2trainer.native.master_trainer.master_ui.TrainerWindow") as window_cls, \
                patch("ct2trainer.native.master_trainer.master_ui.messagebox") as box, \
                patch("ct2trainer.native.master_trainer.master_ui.perform_stale_recovery",
                      return_value=recover) as recover_fn:
            if isinstance(askyesno, bool):
                box.askyesno.return_value = askyesno
            else:
                box.askyesno.side_effect = list(askyesno)
            entry = app.index.entries_for_process("GameA.exe")[0]
            window._start_load(entry, self.process)
        return app, window, engine_cls, window_cls, box, recover_fn

    def test_recovery_stale_declined_fails_start(self):
        # A declined prompt fails the load exactly once (the standalone
        # trainer exits on decline); the loop guard must not re-prompt.
        app, window, engine_cls, _, box, recover_fn = self._window_with_engine(
            [_stale_handle()], askyesno=False)
        self.assertEqual(engine_cls.call_count, 1)
        box.askyesno.assert_called_once()
        box.showerror.assert_not_called()
        recover_fn.assert_not_called()
        self.assertIsNone(window.engine)
        self.assertEqual(app.orchestrator.state, STATE_WAITING)
        self.assertIn("Trainer start failed", window._status_var.get())
        prompt = str(box.askyesno.call_args)
        self.assertIn("Recover", prompt)

    def test_recovery_stale_accepted_recovers_and_starts(self):
        engine = MagicMock()
        app, window, engine_cls, window_cls, box, recover_fn = \
            self._window_with_engine([_stale_handle(), engine])
        recover_fn.assert_called_once()
        self.assertIsInstance(recover_fn.call_args[0][0],
                              StaleStateRecoverable)
        self.assertIs(window.engine, engine)
        self.assertEqual(app.orchestrator.state, STATE_ACTIVE)
        window_cls.assert_called_once_with(
            self.root, engine, master_back=window._back_to_master)
        box.showerror.assert_not_called()

    def test_recovery_artifacts_declined_fails_start(self):
        # Same declined contract for the orphaned-receipts variant.
        app, window, engine_cls, _, box, recover_fn = self._window_with_engine(
            [_artifacts_handle()], askyesno=False)
        self.assertEqual(engine_cls.call_count, 1)
        box.askyesno.assert_called_once()
        self.assertIn("unfinished receipts", str(box.askyesno.call_args))
        box.showerror.assert_not_called()
        recover_fn.assert_not_called()
        self.assertIsNone(window.engine)
        self.assertEqual(app.orchestrator.state, STATE_WAITING)
        self.assertIn("Trainer start failed", window._status_var.get())

    def test_recovery_artifacts_confirmed_proceeds(self):
        engine = MagicMock()
        app, window, engine_cls, window_cls, box, recover_fn = \
            self._window_with_engine([_artifacts_handle(), engine])
        self.assertEqual(engine_cls.call_count, 2)
        recover_fn.assert_called_once()
        self.assertIsInstance(recover_fn.call_args[0][0],
                              StaleArtifactsRecoverable)
        self.assertIs(window.engine, engine)
        self.assertEqual(app.orchestrator.state, STATE_ACTIVE)
        window_cls.assert_called_once_with(
            self.root, engine, master_back=window._back_to_master)
        self.assertIn("unfinished receipts", str(box.askyesno.call_args))

    def test_recovery_failure_shows_error_and_fails_start(self):
        app, window, _, _, box, recover_fn = self._window_with_engine(
            [_stale_handle()], askyesno=True, recover=(False, "archive failed"))
        recover_fn.assert_called_once()
        box.showerror.assert_called_once()
        self.assertIn("Recovery failed", str(box.showerror.call_args))
        self.assertIsNone(window.engine)
        self.assertEqual(app.orchestrator.state, STATE_WAITING)

    def test_live_conflict_shows_error_and_fails_start(self):
        app, window, _, _, box, _ = self._window_with_engine(
            [_live_conflict()])
        box.showerror.assert_called_once()
        call_args = str(box.showerror.call_args)
        self.assertIn("Live session conflict", call_args)
        self.assertIn("321", call_args)
        self.assertIsNone(window.engine)
        self.assertEqual(app.orchestrator.state, STATE_WAITING)

    def test_generic_engine_error_shows_error_and_fails_start(self):
        app, window, _, _, box, _ = self._window_with_engine(
            [RuntimeError("attach refused")])
        box.showerror.assert_called_once()
        self.assertIn("Trainer cannot start", str(box.showerror.call_args))
        self.assertIsNone(window.engine)
        self.assertEqual(app.orchestrator.state, STATE_WAITING)

    def test_recovery_nonconvergence_fails_load_and_arms_guard(self):
        # Four confirmed recoveries, each followed by the same recoverable
        # refusal: the loop must stop and fail the load (fail-closed), not
        # leave the orchestrator stuck in loading.
        app, window, _, _, box, _ = self._window_with_engine(
            [_stale_handle()] * 4, askyesno=True,
            recover=(True, "Archived"))
        box.showerror.assert_called_once()
        self.assertIn("did not converge", str(box.showerror.call_args))
        self.assertIsNone(window.engine)
        self.assertEqual(app.orchestrator.state, STATE_WAITING)
        self.assertIn("Trainer start failed", window._status_var.get())
        outcome = app.orchestrator.tick()
        self.assertIsNone(outcome.request)
        self.assertIn("auto-load suppressed", outcome.reason)


@unittest.skipUnless(tk is not None, "tkinter required for real widget construction")
class TrainerWindowMasterBackTests(unittest.TestCase):
    """The MT-4 additions to the standalone TrainerWindow."""

    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def test_master_back_defaults_none(self):
        from ct2trainer.native.ui import TrainerWindow
        sig = inspect.signature(TrainerWindow.__init__)
        self.assertIn("master_back", sig.parameters)
        self.assertIsNone(sig.parameters["master_back"].default)

    def _engine(self):
        e = MagicMock()
        e.entries = {}
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
        return e

    def test_master_back_button_present_only_when_wired(self):
        # The header button appears only for the Master Trainer; the
        # standalone trainer keeps its exact header.
        from ct2trainer.native.ui import TrainerWindow
        root1 = tk.Tk()
        root1.withdraw()
        self.addCleanup(root1.destroy)
        w1 = TrainerWindow(root1, self._engine(), master_back=lambda: None)
        self.assertIn("\u2b05 Master", _button_texts(w1.header))

        root2 = tk.Tk()
        root2.withdraw()
        self.addCleanup(root2.destroy)
        w2 = TrainerWindow(root2, self._engine())
        self.assertNotIn("\u2b05 Master", _button_texts(w2.header))

    def test_render_skips_destroyed_canvas(self):
        # A pending pulse after-callback can outlive the trainer view when the
        # Master destroys the trainer widgets and rebuilds the waiting view on
        # the same root; a destroyed canvas is skipped, not raised.
        from ct2trainer.native.ui import TrainerWindow
        window = TrainerWindow.__new__(TrainerWindow)
        window._embedded = []
        canvas = tk.Canvas(self.root)
        canvas.pack()
        canvas.destroy()
        window.canvas = canvas
        window.render()  # must not raise out of mainloop


if __name__ == "__main__":
    unittest.main()
