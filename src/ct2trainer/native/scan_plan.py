"""Bounded value-scan session model, independently implemented.

A scan session is bound to exactly one target identity (PID + creation time).
Scan modes are explicit: first_exact, numeric (changed/unchanged/greater/less),
fuzzy and nextscan. Every limit (regions, results, read bytes, time) is a named
refusal, never a silent clamp or partial success. Captured candidate sets are
immutable snapshots; a PID or creation-time change refuses the scan instead of
carrying stale candidates over. AOB wildcard patterns are scan patterns and can
never be interpreted as write values.
"""
from __future__ import annotations

import math
import struct
import time

SCHEMA = 'ct2trainer-value-scan-plan/v1'

_KINDS = {
    'byte': (1, '<B'),
    'short': (2, '<H'),
    'word': (2, '<h'),
    'int': (4, '<i'),
    'uint': (4, '<I'),
    'float': (4, '<f'),
    'qword': (8, '<q'),
    'uint64': (8, '<Q'),
    'double': (8, '<d'),
}
_NUMERIC_KINDS = {'byte', 'short', 'word', 'int', 'uint', 'float', 'qword', 'uint64', 'double'}
_HEX_DIGITS = '0123456789abcdef'


class ScanPlanError(ValueError):
    pass


class StaleSnapshotRejected(ScanPlanError):
    pass


class ResultLimitRefused(ScanPlanError):
    pass


class ReadByteLimitRefused(ScanPlanError):
    pass


class TimeLimitRefused(ScanPlanError):
    pass


class RegionLimitRefused(ScanPlanError):
    pass


class WildcardWriteRefused(ScanPlanError):
    pass


class InvalidTransitionError(ScanPlanError):
    pass


class InvalidScanParameterError(ScanPlanError):
    pass


def _address_limit(pointer_size: int) -> int:
    if pointer_size not in (4, 8):
        raise InvalidScanParameterError('Pointer size must be 4 or 8.')
    return 0xFFFFFFFF if pointer_size == 4 else 0x7FFFFFFFFFFF


class TargetIdentity:
    """PID plus creation time, both observed independently."""

    __slots__ = ('pid', 'created')

    def __init__(self, pid: int, created: int) -> None:
        if (type(pid) is not int or pid <= 0 or pid > 0xFFFFFFFF
                or type(created) is not int or created <= 0):
            raise InvalidScanParameterError('Target identity requires positive PID and creation time.')
        self.pid = pid
        self.created = created

    def matches(self, other: 'TargetIdentity') -> bool:
        return type(other) is TargetIdentity and self.pid == other.pid and self.created == other.created

    def __repr__(self) -> str:
        return f'TargetIdentity(pid={self.pid}, created={self.created})'


class ScanLimits:
    """Hard, named bounds for one session; exceeding any is a refusal."""

    __slots__ = ('max_regions', 'max_results', 'max_read_bytes', 'time_budget')

    def __init__(self, *, max_regions: int, max_results: int,
                 max_read_bytes: int, time_budget: float) -> None:
        if (type(max_regions) is not int or max_regions <= 0
                or type(max_results) is not int or max_results <= 0
                or type(max_read_bytes) is not int or max_read_bytes <= 0
                or type(time_budget) not in (int, float) or time_budget <= 0
                or not math.isfinite(time_budget)):
            raise InvalidScanParameterError('Scan limits must be positive and finite.')
        self.max_regions = max_regions
        self.max_results = max_results
        self.max_read_bytes = max_read_bytes
        self.time_budget = float(time_budget)


class TargetRegions:
    """Allowed address intervals, disjoint and sorted, inside the target width."""

    __slots__ = ('pointer_size', 'regions', 'limit')

    def __init__(self, regions, pointer_size: int) -> None:
        self.pointer_size = pointer_size
        self.limit = _address_limit(pointer_size)
        normalized = []
        for region in regions or ():
            if (type(region) is not tuple or len(region) != 2
                    or type(region[0]) is not int or type(region[1]) is not int
                    or region[0] <= 0 or region[1] > self.limit + 1 or region[0] >= region[1]):
                raise InvalidScanParameterError('Regions are (start, end) pairs inside the target width.')
            if normalized and region[0] < normalized[-1][1]:
                raise InvalidScanParameterError('Regions must be disjoint and sorted.')
            normalized.append((region[0], region[1]))
        self.regions = tuple(normalized)

    def covers(self, start: int, end: int) -> bool:
        return any(region[0] <= start and end <= region[1] for region in self.regions)


class ScanSnapshot:
    """Immutable result of one scan: identity, width, kind and candidates."""

    __slots__ = ('schema', 'identity', 'pointer_size', 'kind', 'candidates', 'scan_index')

    def __init__(self, identity, pointer_size, kind, candidates, scan_index) -> None:
        self.schema = SCHEMA
        self.identity = identity
        self.pointer_size = pointer_size
        self.kind = kind
        self.candidates = tuple(candidates)
        self.scan_index = scan_index

    def __len__(self) -> int:
        return len(self.candidates)


class ScanSession:
    """One bounded value-scan session for one held target identity."""

    _TERMINAL = ('done', 'aborted')

    def __init__(self, identity: TargetIdentity, regions: TargetRegions,
                 limits: ScanLimits, clock=None) -> None:
        self.identity = identity
        self.regions = regions
        self.limits = limits
        self._clock = clock if clock is not None else time.monotonic
        self._state = 'idle'
        self._kind = None
        self._previous = None
        self._scan_index = 0
        self._read_bytes = 0
        self._snapshots: tuple[ScanSnapshot, ...] = ()

    # -- state -------------------------------------------------------------

    @property
    def state(self) -> str:
        return self._state

    def _require(self, *states: str) -> None:
        if self._state not in states:
            raise InvalidTransitionError(
                f'Scan session is {self._state}; only {" / ".join(states)} may continue it.')

    def abort(self) -> None:
        if self._state in self._TERMINAL:
            raise InvalidTransitionError('Scan session is already finished.')
        self._state = 'aborted'

    def finish(self) -> ScanSnapshot:
        self._require('armed')
        self._state = 'done'
        return self.last_snapshot()

    def last_snapshot(self) -> ScanSnapshot | None:
        return self._snapshots[-1] if self._snapshots else None

    def _observe(self, observed: TargetIdentity) -> None:
        if not self.identity.matches(observed):
            raise StaleSnapshotRejected(
                'Target PID or creation time changed; stale candidates are never carried over.')

    # -- value helpers ------------------------------------------------------

    @staticmethod
    def _decode(kind: str, raw: bytes):
        size, code = _KINDS[kind]
        if len(raw) != size:
            raise InvalidScanParameterError('Backend returned the wrong byte count for the scan kind.')
        return struct.unpack(code, raw)[0]

    def _backend_read(self, backend, address: int, size: int, deadline) -> bytes:
        if self._clock() > deadline:
            raise TimeLimitRefused('Scan time budget expired before a read could start.')
        raw = backend(address, size)
        if (type(raw) is not bytes or len(raw) != size):
            raise InvalidScanParameterError('Backend read must return exactly the requested bytes.')
        self._read_bytes += size
        if self._read_bytes > self.limits.max_read_bytes:
            raise ReadByteLimitRefused('Cumulative read bytes exceeded the session limit.')
        if self._clock() > deadline:
            raise TimeLimitRefused('Scan time budget expired after a read; no partial results are returned.')
        return raw

    def _check_regions(self, regions, size: int) -> None:
        if len(regions) > self.limits.max_regions:
            raise RegionLimitRefused('Region count exceeded the scan limit.')
        for start, end in regions:
            if not self.regions.covers(start, end) or start + size > end:
                raise InvalidScanParameterError('Scan region leaves the allowed target regions.')

    def _filter(self, backend, predicate, deadline) -> dict:
        if self._previous is None:
            raise InvalidTransitionError('Numeric refinement needs a captured previous value.')
        if self._clock() > deadline:
            raise TimeLimitRefused('Scan time budget expired before refinement could start.')
        kept = {}
        for address, previous in sorted(self._previous):
            current = self._decode(self._kind, self._backend_read(backend, address, len(struct.pack(_KINDS[self._kind][1], previous)), deadline))
            if predicate(current, previous):
                kept[address] = current
        return kept

    def _commit(self, candidates: dict, observed: TargetIdentity) -> ScanSnapshot:
        if len(candidates) > self.limits.max_results:
            raise ResultLimitRefused('Match count exceeded the scan limit; nothing is returned or kept.')
        self._observe(observed)
        self._scan_index += 1
        self._previous = tuple(sorted(candidates.items()))
        self._state = 'armed'
        snapshot = ScanSnapshot(self.identity, self.regions.pointer_size, self._kind,
                                tuple(sorted(candidates.items())), self._scan_index)
        self._snapshots = self._snapshots + (snapshot,)
        return snapshot

    # -- public scan API -----------------------------------------------------

    def first_exact(self, kind: str, value, regions, backend, observed: TargetIdentity) -> ScanSnapshot:
        self._require('idle')
        if kind not in _KINDS:
            raise InvalidScanParameterError('Unknown value kind.')
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise InvalidScanParameterError('First scan value must be a number.')
        try:
            struct.pack(_KINDS[kind][1], value)
        except struct.error as failure:
            raise InvalidScanParameterError(f'Value does not fit the scan kind: {failure}') from None
        self._kind = kind
        size = _KINDS[kind][0]
        self._check_regions(regions, size)
        deadline = self._clock() + self.limits.time_budget
        candidates = {address: value
                      for address, _ in self._iter_candidates(kind, value, regions, backend, deadline)}
        return self._commit(candidates, observed)

    def _iter_candidates(self, kind, value, regions, backend, deadline):
        size = _KINDS[kind][0]
        for start, end in regions:
            if not self.regions.covers(start, end) or start + size > end:
                raise InvalidScanParameterError('Scan region leaves the allowed target regions.')
            address = start
            while address + size <= end:
                raw = self._backend_read(backend, address, size, deadline)
                if self._decode(kind, raw) == value:
                    yield address, raw
                address += 1

    def numeric(self, mode: str, backend, observed: TargetIdentity) -> ScanSnapshot:
        self._require('armed')
        if mode not in {'changed', 'unchanged', 'greater', 'less'}:
            raise InvalidScanParameterError('Numeric mode must be changed/unchanged/greater/less.')
        deadline = self._clock() + self.limits.time_budget
        if mode == 'changed':
            kept = self._filter(backend, lambda current, previous: current != previous, deadline)
        elif mode == 'unchanged':
            kept = self._filter(backend, lambda current, previous: current == previous, deadline)
        elif mode == 'greater':
            kept = self._filter(backend, lambda current, previous: current > previous, deadline)
        else:
            kept = self._filter(backend, lambda current, previous: current < previous, deadline)
        return self._commit(kept, observed)

    def fuzzy(self, value, delta, backend, observed: TargetIdentity) -> ScanSnapshot:
        self._require('armed')
        if self._kind not in _NUMERIC_KINDS:
            raise InvalidScanParameterError('Fuzzy scan requires a numeric value kind.')
        if (type(delta) not in (int, float) or isinstance(delta, bool)
                or not math.isfinite(delta) or delta <= 0):
            raise InvalidScanParameterError('Fuzzy delta must be positive and finite.')
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise InvalidScanParameterError('Fuzzy reference must be a number.')
        deadline = self._clock() + self.limits.time_budget
        kept = self._filter(backend, lambda current, previous: abs(current - value) <= delta, deadline)
        return self._commit(kept, observed)

    def nextscan(self, value, backend, observed: TargetIdentity) -> ScanSnapshot:
        self._require('armed')
        if self._kind not in _NUMERIC_KINDS:
            raise InvalidScanParameterError('Next scan requires a numeric value kind.')
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise InvalidScanParameterError('Next scan reference must be a number.')
        deadline = self._clock() + self.limits.time_budget
        kept = self._filter(backend, lambda current, previous: current == value, deadline)
        return self._commit(kept, observed)


_HEX_DIGITS = '0123456789abcdef'


def pattern_has_wildcard(pattern) -> bool:
    """Conservative AOB wildcard detection: anything beyond plain hex bytes.

    Full-byte unknowns (?, x, *), nibble unknowns (a second ?/x) and tokens that
    are not 1-2 hex digits are all patterns. A 1-2 digit hex token is a plain
    byte, never a wildcard.
    """
    if type(pattern) is not str:
        raise InvalidScanParameterError('Pattern must be a string.')
    for token in pattern.split():
        if len(token) > 2 or any(char in token for char in '?x*'):
            return True
        if any(char not in _HEX_DIGITS for char in token.lower()):
            return True
    return False


def assert_write_value(value, source_pattern: str | None = None) -> bytes:
    """Write values come from numeric kinds, never from scan patterns."""
    if type(value) is not bytes or not value:
        raise InvalidScanParameterError('Write values are non-empty raw bytes.')
    if source_pattern is not None and pattern_has_wildcard(source_pattern):
        raise WildcardWriteRefused('A wildcard scan pattern is never a write value.')
    return value
