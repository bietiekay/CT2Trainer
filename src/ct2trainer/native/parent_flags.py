"""Parent/child flag model for the four CT relation classes (AP-07 stage 2).

This module provides a declarative, validated layer on top of the
``activation_policy`` stage-1 primitives.  It defines the four parent-child
flag classes as first-class objects, validates topologies for cycles and
consistency, and adds consumer-ownership tracking for cascade effects.

The four flag classes
---------------------

- ``required_dependency``: ON and OFF follow the parent unconditionally.
- ``direct_activation``: the child keeps its own wish; the parent ON
  activates it only when the child wish is set.
- ``navigation``: structural grouping; no effect propagation.
- ``collective_off``: parent OFF deactivates only explicitly active
  children; hidden/inactive children are untouched.

Topology validation and cycle detection are delegated to the existing
:class:`~ct2trainer.native.activation_policy.RecordTable`; this module
does not re-implement the policy state machine.
"""
from __future__ import annotations

from dataclasses import dataclass

from ct2trainer.native.activation_policy import (
    ActivationPolicyError,
    RecordSpec,
    RecordTable,
    RELATION_COLLECTIVE_OFF,
    RELATION_DIRECT,
    RELATION_NAVIGATION,
    RELATION_REQUIRED,
    project_selection,
)

# ---------------------------------------------------------------------------
# Flag-class constants (aliases of the stage-1 relation kinds)
# ---------------------------------------------------------------------------

FLAG_REQUIRED_DEPENDENCY = RELATION_REQUIRED
FLAG_DIRECT_ACTIVATION = RELATION_DIRECT
FLAG_NAVIGATION = RELATION_NAVIGATION
FLAG_COLLECTIVE_OFF = RELATION_COLLECTIVE_OFF

ALL_FLAG_CLASSES = frozenset({
    FLAG_REQUIRED_DEPENDENCY,
    FLAG_DIRECT_ACTIVATION,
    FLAG_NAVIGATION,
    FLAG_COLLECTIVE_OFF,
})

# Semantic properties per flag class (pure model data, no behavior).
_FLAG_PROPERTIES: dict[str, dict] = {
    FLAG_REQUIRED_DEPENDENCY: {
        'on_follows_parent': True,
        'off_follows_parent': True,
        'own_wish': False,
        'effect_propagation': True,
    },
    FLAG_DIRECT_ACTIVATION: {
        'on_follows_parent': False,
        'off_follows_parent': False,
        'own_wish': True,
        'effect_propagation': True,
    },
    FLAG_NAVIGATION: {
        'on_follows_parent': False,
        'off_follows_parent': False,
        'own_wish': False,
        'effect_propagation': False,
    },
    FLAG_COLLECTIVE_OFF: {
        'on_follows_parent': False,
        'off_follows_parent': True,  # only when the child is explicitly active
        'own_wish': False,
        'effect_propagation': True,
    },
}


class ParentFlagError(ActivationPolicyError):
    """Raised for invalid parent-flag declarations."""


class ConsumerOwnershipConflict(ParentFlagError):
    """Raised when two consumers try to claim the same effect."""


# ---------------------------------------------------------------------------
# Declarative binding
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ParentFlagBinding:
    """A single parent-to-child flag assignment.

    Attributes:
        parent_id: The parent record ID (positive int).
        child_id: The child record ID (positive int, != parent_id).
        flag_class: One of the four flag-class constants.
    """
    parent_id: int
    child_id: int
    flag_class: str

    def __post_init__(self) -> None:
        if type(self.parent_id) is not int or self.parent_id <= 0:
            raise ParentFlagError('parent_id must be a positive int.')
        if type(self.child_id) is not int or self.child_id <= 0:
            raise ParentFlagError('child_id must be a positive int.')
        if self.parent_id == self.child_id:
            raise ParentFlagError(
                'Parent and child must differ (%r).' % (self.parent_id,))
        if self.flag_class not in ALL_FLAG_CLASSES:
            raise ParentFlagError('Unknown flag class: %r' % (self.flag_class,))


# ---------------------------------------------------------------------------
# Topology
# ---------------------------------------------------------------------------

class ParentFlagTopology:
    """Validated collection of parent-child flag bindings.

    Acts as a declarative layer: declare record kinds and flag bindings, and
    the topology validates them, derives the consistent parent_ids, and
    exposes a :class:`RecordTable` for the activation-policy engine.

    The bindings are the single source of truth for the parent-child
    structure.  If a supplied :class:`RecordSpec` carries explicit
    ``parent_ids`` that conflict with the bindings, construction fails
    (visible, never silently normalized).

    ``flags`` (optional) passes per-record extra flags (e.g.
    moBindActivation) through to the underlying :class:`RecordTable`; the
    stage-1 policy keeps handling those record-level flags itself.

    Validation performed at construction:
    - record IDs are positive, unique, known kinds.
    - every binding references known records; no duplicate (parent, child)
      pair; no self-referencing binding.
    - no cycles (delegated to RecordTable, which also re-checks the
      derived parent_ids against the relation map).
    """

    def __init__(self, records, bindings, flags=None) -> None:
        self._source_records: dict[int, RecordSpec] = {}
        for record in records or ():
            if not isinstance(record, RecordSpec):
                raise ParentFlagError('Records must be RecordSpec instances.')
            if record.record_id in self._source_records:
                raise ParentFlagError(
                    'Duplicate record ID: %r' % (record.record_id,))
            self._source_records[record.record_id] = record

        self._bindings: list[ParentFlagBinding] = []
        self._relation_map: dict[int, dict[int, str]] = {
            rid: {} for rid in self._source_records
        }
        seen_pairs: set[tuple[int, int]] = set()
        for binding in bindings or ():
            if not isinstance(binding, ParentFlagBinding):
                raise ParentFlagError(
                    'Bindings must be ParentFlagBinding instances.')
            if binding.parent_id not in self._source_records:
                raise ParentFlagError(
                    'Unknown parent record in binding: %r' % (binding.parent_id,))
            if binding.child_id not in self._source_records:
                raise ParentFlagError(
                    'Unknown child record in binding: %r' % (binding.child_id,))
            pair = (binding.parent_id, binding.child_id)
            if pair in seen_pairs:
                raise ParentFlagError(
                    'Duplicate binding: parent=%r child=%r' % pair)
            seen_pairs.add(pair)
            self._relation_map[binding.parent_id][binding.child_id] = (
                binding.flag_class)
            self._bindings.append(binding)

        # Derive parent_ids from the bindings (authoritative view).
        derived_parents: dict[int, tuple] = {
            rid: () for rid in self._source_records
        }
        for binding in self._bindings:
            current = derived_parents[binding.child_id]
            if binding.parent_id not in current:
                derived_parents[binding.child_id] = current + (binding.parent_id,)
        rebuilt: dict[int, RecordSpec] = {}
        for rid, record in self._source_records.items():
            if record.parent_ids and tuple(record.parent_ids) != derived_parents[rid]:
                raise ParentFlagError(
                    'Record %r declares parent_ids %r that conflict with the '
                    'bindings %r.' % (rid, record.parent_ids,
                                      derived_parents[rid]))
            rebuilt[rid] = RecordSpec(rid, record.kind, derived_parents[rid])
        self._records = rebuilt
        self._table = RecordTable(
            list(rebuilt.values()),
            {parent: dict(children)
             for parent, children in self._relation_map.items() if children},
            flags=flags,
        )

    # -- accessors -----------------------------------------------------------

    @property
    def table(self) -> RecordTable:
        """The underlying validated RecordTable."""
        return self._table

    @property
    def records(self) -> dict:
        return dict(self._records)

    @property
    def bindings(self) -> tuple:
        return tuple(self._bindings)

    def flag_class(self, parent_id: int, child_id: int) -> str:
        """Return the flag class for a parent-child pair.

        Raises ParentFlagError if the pair is not a declared binding.
        """
        children = self._relation_map.get(parent_id, {})
        if child_id not in children:
            raise ParentFlagError(
                'No binding from parent %r to child %r.'
                % (parent_id, child_id))
        return children[child_id]

    def children_of(self, parent_id: int,
                    flag_class: str | None = None) -> tuple:
        """Children of a parent, optionally filtered by flag class.

        Returns a tuple of (child_id, flag_class) pairs.
        """
        self.table.record(parent_id)
        children = self._relation_map.get(parent_id, {})
        if flag_class is not None:
            return tuple((cid, fc) for cid, fc in children.items()
                         if fc == flag_class)
        return tuple(children.items())

    def parents_of(self, child_id: int) -> tuple:
        """All (parent_id, flag_class) pairs for a child, sorted by parent."""
        self.table.record(child_id)
        result = []
        for parent_id, children in self._relation_map.items():
            if child_id in children:
                result.append((parent_id, children[child_id]))
        return tuple(sorted(result))

    # -- flag-class semantics ------------------------------------------------

    @staticmethod
    def flag_properties(flag_class: str) -> dict:
        """Return the semantic property dict for a flag class.

        Raises ParentFlagError for unknown classes.
        """
        if flag_class not in _FLAG_PROPERTIES:
            raise ParentFlagError('Unknown flag class: %r' % (flag_class,))
        return dict(_FLAG_PROPERTIES[flag_class])

    def propagation_children(self, record_id: int) -> frozenset:
        """Descendants reachable via effect-propagating flag classes only.

        Navigation children are excluded (no effect propagation).
        """
        self.table.record(record_id)
        found: set[int] = set()
        stack = [record_id]
        while stack:
            node = stack.pop()
            for child_id, fc in self._relation_map.get(node, {}).items():
                if fc == FLAG_NAVIGATION:
                    continue
                if child_id not in found:
                    found.add(child_id)
                    stack.append(child_id)
        return frozenset(found)

    # -- selection -----------------------------------------------------------

    def selection_closure(self, selected) -> frozenset:
        """Selection projection: selected records pull their ancestors along
        (including navigation ancestors, which are structural)."""
        return project_selection(self._table, selected)

    # -- cycle / recursion helpers -------------------------------------------

    def is_ancestor(self, ancestor_id: int, descendant_id: int) -> bool:
        """True if ancestor_id is a proper ancestor of descendant_id."""
        self.table.record(ancestor_id)
        self.table.record(descendant_id)
        return ancestor_id in self.table.ancestors_of(descendant_id)

    def depth(self, record_id: int) -> int:
        """Depth of a record in the tree (roots have depth 0)."""
        return len(self.table.ancestors_of(record_id))


# ---------------------------------------------------------------------------
# Consumer ownership
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ConsumerOwner:
    """Identifies which consumer request owns a set of cascade effects.

    Attributes:
        consumer_id: Opaque consumer identifier (e.g. a UI session).
        request_id: The controller request that produced the cascade.
        root_record_id: The record the consumer directly requested.
        generation: The controller generation at claim time.
        owned_effects: All record IDs in the cascade (including root).
    """
    consumer_id: str
    request_id: int
    root_record_id: int
    generation: int
    owned_effects: tuple


class ConsumerOwnershipTracker:
    """Tracks which consumer logically owns each active cascade effect.

    When a consumer toggles a parent, that consumer owns the parent's
    activated children as well.  A second consumer cannot claim an effect
    already owned by a different consumer's live cascade.  Ownership is
    claimed for confirmed cascades and released when the cascade is
    deactivated or the controller drains.
    """

    def __init__(self) -> None:
        self._effect_owners: dict[int, ConsumerOwner] = {}
        self._request_owners: dict[int, ConsumerOwner] = {}

    def claim(self, consumer_id: str, request_id: int,
              root_record_id: int, generation: int,
              effects: tuple) -> ConsumerOwner:
        """Claim ownership of all effects for a confirmed cascade.

        Raises ConsumerOwnershipConflict if any effect is already owned by a
        different consumer.  Re-claiming by the same consumer is allowed.
        """
        for effect_id in effects:
            existing = self._effect_owners.get(effect_id)
            if existing is not None and existing.consumer_id != consumer_id:
                raise ConsumerOwnershipConflict(
                    'Effect %r is owned by consumer %r (request %r); '
                    'cannot claim it for consumer %r (request %r).'
                    % (effect_id, existing.consumer_id, existing.request_id,
                       consumer_id, request_id))
        owner = ConsumerOwner(
            consumer_id=consumer_id,
            request_id=request_id,
            root_record_id=root_record_id,
            generation=generation,
            owned_effects=tuple(effects),
        )
        for effect_id in effects:
            self._effect_owners[effect_id] = owner
        self._request_owners[request_id] = owner
        return owner

    def release(self, request_id: int) -> None:
        """Release all effects owned by the given request (no-op if none)."""
        owner = self._request_owners.pop(request_id, None)
        if owner is None:
            return
        for effect_id in owner.owned_effects:
            current = self._effect_owners.get(effect_id)
            if current is not None and current.request_id == request_id:
                del self._effect_owners[effect_id]

    def owner_of(self, record_id: int) -> ConsumerOwner | None:
        """Return the consumer owner of a record's active effect, or None."""
        return self._effect_owners.get(record_id)

    def is_owned_by(self, record_id: int, consumer_id: str) -> bool:
        """True if the record's active effect is owned by the consumer."""
        owner = self._effect_owners.get(record_id)
        return owner is not None and owner.consumer_id == consumer_id

    def owned_records(self, consumer_id: str) -> tuple:
        """All record IDs currently owned by the given consumer (sorted)."""
        return tuple(
            sorted(rid for rid, owner in self._effect_owners.items()
                   if owner.consumer_id == consumer_id))

    def all_owners(self) -> tuple:
        """All active owners, sorted by request_id."""
        return tuple(
            sorted(self._request_owners.values(),
                   key=lambda owner: owner.request_id))

    def clear(self) -> None:
        """Drop all ownership state (e.g. on confirmed detach)."""
        self._effect_owners.clear()
        self._request_owners.clear()
