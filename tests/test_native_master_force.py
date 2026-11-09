"""0.38 --force: the Master Trainer forced-start contract in _start_load.

With the persisted --force flag the Master skips the state-lock safety
prompts: a recoverable stale state (or unfinished receipts) is archived
without a confirmation dialog, a leftover recovery fence (any other
unclassifiable held state) triggers the forced reclaim, and the one
boundary that stays is the proven-alive second session (named refusal,
no termination prompt). Failures land in the status line plus the
fail-closed loop guard, exactly like every other startup failure.
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

from native_tk_teardown import force_root_release
from ct2trainer.native.engine import (LiveStateConflict, StateError,
                                       StaleArtifactsRecoverable,
                                       StaleStateRecoverable)
from ct2trainer.native.master_trainer.master_ui import MasterApp, MasterWindow
from ct2trainer.native.master_trainer.orchestrator import (STATE_ACTIVE,
                                                           STATE_WAITING)
from ct2trainer.native.master_trainer.process_watch import (ProcessLister,
                                                            ProcessSnapshotEntry)

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

TRAINER_ID = "a" * 16
TABLE_SHA = "b" * 64

FENCE_MESSAGE = ("A recovery transaction owns this state; "
                 "preserve its fence and evidence")


class _FakeLister(ProcessLister):
    def __init__(self, entries=(), error=None):
        self.entries = list(entries)
        self.error = error

    def list_processes(self):
        if self.error is not None:
            raise self.error
        return list(self.entries)


def _stale_handle() -> StaleStateRecoverable:
    return StaleStateRecoverable(None, "/tmp/state", "/tmp/shared",
                                 "/tmp/archives", TRAINER_ID, TABLE_SHA)


def _artifacts_handle() -> StaleArtifactsRecoverable:
    return StaleArtifactsRecoverable(None, "/tmp/state", "/tmp/shared",
                                     "/tmp/archives", TRAINER_ID, TABLE_SHA)


def _live_conflict() -> LiveStateConflict:
    return LiveStateConflict(321, 999, "/tmp/state")


def _force_compiler(entry, name):
    # A minimal but identity-complete plan so the forced-reclaim branch
    # can address the documented state directories.
    return {"trainer_id": TRAINER_ID, "table_sha256": TABLE_SHA,
            "title": "T", "relative_path": entry.relative_path}


class MasterForceStartTests(unittest.TestCase):
    def setUp(self):
        if tk is None:
            self.skipTest("Tkinter is not available in this environment")
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
        force_root_release([self.root], ((self, "root"),))

    def _force_app(self, compiler=None):
        return MasterApp(self.folder, state_home=self.state_home, poll_ms=50,
                         lister=_FakeLister([self.process]),
                         plan_compiler=compiler or _force_compiler,
                         force=True)

    def _start(self, engine_side_effect, app,
               recover=(True, "Archived stale state"),
               force_reclaim=(True, "forced reclaim quarantined 1 artifact(s)"),
               state_dir_factory=None, askyesno=None):
        if state_dir_factory is not None:
            app.state_dir_factory = state_dir_factory
        window = MasterWindow(self.root, app)
        with patch("ct2trainer.native.master_trainer.master_ui.TrainerEngine",
                   side_effect=engine_side_effect) as engine_cls, \
                patch("ct2trainer.native.master_trainer.master_ui.TrainerWindow") as window_cls, \
                patch("ct2trainer.native.master_trainer.master_ui.messagebox") as box, \
                patch("ct2trainer.native.master_trainer.master_ui.perform_stale_recovery",
                      return_value=recover) as recover_fn, \
                patch("ct2trainer.native.master_trainer.master_ui.force_reclaim",
                      return_value=force_reclaim) as reclaim_fn:
            if askyesno is not None:
                box.askyesno.return_value = askyesno
            entry = app.index.entries_for_process("GameA.exe")[0]
            window._start_load(entry, self.process)
        return (window, engine_cls, window_cls, box, recover_fn, reclaim_fn)

    def test_force_stale_state_recovers_without_prompt(self):
        engine = MagicMock()
        app = self._force_app()
        window, engine_cls, _, box, recover_fn, reclaim_fn = self._start(
            [_stale_handle(), engine], app)
        self.assertEqual(engine_cls.call_count, 2)
        recover_fn.assert_called_once()
        box.askyesno.assert_not_called()
        box.showerror.assert_not_called()
        reclaim_fn.assert_not_called()
        self.assertIs(window.engine, engine)
        self.assertEqual(app.orchestrator.state, STATE_ACTIVE)
        # The waiting view (and its status line) is torn down on trainer
        # entry (MT-19), so the flow is proven through the engine handoff.

    def test_force_artifacts_recovers_without_prompt(self):
        engine = MagicMock()
        app = self._force_app()
        window, engine_cls, _, box, recover_fn, _ = self._start(
            [_artifacts_handle(), engine], app)
        self.assertEqual(engine_cls.call_count, 2)
        recover_fn.assert_called_once()
        box.askyesno.assert_not_called()
        box.showerror.assert_not_called()
        self.assertIs(window.engine, engine)
        self.assertEqual(app.orchestrator.state, STATE_ACTIVE)

    def test_force_stale_recovery_failure_fails_start(self):
        app = self._force_app()
        window, _, _, box, recover_fn, _ = self._start(
            [_stale_handle()], app, recover=(False, "archive failed"))
        recover_fn.assert_called_once()
        box.showerror.assert_not_called()
        self.assertIsNone(window.engine)
        self.assertEqual(app.orchestrator.state, STATE_WAITING)
        self.assertIn("Forced recovery failed: archive failed",
                      window._status_var.get())

    def test_force_fence_dead_end_reclaims_and_starts(self):
        engine = MagicMock()
        app = self._force_app()
        window, engine_cls, _, box, _, reclaim_fn = self._start(
            [StateError(FENCE_MESSAGE), engine], app)
        self.assertEqual(engine_cls.call_count, 2)
        reclaim_fn.assert_called_once()
        box.askyesno.assert_not_called()
        box.showerror.assert_not_called()
        self.assertIs(window.engine, engine)
        self.assertEqual(app.orchestrator.state, STATE_ACTIVE)

    def test_force_fence_reclaim_refusal_fails_start(self):
        app = self._force_app()
        window, _, _, box, _, reclaim_fn = self._start(
            [StateError(FENCE_MESSAGE)], app,
            force_reclaim=(False, "the recorded state owner (PID 4242, "
                                 "recovery fence) is proven alive; "
                                 "--force never displaces a live trainer "
                                 "session"))
        reclaim_fn.assert_called_once()
        self.assertIsNone(window.engine)
        self.assertEqual(app.orchestrator.state, STATE_WAITING)
        self.assertTrue(any("--force refusal" in str(call)
                            and "proven alive" in str(call)
                            for call in box.showerror.call_args_list))
        self.assertIn("--force refusal", window._status_var.get())

    def test_force_live_conflict_refused_without_prompt(self):
        app = self._force_app()
        window, _, _, box, _, _ = self._start([_live_conflict()], app)
        self.assertIsNone(window.engine)
        self.assertEqual(app.orchestrator.state, STATE_WAITING)
        box.askyesno.assert_not_called()
        self.assertTrue(any("proven alive" in str(call)
                            for call in box.showerror.call_args_list))
        self.assertIn("Forced load refused", window._status_var.get())

    def test_force_reclaim_addresses_the_custom_state_dir(self):
        engine = MagicMock()
        app = self._force_app()
        custom = self.tmp / "custom-state"
        custom.mkdir()
        window, _, _, _, _, reclaim_fn = self._start(
            [StateError(FENCE_MESSAGE), engine], app,
            state_dir_factory=lambda plan: str(custom))
        self.assertIs(window.engine, engine)
        args = reclaim_fn.call_args[0]
        self.assertEqual(args[0], custom)
        self.assertEqual(args[1], custom.parent / "_process_sessions")
        self.assertEqual(args[2]["trainer_id"], TRAINER_ID)

    def test_non_force_app_still_prompts(self):
        # The force flag is off by default: the ordinary confirmation
        # contract is untouched (declined prompt fails the start).
        app = MasterApp(self.folder, state_home=self.state_home, poll_ms=50,
                        lister=_FakeLister([self.process]),
                        plan_compiler=_force_compiler)
        self.assertFalse(app.force)
        window, _, _, box, recover_fn, _ = self._start([_stale_handle()], app,
                                                       askyesno=False)
        box.askyesno.assert_called_once()
        recover_fn.assert_not_called()
        self.assertIsNone(window.engine)
        self.assertEqual(app.orchestrator.state, STATE_WAITING)


if __name__ == "__main__":
    unittest.main()
