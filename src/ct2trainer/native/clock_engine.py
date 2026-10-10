"""Clock v2 contract model: pure-Python mirror of the owned clock core.

Mirrors the contract of ``src/ct2trainer/native/clock/clock_core.c``
(status codes, owner/lease rules, fault behaviour, DWORD wrap) and the v2
command/ACK surface of ``clock_adapter.c``. No C, no ctypes, no processes:
every bound is checked in pure Python with explicit 64-bit limits so the
model stays faithful to the integer core's overflow decisions.

Reckoning chain (contract; documented):

- The original raw counter (the trusted QPC callback) is the ONLY time
  source. The scaled clock never samples its own output: qpc, tick64,
  tick32 and multimedia32 are always derived from the raw anchor, the
  fixed capture epochs and the accumulated virtual elapsed time -- never
  from a previously emitted snapshot value.
- Lease deadlines and not-after windows are original-QPC ticks and are
  checked against raw samples, never against scaled qpc output.
- Rate changes advance time segment-wise: the old rate up to the deadline,
  then the new rate from the raw sample at which the change was admitted.
- Fractional remainders survive interval and rate changes (fraction_ppm),
  so small deltas accumulate instead of truncating.
- DWORD outputs (tick32, multimedia32) wrap as API behaviour, not as
  arithmetic faults; sticky faults retain the last valid outputs.
- The x16 core profile caps rates at ``RATE_MAX_CORE = 16 * RATE_ONE``.
  Rates beyond the profile are refused with a visible status -- never
  silently clamped. The profile may be visibly extended by constructing
  with an explicit ``rate_max_ppm`` (e.g. a 20x CT rate with
  ``rate_max_ppm = 20 * RATE_ONE``), which then admits exactly 20x.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

RATE_ONE = 1000000
RATE_MAX_CORE = 16000000
LEASE_SECONDS_MAX = 30
PENDING_SECONDS_MAX = 1
UINT64_MAX = (1 << 64) - 1
INT64_MAX = (1 << 63) - 1


class ClockStatus(IntEnum):
    OK = 0
    BAD_INPUT = 1
    RAW_SAMPLE_FAILED = 2
    REGRESSION = 3
    OVERFLOW = 4
    STALE_OWNER = 5
    OWNER_CONFLICT = 6


class GatewayStatus(IntEnum):
    """Visible adapter-level results (mirrors tf_clock_adapter_status)."""
    OK = 0
    BAD_INPUT = 1
    BUSY = 2
    STALE_SEQUENCE = 3
    PLATFORM_FAULT = 4
    FENCED_OWNER = 5
    EXPIRED = 6
    CLOCK_FAULT = 7


COMMAND_SET_RATE = 1
COMMAND_RENEW = 2
COMMAND_CLOSE = 3

ACK_TRANSITION = 'transition'
ACK_EXPIRED = 'expired'
ACK_CANCELLED_PENDING = 'cancelled_pending'
ACK_CANCELLED_AFTER_CONSUMPTION = 'cancelled_after_consumption'
ACK_PLATFORM_FAULT = 'platform_fault'


class ClockError(Exception):
    """Base of the named clock model refusals."""


class ClockBadInput(ClockError):
    """A visible refusal at construction (C: TF_CLOCK_BAD_INPUT)."""


class ClockOverflow(ClockError):
    """A visible overflow refusal at construction (C: TF_CLOCK_OVERFLOW)."""


@dataclass(frozen=True)
class ClockSnapshot:
    qpc: int
    tick64: int
    tick32: int
    multimedia32: int
    raw_anchor: int
    owner: int
    lease_deadline: int
    rate_ppm: int
    fault: int


def ticks_to_ms(ticks, frequency):
    """Overflow-checked 64-bit millisecond conversion.

    Contract-equal to the C core's ``tf_clock_ticks_to_ms``: returns the
    exact millisecond count or None where the 64-bit result would
    overflow (C: TF_CLOCK_OVERFLOW). No intermediate wrap, by construction.
    """
    if type(ticks) is not int or type(frequency) is not int or frequency <= 0:
        return None
    if ticks < 0:
        return None
    whole = ticks // frequency
    remainder = ticks % frequency
    if whole > UINT64_MAX // 1000:
        return None
    quotient = (remainder * 1000) // frequency
    ms = whole * 1000 + quotient
    if ms > UINT64_MAX:
        return None
    return ms


class FakeCounter:
    """Scripted raw-QPC source used by the tests; None means sample failure."""

    def __init__(self, now=0, fail=False):
        self.now = now
        self.fail = fail

    def __call__(self):
        if self.fail:
            return None
        return self.now


@dataclass(frozen=True)
class ClockConfig:
    frequency: int
    qpc_origin: int
    initial_raw_qpc: int
    tick64_origin: int
    tick64_capture_qpc: int
    multimedia_origin: int
    multimedia_capture_qpc: int
    raw_counter: FakeCounter


def _validate_config(config):
    if not isinstance(config, ClockConfig):
        raise ClockBadInput('Clock configuration must be a ClockConfig.')
    c = config
    if not isinstance(c.raw_counter, FakeCounter) and not callable(c.raw_counter):
        raise ClockBadInput('raw_counter must be callable.')
    if not isinstance(c.frequency, int) or c.frequency <= 0 or c.frequency > INT64_MAX:
        raise ClockBadInput('Frequency must be a positive int64.')
    for name in ('qpc_origin', 'initial_raw_qpc', 'tick64_capture_qpc',
                 'multimedia_capture_qpc'):
        if not isinstance(getattr(c, name), int):
            raise ClockBadInput(f'{name} must be an integer.')
    if c.qpc_origin > c.initial_raw_qpc:
        raise ClockBadInput('qpc_origin must not exceed initial_raw_qpc.')
    if c.initial_raw_qpc > INT64_MAX:
        raise ClockBadInput('initial_raw_qpc exceeds the 64-bit signed bound.')
    if not (c.qpc_origin <= c.tick64_capture_qpc <= c.initial_raw_qpc):
        raise ClockBadInput('tick64 capture epoch outside the raw window.')
    if not (c.qpc_origin <= c.multimedia_capture_qpc <= c.initial_raw_qpc):
        raise ClockBadInput('multimedia capture epoch outside the raw window.')


class ClockCore:
    """State-machine mirror of the C clock core for contract testing.

    Every public operation returns ``(status, snapshot)`` exactly like the
    C API, and every input that the C core would reject maps to the same
    status code or named exception.
    """

    def __init__(self, config, rate_max_ppm=RATE_MAX_CORE):
        _validate_config(config)
        if (type(rate_max_ppm) is not int or rate_max_ppm <= 0
                or rate_max_ppm > INT64_MAX):
            raise ClockBadInput('rate_max_ppm must be a positive int64.')
        self.config = config
        self.rate_max_ppm = rate_max_ppm
        self.raw_anchor = config.initial_raw_qpc
        self.virtual_elapsed = config.initial_raw_qpc - config.qpc_origin
        self.owner = 0
        self.last_owner = 0
        self.lease_deadline = 0
        self.fraction_ppm = 0
        self.rate_ppm = RATE_ONE
        self.fault = ClockStatus.OK
        status, snapshot = self._materialize()
        if status != ClockStatus.OK:
            raise ClockOverflow('Initial clock materialization overflowed.')
        self.last = snapshot

    # -- internals ---------------------------------------------------------
    def _progress(self):
        return self.raw_anchor, self.virtual_elapsed, self.owner, \
            self.lease_deadline, self.fraction_ppm, self.rate_ppm

    def _restore(self, raw_anchor, elapsed, owner, deadline, fraction, rate):
        self.raw_anchor = raw_anchor
        self.virtual_elapsed = elapsed
        self.owner = owner
        self.lease_deadline = deadline
        self.fraction_ppm = fraction
        self.rate_ppm = rate

    def _materialize(self):
        c = self.config
        raw_anchor = self.raw_anchor
        elapsed = self.virtual_elapsed
        owner = self.owner
        deadline = self.lease_deadline
        rate = self.rate_ppm
        ticks_epoch = c.tick64_capture_qpc - c.qpc_origin
        multimedia_epoch = c.multimedia_capture_qpc - c.qpc_origin
        if (elapsed > INT64_MAX - c.qpc_origin or elapsed < ticks_epoch
                or elapsed < multimedia_epoch):
            return ClockStatus.OVERFLOW, None
        tick_ms = ticks_to_ms(elapsed - ticks_epoch, c.frequency)
        if tick_ms is None:
            return ClockStatus.OVERFLOW, None
        multimedia_ms = ticks_to_ms(elapsed - multimedia_epoch, c.frequency)
        if multimedia_ms is None:
            return ClockStatus.OVERFLOW, None
        if tick_ms > UINT64_MAX - c.tick64_origin:
            return ClockStatus.OVERFLOW, None
        tick64 = c.tick64_origin + tick_ms
        snapshot = ClockSnapshot(
            qpc=c.qpc_origin + elapsed,
            tick64=tick64,
            tick32=tick64 & 0xFFFFFFFF,
            multimedia32=(c.multimedia_origin + multimedia_ms) & 0xFFFFFFFF,
            raw_anchor=raw_anchor,
            owner=owner,
            lease_deadline=deadline,
            rate_ppm=rate,
            fault=ClockStatus.OK,
        )
        return ClockStatus.OK, snapshot

    def _advance(self, raw_anchor, elapsed, fraction, rate, now):
        """Advance one segment; returns (ok, elapsed, fraction)."""
        delta = now - raw_anchor
        whole = delta // RATE_ONE
        partial = (delta % RATE_ONE) * rate + fraction
        if rate != 0 and whole > UINT64_MAX // rate:
            return False, None, None
        addition = whole * rate
        if partial // RATE_ONE > UINT64_MAX - addition:
            return False, None, None
        addition += partial // RATE_ONE
        if addition > UINT64_MAX - elapsed:
            return False, None, None
        return True, elapsed + addition, partial % RATE_ONE

    def _fail(self, status):
        """Enter the sticky fault state; returns only the status code."""
        self.fault = status
        self.last = ClockSnapshot(self.last.qpc, self.last.tick64,
                                  self.last.tick32, self.last.multimedia32,
                                  self.raw_anchor, self.owner,
                                  self.lease_deadline, self.rate_ppm, status)
        return status

    def _commit(self, progress, snapshot):
        (raw_anchor, elapsed, owner, deadline, fraction, rate) = progress
        self._restore(raw_anchor, elapsed, owner, deadline, fraction, rate)
        self.last = snapshot

    def _sample_and_advance(self, progress):
        """Shared read path: sample raw, apply expiry, advance, materialize.

        Returns (status, progress_or_None, snapshot_or_None)."""
        if self.fault != ClockStatus.OK:
            return self.fault, None, None
        now = self.config.raw_counter()
        if now is None or not isinstance(now, int) or now <= 0:
            return self._fail(ClockStatus.RAW_SAMPLE_FAILED), None, None
        if now > INT64_MAX:
            return self._fail(ClockStatus.OVERFLOW), None, None
        anchor, elapsed, owner, deadline, fraction, rate = progress
        if now < anchor:
            if anchor - now == 1:
                now = anchor
            else:
                return self._fail(ClockStatus.REGRESSION), None, None
        if owner and now >= deadline:
            ok, elapsed, fraction = self._advance(anchor, elapsed, fraction,
                                                  rate, deadline)
            if not ok:
                return self._fail(ClockStatus.OVERFLOW), None, None
            # C advance_segment sets next.raw_anchor = now (the deadline);
            # the following segment starts from the deadline, not the old
            # anchor, otherwise the interval would be counted twice.
            anchor = deadline
            rate = RATE_ONE
            owner = 0
            deadline = 0
        ok, elapsed, fraction = self._advance(anchor, elapsed, fraction, rate, now)
        if not ok:
            return self._fail(ClockStatus.OVERFLOW), None, None
        next_progress = (now, elapsed, owner, deadline, fraction, rate)
        status, snapshot = self._materialize_for(next_progress)
        if status != ClockStatus.OK:
            return self._fail(status), None, None
        return status, next_progress, snapshot

    def _materialize_for(self, progress):
        (raw_anchor, elapsed, owner, deadline, fraction, rate) = progress
        saved = self.raw_anchor, self.virtual_elapsed, self.owner, \
            self.lease_deadline, self.fraction_ppm, self.rate_ppm
        self._restore(*saved)
        self.raw_anchor, self.virtual_elapsed = raw_anchor, elapsed
        self.owner, self.lease_deadline = owner, deadline
        self.fraction_ppm, self.rate_ppm = fraction, rate
        status, snapshot = self._materialize()
        self._restore(*saved)
        return status, snapshot

    def read(self):
        """Sample raw time, advance the clock, publish a new snapshot."""
        if self.fault != ClockStatus.OK:
            return self.fault, self.last
        status, next_progress, snapshot = self._sample_and_advance(self._progress())
        if status == ClockStatus.OK:
            self._commit(next_progress, snapshot)
            return ClockStatus.OK, snapshot
        return status, self.last

    def _valid_lease(self, ticks):
        maximum = self.config.frequency * LEASE_SECONDS_MAX \
            if self.config.frequency <= UINT64_MAX // LEASE_SECONDS_MAX else UINT64_MAX
        return ticks != 0 and ticks <= maximum

    def _control(self, owner, rate, lease_ticks, operation, not_after):
        if (not isinstance(owner, int) or owner <= 0 or owner > INT64_MAX
                or not isinstance(rate, int) or rate < 0
                or not isinstance(lease_ticks, int) or lease_ticks < 0):
            return ClockStatus.BAD_INPUT, self.last
        if operation >= 3 and (not_after <= 0 or not_after > lease_ticks):
            return ClockStatus.BAD_INPUT, self.last
        if operation != 2:
            if rate > self.rate_max_ppm:
                return ClockStatus.BAD_INPUT, self.last
            if operation < 3 and not self._valid_lease(lease_ticks):
                return ClockStatus.BAD_INPUT, self.last
        status, _ = self.read()
        if status != ClockStatus.OK:
            return status, self.last
        if self.owner != 0 and self.owner != owner:
            return ClockStatus.OWNER_CONFLICT, self.last
        if self.owner == 0 and (operation not in (0, 3) or owner <= self.last_owner):
            return ClockStatus.STALE_OWNER, self.last
        if operation >= 3 and (lease_ticks <= self.raw_anchor
                               or lease_ticks > INT64_MAX
                               or self.raw_anchor >= not_after
                               or not self._valid_lease(lease_ticks - self.raw_anchor)):
            return ClockStatus.BAD_INPUT, self.last
        if operation < 2 and lease_ticks > INT64_MAX - self.raw_anchor:
            return ClockStatus.BAD_INPUT, self.last
        progress = self._progress()
        if operation == 2:
            progress = (progress[0], progress[1], 0, 0, progress[4], RATE_ONE)
        else:
            deadline = lease_ticks if operation >= 3 else progress[0] + lease_ticks
            progress = (progress[0], progress[1], owner, deadline,
                        progress[4], rate if operation in (0, 3) else progress[5])
        status, snapshot = self._materialize_for(progress)
        if status == ClockStatus.OK:
            self._commit(progress, snapshot)
            if owner > self.last_owner:
                self.last_owner = owner
        return status, snapshot

    def set_rate(self, owner, rate_ppm, lease_ticks):
        """Take or refresh a relative lease; rate is 0..rate_max_ppm inclusive."""
        return self._control(owner, rate_ppm, lease_ticks, 0, 0)

    def renew(self, owner, lease_ticks):
        """Extend the current lease, keeping the current rate."""
        return self._control(owner, RATE_ONE, lease_ticks, 1, 0)

    def close(self, owner):
        """Release the lease; the clock keeps its accumulated offset at 1x."""
        return self._control(owner, 0, 0, 2, 0)

    def set_rate_until(self, owner, rate_ppm, not_after, deadline):
        """Absolute original-QPC deadline; never starts a fresh lease window."""
        return self._control(owner, rate_ppm, deadline, 3, not_after)

    def renew_until(self, owner, not_after, deadline):
        """Extend with an absolute original-QPC deadline at rate one."""
        return self._control(owner, RATE_ONE, deadline, 4, not_after)


@dataclass(frozen=True)
class ClockCommand:
    """One bounded command in the original-QPC time domain (adapter v2)."""
    sequence: int
    owner: int
    operation: int
    rate_ppm: int
    not_after_qpc: int
    lease_deadline_qpc: int


@dataclass(frozen=True)
class ClockAck:
    """Immutable acknowledgement of one consumed command."""
    sequence: int
    owner: int
    operation: int
    clock_status: int
    disposition: str
    snapshot_valid: bool
    snapshot: ClockSnapshot


class ClockGateway:
    """Command/ACK/fence model of the owned clock adapter v2 surface.

    Mirrors the adapter's bounded nonblocking slot: ``submit`` admits at most
    one outstanding command; a wrapper ``tick`` consumes it and publishes one
    immutable ACK; only ``take_ack`` releases the slot. A lost ACK keeps the
    slot busy -- the model has no retry, replay or re-apply path. Cancellation
    fences an owner generation; a fenced owner is refused for fresh intent
    (only its own CLOSE passes, mirroring the retirement path). Faults are
    sticky and visible; nothing is retried silently.
    """

    def __init__(self, core, raw_clock):
        if not callable(raw_clock):
            raise ClockBadInput('raw_clock must be the original QPC counter.')
        self.core = core
        self.raw_clock = raw_clock
        self.slot = 'EMPTY'
        self.command = None
        self.ack = None
        self.last_sequence = 0
        self.owner_fence = 0
        self.retired_fence = 0
        self.fault = False

    def submit(self, command):
        """Admit one command into the single bounded slot (visible status).

        Check order mirrors ``tf_clock_adapter`` ``submit_impl`` exactly:
        type/fault, static validation, owner fence, raw sample, expiry,
        pending/lease windows, slot occupancy, sequence, then publication.
        """
        if not isinstance(command, ClockCommand):
            return GatewayStatus.BAD_INPUT
        if self.fault or self.core.fault != ClockStatus.OK:
            return GatewayStatus.CLOCK_FAULT
        c = command
        if (type(c.sequence) is not int or c.sequence <= 0
                or type(c.owner) is not int or c.owner <= 0
                or c.owner > INT64_MAX
                or type(c.operation) is not int
                or type(c.rate_ppm) is not int or c.rate_ppm < 0
                or type(c.not_after_qpc) is not int or c.not_after_qpc <= 0
                or type(c.lease_deadline_qpc) is not int or c.lease_deadline_qpc < 0):
            return GatewayStatus.BAD_INPUT
        if c.operation not in (COMMAND_SET_RATE, COMMAND_RENEW, COMMAND_CLOSE):
            return GatewayStatus.BAD_INPUT
        if c.operation == COMMAND_SET_RATE and c.rate_ppm > self.core.rate_max_ppm:
            # Visible profile refusal: the limit is never clamped silently.
            return GatewayStatus.BAD_INPUT
        if c.operation != COMMAND_SET_RATE and c.rate_ppm != 0:
            return GatewayStatus.BAD_INPUT
        if c.not_after_qpc > INT64_MAX or c.lease_deadline_qpc > INT64_MAX:
            return GatewayStatus.BAD_INPUT
        if c.operation == COMMAND_CLOSE and c.lease_deadline_qpc != 0:
            return GatewayStatus.BAD_INPUT
        if c.operation != COMMAND_CLOSE and c.lease_deadline_qpc < c.not_after_qpc:
            return GatewayStatus.BAD_INPUT
        # A fenced owner cannot submit fresh rate intent; only its own CLOSE
        # (retirement) may still pass the fence.
        if c.owner <= self.owner_fence and c.operation != COMMAND_CLOSE:
            return GatewayStatus.FENCED_OWNER
        now = self.raw_clock()
        if now is None or not isinstance(now, int) or now <= 0:
            return GatewayStatus.CLOCK_FAULT
        if c.not_after_qpc <= now:
            return GatewayStatus.EXPIRED
        if c.not_after_qpc - now > self.core.config.frequency * PENDING_SECONDS_MAX:
            return GatewayStatus.BAD_INPUT
        if c.operation != COMMAND_CLOSE and (
                c.lease_deadline_qpc <= now
                or c.lease_deadline_qpc - now
                > self.core.config.frequency * LEASE_SECONDS_MAX):
            return GatewayStatus.BAD_INPUT
        if self.slot != 'EMPTY':
            return GatewayStatus.BUSY
        if c.sequence <= self.last_sequence:
            return GatewayStatus.STALE_SEQUENCE
        self.command = c
        self.last_sequence = c.sequence
        if c.operation == COMMAND_CLOSE:
            # A published CLOSE fences the owner immediately so that fresh
            # intent from the retiring owner is refused while it is in flight.
            self._fence_owner(c.owner)
        if c.owner <= self.owner_fence and c.operation != COMMAND_CLOSE:
            # The fence advanced between the check and the publication.
            self._publish(ACK_CANCELLED_PENDING, ClockStatus.STALE_OWNER, None,
                          snapshot_valid=False)
        else:
            self.slot = 'READY'
        return GatewayStatus.OK

    def tick(self):
        """Wrapper call: consume a READY command, publish exactly one ACK.

        Order mirrors the C ``consume_command``: fault, fence cancellation,
        raw sample, expiry, core call, expired re-disposition, fenced-owner
        retirement, post-consumption fence check (snapshot = core last).
        """
        if self.slot != 'READY':
            return
        command = self.command
        self.slot = 'BUSY'
        if self.fault or self.core.fault != ClockStatus.OK:
            self._publish(ACK_PLATFORM_FAULT, ClockStatus.RAW_SAMPLE_FAILED, None,
                          snapshot_valid=False)
            return
        if command.operation != COMMAND_CLOSE and command.owner <= self.owner_fence:
            self._publish(ACK_CANCELLED_PENDING, ClockStatus.STALE_OWNER, None,
                          snapshot_valid=False)
            return
        now = self.raw_clock()
        if now is None or not isinstance(now, int) or now <= 0:
            self.fault = True
            self._publish(ACK_PLATFORM_FAULT, ClockStatus.RAW_SAMPLE_FAILED, None,
                          snapshot_valid=False)
            return
        expired = now >= command.not_after_qpc or (
            command.operation != COMMAND_CLOSE
            and now >= command.lease_deadline_qpc)
        if expired:
            self._fence_owner(command.owner)
            self._publish(ACK_EXPIRED, ClockStatus.STALE_OWNER, None,
                          snapshot_valid=False)
            return
        if command.operation == COMMAND_SET_RATE:
            status, snapshot = self.core.set_rate_until(
                command.owner, command.rate_ppm, command.not_after_qpc,
                command.lease_deadline_qpc)
        elif command.operation == COMMAND_RENEW:
            status, snapshot = self.core.renew_until(
                command.owner, command.not_after_qpc, command.lease_deadline_qpc)
        else:
            status, snapshot = self.core.close(command.owner)
        disposition = ACK_TRANSITION
        if (command.operation != COMMAND_CLOSE and status == ClockStatus.BAD_INPUT
                and self.core.raw_anchor >= command.not_after_qpc):
            self._fence_owner(command.owner)
            disposition = ACK_EXPIRED
        self._retire_fenced_owner()
        if (disposition == ACK_TRANSITION
                and command.operation != COMMAND_CLOSE
                and command.owner <= self.owner_fence):
            disposition = ACK_CANCELLED_AFTER_CONSUMPTION
            snapshot = self.core.last
        self._publish(disposition, status, snapshot, snapshot_valid=True)

    def take_ack(self):
        """Claim the immutable ACK; only this call frees the slot."""
        if self.slot != 'ACK':
            return None
        ack = self.ack
        self.ack = None
        self.slot = 'EMPTY'
        return ack

    def cancel(self, owner):
        """Fence an owner generation; drain a READY command without applying it.

        A nonzero drained sequence proves the pending command was cancelled
        before consumption. A BUSY slot is fenced only: cancellation during
        consumption is uncertain by contract.
        """
        if type(owner) is not int or owner <= 0 or owner > INT64_MAX:
            raise ClockBadInput('Owner token must be a positive int64.')
        self._fence_owner(owner)
        drained = 0
        if self.slot == 'READY':
            command = self.command
            if command.owner <= self.owner_fence:
                self._publish(ACK_CANCELLED_PENDING, ClockStatus.STALE_OWNER, None,
                              snapshot_valid=False)
                drained = command.sequence
            # else: the fence does not cover that owner; slot stays READY.
        return self.owner_fence, drained

    def fence_status(self):
        """Monotonic fence metadata without touching the clock."""
        return self.owner_fence, self.retired_fence

    def snapshot(self):
        return {
            'schema': 'ct2trainer-clock-gateway/v1',
            'slot': self.slot,
            'last_sequence': self.last_sequence,
            'owner_fence': self.owner_fence,
            'retired_fence': self.retired_fence,
            'fault': self.fault,
            'core_owner': self.core.owner,
            'core_rate_ppm': self.core.rate_ppm,
            'core_lease_deadline': self.core.lease_deadline,
            'core_fault': int(self.core.fault),
        }

    # -- internals -----------------------------------------------------------
    def _fence_owner(self, owner):
        if owner > self.owner_fence:
            self.owner_fence = owner

    def _retire_fenced_owner(self):
        if self.core.owner and self.core.owner <= self.owner_fence:
            status, _ = self.core.close(self.core.owner)
            if status in (ClockStatus.OK, ClockStatus.STALE_OWNER):
                self.retired_fence = max(self.retired_fence, self.owner_fence)

    def _publish(self, disposition, clock_status, snapshot, snapshot_valid=True):
        command = self.command
        self.command = None
        self.ack = ClockAck(command.sequence, command.owner, command.operation,
                            int(clock_status), disposition, snapshot_valid,
                            snapshot)
        self.slot = 'ACK'
