"""Focused contract tests for the call-broker layer (AP-06).

These tests use injected scripted fake transports over the real
``TypedBroker`` foundation (``src/ct2trainer/native/target_broker``);
no real target process is needed. The C fixture
``tests/windows/target_broker_fixture/broker_target.c`` remains the ABI
reference. Every refusal is a named exception and every receipt state
transition is recorded on the receipt itself.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from ct2trainer.native.call_broker import (
    ALIGNMENT_MAX,
    ArgByRef,
    ArgPointer,
    ArgValue,
    ArgumentContractError,
    BufferReleaseBeforeAck,
    CallAlreadyStarted,
    CallBroker,
    CallBrokerClosed,
    CallBrokerError,
    CallBrokerUncertain,
    CallNotPrepared,
    CaveBadInput,
    CaveRetainedUntilTargetExit,
    EntryAddressChanged,
    EntryBadInput,
    EntryBitnessMismatch,
    EntryImageChanged,
    ReceiptStatus,
)
from ct2trainer.native.target_broker import (
    BrokerError,
    CallContext,
    ReceiptJournal,
    Status,
    TypedBroker,
)
from ct2trainer.native.target_broker.protocol import (
    Command,
    Frame,
    HOLD_START,
    Operation,
    TLS_CLEARED,
    WORKER_COMPLETE,
)
import struct

PE_SHA = "ab" * 32


class ScriptedTransport:
    """Scripted target behavior for the one-shot pipe mailbox."""

    def __init__(self, *, complete_after_queries=0, drop_ack=False,
                 malformed_on_query=False, refuse_submit=False,
                 raise_after_start=False, force_complete=False,
                 unknown_on_query=False, refuse_error=1460):
        self.submissions = []
        self.cancels = 0
        self.releases = 0
        self.calls = 0
        self.status = Status.PREPARED
        self.query_count = 0
        self.drop_ack = drop_ack
        self.malformed_on_query = malformed_on_query
        self.refuse_submit = refuse_submit
        self.raise_after_start = raise_after_start
        self.force_complete = force_complete
        self.unknown_on_query = unknown_on_query
        self.refuse_error = refuse_error
        self.complete_after_queries = complete_after_queries

    def _reply(self, request, status, completed=False, error=0, result_kind=0, payload=b""):
        flags = 0
        if completed:
            flags = WORKER_COMPLETE | TLS_CLEARED
        return dataclasses.replace(
            request, status=status, flags=flags, pointer_bits=64,
            main_thread_id=23, thread_id=42, thread_created=9876,
            call_count=self.calls, result_kind=result_kind,
            payload=payload, error=error)

    def exchange(self, request, context, drop_ack=False):
        context.remaining()
        if request.command == Command.HELLO:
            return dataclasses.replace(request, status=Status.READY,
                                       qpc_frequency=1000000, clock_sample=1000,
                                       pointer_bits=64, main_thread_id=23)
        if request.command == Command.SUBMIT:
            self.submissions.append(request)
            if self.refuse_submit:
                return self._reply(request, Status.REFUSED, completed=True,
                                   error=self.refuse_error)
            if not request.flags & HOLD_START:
                self.status = Status.RUNNING
                self.calls += 1
                if self.raise_after_start:
                    raise ProtocolErrorLike("pipe broke after the target started the call")
            if drop_ack or self.drop_ack:
                return None
            return self._reply(request, Status.PREPARED if request.flags & HOLD_START else self.status)
        if request.command == Command.CANCEL:
            self.cancels += 1
            if self.status == Status.PREPARED:
                self.status = Status.CANCELLED_BEFORE_START
                return self._reply(request, self.status, completed=True,
                                   error=1234 if True else 0)
            return self._reply(request, self.status)
        if request.command == Command.RELEASE:
            self.releases += 1
            if self.status == Status.PREPARED:
                self.status = Status.RUNNING
                self.calls += 1
            if self.status == Status.RUNNING and self.query_count >= self.complete_after_queries:
                self.status = Status.DONE
            return self._reply(request, self.status,
                               completed=self.status == Status.DONE,
                               result_kind=1 if self.status == Status.DONE else 0,
                               payload=struct.pack("<i", 5) if self.status == Status.DONE else b"")
        if request.command == Command.QUERY:
            self.query_count += 1
            if self.status == Status.RUNNING and self.force_complete:
                self.status = Status.DONE
            elif self.status == Status.RUNNING and self.complete_after_queries \
                    and self.query_count >= self.complete_after_queries:
                self.status = Status.DONE
            if self.unknown_on_query:
                return self._reply(request, Status.UNKNOWN)
            if self.malformed_on_query:
                raise ProtocolErrorLike("Foreign malformed reply")
            return self._reply(request, self.status,
                               completed=self.status in (Status.DONE, Status.CANCELLED_BEFORE_START),
                               result_kind=1 if self.status == Status.DONE else 0,
                               payload=struct.pack("<i", 5) if self.status == Status.DONE else b"")
        raise ProtocolErrorLike("Unknown command in scripted transport.")


class ProtocolErrorLike(ValueError):
    """Stands in for ProtocolError when a scripted transport faults."""


def make_session(tmpdir, **transport_kwargs):
    journal = ReceiptJournal(Path(tmpdir) / "receipts",
                             {"owner": [1, 2], "target": [3, 4]})
    transport = ScriptedTransport(**transport_kwargs)
    broker = TypedBroker(
        Frame(Command.HELLO, owner_pid=1, owner_created=2, target_pid=3,
              target_created=4, nonce=b"x" * 16),
        transport, journal, lambda: 1000, 1000000)
    broker.handshake(CallContext.seconds(1))
    from ct2trainer.native.call_broker import ImageIdentity
    image = ImageIdentity(pid=3, created_filetime=4, pe_sha256=PE_SHA)
    call_broker = CallBroker(broker, image)
    return call_broker, broker, transport, journal


def add_call(call_broker, **kwargs):
    call = call_broker.marshal(
        Operation.CDECL_ADD, (ArgValue(2), ArgValue(3)), entry_name=kwargs.pop("entry_name", "entry_a"))
    return call_broker.submit(call, CallContext.seconds(1), **kwargs)


class JournalHelpers:
    @staticmethod
    def kinds(journal):
        return [json.loads(p.read_bytes())["kind"] for p in sorted(journal.directory.glob("*.json"))]


class TestCallBrokerSessionAndEntries(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.cb, self.broker, self.transport, self.journal = make_session(self.temporary.name)

    def test_session_binds_exact_image_identity_and_journals(self):
        self.assertEqual(self.cb.bitness, 64)
        self.assertEqual(self.cb.image.pid, 3)
        self.assertEqual(self.cb.image.created_filetime, 4)
        kinds = JournalHelpers.kinds(self.journal)
        self.assertIn('call-session', kinds)
        session = next(json.loads(p.read_bytes()) for p in self.journal.directory.glob("*.json")
                       if json.loads(p.read_bytes())["kind"] == "call-session")
        self.assertEqual(session["value"]["image_pe_sha256"], PE_SHA)
        self.assertTrue(session["value"]["one_shot"])

    def test_bind_entry_idempotent_for_same_address(self):
        first = self.cb.bind_entry("entry_a", 0x401000)
        again = self.cb.bind_entry("entry_a", 0x401000)
        self.assertIs(first, again)
        self.assertEqual(len(self.cb.entries), 1)

    def test_bind_entry_address_change_refused_with_named_reason(self):
        self.cb.bind_entry("entry_a", 0x401000)
        with self.assertRaises(EntryAddressChanged) as caught:
            self.cb.bind_entry("entry_a", 0x402000)
        self.assertIn("0x401000", str(caught.exception))
        self.assertEqual(self.cb.entries["entry_a"].address, 0x401000)

    def test_bind_entry_bitness_mismatch_refused(self):
        with self.assertRaises(EntryBitnessMismatch):
            self.cb.bind_entry("entry_a", 0x401000, bitness=32)
        with self.assertRaises(EntryBitnessMismatch):
            self.cb.bind_entry("entry_a", 0x401000, bitness=16)

    def test_bind_entry_address_bounds_and_inputs(self):
        for bad in (0, -1, 2 ** 64, 2 ** 65):
            with self.subTest(address=bad), self.assertRaises(EntryBadInput):
                self.cb.bind_entry("entry_a", bad)
        self.cb.bind_entry("entry_a", 2 ** 32)
        for bad in ("", None, 7):
            with self.subTest(name=bad), self.assertRaises(EntryBadInput):
                self.cb.bind_entry(bad, 0x1000)
        with self.assertRaises(EntryBadInput):
            self.cb.bind_entry("entry_a", 1.5)

    def test_foreign_image_identity_refused_before_session(self):
        from ct2trainer.native.call_broker import ImageIdentity
        before = sum(1 for kind in JournalHelpers.kinds(self.journal) if kind == 'call-session')
        with self.assertRaises(EntryImageChanged):
            CallBroker(self.broker, ImageIdentity(pid=9, created_filetime=4, pe_sha256=PE_SHA))
        with self.assertRaises(EntryImageChanged):
            CallBroker(self.broker, ImageIdentity(pid=3, created_filetime=5, pe_sha256=PE_SHA))
        after = sum(1 for kind in JournalHelpers.kinds(self.journal) if kind == 'call-session')
        self.assertEqual(after, before, 'a refused image must not create a session receipt')

    def test_unhandshaken_broker_and_bad_pe_hash_refused(self):
        from ct2trainer.native.call_broker import ImageIdentity
        from ct2trainer.native.target_broker import ReceiptJournal, TypedBroker
        transport = ScriptedTransport()
        fresh = TypedBroker(
            Frame(Command.HELLO, owner_pid=1, owner_created=2, target_pid=3,
                  target_created=4, nonce=b"x" * 16),
            transport, ReceiptJournal(Path(self.temporary.name) / "fresh", {"owner": [1, 2]}),
            lambda: 1000, 1000000)
        image = ImageIdentity(pid=3, created_filetime=4, pe_sha256=PE_SHA)
        with self.assertRaises(CallBrokerError):
            CallBroker(fresh, image)
        fresh.handshake(CallContext.seconds(1))
        for bad_hash in ("ab" * 31, "AB" * 32, "ab" * 33, None):
            with self.subTest(h=bad_hash), self.assertRaises(EntryBadInput):
                CallBroker(fresh, ImageIdentity(pid=3, created_filetime=4, pe_sha256=bad_hash))

    def test_snapshot_reports_bound_entries_and_image(self):
        self.cb.bind_entry("entry_a", 0x401000)
        view = self.cb.snapshot()
        self.assertEqual(view["schema"], "ct2trainer-call-broker/v1")
        self.assertEqual(view["entries"]["entry_a"], {"address": 0x401000, "bitness": 64})
        self.assertEqual(view["image"]["pe_sha256"], PE_SHA)
        self.assertFalse(view["closed"])


class TestMarshalContract(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.cb, self.broker, self.transport, self.journal = make_session(self.temporary.name)
        self.cb.bind_entry("entry_a", 0x401000)

    def test_value_arguments_encode_the_fixed_wire_contract(self):
        call = self.cb.marshal(Operation.CDECL_ADD, (ArgValue(2), ArgValue(3)),
                               entry_name="entry_a")
        self.assertEqual(call.payload, struct.pack("<ii", 2, 3))
        self.assertEqual(call.wire_arguments, (2, 3))
        self.assertEqual(call.byref_specs, ())
        self.assertEqual(call.pointer_specs, ())

    def test_byref_carries_address_and_retains_buffer(self):
        call = self.cb.marshal(Operation.CDECL_ADD,
                               (ArgByRef(0x10000, 8, 8), ArgValue(3)))
        self.assertEqual(call.wire_arguments, (0x10000, 3))
        self.assertEqual(call.byref_specs, ((0x10000, 8, 8),))
        self.assertEqual(call.payload, struct.pack("<ii", 0x10000, 3))

    def test_byref_unaligned_address_refused(self):
        with self.assertRaises(ArgumentContractError):
            self.cb.marshal(Operation.CDECL_ADD,
                            (ArgByRef(0x10004, 8, 8), ArgValue(3)))

    def test_byref_size_bounds(self):
        with self.assertRaises(ArgumentContractError):
            self.cb.marshal(Operation.WIDE_RETURN,
                            (ArgByRef(0x10000, 513, 8), ArgValue(1)))
        with self.assertRaises(ArgumentContractError):
            self.cb.marshal(Operation.WIDE_RETURN,
                            (ArgByRef(0x10000, 0, 8), ArgValue(1)))
        call = self.cb.marshal(Operation.WIDE_RETURN,
                               (ArgByRef(0x10000, 512, 8), ArgValue(1)))
        self.assertEqual(call.byref_specs, ((0x10000, 512, 8),))

    def test_byref_alignment_must_be_power_of_two_up_to_limit(self):
        for alignment in (0, 3, 24, ALIGNMENT_MAX + 1):
            with self.subTest(alignment=alignment), self.assertRaises(ArgumentContractError):
                self.cb.marshal(Operation.CDECL_ADD,
                                (ArgByRef(0x10000, 8, alignment), ArgValue(3)))

    def test_pointer_argument_in_word_slot(self):
        call = self.cb.marshal(Operation.WIDE_RETURN,
                               (ArgPointer(0x7FF00000), ArgPointer(0x1000)))
        self.assertEqual(call.pointer_specs, ((0x7FF00000,), (0x1000,)))
        self.assertEqual(call.wire_arguments, (0x7FF00000, 0x1000))

    def test_byref_refused_outside_word_slots(self):
        with self.assertRaises(ArgumentContractError):
            self.cb.marshal(Operation.MIXED_FIVE,
                            (ArgValue(1), ArgByRef(0x1000, 8, 8), ArgValue(3),
                             ArgValue(4.0), ArgValue(5)))
        with self.assertRaises(ArgumentContractError):
            self.cb.marshal(Operation.UTF16_ECHO, (ArgPointer(0x1000),))
        with self.assertRaises(ArgumentContractError):
            self.cb.marshal(Operation.MAIN_BOOLEAN, (ArgByRef(0x1000, 4, 4),))

    def test_address_escapes_address_space_refused(self):
        with self.assertRaises(ArgumentContractError):
            self.cb.marshal(Operation.CDECL_ADD,
                            (ArgByRef(1 << 64, 8, 8), ArgValue(3)))
        with self.assertRaises(ArgumentContractError):
            self.cb.marshal(Operation.CDECL_ADD,
                            (ArgPointer(0), ArgValue(3)))

    def test_wire_slot_overflow_is_visible_not_clamped(self):
        # A 64-bit address that does not fit the int32 wire slot is refused,
        # never truncated or clamped.
        with self.assertRaises(ArgumentContractError):
            self.cb.marshal(Operation.CDECL_ADD,
                            (ArgValue(2 ** 31), ArgValue(3)))

    def test_arity_and_bad_operation_refused(self):
        with self.assertRaises(ArgumentContractError):
            self.cb.marshal(Operation.CDECL_ADD, (ArgValue(2),))
        with self.assertRaises(ArgumentContractError):
            self.cb.marshal(99, ())
        with self.assertRaises(ArgumentContractError):
            self.cb.marshal(Operation.CDECL_ADD, [2, 3])
        with self.assertRaises(EntryBadInput):
            self.cb.marshal(Operation.CDECL_ADD, (ArgValue(2), ArgValue(3)),
                            entry_name="unbound_entry")


class TestCallOneShotLifecycle(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.cb, self.broker, self.transport, self.journal = make_session(
            self.temporary.name, complete_after_queries=1)
        self.cb.bind_entry("entry_a", 0x401000)

    def test_durable_intent_is_recorded_before_dispatch(self):
        original = self.transport.exchange
        observed = {}

        def checked(request, context, drop_ack=False):
            if request.command == Command.SUBMIT:
                records = [json.loads(p.read_bytes()) for p in self.journal.directory.glob("*.json")]
                intent = [r for r in records if r["kind"] == "call-intent"][-1]["value"]
                observed.update(intent)
            return original(request, context, drop_ack=drop_ack)

        self.transport.exchange = checked
        receipt = add_call(self.cb)
        self.assertEqual(receipt.request_id, 1)
        self.assertEqual(observed["request_id"], 1)
        self.assertTrue(observed["one_shot"])
        self.assertEqual(observed["payload_sha256"],
                         hashlib.sha256(struct.pack("<ii", 2, 3)).hexdigest())

    def test_successful_call_yields_typed_result_and_receipt(self):
        receipt = add_call(self.cb)
        self.assertEqual(receipt.status, ReceiptStatus.RUNNING)
        # Deadline is the QPC model: fixed sample 1000 plus ~1s at 1 MHz,
        # minus the (bounded) elapsed controller time between sampling and submit.
        self.assertGreater(receipt.deadline_qpc, 1000 + 900000)
        self.assertLessEqual(receipt.deadline_qpc, 1000 + 1000000)
        done = self.cb.wait(receipt, CallContext.seconds(2))
        self.assertIs(done, receipt)
        self.assertEqual(receipt.status, ReceiptStatus.DONE)
        self.assertEqual(receipt.result, 5)
        self.assertTrue(receipt.terminal)
        self.assertEqual(self.transport.calls, 1)
        self.assertIn('call-receipt', JournalHelpers.kinds(self.journal))
        self.assertFalse(self.broker.uncertain)

    def test_one_outstanding_call_at_a_time(self):
        first = add_call(self.cb, hold_start=True)
        self.assertEqual(first.status, ReceiptStatus.PENDING)
        with self.assertRaises(CallBrokerError):
            add_call(self.cb)
        self.assertEqual(len(self.transport.submissions), 1)
        self.assertEqual(self.broker.next_id, 2)

    def test_cancel_before_start_is_the_only_safe_cancellation(self):
        receipt = add_call(self.cb, hold_start=True)
        cancelled = self.cb.cancel_before_start(receipt, CallContext.seconds(1))
        self.assertEqual(cancelled.status, ReceiptStatus.CANCELLED)
        self.assertEqual(self.transport.calls, 0)
        done = self.cb.wait(receipt, CallContext.seconds(1))
        self.assertIs(done, receipt)
        self.assertEqual(receipt.status, ReceiptStatus.CANCELLED)
        self.assertFalse(self.broker.uncertain)
        self.assertTrue(receipt.terminal)

    def test_cancel_after_start_refused_and_call_still_runs_to_completion(self):
        receipt = add_call(self.cb)
        self.assertEqual(receipt.status, ReceiptStatus.RUNNING)
        with self.assertRaises(CallAlreadyStarted):
            self.cb.cancel_before_start(receipt, CallContext.seconds(1))
        self.assertEqual(receipt.status, ReceiptStatus.RUNNING)
        self.cb.wait(receipt, CallContext.seconds(2))
        self.assertEqual(receipt.status, ReceiptStatus.DONE)
        self.assertEqual(receipt.result, 5)
        self.assertEqual(self.transport.calls, 1)
        self.assertEqual(self.transport.cancels, 0)

    def test_cancel_on_terminal_receipt_refused_with_named_reason(self):
        receipt = add_call(self.cb)
        self.cb.wait(receipt, CallContext.seconds(2))
        with self.assertRaises(CallNotPrepared):
            self.cb.cancel_before_start(receipt, CallContext.seconds(1))
        with self.assertRaises(CallNotPrepared):
            self.cb.cancel_before_start(receipt, None)

    def test_wait_timeout_yields_hung_not_cancelled_and_stays_observable(self):
        self.transport.complete_after_queries = 10 ** 9
        receipt = add_call(self.cb)
        self.assertEqual(receipt.status, ReceiptStatus.RUNNING)
        hung = self.cb.wait(receipt, CallContext.seconds(0.05))
        self.assertEqual(hung.status, ReceiptStatus.HUNG)
        self.assertFalse(hung.terminal)
        self.assertEqual(receipt.transitions[-1][1],
                         'caller deadline expired while the target call may still run; not cancelled')
        self.assertEqual(self.transport.calls, 1)
        self.assertTrue(self.broker.uncertain, 'session is uncertain while the call may run')
        # No force-stop: the call may still complete and be observed later.
        self.transport.force_complete = True
        done = self.cb.wait(receipt, CallContext.seconds(2))
        self.assertEqual(done.status, ReceiptStatus.DONE)
        self.assertEqual(done.result, 5)

    def test_lost_ack_is_terminal_uncertain_and_blocks_retry(self):
        self.transport.drop_ack = True
        with self.assertRaises(CallBrokerUncertain):
            add_call(self.cb)
        receipt = self.cb.receipts[1]
        self.assertEqual(receipt.status, ReceiptStatus.UNCERTAIN)
        self.assertTrue(receipt.terminal)
        self.assertFalse(receipt.describe()["retry_allowed"])
        self.assertTrue(self.broker.uncertain)
        with self.assertRaises(CallBrokerUncertain):
            add_call(self.cb)
        self.assertEqual(len(self.transport.submissions), 1)
        self.assertNotIn('call-submitted', JournalHelpers.kinds(self.journal))
        kinds = JournalHelpers.kinds(self.journal)
        self.assertIn('call-uncertain', kinds)
        self.assertIsNone(getattr(self.cb, 'retry', None))
        self.assertIsNone(getattr(self.cb, 'replay', None))

    def test_dispatch_exception_after_start_is_uncertain_without_replay(self):
        self.transport.raise_after_start = True
        with self.assertRaises(CallBrokerUncertain):
            add_call(self.cb)
        receipt = self.cb.receipts[1]
        self.assertEqual(receipt.status, ReceiptStatus.UNCERTAIN)
        self.assertEqual(self.transport.calls, 1, 'partial effect: the target did start')
        with self.assertRaises(CallBrokerUncertain):
            add_call(self.cb)
        self.assertEqual(len(self.transport.submissions), 1)

    def test_target_refusal_is_a_visible_terminal_receipt_with_error(self):
        self.transport.refuse_submit = True
        receipt = add_call(self.cb)
        self.assertEqual(receipt.status, ReceiptStatus.REFUSED)
        self.assertEqual(receipt.error, 1460)
        self.assertTrue(receipt.terminal)
        self.assertIsNone(receipt.result)
        self.assertEqual(self.transport.calls, 0)
        # A proven no-effect refusal is observable without a wait round trip.
        self.assertIs(self.cb.wait(receipt, CallContext.seconds(1)), receipt)

    def test_buffers_are_retained_until_the_terminal_ack(self):
        call = self.cb.marshal(Operation.CDECL_ADD,
                               (ArgByRef(0x10000, 8, 8), ArgValue(3)),
                               entry_name="entry_a")
        receipt = self.cb.submit(call, CallContext.seconds(1), hold_start=True)
        self.assertEqual(receipt.buffers, [[0x10000, 8, 8]])
        with self.assertRaises(BufferReleaseBeforeAck):
            self.cb.release_buffers(receipt)
        self.cb.cancel_before_start(receipt, CallContext.seconds(1))
        self.assertEqual(self.cb.release_buffers(receipt), 1)
        self.assertEqual(receipt.buffers, [])
        self.assertIn('call-buffers-released', JournalHelpers.kinds(self.journal))

    def test_unknown_target_state_is_terminal_uncertain(self):
        self.transport.complete_after_queries = 0
        self.transport.unknown_on_query = True
        call = self.cb.marshal(Operation.CDECL_ADD, (ArgValue(2), ArgValue(3)),
                               entry_name="entry_a")
        receipt = self.cb.submit(call, CallContext.seconds(1))
        with self.assertRaises(CallBrokerUncertain):
            self.cb.wait(receipt, CallContext.seconds(2))
        self.assertEqual(receipt.status, ReceiptStatus.UNCERTAIN)
        self.assertTrue(receipt.terminal)
        self.assertTrue(self.broker.uncertain)


class TestCallCaveAndSessionEnd(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.cb, self.broker, self.transport, self.journal = make_session(
            self.temporary.name, complete_after_queries=1)
        self.cb.bind_entry("entry_a", 0x401000)

    def test_cave_is_retained_until_target_exit(self):
        binding = self.cb.register_cave('cave_a', 0x2000, 256, 16)
        self.assertEqual((binding.address, binding.size, binding.alignment), (0x2000, 256, 16))
        self.assertFalse(binding.retired_with_target)
        with self.assertRaises(CaveRetainedUntilTargetExit):
            self.cb.release_cave('cave_a')
        self.assertIn('cave_a', self.cb.caves, 'controller has no free/pool API')
        self.assertNotIn('call-cave-released', JournalHelpers.kinds(self.journal))

    def test_cave_input_validation(self):
        self.cb.register_cave('cave_a', 0x2000, 256, 16)
        with self.assertRaises(CaveBadInput):
            self.cb.register_cave('cave_a', 0x2000, 256, 16)
        with self.assertRaises(CaveBadInput):
            self.cb.register_cave('cave_b', 0x2000, 4097, 16)
        with self.assertRaises(CaveBadInput):
            self.cb.register_cave('cave_b', 0x2000, 0, 16)
        with self.assertRaises(CaveBadInput):
            self.cb.register_cave('cave_b', 0x2008, 256, 16)
        with self.assertRaises(CaveBadInput):
            self.cb.register_cave('cave_b', 0x2000, 256, 12)
        with self.assertRaises(CallBrokerError):
            self.cb.release_cave('does_not_exist')

    def test_close_retires_caves_and_blocks_new_work(self):
        self.cb.register_cave('cave_a', 0x2000, 256, 16)
        receipt = add_call(self.cb, hold_start=True)
        self.cb.close()
        self.assertTrue(self.cb.caves['cave_a'].retired_with_target)
        self.assertTrue(self.broker.closed)
        with self.assertRaises(CallBrokerClosed):
            add_call(self.cb)
        with self.assertRaises(CallBrokerClosed):
            self.cb.bind_entry('entry_b', 0x402000)
        with self.assertRaises(CallBrokerClosed):
            self.cb.register_cave('cave_b', 0x3000, 64, 8)
        # The open receipt stays durable on the session; it is not dropped or
        # marked cancelled just because the controller closed.
        self.assertEqual(receipt.status, ReceiptStatus.PENDING)
        self.assertFalse(receipt.terminal)
        self.assertIn('call-close', JournalHelpers.kinds(self.journal))

    def test_receipt_describe_and_journal_chain_intact(self):
        call = self.cb.marshal(Operation.CDECL_ADD,
                               (ArgByRef(0x10000, 8, 8), ArgValue(3)),
                               entry_name='entry_a')
        receipt = self.cb.submit(call, CallContext.seconds(1))
        self.cb.wait(receipt, CallContext.seconds(2))
        self.assertEqual(self.cb.release_buffers(receipt), 1)
        view = receipt.describe()
        self.assertEqual(view['schema'], 'ct2trainer-call-broker/v1')
        self.assertEqual(view['status_name'], 'DONE')
        self.assertEqual(view['result'], 5)
        self.assertTrue(view['terminal'])
        self.assertFalse(view['retry_allowed'])
        self.assertEqual(view['retained_buffers'], 0)
        self.journal.verify()
