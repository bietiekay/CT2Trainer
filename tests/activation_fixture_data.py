"""Synthetic fixture data for the AP-07 activation lifecycle lane.

Self-contained (no TableReferences, no game inputs): deterministic
parent/child trees that exercise all four parent-child flag classes,
a cycle case, a consumer-ownership tree, and the moBindActivation
blocked-flag cases.  Also provides a deterministic, scriptable target
backend double so tests can pin exact controller behavior for
effect-OK, fail-before-effect, fail-after-effect and late-completion
scenarios without any real target process.

Trees
-----

full_flag_tree::

    1 action (root)
    +-- 2 required_dependency
    |   +-- 3 required_dependency
    |   +-- 4 required_dependency
    +-- 5 direct_activation
    |   +-- 6 required_dependency (under 5)
    +-- 7 navigation
    |   +-- 8 action (under navigation)
    |   +-- 9 action (under navigation)
    +-- 10 collective_off
        +-- 11 action
        +-- 12 action
    20 action (standalone)
    21 async
    22 value_only

cycle_tree: 40 -> 41 -> 42 -> 40 (required chain, rejected).
self_loop_record: 50 parent of itself (rejected by the policy table).
ownership_tree::

    50 action (root)
    +-- 51 required_dependency
    +-- 52 direct_activation
    53 action (standalone, disjoint)

mobind_tree: 30 carries moBindActivation itself; 32 (required child of
31) carries it inside the cascade; 33 is a clean standalone record.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ct2trainer.native.activation_policy import (
    CompensationReceipt,
    RecordSpec,
    RecordTable,
    RELATION_REQUIRED,
)
from ct2trainer.native.parent_flags import (
    ConsumerOwnershipTracker,
    FLAG_COLLECTIVE_OFF,
    FLAG_DIRECT_ACTIVATION,
    FLAG_NAVIGATION,
    FLAG_REQUIRED_DEPENDENCY,
    ParentFlagBinding,
    ParentFlagTopology,
)
from ct2trainer.native.activation_policy import FLAG_MO_BIND_ACTIVATION

# ---------------------------------------------------------------------------
# Record definitions (kinds only; parent_ids are derived from the bindings
# by ParentFlagTopology, which keeps the two views consistent by
# construction and rejects conflicts loudly).
# ---------------------------------------------------------------------------

FULL_RECORDS = [
    RecordSpec(1, 'action'),
    RecordSpec(2, 'action'),
    RecordSpec(3, 'action'),
    RecordSpec(4, 'action'),
    RecordSpec(5, 'action'),
    RecordSpec(6, 'action'),
    RecordSpec(7, 'navigation'),
    RecordSpec(8, 'action'),
    RecordSpec(9, 'action'),
    RecordSpec(10, 'action'),
    RecordSpec(11, 'action'),
    RecordSpec(12, 'action'),
    RecordSpec(20, 'action'),
    RecordSpec(21, 'async'),
    RecordSpec(22, 'value_only'),
]

FULL_BINDINGS = [
    ParentFlagBinding(1, 2, FLAG_REQUIRED_DEPENDENCY),
    ParentFlagBinding(2, 3, FLAG_REQUIRED_DEPENDENCY),
    ParentFlagBinding(2, 4, FLAG_REQUIRED_DEPENDENCY),
    ParentFlagBinding(1, 5, FLAG_DIRECT_ACTIVATION),
    ParentFlagBinding(5, 6, FLAG_REQUIRED_DEPENDENCY),
    ParentFlagBinding(1, 7, FLAG_NAVIGATION),
    ParentFlagBinding(7, 8, FLAG_NAVIGATION),
    ParentFlagBinding(7, 9, FLAG_NAVIGATION),
    ParentFlagBinding(1, 10, FLAG_COLLECTIVE_OFF),
    ParentFlagBinding(10, 11, FLAG_COLLECTIVE_OFF),
    ParentFlagBinding(10, 12, FLAG_COLLECTIVE_OFF),
]

CYCLE_RECORDS = [
    RecordSpec(40, 'action'),
    RecordSpec(41, 'action'),
    RecordSpec(42, 'action'),
]

CYCLE_BINDINGS = [
    ParentFlagBinding(40, 41, FLAG_REQUIRED_DEPENDENCY),
    ParentFlagBinding(41, 42, FLAG_REQUIRED_DEPENDENCY),
    ParentFlagBinding(42, 40, FLAG_REQUIRED_DEPENDENCY),
]

SELF_LOOP_RECORDS = [RecordSpec(50, 'action')]
SELF_LOOP_RELATIONS = {50: {50: RELATION_REQUIRED}}

OWNERSHIP_RECORDS = [
    RecordSpec(50, 'action'),
    RecordSpec(51, 'action'),
    RecordSpec(52, 'action'),
    RecordSpec(53, 'action'),
]

OWNERSHIP_BINDINGS = [
    ParentFlagBinding(50, 51, FLAG_REQUIRED_DEPENDENCY),
    ParentFlagBinding(50, 52, FLAG_DIRECT_ACTIVATION),
]

MOBIND_RECORDS = [
    RecordSpec(30, 'action'),
    RecordSpec(31, 'action'),
    RecordSpec(32, 'action'),
    RecordSpec(33, 'action'),
]

MOBIND_BINDINGS = [
    ParentFlagBinding(31, 32, FLAG_REQUIRED_DEPENDENCY),
]

MOBIND_FLAGS = {
    30: {FLAG_MO_BIND_ACTIVATION},
    32: {FLAG_MO_BIND_ACTIVATION},
}


def full_flag_topology() -> ParentFlagTopology:
    """All four flag classes in one tree (see module docstring)."""
    return ParentFlagTopology(FULL_RECORDS, FULL_BINDINGS)


def full_flag_table() -> RecordTable:
    return full_flag_topology().table


def ownership_topology() -> ParentFlagTopology:
    return ParentFlagTopology(OWNERSHIP_RECORDS, OWNERSHIP_BINDINGS)


def mobind_topology() -> ParentFlagTopology:
    return ParentFlagTopology(MOBIND_RECORDS, MOBIND_BINDINGS,
                              flags=MOBIND_FLAGS)


# ---------------------------------------------------------------------------
# Scripted target backend double
# ---------------------------------------------------------------------------

class BackendOutcome(Enum):
    """Deterministic scripted target behavior for one published request."""

    EFFECT_OK = 'effect-ok'
    FAIL_BEFORE_EFFECT = 'fail-before-effect'
    FAIL_AFTER_EFFECT = 'fail-after-effect'
    LATE_COMPLETION = 'late-completion'


DEFAULT_OUTCOME = BackendOutcome.EFFECT_OK


@dataclass
class ScriptedBackendDouble:
    """Injectable target-side double with a deterministic outcome script.

    Each :meth:`advance` consumes the next scripted outcome (or
    :data:`DEFAULT_OUTCOME` once the script is exhausted) and records the
    invocation so tests can assert the exact publish sequence.
    """

    script: tuple = ()
    invocations: list = field(default_factory=list)
    _cursor: int = 0

    @property
    def remaining(self) -> int:
        return len(self.script) - self._cursor

    def advance(self, record_id: int, direction: str = 'activate') -> BackendOutcome:
        if self._cursor < len(self.script):
            outcome = self.script[self._cursor]
        else:
            outcome = DEFAULT_OUTCOME
        self._cursor += 1
        self.invocations.append((record_id, direction, outcome))
        return outcome


@dataclass(frozen=True)
class DriveResult:
    """Outcome of one full request lifecycle driven through the double."""

    request_id: int
    outcome: BackendOutcome
    generation: int
    receipt: CompensationReceipt | None


def drive_request(controller, backend: ScriptedBackendDouble, record_id: int,
                  intent: str = 'activate',
                  hold_before_complete: bool = False) -> DriveResult:
    """Run request -> dispatch -> publish -> scripted outcome -> terminal
    controller transition for one record.

    The scripted outcome decides the terminal state:

    - EFFECT_OK: confirm_success with the request generation (private
      receipt returned; effects become active).
    - FAIL_BEFORE_EFFECT: fail_before_effect (terminal_failed, no hold,
      no active effects, no receipt).
    - FAIL_AFTER_EFFECT: fail_after_effect (unknown, safety hold on the
      whole sub-tree, no receipt).
    - LATE_COMPLETION: the controller first resolves the request as a
      safe failure (no effect landed), then the target's completion
      arrives late and is only logged (never reverts or mutates state).

    ``hold_before_complete`` parks the request in ``held`` right after
    publish, before the scripted outcome is applied (used to pin
    cancel-during-held-publish behavior).
    """
    request_id = controller.request(record_id, intent)
    generation = controller.request_generation(request_id)
    controller.dispatch(request_id)
    controller.publish(request_id)
    if hold_before_complete:
        controller.hold(request_id)
    outcome = backend.advance(record_id, intent)
    receipt = None
    if outcome is BackendOutcome.EFFECT_OK:
        receipt = controller.confirm_success(request_id, generation)
    elif outcome is BackendOutcome.FAIL_BEFORE_EFFECT:
        controller.fail_before_effect(request_id)
    elif outcome is BackendOutcome.FAIL_AFTER_EFFECT:
        controller.fail_after_effect(request_id)
    elif outcome is BackendOutcome.LATE_COMPLETION:
        controller.fail_before_effect(request_id)
        late_receipt = CompensationReceipt(request_id, record_id, intent,
                                           True, generation)
        controller.late_completion(request_id, late_receipt)
    else:  # pragma: no cover - enum is closed
        raise ValueError('Unscripted backend outcome: %r' % (outcome,))
    return DriveResult(request_id, outcome, generation, receipt)


def fresh_full_controller(attached: bool = True):
    """(ActivationController, ScriptedBackendDouble) on the full tree."""
    from ct2trainer.native.activation_policy import ActivationController
    controller = ActivationController(full_flag_table())
    if attached:
        controller.attach_confirmed()
    return controller, ScriptedBackendDouble()


def fresh_ownership_tracker() -> ConsumerOwnershipTracker:
    return ConsumerOwnershipTracker()
