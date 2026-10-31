"""Master Trainer orchestrator (MT-3): waiting-mode state machine contract.

Covers: the state constants and initial state, tick guards (loading/
active raise), snapshot-failure handling, the deterministic match
policy (first casefold-sorted name, lowest PID), single-table auto-load
requests, multi-table choices (open, idempotent re-tick, open-choice
stability, stale drop with re-request), the all-unreadable dead end,
choose/cancel state guards and plan handoff, load failure memory
(fail-closed loop guard, PID-gone re-arm via _drop_stale), fail_load,
mark_active/deactivate guards, suppress/retry semantics, and
process_name_display. All tests run on a deterministic fake lister and
fake plan compiler; no real processes are spawned.
"""
from __future__ import annotations

import unittest

from ct2trainer.native.master_trainer.orchestrator import (
    STATE_ACTIVE,
    STATE_CHOOSING,
    STATE_LOADING,
    STATE_WAITING,
    LoadOutcome,
    MasterOrchestrator,
    PendingChoice,
    TickOutcome,
    process_name_display,
)
from ct2trainer.native.master_trainer.process_watch import (
    ProcessLister,
    ProcessSnapshotEntry,
)
from ct2trainer.native.master_trainer.table_index import TableEntry, TableIndex


def _entry(relative_path, names, status="ok", detail=None):
    return TableEntry(relative_path, 10, 20, "ab" * 32, tuple(names),
                      status, detail)


def _index(*entries):
    return TableIndex("C:\\tables", {e.relative_path: e for e in entries})


def _snap(pid, name):
    return ProcessSnapshotEntry(pid, name)


class FakeLister(ProcessLister):
    """Deterministic snapshot source; the snapshot is mutable per tick."""

    def __init__(self, snapshot=(), error=None):
        self.snapshot = list(snapshot)
        self.error = error
        self.calls = 0

    def list_processes(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return list(self.snapshot)


class RecordingCompiler:
    def __init__(self):
        self.calls = []

    def __call__(self, table, process_name):
        self.calls.append((table.relative_path, process_name))
        return {"plan": table.relative_path}


class FailingOnceCompiler:
    def __init__(self, message="compile refused: bad plan"):
        self.message = message
        self.calls = []

    def __call__(self, table, process_name):
        self.calls.append((table.relative_path, process_name))
        if len(self.calls) == 1:
            raise ValueError(self.message)
        return {"plan": table.relative_path}


class OrchestratorFixture:
    """Shared helpers; each test builds a fresh orchestrator."""

    @staticmethod
    def make(index, snapshot, compiler=None, lister=None):
        if compiler is None:
            compiler = RecordingCompiler()
        if lister is None:
            lister = FakeLister(snapshot)
        orch = MasterOrchestrator(index, lister, compiler, now=lambda: 0.0)
        return orch, lister, compiler

    @classmethod
    def drive_to_request(cls, index, snapshot):
        orch, lister, compiler = cls.make(index, snapshot)
        outcome = orch.tick()
        assert outcome.request is not None
        orch.load(outcome.request, outcome.request_process)
        return orch, lister, compiler, outcome

    @classmethod
    def drive_to_active(cls, index, snapshot):
        orch, lister, compiler, _ = cls.drive_to_request(index, snapshot)
        orch.mark_active()
        return orch, lister, compiler

    @classmethod
    def drive_to_choice(cls, index, snapshot):
        orch, lister, compiler = cls.make(index, snapshot)
        outcome = orch.tick()
        assert outcome.choice is not None
        return orch, lister, compiler, outcome


class StateAndQueryTests(unittest.TestCase):
    def test_initial_state_is_waiting_and_idle(self):
        orch, _, _ = OrchestratorFixture.make(
            _index(_entry("alpha.ct", ("Game.exe",))),
            [_snap(7, "game.exe")])
        self.assertEqual(orch.state, STATE_WAITING)
        self.assertIsNone(orch.choice)
        self.assertIsNone(orch.last_error)
        self.assertEqual(orch.last_tick_detail, "")
        self.assertTrue(orch.is_idle())
        self.assertEqual(orch.bound_process_names, ["Game.exe"])

    def test_tick_raises_in_loading_state(self):
        index = _index(_entry("alpha.ct", ("Game.exe",)))
        orch, lister, _ = OrchestratorFixture.make(index, [_snap(7, "game.exe")])
        outcome = orch.tick()
        orch.load(outcome.request, outcome.request_process)
        self.assertEqual(orch.state, STATE_LOADING)
        calls_before = lister.calls
        with self.assertRaises(ValueError) as ctx:
            orch.tick()
        self.assertEqual(str(ctx.exception),
                         "tick is only valid while the Master waits")
        self.assertEqual(orch.state, STATE_LOADING)
        self.assertEqual(lister.calls, calls_before)  # snapshot not taken

    def test_tick_raises_in_active_state(self):
        index = _index(_entry("alpha.ct", ("Game.exe",)))
        orch, lister, _ = OrchestratorFixture.make(index, [_snap(7, "game.exe")])
        outcome = orch.tick()
        orch.load(outcome.request, outcome.request_process)
        orch.mark_active()
        self.assertEqual(orch.state, STATE_ACTIVE)
        calls_before = lister.calls
        with self.assertRaises(ValueError) as ctx:
            orch.tick()
        self.assertEqual(str(ctx.exception),
                         "tick is only valid while the Master waits")
        self.assertEqual(orch.state, STATE_ACTIVE)
        self.assertEqual(lister.calls, calls_before)

    def test_is_idle_by_state(self):
        index = _index(_entry("alpha.ct", ("Game.exe",)))
        multi = _index(_entry("alpha.ct", ("Game.exe",)),
                       _entry("beta.ct", ("GAME.EXE",)))
        # waiting
        orch, _, _ = OrchestratorFixture.make(index, [_snap(7, "game.exe")])
        self.assertTrue(orch.is_idle())
        # loading and active are not idle
        outcome = orch.tick()
        orch.load(outcome.request, outcome.request_process)
        self.assertFalse(orch.is_idle())
        orch.mark_active()
        self.assertFalse(orch.is_idle())
        # choosing is idle
        orch2, _, _ = OrchestratorFixture.make(multi, [_snap(7, "game.exe")])
        orch2.tick()
        self.assertEqual(orch2.state, STATE_CHOOSING)
        self.assertTrue(orch2.is_idle())


class SnapshotFailureTests(unittest.TestCase):
    def test_lister_failure_is_named_and_state_kept(self):
        index = _index(_entry("alpha.ct", ("Game.exe",)))
        orch, lister, _ = OrchestratorFixture.make(
            index, [_snap(7, "game.exe")],
            lister=FakeLister([_snap(7, "game.exe")],
                              error=ProcessWatchErrorLike("snapshot backend exploded")))
        outcome = orch.tick()
        self.assertEqual(outcome.state, STATE_WAITING)
        self.assertIsNone(outcome.request)
        self.assertIsNone(outcome.choice)
        self.assertEqual(outcome.reason,
                         "process snapshot failed: ProcessWatchErrorLike: "
                         "snapshot backend exploded")
        self.assertEqual(orch.last_error, outcome.reason)
        self.assertEqual(orch.last_tick_detail, outcome.reason)
        self.assertEqual(lister.calls, 1)

    def test_any_exception_is_caught_and_named(self):
        index = _index(_entry("alpha.ct", ("Game.exe",)))
        orch, _, _ = OrchestratorFixture.make(
            index, [], lister=FakeLister([], error=OSError("toolhelp dead")))
        outcome = orch.tick()
        self.assertEqual(outcome.reason, "process snapshot failed: OSError: toolhelp dead")
        self.assertEqual(orch.state, STATE_WAITING)


class ProcessWatchErrorLike(RuntimeError):
    """Stand-in so the exception class name in the reason is known."""


class DeterminismTests(unittest.TestCase):
    def test_first_casefold_sorted_name_wins(self):
        index = _index(_entry("alpha.ct", ("Zeta.exe",)),
                       _entry("beta.ct", ("Alpha.exe",)))
        orch, _, _ = OrchestratorFixture.make(
            index, [_snap(10, "zeta.exe"), _snap(20, "alpha.exe")])
        outcome = orch.tick()
        self.assertEqual(orch.state, STATE_WAITING)
        self.assertEqual(outcome.request.relative_path, "beta.ct")
        self.assertEqual(outcome.request_process.pid, 20)
        self.assertIsNone(outcome.reason)
        self.assertEqual(orch.last_tick_detail,
                         "matched alpha.exe (PID 20); loading beta.ct")

    def test_lowest_pid_wins_for_single_table(self):
        index = _index(_entry("alpha.ct", ("Game.exe",)))
        orch, _, _ = OrchestratorFixture.make(
            index, [_snap(50, "Game.exe"), _snap(10, "game.exe"),
                    _snap(30, "GAME.exe")])
        outcome = orch.tick()
        self.assertEqual(outcome.request_process.pid, 10)
        # The "matched ... loading" detail is on last_tick_detail; the
        # outcome reason is reserved for guard/deferral paths.
        self.assertIsNone(outcome.reason)
        self.assertEqual(orch.last_tick_detail,
                         "matched game.exe (PID 10); loading alpha.ct")

    def test_choice_uses_lowest_pid_process_name(self):
        index = _index(_entry("alpha.ct", ("Game.exe",)),
                       _entry("beta.ct", ("GAME.EXE",)))
        orch, _, compiler = OrchestratorFixture.make(
            index, [_snap(50, "Game.exe"), _snap(10, "game.exe")])
        outcome = orch.tick()
        self.assertEqual(outcome.choice.process_key, "game.exe")
        self.assertEqual(outcome.choice.process_name, "Game.exe")
        self.assertEqual([e.pid for e in outcome.choice.snapshot_entries],
                         [10, 50])
        result = orch.choose("alpha.ct")
        self.assertTrue(result.ok)
        self.assertEqual(compiler.calls, [("alpha.ct", "game.exe")])


class UniqueMatchTests(unittest.TestCase):
    def test_unique_single_table_request(self):
        index = _index(_entry("alpha.ct", ("Game.exe",)))
        orch, _, _ = OrchestratorFixture.make(index, [_snap(7, "game.exe")])
        outcome = orch.tick()
        self.assertEqual(orch.state, STATE_WAITING)
        self.assertIsInstance(outcome, TickOutcome)
        self.assertEqual(outcome.request.relative_path, "alpha.ct")
        self.assertEqual(outcome.request_process, _snap(7, "game.exe"))
        self.assertIsNone(outcome.choice)
        self.assertIsNone(outcome.reason)
        self.assertEqual(orch.last_tick_detail,
                         "matched game.exe (PID 7); loading alpha.ct")
        self.assertIsNone(orch.last_error)

    def test_no_match_stays_waiting_with_counted_detail(self):
        index = _index(_entry("alpha.ct", ("Game.exe",)),
                       _entry("beta.ct", ("Other.exe",)))
        orch, _, _ = OrchestratorFixture.make(
            index, [_snap(7, "Unrelated.exe")])
        outcome = orch.tick()
        self.assertEqual(orch.state, STATE_WAITING)
        self.assertIsNone(outcome.request)
        self.assertIsNone(outcome.reason)
        self.assertEqual(orch.last_tick_detail,
                         "scanned 1 processes; none of the 2 bound "
                         "target(s) is running")
        self.assertIsNone(orch.last_error)

    def test_no_match_empty_snapshot(self):
        index = _index(_entry("alpha.ct", ("Game.exe",)))
        orch, _, _ = OrchestratorFixture.make(index, [])
        outcome = orch.tick()
        self.assertIsNone(outcome.reason)
        self.assertEqual(orch.last_tick_detail,
                         "scanned 0 processes; none of the 1 bound "
                         "target(s) is running")


class MultiTableChoiceTests(unittest.TestCase):
    def test_multi_table_match_opens_choice(self):
        index = _index(_entry("alpha.ct", ("Game.exe",)),
                       _entry("beta.ct", ("GAME.EXE",)))
        orch, _, _ = OrchestratorFixture.make(
            index, [_snap(50, "Game.exe"), _snap(10, "game.exe")])
        outcome = orch.tick()
        self.assertEqual(orch.state, STATE_CHOOSING)
        self.assertIsInstance(outcome.choice, PendingChoice)
        choice = outcome.choice
        self.assertEqual(choice.process_key, "game.exe")
        self.assertEqual(choice.process_name, "Game.exe")
        self.assertEqual([e.pid for e in choice.snapshot_entries], [10, 50])
        self.assertEqual([t.relative_path for t in choice.tables],
                         ["alpha.ct", "beta.ct"])
        self.assertEqual(orch.last_tick_detail,
                         "matched Game.exe (PID 10, 50); 2 tables bind to "
                         "it - choosing")
        self.assertIsNone(orch.last_error)

    def test_re_tick_with_open_choice_is_idempotent(self):
        index = _index(_entry("alpha.ct", ("Game.exe",)),
                       _entry("beta.ct", ("GAME.EXE",)))
        orch, lister, _ = OrchestratorFixture.make(
            index, [_snap(50, "Game.exe"), _snap(10, "game.exe")])
        first = orch.tick()
        calls_after_first = lister.calls
        second = orch.tick()
        self.assertEqual(orch.state, STATE_CHOOSING)
        self.assertIs(second.choice, first.choice)
        self.assertIsNone(second.request)
        self.assertEqual(lister.calls, calls_after_first + 1)

    def test_open_choice_stability_when_other_name_matches(self):
        index = _index(_entry("alpha.ct", ("Alpha.exe",)),
                       _entry("alpha2.ct", ("ALPHA.EXE",)),
                       _entry("beta.ct", ("Beta.exe",)))
        orch, _, _ = OrchestratorFixture.make(
            index, [_snap(1, "alpha.exe"), _snap(2, "beta.exe")])
        first = orch.tick()
        self.assertEqual(first.choice.process_key, "alpha.exe")
        second = orch.tick()
        self.assertEqual(orch.state, STATE_CHOOSING)
        self.assertIs(second.choice, first.choice)
        self.assertIsNone(second.request)  # no load for beta while open

    def test_stale_choice_dropped_and_re_request_issued(self):
        index = _index(_entry("alpha.ct", ("Alpha.exe",)),
                       _entry("alpha2.ct", ("ALPHA.EXE",)),
                       _entry("beta.ct", ("Beta.exe",)))
        orch, lister, _ = OrchestratorFixture.make(
            index, [_snap(1, "alpha.exe"), _snap(2, "beta.exe")])
        opened = orch.tick()
        self.assertEqual(opened.choice.process_key, "alpha.exe")
        # The alpha process is gone; only beta remains now.
        lister.snapshot = [_snap(9, "beta.exe")]
        outcome = orch.tick()
        self.assertEqual(orch.state, STATE_WAITING)
        self.assertIsNone(orch.choice)
        self.assertEqual(outcome.request.relative_path, "beta.ct")
        self.assertEqual(outcome.request_process.pid, 9)


class UnreadableDeadEndTests(unittest.TestCase):
    def test_all_tables_unreadable_is_named_dead_end(self):
        index = _index(_entry("alpha.ct", ("GameX.exe",),
                              status="unreadable", detail="parse failed"))
        self.assertEqual(index.process_name_set(), {"gamex.exe"})
        orch, _, _ = OrchestratorFixture.make(index, [_snap(5, "GameX.exe")])
        outcome = orch.tick()
        self.assertEqual(orch.state, STATE_WAITING)
        self.assertIsNone(outcome.request)
        self.assertIsNone(outcome.choice)
        self.assertEqual(outcome.reason,
                         "matched process 'GameX.exe' but every bound "
                         "table is unreadable")
        self.assertEqual(orch.last_error, outcome.reason)


class ChooseCancelTests(unittest.TestCase):
    def test_choose_in_wrong_state_raises(self):
        index = _index(_entry("alpha.ct", ("Game.exe",)),
                       _entry("beta.ct", ("GAME.EXE",)))
        orch, _, _ = OrchestratorFixture.make(index, [])
        with self.assertRaises(ValueError) as ctx:
            orch.choose("alpha.ct")
        self.assertEqual(str(ctx.exception), "no open table choice")

    def test_choose_unknown_relative_raises(self):
        index = _index(_entry("alpha.ct", ("Game.exe",)),
                       _entry("beta.ct", ("GAME.EXE",)))
        orch, _, _ = OrchestratorFixture.make(
            index, [_snap(50, "Game.exe"), _snap(10, "game.exe")])
        orch.tick()
        with self.assertRaises(ValueError) as ctx:
            orch.choose("nope.ct")
        self.assertEqual(str(ctx.exception),
                         "chosen table is not part of the open choice")
        self.assertEqual(orch.state, STATE_CHOOSING)

    def test_choose_success_compiles_and_loads(self):
        index = _index(_entry("alpha.ct", ("Game.exe",)),
                       _entry("beta.ct", ("GAME.EXE",)))
        orch, _, compiler = OrchestratorFixture.make(
            index, [_snap(50, "Game.exe"), _snap(10, "game.exe")])
        orch.tick()
        result = orch.choose("alpha.ct")
        self.assertIsInstance(result, LoadOutcome)
        self.assertTrue(result.ok)
        self.assertEqual(result.plan, {"plan": "alpha.ct"})
        self.assertIsNone(result.error)
        self.assertEqual(orch.state, STATE_LOADING)
        self.assertEqual(compiler.calls, [("alpha.ct", "game.exe")])
        self.assertEqual(orch._load_in_flight[0].relative_path, "alpha.ct")
        self.assertEqual(orch._load_in_flight[1].pid, 10)

    def test_choose_in_loading_state_raises(self):
        index = _index(_entry("alpha.ct", ("Game.exe",)))
        orch, _, _ = OrchestratorFixture.make(index, [_snap(7, "game.exe")])
        outcome = orch.tick()
        orch.load(outcome.request, outcome.request_process)
        with self.assertRaises(ValueError):
            orch.choose("alpha.ct")

    def test_cancel_choice_returns_to_waiting(self):
        index = _index(_entry("alpha.ct", ("Game.exe",)),
                       _entry("beta.ct", ("GAME.EXE",)))
        orch, _, _ = OrchestratorFixture.make(
            index, [_snap(50, "Game.exe"), _snap(10, "game.exe")])
        opened = orch.tick()
        orch.cancel_choice()
        self.assertEqual(orch.state, STATE_WAITING)
        self.assertIsNone(orch.choice)
        # The picker re-appears on the next tick (no silent suppression).
        again = orch.tick()
        self.assertEqual(orch.state, STATE_CHOOSING)
        self.assertIsNot(again.choice, opened.choice)

    def test_cancel_choice_wrong_state_raises(self):
        index = _index(_entry("alpha.ct", ("Game.exe",)))
        orch, _, _ = OrchestratorFixture.make(index, [_snap(7, "game.exe")])
        with self.assertRaises(ValueError) as ctx:
            orch.cancel_choice()
        self.assertEqual(str(ctx.exception), "no open table choice")


class LoadFailGuardTests(unittest.TestCase):
    def test_load_failure_is_remembered_and_not_auto_retried(self):
        index = _index(_entry("alpha.ct", ("Game.exe",)))
        compiler = FailingOnceCompiler()
        orch, lister, _ = OrchestratorFixture.make(index, [_snap(7, "game.exe")],
                                                   compiler=compiler)
        outcome = orch.tick()
        result = orch.load(outcome.request, outcome.request_process)
        self.assertIsInstance(result, LoadOutcome)
        self.assertFalse(result.ok)
        self.assertIsNone(result.plan)
        self.assertEqual(result.error, "ValueError: compile refused: bad plan")
        self.assertEqual(orch.state, STATE_WAITING)
        self.assertEqual(orch.last_error, result.error)
        self.assertEqual(orch.last_tick_detail,
                         "load failed for alpha.ct: "
                         "ValueError: compile refused: bad plan")
        # The same pair is not auto-requested again.
        again = orch.tick()
        self.assertIsNone(again.request)
        self.assertEqual(again.reason,
                         "auto-load suppressed (earlier failure for "
                         "alpha.ct: ValueError: compile refused: bad plan)")
        self.assertEqual(orch._failed,
                         {("game.exe", 7): "ValueError: compile refused: bad plan"})

    def test_failed_pair_uses_process_casefold_key(self):
        index = _index(_entry("alpha.ct", ("Game.exe",)))
        compiler = FailingOnceCompiler()
        orch, _, _ = OrchestratorFixture.make(
            index, [_snap(7, "gAmE.ExE")], compiler=compiler)
        outcome = orch.tick()
        orch.load(outcome.request, outcome.request_process)
        self.assertEqual(orch._failed,
                         {("game.exe", 7): "ValueError: compile refused: bad plan"})

    def test_fail_load_requires_inflight(self):
        index = _index(_entry("alpha.ct", ("Game.exe",)))
        orch, _, _ = OrchestratorFixture.make(index, [_snap(7, "game.exe")])
        with self.assertRaises(ValueError) as ctx:
            orch.fail_load("boom")
        self.assertEqual(str(ctx.exception), "no load is in flight")

    def test_fail_load_records_failure_and_blocks_auto_retry(self):
        index = _index(_entry("alpha.ct", ("Game.exe",)))
        orch, lister, _ = OrchestratorFixture.make(index, [_snap(7, "game.exe")])
        outcome = orch.tick()
        orch.load(outcome.request, outcome.request_process)
        self.assertEqual(orch.state, STATE_LOADING)
        orch.fail_load("engine start refused: state lock")
        self.assertEqual(orch.state, STATE_WAITING)
        self.assertEqual(orch.last_error, "engine start refused: state lock")
        self.assertEqual(orch.last_tick_detail,
                         "load failed for alpha.ct: engine start refused: state lock")
        again = orch.tick()
        self.assertIsNone(again.request)
        self.assertEqual(again.reason,
                         "auto-load suppressed (earlier failure for "
                         "alpha.ct: engine start refused: state lock)")
        with self.assertRaises(ValueError):
            orch.fail_load("again")  # no longer in flight

    def test_successful_load_stays_loading_until_confirmed(self):
        index = _index(_entry("alpha.ct", ("Game.exe",)))
        orch, _, compiler = OrchestratorFixture.make(index, [_snap(7, "game.exe")])
        outcome = orch.tick()
        result = orch.load(outcome.request, outcome.request_process)
        self.assertTrue(result.ok)
        self.assertEqual(result.plan, {"plan": "alpha.ct"})
        self.assertEqual(orch.state, STATE_LOADING)
        self.assertIsNotNone(orch._load_in_flight)


class ActiveStateTests(unittest.TestCase):
    def test_mark_active_requires_loading(self):
        index = _index(_entry("alpha.ct", ("Game.exe",)))
        orch, _, _ = OrchestratorFixture.make(index, [_snap(7, "game.exe")])
        with self.assertRaises(ValueError) as ctx:
            orch.mark_active()
        self.assertEqual(str(ctx.exception),
                         "a load must be in flight before activation")

    def test_mark_active_then_deactivate_roundtrip(self):
        index = _index(_entry("alpha.ct", ("Game.exe",)))
        orch, _, _ = OrchestratorFixture.make(index, [_snap(7, "game.exe")])
        outcome = orch.tick()
        orch.load(outcome.request, outcome.request_process)
        orch.mark_active()
        self.assertEqual(orch.state, STATE_ACTIVE)
        self.assertEqual(orch.last_tick_detail, "trainer session active")
        self.assertIsNone(orch.last_error)
        orch.deactivate()
        self.assertEqual(orch.state, STATE_WAITING)
        self.assertEqual(orch.last_tick_detail, "back to Master wait mode")
        # The wait loop works again after the roundtrip.
        again = orch.tick()
        self.assertEqual(again.request.relative_path, "alpha.ct")

    def test_deactivate_requires_active(self):
        index = _index(_entry("alpha.ct", ("Game.exe",)))
        orch, _, _ = OrchestratorFixture.make(index, [_snap(7, "game.exe")])
        with self.assertRaises(ValueError) as ctx:
            orch.deactivate()
        self.assertEqual(str(ctx.exception), "no active session to release")
        # Also refused while a load is in flight.
        outcome = orch.tick()
        orch.load(outcome.request, outcome.request_process)
        with self.assertRaises(ValueError):
            orch.deactivate()


class SuppressRetryTests(unittest.TestCase):
    def test_suppress_defers_exact_pair(self):
        index = _index(_entry("alpha.ct", ("Game.exe",)))
        orch, _, _ = OrchestratorFixture.make(index, [_snap(7, "game.exe")])
        orch.suppress("game.exe", 7)
        outcome = orch.tick()
        self.assertIsNone(outcome.request)
        self.assertEqual(outcome.reason,
                         "auto-load deferred (the user chose not to load "
                         "while this exact process is running; Retry load "
                         "re-arms)")
        self.assertIsNone(orch.last_error)
        self.assertEqual(orch.state, STATE_WAITING)

    def test_suppress_does_not_block_other_pids(self):
        index = _index(_entry("alpha.ct", ("Game.exe",)))
        orch, lister, _ = OrchestratorFixture.make(index, [_snap(7, "game.exe")])
        orch.suppress("game.exe", 7)
        lister.snapshot = [_snap(8, "game.exe")]
        outcome = orch.tick()
        self.assertEqual(outcome.request_process.pid, 8)

    def test_suppress_open_choice_stays_until_resolved(self):
        # While a choice is open for the matched key, the stable-choice
        # branch takes priority over the suppression check.
        index = _index(_entry("alpha.ct", ("Game.exe",)),
                       _entry("beta.ct", ("GAME.EXE",)))
        orch, _, _ = OrchestratorFixture.make(
            index, [_snap(1, "game.exe"), _snap(2, "Game.exe")])
        opened = orch.tick()
        self.assertEqual(orch.state, STATE_CHOOSING)
        orch.suppress("game.exe", 1)
        # The still-matching open choice is returned unchanged.
        again = orch.tick()
        self.assertEqual(orch.state, STATE_CHOOSING)
        self.assertIs(again.choice, opened.choice)
        # Once the picker is cancelled, the suppression takes effect.
        orch.cancel_choice()
        deferred = orch.tick()
        self.assertEqual(orch.state, STATE_WAITING)
        self.assertIsNone(orch.choice)
        self.assertIn("auto-load deferred", deferred.reason)

    def test_retry_with_no_args_clears_everything(self):
        index = _index(_entry("alpha.ct", ("Game.exe",)))
        compiler = FailingOnceCompiler()
        orch, lister, _ = OrchestratorFixture.make(
            index, [_snap(7, "game.exe")], compiler=compiler)
        outcome = orch.tick()
        orch.load(outcome.request, outcome.request_process)  # remembers (game.exe, 7)
        orch.suppress("game.exe", 7)
        orch.retry()
        self.assertEqual(orch._failed, {})
        self.assertEqual(orch._suppressed, set())
        self.assertEqual(orch.tick().request.relative_path, "alpha.ct")

    def test_retry_clears_exact_pair_only(self):
        index = _index(_entry("alpha.ct", ("Alpha.exe",)),
                       _entry("game.ct", ("Game.exe",)))
        compiler = FailingOnceCompiler()
        orch, lister, _ = OrchestratorFixture.make(
            index, [_snap(9, "alpha.exe"), _snap(7, "game.exe")],
            compiler=compiler)
        # Fail a direct load for the game pair, defer the alpha pair.
        orch.load(index.entries["game.ct"], _snap(7, "game.exe"))
        self.assertEqual(orch.state, STATE_WAITING)
        orch.suppress("alpha.exe", 9)
        orch.retry("game.exe", 7)
        self.assertEqual(orch._failed, {})
        self.assertEqual(orch._suppressed, {("alpha.exe", 9)})
        # Alpha is still deferred; game would now load.
        outcome = orch.tick()
        self.assertIsNone(outcome.request)
        self.assertIn("auto-load deferred", outcome.reason)
        orch.retry("alpha.exe", 9)
        outcome = orch.tick()
        self.assertEqual(outcome.request.relative_path, "alpha.ct")

    def test_retry_with_one_argument_raises(self):
        index = _index(_entry("alpha.ct", ("Game.exe",)))
        orch, _, _ = OrchestratorFixture.make(index, [_snap(7, "game.exe")])
        with self.assertRaises(ValueError) as ctx:
            orch.retry("game.exe")
        self.assertEqual(str(ctx.exception),
                         "retry needs both the process key and the PID, "
                         "or neither")
        with self.assertRaises(ValueError):
            orch.retry(pid=7)


class StaleDropTests(unittest.TestCase):
    def test_failed_pid_gone_rearms_auto_load(self):
        index = _index(_entry("alpha.ct", ("Game.exe",)))
        compiler = FailingOnceCompiler()
        orch, lister, _ = OrchestratorFixture.make(
            index, [_snap(7, "game.exe")], compiler=compiler)
        outcome = orch.tick()
        orch.load(outcome.request, outcome.request_process)
        self.assertEqual(orch._failed,
                         {("game.exe", 7): "ValueError: compile refused: bad plan"})
        # The failed process exited; a new PID for the same name started.
        lister.snapshot = [_snap(8, "game.exe")]
        outcome = orch.tick()
        self.assertEqual(outcome.request.relative_path, "alpha.ct")
        self.assertEqual(outcome.request_process.pid, 8)
        # The re-arm is per (name, pid): the stale record survives until a
        # no-match tick runs _drop_stale.
        self.assertIn(("game.exe", 7), orch._failed)
        lister.snapshot = [_snap(9, "Unrelated.exe")]
        orch.tick()
        self.assertEqual(orch._failed, {})

    def test_failed_pid_still_alive_keeps_guard(self):
        index = _index(_entry("alpha.ct", ("Game.exe",)))
        compiler = FailingOnceCompiler()
        orch, lister, _ = OrchestratorFixture.make(
            index, [_snap(7, "game.exe")], compiler=compiler)
        outcome = orch.tick()
        orch.load(outcome.request, outcome.request_process)
        again = orch.tick()
        self.assertIsNone(again.request)
        self.assertEqual(orch._failed,
                         {("game.exe", 7): "ValueError: compile refused: bad plan"})

    def test_drop_stale_drops_suppressed_pairs_too(self):
        index = _index(_entry("alpha.ct", ("Game.exe",)))
        orch, lister, _ = OrchestratorFixture.make(index, [_snap(7, "game.exe")])
        orch.suppress("game.exe", 7)
        lister.snapshot = [_snap(8, "game.exe")]
        outcome = orch.tick()
        # The deferred identity is gone; the fresh PID loads normally.
        self.assertEqual(outcome.request_process.pid, 8)
        # Stale deferral record persists until a no-match tick clears it.
        self.assertIn(("game.exe", 7), orch._suppressed)
        lister.snapshot = [_snap(9, "Unrelated.exe")]
        orch.tick()
        self.assertEqual(orch._suppressed, set())


class ProcessNameDisplayTests(unittest.TestCase):
    def test_single_pid(self):
        choice = PendingChoice("game.exe", "Game.exe",
                               (_snap(10, "game.exe"),), ())
        self.assertEqual(process_name_display(choice), "Game.exe (PID 10)")

    def test_multiple_pids(self):
        choice = PendingChoice("game.exe", "Game.exe",
                               (_snap(10, "game.exe"), _snap(20, "game.exe")),
                               ())
        self.assertEqual(process_name_display(choice), "Game.exe (PID 10, 20)")


if __name__ == "__main__":
    unittest.main()
