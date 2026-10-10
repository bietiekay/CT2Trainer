"""Pure one-shot ON/OFF state-save contract (feature: one_shot_save_contract).

This module is the standalone contract model for one-shot records: records
whose enable program is a one-way action ("grant once") and whose scripts
have no disable section that undoes the effect.  It deliberately does NOT
touch the engine, the compiler or any state-file format; the Root wiring
(aa.py / engine.py integration) consumes this model later.

Pinned contract decisions (build/briefs/brief-one-shot-contract.md):

1. ON executes the record's enable program exactly once (one-shot is an
   action, not a toggle).  A "confirmed ON" is a runtime confirmation
   after the execution finished, delivered exclusively as a backend
   receipt.
2. OFF produces no memory effect (no fabricated disable program).  It
   clears the saved wish only; the effect already applied in the target
   stays visible as effect_persists ("applied, not reversible").  A second
   OFF without an effect is not an error.
3. Save: a one-shot wish is saved only after a confirmed ON.  Failed or
   unclear attempts are never saved and never replayed.
4. Re-attach: a saved one-shot wish is re-executed exactly once per
   attach generation (CE parity: enable scripts run again on restore).
   A FAILED/UNKNOWN attempt is never replayed; after a successfully
   executed replay the wish remains (the marker is information, not a
   double-execution source within the same generation).
5. An explicit user ON is always a new ON action (allowed manual re-run),
   never a restore.
6. Freeze is orthogonal and has no place in this model.

Phase machine (per record, per session):

    INACTIVE --request_on--> PENDING --receipt(confirmed)--> EXECUTED
                               |
                               +--receipt(failed)---------> FAILED
                               |
                               +--(no receipt, held)-------> PENDING

EXECUTED and FAILED are terminal for the attempt; a new explicit ON starts
a fresh attempt (decision 5).  OFF never changes the phase; it only clears
the wish.  PENDING attempts are drained to FAILED at detach (unclear
attempts are never saved and never replayed).
"""

from __future__ import annotations

import re
import struct
import zlib
from dataclasses import dataclass

SCHEMA = 1

INACTIVE = 'INACTIVE'
PENDING = 'PENDING'
EXECUTED = 'EXECUTED'
FAILED = 'FAILED'

_PHASES = (INACTIVE, PENDING, EXECUTED, FAILED)
_PHASE_BYTE = {INACTIVE: 0, PENDING: 1, EXECUTED: 2, FAILED: 3}
_BYTE_PHASE = {byte: name for name, byte in _PHASE_BYTE.items()}
#: PENDING is never persisted; markers store the stable phase only.
_STABLE_PHASES = (INACTIVE, EXECUTED, FAILED)

MAGIC = b'TFSH0001'
NOT_SAVED = 0xFFFFFFFF
_MAX_PROCESS_NAME = 260
_MAX_RECORDS = 20000
_MARKER_LEN = 13  # 4s record_id | 1s phase | 4s attempt_count | 4s saved_generation
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")


class OneShotContractError(ValueError):
    """Base error for the one-shot contract; messages carry record/generation context."""


class OneShotUnknownRecordError(OneShotContractError):
    """Record ID is not part of this contract."""


class OneShotRecordKindRefused(OneShotContractError):
    """Record kind is not a one-shot script (e.g. a value record)."""


class OneShotNotAttachedRefused(OneShotContractError):
    """A target attach is required before the action."""


class OneShotPendingRefused(OneShotContractError):
    """An attempt is still pending (held); no second ON/OFF while held."""


class OneShotWishSaveRefused(OneShotContractError):
    """The wish may only be saved after a confirmed ON."""


class OneShotGenerationConflict(OneShotContractError):
    """Attach generation violates the attach/detach protocol."""


class OneShotReceiptRefused(OneShotContractError):
    """A backend receipt arrived for a non-pending or foreign attempt."""


class OneShotMarkerError(OneShotContractError):
    """Marker bytes are invalid; the whole marker set is rejected."""


@dataclass(frozen=True)
class OneShotReceipt:
    """Backend confirmation for one published enable program.

    ``confirmed`` is True only when the target runtime confirms that the
    effect completed; False when the attempt failed before the effect.
    """

    record_id: int
    confirmed: bool


@dataclass
class _RecordState:
    """Per-record contract state (session phase + persisted attempt data)."""

    phase: str = INACTIVE
    attempt_count: int = 0
    saved: bool = False
    saved_generation: int = NOT_SAVED
    last_outcome: str | None = None
    effect_persists: bool = False


class OneShotContract:
    """Pure contract model for one-shot records (no engine/compiler access).

    ``records``: iterable of ``(record_id, kind)`` pairs, kind is
    ``'script'`` (one-shot) or ``'value'`` (freezeable, orthogonal).
    ``ct_hash``: 64 lowercase hex sha256 of the table bytes.
    ``process_name``: target EXE basename the markers bind to.
    ``programs``: optional mapping record_id -> enable program bytes.

    Backend protocol (duck-typed, injected per call):

        publish(record_id: int, program: bytes) -> OneShotReceipt | None

    A returned receipt resolves the attempt immediately (confirmed or
    failed); ``None`` keeps the attempt PENDING until the backend receipt
    is delivered via :meth:`deliver_receipt`.  ``request_off`` performs
    exactly zero backend operations (contractually pinned).
    """

    def __init__(self, records, ct_hash, process_name, programs=None):
        if not isinstance(ct_hash, str) or not _HEX64.fullmatch(ct_hash):
            raise OneShotMarkerError('ct_hash must be 64 lowercase hex sha256 characters')
        if not isinstance(process_name, str) or not 0 < len(process_name) <= _MAX_PROCESS_NAME:
            raise OneShotMarkerError('process_name must be non-empty text (max 260 chars)')
        self.ct_hash = ct_hash
        self.process_name = process_name
        self.programs: dict[int, bytes] = {}
        if programs is not None:
            for record_id, program in programs.items():
                if type(record_id) is not int or not isinstance(program, (bytes, bytearray)):
                    raise OneShotContractError(
                        f'programs must map record IDs to program bytes: {record_id!r}')
                self.programs[record_id] = bytes(program)
        self.records: dict[int, str] = {}
        for record_id, kind in records:
            if type(record_id) is not int or record_id < 0 or record_id in self.records:
                raise OneShotContractError(f'duplicate or invalid record ID: {record_id!r}')
            if kind not in {'script', 'value'}:
                raise OneShotContractError(
                    f'record {record_id}: unsupported record kind {kind!r}')
            self.records[record_id] = kind
        if len(self.records) > _MAX_RECORDS:
            raise OneShotContractError('too many records for one contract')
        self._state = {record_id: _RecordState() for record_id in self.records}
        self.attached = False
        self.generation = 0
        self._last_generation = 0
        self._replay_attempted: set[int] = set()
        self._pending_source: dict[int, str] = {}
        self.attempts: list[tuple] = []

    # ------------------------------------------------------------------
    # Read paths
    # ------------------------------------------------------------------

    def saved_wish_ids(self) -> tuple:
        return tuple(sorted(rid for rid, state in self._state.items() if state.saved))

    def query(self, record_id: int) -> dict:
        state = self._require_record(record_id)
        return {
            'record_id': record_id,
            'kind': self.records[record_id],
            'phase': state.phase,
            'saved_wish': state.saved,
            'saved_generation': None if not state.saved else state.saved_generation,
            'attempt_count': state.attempt_count,
            'effect_persists': state.effect_persists,
            'last_outcome': state.last_outcome,
        }

    def snapshot(self) -> dict:
        return {
            'schema': SCHEMA,
            'attached': self.attached,
            'generation': self.generation if self.attached else 0,
            'phases': {rid: state.phase for rid, state in sorted(self._state.items())},
            'saved_wishes': list(self.saved_wish_ids()),
            'saved_generations': {rid: state.saved_generation
                                  for rid, state in sorted(self._state.items()) if state.saved},
            'attempt_counts': {rid: state.attempt_count
                               for rid, state in sorted(self._state.items())},
            'effect_persists': sorted(rid for rid, state in self._state.items()
                                     if state.effect_persists),
            'last_outcomes': {rid: state.last_outcome
                              for rid, state in sorted(self._state.items())},
            'attempts': list(self.attempts),
        }

    def _require_record(self, record_id: int) -> _RecordState:
        try:
            return self._state[record_id]
        except KeyError:
            raise OneShotUnknownRecordError(
                f'record {record_id} is not part of this one-shot contract')

    def _require_script(self, record_id: int) -> None:
        kind = self.records[record_id]
        if kind != 'script':
            raise OneShotRecordKindRefused(
                f'record {record_id} is a {kind} record; one-shot actions apply to script records only')

    def _require_attached(self, record_id: int) -> None:
        if not self.attached:
            raise OneShotNotAttachedRefused(
                f'record {record_id}: no confirmed attach; ON attempts require generation >= 1')

    # ------------------------------------------------------------------
    # ON / receipts
    # ------------------------------------------------------------------

    def request_on(self, backend, record_id: int) -> OneShotReceipt | None:
        """One explicit user ON: exactly one publish per attempt.

        Pinned: ON executes the enable program exactly once; confirmation
        arrives only through the backend receipt; the wish becomes
        saveable only after a confirmed ON.  A second ON while the
        attempt is held (PENDING) is refused; ON after EXECUTED or
        FAILED is a fresh explicit attempt (decision 5).
        """
        self._require_record(record_id)
        self._require_script(record_id)
        self._require_attached(record_id)
        state = self._state[record_id]
        if state.phase == PENDING:
            raise OneShotPendingRefused(
                f'record {record_id} attempt is pending (held, generation {self.generation}); '
                f'a second ON is refused until the backend receipt arrives')
        state.attempt_count += 1
        state.phase = PENDING
        self._pending_source[record_id] = 'explicit'
        receipt = backend.publish(record_id, self.programs.get(record_id, b''))
        self._resolve_attempt(record_id, receipt, 'explicit')
        return receipt

    def deliver_receipt(self, record_id: int, receipt: OneShotReceipt) -> None:
        """Deliver the backend receipt of a PENDING attempt (late completion).

        Confirmation reaches the contract exclusively through backend
        receipts; nothing else flips PENDING to EXECUTED or FAILED.
        """
        self._require_record(record_id)
        state = self._state[record_id]
        if not isinstance(receipt, OneShotReceipt) or receipt.record_id != record_id:
            raise OneShotReceiptRefused(
                f'record {record_id}: backend receipt is missing or names a foreign record')
        if state.phase != PENDING:
            raise OneShotReceiptRefused(
                f'record {record_id}: attempt is {state.phase.casefold()} '
                f'(generation {self.generation}); receipt is refused, no state change')
        self._resolve_attempt(record_id, receipt, self._pending_source.get(record_id, 'explicit'))

    def _resolve_attempt(self, record_id: int, receipt, source: str) -> None:
        state = self._state[record_id]
        if receipt is None:
            state.phase = PENDING  # held until the backend receipt arrives
            self.attempts.append((record_id, self.generation, source, 'pending'))
            return
        confirmed = bool(receipt.confirmed)
        state.phase = EXECUTED if confirmed else FAILED
        state.last_outcome = 'confirmed' if confirmed else 'failed'
        if confirmed:
            state.effect_persists = True
        self._pending_source.pop(record_id, None)
        self.attempts.append((record_id, self.generation, source,
                              'confirmed' if confirmed else 'failed'))

    # ------------------------------------------------------------------
    # OFF / save
    # ------------------------------------------------------------------

    def request_off(self, backend, record_id: int) -> dict:
        """One-shot OFF: contractually exactly zero backend operations.

        Pinned: OFF fabricates no disable program and never touches the
        target; it clears the saved wish only.  The effect already
        applied in the target stays visible as effect_persists
        ("applied, not reversible").  A second OFF without an effect is
        not an error.  The ``backend`` argument is accepted for API
        symmetry and is deliberately never used.
        """
        state = self._require_record(record_id)
        if state.phase == PENDING:
            raise OneShotPendingRefused(
                f'record {record_id} attempt is pending (held, generation {self.generation}); '
                f'OFF is refused until the backend receipt arrives')
        wish_cleared = state.saved
        state.saved = False
        state.saved_generation = NOT_SAVED
        return {
            'record_id': record_id,
            'wish_cleared': wish_cleared,
            'effect_persists': state.effect_persists,
            'backend_operations': 0,
        }

    def save(self, record_id: int) -> None:
        """Persist the one-shot wish; allowed only after a confirmed ON."""
        state = self._require_record(record_id)
        self._require_script(record_id)
        if state.phase != EXECUTED:
            raise OneShotWishSaveRefused(
                f'record {record_id}: one-shot wishes save only after a confirmed ON '
                f'(phase {state.phase}, generation {self.generation})')
        state.saved = True
        state.saved_generation = self.generation

    # ------------------------------------------------------------------
    # Attach generations and replay
    # ------------------------------------------------------------------

    def attach(self, generation: int) -> tuple:
        """Start one attach generation; returns the saved wish IDs."""
        if self.attached:
            raise OneShotGenerationConflict(
                f'already attached at generation {self.generation}; detach before a new attach')
        if type(generation) is not int or generation < 1:
            raise OneShotGenerationConflict(
                f'attach generation must be a positive integer, got {generation!r}')
        if generation <= self._last_generation:
            raise OneShotGenerationConflict(
                f'attach generation {generation} must exceed the previous '
                f'generation {self._last_generation}')
        self.attached = True
        self.generation = generation
        self._last_generation = generation
        self._replay_attempted = set()
        return self.saved_wish_ids()

    def detach(self) -> None:
        """End the attach generation; idempotent.

        PENDING attempts are drained to FAILED (unclear attempts are
        never saved and never replayed); session phases reset to
        INACTIVE; saved wishes and per-record attempt history persist
        for the next attach.
        """
        if not self.attached:
            return
        for record_id, state in self._state.items():
            if state.phase == PENDING:
                state.phase = FAILED
                state.last_outcome = 'failed'
                self._pending_source.pop(record_id, None)
                self.attempts.append((record_id, self.generation, 'drain', 'lost'))
            state.phase = INACTIVE
            state.effect_persists = False
        self.attached = False
        self.generation = 0
        self._replay_attempted = set()

    def replay_saved_wishes(self, backend) -> tuple:
        """Re-execute saved one-shot wishes for the current attach.

        Pinned replay rules (one re-run per attach generation):
        - at most one attempt per record per attach generation
          (double-execution guard);
        - a FAILED/UNKNOWN attempt is never replayed
          (skip reason ``failed-or-unknown``);
        - no confirmed attach -> ``not-attached``;
        - a held (PENDING) attempt -> ``held``;
        - an already confirmed ON this session -> ``already-executed``;
        - a successfully replayed wish stays saved (the marker is
          information, not a double-execution source).

        Returns ``(attempted, skipped)``: attempted record IDs (exactly
        one publish each) and ``(record_id, reason)`` skips, sorted.
        """
        wishes = self.saved_wish_ids()
        if not self.attached:
            return (), tuple((rid, 'not-attached') for rid in wishes)
        attempted = []
        skipped = []
        for record_id in wishes:
            state = self._state[record_id]
            if state.phase == PENDING:
                skipped.append((record_id, 'held'))
                continue
            if record_id in self._replay_attempted:
                reason = 'already-executed' if state.phase == EXECUTED else 'failed-or-unknown'
                skipped.append((record_id, reason))
                continue
            if state.last_outcome == 'failed':
                skipped.append((record_id, 'failed-or-unknown'))
                continue
            if state.phase == EXECUTED:
                skipped.append((record_id, 'already-executed'))
                continue
            self._replay_attempted.add(record_id)
            state.attempt_count += 1
            state.phase = PENDING
            self._pending_source[record_id] = 'replay'
            receipt = backend.publish(record_id, self.programs.get(record_id, b''))
            self._resolve_attempt(record_id, receipt, 'replay')
            attempted.append(record_id)
        return tuple(attempted), tuple(skipped)

    # ------------------------------------------------------------------
    # Wish-model marker codec
    # ------------------------------------------------------------------

    def persistent_markers(self) -> list:
        """Persistent per-record state as ``(record_id, phase, attempt_count,
        saved_generation)`` tuples, sorted by record ID.

        Only records with attempt history or a saved wish are emitted.
        The phase is the stable terminal phase: FAILED when the last
        attempt failed or was lost, EXECUTED when it was confirmed,
        INACTIVE when it never ran.  Encoding is refused while any
        attempt is still PENDING (unclear state must not be persisted).
        """
        pending = sorted(rid for rid, state in self._state.items()
                         if state.phase == PENDING)
        if pending:
            raise OneShotContractError(
                'markers cannot be encoded while attempts are pending: '
                + ', '.join(map(str, pending)))
        markers = []
        for record_id in sorted(self._state):
            state = self._state[record_id]
            if state.attempt_count == 0 and not state.saved:
                continue
            if state.last_outcome == 'failed':
                phase = FAILED
            elif state.last_outcome == 'confirmed':
                phase = EXECUTED
            else:
                phase = INACTIVE
            saved_generation = state.saved_generation if state.saved else NOT_SAVED
            markers.append((record_id, phase, state.attempt_count, saved_generation))
        return markers

    def encode_markers(self) -> bytes:
        """Encode this contract's wish model (see module-level
        :func:`encode_markers` for the byte layout)."""
        return encode_markers(self.persistent_markers(),
                              self.ct_hash, self.process_name)

    def decode_markers(self, raw: bytes) -> dict:
        """Decode and validate a marker blob against this contract's
        table hash, process name and script record IDs (full rejection
        on any damage, no partial acceptance)."""
        known = {rid for rid, kind in self.records.items() if kind == 'script'}
        return decode_markers(raw, self.ct_hash, self.process_name,
                              known_records=known)

    def restore_markers(self, raw: bytes) -> dict:
        """Apply a decoded marker blob to this contract (detached only).

        Restores attempt history, wish flags and the replay policy:
        records whose stored phase is FAILED are skipped with
        ``failed-or-unknown`` on the next replay; saved wishes are
        replayed on the next attach.
        """
        if self.attached:
            raise OneShotContractError(
                f'markers can only be restored while detached '
                f'(attached at generation {self.generation})')
        markers = self.decode_markers(raw)
        for state in self._state.values():
            state.phase = INACTIVE
            state.attempt_count = 0
            state.saved = False
            state.saved_generation = NOT_SAVED
            state.last_outcome = None
            state.effect_persists = False
        for record_id, (phase, attempt_count, saved_generation) in markers.items():
            state = self._state[record_id]
            state.attempt_count = attempt_count
            if phase == FAILED:
                state.last_outcome = 'failed'
            elif phase == EXECUTED:
                state.last_outcome = 'confirmed'
            if saved_generation != NOT_SAVED:
                state.saved = True
                state.saved_generation = saved_generation
        return markers


def _validate_identity(ct_hash: str, process_name: str) -> bytes:
    if not isinstance(ct_hash, str) or not _HEX64.fullmatch(ct_hash):
        raise OneShotMarkerError('ct_hash must be 64 lowercase hex sha256 characters')
    if not isinstance(process_name, str) or not 0 < len(process_name) <= _MAX_PROCESS_NAME:
        raise OneShotMarkerError('process_name must be non-empty text (max 260 chars)')
    return bytes.fromhex(ct_hash)


def encode_markers(markers, ct_hash: str, process_name: str) -> bytes:
    """Encode the wish-model marker set deterministically.

    ``markers``: iterable of ``(record_id, phase, attempt_count,
    saved_generation)``; ``phase`` must be a stable phase (PENDING is
    rejected), ``saved_generation`` is NOT_SAVED for unsaved records.
    Byte layout (little-endian)::

        4s   total_len            (byte count after this field)
        8s   magic                TFSH0001
        32s  ct_hash digest
        4s   process_name_len
        ...  process_name (utf-8)
        4s   marker_count
        per marker: 4s record_id | 1s phase | 4s attempt_count |
                    4s saved_generation
        4s   crc32 (over every byte between total_len and the crc field)

    Record IDs are emitted sorted and must be unique.  Repeated
    encodings of equal input are byte-identical.
    """
    digest = _validate_identity(ct_hash, process_name)
    encoded = []
    seen = set()
    for item in markers or ():
        if not isinstance(item, tuple) or len(item) != 4:
            raise OneShotMarkerError(
                'marker must be (record_id, phase, attempt_count, saved_generation): '
                f'{item!r}')
        record_id, phase, attempt_count, saved_generation = item
        if type(record_id) is not int or not 0 <= record_id <= 0xFFFFFFFF:
            raise OneShotMarkerError(f'record ID does not fit the marker format: {record_id!r}')
        if record_id in seen:
            raise OneShotMarkerError(f'duplicate marker for record {record_id}')
        seen.add(record_id)
        if phase not in _STABLE_PHASES:
            raise OneShotMarkerError(
                f'record {record_id}: phase {phase} is not persistable '
                f'(only terminal phases may be stored)')
        if type(attempt_count) is not int or not 0 <= attempt_count <= 0xFFFFFFFF:
            raise OneShotMarkerError(
                f'record {record_id}: attempt_count must be a bounded non-negative integer')
        if type(saved_generation) is not int or not 1 <= saved_generation <= 0xFFFFFFFE:
            if saved_generation != NOT_SAVED:
                raise OneShotMarkerError(
                    f'record {record_id}: saved_generation must be NOT_SAVED or a '
                    f'positive attach generation')
        encoded.append((record_id,
                        struct.pack('<IBII', record_id, _PHASE_BYTE[phase],
                                    attempt_count,
                                    saved_generation if saved_generation != NOT_SAVED
                                    else NOT_SAVED)))
    encoded.sort(key=lambda pair: pair[0])
    name_bytes = process_name.encode('utf-8')
    body = (MAGIC + digest
            + struct.pack('<I', len(name_bytes)) + name_bytes
            + struct.pack('<I', len(encoded))
            + b''.join(blob for _rid, blob in encoded))
    payload = body + struct.pack('<I', zlib.crc32(body) & 0xFFFFFFFF)
    return struct.pack('<I', len(payload)) + payload


def decode_markers(raw, ct_hash: str, process_name: str,
                   known_records=None) -> dict:
    """Decode and validate a marker blob produced by :func:`encode_markers`.

    Any damage or identity mismatch rejects the entire blob
    (:class:`OneShotMarkerError`); there is no partial acceptance.
    ``known_records`` optionally bounds the record IDs to one contract's
    script records.  Returns
    ``{record_id: (phase, attempt_count, saved_generation)}``.
    """
    digest = _validate_identity(ct_hash, process_name)
    if not isinstance(raw, (bytes, bytearray)) or len(raw) < 56:
        raise OneShotMarkerError('marker blob is truncated')
    raw = bytes(raw)
    try:
        (total_len,) = struct.unpack_from('<I', raw, 0)
        if len(raw) != 4 + total_len:
            raise OneShotMarkerError('total length prefix does not match the blob size')
        if raw[4:12] != MAGIC:
            raise OneShotMarkerError('unknown marker magic')
        if raw[12:44] != digest:
            raise OneShotMarkerError('ct_hash binding mismatch (marker belongs to another table)')
        (name_len,) = struct.unpack_from('<I', raw, 44)
        name_end = 48 + name_len
        name = raw[48:name_end].decode('utf-8')
        if name != process_name:
            raise OneShotMarkerError(
                'process_name binding mismatch (marker belongs to another target)')
        (count,) = struct.unpack_from('<I', raw, name_end)
        marker_start = name_end + 4
        marker_end = marker_start + count * _MARKER_LEN
        if marker_end + 4 != len(raw):
            raise OneShotMarkerError('marker count does not match the blob size')
        (stored_crc,) = struct.unpack_from('<I', raw, marker_end)
        if stored_crc != (zlib.crc32(raw[4:marker_end]) & 0xFFFFFFFF):
            raise OneShotMarkerError('crc32 mismatch (marker blob is damaged)')
        markers = {}
        previous = -1
        for index in range(count):
            offset = marker_start + index * _MARKER_LEN
            record_id, phase_byte, attempt_count, saved_generation = \
                struct.unpack_from('<IBII', raw, offset)
            phase = _BYTE_PHASE.get(phase_byte)
            if phase is None:
                raise OneShotMarkerError(
                    f'unknown phase byte {phase_byte} for record {record_id}')
            if record_id <= previous:
                raise OneShotMarkerError(
                    f'markers are not sorted by record ID at record {record_id}')
            if known_records is not None and record_id not in known_records:
                raise OneShotMarkerError(
                    f'record {record_id} is not part of this contract')
            if saved_generation == 0:
                raise OneShotMarkerError(
                    f'record {record_id}: saved_generation 0 is reserved')
            markers[record_id] = (phase, attempt_count, saved_generation)
            previous = record_id
    except UnicodeError as exc:
        raise OneShotMarkerError('process name is not valid utf-8') from exc
    except struct.error as exc:
        raise OneShotMarkerError(f'marker blob is structurally invalid: {exc}') from exc
    return markers

