"""Read the local Windows process snapshot without opening target processes."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import sys


TH32CS_SNAPPROCESS = 0x00000002
ERROR_NO_MORE_FILES = 18


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


@dataclass(frozen=True)
class LocalProcess:
    pid: int
    name: str


def list_local_processes() -> list[LocalProcess]:
    """Return process image base names and PIDs from one Toolhelp snapshot.

    A snapshot is only a momentary view. The builder persists the image name,
    never the PID, so a later launch of the game can have a different PID.
    """
    if sys.platform != "win32":
        raise OSError("Process picker is available on Windows only.")

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel32.CreateToolhelp32Snapshot
    create.argtypes = (wintypes.DWORD, wintypes.DWORD)
    create.restype = wintypes.HANDLE
    first = kernel32.Process32FirstW
    first.argtypes = (wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W))
    first.restype = wintypes.BOOL
    next_process = kernel32.Process32NextW
    next_process.argtypes = first.argtypes
    next_process.restype = wintypes.BOOL
    close = kernel32.CloseHandle
    close.argtypes = (wintypes.HANDLE,)
    close.restype = wintypes.BOOL

    handle = create(TH32CS_SNAPPROCESS, 0)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        processes: list[LocalProcess] = []
        if not first(handle, ctypes.byref(entry)):
            error = ctypes.get_last_error()
            if error == ERROR_NO_MORE_FILES:
                return processes
            raise ctypes.WinError(error)
        while True:
            if entry.szExeFile:
                processes.append(LocalProcess(int(entry.th32ProcessID), entry.szExeFile))
            if not next_process(handle, ctypes.byref(entry)):
                error = ctypes.get_last_error()
                if error != ERROR_NO_MORE_FILES:
                    raise ctypes.WinError(error)
                break
        return sorted(processes, key=lambda process: (process.name.casefold(), process.pid))
    finally:
        close(handle)
