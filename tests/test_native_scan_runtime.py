"""Contract tests for the four-mode value-scan runtime over a fake backend."""

import json
import struct
import unittest

from ct2trainer.native.patterns import pattern_matches
from ct2trainer.native.scan_runtime import (
    DEFAULT_ALLOWANCE_SECONDS,
    DEFAULT_MAX_READ_BYTES,
    DEFAULT_MAX_REGIONS,
    DEFAULT_MAX_RESULTS,
    AllowanceClockError,
    EmptySnapshotRefused,
    InvalidScanParameterError,
    InvalidTransitionError,
    PatternMalformedError,
    ReadByteLimitRefused,
    RegionLimitRefused,
    RegionShiftRefused,
    ResultLimitRefused,
    ScanAllowance,
    ScanHit,
    ScanRuntime,
    StaleTargetError,
    TimeLimitRefused,
    WildcardWriteRefused,
)


BASE = 0x1000
SIZE = 0x1000  # one 4 KiB fake page
REGION = (BASE, BASE + SIZE)


class FakeMemory:
    """Controllable memory backend with the ProcessMemory surface."""

    def __init__(self, *, pid=4242, created=100, alive=True, pointer_size=8,
                 page=bytes(SIZE)):
        self.buffer = bytearray(page)
        self.identity = (pid, created)
        self.pointer_size = pointer_size
        self._alive = alive
        self.read_calls = 0
        self.scan_calls = 0

    def set(self, address, data: bytes):
        self.buffer[address - BASE:address - BASE + len(data)] = data

    def is_alive(self):
        return self._alive

    def read(self, address, size):
        self.read_calls += 1
        if address < BASE or address + size > BASE + SIZE:
            raise OSError("read left the fake page")
        return bytes(self.buffer[address - BASE:address - BASE + size])

    def module(self, name):
        return (BASE, SIZE)

    def scan_matches(self, pattern, start=0, end=None, max_results=65536):
        self.scan_calls += 1
        tokens = pattern.split()
        length = len(tokens)
        end = end if end is not None else BASE + SIZE
        matches = []
        for address in range(max(start, BASE), min(end, BASE + SIZE) - length + 1):
            raw = bytes(self.buffer[address - BASE:address - BASE + length])
            if pattern_matches(pattern, raw):
                matches.append(address)
                if max_results and len(matches) > max_results:
                    raise OSError("Process scan exceeded its result bound; "
                                  "no partial results returned.")
        return sorted(matches[:max_results] if max_results else matches)


def pack(kind, value):
    return struct.pack({'byte': '<B', 'short': '<H', 'word': '<h', 'int': '<i',
                        'uint': '<I', 'float': '<f', 'qword': '<q',
                        'uint64': '<Q', 'double': '<d'}[kind], value)


def put_values(backend, kind, mapping):
    for address, value in mapping.items():
        backend.set(address, pack(kind, value))


class AttachAndShapeTests(unittest.TestCase):
    def test_attach_binds_identity_width_and_region_identity(self):
        backend = FakeMemory()
        runtime = ScanRuntime(backend, [REGION], pointer_size=8)
        self.assertEqual(runtime.state, 'idle')
        runtime.attach()
        self.assertEqual(runtime.state, 'attached')
        report = runtime.report()
        self.assertEqual(report['identity'], [4242, 100])
        self.assertEqual(report['pointer_size'], 8)
        self.assertEqual(report['state'], 'attached')

    def test_attach_refuses_dead_target(self):
        backend = FakeMemory(alive=False)
        runtime = ScanRuntime(backend, [REGION], pointer_size=8)
        with self.assertRaisesRegex(StaleTargetError, 'alive'):
            runtime.attach()
        self.assertEqual(runtime.state, 'idle')

    def test_attach_refuses_observed_identity_mismatch(self):
        backend = FakeMemory()
        runtime = ScanRuntime(backend, [REGION], pointer_size=8)
        with self.assertRaisesRegex(StaleTargetError, 'observed'):
            runtime.attach(observed=(4242, 101))
        self.assertEqual(runtime.state, 'idle')
        narrow = FakeMemory(pointer_size=4)
        runtime2 = ScanRuntime(narrow, [REGION], pointer_size=8)
        with self.assertRaisesRegex(InvalidScanParameterError, 'pointer width'):
            runtime2.attach()
        self.assertEqual(runtime2.state, 'idle')

    def test_pointer_width_and_allowed_region_validation(self):
        backend = FakeMemory()
        for bad in (6, 0, True):
            with self.subTest(pointer_size=bad):
                with self.assertRaisesRegex(InvalidScanParameterError,
                                            'Pointer size'):
                    ScanRuntime(backend, [REGION], pointer_size=bad)
        for regions in ((BASE, BASE + SIZE),  # not a tuple pair
                        [(BASE, BASE)],  # empty span
                        [(BASE + 0x10, BASE + 0x100), (BASE, BASE + 0x20)],  # unsorted
                        [(BASE, BASE + 0x10), (BASE + 0x8, BASE + 0x20)],  # overlap
                        [(0x8000000000000000, 0x8000000000000100)]):  # beyond 64-bit user space
            with self.subTest(regions=regions):
                with self.assertRaises(InvalidScanParameterError):
                    ScanRuntime(backend, regions, pointer_size=8)
        # Width-4 binding: addresses beyond the 32-bit space are refused.
        with self.assertRaises(InvalidScanParameterError):
            ScanRuntime(FakeMemory(pointer_size=4),
                        [(0x100000000, 0x100000100)], pointer_size=4)

    def test_default_allowance_matches_n35_cooperative_profile(self):
        allowance = ScanAllowance(clock=lambda: 0.0)
        self.assertEqual(allowance.seconds if hasattr(allowance, 'seconds')
                         else allowance._seconds, DEFAULT_ALLOWANCE_SECONDS)
        self.assertEqual(allowance.max_results, DEFAULT_MAX_RESULTS)
        self.assertEqual(allowance.max_read_bytes, DEFAULT_MAX_READ_BYTES)
        self.assertEqual(allowance.max_regions, DEFAULT_MAX_REGIONS)

    def test_allowance_validation_bounds(self):
        for kwargs in ({'seconds': 0.0}, {'seconds': 120.5}, {'seconds': float('inf')},
                       {'seconds': True}, {'max_results': 0},
                       {'max_results': 65537}, {'max_read_bytes': 0},
                       {'max_read_bytes': 128 * 1024 * 1024 + 1},
                       {'max_regions': 0}, {'max_regions': 65537}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaisesRegex(InvalidScanParameterError, 'allowance'):
                    ScanAllowance(clock=lambda: 0.0, **kwargs)
        with self.assertRaisesRegex(InvalidScanParameterError, 'clock'):
            ScanAllowance(clock=42)


class FirstExactTests(unittest.TestCase):
    def _runtime(self, **allowance):
        backend = FakeMemory()
        runtime = ScanRuntime(backend, [REGION], pointer_size=8, **allowance)
        runtime.attach()
        return backend, runtime

    def test_first_exact_finds_all_matches_with_hit_binding(self):
        backend, runtime = self._runtime()
        put_values(backend, 'int', {BASE: 42, BASE + 4: 42, BASE + 8: 7})
        snapshot = runtime.first_exact('int', 42, [REGION])
        self.assertEqual(runtime.state, 'armed')
        self.assertEqual(len(snapshot), 2)
        self.assertEqual([h.address for h in snapshot.hits], [BASE, BASE + 4])
        for index, hit in enumerate(snapshot.hits):
            self.assertEqual(hit.kind, 'int')
            self.assertEqual(hit.size, 4)
            self.assertEqual(hit.value, 42)
            self.assertEqual(hit.region, REGION)
            self.assertEqual(hit.region_index, 0)
            self.assertEqual(hit.snapshot_index, 1)
            self.assertEqual(hit.budget_ordinal, index)
            self.assertEqual(hit.budget_results_before, 0)
        # Stride-1 scan over 4 KiB: SIZE - 3 four-byte reads at any alignment.
        self.assertEqual(backend.read_calls, SIZE - 3)
        self.assertEqual(snapshot.read_bytes, backend.read_calls * 4)

    def test_first_exact_empty_result_stays_armed(self):
        backend, runtime = self._runtime()
        snapshot = runtime.first_exact('int', 42, [REGION])
        self.assertEqual(runtime.state, 'armed')
        self.assertEqual(len(snapshot), 0)
        self.assertEqual(snapshot.regions, (REGION,))

    def test_first_exact_value_must_fit_the_kind(self):
        backend, runtime = self._runtime()
        for kind, value in (('byte', 300), ('int', -2**31 - 1),
                            ('qword', 2**64)):
            with self.subTest(kind=kind):
                with self.assertRaisesRegex(InvalidScanParameterError,
                                            'does not fit'):
                    runtime.first_exact(kind, value, [REGION])
        for value in (True, '42', None):
            with self.subTest(value=value):
                with self.assertRaisesRegex(InvalidScanParameterError, 'number'):
                    runtime.first_exact('int', value, [REGION])
        with self.assertRaisesRegex(InvalidScanParameterError, 'Unknown value kind'):
            runtime.first_exact('bogus', 1, [REGION])
        self.assertEqual(runtime.state, 'attached')
        self.assertEqual(runtime.last_snapshot(), None)

    def test_second_first_scan_is_refused(self):
        backend, runtime = self._runtime()
        runtime.first_exact('int', 1, [REGION])
        with self.assertRaises(InvalidTransitionError):
            runtime.first_exact('int', 2, [REGION])

    def test_scan_regions_must_stay_inside_allowed_regions(self):
        backend, runtime = self._runtime()
        runtime.allowed_regions = ((BASE, BASE + 0x10), (BASE + 0x20, BASE + 0x30))
        for bad in ((BASE + 0x40, BASE + 0x50),  # outside both
                    (BASE, BASE + 0x24),        # straddles allowed boundary
                    (BASE - 4, BASE + 4),       # below page
                    (BASE, BASE + 2)):         # smaller than int kind
            with self.subTest(bad=bad):
                with self.assertRaises(InvalidScanParameterError):
                    runtime.first_exact('int', 1, [bad])
        # Multi-region scan spanning both allowed regions is accepted.
        runtime.first_exact('int', 1, [(BASE, BASE + 0x10), (BASE + 0x20, BASE + 0x30)])
        self.assertEqual(len(runtime.last_snapshot().regions), 2)

    def test_read_byte_limit_counts_cumulatively_and_refuses(self):
        backend, runtime = self._runtime(max_read_bytes=8)
        with self.assertRaises(ReadByteLimitRefused):
            runtime.first_exact('int', 1, [REGION])
        self.assertEqual(runtime.state, 'attached')
        self.assertEqual(runtime.last_snapshot(), None)

    def test_region_count_limit_refuses_before_any_read(self):
        backend, runtime = self._runtime(max_regions=1)
        with self.assertRaises(RegionLimitRefused):
            runtime.first_exact('int', 1,
                                [(BASE, BASE + 0x10), (BASE + 0x20, BASE + 0x30)])
        self.assertEqual(backend.read_calls, 0)
        self.assertEqual(runtime.state, 'attached')


class StaleTargetTests(unittest.TestCase):
    def _armed(self):
        backend = FakeMemory()
        put_values(backend, 'int', {BASE: 42})
        runtime = ScanRuntime(backend, [REGION], pointer_size=8)
        runtime.attach()
        runtime.first_exact('int', 42, [REGION])
        return backend, runtime

    def test_pid_change_refuses_and_keeps_old_snapshot(self):
        backend, runtime = self._armed()
        backend.identity = (4243, 100)
        with self.assertRaisesRegex(StaleTargetError, 'creation time'):
            runtime.numeric('changed')
        self.assertEqual(runtime.state, 'armed')
        self.assertEqual(len(runtime.last_snapshot()), 1)

    def test_created_time_change_refuses(self):
        backend, runtime = self._armed()
        backend.identity = (4242, 101)
        with self.assertRaisesRegex(StaleTargetError, 'creation time'):
            runtime.nextscan()

    def test_target_exit_refuses_all_continuations(self):
        backend, runtime = self._armed()
        backend._alive = False
        with self.assertRaisesRegex(StaleTargetError, 'alive'):
            runtime.numeric('unchanged')
        with self.assertRaisesRegex(StaleTargetError, 'alive'):
            runtime.numeric('changed')
        with self.assertRaisesRegex(StaleTargetError, 'alive'):
            runtime.nextscan()
        self.assertEqual(runtime.state, 'armed')


class RefinementModeTests(unittest.TestCase):
    def _armed(self, mapping, value=42):
        backend = FakeMemory()
        put_values(backend, 'int', mapping)
        runtime = ScanRuntime(backend, [REGION], pointer_size=8)
        runtime.attach()
        runtime.first_exact('int', value, [REGION])
        return backend, runtime

    def test_numeric_modes_partition_candidates(self):
        mapping = {BASE: 42, BASE + 4: 42, BASE + 8: 42}
        live = {BASE: 42, BASE + 4: 43, BASE + 8: 41}
        for mode, expected in (('changed', [BASE + 4, BASE + 8]),
                               ('unchanged', [BASE]),
                               ('greater', [BASE + 4]),
                               ('less', [BASE + 8])):
            backend, runtime = self._armed(dict(mapping))
            put_values(backend, 'int', live)
            snapshot = runtime.numeric(mode)
            self.assertEqual([h.address for h in snapshot.hits], expected, mode)

    def test_numeric_refinement_before_first_scan_refused(self):
        backend = FakeMemory()
        runtime = ScanRuntime(backend, [REGION], pointer_size=8)
        runtime.attach()
        with self.assertRaises(InvalidTransitionError):
            runtime.numeric('changed')
        with self.assertRaisesRegex(InvalidScanParameterError, 'Numeric mode'):
            runtime.numeric('same')

    def test_fuzzy_keeps_values_within_delta(self):
        backend, runtime = self._armed({BASE: 10, BASE + 4: 10, BASE + 8: 10},
                                       value=10)
        put_values(backend, 'int', {BASE: 12, BASE + 4: 15, BASE + 8: 10})
        snapshot = runtime.fuzzy(12, 2)
        # Inclusive boundary: BASE(12) is at distance 0 and BASE+8(10) is
        # exactly delta=2 away from the reference, so both are kept;
        # BASE+4(15) is beyond the window.
        self.assertEqual([h.address for h in snapshot.hits], [BASE, BASE + 8])
        # Re-refining the fuzzy result: both surviving hits stay inside.
        snapshot2 = runtime.fuzzy(12, 2)
        self.assertEqual([h.address for h in snapshot2.hits], [BASE, BASE + 8])
        # A value moving just outside the delta is dropped next.
        put_values(backend, 'int', {BASE: 12, BASE + 4: 15, BASE + 8: 9})
        snapshot3 = runtime.fuzzy(12, 2)
        self.assertEqual([h.address for h in snapshot3.hits], [BASE])
        backend2, runtime2 = self._armed({BASE: 10})
        for bad in (0, -1, float('inf'), None, True):
            with self.subTest(delta=bad):
                with self.assertRaisesRegex(InvalidScanParameterError, 'delta'):
                    runtime2.fuzzy(10, bad)
        with self.assertRaisesRegex(InvalidScanParameterError, 'reference'):
            runtime2.fuzzy('10', 1)

    def test_nextscan_keeps_only_values_changed_since_previous_snapshot(self):
        backend, runtime = self._armed({BASE: 42, BASE + 4: 42, BASE + 8: 42})
        put_values(backend, 'int', {BASE: 42, BASE + 4: 43, BASE + 8: 42})
        snapshot = runtime.nextscan()
        self.assertEqual([h.address for h in snapshot.hits], [BASE + 4])
        self.assertEqual(snapshot.mode, 'nextscan')
        # Nothing changed since that nextscan: nothing is reported again.
        self.assertEqual(len(runtime.nextscan()), 0)
        # The empty snapshot above is now the previous snapshot: nextscan
        # refuses it with a named reason instead of scanning against nothing.
        with self.assertRaises(EmptySnapshotRefused):
            runtime.nextscan()

    def test_nextscan_refuses_empty_previous_snapshot_with_named_reason(self):
        backend = FakeMemory()
        runtime = ScanRuntime(backend, [REGION], pointer_size=8)
        runtime.attach()
        runtime.first_exact('int', 42, [REGION])  # empty candidate set
        with self.assertRaises(EmptySnapshotRefused) as caught:
            runtime.nextscan()
        self.assertIn('non-empty previous snapshot', str(caught.exception))
        self.assertEqual(runtime.state, 'armed')

    def test_refinement_of_empty_snapshot_stays_empty_for_numeric_modes(self):
        backend = FakeMemory()
        runtime = ScanRuntime(backend, [REGION], pointer_size=8)
        runtime.attach()
        runtime.first_exact('int', 42, [REGION])
        self.assertEqual(len(runtime.numeric('unchanged')), 0)
        self.assertEqual(len(runtime.fuzzy(42, 1)), 0)


class RegionShiftTests(unittest.TestCase):
    def _armed_two_regions(self):
        backend = FakeMemory()
        allowed = [(BASE, BASE + 0x100), (BASE + 0x100, BASE + SIZE)]
        put_values(backend, 'int', {BASE: 42, BASE + 0x200: 42})
        runtime = ScanRuntime(backend, allowed, pointer_size=8)
        runtime.attach()
        snapshot = runtime.first_exact('int', 42, allowed)
        return backend, runtime, snapshot

    def test_explicit_region_shift_refuses_and_invalidates(self):
        backend, runtime, _ = self._armed_two_regions()
        with self.assertRaises(RegionShiftRefused) as caught:
            runtime.numeric('changed', regions=[(BASE, BASE + 0x100)])
        self.assertIn('rebased', str(caught.exception))
        self.assertEqual(runtime.state, 'invalidated')
        # Old hits are void: no continuation is possible from the old set.
        with self.assertRaises(InvalidTransitionError):
            runtime.numeric('changed')
        with self.assertRaises(InvalidTransitionError):
            runtime.nextscan()

    def test_identical_region_set_is_not_a_shift(self):
        backend, runtime, _ = self._armed_two_regions()
        snapshot = runtime.numeric('unchanged', regions=list(runtime.allowed_regions))
        self.assertEqual(len(snapshot), 2)
        self.assertEqual(runtime.state, 'armed')

    def test_shift_detected_even_if_region_ordering_implicit(self):
        backend, runtime, _ = self._armed_two_regions()
        # A superset of the previous scan region set is a shift, not a rebase.
        with self.assertRaises(RegionShiftRefused):
            runtime.fuzzy(42, 1, regions=[(BASE, BASE + SIZE)])
        self.assertEqual(runtime.state, 'invalidated')

    def test_snapshot_regions_are_bound_to_the_scan_that_created_them(self):
        backend, runtime, snapshot = self._armed_two_regions()
        self.assertEqual(snapshot.regions,
                         ((BASE, BASE + 0x100), (BASE + 0x100, BASE + SIZE)))
        hit = next(h for h in snapshot.hits if h.address == BASE + 0x200)
        self.assertEqual(hit.region, (BASE + 0x100, BASE + SIZE))
        self.assertEqual(hit.region_index, 1)


class AobFoundationTests(unittest.TestCase):
    def _attached(self):
        backend = FakeMemory()
        backend.set(BASE + 0x40, bytes.fromhex('AA BB CC'))
        backend.set(BASE + 0x60, bytes.fromhex('AA BB CC'))
        runtime = ScanRuntime(backend, [REGION], pointer_size=8)
        runtime.attach()
        return backend, runtime

    def test_aob_scan_uses_foundation_and_binds_hits(self):
        backend, runtime = self._attached()
        snapshot = runtime.aob('AA BB CC', [REGION])
        self.assertEqual([h.address for h in snapshot.hits], [BASE + 0x40, BASE + 0x60])
        for hit in snapshot.hits:
            self.assertEqual(hit.kind, 'aob')
            self.assertEqual(hit.size, 3)
            self.assertIsNone(hit.value)
            self.assertEqual(hit.region, REGION)
        self.assertEqual(snapshot.pattern, 'AA BB CC')
        self.assertFalse(snapshot.has_wildcard)
        self.assertFalse(runtime.wildcard_used)
        self.assertEqual(backend.scan_calls, 1)

    def test_aob_pattern_validation_and_wildcard_mark(self):
        backend, runtime = self._attached()
        snapshot = runtime.aob('aa ? cc', [REGION])
        self.assertEqual(snapshot.pattern, 'AA ?? CC')
        self.assertTrue(snapshot.has_wildcard)
        self.assertTrue(runtime.wildcard_used)
        with self.assertRaises(PatternMalformedError):
            runtime.aob('AA ZZ CC', [REGION])
        with self.assertRaises(PatternMalformedError):
            runtime.aob('?? ??', [REGION])  # entirely wildcard
        with self.assertRaises(PatternMalformedError):
            runtime.aob(42, [REGION])

    def test_aob_malformed_backend_matches_refused(self):
        backend, runtime = self._attached()

        class BadBackend:
            def __init__(self, inner, bad): self.inner, self.bad = inner, bad
            identity = property(lambda s: s.inner.identity)
            pointer_size = property(lambda s: s.inner.pointer_size)
            def is_alive(self): return True
            def read(self, a, n): return self.inner.read(a, n)
            def scan_matches(self, pattern, start=0, end=None, max_results=65536):
                return self.bad

        for bad in (BASE + 0x200,  # beyond the requested region end
                    [BASE + 0x40, BASE + 0x40],  # duplicate
                    'nope', 42):
            with self.subTest(bad=bad):
                broken = ScanRuntime(BadBackend(backend, bad), [REGION], pointer_size=8)
                broken.attach()
                with self.assertRaises(PatternMalformedError):
                    broken.aob('AA BB CC', [REGION])
                self.assertEqual(broken.state, 'attached')

    def test_aob_backend_result_bound_maps_to_named_refusal(self):
        backend = FakeMemory()
        # Tile the whole page with the literal pattern so the match count
        # (~SIZE / 3) exceeds the bound; overlapping single sets would not.
        backend.buffer[:] = bytes([0xAA, 0xBB, 0xCC][index % 3]
                                  for index in range(SIZE))
        runtime = ScanRuntime(backend, [REGION], pointer_size=8, max_results=100)
        runtime.attach()
        with self.assertRaises(ResultLimitRefused):
            runtime.aob('AA BB CC', [REGION])
        self.assertEqual(runtime.state, 'attached')


class WildcardWriteTests(unittest.TestCase):
    def _value_session(self):
        backend = FakeMemory()
        put_values(backend, 'int', {BASE: 42})
        runtime = ScanRuntime(backend, [REGION], pointer_size=8)
        runtime.attach()
        runtime.first_exact('int', 42, [REGION])
        return runtime

    def test_value_hit_yields_exact_packed_write_bytes(self):
        runtime = self._value_session()
        hit = runtime.last_snapshot().hits[0]
        self.assertEqual(runtime.to_write_bytes(hit), struct.pack('<i', 42))

    def test_aob_literal_pattern_yields_literal_bytes_only(self):
        backend = FakeMemory()
        backend.set(BASE + 0x40, bytes.fromhex('AA BB CC'))
        runtime = ScanRuntime(backend, [REGION], pointer_size=8)
        runtime.attach()
        runtime.aob('AA BB CC', [REGION])
        hit = runtime.last_snapshot().hits[0]
        self.assertEqual(runtime.to_write_bytes(hit), b'\xAA\xBB\xCC')

    def test_wildcard_aob_hit_is_never_a_write_value(self):
        backend = FakeMemory()
        backend.set(BASE + 0x40, bytes.fromhex('AA BB CC'))
        runtime = ScanRuntime(backend, [REGION], pointer_size=8)
        runtime.attach()
        runtime.aob('AA ? CC', [REGION])
        hit = runtime.last_snapshot().hits[0]
        with self.assertRaisesRegex(WildcardWriteRefused, 'never a write value'):
            runtime.to_write_bytes(hit)

    def test_wildcard_session_taints_all_later_writes(self):
        backend = FakeMemory()
        backend.set(BASE + 0x40, bytes.fromhex('AA BB CC'))
        put_values(backend, 'int', {BASE + 0x80: 7})
        runtime = ScanRuntime(backend, [REGION], pointer_size=8)
        runtime.attach()
        runtime.aob('AA ? CC', [REGION])
        value_hits = runtime.first_exact('int', 7, [REGION]).hits
        for hit in value_hits:
            with self.subTest(address=hit.address):
                with self.assertRaisesRegex(WildcardWriteRefused, 'wildcard'):
                    runtime.to_write_bytes(hit)

    def test_write_binding_rejects_foreign_or_uncommitted_hits(self):
        runtime = self._value_session()
        with self.assertRaises(InvalidScanParameterError):
            runtime.to_write_bytes('not a hit')
        forged = ScanHit(address=BASE, value=42, kind='int', size=4,
                         region=REGION, region_index=0, snapshot_index=1,
                         budget_ordinal=99, budget_results_before=0,
                         budget_read_bytes=0)
        with self.assertRaises(InvalidTransitionError):
            runtime.to_write_bytes(forged)
        empty = ScanRuntime(FakeMemory(), [REGION], pointer_size=8)
        with self.assertRaises(InvalidTransitionError):
            empty.to_write_bytes(runtime.last_snapshot().hits[0])


class SnapshotAndReportTests(unittest.TestCase):
    def test_snapshots_deterministic_sorted_and_immutable(self):
        backend = FakeMemory()
        put_values(backend, 'int', {BASE + 8: 42, BASE: 42})
        runtime = ScanRuntime(backend, [REGION], pointer_size=8)
        runtime.attach()
        first = runtime.first_exact('int', 42, [REGION])
        second = runtime.numeric('unchanged')
        self.assertEqual(first.snapshot_index, 1)
        self.assertEqual(second.snapshot_index, 2)
        self.assertEqual([h.address for h in first.hits], [BASE, BASE + 8])
        with self.assertRaises(TypeError):
            first.hits[0] = None
        self.assertEqual(runtime.finish(), second)
        self.assertEqual(runtime.state, 'done')
        with self.assertRaises(InvalidTransitionError):
            runtime.numeric('changed')
        with self.assertRaises(InvalidTransitionError):
            runtime.abort()

    def test_abort_from_attached_and_refused_when_terminal(self):
        backend = FakeMemory()
        runtime = ScanRuntime(backend, [REGION], pointer_size=8)
        runtime.attach()
        runtime.abort()
        self.assertEqual(runtime.state, 'aborted')
        with self.assertRaises(InvalidTransitionError):
            runtime.abort()
        with self.assertRaises(InvalidTransitionError):
            runtime.first_exact('int', 1, [REGION])

    def test_hit_budget_binding_exact(self):
        backend = FakeMemory()
        put_values(backend, 'int', {BASE: 42, BASE + 4: 42})
        runtime = ScanRuntime(backend, [REGION], pointer_size=8)
        runtime.attach()
        snapshot = runtime.first_exact('int', 42, [REGION])
        reads_per_hit = 4
        total = backend.read_calls * 4
        self.assertEqual(snapshot.read_bytes, total)
        for ordinal, hit in enumerate(snapshot.hits):
            self.assertEqual(hit.budget_ordinal, ordinal)
            self.assertEqual(hit.budget_results_before, 0)
            # Stride-1 admission: the hit at BASE+d is admitted after the
            # read that completes at BASE+d, i.e. after d+1 four-byte reads.
            self.assertEqual(hit.budget_read_bytes,
                             (hit.address - BASE + 1) * reads_per_hit)
        put_values(backend, 'int', {BASE: 42, BASE + 4: 43})
        second = runtime.nextscan()
        self.assertEqual(second.hits[0].budget_results_before, 2)
        self.assertEqual(second.read_bytes > snapshot.read_bytes, True)

    def test_report_is_json_stable_evidence(self):
        backend = FakeMemory()
        put_values(backend, 'int', {BASE: 42})
        runtime = ScanRuntime(backend, [REGION], pointer_size=8)
        runtime.attach()
        runtime.first_exact('int', 42, [REGION])
        report = runtime.report()
        self.assertEqual(report['state'], 'armed')
        self.assertEqual(report['identity'], [4242, 100])
        self.assertEqual(report['allowance']['schema'],
                         'ct2trainer-scan-allowance/v1')
        self.assertEqual(report['allowance']['read_bytes'],
                         snapshot_bytes(runtime))
        text = json.dumps(report, sort_keys=True)
        self.assertEqual(json.dumps(runtime.report(), sort_keys=True), text)
        json.loads(text)

    def test_shared_allowance_couples_two_sessions(self):
        clock_values = iter([0.0] * 1000)
        # Session A scans a 16-byte region stride-1 with int (4 B): 13 reads =
        # 52 bytes, so the shared budget must exactly cover its own scan;
        # session B's first read then exceeds it.
        allowance = ScanAllowance(clock=lambda: next(clock_values),
                                  max_read_bytes=52)
        backend_a = FakeMemory()
        put_values(backend_a, 'int', {BASE: 42})
        runtime_a = ScanRuntime(backend_a, [REGION], pointer_size=8,
                                allowance=allowance)
        runtime_a.attach()
        runtime_a.first_exact('int', 42, [(BASE, BASE + 0x10)])
        backend_b = FakeMemory(pid=4343)
        runtime_b = ScanRuntime(backend_b, [REGION], pointer_size=8,
                                allowance=allowance)
        runtime_b.attach()
        with self.assertRaises(ReadByteLimitRefused):
            runtime_b.first_exact('int', 42, [(BASE, BASE + 0x10)])
        self.assertEqual(allowance.report()['violation'] is not None, True)


def snapshot_bytes(runtime):
    return runtime.last_snapshot().read_bytes


if __name__ == '__main__':
    unittest.main()
