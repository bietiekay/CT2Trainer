"""Tests for the AP-07 parent/async activation policy model (stage 1).

Covers: table validation (duplicates, cycles, ownership, parent_ids
consistency), selection projection, ON top-down / OFF bottom-up expansion,
moBindActivation blocking, owner queue transitions with generations,
safety holds after uncertain effects, cancel semantics, late completion,
the save/replay wish boundary, value-freeze orthogonality and drain on
detach/close. Pure state machine; no Cheat Engine implementation code is
used or required.
"""
import unittest

from ct2trainer.native import activation_policy as ap
from ct2trainer.native.activation_policy import (
    ActivationBlocked,
    ActivationController,
    ActivationPolicyError,
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
    StaleGenerationRefused,
    UnknownRecordError,
    WishSaveRefused,
    project_selection,
)

REQ = ap.RELATION_REQUIRED
DIRECT = ap.RELATION_DIRECT
NAV = ap.RELATION_NAVIGATION
COLL = ap.RELATION_COLLECTIVE_OFF


def build_table():
    records = [
        RecordSpec(1, 'action'),            # root
        RecordSpec(2, 'action', (1,)),      # required child
        RecordSpec(3, 'action', (2,)),      # required grandchild
        RecordSpec(4, 'action', (1,)),      # direct_activation child
        RecordSpec(5, 'navigation', (1,)),  # navigation child
        RecordSpec(6, 'action', (5,)),      # child under navigation
        RecordSpec(7, 'action', (1,)),      # collective_off child
        RecordSpec(10, 'action'),           # standalone action
        RecordSpec(11, 'async'),            # async action
        RecordSpec(12, 'value_only'),       # value record
        RecordSpec(13, 'action'),           # moBindActivation on target
        RecordSpec(14, 'action'),           # parent of moBind child
        RecordSpec(15, 'action', (14,)),    # required child with moBind flag
    ]
    relations = {
        1: {2: REQ, 4: DIRECT, 5: NAV, 7: COLL},
        2: {3: REQ},
        5: {6: NAV},
        14: {15: REQ},
    }
    flags = {13: {FLAG_MO_BIND_ACTIVATION}, 15: {FLAG_MO_BIND_ACTIVATION}}
    return RecordTable(records, relations, flags)


def make_controller(attached=True):
    ctrl = ActivationController(build_table())
    if attached:
        ctrl.attach_confirmed()
    return ctrl


def complete(ctrl, record_id, intent='activate'):
    """Request -> dispatch -> publish -> confirm; return (request_id, receipt)."""
    rid = ctrl.request(record_id, intent)
    gen = ctrl.request_generation(rid)
    ctrl.dispatch(rid)
    ctrl.publish(rid)
    receipt = ctrl.confirm_success(rid, gen)
    return rid, receipt


class TestRecordTable(unittest.TestCase):
    def test_valid_tree_topology(self):
        table = build_table()
        self.assertIn(1, table)
        self.assertNotIn(99, table)
        self.assertEqual(table.record(1).kind, 'action')
        children = dict(table.children(1))
        self.assertEqual(children, {2: REQ, 4: DIRECT, 5: NAV, 7: COLL})
        self.assertEqual(table.children(1, REQ), ((2, REQ),))
        self.assertEqual(table.children(2), ((3, REQ),))
        self.assertEqual(table.ancestors_of(6), (1, 5))
        self.assertEqual(table.ancestors_of(1), ())
        # sub_tree is strict descendants (root excluded, cycle-safe).
        self.assertEqual(table.sub_tree(1), frozenset({2, 3, 4, 5, 6, 7}))
        self.assertEqual(table.sub_tree(3), frozenset())
        self.assertIn(FLAG_MO_BIND_ACTIVATION, table.flags(13))
        self.assertEqual(table.flags(1), frozenset())

    def test_duplicate_record_rejected(self):
        with self.assertRaisesRegex(ActivationPolicyError, 'Duplicate record ID'):
            RecordTable([RecordSpec(1), RecordSpec(1)], {})

    def test_unknown_relation_parent_rejected(self):
        with self.assertRaisesRegex(UnknownRecordError, 'unknown'):
            RecordTable([RecordSpec(1)], {99: {1: REQ}})

    def test_unknown_relation_child_rejected(self):
        with self.assertRaisesRegex(UnknownRecordError, 'unknown'):
            RecordTable([RecordSpec(1)], {1: {99: REQ}})

    def test_self_parent_rejected(self):
        with self.assertRaisesRegex(CycleError, 'itself'):
            RecordTable([RecordSpec(1)], {1: {1: REQ}})

    def test_cycle_rejected(self):
        records = [RecordSpec(20, 'action', (21,)), RecordSpec(21, 'action', (20,))]
        with self.assertRaisesRegex(CycleError, 'cycle'):
            RecordTable(records, {20: {21: REQ}, 21: {20: REQ}})

    def test_unknown_relation_kind_rejected(self):
        with self.assertRaisesRegex(ActivationPolicyError, 'Unknown relation kind'):
            RecordTable(
                [RecordSpec(10), RecordSpec(12)], {10: {12: 'bogus'}})

    def test_bad_record_spec_rejected(self):
        with self.assertRaises(ActivationPolicyError):
            RecordSpec(0)
        with self.assertRaises(ActivationPolicyError):
            RecordSpec(5, 'bogus')
        with self.assertRaises(ActivationPolicyError):
            RecordSpec(5, 'action', [1])
        table = RecordTable([], {})
        with self.assertRaises(UnknownRecordError):
            table.record(1)
        with self.assertRaises(UnknownRecordError):
            table.children(1)

    def test_unknown_flag_record_rejected(self):
        with self.assertRaisesRegex(UnknownRecordError, 'unknown'):
            RecordTable([RecordSpec(1)], {}, {99: {FLAG_MO_BIND_ACTIVATION}})

    def test_parent_ids_must_match_relations(self):
        # Relation says 21 is parent of 20, but 20 declares no parent.
        records = [RecordSpec(20), RecordSpec(21, 'action', (20,))]
        with self.assertRaisesRegex(ActivationPolicyError, 'do not match'):
            RecordTable(records, {21: {20: REQ}})


class TestSelectionProjection(unittest.TestCase):
    def test_selection_pulls_ancestors(self):
        self.assertEqual(project_selection(build_table(), (6,)), frozenset({6, 5, 1}))

    def test_selection_union_empty_and_unknown(self):
        table = build_table()
        self.assertEqual(project_selection(table, ()), frozenset())
        self.assertEqual(project_selection(table, (3, 10)), frozenset({1, 2, 3, 10}))
        with self.assertRaises(UnknownRecordError):
            project_selection(table, (99,))


class TestExpansion(unittest.TestCase):
    def test_on_expansion_top_down(self):
        ctrl = make_controller()
        self.assertEqual(ctrl._expand(1, 'activate'), (1, 2, 3))

    def test_on_includes_wished_direct_child_only(self):
        ctrl = make_controller()
        complete(ctrl, 4)
        self.assertEqual(ctrl._expand(1, 'activate'), (1, 2, 3, 4))
        rid = ctrl.request(4, 'deactivate')
        ctrl.dispatch(rid)
        ctrl.publish(rid)
        ctrl.confirm_success(rid, ctrl.request_generation(rid))
        self.assertEqual(ctrl._expand(1, 'activate'), (1, 2, 3))

    def test_off_expansion_bottom_up_active_only(self):
        ctrl = make_controller()
        complete(ctrl, 1)
        complete(ctrl, 4)
        complete(ctrl, 7)
        self.assertEqual(ctrl._expand(1, 'deactivate'), (3, 2, 4, 7, 1))

    def test_off_excludes_inactive_and_navigation(self):
        ctrl = make_controller()
        complete(ctrl, 1)
        # Only the required chain is active; 4, 7 and navigation children are not.
        self.assertEqual(ctrl._expand(1, 'deactivate'), (3, 2, 1))
        # Navigation children are never part of an effect plan.
        self.assertNotIn(5, ctrl._expand(1, 'activate'))
        self.assertNotIn(6, ctrl._expand(1, 'deactivate'))

    def test_navigation_and_value_targets_refused(self):
        ctrl = make_controller()
        with self.assertRaisesRegex(ActivationTargetRefused, 'not'):
            ctrl._expand(5, 'activate')
        with self.assertRaisesRegex(ActivationTargetRefused, 'not'):
            ctrl._expand(12, 'activate')

    def test_mo_bind_target_blocked(self):
        ctrl = make_controller()
        with self.assertRaisesRegex(ActivationBlocked, 'moBindActivation'):
            ctrl.request(13, 'activate')

    def test_mo_bind_cascade_effect_blocked(self):
        ctrl = make_controller()
        with self.assertRaisesRegex(ActivationBlocked, 'moBindActivation'):
            ctrl.request(14, 'activate')

    def test_mo_bind_outside_cascade_does_not_block(self):
        records = [
            RecordSpec(1, 'action'),
            RecordSpec(5, 'navigation', (1,)),
            RecordSpec(6, 'action', (5,)),
        ]
        relations = {1: {5: NAV}, 5: {6: NAV}}
        flags = {6: {FLAG_MO_BIND_ACTIVATION}}
        ctrl = ActivationController(RecordTable(records, relations, flags))
        ctrl.attach_confirmed()
        rid = ctrl.request(1, 'activate')
        self.assertEqual(ctrl._expand(1, 'activate'), (1,))
        self.assertEqual(ctrl.snapshot()['state'][rid], ap.STATE_QUEUED)


class TestOwnerQueue(unittest.TestCase):
    def test_generation_advances_and_is_exposed(self):
        ctrl = make_controller()
        self.assertEqual(ctrl.snapshot()['generation'], 0)
        rid1 = ctrl.request(10)
        self.assertEqual(ctrl.snapshot()['generation'], 1)
        self.assertEqual(ctrl.request_generation(rid1), 1)
        rid2 = ctrl.request(1)
        self.assertEqual(ctrl.snapshot()['generation'], 2)
        self.assertEqual(ctrl.request_generation(rid2), 2)

    def test_transition_order_enforced(self):
        ctrl = make_controller()
        rid = ctrl.request(10)
        with self.assertRaises(InvalidTransitionError):
            ctrl.publish(rid)
        with self.assertRaises(InvalidTransitionError):
            ctrl.hold(rid)
        ctrl.dispatch(rid)
        with self.assertRaises(InvalidTransitionError):
            ctrl.dispatch(rid)
        ctrl.publish(rid)
        with self.assertRaises(InvalidTransitionError):
            ctrl.dispatch(rid)

    def test_inflight_overlap_refused(self):
        ctrl = make_controller()
        ctrl.request(1)
        with self.assertRaises(OwnershipConflict):
            ctrl.request(2)
        with self.assertRaises(OwnershipConflict):
            ctrl.request(3)
        # Unrelated sub-trees do not conflict.
        self.assertIsNotNone(ctrl.request(10))

    def test_async_requires_confirmed_attach(self):
        ctrl = make_controller(attached=False)
        with self.assertRaises(AsyncBeforeAttachRefused):
            ctrl.request(11)
        ctrl.attach_confirmed()
        self.assertIsNotNone(ctrl.request(11))

    def test_budget_reserve_hook_called_on_dispatch(self):
        calls = []
        ctrl = ActivationController(build_table(),
                                     budget_reserve=lambda r, g: calls.append((r, g)))
        ctrl.attach_confirmed()
        complete(ctrl, 10)
        self.assertEqual(calls, [(10, 1)])


class TestCompletion(unittest.TestCase):
    def test_confirm_success_marks_effects_active(self):
        ctrl = make_controller()
        rid, receipt = complete(ctrl, 1)
        self.assertTrue(ctrl.query(1)['active'])
        self.assertTrue(ctrl.query(2)['active'])
        self.assertTrue(ctrl.query(3)['active'])
        self.assertFalse(ctrl.query(4)['active'])
        self.assertEqual(ctrl.snapshot()['active'], {1: True, 2: True, 3: True})
        self.assertEqual(receipt.request_id, rid)
        self.assertEqual(receipt.record_id, 1)
        self.assertEqual(receipt.direction, 'activate')
        self.assertIs(receipt.confirmed, True)
        self.assertEqual(receipt.generation, 1)

    def test_confirm_requires_matching_generation(self):
        ctrl = make_controller()
        rid = ctrl.request(10)
        ctrl.dispatch(rid)
        ctrl.publish(rid)
        with self.assertRaises(StaleGenerationRefused):
            ctrl.confirm_success(rid, 99)
        receipt = ctrl.confirm_success(rid, 1)
        self.assertIs(receipt.confirmed, True)

    def test_confirm_from_wrong_state_refused(self):
        ctrl = make_controller()
        rid = ctrl.request(10)
        with self.assertRaises(InvalidTransitionError):
            ctrl.confirm_success(rid, 1)
        rid2 = ctrl.request(1)
        ctrl.dispatch(rid2)
        with self.assertRaises(InvalidTransitionError):
            ctrl.confirm_success(rid2, 2)

    def test_confirm_off_clears_wish_and_saved_wish(self):
        ctrl = make_controller()
        complete(ctrl, 4)
        ctrl.save_wish(4)
        self.assertEqual(ctrl.snapshot()['saved_wishes'], [4])
        rid = ctrl.request(4, 'deactivate')
        ctrl.dispatch(rid)
        ctrl.publish(rid)
        ctrl.confirm_success(rid, ctrl.request_generation(rid))
        self.assertEqual(ctrl.snapshot()['saved_wishes'], [])
        self.assertFalse(ctrl.query(4)['active'])
        self.assertFalse(ctrl.query(4)['saved_wish'])
        # The cleared wish drops the child out of future parent ON plans.
        self.assertEqual(ctrl._expand(1, 'activate'), (1, 2, 3))


class TestFailureAndCancel(unittest.TestCase):
    def test_fail_before_effect_is_terminal_failed_without_hold(self):
        ctrl = make_controller()
        rid = ctrl.request(10)
        ctrl.dispatch(rid)
        ctrl.publish(rid)
        ctrl.fail_before_effect(rid)
        self.assertEqual(ctrl.snapshot()['state'][rid], ap.STATE_FAILED)
        self.assertEqual(ctrl.snapshot()['holds'], [])
        self.assertFalse(ctrl.query(10)['hold'])

    def test_fail_after_effect_unknown_and_subtree_hold(self):
        ctrl = make_controller()
        rid = ctrl.request(1)
        ctrl.dispatch(rid)
        ctrl.publish(rid)
        ctrl.fail_after_effect(rid)
        snap = ctrl.snapshot()
        self.assertEqual(snap['state'][rid], ap.STATE_UNKNOWN)
        self.assertTrue({1, 2, 3}.issubset(set(snap['holds'])))
        with self.assertRaises(SafetyHoldRefused):
            ctrl.request(3)
        with self.assertRaises(SafetyHoldRefused):
            ctrl.request(1)
        # Unrelated records stay writable.
        self.assertIsNotNone(ctrl.request(10))
        self.assertTrue(ctrl.query(2)['hold'])

    def test_cancel_queued_is_terminal_failed(self):
        ctrl = make_controller()
        rid = ctrl.request(10)
        ctrl.cancel(rid)
        self.assertEqual(ctrl.snapshot()['state'][rid], ap.STATE_FAILED)
        self.assertEqual(ctrl.snapshot()['holds'], [])

    def test_cancel_inflight_yields_unknown_and_hold(self):
        ctrl = make_controller()
        rid = ctrl.request(10)
        ctrl.dispatch(rid)
        ctrl.cancel(rid)
        self.assertEqual(ctrl.snapshot()['state'][rid], ap.STATE_UNKNOWN)
        self.assertIn(10, ctrl.snapshot()['holds'])

        rid2 = ctrl.request(11)
        ctrl.dispatch(rid2)
        ctrl.publish(rid2)
        ctrl.cancel(rid2)
        self.assertEqual(ctrl.snapshot()['state'][rid2], ap.STATE_UNKNOWN)

        rid3 = ctrl.request(7)
        ctrl.dispatch(rid3)
        ctrl.publish(rid3)
        ctrl.hold(rid3)
        ctrl.cancel(rid3)
        self.assertEqual(ctrl.snapshot()['state'][rid3], ap.STATE_UNKNOWN)
        self.assertIn(7, ctrl.snapshot()['holds'])

    def test_cancel_terminal_refused(self):
        ctrl = make_controller()
        rid, _ = complete(ctrl, 10)
        with self.assertRaises(InvalidTransitionError):
            ctrl.cancel(rid)

    def test_late_completion_only_terminal_and_log_only(self):
        ctrl = make_controller()
        rid = ctrl.request(10)
        ctrl.dispatch(rid)
        ctrl.publish(rid)
        ctrl.fail_before_effect(rid)
        receipt = CompensationReceipt(rid, 10, 'activate', True, 1)
        ctrl.late_completion(rid, receipt)
        self.assertEqual(ctrl.snapshot()['state'][rid], ap.STATE_FAILED)
        self.assertEqual(len(ctrl._completion_log), 1)
        entry = ctrl._completion_log[0]
        self.assertEqual(entry[0], rid)
        self.assertEqual(entry[2], 'late_completion')
        self.assertEqual(entry[5], receipt)
        rid2 = ctrl.request(7)
        with self.assertRaises(InvalidTransitionError):
            ctrl.late_completion(rid2, CompensationReceipt(rid2, 7, 'activate', True, 2))


class TestSaveReplay(unittest.TestCase):
    def test_save_wish_requires_confirmed_on(self):
        ctrl = make_controller()
        with self.assertRaisesRegex(WishSaveRefused, 'confirmed ON'):
            ctrl.save_wish(10)
        complete(ctrl, 10)
        ctrl.save_wish(10)
        self.assertEqual(ctrl.snapshot()['saved_wishes'], [10])
        self.assertTrue(ctrl.query(10)['saved_wish'])

    def test_confirmed_on_not_auto_saved(self):
        ctrl = make_controller()
        complete(ctrl, 10)
        self.assertEqual(ctrl.snapshot()['saved_wishes'], [])

    def test_save_wish_refused_after_failed_attempt(self):
        ctrl = make_controller()
        complete(ctrl, 10)
        ctrl.save_wish(10)
        rid = ctrl.request(10, 'deactivate')
        ctrl.dispatch(rid)
        ctrl.publish(rid)
        ctrl.fail_before_effect(rid)
        with self.assertRaisesRegex(WishSaveRefused, 'never saved'):
            ctrl.save_wish(10)
        # The failed OFF attempt does not erase an earlier confirmed save.
        self.assertEqual(ctrl.snapshot()['saved_wishes'], [10])

    def test_replay_skips_held_per_record(self):
        ctrl = make_controller()
        complete(ctrl, 4)
        ctrl.save_wish(4)
        complete(ctrl, 10)
        ctrl.save_wish(10)
        rid = ctrl.request(1, 'activate')
        ctrl.dispatch(rid)
        ctrl.publish(rid)
        ctrl.fail_after_effect(rid)
        replayed, skipped = ctrl.replay_saved_wishes()
        self.assertEqual(replayed, (10,))
        self.assertEqual(skipped, ((4, 'held'),))

    def test_replay_skips_failed_and_inflight(self):
        ctrl = make_controller()
        complete(ctrl, 10)
        ctrl.save_wish(10)
        complete(ctrl, 4)
        ctrl.save_wish(4)
        rid = ctrl.request(4, 'deactivate')
        ctrl.dispatch(rid)
        ctrl.publish(rid)
        ctrl.fail_before_effect(rid)
        ctrl.request(10)  # queued, in-flight
        replayed, skipped = ctrl.replay_saved_wishes()
        self.assertEqual(replayed, ())
        self.assertEqual(skipped, ((4, 'failed-or-unknown'), (10, 'inflight')))

    def test_replay_reactivates_cascade(self):
        ctrl = make_controller()
        complete(ctrl, 1)
        ctrl.save_wish(1)
        replayed, skipped = ctrl.replay_saved_wishes()
        self.assertEqual((replayed, skipped), ((1,), ()))
        rid = max(ctrl.snapshot()['state'])
        gen = ctrl.request_generation(rid)
        ctrl.dispatch(rid)
        ctrl.publish(rid)
        ctrl.confirm_success(rid, gen)
        self.assertTrue(ctrl.query(1)['active'])
        self.assertTrue(ctrl.query(2)['active'])
        self.assertTrue(ctrl.query(3)['active'])


class TestFreeze(unittest.TestCase):
    def test_freeze_receipt_and_record_kind_gate(self):
        ctrl = make_controller()
        self.assertEqual(ctrl.freeze_value(12, True), (12, True, 0))
        with self.assertRaises(ActivationTargetRefused):
            ctrl.freeze_value(5, True)
        with self.assertRaises(ActivationTargetRefused):
            ctrl.freeze_value(11, True)
        self.assertEqual(ctrl.freeze_value(10, False), (10, False, 0))
        self.assertEqual(len(ctrl.freeze_receipts), 2)

    def test_freeze_is_never_a_wish(self):
        ctrl = make_controller()
        ctrl.freeze_value(10, True)
        with self.assertRaises(WishSaveRefused):
            ctrl.save_wish(10)
        complete(ctrl, 10)
        ctrl.save_wish(10)
        replayed, skipped = ctrl.replay_saved_wishes()
        self.assertEqual((replayed, skipped), ((10,), ()))
        self.assertEqual(ctrl.snapshot()['saved_wishes'], [10])
        self.assertEqual(ctrl.freeze_receipts, ((10, True, 0),))


class TestDrain(unittest.TestCase):
    def test_detach_drains_inflight_clears_active_blocks_async(self):
        ctrl = make_controller()
        complete(ctrl, 10)
        ctrl.save_wish(10)
        rid_queued = ctrl.request(4)
        rid_publish = ctrl.request(7)
        ctrl.dispatch(rid_publish)
        ctrl.publish(rid_publish)
        ctrl.detach()
        state = ctrl.snapshot()['state']
        self.assertEqual(state[rid_queued], ap.STATE_FAILED)
        self.assertEqual(state[rid_publish], ap.STATE_UNKNOWN)
        self.assertIn(7, ctrl.snapshot()['holds'])
        # Saved wishes survive detach for the next attach; active effects do not.
        self.assertEqual(ctrl.snapshot()['saved_wishes'], [10])
        self.assertFalse(ctrl.query(10)['active'])
        with self.assertRaises(AsyncBeforeAttachRefused):
            ctrl.request(11)

    def test_close_drains_inflight_keeps_attach(self):
        ctrl = make_controller()
        complete(ctrl, 10)
        rid_queued = ctrl.request(4)
        rid_publish = ctrl.request(7)
        ctrl.dispatch(rid_publish)
        ctrl.publish(rid_publish)
        ctrl.close_or_target_exit()
        state = ctrl.snapshot()['state']
        self.assertEqual(state[rid_queued], ap.STATE_FAILED)
        self.assertEqual(state[rid_publish], ap.STATE_UNKNOWN)
        # Trainer close does not kill the target's effects.
        self.assertTrue(ctrl.query(10)['active'])
        self.assertIsNotNone(ctrl.request(11))

    def test_drain_preserves_terminal_requests(self):
        ctrl = make_controller()
        rid_done, _ = complete(ctrl, 10)
        rid_open = ctrl.request(4)
        ctrl.close_or_target_exit()
        state = ctrl.snapshot()['state']
        self.assertEqual(state[rid_done], ap.STATE_SUCCESS)
        self.assertEqual(state[rid_open], ap.STATE_FAILED)


if __name__ == '__main__':
    unittest.main()
