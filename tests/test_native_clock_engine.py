"""Focused contract tests for the pure-Python clock v2 model (lane AP-06).

Covers the ClockCore state machine (fractional/zero/negative rates, DWORD
wrap, sticky faults, ownership/lease rules, x16 vs extended profile,
oracle independence) and the ClockGateway slot/ACK/fence semantics
(submit ordering, lost ACK without retry, cancellation drain, expiry).
"""
import unittest

from ct2trainer.native.clock_engine import (
    ACK_CANCELLED_AFTER_CONSUMPTION,
    ACK_CANCELLED_PENDING,
    ACK_EXPIRED,
    ACK_PLATFORM_FAULT,
    ACK_TRANSITION,
    COMMAND_CLOSE,
    COMMAND_RENEW,
    COMMAND_SET_RATE,
    ClockBadInput,
    ClockCommand,
    ClockConfig,
    ClockCore,
    ClockGateway,
    ClockOverflow,
    ClockStatus,
    FakeCounter,
    GatewayStatus,
    INT64_MAX,
    RATE_MAX_CORE,
    RATE_ONE,
    UINT64_MAX,
    ticks_to_ms,
)

FREQ = 1000


def make_core(rate_max_ppm=RATE_MAX_CORE, **overrides):
    counter = FakeCounter(now=2000)
    kwargs = dict(
        frequency=FREQ,
        qpc_origin=1000,
        initial_raw_qpc=2000,
        tick64_origin=10000,
        tick64_capture_qpc=1500,
        multimedia_origin=20000,
        multimedia_capture_qpc=1700,
        raw_counter=counter,
    )
    kwargs.update(overrides)
    return ClockCore(ClockConfig(**kwargs), rate_max_ppm=rate_max_ppm), counter


def make_gateway(core, counter):
    # The gateway must sample through the same callable source as the core,
    # so scripted sample failures (counter.fail) are visible to both.
    return ClockGateway(core, counter)


def command(sequence, owner, operation, rate_ppm=0, not_after=3000, lease=4000):
    return ClockCommand(
        sequence=sequence,
        owner=owner,
        operation=operation,
        rate_ppm=rate_ppm,
        not_after_qpc=not_after,
        lease_deadline_qpc=lease,
    )


class TestClockCoreReckoning(unittest.TestCase):
    def test_initial_snapshot_reckoning_chain(self):
        core, counter = make_core()
        status, snap = core.read()
        self.assertEqual(status, ClockStatus.OK)
        # qpc/tick64/multimedia all derive from the raw anchor plus the fixed
        # capture epochs -- never from each other.
        self.assertEqual(snap.qpc, 2000)
        self.assertEqual(snap.tick64, 10500)
        self.assertEqual(snap.tick32, 10500)
        self.assertEqual(snap.multimedia32, 20300)
        self.assertEqual(snap.raw_anchor, 2000)
        self.assertEqual(snap.owner, 0)
        self.assertEqual(snap.lease_deadline, 0)
        self.assertEqual(snap.rate_ppm, RATE_ONE)
        self.assertEqual(snap.fault, ClockStatus.OK)

    def test_integer_advance_at_one_x(self):
        core, counter = make_core()
        counter.now = 4000
        status, snap = core.read()
        self.assertEqual(status, ClockStatus.OK)
        # 1x: qpc tracks the raw oracle exactly.
        self.assertEqual(snap.qpc, 4000)
        self.assertEqual(snap.tick64, 12500)
        self.assertEqual(snap.multimedia32, 22300)
        self.assertEqual(snap.raw_anchor, 4000)

    def test_fractional_remainder_carries_across_intervals(self):
        core, counter = make_core()
        status, _ = core.set_rate(1, 2500, 30000)
        self.assertEqual(status, ClockStatus.OK)
        counter.now = 3000
        status, first = core.read()
        self.assertEqual(status, ClockStatus.OK)
        self.assertEqual(first.qpc, 2002)
        self.assertEqual(core.fraction_ppm, 500000)
        counter.now = 4000
        status, second = core.read()
        self.assertEqual(status, ClockStatus.OK)
        # Truncating arithmetic would give 2+2=4 ticks; the carried fraction
        # yields 2+3=5, proving remainders survive interval boundaries.
        self.assertEqual(second.qpc, 2005)
        self.assertEqual(second.tick64, 10505)
        self.assertEqual(core.fraction_ppm, 0)

    def test_zero_rate_freezes_scaled_outputs(self):
        core, counter = make_core()
        status, snap = core.set_rate(1, 0, 30000)
        self.assertEqual(status, ClockStatus.OK)
        self.assertEqual(snap.rate_ppm, 0)
        counter.now = 12000
        status, snap = core.read()
        self.assertEqual(status, ClockStatus.OK)
        # Scaled time frozen while the raw anchor keeps advancing; zero rate
        # is a valid setting, not a fault.
        self.assertEqual(snap.qpc, 2000)
        self.assertEqual(snap.tick64, 10500)
        self.assertEqual(snap.multimedia32, 20300)
        self.assertEqual(snap.raw_anchor, 12000)
        self.assertEqual(snap.fault, ClockStatus.OK)

    def test_sub_one_rate_slows_time(self):
        core, counter = make_core()
        status, _ = core.set_rate(1, RATE_ONE - 1, 30000)
        self.assertEqual(status, ClockStatus.OK)
        counter.now = 22000
        status, snap = core.read()
        self.assertEqual(status, ClockStatus.OK)
        # Raw advanced 20000 ticks; qpc advanced 19999 (1 ppm slower).
        self.assertEqual(snap.qpc, 21999)

    def test_tick32_wraps_without_fault(self):
        core, counter = make_core(tick64_origin=4294966790)
        _, before = core.read()
        self.assertEqual(before.tick32, 0xFFFFFFFA)
        counter.now = 2100
        status, after = core.read()
        self.assertEqual(status, ClockStatus.OK)
        # tick64 keeps growing past 2**32 while tick32 wraps modulo 2**32.
        self.assertGreater(after.tick64, before.tick64)
        self.assertEqual(after.tick64, 4294967390)
        self.assertEqual(after.tick32, 94)
        self.assertEqual(after.fault, ClockStatus.OK)

    def test_multimedia32_wraps_without_fault(self):
        core, counter = make_core(multimedia_origin=4294966990)
        _, before = core.read()
        self.assertEqual(before.multimedia32, 0xFFFFFFFA)
        counter.now = 2100
        status, after = core.read()
        self.assertEqual(status, ClockStatus.OK)
        self.assertEqual(after.multimedia32, 94)
        # The independent tick64 channel is unaffected by the multimedia wrap.
        self.assertEqual(after.tick64, 10600)
        self.assertEqual(after.fault, ClockStatus.OK)

    def test_original_time_never_read_from_scaled_clock(self):
        core, counter = make_core()
        counter0 = counter.now
        status, _ = core.set_rate(1, 2 * RATE_ONE, 30000)
        self.assertEqual(status, ClockStatus.OK)
        counter.now = 3000
        status, snap = core.read()
        self.assertEqual(status, ClockStatus.OK)
        # Output derives from the oracle delta, not from the previous scaled
        # qpc: the anchor equals the oracle sample and qpc scaled the raw
        # delta, not its own last output.
        self.assertEqual(snap.raw_anchor, counter.now)
        self.assertEqual(snap.qpc - counter0, 2 * (counter.now - counter0))


class TestClockCoreFaultsAndBounds(unittest.TestCase):
    def test_one_tick_regression_is_clamped(self):
        core, counter = make_core()
        _, _ = core.read()
        counter.now = 1999
        status, snap = core.read()
        # The QPC one-tick ambiguity is absorbed: anchor kept, no fault.
        self.assertEqual(status, ClockStatus.OK)
        self.assertEqual(snap.qpc, 2000)
        self.assertEqual(snap.raw_anchor, 2000)

    def test_multi_tick_regression_is_sticky(self):
        core, counter = make_core()
        counter.now = 1998
        status, snap = core.read()
        self.assertEqual(status, ClockStatus.REGRESSION)
        self.assertEqual(snap.fault, ClockStatus.REGRESSION)
        counter.now = 5000
        status, snap = core.read()
        # Sticky fault: the last valid outputs are retained, nothing is
        # re-sampled or silently recovered.
        self.assertEqual(status, ClockStatus.REGRESSION)
        self.assertEqual(snap.qpc, 2000)
        self.assertEqual(snap.fault, ClockStatus.REGRESSION)

    def test_raw_sample_failure_is_sticky(self):
        core, counter = make_core()
        counter.fail = True
        status, snap = core.read()
        self.assertEqual(status, ClockStatus.RAW_SAMPLE_FAILED)
        self.assertEqual(snap.qpc, 2000)
        counter.fail = False
        counter.now = 5000
        status, snap = core.read()
        self.assertEqual(status, ClockStatus.RAW_SAMPLE_FAILED)
        self.assertEqual(snap.qpc, 2000)

    def test_overflow_at_initialization_raises(self):
        counter = FakeCounter(now=INT64_MAX)
        config = ClockConfig(
            frequency=1,
            qpc_origin=0,
            initial_raw_qpc=INT64_MAX,
            tick64_origin=UINT64_MAX - 1,
            tick64_capture_qpc=0,
            multimedia_origin=0,
            multimedia_capture_qpc=0,
            raw_counter=counter,
        )
        with self.assertRaises(ClockOverflow):
            ClockCore(config)

    def test_ticks_to_ms_matches_reference(self):
        cases = [
            ((0, FREQ), 0),
            ((999, FREQ), 999),
            ((1000, FREQ), 1000),
            ((1999, FREQ), 1999),
            ((1000, 3), 333333),
            ((2, 3), 666),
        ]
        for (ticks, frequency), expected in cases:
            with self.subTest(ticks=ticks, frequency=frequency):
                self.assertEqual(ticks_to_ms(ticks, frequency), expected)
                # Same value as the arbitrary-precision reference used by the
                # fixture test.
                self.assertEqual(ticks_to_ms(ticks, frequency),
                                 ticks * 1000 // frequency)
        self.assertIsNone(ticks_to_ms(UINT64_MAX, 1))
        self.assertIsNone(ticks_to_ms(-1, FREQ))
        self.assertIsNone(ticks_to_ms(5, 0))
        self.assertIsNone(ticks_to_ms(1.5, FREQ))

    def test_bad_configs_refused(self):
        def config(**overrides):
            kwargs = dict(
                frequency=FREQ,
                qpc_origin=1000,
                initial_raw_qpc=2000,
                tick64_origin=10000,
                tick64_capture_qpc=1500,
                multimedia_origin=20000,
                multimedia_capture_qpc=1700,
                raw_counter=FakeCounter(now=2000),
            )
            kwargs.update(overrides)
            return ClockConfig(**kwargs)

        # The C core validates the configuration at clock initialization.
        with self.assertRaises(ClockBadInput):
            ClockCore(config(frequency=0))
        with self.assertRaises(ClockBadInput):
            ClockCore(config(qpc_origin=3000))
        with self.assertRaises(ClockBadInput):
            ClockCore(config(initial_raw_qpc=INT64_MAX + 1))
        with self.assertRaises(ClockBadInput):
            ClockCore(config(tick64_capture_qpc=3000))
        with self.assertRaises(ClockBadInput):
            ClockCore(config(tick64_capture_qpc=500))
        with self.assertRaises(ClockBadInput):
            ClockCore(config(multimedia_capture_qpc=500))
        with self.assertRaises(ClockBadInput):
            ClockCore(config(raw_counter=None))
        with self.assertRaises(ClockBadInput):
            ClockCore(config(), rate_max_ppm=0)
        with self.assertRaises(ClockBadInput):
            ClockCore(config(), rate_max_ppm=-5)

    def test_negative_and_over_profile_rate_refused(self):
        core, _ = make_core()
        status, snap = core.set_rate(1, -1, 1000)
        self.assertEqual(status, ClockStatus.BAD_INPUT)
        self.assertEqual(snap.owner, 0)
        self.assertEqual(snap.rate_ppm, RATE_ONE)
        status, snap = core.set_rate(1, RATE_MAX_CORE + 1, 1000)
        self.assertEqual(status, ClockStatus.BAD_INPUT)
        self.assertEqual(snap.rate_ppm, RATE_ONE)


class TestClockCoreOwnership(unittest.TestCase):
    def test_lease_expiry_reverts_to_one_x(self):
        core, counter = make_core()
        status, snap = core.set_rate(1, 2 * RATE_ONE, 2000)
        self.assertEqual(status, ClockStatus.OK)
        self.assertEqual(snap.lease_deadline, 4000)
        counter.now = 3999
        _, snap = core.read()
        self.assertEqual(snap.owner, 1)
        self.assertEqual(snap.rate_ppm, 2 * RATE_ONE)
        counter.now = 4000
        status, snap = core.read()
        self.assertEqual(status, ClockStatus.OK)
        # Old rate applied up to the deadline, then 1x; owner released.
        self.assertEqual(snap.qpc, 6000)
        self.assertEqual(snap.owner, 0)
        self.assertEqual(snap.rate_ppm, RATE_ONE)
        self.assertEqual(snap.lease_deadline, 0)

    def test_owner_conflict_visible(self):
        core, counter = make_core()
        status, _ = core.set_rate(10, 2 * RATE_ONE, 2000)
        self.assertEqual(status, ClockStatus.OK)
        status, snap = core.set_rate(11, 3 * RATE_ONE, 2000)
        self.assertEqual(status, ClockStatus.OWNER_CONFLICT)
        self.assertEqual(snap.owner, 10)
        self.assertEqual(snap.rate_ppm, 2 * RATE_ONE)
        counter.now = 2500
        status, snap = core.renew(10, 2000)
        self.assertEqual(status, ClockStatus.OK)
        self.assertEqual(snap.owner, 10)

    def test_stale_owner_refused_after_close(self):
        core, _ = make_core()
        status, _ = core.set_rate(5, 2 * RATE_ONE, 1000)
        self.assertEqual(status, ClockStatus.OK)
        status, _ = core.close(5)
        self.assertEqual(status, ClockStatus.OK)
        status, snap = core.set_rate(3, 2 * RATE_ONE, 1000)
        self.assertEqual(status, ClockStatus.STALE_OWNER)
        self.assertEqual(snap.owner, 0)
        status, _ = core.renew(3, 1000)
        self.assertEqual(status, ClockStatus.STALE_OWNER)
        status, snap = core.set_rate(6, 2 * RATE_ONE, 1000)
        self.assertEqual(status, ClockStatus.OK)
        self.assertEqual(snap.owner, 6)

    def test_close_preserves_accumulated_offset_at_one_x(self):
        core, counter = make_core()
        status, _ = core.set_rate(1, 3 * RATE_ONE, 30000)
        self.assertEqual(status, ClockStatus.OK)
        counter.now = 3000
        status, snap = core.read()
        self.assertEqual(status, ClockStatus.OK)
        self.assertEqual(snap.qpc, 5000)
        status, snap = core.close(1)
        self.assertEqual(status, ClockStatus.OK)
        self.assertEqual(snap.owner, 0)
        self.assertEqual(snap.rate_ppm, RATE_ONE)
        self.assertEqual(snap.qpc, 5000)
        counter.now = 4000
        status, snap = core.read()
        self.assertEqual(status, ClockStatus.OK)
        # The 3x offset accumulated before close persists at 1x afterwards.
        self.assertEqual(snap.qpc, 6000)

    def test_lease_window_bounds(self):
        core, _ = make_core()
        status, _ = core.set_rate(1, 2 * RATE_ONE, FREQ * 30)
        self.assertEqual(status, ClockStatus.OK)
        status, _ = core.set_rate(1, 2 * RATE_ONE, FREQ * 30 + 1)
        self.assertEqual(status, ClockStatus.BAD_INPUT)
        status, _ = core.set_rate(1, 2 * RATE_ONE, 0)
        self.assertEqual(status, ClockStatus.BAD_INPUT)

    def test_absolute_deadline_rules(self):
        core, _ = make_core()
        # not_after must be positive and inside the lease window.
        status, _ = core.set_rate_until(1, 2 * RATE_ONE, 5000, 4000)
        self.assertEqual(status, ClockStatus.BAD_INPUT)
        status, _ = core.set_rate_until(1, 2 * RATE_ONE, 0, 4000)
        self.assertEqual(status, ClockStatus.BAD_INPUT)
        # Deadline already at/past the current raw sample.
        status, _ = core.set_rate_until(1, 2 * RATE_ONE, 2000, 2000)
        self.assertEqual(status, ClockStatus.BAD_INPUT)
        # Renewal (operation 4) without an active lease is a stale owner:
        # the C core only admits renew when that owner already holds it.
        status, _ = core.renew_until(1, 2000, 3000)
        self.assertEqual(status, ClockStatus.STALE_OWNER)
        # Happy path: relative lease first, then absolute renewal keeps rate.
        status, snap = core.set_rate(1, 2 * RATE_ONE, 1000)
        self.assertEqual(status, ClockStatus.OK)
        status, snap = core.renew_until(1, 2500, 3500)
        self.assertEqual(status, ClockStatus.OK)
        self.assertEqual(snap.lease_deadline, 3500)
        self.assertEqual(snap.rate_ppm, 2 * RATE_ONE)

    def test_x20_rate_refused_by_default_profile(self):
        core, _ = make_core()
        status, snap = core.set_rate(1, 20 * RATE_ONE, 1000)
        # Visible refusal, never a silent clamp: state is untouched.
        self.assertEqual(status, ClockStatus.BAD_INPUT)
        self.assertEqual(snap.owner, 0)
        self.assertEqual(snap.rate_ppm, RATE_ONE)

    def test_x20_rate_admitted_by_visible_profile_extension(self):
        counter = FakeCounter(now=2000)
        config = ClockConfig(
            frequency=FREQ,
            qpc_origin=1000,
            initial_raw_qpc=2000,
            tick64_origin=10000,
            tick64_capture_qpc=1500,
            multimedia_origin=20000,
            multimedia_capture_qpc=1700,
            raw_counter=counter,
        )
        core = ClockCore(config, rate_max_ppm=20 * RATE_ONE)
        status, snap = core.set_rate(1, 20 * RATE_ONE, 1000)
        self.assertEqual(status, ClockStatus.OK)
        self.assertEqual(snap.rate_ppm, 20 * RATE_ONE)
        counter.now = 3000
        status, snap = core.read()
        self.assertEqual(status, ClockStatus.OK)
        self.assertEqual(snap.qpc, 22000)


class TestClockGateway(unittest.TestCase):
    """Command/ACK/fence model of the owned adapter v2 surface."""

    def _gateway(self, rate_max_ppm=RATE_MAX_CORE):
        core, counter = make_core(rate_max_ppm=rate_max_ppm)
        return core, counter, make_gateway(core, counter)

    def test_submit_ack_roundtrip_applies_rate(self):
        core, counter, gw = self._gateway()
        self.assertEqual(
            gw.submit(command(1, 10, COMMAND_SET_RATE, 2 * RATE_ONE,
                              not_after=3000, lease=4000)),
            GatewayStatus.OK)
        self.assertEqual(gw.slot, 'READY')
        gw.tick()
        ack = gw.take_ack()
        self.assertIsNotNone(ack)
        self.assertEqual(gw.slot, 'EMPTY')
        self.assertEqual(ack.sequence, 1)
        self.assertEqual(ack.owner, 10)
        self.assertEqual(ack.operation, COMMAND_SET_RATE)
        self.assertEqual(ack.clock_status, int(ClockStatus.OK))
        self.assertEqual(ack.disposition, ACK_TRANSITION)
        self.assertTrue(ack.snapshot_valid)
        self.assertEqual(ack.snapshot.owner, 10)
        self.assertEqual(ack.snapshot.rate_ppm, 2 * RATE_ONE)
        self.assertEqual(ack.snapshot.lease_deadline, 4000)
        self.assertEqual(ack.snapshot.qpc, 2000)
        self.assertEqual(core.owner, 10)
        self.assertEqual(core.rate_ppm, 2 * RATE_ONE)

    def test_lost_ack_keeps_slot_busy_with_no_retry(self):
        core, counter, gw = self._gateway()
        self.assertEqual(gw.submit(command(1, 10, COMMAND_SET_RATE, 2 * RATE_ONE,
                                           not_after=3000, lease=4000)),
                         GatewayStatus.OK)
        gw.tick()  # publishes the ACK; the slot is now occupied by the ACK
        # A lost ACK is visible: the single slot stays occupied and there is
        # no retry, replay or re-apply path until the ACK is claimed.
        self.assertEqual(
            gw.submit(command(2, 11, COMMAND_SET_RATE, 2 * RATE_ONE,
                              not_after=3000, lease=4000)),
            GatewayStatus.BUSY)
        ack = gw.take_ack()
        self.assertEqual(ack.sequence, 1)
        self.assertEqual(gw.slot, 'EMPTY')
        # Forward progress is admitted again once the slot is free.
        self.assertEqual(gw.submit(command(2, 11, COMMAND_SET_RATE, 2 * RATE_ONE,
                                           not_after=3000, lease=4000)),
                         GatewayStatus.OK)

    def test_stale_sequence_refused(self):
        core, counter, gw = self._gateway()
        self.assertEqual(gw.submit(command(1, 10, COMMAND_SET_RATE, 2 * RATE_ONE,
                                           not_after=3000, lease=4000)),
                         GatewayStatus.OK)
        gw.tick()
        self.assertIsNotNone(gw.take_ack())
        self.assertEqual(
            gw.submit(command(1, 11, COMMAND_SET_RATE, 2 * RATE_ONE,
                              not_after=3000, lease=4000)),
            GatewayStatus.STALE_SEQUENCE)
        self.assertEqual(gw.slot, 'EMPTY')
        self.assertEqual(gw.submit(command(2, 11, COMMAND_SET_RATE, 2 * RATE_ONE,
                                           not_after=3000, lease=4000)),
                         GatewayStatus.OK)

    def test_fence_is_checked_before_slot_occupancy(self):
        # C submit_impl order: the owner fence is refused before the slot
        # occupancy check, so a fenced owner sees FENCED_OWNER, not BUSY.
        core, counter, gw = self._gateway()
        self.assertEqual(gw.submit(command(1, 20, COMMAND_SET_RATE, 2 * RATE_ONE,
                                           not_after=3000, lease=4000)),
                         GatewayStatus.OK)
        fence, drained = gw.cancel(10)
        self.assertEqual((fence, drained), (10, 0))
        self.assertEqual(gw.slot, 'READY')  # unrelated command stays pending
        self.assertEqual(
            gw.submit(command(2, 10, COMMAND_SET_RATE, 2 * RATE_ONE,
                              not_after=3000, lease=4000)),
            GatewayStatus.FENCED_OWNER)
        self.assertEqual(
            gw.submit(command(3, 30, COMMAND_SET_RATE, 2 * RATE_ONE,
                              not_after=3000, lease=4000)),
            GatewayStatus.BUSY)

    def test_expired_at_consume_fences_owner(self):
        core, counter, gw = self._gateway()
        self.assertEqual(gw.submit(command(1, 7, COMMAND_SET_RATE, 2 * RATE_ONE,
                                           not_after=2500, lease=3500)),
                         GatewayStatus.OK)
        counter.now = 3000
        gw.tick()
        ack = gw.take_ack()
        self.assertEqual(ack.disposition, ACK_EXPIRED)
        self.assertEqual(ack.clock_status, int(ClockStatus.STALE_OWNER))
        self.assertFalse(ack.snapshot_valid)
        self.assertIsNone(ack.snapshot)
        self.assertEqual(gw.fence_status(), (7, 0))
        # The command was never consumed: core state is untouched.
        self.assertEqual(core.owner, 0)
        self.assertEqual(core.rate_ppm, RATE_ONE)

    def test_cancel_drains_ready_command(self):
        core, counter, gw = self._gateway()
        self.assertEqual(gw.submit(command(1, 10, COMMAND_SET_RATE, 2 * RATE_ONE,
                                           not_after=3000, lease=4000)),
                         GatewayStatus.OK)
        fence, drained = gw.cancel(10)
        self.assertEqual((fence, drained), (10, 1))
        self.assertEqual(gw.slot, 'ACK')
        self.assertEqual(core.owner, 0)  # never applied
        ack = gw.take_ack()
        self.assertEqual(ack.disposition, ACK_CANCELLED_PENDING)
        self.assertEqual(ack.clock_status, int(ClockStatus.STALE_OWNER))
        self.assertFalse(ack.snapshot_valid)
        # The retired generation cannot submit fresh intent afterwards.
        self.assertEqual(gw.submit(command(2, 10, COMMAND_SET_RATE, 2 * RATE_ONE,
                                           not_after=3000, lease=4000)),
                         GatewayStatus.FENCED_OWNER)

    def test_cancel_without_pending_only_fences(self):
        core, counter, gw = self._gateway()
        fence, drained = gw.cancel(5)
        self.assertEqual((fence, drained), (5, 0))
        self.assertEqual(gw.slot, 'EMPTY')
        self.assertEqual(gw.submit(command(1, 5, COMMAND_SET_RATE, 2 * RATE_ONE,
                                           not_after=3000, lease=4000)),
                         GatewayStatus.FENCED_OWNER)
        with self.assertRaises(ClockBadInput):
            gw.cancel(0)

    def test_fenced_owner_close_still_passes(self):
        core, counter, gw = self._gateway()
        self.assertEqual(gw.submit(command(1, 4, COMMAND_SET_RATE, 2 * RATE_ONE,
                                           not_after=3000, lease=4000)),
                         GatewayStatus.OK)
        gw.tick()
        self.assertIsNotNone(gw.take_ack())
        self.assertEqual(core.owner, 4)
        fence, drained = gw.cancel(4)
        self.assertEqual((fence, drained), (4, 0))
        self.assertEqual(
            gw.submit(command(2, 4, COMMAND_SET_RATE, 2 * RATE_ONE,
                              not_after=3000, lease=4000)),
            GatewayStatus.FENCED_OWNER)
        # Only the owner's own CLOSE (retirement) passes the fence.
        self.assertEqual(gw.submit(command(3, 4, COMMAND_CLOSE,
                                           not_after=3000, lease=0)),
                         GatewayStatus.OK)
        gw.tick()
        ack = gw.take_ack()
        self.assertEqual(ack.disposition, ACK_TRANSITION)
        self.assertEqual(ack.clock_status, int(ClockStatus.OK))
        self.assertTrue(ack.snapshot_valid)
        self.assertEqual(ack.snapshot.owner, 0)
        self.assertEqual(ack.snapshot.rate_ppm, RATE_ONE)
        # Lower generations are both fenced and stale in the core.
        self.assertEqual(gw.submit(command(4, 3, COMMAND_SET_RATE, 2 * RATE_ONE,
                                           not_after=3000, lease=4000)),
                         GatewayStatus.FENCED_OWNER)

    def test_owner_conflict_visible_through_gateway(self):
        core, counter, gw = self._gateway()
        self.assertEqual(gw.submit(command(1, 10, COMMAND_SET_RATE, 2 * RATE_ONE,
                                           not_after=3000, lease=4000)),
                         GatewayStatus.OK)
        gw.tick()
        self.assertIsNotNone(gw.take_ack())
        # A second owner is admitted by the adapter; the conflict is visible
        # in the ACK, and the first owner's state is preserved.
        self.assertEqual(gw.submit(command(2, 20, COMMAND_SET_RATE, 3 * RATE_ONE,
                                           not_after=3000, lease=4000)),
                         GatewayStatus.OK)
        gw.tick()
        ack = gw.take_ack()
        self.assertEqual(ack.disposition, ACK_TRANSITION)
        self.assertEqual(ack.clock_status, int(ClockStatus.OWNER_CONFLICT))
        self.assertTrue(ack.snapshot_valid)
        self.assertEqual(ack.snapshot.owner, 10)
        self.assertEqual(ack.snapshot.rate_ppm, 2 * RATE_ONE)
        self.assertEqual(core.owner, 10)

    def test_core_fault_blocks_and_no_retry(self):
        # Sticky core fault: every new submission is visibly refused.
        core, counter, gw = self._gateway()
        counter.fail = True
        status, _ = core.read()
        self.assertEqual(status, ClockStatus.RAW_SAMPLE_FAILED)
        counter.fail = False
        self.assertEqual(gw.submit(command(1, 10, COMMAND_SET_RATE, 2 * RATE_ONE,
                                           not_after=3000, lease=4000)),
                         GatewayStatus.CLOCK_FAULT)
        # Platform fault during consumption: the ACK is visible, the slot is
        # not retried, and the gateway faults for good.
        core2, counter2, gw2 = self._gateway()
        self.assertEqual(gw2.submit(command(1, 10, COMMAND_SET_RATE, 2 * RATE_ONE,
                                            not_after=3000, lease=4000)),
                         GatewayStatus.OK)
        counter2.fail = True
        gw2.tick()
        ack = gw2.take_ack()
        self.assertEqual(ack.disposition, ACK_PLATFORM_FAULT)
        self.assertEqual(ack.clock_status, int(ClockStatus.RAW_SAMPLE_FAILED))
        self.assertFalse(ack.snapshot_valid)
        self.assertTrue(gw2.fault)
        self.assertEqual(gw2.submit(command(2, 11, COMMAND_SET_RATE, 2 * RATE_ONE,
                                            not_after=3000, lease=4000)),
                         GatewayStatus.CLOCK_FAULT)

    def test_bad_commands_refused(self):
        core, counter, gw = self._gateway()
        bad = [
            'not a command',
            command(1, 0, COMMAND_SET_RATE, 2 * RATE_ONE),
            command(0, 10, COMMAND_SET_RATE, 2 * RATE_ONE),
            command(1, 10, 99, 2 * RATE_ONE),
            command(1, 10, COMMAND_RENEW, 1),
            command(1, 10, COMMAND_CLOSE, not_after=3000, lease=5),
            command(1, 10, COMMAND_SET_RATE, 2 * RATE_ONE,
                    not_after=4000, lease=3000),
            command(1, 10, COMMAND_SET_RATE, 2 * RATE_ONE, not_after=0, lease=4000),
        ]
        for value in bad:
            with self.subTest(value=value):
                self.assertEqual(gw.submit(value), GatewayStatus.BAD_INPUT)
        self.assertEqual(gw.slot, 'EMPTY')

    def test_profile_refusal_and_extension_through_gateway(self):
        core, counter, gw = self._gateway()  # default x16 profile
        self.assertEqual(gw.submit(command(1, 10, COMMAND_SET_RATE, 20 * RATE_ONE,
                                           not_after=3000, lease=4000)),
                         GatewayStatus.BAD_INPUT)
        self.assertEqual(gw.slot, 'EMPTY')
        core20, counter20, gw20 = self._gateway(rate_max_ppm=20 * RATE_ONE)
        self.assertEqual(gw20.submit(command(1, 10, COMMAND_SET_RATE, 20 * RATE_ONE,
                                            not_after=3000, lease=4000)),
                         GatewayStatus.OK)
        gw20.tick()
        ack = gw20.take_ack()
        self.assertEqual(ack.clock_status, int(ClockStatus.OK))
        self.assertEqual(ack.snapshot.rate_ppm, 20 * RATE_ONE)
        self.assertEqual(core20.rate_ppm, 20 * RATE_ONE)

    def test_snapshot_schema(self):
        core, counter, gw = self._gateway()
        snap = gw.snapshot()
        self.assertEqual(snap['schema'], 'ct2trainer-clock-gateway/v1')
        self.assertEqual(snap['slot'], 'EMPTY')
        self.assertEqual(snap['last_sequence'], 0)
        self.assertEqual(snap['owner_fence'], 0)
        self.assertEqual(snap['retired_fence'], 0)
        self.assertFalse(snap['fault'])
        self.assertEqual(snap['core_owner'], 0)
        self.assertEqual(snap['core_rate_ppm'], RATE_ONE)
        self.assertEqual(snap['core_fault'], 0)


if __name__ == "__main__":
    unittest.main()
