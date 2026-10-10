"""Meaningful one-shot transport/receipt/ABI gates, independent of engine code."""
import dataclasses
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import ctypes
import io
import subprocess

from ct2trainer.native.target_broker import (BrokerError, BrokerCancelled,
    BrokerUncertain, CallContext, Command, Frame, Operation, ProtocolError,
    OwnedFixture, ReceiptJournal, Status, TypedBroker)
from ct2trainer.native.target_broker.protocol import (FRAME_SIZE, HEADER,
    HOLD_START, MAIN_COMPLETE, TLS_CLEARED, WORKER_COMPLETE, encode_arguments)
from ct2trainer.native.target_broker.client import _PipeTransport
import ct2trainer.native.target_broker.client as broker_client


class ProtocolTests(unittest.TestCase):
    def test_wire_layout_is_architecture_independent_and_counted(self):
        frame = Frame(Command.SUBMIT, operation=Operation.UTF16_ECHO, request_id=2,
                      owner_created=0x1_FFFF_FFFF, payload="a\0猫🙂".encode("utf-16-le"))
        self.assertEqual(HEADER.size, 152)
        self.assertEqual(FRAME_SIZE, 664)
        self.assertEqual(Frame.decode(frame.encode()), frame)
        self.assertEqual(Frame.decode(frame.encode()).payload, frame.payload)

    def test_unknown_schema_length_padding_and_integer_overflow_are_refused(self):
        raw = Frame(Command.HELLO).encode()
        variants = [raw[:-1], b"BAD!" + raw[4:], raw[:4] + b"\x02\0" + raw[6:], raw[:-1] + b"\x01"]
        for value in variants:
            with self.subTest(value=value[:8]), self.assertRaises(ProtocolError):
                Frame.decode(value)
        for change in ({"owner_pid": True}, {"request_id": 1 << 64}, {"nonce": b"x"}, {"payload": b"x" * 513}):
            with self.subTest(change=change), self.assertRaises(ProtocolError):
                dataclasses.replace(Frame(Command.HELLO), **change).encode()

    def test_fixed_typed_contracts_have_exact_sizes_and_no_pointer_contract(self):
        self.assertEqual(encode_arguments(Operation.CDECL_ADD, (-3, 12)), struct.pack("<ii", -3, 12))
        self.assertEqual(encode_arguments(Operation.WIDE_RETURN, (0xFEDCBA98, 0x87654321)), bytes.fromhex("98badcfe21436587"))
        self.assertEqual(len(encode_arguments(Operation.MIXED_FIVE, (1, 2.5, 3, 4.25, 5))), 24)
        self.assertEqual(encode_arguments(Operation.MAIN_BOOLEAN, (True,)), b"\1\0\0\0")
        bad = [(Operation.CDECL_ADD, (True, 1)), (Operation.CDECL_ADD, (0x7FFFFFFF, 1)),
               (Operation.WIDE_RETURN, (1 << 32, 0)), (Operation.MIXED_FIVE, (1, float("nan"), 3, 4., 5)),
               (Operation.UTF16_ECHO, ("x" * 257,)), (Operation.MAIN_BOOLEAN, (1,)), (99, (0x1234,))]
        for op, args in bad:
            with self.subTest(op=op, args=args), self.assertRaises(ProtocolError):
                encode_arguments(op, args)

    def test_completion_requires_return_thread_and_tls_proofs(self):
        reply = Frame(Command.QUERY, status=Status.DONE, operation=Operation.CDECL_ADD, result_kind=1, payload=struct.pack("<i", 17))
        for flags in (0, TLS_CLEARED, WORKER_COMPLETE, MAIN_COMPLETE):
            with self.subTest(flags=flags), self.assertRaises(ProtocolError):
                dataclasses.replace(reply, flags=flags).result()
        self.assertEqual(dataclasses.replace(reply, flags=WORKER_COMPLETE | TLS_CLEARED).result(), 17)
        self.assertEqual(dataclasses.replace(reply, flags=MAIN_COMPLETE | TLS_CLEARED).result(), 17)
        with self.assertRaises(ProtocolError):
            dataclasses.replace(reply, status=Status.RUNNING, flags=WORKER_COMPLETE | TLS_CLEARED).result()

    def test_response_exact_identity_owner_generation_and_clock(self):
        request = Frame(Command.SUBMIT, owner_pid=1, target_pid=2, owner_created=3, target_created=4,
                        request_id=5, generation=6, nonce=b"x" * 16, qpc_frequency=1000)
        reply = dataclasses.replace(request, status=Status.PREPARED, pointer_bits=32)
        reply.response_binding(request)
        for name in ("owner_pid", "target_pid", "owner_created", "target_created", "request_id", "generation", "qpc_frequency", "operation", "deadline_qpc"):
            with self.subTest(name=name), self.assertRaises(ProtocolError):
                dataclasses.replace(reply, **{name: getattr(reply, name) + 1}).response_binding(request)

    def test_completion_cannot_mix_main_worker_or_forge_thread_identity(self):
        request = Frame(Command.QUERY)
        reply = dataclasses.replace(request, status=Status.DONE, pointer_bits=64,
            flags=WORKER_COMPLETE | TLS_CLEARED, thread_id=2, main_thread_id=3, thread_created=4)
        reply.response_binding(request)
        for change in ({"thread_created": 0}, {"thread_id": 3},
                       {"flags": WORKER_COMPLETE | MAIN_COMPLETE | TLS_CLEARED},
                       {"flags": MAIN_COMPLETE | TLS_CLEARED}):
            with self.subTest(change=change), self.assertRaises(ProtocolError):
                dataclasses.replace(reply, **change).response_binding(request)


class FakeTransport:
    def __init__(self):
        self.calls, self.submissions = 0, []
        self.status = Status.PREPARED
        self.completed = False
        self.malformed = False

    def exchange(self, request, context, drop_ack=False):
        context.remaining()
        if self.malformed:
            raise ProtocolError("Foreign malformed reply")
        if request.command == Command.HELLO:
            return dataclasses.replace(request, status=Status.READY, qpc_frequency=1000000,
                                       clock_sample=1000, pointer_bits=64, main_thread_id=23)
        if request.command == Command.SUBMIT:
            self.submissions.append(request)
            if not request.flags & HOLD_START:
                self.status = Status.RUNNING
                self.calls += 1
            if drop_ack:
                return None
        if request.command == Command.CANCEL and self.status == Status.PREPARED:
            self.status, self.completed = Status.CANCELLED_BEFORE_START, True
        if request.command == Command.RELEASE and self.status == Status.RUNNING:
            self.status, self.completed = Status.DONE, True
        flags = (WORKER_COMPLETE | TLS_CLEARED) if self.completed else 0
        return dataclasses.replace(request, status=self.status, flags=flags, pointer_bits=64,
            main_thread_id=23, thread_id=42, thread_created=9876, call_count=self.calls,
            result_kind=1 if self.status == Status.DONE else 0,
            payload=struct.pack("<i", 19) if self.status == Status.DONE else b"")


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.journal = ReceiptJournal(Path(self.temporary.name) / "receipts", {"owner": [1, 2], "target": [3, 4]})
        self.transport = FakeTransport()
        self.clock = lambda: 1000
        self.broker = TypedBroker(Frame(Command.HELLO, owner_pid=1, owner_created=2,
            target_pid=3, target_created=4), self.transport, self.journal, self.clock, 1000000)
        self.broker.handshake(CallContext.seconds(1))

    def test_intent_is_durable_before_dispatch_and_id_never_reused_after_ack_loss(self):
        original = self.transport.exchange
        def checked(request, context, **kwargs):
            if request.command == Command.SUBMIT:
                records = [json.loads(p.read_bytes()) for p in self.journal.directory.glob("*.json")]
                intent = [x for x in records if x["kind"] == "intent"][-1]["value"]
                self.assertEqual(intent["request_hex"], request.encode().hex())
                self.assertEqual(intent["sha256"], hashlib.sha256(request.encode()).hexdigest())
            return original(request, context, **kwargs)
        self.transport.exchange = checked
        with self.assertRaises(BrokerUncertain):
            self.broker.submit(Operation.CDECL_ADD, (2, 3), CallContext.seconds(1), drop_ack=True)
        self.assertEqual(self.broker.next_id, 2)
        self.assertEqual(self.transport.calls, 1)
        with self.assertRaises(BrokerUncertain):
            self.broker.submit(Operation.CDECL_ADD, (2, 3), CallContext.seconds(1))
        self.assertEqual(len(self.transport.submissions), 1)

    def test_expired_or_cancelled_context_does_not_create_intent(self):
        cancel = threading.Event(); cancel.set()
        for context in (CallContext(time.monotonic() - 1), CallContext.seconds(1, cancel)):
            with self.assertRaises(BrokerCancelled):
                self.broker.submit(Operation.CDECL_ADD, (1, 2), context)
        self.assertEqual(self.transport.calls, 0)
        self.assertFalse(self.broker.requests)

    def test_direct_context_cannot_refresh_an_unbounded_future_deadline(self):
        with self.assertRaises(BrokerError):
            CallContext(time.monotonic() + 31)
        with self.assertRaises(BrokerError):
            CallContext(float("nan"))
        with self.assertRaises(BrokerError):
            CallContext(time.monotonic() + 1, object())

    def test_prestart_target_ack_proves_no_call_and_no_uncertainty(self):
        reply = self.broker.submit(Operation.CDECL_ADD, (1, 2), CallContext.seconds(1), hold_start=True)
        cancelled = self.broker.observe(reply.request_id, CallContext.seconds(1), Command.CANCEL)
        self.assertTrue(cancelled.completed)
        with self.assertRaises(BrokerCancelled):
            self.broker.wait(reply.request_id, CallContext.seconds(1))
        self.assertEqual(self.transport.calls, 0)
        self.assertFalse(self.broker.uncertain)

    def test_timeout_while_running_retains_uncertainty_after_late_result(self):
        reply = self.broker.submit(Operation.WAIT_ADD, (1, 2), CallContext.seconds(1))
        with self.assertRaises(BrokerUncertain):
            self.broker.wait(reply.request_id, CallContext(time.monotonic() - 1))
        self.broker.observe(reply.request_id, CallContext.seconds(1), Command.RELEASE)
        self.assertEqual(self.broker.observe(reply.request_id, CallContext.seconds(1)).result(), 19)
        self.assertTrue(self.broker.uncertain)
        with self.assertRaises(BrokerUncertain):
            self.broker.submit(Operation.CDECL_ADD, (2, 3), CallContext.seconds(1))

    def test_ack_lost_prepared_call_cannot_be_released(self):
        with self.assertRaises(BrokerUncertain):
            self.broker.submit(Operation.CDECL_ADD, (1, 2), CallContext.seconds(1), hold_start=True, drop_ack=True)
        with self.assertRaises(BrokerUncertain):
            self.broker.observe(1, CallContext.seconds(1), Command.RELEASE)
        self.assertEqual(self.transport.calls, 0)

    def test_only_one_outstanding_call_is_admitted_before_intent(self):
        self.broker.submit(Operation.CDECL_ADD, (1, 2), CallContext.seconds(1), hold_start=True)
        with self.assertRaises(BrokerError):
            self.broker.submit(Operation.CDECL_ADD, (3, 4), CallContext.seconds(1))
        self.assertEqual(self.broker.next_id, 2)
        self.assertEqual(len(self.transport.submissions), 1)

    def test_malformed_completion_blocks_new_work(self):
        reply = self.broker.submit(Operation.CDECL_ADD, (1, 2), CallContext.seconds(1))
        self.transport.malformed = True
        with self.assertRaises(BrokerUncertain):
            self.broker.wait(reply.request_id, CallContext.seconds(1))
        self.assertTrue(self.broker.uncertain)

    def test_durable_journal_change_blocks_submission_before_target_dispatch(self):
        path = next(self.journal.directory.glob("0000-*.json"))
        path.write_bytes(path.read_bytes().replace(b'"owner":[1,2]', b'"owner":[5,6]'))
        with self.assertRaises(BrokerUncertain):
            self.broker.submit(Operation.CDECL_ADD, (1, 2), CallContext.seconds(1))
        self.assertEqual(self.transport.calls, 0)

    def test_receipt_inventory_change_and_fresh_directory_are_guarded(self):
        with self.assertRaises(FileExistsError):
            ReceiptJournal(self.journal.directory, {})
        (self.journal.directory / "9999-foreign.json").write_text("{}")
        with self.assertRaises(BrokerUncertain):
            self.journal.verify()

    def test_closed_session_refuses_all_later_calls(self):
        self.broker.closed = True
        with self.assertRaises(BrokerError):
            self.broker.submit(Operation.CDECL_ADD, (1, 2), CallContext.seconds(1))


class NativeIoRetentionTests(unittest.TestCase):
    class Kernel:
        def __init__(self, waits, result_error):
            self.waits, self.result_error = iter(waits), result_error
            self.error, self.closed, self.cancelled = 0, [], 0
        def CreateEventW(self, *args): return 123
        def WriteFile(self, *args): self.error = 997; return 0
        def ReadFile(self, *args): self.error = 997; return 0
        def WaitForSingleObject(self, *args): return next(self.waits)
        def GetOverlappedResult(self, *args): self.error = self.result_error; return 0
        def CancelIoEx(self, *args): self.cancelled += 1; return 1
        def CloseHandle(self, value): self.closed.append(value); return 1

    def test_unknown_wait_and_incomplete_result_keep_exact_async_objects_alive(self):
        for waits, error in (([0xFFFFFFFF, 0xFFFFFFFF], 996), ([0, 0], 996), ([0, 0], 6)):
            with self.subTest(waits=waits, error=error):
                kernel = self.Kernel(waits, error)
                windows = type("Windows", (), {"k": kernel, "alive": lambda *args: True})()
                transport = _PipeTransport(windows, 1, (1, 2), bytes(16))
                with patch("ct2trainer.native.target_broker.client.ctypes.get_last_error", lambda: kernel.error, create=True):
                    with self.assertRaises(BrokerUncertain):
                        transport._io(99, Frame(Command.HELLO).encode(), read=False, context=CallContext.seconds(1))
                self.assertEqual(kernel.cancelled, 1)
                self.assertEqual(kernel.closed, [])
                self.assertEqual(len(transport.retained_io), 1)
                pipe, overlap, buffer = transport.retained_io[0]
                self.assertEqual(pipe, 99)
                self.assertEqual(overlap.hEvent, 123)
                self.assertEqual(buffer.raw[:FRAME_SIZE], Frame(Command.HELLO).encode())

    def test_cancelled_io_is_released_only_after_exact_terminal_completion(self):
        kernel = self.Kernel([0xFFFFFFFF, 0], 995)
        windows = type("Windows", (), {"k": kernel, "alive": lambda *args: True})()
        transport = _PipeTransport(windows, 1, (1, 2), bytes(16))
        with patch("ct2trainer.native.target_broker.client.ctypes.get_last_error", lambda: kernel.error, create=True):
            with self.assertRaises(BrokerUncertain):
                transport._io(99, Frame(Command.HELLO).encode(), read=False, context=CallContext.seconds(1))
        self.assertEqual(kernel.closed, [123])
        self.assertEqual(transport.retained_io, [])


class SetupFailureTests(unittest.TestCase):
    class RecordingInput(io.BytesIO):
        def __init__(self): super().__init__(); self.writes = []
        def write(self, raw): self.writes.append(raw); return super().write(raw)

    class FakeProcess:
        def __init__(self, stop_unknown=False):
            self.pid, self._handle, self.returncode = 7, 30, None
            self.stdin, self.stdout, self.stderr = SetupFailureTests.RecordingInput(), None, None
            self.stop_unknown, self.waits = stop_unknown, 0
        def poll(self): return self.returncode
        def wait(self, timeout):
            self.waits += 1
            if self.stop_unknown: raise subprocess.TimeoutExpired("own fixture", timeout)
            self.returncode = 0; return 0

    class FakeWindows:
        def __init__(self, mode):
            self.mode, self.owner, self.owner_handle, self.frequency = mode, (1, 100), 10, 1000000
            self.closed = []
            self.k = type("Kernel", (), {"CloseHandle": lambda k, h: self.closed.append(h) or 1,
                "WaitForSingleObject": lambda k, h, ms: 0})()
        def open_process(self, pid):
            if self.mode == "open": raise BrokerError("target OpenProcess failed")
            return 20
        def created(self, handle):
            if self.mode == "created": raise BrokerError("target GetProcessTimes failed")
            return 200
        def bits(self, handle, expected):
            if self.mode == "bits": raise BrokerError("target architecture refused")
        def qpc(self): return 1000

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        directory = Path(self.temporary.name)
        source_dir, bin_dir = directory / "source", directory / "x64"
        source_dir.mkdir(); bin_dir.mkdir()
        root = Path(__file__).resolve().parents[1]
        sources = []
        for relative in ("src/ct2trainer/native/target_broker/broker.c", "src/ct2trainer/native/target_broker/broker_abi.h",
                         "tests/windows/target_broker_fixture/broker_target.c", "tests/windows/target_broker_fixture/Invoke-TargetBrokerBuild.ps1"):
            path = root / relative
            raw = path.read_bytes()
            copy = source_dir / path.name; copy.write_bytes(raw)
            sources.append({"path": str(path), "snapshot": str(copy), "sha256": hashlib.sha256(raw).hexdigest()})
        components = []
        for name in ("NativeTargetBrokerFixture.exe", "CT2TrainerOwnedBroker.dll"):
            path = bin_dir / name
            raw = bytearray(128); raw[:2] = b"MZ"; raw[0x3C:0x40] = struct.pack("<I", 64)
            raw[64:68] = b"PE\0\0"; raw[68:70] = struct.pack("<H", 0x8664)
            path.write_bytes(raw)
            components.append({"path": str(path), "pe_machine": 0x8664, "sha256": hashlib.sha256(raw).hexdigest()})
        self.report = directory / "verification.json"
        self.report.write_text(json.dumps({"schema": "ct2trainer-owned-target-broker-build/v1", "status": "passed", "ce_inputs": [],
            "sources": sources, "results": [{"architecture": "x64", "executable": components[0]["path"],
                "dll": components[1]["path"], "components": components}]}))
        self.receipts = directory / "receipts"

    def exercise(self, mode, *, journal_failure=False, stop_unknown=False):
        windows, process = self.FakeWindows(mode), self.FakeProcess(stop_unknown)
        original_append = ReceiptJournal.append
        def append(journal, kind, value):
            if journal_failure and kind in {"process-created", "setup-failure", "target-exit"}:
                raise OSError("disk write failed after own child creation")
            return original_append(journal, kind, value)
        before = list(broker_client._RETAINED_FIXTURES)
        try:
            with patch.object(broker_client, "_Windows", return_value=windows), \
                 patch.object(broker_client.subprocess, "Popen", return_value=process), \
                 patch.object(broker_client.subprocess, "CREATE_NO_WINDOW", 0, create=True), \
                 patch.object(ReceiptJournal, "append", append):
                with self.assertRaises(BrokerError):
                    OwnedFixture(self.report, "x64", self.receipts)
            self.assertEqual(process.stdin.writes, [b"q\n"])
            self.assertEqual(process.waits, 1)
            self.assertNotIn(30, windows.closed, "Popen owns its CreateProcess handle; never double-close it")
            retained = [x for x in broker_client._RETAINED_FIXTURES if not any(x is old for old in before)]
            return windows, process, retained
        finally:
            # Fake handles have no kernel ownership. Explicit test-only release
            # prevents intentionally retained simulated faults affecting cleanup.
            for fixture in broker_client._RETAINED_FIXTURES:
                if not any(fixture is old for old in before):
                    for name in ("_stdout_sink", "_stderr_sink"):
                        stream = getattr(fixture, name, None)
                        if stream is not None: stream.close()
            broker_client._RETAINED_FIXTURES[:] = before

    def test_postlaunch_open_failure_exits_exact_child_and_uses_popen_handle_once(self):
        windows, process, retained = self.exercise("open")
        self.assertEqual(windows.closed, [10])
        self.assertEqual(retained, [])
        self.assertEqual(process.returncode, 0)
        self.assertTrue(list(self.receipts.glob("*-target-exit.json")))

    def test_postlaunch_bitness_failure_exits_before_any_broker_call(self):
        windows, process, retained = self.exercise("bits")
        self.assertEqual(windows.closed, [20, 10])
        self.assertEqual(retained, [])
        self.assertFalse([p for p in self.receipts.glob("*.json") if json.loads(p.read_bytes())["kind"] == "intent"])

    def test_creation_proof_failure_still_requests_exit_and_retains_uncertainty(self):
        windows, process, retained = self.exercise("created")
        self.assertEqual(process.returncode, 0)
        self.assertEqual(windows.closed, [])
        self.assertEqual(len(retained), 1)
        self.assertFalse(list(self.receipts.glob("*-target-exit.json")))

    def test_postlaunch_journal_failure_cannot_skip_owned_exit_request(self):
        windows, process, retained = self.exercise("journal", journal_failure=True)
        self.assertEqual(process.returncode, 0)
        self.assertEqual(len(retained), 1)
        self.assertEqual(windows.closed, [])

    def test_unknown_exit_retains_child_and_exact_receipt_resources(self):
        windows, process, retained = self.exercise("open", stop_unknown=True)
        self.assertIsNone(process.returncode)
        self.assertEqual(len(retained), 1)
        self.assertEqual(windows.closed, [])

    def test_foreign_or_changed_build_report_has_no_process_or_receipt_effect(self):
        report = json.loads(self.report.read_bytes())
        report["sources"][0]["sha256"] = "0" * 64
        self.report.write_text(json.dumps(report))
        with patch.object(broker_client.subprocess, "Popen") as spawn, patch.object(broker_client, "_Windows") as windows:
            with self.assertRaises(BrokerError):
                OwnedFixture(self.report, "x64", self.receipts)
            spawn.assert_not_called(); windows.assert_not_called()
        self.assertFalse(self.receipts.exists())


if __name__ == "__main__":
    unittest.main()
