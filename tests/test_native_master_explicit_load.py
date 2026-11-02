"""Explicit user table load resolution (MT-10, 0.25).

Covers ``MasterOrchestrator.request_load``: the named
:class:`ExplicitLoadRefusal` codes (not-in-index, table-unreadable,
no-process-binding, process-snapshot-failed), the running-candidate
resolution (smallest-PID process, plan compiled against that
process's name), the no-candidate fallback (first bound name in
casefold order, synthetic zero-PID entry, the engine waits for the
process to start), and the documented loop-guard bypass (a remembered
failure for the pair does not block an explicit request; a later
``load()`` failure still records the ordinary suppression).
Deterministic fakes only; no real processes.
"""
from __future__ import annotations

import unittest

from test_native_master_orchestrator import (
    FakeLister,
    OrchestratorFixture,
    RecordingCompiler,
    _entry,
    _index,
    _snap,
)

from ct2trainer.native.master_trainer.orchestrator import (
    ExplicitLoadRefusal,
    MasterOrchestrator,
)


def _orch(snapshot, *entries, error=None):
    index = _index(*entries)
    compiler = RecordingCompiler()
    lister = FakeLister(snapshot, error=error)
    orch = MasterOrchestrator(index, lister, compiler, now=lambda: 0.0)
    return orch, lister, compiler


def _refusal_code(exc):
    return exc.code


class RequestLoadRefusalTests(unittest.TestCase):
    def test_not_in_index(self):
        orch, _, _ = _orch([], _entry("a.ct", ("GameA.exe",)))
        with self.assertRaises(ExplicitLoadRefusal) as ctx:
            orch.request_load("missing.ct")
        self.assertEqual(_refusal_code(ctx.exception), "not-in-index")
        self.assertIn("missing.ct", ctx.exception.detail)

    def test_empty_path_refused(self):
        orch, _, _ = _orch([], _entry("a.ct", ("GameA.exe",)))
        with self.assertRaises(ExplicitLoadRefusal) as ctx:
            orch.request_load("")
        self.assertEqual(_refusal_code(ctx.exception), "not-in-index")

    def test_non_string_path_refused(self):
        orch, _, _ = _orch([], _entry("a.ct", ("GameA.exe",)))
        with self.assertRaises(ExplicitLoadRefusal) as ctx:
            orch.request_load(None)
        self.assertEqual(_refusal_code(ctx.exception), "not-in-index")

    def test_table_unreadable_carries_the_scan_detail(self):
        orch, _, _ = _orch(
            [], _entry("bad.ct", (), status="unreadable",
                       detail="parse failed: TableError: boom"))
        with self.assertRaises(ExplicitLoadRefusal) as ctx:
            orch.request_load("bad.ct")
        self.assertEqual(_refusal_code(ctx.exception), "table-unreadable")
        self.assertIn("parse failed", ctx.exception.detail)

    def test_no_process_binding(self):
        orch, _, _ = _orch([], _entry("anon.ct", ()))
        with self.assertRaises(ExplicitLoadRefusal) as ctx:
            orch.request_load("anon.ct")
        self.assertEqual(_refusal_code(ctx.exception),
                         "no-process-binding")

    def test_snapshot_failure_named(self):
        orch, _, _ = _orch([], _entry("a.ct", ("GameA.exe",)),
                          error=OSError("list failed"))
        with self.assertRaises(ExplicitLoadRefusal) as ctx:
            orch.request_load("a.ct")
        self.assertEqual(_refusal_code(ctx.exception),
                         "process-snapshot-failed")
        self.assertIn("list failed", ctx.exception.detail)


class RequestLoadResolutionTests(unittest.TestCase):
    def test_no_running_process_waits_for_start(self):
        orch, _, _ = _orch([], _entry("a.ct", ("GameA.exe",)))
        request = orch.request_load("a.ct")
        self.assertEqual(request.plan_process, "GameA.exe")
        self.assertEqual(request.candidates, ())
        self.assertEqual(request.process.pid, 0)
        self.assertEqual(request.process.name, "GameA.exe")
        self.assertEqual(request.table.relative_path, "a.ct")

    def test_running_candidate_wins_with_smallest_pid(self):
        snap = [_snap(9, "GameA.exe"), _snap(5, "GameA.exe")]
        orch, _, _ = _orch(snap, _entry("a.ct", ("GameA.exe",)))
        request = orch.request_load("a.ct")
        self.assertEqual(request.plan_process, "GameA.exe")
        self.assertEqual(request.process.pid, 5)
        self.assertEqual([e.pid for e in request.candidates], [5, 9])

    def test_plan_process_uses_the_snapshot_name_spelling(self):
        snap = [_snap(5, "gamea.exe")]
        orch, _, _ = _orch(snap, _entry("a.ct", ("GameA.exe",)))
        request = orch.request_load("a.ct")
        self.assertEqual(request.plan_process, "gamea.exe")

    def test_multi_name_table_resolves_the_running_bound_name(self):
        snap = [_snap(3, "GameB.exe")]
        orch, _, _ = _orch(
            snap, _entry("a.ct", ("GameA.exe", "GameB.exe")))
        request = orch.request_load("a.ct")
        self.assertEqual(request.plan_process, "GameB.exe")
        self.assertEqual(request.process.pid, 3)

    def test_unmatched_running_process_is_not_a_candidate(self):
        snap = [_snap(3, "Other.exe")]
        orch, _, _ = _orch(snap, _entry("a.ct", ("GameA.exe",)))
        request = orch.request_load("a.ct")
        self.assertEqual(request.candidates, ())
        self.assertEqual(request.process.pid, 0)


class RequestLoadLoopGuardBypassTests(unittest.TestCase):
    def test_remembered_failure_does_not_block_explicit_request(self):
        # A failed auto-load for the exact (name, PID) pair is recorded
        # by load(); the explicit request must still resolve.
        snap = [_snap(5, "GameA.exe")]
        orch, lister, compiler = _orch(
            snap, _entry("a.ct", ("GameA.exe",)))

        def failing(_table, _name):
            raise ValueError("compile refused: bad plan")

        orch.plan_compiler = failing
        outcome = orch.load(_entry("a.ct", ("GameA.exe",)),
                            _snap(5, "GameA.exe"))
        self.assertFalse(outcome.ok)
        self.assertIn(("gamea.exe", 5), orch._failed)

        # The auto-load tick is suppressed for the pair (loop guard).
        tick = orch.tick()
        self.assertIsNotNone(tick.reason)
        self.assertIn("auto-load suppressed", tick.reason)

        # The explicit request still resolves the same table.
        request = orch.request_load("a.ct")
        self.assertEqual(request.process.pid, 5)

    def test_explicit_load_failure_still_rearms_the_loop_guard(self):
        snap = [_snap(5, "GameA.exe")]
        orch, _, _ = _orch(snap, _entry("a.ct", ("GameA.exe",)))
        request = orch.request_load("a.ct")
        orch.plan_compiler = lambda _t, _n: (_ for _ in ()).throw(
            ValueError("explicit compile refused"))
        outcome = orch.load(request.table, request.process)
        self.assertFalse(outcome.ok)
        self.assertIn(("gamea.exe", 5), orch._failed)
        tick = orch.tick()
        self.assertIn("auto-load suppressed", tick.reason)


if __name__ == "__main__":
    unittest.main()
