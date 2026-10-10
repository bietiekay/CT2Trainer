"""Typed one-shot remote call operations on top of the owned target-broker foundation.

Built directly on ``src/ct2trainer/native/target_broker`` (``TypedBroker``,
``Frame``, ``ReceiptJournal``, ``CallContext``, ``encode_arguments``); the C
fixture ``tests/windows/target_broker_fixture/broker_target.c`` remains the
ABI reference. This module adds the trainer-level call contract on top of the
foundation's one-shot pipe mailbox; it does not introduce a new wire ABI.

Contract (explicit, named refusals, no silent recovery):

- Entry binding: an entry name binds one target address, one bitness and one
  exact image identity (PID + FILETIME creation + PE SHA-256). Re-binding the
  same name to another address is refused as ``EntryAddressChanged``; a
  different image or bitness is ``EntryImageChanged`` /
  ``EntryBitnessMismatch``. A bound entry is immutable for the session.
- Argument marshal: value / byref / pointer argument specs with size and
  alignment limits. Byref/pointer addresses must lie in the target address
  space, be aligned to a power-of-two limit, and fit the chosen wire slot;
  the payload never exceeds the foundation's bounded mailbox.
- No buffer before ACK: byref buffers are retained by the controller until
  the terminal ACK of the exact one-shot call; releasing them earlier is
  refused as ``BufferReleaseBeforeAck``.
- Completion receipts: one-shot IDs from the foundation ledger; deadlines use
  the injected QPC model (``CallContext`` + target frequency). Cancellation
  before start is the only safe cancellation (target-side CAS). A started
  call is never cancelled and never force-terminated: a caller deadline while
  the call still runs yields a ``HUNG`` receipt, not a cancellation.
- Lost ACK or exception after a possible partial effect is terminal
  ``UNCERTAIN``: no retry, no save, no replay, no re-apply. The foundation's
  durable one-shot journal blocks further submissions.
- Cave/worker lifetime: registered cave bookkeeping is retained until target
  exit while receipts are open; the controller has no free/pool API
  (``CaveRetainedUntilTargetExit``). After session close the caves are only
  marked ``retired_with_target``.
"""
from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from enum import IntEnum

from .target_broker import (BrokerCancelled, CallContext, TypedBroker)
from .target_broker.protocol import (Command, Operation, ProtocolError, Status,
                                     PAYLOAD_LIMIT, encode_arguments)

SCHEMA = 'ct2trainer-call-broker/v1'
CAVE_SIZE_MAX = 4096
ALIGNMENT_MAX = 16
_HEX64 = re.compile(r'^[0-9a-f]{64}$')


class CallBrokerError(RuntimeError):
    """Named refusal of the call-broker contract layer."""


class EntryBadInput(CallBrokerError):
    pass


class EntryAddressChanged(CallBrokerError):
    pass


class EntryImageChanged(CallBrokerError):
    pass


class EntryBitnessMismatch(CallBrokerError):
    pass


class ArgumentContractError(CallBrokerError):
    pass


class BufferReleaseBeforeAck(CallBrokerError):
    pass


class CallAlreadyStarted(CallBrokerError):
    pass


class CallNotPrepared(CallBrokerError):
    pass


class CaveBadInput(CallBrokerError):
    pass


class CaveRetainedUntilTargetExit(CallBrokerError):
    pass


class CallBrokerUncertain(CallBrokerError):
    pass


class CallBrokerClosed(CallBrokerError):
    pass


class ReceiptStatus(IntEnum):
    PENDING = 0
    RUNNING = 1
    DONE = 2
    CANCELLED = 3
    REFUSED = 4
    HUNG = 5
    UNCERTAIN = 6


#: Proven terminal outcomes; only these release their retained buffers.
RELEASABLE_STATES = {ReceiptStatus.DONE, ReceiptStatus.CANCELLED,
                     ReceiptStatus.REFUSED}
#: Receipts that can no longer transition to a proven outcome.
FINAL_STATES = RELEASABLE_STATES | {ReceiptStatus.UNCERTAIN}


@dataclass(frozen=True)
class ImageIdentity:
    """Exact target image identity: PID + FILETIME creation + PE SHA-256."""
    pid: int
    created_filetime: int
    pe_sha256: str


@dataclass(frozen=True)
class EntryBinding:
    """Immutable per-session binding of an entry name to one address."""
    name: str
    address: int
    bitness: int
    image: ImageIdentity


@dataclass(frozen=True)
class ArgValue:
    """A literal value inlined into the bounded wire payload."""
    value: object


@dataclass(frozen=True)
class ArgByRef:
    """A target-side buffer: the wire carries the address, the buffer
    bookkeeping stays in the controller and is retained until the terminal
    ACK of the exact one-shot call."""
    address: int
    size: int
    alignment: int = 8


@dataclass(frozen=True)
class ArgPointer:
    """A bare target address without a size contract."""
    address: int


@dataclass(frozen=True)
class CaveBinding:
    """Controller-side bookkeeping for a target cave; never freed by the
    controller, only retired when the target process exits."""
    name: str
    address: int
    size: int
    alignment: int
    retired_with_target: bool = False


@dataclass(frozen=True)
class MarshaledCall:
    """Validated, wire-ready call: fixed operation, wire arguments, payload."""
    operation: Operation
    entry_name: str
    wire_arguments: tuple
    payload: bytes
    byref_specs: tuple
    pointer_specs: tuple


@dataclass
class CallReceipt:
    """Durable completion receipt for one one-shot call."""
    request_id: int
    operation: Operation
    entry_name: str
    status: ReceiptStatus
    deadline_qpc: int = 0
    result: object = None
    error: int = 0
    buffers: list = field(default_factory=list)
    transitions: list = field(default_factory=list)

    def __post_init__(self):
        self.transitions.append((int(self.status), 'submitted'))

    @property
    def terminal(self) -> bool:
        return self.status in FINAL_STATES

    def describe(self) -> dict:
        return {
            'schema': SCHEMA,
            'request_id': self.request_id,
            'entry': self.entry_name,
            'operation': int(self.operation),
            'status': int(self.status),
            'status_name': self.status.name,
            'terminal': self.terminal,
            'result': self.result,
            'error': self.error,
            'deadline_qpc': self.deadline_qpc,
            'retained_buffers': len(self.buffers),
            'retry_allowed': False,
        }


_ARITY = {
    Operation.CDECL_ADD: 2, Operation.STDCALL_ADD: 2, Operation.WAIT_ADD: 2,
    Operation.WIDE_RETURN: 2, Operation.MIXED_FIVE: 5,
    Operation.UTF16_ECHO: 1, Operation.MAIN_BOOLEAN: 1,
    Operation.MAIN_BOOLEAN_ON_WORKER: 1,
}

#: Operations whose wire slots are plain integer words and therefore accept
#: byref/pointer arguments (their target address rides in the word slot).
_WORD_OPERATIONS = {Operation.CDECL_ADD, Operation.STDCALL_ADD,
                    Operation.WAIT_ADD, Operation.WIDE_RETURN}


class CallBroker:
    """Trainer-level one-shot call contract over the target-broker foundation."""

    def __init__(self, broker, image):
        if not isinstance(broker, TypedBroker):
            raise CallBrokerError('Call broker requires the owned TypedBroker session.')
        if broker.clock_offset is None:
            raise CallBrokerError('Broker session is not handshaken.')
        if broker.pointer_bits not in (32, 64):
            raise CallBrokerError('Broker lacks its target bitness proof.')
        if not isinstance(image, ImageIdentity):
            raise CallBrokerError('Image identity must be an ImageIdentity binding.')
        if type(image.pid) is not int or image.pid <= 0:
            raise EntryBadInput('Image PID must be a positive integer.')
        if type(image.created_filetime) is not int or image.created_filetime <= 0:
            raise EntryBadInput('Image FILETIME must be a positive integer.')
        if type(image.pe_sha256) is not str or not _HEX64.match(image.pe_sha256):
            raise EntryBadInput('Image PE hash must be exactly 64 lowercase hex characters.')
        if image.pid != broker.binding.target_pid:
            raise EntryImageChanged('Bound image PID differs from the broker target identity.')
        if image.created_filetime != broker.binding.target_created:
            raise EntryImageChanged('Bound image FILETIME differs from the broker target identity.')
        self._broker = broker
        self.image = image
        self.bitness = broker.pointer_bits
        self.entries = {}
        self.caves = {}
        self.receipts = {}
        self._closed = False
        broker.journal.append('call-session', {
            'image_pid': image.pid,
            'image_created_filetime': image.created_filetime,
            'image_pe_sha256': image.pe_sha256,
            'bitness': self.bitness,
            'main_thread_id': broker.main_tid,
            'one_shot': True,
        })

    def _guard_open(self):
        if self._closed:
            raise CallBrokerClosed('Call broker session is closed.')

    def _note(self, kind, value):
        self._broker.journal.append(kind, value)

    def _require_receipt(self, receipt):
        if not isinstance(receipt, CallReceipt) or receipt not in self.receipts.values():
            raise CallBrokerError('Foreign call receipt.')
        return receipt

    def _finalize(self, receipt, status, note, *, result=None, error=0):
        if result is not None:
            receipt.result = result
        receipt.error = error
        receipt.status = status
        receipt.transitions.append((int(status), note))
        self._note('call-receipt', {'request_id': receipt.request_id,
                                    'status': int(status), 'error': error})
        return receipt

    def bind_entry(self, name, address, bitness=None):
        """Bind an entry name to one exact address/bitness/image; immutable."""
        self._guard_open()
        if type(name) is not str or not name:
            raise EntryBadInput('Entry name must be a non-empty string.')
        if type(address) is not int or address <= 0:
            raise EntryBadInput('Entry address must be a positive integer.')
        if bitness is None:
            bitness = self.bitness
        if bitness not in (32, 64):
            raise EntryBitnessMismatch('Explicit bitness must be 32 or 64.')
        if bitness != self.bitness:
            raise EntryBitnessMismatch(
                f'Entry bitness {bitness} differs from the bound target ABI {self.bitness}.')
        if address >= 1 << bitness:
            raise EntryBadInput('Entry address escapes the target address space.')
        existing = self.entries.get(name)
        if existing is not None:
            if existing.address != address:
                raise EntryAddressChanged(
                    f'Entry {name!r} is bound to {existing.address:#x}; '
                    f'rebinding to {address:#x} is refused.')
            return existing
        binding = EntryBinding(name, address, bitness, self.image)
        self.entries[name] = binding
        self._broker.journal.append('call-entry', {
            'name': name, 'address': address, 'bitness': bitness,
            'image_pid': self.image.pid,
            'image_created_filetime': self.image.created_filetime,
            'image_pe_sha256': self.image.pe_sha256,
            'immutable': True,
        })
        return binding

    def marshal(self, operation, args, *, entry_name=''):
        """Validate value/byref/pointer arguments against the wire contract."""
        self._guard_open()
        try:
            operation = Operation(operation)
        except ValueError as exc:
            raise ArgumentContractError('Unsupported typed operation.') from exc
        arity = _ARITY.get(operation, 0)
        if type(args) is not tuple and type(args) is not list:
            raise ArgumentContractError('Arguments must be a tuple of typed specs.')
        args = tuple(args)
        if len(args) != arity:
            raise ArgumentContractError(
                f'{operation.name} requires exactly {arity} arguments.')
        if entry_name and entry_name not in self.entries:
            raise EntryBadInput('Marshaled call names an unbound entry.')
        wire = []
        byref_specs = []
        pointer_specs = []
        for index, spec in enumerate(args):
            if isinstance(spec, ArgByRef):
                self._check_word_slot(operation, index)
                self._check_address(spec.address, 'byref address')
                if type(spec.size) is not int or not 1 <= spec.size <= PAYLOAD_LIMIT:
                    raise ArgumentContractError(
                        'Byref size must be a positive count within the mailbox budget.')
                self._check_alignment(spec.alignment, 'byref alignment', spec.address)
                byref_specs.append((spec.address, spec.size, spec.alignment))
                wire.append(spec.address)
            elif isinstance(spec, ArgPointer):
                self._check_word_slot(operation, index)
                self._check_address(spec.address, 'pointer address')
                pointer_specs.append((spec.address,))
                wire.append(spec.address)
            elif isinstance(spec, ArgValue):
                wire.append(spec.value)
            else:
                raise ArgumentContractError(
                    'Arguments must be ArgValue, ArgByRef or ArgPointer specs.')
        try:
            payload = encode_arguments(operation, tuple(wire))
        except ProtocolError as exc:
            raise ArgumentContractError(
                f'Typed wire contract refused the arguments: {exc}') from exc
        return MarshaledCall(operation, entry_name, tuple(wire), payload,
                             tuple(byref_specs), tuple(pointer_specs))

    def _check_word_slot(self, operation, index):
        if operation not in _WORD_OPERATIONS:
            raise ArgumentContractError(
                f'{operation.name} carries no byref/pointer slots; '
                'only literal values are admitted.')

    def _check_address(self, address, what):
        if type(address) is not int or address <= 0:
            raise ArgumentContractError(f'{what.capitalize()} must be a positive integer.')
        if address >= 1 << self.bitness:
            raise ArgumentContractError(
                f'{what.capitalize()} escapes the target address space.')

    def _check_alignment(self, alignment, what, address):
        if (type(alignment) is not int or alignment < 1 or alignment > ALIGNMENT_MAX
                or alignment & (alignment - 1)):
            raise ArgumentContractError(
                f'{what.capitalize()} must be a power of two up to {ALIGNMENT_MAX}.')
        if address % alignment:
            raise ArgumentContractError(
                f'{what.capitalize()} does not divide the address.')

    def submit(self, call, context, *, hold_start=False, drop_ack=False):
        """Submit one one-shot call; returns the durable completion receipt."""
        self._guard_open()
        if not isinstance(call, MarshaledCall):
            raise CallBrokerError('Submit requires a marshaled call.')
        if not isinstance(context, CallContext):
            raise CallBrokerError('Submit requires an explicit CallContext deadline.')
        if self._broker.uncertain:
            raise CallBrokerUncertain(
                'The session is uncertain after a lost or unverified one-shot; '
                'no retry, replay or re-apply is permitted.')
        if any(not self._broker.observations.get(item)
               or not self._broker.observations[item].completed
               for item in self._broker.requests):
            raise CallBrokerError(
                'The bounded broker accepts one outstanding invocation at a time.')
        receipt = CallReceipt(
            self._broker.next_id, call.operation, call.entry_name,
            ReceiptStatus.PENDING if hold_start else ReceiptStatus.RUNNING,
            buffers=[list(spec) for spec in call.byref_specs])
        self.receipts[receipt.request_id] = receipt
        self._note('call-intent', {
            'request_id': receipt.request_id,
            'entry': call.entry_name,
            'operation': int(call.operation),
            'payload_sha256': hashlib.sha256(call.payload).hexdigest(),
            'byref': [list(spec) for spec in call.byref_specs],
            'pointer': [list(spec) for spec in call.pointer_specs],
            'hold_start': hold_start,
            'one_shot': True,
        })
        try:
            reply = self._broker.submit(call.operation, call.wire_arguments, context,
                                        hold_start=hold_start, drop_ack=drop_ack)
        except Exception as exc:
            receipt.status = ReceiptStatus.UNCERTAIN
            receipt.transitions.append((int(ReceiptStatus.UNCERTAIN),
                                        f'dispatch unverified: {str(exc)[:200]}'))
            self._note('call-uncertain', {'request_id': receipt.request_id,
                                          'reason': str(exc)[:512]})
            raise CallBrokerUncertain(
                'One-shot dispatch has no verified acknowledgement; no retry, '
                'save, replay or re-apply is permitted.') from exc
        receipt.deadline_qpc = reply.deadline_qpc
        if reply.completed:
            # The target finished before the acknowledgement came back; the
            # receipt is terminal from the start and no wait is needed.
            if reply.status == Status.DONE:
                self._finalize(receipt, ReceiptStatus.DONE,
                               'terminal completion at acknowledgement',
                               result=reply.result(), error=reply.error)
            elif reply.status == Status.CANCELLED_BEFORE_START:
                self._finalize(receipt, ReceiptStatus.CANCELLED,
                               'cancelled before start', error=reply.error)
            else:
                self._finalize(receipt, ReceiptStatus.REFUSED,
                               'target refused the call', error=reply.error)
        else:
            receipt.status = (ReceiptStatus.PENDING if reply.status == Status.PREPARED
                              else ReceiptStatus.RUNNING)
            receipt.transitions.append((int(receipt.status), 'acknowledged'))
            self._note('call-submitted', {'request_id': receipt.request_id,
                                          'status': int(receipt.status),
                                          'deadline_qpc': reply.deadline_qpc})
        return receipt

    def cancel_before_start(self, receipt, context):
        """Cancel only while the target has not started (target-side CAS)."""
        self._guard_open()
        self._require_receipt(receipt)
        if receipt.status != ReceiptStatus.PENDING:
            if receipt.status in (ReceiptStatus.RUNNING, ReceiptStatus.HUNG):
                raise CallAlreadyStarted(
                    'Cancellation after start is refused: a started call is never '
                    'cancelled or force-terminated.')
            raise CallNotPrepared(
                f'Receipt {receipt.request_id} is {receipt.status.name}; only a '
                'prepared call can be cancelled.')
        if not isinstance(context, CallContext):
            raise CallBrokerError('Cancellation requires an explicit CallContext.')
        try:
            reply = self._broker.observe(receipt.request_id, context, Command.CANCEL)
        except Exception as exc:
            receipt.status = ReceiptStatus.UNCERTAIN
            receipt.transitions.append((int(ReceiptStatus.UNCERTAIN),
                                        f'cancellation unverified: {str(exc)[:200]}'))
            self._note('call-uncertain', {'request_id': receipt.request_id,
                                          'reason': str(exc)[:512]})
            raise CallBrokerUncertain(
                'Cancellation has no verified acknowledgement; no retry is permitted.') from exc
        if reply.status == Status.CANCELLED_BEFORE_START and reply.completed:
            receipt.status = ReceiptStatus.CANCELLED
            receipt.transitions.append((int(ReceiptStatus.CANCELLED),
                                        'cancelled before start'))
            self._note('call-cancelled', {'request_id': receipt.request_id,
                                          'error': reply.error})
        else:
            # The target admitted the call meanwhile; the outcome is visible,
            # never a silent cancellation.
            receipt.status = ReceiptStatus.RUNNING
            receipt.transitions.append((int(ReceiptStatus.RUNNING),
                                        'target started before the cancellation'))
        return receipt

    def wait(self, receipt, context):
        """Block until the receipt reaches a known state within the context.

        A caller deadline while the target call still runs yields HUNG (not
        cancelled); the receipt stays observable and the session uncertain.
        A target-reported unknown state yields UNCERTAIN, also terminal.
        """
        self._guard_open()
        self._require_receipt(receipt)
        if receipt.terminal:
            return receipt
        if not isinstance(context, CallContext):
            raise CallBrokerError('Waiting requires an explicit CallContext.')
        reply = None
        try:
            while True:
                context.remaining()
                reply = self._broker.observe(receipt.request_id, context)
                if reply.status == Status.UNKNOWN:
                    self._finalize(receipt, ReceiptStatus.UNCERTAIN,
                                   'target reported an unknown one-shot state',
                                   error=reply.error)
                    self._broker.uncertain = True
                    raise CallBrokerUncertain(
                        'Target reported an unknown one-shot state; no retry, '
                        'save, replay or re-apply is permitted.')
                if reply.completed:
                    break
                if reply.status in (Status.PREPARED, Status.RUNNING):
                    receipt.status = (ReceiptStatus.PENDING
                                      if reply.status == Status.PREPARED
                                      else ReceiptStatus.RUNNING)
                time.sleep(0.003)
        except BrokerCancelled:
            # The caller stopped waiting; only a target-acknowledged CAS
            # cancellation proves the call never ran, otherwise HUNG.
            return self._prove_cancellation(receipt)
        except Exception as exc:
            # Exception after a possible partial effect: unknown, no retry.
            self._finalize(receipt, ReceiptStatus.UNCERTAIN,
                           f'observation failed: {str(exc)[:200]}', error=0)
            raise CallBrokerUncertain(
                'Completion evidence is unavailable; no retry, save, replay or '
                're-apply is permitted.') from exc
        if reply.status == Status.DONE:
            self._finalize(receipt, ReceiptStatus.DONE, 'terminal completion',
                           result=reply.result(), error=reply.error)
        elif reply.status == Status.CANCELLED_BEFORE_START:
            self._finalize(receipt, ReceiptStatus.CANCELLED,
                           'cancelled before start', error=reply.error)
        elif reply.status == Status.REFUSED:
            self._finalize(receipt, ReceiptStatus.REFUSED,
                           'target refused the call', error=reply.error)
        else:
            self._finalize(receipt, ReceiptStatus.UNCERTAIN,
                           'completed reply lacks a proven terminal state',
                           error=reply.error)
        return receipt

    def _prove_cancellation(self, receipt):
        """The caller's deadline expired without a no-call completion proof.
        One bounded cleanup window attempts a CAS cancel + observation; only a
        target-acknowledged cancellation proves the call never ran. Otherwise
        the receipt is HUNG and the session is uncertain; no force-stop."""
        proven = False
        try:
            cleanup = CallContext.seconds(1)
            reply = self._broker.observe(receipt.request_id, cleanup, Command.CANCEL)
            for _ in range(100):
                if reply.completed:
                    break
                time.sleep(0.003)
                reply = self._broker.observe(receipt.request_id, cleanup)
            proven = (reply.completed and
                      reply.status == Status.CANCELLED_BEFORE_START)
        except Exception:
            pass
        if proven:
            receipt.status = ReceiptStatus.CANCELLED
            receipt.transitions.append((int(ReceiptStatus.CANCELLED),
                                        'acknowledged cancellation before start'))
            self._note('call-cancelled', {'request_id': receipt.request_id,
                                          'proven': True})
        else:
            receipt.status = ReceiptStatus.HUNG
            receipt.transitions.append((int(ReceiptStatus.HUNG),
                                        'caller deadline expired while the target '
                                        'call may still run; not cancelled'))
            self._note('call-hung', {'request_id': receipt.request_id})
        self._broker.uncertain = True
        return receipt

    def release_buffers(self, receipt):
        """Release retained byref buffers only after the terminal ACK."""
        self._guard_open()
        self._require_receipt(receipt)
        if receipt.status not in RELEASABLE_STATES:
            raise BufferReleaseBeforeAck(
                f'Buffers stay retained until the terminal ACK; receipt '
                f'{receipt.request_id} is {receipt.status.name}.')
        count = len(receipt.buffers)
        receipt.buffers.clear()
        self._note('call-buffers-released', {'request_id': receipt.request_id,
                                             'count': count})
        return count

    def register_cave(self, name, address, size, alignment):
        """Reserve target cave bookkeeping; retained until target exit."""
        self._guard_open()
        if type(name) is not str or not name or name in self.caves:
            raise CaveBadInput('Cave name must be a non-empty unique string.')
        if type(address) is not int or address <= 0 or address >= 1 << self.bitness:
            raise CaveBadInput('Cave address must lie inside the target address space.')
        if type(size) is not int or not 1 <= size <= CAVE_SIZE_MAX:
            raise CaveBadInput(f'Cave size must be within 1..{CAVE_SIZE_MAX}.')
        if (type(alignment) is not int or alignment < 1 or alignment > ALIGNMENT_MAX
                or alignment & (alignment - 1)):
            raise CaveBadInput(f'Cave alignment must be a power of two up to {ALIGNMENT_MAX}.')
        if address % alignment:
            raise CaveBadInput('Cave address is not aligned to its declared alignment.')
        binding = CaveBinding(name, address, size, alignment)
        self.caves[name] = binding
        self._note('call-cave', {'name': name, 'address': address, 'size': size,
                                 'alignment': alignment, 'retained_until': 'target exit'})
        return binding

    def release_cave(self, name):
        if not isinstance(name, str) or name not in self.caves:
            raise CallBrokerError('Unknown cave name.')
        raise CaveRetainedUntilTargetExit(
            'Cave bookkeeping is retained until target exit; the controller '
            'has no free or pool API.')

    def close(self):
        """Close the session; open receipts stay durable, caves retire with the
        target process exit; nothing is freed by the controller."""
        if self._closed:
            return
        self._closed = True
        for name, binding in list(self.caves.items()):
            self.caves[name] = CaveBinding(binding.name, binding.address, binding.size,
                                           binding.alignment, retired_with_target=True)
        open_receipts = [receipt.request_id for receipt in self.receipts.values()
                         if not receipt.terminal]
        self._broker.closed = True
        self._note('call-close', {'open_receipts': open_receipts,
                                  'caves_retired': sorted(self.caves),
                                  'retention': 'open receipts stay durable; caves stay '
                                               'pinned until target exit'})

    def snapshot(self):
        return {
            'schema': SCHEMA,
            'image': {'pid': self.image.pid,
                      'created_filetime': self.image.created_filetime,
                      'pe_sha256': self.image.pe_sha256},
            'bitness': self.bitness,
            'closed': self._closed,
            'entries': {name: {'address': binding.address, 'bitness': binding.bitness}
                        for name, binding in self.entries.items()},
            'caves': {name: {'address': binding.address, 'size': binding.size,
                             'retired_with_target': binding.retired_with_target}
                      for name, binding in self.caves.items()},
            'receipts': [receipt.describe() for receipt in self.receipts.values()],
        }
