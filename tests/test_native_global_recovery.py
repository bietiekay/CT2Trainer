"""AP-02 lane (Frozen-Global-Gates): strict Global-recovery gate tests.

Part A: GlobalPool.finish_after_exit contract, driven through the real
        engine flow against the owned fake target memory.
Part B: crash recovery hard-blocks on the global pool/member journals:
        the recovery schema cannot parse them, so a live close that
        retains global storage always needs a schema-aware journal
        parser (open milestone point, no auto-recovery claim here).
Part C: owner/probe blocks on a clean (journal-free) state.
Part D: post-fence evidence changes keep the fence and every original
        (status uncertain), win32 only.
Part E: restoration-budget semantics around the global disable path.
Part F: clean contrast: the identical engine-generated state without a
        global journal is fully recoverable with real dead child
        processes, win32 only.

No src/ file is modified. The fake memory never touches a real process.
Parts D and F use real process death proof only for owned children that
this test itself spawned.
"""
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

_TESTS_DIR = str(Path(__file__).resolve().parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

import xml.etree.ElementTree as ET

from test_native_global_engine import Coordinator, Memory, source
from test_native_lua_work_budget import Clock
from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import NativeRuntimeError, TrainerEngine
from ct2trainer.native.global_alloc import GlobalError, GlobalUncertain
from ct2trainer.native.recovery import (
    WAIT_OBJECT_0, WAIT_TIMEOUT, ProcessIdentity, ProcessObservation,
    WindowsProcessProbe, assess_recovery,
)
from ct2trainer.native.recovery_operation import recover_assessment
from ct2trainer.native.restoration_budget import (
    RestorationBudgetError, restoration_operation,
)


TRAINER_ID = 'a' * 16
TABLE_SHA = 'b' * 64
OWNER_PID, OWNER_CREATED = 333, 3333
TARGET_PID, TARGET_CREATED = 444, 4444
NONCE = 'c' * 32

_ORDINARY_SOURCE = ('[ENABLE]\nlabel(done)\nalloc(cave,1000)\ncave:\nmov eax,1\n'
                    'jmp done\n0x1000:\njmp cave\ndone:\n[DISABLE]\n0x1000:\n'
                    'db B8 01 00 00 00\ndealloc(cave)')


def _json(document):
    return json.dumps(document, sort_keys=True, separators=(',', ':')).encode()


def _owner_document(pid=OWNER_PID, created=OWNER_CREATED, nonce=NONCE,
                    legacy=False):
    document = {'owner_pid': pid, 'nonce': nonce}
    if not legacy:
        document.update(schema=2, owner_created=created)
    return document


def _session_document(owner_document, target_pid=TARGET_PID,
                      target_created=TARGET_CREATED, trainer_id=TRAINER_ID):
    return {'schema': 1, 'owner': owner_document, 'trainer_id': trainer_id,
            'target_pid': target_pid, 'target_created': target_created}


def _state_document(trainer_id=TRAINER_ID, table_sha=TABLE_SHA, desired=()):
    payload = {'schema': 1, 'engine': 'ct2trainer',
               'trainer_id': trainer_id, 'table_sha256': table_sha,
               'process_name': 'Owned.exe', 'desired': sorted(desired)}
    return {'payload': payload,
            'sha256': hashlib.sha256(_json(payload)).hexdigest()}


def _pool_journal_document():
    """Byte-shaped pool receipt as GlobalPool writes it (no engine key)."""
    return {'schema': 'ct2trainer-global-pool-draft/v1',
            'trainer_id': TRAINER_ID, 'table_sha256': TABLE_SHA,
            'target': [TARGET_PID, TARGET_CREATED], 'pool_nonce': 'e' * 32,
            'state': 'live', 'pending': [],
            'members': [{'name': 'shared', 'size': 4, 'near': None,
                         'executable': False, 'writable': True,
                         'address': 0x10000, 'actual_size': 4096,
                         'initializer': '64000000',
                         'source_sha256': 'f' * 64,
                         'journal': 'global-shared-01234567.json'}],
            'consumers': [{'nonce': '0' * 32, 'record_id': 1,
                           'activation': '1' * 32,
                           'source_sha256': 'f' * 64,
                           'globals': ['shared'], 'state': 'enabled',
                           'consumer_journal': 'consumer-01234567.json'}]}


def _member_journal_document(owner=TRAINER_ID):
    """Fully valid hook receipt except the owner lacks the ':id' binding."""
    return {'schema': 1, 'engine': 'ct2trainer-hooks',
            'owner': owner, 'target_pid': TARGET_PID,
            'target_created': TARGET_CREATED, 'state': 'enabled',
            'uncertain': False, 'data_commit': False,
            'allocations': {'shared': {'address': 0x10000, 'size': 4,
                                       'budget_size': 4096, 'near': None,
                                       'executable': False,
                                       'writable': True,
                                       'state': 'published'}},
            'blocks': [{'address': 0x10000, 'bytes': '64000000',
                        'original': '00000000', 'is_allocation': True,
                        'executable': False, 'requires_coordinator': False,
                        'allocation': 'shared'}],
            'entries': [], 'exports': {'shared': 0x10000},
            'retirement_policy':
                'retain-published-allocations-until-target-exit'}


def _valid_hook_document():
    document = _member_journal_document()
    document['owner'] = TRAINER_ID + ':fixture'
    return document


def _probe_dead(identity):
    return ProcessObservation(identity, 'dead', identity.created,
                              WAIT_OBJECT_0)


def _all_files(*directories):
    return {path: path.read_bytes() for directory in directories
            for path in directory.rglob('*') if path.is_file()}


class _StateFixture:
    """Hand-written crashed-state layout (state dir + sibling shared dir)."""

    def __init__(self, root, *, pool=False, member=False, valid_hook=False,
                 corrupt_pool=False, legacy_owner=False, session_owner=None,
                 desired=()):
        self.root = root
        self.state = root / 'state'
        self.shared = root / 'shared'
        self.archive = root / 'evidence'
        (self.state / 'hooks').mkdir(parents=True, exist_ok=True)
        self.shared.mkdir(exist_ok=True)
        owner_document = (session_owner if session_owner is not None
                          else _owner_document(legacy=legacy_owner))
        lock = _owner_document(legacy=legacy_owner)
        session = _session_document(owner_document)
        (self.state / 'state.lock').write_bytes(_json(lock))
        (self.state / 'session.json').write_bytes(_json(session))
        (self.state / 'state.json').write_bytes(
            _json(_state_document(desired=desired)))
        (self.shared / f'{TARGET_PID}-{TARGET_CREATED}.json').write_bytes(
            _json(session))
        if pool:
            raw = (b'{"schema":' if corrupt_pool
                   else _json(_pool_journal_document()))
            (self.state / 'hooks' / 'global-pool.json').write_bytes(raw)
        if member:
            (self.state / 'hooks' / 'global-shared-01234567.json').write_bytes(
                _json(_member_journal_document()))
        if valid_hook:
            (self.state / 'hooks' / 'hook.json').write_bytes(
                _json(_valid_hook_document()))

    def assess(self, probe=_probe_dead):
        return assess_recovery(self.state, self.shared, process_probe=probe,
                               expected_trainer_id=TRAINER_ID,
                               expected_table_sha256=TABLE_SHA)

    def recover(self, assessment=None, probe=_probe_dead, archive=None):
        return recover_assessment(
            assessment if assessment is not None else self.assess(probe),
            archive or self.archive, expected_trainer_id=TRAINER_ID,
            expected_table_sha256=TABLE_SHA, process_probe=probe)

    def originals(self):
        return _all_files(self.state, self.shared)


class _EngineState:
    """Engine-generated state: connect to the fake target, save, crash."""

    def __init__(self, root, script):
        self.root = root
        self.state = root / 'state'
        self.shared = root / 'shared'
        root_el = ET.Element('CheatTable', CheatEngineTableVersion='45')
        entries = ET.SubElement(root_el, 'CheatEntries')
        entry = ET.SubElement(entries, 'CheatEntry')
        for key, value in {'ID': '1', 'Description': 'Own 1',
                           'VariableType': 'Auto Assembler Script',
                           'AssemblerScript': script}.items():
            ET.SubElement(entry, key).text = value
        cheat = root / 'own.ct'
        cheat.write_bytes(ET.tostring(root_el, encoding='utf-8',
                                      xml_declaration=True))
        self.plan = compile_table(cheat, 'Owned.exe')
        self.memory = Memory()
        engine = TrainerEngine(self.plan, self.state,
                               lambda name: self.memory, self.shared,
                               hook_coordinator=Coordinator())
        engine.poll()
        if not engine.connected:
            raise AssertionError(engine.error or engine.status)
        engine.store.save({1})
        # Deliberate crash: drop the engine without close(), leaving
        # state.lock, session.json, the shared claim and state.json.
        self.engine = None


def _dead_child_pair():
    children = [subprocess.Popen(
        [sys.executable, '-c', 'import sys; sys.stdin.readline()'],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=0x08000000 if sys.platform == 'win32' else 0)
        for _ in range(2)]
    identities = []
    for child in children:
        observed = WindowsProcessProbe()(ProcessIdentity(child.pid, None))
        if observed.status != 'alive':
            raise AssertionError('owned child is not alive: ' +
                                 str(observed))
        identities.append(ProcessIdentity(child.pid, observed.observed_created))
    for child in children:
        child.stdin.close()
        child.wait(timeout=5)
    return children, identities


def _rebind_engine_state(estate, owner_id, target_id):
    """Rebind ownership to two real dead children (crash simulation)."""
    lock = json.loads((estate.state / 'state.lock').read_bytes())
    owner_document = {'schema': 2, 'owner_pid': owner_id.pid,
                      'owner_created': owner_id.created, 'nonce': lock['nonce']}
    session = {'schema': 1, 'owner': owner_document,
               'trainer_id': estate.plan['trainer_id'],
               'target_pid': target_id.pid,
               'target_created': target_id.created}
    (estate.state / 'state.lock').write_bytes(_json(owner_document))
    (estate.state / 'session.json').write_bytes(_json(session))
    old_claim = estate.shared / '123-456.json'
    if old_claim.exists():
        old_claim.unlink()
    (estate.shared / f'{target_id.pid}-{target_id.created}.json').write_bytes(
        _json(session))


class PoolRetirementContractTests(unittest.TestCase):
    """Part A: GlobalPool.finish_after_exit through the real engine flow."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='native-global-a-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.memory = Memory()
        root_el = ET.Element('CheatTable', CheatEngineTableVersion='45')
        entries = ET.SubElement(root_el, 'CheatEntries')
        entry = ET.SubElement(entries, 'CheatEntry')
        for key, value in {'ID': '1', 'Description': 'Own 1',
                           'VariableType': 'Auto Assembler Script',
                           'AssemblerScript': source()}.items():
            ET.SubElement(entry, key).text = value
        cheat = self.root / 'own.ct'
        cheat.write_bytes(ET.tostring(root_el, encoding='utf-8',
                                      xml_declaration=True))
        plan = compile_table(cheat, 'Owned.exe')
        self.engine = TrainerEngine(plan, self.root / 'state',
                                    lambda name: self.memory,
                                    self.root / 'shared',
                                    hook_coordinator=Coordinator())
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.error)
        self.assertTrue(self.engine.toggle(1, True))
        self.pool = self.engine.global_pool
        self.hooks = self.root / 'state' / 'hooks'
        self.pool_journal = self.hooks / 'global-pool.json'

    def test_alive_target_refuses_retirement(self):
        with self.assertRaisesRegex(GlobalError,
                                    'Exact target death and original receipts are required\\.'):
            self.pool.finish_after_exit()
        self.assertEqual(self.pool.state, 'live')

    def test_tampered_pool_journal_refuses_retirement(self):
        self.memory.alive = False
        raw = self.pool_journal.read_bytes()
        self.pool_journal.write_bytes(raw + b'x')
        with self.assertRaisesRegex(GlobalError,
                                    'Exact target death and original receipts are required\\.'):
            self.pool.finish_after_exit()
        self.assertEqual(self.pool_journal.read_bytes(), raw + b'x')

    def test_changed_identity_refuses_retirement(self):
        self.memory.alive = False
        self.memory.identity = (999, 999)
        with self.assertRaisesRegex(GlobalError,
                                    'Exact target death and original receipts are required\\.'):
            self.pool.finish_after_exit()

    def test_released_controller_lock_refuses_retirement(self):
        self.memory.alive = False
        self.pool.controller_guard = lambda: False
        with self.assertRaisesRegex(GlobalError,
                                    'The controller lock must remain held during target-exit retirement\\.'):
            self.pool.finish_after_exit()
        self.assertEqual(self.pool.state, 'live')

    def test_exit_retirement_retains_terminal_journal_until_explicit_release(self):
        member_journal = next(self.hooks.glob('global-shared-*.json'))
        self.assertTrue(member_journal.exists())
        self.memory.alive = False
        self.pool.finish_after_exit(remove_journal=False)
        self.assertEqual(self.pool.state, 'target-exited')
        self.assertFalse(member_journal.exists())
        self.assertTrue(self.pool_journal.exists())
        document = json.loads(self.pool_journal.read_bytes())
        self.assertEqual(document['state'], 'target-exited')
        self.assertTrue(document['consumers'])
        self.assertTrue(all(consumer['state'] == 'target-exited'
                            for consumer in document['consumers']))
        self.assertEqual(self.memory.releases, [])

    def test_exit_retirement_releases_journal_and_blocks_later_pool_operations(self):
        self.memory.alive = False
        self.pool.finish_after_exit(remove_journal=True)
        self.assertFalse(self.pool_journal.exists())
        self.assertFalse(list(self.hooks.glob('global-shared-*.json')))
        with self.assertRaisesRegex(GlobalUncertain,
                                    'This pool is retired or uncertain\\.'):
            self.pool.symbols()
        with self.assertRaisesRegex(GlobalUncertain,
                                    'This pool is retired or uncertain\\.'):
            self.pool.diagnostic()


class GlobalJournalRecoveryBlockTests(unittest.TestCase):
    """Part B: crash recovery hard-blocks on global pool/member journals."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='native-global-b-')
        self.addCleanup(self.tmp.cleanup)
        self.fixture = _StateFixture(Path(self.tmp.name))

    def test_pool_journal_alone_blocks_with_exact_engine_reason(self):
        self.fixture = _StateFixture(Path(self.tmp.name), pool=True)
        assessment = self.fixture.assess()
        self.assertEqual(assessment.status, 'blocked')
        self.assertFalse(assessment.eligible)
        self.assertEqual(assessment.reasons,
                         ('global-pool.json: Unknown hook/Lua journal engine or schema',))
        self.assertIn(self.fixture.state / 'hooks' / 'global-pool.json',
                      assessment.candidate_paths)

    def test_member_journal_without_owner_suffix_blocks_with_binding_reason(self):
        self.fixture = _StateFixture(Path(self.tmp.name), member=True)
        assessment = self.fixture.assess()
        self.assertEqual(assessment.status, 'blocked')
        self.assertFalse(assessment.eligible)
        self.assertEqual(assessment.reasons,
                         ('global-shared-01234567.json: Unknown or unbound owned-hook schema',))

    def test_both_global_journals_report_both_reasons(self):
        self.fixture = _StateFixture(Path(self.tmp.name), pool=True, member=True)
        assessment = self.fixture.assess()
        self.assertEqual(assessment.status, 'blocked')
        self.assertFalse(assessment.eligible)
        self.assertEqual(sorted(assessment.reasons),
                         sorted(['global-pool.json: Unknown hook/Lua journal engine or schema',
                                 'global-shared-01234567.json: Unknown or unbound owned-hook schema']))

    def test_corrupt_pool_journal_is_reported_corrupt_not_unknown_engine(self):
        self.fixture = _StateFixture(Path(self.tmp.name), pool=True, corrupt_pool=True)
        assessment = self.fixture.assess()
        self.assertEqual(assessment.status, 'blocked')
        self.assertEqual(assessment.reasons,
                         ('global-pool.json: Recovery JSON is corrupt or ambiguous',))

    def test_valid_sibling_hook_journal_does_not_rescue_global_pool_journal(self):
        self.fixture = _StateFixture(Path(self.tmp.name), pool=True, valid_hook=True)
        assessment = self.fixture.assess()
        self.assertEqual(assessment.status, 'blocked')
        self.assertEqual(assessment.reasons,
                         ('global-pool.json: Unknown hook/Lua journal engine or schema',))

    def test_blocked_assessment_is_read_only_and_preserves_every_receipt(self):
        self.fixture = _StateFixture(Path(self.tmp.name), pool=True, member=True)
        originals = self.fixture.originals()
        before = {path: path.stat() for path in originals}
        before_listing = sorted(
            str(path.relative_to(self.fixture.root))
            for path in list(self.fixture.state.rglob('*'))
            + list(self.fixture.shared.rglob('*')))
        assessment = self.fixture.assess()
        self.assertEqual(assessment.status, 'blocked')
        self.assertFalse(assessment.eligible)
        self.assertTrue(assessment.read_only)
        self.assertFalse(assessment.mutation_authorized)
        self.assertEqual(self.fixture.originals(), originals)
        self.assertEqual({path: stat.st_mtime_ns for path, stat in before.items()},
                         {path: path.stat().st_mtime_ns for path in originals})
        after_listing = sorted(
            str(path.relative_to(self.fixture.root))
            for path in list(self.fixture.state.rglob('*'))
            + list(self.fixture.shared.rglob('*')))
        self.assertEqual(after_listing, before_listing)
        self.assertFalse((self.fixture.state / 'recovery.lock').exists())

    def test_blocked_assessment_refuses_recovery_before_any_claim(self):
        self.fixture = _StateFixture(Path(self.tmp.name), pool=True, member=True)
        originals = self.fixture.originals()
        assessment = self.fixture.assess()
        report = self.fixture.recover(assessment)
        self.assertEqual(report.status, 'refused')
        self.assertFalse(report.completed)
        self.assertEqual(report.released, ())
        self.assertIsNone(report.archive_path)
        self.assertIsNone(report.archive_sha256)
        self.assertIsNone(report.journal_path)
        self.assertIsNone(report.journal_sha256)
        self.assertFalse(report.fence_path.exists())
        self.assertFalse(self.fixture.archive.exists())
        self.assertEqual(report.reasons,
                         ('The supplied assessment is not an eligible read-only death proof',))
        self.assertEqual(self.fixture.originals(), originals)


class OwnerAndProbeBlockTests(unittest.TestCase):
    """Part C: owner/probe blocks on a clean journal-free state."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='native-global-c-')
        self.addCleanup(self.tmp.cleanup)
        self.fixture = _StateFixture(Path(self.tmp.name))

    def test_legacy_owner_lock_cannot_prove_owner_dead(self):
        self.fixture = _StateFixture(Path(self.tmp.name), legacy_owner=True)
        def probe(identity):
            if identity.created is None:
                return ProcessObservation(identity, 'absent')
            return _probe_dead(identity)
        assessment = self.fixture.assess(probe)
        self.assertEqual(assessment.status, 'blocked')
        self.assertIn(
            'Legacy owner lock has no creation time; automatic recovery '
            'cannot prove the exact owner dead', assessment.reasons)
        self.assertTrue(any(reason.startswith('Exact process 333/None')
                            for reason in assessment.reasons),
                        assessment.reasons)

    def test_live_owner_blocks_recovery_with_exact_status_reason(self):
        def probe(identity):
            if identity.pid == OWNER_PID:
                return ProcessObservation(identity, 'alive', identity.created,
                                          WAIT_TIMEOUT)
            return _probe_dead(identity)
        assessment = self.fixture.assess(probe)
        self.assertEqual(assessment.status, 'blocked')
        self.assertEqual(assessment.reasons,
                         ('Exact process 333/3333 is not proven dead in both '
                          'observations (alive, alive)',))

    def test_probe_failure_yields_unknown_and_blocks(self):
        def probe(identity):
            if identity.pid == OWNER_PID:
                raise RuntimeError('denied')
            return _probe_dead(identity)
        assessment = self.fixture.assess(probe)
        self.assertEqual(assessment.status, 'blocked')
        self.assertEqual(assessment.reasons,
                         ('Exact process 333/3333 is not proven dead in both '
                          'observations (unknown, unknown)',))

    def test_session_owner_mismatch_blocks_with_claim_reason(self):
        self.fixture = _StateFixture(
            Path(self.tmp.name),
            session_owner=_owner_document(pid=555, created=5555,
                                          nonce='d' * 32))
        assessment = self.fixture.assess()
        self.assertEqual(assessment.status, 'blocked')
        self.assertEqual(assessment.reasons,
                         ('Session owner differs from the state-lock owner',
                          'Session has no byte-identical shared target claim'))


@unittest.skipUnless(sys.platform == 'win32',
                     'Held-file recovery requires Windows')
class FencedRecoveryUncertaintyTests(unittest.TestCase):
    """Part D: post-fence evidence changes keep the fence (win32)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='native-global-d-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _state_with_dead_children(self):
        children, identities = _dead_child_pair()
        self.addCleanup(self._kill_leftovers, children)
        estate = _EngineState(self.root, _ORDINARY_SOURCE)
        _rebind_engine_state(estate, identities[0], identities[1])
        return estate

    def _kill_leftovers(self, children):
        for child in children:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)

    def test_reprobed_unknown_after_fencing_keeps_fence_archive_and_journal(
            self):
        estate = self._state_with_dead_children()
        assessment = assess_recovery(
            estate.state, estate.shared, process_probe=WindowsProcessProbe(),
            expected_trainer_id=estate.plan['trainer_id'],
            expected_table_sha256=estate.plan['table_sha256'])
        self.assertTrue(assessment.eligible, assessment.reasons)
        originals = _all_files(estate.state, estate.shared)
        calls = 0
        def flip_probe(identity):
            nonlocal calls
            calls += 1
            if calls <= 4:
                return _probe_dead(identity)
            return ProcessObservation(identity, 'unknown',
                                      detail='query failed')
        report = recover_assessment(
            assessment, self.root / 'evidence',
            expected_trainer_id=estate.plan['trainer_id'],
            expected_table_sha256=estate.plan['table_sha256'],
            process_probe=flip_probe)
        self.assertEqual(report.status, 'uncertain')
        self.assertEqual(report.released, ())
        self.assertTrue(report.fence_path.exists())
        self.assertTrue(report.archive_path is not None
                        and report.archive_path.exists())
        self.assertIsNotNone(report.archive_sha256)
        self.assertTrue(report.journal_path is not None
                        and report.journal_path.exists())
        self.assertEqual(report.reasons,
                         ('An exact owner or target is not proven dead '
                          'before file release',))
        for path, raw in originals.items():
            self.assertEqual(path.read_bytes(), raw, str(path))

    def test_changed_evidence_after_fencing_keeps_fence_and_all_originals(
            self):
        estate = self._state_with_dead_children()
        assessment = assess_recovery(
            estate.state, estate.shared, process_probe=WindowsProcessProbe(),
            expected_trainer_id=estate.plan['trainer_id'],
            expected_table_sha256=estate.plan['table_sha256'])
        self.assertTrue(assessment.eligible, assessment.reasons)
        originals = _all_files(estate.state, estate.shared)
        calls = 0
        def side_effect_probe(identity):
            nonlocal calls
            calls += 1
            if calls == 1:
                (estate.state / 'stray-evidence.json').write_bytes(
                    b'{"stray":true}')
            return _probe_dead(identity)
        report = recover_assessment(
            assessment, self.root / 'evidence',
            expected_trainer_id=estate.plan['trainer_id'],
            expected_table_sha256=estate.plan['table_sha256'],
            process_probe=side_effect_probe)
        self.assertEqual(report.status, 'uncertain')
        self.assertEqual(report.released, ())
        self.assertTrue(report.fence_path.exists())
        self.assertIsNone(report.archive_path)
        self.assertTrue(report.journal_path is not None
                        and report.journal_path.exists())
        self.assertTrue(
            report.reasons[0].startswith(
                'Recovery reassessment blocks release: Recovery hashes, '
                'file identities, or directory inventory changed during '
                'process proof'), report.reasons)
        for path, raw in originals.items():
            self.assertEqual(path.read_bytes(), raw, str(path))
        self.assertTrue((estate.state / 'stray-evidence.json').exists())


class GlobalDisableBudgetTests(unittest.TestCase):
    """Part E: restoration-budget semantics around the global disable path."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='native-global-e-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.clock = Clock()
        self.memory = Memory()
        root_el = ET.Element('CheatTable', CheatEngineTableVersion='45')
        entries = ET.SubElement(root_el, 'CheatEntries')
        entry = ET.SubElement(entries, 'CheatEntry')
        for key, value in {'ID': '1', 'Description': 'Own 1',
                           'VariableType': 'Auto Assembler Script',
                           'AssemblerScript': source()}.items():
            ET.SubElement(entry, key).text = value
        cheat = self.root / 'own.ct'
        cheat.write_bytes(ET.tostring(root_el, encoding='utf-8',
                                      xml_declaration=True))
        plan = compile_table(cheat, 'Owned.exe')
        self.engine = TrainerEngine(plan, self.root / 'state',
                                    lambda name: self.memory,
                                    self.root / 'shared',
                                    hook_coordinator=Coordinator())
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.error)
        self.engine._clock = self.clock
        self.assertTrue(self.engine.toggle(1, True))

    def test_disable_within_budget_hides_symbol_and_retains_storage(self):
        base = self.engine.symbols['shared']
        self.assertEqual(self.memory.read(base, 4).hex(), '64000000')
        self.assertFalse(self.engine.toggle(1, False))
        self.assertNotIn(1, self.engine.applied)
        self.assertFalse(self.engine.blocked, self.engine.error)
        self.assertNotIn('shared', self.engine.symbols)
        self.assertEqual(self.memory.read(base, 4).hex(), '64000000')
        self.assertEqual(self.memory.read(0x1000, 5).hex(), 'b801000000')
        self.assertEqual(self.memory.releases, [])
        self.assertEqual(self.clock.value, 100.0)

    def test_budget_expiry_inside_disable_write_marks_journal_uncertain_and_blocks(self):
        base = self.engine.symbols['shared']
        self.memory.before_write = lambda address, raw: self.clock.advance(31)
        with self.assertRaisesRegex(NativeRuntimeError,
                                    'Hook mutation is uncertain.*'
                                    'retain uncertain receipts'):
            self.engine.toggle(1, False)
        self.assertTrue(self.engine.blocked)
        self.assertTrue(self.engine.error.startswith(
            'Executable disable is uncertain'), self.engine.error)
        self.assertIn('retain uncertain receipts', self.engine.error)
        lease = self.engine.global_leases[1]
        manager = lease._manager
        self.assertTrue(manager.uncertain)
        self.assertEqual(manager.state, 'uncertain')
        document = json.loads(manager.path.read_bytes())
        self.assertEqual(document['state'], 'uncertain')
        self.assertTrue(document['uncertain'])
        self.assertEqual(self.memory.read(base, 4).hex(), '64000000')
        self.assertEqual(self.memory.releases, [])
        with self.assertRaisesRegex(NativeRuntimeError,
                                    'Executable disable is uncertain'):
            self.engine.toggle(1, True)
        self.assertTrue(self.engine.blocked)

    def test_nested_restoration_operations_share_one_unextendable_deadline(self):
        clock = Clock()
        with restoration_operation(clock, timeout=30) as outer:
            outer.begin()
            self.assertEqual(outer.deadline, 130.0)
            with restoration_operation(clock, timeout=120) as inner:
                self.assertIs(inner, outer)
                self.assertEqual(outer.deadline, 130.0)
            clock.advance(31)
            with self.assertRaisesRegex(RestorationBudgetError,
                                        'Shared restoration deadline exceeded'):
                outer.check()


@unittest.skipUnless(sys.platform == 'win32',
                     'Real-dead process recovery requires Windows')
class RealDeathContrastTests(unittest.TestCase):
    """Part F: identical engine state without a global journal recovers clean."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='native-global-f-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _kill_leftovers(self, children):
        for child in children:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)

    def test_engine_generated_state_recovers_clean_with_real_dead_children(self):
        children, identities = _dead_child_pair()
        self.addCleanup(self._kill_leftovers, children)
        estate = _EngineState(self.root, _ORDINARY_SOURCE)
        _rebind_engine_state(estate, identities[0], identities[1])
        trainer_id = estate.plan['trainer_id']
        table_sha = estate.plan['table_sha256']
        assessment = assess_recovery(
            estate.state, estate.shared, process_probe=WindowsProcessProbe(),
            expected_trainer_id=trainer_id, expected_table_sha256=table_sha)
        self.assertEqual(assessment.status, 'eligible-read-only',
                         assessment.reasons)
        self.assertTrue(assessment.eligible)
        self.assertTrue(assessment.read_only)
        originals = _all_files(estate.state, estate.shared)
        report = recover_assessment(
            assessment, self.root / 'evidence', expected_trainer_id=trainer_id,
            expected_table_sha256=table_sha,
            process_probe=WindowsProcessProbe())
        self.assertEqual(report.status, 'completed', report.reasons)
        self.assertTrue(report.completed)
        self.assertEqual(set(report.released), set(assessment.candidate_paths))
        self.assertEqual(report.released[-1], estate.state / 'state.lock')
        self.assertFalse(report.fence_path.exists())
        self.assertTrue(report.archive_path is not None
                        and report.archive_path.exists())
        self.assertEqual(hashlib.sha256(report.archive_path.read_bytes()).hexdigest(),
                         report.archive_sha256)
        self.assertTrue(report.journal_path is not None
                        and report.journal_path.exists())
        self.assertFalse(report.remote_writes)
        self.assertTrue(report.fence_released)
        self.assertEqual((estate.state / 'state.json').read_bytes(),
                         originals[estate.state / 'state.json'])
        self.assertEqual(_all_files(estate.state),
                         {estate.state / 'state.json':
                          originals[estate.state / 'state.json']})
        self.assertEqual(_all_files(estate.shared), {})
        reassess = assess_recovery(
            estate.state, estate.shared, process_probe=WindowsProcessProbe(),
            expected_trainer_id=trainer_id, expected_table_sha256=table_sha)
        self.assertEqual(reassess.status, 'clean', reassess.reasons)
        self.assertFalse(reassess.eligible)


if __name__ == '__main__':
    unittest.main()
