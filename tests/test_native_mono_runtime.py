"""Contract tests for the engine-side Mono runtime route (AP-04 stage 2).

``mono_runtime`` binds the typed broker (``mono_broker``) to the own C
adapter contract (``mono_api.c`` / ``mono_collector.c``: 4 exports, 42 typed
functions) with an injectable adapter backend. All backend tests run in
process against fakes; the ctypes cross-checks at the end exercise the
built ``CT2TrainerMonoExisting.dll`` and the fake export DLLs behind the
same environment gates as ``test_native_mono_sources``.
"""
import ctypes
import json
import os
import sys
import unittest
from pathlib import Path

from ct2trainer.native import mono_runtime as m
from ct2trainer.native.mono_broker import (
    ARG_BYREF,
    ARG_STATIC_BYTES,
    CONTRACT_GETTER,
    CONTRACT_IRREVERSIBLE,
    CONTRACT_REVERSIBLE,
    ExportPin,
    InvocationSpec,
)

ROOT = Path(__file__).resolve().parents[1]
SHA = 'a' * 64
PID = 4242
CREATION_TIME = 123456789
DEADLINE = 10_000


class Clock:
    def __init__(self, value=1000):
        self.value = value

    def __call__(self):
        return self.value

    def advance(self, ticks):
        self.value += ticks


class FakeBackend(m.AdapterBackend):
    def __init__(self, handle=0x400000, sha=SHA, pid=PID, created=CREATION_TIME,
                 bitness=64, exports=None, domain=(0x5000, 0, 1), jit=None):
        self.handle = handle
        self.sha = sha
        self._pid = pid
        self.created = created
        self._bitness = bitness
        self._exports = set(exports) if exports is not None else None
        self.domain = domain
        self._jit = dict(jit or {})
        self.jit_calls = 0

    def module_handle(self):
        return self.handle

    def module_sha256(self):
        return self.sha

    def exports(self):
        if self._exports is None:
            return {pin.export for pin in m.PINNED_EXPORTS}
        return set(self._exports)

    def pid(self):
        return self._pid

    def created_time(self):
        return self.created

    def bitness(self):
        return self._bitness

    def domain_identity(self):
        return self.domain

    def jit_info(self, method_token):
        self.jit_calls += 1
        return self._jit.get(method_token)


def make_runtime(backend=None, clock=None, binding=None):
    if clock is None:
        clock = Clock()
    if backend is None:
        backend = FakeBackend()
    if binding is None:
        binding = m.AdapterBinding.for_module(SHA, PID, CREATION_TIME, 64)
    return m.MonoRuntime(binding, backend=backend, now_qpc=clock), backend, clock


def opened(**overrides):
    runtime, backend, clock = make_runtime(**overrides)
    runtime.open()
    return runtime, backend, clock


def boot(runtime, nonce='nonce-1', token=9001, deadline=DEADLINE, **overrides):
    msg = dict(owner_module_sha256=SHA, pid=PID, created_time=CREATION_TIME,
               deadline_qpc=deadline, nonce=nonce)
    msg.update(overrides)
    return runtime.bootstrap(m.FrozenBootstrap(**msg), token=token)


def make_spec(**overrides):
    base = dict(method_token=0x60010001, is_instance=False,
                argument_kinds=(ARG_STATIC_BYTES,), contract=CONTRACT_GETTER)
    base.update(overrides)
    return InvocationSpec(**base)


def make_extent(token=0x60010001, size=40, address=0x1000, domain_id=0):
    return m.JitExtent(token, address, size, domain_id, bytes(min(size, 32)))


def session_state(runtime, session_id):
    for session in runtime.snapshot()['broker']['sessions']:
        if session['session_id'] == session_id:
            return session['state']
    raise AssertionError(f'session {session_id} not found')


class RuntimePinnedTableTests(unittest.TestCase):
    def test_pinned_table_matches_api_prototypes_json(self):
        raw = json.loads((ROOT / 'dependencies/native/mono-api-source/api-prototypes.json')
                         .read_text(encoding='utf-8'))
        self.assertEqual(raw['schema'], 'ct2trainer-mono-api-prototypes/v1')
        expected = tuple(ExportPin(e['export'], e['field'])
                         for e in raw['required_exports'])
        self.assertEqual(m.PINNED_EXPORTS, expected)

    def test_binding_helper_carries_the_pinned_table(self):
        binding = m.AdapterBinding.for_module(SHA, PID, CREATION_TIME, 64)
        self.assertEqual(binding.exports, m.PINNED_EXPORTS)
        self.assertEqual(binding.module_sha256, SHA)

    def test_binding_refuses_divergent_export_tables(self):
        table = list(m.PINNED_EXPORTS)
        self.assertEqual(len(table), 42)
        with self.subTest(case='swapped_name'):
            swapped = table[:3] + [ExportPin('not_pinned', table[3].field)] + table[4:]
            with self.assertRaises(m.MonoRuntimeError):
                m.AdapterBinding(SHA, tuple(swapped), PID, CREATION_TIME, 64)
        with self.subTest(case='reordered'):
            reordered = [table[1]] + table[:1] + table[2:]
            with self.assertRaises(m.MonoRuntimeError):
                m.AdapterBinding(SHA, tuple(reordered), PID, CREATION_TIME, 64)
        with self.subTest(case='missing_one'):
            with self.assertRaises(m.MonoRuntimeError):
                m.AdapterBinding(SHA, tuple(table[:-1]), PID, CREATION_TIME, 64)
        with self.subTest(case='extra_entry'):
            with self.assertRaises(m.MonoRuntimeError):
                m.AdapterBinding(SHA, tuple(table + [table[0]]), PID, CREATION_TIME, 64)

    def test_binding_refuses_bad_identity_fields(self):
        for sha in ('A' * 64, 'b' * 63, 'g' * 64):
            with self.subTest(sha=sha[:2]):
                with self.assertRaises(m.MonoRuntimeError):
                    m.AdapterBinding.for_module(sha, PID, CREATION_TIME, 64)
        for pid in (0, 2 ** 32):
            with self.subTest(pid=pid):
                with self.assertRaises(m.MonoRuntimeError):
                    m.AdapterBinding.for_module(SHA, pid, CREATION_TIME, 64)
        with self.subTest(created=2 ** 64):
            with self.assertRaises(m.MonoRuntimeError):
                m.AdapterBinding.for_module(SHA, PID, 2 ** 64, 64)
        with self.subTest(bitness=16):
            with self.assertRaises(m.MonoRuntimeError):
                m.AdapterBinding.for_module(SHA, PID, CREATION_TIME, 16)


class PinnedTablePathTests(unittest.TestCase):
    """Default table resolution for source checkouts and frozen bundles.

    Regression test for the portable build: in a PyInstaller onefile the
    module ``__file__`` points inside ``sys._MEIPASS``, so a plain
    ``parents[3]`` resolution lands in the system temp dir and trainer
    generation failed with ``FileNotFoundError`` as soon as the engine
    module imported ``mono_runtime``. The build bundles
    ``api-prototypes.json`` under the same relative path inside the
    bundle, and ``_default_export_table_path`` must resolve there.
    """

    def test_source_mode_resolves_repository_path(self):
        path = m._default_export_table_path()
        self.assertEqual(
            path,
            ROOT / 'dependencies/native/mono-api-source/api-prototypes.json')
        self.assertTrue(path.is_file())

    def test_frozen_mode_resolves_bundle_path(self):
        import shutil
        import tempfile
        bundle = Path(tempfile.mkdtemp())
        try:
            target = (bundle / 'dependencies/native/mono-api-source'
                      / 'api-prototypes.json')
            target.parent.mkdir(parents=True)
            target.write_bytes(m._default_export_table_path().read_bytes())
            had_frozen = hasattr(sys, 'frozen')
            had_meipass = hasattr(sys, '_MEIPASS')
            saved_frozen = getattr(sys, 'frozen', None)
            saved_meipass = getattr(sys, '_MEIPASS', None)
            sys.frozen = True
            sys._MEIPASS = str(bundle)
            try:
                self.assertEqual(m._default_export_table_path(), target)
                self.assertEqual(len(m.load_pinned_export_table()), 42)
            finally:
                if had_frozen:
                    sys.frozen = saved_frozen
                else:
                    del sys.frozen
                if had_meipass:
                    sys._MEIPASS = saved_meipass
                else:
                    del sys._MEIPASS
        finally:
            shutil.rmtree(bundle, ignore_errors=True)


class RuntimeOpenTests(unittest.TestCase):
    def test_open_binds_matching_backend(self):
        runtime, _, _ = opened()
        snapshot = runtime.snapshot()
        self.assertEqual(snapshot['schema'], 'ct2trainer-mono-runtime/v1')
        self.assertEqual(snapshot['binding']['module_sha256'], SHA)
        self.assertEqual(snapshot['binding']['export_count'], 42)
        self.assertEqual(snapshot['binding']['pid'], PID)
        self.assertEqual(snapshot['binding']['creation_time'], CREATION_TIME)
        self.assertEqual(snapshot['binding']['bitness'], 64)
        self.assertTrue(snapshot['module_held'])
        self.assertFalse(snapshot['closed'])
        self.assertFalse(snapshot['bootstrapped'])
        self.assertEqual(snapshot['nonces_consumed'], 0)
        self.assertEqual(snapshot['domain']['domain_ptr'], 0x5000)
        self.assertEqual(snapshot['domain']['domain_id'], 0)
        self.assertEqual(snapshot['domain']['generation'], 1)
        self.assertFalse(snapshot['domain']['unloaded'])
        self.assertFalse(snapshot['domain']['visible_unknown'])

    def test_open_is_idempotent(self):
        runtime, _, _ = opened()
        runtime.open()
        snapshot = runtime.snapshot()
        self.assertTrue(snapshot['module_held'])
        self.assertEqual(snapshot, runtime.snapshot())

    def test_work_before_open_is_refused(self):
        runtime, _, clock = make_runtime()
        msg = m.FrozenBootstrap(SHA, PID, CREATION_TIME, DEADLINE, 'n')
        with self.subTest(op='bootstrap'):
            with self.assertRaises(m.NotOpenRefused):
                runtime.bootstrap(msg, token=1)
        with self.subTest(op='snapshot'):
            with self.assertRaises(m.NotOpenRefused):
                runtime.snapshot()
        with self.subTest(op='gc_acquire'):
            with self.assertRaises(m.NotOpenRefused):
                runtime.gc_acquire(1)
        with self.subTest(op='mark_domain_unloaded'):
            with self.assertRaises(m.NotOpenRefused):
                runtime.mark_domain_unloaded()

    def test_module_sha_mismatch_is_binding_refused_and_stays_unbound(self):
        runtime, _, _ = make_runtime(backend=FakeBackend(sha='b' * 64))
        with self.assertRaises(m.BindingRefused):
            runtime.open()
        with self.assertRaises(m.NotOpenRefused):
            runtime.snapshot()

    def test_owner_facts_mismatch_is_refused(self):
        for overrides in (dict(pid=PID + 1), dict(created=CREATION_TIME + 1),
                          dict(bitness=32)):
            runtime, _, _ = make_runtime(backend=FakeBackend(**overrides))
            with self.subTest(overrides=overrides):
                with self.assertRaises(m.OwnerMismatchRefused):
                    runtime.open()
                with self.assertRaises(m.NotOpenRefused):
                    runtime.snapshot()

    def test_missing_pinned_export_is_refused_by_name(self):
        for pin in (m.PINNED_EXPORTS[0], m.PINNED_EXPORTS[-1]):
            exports = [p.export for p in m.PINNED_EXPORTS if p.export != pin.export]
            runtime, _, _ = make_runtime(backend=FakeBackend(exports=exports))
            with self.subTest(pin=pin.export):
                with self.assertRaises(m.ExportTableRefused) as caught:
                    runtime.open()
                self.assertIn(pin.export, str(caught.exception))
            with self.assertRaises(m.NotOpenRefused):
                runtime.snapshot()

    def test_extra_module_exports_are_admitted(self):
        exports = [p.export for p in m.PINNED_EXPORTS] + ['extra_one', 'extra_two']
        runtime, _, _ = opened(backend=FakeBackend(exports=exports))
        self.assertEqual(runtime.snapshot()['binding']['export_count'], 42)

    def test_invalid_module_handle_is_refused(self):
        runtime, _, _ = make_runtime(backend=FakeBackend(handle=0))
        with self.assertRaises(m.BindingRefused):
            runtime.open()

    def test_closed_route_refuses_reopen(self):
        runtime, _, _ = opened()
        session = boot(runtime)
        runtime.dispatch(session)
        runtime.start(session)
        runtime.ack(session, ok=True)
        runtime.mark_target_ended()
        runtime.close()
        with self.assertRaises(m.InvalidTransitionError):
            runtime.open()
        # The deterministic final-state read remains available after close.
        self.assertTrue(runtime.snapshot()['closed'])


class RuntimeBootstrapTests(unittest.TestCase):
    def test_bootstrap_admits_matching_message(self):
        runtime, _, _ = opened()
        session = boot(runtime)
        self.assertIsInstance(session, int)
        snapshot = runtime.snapshot()
        self.assertTrue(snapshot['bootstrapped'])
        self.assertEqual(snapshot['nonces_consumed'], 1)
        self.assertEqual(session_state(runtime, session), 'prepared')
        broker_session = runtime.snapshot()['broker']['sessions'][0]
        self.assertEqual(broker_session['method_token'], m.BOOTSTRAP_METHOD_TOKEN)

    def test_bootstrap_owner_mismatch_refused_and_nonce_preserved(self):
        for overrides in (dict(pid=PID + 1), dict(created_time=CREATION_TIME + 1),
                          dict(owner_module_sha256='b' * 64)):
            runtime, _, _ = opened()
            with self.subTest(overrides=overrides):
                with self.assertRaises(m.OwnerMismatchRefused):
                    boot(runtime, **overrides)
                self.assertEqual(runtime.snapshot()['nonces_consumed'], 0)
                with self.assertRaises(m.NotBootstrappedRefused):
                    runtime.invoke(make_spec(), token=1, deadline_qpc=DEADLINE,
                                   signature=(False, 1))

    def test_stale_deadline_refused_and_nonce_consumed(self):
        runtime, _, clock = opened()
        with self.assertRaises(m.DeadlineRefused):
            boot(runtime, nonce='n1', deadline=clock.value)
        self.assertEqual(runtime.snapshot()['nonces_consumed'], 1)
        with self.assertRaises(m.NonceReplayRefused):
            boot(runtime, nonce='n1', deadline=clock.value + 5000)
        session = boot(runtime, nonce='n2', deadline=clock.value + 5000)
        self.assertEqual(session_state(runtime, session), 'prepared')

    def test_second_bootstrap_refused_after_success(self):
        runtime, _, _ = opened()
        boot(runtime, nonce='n1')
        with self.assertRaises(m.BootstrapReplayRefused):
            boot(runtime, nonce='n2')

    def test_invoke_before_bootstrap_refused(self):
        runtime, _, _ = opened()
        with self.assertRaises(m.NotBootstrappedRefused):
            runtime.invoke(make_spec(), token=1, deadline_qpc=DEADLINE,
                           signature=(False, 1))

    def test_bootstrap_consumes_its_cas_token(self):
        runtime, _, _ = opened()
        boot(runtime, token=7)
        with self.assertRaises(m.TokenReplayRefused):
            runtime.invoke(make_spec(), token=7, deadline_qpc=DEADLINE,
                           signature=(False, 1))

    def test_bootstrap_message_validation(self):
        cases = [
            dict(nonce=''),
            dict(deadline_qpc=-1),
            dict(owner_module_sha256='B' * 64),
            dict(pid=0),
            dict(created_time=2 ** 64),
        ]
        for overrides in cases:
            base = dict(owner_module_sha256=SHA, pid=PID, created_time=CREATION_TIME,
                        deadline_qpc=DEADLINE, nonce='n')
            base.update(overrides)
            with self.subTest(overrides=overrides):
                with self.assertRaises(m.MonoRuntimeError):
                    m.FrozenBootstrap(**base)


class RuntimeDomainLifecycleTests(unittest.TestCase):
    def test_root_domain_id_zero_is_valid(self):
        runtime, _, _ = opened()
        runtime.bind_domain(domain_ptr=0x5000, domain_id=0, generation=1)
        self.assertEqual(runtime.snapshot()['domain']['domain_id'], 0)

    def test_nonzero_root_domain_id_is_valid(self):
        runtime, _, _ = opened(backend=FakeBackend(domain=(0x5000, 7, 1)))
        runtime.bind_domain(domain_ptr=0x5000, domain_id=7, generation=1)
        self.assertEqual(runtime.snapshot()['domain']['domain_id'], 7)

    def test_stale_domain_rebind_refused(self):
        for kwargs in (dict(domain_ptr=0x9999, domain_id=0, generation=1),
                       dict(domain_ptr=0x5000, domain_id=3, generation=1),
                       dict(domain_ptr=0x5000, domain_id=0, generation=2)):
            runtime, _, _ = opened()
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(m.StaleDomainRefused):
                    runtime.bind_domain(**kwargs)

    def test_unload_possible_while_module_held_and_visible_unknown(self):
        runtime, _, _ = opened()
        runtime.mark_domain_unloaded()
        snapshot = runtime.snapshot()
        self.assertTrue(snapshot['domain']['unloaded'])
        self.assertTrue(snapshot['domain']['visible_unknown'])
        self.assertTrue(snapshot['module_held'])
        self.assertFalse(snapshot['closed'])

    def test_unload_taints_dispatched_session_and_blocks_retry(self):
        runtime, _, _ = opened()
        boot(runtime)
        session = runtime.invoke(make_spec(), token=2, deadline_qpc=DEADLINE,
                                 signature=(False, 1))
        runtime.dispatch(session)
        runtime.mark_domain_unloaded()
        state = session_state(runtime, session)
        self.assertEqual(state, 'ack_lost')
        snapshot = runtime.snapshot()
        self.assertTrue(snapshot['broker']['sessions'][1]['unknown_effect'])
        self.assertIn(0x60010001, snapshot['broker']['unknown_method_tokens'])
        # The unloaded route refuses any new work before the tainted-token check.
        with self.assertRaises(m.DomainUnloadedRefused):
            runtime.invoke(make_spec(), token=3, deadline_qpc=DEADLINE,
                           signature=(False, 1))

    def test_unload_taints_running_session(self):
        runtime, _, _ = opened()
        boot(runtime)
        session = runtime.invoke(make_spec(), token=2, deadline_qpc=DEADLINE,
                                 signature=(False, 1))
        runtime.dispatch(session)
        runtime.start(session)
        runtime.mark_domain_unloaded()
        self.assertEqual(session_state(runtime, session), 'ack_lost')

    def test_unload_keeps_prepared_sessions_safely_cancellable(self):
        runtime, _, _ = opened()
        boot_session = boot(runtime)
        session = runtime.invoke(make_spec(), token=2, deadline_qpc=DEADLINE,
                                 signature=(False, 1))
        runtime.mark_domain_unloaded()
        runtime.cancel(session)
        self.assertEqual(session_state(runtime, session), 'cancelled')
        runtime.cancel(boot_session)
        self.assertEqual(session_state(runtime, boot_session), 'cancelled')
        with self.assertRaises(m.DomainUnloadedRefused):
            runtime.dispatch(session)

    def test_unload_refuses_new_work(self):
        runtime, _, _ = opened()
        runtime.mark_domain_unloaded()
        with self.subTest(op='bootstrap'):
            with self.assertRaises(m.DomainUnloadedRefused):
                boot(runtime)
        with self.subTest(op='invoke'):
            with self.assertRaises(m.DomainUnloadedRefused):
                runtime.invoke(make_spec(), token=1, deadline_qpc=DEADLINE,
                               signature=(False, 1))
        with self.subTest(op='gc_acquire'):
            with self.assertRaises(m.DomainUnloadedRefused):
                runtime.gc_acquire(1)
        with self.subTest(op='thread_attach'):
            with self.assertRaises(m.DomainUnloadedRefused):
                runtime.thread_attach()
        with self.subTest(op='request_jit_extent'):
            with self.assertRaises(m.DomainUnloadedRefused):
                runtime.request_jit_extent(0x60010001)
        with self.subTest(op='bind_domain'):
            with self.assertRaises(m.DomainUnloadedRefused):
                runtime.bind_domain(domain_ptr=0x5000, domain_id=0, generation=1)
        runtime.mark_domain_unloaded()

    def test_unload_before_open_refused(self):
        runtime, _, _ = make_runtime()
        with self.assertRaises(m.NotOpenRefused):
            runtime.mark_domain_unloaded()


def _finish(runtime, session):
    """Drive a session through dispatch/start to a successful ack."""
    runtime.dispatch(session)
    runtime.start(session)
    runtime.ack(session, ok=True)


class RuntimeCleanupGateTests(unittest.TestCase):
    def test_close_before_target_end_refused_even_when_balanced(self):
        runtime, _, _ = opened()
        session = boot(runtime)
        _finish(runtime, session)
        with self.assertRaises(m.CleanupBeforeTargetEndRefused):
            runtime.close()

    def test_close_refused_while_sessions_live(self):
        runtime, _, _ = opened()
        boot(runtime)
        runtime.invoke(make_spec(), token=2, deadline_qpc=DEADLINE,
                       signature=(False, 1))
        runtime.mark_target_ended()
        with self.assertRaises(m.UnbalancedCloseRefused):
            runtime.close()

    def test_close_refused_with_live_gc_handle(self):
        runtime, _, _ = opened()
        session = boot(runtime)
        _finish(runtime, session)
        runtime.gc_acquire(0x77)
        runtime.mark_target_ended()
        with self.assertRaises(m.UnbalancedCloseRefused):
            runtime.close()

    def test_close_refused_with_attached_thread(self):
        runtime, _, _ = opened()
        session = boot(runtime)
        _finish(runtime, session)
        runtime.thread_attach()
        runtime.mark_target_ended()
        with self.assertRaises(m.UnbalancedCloseRefused):
            runtime.close()

    def test_close_succeeds_when_balanced_after_target_end(self):
        runtime, _, _ = opened()
        session = boot(runtime)
        _finish(runtime, session)
        handle = runtime.gc_acquire(0x77)
        runtime.gc_release(handle)
        thread = runtime.thread_attach()
        runtime.thread_detach(thread)
        runtime.mark_target_ended()
        runtime.close()
        snapshot = runtime.snapshot()
        self.assertTrue(snapshot['closed'])
        self.assertFalse(snapshot['module_held'])

    def test_work_refused_after_target_end(self):
        runtime, _, _ = opened()
        session = boot(runtime)
        _finish(runtime, session)
        runtime.mark_target_ended()
        with self.subTest(op='invoke'):
            with self.assertRaises(m.TargetEndedRefused):
                runtime.invoke(make_spec(), token=2, deadline_qpc=DEADLINE,
                               signature=(False, 1))
        with self.subTest(op='bootstrap'):
            with self.assertRaises(m.TargetEndedRefused):
                boot(runtime, nonce='n2', token=2)
        with self.subTest(op='gc_acquire'):
            with self.assertRaises(m.TargetEndedRefused):
                runtime.gc_acquire(1)
        with self.subTest(op='thread_attach'):
            with self.assertRaises(m.TargetEndedRefused):
                runtime.thread_attach()

    def test_operations_refused_after_close_but_late_completion_logged(self):
        runtime, _, _ = opened()
        session = boot(runtime)
        _finish(runtime, session)
        runtime.mark_target_ended()
        runtime.close()
        for op in (lambda: runtime.open(),
                   lambda: boot(runtime, nonce='n2', token=2),
                   lambda: runtime.invoke(make_spec(), token=3,
                                          deadline_qpc=DEADLINE,
                                          signature=(False, 1)),
                   lambda: runtime.gc_acquire(1)):
            with self.assertRaises(m.InvalidTransitionError):
                op()
        runtime.late_completion(session, 'late-ack-after-close')
        # The broker log keeps the receipt; the state stays terminal.
        broker = runtime._broker
        self.assertEqual(
            [s for s in broker.snapshot()['sessions']
             if s['session_id'] == session][0]['state'], 'ack_success')


class RuntimeSessionContractTests(unittest.TestCase):
    def _booted(self):
        runtime, backend, clock = opened()
        boot(runtime)
        return runtime, backend, clock

    def test_getter_happy_path(self):
        runtime, _, _ = opened()
        boot_session = boot(runtime)
        session = runtime.invoke(make_spec(), token=2, deadline_qpc=DEADLINE,
                                 signature=(False, 1))
        _finish(runtime, boot_session)
        _finish(runtime, session)
        snapshot = runtime.snapshot()
        self.assertEqual(session_state(runtime, session), 'ack_success')
        self.assertEqual(snapshot['broker']['counts']['sessions'], 2)
        self.assertEqual(snapshot['broker']['counts']['terminal'], 2)
        self.assertEqual(snapshot['broker']['unknown_method_tokens'], [])

    def test_invoke_before_bootstrap_refused(self):
        runtime, _, _ = opened()
        with self.assertRaises(m.NotBootstrappedRefused):
            runtime.invoke(make_spec(), token=1, deadline_qpc=DEADLINE,
                           signature=(False, 1))

    def test_getter_refuses_any_patch_extent(self):
        runtime, backend, _ = self._booted()
        backend._jit[0x60010001] = make_extent()
        with self.assertRaises(m.GetterMutationRefused):
            runtime.invoke(make_spec(jit_info_extent=40), token=1,
                           deadline_qpc=DEADLINE, signature=(False, 1),
                           patch_extent=4)
        # The refusal happens before the broker sees the invocation.
        self.assertEqual(runtime.snapshot()['broker']['counts']['sessions'], 1)

    def test_mutable_argument_requires_capability(self):
        runtime, _, _ = self._booted()
        with self.assertRaises(m.UnsupportedSignatureRefused):
            runtime.invoke(make_spec(argument_kinds=(ARG_BYREF,),
                                     contract=CONTRACT_REVERSIBLE), token=1,
                           deadline_qpc=DEADLINE, signature=(False, 1))
        session = runtime.invoke(
            make_spec(argument_kinds=(ARG_BYREF,), contract=CONTRACT_REVERSIBLE),
            token=1, deadline_qpc=DEADLINE, signature=(False, 1),
            capabilities=frozenset({ARG_BYREF}))
        self.assertIsNotNone(session)

    def test_getter_refuses_mutable_argument_even_with_capability(self):
        runtime, _, _ = self._booted()
        with self.assertRaises(m.UnsupportedSignatureRefused):
            runtime.invoke(make_spec(argument_kinds=(ARG_BYREF,)), token=1,
                           deadline_qpc=DEADLINE, signature=(False, 1),
                           capabilities=frozenset({ARG_BYREF}))

    def test_cas_token_is_one_shot(self):
        runtime, _, _ = self._booted()
        runtime.invoke(make_spec(), token=9, deadline_qpc=DEADLINE,
                       signature=(False, 1))
        with self.assertRaises(m.TokenReplayRefused):
            runtime.invoke(make_spec(method_token=0x60010002), token=9,
                           deadline_qpc=DEADLINE, signature=(False, 1))

    def test_irreversible_method_token_is_one_shot(self):
        runtime, _, _ = self._booted()
        spec = make_spec(contract=CONTRACT_IRREVERSIBLE)
        runtime.invoke(spec, token=1, deadline_qpc=DEADLINE, signature=(False, 1))
        # Burned even while the first session is still live.
        with self.assertRaises(m.TokenReplayRefused):
            runtime.invoke(spec, token=2, deadline_qpc=DEADLINE,
                           signature=(False, 1))

    def test_ack_lost_marks_unknown_and_blocks_retry(self):
        runtime, _, _ = self._booted()
        session = runtime.invoke(make_spec(), token=2, deadline_qpc=DEADLINE,
                                 signature=(False, 1))
        runtime.dispatch(session)
        runtime.ack_lost(session)
        snapshot = runtime.snapshot()
        self.assertEqual(session_state(runtime, session), 'ack_lost')
        self.assertTrue(snapshot['broker']['sessions'][1]['unknown_effect'])
        self.assertIn(0x60010001,
                      snapshot['broker']['unknown_method_tokens'])
        # A fresh CAS token does not launder the tainted method token.
        with self.assertRaises(m.UnknownRetryRefused):
            runtime.invoke(make_spec(), token=3, deadline_qpc=DEADLINE,
                           signature=(False, 1))

    def test_exception_after_effect_is_unknown(self):
        runtime, _, _ = self._booted()
        session = runtime.invoke(make_spec(contract=CONTRACT_IRREVERSIBLE),
                                 token=2, deadline_qpc=DEADLINE,
                                 signature=(False, 1))
        runtime.dispatch(session)
        runtime.start(session)
        runtime.ack(session, ok=False, exception='AccessViolation',
                    effect_observed=True)
        self.assertEqual(session_state(runtime, session), 'unknown')
        with self.assertRaises(m.UnknownRetryRefused):
            runtime.invoke(make_spec(contract=CONTRACT_IRREVERSIBLE),
                           token=3, deadline_qpc=DEADLINE,
                           signature=(False, 1))

    def test_plain_failure_is_not_unknown_and_retry_is_allowed(self):
        runtime, _, _ = self._booted()
        session = runtime.invoke(make_spec(), token=2, deadline_qpc=DEADLINE,
                                 signature=(False, 1))
        runtime.dispatch(session)
        runtime.start(session)
        runtime.ack(session, ok=False, exception='NullReferenceException')
        snapshot = runtime.snapshot()
        self.assertEqual(session_state(runtime, session), 'ack_failure')
        self.assertNotIn(0x60010001,
                         snapshot['broker']['unknown_method_tokens'])
        retry = runtime.invoke(make_spec(), token=3, deadline_qpc=DEADLINE,
                               signature=(False, 1))
        self.assertIsNotNone(retry)

    def test_cancel_only_pre_start(self):
        runtime, _, _ = self._booted()
        session = runtime.invoke(make_spec(), token=2, deadline_qpc=DEADLINE,
                                 signature=(False, 1))
        runtime.cancel(session)
        self.assertEqual(session_state(runtime, session), 'cancelled')
        with self.assertRaises(m.InvalidTransitionError):
            runtime.cancel(session)

    def test_cancel_dispatched_and_running_refused(self):
        runtime, _, _ = self._booted()
        session = runtime.invoke(make_spec(), token=2, deadline_qpc=DEADLINE,
                                 signature=(False, 1))
        runtime.dispatch(session)
        with self.assertRaises(m.RunningNotCancelable):
            runtime.cancel(session)
        runtime.start(session)
        with self.assertRaises(m.RunningNotCancelable):
            runtime.cancel(session)

    def test_dispatch_after_deadline_is_timeout_and_taints(self):
        runtime, _, clock = self._booted()
        session = runtime.invoke(make_spec(), token=2,
                                 deadline_qpc=clock.value + 100,
                                 signature=(False, 1))
        clock.advance(200)
        with self.assertRaises(m.DeadlineRefused):
            runtime.dispatch(session)
        snapshot = runtime.snapshot()
        self.assertEqual(session_state(runtime, session), 'timeout')
        self.assertTrue(snapshot['broker']['sessions'][1]['unknown_effect'])
        with self.assertRaises(m.UnknownRetryRefused):
            runtime.invoke(make_spec(), token=3, deadline_qpc=DEADLINE,
                           signature=(False, 1))

    def test_reversible_requires_undo_receipt_before_success(self):
        runtime, _, _ = self._booted()
        session = runtime.invoke(
            make_spec(contract=CONTRACT_REVERSIBLE), token=2,
            deadline_qpc=DEADLINE, signature=(False, 1))
        runtime.dispatch(session)
        runtime.start(session)
        with self.assertRaises(m.ContractViolation):
            runtime.ack(session, ok=True)
        runtime.record_undo(session, {'bytes': '01020304'})
        runtime.ack(session, ok=True)
        self.assertEqual(session_state(runtime, session), 'ack_success')

    def test_late_completion_is_log_only_after_terminal(self):
        runtime, _, _ = self._booted()
        session = runtime.invoke(make_spec(), token=2, deadline_qpc=DEADLINE,
                                 signature=(False, 1))
        with self.assertRaises(m.InvalidTransitionError):
            runtime.late_completion(session, 'too-early')
        _finish(runtime, session)
        runtime.late_completion(session, 'late-ack')
        snapshot = runtime.snapshot()
        self.assertEqual(session_state(runtime, session), 'ack_success')
        self.assertTrue(any('late completion' in entry
                            for entry in
                            snapshot['broker']['sessions'][1]['log']))

    def test_invoke_owner_rebind_refused(self):
        runtime, _, _ = self._booted()
        for owner in ((PID + 1, CREATION_TIME, SHA),
                      (PID, CREATION_TIME + 1, SHA),
                      (PID, CREATION_TIME, 'b' * 64)):
            with self.subTest(owner=owner[0]):
                with self.assertRaises(m.OwnerMismatchRefused):
                    runtime.invoke(make_spec(), token=2,
                                   deadline_qpc=DEADLINE,
                                   signature=(False, 1), owner=owner)

    def test_prepare_deadline_not_future_refused(self):
        runtime, _, clock = self._booted()
        for deadline in (clock.value, clock.value - 1):
            with self.subTest(deadline=deadline):
                with self.assertRaises(m.DeadlineRefused):
                    runtime.invoke(make_spec(), token=2, deadline_qpc=deadline,
                                   signature=(False, 1))


class RuntimeJitExtentTests(unittest.TestCase):
    def test_extent_field_validation(self):
        base = dict(address=0x1000, domain_id=0)
        cases = [
            ('code_size_zero', dict(method_token=1, code_size=0,
                                    first_bytes=b'')),
            ('code_size_over_1mib', dict(method_token=1, code_size=1024 * 1024 + 1,
                                         first_bytes=b'\0' * 32)),
            ('first_bytes_wrong_length', dict(method_token=1, code_size=40,
                                              first_bytes=b'\0' * 40)),
            ('token_zero', dict(method_token=0, code_size=40,
                                first_bytes=b'\0' * 32)),
            ('address_zero', dict(method_token=1, code_size=40, address=0,
                                  first_bytes=b'\0' * 32)),
            ('domain_id_overflow', dict(method_token=1, code_size=40,
                                        domain_id=2 ** 32,
                                        first_bytes=b'\0' * 32)),
        ]
        for name, fields in cases:
            with self.subTest(case=name):
                with self.assertRaises(m.MonoRuntimeError):
                    m.JitExtent(**{**base, **fields})

    def test_registration_refuses_foreign_domain(self):
        runtime, _, _ = opened()
        with self.assertRaises(m.JitExtentRefused):
            runtime.register_jit_extent(make_extent(domain_id=1))
        self.assertEqual(runtime.snapshot()['jit_extents'], {})

    def test_probe_missing_refused_without_registration(self):
        runtime, backend, _ = opened()
        with self.assertRaises(m.JitExtentRefused):
            runtime.request_jit_extent(0x60010001)
        self.assertEqual(backend.jit_calls, 1)
        self.assertEqual(runtime.snapshot()['jit_extents'], {})

    def test_probe_registers_and_second_invoke_reuses_it(self):
        runtime, backend, _ = opened()
        boot(runtime)
        backend._jit[0x60010001] = make_extent(size=40)
        runtime.invoke(make_spec(jit_info_extent=40, contract=CONTRACT_REVERSIBLE), token=2,
                       deadline_qpc=DEADLINE, signature=(False, 1),
                       patch_extent=40)
        self.assertEqual(backend.jit_calls, 1)
        self.assertEqual(runtime.snapshot()['jit_extents'][0x60010001]['code_size'], 40)
        runtime.invoke(make_spec(jit_info_extent=40, contract=CONTRACT_REVERSIBLE), token=3,
                       deadline_qpc=DEADLINE, signature=(False, 1),
                       patch_extent=16)
        self.assertEqual(backend.jit_calls, 1)

    def test_blanket_span_beyond_code_size_refused(self):
        runtime, backend, _ = opened()
        boot(runtime)
        backend._jit[0x60010001] = make_extent(size=40)
        with self.assertRaises(m.JitExtentRefused):
            runtime.invoke(make_spec(jit_info_extent=40, contract=CONTRACT_REVERSIBLE), token=2,
                           deadline_qpc=DEADLINE, signature=(False, 1),
                           patch_extent=80)

    def test_declared_extent_must_match_probed(self):
        runtime, backend, _ = opened()
        boot(runtime)
        backend._jit[0x60010001] = make_extent(size=40)
        with self.assertRaises(m.JitExtentRefused):
            runtime.invoke(make_spec(jit_info_extent=16, contract=CONTRACT_REVERSIBLE), token=2,
                           deadline_qpc=DEADLINE, signature=(False, 1),
                           patch_extent=16)
        session = runtime.invoke(make_spec(jit_info_extent=40, contract=CONTRACT_REVERSIBLE), token=2,
                                 deadline_qpc=DEADLINE, signature=(False, 1),
                                 patch_extent=40)
        self.assertIsNotNone(session)

    def test_no_extent_derived_without_admitted_probe(self):
        runtime, backend, _ = opened()
        boot(runtime)
        with self.assertRaises(m.JitExtentRefused):
            runtime.invoke(make_spec(jit_info_extent=16, contract=CONTRACT_REVERSIBLE), token=2,
                           deadline_qpc=DEADLINE, signature=(False, 1),
                           patch_extent=16)
        self.assertEqual(backend.jit_calls, 1)

    def test_divergent_reregistration_refused_identical_idempotent(self):
        runtime, _, _ = opened()
        extent = make_extent(size=40)
        runtime.register_jit_extent(extent)
        runtime.register_jit_extent(extent)
        with self.assertRaises(m.JitExtentRefused):
            runtime.register_jit_extent(make_extent(size=48))
        self.assertEqual(runtime.snapshot()['jit_extents'][0x60010001]
                         ['code_size'], 40)


class RuntimeGcThreadTests(unittest.TestCase):
    def test_gc_handle_lifecycle(self):
        runtime, _, _ = opened()
        boot(runtime)
        handle = runtime.gc_acquire(0x77)
        self.assertEqual(runtime.gc_target(handle), 0x77)
        runtime.gc_release(handle)
        with self.assertRaises(m.GCHandleRefused):
            runtime.gc_target(handle)
        with self.assertRaises(m.GCHandleRefused):
            runtime.gc_release(handle)
        with self.assertRaises(m.GCHandleRefused):
            runtime.gc_release(99)

    def test_thread_attach_detach_balance(self):
        runtime, _, _ = opened()
        boot(runtime)
        thread = runtime.thread_attach()
        self.assertEqual(runtime.snapshot()['broker']['attached_threads'],
                         [thread])
        runtime.thread_detach(thread)
        self.assertEqual(runtime.snapshot()['broker']['attached_threads'], [])
        with self.assertRaises(m.ThreadBalanceRefused):
            runtime.thread_detach(thread)
        with self.assertRaises(m.ThreadBalanceRefused):
            runtime.thread_detach(99)

    def test_gc_and_thread_ops_refused_after_target_end(self):
        runtime, _, _ = opened()
        boot(runtime)
        runtime.mark_target_ended()
        with self.assertRaises(m.TargetEndedRefused):
            runtime.gc_acquire(1)
        with self.assertRaises(m.TargetEndedRefused):
            runtime.thread_attach()


CHECK = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p)


class _Api(ctypes.Structure):
    """ctypes mirror of the C ``tf_mono_api`` struct (3 header fields +
    the 42 pinned typed pointers, in pinned-table order)."""

    _fields_ = [('module', ctypes.c_void_p),
                ('image_begin', ctypes.c_size_t),
                ('image_end', ctypes.c_size_t)] + \
               [(pin.field, ctypes.c_void_p) for pin in m.PINNED_EXPORTS]


class _Context(ctypes.Structure):
    """ctypes mirror of the C ``tf_mono_context`` struct."""

    _fields_ = [('owner', ctypes.c_void_p)] + \
               [(p, ctypes.c_uint64) for p in
                ('owner_created', 'target_created', 'deadline_qpc',
                 'qpc_frequency', 'request_id')] + \
               [('target_pid', ctypes.c_uint32)]


def _admitted_context(**overrides):
    """Build a context that passes the C ``tf_admitted`` checks in-process.

    owner = current process handle, FILETIMEs from GetProcessTimes, QPC
    deadline now+30s, target_pid = this process. Same construction as
    test_native_mono_sources.
    """
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.GetProcessTimes.argtypes = (ctypes.c_void_p, ctypes.c_void_p,
                                       ctypes.c_void_p, ctypes.c_void_p,
                                       ctypes.c_void_p)
    kernel.QueryPerformanceFrequency.argtypes = (ctypes.POINTER(ctypes.c_int64),)
    kernel.QueryPerformanceCounter.argtypes = (ctypes.POINTER(ctypes.c_int64),)
    times = [ctypes.c_uint64() for _ in range(4)]
    owner = kernel.GetCurrentProcess()
    assert kernel.GetProcessTimes(owner, *[ctypes.byref(t) for t in times])
    frequency = ctypes.c_int64()
    now = ctypes.c_int64()
    assert kernel.QueryPerformanceFrequency(ctypes.byref(frequency))
    assert kernel.QueryPerformanceCounter(ctypes.byref(now))
    ctx = _Context(owner, times[0].value, times[0].value,
                   now.value + frequency.value * 30, frequency.value, 1,
                   kernel.GetCurrentProcessId())
    for name, value in overrides.items():
        setattr(ctx, name, value)
    return ctx


class RuntimeCtypesAdapterTests(unittest.TestCase):
    """Cross-checks against the real built adapter DLLs (env-gated).

    Same gates as test_native_mono_sources: CT2TRAINER_MONO_SOURCE_BUILD
    and CT2TRAINER_MONO_FAKE_BUILD must point at fresh build outputs.
    """

BUILD = Path(os.environ.get('CT2TRAINER_MONO_SOURCE_BUILD', 'missing-mono-source-build'))
FAKE = Path(os.environ.get('CT2TRAINER_MONO_FAKE_BUILD', 'missing-mono-fake-build'))
_BUILDS_AVAILABLE = (
    sys.platform == 'win32'
    and (BUILD / 'x64' / 'CT2TrainerMonoExisting.dll').is_file()
    and (BUILD / 'x86' / 'CT2TrainerMonoExisting.dll').is_file()
    and all((FAKE / (n + '.dll')).is_file()
            for n in ('complete', 'missing', 'oldversion', 'forwarded', 'data', 'admission_probe'))
)


class RuntimeCtypesAdapterTests(unittest.TestCase):
    """Cross-checks against the real built adapter DLLs (env-gated).

    Same gates as test_native_mono_sources: CT2TRAINER_MONO_SOURCE_BUILD
    and CT2TRAINER_MONO_FAKE_BUILD must point at fresh build outputs.
    """

    @classmethod
    def setUpClass(cls):
        if not _BUILDS_AVAILABLE:
            return
        cls.adapter = ctypes.CDLL(str(BUILD / 'x64' / 'CT2TrainerMonoExisting.dll'))
        cls.complete = ctypes.CDLL(str(FAKE / 'complete.dll'))
        cls.adapter.tf_mono_api_select.argtypes = (ctypes.c_void_p, ctypes.POINTER(_Api), CHECK, ctypes.c_void_p)
        cls.adapter.tf_mono_api_select.restype = ctypes.c_int
        cls.adapter.tf_mono_api_discard.argtypes = (ctypes.POINTER(_Api),)
        cls.adapter.tf_mono_api_discard.restype = None
        cls.adapter.tf_mono_bind_existing.argtypes = (ctypes.POINTER(_Context), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
        cls.adapter.tf_mono_bind_existing.restype = ctypes.c_int
        cls.adapter.tf_mono_get_jit.argtypes = (ctypes.POINTER(_Context), ctypes.c_uint64, ctypes.c_void_p)
        cls.adapter.tf_mono_get_jit.restype = ctypes.c_int

    @unittest.skipUnless(_BUILDS_AVAILABLE, 'explicit source/fake DLL build gate required; no Mono runtime is loaded')
    def test_adapter_exposes_the_four_contract_exports(self):
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetProcAddress.argtypes = (ctypes.c_void_p, ctypes.c_char_p)
        kernel.GetProcAddress.restype = ctypes.c_void_p
        for name in ('tf_mono_api_select', 'tf_mono_api_discard', 'tf_mono_bind_existing', 'tf_mono_get_jit'):
            with self.subTest(export=name):
                self.assertIsNotNone(kernel.GetProcAddress(self.adapter._handle, name.encode()))

    @unittest.skipUnless(_BUILDS_AVAILABLE, 'explicit source/fake DLL build gate required; no Mono runtime is loaded')
    def test_complete_fake_dll_covers_all_pinned_exports(self):
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetProcAddress.argtypes = (ctypes.c_void_p, ctypes.c_char_p)
        kernel.GetProcAddress.restype = ctypes.c_void_p
        missing = [pin.export for pin in m.PINNED_EXPORTS
                   if not kernel.GetProcAddress(self.complete._handle, pin.export.encode())]
        self.assertEqual(missing, [])

    @unittest.skipUnless(_BUILDS_AVAILABLE, 'explicit source/fake DLL build gate required; no Mono runtime is loaded')
    def test_jit_probe_before_bind_is_refused_by_adapter(self):
        # The C adapter refuses a JIT probe before any bind, mirroring the
        # runtime contract that no extent may be derived without an admitted
        # context. TF_RUNTIME == 9.
        ctx = _admitted_context()
        result = (ctypes.c_ubyte * 56)()
        self.assertEqual(self.adapter.tf_mono_get_jit(ctypes.byref(ctx), 1, result), 9)

    @unittest.skipUnless(_BUILDS_AVAILABLE, 'explicit source/fake DLL build gate required; no Mono runtime is loaded')
    def test_bind_existing_refuses_stale_owner_context(self):
        # target_created diverges from the real process FILETIME -> TF_EXPIRED (10).
        ctx = _admitted_context()
        ctx.target_created = 1
        self.assertEqual(self.adapter.tf_mono_bind_existing(
            ctypes.byref(ctx), self.complete._handle, 1, 1), 10)

    @unittest.skipUnless(_BUILDS_AVAILABLE, 'explicit source/fake DLL build gate required; no Mono runtime is loaded')
    def test_bind_existing_refuses_divergent_root_claim(self):
        # Admitted context and complete export table, but the claimed owned
        # root domain is not the runtime's actual root -> refused (TF_RUNTIME, 9).
        ctx = _admitted_context()
        self.assertEqual(self.adapter.tf_mono_bind_existing(
            ctypes.byref(ctx), self.complete._handle, 1, 1), 9)

    @unittest.skipUnless(_BUILDS_AVAILABLE, 'explicit source/fake DLL build gate required; no Mono runtime is loaded')
    def test_select_binds_all_42_fields_inside_held_image_then_discards(self):
        out = _Api()
        ok = self.adapter.tf_mono_api_select(self.complete._handle, ctypes.byref(out),
                                            CHECK(lambda opaque: 1), None)
        self.assertEqual(ok, 1)
        self.assertEqual(out.module, self.complete._handle)
        self.assertLess(out.image_begin, out.image_end)
        for pin in m.PINNED_EXPORTS:
            with self.subTest(pin=pin.export):
                self.assertGreaterEqual(getattr(out, pin.field), out.image_begin)
                self.assertLess(getattr(out, pin.field), out.image_end)
        self.adapter.tf_mono_api_discard(ctypes.byref(out))
        self.assertEqual(bytes(out), b'\0' * ctypes.sizeof(out))


if __name__ == '__main__':
    unittest.main()
