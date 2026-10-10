"""Focused fixture-driven tests for the AP-07 activation policy lane.

Drives ``activation_policy.py`` (stage 1, unmodified) against the
synthetic fixture trees in ``activation_fixture_data.py`` and the
declarative flag model in ``parent_flags.py`` (stage 2).  Pinned
scenarios: per-flag-class ON/OFF ordering, cycle refusal, consumer
ownership, moBindActivation blocking, fail-before/fail-after effect,
cancel during held publish, close/target-exit drain, late completion,
and the save/replay wish boundary.  No engine, Lua, C fixture, or real
target is involved.
"""
import unittest

from ct2trainer.native import activation_policy as ap
from ct2trainer.native.activation_policy import (
    ActivationBlocked,
    ActivationController,
    ActivationTargetRefused,
    AsyncBeforeAttachRefused,
    CompensationReceipt,
    CycleError,
    FLAG_MO_BIND_ACTIVATION,
    InvalidTransitionError,
    OwnershipConflict,
    RecordSpec,
    RecordTable,
    SafetyHoldRefused,
    UnknownRecordError,
    WishSaveRefused,
)
from ct2trainer.native.parent_flags import (
    ALL_FLAG_CLASSES,
    ConsumerOwnershipConflict,
    ConsumerOwnershipTracker,
    ConsumerOwner,
    FLAG_COLLECTIVE_OFF,
    FLAG_DIRECT_ACTIVATION,
    FLAG_NAVIGATION,
    FLAG_REQUIRED_DEPENDENCY,
    ParentFlagBinding,
    ParentFlagError,
    ParentFlagTopology,
)

try:
    from activation_fixture_data import (
        BackendOutcome,
        ScriptedBackendDouble,
        drive_request,
        full_flag_topology,
        full_flag_table,
        mobind_topology,
        ownership_topology,
        fresh_full_controller,
        CYCLE_RECORDS,
        CYCLE_BINDINGS,
        SELF_LOOP_RECORDS,
        SELF_LOOP_RELATIONS,
    )
except ModuleNotFoundError:  # invoked as tests.test_native_activation_fixture
    from tests.activation_fixture_data import (
        BackendOutcome,
        ScriptedBackendDouble,
        drive_request,
        full_flag_topology,
        full_flag_table,
        mobind_topology,
        ownership_topology,
        fresh_full_controller,
        CYCLE_RECORDS,
        CYCLE_BINDINGS,
        SELF_LOOP_RECORDS,
        SELF_LOOP_RELATIONS,
    )


def effects_of(ctrl, record_id, intent='activate'):
    """Planned effect order for one request (stage-1 expansion)."""
    return ctrl._expand(record_id, intent)


def complete(ctrl, record_id, intent='activate'):
    """Request -> dispatch -> publish -> confirm; return the request id."""
    rid = ctrl.request(record_id, intent)
    gen = ctrl.request_generation(rid)
    ctrl.dispatch(rid)
    ctrl.publish(rid)
    ctrl.confirm_success(rid, gen)
    return rid


def complete_via(ctrl, backend, record_id, intent='activate'):
    """Same lifecycle through the scripted double (EFFECT_OK)."""
    result = drive_request(ctrl, backend, record_id, intent)
    return result.request_id, result.receipt


class TestFixtureTopology(unittest.TestCase):
    def test_full_topology_builds_with_all_flag_classes(self):
        topo = full_flag_topology()
        classes = {binding.flag_class for binding in topo.bindings}
        self.assertEqual(classes, ALL_FLAG_CLASSES)
        self.assertIsInstance(topo.table, RecordTable)
        self.assertEqual(len(topo.bindings), 11)

    def test_derived_parent_ids_match_bindings(self):
        table = full_flag_table()
        self.assertEqual(table.record(2).parent_ids, (1,))
        self.assertEqual(table.record(6).parent_ids, (5,))
        self.assertEqual(table.record(11).parent_ids, (10,))
        self.assertEqual(table.record(1).parent_ids, ())
        self.assertEqual(table.record(20).parent_ids, ())

    def test_binding_lookup_and_children_of(self):
        topo = full_flag_topology()
        self.assertEqual(topo.flag_class(1, 5), FLAG_DIRECT_ACTIVATION)
        self.assertEqual(topo.flag_class(10, 12), FLAG_COLLECTIVE_OFF)
        self.assertEqual(dict(topo.children_of(1)),
                         {2: FLAG_REQUIRED_DEPENDENCY,
                          5: FLAG_DIRECT_ACTIVATION,
                          7: FLAG_NAVIGATION,
                          10: FLAG_COLLECTIVE_OFF})
        self.assertEqual(topo.children_of(1, FLAG_NAVIGATION),
                         ((7, FLAG_NAVIGATION),))
        self.assertEqual(topo.children_of(1, FLAG_DIRECT_ACTIVATION),
                         ((5, FLAG_DIRECT_ACTIVATION),))
        with self.assertRaises(ParentFlagError):
            topo.flag_class(1, 3)

    def test_parents_of(self):
        topo = full_flag_topology()
        self.assertEqual(topo.parents_of(6), ((5, FLAG_REQUIRED_DEPENDENCY),))
        self.assertEqual(topo.parents_of(2), ((1, FLAG_REQUIRED_DEPENDENCY),))
        self.assertEqual(topo.parents_of(1), ())

    def test_flag_properties_per_class(self):
        props = {flag: ParentFlagTopology.flag_properties(flag)
                 for flag in sorted(ALL_FLAG_CLASSES)}
        self.assertEqual(props[FLAG_REQUIRED_DEPENDENCY],
                         {'on_follows_parent': True, 'off_follows_parent': True,
                          'own_wish': False, 'effect_propagation': True})
        self.assertEqual(props[FLAG_DIRECT_ACTIVATION],
                         {'on_follows_parent': False, 'off_follows_parent': False,
                          'own_wish': True, 'effect_propagation': True})
        self.assertEqual(props[FLAG_NAVIGATION],
                         {'on_follows_parent': False, 'off_follows_parent': False,
                          'own_wish': False, 'effect_propagation': False})
        self.assertEqual(props[FLAG_COLLECTIVE_OFF],
                         {'on_follows_parent': False, 'off_follows_parent': True,
                          'own_wish': False, 'effect_propagation': True})

    def test_flag_properties_unknown_rejected(self):
        with self.assertRaises(ParentFlagError):
            ParentFlagTopology.flag_properties('bogus')

    def test_propagation_children_excludes_navigation(self):
        topo = full_flag_topology()
        self.assertEqual(topo.propagation_children(1),
                         frozenset({2, 3, 4, 5, 6, 10, 11, 12}))
        self.assertEqual(topo.propagation_children(7), frozenset())
        self.assertEqual(topo.propagation_children(10), frozenset({11, 12}))

    def test_depth_and_is_ancestor(self):
        topo = full_flag_topology()
        self.assertEqual(topo.depth(1), 0)
        self.assertEqual(topo.depth(6), 2)
        self.assertEqual(topo.depth(8), 2)
        self.assertTrue(topo.is_ancestor(1, 6))
        self.assertTrue(topo.is_ancestor(7, 8))
        self.assertFalse(topo.is_ancestor(6, 1))
        self.assertTrue(topo.is_ancestor(10, 11))

    def test_selection_closure_pulls_ancestors(self):
        topo = full_flag_topology()
        self.assertEqual(topo.selection_closure((6,)), frozenset({1, 5, 6}))
        self.assertEqual(topo.selection_closure((8,)), frozenset({1, 7, 8}))
        self.assertEqual(topo.selection_closure((11, 20)), frozenset({1, 10, 11, 20}))
        self.assertEqual(topo.selection_closure(()), frozenset())
        with self.assertRaises(UnknownRecordError):
            topo.selection_closure((99,))

    def test_flags_passthrough_to_policy_table(self):
        topo = mobind_topology()
        self.assertIn(FLAG_MO_BIND_ACTIVATION, topo.table.flags(30))
        self.assertIn(FLAG_MO_BIND_ACTIVATION, topo.table.flags(32))
        self.assertEqual(topo.table.flags(31), frozenset())
        self.assertEqual(topo.table.flags(33), frozenset())

    def test_ownership_topology_builds(self):
        topo = ownership_topology()
        self.assertEqual(dict(topo.children_of(50)),
                         {51: FLAG_REQUIRED_DEPENDENCY,
                          52: FLAG_DIRECT_ACTIVATION})
        self.assertIn(53, topo.table)


class TestTopologyValidation(unittest.TestCase):
    def test_duplicate_binding_rejected(self):
        topo = full_flag_topology()
        with self.assertRaisesRegex(ParentFlagError, 'Duplicate binding'):
            ParentFlagTopology(list(topo.records.values()),
                               list(topo.bindings) + [topo.bindings[0]])

    def test_unknown_record_in_binding_rejected(self):
        with self.assertRaisesRegex(ParentFlagError, 'Unknown child record'):
            ParentFlagTopology(
                [RecordSpec(1)], [ParentFlagBinding(1, 99, FLAG_REQUIRED_DEPENDENCY)])

    def test_parent_ids_conflict_with_bindings_rejected(self):
        with self.assertRaisesRegex(ParentFlagError, 'conflict'):
            ParentFlagTopology(
                [RecordSpec(1), RecordSpec(2, 'action', (99,))],
                [ParentFlagBinding(1, 2, FLAG_REQUIRED_DEPENDENCY)])

    def test_unknown_flag_class_rejected(self):
        with self.assertRaisesRegex(ParentFlagError, 'Unknown flag class'):
            ParentFlagBinding(1, 2, 'bogus')

    def test_self_parent_binding_rejected(self):
        with self.assertRaisesRegex(ParentFlagError, 'must differ'):
            ParentFlagBinding(50, 50, FLAG_REQUIRED_DEPENDENCY)

    def test_duplicate_record_rejected(self):
        with self.assertRaisesRegex(ParentFlagError, 'Duplicate record ID'):
            ParentFlagTopology([RecordSpec(1), RecordSpec(1)], [])

    def test_cycle_topology_rejected(self):
        with self.assertRaisesRegex(CycleError, 'cycle'):
            ParentFlagTopology(CYCLE_RECORDS, CYCLE_BINDINGS)

    def test_self_loop_policy_table_rejected(self):
        with self.assertRaisesRegex(CycleError, 'itself'):
            RecordTable(SELF_LOOP_RECORDS, SELF_LOOP_RELATIONS)

    def test_cycle_error_names_path(self):
        try:
            ParentFlagTopology(CYCLE_RECORDS, CYCLE_BINDINGS)
        except CycleError as error:
            self.assertIn('40', str(error))
            self.assertIn('->', str(error))
        else:
            self.fail('CycleError not raised')


class TestOrderingRequired(unittest.TestCase):
    def test_required_on_is_top_down(self):
        ctrl, _backend = fresh_full_controller()
        # Root first, then required descendants parent before child.
        self.assertEqual(effects_of(ctrl, 1, 'activate'), (1, 2, 3, 4))
        self.assertEqual(effects_of(ctrl, 5, 'activate'), (5, 6))

    def test_required_off_is_bottom_up(self):
        ctrl, _backend = fresh_full_controller()
        complete(ctrl, 1)
        self.assertEqual(effects_of(ctrl, 1, 'deactivate'), (4, 3, 2, 1))

    def test_required_child_off_before_parent(self):
        ctrl, _backend = fresh_full_controller()
        complete(ctrl, 5)  # activates 5 and required child 6
        self.assertEqual(effects_of(ctrl, 5, 'deactivate'), (6, 5))
        rid = ctrl.request(5, 'deactivate')
        gen = ctrl.request_generation(rid)
        ctrl.dispatch(rid)
        ctrl.publish(rid)
        ctrl.confirm_success(rid, gen)
        self.assertFalse(ctrl.query(5)['active'])
        self.assertFalse(ctrl.query(6)['active'])


class TestOrderingDirect(unittest.TestCase):
    def test_direct_on_includes_wished_child_with_required_descendants(self):
        ctrl, _backend = fresh_full_controller()
        complete(ctrl, 5)  # sets the child wish
        self.assertEqual(effects_of(ctrl, 1, 'activate'), (1, 2, 3, 4, 5, 6))

    def test_direct_on_excludes_unwished_child(self):
        ctrl, _backend = fresh_full_controller()
        self.assertEqual(effects_of(ctrl, 1, 'activate'), (1, 2, 3, 4))

    def test_direct_off_child_only_when_explicitly_active(self):
        ctrl, _backend = fresh_full_controller()
        complete(ctrl, 1)
        self.assertEqual(effects_of(ctrl, 1, 'deactivate'), (4, 3, 2, 1))
        complete(ctrl, 5)  # now 5 (and required 6) are explicitly active
        self.assertEqual(effects_of(ctrl, 1, 'deactivate'), (4, 3, 2, 5, 1))


class TestOrderingNavigation(unittest.TestCase):
    def test_navigation_record_is_not_an_activation_target(self):
        ctrl, _backend = fresh_full_controller()
        with self.assertRaisesRegex(ActivationTargetRefused, 'not'):
            ctrl.request(7, 'activate')

    def test_navigation_never_in_parent_cascade(self):
        ctrl, _backend = fresh_full_controller()
        self.assertNotIn(7, effects_of(ctrl, 1, 'activate'))
        complete(ctrl, 8)
        complete(ctrl, 9)
        self.assertNotIn(7, effects_of(ctrl, 1, 'deactivate'))
        self.assertNotIn(8, effects_of(ctrl, 1, 'deactivate'))
        self.assertNotIn(9, effects_of(ctrl, 1, 'deactivate'))

    def test_navigation_off_untouches_active_children(self):
        ctrl, _backend = fresh_full_controller()
        complete(ctrl, 1)
        complete(ctrl, 8)
        complete(ctrl, 9)
        # 8 and 9 are active under navigation parent 7; the root OFF plan
        # must not touch navigation records, and 7 itself can never be
        # toggled (it is not an activation target).
        rid = ctrl.request(1, 'deactivate')
        gen = ctrl.request_generation(rid)
        ctrl.dispatch(rid)
        ctrl.publish(rid)
        ctrl.confirm_success(rid, gen)
        self.assertFalse(ctrl.query(1)['active'])
        self.assertTrue(ctrl.query(8)['active'])
        self.assertTrue(ctrl.query(9)['active'])


class TestOrderingCollectiveOff(unittest.TestCase):
    def test_collective_off_on_propagates_nothing(self):
        ctrl, _backend = fresh_full_controller()
        self.assertEqual(effects_of(ctrl, 10, 'activate'), (10,))

    def test_collective_off_deactivates_only_explicitly_active_children(self):
        ctrl, _backend = fresh_full_controller()
        complete(ctrl, 10)
        complete(ctrl, 11)  # 12 stays inactive ("hidden")
        self.assertEqual(effects_of(ctrl, 10, 'deactivate'), (11, 10))
        rid = ctrl.request(10, 'deactivate')
        gen = ctrl.request_generation(rid)
        ctrl.dispatch(rid)
        ctrl.publish(rid)
        ctrl.confirm_success(rid, gen)
        self.assertFalse(ctrl.query(11)['active'])
        self.assertFalse(ctrl.query(10)['active'])
        self.assertFalse(ctrl.query(12)['active'])

    def test_collective_off_child_wish_does_not_propagate_on(self):
        ctrl, _backend = fresh_full_controller()
        complete(ctrl, 11)      # sets wish[11] and active[11]
        complete(ctrl, 11, 'deactivate')  # clears wish[11], active stays off
        self.assertEqual(effects_of(ctrl, 10, 'activate'), (10,))
        self.assertFalse(ctrl.query(11)['active'])

    def test_root_off_places_collective_child_before_root(self):
        ctrl, _backend = fresh_full_controller()
        complete(ctrl, 1)
        complete(ctrl, 10)
        self.assertEqual(effects_of(ctrl, 1, 'deactivate'), (4, 3, 2, 10, 1))


class TestRootOffExpansionBoundary(unittest.TestCase):
    """Stage-1 expansion boundary: a parent OFF does not walk the required
    sub-tree of a direct child nor the collective sub-tree of a collective
    child.  Pinned here; the exact product contract for deeper walks is a
    separately evidenced decision (plan AP-07)."""

    def _fully_active(self, ctrl):
        complete(ctrl, 1)
        complete(ctrl, 5)
        complete(ctrl, 10)
        complete(ctrl, 11)
        complete(ctrl, 12)

    def test_root_off_does_not_deactivate_direct_child_subtree(self):
        ctrl, _backend = fresh_full_controller()
        self._fully_active(ctrl)
        rid = ctrl.request(1, 'deactivate')
        gen = ctrl.request_generation(rid)
        ctrl.dispatch(rid)
        ctrl.publish(rid)
        ctrl.confirm_success(rid, gen)
        self.assertFalse(ctrl.query(5)['active'])
        self.assertTrue(ctrl.query(6)['active'])  # untouched: not in plan

    def test_root_off_does_not_deactivate_collective_grandchildren(self):
        ctrl, _backend = fresh_full_controller()
        self._fully_active(ctrl)
        rid = ctrl.request(1, 'deactivate')
        gen = ctrl.request_generation(rid)
        ctrl.dispatch(rid)
        ctrl.publish(rid)
        ctrl.confirm_success(rid, gen)
        self.assertFalse(ctrl.query(10)['active'])
        self.assertTrue(ctrl.query(11)['active'])  # untouched: not in plan
        self.assertTrue(ctrl.query(12)['active'])  # untouched: not in plan


def make_mobind_controller():
    ctrl = ActivationController(mobind_topology().table)
    ctrl.attach_confirmed()
    return ctrl


class TestMoBindBlocked(unittest.TestCase):
    def test_mo_bind_target_stays_blocked(self):
        ctrl = make_mobind_controller()
        with self.assertRaisesRegex(ActivationBlocked, 'moBindActivation'):
            ctrl.request(30, 'activate')
        self.assertEqual(ctrl.snapshot()['state'], {})

    def test_mo_bind_inside_required_cascade_blocks_parent(self):
        ctrl = make_mobind_controller()
        with self.assertRaisesRegex(ActivationBlocked, 'moBindActivation'):
            ctrl.request(31, 'activate')
        self.assertEqual(ctrl.snapshot()['state'], {})

    def test_mo_bind_outside_cascade_does_not_block(self):
        ctrl = make_mobind_controller()
        rid = ctrl.request(33, 'activate')
        self.assertEqual(ctrl.snapshot()['state'][rid], ap.STATE_QUEUED)

    def test_mo_bind_block_persists_across_generations(self):
        ctrl = make_mobind_controller()
        complete(ctrl, 33)  # advances the generation
        self.assertEqual(ctrl.snapshot()['generation'], 1)
        with self.assertRaises(ActivationBlocked):
            ctrl.request(30, 'activate')
        with self.assertRaises(ActivationBlocked):
            ctrl.request(31, 'activate')
        # Refusals do not consume a generation.
        self.assertEqual(ctrl.snapshot()['generation'], 1)

    def test_mo_bind_off_cascade_excludes_inactive_blocked_child(self):
        # 32 can never be activated (its own requests are blocked), so the
        # OFF plan for 31 contains only 31 and is not blocked; the blocked
        # child is never touched.
        ctrl = make_mobind_controller()
        self.assertEqual(effects_of(ctrl, 31, 'deactivate'), (31,))
        rid = ctrl.request(31, 'deactivate')
        self.assertEqual(ctrl.snapshot()['state'][rid], ap.STATE_QUEUED)
        self.assertFalse(ctrl.query(32)['active'])


class TestFailBeforeEffect(unittest.TestCase):
    def test_fail_before_terminal_failed_without_hold(self):
        ctrl, backend = fresh_full_controller()
        backend.script = (BackendOutcome.FAIL_BEFORE_EFFECT,)
        result = drive_request(ctrl, backend, 10, 'activate')
        self.assertEqual(result.outcome, BackendOutcome.FAIL_BEFORE_EFFECT)
        self.assertIsNone(result.receipt)
        snap = ctrl.snapshot()
        self.assertEqual(snap['state'][result.request_id], ap.STATE_FAILED)
        self.assertEqual(snap['holds'], [])
        self.assertEqual(backend.invocations,
                         [(10, 'activate', BackendOutcome.FAIL_BEFORE_EFFECT)])

    def test_fail_before_leaves_no_active_no_wish(self):
        ctrl, backend = fresh_full_controller()
        backend.script = (BackendOutcome.FAIL_BEFORE_EFFECT,)
        drive_request(ctrl, backend, 1)
        self.assertEqual(ctrl.snapshot()['active'], {})
        self.assertEqual(ctrl.snapshot()['saved_wishes'], [])
        self.assertFalse(ctrl.query(1)['active'])
        self.assertFalse(ctrl.query(2)['active'])

    def test_fail_before_save_refused(self):
        ctrl, backend = fresh_full_controller()
        backend.script = (BackendOutcome.FAIL_BEFORE_EFFECT,)
        drive_request(ctrl, backend, 10)
        with self.assertRaises(WishSaveRefused):
            ctrl.save_wish(10)

    def test_fail_before_no_compensation_and_retry_allowed(self):
        ctrl, backend = fresh_full_controller()
        backend.script = (BackendOutcome.FAIL_BEFORE_EFFECT,)
        drive_request(ctrl, backend, 10)
        # Exactly one publish hit the target; no compensation write followed.
        self.assertEqual(len(backend.invocations), 1)
        # No hold: the sub-tree stays writable, retry is a fresh request.
        self.assertNotIn(10, ctrl.snapshot()['holds'])
        retry = ctrl.request(10, 'activate')
        self.assertNotEqual(retry, 1)

    def test_fail_before_root_does_not_hold_subtree(self):
        ctrl, backend = fresh_full_controller()
        backend.script = (BackendOutcome.FAIL_BEFORE_EFFECT,)
        drive_request(ctrl, backend, 1)
        self.assertEqual(ctrl.snapshot()['holds'], [])
        # Contrast to fail_after_effect: the sub-tree stays writable.
        self.assertIsNotNone(ctrl.request(2))
        with self.assertRaises(WishSaveRefused):
            ctrl.save_wish(1)


class TestFailAfterEffect(unittest.TestCase):
    def test_fail_after_unknown_with_exact_subtree_holds(self):
        ctrl, backend = fresh_full_controller()
        backend.script = (BackendOutcome.FAIL_AFTER_EFFECT,)
        result = drive_request(ctrl, backend, 1, 'activate')
        snap = ctrl.snapshot()
        self.assertEqual(snap['state'][result.request_id], ap.STATE_UNKNOWN)
        self.assertEqual(set(snap['holds']), {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12})
        self.assertEqual(snap['active'], {})

    def test_fail_after_blocks_writes_on_subtree(self):
        ctrl, backend = fresh_full_controller()
        backend.script = (BackendOutcome.FAIL_AFTER_EFFECT,)
        drive_request(ctrl, backend, 1)
        # Action records in the held sub-tree are refused for writes...
        for record_id in (1, 3, 12):
            with self.assertRaises(SafetyHoldRefused):
                ctrl.request(record_id, 'activate')
        # ...navigation records fail the kind check first, but the hold is
        # still visible on the read path.
        self.assertTrue(ctrl.query(7)['hold'])

    def test_fail_after_unrelated_records_stay_writable(self):
        ctrl, backend = fresh_full_controller()
        backend.script = (BackendOutcome.FAIL_AFTER_EFFECT,)
        drive_request(ctrl, backend, 1)
        self.assertIsNotNone(ctrl.request(20))
        self.assertIsNotNone(ctrl.request(21))  # async, attached

    def test_fail_after_yields_no_private_receipt(self):
        ctrl, backend = fresh_full_controller()
        backend.script = (BackendOutcome.FAIL_AFTER_EFFECT,)
        result = drive_request(ctrl, backend, 1)
        self.assertIsNone(result.receipt)
        self.assertIsNone(ctrl._requests[result.request_id].receipt)

    def test_fail_after_exact_compensation_sequence(self):
        # A confirmed healthy cascade, then a partial-effect failure on an
        # unrelated sub-tree: the double must see exactly two publishes in
        # order and the controller must hold only the failed sub-tree.
        ctrl, backend = fresh_full_controller()
        backend.script = (BackendOutcome.EFFECT_OK, BackendOutcome.FAIL_AFTER_EFFECT)
        drive_request(ctrl, backend, 5)
        result = drive_request(ctrl, backend, 10)
        self.assertEqual(backend.invocations,
                         [(5, 'activate', BackendOutcome.EFFECT_OK),
                          (10, 'activate', BackendOutcome.FAIL_AFTER_EFFECT)])
        snap = ctrl.snapshot()
        self.assertEqual(snap['active'], {5: True, 6: True})
        self.assertEqual(snap['state'][result.request_id], ap.STATE_UNKNOWN)
        self.assertEqual(set(snap['holds']), {10, 11, 12})
        self.assertEqual(snap['saved_wishes'], [])
        with self.assertRaises(WishSaveRefused):
            ctrl.save_wish(10)

    def test_fail_after_read_paths_stay_responsive(self):
        ctrl, backend = fresh_full_controller()
        backend.script = (BackendOutcome.FAIL_AFTER_EFFECT,)
        drive_request(ctrl, backend, 1)
        snap = ctrl.snapshot()
        self.assertEqual(snap['schema'], ap.SCHEMA)
        self.assertEqual(ctrl.query(2), {'record_id': 2, 'active': False,
                                         'hold': True, 'saved_wish': False})
        self.assertFalse(ctrl.query(20)['hold'])


class TestCancelDuringHeldPublish(unittest.TestCase):
    def _to_held(self, ctrl, record_id):
        rid = ctrl.request(record_id, 'activate')
        ctrl.dispatch(rid)
        ctrl.publish(rid)
        ctrl.hold(rid)
        return rid

    def test_cancel_held_yields_unknown(self):
        ctrl, _backend = fresh_full_controller()
        rid = self._to_held(ctrl, 10)
        ctrl.cancel(rid)
        self.assertEqual(ctrl.snapshot()['state'][rid], ap.STATE_UNKNOWN)

    def test_cancel_held_is_never_terminal_failed(self):
        ctrl, _backend = fresh_full_controller()
        rid = self._to_held(ctrl, 10)
        ctrl.cancel(rid)
        self.assertNotEqual(ctrl.snapshot()['state'][rid], ap.STATE_FAILED)

    def test_cancel_held_creates_subtree_hold(self):
        ctrl, _backend = fresh_full_controller()
        rid = self._to_held(ctrl, 10)
        ctrl.cancel(rid)
        self.assertEqual(set(ctrl.snapshot()['holds']), {10, 11, 12})

    def test_cancel_held_blocks_subtree_writes(self):
        ctrl, _backend = fresh_full_controller()
        rid = self._to_held(ctrl, 10)
        ctrl.cancel(rid)
        with self.assertRaises(SafetyHoldRefused):
            ctrl.request(11, 'activate')
        with self.assertRaises(SafetyHoldRefused):
            ctrl.request(10, 'deactivate')

    def test_cancel_queued_is_safe_terminal_failed(self):
        ctrl, _backend = fresh_full_controller()
        rid = ctrl.request(20, 'activate')
        ctrl.cancel(rid)
        self.assertEqual(ctrl.snapshot()['state'][rid], ap.STATE_FAILED)
        self.assertEqual(ctrl.snapshot()['holds'], [])

    def test_cancel_terminal_refused(self):
        ctrl, _backend = fresh_full_controller()
        rid = complete(ctrl, 20)
        with self.assertRaises(InvalidTransitionError):
            ctrl.cancel(rid)


class TestCloseAndTargetExit(unittest.TestCase):
    def test_detach_clears_active_effects(self):
        ctrl, _backend = fresh_full_controller()
        complete(ctrl, 1)
        ctrl.detach()
        self.assertEqual(ctrl.snapshot()['active'], {})

    def test_detach_drains_queued_to_failed(self):
        ctrl, _backend = fresh_full_controller()
        rid = ctrl.request(4, 'activate')
        ctrl.detach()
        self.assertEqual(ctrl.snapshot()['state'][rid], ap.STATE_FAILED)

    def test_detach_drains_publishing_to_unknown_with_hold(self):
        ctrl, _backend = fresh_full_controller()
        rid = ctrl.request(10, 'activate')
        ctrl.dispatch(rid)
        ctrl.publish(rid)
        ctrl.detach()
        self.assertEqual(ctrl.snapshot()['state'][rid], ap.STATE_UNKNOWN)
        self.assertIn(10, ctrl.snapshot()['holds'])
        drain_entries = [e for e in ctrl._completion_log if e[2] == 'drained']
        self.assertEqual(len(drain_entries), 1)
        self.assertEqual(drain_entries[0][3], 'detach')

    def test_detach_keeps_saved_wishes_for_next_attach(self):
        ctrl, _backend = fresh_full_controller()
        complete(ctrl, 10)
        ctrl.save_wish(10)
        ctrl.detach()
        self.assertEqual(ctrl.snapshot()['saved_wishes'], [10])

    def test_detach_blocks_async_until_reattach(self):
        ctrl, _backend = fresh_full_controller()
        complete(ctrl, 10)
        ctrl.detach()
        with self.assertRaises(AsyncBeforeAttachRefused):
            ctrl.request(21, 'activate')
        ctrl.attach_confirmed()
        self.assertIsNotNone(ctrl.request(21, 'activate'))

    def test_close_keeps_active_effects(self):
        ctrl, _backend = fresh_full_controller()
        complete(ctrl, 1)
        ctrl.close_or_target_exit()
        self.assertEqual(ctrl.snapshot()['active'], {1: True, 2: True, 3: True,
                                                     4: True})

    def test_close_drains_inflight_and_keeps_async(self):
        ctrl, _backend = fresh_full_controller()
        complete(ctrl, 10)
        rid_queued = ctrl.request(4, 'activate')
        rid_publish = ctrl.request(9, 'activate')
        ctrl.dispatch(rid_publish)
        ctrl.publish(rid_publish)
        ctrl.close_or_target_exit()
        state = ctrl.snapshot()['state']
        self.assertEqual(state[rid_queued], ap.STATE_FAILED)
        self.assertEqual(state[rid_publish], ap.STATE_UNKNOWN)
        # Trainer close does not end the attach.
        self.assertIsNotNone(ctrl.request(21, 'activate'))

    def test_close_drain_reason_is_close_or_target_exit(self):
        ctrl, _backend = fresh_full_controller()
        rid = ctrl.request(20, 'activate')
        ctrl.close_or_target_exit()
        entries = [e for e in ctrl._completion_log if e[2] == 'drained']
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0][3], 'close_or_target_exit')


class TestLateCompletion(unittest.TestCase):
    def test_late_completion_logs_only(self):
        ctrl, backend = fresh_full_controller()
        backend.script = (BackendOutcome.LATE_COMPLETION,)
        result = drive_request(ctrl, backend, 10, 'activate')
        self.assertEqual(result.outcome, BackendOutcome.LATE_COMPLETION)
        self.assertEqual(ctrl.snapshot()['state'][result.request_id],
                         ap.STATE_FAILED)
        self.assertEqual(len(ctrl._completion_log), 1)
        self.assertEqual(ctrl._completion_log[0][2], 'late_completion')

    def test_late_completion_entry_fields(self):
        ctrl, backend = fresh_full_controller()
        backend.script = (BackendOutcome.LATE_COMPLETION,)
        result = drive_request(ctrl, backend, 10, 'activate')
        entry = ctrl._completion_log[0]
        self.assertEqual(entry[0], result.request_id)
        self.assertEqual(entry[1], 10)
        self.assertEqual(entry[2], 'late_completion')
        self.assertEqual(entry[3], ap.STATE_FAILED)
        self.assertEqual(entry[4], result.generation)
        late_receipt = entry[5]
        self.assertIsInstance(late_receipt, CompensationReceipt)
        self.assertEqual(late_receipt.record_id, 10)
        self.assertEqual(late_receipt.direction, 'activate')
        self.assertIs(late_receipt.confirmed, True)

    def test_late_completion_state_unchanged(self):
        ctrl, backend = fresh_full_controller()
        backend.script = (BackendOutcome.LATE_COMPLETION,)
        drive_request(ctrl, backend, 10)
        snap = ctrl.snapshot()
        self.assertEqual(snap['active'], {})
        self.assertEqual(snap['holds'], [])
        self.assertEqual(snap['saved_wishes'], [])
        with self.assertRaises(WishSaveRefused):
            ctrl.save_wish(10)

    def test_late_completion_requires_terminal(self):
        ctrl, _backend = fresh_full_controller()
        rid = ctrl.request(20, 'activate')  # still queued
        receipt = CompensationReceipt(rid, 20, 'activate', True, 1)
        with self.assertRaises(InvalidTransitionError):
            ctrl.late_completion(rid, receipt)


class TestSaveReplayBoundary(unittest.TestCase):
    def test_save_wish_only_after_confirmed_on(self):
        ctrl, _backend = fresh_full_controller()
        with self.assertRaisesRegex(WishSaveRefused, 'confirmed ON'):
            ctrl.save_wish(20)
        complete(ctrl, 20)
        ctrl.save_wish(20)
        self.assertEqual(ctrl.snapshot()['saved_wishes'], [20])
        self.assertTrue(ctrl.query(20)['saved_wish'])

    def test_failed_attempt_never_saved(self):
        ctrl, backend = fresh_full_controller()
        complete(ctrl, 20)  # confirmed ON, saved
        ctrl.save_wish(20)
        backend.script = (BackendOutcome.FAIL_BEFORE_EFFECT,)
        drive_request(ctrl, backend, 20, 'deactivate')  # failed OFF attempt
        with self.assertRaisesRegex(WishSaveRefused, 'never saved'):
            ctrl.save_wish(20)
        # The failed attempt does not erase the earlier confirmed save.
        self.assertEqual(ctrl.snapshot()['saved_wishes'], [20])

    def test_failed_attempt_not_replayed_on_next_attach(self):
        ctrl, backend = fresh_full_controller()
        complete(ctrl, 20)
        ctrl.save_wish(20)
        backend.script = (BackendOutcome.FAIL_BEFORE_EFFECT,)
        drive_request(ctrl, backend, 20, 'deactivate')  # failed OFF attempt
        ctrl.detach()
        ctrl.attach_confirmed()  # next attach
        replayed, skipped = ctrl.replay_saved_wishes()
        self.assertEqual(replayed, ())
        self.assertEqual(skipped, ((20, 'failed-or-unknown'),))

    def test_replay_skips_held_records(self):
        ctrl, backend = fresh_full_controller()
        complete(ctrl, 3)
        ctrl.save_wish(3)
        complete(ctrl, 20)
        ctrl.save_wish(20)
        backend.script = (BackendOutcome.FAIL_AFTER_EFFECT,)
        drive_request(ctrl, backend, 2)  # holds {2, 3, 4}
        replayed, skipped = ctrl.replay_saved_wishes()
        self.assertEqual(replayed, (20,))
        self.assertEqual(skipped, ((3, 'held'),))

    def test_replay_skips_failed_and_inflight(self):
        ctrl, backend = fresh_full_controller()
        complete(ctrl, 10)
        ctrl.save_wish(10)
        complete(ctrl, 4)
        ctrl.save_wish(4)
        backend.script = (BackendOutcome.FAIL_BEFORE_EFFECT,)
        drive_request(ctrl, backend, 4, 'deactivate')
        ctrl.request(10, 'activate')  # queued, in-flight
        replayed, skipped = ctrl.replay_saved_wishes()
        self.assertEqual(replayed, ())
        self.assertEqual(skipped, ((4, 'failed-or-unknown'), (10, 'inflight')))

    def test_replay_reactivates_full_required_cascade(self):
        ctrl, _backend = fresh_full_controller()
        complete(ctrl, 1)
        ctrl.save_wish(1)
        replayed, skipped = ctrl.replay_saved_wishes()
        self.assertEqual((replayed, skipped), ((1,), ()))
        rid = max(ctrl.snapshot()['state'])
        gen = ctrl.request_generation(rid)
        ctrl.dispatch(rid)
        ctrl.publish(rid)
        ctrl.confirm_success(rid, gen)
        self.assertEqual(ctrl.snapshot()['active'], {1: True, 2: True, 3: True,
                                                     4: True})

    def test_replay_async_before_attach_skipped(self):
        ctrl, _backend = fresh_full_controller()
        complete(ctrl, 21)
        ctrl.save_wish(21)
        ctrl.detach()
        replayed, skipped = ctrl.replay_saved_wishes()
        self.assertEqual(replayed, ())
        self.assertEqual(skipped, ((21, 'not-attached'),))

    def test_confirmed_off_clears_saved_wish(self):
        ctrl, _backend = fresh_full_controller()
        complete(ctrl, 5)
        ctrl.save_wish(5)
        self.assertEqual(ctrl.snapshot()['saved_wishes'], [5])
        rid = ctrl.request(5, 'deactivate')
        gen = ctrl.request_generation(rid)
        ctrl.dispatch(rid)
        ctrl.publish(rid)
        ctrl.confirm_success(rid, gen)
        self.assertEqual(ctrl.snapshot()['saved_wishes'], [])
        self.assertFalse(ctrl.query(5)['saved_wish'])
        # Cleared wish drops the child out of future parent ON plans.
        self.assertEqual(effects_of(ctrl, 1, 'activate'), (1, 2, 3, 4))


class TestFreezeNotAWish(unittest.TestCase):
    def test_freeze_never_creates_saved_wish(self):
        ctrl, _backend = fresh_full_controller()
        ctrl.freeze_value(22, True)  # value_only record
        with self.assertRaises(WishSaveRefused):
            ctrl.save_wish(22)

    def test_freeze_kind_gate_and_receipts(self):
        ctrl, _backend = fresh_full_controller()
        with self.assertRaises(ActivationTargetRefused):
            ctrl.freeze_value(7, True)   # navigation
        with self.assertRaises(ActivationTargetRefused):
            ctrl.freeze_value(21, True)  # async
        self.assertEqual(ctrl.freeze_value(22, True), (22, True, 0))
        self.assertEqual(ctrl.freeze_value(22, False), (22, False, 0))
        self.assertEqual(ctrl.freeze_receipts, ((22, True, 0), (22, False, 0)))


class TestScriptedBackendDouble(unittest.TestCase):
    def test_script_consumed_then_defaults_to_effect_ok(self):
        backend = ScriptedBackendDouble((BackendOutcome.FAIL_BEFORE_EFFECT,))
        self.assertEqual(backend.advance(1, 'activate'),
                         BackendOutcome.FAIL_BEFORE_EFFECT)
        self.assertEqual(backend.advance(2, 'deactivate'),
                         BackendOutcome.EFFECT_OK)
        self.assertEqual(
            backend.invocations,
            [(1, 'activate', BackendOutcome.FAIL_BEFORE_EFFECT),
             (2, 'deactivate', BackendOutcome.EFFECT_OK)])

    def test_remaining_counts_unconsumed_script(self):
        backend = ScriptedBackendDouble(
            (BackendOutcome.FAIL_AFTER_EFFECT, BackendOutcome.LATE_COMPLETION))
        self.assertEqual(backend.remaining, 2)
        backend.advance(1)
        self.assertEqual(backend.remaining, 1)
        backend.advance(2)
        self.assertEqual(backend.remaining, 0)

    def test_drive_result_fields_on_success(self):
        ctrl, backend = fresh_full_controller()
        result = drive_request(ctrl, backend, 20)
        self.assertIsInstance(result.receipt, CompensationReceipt)
        self.assertEqual(result.receipt.record_id, 20)
        self.assertEqual(result.receipt.direction, 'activate')
        self.assertIs(result.receipt.confirmed, True)
        self.assertEqual(result.generation, 1)
        self.assertTrue(ctrl.query(20)['active'])


class TestConsumerOwnership(unittest.TestCase):
    def _ownership_controller(self):
        ctrl = ActivationController(ownership_topology().table)
        ctrl.attach_confirmed()
        return ctrl

    def test_claim_and_lookup_after_parent_cascade(self):
        ctrl = self._ownership_controller()
        backend = ScriptedBackendDouble()
        tracker = ConsumerOwnershipTracker()
        rid, receipt = complete_via(ctrl, backend, 50)
        owner = tracker.claim('A', rid, 50, receipt.generation, (50, 51))
        self.assertIsInstance(owner, ConsumerOwner)
        self.assertEqual(tracker.owner_of(50).consumer_id, 'A')
        self.assertEqual(tracker.owner_of(51).consumer_id, 'A')
        self.assertTrue(tracker.is_owned_by(51, 'A'))
        self.assertFalse(tracker.is_owned_by(51, 'B'))
        self.assertIsNone(tracker.owner_of(52))

    def test_conflict_across_consumers(self):
        ctrl = self._ownership_controller()
        backend = ScriptedBackendDouble()
        tracker = ConsumerOwnershipTracker()
        rid, receipt = complete_via(ctrl, backend, 50)
        tracker.claim('A', rid, 50, receipt.generation, (50, 51))
        with self.assertRaises(ConsumerOwnershipConflict):
            tracker.claim('B', 99, 51, 99, (51,))
        # The failed claim leaves existing ownership intact.
        self.assertEqual(tracker.owner_of(51).consumer_id, 'A')

    def test_disjoint_claims_allowed(self):
        ctrl = self._ownership_controller()
        backend = ScriptedBackendDouble()
        tracker = ConsumerOwnershipTracker()
        rid, receipt = complete_via(ctrl, backend, 50)
        tracker.claim('A', rid, 50, receipt.generation, (50, 51))
        owner_b = tracker.claim('B', 99, 53, 99, (53,))
        self.assertEqual(owner_b.consumer_id, 'B')
        self.assertEqual(tracker.owned_records('A'), (50, 51))
        self.assertEqual(tracker.owned_records('B'), (53,))

    def test_same_consumer_reclaim_allowed(self):
        ctrl = self._ownership_controller()
        backend = ScriptedBackendDouble()
        tracker = ConsumerOwnershipTracker()
        rid, receipt = complete_via(ctrl, backend, 50)
        tracker.claim('A', rid, 50, receipt.generation, (50, 51))
        owner = tracker.claim('A', rid + 1, 51, 2, (51,))
        self.assertEqual(owner.request_id, rid + 1)

    def test_release_frees_effects_for_other_consumers(self):
        ctrl = self._ownership_controller()
        backend = ScriptedBackendDouble()
        tracker = ConsumerOwnershipTracker()
        rid, receipt = complete_via(ctrl, backend, 50)
        tracker.claim('A', rid, 50, receipt.generation, (50, 51))
        # Parent 50 is turned off again; its cascade effects are released.
        off = complete(ctrl, 50, 'deactivate')
        tracker.release(rid)
        self.assertIsNone(tracker.owner_of(50))
        self.assertIsNone(tracker.owner_of(51))
        owner_b = tracker.claim('B', off, 50, 2, (50,))
        self.assertEqual(owner_b.consumer_id, 'B')

    def test_release_unknown_request_is_noop(self):
        tracker = ConsumerOwnershipTracker()
        tracker.release(4242)  # must not raise
        self.assertEqual(tracker.all_owners(), ())

    def test_all_owners_sorted_by_request(self):
        tracker = ConsumerOwnershipTracker()
        tracker.claim('A', 1, 1, 1, (1,))
        tracker.claim('B', 2, 2, 2, (2,))
        owners = tracker.all_owners()
        self.assertEqual([o.request_id for o in owners], [1, 2])
        tracker.clear()
        self.assertEqual(tracker.all_owners(), ())


if __name__ == '__main__':
    unittest.main()
