"""First-party fixed-signature mailbox ABI; no arbitrary target pointers.

The ABI is deliberately separate from Mono/IL2CPP resolution. Its first backend
is an independently owned, preloaded Windows fixture DLL. All integers are
little endian and the wire layout is identical for x86 and AMD64 targets.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
import math
import struct

VERSION = 1
PAYLOAD_LIMIT = 512
HEADER = struct.Struct("<4sHHIIIIQQIIQQ16sQQIIQQIIQIIQ")
FRAME_SIZE = HEADER.size + PAYLOAD_LIMIT
MAX_REQUESTS = 64
HOLD_START = 1
WORKER_COMPLETE = 0x100
MAIN_COMPLETE = 0x200
TLS_CLEARED = 0x400


class Command(IntEnum):
    HELLO = 1
    SUBMIT = 2
    QUERY = 3
    CANCEL = 4
    RELEASE = 5


class Status(IntEnum):
    REQUEST = 0
    READY = 1
    PREPARED = 2
    RUNNING = 3
    DONE = 4
    CANCELLED_BEFORE_START = 5
    REFUSED = 6
    UNKNOWN = 7


class Operation(IntEnum):
    CDECL_ADD = 1
    STDCALL_ADD = 2
    WIDE_RETURN = 3
    MIXED_FIVE = 4
    UTF16_ECHO = 5
    MAIN_BOOLEAN = 6
    WAIT_ADD = 7
    MAIN_BOOLEAN_ON_WORKER = 8  # owned negative affinity fixture


class ResultKind(IntEnum):
    NONE = 0
    I32 = 1
    U64 = 2
    F64 = 3
    UTF16 = 4
    BOOL = 5


class ProtocolError(ValueError):
    pass


def _uint(value: int, bits: int, field: str) -> int:
    if type(value) is not int or not 0 <= value < 1 << bits:
        raise ProtocolError(f"Invalid {field}.")
    return value


@dataclass(frozen=True)
class Frame:
    command: int
    status: int = 0
    operation: int = 0
    flags: int = 0
    request_id: int = 0
    generation: int = 1
    owner_pid: int = 0
    target_pid: int = 0
    owner_created: int = 0
    target_created: int = 0
    nonce: bytes = bytes(16)
    deadline_qpc: int = 0
    qpc_frequency: int = 0
    thread_id: int = 0
    main_thread_id: int = 0
    thread_created: int = 0
    call_count: int = 0
    payload: bytes = b""
    error: int = 0
    clock_sample: int = 0
    result_kind: int = 0
    pointer_bits: int = 0
    tls_marker: int = 0

    def encode(self) -> bytes:
        if type(self.payload) is not bytes or len(self.payload) > PAYLOAD_LIMIT:
            raise ProtocolError("Mailbox payload exceeds its bounded byte span.")
        if type(self.nonce) is not bytes or len(self.nonce) != 16:
            raise ProtocolError("Mailbox nonce must have exactly 16 bytes.")
        fields = (self.command, self.status, self.operation, self.flags,
                  self.request_id, self.generation, self.owner_pid, self.target_pid,
                  self.owner_created, self.target_created, self.nonce,
                  self.deadline_qpc, self.qpc_frequency, self.thread_id,
                  self.main_thread_id, self.thread_created, self.call_count,
                  len(self.payload), self.error, self.clock_sample, self.result_kind,
                  self.pointer_bits, self.tls_marker)
        wide = {4, 5, 8, 9, 11, 12, 15, 16, 19, 22}
        for index, value in enumerate(fields):
            if index != 10:
                _uint(int(value) if isinstance(value, IntEnum) else value, 64 if index in wide else 32, "mailbox scalar")
        return HEADER.pack(b"TFB1", VERSION, FRAME_SIZE, *fields) + self.payload.ljust(PAYLOAD_LIMIT, b"\0")

    @classmethod
    def decode(cls, raw: bytes) -> "Frame":
        if type(raw) is not bytes or len(raw) != FRAME_SIZE:
            raise ProtocolError("Mailbox frame length changed.")
        fields = HEADER.unpack_from(raw)
        if fields[:3] != (b"TFB1", VERSION, FRAME_SIZE):
            raise ProtocolError("Unknown mailbox schema or version.")
        values = fields[3:]
        length = values[17]
        if length > PAYLOAD_LIMIT or any(raw[HEADER.size + length:]):
            raise ProtocolError("Malformed counted payload or nonzero padding.")
        if values[0] not in Command._value2member_map_ or values[1] not in Status._value2member_map_:
            raise ProtocolError("Unknown mailbox command or status.")
        return cls(*values[:17], raw[HEADER.size:HEADER.size + length], *values[18:])

    def response_binding(self, request: "Frame") -> None:
        for name in ("command", "request_id", "generation", "owner_pid", "target_pid",
                     "owner_created", "target_created", "nonce", "operation", "deadline_qpc"):
            if getattr(self, name) != getattr(request, name):
                raise ProtocolError(f"Mailbox response changed {name}.")
        if self.status == Status.REQUEST or self.pointer_bits not in {32, 64}:
            raise ProtocolError("Mailbox response lacks its target ABI proof.")
        if self.qpc_frequency != request.qpc_frequency and request.command != Command.HELLO:
            raise ProtocolError("Mailbox clock frequency changed.")
        if self.flags & ~(HOLD_START | WORKER_COMPLETE | MAIN_COMPLETE | TLS_CLEARED):
            raise ProtocolError("Unknown completion flags.")
        completion = self.flags & (WORKER_COMPLETE | MAIN_COMPLETE)
        if completion == WORKER_COMPLETE | MAIN_COMPLETE:
            raise ProtocolError("Conflicting worker/main completion proofs.")
        if completion == WORKER_COMPLETE and (not self.thread_id or not self.thread_created or self.thread_id == self.main_thread_id):
            raise ProtocolError("Worker completion lacks its exact thread identity.")
        if completion == MAIN_COMPLETE and (not self.thread_created or not self.thread_id or self.thread_id != self.main_thread_id):
            raise ProtocolError("Main completion changed its captured thread identity.")

    @property
    def completed(self) -> bool:
        completion = self.flags & (WORKER_COMPLETE | MAIN_COMPLETE)
        return self.status in {Status.DONE, Status.CANCELLED_BEFORE_START, Status.REFUSED} and completion in {
            WORKER_COMPLETE, MAIN_COMPLETE}

    def result(self):
        if self.status != Status.DONE or not self.completed or not self.flags & TLS_CLEARED:
            raise ProtocolError("Typed result lacks a terminal, returned-call proof.")
        expected = {Operation.CDECL_ADD: ResultKind.I32, Operation.STDCALL_ADD: ResultKind.I32,
                    Operation.WAIT_ADD: ResultKind.I32, Operation.WIDE_RETURN: ResultKind.U64,
                    Operation.MIXED_FIVE: ResultKind.F64, Operation.UTF16_ECHO: ResultKind.UTF16,
                    Operation.MAIN_BOOLEAN: ResultKind.BOOL}
        if expected.get(self.operation) != self.result_kind:
            raise ProtocolError("Result type differs from its fixed operation contract.")
        kinds = {ResultKind.I32: ("<i", 4), ResultKind.U64: ("<Q", 8),
                 ResultKind.F64: ("<d", 8), ResultKind.BOOL: ("<I", 4)}
        if self.result_kind == ResultKind.UTF16:
            if len(self.payload) % 2:
                raise ProtocolError("Malformed counted UTF-16 result.")
            return self.payload.decode("utf-16-le", errors="strict")
        if self.result_kind not in kinds:
            raise ProtocolError("Unknown typed result.")
        fmt, size = kinds[self.result_kind]
        if len(self.payload) != size:
            raise ProtocolError("Typed result length mismatch.")
        value = struct.unpack(fmt, self.payload)[0]
        if self.result_kind == ResultKind.BOOL and value not in {0, 1}:
            raise ProtocolError("Malformed Boolean result.")
        if self.result_kind == ResultKind.F64 and not math.isfinite(value):
            raise ProtocolError("Nonfinite fixture result.")
        return value


def encode_arguments(operation: Operation, arguments: tuple) -> bytes:
    """Fixed contracts selected by a trusted caller, never by arbitrary code."""
    try:
        operation = Operation(operation)
        if type(arguments) is not tuple:
            raise ProtocolError("Typed arguments must be an immutable tuple.")
        if operation in {Operation.CDECL_ADD, Operation.STDCALL_ADD, Operation.WAIT_ADD}:
            if len(arguments) != 2 or any(type(x) is not int or not -(1 << 31) <= x < 1 << 31 for x in arguments):
                raise ProtocolError("Add contract requires two signed 32-bit integers.")
            if not -(1 << 31) <= sum(arguments) < 1 << 31:
                raise ProtocolError("Add result would overflow its signed contract.")
            return struct.pack("<ii", *arguments)
        if operation == Operation.WIDE_RETURN:
            if len(arguments) != 2:
                raise ProtocolError("Wide contract requires high and low words.")
            return struct.pack("<II", *(_uint(x, 32, "word") for x in arguments))
        if operation == Operation.MIXED_FIVE:
            if len(arguments) != 5:
                raise ProtocolError("Mixed contract requires five scalar arguments.")
            a, b, c, d, e = arguments
            if any(type(x) is not int or not -(1 << 31) <= x < 1 << 31 for x in (a, c, e)):
                raise ProtocolError("Mixed integer slots need signed 32-bit values.")
            if any(type(x) not in {float, int} or not math.isfinite(x) or abs(x) > 1e20 for x in (b, d)):
                raise ProtocolError("Mixed floating slots must be finite and bounded.")
            return struct.pack("<idi fi".replace(" ", ""), a, float(b), c, float(d), e)
        if operation == Operation.UTF16_ECHO:
            if len(arguments) != 1 or type(arguments[0]) is not str:
                raise ProtocolError("Echo contract requires a counted string.")
            raw = arguments[0].encode("utf-16-le", errors="strict")
            if len(raw) > PAYLOAD_LIMIT:
                raise ProtocolError("Counted string exceeds the mailbox budget.")
            return raw
        if operation in {Operation.MAIN_BOOLEAN, Operation.MAIN_BOOLEAN_ON_WORKER}:
            if len(arguments) != 1 or type(arguments[0]) is not bool:
                raise ProtocolError("Main-thread Boolean contract requires a Boolean.")
            return struct.pack("<I", int(arguments[0]))
    except (ValueError, OverflowError, struct.error) as exc:
        raise ProtocolError("Invalid typed fixture arguments.") from exc
    raise ProtocolError("Unsupported typed contract.")
