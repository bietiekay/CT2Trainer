"""Managed-runtime session binding for the Lua-facing Mono surface (AP-04/05).

The embedded trainer corpus reaches the target's managed runtime through a
small, fixed surface (Yooka-Laylee shape)::

    LaunchMonoDataCollector()
    mono_enumDomains()
    mono_findMethod(namespace, class, method)
    mono_invoke_method(domain, method, isStatic, args)

where every ``args`` entry is ``{type=vt..., value=...}`` with the CE value
type names ``vtByte|vtWord|vtDWord|vtQWord|vtSingle|vtDouble|vtPointer|
vtObject|vtString|vtChar|vtByRef|vtGeneric`` (example:
``mono_invoke_method(domain, method, 0, args)`` with
``args[1] = {type=vtByte, value=1}``).

This module owns the session contract the engine adopts (duck-typed: the
engine works with whatever object its injected factory returns) and provides
:class:`ManagedRuntimeSession`, the reference implementation that drives the
tested stage models :mod:`ct2trainer.native.mono_runtime` (stage 2) over
:mod:`ct2trainer.native.mono_broker` (stage 1).

Session contract (structural):

- ``pid`` (int): the target PID; the engine cross-checks it against the
  attached session identity before adoption;
- ``bootstrapped`` (bool, read-only): the frozen bootstrap was admitted;
- ``domains() -> list[dict]``: one ``{'id', 'ptr', 'generation'}`` entry per
  visible domain of the bound route;
- ``find_method(namespace, class_name, method_name) -> int``: resolves one
  method token (``1..0xFFFFFFFF``) through the injected resolver;
- ``invoke(*, domain_id, method_token, is_static, arguments) -> bool``:
  dispatches one reversible typed call; ``arguments`` is a tuple of
  ``(vt_name, value)`` pairs; returns ``True`` only on a success ack, raises
  a named error on refusal or an unknown outcome;
- ``target_ended() -> None``: confirmed target exit; MUST never raise
  (uncertainty is recorded on the session instead);
- ``release() -> None``: trainer-close retirement; MUST never raise. The
  tested runtime contract forbids closing the route before target end
  (``CleanupBeforeTargetEndRefused``) and requires balanced live sessions, so
  trainer-close retirement is bookkeeping only: the module hold stays with
  the backend/adapter through process exit.

Fail-closed named refusals (all effect-free):

- ``ManagedSessionNotAttached``   no session / closed trainer / not
                                  bootstrapped where the facade gates it
- ``ManagedSessionBadPid``        session identity mismatch (engine gate)
- ``ManagedSessionReleased``      invoke after retirement or target end
- ``ManagedSessionNotBootstrapped`` the frozen bootstrap was never admitted
- ``ManagedDomainRefused``        domain argument is not the bound domain
- ``ManagedValueRefused``         malformed names, tokens or value types
- ``ManagedCallFailed``           terminal failure of the managed call
                                  (including a success ack without the undo
                                  receipt a reversible contract requires)
- ``ManagedCallUnknown``          terminal unknown (ack lost, timeout, or an
                                  exception after a one-shot effect); no
                                  retry, save or replay is ever offered
"""
from __future__ import annotations

import secrets

from .mono_broker import (
    ARG_BYREF,
    ARG_GENERIC,
    ARG_INSTANCE_REF,
    ARG_STATIC_BYTES,
    ARG_STRING,
    CONTRACT_REVERSIBLE,
    InvocationSpec,
    STATE_ACK_SUCCESS,
    STATE_UNKNOWN,
)
from .mono_runtime import AdapterBinding, FrozenBootstrap, MonoRuntime

#: CE value type names mapped onto the broker's typed argument kinds
#: (case-insensitive; ``vt`` prefix folded away before lookup).
_VALUE_TYPES = {
    'byte': ARG_STATIC_BYTES,
    'word': ARG_STATIC_BYTES,
    'dword': ARG_STATIC_BYTES,
    'qword': ARG_STATIC_BYTES,
    'single': ARG_STATIC_BYTES,
    'double': ARG_STATIC_BYTES,
    'char': ARG_STATIC_BYTES,
    'pointer': ARG_STATIC_BYTES,
    'object': ARG_INSTANCE_REF,
    'string': ARG_STRING,
    'byref': ARG_BYREF,
    'generic': ARG_GENERIC,
}

#: Terminal broker states that mean "the outcome is unknown" (the possible
#: one-shot effect may or may not have landed; no retry is ever offered).
_UNKNOWN_TERMINAL = {STATE_UNKNOWN, 'ack_lost', 'timeout'}


class ManagedSessionError(ValueError):
    """Base of the named managed-session refusals."""


class ManagedSessionNotAttached(ManagedSessionError):
    """No managed session is attached (or the trainer is closed)."""


class ManagedSessionBadPid(ManagedSessionError):
    """The session binds a different target identity than the engine."""


class ManagedSessionNotBootstrapped(ManagedSessionError):
    """The frozen bootstrap was never admitted on this route."""


class ManagedSessionReleased(ManagedSessionError):
    """The session was retired (trainer close or confirmed target exit)."""


class ManagedDomainRefused(ManagedSessionError):
    """The requested domain is not the domain the route is bound to."""


class ManagedValueRefused(ManagedSessionError):
    """A method name, token or managed value type is malformed."""


class ManagedCallFailed(ManagedSessionError):
    """The managed call ended in a terminal failure state."""


class ManagedCallUnknown(ManagedSessionError):
    """The managed call ended in a terminal unknown state."""


def _vt_kind(vt_name: str) -> str:
    if not isinstance(vt_name, str):
        raise ManagedValueRefused('value type must be text, got '
                                  f'{type(vt_name).__name__}')
    key = vt_name.casefold()
    if key.startswith('vt'):
        key = key[2:]
    kind = _VALUE_TYPES.get(key)
    if kind is None:
        raise ManagedValueRefused(f'Unknown managed value type: {vt_name!r}')
    return kind


class ManagedRuntimeSession:
    """Reference session driving the tested :class:`MonoRuntime` route.

    The constructor performs the full bring-up (open + one frozen bootstrap)
    so a factory that returns this object has already either produced a
    working session or raised a named refusal. Every later invocation uses a
    fresh one-shot CAS token (the bootstrap consumed token ``1``).
    """

    def __init__(self, *, binding: AdapterBinding, backend, now_qpc,
                 method_resolver, ack_provider,
                 deadline_margin_qpc: int = 30_000_000) -> None:
        if not isinstance(binding, AdapterBinding):
            raise ManagedValueRefused('binding must be an AdapterBinding')
        if not callable(method_resolver):
            raise ManagedValueRefused('method_resolver must be callable')
        if not callable(ack_provider):
            raise ManagedValueRefused('ack_provider must be callable')
        if type(deadline_margin_qpc) is not int or deadline_margin_qpc <= 0:
            raise ManagedValueRefused(
                'deadline_margin_qpc must be a positive integer')
        self._binding = binding
        self._method_resolver = method_resolver
        self._ack_provider = ack_provider
        self._deadline_margin_qpc = deadline_margin_qpc
        self.uncertainty: str | None = None
        self._ended = False
        self._released = False
        self._next_token = 2  # token 1 belongs to the frozen bootstrap
        self._runtime = MonoRuntime(binding, backend=backend, now_qpc=now_qpc)
        self._runtime.open()
        message = FrozenBootstrap(
            owner_module_sha256=binding.module_sha256,
            pid=binding.pid,
            created_time=binding.creation_time,
            deadline_qpc=int(now_qpc()) + deadline_margin_qpc,
            nonce=secrets.token_hex(16),
        )
        self._runtime.bootstrap(message, token=1)

    # -- contract surface ---------------------------------------------------

    @property
    def pid(self) -> int:
        return self._binding.pid

    @property
    def bootstrapped(self) -> bool:
        return self._runtime.snapshot()['bootstrapped']

    def domains(self) -> list[dict]:
        domain = self._runtime.snapshot()['domain']
        return [{'id': domain['domain_id'], 'ptr': domain['domain_ptr'],
                 'generation': domain['generation']}]

    def find_method(self, namespace: str, class_name: str, method_name: str) -> int:
        for value, name in ((namespace, 'namespace'),
                            (class_name, 'class_name'),
                            (method_name, 'method_name')):
            if not isinstance(value, str) or not value:
                raise ManagedValueRefused(f'{name} must be non-empty text')
        token = self._method_resolver(namespace, class_name, method_name)
        if type(token) is not int or not 1 <= token <= 0xFFFFFFFF:
            raise ManagedValueRefused(
                f'method resolver returned an invalid token: {token!r}')
        return token

    def invoke(self, *, domain_id: int, method_token: int, is_static: bool,
               arguments: tuple) -> bool:
        if self._released or self._ended:
            raise ManagedSessionReleased(
                'managed session is retired; the target identity is gone')
        if not self._runtime.snapshot()['bootstrapped']:
            raise ManagedSessionNotBootstrapped(
                'managed session is not bootstrapped; invoke is unavailable')
        if type(domain_id) is not int or domain_id < 0:
            raise ManagedDomainRefused(
                f'domain id must be a nonnegative integer, got {domain_id!r}')
        bound_id = self._runtime.snapshot()['domain']['domain_id']
        if domain_id != bound_id:
            raise ManagedDomainRefused(
                f'domain id {domain_id} does not match the bound domain '
                f'{bound_id}')
        if type(method_token) is not int or not 1 <= method_token <= 0xFFFFFFFF:
            raise ManagedValueRefused(
                f'method token must be an integer in 1..0xFFFFFFFF, '
                f'got {method_token!r}')
        kinds = []
        for item in arguments:
            if not isinstance(item, (tuple, list)) or len(item) != 2:
                raise ManagedValueRefused(
                    'arguments must be (vt_name, value) pairs, got '
                    f'{item!r}')
            kinds.append(_vt_kind(item[0]))
        spec = InvocationSpec(method_token=method_token,
                              is_instance=not is_static,
                              argument_kinds=tuple(kinds),
                              contract=CONTRACT_REVERSIBLE)
        token = self._next_token
        self._next_token += 1
        deadline = int(self._runtime.snapshot()['broker']['now_qpc']) + \
            self._deadline_margin_qpc
        session_id = self._runtime.invoke(
            spec, token=token, deadline_qpc=deadline,
            signature=(not is_static, len(kinds)))
        self._runtime.dispatch(session_id)
        self._runtime.start(session_id)
        ack = self._ack_provider(session_id)
        if ack is None:
            # The ACK never arrived: terminal unknown, never retried.
            self._runtime.ack_lost(session_id)
        else:
            ok, exception, effect_observed, undo_receipt = ack
            if ok and undo_receipt is None:
                # A reversible contract must carry its undo receipt into a
                # success ack; without one the call is refused un-acked.
                raise ManagedCallFailed(
                    'Reversible call was acked without an undo receipt')
            if ok:
                self._runtime.record_undo(session_id, undo_receipt)
                self._runtime.ack(session_id, ok=True)
            else:
                self._runtime.ack(session_id, ok=False, exception=exception,
                                  effect_observed=effect_observed)
        state = self._final_state(session_id)
        if state == STATE_ACK_SUCCESS:
            return True
        if state in _UNKNOWN_TERMINAL:
            raise ManagedCallUnknown(
                f'managed call ended in terminal state {state!r}; the '
                'possible effect is recorded and never retried')
        raise ManagedCallFailed(
            f'managed call ended in terminal state {state!r}')

    def target_ended(self) -> None:
        """Confirmed target exit; must never raise (records uncertainty)."""
        if self._ended or self._released:
            return
        try:
            self._runtime.mark_target_ended()
        except Exception as exc:
            self.uncertainty = str(exc)
        try:
            self._runtime.close()
        except Exception as exc:
            # Live sessions (e.g. the prepared bootstrap) keep the route
            # unbalanced; the hold stays with the adapter through exit.
            self.uncertainty = str(exc)
        self._ended = True

    def release(self) -> None:
        """Trainer-close retirement; must never raise.

        The tested runtime contract refuses ``close()`` before target end, so
        retirement here is bookkeeping only; the module hold stays with the
        backend/adapter until the process exits.
        """
        self._released = True

    # -- internals -----------------------------------------------------------

    def _final_state(self, session_id: int) -> str:
        for session in self._runtime.snapshot()['broker']['sessions']:
            if session['session_id'] == session_id:
                return session['state']
        raise ManagedCallUnknown(
            f'managed call session {session_id} vanished from the broker '
            'snapshot')
