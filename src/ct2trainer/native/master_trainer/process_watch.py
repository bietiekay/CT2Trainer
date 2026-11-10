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

from dataclasses import dataclass, replace
from pathlib import Path
import ctypes
import os
import sys


class ProcessWatchError(RuntimeError):
    """No process-list backend is available for this platform, or the
    snapshot backend failed."""


@dataclass(frozen=True)
class ProcessSnapshotEntry:
    """One process visible in a snapshot.

    ``name`` is the image basename exactly as the backend spells it; the
    matcher keeps the original spelling for display.

    MT-31 (0.40): the optional identification fields - ``path`` (the
    full image path), ``creation_time`` (the process start, Unix epoch
    seconds) and ``pointer_size`` (4 or 8, the target bitness) - are
    filled only by the bounded per-candidate enrichment (see
    :func:`enrich_candidates`); ``None`` means the fact was refused or
    is unavailable (fail-closed: the display falls back to name + PID,
    the decision logic is never affected).  ``pid`` and ``name`` are
    the decision fields; the enrichment never changes them.
    """

    pid: int
    name: str
    path: str | None = None
    creation_time: float | None = None
    pointer_size: int | None = None


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
        from ...local_processes import list_local_processes
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


# MT-31 (0.40): bounded per-candidate identification enrichment.  The
# snapshot listers stay cheap (name + PID only); the picker and the
# table-details window ask for the extra facts only for the bounded
# candidate set they display - never for the full snapshot (the 30 s
# auto-rescan tick keeps its cheap contract).
PROCESS_QUERY_INFORMATION = 0x0400
# The FILETIME epoch (1601-01-01) to the Unix epoch (1970-01-01), in
# seconds; Windows creation times are 100 ns ticks since 1601-01-01.
_FILETIME_EPOCH_DELTA_SECONDS = 11644473600.0


class _FILETIME(ctypes.Structure):
    _fields_ = [("low", ctypes.c_uint32), ("high", ctypes.c_uint32)]


def _windows_enrich_entry(entry: ProcessSnapshotEntry,
                          kernel=None) -> ProcessSnapshotEntry:
    """Windows identification query for one candidate (MT-31).

    Opens the process with ``PROCESS_QUERY_INFORMATION`` only (no other
    rights are requested), asks ``QueryFullProcessImageNameW`` /
    ``GetProcessTimes`` / ``IsWow64Process2`` and closes the handle.
    Every failure - the process exiting mid-query, a refused handle, a
    missing export - keeps the entry unenriched (fail-closed: no error
    propagates, the name + PID decision logic is never affected).
    ``kernel`` is the test seam; the default is the configured kernel32
    from the native memory module.
    """
    if kernel is None:
        from ..memory import _api
        kernel = _api()
    handle = kernel.OpenProcess(PROCESS_QUERY_INFORMATION, False, entry.pid)
    if not handle:
        return entry
    try:
        path = None
        buffer = ctypes.create_unicode_buffer(32768)
        size = ctypes.c_uint32(len(buffer))
        if kernel.QueryFullProcessImageNameW(handle, 0, buffer,
                                             ctypes.byref(size)):
            if 0 < size.value < len(buffer):
                path = buffer.value or None
        creation_time = None
        times = [_FILETIME() for _ in range(4)]
        if kernel.GetProcessTimes(
                handle, *(ctypes.byref(item) for item in times)):
            ticks = times[0].low | times[0].high << 32
            if ticks:
                creation_time = (ticks / 10_000_000.0
                                 - _FILETIME_EPOCH_DELTA_SECONDS)
        pointer_size = None
        if hasattr(kernel, "IsWow64Process2"):
            machine = ctypes.c_uint16()
            native = ctypes.c_uint16()
            if kernel.IsWow64Process2(handle, ctypes.byref(machine),
                                      ctypes.byref(native)):
                architecture = machine.value or native.value
                if architecture == 0x014C:      # IMAGE_FILE_MACHINE_I386
                    pointer_size = 4
                elif architecture == 0x8664:    # IMAGE_FILE_MACHINE_AMD64
                    pointer_size = 8
        return replace(entry, path=path, creation_time=creation_time,
                       pointer_size=pointer_size)
    finally:
        try:
            kernel.CloseHandle(handle)
        except Exception:
            pass


def _procfs_enrich_entry(entry: ProcessSnapshotEntry,
                         proc_root: Path) -> ProcessSnapshotEntry:
    """``/proc`` identification for one candidate (Linux/SteamOS).

    The image path is the full ``exe`` link target (under Proton the
    compatibility-prefix path of the Windows EXE the table binds to);
    the creation time is the ``starttime`` field of ``/proc/<pid>/stat``
    (clock ticks since boot) plus the system boot time (``btime`` from
    ``/proc/stat``), in Unix seconds.  The bitness is not provable from
    ``/proc`` alone and stays ``None``.  Any read failure keeps the
    entry unenriched (fail-closed, the same contract as the lister's
    unreadable-process skip).
    """
    path = None
    creation_time = None
    try:
        target = (proc_root / str(entry.pid) / "exe").readlink()
        if target:
            path = target
        stat_text = (proc_root / str(entry.pid) / "stat").read_text()
        tail = stat_text[stat_text.rfind(")") + 1:].lstrip()
        # ``starttime`` is field 22 of the raw file; after the leading
        # "pid (comm)" chunk the state field (3) is index 0, so field
        # 22 is index 19 of the split tail.
        start_ticks = int(tail.split()[19])
    except (OSError, ValueError, IndexError):
        return entry
    try:
        for line in (proc_root / "stat").read_text().splitlines():
            if line.startswith("btime "):
                creation_time = (int(line.split()[1])
                                 + start_ticks / os.sysconf("SC_CLK_TCK"))
                break
    except (OSError, ValueError, IndexError):
        creation_time = None
    if path is None and creation_time is None:
        return entry
    return replace(entry, path=path, creation_time=creation_time)


def default_process_enricher():
    """Platform-selected per-entry enricher (MT-31).

    Windows: :func:`_windows_enrich_entry`; Linux: the ``/proc``
    variant; unsupported platforms keep the entry unchanged (the Master
    already fails closed on the lister for those platforms).
    """
    if sys.platform == "win32":
        return _windows_enrich_entry
    if sys.platform.startswith("linux"):
        return lambda entry: _procfs_enrich_entry(entry, Path("/proc"))
    return lambda entry: entry


def enrich_candidates(entries, enricher=None) -> list[ProcessSnapshotEntry]:
    """Bounded per-candidate identification enrichment (MT-31).

    Applies ``enricher`` (the injected test seam, or the platform
    :func:`default_process_enricher`) to each entry of a BOUNDED
    candidate set - the picker / details rows only.  Every per-entry
    failure fails closed: the entry stays unenriched, no error
    propagates, and a result that is not a snapshot entry is treated
    as a refused enrichment as well.
    """
    if enricher is None:
        enricher = default_process_enricher()
    out: list[ProcessSnapshotEntry] = []
    for entry in entries:
        try:
            enriched = enricher(entry)
        except Exception:
            enriched = entry
        out.append(enriched
                   if isinstance(enriched, ProcessSnapshotEntry)
                   else entry)
    return out
