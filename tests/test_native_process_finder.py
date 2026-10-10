"""Process finder contracts: exact (pid, created) identity, no silent choice."""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from ct2trainer.native import process_finder
from ct2trainer.native.process_finder import (
    ProcessCandidate,
    ProcessFinder,
    ProcessFinderError,
    names_match,
    validate_basename,
)
from ct2trainer.native.recovery import ProcessIdentity, WindowsProcessProbe


@unittest.skipUnless(sys.platform == "win32", "Win32 process enumeration required")
class RealProcessFinderTests(unittest.TestCase):
    def setUp(self):
        self.children = []
        self.addCleanup(self.stop_children)

    def spawn(self):
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        self.children.append(child)
        return child

    def stop_children(self):
        for child in self.children:
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=10)

    def test_spawned_child_is_found_with_its_exact_creation_identity(self):
        child = self.spawn()
        name = Path(sys.executable).name
        result = ProcessFinder().find(name)
        self.assertIn(child.pid, [item.pid for item in result.matches])
        candidate = next(item for item in result.matches if item.pid == child.pid)
        self.assertEqual(candidate.name, name)
        self.assertTrue(candidate.certain)
        probe = WindowsProcessProbe()(ProcessIdentity(child.pid, None))
        self.assertEqual(probe.status, "alive", probe)
        self.assertEqual(candidate.creation_time, probe.observed_created)

    def test_original_snapshot_spelling_is_kept_for_display(self):
        child = self.spawn()
        name = Path(sys.executable).name
        result = ProcessFinder().find(name.upper())
        candidate = next(item for item in result.matches if item.pid == child.pid)
        self.assertEqual(candidate.name, name)
        self.assertNotEqual(name, name.upper())
        self.assertEqual(result.requested, name.upper())

    def test_multiple_children_are_ambiguous_and_never_silently_chosen(self):
        first, second = self.spawn(), self.spawn()
        name = Path(sys.executable).name
        result = ProcessFinder().find(name)
        pids = [item.pid for item in result.matches]
        self.assertIn(first.pid, pids)
        self.assertIn(second.pid, pids)
        self.assertGreater(len(pids), 1)
        self.assertEqual(result.status, "ambiguous")
        self.assertIsNone(result.single)
        finder = ProcessFinder()
        for child in (first, second):
            probe = WindowsProcessProbe()(ProcessIdentity(child.pid, None))
            chosen = finder.select(result, (child.pid, probe.observed_created))
            self.assertEqual(chosen.pid, child.pid)

    def test_pid_reuse_is_a_different_identity_after_child_restart(self):
        name = Path(sys.executable).name
        old = self.spawn()
        probe = WindowsProcessProbe()
        observed = probe(ProcessIdentity(old.pid, None))
        old_identity = (old.pid, observed.observed_created)
        self.stop_children()
        new = self.spawn()
        self.addCleanup(self.stop_children)
        observed_new = probe(ProcessIdentity(new.pid, None))
        new_identity = (new.pid, observed_new.observed_created)
        self.assertEqual(new_identity[1], observed_new.observed_created)
        result = ProcessFinder().find(name)
        ids = [item.identity for item in result.matches]
        self.assertIn(new_identity, ids)
        self.assertNotIn(old_identity, ids)
        old_candidate = ProcessCandidate(*old_identity, name)
        self.assertTrue(ProcessFinder().verify(old_candidate) is False
                        or old_identity not in ids)

    def test_finder_never_terminates_external_processes(self):
        child = self.spawn()
        self.assertIsNone(child.poll())
        for _ in range(3):
            ProcessFinder().find(Path(sys.executable).name)
        self.assertIsNone(child.poll(), "the finder must never end the target process")
        for attr in ("kill", "terminate", "close_process", "destroy"):
            self.assertFalse(hasattr(ProcessFinder, attr))

    def test_verify_rechecks_the_creation_time_of_a_certain_candidate(self):
        child = self.spawn()
        probe = WindowsProcessProbe()(ProcessIdentity(child.pid, None))
        candidate = ProcessCandidate(child.pid, probe.observed_created, Path(sys.executable).name)
        self.assertTrue(ProcessFinder().verify(candidate))
        self.spawn()  # another process running; identity of the first is unchanged
        self.assertTrue(ProcessFinder().verify(candidate))


class DeterministicFinderTests(unittest.TestCase):
    def _finder(self, snapshot, creations):
        return ProcessFinder(snapshot_provider=lambda: snapshot,
                             creation_provider=lambda pid: creations.get(pid))

    def test_unique_certain_match_returns_single(self):
        finder = self._finder([(100, "game.exe")], {100: 4242})
        result = finder.find("game.exe")
        self.assertEqual(result.status, "unique")
        self.assertEqual(result.single.identity, (100, 4242))

    def test_single_unreadable_creation_time_stays_visible_but_uncertain(self):
        finder = self._finder([(100, "game.exe")], {})
        result = finder.find("game.exe")
        self.assertEqual(result.status, "uncertain")
        self.assertEqual(len(result.matches), 1)
        self.assertFalse(result.matches[0].certain)
        self.assertIsNone(result.single)

    def test_no_match_reports_none(self):
        result = self._finder([(100, "game.exe")], {100: 1}).find("other.exe")
        self.assertEqual(result.status, "none")
        self.assertEqual(result.matches, ())

    def test_selection_rejects_a_stale_identity(self):
        finder = self._finder([(100, "game.exe")], {100: 42})
        result = finder.find("game.exe")
        with self.assertRaises(ProcessFinderError):
            finder.select(result, (100, 9999))
        self.assertEqual(finder.select(result, (100, 42)).pid, 100)

    def test_verify_detects_creation_time_change(self):
        finder = self._finder([(100, "game.exe")], {100: 42})
        candidate = finder.find("game.exe").single
        self.assertTrue(finder.verify(candidate))
        finder._creation_provider = lambda pid: 43  # same PID, new creation time
        self.assertFalse(finder.verify(candidate))

    def test_results_are_sorted_deterministically(self):
        finder = self._finder([(300, "game.exe"), (100, "Game.EXE"), (200, "GAME.exe")],
                              {100: 1, 200: 2, 300: 3})
        result = finder.find("game.exe")
        self.assertEqual([item.pid for item in result.matches], [100, 200, 300])
        self.assertEqual(result.status, "ambiguous")

    def test_invalid_basenames_are_rejected(self):
        for bad in ("", "game .exe", "C:\\dir\\game.exe", "gam*.exe", ".", "..", "g" * 256, "a/b.exe"):
            with self.subTest(bad=bad):
                with self.assertRaises(ProcessFinderError):
                    validate_basename(bad)

    def test_non_windows_backend_is_refused_without_injection(self):
        with mock.patch.object(sys, "platform", "linux"):
            with self.assertRaises(ProcessFinderError):
                ProcessFinder()
            # non-ASCII names are never matched off-Windows (no ordinal backend)
            self.assertFalse(names_match("Übung.exe", "übung.exe"))

    def test_ordinal_ascii_case_insensitive_matching(self):
        self.assertTrue(names_match("Game.EXE", "game.exe"))
        self.assertTrue(names_match("game.exe", "game.exe"))
        self.assertFalse(names_match("game.exe", "other.exe"))


@unittest.skipUnless(sys.platform == "win32", "CompareStringOrdinal required")
class OrdinalUnicodeTests(unittest.TestCase):
    def test_ordinal_compare_folds_case_but_not_linguistic_equivalence(self):
        # ordinal case folding applies to Unicode letters...
        self.assertTrue(names_match("Übung.exe", "übung.exe"))
        self.assertTrue(names_match("Γamma.exe", "γamma.exe"))
        # ...but ß is never equated with the digraph ss
        self.assertFalse(names_match("ßpiel.exe", "sspiel.exe"))


if __name__ == "__main__":
    unittest.main()
