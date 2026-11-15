"""Owned luacall binding: the reviewed nth-AOB helper route for records
whose AA envelope carries luaCall(...) references.

The owned runtime route behind the engine's luacall activation gate
(``TrainerEngine(luacall_binding_factory=...)``).  The binding covers
exactly the two reviewed nth-AOB helper function names
(``lua_aobscan`` / ``ct2trainerNthAOB``, :data:`aa_luacall.AOB_FUNCTIONS`)
and provides an AOB port backed by the engine's own attached target
memory.  The port is the same owned scan route the record's activation
journals through (``nth_aob.scan_nth``): module-bounded, 1-based
occurrence-nth, identity- and liveness-checked, and a bounded read-only
pass - a scan never writes target memory.

The engine keeps its fail-closed default (no factory: the visible named
refusal before any allocation or write).  The production wiring lives at
the trainer and owned-gate construction sites: the standalone and Master
trainer startup (``ui`` / ``master_trainer``) and the owned scan gate
(``scan_probe``).  A record whose luaCall plan names any other Lua
function stays refused by exact name: the owned route proves the
reviewed helper names only, and the generic table-Lua route for other
functions remains open (AP-11).

Fail-closed named refusals:

- ``NthAOBError``            the module-bounded scan refused the request
                             (no attached memory, identity/liveness
                             changed, module bounds unknown or exceeded,
                             occurrence not found, selected bytes changed
                             before publication) - named by
                             ``nth_aob.scan_nth``
- the gate's own names stay in ``aa_luacall``: uncovered function by
  exact name + line, missing AOB port, malformed binding
"""
from __future__ import annotations

from .aa_luacall import AOB_FUNCTIONS, LuaCallBinding, NthAobPort


class OwnedNthAobPort(NthAobPort):
    """Module-bounded nth-AOB resolution over the attached target memory.

    The scan runs against the engine's attached target memory at call
    time with the identity captured at the call as the expected
    identity: a target that restarts or whose identity the attached
    reader can no longer prove is refused before any address is
    returned.  The read is bounded to the exact module bounds and writes
    nothing.
    """

    def __init__(self, engine):
        self._engine = engine

    def scan(self, *, symbol: str, module: str, pattern: str,
             occurrence: int) -> int:
        from .nth_aob import NthAOBError, scan_nth
        memory = getattr(self._engine, 'memory', None)
        if memory is None:
            raise NthAOBError('Nth-AOB port has no attached target memory')
        definition = {'op': 'nth_aobscan', 'symbol': symbol, 'module': module,
                      'pattern': pattern, 'occurrence': occurrence,
                      'part_index': 0, 'helper': 'ct2trainerNthAOB'}
        result = scan_nth(definition, memory, expected_identity=memory.identity)
        return result['address']


class OwnedLuaCallBinding(LuaCallBinding):
    """The owned luacall route: exactly the two reviewed nth-AOB helper
    function names, with an AOB port on the attached target memory."""

    def __init__(self, engine):
        self._port = OwnedNthAobPort(engine)

    def function_names(self) -> frozenset:
        return frozenset(AOB_FUNCTIONS)

    def aob_port(self) -> NthAobPort | None:
        return self._port


def owned_luacall_binding_factory(engine):
    """Production ``luacall_binding_factory`` for the owned runtime route.

    Returns a fresh owned binding per call; the binding and its port are
    stateless (the port reads the engine's attached target memory at
    call time).
    """
    return OwnedLuaCallBinding(engine)
