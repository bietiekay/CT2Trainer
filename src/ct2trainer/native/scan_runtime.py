"""Bounded four-mode value-scan runtime over the AOB scan foundation (AP-08.7).

Pure state machine over an injectable memory backend with the documented
ProcessMemory surface (identity, pointer_size, is_alive, read, scan_matches).
All limits are cooperative in the N35 restoration-budget style: a shared
allowance (default 30 s / 65536 results / 128 MiB reads / 65536 regions) is
checked at checkpoints and refuses named work instead of interrupting an
in-flight backend call. Every committed hit carries region identity, a
snapshot reference and its admission-time budget state, so results can be
audited without re-trusting live memory.

Mode semantics differ deliberately from scan_plan where the task contract
requires them: nextscan keeps only values that CHANGED against the previous
snapshot, and it refuses an empty previous snapshot with a named reason.
Region sets are bound to each snapshot; a different region set between scans
refuses the refinement, invalidates the old hits and never silently rebases
addresses. AOB wildcard patterns are scan inputs only and can never become
write values; a session that used one refuses every derived write.
"""

from __future__ import annotations

import math
import struct
import time
from dataclasses import dataclass

from .patterns import normalize_pattern, pattern_byte_length
from .scan_plan import pattern_has_wildcard


SCHEMA = 'ct2trainer-scan-runtime/v1'
ALLOWANCE_SCHEMA = 'ct2trainer-scan-allowance/v1'
ALLOWANCE_SECONDS_RANGE = (0.001, 120.0)
ALLOWANCE_MAX_RESULTS_CAP = 65536
ALLOWANCE_MAX_READ_BYTES_CAP = 128 * 1024 * 1024
ALLOWANCE_MAX_REGIONS_CAP = 65536
DEFAULT_ALLOWANCE_SECONDS = 30.0
DEFAULT_MAX_RESULTS = 65536
DEFAULT_MAX_READ_BYTES = 128 * 1024 * 1024
DEFAULT_MAX_REGIONS = 65536

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
_NUMERIC_KINDS = set(_KINDS)


class ScanRuntimeError(ValueError):
    """Base for all named, bounded scan-runtime rejections."""


class InvalidScanParameterError(ScanRuntimeError):
    pass


class InvalidTransitionError(ScanRuntimeError):
    pass


class StaleTargetError(ScanRuntimeError):
    pass


class EmptySnapshotRefused(ScanRuntimeError):
    pass


class RegionShiftRefused(ScanRuntimeError):
    pass


class RegionLimitRefused(ScanRuntimeError):
    pass


class ResultLimitRefused(ScanRuntimeError):
    pass


class ReadByteLimitRefused(ScanRuntimeError):
    pass


class TimeLimitRefused(ScanRuntimeError):
    pass


class WildcardWriteRefused(ScanRuntimeError):
    pass


class PatternMalformedError(ScanRuntimeError):
    pass


class AllowanceClockError(ScanRuntimeError):
    pass


def _address_limit(pointer_size: int) -> int:
    return 0xFFFFFFFF if pointer_size == 4 else 0x7FFFFFFFFFFF


def _check_region_set(regions, pointer_size: int, label: str) -> tuple:
    limit = _address_limit(pointer_size)
    if not isinstance(regions, (tuple, list)):
        raise InvalidScanParameterError(label + ' scan regions must be a sequence of (start, end) pairs.')
    normalized = []
    for region in regions:
        if (type(region) is not tuple or len(region) != 2
                or type(region[0]) is not int or type(region[1]) is not int
                or isinstance(region[0], bool) or isinstance(region[1], bool)
                or region[0] <= 0 or region[1] > limit + 1 or region[0] >= region[1]):
            raise InvalidScanParameterError(
                label + ' scan regions are (start, end) pairs inside the target width.')
        if normalized and region[0] < normalized[-1][1]:
            raise InvalidScanParameterError(label + ' scan regions must be disjoint and sorted.')
        normalized.append((region[0], region[1]))
    return tuple(normalized)


@dataclass(frozen=True)
class ScanHit:
    """One committed result with full result-binding for audit.

    region/region_index identify the scan region and its position in the
    session's allowed region set; snapshot_index references the immutable
    snapshot that committed this hit; the budget_* fields record the
    cooperative allowance state at admission time (N35 ledger style).
    """

    address: int
    value: object
    kind: str
    size: int
    region: tuple
    region_index: int
    snapshot_index: int
    budget_ordinal: int
    budget_results_before: int
    budget_read_bytes: int

    def to_dict(self) -> dict:
        return {'address': self.address, 'value': self.value, 'kind': self.kind,
                'size': self.size, 'region': list(self.region),
                'region_index': self.region_index,
                'snapshot_index': self.snapshot_index,
                'budget_ordinal': self.budget_ordinal,
                'budget_results_before': self.budget_results_before,
                'budget_read_bytes': self.budget_read_bytes}


@dataclass(frozen=True)
class ScanSnapshot:
    """Immutable, sorted result of one scan operation."""

    schema: str
    snapshot_index: int
    mode: str
    kind: str
    pointer_size: int
    pid: int
    created: int
    regions: tuple
    hits: tuple
    read_bytes: int
    elapsed: float
    pattern: str | None
    has_wildcard: bool

    def __len__(self) -> int:
        return len(self.hits)

    def to_dict(self) -> dict:
        return {'schema': self.schema, 'snapshot_index': self.snapshot_index,
                'mode': self.mode, 'kind': self.kind,
                'pointer_size': self.pointer_size, 'pid': self.pid,
                'created': self.created,
                'regions': [list(r) for r in self.regions],
                'hits': [h.to_dict() for h in self.hits],
                'read_bytes': self.read_bytes, 'elapsed': self.elapsed,
                'pattern': self.pattern, 'has_wildcard': self.has_wildcard}


class ScanAllowance:
    """Cooperative shared scan allowance, N35 restoration-budget style.

    The controller clock is injectable. A deadline stops returned
    synchronous work at the next checkpoint; it never interrupts an in-flight
    backend call. Result and read-byte budgets are cumulative for the whole
    session; a violation retains all prior state and commits nothing new.
    """

    def __init__(self, clock=None, *, seconds=DEFAULT_ALLOWANCE_SECONDS,
                 max_results: int = DEFAULT_MAX_RESULTS,
                 max_read_bytes: int = DEFAULT_MAX_READ_BYTES,
                 max_regions: int = DEFAULT_MAX_REGIONS) -> None:
        if clock is not None and not callable(clock):
            raise InvalidScanParameterError('Scan allowance clock must be controller-owned.')
        if (type(seconds) not in (int, float) or isinstance(seconds, bool)
                or not math.isfinite(seconds)
                or not ALLOWANCE_SECONDS_RANGE[0] <= seconds <= ALLOWANCE_SECONDS_RANGE[1]):
            raise InvalidScanParameterError(
                f'Scan allowance seconds must be finite within '
                f'{ALLOWANCE_SECONDS_RANGE[0]}..{ALLOWANCE_SECONDS_RANGE[1]}.')
        for label, value, cap in (('max_results', max_results, ALLOWANCE_MAX_RESULTS_CAP),
                                  ('max_read_bytes', max_read_bytes, ALLOWANCE_MAX_READ_BYTES_CAP),
                                  ('max_regions', max_regions, ALLOWANCE_MAX_REGIONS_CAP)):
            if type(value) is not int or isinstance(value, bool) or not 1 <= value <= cap:
                raise InvalidScanParameterError(
                    f'Scan allowance {label} must be an integer within 1..{cap}.')
        self._clock = clock if clock is not None else time.monotonic
        self._seconds = float(seconds)
        self.max_results = max_results
        self.max_read_bytes = max_read_bytes
        self.max_regions = max_regions
        self._last: float | None = None
        self.started: float | None = None
        self.deadline: float | None = None
        self.violation: str | None = None
        self.read_bytes = 0
        self.results = 0
        self.region_uses = 0

    def now(self) -> float:
        value = self._clock()
        if type(value) not in (int, float) or not math.isfinite(value):
            self._fail('Scan allowance clock is not finite.')
        value = float(value)
        if self._last is not None and value < self._last:
            self._fail('Scan allowance clock moved backwards.')
        self._last = value
        return value

    def _fail(self, reason: str) -> None:
        if self.violation is None:
            self.violation = reason
        if reason.startswith('Scan deadline'):
            raise TimeLimitRefused(reason)
        if reason.startswith('Cumulative read'):
            raise ReadByteLimitRefused(reason)
        if reason.startswith('Result count'):
            raise ResultLimitRefused(reason)
        if reason.startswith('Region count'):
            raise RegionLimitRefused(reason)
        raise AllowanceClockError(reason)

    def begin(self) -> None:
        if self.deadline is None:
            self.started = self.now()
            self.deadline = self.started + self._seconds
        self.check()

    def check(self) -> None:
        if self.violation is not None:
            self._fail(self.violation)
        if self.deadline is not None and self.now() >= self.deadline:
            self._fail('Scan deadline exceeded; retain uncertain results, commit nothing.')

    def reserve_read(self, size: int) -> None:
        if type(size) is not int or isinstance(size, bool) or size <= 0:
            raise InvalidScanParameterError('Scan read size must be a positive integer.')
        self.check()
        if self.read_bytes + size > self.max_read_bytes:
            self._fail(f'Cumulative read bytes would exceed {self.max_read_bytes}.')
        self.read_bytes += size

    def reserve_results(self, count: int) -> None:
        if type(count) is not int or isinstance(count, bool) or count < 0:
            raise InvalidScanParameterError('Scan result count must be a non-negative integer.')
        self.check()
        if self.results + count > self.max_results:
            self._fail(f'Result count would exceed the session budget of {self.max_results}.')
        self.results += count

    def reserve_region(self) -> None:
        self.check()
        if self.region_uses + 1 > self.max_regions:
            self._fail(f'Region count would exceed the session budget of {self.max_regions}.')
        self.region_uses += 1

    def report(self) -> dict:
        return {'schema': ALLOWANCE_SCHEMA,
                'seconds': self._seconds, 'max_results': self.max_results,
                'max_read_bytes': self.max_read_bytes,
                'max_regions': self.max_regions,
                'started': self.started, 'deadline': self.deadline,
                'read_bytes': self.read_bytes, 'results': self.results,
                'region_uses': self.region_uses, 'violation': self.violation}


class ScanRuntime:
    """One bounded four-mode scan session over a held target identity.

    States: idle -> attached -> armed -> done/aborted; a region shift during
    refinement moves the session to the terminal 'invalidated' state, where
    every prior hit is void and no operation rebinds addresses.
    """

    _TERMINAL = ('done', 'aborted', 'invalidated')

    def __init__(self, backend, allowed_regions, *, pointer_size: int,
                 clock=None, allowance: ScanAllowance | None = None,
                 seconds=DEFAULT_ALLOWANCE_SECONDS,
                 max_results: int = DEFAULT_MAX_RESULTS,
                 max_read_bytes: int = DEFAULT_MAX_READ_BYTES,
                 max_regions: int = DEFAULT_MAX_REGIONS) -> None:
        if type(pointer_size) is not int or isinstance(pointer_size, bool) \
                or pointer_size not in (4, 8):
            raise InvalidScanParameterError('Pointer size must be 4 or 8 bytes.')
        self.backend = backend
        self.pointer_size = pointer_size
        self.allowed_regions = _check_region_set(allowed_regions, pointer_size, 'Allowed')
        if allowance is not None:
            if type(allowance) is not ScanAllowance:
                raise InvalidScanParameterError('Allowance must be a ScanAllowance.')
            self.allowance = allowance
        else:
            self.allowance = ScanAllowance(clock, seconds=seconds,
                                           max_results=max_results,
                                           max_read_bytes=max_read_bytes,
                                           max_regions=max_regions)
        self._state = 'idle'
        self._identity: tuple[int, int] | None = None
        self._snapshots: tuple[ScanSnapshot, ...] = ()
        self._wildcard_used = False

    @property
    def state(self) -> str:
        return self._state

    @property
    def wildcard_used(self) -> bool:
        return self._wildcard_used

    def _require(self, *states: str) -> None:
        if self._state not in states:
            raise InvalidTransitionError(
                f'Scan runtime is {self._state}; only {" / ".join(states)} may continue it.')

    def attach(self, observed: tuple[int, int] | None = None) -> None:
        """Bind the session to the backend's target identity and width."""
        self._require('idle')
        identity = getattr(self.backend, 'identity', None)
        if (type(identity) is not tuple or len(identity) != 2
                or any(type(item) is not int or isinstance(item, bool) or item <= 0
                       for item in identity)
                or identity[0] > 0xFFFFFFFF or identity[1] > 0xFFFFFFFFFFFFFFFF):
            raise InvalidScanParameterError(
                'Backend identity must be a (pid, created) pair of positive integers.')
        width = getattr(self.backend, 'pointer_size', None)
        if type(width) is not int or width != self.pointer_size:
            raise InvalidScanParameterError(
                'Backend pointer width differs from the configured scan width.')
        is_alive = getattr(self.backend, 'is_alive', None)
        if not callable(is_alive) or is_alive() is not True:
            raise StaleTargetError('Target is not observable as alive before attach.')
        if observed is not None:
            if (type(observed) is not tuple or len(observed) != 2
                    or observed != identity):
                raise StaleTargetError(
                    'Externally observed target identity differs from the backend.')
        self._identity = identity
        self.allowance.begin()
        self._state = 'attached'

    def _require_target(self) -> None:
        self._require('attached', 'armed')
        if self.backend.identity != self._identity:
            raise StaleTargetError(
                'Target PID or creation time changed; stale candidates are never carried over.')
        if self.backend.is_alive() is not True:
            raise StaleTargetError('Target no longer alive; stale candidates are not carried over.')

    def _check_regions(self, regions, size: int) -> tuple:
        checked = _check_region_set(regions, self.pointer_size, 'Operation')
        if len(checked) > self.allowance.max_regions:
            raise RegionLimitRefused(
                f'Region count {len(checked)} exceeds the allowance budget '
                f'of {self.allowance.max_regions}.')
        allowed = list(self.allowed_regions)
        for index, (start, end) in enumerate(checked):
            if not any(a <= start and end <= b for a, b in allowed):
                raise InvalidScanParameterError(
                    'Scan region leaves the allowed target regions.')
            if start + size > end:
                raise InvalidScanParameterError(
                    'Scan region is smaller than the value kind.')
        return checked

    def _region_index(self, address: int) -> int:
        for index, (start, end) in enumerate(self.allowed_regions):
            if start <= address < end:
                return index
        raise InvalidScanParameterError('Hit address left the allowed regions.')

    def _read(self, address: int, size: int) -> bytes:
        raw = self.backend.read(address, size)
        if type(raw) is not bytes or len(raw) != size:
            raise InvalidScanParameterError(
                'Backend read must return exactly the requested bytes.')
        self.allowance.reserve_read(size)
        return raw

    def _commit(self, mode: str, kind: str, regions: tuple, hits,
                pattern: str | None, has_wildcard: bool) -> ScanSnapshot:
        self._require_target()
        self.allowance.check()
        self.allowance.reserve_results(len(hits))
        snapshot_index = len(self._snapshots) + 1
        ordered = tuple(sorted(hits, key=lambda hit: hit.address))
        snapshot = ScanSnapshot(
            schema=SCHEMA, snapshot_index=snapshot_index, mode=mode, kind=kind,
            pointer_size=self.pointer_size, pid=self._identity[0],
            created=self._identity[1], regions=regions, hits=ordered,
            read_bytes=self.allowance.read_bytes,
            elapsed=self.allowance.now() - self.allowance.started,
            pattern=pattern, has_wildcard=has_wildcard)
        self._snapshots = self._snapshots + (snapshot,)
        self._state = 'armed'
        return snapshot

    def _hits(self, kind, checked, entries, snapshot_index) -> list:
        """Bind discovered (address, region_index, value, read_bytes) entries.

        Entries are ordered by address before the ordinal is assigned, so the
        binding is deterministic and auditable. The per-entry read-byte count
        is the allowance state at the moment the hit was admitted, not the
        total at commit time.
        """
        ordered = sorted(entries, key=lambda entry: entry[0])
        if len(set(entry[0] for entry in ordered)) != len(ordered):
            raise PatternMalformedError('Duplicate hit address in one scan operation.')
        budget_before = self.allowance.results
        hits = []
        for ordinal, (address, region_index, value, read_bytes_at) in enumerate(ordered):
            hits.append(ScanHit(address=address, value=value, kind=kind,
                                size=_KINDS[kind][0] if kind != 'aob' else self._pattern_size,
                                region=(checked[region_index][0], checked[region_index][1]),
                                region_index=region_index,
                                snapshot_index=snapshot_index,
                                budget_ordinal=ordinal,
                                budget_results_before=budget_before,
                                budget_read_bytes=read_bytes_at))
        return hits

    def first_exact(self, kind, value, regions, observed=None) -> ScanSnapshot:
        """First scan: keep every address whose stored value equals value."""
        self._require('attached')
        if kind not in _KINDS:
            raise InvalidScanParameterError('Unknown value kind.')
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise InvalidScanParameterError('First scan value must be a number.')
        try:
            struct.pack(_KINDS[kind][1], value)
        except struct.error as failure:
            raise InvalidScanParameterError(
                f'Value does not fit the scan kind: {failure}') from None
        checked = self._check_regions(regions, _KINDS[kind][0])
        self._require_target()
        size, code = _KINDS[kind]
        self.allowance.begin()
        entries = []
        for region_index, (start, end) in enumerate(checked):
            self.allowance.reserve_region()
            address = start
            while address + size <= end:
                self.allowance.check()
                raw = self._read(address, size)
                current = struct.unpack(code, raw)[0]
                if current == value:
                    entries.append((address, region_index, current,
                                    self.allowance.read_bytes))
                address += 1
        hits = self._hits(kind, checked, entries, len(self._snapshots) + 1)
        return self._commit('first_exact', kind, checked, hits, None, False)

    def _refine(self, mode, predicate, regions=None) -> ScanSnapshot:
        self._require('armed')
        previous = self.last_snapshot()
        if mode == 'nextscan' and len(previous) == 0:
            raise EmptySnapshotRefused(
                'nextscan requires a non-empty previous snapshot.')
        if regions is None:
            checked = previous.regions
        else:
            checked = _check_region_set(regions, self.pointer_size, 'Operation')
            if checked != previous.regions:
                self._state = 'invalidated'
                raise RegionShiftRefused(
                    'Scan regions shifted between scans; previous hits are invalid '
                    'and are never rebased.')
        kind = previous.kind
        size, code = _KINDS[kind]
        self._require_target()
        self.allowance.begin()
        self.allowance.check()
        entries = []
        for previous_hit in previous.hits:
            self.allowance.check()
            raw = self._read(previous_hit.address, size)
            current = struct.unpack(code, raw)[0]
            if predicate(current, previous_hit.value):
                entries.append((previous_hit.address, previous_hit.region_index,
                                current, self.allowance.read_bytes))
        hits = self._hits(kind, checked, entries, len(self._snapshots) + 1)
        return self._commit(mode, kind, checked, hits, None, False)

    def numeric(self, mode, observed=None, regions=None) -> ScanSnapshot:
        """Refine the previous snapshot by changed/unchanged/greater/less."""
        if mode not in {'changed', 'unchanged', 'greater', 'less'}:
            raise InvalidScanParameterError(
                'Numeric mode must be changed/unchanged/greater/less.')
        if mode == 'changed':
            return self._refine(mode, lambda current, previous: current != previous, regions)
        if mode == 'unchanged':
            return self._refine(mode, lambda current, previous: current == previous, regions)
        if mode == 'greater':
            return self._refine(mode, lambda current, previous: current > previous, regions)
        return self._refine(mode, lambda current, previous: current < previous, regions)

    def fuzzy(self, value, delta, observed=None, regions=None) -> ScanSnapshot:
        """Refine the previous snapshot by values within +/- delta of value."""
        self._require('armed')
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise InvalidScanParameterError('Fuzzy reference must be a number.')
        if (type(delta) not in (int, float) or isinstance(delta, bool)
                or not math.isfinite(delta) or delta <= 0):
            raise InvalidScanParameterError('Fuzzy delta must be positive and finite.')
        return self._refine('fuzzy',
                            lambda current, previous: abs(current - value) <= delta, regions)

    def nextscan(self, observed=None, regions=None) -> ScanSnapshot:
        """Keep only values that changed against the previous snapshot.

        An empty previous snapshot is a named refusal, never a silent pass.
        """
        return self._refine('nextscan',
                            lambda current, previous: current != previous, regions)

    def aob(self, pattern, regions, observed=None) -> ScanSnapshot:
        """Bounded pattern scan over the AOB foundation of the backend.

        The pattern is validated and normalized; a wildcard pattern marks the
        whole session so that no hit of this session can later become a
        write value. Matches are bound to their region and snapshot.
        """
        self._require('attached', 'armed')
        entered = self._state
        try:
            normalized = normalize_pattern(pattern)
        except ValueError as exc:
            raise PatternMalformedError(str(exc)) from exc
        has_wildcard = pattern_has_wildcard(normalized)
        self._pattern_size = pattern_byte_length(normalized)
        if has_wildcard:
            self._wildcard_used = True
        checked = self._check_regions(regions, self._pattern_size)
        self._require_target()
        self.allowance.begin()
        entries = []
        for region_index, (start, end) in enumerate(checked):
            self.allowance.reserve_region()
            self.allowance.check()
            try:
                matches = self.backend.scan_matches(normalized, start=start, end=end,
                                                   max_results=self.allowance.max_results)
            except ValueError as exc:
                raise PatternMalformedError(
                    f'AOB backend rejected the scan request: {exc}') from exc
            except OSError as exc:
                # The bounded backend raises instead of truncating a match
                # list; the session budget for results is therefore exceeded.
                raise ResultLimitRefused(
                    f'AOB match count exceeded the backend/allowance bound: {exc}') from exc
            if type(matches) is not list:
                raise PatternMalformedError('AOB backend must return a match list.')
            for address in matches:
                if (type(address) is not int or isinstance(address, bool)
                        or not start <= address < end - self._pattern_size + 1):
                    raise PatternMalformedError(
                        'AOB backend returned a match outside its region.')
                entries.append((address, region_index, None, self.allowance.read_bytes))
        hits = self._hits('aob', checked, entries, len(self._snapshots) + 1)
        # A pattern scan is a side channel of the session: it must not move
        # a value-scan chain out of 'attached' or overwrite 'armed'.
        snapshot = self._commit('aob', 'aob', checked, hits, normalized, has_wildcard)
        self._state = entered
        return snapshot

    def last_snapshot(self) -> ScanSnapshot | None:
        return self._snapshots[-1] if self._snapshots else None

    def finish(self) -> ScanSnapshot:
        self._require('armed')
        self._state = 'done'
        return self.last_snapshot()

    def abort(self) -> None:
        if self._state in self._TERMINAL:
            raise InvalidTransitionError('Scan runtime is already finished.')
        self._state = 'aborted'

    def to_write_bytes(self, hit) -> bytes:
        """Produce write bytes for a committed hit; never from a wildcard.

        Value hits pack their captured value with the scan kind. AOB hits
        are only convertible when their pattern is fully literal; a
        wildcard pattern is a scan input and can never become a write
        value. Once any wildcard pattern was used in this session, every
        derived write is refused conservatively.
        """
        if not isinstance(hit, ScanHit):
            raise InvalidScanParameterError('Write binding requires a committed ScanHit.')
        if not self._snapshots or not (1 <= hit.snapshot_index <= len(self._snapshots)):
            raise InvalidTransitionError('Write binding requires a committed snapshot reference.')
        snapshot = self._snapshots[hit.snapshot_index - 1]
        if hit not in snapshot.hits:
            raise InvalidTransitionError('Write binding hit does not belong to its snapshot.')
        if hit.kind == 'aob':
            pattern = snapshot.pattern
            if pattern is None or pattern_has_wildcard(pattern):
                raise WildcardWriteRefused(
                    'A wildcard scan pattern is never a write value.')
            return bytes(int(token, 16) for token in pattern.split())
        if self._wildcard_used:
            raise WildcardWriteRefused(
                'This session used a wildcard scan pattern; no derived value '
                'may become a write value.')
        size, code = _KINDS[hit.kind]
        return struct.pack(code, hit.value)[:size]

    def report(self) -> dict:
        return {'schema': SCHEMA, 'state': self._state,
                'identity': list(self._identity) if self._identity else None,
                'pointer_size': self.pointer_size,
                'wildcard_used': self._wildcard_used,
                'allowance': self.allowance.report(),
                'snapshots': [snapshot.to_dict() for snapshot in self._snapshots]}


__all__ = [
    'SCHEMA', 'ALLOWANCE_SCHEMA', 'DEFAULT_ALLOWANCE_SECONDS',
    'DEFAULT_MAX_RESULTS', 'DEFAULT_MAX_READ_BYTES', 'DEFAULT_MAX_REGIONS',
    'ScanRuntimeError', 'InvalidScanParameterError', 'InvalidTransitionError',
    'StaleTargetError', 'EmptySnapshotRefused', 'RegionShiftRefused',
    'ResultLimitRefused', 'ReadByteLimitRefused', 'TimeLimitRefused',
    'WildcardWriteRefused', 'PatternMalformedError', 'AllowanceClockError',
    'ScanHit', 'ScanSnapshot', 'ScanAllowance', 'ScanRuntime',
]
