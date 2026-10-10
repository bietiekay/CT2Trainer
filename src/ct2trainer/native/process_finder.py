"""Independent process finder with exact PID + creation-time identity.

Authored from public Win32 contracts only: the Toolhelp32 process snapshot
for names/PIDs and OpenProcess/GetProcessTimes (PROCESS_QUERY_LIMITED_INFORMATION
plus SYNCHRONIZE, no write or termination rights) for the FILETIME creation
value. No CE implementation code is involved.

Contracts:
- Identity is the pair (pid, creation_time). A PID alone is never proof of
  the same process; a reused PID with a different creation time is a
  different identity.
- Basename comparison is ordinal (ASCII case-insensitive; non-ASCII via
  CompareStringOrdinal on Windows, refused elsewhere rather than guessed).
  Display always keeps the original snapshot spelling.
- Multiple matches for one basename are returned together as a visible
  ambiguity; the finder never silently picks one.
- The finder never opens a target with write/termination rights and exposes
  no kill path; external PIDs are never terminated by this module.
- Entries whose creation time cannot be read (access denied, snapshot
  races) stay visible as uncertain candidates instead of disappearing.

Primary contracts:
https://learn.microsoft.com/windows/win32/api/tlhelp32/nf-tlhelp32-createtoolhelp32snapshot
https://learn.microsoft.com/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocesstimes
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import sys

MAX_BASENAME = 255
MAX_SNAPSHOT_ENTRIES = 131072
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SYNCHRONIZE = 0x100000
TH32CS_SNAPPROCESS = 0x00000002
ERROR_NO_MORE_FILES = 18


class ProcessFinderError(RuntimeError):
    """Invalid request or an unexpected process API failure."""


@dataclass(frozen=True)
class ProcessCandidate:
    """One visible snapshot entry; uncertain when the creation time is unreadable."""

    pid: int
    creation_time: int | None  # FILETIME in 100-ns units; None when unproven
    name: str                  # original basename exactly as the snapshot spells it

    @property
    def identity(self) -> tuple[int, int | None]:
        return (self.pid, self.creation_time)

    @property
    def certain(self) -> bool:
        return self.creation_time is not None and 0 < self.creation_time


@dataclass(frozen=True)
class FindResult:
    requested: str
    matches: tuple[ProcessCandidate, ...]
    status: str  # none | unique | ambiguous

    @property
    def single(self) -> ProcessCandidate | None:
        """The only match, but only when the result is a certain unique hit."""
        if self.status != "unique" or len(self.matches) != 1:
            return None
        return self.matches[0]


def validate_basename(name: str) -> str:
    if not isinstance(name, str) or not name or len(name) > MAX_BASENAME:
        raise ProcessFinderError("A nonempty image base name of bounded length is required.")
    if name != name.strip() or name in {".", ".."}:
        raise ProcessFinderError("Base names must be exact tokens without surrounding blanks.")
    if any(c.isspace() for c in name):
        raise ProcessFinderError("Base names are exact tokens and may not contain blanks.")
    if any(ord(c) < 32 or c in '\\/:*?"<>|' for c in name):
        raise ProcessFinderError("Base names may not contain paths, separators, or wildcards.")
    return name


def names_match(left: str, right: str) -> bool:
    """Ordinal basename comparison; never a locale- or culture-sensitive fold."""
    if left == right:
        return True
    if left.isascii() and right.isascii():
        return left.lower() == right.lower()
    if sys.platform != "win32":
        return False  # no ordinal Unicode backend off-Windows; refuse to guess
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    compare = kernel.CompareStringOrdinal
    compare.argtypes = (wintypes.LPCWSTR, ctypes.c_int, wintypes.LPCWSTR, ctypes.c_int, wintypes.BOOL)
    compare.restype = ctypes.c_int
    result = compare(left, -1, right, -1, True)
    if result not in {1, 2, 3}:
        raise ProcessFinderError("CompareStringOrdinal failed for basename comparison")
    return result == 2


class _ProcessEntry(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("usage", wintypes.DWORD),
                ("pid", wintypes.DWORD), ("heap", ctypes.c_size_t),
                ("module", wintypes.DWORD), ("threads", wintypes.DWORD),
                ("parent", wintypes.DWORD), ("priority", ctypes.c_int32),
                ("flags", wintypes.DWORD), ("name", wintypes.WCHAR * 260)]


class _FileTime(ctypes.Structure):
    _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]


class _WindowsSnapshotAPI:
    """Read-only snapshot + per-PID creation-time lookup from kernel32."""

    def __init__(self):
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "CreateToolhelp32Snapshot": ([wintypes.DWORD, wintypes.DWORD], wintypes.HANDLE),
            "Process32FirstW": ([wintypes.HANDLE, ctypes.POINTER(_ProcessEntry)], wintypes.BOOL),
            "Process32NextW": ([wintypes.HANDLE, ctypes.POINTER(_ProcessEntry)], wintypes.BOOL),
            "OpenProcess": ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
            "GetProcessTimes": ([wintypes.HANDLE] + [ctypes.POINTER(_FileTime)] * 4, wintypes.BOOL),
            "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(kernel, name)
            function.argtypes, function.restype = arguments, result
        self._kernel = kernel

    def snapshot(self) -> list[tuple[int, str]]:
        kernel = self._kernel
        handle = kernel.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if not handle or handle == ctypes.c_void_p(-1).value:
            raise ProcessFinderError("Process snapshot could not be created")
        try:
            entry = _ProcessEntry()
            entry.size = ctypes.sizeof(entry)
            entries: list[tuple[int, str]] = []
            if not kernel.Process32FirstW(handle, ctypes.byref(entry)):
                raise ProcessFinderError("Process snapshot is empty or unreadable")
            while True:
                if entry.name:
                    entries.append((int(entry.pid), entry.name))
                if len(entries) > MAX_SNAPSHOT_ENTRIES:
                    raise ProcessFinderError("Process snapshot exceeded its entry bound")
                if not kernel.Process32NextW(handle, ctypes.byref(entry)):
                    if ctypes.get_last_error() == ERROR_NO_MORE_FILES:
                        break
                    raise ProcessFinderError("Process snapshot enumeration failed")
            return entries
        finally:
            if not kernel.CloseHandle(handle):
                raise ProcessFinderError("Process snapshot handle cleanup failed")

    def creation_time(self, pid: int) -> int | None:
        """FILETIME creation value, or None when the query is denied or fails."""
        kernel = self._kernel
        handle = kernel.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, pid)
        if not handle or handle == ctypes.c_void_p(-1).value:
            return None
        try:
            creation = _FileTime()
            rest = (_FileTime() for _ in range(3))
            times = (creation, *rest)
            if not kernel.GetProcessTimes(handle, *(ctypes.byref(item) for item in times)):
                return None
            value = creation.low | (creation.high << 32)
            return value or None
        finally:
            if not kernel.CloseHandle(handle):
                raise ProcessFinderError("Process handle cleanup failed")


class ProcessFinder:
    """Basename search over one snapshot, with exact (pid, created) identities.

    Inject ``snapshot_provider`` / ``creation_provider`` to test without
    spawning processes; the default backend is the read-only Win32 API.
    """

    def __init__(self, snapshot_provider=None, creation_provider=None):
        if sys.platform != "win32" and (snapshot_provider is None or creation_provider is None):
            raise ProcessFinderError("The native process finder requires Windows")
        self._snapshot_provider = snapshot_provider
        self._creation_provider = creation_provider

    def _snapshot(self):
        if self._snapshot_provider is not None:
            return list(self._snapshot_provider())
        return _WindowsSnapshotAPI().snapshot()

    def _creation_time(self, pid: int) -> int | None:
        if self._creation_provider is not None:
            return self._creation_provider(pid)
        return _WindowsSnapshotAPI().creation_time(pid)

    def find(self, basename: str) -> FindResult:
        """Return every snapshot entry matching the basename; never auto-select."""
        requested = validate_basename(basename)
        matches = []
        for pid, name in self._snapshot():
            if not names_match(name, requested):
                continue
            matches.append(ProcessCandidate(pid, self._creation_time(pid), name))
        if not matches:
            return FindResult(requested, (), "none")
        matches.sort(key=lambda item: (item.name.casefold(), item.pid))
        if len(matches) == 1:
            status = "unique" if matches[0].certain else "uncertain"
        else:
            status = "ambiguous"
        return FindResult(requested, tuple(matches), status)

    def select(self, result: FindResult, identity: tuple[int, int | None]) -> ProcessCandidate:
        """Explicit disambiguation: choose one exact identity from a result.

        Selecting an identity that is not present in the current result is a
        stale-selection error, never a re-search.
        """
        for candidate in result.matches:
            if candidate.identity == identity:
                return candidate
        raise ProcessFinderError("The selected identity is not present in the current snapshot")

    def verify(self, candidate: ProcessCandidate) -> bool:
        """Re-check that a certain candidate still names the same process."""
        if not candidate.certain:
            return False
        return self._creation_time(candidate.pid) == candidate.creation_time
