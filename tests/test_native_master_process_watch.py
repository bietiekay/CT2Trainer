"""Master Trainer process watch (MT-2): snapshot backends + target matching.

Covers: the frozen snapshot entry, the read-only lister contract, the
procfs backend over a fake /proc tree (numeric pid dirs, exe links,
skips for non-numeric dirs / missing or unreadable exe, missing proc
root), the platform branch of default_process_lister (the other branch
exercised by patching sys.platform), the ordinal/casefold semantics of
names_match, and the pure match_targets decision function. All core
logic tests run on deterministic fakes; no real processes are spawned.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ct2trainer.native.master_trainer.process_watch import (
    ProcessLister,
    ProcessSnapshotEntry,
    ProcessWatchError,
    ProcfsProcessLister,
    WindowsProcessLister,
    default_process_lister,
    match_targets,
    names_match,
)


def _symlink_capable() -> bool:
    """Probe os.symlink once in a scratch dir (Windows may need
    developer mode / admin rights)."""
    try:
        with tempfile.TemporaryDirectory() as td:
            link = Path(td) / "probe-link"
            target = Path(td) / "probe-target"
            target.write_text("x", encoding="utf-8")
            os.symlink(str(target), str(link))
            return link.is_symlink()
    except (OSError, NotImplementedError, AttributeError):
        return False


SYMLINKS_OK = _symlink_capable()


class ProcessSnapshotEntryTests(unittest.TestCase):
    def test_fields_and_construction(self):
        entry = ProcessSnapshotEntry(4242, "Game.exe")
        self.assertEqual(entry.pid, 4242)
        self.assertEqual(entry.name, "Game.exe")

    def test_equality_and_hash(self):
        a = ProcessSnapshotEntry(7, "Game.exe")
        b = ProcessSnapshotEntry(7, "Game.exe")
        c = ProcessSnapshotEntry(8, "Game.exe")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertEqual(hash(a), hash(b))
        self.assertEqual(len({a, b, c}), 2)  # hashable set members

    def test_frozen(self):
        entry = ProcessSnapshotEntry(7, "Game.exe")
        with self.assertRaises(AttributeError):
            entry.pid = 8
        with self.assertRaises(AttributeError):
            entry.name = "Other.exe"


class ProcessListerBaseTests(unittest.TestCase):
    def test_base_lister_is_abstract(self):
        with self.assertRaises(NotImplementedError):
            ProcessLister().list_processes()

    def test_backends_subclass_the_base(self):
        self.assertTrue(issubclass(WindowsProcessLister, ProcessLister))
        self.assertTrue(issubclass(ProcfsProcessLister, ProcessLister))
        self.assertIsInstance(WindowsProcessLister(), ProcessLister)
        self.assertIsInstance(ProcfsProcessLister(), ProcessLister)


class FakeListerTests(unittest.TestCase):
    """A deterministic fake backend for the orchestrator lane; the
    contract it must uphold (entries are ProcessSnapshotEntry, the
    snapshot is stable) is pinned here."""

    def test_fake_lister_contract(self):
        snapshot = (ProcessSnapshotEntry(3, "Game.exe"),
                    ProcessSnapshotEntry(1, "Game.exe"))

        class Fake(ProcessLister):
            def list_processes(self):
                return list(snapshot)

        lister = Fake()
        first = lister.list_processes()
        second = lister.list_processes()
        self.assertEqual(first, second)
        for entry in first:
            self.assertIsInstance(entry, ProcessSnapshotEntry)
            self.assertIsInstance(entry.pid, int)
            self.assertIsInstance(entry.name, str)

    def test_error_raising_fake(self):
        class Broken(ProcessLister):
            def list_processes(self):
                raise ProcessWatchError("snapshot backend exploded")

        with self.assertRaises(ProcessWatchError) as ctx:
            Broken().list_processes()
        self.assertEqual(str(ctx.exception), "snapshot backend exploded")
        # The watch error is a named RuntimeError subclass.
        self.assertTrue(isinstance(ctx.exception, RuntimeError))


class ProcfsListerFixture:
    """Shared fake-/proc tree builder."""

    @staticmethod
    def build(base: Path) -> Path:
        root = base / "proc"
        # Numeric pid dirs with an exe entry (a regular file standing in
        # for the magic link; readlink fails on a regular file and the
        # entry is skipped, so real names only come from symlinks).
        (root / "123").mkdir()
        (root / "456").mkdir()
        (root / "789").mkdir()
        (root / "123" / "exe").write_text("", encoding="utf-8")
        # Non-numeric dirs are skipped.
        (root / "self").mkdir()
        (root / "sys").mkdir()
        # A numeric dir without an exe entry is skipped.
        (root / "42").mkdir()
        (root / "42" / "comm").write_text("kernel_thread", encoding="utf-8")
        # A numeric dir whose exe is a regular file is skipped without
        # failing the whole snapshot (unreadable magic link).
        (root / "55").mkdir()
        (root / "55" / "exe").write_text("plain file", encoding="utf-8")
        return root

    @staticmethod
    def link(root: Path, pid: str, target: str) -> None:
        os.symlink(target, str(root / pid / "exe"))


@unittest.skipUnless(SYMLINKS_OK, "os.symlink unavailable on this platform")
class ProcfsListerSymlinkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def test_collects_exe_links_from_numeric_pid_dirs(self):
        root = ProcfsListerFixture.build(self.base)
        ProcfsListerFixture.link(root, "123", "/opt/unity/MyGame.exe")
        ProcfsListerFixture.link(root, "456", "/usr/bin/python3.12")
        ProcfsListerFixture.link(root, "789",
                                 "/home/x/.local/share/Steam/compatibility/"
                                 "tools/vulkan/steam_game.exe")
        entries = ProcfsProcessLister(root).list_processes()
        # Basenames only, the full prefix path is not part of the name.
        self.assertEqual(
            [(e.pid, e.name) for e in entries],
            [(456, "python3.12"), (123, "MyGame.exe"), (789, "steam_game.exe")])
        # Sorted by (name.casefold(), pid).
        self.assertEqual(entries,
                         sorted(entries, key=lambda e: (e.name.casefold(), e.pid)))

    def test_skips_non_numeric_dirs_and_dirs_without_exe(self):
        root = ProcfsListerFixture.build(self.base)
        ProcfsListerFixture.link(root, "456", "/usr/bin/alpha.exe")
        entries = ProcfsProcessLister(root).list_processes()
        self.assertEqual([(e.pid, e.name) for e in entries], [(456, "alpha.exe")])

    def test_unreadable_exe_is_skipped_not_fatal(self):
        # Pid 55 has a regular file as exe: readlink fails, the entry is
        # dropped, the rest of the snapshot is collected.
        root = ProcfsListerFixture.build(self.base)
        ProcfsListerFixture.link(root, "123", "/game/Beta.exe")
        entries = ProcfsProcessLister(root).list_processes()
        self.assertEqual([(e.pid, e.name) for e in entries], [(123, "Beta.exe")])

    def test_empty_basename_is_skipped(self):
        root = self.base / "proc"
        root.mkdir()
        (root / "9").mkdir()
        # Link target ending in "/" yields an empty basename.
        os.symlink("/opt/empty/", str(root / "9" / "exe"))
        self.assertEqual(ProcfsProcessLister(root).list_processes(), [])


class ProcfsListerNonsymlinkTests(unittest.TestCase):
    """The parts of the procfs contract that need no symlink support:
    root validation, dir filtering, unreadable-exe skip, ordering."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def test_missing_proc_root_fails_closed(self):
        missing = self.base / "no-such-proc"
        lister = ProcfsProcessLister(missing)
        self.assertEqual(lister.proc_root, missing)
        with self.assertRaises(ProcessWatchError) as ctx:
            lister.list_processes()
        self.assertEqual(str(ctx.exception),
                         "proc filesystem is unavailable: " + str(missing))

    def test_proc_root_must_be_a_directory(self):
        file_root = self.base / "not-a-dir"
        file_root.write_text("x", encoding="utf-8")
        with self.assertRaises(ProcessWatchError):
            ProcfsProcessLister(file_root).list_processes()

    def test_numeric_dirs_without_readable_exe_yield_nothing(self):
        # No symlink support needed: every numeric dir either lacks an
        # exe entry or has one that cannot be read as a link, so the
        # snapshot is empty but the scan completes.
        root = self.base / "proc"
        root.mkdir()
        (root / "123").mkdir()
        (root / "123" / "exe").write_text("plain", encoding="utf-8")
        (root / "42").mkdir()
        (root / "self").mkdir()
        self.assertEqual(ProcfsProcessLister(root).list_processes(), [])

    def test_constructor_accepts_str_and_path(self):
        root = self.base / "proc"
        root.mkdir()
        self.assertEqual(ProcfsProcessLister(str(root)).proc_root, root)
        self.assertEqual(ProcfsProcessLister(root).proc_root, root)
        # The platform default points at the real proc filesystem.
        self.assertEqual(ProcfsProcessLister().proc_root, Path("/proc"))


class DefaultListerTests(unittest.TestCase):
    def test_returns_the_running_platform_backend(self):
        lister = default_process_lister()
        if sys.platform == "win32":
            self.assertIsInstance(lister, WindowsProcessLister)
        elif sys.platform.startswith("linux"):
            self.assertIsInstance(lister, ProcfsProcessLister)
        else:  # pragma: no cover - the suite runs on win32/linux
            raise ProcessWatchError("unsupported platform in test")

    def test_win32_branch_returns_windows_lister(self):
        with mock.patch.object(sys, "platform", "win32"):
            self.assertIsInstance(default_process_lister(), WindowsProcessLister)

    def test_linux_branches_return_procfs_lister(self):
        for platform in ("linux", "linux2", "linux3"):
            with mock.patch.object(sys, "platform", platform):
                self.assertIsInstance(default_process_lister(),
                                      ProcfsProcessLister)

    def test_unsupported_platform_fails_closed(self):
        with mock.patch.object(sys, "platform", "darwin"):
            with self.assertRaises(ProcessWatchError) as ctx:
                default_process_lister()
        message = str(ctx.exception)
        self.assertIn("No process-list backend", message)
        self.assertIn("/proc", message)

    def test_platform_listers_are_listers(self):
        with mock.patch.object(sys, "platform", "win32"):
            self.assertIsInstance(default_process_lister(), ProcessLister)
        with mock.patch.object(sys, "platform", "linux"):
            self.assertIsInstance(default_process_lister(), ProcessLister)


class WindowsListerTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32",
                         "Toolhelp32 backend is Windows-only")
    def test_real_windows_snapshot_has_the_expected_shape(self):
        entries = WindowsProcessLister().list_processes()
        self.assertIsInstance(entries, list)
        self.assertGreater(len(entries), 0)
        for entry in entries:
            self.assertIsInstance(entry, ProcessSnapshotEntry)
            self.assertIsInstance(entry.pid, int)
            self.assertIsInstance(entry.name, str)
            # PID 0 (the System Idle Process) is a real entry in the
            # Toolhelp snapshot, so 0 is a legitimate pid here.
            self.assertGreaterEqual(entry.pid, 0)
            self.assertTrue(entry.name)
        # The process running this test must be visible in the snapshot.
        names = {entry.name for entry in entries}
        self.assertIn(os.path.basename(sys.executable), names)
        # The backend contract keeps the deterministic order.
        self.assertEqual(entries, sorted(entries,
                     key=lambda e: (e.name.casefold(), e.pid)))


class NamesMatchTests(unittest.TestCase):
    def test_ascii_case_insensitive(self):
        self.assertTrue(names_match("Game.exe", "game.exe"))
        self.assertTrue(names_match("Game.exe", "GAME.EXE"))
        self.assertTrue(names_match("GAME.EXE", "game.exe"))

    def test_exact_match_short_circuit(self):
        self.assertTrue(names_match("Game.exe", "Game.exe"))

    def test_non_matching_ascii(self):
        self.assertFalse(names_match("Gamee.exe", "Game.exe"))
        self.assertFalse(names_match("Game.exe", "Game.exe "))

    def test_non_ascii_uses_casefold(self):
        # The source compares casefold (not lower) for non-ASCII names on
        # every platform.
        self.assertTrue(names_match("Übung.exe", "übung.exe"))
        self.assertTrue(names_match("ÜBUNG.exe", "übung.exe"))
        self.assertFalse(names_match("Übung.exe", "Ubung.exe"))

    def test_non_ascii_comparisons_use_casefold_not_lower(self):
        # One non-ASCII operand switches the whole comparison to casefold.
        # 'ß' lowercases to itself but casefolds to 'ss', so these pairs
        # distinguish the documented casefold semantics from a naive
        # lower() comparison.
        self.assertTrue(names_match("straße.exe", "STRASSE.exe"))
        self.assertTrue(names_match("STRASSE.exe", "straße.exe"))
        self.assertTrue(names_match("Straße.exe", "strasse.exe"))
        self.assertFalse(names_match("straße.exe", "StrasseX.exe"))

    def test_ascii_matching_is_ordinal_and_pure_ascii(self):
        # ASCII pairs never touch the casefold branch: they match on the
        # ordinal lower compare, and any non-ASCII-looking input does not
        # leak into the ASCII branch.
        self.assertTrue(names_match("gAmE.eXe", "GAME.EXE"))
        self.assertFalse(names_match("Game.exe", "Game1.exe"))


class MatchTargetsTests(unittest.TestCase):
    def _entry(self, pid, name):
        return ProcessSnapshotEntry(pid, name)

    def test_casefold_key_matching(self):
        snapshot = [self._entry(1, "game.exe")]
        matches = match_targets(snapshot, {"GAME.EXE"})
        # The result is keyed by the casefolded name.
        self.assertEqual(list(matches), ["game.exe"])
        self.assertEqual(matches["game.exe"], [snapshot[0]])

    def test_multiple_pids_for_one_name_all_matched(self):
        entries = [self._entry(30, "Game.exe"),
                   self._entry(10, "Game.exe"),
                   self._entry(20, "Game.exe")]
        matches = match_targets(entries, {"Game.exe"})
        self.assertEqual(len(matches["game.exe"]), 3)
        # Sorted by (name.casefold(), pid) -> ascending pid.
        self.assertEqual([e.pid for e in matches["game.exe"]], [10, 20, 30])

    def test_result_lists_are_sorted_by_name_then_pid(self):
        snapshot = [self._entry(9, "Zebra.exe"),
                    self._entry(5, "alpha.exe"),
                    self._entry(7, "Alpha.exe"),
                    self._entry(1, "alpha.exe")]
        matches = match_targets(snapshot, {"alpha.exe", "Zebra.exe"})
        # Per-key lists are sorted by (name.casefold(), pid): all three
        # alpha entries casefold identically, so the pid decides.
        self.assertEqual([e.pid for e in matches["alpha.exe"]], [1, 5, 7])
        self.assertEqual([e.pid for e in matches["zebra.exe"]], [9])

    def test_non_matching_entries_excluded(self):
        snapshot = [self._entry(1, "Game.exe"),
                    self._entry(2, "Unrelated.exe"),
                    self._entry(3, "Game2.exe")]
        matches = match_targets(snapshot, {"Game.exe"})
        self.assertEqual(list(matches), ["game.exe"])
        self.assertEqual([e.pid for e in matches["game.exe"]], [1])

    def test_empty_snapshot_empty_result(self):
        self.assertEqual(match_targets([], {"Game.exe"}), {})

    def test_empty_target_names_empty_result(self):
        snapshot = [self._entry(1, "Game.exe")]
        self.assertEqual(match_targets(snapshot, set()), {})

    def test_bound_name_in_other_casing_matches_process(self):
        # A bound name "GAME.EXE" must match a running "game.exe" via the
        # casefold key (the orchestrator relies on this).
        snapshot = [self._entry(11, "game.exe")]
        matches = match_targets(snapshot, {"GAME.EXE"})
        self.assertIn("game.exe", matches)
        self.assertEqual(matches["game.exe"], [snapshot[0]])

    def test_distinct_names_do_not_cross_match(self):
        snapshot = [self._entry(1, "Game.exe")]
        # Casefold equality, not prefix/substring, is the contract.
        self.assertEqual(match_targets(snapshot, {"Game.exe "}), {})
        self.assertEqual(match_targets(snapshot, {"Game"}), {})
        self.assertEqual(match_targets(snapshot, {"Game.EXEX"}), {})


if __name__ == "__main__":
    unittest.main()
