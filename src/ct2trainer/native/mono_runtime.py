"""Engine-side Mono runtime route (AP-04 stage 2, pure Python model).

This module binds the typed broker (``mono_broker``) to the own C adapter
contract (``mono/mono_api.c``: ``tf_mono_api_select``/``tf_mono_api_discard``;
``mono/mono_collector.c``: ``tf_mono_bind_existing``/``tf_mono_get_jit``) as
the route an engine uses to reach a target's managed runtime. The C adapter
holds only an already-loaded current-process module, resolves exactly the 42
typed exports pinned in
``dependencies/native/mono-api-source/api-prototypes.json``, and refuses every
request whose owner identity or QPC deadline no longer admits it. No process,
no DLL load and no managed execution happens in this model layer: tests
inject fake adapter backends, and the ctypes cross-checks against the built
``CT2TrainerMonoExisting.dll`` fixtures live in
``tests/test_native_mono_runtime.py``.

Semantics (explicit Native contract, stage 2):

- ``AdapterBinding`` freezes module SHA-256, the pinned export table, target
  PID, FILETIME creation time and bitness. Any divergence at ``open()`` or in
  a bootstrap message is a named refusal
  (``BindingRefused``/``ExportTableRefused``/``OwnerMismatchRefused``).
- the bound domain keeps pointer, ID and generation; the root domain ID
  ``0`` is valid; a stale rebind is ``StaleDomainRefused``.
- a held DLL module does not fence Mono domain cleanup: after
  ``mark_domain_unloaded()`` the route stays module-held, every new request
  is ``DomainUnloadedRefused``, in-flight sessions become terminal unknown,
  and the snapshot surfaces ``domain.visible_unknown``. Prepared sessions
  remain safely cancellable (CAS before start).
- no cleanup before target end: ``close()`` before ``mark_target_ended()`` is
  ``CleanupBeforeTargetEndRefused``; at close, live sessions, GC handles and
  attached threads must be balanced (``UnbalancedCloseRefused``).
- the frozen bootstrap message carries owner SHA, PID, FILETIME creation
  time, QPC deadline and a one-shot nonce; only one bootstrap is admitted per
  route (``BootstrapReplayRefused``) and a nonce is consumed forever
  (``NonceReplayRefused``).
- ACK loss, timeout and an exception after a one-shot effect yield unknown
  sessions with a tainted method token; the route offers no retry, save or
  replay (``UnknownRetryRefused``).
- getter contracts never mutate: a patch extent on a getter is
  ``GetterMutationRefused``.
- patch extents come only from the per-method ``tf_mono_get_jit`` model
  (short code sizes, ``1..1 MiB``); an unregistered or divergent extent is
  ``JitExtentRefused`` and no blanket span is ever derived.
- GC handles and thread attach/detach stay balanced; detach without attach
  or a double detach is ``ThreadBalanceRefused``.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
import sys

from .mono_broker import (
    API_PROTOTYPES_SCHEMA,
    CONTRACT_GETTER,
    CONTRACT_IRREVERSIBLE,
    CONTRACT_REVERSIBLE,
    DomainBinding,
    ExportPin,
    InvocationSpec,
    MonoBroker,
    MonoBrokerError,
    MonoBrokerIdentity,
    ContractViolation,
    DeadlineRefused,
    GCHandleRefused,
    InvalidTransitionError,
    JitExtentRefused,
    OwnerMismatchRefused,
    RunningNotCancelable,
    StaleDomainRefused,
    ThreadBalanceRefused,
    TokenReplayRefused,
    UnknownRetryRefused,
    UnsupportedSignatureRefused,
)

SCHEMA = 'ct2trainer-mono-runtime/v1'
MAX_JIT_CODE_SIZE = 1024 * 1024      # C model: size > 1MiB is TF_QUOTA
JIT_PROBE_BYTES = 32                 # C model: tf_mono_jit.first_bytes[32]
BOOTSTRAP_METHOD_TOKEN = 0x74660001  # 'tf' + 0001, inside the 32-bit token domain
_TERMINAL_STATES = {'cancelled', 'ack_success', 'ack_failure', 'ack_lost',
                    'timeout', 'unknown'}


class MonoRuntimeError(ValueError):
    """Base class for named, bounded runtime-route refusals."""


class NotOpenRefused(MonoRuntimeError):
    pass


class BindingRefused(MonoRuntimeError):
    pass


class ExportTableRefused(MonoRuntimeError):
    pass


class DomainUnloadedRefused(MonoRuntimeError):
    pass


class TargetEndedRefused(MonoRuntimeError):
    pass


class NotBootstrappedRefused(MonoRuntimeError):
    pass


class BootstrapReplayRefused(MonoRuntimeError):
    pass


class NonceReplayRefused(MonoRuntimeError):
    pass


class GetterMutationRefused(MonoRuntimeError):
    pass


class CleanupBeforeTargetEndRefused(MonoRuntimeError):
    pass


class UnbalancedCloseRefused(MonoRuntimeError):
    pass


def _check_hex_sha(value, what: str) -> str:
    if (not isinstance(value, str) or len(value) != 64
            or any(c not in '0123456789abcdef' for c in value)):
        raise MonoRuntimeError(f'{what} must be 64 lowercase hex chars')
    return value


def _check_pid(value, what: str = 'pid') -> int:
    if type(value) is not int or not 1 <= value <= 0xFFFFFFFF:
        raise MonoRuntimeError(f'{what} must be an integer in 1..4294967295')
    return value


def _check_filetime(value, what: str = 'creation_time') -> int:
    if type(value) is not int or not 0 <= value <= 0xFFFFFFFFFFFFFFFF:
        raise MonoRuntimeError(f'{what} must be a FILETIME in 0..2^64-1')
    return value


def _default_export_table_path() -> Path:
    """Locate the pinned table in source mode and frozen builds alike.

    In a PyInstaller bundle ``__file__`` points inside ``sys._MEIPASS``, so
    the table must be resolved against the bundle root; the build ships it
    there via --add-data at the same relative path as the repo checkout.
    """
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base = Path(__file__).resolve().parents[3]
    return base / 'dependencies/native/mono-api-source/api-prototypes.json'


def load_pinned_export_table(path=None) -> tuple[ExportPin, ...]:
    """Load the pinned 42-export table from ``api-prototypes.json``."""
    if path is None:
        path = _default_export_table_path()
    raw = json.loads(Path(path).read_text(encoding='utf-8'))
    if raw.get('schema') != API_PROTOTYPES_SCHEMA:
        raise MonoRuntimeError(f'pinned table schema mismatch: {raw.get("schema")!r}')
    return tuple(ExportPin(e['export'], e['field']) for e in raw['required_exports'])


PINNED_EXPORTS = load_pinned_export_table()


@dataclass(frozen=True)
class AdapterBinding:
    """Exact adapter identity every message re-binds before any work.

    ``exports`` is the exact 42-entry pinned table from
    ``api-prototypes.json`` (schema ``ct2trainer-mono-api-prototypes/v1``);
    divergence from the pinned table is refused at construction.
    """

    module_sha256: str
    exports: tuple[ExportPin, ...]
    pid: int
    creation_time: int
    bitness: int

    def __post_init__(self) -> None:
        _check_hex_sha(self.module_sha256, 'module_sha256')
        if len(self.exports) != 42:
            raise MonoRuntimeError(
                f'binding must carry exactly the 42 pinned exports, got {len(self.exports)}')
        seen = set()
        for pin in self.exports:
            if not isinstance(pin.export, str) or not pin.export:
                raise MonoRuntimeError('export name must be a nonempty string')
            if not pin.field.startswith('tf_'):
                raise MonoRuntimeError(
                    f'export field must start with tf_: {pin.field}')
            if pin.export in seen:
                raise MonoRuntimeError(
                    f'duplicate export in binding table: {pin.export}')
            seen.add(pin.export)
        pinned = {pin.export for pin in PINNED_EXPORTS}
        if seen != pinned:
            missing = sorted(pinned - seen)
            extra = sorted(seen - pinned)
            raise MonoRuntimeError(
                'binding export table diverges from the pinned table '
                f'(missing={missing[:3]}, extra={extra[:3]})')
        if [pin.export for pin in self.exports] != [pin.export for pin in PINNED_EXPORTS] \
                or [pin.field for pin in self.exports] != [pin.field for pin in PINNED_EXPORTS]:
            raise MonoRuntimeError(
                'binding export table order/fields diverge from the pinned table')
        _check_pid(self.pid)
        _check_filetime(self.creation_time)
        if self.bitness not in (32, 64):
            raise MonoRuntimeError('bitness must be 32 or 64')

    @classmethod
    def for_module(cls, module_sha256: str, pid: int, creation_time: int,
                   bitness: int) -> 'AdapterBinding':
        """Build a binding over the pinned 42-export table for one target."""
        return cls(module_sha256, PINNED_EXPORTS, pid, creation_time, bitness)


@dataclass(frozen=True)
class FrozenBootstrap:
    """One frozen broker bootstrap message (never retried or reserialized).

    Carries the owner identity (module SHA), target PID, FILETIME creation
    time, the QPC deadline and a one-shot nonce.
    """

    owner_module_sha256: str
    pid: int
    created_time: int
    deadline_qpc: int
    nonce: str

    def __post_init__(self) -> None:
        _check_hex_sha(self.owner_module_sha256, 'owner_module_sha256')
        _check_pid(self.pid)
        _check_filetime(self.created_time, 'created_time')
        if type(self.deadline_qpc) is not int or self.deadline_qpc < 0:
            raise MonoRuntimeError('deadline_qpc must be a nonnegative integer')
        if not isinstance(self.nonce, str) or not self.nonce:
            raise MonoRuntimeError('nonce must be a nonempty string')


@dataclass(frozen=True)
class JitExtent:
    """Per-method JIT code extent as reported by the ``tf_mono_get_jit`` model.

    ``code_size`` is the exact declared code size of one method (short spans);
    it is the maximum patch extent for that method. ``first_bytes`` holds
    ``min(code_size, 32)`` leading bytes, mirroring ``tf_mono_jit``.
    """

    method_token: int
    address: int
    code_size: int
    domain_id: int
    first_bytes: bytes

    def __post_init__(self) -> None:
        if (type(self.method_token) is not int
                or not 1 <= self.method_token <= 0xFFFFFFFF):
            raise MonoRuntimeError(
                'method_token must be an integer in 1..0xFFFFFFFF')
        if (type(self.address) is not int
                or not 1 <= self.address <= 0xFFFFFFFFFFFFFFFF):
            raise MonoRuntimeError('address must be a nonzero 64-bit integer')
        if (type(self.code_size) is not int
                or not 1 <= self.code_size <= MAX_JIT_CODE_SIZE):
            raise MonoRuntimeError(
                f'code_size must be an integer in 1..{MAX_JIT_CODE_SIZE} '
                '(tf_mono_get_jit model)')
        if type(self.domain_id) is not int or not 0 <= self.domain_id <= 0xFFFFFFFF:
            raise MonoRuntimeError('domain_id must be an unsigned 32-bit integer')
        if not isinstance(self.first_bytes, (bytes, bytearray)):
            raise MonoRuntimeError('first_bytes must be bytes')
        if len(self.first_bytes) != min(self.code_size, JIT_PROBE_BYTES):
            raise MonoRuntimeError(
                'first_bytes must hold exactly min(code_size, 32) bytes')
        object.__setattr__(self, 'first_bytes', bytes(self.first_bytes))


class AdapterBackend(ABC):
    """Injectable adapter surface mirroring the C exports and process facts.

    ``module_handle``/``module_sha256`` describe the already-loaded target
    module; ``pid``/``created_time``/``bitness`` its identity; ``exports`` the
    export names it admits; ``domain_identity`` the bound root domain; and
    ``jit_info`` models ``tf_mono_get_jit`` (``None`` = probe refused or no
    method, i.e. no extent may be derived).
    """

    @abstractmethod
    def module_handle(self) -> int:
        """Nonzero handle of the loaded module (mirrors HMODULE)."""

    @abstractmethod
    def module_sha256(self) -> str:
        """SHA-256 of the exact loaded image bytes."""

    @abstractmethod
    def exports(self) -> set:
        """Export names the loaded module admits (strings)."""

    @abstractmethod
    def pid(self) -> int:
        """Target process ID."""

    @abstractmethod
    def created_time(self) -> int:
        """Target FILETIME creation time."""

    @abstractmethod
    def bitness(self) -> int:
        """Target bitness (32 or 64)."""

    @abstractmethod
    def domain_identity(self) -> tuple:
        """``(domain_ptr, domain_id, generation)`` of the bound root domain."""

    @abstractmethod
    def jit_info(self, method_token: int):
        """``JitExtent`` for the token or ``None`` when the probe refuses."""


class MonoRuntime:
    """Engine-side route binding the typed broker to the adapter contract.

    ``now_qpc`` is an injected monotonic clock in QPC ticks; no wall clock is
    read anywhere. The binding itself carries the exact pinned 42-export
    table used as the reference at ``open()``.
    """

    def __init__(self, binding: AdapterBinding, *, backend: AdapterBackend,
                 now_qpc) -> None:
        if not isinstance(binding, AdapterBinding):
            raise MonoRuntimeError('binding must be an AdapterBinding')
        if not isinstance(backend, AdapterBackend):
            raise MonoRuntimeError('backend must be an AdapterBackend')
        if not callable(now_qpc):
            raise MonoRuntimeError('now_qpc must be a trusted callable')
        self._binding = binding
        self._backend = backend
        self._clock = now_qpc
        self._broker: MonoBroker | None = None
        self._domain: DomainBinding | None = None
        self._open = False
        self._closed = False
        self._unloaded = False
        self._target_ended = False
        self._bootstrapped = False
        self._nonces: set[str] = set()
        self._module_held = False
        self._jit: dict[int, JitExtent] = {}

    # -- gates ---------------------------------------------------------------

    def _require_open(self) -> None:
        if self._closed:
            raise InvalidTransitionError('route is closed; no further work is admitted')
        if not self._open:
            raise NotOpenRefused('runtime route is not bound to a target')

    def _require_work(self) -> None:
        self._require_open()
        if self._unloaded:
            raise DomainUnloadedRefused(
                'domain is unloaded; the held module does not fence cleanup')
        if self._target_ended:
            raise TargetEndedRefused('target has ended; no new work is admitted')

    def _broker_ref(self) -> MonoBroker:
        if self._broker is None:
            raise NotOpenRefused('runtime route is not bound to a target')
        return self._broker

    # -- binding --------------------------------------------------------------

    def open(self) -> None:
        """Bind the backend to the frozen binding; named refusals on divergence.

        Order mirrors the C admission: handle, module identity, owner
        identity, export table coverage, then the root domain binding.
        """
        if self._closed:
            raise InvalidTransitionError('route is closed; no further work is admitted')
        if self._open:
            return
        backend = self._backend
        handle = backend.module_handle()
        if type(handle) is not int or handle <= 0:
            raise BindingRefused('adapter module handle is invalid')
        sha = backend.module_sha256()
        if sha != self._binding.module_sha256:
            raise BindingRefused(
                f'loaded module sha256 {sha} does not match the pinned '
                f'{self._binding.module_sha256}')
        facts = (('pid', backend.pid(), self._binding.pid),
                 ('creation_time', backend.created_time(),
                  self._binding.creation_time),
                 ('bitness', backend.bitness(), self._binding.bitness))
        for name, actual, expected in facts:
            if actual != expected:
                raise OwnerMismatchRefused(
                    f'target {name} diverges from the pinned binding '
                    f'({actual} != {expected})')
        exposed = set(backend.exports())
        missing = [pin.export for pin in self._binding.exports
                   if pin.export not in exposed]
        if missing:
            raise ExportTableRefused(
                'loaded module is missing pinned exports: ' + ', '.join(missing[:4]))
        domain_ptr, domain_id, generation = backend.domain_identity()
        self._domain = DomainBinding(domain_ptr, domain_id, generation)
        self._broker = MonoBroker(
            MonoBrokerIdentity(self._binding.module_sha256, self._binding.exports,
                               self._binding.pid, self._binding.creation_time,
                               self._binding.bitness),
            self._domain, now_qpc=self._clock)
        self._module_held = True
        self._open = True

    # -- domain lifecycle -------------------------------------------------------

    def bind_domain(self, *, domain_ptr: int, domain_id: int, generation: int) -> None:
        """Re-bind the session domain; root domain ID 0 is valid."""
        self._require_work()
        self._broker_ref().bind_domain(domain_ptr=domain_ptr, domain_id=domain_id,
                                       generation=generation)

    def mark_domain_unloaded(self) -> None:
        """Confirmed unload. The held module does not fence it.

        In-flight (dispatched/running) sessions can no longer be
        acknowledged and become terminal unknown with a tainted method
        token. Prepared sessions stay safely cancellable (CAS before start).
        The module hold itself persists until close after target end.
        """
        self._require_open()
        if self._unloaded:
            return
        self._unloaded = True
        broker = self._broker_ref()
        broker.mark_domain_unloaded()
        for session in broker.snapshot()['sessions']:
            if session['state'] in ('dispatched', 'running'):
                broker.ack_lost(session['session_id'])

    def mark_target_ended(self) -> None:
        """Target process end confirmed; only cleanup remains from now on."""
        self._require_open()
        self._target_ended = True

    def close(self) -> None:
        """Release the route; only after target end and full balance."""
        self._require_open()
        if not self._target_ended:
            raise CleanupBeforeTargetEndRefused(
                'no cleanup before target end; the module hold stays through '
                'process exit')
        broker = self._broker_ref()
        snapshot = broker.snapshot()
        live = [s for s in snapshot['sessions'] if s['state'] not in _TERMINAL_STATES]
        if live:
            raise UnbalancedCloseRefused(
                f'{len(live)} live session(s) must reach a terminal state before close')
        if snapshot['gc_handles'] or snapshot['attached_threads']:
            raise UnbalancedCloseRefused(
                'GC handles or attached threads are not balanced at close')
        self._closed = True
        self._module_held = False

    # -- frozen bootstrap ------------------------------------------------------

    def bootstrap(self, message: FrozenBootstrap, *, token: int) -> int:
        """Admit the one frozen bootstrap message and open its session.

        The message re-binds owner identity, the deadline must be open on the
        injected clock, and the nonce is consumed forever. The bootstrap
        session itself is a getter-contract CAS session; it follows the
        normal dispatch/start/ack lifecycle afterwards.
        """
        self._require_work()
        if self._bootstrapped:
            raise BootstrapReplayRefused(
                'the frozen bootstrap is one-shot per route')
        owner = (message.pid, message.created_time,
                 message.owner_module_sha256)
        pinned = (self._binding.pid, self._binding.creation_time,
                  self._binding.module_sha256)
        if owner != pinned:
            raise OwnerMismatchRefused(
                'bootstrap owner does not match the pinned binding '
                '(pid, created_time or module sha diverged)')
        if message.nonce in self._nonces:
            raise NonceReplayRefused(
                f'nonce {message.nonce!r} was already consumed')
        # The nonce is consumed as soon as the message is admitted (owner
        # verified), so a retried message must carry a fresh nonce even when
        # the first attempt failed for another reason.
        self._nonces.add(message.nonce)
        if message.deadline_qpc <= self._clock():
            raise DeadlineRefused('bootstrap deadline is not in the future')
        spec = InvocationSpec(method_token=BOOTSTRAP_METHOD_TOKEN,
                              is_instance=False, argument_kinds=(),
                              contract=CONTRACT_GETTER)
        session = self._broker_ref().prepare(
            spec, token=token, deadline_qpc=message.deadline_qpc,
            signature=(False, 0))
        self._bootstrapped = True
        return session

    # -- invocations -------------------------------------------------------------

    def invoke(self, spec: InvocationSpec, *, token: int, deadline_qpc: int,
               signature: tuple, capabilities: frozenset = frozenset(),
               patch_extent: int = 0,
               owner: tuple | None = None) -> int:
        """Prepare one typed invocation through the bound broker.

        Getters never mutate (any patch extent is refused). Patch extents
        must match the per-method JIT extent registered from the
        ``tf_mono_get_jit`` model; no blanket span is ever derived.
        """
        self._require_work()
        if not self._bootstrapped:
            raise NotBootstrappedRefused(
                'bootstrap the frozen broker before invoking')
        if spec.contract == CONTRACT_GETTER and patch_extent > 0:
            raise GetterMutationRefused(
                'getter contract never mutates; patch extents are refused')
        if patch_extent > 0:
            extent = self._jit.get(spec.method_token)
            if extent is None:
                extent = self.request_jit_extent(spec.method_token)
            if spec.jit_info_extent != extent.code_size:
                raise JitExtentRefused(
                    f'declared jit_info_extent {spec.jit_info_extent} diverges '
                    f'from the probed code size {extent.code_size}')
            if patch_extent > extent.code_size:
                raise JitExtentRefused(
                    f'patch extent {patch_extent} exceeds the probed code size '
                    f'{extent.code_size}; no blanket span is derived')
        return self._broker_ref().prepare(
            spec, token=token, deadline_qpc=deadline_qpc,
            signature=signature, capabilities=capabilities,
            patch_extent=patch_extent, owner=owner)

    # -- JIT extents ---------------------------------------------------------------

    def request_jit_extent(self, method_token: int) -> JitExtent:
        """Probe the adapter for one method's JIT extent (tf_mono_get_jit).

        A refused or missing probe leaves no extent registered: callers
        must never derive a blanket span.
        """
        self._require_work()
        extent = self._backend.jit_info(method_token)
        if extent is None:
            raise JitExtentRefused(
                f'no JIT extent admitted for method token {method_token}; '
                'no blanket span is ever derived')
        self.register_jit_extent(extent)
        return extent

    def register_jit_extent(self, extent: JitExtent) -> None:
        """Record one probed extent; a divergent re-registration is refused."""
        self._require_work()
        if not isinstance(extent, JitExtent):
            raise MonoRuntimeError('extent must be a JitExtent')
        if extent.domain_id != self._domain.domain_id:
            raise JitExtentRefused(
                f'extent domain id {extent.domain_id} does not match the bound '
                f'domain {self._domain.domain_id}')
        existing = self._jit.get(extent.method_token)
        if existing is not None and existing != extent:
            raise JitExtentRefused(
                f'JIT extent for method token {extent.method_token} diverged '
                f'(size {existing.code_size} -> {extent.code_size})')
        self._jit[extent.method_token] = extent

    # -- session control -------------------------------------------------------------

    def dispatch(self, session_id: int) -> None:
        """CAS-complete a prepared session; refused after domain unload."""
        self._require_work()
        if self._unloaded:
            raise DomainUnloadedRefused(
                'cannot dispatch work on an unloaded domain')
        self._broker_ref().dispatch(session_id)

    def start(self, session_id: int) -> None:
        self._require_work()
        self._broker_ref().start(session_id)

    def cancel(self, session_id: int) -> None:
        """CAS before start: still safe on a prepared session after unload."""
        self._require_open()
        self._broker_ref().cancel(session_id)

    def record_undo(self, session_id: int, receipt) -> None:
        self._require_work()
        self._broker_ref().record_undo(session_id, receipt)

    def ack(self, session_id: int, *, ok: bool, exception: str | None = None,
            effect_observed: bool = False) -> None:
        """Acknowledge a managed call; a lost ACK is terminal unknown."""
        self._require_work()
        self._broker_ref().ack(session_id, ok=ok, exception=exception,
                              effect_observed=effect_observed)

    def ack_lost(self, session_id: int) -> None:
        """The ACK never arrived: terminal unknown, no retry/save/replay."""
        self._require_work()
        self._broker_ref().ack_lost(session_id)

    def timeout(self, session_id: int) -> None:
        self._require_work()
        self._broker_ref().timeout(session_id)

    def late_completion(self, session_id: int, receipt) -> None:
        """Logged only on a terminal session; it never reverts state.

        Remains available after close: a completion arriving after cleanup is
        still logged, but it can never mutate or resurrect state.
        """
        if self._broker is None:
            raise NotOpenRefused('runtime route is not bound to a target')
        self._broker.late_completion(session_id, receipt)

    # -- GC handles / threads -----------------------------------------------------

    def gc_acquire(self, obj_token: int) -> int:
        self._require_work()
        return self._broker_ref().gc_acquire(obj_token)

    def gc_release(self, handle: int) -> None:
        self._require_work()
        self._broker_ref().gc_release(handle)

    def gc_target(self, handle: int) -> int:
        self._require_work()
        return self._broker_ref().gc_target(handle)

    def thread_attach(self) -> int:
        self._require_work()
        return self._broker_ref().thread_attach()

    def thread_detach(self, thread: int) -> None:
        """Detach must mirror a previous attach exactly once."""
        self._require_work()
        self._broker_ref().thread_detach(thread)

    # -- introspection -------------------------------------------------------------

    def snapshot(self) -> dict:
        """Responsive, deterministic read; surfaces the domain visibility.

        Read-only: it stays available after close so the final released state
        can still be inspected.
        """
        if self._broker is None:
            raise NotOpenRefused('runtime route is not bound to a target')
        broker_snapshot = self._broker.snapshot()
        domain = dict(broker_snapshot['domain'])
        domain['visible_unknown'] = self._unloaded
        return {
            'schema': SCHEMA,
            'binding': {
                'module_sha256': self._binding.module_sha256,
                'export_count': len(self._binding.exports),
                'pid': self._binding.pid,
                'creation_time': self._binding.creation_time,
                'bitness': self._binding.bitness,
            },
            'module_held': self._module_held,
            'target_ended': self._target_ended,
            'closed': self._closed,
            'bootstrapped': self._bootstrapped,
            'nonces_consumed': len(self._nonces),
            'domain': domain,
            'jit_extents': {
                token: {'address': extent.address,
                        'code_size': extent.code_size,
                        'domain_id': extent.domain_id}
                for token, extent in sorted(self._jit.items())
            },
            'broker': broker_snapshot,
        }
