"""Parent/child activation policy model, independently implemented (AP-07 stage 1).

The model captures the CT activation contract as a pure state machine:
record kinds, parent-child relations, selection projection, an owner queue
with generations, safety holds after uncertain partial effects, and the
save/replay boundary (only independently confirmed ON wishes are saved and
replayed). Cheat Engine implementation code is not used; the public
MemoryRecord contract (activate/deactivate children, collective behavior)
is the derivation source.

Semantics (explicit Native contract, stage 1):

- record kinds: ``action`` (toggleable effect), ``navigation`` (structure
  only), ``async`` (runs only after attach), ``value_only`` (value, no
  toggle).
- parent-child relations:
  - ``required_dependency``: ON and OFF follow the parent.
  - ``direct_activation``: the child keeps its own wish; the parent ON only
    activates it when the child wish is set.
  - ``navigation``: structural grouping, no effect propagation.
  - ``collective_off``: parent OFF deactivates only explicitly active
    children; hidden children are untouched.
- ``moBindActivation`` stays blocked: it cannot be derived from child
  flags and is always a named ``ActivationBlocked`` refusal, whether the
  flag is on the target or on any record inside the cascade.
- a request refuses to expand while any cascade effect is under a safety
  hold (no further writes after an uncertain partial effect).
- ON order is top-down (parent before required children), OFF order is
  bottom-up (children before parent).
- the owner queue has one controller; UI requests work, only the
  controller publishes effects. Cancellation in ``pending``/``publishing``/
  ``held`` yields ``unknown`` (never ``terminal_failed``); cancellation of
  a never-dispatched ``queued`` request is a safe ``terminal_failed``.
- ``detach`` (confirmed target exit) clears active effects and blocks
  async records until the next attach; ``close_or_target_exit`` drains
  in-flight requests without clearing active effects.
- after an uncertain partial effect a safety hold blocks further writes on
  the affected sub-tree; read paths (snapshot/query) stay responsive.
- value freeze is never an activation wish; failed or uncertain attempts
  are never saved and never replayed on the next attach.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

SCHEMA = 'ct2trainer-activation-policy/v1'

RECORD_ACTION = 'action'
RECORD_NAVIGATION = 'navigation'
RECORD_ASYNC = 'async'
RECORD_VALUE_ONLY = 'value_only'
_RECORD_KINDS = {RECORD_ACTION, RECORD_NAVIGATION, RECORD_ASYNC, RECORD_VALUE_ONLY}

RELATION_REQUIRED = 'required_dependency'
RELATION_DIRECT = 'direct_activation'
RELATION_NAVIGATION = 'navigation'
RELATION_COLLECTIVE_OFF = 'collective_off'
_RELATION_KINDS = {RELATION_REQUIRED, RELATION_DIRECT, RELATION_NAVIGATION,
                   RELATION_COLLECTIVE_OFF}

FLAG_MO_BIND_ACTIVATION = 'moBindActivation'

STATE_QUEUED = 'queued'
STATE_PENDING = 'pending'
STATE_PUBLISHING = 'publishing'
STATE_HELD = 'held'
STATE_SUCCESS = 'terminal_success'
STATE_FAILED = 'terminal_failed'
STATE_UNKNOWN = 'unknown'
_TERMINAL = {STATE_SUCCESS, STATE_FAILED, STATE_UNKNOWN}


class ActivationPolicyError(ValueError):
    pass


class CycleError(ActivationPolicyError):
    pass


class ActivationBlocked(ActivationPolicyError):
    pass


class ActivationTargetRefused(ActivationPolicyError):
    pass


class AsyncBeforeAttachRefused(ActivationPolicyError):
    pass


class OwnershipConflict(ActivationPolicyError):
    pass


class UnknownRecordError(ActivationPolicyError):
    pass


class InvalidTransitionError(ActivationPolicyError):
    pass


class SafetyHoldRefused(ActivationPolicyError):
    pass


class StaleGenerationRefused(ActivationPolicyError):
    pass


class WishSaveRefused(ActivationPolicyError):
    pass


@dataclass(frozen=True)
class RecordSpec:
    record_id: int
    kind: str = RECORD_ACTION
    parent_ids: tuple = ()

    def __post_init__(self):
        if type(self.record_id) is not int or self.record_id <= 0:
            raise ActivationPolicyError('Record IDs are positive integers.')
        if self.kind not in _RECORD_KINDS:
            raise ActivationPolicyError('Unknown record kind: %r' % (self.kind,))
        if type(self.parent_ids) is not tuple:
            raise ActivationPolicyError('parent_ids must be a tuple.')


@dataclass(frozen=True)
class CompensationReceipt:
    """Private compensation receipt for one effect direction (stage 1)."""

    request_id: int
    record_id: int
    direction: str
    confirmed: bool
    generation: int


@dataclass
class _Request:
    request_id: int
    record_id: int
    intent: str
    generation: int
    effects: tuple
    state: str = STATE_QUEUED
    receipt: CompensationReceipt | None = None


class RecordTable:
    """Validated parent/child topology with cycle detection."""

    def __init__(self, records, relations, flags=None) -> None:
        self._records = {}
        for record in records or ():
            if not isinstance(record, RecordSpec):
                raise ActivationPolicyError('Records are RecordSpec instances.')
            if record.record_id in self._records:
                raise ActivationPolicyError('Duplicate record ID: %r' % (record.record_id,))
            self._records[record.record_id] = record
        self._relations = {}
        for parent_id, children in (relations or {}).items():
            if parent_id not in self._records:
                raise UnknownRecordError('Relation parent is unknown: %r' % (parent_id,))
            clean = {}
            for child_id, relation in children.items():
                if child_id not in self._records:
                    raise UnknownRecordError('Relation child is unknown: %r' % (child_id,))
                if child_id == parent_id:
                    raise CycleError('Record refers to itself: %r' % (child_id,))
                if relation not in _RELATION_KINDS:
                    raise ActivationPolicyError('Unknown relation kind: %r' % (relation,))
                if child_id in clean:
                    raise ActivationPolicyError('Duplicate child relation: %r' % (child_id,))
                clean[child_id] = relation
            self._relations[parent_id] = clean
        self._flags = {record_id: set(extra or ())
                       for record_id, extra in (flags or {}).items()}
        for record_id in self._flags:
            if record_id not in self._records:
                raise UnknownRecordError('Flag record is unknown: %r' % (record_id,))
        self._validate_parent_ids()
        self._detect_cycles()

    def __contains__(self, record_id: int) -> bool:
        return record_id in self._records

    def record(self, record_id: int) -> RecordSpec:
        if record_id not in self._records:
            raise UnknownRecordError('Unknown record: %r' % (record_id,))
        return self._records[record_id]

    def flags(self, record_id: int) -> frozenset:
        return frozenset(self._flags.get(record_id, ()))

    def children(self, record_id: int, relation: str | None = None) -> tuple:
        self.record(record_id)
        found = [(child, kind) for child, kind in self._relations.get(record_id, {}).items()
                 if relation is None or kind == relation]
        return tuple(found)

    def ancestors_of(self, record_id: int) -> tuple:
        self.record(record_id)
        seen = []
        stack = list(self._records[record_id].parent_ids)
        while stack:
            parent = stack.pop()
            if parent in seen or parent not in self._records:
                continue
            seen.append(parent)
            stack.extend(self._records[parent].parent_ids)
        return tuple(reversed(seen))

    def sub_tree(self, record_id: int) -> frozenset:
        """All descendants (any relation), cycle-safe by construction."""
        self.record(record_id)
        found = set()
        stack = [record_id]
        while stack:
            node = stack.pop()
            for child in self._relations.get(node, {}):
                if child not in found:
                    found.add(child)
                    stack.append(child)
        return frozenset(found)

    def _validate_parent_ids(self) -> None:
        """parent_ids must mirror the relation map.

        Selection projection walks parent_ids while effect expansion walks
        the parent-to-children relation map; diverging views would let a
        selection pull in ancestors that the cascade never gates, so the
        two must be kept in sync by construction.
        """
        parents = {record_id: set() for record_id in self._records}
        for parent_id, children in self._relations.items():
            for child_id in children:
                parents[child_id].add(parent_id)
        for record_id, record in self._records.items():
            if set(record.parent_ids) != parents[record_id]:
                raise ActivationPolicyError(
                    'parent_ids of record %r do not match the relation map: '
                    'expected %r.' % (record_id, tuple(sorted(parents[record_id]))))

    def _detect_cycles(self) -> None:
        color = {}
        stack_path = []

        def visit(node):
            color[node] = 1
            stack_path.append(node)
            for child in self._relations.get(node, {}):
                state = color.get(child, 0)
                if state == 1:
                    cycle = stack_path[stack_path.index(child):] + [child]
                    raise CycleError('Parent/child cycle: %s' % ' -> '.join(map(str, cycle)))
                if state == 0:
                    visit(child)
            stack_path.pop()
            color[node] = 2

        for node in self._records:
            if color.get(node, 0) == 0:
                visit(node)


def project_selection(table: RecordTable, selected) -> frozenset:
    """Selection projection: selected records pull their ancestors along."""
    projected = set()
    for record_id in selected or ():
        table.record(record_id)
        projected.add(record_id)
        projected.update(table.ancestors_of(record_id))
    return frozenset(projected)


class ActivationController:
    """One owner queue with generation, holds, receipts and save boundary."""

    def __init__(self, table: RecordTable, budget_reserve=None) -> None:
        self.table = table
        self._budget_reserve = budget_reserve
        self._requests: dict[int, _Request] = {}
        self._next_request = itertools.count(1)
        self._generation = 0
        self._holds: set[int] = set()
        self._confirmed_on: set[int] = set()
        self._failed_or_unknown: set[int] = set()
        self._saved_wishes: set[int] = set()
        self._wish: dict[int, bool] = {}
        self._active: dict[int, bool] = {}
        self._completion_log: list[tuple] = []
        self._freeze_receipts: list[tuple] = []
        self._attached = False

    # -- attach lifecycle ----------------------------------------------------

    def attach_confirmed(self) -> None:
        self._attached = True

    def detach(self) -> None:
        """Confirmed target exit: no effect can persist, so all active
        flags clear (saved wishes survive for the next attach)."""
        self._attached = False
        self._active.clear()
        self._drain_inflight(reason='detach')

    def close_or_target_exit(self) -> None:
        self._drain_inflight(reason='close_or_target_exit')

    def _drain_inflight(self, reason: str) -> None:
        for request in self._requests.values():
            if request.state in _TERMINAL:
                continue
            if request.state == STATE_QUEUED:
                # Never dispatched: no effect could have landed.
                request.state = STATE_FAILED
            else:
                request.state = STATE_UNKNOWN
                self._hold_sub_tree(request.record_id)
                self._failed_or_unknown.add(request.record_id)
            self._completion_log.append(
                (request.request_id, request.record_id, 'drained', reason, request.generation))

    # -- planning ------------------------------------------------------------

    def _expand(self, record_id: int, intent: str) -> tuple:
        record = self.table.record(record_id)
        if record.kind not in (RECORD_ACTION, RECORD_ASYNC):
            raise ActivationTargetRefused(
                'Only action/async records are activation targets, not %r.' % (record.kind,))
        if FLAG_MO_BIND_ACTIVATION in self.table.flags(record_id):
            raise ActivationBlocked(
                'moBindActivation has no derived contract; record stays blocked.')
        effects = []
        if intent == 'activate':
            # Top-down: the record first, then required descendants level by
            # level, then direct-activation children whose own wish is set
            # (with their required descendants).
            effects.append(record_id)
            effects.extend(self._required_descendants(record_id))
            for child, _relation in self.table.children(record_id, RELATION_DIRECT):
                if self._wish.get(child, False):
                    effects.append(child)
                    effects.extend(self._required_descendants(child))
        else:
            # Bottom-up: explicitly active children before their parent.
            # Required descendants always follow the parent; direct and
            # collective-off children are only deactivated when explicitly
            # active; navigation children never propagate effects.
            for child in reversed(self._required_descendants(record_id)):
                if self._active.get(child, False):
                    effects.append(child)
            for relation in (RELATION_DIRECT, RELATION_COLLECTIVE_OFF):
                for child, _kind in self.table.children(record_id, relation):
                    if self._active.get(child, False):
                        effects.append(child)
            effects.append(record_id)
        seen = set()
        ordered = []
        for effect in effects:
            if effect not in seen:
                seen.add(effect)
                ordered.append(effect)
        return tuple(ordered)

    def _required_descendants(self, record_id: int) -> list:
        """Required descendants in top-down (parent before child) BFS order."""
        found = []
        frontier = [record_id]
        while frontier:
            next_frontier = []
            for node in frontier:
                for child, _relation in self.table.children(node, RELATION_REQUIRED):
                    if child in found:
                        continue
                    found.append(child)
                    next_frontier.append(child)
            frontier = next_frontier
        return found

    # -- owner queue -----------------------------------------------------------

    def request(self, record_id: int, intent: str = 'activate') -> int:
        if intent not in ('activate', 'deactivate'):
            raise ActivationPolicyError('Intent must be activate or deactivate.')
        effects = self._expand(record_id, intent)
        for effect in effects:
            if self._in_hold(effect):
                raise SafetyHoldRefused(
                    'Effect %r is under a safety hold after an uncertain '
                    'effect; no further writes on that sub-tree.' % (effect,))
            if FLAG_MO_BIND_ACTIVATION in self.table.flags(effect):
                raise ActivationBlocked(
                    'moBindActivation has no derived contract; effect %r '
                    'stays blocked.' % (effect,))
            if self._inflight(effect):
                raise OwnershipConflict(
                    'Record %r already has an in-flight request.' % (effect,))
        record = self.table.record(record_id)
        if record.kind == RECORD_ASYNC and not self._attached:
            raise AsyncBeforeAttachRefused(
                'Async record %r runs only after confirmed attach.' % (record_id,))
        self._generation += 1
        request = _Request(request_id=next(self._next_request), record_id=record_id,
                           intent=intent, generation=self._generation, effects=effects)
        self._requests[request.request_id] = request
        return request.request_id

    def request_generation(self, request_id: int) -> int:
        return self._require_request(request_id).generation

    def effects(self, request_id: int) -> tuple:
        """Ordered effect tuple of a request (read-only).

        The owner queue expands the cascade once at request time; the
        engine executes exactly these effects in this order and reports
        completion against the request generation.
        """
        return self._require_request(request_id).effects

    def dispatch(self, request_id: int) -> None:
        request = self._require_request(request_id)
        self._require_state(request, STATE_QUEUED)
        request.state = STATE_PENDING
        if self._budget_reserve is not None:
            self._budget_reserve(request.record_id, request.generation)

    def publish(self, request_id: int) -> None:
        request = self._require_request(request_id)
        self._require_state(request, STATE_PENDING)
        request.state = STATE_PUBLISHING

    def hold(self, request_id: int) -> None:
        request = self._require_request(request_id)
        self._require_state(request, STATE_PUBLISHING)
        request.state = STATE_HELD

    def confirm_success(self, request_id: int, generation: int) -> CompensationReceipt:
        request = self._require_request(request_id)
        self._require_state(request, STATE_PUBLISHING, STATE_HELD)
        if type(generation) is not int or generation != request.generation:
            raise StaleGenerationRefused(
                'Generation %r does not match the request generation %r.'
                % (generation, request.generation))
        request.state = STATE_SUCCESS
        for effect in request.effects:
            self._active[effect] = request.intent == 'activate'
        if request.intent == 'activate':
            self._confirmed_on.add(request.record_id)
            self._wish[request.record_id] = True
        else:
            # A confirmed OFF clears the wish; it must not be replayed next
            # attach.
            self._wish[request.record_id] = False
            self._saved_wishes.discard(request.record_id)
        receipt = CompensationReceipt(request.request_id, request.record_id,
                                      request.intent, True, request.generation)
        request.receipt = receipt
        return receipt

    def fail_before_effect(self, request_id: int) -> None:
        request = self._require_request(request_id)
        self._require_state(request, STATE_PENDING, STATE_PUBLISHING, STATE_HELD)
        request.state = STATE_FAILED
        self._failed_or_unknown.add(request.record_id)

    def fail_after_effect(self, request_id: int) -> None:
        request = self._require_request(request_id)
        self._require_state(request, STATE_PENDING, STATE_PUBLISHING, STATE_HELD)
        request.state = STATE_UNKNOWN
        self._hold_sub_tree(request.record_id)
        self._failed_or_unknown.add(request.record_id)

    def cancel(self, request_id: int) -> None:
        request = self._require_request(request_id)
        if request.state == STATE_QUEUED:
            request.state = STATE_FAILED
            return
        if request.state in (STATE_PENDING, STATE_PUBLISHING, STATE_HELD):
            request.state = STATE_UNKNOWN
            self._hold_sub_tree(request.record_id)
            self._failed_or_unknown.add(request.record_id)
            return
        raise InvalidTransitionError(
            'Request %r is terminal (%s); it cannot be cancelled.'
            % (request_id, request.state))

    def late_completion(self, request_id: int, receipt: CompensationReceipt) -> None:
        """Late completion never silently reverts a state; it is logged."""
        request = self._require_request(request_id)
        if request.state not in _TERMINAL:
            raise InvalidTransitionError(
                'Late completion requires a terminal request, found %s.' % (request.state,))
        self._completion_log.append(
            (request_id, request.record_id, 'late_completion', request.state,
             request.generation, receipt))

    # -- reads (stay responsive under holds) ----------------------------------

    def snapshot(self) -> dict:
        return {
            'schema': SCHEMA,
            'state': {rid: req.state for rid, req in sorted(self._requests.items())},
            'active': dict(sorted(self._active.items())),
            'holds': sorted(self._holds),
            'saved_wishes': sorted(self._saved_wishes),
            'generation': self._generation,
        }

    def query(self, record_id: int) -> dict:
        self.table.record(record_id)
        return {
            'record_id': record_id,
            'active': self._active.get(record_id, False),
            'hold': self._in_hold(record_id),
            'saved_wish': record_id in self._saved_wishes,
        }

    def mirror_effect(self, record_id: int, active: bool) -> None:
        """Mirror an engine-side effect observation into the active state.

        The engine drives record effects through its ordinary paths (byte
        patches, assembly/Lua programs, global leases) outside controller
        requests; OFF expansion deactivates only explicitly active children,
        so the engine must report every observed live effect it owns.  This
        never publishes an effect - it only records the engine's own
        observation.  Records outside the topology are refused.
        """
        self.table.record(record_id)
        self._active[record_id] = bool(active)

    def mirror_wish(self, record_id: int, wished: bool) -> None:
        """Mirror the persisted wish state of a record.

        The desired set (state.json) is the cross-session wish store; the
        controller's session-scoped wish state must reflect it so that
        direct-activation ON expansion and the save boundary act on the
        true wish of every child, whether it was enabled through the
        cascade or through its own toggle.  This never saves a wish -
        it only mirrors the engine's persisted state.  Records outside
        the topology are refused.
        """
        self.table.record(record_id)
        self._wish[record_id] = bool(wished)

    # -- save/replay boundary --------------------------------------------------

    def save_wish(self, record_id: int) -> None:
        self.table.record(record_id)
        if record_id not in self._confirmed_on:
            raise WishSaveRefused(
                'Wishes are saved only after independently confirmed ON; '
                'record %r has no confirmed ON.' % (record_id,))
        if record_id in self._failed_or_unknown:
            raise WishSaveRefused(
                'Record %r has a failed or uncertain attempt and is never saved.' % (record_id,))
        self._saved_wishes.add(record_id)
        self._wish[record_id] = True

    def replay_saved_wishes(self) -> tuple:
        """Replay only confirmed saved wishes; failed/unknown are never replayed.

        Returns (replayed, skipped) where skipped is a tuple of
        (record_id, reason) pairs. Skip reasons: 'failed-or-unknown'
        (permanent for this controller), 'held' (safety hold on the record or
        on any cascade effect), 'inflight' (overlapping open request),
        'blocked' (moBindActivation inside the cascade) and 'not-attached'
        (async wish before a confirmed attach). A hold never silently
        authorizes a write on that sub-tree, but it does not block healthy,
        unrelated saved wishes.
        """
        replayed = []
        skipped = []
        for record_id in sorted(self._saved_wishes):
            if record_id in self._failed_or_unknown:
                skipped.append((record_id, 'failed-or-unknown'))
                continue
            if self._in_hold(record_id):
                skipped.append((record_id, 'held'))
                continue
            try:
                self.request(record_id, 'activate')
            except OwnershipConflict:
                skipped.append((record_id, 'inflight'))
                continue
            except SafetyHoldRefused:
                skipped.append((record_id, 'held'))
                continue
            except ActivationBlocked:
                skipped.append((record_id, 'blocked'))
                continue
            except AsyncBeforeAttachRefused:
                skipped.append((record_id, 'not-attached'))
                continue
            replayed.append(record_id)
        return tuple(replayed), tuple(skipped)

    # -- value freeze (never an activation wish) -------------------------------

    def freeze_value(self, record_id: int, freeze: bool) -> tuple:
        record = self.table.record(record_id)
        if record.kind not in (RECORD_VALUE_ONLY, RECORD_ACTION):
            raise ActivationTargetRefused(
                'Value freeze applies to value/action records, not %r.' % (record.kind,))
        receipt = (record_id, freeze, len(self._requests))
        self._freeze_receipts.append(receipt)
        return receipt

    @property
    def freeze_receipts(self) -> tuple:
        return tuple(self._freeze_receipts)

    # -- internals --------------------------------------------------------------

    def _require_request(self, request_id: int) -> _Request:
        request = self._requests.get(request_id)
        if request is None:
            raise UnknownRecordError('Unknown request: %r' % (request_id,))
        return request

    @staticmethod
    def _require_state(request: _Request, *states: str) -> None:
        if request.state not in states:
            raise InvalidTransitionError(
                'Request %r is %s; transition requires %s.'
                % (request.request_id, request.state, ' / '.join(states)))

    def _hold_sub_tree(self, record_id: int) -> None:
        self._holds.add(record_id)
        self._holds.update(self.table.sub_tree(record_id))

    def _in_hold(self, record_id: int) -> bool:
        return record_id in self._holds

    def _inflight(self, record_id: int) -> bool:
        return any(req.record_id == record_id or record_id in req.effects
                   for req in self._requests.values() if req.state not in _TERMINAL)
