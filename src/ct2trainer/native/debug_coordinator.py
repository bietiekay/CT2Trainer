"""Documented Win32 debug-event quiescence, without CE or suspension races.

A dedicated thread owns attach, event delivery, continuation, and detach. A
pending OS debug event stops every target thread, including newly created ones.
Each held context must lie outside the overwritten ranges. This establishes
physical write quiescence, not arbitrary script/game correctness: saved exception
contexts and unproven future branches into patch interiors are separate gates.
Displaced calls/interrupts are refused because their return contexts may be hidden.

https://learn.microsoft.com/windows/win32/api/debugapi/nf-debugapi-debugactiveprocess
https://learn.microsoft.com/windows/win32/api/debugapi/nf-debugapi-waitfordebugevent
https://learn.microsoft.com/windows/win32/api/processthreadsapi/nf-processthreadsapi-getthreadcontext
"""
from __future__ import annotations

from contextlib import contextmanager
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import os
import struct
import sys
import threading
import time

from .lua_work_budget import remaining_seconds, broker_checkpoint
from typing import Any

from .hooks import (
    HookError,
    HookUncertain,
    QuiescenceProof,
    validate_entry_control_flow,
    validate_entry_prefix_cut,
)


MAX_DEBUG_THREADS = 1024
MAX_DEBUG_EVENTS = 8192
DBG_CONTINUE = 0x10002
DBG_EXCEPTION_NOT_HANDLED = 0x80010001
BREAKPOINT_CODES = {0x80000003, 0x4000001F}
ERROR_SEM_TIMEOUT = 121
ERROR_NO_MORE_FILES = 18
ERROR_INVALID_HANDLE = 6
_DWORD = ctypes.c_uint32


class _ExceptionRecord(ctypes.Structure):
    _fields_ = [("code", _DWORD), ("flags", _DWORD), ("record", ctypes.c_void_p),
                ("address", ctypes.c_void_p), ("parameter_count", _DWORD),
                ("information", ctypes.c_size_t * 15)]


class _ExceptionInfo(ctypes.Structure):
    _fields_ = [("record", _ExceptionRecord), ("first_chance", _DWORD)]


class _CreateThreadInfo(ctypes.Structure):
    _fields_ = [("thread", wintypes.HANDLE), ("tls", ctypes.c_void_p), ("start", ctypes.c_void_p)]


class _CreateProcessInfo(ctypes.Structure):
    _fields_ = [("file", wintypes.HANDLE), ("process", wintypes.HANDLE), ("thread", wintypes.HANDLE),
                ("base", ctypes.c_void_p), ("debug_offset", _DWORD), ("debug_size", _DWORD),
                ("tls", ctypes.c_void_p), ("start", ctypes.c_void_p),
                ("image_name", ctypes.c_void_p), ("unicode", wintypes.WORD)]


class _LoadDllInfo(ctypes.Structure):
    _fields_ = [("file", wintypes.HANDLE), ("base", ctypes.c_void_p),
                ("debug_offset", _DWORD), ("debug_size", _DWORD),
                ("image_name", ctypes.c_void_p), ("unicode", wintypes.WORD)]


class _DebugUnion(ctypes.Union):
    _fields_ = [("exception", _ExceptionInfo), ("create_thread", _CreateThreadInfo),
                ("create_process", _CreateProcessInfo), ("load_dll", _LoadDllInfo),
                ("exit_code", _DWORD)]


class _DebugEvent(ctypes.Structure):
    _fields_ = [("code", _DWORD), ("pid", _DWORD), ("tid", _DWORD), ("info", _DebugUnion)]


class _ThreadEntry(ctypes.Structure):
    _fields_ = [("size", _DWORD), ("usage", _DWORD), ("tid", _DWORD), ("pid", _DWORD),
                ("base_priority", ctypes.c_int32), ("delta_priority", ctypes.c_int32), ("flags", _DWORD)]


def _api():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    signatures = {
        "DebugActiveProcess": ((_DWORD,), wintypes.BOOL),
        "DebugActiveProcessStop": ((_DWORD,), wintypes.BOOL),
        "DebugSetProcessKillOnExit": ((wintypes.BOOL,), wintypes.BOOL),
        "WaitForDebugEvent": ((ctypes.POINTER(_DebugEvent), _DWORD), wintypes.BOOL),
        "ContinueDebugEvent": ((_DWORD, _DWORD, _DWORD), wintypes.BOOL),
        "OpenThread": ((_DWORD, wintypes.BOOL, _DWORD), wintypes.HANDLE),
        "GetThreadContext": ((wintypes.HANDLE, ctypes.c_void_p), wintypes.BOOL),
        "Wow64GetThreadContext": ((wintypes.HANDLE, ctypes.c_void_p), wintypes.BOOL),
        "CreateToolhelp32Snapshot": ((_DWORD, _DWORD), wintypes.HANDLE),
        "Thread32First": ((wintypes.HANDLE, ctypes.POINTER(_ThreadEntry)), wintypes.BOOL),
        "Thread32Next": ((wintypes.HANDLE, ctypes.POINTER(_ThreadEntry)), wintypes.BOOL),
        "CloseHandle": ((wintypes.HANDLE,), wintypes.BOOL),
        "CheckRemoteDebuggerPresent": ((wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)), wintypes.BOOL),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(kernel, name)
        function.argtypes, function.restype = arguments, result
    return kernel


def _error(operation):
    return HookError(f"{operation} failed (Win32 error {ctypes.get_last_error()}).")


def _thread_ip(kernel, thread, pointer_size):
    if pointer_size == 8:
        # CONTEXT_AMD64 is 1232 bytes, aligned to sixteen bytes. Only the
        # documented CONTROL portion is requested; no registers are modified.
        buffer = ctypes.create_string_buffer(1232 + 15)
        address = (ctypes.addressof(buffer) + 15) & ~15
        ctypes.c_uint32.from_address(address + 48).value = 0x100001
        if not kernel.GetThreadContext(thread, address):
            raise _error("GetThreadContext")
        ip = ctypes.c_uint64.from_address(address + 248).value
    elif pointer_size == 4:
        # Documented WOW64_CONTEXT layout: ContextFlags at zero, Eip at 184.
        buffer = ctypes.create_string_buffer(716 + 15)
        address = (ctypes.addressof(buffer) + 15) & ~15
        ctypes.c_uint32.from_address(address).value = 0x10001
        if not kernel.Wow64GetThreadContext(thread, address):
            raise _error("Wow64GetThreadContext")
        ip = ctypes.c_uint32.from_address(address + 184).value
    else:
        raise HookError("Only x86/x64 debugger contexts are supported.")
    if not ip:
        raise HookError("The held thread instruction pointer is unavailable.")
    return ip


def _threads(kernel, pid):
    snapshot = kernel.CreateToolhelp32Snapshot(0x04, 0)
    if not snapshot or snapshot == ctypes.c_void_p(-1).value:
        raise _error("CreateToolhelp32Snapshot threads")
    try:
        entry = _ThreadEntry()
        entry.size = ctypes.sizeof(entry)
        if not kernel.Thread32First(snapshot, ctypes.byref(entry)):
            raise _error("Thread32First")
        result = []
        while True:
            if entry.pid == pid:
                result.append(int(entry.tid))
                if len(result) > MAX_DEBUG_THREADS:
                    raise HookError("Target thread count exceeds the debugger coordinator bound.")
            if not kernel.Thread32Next(snapshot, ctypes.byref(entry)):
                if ctypes.get_last_error() != ERROR_NO_MORE_FILES:
                    raise _error("Thread32Next")
                break
        if not result:
            raise HookError("The held process has no observable thread contexts.")
        return result
    finally:
        if not kernel.CloseHandle(snapshot):
            raise _error("CloseHandle thread snapshot")


def _check_contexts(kernel, memory, ranges):
    observed = {}
    for tid in _threads(kernel, memory.pid):
        thread = kernel.OpenThread(0x0008 | 0x0040, False, tid)  # GET_CONTEXT | QUERY_INFORMATION
        if not thread:
            raise _error("OpenThread held context")
        try:
            ip = _thread_ip(kernel, thread, memory.pointer_size)
            if any(address <= ip < address + length for address, length in ranges):
                raise HookError("A held thread is inside an overwritten instruction range; retry later.")
            observed[tid] = ip
        finally:
            if not kernel.CloseHandle(thread):
                raise _error("CloseHandle held thread")
    return observed


def _check_overwrite_windows(memory, ranges, entry_windows=None):
    if not isinstance(ranges, (list, tuple)) or len(ranges) > 4096:
        raise HookError("Invalid debugger overwrite range list.")
    owned = {address: (original, replacement, expected)
             for address, original, replacement, expected in entry_windows or ()}
    if entry_windows is not None and (len(owned) != len(ranges) or len(owned) != len(entry_windows)):
        raise HookError("Invalid or overlapping controller entry receipts.")
    for address, length in ranges:
        if (type(address) is not int or type(length) is not int or not 0 < length <= 65536
                or not 0 < address <= 0x7FFFFFFFFFFF or length - 1 > 0x7FFFFFFFFFFF - address):
            raise HookError("Invalid debugger overwrite range.")
        if address in owned:
            original, replacement, expected = owned[address]
            if (not all(type(raw) is bytes and len(raw) == length for raw in (original, replacement, expected))
                    or expected not in (original, replacement)
                    or memory.read(address, length) != expected):
                raise HookError("Owned entry receipt differs from the held exact instructions.")
        if not memory.is_executable(address, length):
            continue
        if address in owned:
            try:
                validate_entry_control_flow(address, original, memory.pointer_size * 8)
                validate_entry_control_flow(address, replacement, memory.pointer_size * 8,
                                            inline_jump=True)
            except HookError:
                # A proven prefix-cut receipt (byte patch rewriting an
                # instruction prefix, e.g. db 90 E9 over a conditional jump)
                # keeps the complete-sequence contract live: the captured
                # original is the head of a longer original instruction and
                # the patched stream must complete exactly on that boundary.
                # The live proof re-validates against the quiesced target
                # under the held context; a complete original fast-paths
                # back into the full two-sided strict contract, so a call
                # or interrupt entry keeps its return-context refusal.
                validate_entry_prefix_cut(memory, address, replacement, original,
                                          memory.pointer_size * 8)
        else:
            validate_entry_control_flow(address, memory.read(address, length), memory.pointer_size * 8)


def _check_literal_windows(memory, windows, exclusions):
    """Validate controller-proven data separately from instruction windows.

    Literal bytes may decode as CALL or invalid opcodes. Their provenance comes
    from the owning hook's actual linker output, not from disassembly. Every
    target IP must instead be outside the entire executable owner allocation.
    """
    if len(windows) > 4096 or len(exclusions) > 4096:
        raise HookError("Executable literal receipt bounds exceeded.")
    for start, size in exclusions:
        if (type(start) is not int or type(size) is not int or not 0 < size <= 4 * 1024 * 1024
                or not 0 < start <= 0x7FFFFFFFFFFF or size - 1 > 0x7FFFFFFFFFFF - start
                or not memory.is_executable(start, size)):
            raise HookError("Invalid executable owner exclusion range.")
    observed = []
    for address, original, replacement, expected in windows:
        if (type(address) is not int or not 0 < address <= 0x7FFFFFFFFFFF
                or not all(type(raw) is bytes for raw in (original, replacement, expected))
                or not 0 < len(original) <= 65536 or len(original) != len(replacement)
                or expected not in (original, replacement)
                or not any(start <= address and address + len(original) <= start + size
                           for start, size in exclusions)
                or not memory.is_executable(address, len(original))):
            raise HookError("Literal receipt lacks an exact executable owner exclusion.")
        if any(address < start + size and start < address + len(original) for start, size in observed):
            raise HookError("Executable literal windows overlap.")
        if memory.read(address, len(expected)) != expected:
            raise HookError("Owned literal receipt differs from the held exact data.")
        observed.append((address, len(original)))


def _data_ranges(ranges):
    """Normalize controller-owned data windows without consulting the target."""
    if not isinstance(ranges, (list, tuple)) or not 0 < len(ranges) <= 4096:
        raise HookError("Debugger data windows must be a bounded nonempty list.")
    checked, total = [], 0
    for item in ranges:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise HookError("Invalid debugger data window.")
        address, size = item
        if (type(address) is not int or type(size) is not int or not 0 < size <= 65536
                or not 0 < address <= 0x7FFFFFFFFFFF or size - 1 > 0x7FFFFFFFFFFF - address):
            raise HookError("Invalid debugger data window address/size.")
        total += size
        if total > 1024 * 1024:
            raise HookError("Debugger data windows exceed the 1 MiB total bound.")
        checked.append((address, size))
    ordered = sorted(checked)
    if any(start + size > next_start for (start, size), (next_start, _) in zip(ordered, ordered[1:])):
        raise HookError("Debugger data windows overlap.")
    return tuple(checked)


def _check_data_windows(memory, ranges):
    """Admit readable committed non-executable pages; perform no mutation.

    ProcessMemory.is_executable checks every covered region's committed/guard
    state. The exact read also rejects NOACCESS or failed/partial transfers.
    Contents are ordinary data, even when their bytes resemble instructions.
    The caller must freshly read its RMW inputs after acquiring the proof.
    """
    checked = _data_ranges(ranges)
    for address, size in checked:
        try:
            if memory.is_executable(address, size) is not False:
                raise HookError("Executable or unclassified pages cannot be debugger data windows.")
            raw = memory.read(address, size)
            if type(raw) is not bytes or len(raw) != size:
                raise HookError("Debugger data window did not return an exact readable transfer.")
        except (OSError, ValueError) as exc:
            raise HookError("Debugger data window is not committed readable non-executable memory: " + str(exc)) from exc


@dataclass
class _Hold:
    ready: threading.Event
    release: threading.Event
    finished: threading.Event
    held: bool = False
    error: Exception | None = None
    deadline: float = 0
    contexts: dict | None = None
    events: int = 0
    worker: threading.Thread | None = None


class DebugEventCoordinator:
    """A bounded user-mode debug-event publication coordinator.

    Attaching changes debugger-visible process state and requires debugging
    access. No privilege is enabled, no debugger conflict is bypassed, and no
    remote injected breakpoint thread is created by our code. Bounds and failed
    contexts reject publication. Lease expiry never resumes a pending writer.
    """
    def __init__(self, acquire_timeout=5.0, hold_timeout=30.0):
        if (type(acquire_timeout) not in {int, float} or not 0.05 <= acquire_timeout <= 30
                or type(hold_timeout) not in {int, float} or not 0.05 <= hold_timeout <= 120):
            raise ValueError("Invalid bounded debugger acquisition/hold timeout.")
        self.acquire_timeout, self.hold_timeout = float(acquire_timeout), float(hold_timeout)
        self._busy = threading.Lock()
        self.last_observation: dict = {}

    def _run(self, memory, identity, ranges, hold, entry_windows=None,
             literal_windows=(), exclusion_ranges=(), data_only=False):
        kernel = None
        attached = False
        kill_disabled = False
        pending = None
        continue_status = DBG_CONTINUE
        debug_threads = {}
        debug_process = None
        try:
            kernel = _api()
            if memory.identity != identity or not memory.is_alive():
                raise HookError("The exact debugger target exited or changed before attach.")
            present = wintypes.BOOL()
            if not kernel.CheckRemoteDebuggerPresent(memory._handle, ctypes.byref(present)):
                raise _error("CheckRemoteDebuggerPresent")
            if present.value:
                raise HookError("The target already has a debugger; publication is refused.")
            if not kernel.DebugActiveProcess(memory.pid):
                raise _error("DebugActiveProcess")
            attached = True
            # Windows only permits this after a debug connection exists. Set
            # it before continuing any event or exposing a proof to the caller.
            if not kernel.DebugSetProcessKillOnExit(False):
                raise _error("DebugSetProcessKillOnExit(FALSE)")
            kill_disabled = True
            while not hold.release.is_set():
                if time.monotonic() > hold.deadline:
                    raise HookError("Debug-event acquisition timed out; no entry was admitted.")
                event = _DebugEvent()
                if not kernel.WaitForDebugEvent(ctypes.byref(event), 50):
                    if ctypes.get_last_error() == ERROR_SEM_TIMEOUT:
                        continue
                    raise _error("WaitForDebugEvent")
                pending = event
                hold.events += 1
                if hold.events > MAX_DEBUG_EVENTS or event.pid != memory.pid:
                    raise HookError("Unexpected process or excessive event count in debugger hold.")
                continue_status = DBG_CONTINUE
                if event.code == 3:
                    debug_process = event.info.create_process.process
                    debug_threads[event.tid] = event.info.create_process.thread
                    if event.info.create_process.file and not kernel.CloseHandle(event.info.create_process.file):
                        raise _error("CloseHandle debug image file")
                elif event.code == 2:
                    debug_threads[event.tid] = event.info.create_thread.thread
                elif event.code == 6:
                    if event.info.load_dll.file and not kernel.CloseHandle(event.info.load_dll.file):
                        raise _error("CloseHandle debug DLL file")
                elif event.code == 4:
                    debug_threads.pop(event.tid, None)  # OS closes it on continuation.
                elif event.code == 5:
                    debug_threads.clear()
                    debug_process = None  # OS closes process/thread handles on continuation.
                    raise HookError("The debugger target exited before a write safe point.")
                elif event.code == 1:
                    continue_status = DBG_EXCEPTION_NOT_HANDLED
                    record = event.info.exception.record
                    if record.code in BREAKPOINT_CODES:
                        # Admit only the known attach breakpoint inside held
                        # ntdll, never swallow arbitrary application int3 events.
                        addresses = {memory.resolve_export("ntdll", "DbgBreakPoint", pointer_size=8)}
                        if memory.pointer_size == 4:
                            addresses.add(memory.resolve_export("ntdll", "DbgBreakPoint", pointer_size=4))
                        if int(record.address or 0) not in addresses:
                            raise HookError("Unexpected application breakpoint during debugger attach.")
                        continue_status = DBG_CONTINUE
                        if data_only:
                            _check_data_windows(memory, ranges)
                        else:
                            code_ranges = (tuple((address, len(original)) for address, original, _, _ in entry_windows)
                                           if entry_windows is not None else ranges)
                            _check_overwrite_windows(memory, code_ranges, entry_windows)
                            if literal_windows:
                                _check_literal_windows(memory, literal_windows, exclusion_ranges)
                        hold.contexts = _check_contexts(kernel, memory, ranges)
                        if memory.identity != identity or not memory.is_alive():
                            raise HookError("The held debug-event target identity is uncertain.")
                        hold.deadline = time.monotonic() + self.hold_timeout
                        hold.held = True
                        hold.ready.set()
                        # Expiration invalidates proof, but only the caller's
                        # context exit releases this event. Otherwise a writer
                        # could race automatic resume after checking its lease.
                        hold.release.wait()
                        hold.held = False
                        break
                if not kernel.ContinueDebugEvent(event.pid, event.tid, continue_status):
                    raise _error("ContinueDebugEvent acquisition")
                pending = None
        except Exception as exc:
            hold.error = exc
        finally:
            hold.held = False
            if kernel and pending is not None:
                if not kernel.ContinueDebugEvent(pending.pid, pending.tid, continue_status):
                    hold.error = HookUncertain(f"Debug-event continuation cleanup failed: {ctypes.get_last_error()}")
            if kernel and attached:
                def target_may_be_alive():
                    try:
                        return memory.is_alive()
                    except Exception:
                        # Unknown liveness must not let the debugger owner exit
                        # while Windows' default kill policy could still apply.
                        return True
                if not kernel.DebugActiveProcessStop(memory.pid):
                    # Natural exit removes the debug connection as well.
                    if target_may_be_alive():
                        hold.error = HookUncertain(f"Debugger detach cleanup failed: {ctypes.get_last_error()}")
                        if not kill_disabled:
                            # Exiting this thread while Windows' default policy
                            # still applies would kill the target. Keep ownership
                            # alive and reject every caller proof until either
                            # kill-on-exit is disabled or actual detach succeeds.
                            hold.ready.set()
                            while target_may_be_alive():
                                if kernel.DebugSetProcessKillOnExit(False):
                                    kill_disabled = True
                                    kernel.DebugActiveProcessStop(memory.pid)
                                    break
                                if kernel.DebugActiveProcessStop(memory.pid):
                                    break
                                time.sleep(0.05)
            if kernel:
                for handle in list(debug_threads.values()) + ([debug_process] if debug_process else []):
                    if handle and not kernel.CloseHandle(handle) and ctypes.get_last_error() != ERROR_INVALID_HANDLE:
                        hold.error = HookUncertain("Debugger owned-handle cleanup failed.")
            self.last_observation = {"identity": list(identity), "thread_contexts": hold.contexts,
                                     "events": hold.events, "error": str(hold.error) if hold.error else None,
                                     "context_policy": ("all-IP-outside-committed-nonexecutable-data" if data_only else
                                                        "all-IP-outside-overwrites-no-displaced-calls"),
                                     "saved_exception_contexts_verified": False}
            hold.ready.set()
            hold.finished.set()

    def hold(self, memory: Any, ranges):
        return self._hold(memory, tuple(ranges))

    def hold_data(self, memory: Any, ranges):
        """Hold a real debug event for fresh data-only read/modify/write inputs.

        This controller API admits only committed readable non-executable
        windows. It observes every held thread context without decoding data
        as instructions. Acquiring/releasing a lease performs no remote write.
        Executable provider allocations need their separate owned-data permit.
        """
        return self._hold(memory, _data_ranges(ranges), data_only=True)

    def hold_entries(self, memory: Any, entry_windows, *, literal_windows=(), exclusion_ranges=()):
        """Consume immutable original/replacement receipts from HookManager.

        This internal controller API is unavailable to table code. Both entry
        sequences are checked while the OS event is held; only a verified owned
        replacement can describe an inline far-jump pointer as data.
        """
        windows, literals = tuple(entry_windows), tuple(literal_windows)
        exclusions = tuple(dict.fromkeys(tuple(item) for item in exclusion_ranges))
        if (len(windows) + len(literals) > 4096
                or any(not isinstance(item, tuple) or len(item) != 4
                       or type(item[0]) is not int or type(item[1]) is not bytes
                       for item in windows + literals)
                or len(exclusions) > 4096 or any(len(item) != 2 for item in exclusions)):
            raise HookError("Invalid controller-owned entry window list.")
        ranges = tuple((address, len(original)) for address, original, _, _ in windows)
        if literals and not exclusions or exclusions and not literals:
            raise HookError("Executable literal windows require owner exclusions.")
        for address, original, _, _ in literals:
            if any(address < start + size and start < address + len(original) for start, size in ranges):
                raise HookError("Code and literal overwrite windows overlap.")
        return self._hold(memory, ranges + exclusions, windows, literals, exclusions)

    @contextmanager
    def _hold(self, memory: Any, ranges, entry_windows=None, literal_windows=(), exclusion_ranges=(), data_only=False):
        if sys.platform != "win32" or ctypes.sizeof(ctypes.c_void_p) != 8:
            raise HookError("Debug-event coordination requires Windows x64 Python.")
        if memory.pid == os.getpid():
            raise HookError("A trainer cannot debug/pause its own Python process.")
        if data_only:
            _check_data_windows(memory, ranges)
        acquire_timeout = remaining_seconds(self.acquire_timeout)
        if not self._busy.acquire(blocking=False):
            raise HookError("This debugger coordinator already owns another hold.")
        state = _Hold(threading.Event(), threading.Event(), threading.Event(),
                      deadline=time.monotonic() + acquire_timeout)
        identity = memory.identity
        thread = threading.Thread(target=self._run, args=(memory, identity, tuple(ranges), state, entry_windows,
                                                        literal_windows, exclusion_ranges, data_only),
                                  name="CT2Trainer-debug-event", daemon=True)
        state.worker = thread
        try:
            thread.start()
            wait_deadline = time.monotonic() + acquire_timeout + 1
            while not state.ready.wait(min(0.05, remaining_seconds(0.05))):
                broker_checkpoint()
                if time.monotonic() >= wait_deadline:
                    raise HookError("Debugger safe-point acquisition did not complete in time.")
            broker_checkpoint()
            if state.error:
                raise state.error
            if not state.held or state.finished.is_set():
                raise HookError("No OS debug event remains held for the target.")
            # Fast final admission: QuiescenceProof.verify separately checks
            # held target liveness, which can perform slow Win32 reads. Keep
            # this predicate free of process I/O and test its lease clock last.
            check = lambda: (memory.identity == identity and state.held
                             and not state.finished.is_set() and state.worker.is_alive()
                             and time.monotonic() <= state.deadline)
            yield QuiescenceProof(identity, tuple(ranges),
                                  "win32-debug-event-data-IP-checked" if data_only else "win32-debug-event-IP-checked", check)
        finally:
            state.release.set()
            finished = state.finished.wait(5)
            if not finished:
                raise HookUncertain("Debugger cleanup is still live; preserve receipt and avoid further writes.")
            self._busy.release()
            if state.error:
                raise state.error
