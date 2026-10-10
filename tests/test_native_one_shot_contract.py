"""Focused fixture-driven tests for the one-shot ON/OFF save contract.

Drives ``one_shot_contract.py`` against the synthetic record sets and the
deterministic backend double from ``one_shot_fixture_data.py``.  Pinned
scenarios: phase transitions including the PENDING block, save only
after a confirmed ON, OFF with exactly zero backend operations, the
re-attach replay rules (exactly once per attach generation, FAILED /
UNKNOWN never, not-attached / held / already-executed skips,
double-execution guard), explicit manual re-runs, the marker codec
(round-trip, sorting, CRC, length, identity binding, empty list, full
corruption rejection), and freeze orthogonality.  No engine, compiler,
state file, or real target is involved.
"""
import struct
import unittest
import zlib

from ct2trainer.native.one_shot_contract import (
    EXECUTED,
    FAILED,
    INACTIVE,
    NOT_SAVED,
    PENDING,
    OneShotContract,
    OneShotContractError,
    OneShotGenerationConflict,
    OneShotMarkerError,
    OneShotNotAttachedRefused,
    OneShotPendingRefused,
    OneShotReceipt,
    OneShotReceiptRefused,
    OneShotRecordKindRefused,
    OneShotUnknownRecordError,
    OneShotWishSaveRefused,
    decode_markers,
    encode_markers,
)

try:
    from one_shot_fixture_data import (
        CT_HASH,
        DEFAULT_PROGRAMS,
        FLAKY,
        MIXED_RECORDS,
        ONE_SHOT_RECORDS,
        PARENT_CHILD_RECORDS,
        PROCESS_NAME,
        OneShotBackendDouble,
        OneShotOutcome,
        attached_contract,
        make_contract,
    )
except ModuleNotFoundError:  # invoked as tests.test_native_one_shot_contract
    from tests.one_shot_fixture_data import (
        CT_HASH,
        DEFAULT_PROGRAMS,
        FLAKY,
        MIXED_RECORDS,
        ONE_SHOT_RECORDS,
        PARENT_CHILD_RECORDS,
        PROCESS_NAME,
        OneShotBackendDouble,
        OneShotOutcome,
        attached_contract,
        make_contract,
    )


def session(records=None, programs=None, generation=1):
    """Attached contract plus a fresh scripted backend double."""
    contract = make_contract(records, programs)
    contract.attach(generation)
    return contract, OneShotBackendDouble()


def marker_region(raw, marker_index=0):
    """Offset of one 13-byte marker inside an encoded blob."""
    name_len = len(PROCESS_NAME)
    return 4 + 8 + 32 + 4 + name_len + 4 + marker_index * 13


class TestPhaseMachine(unittest.TestCase):
    def test_initial_state_all_inactive(self):
        contract, backend = session()
        snap = contract.snapshot()
        self.assertTrue(snap['attached'])
        self.assertEqual(snap['generation'], 1)
        self.assertEqual(snap['phases'], {1: INACTIVE, 2: INACTIVE,
                                          3: INACTIVE, 4: INACTIVE})
        self.assertEqual(snap['saved_wishes'], [])
        self.assertEqual(snap['attempts'], [])

    def test_unknown_record_rejected_with_record_context(self):
        contract, backend = session()
        with self.assertRaisesRegex(OneShotUnknownRecordError,
                                    r'record 99 is not part'):
            contract.request_on(backend, 99)

    def test_confirmed_on_executes_exactly_once(self):
        contract, backend = session()
        receipt = contract.request_on(backend, 1)
        self.assertEqual(receipt, OneShotReceipt(1, True))
        query = contract.query(1)
        self.assertEqual(query['phase'], EXECUTED)
        self.assertEqual(query['attempt_count'], 1)
        self.assertTrue(query['effect_persists'])
        self.assertEqual(backend.invocations,
                         [(1, b'one-shot:grant-1', OneShotOutcome.OK)])
        self.assertEqual(contract.snapshot()['attempts'],
                         [(1, 1, 'explicit', 'confirmed')])

    def test_failed_on_reaches_failed(self):
        contract, backend = session()
        backend.script = (OneShotOutcome.FAIL,)
        contract.request_on(backend, 2)
        query = contract.query(2)
        self.assertEqual(query['phase'], FAILED)
        self.assertEqual(query['last_outcome'], 'failed')
        self.assertFalse(query['effect_persists'])
        self.assertEqual(backend.invocations,
                         [(2, b'one-shot:grant-2', OneShotOutcome.FAIL)])

    def test_pending_holds_after_late_publish(self):
        contract, backend = session()
        backend.script = (OneShotOutcome.LATE,)
        receipt = contract.request_on(backend, 3)
        self.assertIsNone(receipt)
        self.assertEqual(contract.query(3)['phase'], PENDING)
        self.assertEqual(len(backend.invocations), 1)

    def test_second_on_refused_while_pending(self):
        contract, backend = session()
        backend.script = (OneShotOutcome.LATE,)
        contract.request_on(backend, 3)
        with self.assertRaisesRegex(OneShotPendingRefused,
                                    r'record 3 attempt is pending \(held, generation 1\)'):
            contract.request_on(backend, 3)
        self.assertEqual(contract.query(3)['attempt_count'], 1)
        self.assertEqual(len(backend.invocations), 1)

    def test_off_refused_while_pending(self):
        contract, backend = session()
        backend.script = (OneShotOutcome.LATE,)
        contract.request_on(backend, 3)
        with self.assertRaisesRegex(OneShotPendingRefused, 'held'):
            contract.request_off(backend, 3)

    def test_deliver_confirmed_receipt_reaches_executed(self):
        contract, backend = session()
        backend.script = (OneShotOutcome.LATE,)
        contract.request_on(backend, 1)
        contract.deliver_receipt(1, backend.pending_receipt(1))
        self.assertEqual(contract.query(1)['phase'], EXECUTED)
        self.assertTrue(contract.query(1)['effect_persists'])
        self.assertEqual(contract.snapshot()['attempts'],
                         [(1, 1, 'explicit', 'pending'),
                          (1, 1, 'explicit', 'confirmed')])

    def test_deliver_failed_receipt_reaches_failed(self):
        contract, backend = session()
        backend.script = (OneShotOutcome.LATE,)
        contract.request_on(backend, 1)
        contract.deliver_receipt(1, OneShotReceipt(1, False))
        self.assertEqual(contract.query(1)['phase'], FAILED)
        self.assertFalse(contract.query(1)['effect_persists'])

    def test_deliver_receipt_refused_for_terminal_attempt(self):
        contract, backend = session()
        contract.request_on(backend, 1)
        with self.assertRaisesRegex(OneShotReceiptRefused,
                                    r'attempt is executed'):
            contract.deliver_receipt(1, OneShotReceipt(1, True))
        self.assertEqual(contract.query(1)['phase'], EXECUTED)

    def test_deliver_receipt_for_foreign_record_refused(self):
        contract, backend = session()
        with self.assertRaisesRegex(OneShotReceiptRefused,
                                    r'names a foreign record'):
            contract.deliver_receipt(1, OneShotReceipt(2, True))
        self.assertEqual(contract.query(1)['phase'], INACTIVE)

    def test_request_on_refused_before_attach(self):
        contract = make_contract()
        backend = OneShotBackendDouble()
        with self.assertRaisesRegex(OneShotNotAttachedRefused,
                                    r'record 1: no confirmed attach'):
            contract.request_on(backend, 1)
        self.assertEqual(backend.invocations, [])

    def test_re_on_after_executed_is_new_attempt(self):
        contract, backend = session()
        contract.request_on(backend, 1)
        contract.request_on(backend, 1)
        self.assertEqual(contract.query(1)['attempt_count'], 2)
        self.assertEqual(len(backend.invocations), 2)
        self.assertEqual(contract.query(1)['phase'], EXECUTED)

    def test_re_on_after_failed_is_new_attempt(self):
        contract, backend = session()
        backend.script = (OneShotOutcome.FAIL, OneShotOutcome.OK)
        contract.request_on(backend, 1)
        contract.request_on(backend, 1)
        self.assertEqual(contract.query(1)['phase'], EXECUTED)
        self.assertEqual(contract.query(1)['attempt_count'], 2)

    def test_query_and_snapshot_agree(self):
        contract, backend = session()
        contract.request_on(backend, 1)
        contract.save(1)
        query = contract.query(1)
        snap = contract.snapshot()
        self.assertEqual(query['phase'], snap['phases'][1])
        self.assertEqual(query['saved_wish'], 1 in snap['saved_wishes'])
        self.assertEqual(query['attempt_count'], snap['attempt_counts'][1])
        self.assertEqual(query['saved_generation'],
                         snap['saved_generations'][1])

    def test_value_record_on_refused_with_kind_context(self):
        contract, backend = session(records=MIXED_RECORDS)
        with self.assertRaisesRegex(OneShotRecordKindRefused,
                                    r'record 12 is a value record'):
            contract.request_on(backend, 12)
        self.assertEqual(backend.invocations, [])

    def test_value_record_off_is_plain_noop(self):
        contract, backend = session(records=MIXED_RECORDS)
        result = contract.request_off(backend, 12)
        self.assertEqual(result['wish_cleared'], False)
        self.assertEqual(result['backend_operations'], 0)

    def test_invalid_construction_rejected(self):
        with self.assertRaisesRegex(OneShotMarkerError, 'ct_hash'):
            OneShotContract(ONE_SHOT_RECORDS, 'zz' * 32, PROCESS_NAME)
        with self.assertRaises(OneShotContractError):
            OneShotContract([(1, 'script'), (1, 'value')], CT_HASH, PROCESS_NAME)
        with self.assertRaises(OneShotMarkerError):
            OneShotContract(ONE_SHOT_RECORDS, CT_HASH, '')
        with self.assertRaises(OneShotContractError):
            OneShotContract([(1, 'bogus')], CT_HASH, PROCESS_NAME)

class TestSaveContract(unittest.TestCase):
    def test_save_before_any_on_refused(self):
        contract, backend = session()
        with self.assertRaisesRegex(OneShotWishSaveRefused,
                                    r'record 1: one-shot wishes save only after a confirmed ON'):
            contract.save(1)

    def test_save_after_failed_on_refused(self):
        contract, backend = session()
        backend.script = (OneShotOutcome.FAIL,)
        contract.request_on(backend, 1)
        with self.assertRaisesRegex(OneShotWishSaveRefused, 'confirmed ON'):
            contract.save(1)
        self.assertEqual(contract.saved_wish_ids(), ())

    def test_save_after_confirmed_on(self):
        contract, backend = session()
        contract.request_on(backend, 1)
        contract.save(1)
        self.assertEqual(contract.saved_wish_ids(), (1,))
        self.assertEqual(contract.query(1)['saved_wish'], True)
        self.assertEqual(contract.query(1)['saved_generation'], 1)
        self.assertEqual(contract.snapshot()['saved_generations'], {1: 1})

    def test_save_while_pending_refused(self):
        contract, backend = session()
        backend.script = (OneShotOutcome.LATE,)
        contract.request_on(backend, 1)
        with self.assertRaisesRegex(OneShotWishSaveRefused, r'phase PENDING'):
            contract.save(1)

    def test_save_uses_current_attach_generation(self):
        contract = make_contract()
        backend = OneShotBackendDouble()
        contract.attach(1)
        contract.request_on(backend, 1)
        contract.detach()
        contract.attach(5)
        contract.request_on(backend, 2)
        contract.save(2)
        self.assertEqual(contract.query(2)['saved_generation'], 5)

    def test_off_then_re_save_allowed(self):
        contract, backend = session()
        contract.request_on(backend, 1)
        contract.save(1)
        result = contract.request_off(backend, 1)
        self.assertTrue(result['wish_cleared'])
        self.assertEqual(contract.query(1)['phase'], EXECUTED)
        contract.save(1)  # the confirmed ON stands; a fresh wish is saveable
        self.assertEqual(contract.saved_wish_ids(), (1,))

    def test_failed_attempt_after_wish_clear_never_saved(self):
        contract, backend = session()
        contract.request_on(backend, 1)
        contract.save(1)
        contract.request_off(backend, 1)
        backend.arm((OneShotOutcome.FAIL,))
        contract.request_on(backend, 1)
        with self.assertRaisesRegex(OneShotWishSaveRefused, 'confirmed ON'):
            contract.save(1)
        self.assertEqual(contract.saved_wish_ids(), ())

    def test_value_record_cannot_save(self):
        contract, backend = session(records=MIXED_RECORDS)
        with self.assertRaisesRegex(OneShotRecordKindRefused,
                                    r'record 12 is a value record'):
            contract.save(12)


class TestOffContract(unittest.TestCase):
    def test_off_performs_zero_backend_operations(self):
        contract, backend = session()
        contract.request_on(backend, 1)  # exactly one publish
        result = contract.request_off(backend, 1)
        self.assertEqual(backend.invocations,
                         [(1, b'one-shot:grant-1', OneShotOutcome.OK)])
        self.assertEqual(result['backend_operations'], 0)

    def test_off_clears_saved_wish(self):
        contract, backend = session()
        contract.request_on(backend, 1)
        contract.save(1)
        result = contract.request_off(backend, 1)
        self.assertTrue(result['wish_cleared'])
        self.assertEqual(contract.saved_wish_ids(), ())
        self.assertIsNone(contract.query(1)['saved_generation'])

    def test_off_keeps_effect_persists_visible(self):
        contract, backend = session()
        contract.request_on(backend, 1)
        result = contract.request_off(backend, 1)
        self.assertIs(result['effect_persists'], True)
        self.assertTrue(contract.query(1)['effect_persists'])
        self.assertEqual(contract.snapshot()['effect_persists'], [1])

    def test_off_without_any_on_is_not_error(self):
        contract, backend = session()
        result = contract.request_off(backend, 4)
        self.assertEqual(result, {'record_id': 4, 'wish_cleared': False,
                                  'effect_persists': False,
                                  'backend_operations': 0})
        self.assertEqual(backend.invocations, [])

    def test_second_off_is_noop_not_error(self):
        contract, backend = session()
        contract.request_on(backend, 1)
        contract.save(1)
        first = contract.request_off(backend, 1)
        second = contract.request_off(backend, 1)
        self.assertTrue(first['wish_cleared'])
        self.assertFalse(second['wish_cleared'])
        self.assertTrue(second['effect_persists'])

    def test_off_does_not_change_phase(self):
        contract, backend = session()
        contract.request_on(backend, 1)
        contract.request_off(backend, 1)
        self.assertEqual(contract.query(1)['phase'], EXECUTED)
        self.assertEqual(contract.query(1)['last_outcome'], 'confirmed')

    def test_off_drops_wish_from_next_replay(self):
        contract, backend = session()
        contract.request_on(backend, 1)
        contract.save(1)
        contract.request_off(backend, 1)
        contract.detach()
        contract.attach(2)
        attempted, skipped = contract.replay_saved_wishes(backend)
        self.assertEqual((attempted, skipped), ((), ()))
        self.assertEqual(backend.invocations,
                         [(1, b'one-shot:grant-1', OneShotOutcome.OK)])

    def test_off_while_detached_clears_wish(self):
        contract, backend = session()
        contract.request_on(backend, 1)
        contract.save(1)
        contract.detach()
        result = contract.request_off(backend, 1)
        self.assertTrue(result['wish_cleared'])
        self.assertFalse(result['effect_persists'])
        self.assertEqual(contract.saved_wish_ids(), ())
        self.assertEqual(backend.invocations,
                         [(1, b'one-shot:grant-1', OneShotOutcome.OK)])

    def test_off_refused_for_unknown_record(self):
        contract, backend = session()
        with self.assertRaisesRegex(OneShotUnknownRecordError, 'record 77'):
            contract.request_off(backend, 77)

class TestAttachReplay(unittest.TestCase):
    def _saved(self, contract, backend, record_ids=(1,)):
        for record_id in record_ids:
            contract.request_on(backend, record_id)
            contract.save(record_id)

    def test_attach_starts_generation_and_lists_wishes(self):
        contract, backend = session()
        self._saved(contract, backend)
        contract.detach()
        self.assertEqual(contract.attach(2), (1,))
        self.assertEqual(contract.snapshot()['generation'], 2)

    def test_attach_refused_when_attached(self):
        contract, _backend = session()
        with self.assertRaisesRegex(OneShotGenerationConflict,
                                    r'already attached at generation 1'):
            contract.attach(2)

    def test_attach_refused_non_increasing_generation(self):
        contract, backend = session()
        contract.detach()
        with self.assertRaisesRegex(OneShotGenerationConflict,
                                    r'attach generation 1 must exceed the previous generation 1'):
            contract.attach(1)

    def test_attach_refused_invalid_generation(self):
        contract, _backend = session()
        contract.detach()
        with self.assertRaises(OneShotGenerationConflict):
            contract.attach(0)
        with self.assertRaises(OneShotGenerationConflict):
            contract.attach(True)

    def test_replay_runs_saved_wish_exactly_once(self):
        contract, backend = session()
        self._saved(contract, backend)
        contract.detach()
        contract.attach(2)
        attempted, skipped = contract.replay_saved_wishes(backend)
        self.assertEqual(attempted, (1,))
        self.assertEqual(skipped, ())
        self.assertEqual(len(backend.invocations), 2)  # original ON + one replay publish
        self.assertEqual(contract.query(1)['phase'], EXECUTED)
        self.assertEqual(contract.query(1)['attempt_count'], 2)
        self.assertEqual(contract.saved_wish_ids(), (1,))  # wish remains after replay

    def test_replay_double_execution_guard_same_generation(self):
        contract, backend = session()
        self._saved(contract, backend)
        contract.detach()
        contract.attach(2)
        contract.replay_saved_wishes(backend)
        attempted, skipped = contract.replay_saved_wishes(backend)
        self.assertEqual(attempted, ())
        self.assertEqual(skipped, ((1, 'already-executed'),))
        self.assertEqual(len(backend.invocations), 2)

    def test_replay_failure_never_replayed_in_later_generation(self):
        contract, backend = session()
        self._saved(contract, backend)
        contract.detach()
        contract.attach(2)
        backend.arm((OneShotOutcome.FAIL,))
        attempted, skipped = contract.replay_saved_wishes(backend)
        self.assertEqual(attempted, (1,))
        self.assertEqual(contract.query(1)['phase'], FAILED)
        self.assertEqual(contract.query(1)['last_outcome'], 'failed')
        attempted, skipped = contract.replay_saved_wishes(backend)
        self.assertEqual((attempted, skipped), ((), ((1, 'failed-or-unknown'),)))
        contract.detach()
        contract.attach(3)
        attempted, skipped = contract.replay_saved_wishes(backend)
        self.assertEqual((attempted, skipped), ((), ((1, 'failed-or-unknown'),)))
        self.assertEqual(contract.saved_wish_ids(), (1,))  # wish is preserved, not replayed
        self.assertEqual(len(backend.invocations), 2)  # original ON + one failed replay

    def test_replay_success_wish_retained_and_replays_next_generation(self):
        contract, backend = session()
        self._saved(contract, backend)
        contract.detach()
        contract.attach(2)
        attempted, skipped = contract.replay_saved_wishes(backend)
        self.assertEqual((attempted, skipped), ((1,), ()))
        self.assertEqual(contract.query(1)['saved_generation'], 1)  # original save generation kept
        contract.detach()
        contract.attach(3)
        attempted, skipped = contract.replay_saved_wishes(backend)
        self.assertEqual((attempted, skipped), ((1,), ()))
        self.assertEqual(contract.query(1)['attempt_count'], 3)

    def test_replay_not_attached_skips_all(self):
        contract, backend = session()
        self._saved(contract, backend)
        contract.detach()
        attempted, skipped = contract.replay_saved_wishes(backend)
        self.assertEqual(attempted, ())
        self.assertEqual(skipped, ((1, 'not-attached'),))
        self.assertEqual(len(backend.invocations), 1)

    def test_replay_skips_held_record(self):
        contract, backend = session()
        self._saved(contract, backend)
        contract.detach()
        contract.attach(2)
        backend.arm((OneShotOutcome.LATE,))
        attempted, skipped = contract.replay_saved_wishes(backend)
        self.assertEqual(attempted, (1,))
        self.assertEqual(contract.query(1)['phase'], PENDING)
        attempted, skipped = contract.replay_saved_wishes(backend)
        self.assertEqual(attempted, ())
        self.assertEqual(skipped, ((1, 'held'),))
        contract.deliver_receipt(1, backend.pending_receipt(1))
        self.assertEqual(contract.query(1)['phase'], EXECUTED)

    def test_replay_skips_already_executed_this_generation(self):
        contract, backend = session()
        self._saved(contract, backend)
        contract.detach()
        contract.attach(2)
        contract.request_on(backend, 1)  # explicit ON in this generation first
        attempted, skipped = contract.replay_saved_wishes(backend)
        self.assertEqual(attempted, ())
        self.assertEqual(skipped, ((1, 'already-executed'),))
        self.assertEqual(len(backend.invocations), 2)

    def test_replay_results_are_sorted(self):
        contract, backend = session()
        self._saved(contract, backend, record_ids=(3, 1, 4, 2))
        contract.detach()
        contract.attach(2)
        attempted, skipped = contract.replay_saved_wishes(backend)
        self.assertEqual(attempted, (1, 2, 3, 4))
        self.assertEqual(skipped, ())

    def test_detach_drains_pending_attempt_to_failed(self):
        contract, backend = session()
        backend.script = (OneShotOutcome.LATE,)
        contract.request_on(backend, 1)
        contract.detach()
        self.assertEqual(contract.query(1)['phase'], INACTIVE)
        self.assertEqual(contract.query(1)['last_outcome'], 'failed')
        self.assertEqual(contract.snapshot()['attempts'],
                         [(1, 1, 'explicit', 'pending'), (1, 1, 'drain', 'lost')])
        contract.attach(2)
        # No saved wish exists, so there is nothing to replay or skip.
        attempted, skipped = contract.replay_saved_wishes(backend)
        self.assertEqual((attempted, skipped), ((), ()))

    def test_drained_failed_attempt_blocks_replay_of_saved_wish(self):
        contract, backend = session()
        contract.request_on(backend, 1)
        contract.save(1)
        backend.arm((OneShotOutcome.LATE,))
        contract.request_on(backend, 1)  # explicit re-ON held at detach
        contract.detach()
        contract.attach(2)
        attempted, skipped = contract.replay_saved_wishes(backend)
        self.assertEqual((attempted, skipped), ((), ((1, 'failed-or-unknown'),)))

    def test_detach_is_idempotent(self):
        contract, _backend = session()
        contract.detach()
        contract.detach()
        self.assertFalse(contract.snapshot()['attached'])

    def test_explicit_on_after_failed_replay_restores_replay(self):
        contract, backend = session()
        self._saved(contract, backend)
        contract.detach()
        contract.attach(2)
        backend.arm((OneShotOutcome.FAIL,))
        contract.replay_saved_wishes(backend)
        self.assertEqual(contract.query(1)['last_outcome'], 'failed')
        backend.arm(())
        contract.request_on(backend, 1)  # new explicit ON action, confirmed
        self.assertEqual(contract.query(1)['last_outcome'], 'confirmed')
        contract.detach()
        contract.attach(3)
        attempted, skipped = contract.replay_saved_wishes(backend)
        self.assertEqual((attempted, skipped), ((1,), ()))

def save_wishes(contract, backend, record_ids=(1,)):
    for record_id in record_ids:
        contract.request_on(backend, record_id)
        contract.save(record_id)


class TestManualRerun(unittest.TestCase):
    def test_explicit_on_logged_as_explicit_not_replay(self):
        contract, backend = session()
        contract.request_on(backend, 1)
        self.assertEqual(contract.snapshot()['attempts'],
                         [(1, 1, 'explicit', 'confirmed')])

    def test_replay_logged_as_replay(self):
        contract, backend = session()
        save_wishes(contract, backend)
        contract.detach()
        contract.attach(2)
        contract.replay_saved_wishes(backend)
        self.assertEqual(contract.snapshot()['attempts'],
                         [(1, 1, 'explicit', 'confirmed'),
                          (1, 2, 'replay', 'confirmed')])

    def test_manual_rerun_after_replay_is_a_new_action(self):
        contract, backend = session()
        save_wishes(contract, backend)
        contract.detach()
        contract.attach(2)
        contract.replay_saved_wishes(backend)
        contract.request_on(backend, 1)  # allowed manual re-run, not a restore
        self.assertEqual(contract.query(1)['attempt_count'], 3)
        self.assertEqual(contract.query(1)['phase'], EXECUTED)
        self.assertEqual(len(backend.invocations), 3)


class TestParentChildIndependence(unittest.TestCase):
    def test_on_of_parent_does_not_run_children(self):
        contract, backend = session(records=PARENT_CHILD_RECORDS)
        contract.request_on(backend, 20)
        self.assertEqual(backend.invocations,
                         [(20, b'one-shot:tree-20', OneShotOutcome.OK)])
        self.assertEqual(contract.query(21)['phase'], INACTIVE)
        self.assertEqual(contract.query(22)['phase'], INACTIVE)

    def test_child_wish_replays_without_parent_involvement(self):
        contract, backend = session(records=PARENT_CHILD_RECORDS)
        contract.request_on(backend, 22)
        contract.save(22)
        contract.detach()
        contract.attach(2)
        attempted, skipped = contract.replay_saved_wishes(backend)
        self.assertEqual(attempted, (22,))
        self.assertEqual(skipped, ())
        self.assertEqual([call[0] for call in backend.invocations], [22, 22])


class TestFreezeOrthogonality(unittest.TestCase):
    def test_value_records_excluded_from_markers(self):
        contract, backend = session(records=MIXED_RECORDS)
        contract.request_on(backend, 10)
        contract.save(10)
        contract.request_on(backend, 11)
        contract.detach()
        decoded = contract.decode_markers(contract.encode_markers())
        # script records carry attempt history; value records (12, 13) never
        self.assertEqual(decoded, {10: (EXECUTED, 1, 1),
                                   11: (EXECUTED, 1, NOT_SAVED)})

    def test_no_freeze_state_in_model(self):
        contract, _backend = session(records=MIXED_RECORDS)
        snap = contract.snapshot()
        keys = ' '.join(snap).casefold()
        for term in ('frozen', 'freeze'):
            self.assertNotIn(term, keys)
        self.assertEqual(contract.query(12)['kind'], 'value')

    def test_value_records_rejected_in_marker_restore(self):
        contract = make_contract(MIXED_RECORDS)  # detached: restore requires no attach
        raw = encode_markers([(12, EXECUTED, 1, 1)], CT_HASH, PROCESS_NAME)
        with self.assertRaisesRegex(OneShotMarkerError,
                                    r'record 12 is not part of this contract'):
            contract.restore_markers(raw)


class TestBackendDouble(unittest.TestCase):
    def test_script_consumption_and_default_ok(self):
        backend = OneShotBackendDouble((OneShotOutcome.FAIL,))
        self.assertEqual(backend.publish(1, b'p'), OneShotReceipt(1, False))
        self.assertEqual(backend.publish(2, b'p'), OneShotReceipt(2, True))
        self.assertEqual(backend.invocations,
                         [(1, b'p', OneShotOutcome.FAIL),
                          (2, b'p', OneShotOutcome.OK)])

    def test_late_receipt_is_pending(self):
        backend = OneShotBackendDouble((OneShotOutcome.LATE,))
        self.assertIsNone(backend.publish(5, b'p'))
        self.assertEqual(backend.pending_receipt(5), OneShotReceipt(5, True))
        self.assertEqual(backend.pending, {})

    def test_flaky_script_fails_then_confirms(self):
        contract = make_contract()
        contract.attach(1)
        backend = OneShotBackendDouble(FLAKY)
        contract.request_on(backend, 1)
        self.assertEqual(contract.query(1)['phase'], FAILED)
        contract.request_on(backend, 1)
        self.assertEqual(contract.query(1)['phase'], EXECUTED)
        self.assertEqual(contract.query(1)['attempt_count'], 2)


class TestMarkerCodec(unittest.TestCase):
    def _markers(self):
        return [(2, EXECUTED, 3, 2), (1, FAILED, 1, NOT_SAVED), (10, INACTIVE, 2, 4)]

    def test_roundtrip_lossless(self):
        raw = encode_markers(self._markers(), CT_HASH, PROCESS_NAME)
        self.assertEqual(decode_markers(raw, CT_HASH, PROCESS_NAME),
                         {1: (FAILED, 1, NOT_SAVED),
                          2: (EXECUTED, 3, 2),
                          10: (INACTIVE, 2, 4)})

    def test_encoding_is_sorted_by_record_id(self):
        raw = encode_markers([(7, EXECUTED, 1, 1), (2, FAILED, 2, NOT_SAVED)],
                             CT_HASH, PROCESS_NAME)
        decoded = decode_markers(raw, CT_HASH, PROCESS_NAME)
        self.assertEqual(list(decoded), [2, 7])
        self.assertEqual(struct.unpack_from('<I', raw, marker_region(raw, 0))[0], 2)
        self.assertEqual(struct.unpack_from('<I', raw, marker_region(raw, 1))[0], 7)

    def test_byte_identical_reruns(self):
        first = encode_markers(self._markers(), CT_HASH, PROCESS_NAME)
        second = encode_markers(list(reversed(self._markers())), CT_HASH, PROCESS_NAME)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 4 + 8 + 32 + 4 + len(PROCESS_NAME) + 4 + 3 * 13 + 4)

    def test_crc_error_rejected(self):
        raw = encode_markers([(1, EXECUTED, 1, 1)], CT_HASH, PROCESS_NAME)
        damaged = bytearray(raw)
        damaged[marker_region(raw, 0) + 1] ^= 0x01
        with self.assertRaisesRegex(OneShotMarkerError, 'crc32 mismatch'):
            decode_markers(bytes(damaged), CT_HASH, PROCESS_NAME)

    def test_truncated_blob_rejected(self):
        raw = encode_markers([(1, EXECUTED, 1, 1)], CT_HASH, PROCESS_NAME)
        with self.assertRaises(OneShotMarkerError):
            decode_markers(raw[:-1], CT_HASH, PROCESS_NAME)
        with self.assertRaises(OneShotMarkerError):
            decode_markers(raw[:10], CT_HASH, PROCESS_NAME)

    def test_trailing_garbage_rejected(self):
        raw = encode_markers([], CT_HASH, PROCESS_NAME)
        with self.assertRaises(OneShotMarkerError):
            decode_markers(raw + b'X', CT_HASH, PROCESS_NAME)

    def test_total_length_mismatch_rejected(self):
        raw = encode_markers([(1, EXECUTED, 1, 1)], CT_HASH, PROCESS_NAME)
        patched = raw[:4] + struct.pack('<I', 100) + raw[4:]
        with self.assertRaisesRegex(OneShotMarkerError, 'total length prefix'):
            decode_markers(patched, CT_HASH, PROCESS_NAME)

    def test_wrong_magic_rejected(self):
        raw = encode_markers([], CT_HASH, PROCESS_NAME)
        patched = raw[:4] + b'XXXXXXXX' + raw[12:]
        with self.assertRaisesRegex(OneShotMarkerError, 'magic'):
            decode_markers(patched, CT_HASH, PROCESS_NAME)

    def test_foreign_ct_hash_rejected(self):
        raw = encode_markers([(1, EXECUTED, 1, 1)], CT_HASH, PROCESS_NAME)
        with self.assertRaisesRegex(OneShotMarkerError, 'ct_hash binding mismatch'):
            decode_markers(raw, 'cd' * 32, PROCESS_NAME)

    def test_foreign_process_name_rejected(self):
        raw = encode_markers([(1, EXECUTED, 1, 1)], CT_HASH, PROCESS_NAME)
        with self.assertRaisesRegex(OneShotMarkerError, 'process_name binding mismatch'):
            decode_markers(raw, CT_HASH, 'other.exe')

    def test_empty_marker_list_valid(self):
        raw = encode_markers([], CT_HASH, PROCESS_NAME)
        self.assertEqual(decode_markers(raw, CT_HASH, PROCESS_NAME), {})

    def test_duplicate_record_id_rejected(self):
        with self.assertRaisesRegex(OneShotMarkerError, 'duplicate marker'):
            encode_markers([(1, EXECUTED, 1, 1), (1, FAILED, 2, NOT_SAVED)],
                           CT_HASH, PROCESS_NAME)

    def test_unsorted_record_ids_rejected_on_decode(self):
        raw = bytearray(encode_markers([(2, EXECUTED, 1, 1),
                                        (1, FAILED, 2, NOT_SAVED)],
                                       CT_HASH, PROCESS_NAME))
        start = marker_region(raw, 0)
        raw[start:start + 26] = raw[start + 13:start + 26] + raw[start:start + 13]
        body = bytes(raw[4:start + 26])
        raw[start + 26:start + 30] = struct.pack('<I', zlib.crc32(body) & 0xFFFFFFFF)
        with self.assertRaisesRegex(OneShotMarkerError, 'not sorted by record ID'):
            decode_markers(bytes(raw), CT_HASH, PROCESS_NAME)

    def test_unknown_record_id_rejected_against_contract(self):
        raw = encode_markers([(99, EXECUTED, 1, 1)], CT_HASH, PROCESS_NAME)
        with self.assertRaisesRegex(OneShotMarkerError,
                                    r'record 99 is not part of this contract'):
            decode_markers(raw, CT_HASH, PROCESS_NAME, known_records={1, 2, 3, 4})

    def test_invalid_phase_byte_rejected(self):
        raw = bytearray(encode_markers([(1, EXECUTED, 1, 1)], CT_HASH, PROCESS_NAME))
        raw[marker_region(raw, 0) + 4] = 7
        body = bytes(raw[4:marker_region(raw, 0) + 13])
        raw[marker_region(raw, 0) + 13:marker_region(raw, 0) + 17] = \
            struct.pack('<I', zlib.crc32(body) & 0xFFFFFFFF)
        with self.assertRaisesRegex(OneShotMarkerError, 'unknown phase byte 7'):
            decode_markers(bytes(raw), CT_HASH, PROCESS_NAME)

    def test_marker_count_mismatch_rejected(self):
        raw = bytearray(encode_markers([(1, EXECUTED, 1, 1)], CT_HASH, PROCESS_NAME))
        name_end = 48 + len(PROCESS_NAME)
        raw[name_end:name_end + 4] = struct.pack('<I', 2)
        with self.assertRaisesRegex(OneShotMarkerError, 'marker count does not match'):
            decode_markers(bytes(raw), CT_HASH, PROCESS_NAME)

    def test_encoding_rejects_pending_phase(self):
        with self.assertRaisesRegex(OneShotMarkerError, 'not persistable'):
            encode_markers([(1, PENDING, 1, NOT_SAVED)], CT_HASH, PROCESS_NAME)

    def test_encoding_rejects_bad_saved_generation(self):
        with self.assertRaisesRegex(OneShotMarkerError, 'saved_generation'):
            encode_markers([(1, EXECUTED, 1, 0)], CT_HASH, PROCESS_NAME)


class TestContractMarkerWiring(unittest.TestCase):
    def test_contract_encode_decode_roundtrip(self):
        contract, backend = session()
        save_wishes(contract, backend)
        backend.arm((OneShotOutcome.FAIL,))
        contract.request_on(backend, 3)
        contract.detach()
        raw = contract.encode_markers()
        self.assertEqual(decode_markers(raw, CT_HASH, PROCESS_NAME),
                         {1: (EXECUTED, 1, 1), 3: (FAILED, 1, NOT_SAVED)})
        fresh = make_contract()
        fresh.restore_markers(raw)
        self.assertEqual(fresh.query(1)['last_outcome'], 'confirmed')
        self.assertEqual(fresh.query(3)['last_outcome'], 'failed')
        self.assertEqual(fresh.query(1)['attempt_count'], 1)
        self.assertEqual(fresh.saved_wish_ids(), (1,))

    def test_restored_failed_attempt_is_never_replayed(self):
        contract, backend = session()
        save_wishes(contract, backend)
        contract.detach()
        raw = contract.encode_markers()
        fresh = make_contract()
        fresh.restore_markers(raw)
        fresh.attach(2)
        backend2 = OneShotBackendDouble((OneShotOutcome.FAIL,))
        attempted, skipped = fresh.replay_saved_wishes(backend2)
        self.assertEqual(attempted, (1,))
        self.assertEqual(fresh.query(1)['last_outcome'], 'failed')
        attempted, skipped = fresh.replay_saved_wishes(backend2)
        self.assertEqual(skipped, ((1, 'failed-or-unknown'),))

    def test_restore_refused_while_attached(self):
        contract, _backend = session()
        raw = encode_markers([], CT_HASH, PROCESS_NAME)
        with self.assertRaisesRegex(OneShotContractError, 'detached'):
            contract.restore_markers(raw)

    def test_encoding_refused_while_attempt_pending(self):
        contract, backend = session()
        backend.script = (OneShotOutcome.LATE,)
        contract.request_on(backend, 1)
        with self.assertRaisesRegex(OneShotContractError, 'pending'):
            contract.encode_markers()


if __name__ == '__main__':
    unittest.main()
