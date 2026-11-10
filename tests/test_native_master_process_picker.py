"""Process-selection decision logic for the Master Trainer (MT-11, 0.25).

Covers the pure decision layer in ``process_picker``: deterministic
candidate collection over the snapshot, the attach decision matrix
(auto/ask x zero/one/many candidates), the named refusal for an
unknown attach mode, and the pinned memory factory (pinned PID honoured,
pin self-clearing once the PID is gone, name-based fallback, smallest-
PID multi-instance fallback, pass-through refusal when nothing runs).
The native ``ProcessMemory`` is replaced with a deterministic fake; no
real process is touched.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from ct2trainer.native.master_trainer.process_picker import (
    DECISION_ATTACH_DIRECT,
    DECISION_PICK,
    DECISION_WAIT,
    attach_decision,
    candidate_display_text,
    candidate_processes,
    format_creation_time,
    make_pinned_memory_factory,
)
from ct2trainer.native.master_trainer.process_watch import ProcessSnapshotEntry
from ct2trainer.native.memory import ProcessMemoryError


def _snap(pid, name):
    return ProcessSnapshotEntry(pid, name)


class CandidateProcessesTests(unittest.TestCase):
    def test_no_candidates_when_nothing_runs(self):
        self.assertEqual(candidate_processes([], ("GameA.exe",)), ())

    def test_matches_bound_names_case_insensitively(self):
        snapshot = [
            _snap(10, "GameA.exe"),
            _snap(20, "Other.exe"),
            _snap(30, "gamea.exe"),
        ]
        out = candidate_processes(snapshot, ("GameA.exe",))
        self.assertEqual([e.pid for e in out], [10, 30])

    def test_matches_any_of_several_bound_names(self):
        snapshot = [
            _snap(10, "GameA.exe"),
            _snap(20, "GameB.exe"),
            _snap(30, "Other.exe"),
        ]
        out = candidate_processes(snapshot, ("GameA.exe", "GameB.exe"))
        self.assertEqual([e.pid for e in out], [10, 20])

    def test_deterministic_order_name_then_pid(self):
        snapshot = [
            _snap(30, "GameB.exe"),
            _snap(10, "GameA.exe"),
            _snap(20, "GameA.exe"),
        ]
        out = candidate_processes(snapshot, ("GameA.exe", "GameB.exe"))
        self.assertEqual([(e.name.casefold(), e.pid) for e in out],
                         [("gamea.exe", 10), ("gamea.exe", 20),
                          ("gameb.exe", 30)])


class AttachDecisionTests(unittest.TestCase):
    def test_auto_without_candidates_waits(self):
        self.assertEqual(attach_decision(()),
                         (DECISION_WAIT, None))

    def test_auto_single_candidate_attaches_direct(self):
        entry = _snap(7, "GameA.exe")
        self.assertEqual(attach_decision((entry,)),
                         (DECISION_ATTACH_DIRECT, entry))

    def test_auto_multiple_candidates_attaches_smallest_pid(self):
        small = _snap(5, "GameA.exe")
        big = _snap(9, "GameA.exe")
        self.assertEqual(attach_decision((big, small)),
                         (DECISION_ATTACH_DIRECT, small))

    def test_ask_without_candidates_waits(self):
        self.assertEqual(attach_decision((), attach_mode="ask"),
                         (DECISION_WAIT, None))

    def test_ask_single_candidate_picks(self):
        self.assertEqual(attach_decision((_snap(7, "GameA.exe"),),
                                         attach_mode="ask"),
                         (DECISION_PICK, None))

    def test_ask_multiple_candidates_picks(self):
        cands = (_snap(5, "GameA.exe"), _snap(9, "GameA.exe"))
        self.assertEqual(attach_decision(cands, attach_mode="ask"),
                         (DECISION_PICK, None))

    def test_unknown_attach_mode_refused(self):
        with self.assertRaisesRegex(ValueError, "attach_mode"):
            attach_decision((_snap(7, "GameA.exe"),),
                           attach_mode="sometimes")


class _FakeLister:
    def __init__(self, entries=()):
        self.entries = list(entries)

    def list_processes(self):
        return list(self.entries)


class _FakeMem:
    def __init__(self, pid):
        self.pid = pid


class _FakeMemoryClass:
    """Deterministic stand-in for ProcessMemory.

    ``instances`` maps casefolded name to the PIDs currently running;
    ``fail_pids`` are explicit-PID opens that fail (the PID is gone);
    ``fail_name_based`` makes the name-based open fail (used to force
    the multi-instance fallback path).
    """

    def __init__(self, instances, fail_pids=(), fail_name_based=False):
        self.instances = {k.casefold(): list(v)
                          for k, v in instances.items()}
        self.fail_pids = set(fail_pids)
        self.fail_name_based = fail_name_based
        self.calls = []

    def __call__(self, name, pid=None):
        key = name.casefold()
        pids = self.instances.get(key, [])
        self.calls.append((name, pid))
        if pid is not None:
            if pid in self.fail_pids or pid not in pids:
                raise ProcessMemoryError("pid gone")
            return _FakeMem(pid)
        if self.fail_name_based:
            raise ProcessMemoryError("multiple instances")
        if len(pids) == 1:
            return _FakeMem(pids[0])
        raise ProcessMemoryError("multiple instances")


class PinnedMemoryFactoryTests(unittest.TestCase):
    """The factory resolves ProcessMemory from the memory module at call
    time, so every scenario patches that module attribute."""

    def _run(self, fake, pin, lister_entries=()):
        lister = _FakeLister([_snap(pid, name)
                             for pid, name in lister_entries])
        factory = make_pinned_memory_factory(lister, pin)
        with patch("ct2trainer.native.memory.ProcessMemory", fake), \
                patch("ct2trainer.native.memory.ProcessMemoryError",
                      ProcessMemoryError):
            return factory("GameA.exe"), fake.calls

    def test_pin_honoured(self):
        fake = _FakeMemoryClass({"GameA.exe": [7, 9]})
        pin = {"pid": 9}
        mem, calls = self._run(fake, pin)
        self.assertEqual(mem.pid, 9)
        self.assertEqual(calls, [("GameA.exe", 9)])
        self.assertEqual(pin, {"pid": 9})

    def test_pin_self_clears_when_pid_gone(self):
        fake = _FakeMemoryClass({"GameA.exe": [7]}, fail_pids=(9,))
        pin = {"pid": 9}
        mem, calls = self._run(fake, pin)
        self.assertEqual(mem.pid, 7)  # fell back to the name-based open
        self.assertIsNone(pin["pid"])  # stale pin cleared
        self.assertEqual(calls, [("GameA.exe", 9), ("GameA.exe", None)])

    def test_no_pin_opens_name_based(self):
        fake = _FakeMemoryClass({"GameA.exe": [7]})
        mem, calls = self._run(fake, {"pid": None})
        self.assertEqual(mem.pid, 7)
        self.assertEqual(calls, [("GameA.exe", None)])

    def test_multi_instance_fallback_to_smallest_pid(self):
        fake = _FakeMemoryClass({"GameA.exe": [11, 4]},
                                fail_name_based=True)
        mem, calls = self._run(fake, {"pid": None},
                               lister_entries=[(11, "GameA.exe"),
                                               (4, "GameA.exe"),
                                               (2, "Other.exe")])
        self.assertEqual(mem.pid, 4)
        self.assertEqual(calls, [("GameA.exe", None),
                                 ("GameA.exe", 4)])

    def test_no_candidates_reraises_the_refusal(self):
        fake = _FakeMemoryClass({"GameA.exe": []}, fail_name_based=True)
        pin = {"pid": None}
        lister = _FakeLister()
        factory = make_pinned_memory_factory(lister, pin)
        with patch("ct2trainer.native.memory.ProcessMemory", fake), \
                patch("ct2trainer.native.memory.ProcessMemoryError",
                      ProcessMemoryError):
            with self.assertRaises(ProcessMemoryError):
                factory("GameA.exe")
        self.assertEqual(fake.calls, [("GameA.exe", None)])


class CandidateDisplayTextTests(unittest.TestCase):
    """MT-31 (0.40): the picker / details row text for one candidate."""

    def test_unenriched_rows_stay_byte_stable_against_the_pre_040_form(self):
        entry = ProcessSnapshotEntry(7, "GameA.exe")
        self.assertEqual(candidate_display_text(entry),
                         "GameA.exe  (PID 7)")

    def test_only_the_proved_facts_render(self):
        # One fact at a time: every None field is refused (fail-closed)
        # and never rendered.
        entry = ProcessSnapshotEntry(
            7, "GameA.exe", path="C:\\games\\GameA.exe")
        self.assertEqual(
            candidate_display_text(entry),
            "GameA.exe  (PID 7)  -  C:\\games\\GameA.exe")
        entry = ProcessSnapshotEntry(
            7, "GameA.exe", creation_time=1700000000.0)
        self.assertEqual(
            candidate_display_text(entry),
            "GameA.exe  (PID 7)  -  started "
            + format_creation_time(1700000000.0))
        entry = ProcessSnapshotEntry(7, "GameA.exe", pointer_size=4)
        self.assertEqual(candidate_display_text(entry),
                         "GameA.exe  (PID 7)  -  32-bit")

    def test_full_identification_renders_all_facts_in_order(self):
        entry = ProcessSnapshotEntry(
            7, "GameA.exe", path="C:\\games\\GameA.exe",
            creation_time=1700000000.0, pointer_size=8)
        self.assertEqual(
            candidate_display_text(entry),
            "GameA.exe  (PID 7)  -  C:\\games\\GameA.exe  -  started "
            + format_creation_time(1700000000.0) + "  -  64-bit")

    def test_the_creation_time_uses_the_modified_column_style(self):
        # 1700000000.0 is 2023-11-14 22:13:20 UTC; the local rendering
        # keeps the year and the day may shift by one at the extremes
        # of the timezone offsets - the format is the contract.
        text = format_creation_time(1700000000.0)
        self.assertRegex(text, r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
        self.assertTrue(text.startswith("2023-11-1"))


if __name__ == "__main__":
    unittest.main()
