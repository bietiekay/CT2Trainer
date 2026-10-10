"""Bounded value-scan session model: modes, limits, stale identity, wildcards."""
import struct
import unittest

from ct2trainer.native.scan_plan import (
    InvalidScanParameterError,
    InvalidTransitionError,
    ReadByteLimitRefused,
    RegionLimitRefused,
    ResultLimitRefused,
    ScanLimits,
    ScanSession,
    StaleSnapshotRejected,
    TargetIdentity,
    TargetRegions,
    TimeLimitRefused,
    WildcardWriteRefused,
    assert_write_value,
    pattern_has_wildcard,
)
from ct2trainer.native.scan_plan import _KINDS


def _identity(pid=4242, created=100):
    return TargetIdentity(pid, created)


def _limits(**overrides):
    options = {'max_regions': 4, 'max_results': 100, 'max_read_bytes': 10000,
               'time_budget': 5.0}
    options.update(overrides)
    return ScanLimits(**options)


def _backend(kind, values):
    """Backend over a value map; unmatched addresses read as zero."""
    size, code = _KINDS[kind]
    zero = 0.0 if code[-1] == 'd' else (0.0 if code[-1] == 'f' else 0)

    def backend(address, size2):
        assert size2 == size
        value = values.get(address, zero)
        return struct.pack(code, value)

    return backend


def _clock(values):
    """Returns each value once, then holds the last one."""
    values = list(values)
    state = {'index': 0}

    def clock():
        value = values[state['index']]
        if state['index'] + 1 < len(values):
            state['index'] += 1
        return value

    return clock


class FirstScanTests(unittest.TestCase):
    def test_first_exact_finds_all_matches_and_arm_session(self):
        session = ScanSession(_identity(), TargetRegions([(0x1000, 0x1100)], 8), _limits())
        snapshot = session.first_exact('int', 42, [(0x1000, 0x1100)],
                                       _backend('int', {0x1000: 42, 0x1004: 42, 0x1008: 7}),
                                       _identity())
        self.assertEqual(session.state, 'armed')
        self.assertEqual(len(snapshot), 2)
        self.assertEqual(snapshot.candidates, ((0x1000, 42), (0x1004, 42)))
        self.assertEqual(snapshot.kind, 'int')
        self.assertEqual(snapshot.pointer_size, 8)
        self.assertEqual(snapshot.scan_index, 1)

    def test_first_exact_without_matches_stays_armed_with_kind(self):
        session = ScanSession(_identity(), TargetRegions([(0x1000, 0x1010)], 4), _limits())
        snapshot = session.first_exact('int', 42, [(0x1000, 0x1010)], _backend('int', {}), _identity())
        self.assertEqual(session.state, 'armed')
        self.assertEqual(len(snapshot), 0)
        self.assertEqual(snapshot.kind, 'int')
        self.assertEqual(snapshot.pointer_size, 4)

    def test_first_exact_rejects_values_that_do_not_fit_the_kind(self):
        session = ScanSession(_identity(), TargetRegions([(0x1000, 0x1010)], 8), _limits())
        regions = [(0x1000, 0x1010)]
        with self.assertRaisesRegex(InvalidScanParameterError, 'does not fit'):
            session.first_exact('byte', 300, regions, _backend('byte', {}), _identity())
        with self.assertRaisesRegex(InvalidScanParameterError, 'does not fit'):
            session.first_exact('int', -2**31 - 1, regions, _backend('int', {}), _identity())
        with self.assertRaisesRegex(InvalidScanParameterError, 'must be a number'):
            session.first_exact('int', True, regions, _backend('int', {}), _identity())

    def test_first_exact_rejects_unknown_kind_and_second_scan(self):
        session = ScanSession(_identity(), TargetRegions([(0x1000, 0x1010)], 8), _limits())
        regions = [(0x1000, 0x1010)]
        with self.assertRaisesRegex(InvalidScanParameterError, 'Unknown value kind'):
            session.first_exact('bogus', 1, regions, _backend('int', {}), _identity())
        session.first_exact('int', 1, regions, _backend('int', {}), _identity())
        with self.assertRaises(InvalidTransitionError):
            session.first_exact('int', 2, regions, _backend('int', {}), _identity())


class RefinementModeTests(unittest.TestCase):
    def _session_with_values(self, values):
        session = ScanSession(_identity(), TargetRegions([(0x1000, 0x1100)], 8), _limits())
        backend = _backend('int', dict(values))
        session.first_exact('int', 42, [(0x1000, 0x1100)], backend, _identity())
        return session, backend

    def test_numeric_modes_partition_candidates(self):
        session, _ = self._session_with_values({0x1000: 42, 0x1004: 42, 0x1008: 42})
        live = {0x1000: 42, 0x1004: 43, 0x1008: 41}
        backend = _backend('int', live)
        self.assertEqual([a for a, _ in session.numeric('changed', backend, _identity()).candidates],
                         [0x1004, 0x1008])
        session2, _ = self._session_with_values({0x1000: 42, 0x1004: 42, 0x1008: 42})
        self.assertEqual([a for a, _ in session2.numeric('unchanged', _backend('int', live), _identity()).candidates],
                         [0x1000])
        session3, _ = self._session_with_values({0x1000: 42, 0x1004: 42, 0x1008: 42})
        self.assertEqual([a for a, _ in session3.numeric('greater', _backend('int', live), _identity()).candidates],
                         [0x1004])
        session4, _ = self._session_with_values({0x1000: 42, 0x1004: 42, 0x1008: 42})
        self.assertEqual([a for a, _ in session4.numeric('less', _backend('int', live), _identity()).candidates],
                         [0x1008])

    def test_numeric_before_first_scan_is_refused(self):
        session = ScanSession(_identity(), TargetRegions([(0x1000, 0x1100)], 8), _limits())
        with self.assertRaises(InvalidTransitionError):
            session.numeric('changed', _backend('int', {}), _identity())

    def test_numeric_rejects_unknown_mode(self):
        session, _ = self._session_with_values({0x1000: 42})
        with self.assertRaisesRegex(InvalidScanParameterError, 'Numeric mode'):
            session.numeric('same', _backend('int', {}), _identity())

    def test_fuzzy_keeps_values_within_delta_exclusive_of_beyond(self):
        initial = {0x1000: 10, 0x1004: 10, 0x1008: 10}
        live = {0x1000: 10, 0x1004: 12, 0x1008: 15}
        session = ScanSession(_identity(), TargetRegions([(0x1000, 0x1100)], 8), _limits())
        session.first_exact('int', 10, [(0x1000, 0x1100)], _backend('int', initial), _identity())
        snapshot = session.fuzzy(10, 2, _backend('int', live), _identity())
        self.assertEqual([a for a, _ in snapshot.candidates], [0x1000, 0x1004])
        session2 = ScanSession(_identity(), TargetRegions([(0x1000, 0x1100)], 8), _limits())
        session2.first_exact('int', 10, [(0x1000, 0x1100)], _backend('int', initial), _identity())
        snapshot2 = session2.fuzzy(10, 1.5, _backend('int', live), _identity())
        self.assertEqual([a for a, _ in snapshot2.candidates], [0x1000])

    def test_fuzzy_rejects_invalid_deltas_and_references(self):
        session, _ = self._session_with_values({0x1000: 10})
        backend = _backend('int', {0x1000: 10})
        for bad in (0, -1, float('inf'), None, True):
            with self.subTest(delta=bad), self.assertRaisesRegex(InvalidScanParameterError, 'delta'):
                session.fuzzy(10, bad, backend, _identity())
        with self.assertRaisesRegex(InvalidScanParameterError, 'reference'):
            session.fuzzy('10', 1, backend, _identity())

    def test_nextscan_uses_current_values_against_given_reference(self):
        session, _ = self._session_with_values({0x1000: 42, 0x1004: 42, 0x1008: 42})
        snapshot = session.nextscan(42, _backend('int', {0x1000: 42, 0x1004: 42, 0x1008: 42}), _identity())
        self.assertEqual(len(snapshot), 3)
        session2, _ = self._session_with_values({0x1000: 42, 0x1004: 42, 0x1008: 42})
        snapshot2 = session2.nextscan(43, _backend('int', {0x1000: 43, 0x1004: 42, 0x1008: 42}), _identity())
        self.assertEqual([a for a, _ in snapshot2.candidates], [0x1000])

    def test_refinement_of_empty_candidate_set_stays_empty_not_refused(self):
        session = ScanSession(_identity(), TargetRegions([(0x1000, 0x1010)], 8), _limits())
        session.first_exact('int', 42, [(0x1000, 0x1010)], _backend('int', {}), _identity())
        self.assertEqual(len(session.numeric('unchanged', _backend('int', {}), _identity())), 0)
        self.assertEqual(len(session.fuzzy(42, 1, _backend('int', {}), _identity())), 0)
        self.assertEqual(len(session.nextscan(42, _backend('int', {}), _identity())), 0)


class StaleIdentityTests(unittest.TestCase):
    def _armed(self):
        session = ScanSession(_identity(), TargetRegions([(0x1000, 0x1100)], 8), _limits())
        session.first_exact('int', 42, [(0x1000, 0x1100)],
                            _backend('int', {0x1000: 42}), _identity())
        return session

    def test_pid_change_refuses_and_preserves_session_state(self):
        session = self._armed()
        with self.assertRaises(StaleSnapshotRejected):
            session.numeric('unchanged', _backend('int', {0x1000: 42}), TargetIdentity(4243, 100))
        self.assertEqual(session.state, 'armed')
        self.assertEqual(len(session.last_snapshot()), 1)
        self.assertEqual(len(session.numeric('unchanged', _backend('int', {0x1000: 42}), _identity())), 1)

    def test_creation_time_change_refuses(self):
        session = self._armed()
        with self.assertRaises(StaleSnapshotRejected):
            session.numeric('changed', _backend('int', {}), TargetIdentity(4242, 101))

    def test_identity_requires_positive_integers(self):
        for bad in ((0, 100), (42, 0), (-1, 100), (42, -1), (True, 100), (42, True)):
            with self.subTest(bad=bad), self.assertRaises(InvalidScanParameterError):
                TargetIdentity(*bad)


class LimitTests(unittest.TestCase):
    def _session(self, **limit_overrides):
        return ScanSession(_identity(), TargetRegions([(0x1000, 0x1100)], 8), _limits(**limit_overrides))

    def test_result_limit_refuses_instead_of_truncating(self):
        session = self._session(max_results=1)
        with self.assertRaisesRegex(ResultLimitRefused, 'exceeded'):
            session.first_exact('int', 42, [(0x1000, 0x1100)],
                                _backend('int', {0x1000: 42, 0x1004: 42, 0x1008: 42}), _identity())
        self.assertEqual(session.state, 'idle')
        snapshot = session.first_exact('int', 42, [(0x1000, 0x1100)],
                                       _backend('int', {0x1004: 42}), _identity())
        self.assertEqual(len(snapshot), 1)

    def test_read_byte_limit_counts_cumulatively_across_scans(self):
        session = self._session(max_read_bytes=12)
        backend = _backend('int', {0x1000: 42})
        session.first_exact('int', 42, [(0x1000, 0x1004)], backend, _identity())
        session.numeric('unchanged', backend, _identity())
        session.numeric('unchanged', backend, _identity())
        with self.assertRaises(ReadByteLimitRefused):
            session.numeric('unchanged', backend, _identity())

    def test_read_byte_limit_refuses_before_any_partial_result(self):
        session = self._session(max_read_bytes=3)
        with self.assertRaises(ReadByteLimitRefused):
            session.first_exact('int', 42, [(0x1000, 0x1100)], _backend('int', {0x1000: 42}), _identity())
        self.assertEqual(session.state, 'idle')

    def test_time_limit_refuses_before_and_after_reads(self):
        session = ScanSession(_identity(), TargetRegions([(0x1000, 0x1010)], 8),
                              _limits(time_budget=5.0), clock=_clock([0.0, 6.0]))
        with self.assertRaises(TimeLimitRefused):
            session.first_exact('int', 42, [(0x1000, 0x1010)], _backend('int', {}), _identity())
        session2 = ScanSession(_identity(), TargetRegions([(0x1000, 0x1010)], 8),
                               _limits(time_budget=5.0), clock=_clock([0.0, 0.0, 6.0]))
        with self.assertRaises(TimeLimitRefused):
            session2.first_exact('int', 42, [(0x1000, 0x1010)], _backend('int', {0x1000: 42}), _identity())
        self.assertEqual(session2.state, 'idle')

    def test_region_limit_refuses_before_any_read(self):
        session = self._session(max_regions=1)
        with self.assertRaises(RegionLimitRefused):
            session.first_exact('int', 42, [(0x1000, 0x1080), (0x1080, 0x1100)],
                                _backend('int', {}), _identity())
        self.assertEqual(session.state, 'idle')


class RegionAndWidthTests(unittest.TestCase):
    def test_scan_regions_must_stay_inside_allowed_regions(self):
        session = ScanSession(_identity(), TargetRegions([(0x1000, 0x1100)], 8), _limits())
        for bad in ((0x2000, 0x2100), (0x10F0, 0x1110), (0x1000, 0x1002), (0, 0x1100)):
            with self.subTest(bad=bad), self.assertRaises(InvalidScanParameterError):
                session.first_exact('int', 42, [bad], _backend('int', {}), _identity())

    def test_target_regions_reject_overlap_order_and_bad_bounds(self):
        cases = [([(0x1000, 0x1100), (0x10F0, 0x1200)], 'disjoint'),
                 ([(0x1100, 0x1200), (0x1000, 0x1100)], 'sorted'),
                 ([(0x1000, 0x1000), (0x1010, 0x1020)], 'empty'),
                 ([(0x1000, 0x1100), (0x2000, -1)], 'bounds'),
                 ([(0x1000,)], 'shape'),
                 ([(0x1000, 4352.5), (0x1200, 0x1300)], 'types')]
        for regions, label in cases:
            with self.subTest(label=label), self.assertRaises(InvalidScanParameterError):
                TargetRegions(regions, 8)

    def test_pointer_width_binds_address_limit(self):
        with self.assertRaises(InvalidScanParameterError):
            TargetRegions([(0x100000000, 0x100000100)], 4)
        TargetRegions([(0x1000, 0x100000000)], 4)
        with self.assertRaises(InvalidScanParameterError):
            TargetRegions([(0x8000000000000000, 0x8000000000000100)], 8)

    def test_invalid_pointer_size_refused(self):
        with self.assertRaises(InvalidScanParameterError):
            TargetRegions([(0x1000, 0x1100)], 6)


class TransitionTests(unittest.TestCase):
    def _armed(self):
        session = ScanSession(_identity(), TargetRegions([(0x1000, 0x1100)], 8), _limits())
        session.first_exact('int', 42, [(0x1000, 0x1100)], _backend('int', {0x1000: 42}), _identity())
        return session

    def test_finish_returns_last_snapshot_and_terminates(self):
        session = self._armed()
        snapshot = session.finish()
        self.assertEqual(snapshot, session.last_snapshot())
        self.assertEqual(session.state, 'done')
        with self.assertRaises(InvalidTransitionError):
            session.numeric('changed', _backend('int', {}), _identity())
        with self.assertRaises(InvalidTransitionError):
            session.abort()

    def test_abort_terminates_and_finish_requires_armed_state(self):
        session = ScanSession(_identity(), TargetRegions([(0x1000, 0x1100)], 8), _limits())
        with self.assertRaises(InvalidTransitionError):
            session.finish()
        session.abort()
        self.assertEqual(session.state, 'aborted')
        with self.assertRaises(InvalidTransitionError):
            session.first_exact('int', 1, [(0x1000, 0x1100)], _backend('int', {}), _identity())
        with self.assertRaises(InvalidTransitionError):
            session.abort()

    def test_backend_must_return_exactly_requested_bytes(self):
        session = self._armed()
        def bad_backend(address, size):
            return b'\x00'
        with self.assertRaises(InvalidScanParameterError):
            session.numeric('unchanged', bad_backend, _identity())
        self.assertEqual(session.state, 'armed')


class WildcardWriteBoundaryTests(unittest.TestCase):
    def test_wildcard_detection_is_conservative(self):
        for pattern in ('48 ? 89', '?', 'x', '*', '48 A? 89', 'Z8'):
            with self.subTest(pattern=pattern):
                self.assertTrue(pattern_has_wildcard(pattern))
        for pattern in ('48 89 8B', 'DE AD BE EF', '1', 'A8', '48 8B 48'):
            with self.subTest(pattern=pattern):
                self.assertFalse(pattern_has_wildcard(pattern))
        with self.assertRaises(InvalidScanParameterError):
            pattern_has_wildcard(48)

    def test_wildcard_pattern_is_never_a_write_value(self):
        with self.assertRaises(WildcardWriteRefused):
            assert_write_value(b'\x48\x89', '48 ? 89')
        with self.assertRaises(WildcardWriteRefused):
            assert_write_value(b'\x48\x89', '48 A? 89')
        self.assertEqual(assert_write_value(b'\x48\x89', '48 89 8B'), b'\x48\x89')
        self.assertEqual(assert_write_value(b'\x48\x89'), b'\x48\x89')
        with self.assertRaises(InvalidScanParameterError):
            assert_write_value(b'')
        with self.assertRaises(InvalidScanParameterError):
            assert_write_value('48 89')


class LimitValidationTests(unittest.TestCase):
    def test_limits_must_be_positive_and_finite(self):
        for overrides in ({'max_regions': 0}, {'max_results': -1}, {'max_read_bytes': 0},
                          {'time_budget': 0}, {'time_budget': float('inf')}, {'time_budget': True}):
            with self.subTest(overrides=overrides), self.assertRaises(InvalidScanParameterError):
                _limits(**overrides)


class SnapshotShapeTests(unittest.TestCase):
    def test_snapshots_are_immutable_sorted_and_indexed(self):
        session = ScanSession(_identity(), TargetRegions([(0x1000, 0x1100)], 8), _limits())
        first = session.first_exact('int', 42, [(0x1000, 0x1100)],
                                    _backend('int', {0x1008: 42, 0x1000: 42}), _identity())
        second = session.nextscan(42, _backend('int', {0x1008: 42, 0x1000: 42}), _identity())
        self.assertEqual(first.scan_index, 1)
        self.assertEqual(second.scan_index, 2)
        self.assertEqual(first.candidates, ((0x1000, 42), (0x1008, 42)))
        with self.assertRaises(TypeError):
            first.candidates[0] = (0, 0)


if __name__ == '__main__':
    unittest.main()
