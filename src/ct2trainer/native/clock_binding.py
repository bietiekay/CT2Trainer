"""Per-attach clock/speed binding for the Lua host profile (N-16).

The engine owns one binding per confirmed attach. It routes the corpus
speed surface (``speedhack_setSpeed`` / ``speedhack_getSpeed`` as used by
the pinned Alien Isolation and re2 records) through the tested Clock v2
core/gateway model in :mod:`clock_engine`. All clock semantics --
multiplier-to-ppm conversion, the visible profile limit, lease windows,
owner rules and fault stickiness -- stay in that model; this module only
routes commands and refuses fail-closed.

The production default binding samples no raw counter: the owned Windows
clock route (AP-11) is still open, so every speed call refuses visibly
instead of inventing time. Tests inject a binding built on the tested
model with a scripted counter, so no Windows API is touched.

Fail-closed named refusals:

- ``ClockNotAttached``    no live binding (target session not attached)
- ``ClockTerminated``     binding already finished on detach/close
- ``ClockBadMultiplier``  invalid speed argument (type, sign, finiteness)
- ``ClockRateOutOfRange`` multiplier above the visible profile limit;
                          the limit is never clamped silently
- ``ClockFault``          sticky core/gateway fault or refused command
"""
from __future__ import annotations

import math

from .clock_engine import (
    ACK_TRANSITION,
    ClockBadInput,
    ClockCommand,
    ClockConfig,
    ClockCore,
    ClockGateway,
    ClockStatus,
    COMMAND_CLOSE,
    COMMAND_RENEW,
    COMMAND_SET_RATE,
    GatewayStatus,
    LEASE_SECONDS_MAX,
    PENDING_SECONDS_MAX,
    RATE_MAX_CORE,
    RATE_ONE,
)


class ClockBindingError(Exception):
    """Base of the named clock binding refusals."""


class ClockNotAttached(ClockBindingError):
    """No live clock binding: the target session is not attached."""


class ClockTerminated(ClockBindingError):
    """The binding was finished on detach/close and can no longer act."""


class ClockBadMultiplier(ClockBindingError):
    """The speed argument is not a valid finite non-negative number."""


class ClockRateOutOfRange(ClockBindingError):
    """The multiplier exceeds the visible profile limit; it is never clamped."""


class ClockFault(ClockBindingError):
    """Sticky core/gateway fault or a refused clock command."""


_GATEWAY_REFUSALS = {
    GatewayStatus.BAD_INPUT: 'invalid clock command',
    GatewayStatus.BUSY: 'clock command slot is busy',
    GatewayStatus.STALE_SEQUENCE: 'stale clock command sequence',
    GatewayStatus.PLATFORM_FAULT: 'clock platform fault',
    GatewayStatus.FENCED_OWNER: 'clock owner is fenced',
    GatewayStatus.EXPIRED: 'clock command expired before consumption',
    GatewayStatus.CLOCK_FAULT: 'clock model fault',
}


class ClockSpeedBinding:
    """One attach's speed control over the tested Clock v2 model.

    ``set_speed`` applies a corpus multiplier (0 freezes the scaled clock,
    1 is normal time) and returns nil on purpose: the pinned luacall
    records use it as a statement, and a non-nil return would break the
    Lua program's AA-return contract. ``get_speed`` reports the current
    multiplier from the model. ``tick`` is the engine poll hook that keeps
    a held lease alive; ``finish`` retires the owner on detach/close so a
    stopped target keeps no speed state in the engine.
    """

    def __init__(self, core: ClockCore, gateway: ClockGateway, *, owner: int = 1):
        if not isinstance(core, ClockCore):
            raise ClockBadInput('Clock binding requires the tested ClockCore')
        if not isinstance(gateway, ClockGateway):
            raise ClockBadInput('Clock binding requires the tested ClockGateway')
        if type(owner) is not int or owner <= 0:
            raise ClockBadInput('Clock binding owner must be a positive integer')
        self.core = core
        self.gateway = gateway
        self.owner = owner
        self.terminated = False

    # -- state --------------------------------------------------------------
    @property
    def rate_ppm(self) -> int:
        return self.core.rate_ppm

    @property
    def active(self) -> bool:
        return not self.terminated and self.core.owner == self.owner

    # -- corpus surface -------------------------------------------------------
    def set_speed(self, speed) -> None:
        """Apply the corpus multiplier; returns nil by contract."""
        self._guard()
        if type(speed) is bool or not isinstance(speed, (int, float)):
            raise ClockBadMultiplier('speedhack_setSpeed requires a numeric multiplier')
        if isinstance(speed, float) and (math.isnan(speed) or math.isinf(speed)):
            raise ClockBadMultiplier('speedhack_setSpeed requires a finite multiplier')
        if speed < 0:
            raise ClockBadMultiplier('speedhack_setSpeed multipliers must not be negative')
        rate = round(float(speed) * RATE_ONE)
        if rate > self.core.rate_max_ppm:
            raise ClockRateOutOfRange(
                f'speedhack_setSpeed({speed}) exceeds the x{self.core.rate_max_ppm // RATE_ONE} profile; '
                'extend the profile visibly instead of clamping')
        self._roundtrip(COMMAND_SET_RATE, rate)

    def get_speed(self) -> float:
        """Read the current multiplier from the model (1.0 = normal time)."""
        self._guard()
        status, snapshot = self.core.read()
        if status != ClockStatus.OK:
            raise ClockFault(f'Clock read failed with status {int(status)}')
        return snapshot.rate_ppm / RATE_ONE

    def tick(self) -> None:
        """Engine poll hook: extend a held speed lease before it expires.

        Lease upkeep is background maintenance, not user input: a failed
        sample or refused renewal leaves the tested core to fault or the
        lease to expire on its own, after which every speed call refuses
        visibly as ``ClockFault``. It therefore never raises into the
        poll loop and cannot take down the rest of the trainer.
        """
        if self.terminated:
            return
        if self.core.owner != self.owner:
            return
        try:
            status, _ = self.core.read()
            if status != ClockStatus.OK:
                return
            remaining = self.core.lease_deadline - self.core.raw_anchor
            if remaining > self.core.config.frequency * LEASE_SECONDS_MAX // 2:
                return
            self._roundtrip(COMMAND_RENEW)
        except ClockBindingError:
            # Retained in the model: sticky core/gateway fault, or the lease
            # expires at its deadline and the core reverts to 1x on its own.
            return

    def finish(self) -> None:
        """Detach/close: fence the owner and drop the speed lease.

        Any in-flight speed intent is cancelled before consumption; a held
        lease is closed visibly so the core reverts to 1x while keeping its
        accumulated offset. After this call the binding is terminated and
        every speed call refuses with ``ClockTerminated``.
        """
        if self.terminated:
            return
        self.terminated = True
        # Fence first: no fresh intent from the retiring owner can pass, and
        # a pending READY command is drained without being applied.
        self.gateway.cancel(self.owner)
        if self.gateway.slot == 'ACK':
            self.gateway.take_ack()
        # Total by construction: core.close only returns status codes, so a
        # faulty core keeps its last valid state instead of raising.
        if self.core.owner == self.owner:
            self.core.close(self.owner)

    # -- internals ------------------------------------------------------------
    def _guard(self) -> None:
        if self.terminated:
            raise ClockTerminated(
                'Clock binding was finished with the session; the target is no longer attached')
        if self.gateway.fault or self.core.fault != ClockStatus.OK:
            raise ClockFault(
                f'Clock model is in a sticky fault (status {int(self.core.fault)})')

    def _raw_now(self) -> int:
        now = self.core.config.raw_counter()
        if now is None or not isinstance(now, int) or now <= 0:
            raise ClockFault('Original raw counter sample failed; clock state is uncertain')
        return now

    def _roundtrip(self, operation: int, rate_ppm: int = 0) -> None:
        """One bounded gateway round-trip: submit, consume, claim the ACK."""
        now = self._raw_now()
        frequency = self.core.config.frequency
        command = ClockCommand(
            sequence=self.gateway.last_sequence + 1,
            owner=self.owner,
            operation=operation,
            rate_ppm=rate_ppm,
            not_after_qpc=now + frequency * PENDING_SECONDS_MAX,
            lease_deadline_qpc=0 if operation == COMMAND_CLOSE
            else now + frequency * LEASE_SECONDS_MAX,
        )
        status = self.gateway.submit(command)
        if status is not GatewayStatus.OK:
            raise ClockFault('Clock command refused: ' + _GATEWAY_REFUSALS[status])
        self.gateway.tick()
        ack = self.gateway.take_ack()
        if ack is None:
            raise ClockFault('Clock command was not acknowledged')
        if ack.disposition != ACK_TRANSITION:
            raise ClockFault(f'Clock command ended as {ack.disposition}')
        if ack.clock_status != int(ClockStatus.OK):
            raise ClockFault(f'Clock command applied with refusal status {ack.clock_status}')


def default_speed_binding(rate_max_ppm: int = RATE_MAX_CORE) -> ClockSpeedBinding:
    """Engine default: per-attach binding over a not-ready raw counter.

    Until the owned Windows clock route (AP-11) exists and is verified, no
    sample is produced: the first speed call faults the tested model
    visibly, and every later call refuses with ``ClockFault``.
    """
    counter = lambda: None  # noqa: E731 -- deliberate not-ready sample source
    config = ClockConfig(
        frequency=1,
        qpc_origin=0,
        initial_raw_qpc=0,
        tick64_origin=0,
        tick64_capture_qpc=0,
        multimedia_origin=0,
        multimedia_capture_qpc=0,
        raw_counter=counter,
    )
    core = ClockCore(config, rate_max_ppm=rate_max_ppm)
    return ClockSpeedBinding(core, ClockGateway(core, counter))
