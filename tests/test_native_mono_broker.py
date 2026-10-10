"""State-machine tests for the typed Mono broker model (AP-04 stage 1).

The broker is a pure Python model of the broker contract that the own C
adapter (``mono_api.c`` / ``mono_collector.c``, 42 typed exports) must
satisfy. No processes, no ctypes, no managed execution: identity binding,
domain generation, one-shot CAS tokens, cancellation rules, unknown-effect
semantics, GC handle lifetime, thread balance, JitInfo extent and contract
classes are all checked against the model only.
"""

import json
import unittest
from pathlib import Path

from ct2trainer.native.mono_broker import (
    ARG_BYREF,
    ARG_GENERIC,
    ARG_INSTANCE_REF,
    ARG_STATIC_BYTES,
    ARG_STRING,
    ARG_VARARG,
    CONTRACT_GETTER,
    CONTRACT_IRREVERSIBLE,
    CONTRACT_REVERSIBLE,
    DomainBinding,
    ExportPin,
    InvocationSpec,
    MAX_ARGUMENTS,
    MAX_LOG_ENTRIES,
    MAX_SESSIONS,
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

ROOT = Path(__file__).resolve().parents[1]

SHA = 'a' * 64
EXPORTS = (
    ExportPin('mono_get_root_domain', 'tf_get_root_domain'),
    ExportPin('mono_runtime_invoke', 'tf_runtime_invoke'),
)
PID = 4242
CREATION_TIME = 123456


class FakeClock:
    def __init__(self, value=1000):
        self.value = value

    def __call__(self):
        return self.value

    def advance(self, ticks):
        self.value += ticks


def make_identity(**overrides):
    base = dict(module_sha256=SHA, exports=EXPORTS, pid=PID,
                creation_time=CREATION_TIME, bitness=64)
    base.update(overrides)
    return MonoBrokerIdentity(**base)


def make_broker(clock=None, **identity_overrides):
    clock = clock if clock is not None else FakeClock()
    domain = DomainBinding(domain_ptr=0x1000, domain_id=0, generation=1)
    broker = MonoBroker(make_identity(**identity_overrides), domain,
                        now_qpc=clock)
    return broker, clock


def make_spec(**overrides):
    base = dict(method_token=0x60010001, is_instance=False,
                argument_kinds=(ARG_STATIC_BYTES,), contract=CONTRACT_GETTER)
    base.update(overrides)
    return InvocationSpec(**base)


def prepare(broker, spec_kwargs=None, **kwargs):
    spec = make_spec(**(spec_kwargs or {}))
    keyword = dict(token=1, deadline_qpc=10_000,
                   signature=(spec.is_instance, len(spec.argument_kinds)))
    keyword.update(kwargs)
    return broker.prepare(spec, **keyword)


class MonoBrokerIdentityTests(unittest.TestCase):
    def test_identity_valid_bitness_and_bounds(self):
        for bitness in (32, 64):
            identity = make_identity(bitness=bitness)
            self.assertEqual(identity.bitness, bitness)

    def test_identity_rejects_bad_bitness(self):
        with self.assertRaises(MonoBrokerError):
            make_identity(bitness=33)

    def test_identity_rejects_bad_sha(self):
        for sha in ('x' * 63, 'A' * 64, 'g' * 64):
            with self.subTest(sha=sha[:3]):
                with self.assertRaises(MonoBrokerError):
                    make_identity(module_sha256=sha)

    def test_identity_rejects_empty_or_bad_export_table(self):
        with self.assertRaises(MonoBrokerError):
            make_identity(exports=())
        with self.assertRaises(MonoBrokerError):
            make_identity(exports=(ExportPin('', 'tf_empty'),))
        with self.assertRaises(MonoBrokerError):
            make_identity(exports=(ExportPin('mono_free', 'no_prefix'),))
        with self.assertRaises(MonoBrokerError):
            make_identity(exports=(ExportPin('mono_free', 'tf_free'),
                                   ExportPin('mono_free', 'tf_free2')))

    def test_identity_rejects_out_of_range_pid_and_time(self):
        with self.assertRaises(MonoBrokerError):
            make_identity(pid=0)
        with self.assertRaises(MonoBrokerError):
            make_identity(pid=2 ** 32)
        with self.assertRaises(MonoBrokerError):
            make_identity(creation_time=2 ** 64)

    def test_pinned_api_prototypes_table_accepted(self):
        raw = json.loads(
            (ROOT / 'dependencies/native/mono-api-source/api-prototypes.json')
            .read_text(encoding='utf-8'))
        self.assertEqual(raw['schema'], 'ct2trainer-mono-api-prototypes/v1')
        exports = tuple(ExportPin(e['export'], e['field'])
                        for e in raw['required_exports'])
        self.assertEqual(len(exports), 42)
        broker, _ = make_broker(exports=exports)
        snapshot = broker.snapshot()
        self.assertEqual(snapshot['identity']['export_count'], 42)


class MonoBrokerDomainTests(unittest.TestCase):
    def test_root_domain_id_zero_is_valid(self):
        domain = DomainBinding(domain_ptr=0x2000, domain_id=0, generation=1)
        broker = MonoBroker(make_identity(), domain, now_qpc=FakeClock())
        broker.bind_domain(domain_ptr=0x2000, domain_id=0, generation=1)
        self.assertEqual(broker.snapshot()['domain']['domain_id'], 0)

    def test_stale_domain_generation_refused(self):
        broker, _ = make_broker()
        with self.assertRaises(StaleDomainRefused):
            broker.bind_domain(domain_ptr=0x1000, domain_id=0, generation=2)

    def test_stale_domain_pointer_refused(self):
        broker, _ = make_broker()
        with self.assertRaises(StaleDomainRefused):
            broker.bind_domain(domain_ptr=0x9999, domain_id=0, generation=1)

    def test_stale_domain_id_refused(self):
        broker, _ = make_broker()
        with self.assertRaises(StaleDomainRefused):
            broker.bind_domain(domain_ptr=0x1000, domain_id=7, generation=1)

    def test_domain_unload_refuses_gc_and_threads(self):
        broker, _ = make_broker()
        broker.mark_domain_unloaded()
        with self.assertRaises(GCHandleRefused):
            broker.gc_acquire(5)
        with self.assertRaises(ThreadBalanceRefused):
            broker.thread_attach()
        snapshot = broker.snapshot()
        self.assertTrue(snapshot['domain']['unloaded'])


class MonoBrokerSignatureTests(unittest.TestCase):
    def test_byref_vararg_generic_refused_without_capability(self):
        for kind in (ARG_BYREF, ARG_VARARG, ARG_GENERIC):
            with self.subTest(kind=kind):
                broker, _ = make_broker()
                with self.assertRaises(UnsupportedSignatureRefused):
                    prepare(broker,
                            spec_kwargs=dict(argument_kinds=(kind,),
                                             contract=CONTRACT_REVERSIBLE))

    def test_capability_token_allows_byref(self):
        broker, _ = make_broker()
        session = prepare(broker,
                          spec_kwargs=dict(argument_kinds=(ARG_BYREF,),
                                           contract=CONTRACT_REVERSIBLE),
                          capabilities=frozenset({ARG_BYREF}))
        self.assertIsNotNone(session)

    def test_getter_forbids_mutable_kinds_even_with_capability(self):
        broker, _ = make_broker()
        with self.assertRaises(UnsupportedSignatureRefused):
            prepare(broker,
                    spec_kwargs=dict(argument_kinds=(ARG_BYREF,),
                                     contract=CONTRACT_GETTER),
                    capabilities=frozenset({ARG_BYREF}))

    def test_static_vs_instance_mismatch_refused(self):
        broker, _ = make_broker()
        with self.assertRaises(UnsupportedSignatureRefused):
            prepare(broker, spec_kwargs=dict(is_instance=True),
                    signature=(False, 1))
        with self.assertRaises(UnsupportedSignatureRefused):
            prepare(broker, spec_kwargs=dict(is_instance=False),
                    signature=(True, 1))

    def test_argument_count_mismatch_refused(self):
        broker, _ = make_broker()
        with self.assertRaises(UnsupportedSignatureRefused):
            prepare(broker,
                    spec_kwargs=dict(argument_kinds=(ARG_STATIC_BYTES,
                                                    ARG_STATIC_BYTES)),
                    signature=(False, 1))

    def test_unknown_argument_kind_rejected_at_spec(self):
        with self.assertRaises(MonoBrokerError):
            make_spec(argument_kinds=('opaque',))

    def test_max_arguments_bound(self):
        with self.assertRaises(MonoBrokerError):
            make_spec(argument_kinds=(ARG_STATIC_BYTES,) * (MAX_ARGUMENTS + 1))
        broker, _ = make_broker()
        session = prepare(
            broker,
            spec_kwargs=dict(
                argument_kinds=(ARG_STATIC_BYTES,) * MAX_ARGUMENTS),
            signature=(False, MAX_ARGUMENTS))
        self.assertIsNotNone(session)


class MonoBrokerSessionTests(unittest.TestCase):
    def test_happy_path_getter(self):
        broker, _ = make_broker()
        session = prepare(broker)
        broker.dispatch(session)
        broker.start(session)
        broker.ack(session, ok=True)
        snapshot = broker.snapshot()
        state = snapshot['sessions'][0]
        self.assertEqual(state['state'], 'ack_success')
        self.assertEqual(snapshot['counts']['terminal'], 1)
        self.assertEqual(snapshot['unknown_method_tokens'], [])

    def test_cancel_prepared_is_safe(self):
        broker, _ = make_broker()
        session = prepare(broker)
        broker.cancel(session)
        self.assertEqual(broker.snapshot()['sessions'][0]['state'], 'cancelled')

    def test_cancel_dispatched_refused(self):
        broker, _ = make_broker()
        session = prepare(broker)
        broker.dispatch(session)
        with self.assertRaises(RunningNotCancelable):
            broker.cancel(session)

    def test_cancel_running_refused(self):
        broker, _ = make_broker()
        session = prepare(broker)
        broker.dispatch(session)
        broker.start(session)
        with self.assertRaises(RunningNotCancelable):
            broker.cancel(session)

    def test_cancel_terminal_refused(self):
        broker, _ = make_broker()
        session = prepare(broker)
        broker.cancel(session)
        with self.assertRaises(InvalidTransitionError):
            broker.cancel(session)

    def test_ack_failure_terminal(self):
        broker, _ = make_broker()
        session = prepare(broker)
        broker.dispatch(session)
        broker.start(session)
        broker.ack(session, ok=False, exception='NullReferenceException')
        state = broker.snapshot()['sessions'][0]
        self.assertEqual(state['state'], 'ack_failure')
        self.assertFalse(state['unknown_effect'])
        self.assertNotIn(state['method_token'],
                         broker.snapshot()['unknown_method_tokens'])

    def test_ack_lost_is_unknown_terminal(self):
        broker, _ = make_broker()
        session = prepare(broker, spec_kwargs=dict(method_token=0x60010009))
        broker.dispatch(session)
        broker.ack_lost(session)
        snapshot = broker.snapshot()
        self.assertEqual(snapshot['sessions'][0]['state'], 'ack_lost')
        self.assertEqual(snapshot['sessions'][0]['unknown_effect'], True)
        self.assertEqual(snapshot['unknown_method_tokens'], [0x60010009])

    def test_unknown_effect_never_retried(self):
        broker, _ = make_broker()
        session = prepare(broker, spec_kwargs=dict(method_token=0x6001000A),
                          token=1)
        broker.dispatch(session)
        broker.start(session)
        broker.ack(session, ok=False, exception='AccessViolation',
                   effect_observed=True)
        self.assertEqual(broker.snapshot()['sessions'][0]['state'], 'unknown')
        # A fresh CAS token does not help: the method token is tainted.
        with self.assertRaises(UnknownRetryRefused):
            prepare(broker, spec_kwargs=dict(method_token=0x6001000A),
                    token=2)

    def test_late_completion_log_only_on_terminal(self):
        broker, _ = make_broker()
        session = prepare(broker)
        broker.dispatch(session)
        broker.start(session)
        broker.ack(session, ok=True)
        broker.late_completion(session, receipt='late-ack')
        snapshot = broker.snapshot()
        self.assertEqual(snapshot['sessions'][0]['state'], 'ack_success')
        self.assertTrue(any('late completion' in entry
                            for entry in snapshot['sessions'][0]['log']))

    def test_late_completion_refused_on_live_session(self):
        broker, _ = make_broker()
        session = prepare(broker)
        with self.assertRaises(InvalidTransitionError):
            broker.late_completion(session, receipt='too-early')

    def test_late_completion_log_bounded(self):
        broker, _ = make_broker()
        session = prepare(broker)
        broker.cancel(session)
        for _ in range(MAX_LOG_ENTRIES + 30):
            broker.late_completion(session, receipt='x')
        self.assertEqual(len(broker.snapshot()['sessions'][0]['log']),
                         MAX_LOG_ENTRIES)

    def test_ack_requires_running(self):
        broker, _ = make_broker()
        session = prepare(broker)
        with self.assertRaises(InvalidTransitionError):
            broker.ack(session, ok=True)

    def test_dispatch_requires_prepared(self):
        broker, _ = make_broker()
        session = prepare(broker)
        broker.dispatch(session)
        with self.assertRaises(InvalidTransitionError):
            broker.dispatch(session)

    def test_unknown_session_refused(self):
        broker, _ = make_broker()
        with self.assertRaises(InvalidTransitionError):
            broker.dispatch(99)

    def test_token_replay_refused(self):
        broker, _ = make_broker()
        prepare(broker, token=7)
        with self.assertRaises(TokenReplayRefused):
            prepare(broker, token=7)

    def test_irreversible_one_shot_token(self):
        broker, _ = make_broker()
        session = prepare(broker, spec_kwargs=dict(contract=CONTRACT_IRREVERSIBLE),
                          token=1)
        # The same method token is already burned even while live.
        with self.assertRaises(TokenReplayRefused):
            prepare(broker, spec_kwargs=dict(contract=CONTRACT_IRREVERSIBLE),
                    token=2)
        broker.dispatch(session)
        broker.start(session)
        broker.ack(session, ok=True)
        with self.assertRaises(TokenReplayRefused):
            prepare(broker, spec_kwargs=dict(contract=CONTRACT_IRREVERSIBLE),
                    token=3)

    def test_reversible_requires_undo_receipt_before_success(self):
        broker, _ = make_broker()
        session = prepare(broker, spec_kwargs=dict(contract=CONTRACT_REVERSIBLE))
        broker.dispatch(session)
        broker.start(session)
        with self.assertRaises(ContractViolation):
            broker.ack(session, ok=True)
        broker.record_undo(session, receipt={'bytes': '01020304'})
        broker.ack(session, ok=True)
        self.assertEqual(broker.snapshot()['sessions'][0]['state'],
                         'ack_success')

    def test_record_undo_contract_guard(self):
        broker, _ = make_broker()
        session = prepare(broker, spec_kwargs=dict(contract=CONTRACT_GETTER))
        with self.assertRaises(ContractViolation):
            broker.record_undo(session, receipt='r')
        with self.assertRaises(ContractViolation):
            broker.record_undo(session, receipt=None)


class MonoBrokerDeadlineTests(unittest.TestCase):
    def test_prepare_requires_future_deadline(self):
        broker, clock = make_broker()
        with self.assertRaises(DeadlineRefused):
            prepare(broker, deadline_qpc=clock.value)
        with self.assertRaises(DeadlineRefused):
            prepare(broker, deadline_qpc=clock.value - 1)

    def test_dispatch_refused_when_deadline_expired(self):
        broker, clock = make_broker()
        session = prepare(broker, spec_kwargs=dict(method_token=0x6001000B))
        clock.advance(20_000)
        with self.assertRaises(DeadlineRefused):
            broker.dispatch(session)
        snapshot = broker.snapshot()
        self.assertEqual(snapshot['sessions'][0]['state'], 'timeout')
        self.assertTrue(snapshot['sessions'][0]['unknown_effect'])
        with self.assertRaises(UnknownRetryRefused):
            prepare(broker, spec_kwargs=dict(method_token=0x6001000B),
                    token=2)

    def test_timeout_refused_before_deadline(self):
        broker, clock = make_broker()
        session = prepare(broker)
        broker.dispatch(session)
        with self.assertRaises(DeadlineRefused):
            broker.timeout(session)
        clock.advance(20_000)
        broker.timeout(session)
        self.assertEqual(broker.snapshot()['sessions'][0]['state'], 'timeout')


class MonoBrokerOwnerTests(unittest.TestCase):
    def test_owner_mismatch_refused(self):
        broker, _ = make_broker()
        for owner in (
                (PID + 1, CREATION_TIME, SHA),
                (PID, CREATION_TIME + 1, SHA),
                (PID, CREATION_TIME, 'b' * 64)):
            with self.subTest(owner=owner[:1]):
                with self.assertRaises(OwnerMismatchRefused):
                    prepare(broker, owner=owner)

    def test_matching_owner_accepted(self):
        broker, _ = make_broker()
        session = prepare(broker, owner=(PID, CREATION_TIME, SHA))
        self.assertIsNotNone(session)


class MonoBrokerGCHandleTests(unittest.TestCase):
    def test_handle_lifecycle(self):
        broker, _ = make_broker()
        handle = broker.gc_acquire(0x77)
        self.assertEqual(broker.gc_target(handle), 0x77)
        broker.gc_release(handle)
        with self.assertRaises(GCHandleRefused):
            broker.gc_target(handle)
        with self.assertRaises(GCHandleRefused):
            broker.gc_release(handle)

    def test_release_unknown_handle_refused(self):
        broker, _ = make_broker()
        with self.assertRaises(GCHandleRefused):
            broker.gc_release(99)

    def test_release_after_unload_refused(self):
        broker, _ = make_broker()
        handle = broker.gc_acquire(0x77)
        broker.mark_domain_unloaded()
        with self.assertRaises(GCHandleRefused):
            broker.gc_release(handle)


class MonoBrokerThreadTests(unittest.TestCase):
    def test_attach_detach_balance(self):
        broker, _ = make_broker()
        thread = broker.thread_attach()
        broker.thread_detach(thread)
        self.assertEqual(broker.snapshot()['attached_threads'], [])

    def test_detach_without_attach_refused(self):
        broker, _ = make_broker()
        with self.assertRaises(ThreadBalanceRefused):
            broker.thread_detach(1)

    def test_double_detach_refused(self):
        broker, _ = make_broker()
        thread = broker.thread_attach()
        broker.thread_detach(thread)
        with self.assertRaises(ThreadBalanceRefused):
            broker.thread_detach(thread)


class MonoBrokerJitExtentTests(unittest.TestCase):
    def test_patch_extent_bounded_by_jit_info(self):
        broker, _ = make_broker()
        with self.assertRaises(JitExtentRefused):
            prepare(broker,
                    spec_kwargs=dict(jit_info_extent=16),
                    patch_extent=17)
        session = prepare(broker, spec_kwargs=dict(jit_info_extent=16),
                          patch_extent=16)
        self.assertIsNotNone(session)

    def test_spec_jit_extent_bounded(self):
        with self.assertRaises(MonoBrokerError):
            make_spec(jit_info_extent=64 * 1024 * 1024 + 1)


class MonoBrokerSnapshotTests(unittest.TestCase):
    def test_snapshot_shape_and_determinism(self):
        broker, clock = make_broker()
        session = prepare(broker, token=11)
        broker.dispatch(session)
        first = broker.snapshot()
        second = broker.snapshot()
        self.assertEqual(first, second)
        self.assertEqual(first['schema'], 'ct2trainer-mono-broker/v1')
        self.assertEqual(first['identity']['pid'], PID)
        self.assertEqual(first['identity']['module_sha256'], SHA)
        self.assertEqual(first['domain']['domain_id'], 0)
        self.assertEqual(first['domain']['generation'], 1)
        self.assertEqual(first['now_qpc'], clock.value)
        self.assertEqual(first['counts']['sessions'], 1)
        self.assertEqual(first['counts']['terminal'], 0)

    def test_session_limit(self):
        broker, _ = make_broker()
        for index in range(MAX_SESSIONS):
            prepare(broker, token=index + 1,
                    spec_kwargs=dict(method_token=0x70000000 + index))
        with self.assertRaises(MonoBrokerError):
            prepare(broker, token=MAX_SESSIONS + 1,
                    spec_kwargs=dict(method_token=0x7FFFFFFF))


if __name__ == '__main__':
    unittest.main()
