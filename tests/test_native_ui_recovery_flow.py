"""Startup recovery dialogs: stale lock, orphaned artifacts, live conflict.

``run_trainer`` turns every recoverable startup refusal into a visible,
user-confirmed action instead of a bare error dialog: a stale state lock,
unfinished receipts or session artifacts (the "unfinalized receipt" refusal),
and a proven-alive second session (user-confirmed termination, then the
stale-lock recovery on the following attempt). A conservative StateError
without a death proof still exits with the plain error dialog, and a
recovery that never converges stops after four attempts.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from ct2trainer.native.engine import (LiveStateConflict, StateError,
                                        StaleArtifactsRecoverable,
                                        StaleStateRecoverable)
from ct2trainer.native.ui import run_trainer


def _artifacts_handle() -> StaleArtifactsRecoverable:
    return StaleArtifactsRecoverable(None, "/tmp/state", "/tmp/shared",
                                     "/tmp/archives", "a" * 16, "b" * 64)


def _stale_handle() -> StaleStateRecoverable:
    return StaleStateRecoverable(None, "/tmp/state", "/tmp/shared",
                                 "/tmp/archives", "a" * 16, "b" * 64)


def _live_handle(owner_created: int | None) -> LiveStateConflict:
    return LiveStateConflict(222, owner_created, "/tmp/state")


class RunTrainerRecoveryFlowTests(unittest.TestCase):
    def _run(self, engine_side_effects, yesno=True,
             recover=(True, "Archived stale state to /tmp/archives/x.zip"),
             terminate=(True, "Terminated owner session")):
        effects = list(engine_side_effects)
        with patch('ct2trainer.native.ui.tk.Tk') as tk_cls, \
                patch('ct2trainer.native.ui.window_icon_path',
                      return_value=Path('/nonexistent/icon.ico')), \
                patch('ct2trainer.native.ui.TrainerEngine',
                      side_effect=effects) as engine_cls, \
                patch('ct2trainer.native.ui.perform_stale_recovery',
                      return_value=recover) as recover_fn, \
                patch('ct2trainer.native.ui.terminate_live_session',
                      return_value=terminate) as terminate_fn, \
                patch('ct2trainer.native.ui.messagebox') as box, \
                patch('ct2trainer.native.ui.TrainerWindow') as window:
            root = tk_cls.return_value
            if isinstance(yesno, bool):
                box.askyesno.return_value = yesno
            else:
                box.askyesno.side_effect = list(yesno)
            rc = run_trainer({"anything": True})
        return rc, box, engine_cls, recover_fn, terminate_fn, window, root

    def test_artifacts_recovery_confirmed_starts_trainer(self):
        engine = MagicMock()
        engine.blocked = False
        handle = _artifacts_handle()
        rc, box, _, recover_fn, _, window, root = self._run(
            [handle, engine])
        self.assertEqual(rc, 0)
        recover_fn.assert_called_once_with(handle)
        prompt = str(box.askyesno.call_args)
        self.assertIn("unfinished receipts", prompt)
        window.assert_called_once_with(root, engine)
        root.mainloop.assert_called_once()

    def test_artifacts_recovery_declined_exits_state_untouched(self):
        engine = MagicMock()
        engine.blocked = False
        rc, box, _, recover_fn, _, window, _ = self._run(
            [_artifacts_handle(), engine], yesno=False)
        self.assertEqual(rc, 1)
        recover_fn.assert_not_called()
        window.assert_not_called()
        self.assertTrue(any("left untouched" in str(call)
                            for call in box.showinfo.call_args_list))

    def test_artifacts_recovery_failure_exits_with_error(self):
        engine = MagicMock()
        engine.blocked = False
        rc, box, _, recover_fn, _, window, _ = self._run(
            [_artifacts_handle(), engine],
            recover=(False, "boom"))
        self.assertEqual(rc, 1)
        self.assertEqual(recover_fn.call_count, 1)
        window.assert_not_called()
        self.assertTrue(any("recovery failed" in str(call)
                            for call in box.showerror.call_args_list))

    def test_live_takeover_then_stale_recovery_starts_trainer(self):
        engine = MagicMock()
        engine.blocked = False
        rc, box, _, recover_fn, terminate_fn, window, _ = self._run(
            [_live_handle(2222), _stale_handle(), engine],
            yesno=[True, True])
        self.assertEqual(rc, 0)
        terminate_fn.assert_called_once_with(222, 2222)
        self.assertEqual(recover_fn.call_count, 1)
        window.assert_called_once()

    def test_live_conflict_without_creation_identity_refuses_termination(self):
        engine = MagicMock()
        engine.blocked = False
        rc, box, _, recover_fn, terminate_fn, window, _ = self._run(
            [_live_handle(None), engine])
        self.assertEqual(rc, 1)
        terminate_fn.assert_not_called()
        recover_fn.assert_not_called()
        window.assert_not_called()
        self.assertTrue(any("creation identity is unknown" in str(call)
                            for call in box.showinfo.call_args_list))

    def test_conservative_state_error_exits_with_error_dialog(self):
        refusal = StateError(
            "Prior executable allocations still have an unfinalized receipt. "
            "Restart the exact target and verify recovery before another "
            "controller claims this state.")
        rc, box, _, recover_fn, _, window, _ = self._run([refusal])
        self.assertEqual(rc, 1)
        box.askyesno.assert_not_called()
        recover_fn.assert_not_called()
        window.assert_not_called()
        self.assertTrue(any("cannot start" in str(call)
                            for call in box.showerror.call_args_list))

    def test_non_converging_recovery_stops_after_four_attempts(self):
        rc, box, engine_cls, recover_fn, _, window, _ = self._run(
            [_artifacts_handle()] * 4)
        self.assertEqual(rc, 1)
        self.assertEqual(engine_cls.call_count, 4)
        self.assertEqual(recover_fn.call_count, 4)
        window.assert_not_called()
        self.assertTrue(any("did not converge" in str(call)
                            for call in box.showerror.call_args_list))


class RunTrainerForceFlowTests(unittest.TestCase):
    """0.38 --force: the state-lock safety prompts are skipped; the one
    boundary that stays is the proven-alive second session."""

    def _run(self, engine_side_effects,
             force_reclaim=(True, "forced reclaim quarantined 2 artifact(s)"),
             recover=(True, "Archived stale state to /tmp/archives/x.zip")):
        effects = list(engine_side_effects)
        plan = {"trainer_id": "a" * 16, "table_sha256": "b" * 64}
        with patch('ct2trainer.native.ui.tk.Tk') as tk_cls, \
                patch('ct2trainer.native.ui.window_icon_path',
                      return_value=Path('/nonexistent/icon.ico')), \
                patch('ct2trainer.native.ui.TrainerEngine',
                      side_effect=effects) as engine_cls, \
                patch('ct2trainer.native.ui.perform_stale_recovery',
                      return_value=recover) as recover_fn, \
                patch('ct2trainer.native.ui.terminate_live_session',
                      return_value=(True, "Terminated owner session")) as terminate_fn, \
                patch('ct2trainer.native.ui._force_reclaim',
                      return_value=force_reclaim) as reclaim_fn, \
                patch('ct2trainer.native.ui.messagebox') as box, \
                patch('ct2trainer.native.ui.TrainerWindow') as window:
            root = tk_cls.return_value
            rc = run_trainer(plan, force=True)
        return (rc, box, engine_cls, recover_fn, terminate_fn, reclaim_fn,
                window, root)

    def test_force_stale_state_recovers_without_prompt(self):
        engine = MagicMock()
        engine.blocked = False
        handle = _stale_handle()
        rc, box, _, recover_fn, _, _, window, _ = self._run([handle, engine])
        self.assertEqual(rc, 0)
        recover_fn.assert_called_once_with(handle)
        box.askyesno.assert_not_called()
        box.showerror.assert_not_called()
        window.assert_called_once()

    def test_force_artifacts_recovers_without_prompt(self):
        engine = MagicMock()
        engine.blocked = False
        handle = _artifacts_handle()
        rc, box, _, recover_fn, _, _, window, _ = self._run([handle, engine])
        self.assertEqual(rc, 0)
        recover_fn.assert_called_once_with(handle)
        box.askyesno.assert_not_called()
        box.showerror.assert_not_called()
        window.assert_called_once()

    def test_force_stale_recovery_failure_exits_with_error(self):
        engine = MagicMock()
        engine.blocked = False
        handle = _stale_handle()
        rc, box, _, recover_fn, _, _, window, _ = self._run(
            [handle, engine], recover=(False, "boom"))
        self.assertEqual(rc, 1)
        recover_fn.assert_called_once_with(handle)
        window.assert_not_called()
        self.assertTrue(any("forced recovery failed" in str(call)
                            for call in box.showerror.call_args_list))

    def test_force_fence_dead_end_reclaims_and_starts(self):
        engine = MagicMock()
        engine.blocked = False
        refusal = StateError(
            "A recovery transaction owns this state; "
            "preserve its fence and evidence")
        rc, box, _, _, _, reclaim_fn, window, _ = self._run(
            [refusal, engine])
        self.assertEqual(rc, 0)
        reclaim_fn.assert_called_once()
        box.askyesno.assert_not_called()
        box.showerror.assert_not_called()
        window.assert_called_once()

    def test_force_fence_reclaim_refusal_exits(self):
        engine = MagicMock()
        engine.blocked = False
        refusal = StateError(
            "A recovery transaction owns this state; "
            "preserve its fence and evidence")
        rc, box, _, _, _, reclaim_fn, window, _ = self._run(
            [refusal, refusal],
            force_reclaim=(False, "the recorded state owner (PID 4242, "
                                  "recovery fence) is proven alive; "
                                  "--force never displaces a live trainer "
                                  "session"))
        self.assertEqual(rc, 1)
        reclaim_fn.assert_called_once()
        window.assert_not_called()
        self.assertTrue(any("--force refusal" in str(call)
                            and "proven alive" in str(call)
                            for call in box.showerror.call_args_list))

    def test_force_live_conflict_refused_without_termination(self):
        engine = MagicMock()
        engine.blocked = False
        handle = _live_handle(2222)
        rc, box, _, _, terminate_fn, _, window, _ = self._run(
            [handle, engine])
        self.assertEqual(rc, 1)
        terminate_fn.assert_not_called()
        window.assert_not_called()
        self.assertTrue(any("--force refusal" in str(call)
                            and "proven alive" in str(call)
                            for call in box.showerror.call_args_list))


if __name__ == "__main__":
    unittest.main()
