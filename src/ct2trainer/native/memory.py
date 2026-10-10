"""Independent, bounded Win32 process-memory operations.

This module uses documented Microsoft APIs, not Cheat Engine code or binaries.
The handle stays bound to one PID/start-time identity until closed. No debugger,
driver, injected DLL, elevated privilege, or PROCESS_ALL_ACCESS is requested.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import ntpath
import re
import sys
import threading
import time

from .lua_work_budget import _mutation_checkpoint, remaining_seconds, broker_checkpoint
from collections.abc import Mapping, Sequence

from ct2trainer.local_processes import list_local_processes

from .patterns import normalize_pattern


MAX_TRANSFER = 64 * 1024 * 1024
MAX_SCAN_SIZE = 512 * 1024 * 1024
SCAN_CHUNK_SIZE = 1024 * 1024
MAX_PATTERN_SIZE = 4096
MAX_POINTER_DEPTH = 32
MAX_SCAN_CANDIDATES = 2_000_000
MAX_SCAN_SECONDS = 30
MAX_PROCESS_SCAN_BYTES = 2 * 1024 * 1024 * 1024
MAX_PROCESS_SCAN_REGIONS = 65536
MAX_SCAN_RESULTS = 65536
PROCESS_ACCESS = 0x0400 | 0x0010 | 0x0020 | 0x0008 | 0x00100000
# QUERY_INFORMATION | VM_READ | VM_WRITE | VM_OPERATION | SYNCHRONIZE
MEM_COMMIT = 0x1000
MEM_RESERVE = 0x2000
MEM_RELEASE = 0x8000
MEM_FREE = 0x10000
MAX_REMOTE_ALLOCATION = 4 * 1024 * 1024
MAX_NEAR_REGIONS = 65536
MAX_NEAR_SECONDS = 5
PAGE_GUARD = 0x100
READABLE = {0x02, 0x04, 0x08, 0x20, 0x40, 0x80}
WRITABLE = {0x04, 0x08, 0x40, 0x80}
EXECUTABLE = {0x10, 0x20, 0x40, 0x80}
WAIT_OBJECT_0, WAIT_TIMEOUT = 0, 0x102
ERROR_NO_MORE_FILES = 18
ERROR_BAD_LENGTH = 24
_DWORD = ctypes.c_uint32
_WORD = ctypes.c_uint16


class ProcessMemoryError(OSError):
    """A failed or ambiguous memory/identity operation; no success is implied."""


class _FILETIME(ctypes.Structure):
    _fields_ = [("low", _DWORD), ("high", _DWORD)]


class _MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", _DWORD), ("PartitionId", _WORD),
        ("RegionSize", ctypes.c_size_t), ("State", _DWORD),
        ("Protect", _DWORD), ("Type", _DWORD),
    ]


class _SYSTEM_INFO(ctypes.Structure):
    _fields_ = [
        ("architecture", _DWORD), ("page_size", _DWORD),
        ("minimum_address", ctypes.c_void_p), ("maximum_address", ctypes.c_void_p),
        ("processor_mask", ctypes.c_size_t), ("processor_count", _DWORD),
        ("processor_type", _DWORD), ("allocation_granularity", _DWORD),
        ("processor_level", _WORD), ("processor_revision", _WORD),
    ]


class _MODULEENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", _DWORD), ("th32ModuleID", _DWORD), ("th32ProcessID", _DWORD),
        ("GlblcntUsage", _DWORD), ("ProccntUsage", _DWORD),
        ("modBaseAddr", ctypes.c_void_p), ("modBaseSize", _DWORD),
        ("hModule", ctypes.c_void_p), ("szModule", wintypes.WCHAR * 256),
        ("szExePath", wintypes.WCHAR * 260),
    ]


def _api() -> object:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    signatures = {
        "OpenProcess": ((_DWORD, wintypes.BOOL, _DWORD), wintypes.HANDLE),
        "CloseHandle": ((wintypes.HANDLE,), wintypes.BOOL),
        "GetProcessId": ((wintypes.HANDLE,), _DWORD),
        "GetProcessTimes": ((wintypes.HANDLE,) + (ctypes.POINTER(_FILETIME),) * 4, wintypes.BOOL),
        "QueryFullProcessImageNameW": ((wintypes.HANDLE, _DWORD, wintypes.LPWSTR, ctypes.POINTER(_DWORD)), wintypes.BOOL),
        "WaitForSingleObject": ((wintypes.HANDLE, _DWORD), _DWORD),
        "ReadProcessMemory": ((wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)), wintypes.BOOL),
        "WriteProcessMemory": ((wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)), wintypes.BOOL),
        "VirtualQueryEx": ((wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(_MEMORY_BASIC_INFORMATION), ctypes.c_size_t), ctypes.c_size_t),
        "VirtualProtectEx": ((wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t, _DWORD, ctypes.POINTER(_DWORD)), wintypes.BOOL),
        "VirtualAllocEx": ((wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t, _DWORD, _DWORD), ctypes.c_void_p),
        "VirtualFreeEx": ((wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t, _DWORD), wintypes.BOOL),
        "GetSystemInfo": ((ctypes.POINTER(_SYSTEM_INFO),), None),
        "FlushInstructionCache": ((wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t), wintypes.BOOL),
        "CreateToolhelp32Snapshot": ((_DWORD, _DWORD), wintypes.HANDLE),
        "Module32FirstW": ((wintypes.HANDLE, ctypes.POINTER(_MODULEENTRY32W)), wintypes.BOOL),
        "Module32NextW": ((wintypes.HANDLE, ctypes.POINTER(_MODULEENTRY32W)), wintypes.BOOL),
        "IsWow64Process": ((wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)), wintypes.BOOL),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(kernel, name)
        function.argtypes, function.restype = arguments, result
    if hasattr(kernel, "IsWow64Process2"):
        kernel.IsWow64Process2.argtypes = (wintypes.HANDLE, ctypes.POINTER(_WORD), ctypes.POINTER(_WORD))
        kernel.IsWow64Process2.restype = wintypes.BOOL
    return kernel


def _windows_error(operation: str) -> ProcessMemoryError:
    code = ctypes.get_last_error()
    return ProcessMemoryError(f"{operation} failed (Win32 error {code}).")


def _basename(name: str, *, executable: bool = False) -> str:
    if not isinstance(name, str) or not name or len(name) > 255:
        raise ValueError("An exact image base name is required.")
    if name != name.strip() or any(ord(c) < 32 or c in '\\/:<>|?*"' for c in name) or name in {".", ".."}:
        raise ValueError("Image names must be exact base names without paths or wildcards.")
    if executable and not name.casefold().endswith(".exe"):
        raise ValueError("The target image base name must end in .exe.")
    return name


def _names_equal(left: str, right: str) -> bool:
    """Compare image names ordinally; Unicode casefold can conflate filenames."""
    if left == right:
        return True
    if left.isascii() and right.isascii():
        return left.lower() == right.lower()
    if sys.platform != "win32":
        return False  # No native backend exists here; do not guess Unicode rules.
    compare = ctypes.WinDLL("kernel32", use_last_error=True).CompareStringOrdinal
    compare.argtypes = (wintypes.LPCWSTR, ctypes.c_int, wintypes.LPCWSTR, ctypes.c_int, wintypes.BOOL)
    compare.restype = ctypes.c_int
    result = compare(left, -1, right, -1, True)
    if result not in {1, 2, 3}:
        raise _windows_error("CompareStringOrdinal")
    return result == 2


def _compile_pattern(pattern: str) -> tuple[re.Pattern[bytes], int]:
    """Compile overlapping byte/nibble matches; avoid executing table code."""
    if not isinstance(pattern, str) or len(pattern) > MAX_PATTERN_SIZE * 3:
        raise ValueError("Invalid or oversized byte pattern.")
    tokens = normalize_pattern(pattern).split()
    if not tokens or len(tokens) > MAX_PATTERN_SIZE:
        raise ValueError("A byte pattern must contain 1 to 4096 bytes.")
    parts: list[bytes] = []
    constrained = False
    for token in tokens:
        if token in {"?", "*"}:
            token = "??"
        if not re.fullmatch(r"[0-9a-fA-F?]{2}", token):
            raise ValueError(f"Invalid pattern byte: {token!r}.")
        if token == "??":
            parts.append(b".")
        elif "?" not in token:
            parts.append(re.escape(bytes([int(token, 16)])))
            constrained = True
        else:
            choices = [byte for byte in range(256) if all(char == "?" or char.lower() == f"{byte:02x}"[index] for index, char in enumerate(token))]
            parts.append(b"[" + b"".join(re.escape(bytes([byte])) for byte in choices) + b"]")
            constrained = True
    if not constrained:
        raise ValueError("An entirely wildcard pattern cannot identify an address.")
    return re.compile(b"(?=" + b"".join(parts) + b")", re.DOTALL), len(tokens)


def _pattern_anchor(pattern: str) -> tuple[bytes | re.Pattern[bytes], int]:
    """Find candidates using the longest literal run, or one constrained nibble."""
    tokens = normalize_pattern(pattern).split()
    best, best_offset, current, offset = b"", 0, bytearray(), 0
    for index, token in enumerate(tokens):
        if re.fullmatch(r"[0-9a-fA-F]{2}", token):
            if not current:
                offset = index
            current.append(int(token, 16))
            if len(current) > len(best):
                best, best_offset = bytes(current), offset
        else:
            current.clear()
    if best:
        return best, best_offset
    for index, token in enumerate(tokens):
        if re.fullmatch(r"[0-9a-fA-F?]{2}", token) and token != "??":
            return _compile_pattern(token)[0], index
    raise ValueError("A byte pattern needs a constrained anchor.")


def _candidate_offsets(data: bytes, anchor: bytes | re.Pattern[bytes], offset: int):
    if isinstance(anchor, bytes):
        start = data.find(anchor)
        while start != -1:
            yield start - offset
            start = data.find(anchor, start + 1)
    else:
        for match in anchor.finditer(data):
            yield match.start() - offset


def _checked_release(memory, address, size, before_release):
    """Controller adapter preserving the real backend's last-kernel guard."""
    from .restoration_budget import mutation_admission, checkpoint
    function = getattr(memory, '_release_checked', None)
    if callable(function):
        return function(address, before_release)
    before_release()
    _mutation_checkpoint()
    mutation_admission(size)
    memory.release(address)
    checkpoint(full=False)


def _checked_write(memory, address, data, *, before_kernel=None, rollback=False):
    """Controller-only admission; no callback is exposed through Lua/JSON."""
    if isinstance(memory, ProcessMemory):
        return memory._write_checked(address, data, before_kernel=before_kernel,
                                     _rollback=rollback)
    if not rollback:
        broker_checkpoint()
    if before_kernel is not None:
        before_kernel()
    _mutation_checkpoint()
    from .restoration_budget import mutation_admission, checkpoint
    mutation_admission(len(data),rollback=rollback)
    result=memory.write(address,data)
    checkpoint(full=False)
    return result


class ProcessMemory:
    """Own a handle to an exact executable and expose checked memory actions.

    With no PID, exactly one matching image must exist. An explicit PID permits
    intentional selection, but its snapshot and opened image must both match.
    Image names compare case-insensitively, as Windows executable names do.
    The creation timestamp is the raw Windows FILETIME value (100 ns ticks).
    """

    def __init__(self, process_name: str, pid: int | None = None):
        self._name = _basename(process_name, executable=True)
        if sys.platform != "win32" or ctypes.sizeof(ctypes.c_void_p) != 8:
            raise ProcessMemoryError("Native process memory requires Windows and x64 Python.")
        if pid is not None and (type(pid) is not int or not 0 < pid <= 0xFFFFFFFF):
            raise ValueError("PID must be a positive 32-bit integer.")
        candidates = [item for item in list_local_processes() if _names_equal(item.name, self._name) and (pid is None or item.pid == pid)]
        if len(candidates) != 1:
            raise ProcessMemoryError(f"Expected one exact {self._name} process; found {len(candidates)}.")
        self._lock = threading.RLock()
        self._kernel = _api()
        self._handle = self._kernel.OpenProcess(PROCESS_ACCESS, False, candidates[0].pid)
        self._write_uncertain = False
        if not self._handle:
            raise _windows_error("OpenProcess")
        try:
            actual_pid = int(self._kernel.GetProcessId(self._handle))
            if actual_pid != candidates[0].pid:
                raise ProcessMemoryError("Opened handle PID does not match the selected process.")
            if not _names_equal(ntpath.basename(self._image_path()), self._name):
                raise ProcessMemoryError("Opened image does not match the exact target executable.")
            self._pid = actual_pid
            self._creation_time = self._start_time()
            self._pointer_size = self._detect_pointer_size()
            self._require_alive()
        except BaseException:
            self.close()
            raise

    @property
    def pid(self) -> int:
        return self._pid

    @property
    def process_handle(self) -> int:
        """Owned target HANDLE while open; 0 once the handle was closed.

        Read-only accessor for the Lua host process API; the handle itself
        stays bound to one PID/start-time identity until close().
        """
        return int(self._handle) if self._handle else 0

    @property
    def creation_time(self) -> int:
        return self._creation_time

    @property
    def identity(self) -> tuple[int, int]:
        return self._pid, self._creation_time

    @property
    def pointer_size(self) -> int:
        return self._pointer_size

    def _image_path(self) -> str:
        buffer = ctypes.create_unicode_buffer(32768)
        size = _DWORD(len(buffer))
        if not self._kernel.QueryFullProcessImageNameW(self._handle, 0, buffer, ctypes.byref(size)):
            raise _windows_error("QueryFullProcessImageNameW")
        if not 0 < size.value < len(buffer):
            raise ProcessMemoryError("Invalid executable image path length.")
        return buffer.value

    def _start_time(self) -> int:
        times = [_FILETIME() for _ in range(4)]
        if not self._kernel.GetProcessTimes(self._handle, *(ctypes.byref(item) for item in times)):
            raise _windows_error("GetProcessTimes")
        result = times[0].low | times[0].high << 32
        if result == 0:
            raise ProcessMemoryError("The process creation timestamp is unavailable.")
        return result

    def _detect_pointer_size(self) -> int:
        if hasattr(self._kernel, "IsWow64Process2"):
            machine, native = _WORD(), _WORD()
            if not self._kernel.IsWow64Process2(self._handle, ctypes.byref(machine), ctypes.byref(native)):
                raise _windows_error("IsWow64Process2")
            if native.value != 0x8664:
                raise ProcessMemoryError("Native process memory requires a confirmed AMD64 Windows host; ARM64/emulation is unverified.")
            architecture = machine.value or native.value
            if architecture not in {0x014C, 0x8664}:
                raise ProcessMemoryError("Only x86 and x64 target processes are supported.")
            return 4 if architecture == 0x014C else 8
        # GetNativeSystemInfo can report an emulated x64 architecture on ARM64.
        # An old boolean WOW64 answer therefore cannot prove this host/context ABI.
        raise ProcessMemoryError("IsWow64Process2 is required to prove target and native host architecture (Windows 10 1709 or newer).")

    def is_alive(self) -> bool:
        with self._lock:
            if not self._handle:
                raise ProcessMemoryError("The process memory handle is closed.")
            status = int(self._kernel.WaitForSingleObject(self._handle, 0))
            if status == WAIT_OBJECT_0:
                return False
            if status != WAIT_TIMEOUT:
                raise _windows_error("WaitForSingleObject")
            if int(self._kernel.GetProcessId(self._handle)) != self._pid or self._start_time() != self._creation_time:
                raise ProcessMemoryError("The opened process identity changed or became uncertain.")
            return True

    def _require_alive(self) -> None:
        if not self.is_alive():
            raise ProcessMemoryError("The bound target process has exited.")

    def close(self) -> None:
        with self._lock:
            if self._handle:
                if not self._kernel.CloseHandle(self._handle):
                    raise _windows_error("CloseHandle")
                self._handle = None

    def __enter__(self) -> ProcessMemory:
        return self

    def __exit__(self, *unused: object) -> None:
        self.close()

    def _range(self, address: int, size: int, *, limit: int = MAX_TRANSFER) -> None:
        maximum = 0xFFFFFFFF if self._pointer_size == 4 else 0x7FFFFFFFFFFF
        if type(address) is not int or type(size) is not int or not 0 < size <= limit or not 0 < address <= maximum or size - 1 > maximum - address:
            raise ValueError("Invalid, overflowing, or oversized memory range.")

    def _query(self, address: int) -> _MEMORY_BASIC_INFORMATION:
        information = _MEMORY_BASIC_INFORMATION()
        size = self._kernel.VirtualQueryEx(self._handle, address, ctypes.byref(information), ctypes.sizeof(information))
        if size != ctypes.sizeof(information):
            raise _windows_error("VirtualQueryEx")
        base = int(information.BaseAddress or 0)
        if not base <= address < base + information.RegionSize:
            raise ProcessMemoryError("VirtualQueryEx returned a nonprogressing memory region.")
        return information

    def _read_exact(self, address: int, size: int) -> bytes:
        buffer = ctypes.create_string_buffer(size)
        transferred = ctypes.c_size_t()
        if not self._kernel.ReadProcessMemory(self._handle, address, buffer, size, ctypes.byref(transferred)):
            raise _windows_error("ReadProcessMemory")
        if transferred.value != size:
            raise ProcessMemoryError("ReadProcessMemory returned a partial result.")
        return buffer.raw

    def read(self, address: int, size: int) -> bytes:
        with self._lock:
            self._range(address, size)
            self._require_alive()
            result = self._read_exact(address, size)
            self._require_alive()
            return result

    def write(self, address: int, data: bytes) -> None:
        self._write_checked(address, data)

    def _write_checked(self, address: int, data: bytes, *, before_kernel=None,
                       _rollback: bool = False) -> None:
        """Write exact bytes, restore every page protection, and verify readback.

        A failure can follow a partial write. The backend then blocks additional
        writes; it never silently retries or claims that memory was rolled back.
        Patches are not atomic with respect to the target's running threads.
        """
        if before_kernel is not None and not callable(before_kernel):
            raise ValueError("Write admission requires a private callable.")
        if type(_rollback) is not bool:
            raise ValueError("Invalid private rollback mode.")
        if _rollback:
            from .restoration_budget import in_restoration, RestorationBudgetError
            if not in_restoration():
                raise RestorationBudgetError("Emergency rollback requires a controller restoration region")
        if not isinstance(data, bytes):
            raise ValueError("Memory writes require immutable bytes.")
        with self._lock:
            self._range(address, len(data))
            self._require_alive()
            if self._write_uncertain:
                raise ProcessMemoryError("A previous write was uncertain; further writes are blocked.")
            regions = []
            cursor, end = address, address + len(data)
            while cursor < end:
                region = self._query(cursor)
                protection = int(region.Protect)
                if region.State != MEM_COMMIT or protection & PAGE_GUARD or protection & 0xFF not in READABLE:
                    raise ProcessMemoryError("The write range contains inaccessible or guarded memory.")
                length = min(end, int(region.BaseAddress or 0) + region.RegionSize) - cursor
                regions.append((cursor, length, protection))
                cursor += length
            changed: list[tuple[int, int, int]] = []
            errors: list[str] = []
            executable = any(protection & 0xFF in EXECUTABLE for _, _, protection in regions)
            attempted = False
            restore_failed = False
            refusal = None
            try:
                for start, length, protection in regions:
                    if protection & 0xFF not in WRITABLE:
                        previous = _DWORD()
                        temporary = 0x40 if protection & 0xFF in EXECUTABLE else 0x04
                        # Admit new preparation only before the cooperative
                        # ceiling. The finally block must still restore pages
                        # already changed, even if that in-flight call was late.
                        broker_checkpoint()
                        _mutation_checkpoint()
                        if not self._kernel.VirtualProtectEx(self._handle, start, length, temporary, ctypes.byref(previous)):
                            raise _windows_error("VirtualProtectEx")
                        changed.append((start, length, previous.value))
                        if previous.value != protection:
                            raise ProcessMemoryError("Memory protection changed during the write preparation.")
                self._require_alive()
                buffer = ctypes.create_string_buffer(data, len(data))
                transferred = ctypes.c_size_t()
                # This is the last controller admission before the native
                # mutation, after buffer creation and slow backend guards.
                if not _rollback:
                    broker_checkpoint()
                if before_kernel is not None:
                    before_kernel()
                _mutation_checkpoint()
                from .restoration_budget import mutation_admission
                mutation_admission(len(data),rollback=_rollback)
                attempted = True
                if not self._kernel.WriteProcessMemory(self._handle, address, buffer, len(data), ctypes.byref(transferred)):
                    raise _windows_error("WriteProcessMemory (memory may be partially changed)")
                if transferred.value != len(data):
                    raise ProcessMemoryError("WriteProcessMemory was partial; memory may be changed.")
            except Exception as error:
                refusal = error
                errors.append(str(error))
            finally:
                for start, length, protection in reversed(changed):
                    previous = _DWORD()
                    if not self._kernel.VirtualProtectEx(self._handle, start, length, protection, ctypes.byref(previous)):
                        restore_failed = True
                        errors.append(str(_windows_error("VirtualProtectEx restoration")))
                if executable and attempted and not self._kernel.FlushInstructionCache(self._handle, address, len(data)):
                    errors.append(str(_windows_error("FlushInstructionCache")))
            if not errors:
                try:
                    self._require_alive()
                    if self._read_exact(address, len(data)) != data:
                        raise ProcessMemoryError("Memory write readback differs; memory may be changed.")
                    self._require_alive()
                    from .restoration_budget import checkpoint
                    checkpoint(full=False)
                except Exception as error:
                    errors.append(str(error))
            if errors:
                if not attempted and not restore_failed:
                    # No WPM began and every temporary protection was restored.
                    # A deadline/proof refusal does not poison unchanged bytes.
                    raise refusal
                self._write_uncertain = True
                raise ProcessMemoryError("; ".join(errors))

    def allocate(self, size: int, near: int | None = None,
                 max_distance: int = 0x7FFF0000) -> int:
        """Reserve/commit owned RW pages, optionally wholly near an anchor.

        Near allocation never silently falls back to an out-of-range address.
        A later hook manager must stage, protect, and coordinate publication;
        this method itself does not install or execute code.
        """
        if type(size) is not int or not 0 < size <= MAX_REMOTE_ALLOCATION:
            raise ValueError("Remote allocations require 1 byte to 4 MiB.")
        if type(max_distance) is not int or not 0 < max_distance <= 0x7FFFFFFF:
            raise ValueError("Invalid near-allocation distance.")
        with self._lock:
            self._require_alive()
            if self._write_uncertain:
                raise ProcessMemoryError("A previous mutation was uncertain; allocation is blocked.")
            information = _SYSTEM_INFO()
            self._kernel.GetSystemInfo(ctypes.byref(information))
            page, granularity = information.page_size, information.allocation_granularity
            if (not page or page & (page - 1) or not granularity
                    or granularity & (granularity - 1) or granularity < page):
                raise ProcessMemoryError("Invalid system page/allocation granularity.")
            rounded = (size + page - 1) // page * page
            candidates: list[int | None] = [None]
            if near is not None:
                self._range(near, 1)
                minimum = max(int(information.minimum_address or granularity), near - max_distance)
                maximum = min(int(information.maximum_address or 0x7FFFFFFFFFFF),
                              0xFFFFFFFF if self._pointer_size == 4 else 0x7FFFFFFFFFFF,
                              near + max_distance)
                cursor = (minimum + granularity - 1) // granularity * granularity
                candidates = []
                regions, deadline = 0, time.monotonic() + remaining_seconds(MAX_NEAR_SECONDS)
                while cursor + rounded - 1 <= maximum:
                    broker_checkpoint()
                    regions += 1
                    if regions > MAX_NEAR_REGIONS or time.monotonic() > deadline:
                        raise ProcessMemoryError("Near-allocation search exceeded its region/time bound.")
                    region = self._query(cursor)
                    end = min(maximum + 1, int(region.BaseAddress or 0) + region.RegionSize)
                    if region.State == MEM_FREE:
                        lower = (cursor + granularity - 1) // granularity * granularity
                        upper = (end - rounded) // granularity * granularity
                        if lower <= upper:
                            # One nearest aligned address from every free region.
                            candidate = min(upper, max(lower, near // granularity * granularity))
                            candidates.append(candidate)
                    cursor = end
                candidates.sort(key=lambda address: abs(address - near))
            for desired in candidates:
                broker_checkpoint()
                self._require_alive()
                broker_checkpoint()
                address = int(self._kernel.VirtualAllocEx(
                    self._handle, desired, rounded, MEM_COMMIT | MEM_RESERVE, 0x04) or 0)
                if not address:
                    continue
                if not hasattr(self, "_owned_allocations"):
                    self._owned_allocations = {}
                self._owned_allocations[address] = {"size": rounded, "requested": size,
                                                    "executable": False}
                try:
                    self._range(address, rounded)
                    if desired is not None and address != desired:
                        raise ProcessMemoryError("Near allocation returned a different base address.")
                    if near is not None and not (near - max_distance <= address
                                                and address + rounded - 1 <= near + max_distance):
                        raise ProcessMemoryError("The complete allocation is outside the requested near range.")
                    region = self._query(address)
                    if (region.State != MEM_COMMIT or int(region.AllocationBase or 0) != address
                            or region.RegionSize < rounded or region.Protect != 0x04):
                        raise ProcessMemoryError("The new owned allocation could not be verified.")
                    self._require_alive()
                    return address
                except Exception as primary:
                    from .restoration_budget import restoration_region, _clock_for
                    try:
                        # This address was created by this exact handle and
                        # has never escaped allocate(). It may be reclaimed
                        # only under the same shared controller allowance.
                        with restoration_region(self._require_alive, _clock_for(self)):
                            self._release_checked(address, self._require_alive)
                    except Exception as cleanup:
                        # Even a clean free refusal retains a real, unpublished
                        # allocation created earlier in this operation. Do not
                        # advertise a clean backend or lose that ownership.
                        self._write_uncertain = True
                        raise ProcessMemoryError(str(primary) + "; unpublished allocation reclamation is uncertain: " + str(cleanup)) from primary
                    raise
            raise ProcessMemoryError("No owned allocation fits the requested address range.")

    def allocation_size(self, address: int) -> int:
        """Return actual page-rounded size only for an allocation we own."""
        with self._lock:
            allocation = getattr(self, "_owned_allocations", {}).get(address)
            if allocation is None:
                raise ProcessMemoryError("The allocation base is not owned by this memory handle.")
            return allocation["size"]

    def protect_allocation(self, address: int, executable: bool = True,
                           writable: bool = False) -> None:
        """Finalize as RX code, explicit RWX mixed code/data, or RW data."""
        if type(executable) is not bool or type(writable) is not bool:
            raise ValueError("Allocation executable/writable policy must be boolean.")
        with self._lock:
            self._require_alive()
            if self._write_uncertain:
                raise ProcessMemoryError("A previous mutation was uncertain; protection is blocked.")
            size = self.allocation_size(address)
            region = self._query(address)
            if (region.State != MEM_COMMIT or int(region.AllocationBase or 0) != address
                    or region.RegionSize < size or region.Protect != 0x04):
                raise ProcessMemoryError("Only intact owned RW allocations can be finalized.")
            protection = (0x40 if writable else 0x20) if executable else 0x04
            previous = _DWORD()
            attempted = False
            try:
                attempted = True
                if not self._kernel.VirtualProtectEx(self._handle, address, size, protection,
                                                    ctypes.byref(previous)):
                    raise _windows_error("VirtualProtectEx allocation finalization")
                if previous.value != 0x04:
                    raise ProcessMemoryError("Owned allocation protection changed during finalization.")
                region = self._query(address)
                if (region.Protect != protection or int(region.AllocationBase or 0) != address
                        or region.RegionSize < size):
                    raise ProcessMemoryError("Final allocation protection could not be verified.")
                if executable and not self._kernel.FlushInstructionCache(self._handle, address, size):
                    raise _windows_error("FlushInstructionCache allocation finalization")
                self._require_alive()
                self._owned_allocations[address]["executable"] = executable
                self._owned_allocations[address]["writable"] = writable or not executable
            except Exception:
                if attempted:
                    self._write_uncertain = True
                raise

    def release(self, address: int) -> None:
        """Release only an owned, caller-proven unpublished allocation."""
        return self._release_checked(address, None)

    def _release_checked(self, address: int, before_release) -> None:
        """Private last-VirtualFree admission; no new allocation authority."""
        if before_release is not None and not callable(before_release):
            raise ValueError("A release checkpoint must be controller-owned")
        from .restoration_budget import mutation_admission, checkpoint
        with self._lock:
            self._require_alive()
            if self._write_uncertain:
                raise ProcessMemoryError("A previous mutation was uncertain; release is blocked.")
            size = self.allocation_size(address)
            attempted = False
            try:
                broker_checkpoint()
                if before_release is not None:
                    before_release()
                _mutation_checkpoint()
                mutation_admission(size)
                attempted = True
                if not self._kernel.VirtualFreeEx(self._handle, address, 0, MEM_RELEASE):
                    raise _windows_error("VirtualFreeEx owned allocation")
                del self._owned_allocations[address]
                checkpoint(full=False)
            except Exception:
                if attempted:
                    self._write_uncertain = True
                raise

    def is_executable(self, address: int, size: int) -> bool:
        """Query whether any page in a checked range has executable protection."""
        with self._lock:
            self._range(address, size)
            self._require_alive()
            cursor, end, executable = address, address + size, False
            while cursor < end:
                region = self._query(cursor)
                if region.State != MEM_COMMIT or region.Protect & PAGE_GUARD:
                    raise ProcessMemoryError("The code range is not committed accessible memory.")
                executable |= region.Protect & 0xFF in EXECUTABLE
                cursor = min(end, int(region.BaseAddress or 0) + region.RegionSize)
            self._require_alive()
            return executable

    def module(self, name: str) -> tuple[int, int]:
        """Select the held target's PE architecture, including WOW64 duplicates."""
        result = self.module_for_architecture(name, self._pointer_size)
        self._range(*result, limit=0xFFFFFFFF)
        return result

    def _read_host_metadata(self, address: int, size: int) -> bytes:
        """Read bounded debugger/PE metadata in native user address space.

        WOW64 maps native ntdll above 4 GiB alongside its 32-bit image. Only
        structured read-only metadata paths use this internal method; ordinary
        target reads, pointer chains and every write retain target-width bounds.
        """
        if (type(address) is not int or type(size) is not int or not 0 < size <= MAX_TRANSFER
                or not 0 < address <= 0x7FFFFFFFFFFF or size - 1 > 0x7FFFFFFFFFFF - address):
            raise ValueError("Invalid native metadata range.")
        with self._lock:
            self._require_alive()
            result = self._read_exact(address, size)
            self._require_alive()
            return result

    def module_for_architecture(self, name: str, pointer_size: int) -> tuple[int, int]:
        """Select a uniquely named mapped PE image with explicit x86/x64 ABI."""
        _basename(name)
        if type(pointer_size) is not int or pointer_size not in {4, 8}:
            raise ValueError("A module architecture requires a 4/8-byte pointer width.")
        with self._lock:
            self._require_alive()
            snapshot = None
            for _ in range(3):
                snapshot = self._kernel.CreateToolhelp32Snapshot(0x08 | 0x10, self._pid)
                if snapshot != ctypes.c_void_p(-1).value:
                    break
                if ctypes.get_last_error() != ERROR_BAD_LENGTH:
                    raise _windows_error("CreateToolhelp32Snapshot architecture modules")
            if not snapshot or snapshot == ctypes.c_void_p(-1).value:
                raise _windows_error("CreateToolhelp32Snapshot architecture modules")
            matches = {}
            started, examined = time.monotonic(), 0
            try:
                entry = _MODULEENTRY32W()
                entry.dwSize = ctypes.sizeof(entry)
                if not self._kernel.Module32FirstW(snapshot, ctypes.byref(entry)):
                    raise _windows_error("Module32FirstW architecture")
                while True:
                    examined += 1
                    if examined > 4096 or time.monotonic() - started > 5:
                        raise ProcessMemoryError("Module inventory exceeds its count/time bound.")
                    if _names_equal(entry.szModule, name):
                        base, size = int(entry.modBaseAddr or 0), int(entry.modBaseSize)
                        if not base or not 64 <= size <= 0xFFFFFFFF:
                            raise ProcessMemoryError("Invalid architecture module image range.")
                        dos = self._read_host_metadata(base, 64)
                        offset = int.from_bytes(dos[60:64], "little")
                        if dos[:2] != b"MZ" or not 64 <= offset <= min(1024 * 1024, size - 26):
                            raise ProcessMemoryError("Invalid architecture module DOS/PE header.")
                        pe = self._read_host_metadata(base + offset, 26)
                        machine, magic = int.from_bytes(pe[4:6], "little"), int.from_bytes(pe[24:26], "little")
                        if pe[:4] != b"PE\0\0":
                            raise ProcessMemoryError("Invalid architecture module PE signature.")
                        if (pointer_size == 4 and (machine, magic) == (0x14C, 0x10B)
                                or pointer_size == 8 and (machine, magic) == (0x8664, 0x20B)):
                            maximum = 0xFFFFFFFF if pointer_size == 4 else 0x7FFFFFFFFFFF
                            if base > maximum or size - 1 > maximum - base:
                                raise ProcessMemoryError("Architecture module image exceeds its address width.")
                            # Combined native/WOW64 snapshots can repeat the
                            # identical mapped image. Different paths, ranges or
                            # architectures never become one module by basename.
                            matches.setdefault((base, size, entry.szExePath), (base, size))
                    if not self._kernel.Module32NextW(snapshot, ctypes.byref(entry)):
                        if ctypes.get_last_error() != ERROR_NO_MORE_FILES:
                            raise _windows_error("Module32NextW architecture")
                        break
            finally:
                if not self._kernel.CloseHandle(snapshot):
                    raise _windows_error("CloseHandle architecture module snapshot")
            self._require_alive()
            if len(matches) != 1:
                raise ProcessMemoryError(f"Expected one exact {pointer_size * 8}-bit module {name}; found {len(matches)}.")
            return next(iter(matches.values()))

    def resolve_export(self, module_name: str, export_name: str,
                       *, pointer_size: int | None = None) -> int:
        """Resolve a PE export against held remote modules, including forwarders.

        No locally loaded DLL address is substituted. API-set contracts without
        a loaded target module remain unsupported until target schema mapping.
        """
        from .pe_exports import ExportResolutionError, resolve_remote_export
        with self._lock:
            self._require_alive()
            architecture = self._pointer_size if pointer_size is None else pointer_size
            if architecture not in {4, 8}:
                raise ValueError("An export architecture requires a 4/8-byte pointer width.")
            try:
                address = resolve_remote_export(self._read_host_metadata,
                    lambda name: self.module_for_architecture(name, architecture), module_name, export_name)
            except ExportResolutionError as exc:
                raise ProcessMemoryError(str(exc)) from exc
            if architecture == self._pointer_size:
                self._range(address, 1)
            elif not 0 < address <= 0x7FFFFFFFFFFF:
                raise ProcessMemoryError("Invalid native debugger export address.")
            self._require_alive()
            return address

    def scan_module(self, name: str, pattern: str) -> int:
        matcher, pattern_size = _compile_pattern(pattern)
        anchor, anchor_offset = _pattern_anchor(pattern)
        with self._lock:
            base, size = self.module(name)
            self._range(base, size, limit=MAX_SCAN_SIZE)
            cursor, end, tail = base, base + size, b""
            matches: set[int] = set()
            candidates = 0
            deadline = time.monotonic() + remaining_seconds(MAX_SCAN_SECONDS)
            while cursor < end:
                broker_checkpoint()
                if time.monotonic() > deadline:
                    raise ProcessMemoryError("The module byte scan exceeded its time bound.")
                self._require_alive()
                region = self._query(cursor)
                region_end = min(end, int(region.BaseAddress or 0) + region.RegionSize)
                if region.State != MEM_COMMIT or region.Protect & PAGE_GUARD or region.Protect & 0xFF not in READABLE:
                    tail = b""
                    cursor = region_end
                    continue
                while cursor < region_end:
                    broker_checkpoint()
                    length = min(SCAN_CHUNK_SIZE, region_end - cursor)
                    data = tail + self.read(cursor, length)
                    start = cursor - len(tail)
                    for candidate in _candidate_offsets(data, anchor, anchor_offset):
                        candidates += 1
                        if candidates % 2048 == 0: broker_checkpoint()
                        if candidates > MAX_SCAN_CANDIDATES or candidates % 2048 == 0 and time.monotonic() > deadline:
                            raise ProcessMemoryError("The module byte scan exceeded its candidate/time bound.")
                        if candidate < 0 or candidate + pattern_size > len(data) or not matcher.match(data, candidate):
                            continue
                        found = start + candidate
                        if base <= found and found + pattern_size <= end:
                            matches.add(found)
                            if len(matches) > 1:
                                raise ProcessMemoryError("The module byte pattern is ambiguous (multiple matches).")
                    tail = data[-(pattern_size - 1):] if pattern_size > 1 else b""
                    cursor += length
            broker_checkpoint()
            if self.module(name) != (base, size):
                raise ProcessMemoryError("The module changed while scanning.")
            if len(matches) != 1:
                raise ProcessMemoryError("The module byte pattern was not found in readable committed memory.")
            return matches.pop()

    def scan_matches(self, pattern: str, start: int = 0, end: int | None = None,
                     protection: str = "", alignment_type: int = 0,
                     alignment_parameter: str | int | None = None,
                     max_results: int = MAX_SCAN_RESULTS, *, checkpoint=None) -> list[int]:
        """Return all bounded matches in [start, end), with an exclusive end.

        Protection uses independent +required/-excluded/*any X(executable),
        W(writable), C(copy-on-write) flags. Alignment 1 divides addresses by a
        hexadecimal modulus; 2 compares hexadecimal address suffix digits.
        Only readable committed pages qualify. Full process scans remain finite:
        2 GiB read bytes, 65536 regions/results, candidate and elapsed-time caps.
        Exceeding a cap raises, never returns a misleading truncated match list.
        Addresses beyond the target/system user range contain no eligible pages
        and are clamped rather than traversing kernel/noncanonical address space.
        """
        matcher, pattern_size = _compile_pattern(pattern)
        anchor, anchor_offset = _pattern_anchor(pattern)
        if checkpoint is not None and not callable(checkpoint):
            raise ValueError("A scan checkpoint must be a trusted callable.")
        def check():
            broker_checkpoint()
            if checkpoint is not None:
                checkpoint()
                broker_checkpoint()
        check()
        if (type(start) is not int or not 0 <= start <= 0xFFFFFFFFFFFFFFFF
                or end is not None and (type(end) is not int or not 0 <= end <= 0x10000000000000000)
                or end is not None and end < start):
            raise ValueError("Scan ranges require ascending unsigned addresses and an exclusive end.")
        if type(max_results) is not int or not 1 <= max_results <= MAX_SCAN_RESULTS:
            raise ValueError("Scan result limit requires 1..65536.")
        if not isinstance(protection, str) or len(protection) > 64:
            raise ValueError("Invalid scan protection expression.")
        expression = re.sub(r"\s+", "", protection).upper()
        if not re.fullmatch(r"(?:[+*\-][XWC])*", expression):
            raise ValueError("Scan protection accepts only +/-/* X, W and C flags.")
        filters = {}
        for sign, flag in re.findall(r"([+*\-])([XWC])", expression):
            if flag in filters:
                raise ValueError("Duplicate scan protection flags are ambiguous.")
            filters[flag] = sign
        if type(alignment_type) is not int or alignment_type not in {0, 1, 2}:
            raise ValueError("Unsupported fast-scan alignment mode.")
        modulus, suffix_mask, suffix_value = 1, 0, 0
        if alignment_type:
            if type(alignment_parameter) is int and alignment_type == 1:
                modulus = alignment_parameter
            elif isinstance(alignment_parameter, str) and re.fullmatch(r"(?:0[xX])?[0-9A-Fa-f]{1,16}", alignment_parameter):
                digits = alignment_parameter.removeprefix("0x").removeprefix("0X")
                if alignment_type == 1:
                    modulus = int(digits, 16)
                else:
                    suffix_value, suffix_mask = int(digits, 16), (1 << (len(digits) * 4)) - 1
            else:
                raise ValueError("Fast-scan alignment requires bounded hexadecimal digits.")
            if alignment_type == 1 and not 0 < modulus <= 0x100000000:
                raise ValueError("Fast-scan divisor requires 1..2^32.")

        with self._lock:
            self._require_alive()
            information = _SYSTEM_INFO()
            self._kernel.GetSystemInfo(ctypes.byref(information))
            maximum = min(int(information.maximum_address or 0),
                          0xFFFFFFFF if self._pointer_size == 4 else 0x7FFFFFFFFFFF)
            if not maximum:
                raise ProcessMemoryError("System user-address scan bounds are unavailable.")
            scan_end = maximum + 1 if end is None else min(end, maximum + 1)
            cursor, tail, matches = start, b"", set()
            regions = scanned = candidates = 0
            deadline = time.monotonic() + remaining_seconds(MAX_SCAN_SECONDS)
            while cursor < scan_end:
                check()
                regions += 1
                if regions > MAX_PROCESS_SCAN_REGIONS or time.monotonic() > deadline:
                    raise ProcessMemoryError("Process scan exceeded its region/time bound; no partial results returned.")
                self._require_alive()
                region = self._query(cursor)
                region_end = min(scan_end, int(region.BaseAddress or 0) + region.RegionSize)
                if not cursor < region_end <= scan_end:
                    raise ProcessMemoryError("Process scan inventory did not make valid bounded progress.")
                flags = {"X": region.Protect & 0xFF in EXECUTABLE,
                         "W": region.Protect & 0xFF in WRITABLE,
                         "C": region.Protect & 0xFF in {0x08, 0x80}}
                qualifies = (region.State == MEM_COMMIT and not region.Protect & PAGE_GUARD
                             and region.Protect & 0xFF in READABLE
                             and all(sign == "*" or flags[flag] == (sign == "+")
                                     for flag, sign in filters.items()))
                if not qualifies:
                    tail = b""
                    cursor = region_end
                    continue
                while cursor < region_end:
                    check()
                    if time.monotonic() > deadline:
                        raise ProcessMemoryError("Process scan exceeded its time bound; no partial results returned.")
                    length = min(SCAN_CHUNK_SIZE, region_end - cursor)
                    scanned += length
                    if scanned > MAX_PROCESS_SCAN_BYTES:
                        raise ProcessMemoryError("Process scan exceeded its byte-read bound; no partial results returned.")
                    data = tail + self.read(cursor, length)
                    beginning = cursor - len(tail)
                    for candidate in _candidate_offsets(data, anchor, anchor_offset):
                        candidates += 1
                        if candidates % 2048 == 0:
                            check()
                        if candidates > MAX_SCAN_CANDIDATES or candidates % 2048 == 0 and time.monotonic() > deadline:
                            raise ProcessMemoryError("Process scan exceeded its candidate/time bound; no partial results returned.")
                        if candidate < 0 or candidate + pattern_size > len(data) or not matcher.match(data, candidate):
                            continue
                        address = beginning + candidate
                        if (start <= address and address + pattern_size <= scan_end
                                and (alignment_type != 1 or address % modulus == 0)
                                and (alignment_type != 2 or address & suffix_mask == suffix_value)):
                            matches.add(address)
                            if len(matches) > max_results:
                                raise ProcessMemoryError("Process scan exceeded its result bound; no partial results returned.")
                    tail = data[-(pattern_size - 1):] if pattern_size > 1 else b""
                    cursor += length
            check()
            self._require_alive()
            broker_checkpoint()
            return sorted(matches)

    def _unique_scan(self, pattern, start=0, end=None, *, checkpoint=None):
        """One complete bounded result; quotas and uncertainty never pick first."""
        with self._lock:
            identity = self.identity
            width = self.pointer_size
            matches = self.scan_matches(pattern, start, end, max_results=2, checkpoint=checkpoint)
            self._require_alive()
            if self.identity != identity or self.pointer_size != width:
                raise ProcessMemoryError("Bound target identity/architecture changed during AOB scan.")
            if not matches:
                raise ProcessMemoryError("The byte pattern was not found in readable committed memory.")
            if len(matches) != 1:
                raise ProcessMemoryError("The byte pattern is ambiguous (multiple matches).")
            return matches[0]

    def scan_process(self, pattern: str, *, checkpoint=None) -> int:
        """Scan every eligible user page, including memory outside loaded modules."""
        return self._unique_scan(pattern, checkpoint=checkpoint)

    def scan_region(self, start: int, end: int, pattern: str, *, checkpoint=None) -> int:
        """Unique match in a bounded explicit half-open range, never a module."""
        if (type(start) is not int or type(end) is not int or not 0 < start < end
                or end - start > MAX_SCAN_SIZE):
            raise ValueError("AA scan regions require an ascending bounded exclusive range.")
        self._range(start, end - start, limit=MAX_SCAN_SIZE)
        return self._unique_scan(pattern, start, end, checkpoint=checkpoint)

    def resolve(self, expression: str, symbols: Mapping[str, int] | None = None) -> int:
        """Resolve a limited address grammar, with hexadecimal numeric terms."""
        if not isinstance(expression, str) or not expression.strip() or len(expression) > 1024:
            raise ValueError("Invalid or oversized address expression.")
        expression = expression.strip()
        # Quoted modules may contain spaces and hyphens; no evaluation occurs.
        parsed = re.fullmatch(r'("[^"\r\n]+"|[A-Za-z_][A-Za-z0-9_.$]*|(?:0[xX]|\$)?[0-9A-Fa-f]+)((?:\s*[+-]\s*(?:0[xX]|\$)?[0-9A-Fa-f]+)*)', expression)
        if not parsed:
            raise ValueError("Unsupported address expression; use a module/symbol and hexadecimal offsets.")
        atom, suffix = parsed.groups()
        quoted = atom.startswith('"')
        atom = atom[1:-1] if quoted else atom
        with self._lock:
            self._require_alive()
            symbol_matches = []
            if not quoted and symbols is not None:
                if not isinstance(symbols, Mapping) or any(not isinstance(key, str) for key in symbols):
                    raise ValueError("Symbol mappings require string names.")
                symbol_matches = [value for key, value in symbols.items() if key.casefold() == atom.casefold()]
                if len(symbol_matches) > 1:
                    raise ValueError("Ambiguous symbol name differing only by case.")
            if symbol_matches:
                address = symbol_matches[0]
                if type(address) is not int:
                    raise ValueError("Symbol addresses must be integers.")
            elif not quoted and re.fullmatch(r"(?:0[xX]|\$)?[0-9A-Fa-f]+", atom):
                address = int(atom.removeprefix("$"), 16)
            else:
                address = self.module(atom)[0]
            for sign, value in re.findall(r"([+-])\s*((?:0[xX]|\$)?[0-9A-Fa-f]+)", suffix):
                delta = int(value.removeprefix("$"), 16)
                address += delta if sign == "+" else -delta
            self._range(address, 1)
            return address

    def resolve_pointer(self, address: int | str, offsets: Sequence[int], symbols: Mapping[str, int] | None = None) -> int:
        """Resolve CT offsets in XML order (last offset is dereferenced first)."""
        if not isinstance(offsets, (tuple, list)) or len(offsets) > MAX_POINTER_DEPTH or any(type(offset) is not int or abs(offset) > 0x7FFFFFFFFFFFFFFF for offset in offsets):
            raise ValueError("Pointer chains require at most 32 signed integer offsets.")
        with self._lock:
            current = self.resolve(address, symbols) if isinstance(address, str) else address
            self._range(current, 1)
            self._require_alive()
            for offset in reversed(offsets):
                pointer = int.from_bytes(self.read(current, self._pointer_size), "little")
                if pointer == 0:
                    raise ProcessMemoryError("The pointer chain contains a null pointer.")
                current = pointer + offset
                self._range(current, 1)
            return current
