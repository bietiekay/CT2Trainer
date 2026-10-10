"""Debugger session binding for the Lua-facing debugger surface.

The CE corpus exposes the debugger surface as the flat calls
``attachProcess(pid)`` and ``detachProcess()``. The engine owns at most one
session binding per attached target: it is created lazily through an
injected ``debugger_factory(engine, memory)`` when ``attachProcess`` is
called, and retired on confirmed target exit and close (mirroring the
call-broker lifecycle). The tested :mod:`debug_coordinator` remains the
scoped quiescence owner for write publication; a persistent owned Windows
debug attach route stays open (AP-11), so the default trainer (no factory)
refuses visibly fail-closed instead of inventing debugger state.

Session binding contract (structural, duck-typed):

- ``pid`` (int): the target PID the binding is bound to; the engine
  cross-checks it against the attached session identity before adoption;
- ``attached`` (bool, read-only): current attach state;
- ``detach()``: total; detaches the debugger even when the target already
  exited, and never raises into the poll/close path (uncertainty is
  recorded by the binding itself, e.g. in a ``last_error`` attribute).

Fail-closed named refusals (all effect-free, raised by the engine facade):

- ``DebuggerNotAttached``      no attached target session, no configured
                               binding, or no live session to detach
- ``DebuggerBadPid``           the attach argument is not the attached
                               target PID, or the binding binds a different
                               target identity
- ``DebuggerAlreadyAttached``  a session binding is already active
"""
from __future__ import annotations


class DebuggerBindingError(ValueError):
    """Base of the named debugger binding refusals."""


class DebuggerNotAttached(DebuggerBindingError):
    """No attached target session or no live debugger session."""


class DebuggerBadPid(DebuggerBindingError):
    """The requested or bound target identity is not the session target."""


class DebuggerAlreadyAttached(DebuggerBindingError):
    """A debugger session is already attached to the target."""
