"""Cross-platform process snapshot and target matching for the Master Trainer.

The Master Trainer waits for one of the process names bound by the indexed
tables to appear.  Two platform backends supply the read-only snapshot:

- Windows: the Toolhelp32 process snapshot (the same read-only contract as
  ``ct2trainer.local_processes``; no handle rights are requested).
- Linux/SteamOS: the ``/proc/<pid>/exe`` magic link; the basename is the
  image name.  Under Proton the link resolves into the compatibility
  prefix, so the basename is the Windows game EXE name the table binds to.

The matcher is a pure function so the decision logic (which table to load,
which candidate to offer) is testable without spawning processes.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys


class ProcessWatchError(RuntimeError):
    """No process-list backend is available for this platform, or the
    snapshot backend failed."""


@dataclass(frozen=True)
class ProcessSnapshotEntry:
    """One process visible in a snapshot.

    ``name`` is the image basename exactly as the backend spells it; the
    matcher keeps the original spelling for display.
    """

    pid: int
    name: str


class ProcessLister:
    """Read-only process snapshot backend.

    Implementations never open, write to or terminate a target; they only
    observe image names and PIDs.
    """

    def list_processes(self) -> list[ProcessSnapshotEntry]:
        raise NotImplementedError


class WindowsProcessLister(ProcessLister):
    """Toolhelp32 snapshot via the main-branch local process module."""

    def list_processes(self) -> list[ProcessSnapshotEntry]:
        from ..local_processes import list_local_processes
        return [ProcessSnapshotEntry(p.pid, p.name)
                for p in list_local_processes()]


class ProcfsProcessLister(ProcessLister):
    """``/proc`` snapshot for Linux (SteamOS).

    ``proc_root`` is injectable for tests; the default is ``/proc``.  A
    process whose ``exe`` link cannot be read (kernel threads, races) is
    skipped: the Master Trainer only binds on a provable image name, and a
    15-char comm truncation could produce false process-name matches.
    """

    def __init__(self, proc_root: str | Path = "/proc"):
        self.proc_root = Path(proc_root)

    def list_processes(self) -> list[ProcessSnapshotEntry]:
        root = self.proc_root
        if not root.is_dir():
            raise ProcessWatchError("proc filesystem is unavailable: " + str(root))
        entries: list[ProcessSnapshotEntry] = []
        for child in root.iterdir():
            if not child.name.isdigit():
                continue
            pid = int(child.name)
            try:
                target = (child / "exe").readlink()
            except OSError:
                continue  # kernel thread, exited mid-scan or unreadable
            basename = target.rsplit("/", 1)[-1]
            if basename:
                entries.append(ProcessSnapshotEntry(pid, basename))
        return sorted(entries, key=lambda e: (e.name.casefold(), e.pid))


def default_process_lister() -> ProcessLister:
    """Platform-selected backend; fails closed on unsupported platforms."""
    if sys.platform == "win32":
        return WindowsProcessLister()
    if sys.platform.startswith("linux"):
        return ProcfsProcessLister()
    raise ProcessWatchError(
        "No process-list backend for this platform; "
        "the Master Trainer needs Windows or a /proc Linux filesystem.")


def names_match(left: str, right: str) -> bool:
    """Ordinal basename comparison, cross-platform.

    Mirrors the main-branch process finder's ordinal semantics for the
    common ASCII case (exact or case-insensitive lower compare); non-ASCII
    names compare casefold on every platform instead of being refused,
    because the Master Trainer only uses the match as a load candidate and
    the trainer engine re-proves the exact target identity at attach time.
    """
    if left == right:
        return True
    if left.isascii() and right.isascii():
        return left.lower() == right.lower()
    return left.casefold() == right.casefold()


def match_targets(snapshot: list[ProcessSnapshotEntry],
                  target_names: set[str]) -> dict[str, list[ProcessSnapshotEntry]]:
    """Match a snapshot against bound target names.

    Returns a dict keyed by the casefolded target name; the values are the
    snapshot entries matching that name (possibly several PIDs).  An empty
    result means no bound process is running.
    """
    matches: dict[str, list[ProcessSnapshotEntry]] = {}
    wanted: dict[str, list] = {}
    for name in target_names:
        wanted.setdefault(name.casefold(), []).append(name)
    for entry in snapshot:
        for key, _ in wanted.items():
            if names_match(entry.name, key):
                matches.setdefault(key, []).append(entry)
    for key in matches:
        matches[key].sort(key=lambda e: (e.name.casefold(), e.pid))
    return matches
