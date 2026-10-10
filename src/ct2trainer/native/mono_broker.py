"""Typed Mono broker message/state model (AP-04 stage 1, pure Python).

The model captures the broker contract the own C adapter must satisfy:
``src/ct2trainer/native/mono/mono_api.c`` / ``mono_collector.c`` expose the
42 typed direct exports pinned in
``dependencies/native/mono-api-source/api-prototypes.json``
(schema ``ct2trainer-mono-api-prototypes/v1``); this module models how
broker messages bind to that identity, how invocations are prepared,
dispatched and acknowledged, and which transitions are refused. No C, no
ctypes, no processes and no managed execution: every bound is checked in
pure Python and every refusal is a named exception.

Semantics (explicit Native contract, stage 1):

- every message re-binds the exact broker identity (module SHA-256, pinned
  export table, PID + FILETIME creation time, bitness); any divergence is
  ``OwnerMismatchRefused``.
- the session domain binding keeps the domain pointer, domain ID and
  generation; the root domain ID ``0`` is valid; a stale pointer or
  generation is ``StaleDomainRefused``.
- invocations carry a method token and typed argument descriptors
  (``static_bytes`` / ``instance_ref`` / ``string`` / ``byref`` / ``vararg``
  / ``generic``). ``byref``/``vararg``/``generic`` are refused by default
  unless an explicit capability token names that kind; getter contracts
  refuse them unconditionally (read-only contract, no write budget).
- one-shot CAS token: a token is consumed forever; reuse is
  ``TokenReplayRefused``.
- session flow ``prepared -> dispatched -> running -> terminal``;
  ``cancel()`` is legal only while ``prepared`` (CAS before start is the
  only safe cancellation). Cancellation after dispatch/start is
  ``RunningNotCancelable``: a started managed call is never force-terminated
  and its buffers are never freed early.
- ``ack`` loss, a deadline timeout or an exception after a one-shot effect
  yields the terminal state ``unknown`` with a recorded possible partial
  effect; after ``unknown`` there is never an automatic retry, replay or
  save, and a fresh invocation of the same method token is
  ``UnknownRetryRefused``.
- late completion on a terminal session is logged only and never reverts
  state; on a live session it is refused.
- the deadline is given in QPC ticks against an injected clock (no wall
  clock); an expired deadline at prepare or dispatch is refused.
- GC handles: acquire/release/target; after ``mark_domain_unloaded()`` every
  GC operation is refused (the OS-held image cannot fence unload).
- thread attach/detach must stay balanced; detach without attach or a
  double detach is refused.
- a patch extent larger than the declared JitInfo code size is
  ``JitExtentRefused`` (no blanket patch spans).
- contract classes: ``getter`` (read-only, no write budget, no save),
  ``reversible`` (requires a registered undo receipt before a success ack),
  ``irreversible`` (one-shot: no retry, no save, no replay; the method token
  is never reusable).
- ``snapshot()`` stays responsive: it reports sessions, holds, handles and
  thread balance without mutating state.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass

SCHEMA = 'ct2trainer-mono-broker/v1'
API_PROTOTYPES_SCHEMA = 'ct2trainer-mono-api-prototypes/v1'

CONTRACT_GETTER = 'getter'
CONTRACT_REVERSIBLE = 'reversible'
CONTRACT_IRREVERSIBLE = 'irreversible'
_CONTRACTS = {CONTRACT_GETTER, CONTRACT_REVERSIBLE, CONTRACT_IRREVERSIBLE}

ARG_STATIC_BYTES = 'static_bytes'
ARG_INSTANCE_REF = 'instance_ref'
ARG_STRING = 'string'
ARG_BYREF = 'byref'
ARG_VARARG = 'vararg'
ARG_GENERIC = 'generic'
_ARGUMENT_KINDS = {ARG_STATIC_BYTES, ARG_INSTANCE_REF, ARG_STRING,
                   ARG_BYREF, ARG_VARARG, ARG_GENERIC}
_MUTABLE_KINDS = {ARG_BYREF, ARG_VARARG, ARG_GENERIC}

STATE_PREPARED = 'prepared'
STATE_DISPATCHED = 'dispatched'
STATE_RUNNING = 'running'
STATE_CANCELLED = 'cancelled'
STATE_ACK_SUCCESS = 'ack_success'
STATE_ACK_FAILURE = 'ack_failure'
STATE_ACK_LOST = 'ack_lost'
STATE_TIMEOUT = 'timeout'
STATE_UNKNOWN = 'unknown'
_TERMINAL = {STATE_CANCELLED, STATE_ACK_SUCCESS, STATE_ACK_FAILURE,
             STATE_ACK_LOST, STATE_TIMEOUT, STATE_UNKNOWN}

MAX_SESSIONS = 4096
MAX_LOG_ENTRIES = 64
MAX_ARGUMENTS = 256
MAX_PATCH_EXTENT = 64 * 1024 * 1024
_INT32_MIN, _INT32_MAX = -(1 << 31), (1 << 31) - 1
_SHA256_HEX = 64


class MonoBrokerError(ValueError):
    """Base class for named, bounded broker refusals."""


class OwnerMismatchRefused(MonoBrokerError):
    pass


class StaleDomainRefused(MonoBrokerError):
    pass


class UnsupportedSignatureRefused(MonoBrokerError):
    pass


class TokenReplayRefused(MonoBrokerError):
    pass


class UnknownRetryRefused(MonoBrokerError):
    pass


class RunningNotCancelable(MonoBrokerError):
    pass


class DeadlineRefused(MonoBrokerError):
    pass


class GCHandleRefused(MonoBrokerError):
    pass


class ThreadBalanceRefused(MonoBrokerError):
    pass


class JitExtentRefused(MonoBrokerError):
    pass


class ContractViolation(MonoBrokerError):
    pass


class InvalidTransitionError(MonoBrokerError):
    pass


def _check_int(value, minimum, maximum, what: str) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise MonoBrokerError(f'{what} must be an integer in {minimum}..{maximum}')
    return value


def _check_nonempty_str(value, what: str) -> str:
    if not isinstance(value, str) or not value:
        raise MonoBrokerError(f'{what} must be a nonempty string')
    return value


@dataclass(frozen=True)
class ExportPin:
    """One pinned direct export: upstream name and own adapter field."""

    export: str
    field: str


@dataclass(frozen=True)
class MonoBrokerIdentity:
    """Exact broker identity every message re-binds before any work.

    ``exports`` mirrors the 42 typed exports of
    ``api-prototypes.json`` (schema ``API_PROTOTYPES_SCHEMA``) as
    ``(export, field)`` pairs; the JSON itself is not copied into this
    model.
    """

    module_sha256: str
    exports: tuple[ExportPin, ...]
    pid: int
    creation_time: int
    bitness: int

    def __post_init__(self) -> None:
        sha = self.module_sha256
        if (not isinstance(sha, str) or len(sha) != _SHA256_HEX
                or any(c not in '0123456789abcdef' for c in sha)):
            raise MonoBrokerError('module_sha256 must be 64 lowercase hex chars')
        if len(self.exports) == 0:
            raise MonoBrokerError('export table must not be empty')
        seen = set()
        for pin in self.exports:
            _check_nonempty_str(pin.export, 'export name')
            if not pin.field.startswith('tf_'):
                raise MonoBrokerError(f'export field must start with tf_: {pin.field}')
            if pin.export in seen:
                raise MonoBrokerError(f'duplicate export in pinned table: {pin.export}')
            seen.add(pin.export)
        _check_int(self.pid, 1, 2 ** 32 - 1, 'pid')
        _check_int(self.creation_time, 0, 2 ** 64 - 1, 'creation_time')
        if self.bitness not in (32, 64):
            raise MonoBrokerError('bitness must be 32 or 64')


@dataclass(frozen=True)
class DomainBinding:
    """Domain pointer + ID + generation a session is bound to.

    The root domain ID ``0`` is valid (``mono_get_root_domain``).
    """

    domain_ptr: int
    domain_id: int
    generation: int

    def __post_init__(self) -> None:
        _check_int(self.domain_ptr, 0, 2 ** 64 - 1, 'domain_ptr')
        _check_int(self.domain_id, _INT32_MIN, _INT32_MAX, 'domain_id')
        _check_int(self.generation, 1, 2 ** 63 - 1, 'generation')


@dataclass(frozen=True)
class InvocationSpec:
    """One typed invocation as derived from the metadata, not from runtime.

    ``argument_kinds`` holds one descriptor kind per parameter;
    ``jit_info_extent`` is the declared JitInfo code size in bytes that a
    patch may not exceed (0 = no patch budget).
    """

    method_token: int
    is_instance: bool
    argument_kinds: tuple[str, ...]
    contract: str
    jit_info_extent: int = 0

    def __post_init__(self) -> None:
        _check_int(self.method_token, 1, 0xFFFFFFFF, 'method_token')
        if not isinstance(self.is_instance, bool):
            raise MonoBrokerError('is_instance must be a bool')
        if self.contract not in _CONTRACTS:
            raise MonoBrokerError(
                f'contract must be one of {sorted(_CONTRACTS)}, got {self.contract!r}')
        if len(self.argument_kinds) > MAX_ARGUMENTS:
            raise MonoBrokerError(f'more than {MAX_ARGUMENTS} arguments')
        for kind in self.argument_kinds:
            if kind not in _ARGUMENT_KINDS:
                raise MonoBrokerError(f'unknown argument kind: {kind!r}')
        _check_int(self.jit_info_extent, 0, MAX_PATCH_EXTENT, 'jit_info_extent')


class _Session:
    __slots__ = ('session_id', 'spec', 'state', 'token', 'deadline_qpc',
                 'undo_receipt', 'unknown_effect', 'log')

    def __init__(self, session_id: int, spec: InvocationSpec, token: int,
                 deadline_qpc: int) -> None:
        self.session_id = session_id
        self.spec = spec
        self.state = STATE_PREPARED
        self.token = token
        self.deadline_qpc = deadline_qpc
        self.undo_receipt = None
        self.unknown_effect = False
        self.log: list[str] = []

    def note(self, entry: str) -> None:
        if len(self.log) < MAX_LOG_ENTRIES:
            self.log.append(entry)

    def to_dict(self) -> dict:
        return {
            'session_id': self.session_id,
            'method_token': self.spec.method_token,
            'contract': self.spec.contract,
            'state': self.state,
            'token': self.token,
            'deadline_qpc': self.deadline_qpc,
            'undo_receipt': self.undo_receipt,
            'unknown_effect': self.unknown_effect,
            'log': list(self.log),
        }


class MonoBroker:
    """Pure state machine over the typed Mono broker contract.

    ``now_qpc`` is an injected monotonic clock in QPC ticks; no wall clock
    is read anywhere.
    """

    def __init__(self, identity: MonoBrokerIdentity, domain: DomainBinding,
                 *, now_qpc) -> None:
        if not callable(now_qpc):
            raise MonoBrokerError('now_qpc must be a trusted callable')
        self._identity = identity
        self._domain = domain
        self._clock = now_qpc
        self._sessions: dict[int, _Session] = {}
        self._session_ids = itertools.count(1)
        self._used_tokens: set[int] = set()
        self._unknown_method_tokens: set[int] = set()
        self._irreversible_method_tokens: set[int] = set()
        self._handles: dict[int, int] = {}
        self._handles_seq = itertools.count(1)
        self._domain_unloaded = False
        self._threads: set[int] = set()
        self._thread_seq = itertools.count(1)

    # -- identity / domain -------------------------------------------------

    def _check_owner(self, *, pid: int, creation_time: int,
                     module_sha256: str) -> None:
        if (pid, creation_time, module_sha256) != (
                self._identity.pid, self._identity.creation_time,
                self._identity.module_sha256):
            raise OwnerMismatchRefused(
                'message owner does not match the pinned broker identity '
                '(pid, creation_time or module sha diverged)')

    def bind_domain(self, *, domain_ptr: int, domain_id: int,
                    generation: int) -> None:
        """Re-bind the session domain; any divergence is refused."""
        if generation != self._domain.generation:
            raise StaleDomainRefused(
                f'domain generation {generation} != bound {self._domain.generation}')
        if domain_ptr != self._domain.domain_ptr:
            raise StaleDomainRefused('domain pointer diverges from the bound domain')
        if domain_id != self._domain.domain_id:
            raise StaleDomainRefused('domain ID diverges from the bound domain')

    def mark_domain_unloaded(self) -> None:
        """Confirmed domain unload; every GC operation is refused from now on."""
        self._domain_unloaded = True

    # -- invocations ---------------------------------------------------------

    def prepare(self, spec: InvocationSpec, *, token: int, deadline_qpc: int,
                signature: tuple[bool, int],
                capabilities: frozenset[str] = frozenset(),
                patch_extent: int = 0,
                owner: tuple[int, int, str] | None = None) -> int:
        """Validate one invocation and open its prepared session.

        ``signature`` is the expected ``(is_instance, param_count)`` from
        the metadata; ``capabilities`` explicitly authorizes otherwise
        refused argument kinds; ``patch_extent`` is the byte count a patch
        would touch; ``owner`` (pid, creation_time, module sha) re-binds
        the identity when given.
        """
        if owner is not None:
            self._check_owner(pid=owner[0], creation_time=owner[1],
                              module_sha256=owner[2])
        if len(self._sessions) >= MAX_SESSIONS:
            raise MonoBrokerError(f'more than {MAX_SESSIONS} tracked sessions')
        _check_int(token, 1, 2 ** 63 - 1, 'token')
        if token in self._used_tokens:
            raise TokenReplayRefused(f'token {token} was already consumed')
        if spec.method_token in self._unknown_method_tokens:
            raise UnknownRetryRefused(
                f'method token {spec.method_token} has an unknown effect; '
                'no retry, replay or save is ever allowed')
        if spec.contract == CONTRACT_IRREVERSIBLE and spec.method_token in self._irreversible_method_tokens:
            raise TokenReplayRefused(
                f'method token {spec.method_token} was already used by an '
                'irreversible invocation; one-shot only')
        now = self._clock()
        _check_int(deadline_qpc, 0, 2 ** 64 - 1, 'deadline_qpc')
        if deadline_qpc <= now:
            raise DeadlineRefused('deadline is not in the future at prepare')
        is_instance, param_count = signature
        if type(is_instance) is not bool or not isinstance(param_count, int):
            raise UnsupportedSignatureRefused(
                'signature must be (is_instance: bool, param_count: int)')
        if spec.is_instance != is_instance:
            raise UnsupportedSignatureRefused(
                f'static/instance contract mismatch '
                f'(spec {spec.is_instance}, signature {is_instance})')
        if len(spec.argument_kinds) != param_count:
            raise UnsupportedSignatureRefused(
                f'argument count {len(spec.argument_kinds)} != '
                f'expected {param_count}')
        for kind in spec.argument_kinds:
            if kind in _MUTABLE_KINDS:
                if spec.contract == CONTRACT_GETTER:
                    raise UnsupportedSignatureRefused(
                        f'getter contract cannot carry mutable argument {kind!r}')
                if kind not in capabilities:
                    raise UnsupportedSignatureRefused(
                        f'argument kind {kind!r} requires an explicit capability token')
        _check_int(patch_extent, 0, MAX_PATCH_EXTENT, 'patch_extent')
        if patch_extent > spec.jit_info_extent:
            raise JitExtentRefused(
                f'patch extent {patch_extent} exceeds declared '
                f'jit_info_extent {spec.jit_info_extent}')
        session = _Session(next(self._session_ids), spec, token, deadline_qpc)
        session.note('prepared')
        self._sessions[session.session_id] = session
        self._used_tokens.add(token)
        if spec.contract == CONTRACT_IRREVERSIBLE:
            self._irreversible_method_tokens.add(spec.method_token)
        return session.session_id

    def _session(self, session_id: int) -> _Session:
        if type(session_id) is not int or session_id not in self._sessions:
            raise InvalidTransitionError(f'unknown session {session_id!r}')
        return self._sessions[session_id]

    def _require_live(self, session: _Session, what: str) -> None:
        if session.state in _TERMINAL:
            raise InvalidTransitionError(
                f'{what} is not allowed on terminal session {session.session_id} '
                f'({session.state})')

    def dispatch(self, session_id: int) -> None:
        """CAS-complete the prepared session into the in-flight state."""
        session = self._session(session_id)
        self._require_live(session, 'dispatch')
        if session.state != STATE_PREPARED:
            raise InvalidTransitionError(f'dispatch requires prepared, got {session.state}')
        if self._clock() >= session.deadline_qpc:
            session.state = STATE_TIMEOUT
            session.unknown_effect = True
            session.note('timeout: deadline expired before dispatch')
            self._unknown_method_tokens.add(session.spec.method_token)
            raise DeadlineRefused(
                f'session {session_id} deadline expired before dispatch')
        session.state = STATE_DISPATCHED
        session.note('dispatched')

    def start(self, session_id: int) -> None:
        """The managed call starts; cancellation is impossible from here on."""
        session = self._session(session_id)
        self._require_live(session, 'start')
        if session.state != STATE_DISPATCHED:
            raise InvalidTransitionError(f'start requires dispatched, got {session.state}')
        session.state = STATE_RUNNING
        session.note('running')

    def cancel(self, session_id: int) -> None:
        """CAS before start: the only safe cancellation.

        Legal only while ``prepared``; afterwards a started (or in-flight)
        managed call is never force-terminated, so the refusal is named
        ``RunningNotCancelable`` and no buffer is freed early.
        """
        session = self._session(session_id)
        self._require_live(session, 'cancel')
        if session.state != STATE_PREPARED:
            raise RunningNotCancelable(
                f'session {session.session_id} is {session.state}; '
                'started managed calls are never force-terminated')
        session.state = STATE_CANCELLED
        session.note('cancelled')

    def record_undo(self, session_id: int, receipt) -> None:
        """Register the undo receipt a reversible contract must have ready."""
        session = self._session(session_id)
        if session.spec.contract != CONTRACT_REVERSIBLE:
            raise ContractViolation('undo receipts belong to reversible contracts')
        self._require_live(session, 'record_undo')
        if receipt is None:
            raise ContractViolation('undo receipt must not be None')
        session.undo_receipt = receipt
        session.note('undo receipt registered')

    def ack(self, session_id: int, *, ok: bool, exception: str | None = None,
            effect_observed: bool = False) -> None:
        """Acknowledge the managed call result.

        ``effect_observed`` marks the exception-after-one-shot-effect case:
        the result is then terminal ``unknown`` with a recorded possible
        partial effect, never a plain failure.
        """
        session = self._session(session_id)
        self._require_live(session, 'ack')
        if session.state != STATE_RUNNING:
            raise InvalidTransitionError(f'ack requires running, got {session.state}')
        if ok:
            if (session.spec.contract == CONTRACT_REVERSIBLE
                    and session.undo_receipt is None):
                raise ContractViolation(
                    'reversible contract requires a registered undo receipt '
                    'before a success ack')
            session.state = STATE_ACK_SUCCESS
            session.note('ack success')
            return
        if effect_observed:
            session.state = STATE_UNKNOWN
            session.unknown_effect = True
            session.note(f'unknown: exception after one-shot effect: {exception}')
            self._unknown_method_tokens.add(session.spec.method_token)
            return
        session.state = STATE_ACK_FAILURE
        session.note(f'ack failure: {exception}')

    def ack_lost(self, session_id: int) -> None:
        """The ACK never arrived: terminal unknown, no automatic replay."""
        session = self._session(session_id)
        self._require_live(session, 'ack_lost')
        if session.state not in (STATE_DISPATCHED, STATE_RUNNING):
            raise InvalidTransitionError(f'ack_lost requires an in-flight session, got {session.state}')
        session.state = STATE_ACK_LOST
        session.unknown_effect = True
        session.note('ack lost')
        self._unknown_method_tokens.add(session.spec.method_token)

    def timeout(self, session_id: int) -> None:
        """Deadline exceeded while in flight: terminal unknown."""
        session = self._session(session_id)
        self._require_live(session, 'timeout')
        if session.state not in (STATE_DISPATCHED, STATE_RUNNING):
            raise InvalidTransitionError(f'timeout requires an in-flight session, got {session.state}')
        if self._clock() < session.deadline_qpc:
            raise DeadlineRefused('deadline has not expired yet')
        session.state = STATE_TIMEOUT
        session.unknown_effect = True
        session.note('timeout: deadline exceeded in flight')
        self._unknown_method_tokens.add(session.spec.method_token)

    def late_completion(self, session_id: int, receipt) -> None:
        """A completion that arrives after the terminal state.

        Logged only; it never reverts state. On a live session it is
        refused (use the ack path instead).
        """
        session = self._session(session_id)
        if session.state not in _TERMINAL:
            raise InvalidTransitionError(
                f'late completion requires a terminal session, got {session.state}')
        session.note(f'late completion logged (receipt={receipt!r}); state stays {session.state}')

    # -- GC handles ----------------------------------------------------------

    def gc_acquire(self, obj_token: int) -> int:
        _check_int(obj_token, 1, 2 ** 32 - 1, 'obj_token')
        if self._domain_unloaded:
            raise GCHandleRefused('domain is unloaded; GC handles cannot be acquired')
        handle = next(self._handles_seq)
        self._handles[handle] = obj_token
        return handle

    def gc_release(self, handle: int) -> None:
        if self._domain_unloaded:
            raise GCHandleRefused('domain is unloaded; GC handles cannot be released')
        if handle not in self._handles:
            raise GCHandleRefused(f'unknown or already released GC handle {handle}')
        del self._handles[handle]

    def gc_target(self, handle: int) -> int:
        if self._domain_unloaded:
            raise GCHandleRefused('domain is unloaded; GC handles cannot be inspected')
        if handle not in self._handles:
            raise GCHandleRefused(f'unknown or already released GC handle {handle}')
        return self._handles[handle]

    # -- threads ---------------------------------------------------------------

    def thread_attach(self) -> int:
        if self._domain_unloaded:
            raise ThreadBalanceRefused('domain is unloaded; threads cannot attach')
        thread = next(self._thread_seq)
        self._threads.add(thread)
        return thread

    def thread_detach(self, thread: int) -> None:
        if thread not in self._threads:
            raise ThreadBalanceRefused(
                f'thread {thread} has no matching attach (detach without attach '
                'or double detach)')
        self._threads.discard(thread)

    # -- introspection -----------------------------------------------------------

    def snapshot(self) -> dict:
        """Responsive, deterministic read: sessions, holds, handles, threads."""
        sessions = [self._sessions[sid].to_dict() for sid in sorted(self._sessions)]
        return {
            'schema': SCHEMA,
            'identity': {
                'module_sha256': self._identity.module_sha256,
                'export_count': len(self._identity.exports),
                'pid': self._identity.pid,
                'creation_time': self._identity.creation_time,
                'bitness': self._identity.bitness,
            },
            'domain': {
                'domain_ptr': self._domain.domain_ptr,
                'domain_id': self._domain.domain_id,
                'generation': self._domain.generation,
                'unloaded': self._domain_unloaded,
            },
            'now_qpc': self._clock(),
            'sessions': sessions,
            'unknown_method_tokens': sorted(self._unknown_method_tokens),
            'gc_handles': len(self._handles),
            'attached_threads': sorted(self._threads),
            'counts': {
                'sessions': len(sessions),
                'terminal': sum(1 for s in sessions if s['state'] in _TERMINAL),
                'unknown_effect': sum(1 for s in sessions if s['unknown_effect']),
            },
        }
