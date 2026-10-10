"""Owned-fixture typed broker controller with durable one-shot receipts.

This does not inject a DLL, attach a managed runtime, invoke arbitrary pointers,
or expose game execution. A fixture build manifest binds the exact independently
owned EXE/DLL/source bytes before a process is created. A future runtime adapter
needs its own binding and affinity proof; it cannot simply reuse this admission.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass, replace
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time

from .protocol import (Command, Frame, Operation, ProtocolError, Status,
                       FRAME_SIZE, HOLD_START, MAX_REQUESTS, encode_arguments)

# Unfinished native OVERLAPPED memory must outlive even a discarded controller.
# Entries are intentionally never automatically reclaimed on uncertainty.
_RETAINED_NATIVE_IO = []
_RETAINED_FIXTURES = []


class BrokerError(RuntimeError):
    pass


class BrokerUncertain(BrokerError):
    pass


class BrokerCancelled(BrokerError):
    pass


@dataclass(frozen=True)
class CallContext:
    """Explicit caller-owned deadline/cancellation; no thread-local assumptions."""
    deadline: float
    cancellation: threading.Event | None = None

    def __post_init__(self):
        if type(self.deadline) not in {int, float} or not math.isfinite(self.deadline) or self.deadline > time.monotonic() + 30:
            raise BrokerError("An explicit broker context cannot exceed one absolute 30-second deadline.")
        if self.cancellation is not None and not isinstance(self.cancellation, threading.Event):
            raise BrokerError("Broker cancellation must be an explicit event.")

    @classmethod
    def seconds(cls, seconds: float, cancellation: threading.Event | None = None):
        if type(seconds) not in {int, float} or not math.isfinite(seconds) or not 0 < seconds <= 30:
            raise BrokerError("Broker deadline must be positive and at most 30 seconds.")
        return cls(time.monotonic() + seconds, cancellation)

    def remaining(self) -> float:
        if type(self.deadline) not in {int, float} or not math.isfinite(self.deadline):
            raise BrokerError("Invalid explicit broker deadline.")
        if self.cancellation is not None and self.cancellation.is_set():
            raise BrokerCancelled("Caller cancelled its one-shot request.")
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise BrokerCancelled("Caller deadline expired.")
        return min(30.0, remaining)


class _Overlapped(ctypes.Structure):
    _fields_ = [("Internal", ctypes.c_size_t), ("InternalHigh", ctypes.c_size_t),
                ("Offset", wintypes.DWORD), ("OffsetHigh", wintypes.DWORD),
                ("hEvent", wintypes.HANDLE)]


class _Windows:
    def __init__(self):
        if sys.platform != "win32" or ctypes.sizeof(ctypes.c_void_p) != 8:
            raise BrokerError("The owned broker controller requires Windows AMD64 Python.")
        self.k = ctypes.WinDLL("kernel32", use_last_error=True)
        specs = {
            "OpenProcess": (wintypes.HANDLE, [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]),
            "GetProcessTimes": (wintypes.BOOL, [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4),
            "WaitForSingleObject": (wintypes.DWORD, [wintypes.HANDLE, wintypes.DWORD]),
            "CloseHandle": (wintypes.BOOL, [wintypes.HANDLE]),
            "CreateFileW": (wintypes.HANDLE, [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                            ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]),
            "WaitNamedPipeW": (wintypes.BOOL, [wintypes.LPCWSTR, wintypes.DWORD]),
            "SetNamedPipeHandleState": (wintypes.BOOL, [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p, ctypes.c_void_p]),
            "GetNamedPipeServerProcessId": (wintypes.BOOL, [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]),
            "CreateEventW": (wintypes.HANDLE, [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]),
            "ReadFile": (wintypes.BOOL, [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(_Overlapped)]),
            "WriteFile": (wintypes.BOOL, [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(_Overlapped)]),
            "GetOverlappedResult": (wintypes.BOOL, [wintypes.HANDLE, ctypes.POINTER(_Overlapped), ctypes.POINTER(wintypes.DWORD), wintypes.BOOL]),
            "CancelIoEx": (wintypes.BOOL, [wintypes.HANDLE, ctypes.POINTER(_Overlapped)]),
            "QueryPerformanceCounter": (wintypes.BOOL, [ctypes.POINTER(ctypes.c_int64)]),
            "QueryPerformanceFrequency": (wintypes.BOOL, [ctypes.POINTER(ctypes.c_int64)]),
            "IsWow64Process2": (wintypes.BOOL, [wintypes.HANDLE, ctypes.POINTER(ctypes.c_ushort), ctypes.POINTER(ctypes.c_ushort)]),
        }
        for name, (restype, argtypes) in specs.items():
            try:
                function = getattr(self.k, name)
            except AttributeError as exc:
                raise BrokerError(f"Owned broker requires {name} on Windows AMD64.") from exc
            function.restype, function.argtypes = restype, argtypes
        self.owner_handle = self.open_process(os.getpid())
        try:
            self.owner = (os.getpid(), self.created(self.owner_handle))
            self.bits(self.owner_handle, expected=64)
            value = ctypes.c_int64()
            if not self.k.QueryPerformanceFrequency(ctypes.byref(value)) or value.value <= 0:
                raise BrokerError("A monotonic QPC clock is unavailable.")
            self.frequency = value.value
        except Exception:
            self.k.CloseHandle(self.owner_handle)
            raise

    def open_process(self, pid):
        handle = self.k.OpenProcess(0x1000 | 0x100000, False, pid)
        if not handle:
            raise BrokerError(f"Cannot hold exact process identity: Win32 {ctypes.get_last_error()}.")
        return handle

    def created(self, handle):
        values = [wintypes.FILETIME() for _ in range(4)]
        if not self.k.GetProcessTimes(handle, *(ctypes.byref(v) for v in values)):
            raise BrokerError("Exact process creation-time proof failed.")
        return values[0].dwHighDateTime << 32 | values[0].dwLowDateTime

    def alive(self, handle, identity):
        return self.created(handle) == identity[1] and self.k.WaitForSingleObject(handle, 0) == 258

    def bits(self, handle, expected):
        process, native = ctypes.c_ushort(), ctypes.c_ushort()
        if not self.k.IsWow64Process2(handle, ctypes.byref(process), ctypes.byref(native)) or native.value != 0x8664:
            raise BrokerError("Owned broker profile requires Windows on native AMD64.")
        actual = 32 if process.value == 0x14C else 64 if process.value == 0 else 0
        if actual != expected:
            raise BrokerError("Owned target ABI differs from its pinned build.")

    def qpc(self):
        value = ctypes.c_int64()
        if not self.k.QueryPerformanceCounter(ctypes.byref(value)) or value.value < 0:
            raise BrokerError("Broker clock sample failed.")
        return value.value


class _PipeTransport:
    def __init__(self, windows, target_handle, target, nonce):
        self.w = windows
        self.target_handle, self.target = target_handle, target
        self.name = rf"\\.\pipe\CT2TrainerOwnedBroker-{target[0]}-{nonce.hex()}"
        self.retained_io = []  # A failed drain retains the exact OVERLAPPED/buffer/event.

    def _guard(self, context):
        context.remaining()
        if not self.w.alive(self.target_handle, self.target):
            raise BrokerUncertain("Exact target process exited before the exchange completed.")

    def _io(self, pipe, raw, *, read, context):
        k = self.w.k
        buffer = ctypes.create_string_buffer(FRAME_SIZE) if read else ctypes.create_string_buffer(raw, len(raw))
        overlap, done = _Overlapped(), wintypes.DWORD()
        overlap.hEvent = k.CreateEventW(None, True, False, None)
        if not overlap.hEvent:
            raise BrokerError("Cannot create bounded transport completion event.")
        pending = False
        try:
            function = k.ReadFile if read else k.WriteFile
            self._guard(context)
            okay = function(pipe, buffer, FRAME_SIZE, ctypes.byref(done), ctypes.byref(overlap))
            if not okay:
                if ctypes.get_last_error() != 997:
                    raise BrokerUncertain(f"Mailbox I/O failed: Win32 {ctypes.get_last_error()}.")
                pending = True
                while True:
                    observed = k.WaitForSingleObject(overlap.hEvent, 5)
                    if observed == 0:
                        break
                    if observed != 258:
                        raise BrokerUncertain("Mailbox I/O completion wait is unknown.")
                    self._guard(context)
                okay = k.GetOverlappedResult(pipe, ctypes.byref(overlap), ctypes.byref(done), False)
                if not okay and ctypes.get_last_error() in {996, 997, 6}:
                    raise BrokerUncertain("Exact mailbox I/O may still be pending.")
                pending = False
            if not okay or done.value != FRAME_SIZE:
                raise BrokerUncertain("Mailbox message was not transferred as one exact frame.")
            self._guard(context)
            return buffer.raw[:FRAME_SIZE] if read else None
        finally:
            if pending:
                k.CancelIoEx(pipe, ctypes.byref(overlap))
                # Cancellation is not completion. Never release an in-flight buffer.
                drained = k.WaitForSingleObject(overlap.hEvent, 1000) == 0
                if drained:
                    completed = k.GetOverlappedResult(pipe, ctypes.byref(overlap), ctypes.byref(done), False)
                    drained = bool(completed) or ctypes.get_last_error() not in {996, 997, 6}
                if not drained:
                    self.retained_io.append((pipe, overlap, buffer))
                    _RETAINED_NATIVE_IO.append((self.w, pipe, overlap, buffer))
                    overlap = None
            if overlap is not None:
                k.CloseHandle(overlap.hEvent)

    def exchange(self, frame, context, *, drop_ack=False):
        k, pipe = self.w.k, None
        try:
            while True:
                self._guard(context)
                pipe = k.CreateFileW(self.name, 0x80000000 | 0x40000000, 0, None, 3, 0x40000000, None)
                if pipe != ctypes.c_void_p(-1).value:
                    break
                pipe = None
                error = ctypes.get_last_error()
                if error not in {2, 231}:
                    raise BrokerError(f"Cannot open owned mailbox: Win32 {error}.")
                k.WaitNamedPipeW(self.name, min(20, max(1, int(context.remaining() * 1000))))
                time.sleep(0.001)
            server = wintypes.DWORD()
            if not k.GetNamedPipeServerProcessId(pipe, ctypes.byref(server)) or server.value != self.target[0]:
                raise BrokerUncertain("Named-pipe server identity changed.")
            mode = wintypes.DWORD(2)
            if not k.SetNamedPipeHandleState(pipe, ctypes.byref(mode), None, None):
                raise BrokerError("Cannot require message-framed mailbox reads.")
            self._guard(context)
            self._io(pipe, frame.encode(), read=False, context=context)
            if drop_ack:
                return None
            raw = self._io(pipe, None, read=True, context=context)
            reply = Frame.decode(raw)
            reply.response_binding(frame)
            return reply
        finally:
            if pipe and not any(item[0] == pipe for item in self.retained_io):
                k.CloseHandle(pipe)


class ReceiptJournal:
    """Exclusive immutable, hash-chained files; no pending state overwrites."""
    def __init__(self, directory: Path, binding: dict):
        self.directory = Path(directory).absolute()
        self.directory.mkdir(parents=True, exist_ok=False)
        self.sequence, self.previous = 0, "0" * 64
        self.append("binding", binding)

    def append(self, kind, value):
        if self.sequence >= 4096:
            raise BrokerUncertain("Broker journal count budget exhausted.")
        record = {"schema": "ct2trainer-target-broker-receipt/v1", "sequence": self.sequence,
                  "previous_sha256": self.previous, "kind": kind, "value": value}
        raw = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        if len(raw) > 8192:
            raise BrokerUncertain("Broker journal byte budget exhausted.")
        path = self.directory / f"{self.sequence:04d}-{kind}.json"
        with path.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if path.read_bytes() != raw:
            raise BrokerUncertain("Durable broker journal changed during verification.")
        self.previous = hashlib.sha256(raw).hexdigest()
        self.sequence += 1
        return path

    def verify(self):
        paths = []
        with os.scandir(self.directory) as entries:
            for count, entry in enumerate(entries):
                if count > 4098:
                    raise BrokerUncertain("Broker journal inventory exceeds its bounded scope.")
                if entry.name.endswith(".json"):
                    paths.append(Path(entry.path))
        paths.sort()
        previous = "0" * 64
        if len(paths) != self.sequence:
            raise BrokerUncertain("Broker journal inventory changed.")
        for index, path in enumerate(paths):
            if path.stat().st_size > 8192:
                raise BrokerUncertain("Broker journal grew beyond its budget.")
            with path.open("rb") as stream:
                raw = stream.read(8193)
            if len(raw) > 8192:
                raise BrokerUncertain("Broker journal grew beyond its budget.")
            record = json.loads(raw)
            if record.get("sequence") != index or record.get("previous_sha256") != previous:
                raise BrokerUncertain("Broker durable receipt chain changed.")
            previous = hashlib.sha256(raw).hexdigest()
        if previous != self.previous:
            raise BrokerUncertain("Broker durable receipt hash changed.")


class TypedBroker:
    """Trusted-Python controller. Invocation is one-shot, never a saved toggle."""
    def __init__(self, binding: Frame, transport, journal: ReceiptJournal, qpc, frequency):
        self.binding, self.transport, self.journal = binding, transport, journal
        self.qpc, self.frequency = qpc, frequency
        self.next_id, self.requests, self.uncertain = 1, {}, False
        self.observations = {}
        self.closed, self.clock_offset = False, None
        self.main_tid, self.pointer_bits = 0, 0

    def handshake(self, context):
        before = self.qpc()
        request = replace(self.binding, command=Command.HELLO)
        reply = self.transport.exchange(request, context)
        after = self.qpc()
        if reply.status != Status.READY or reply.qpc_frequency != self.frequency or not before <= reply.clock_sample <= after:
            raise BrokerError("Target QPC epoch/frequency did not match its bounded handshake.")
        # On this same-host profile, calibrate a conservative lower clock offset.
        # A deadline is translated from the original absolute context, never reset.
        self.clock_offset = reply.clock_sample - after
        self.main_tid, self.pointer_bits = reply.main_thread_id, reply.pointer_bits
        self.journal.append("clock-proof", {"controller_before": before, "controller_after": after,
            "target_sample": reply.clock_sample, "frequency": self.frequency, "offset_lower": self.clock_offset,
            "main_thread_id": self.main_tid, "pointer_bits": self.pointer_bits})

    def _guard(self, *, mutation=False):
        if self.closed or self.clock_offset is None:
            raise BrokerError("Broker session is closed or lacks a clock binding.")
        self.journal.verify()
        if mutation and self.uncertain:
            raise BrokerUncertain("An uncertain one-shot invocation forbids further submissions.")

    def submit(self, operation: Operation, arguments: tuple, context: CallContext, *, hold_start=False, drop_ack=False):
        self._guard(mutation=True)
        if any(not self.observations.get(identifier) or not self.observations[identifier].completed for identifier in self.requests):
            raise BrokerError("The bounded broker accepts one outstanding invocation at a time.")
        if self.next_id > MAX_REQUESTS:
            raise BrokerError("Owned request ledger budget exhausted.")
        payload = encode_arguments(operation, arguments)
        context.remaining()
        before = time.monotonic()
        sample = self.qpc()
        after = time.monotonic()
        if after < before:
            raise BrokerError("Controller monotonic clock moved backwards.")
        deadline = sample + math.floor((context.deadline - after) * self.frequency) + self.clock_offset
        if deadline <= sample or deadline - sample > self.frequency * 30:
            raise BrokerCancelled("Original caller deadline cannot admit a target call.")
        request = replace(self.binding, command=Command.SUBMIT, operation=int(operation),
                          flags=HOLD_START if hold_start else 0, request_id=self.next_id,
                          payload=payload, deadline_qpc=deadline, qpc_frequency=self.frequency)
        self.journal.append("intent", {"request_id": request.request_id, "request_hex": request.encode().hex(),
                                     "sha256": hashlib.sha256(request.encode()).hexdigest(), "one_shot": True})
        self.requests[request.request_id] = request
        self.next_id += 1  # Intent consumes its ID even when acknowledgement is lost.
        try:
            reply = self.transport.exchange(request, context, drop_ack=drop_ack)
            if reply is None:
                raise BrokerUncertain("Submission acknowledgement was deliberately lost.")
            self._record(reply)
            return reply
        except Exception as exc:
            self.uncertain = True
            self.journal.append("uncertain", {"request_id": request.request_id, "reason": str(exc)[:1024]})
            raise BrokerUncertain("One-shot dispatch has no verified acknowledgement; no replay is permitted.") from exc

    def _record(self, reply):
        if reply.main_thread_id != self.main_tid or reply.pointer_bits != self.pointer_bits:
            raise BrokerUncertain("Target ABI or main-thread binding changed.")
        self.journal.append("observation", {"request_id": reply.request_id, "response_hex": reply.encode().hex(),
                                          "sha256": hashlib.sha256(reply.encode()).hexdigest()})
        self.observations[reply.request_id] = reply

    def observe(self, request_id: int, context: CallContext, command=Command.QUERY):
        self._guard()
        if request_id not in self.requests or command not in {Command.QUERY, Command.CANCEL, Command.RELEASE}:
            raise BrokerError("Cannot observe or control a foreign one-shot request.")
        original = self.requests[request_id]
        if self.uncertain and command == Command.RELEASE:
            observed = self.observations.get(request_id)
            if original.operation != Operation.WAIT_ADD or observed is None or observed.status != Status.RUNNING:
                raise BrokerUncertain("An uncertain prepared call cannot be released into execution.")
        request = replace(original, command=command, flags=0, payload=b"")
        if command != Command.QUERY:
            self.journal.append("control-intent", {"request_id": request_id, "command": int(command)})
        try:
            reply = self.transport.exchange(request, context)
            self._record(reply)
            return reply
        except Exception:
            self.uncertain = True
            raise

    def wait(self, request_id: int, context: CallContext):
        try:
            while True:
                context.remaining()
                reply = self.observe(request_id, context)
                if reply.completed:
                    if reply.status == Status.CANCELLED_BEFORE_START:
                        raise BrokerCancelled("Target acknowledged cancellation before the call began.")
                    if reply.status == Status.REFUSED:
                        raise BrokerError(f"Typed call was refused: Win32 {reply.error}.")
                    return reply
                if reply.status == Status.UNKNOWN:
                    raise BrokerUncertain("Target reported an unknown one-shot state.")
                time.sleep(0.003)
        except BrokerCancelled as exc:
            # A terminal cancellation is already proven; an expired wait needs an
            # independent observation lease, without extending target admission.
            if "acknowledged cancellation" in str(exc):
                raise
            proven_cancel = False
            try:
                cleanup = CallContext.seconds(1)
                reply = self.observe(request_id, cleanup, Command.CANCEL)
                for _ in range(100):
                    if reply.completed:
                        break
                    time.sleep(0.003)
                    reply = self.observe(request_id, cleanup)
                if reply.completed and reply.status == Status.CANCELLED_BEFORE_START:
                    proven_cancel = True
            except Exception:
                pass
            if proven_cancel:
                raise BrokerCancelled("Target acknowledged cancellation before the call began.") from exc
            self.uncertain = True
            self.journal.append("uncertain", {"request_id": request_id, "reason": "deadline/cancellation without no-call completion"})
            raise BrokerUncertain("Caller stopped waiting while a target call may still execute.") from exc
        except BrokerUncertain:
            self.uncertain = True
            raise
        except BrokerError:
            raise
        except Exception as exc:
            self.uncertain = True
            self.journal.append("uncertain", {"request_id": request_id, "reason": str(exc)[:1024]})
            raise BrokerUncertain("Completion evidence could not be validated.") from exc

    def invoke(self, operation, arguments, context):
        reply = self.submit(operation, arguments, context)
        return self.wait(reply.request_id, context).result()


def _sha(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > 32 * 1024 * 1024:
        raise BrokerError("Owned fixture component is absent or exceeds its size budget.")
    with path.open("rb") as stream:
        raw = stream.read(32 * 1024 * 1024 + 1)
    if len(raw) > 32 * 1024 * 1024:
        raise BrokerError("Owned fixture component grew beyond its size budget.")
    return hashlib.sha256(raw).hexdigest()


class OwnedFixture:
    """Only a canonical first-party build report can admit this owned process."""
    def __init__(self, build_report, architecture: str, receipt_directory):
        if architecture not in {"x86", "x64"}:
            raise BrokerError("Owned fixture architecture must be explicit.")
        report_path = Path(build_report).absolute()
        if report_path.stat().st_size > 65536:
            raise BrokerError("Owned fixture report exceeds its budget.")
        report = json.loads(report_path.read_bytes())
        if report.get("schema") != "ct2trainer-owned-target-broker-build/v1" or report.get("status") != "passed" or report.get("ce_inputs") != []:
            raise BrokerError("Not an independently owned broker fixture build.")
        # Bound exactly the four first-party sources, not arbitrary report claims.
        root = Path(__file__).resolve().parents[4]
        expected = [root / "src/ct2trainer/native/target_broker/broker.c",
                    root / "src/ct2trainer/native/target_broker/broker_abi.h",
                    root / "tests/windows/target_broker_fixture/broker_target.c",
                    root / "tests/windows/target_broker_fixture/Invoke-TargetBrokerBuild.ps1"]
        sources = report.get("sources")
        if not isinstance(sources, list) or len(sources) != len(expected):
            raise BrokerError("Owned fixture source inventory is incomplete.")
        for item, path in zip(sources, expected):
            if Path(item.get("path", "")).resolve() != path.resolve() or item.get("sha256") != _sha(path) or _sha(item.get("snapshot", "")) != item["sha256"]:
                raise BrokerError("Owned fixture source pin changed.")
        choices = [x for x in report.get("results", []) if x.get("architecture") == architecture]
        if len(choices) != 1:
            raise BrokerError("Owned fixture build lacks exactly one requested architecture.")
        selected = choices[0]
        exe, dll = Path(selected["executable"]).absolute(), Path(selected["dll"]).absolute()
        if (exe.resolve() != (report_path.parent / architecture / "NativeTargetBrokerFixture.exe").resolve()
                or dll.resolve() != (report_path.parent / architecture / "CT2TrainerOwnedBroker.dll").resolve()):
            raise BrokerError("Owned broker component names changed.")
        components = selected.get("components")
        if not isinstance(components, list) or len(components) != 2:
            raise BrokerError("Owned broker component inventory changed.")
        machine = 0x14C if architecture == "x86" else 0x8664
        for item, path in zip(components, (exe, dll)):
            if Path(item.get("path", "")).resolve() != path.resolve() or item.get("sha256") != _sha(path) or item.get("pe_machine") != machine:
                raise BrokerError("Owned broker binary pin changed.")
            raw = path.read_bytes()
            offset = int.from_bytes(raw[0x3C:0x40], "little")
            if raw[:2] != b"MZ" or raw[offset:offset + 4] != b"PE\0\0" or int.from_bytes(raw[offset + 4:offset + 6], "little") != machine:
                raise BrokerError("Owned broker actual PE ABI changed.")
        self.windows = _Windows()
        nonce = secrets.token_bytes(16)
        self.process = None
        try:
            self.journal = ReceiptJournal(Path(receipt_directory), {"owner": self.windows.owner,
                "nonce": nonce.hex(), "generation": 1, "architecture": architecture,
                "executable_sha256": _sha(exe), "dll_sha256": _sha(dll), "build_sha256": _sha(report_path),
                "retention": "all target ledger/code/buffers/worker handles until target process exit", "one_shot": True})
            self.journal.append("launch-intent", {"executable": str(exe), "dll": str(dll), "owner": self.windows.owner})
            self._stdout_path = self.journal.directory / "target.stdout.jsonl"
            self._stderr_path = self.journal.directory / "target.stderr.log"
            self._stdout_sink = self._stdout_path.open("xb")
            self._stderr_sink = self._stderr_path.open("xb")
            self.process = subprocess.Popen([str(exe), str(dll), str(self.windows.owner[0]),
                str(self.windows.owner[1]), nonce.hex()], stdin=subprocess.PIPE, stdout=self._stdout_sink, stderr=self._stderr_sink,
                creationflags=subprocess.CREATE_NO_WINDOW)
            self.journal.append("process-created", {"pid": self.process.pid, "created": None})
            self.target_handle = self.windows.open_process(self.process.pid)
            self.target = (self.process.pid, self.windows.created(self.target_handle))
            self.journal.append("target-binding", {"target": self.target})
            self.windows.bits(self.target_handle, expected=32 if architecture == "x86" else 64)
            binding = Frame(Command.HELLO, owner_pid=self.windows.owner[0], owner_created=self.windows.owner[1],
                            target_pid=self.target[0], target_created=self.target[1], nonce=nonce)
            self.broker = TypedBroker(binding, _PipeTransport(self.windows, self.target_handle, self.target, nonce),
                                      self.journal, self.windows.qpc, self.windows.frequency)
            self.broker.handshake(CallContext.seconds(3))
        except Exception as exc:
            try:
                if hasattr(self, "journal"):
                    try:
                        self.journal.append("setup-failure", {"reason": str(exc)[:1024], "pid": self.process.pid if self.process else None})
                    except Exception:
                        pass  # Journal failure must not skip the owned exit request.
                if self.process is not None:
                    # Popen holds the exact CreateProcess handle even when a
                    # subsequent PID-based OpenProcess or identity query fails.
                    if not hasattr(self, "target"):
                        # Stop our exact owned CreateProcess child even if a
                        # creation-time query remains unavailable afterward.
                        self._request_exit()
                        self.target = (self.process.pid, self.windows.created(int(self.process._handle)))
                    if not hasattr(self, "target_handle"):
                        self.target_handle = int(self.process._handle)
                        self._popen_handle_only = True
                    self.stop()
                else:
                    for name in ("_stdout_sink", "_stderr_sink"):
                        stream = getattr(self, name, None)
                        if stream is not None:
                            stream.close()
                    self.windows.k.CloseHandle(self.windows.owner_handle)
            except Exception as cleanup_error:
                if not any(item is self for item in _RETAINED_FIXTURES):
                    _RETAINED_FIXTURES.append(self)
                raise BrokerUncertain("Owned fixture setup failed; exact child/receipt resources remain retained.") from cleanup_error
            raise

    def _request_exit(self):
        if self.process.poll() is None:
            try:
                self.process.stdin.write(b"q\n")
                self.process.stdin.flush()
                self.process.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired) as exc:
                if hasattr(self, "journal"):
                    self.journal.append("uncertain", {"reason": "owned target did not stop through its explicit exit channel"})
                raise BrokerUncertain("Owned fixture remains live; its buffers and code must remain retained.") from exc

    def stop(self):
        if getattr(self, "_stopped", False):
            return
        if not any(item is self for item in _RETAINED_FIXTURES):
            _RETAINED_FIXTURES.append(self)
        self._request_exit()
        if self.windows.k.WaitForSingleObject(self.target_handle, 0) != 0 or self.windows.created(self.target_handle) != self.target[1]:
            raise BrokerUncertain("Owned target exit lacks exact held-handle proof.")
        for name in ("_stdout_sink", "_stderr_sink"):
            stream = getattr(self, name, None)
            if stream is not None:
                stream.close()
        with self._stdout_path.open("rb") as stream:
            raw_output = stream.read(4097)
        if len(raw_output) > 4096:
            raise BrokerUncertain("Owned target output exceeded its diagnostic budget.")
        self.retention = None
        if hasattr(self, "broker") and self.broker.clock_offset is not None:
            try:
                lines = [json.loads(line) for line in raw_output.splitlines()]
                metadata, retention = lines
            except (ValueError, TypeError) as exc:
                raise BrokerUncertain("Owned target lacked its exact terminal retention report.") from exc
            if (metadata != {"schema": "ct2trainer-owned-broker-target/v1", "pid": self.target[0], "created": self.target[1],
                             "pointer_bits": self.broker.pointer_bits, "main_thread_id": self.broker.main_tid}
                    or retention.get("schema") != "ct2trainer-owned-broker-retention/v1"):
                raise BrokerUncertain("Owned target diagnostic identity changed.")
            self.retention = retention
        if hasattr(self, "journal"):
            self.journal.append("target-exit", {"target": self.target, "wait_result": 0,
                "exit_code": self.process.returncode, "replay_allowed": False,
                "stdout_sha256": hashlib.sha256(raw_output).hexdigest(), "retention": self.retention})
        if hasattr(self, "broker"):
            self.broker.closed = True
        self._stopped = True
        if not getattr(self, "_popen_handle_only", False):
            self.windows.k.CloseHandle(self.target_handle)
        self.windows.k.CloseHandle(self.windows.owner_handle)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            if stream is not None:
                stream.close()
        _RETAINED_FIXTURES[:] = [item for item in _RETAINED_FIXTURES if item is not self]

