"""RT-4.5 (O19/O21) contract tests for shared-global reset semantics.

Pins:
- a direct cursor on an initialized global in DISABLE starts a no-op reset
  region whose bytes must repeat the exact ENABLE initializer (equal or
  empty is accepted, changed bytes are refused with a named reason);
- after literal data is consumed under the cursor, the first non-literal
  line closes the global region and returns to consumer semantics (O21);
- a record whose whole body is global declaration/initializer/reset lines
  gets the canonical empty consumer program, round-trips through the
  manager-less pool flow (prepare -> acquire -> bind -> confirm -> release)
  and through plan validation, and re-arms against the retained member.

Self-contained synthetic sources; no original tables, no CE inputs.
"""
import hashlib
import tempfile
import unittest

from ct2trainer.native import global_alloc as ga
from test_native_hooks import _Memory


PROCESS = 'FixtureTarget.exe'

MATCHING = (
    '[ENABLE]\n'
    'globalalloc(fov,4)\n'
    'fov:\n'
    'dd (float)80\n'
    'label(done)\n'
    'alloc(cave,1000)\n'
    'cave:\n'
    'mov rcx,fov\n'
    'mov eax,[rcx]\n'
    'jmp done\n'
    '0x1000:\n'
    'jmp cave\n'
    'done:\n'
    '[DISABLE]\n'
    'fov:\n'
    'dd (float)80\n'
    '0x1000:\n'
    'db B8 01 00 00 00\n'
    'dealloc(cave)\n'
    'dealloc(fov)'
)

EXPECTED_CONSUMER = (
    '[ENABLE]\n'
    'label(done)\n'
    'alloc(cave,1000)\n'
    'cave:\n'
    'mov rcx,fov\n'
    'mov eax,[rcx]\n'
    'jmp done\n'
    '0x1000:\n'
    'jmp cave\n'
    'done:\n'
    '[DISABLE]\n'
    '0x1000:\n'
    'db B8 01 00 00 00\n'
    'dealloc(cave)'
)


def _source(**kw):
    base = dict(name='flag', size=1, init='db 1', reset='db 1',
                enable_tail='label(done)\nalloc(cave,1000)\ncave:\n'
                            'mov rcx,flag\nmov eax,[rcx]\njmp done\n'
                            '0x1000:\njmp cave\ndone:\n')
    base.update(kw)
    return ('[ENABLE]\n'
            f"globalalloc({base['name']},{base['size']:X})\n"
            f"{base['name']}:\n{base['init']}\n"
            + base['enable_tail'] +
            '[DISABLE]\n'
            f"{base['name']}:\n{base['reset']}\n"
            '0x1000:\ndb B8 01 00 00 00\n'
            'dealloc(cave)\n'
            f"dealloc({base['name']})")


class ResetRegionTests(unittest.TestCase):
    def test_matching_reset_is_stripped_and_initializer_kept(self):
        profile = ga.prepare_global_program(MATCHING, PROCESS, bitness=64)
        self.assertEqual(profile['globals'][0]['initializer'], '0000a042')
        self.assertFalse(profile.get('consumer_empty'))
        self.assertEqual(profile['consumer_source'], EXPECTED_CONSUMER)
        # the reset lines and the shared dealloc left no consumer content
        self.assertNotIn('fov:', profile['consumer_source'])
        self.assertNotIn('dealloc(fov)', profile['consumer_source'])
        # plan round-trip stays byte-identical
        self.assertEqual(ga.validate_global_program(profile), profile)

    def test_changed_reset_bytes_are_refused_named(self):
        with self.assertRaisesRegex(
                ga.GlobalError,
                r'Global DISABLE re-initialization must repeat the exact ENABLE'
                r' initializer bytes; the changed value stays blocked: flag'):
            ga.prepare_global_program(
                _source(reset='db 0'), PROCESS, bitness=64)

    def test_empty_reset_region_is_a_noop(self):
        source = (_source().replace('flag:\ndb 1\n0x1000:',
                                    'flag:\n0x1000:')
                  .replace('flag:\ndb 1\n0x1000:', 'flag:\n0x1000:', 1))
        # single region: cursor opens, next cursor (0x1000:) closes it empty
        profile = ga.prepare_global_program(source, PROCESS, bitness=64)
        self.assertEqual(profile['globals'][0]['initializer'], '01')
        self.assertNotIn('flag:', profile['consumer_source'])

    def test_reset_of_never_initialized_global_is_refused(self):
        source = _source(init='').replace('flag:\n\ndone_tail', '')
        source = ('[ENABLE]\n'
                  'globalalloc(flag,1)\n'
                  'alloc(cave,1000)\ncave:\nmov rcx,flag\nmov eax,[rcx]\n'
                  'jmp done\n0x1000:\njmp cave\ndone:\n'
                  '[DISABLE]\nflag:\ndb 1\n0x1000:\ndb B8 01 00 00 00\n'
                  'dealloc(cave)\ndealloc(flag)')
        with self.assertRaisesRegex(
                ga.GlobalError,
                r'Global initialization requires one direct ENABLE cursor\.'):
            ga.prepare_global_program(source, PROCESS, bitness=64)

    def test_non_literal_reset_data_is_refused(self):
        source = _source().replace('flag:\ndb 1\n0x1000:',
                                  'flag:\nmov eax,[flag]\n0x1000:')
        with self.assertRaisesRegex(
                ga.GlobalError,
                r'Global DISABLE reset data must repeat the literal ENABLE'
                r' initializer \(db/dw/dd/dq only\)\.'):
            ga.prepare_global_program(source, PROCESS, bitness=64)

    def test_oversized_reset_is_refused(self):
        with self.assertRaisesRegex(
                ga.GlobalError,
                r'Global DISABLE reset crosses the declared global storage'
                r' size: flag'):
            ga.prepare_global_program(_source(reset='db 1\ndb 1'), PROCESS,
                                      bitness=64)

    def test_double_reset_region_is_refused(self):
        source = _source().replace('flag:\ndb 1\n0x1000:',
                                  'flag:\ndb 1\nflag:\ndb 1\n0x1000:')
        with self.assertRaisesRegex(
                ga.GlobalError,
                r'A global reset must be a single contiguous DISABLE region: flag'):
            ga.prepare_global_program(source, PROCESS, bitness=64)

    def test_readmem_under_reset_cursor_is_refused(self):
        # readmem under a global cursor is the staged-readmem shape, which is
        # reserved for ENABLE; in DISABLE the established staged gate fires
        # before the reset bookkeeping.
        source = _source().replace('flag:\ndb 1\n0x1000:',
                                  'flag:\nreadmem(flag,4)\n0x1000:')
        with self.assertRaisesRegex(
                ga.GlobalError,
                r'Staged global readmem under a global cursor requires the'
                r' ENABLE section\.'):
            ga.prepare_global_program(source, PROCESS, bitness=64)


class LabelRegionBoundaryTests(unittest.TestCase):
    def test_label_before_data_stays_refused(self):
        source = _source().replace('flag:\ndb 1\n',
                                  'flag:\nlabel(mid)\ndb 1\n')
        with self.assertRaisesRegex(
                ga.GlobalError,
                'Labels inside a global initializer are outside the direct'
                r' literal profile\.'):
            ga.prepare_global_program(source, PROCESS, bitness=64)

    def test_label_after_data_closes_the_region(self):
        source = _source().replace('label(done)\nalloc',
                                  'alloc') \
                          .replace('flag:\ndb 1\n', 'flag:\ndb 1\nlabel(mid)\n')
        profile = ga.prepare_global_program(source, PROCESS, bitness=64)
        self.assertIn('label(mid)\n', profile['consumer_source'])
        self.assertNotIn('flag:', profile['consumer_source'])

    def test_instruction_after_data_closes_the_region(self):
        source = _source().replace('flag:\ndb 1\n',
                                  'flag:\ndb 1\nmov rax,flag\n')
        profile = ga.prepare_global_program(source, PROCESS, bitness=64)
        self.assertIn('mov rax,flag\n', profile['consumer_source'])
        # subsequent data no longer lands in the global initializer
        self.assertEqual(profile['globals'][0]['initializer'], '01')


class EmptyConsumerProfileTests(unittest.TestCase):
    SOURCE = ('[ENABLE]\n'
              'globalalloc(bshowhidelua,1)\n'
              'bshowhidelua:\n'
              'db 1\n'
              '[DISABLE]\n'
              'bshowhidelua:\n'
              'db 1\n')

    def test_canonical_empty_consumer_shape(self):
        profile = ga.prepare_global_program(self.SOURCE, PROCESS, bitness=64)
        self.assertTrue(profile['consumer_empty'])
        self.assertEqual(profile['consumer_source'], '[ENABLE]\n[DISABLE]')
        # the canonical empty program is deterministic from the alias-prefixed
        # consumer source; the pool test pins the instance bound to the live
        # member address.
        alias_source = ga._alias_source(profile['consumer_source'],
                                        {'bshowhidelua': 0x10000})
        self.assertEqual(alias_source,
                         'define(bshowhidelua,0x10000)\n[ENABLE]\n[DISABLE]')
        canonical = ga.empty_consumer_program(alias_source, PROCESS, 64)
        self.assertTrue(canonical['one_shot'])
        self.assertEqual(canonical['enable'], [])
        self.assertEqual(canonical['disable'], [])
        self.assertEqual(canonical['source_sha256'],
                         hashlib.sha256(alias_source.encode('utf-8')).hexdigest())
        self.assertEqual(profile['provides'], ['bshowhidelua'])
        self.assertEqual(profile['consumer_shape']['requires_coordinator'],
                         False)
        # byte-verifiable plan round-trip
        self.assertEqual(ga.validate_global_program(profile), profile)


def _pool_flow(memory, directory, profile, activation):
    """The exact engine sequence for a global record, manager-less if empty."""
    capture, resolved = ga.GlobalScanCapture.prepare(
        profile, memory, {}, lambda: True)
    pool = ga.GlobalPool(memory, directory, trainer_id='1' * 16,
                         table_sha256='2' * 64,
                         controller_guard=lambda: True)
    lease = pool.acquire(profile, record_id=7, activation=activation,
                         symbols=resolved['symbols'])
    program = pool.binding(lease)
    capture.bind(profile, program)
    pool.confirm_enabled(lease, program)
    return pool, lease, program


class EmptyConsumerPoolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.memory = _Memory()
        self.profile = ga.prepare_global_program(
            EmptyConsumerProfileTests.SOURCE, PROCESS, bitness=64)

    def test_manager_less_round_trip(self):
        pool, lease, program = _pool_flow(
            self.memory, self.tmp.name, self.profile, 'act-1')
        address = pool.members['bshowhidelua']['address']
        self.assertIsNone(lease._manager)
        self.assertTrue(program['one_shot'])
        self.assertEqual(program['enable'], [])
        self.assertEqual(program['disable'], [])
        self.assertEqual(pool.symbols(), {'bshowhidelua': address})
        # the acquisition itself is the whole activation: initializer landed
        self.assertEqual(self.memory.read(address, 1), b'\x01')
        pool.release(lease)
        self.assertEqual(lease.state, 'released')
        # retired members are retained for the target lifetime
        self.assertIn('bshowhidelua', pool.members)
        self.assertNotIn('bshowhidelua', pool.symbols())

    def test_reenable_after_release_and_changed_initializer_refusal(self):
        pool, lease, _ = _pool_flow(
            self.memory, self.tmp.name, self.profile, 'act-1')
        address = pool.members['bshowhidelua']['address']
        pool.release(lease)
        capture2, resolved2 = ga.GlobalScanCapture.prepare(
            self.profile, self.memory, {}, lambda: True)
        lease2 = pool.acquire(self.profile, record_id=7, activation='act-2',
                              symbols=resolved2['symbols'])
        program2 = pool.binding(lease2)
        capture2.bind(self.profile, program2)
        pool.confirm_enabled(lease2, program2)
        self.assertEqual(lease2.state, 'enabled')
        self.assertEqual(self.memory.read(address, 1), b'\x01')
        # a second release leaves the member retained but unconsumed
        pool.release(lease2)
        # externally changed storage refuses re-initialization
        self.memory.write(address, b'\x02')
        with self.assertRaisesRegex(
                ga.GlobalError,
                'Changed global reinitialization requires a future verified'
                r' data-commit profile\.'):
            pool.acquire(self.profile, record_id=7, activation='act-3',
                         symbols=resolved2['symbols'])

    def test_bind_refuses_a_tampered_consumer(self):
        pool, lease, program = _pool_flow(
            self.memory, self.tmp.name, self.profile, 'act-1')
        tampered = dict(program)
        tampered['source'] = program['source'] + '\ndefine(foreign,0x2)'
        capture, _ = ga.GlobalScanCapture.prepare(
            self.profile, self.memory, {}, lambda: True)
        with self.assertRaisesRegex(
                ga.GlobalError,
                'Consumer differs from the exact original body and literal'
                r' alias binding\.'):
            capture.bind(self.profile, tampered)

    def test_confirm_refuses_a_foreign_program(self):
        pool, lease, program = _pool_flow(
            self.memory, self.tmp.name, self.profile, 'act-1')
        pool.release(lease)
        pool2 = ga.GlobalPool(self.memory, self.tmp.name + '_second',
                              trainer_id='1' * 16, table_sha256='2' * 64,
                              controller_guard=lambda: True)
        lease2 = pool2.acquire(self.profile, record_id=8, activation='act-9',
                               symbols={})
        foreign = dict(program)
        foreign['source'] = program['source'].replace('0x10000', '0x20000')
        with self.assertRaisesRegex(
                ga.GlobalError,
                r'A consumer cannot confirm a different source/address binding\.'):
            pool2.confirm_enabled(lease2, foreign)

    def test_non_empty_confirm_still_requires_a_transaction(self):
        profile = ga.prepare_global_program(
            _source(), PROCESS, bitness=64)
        self.assertFalse(profile.get('consumer_empty'))
        capture, resolved = ga.GlobalScanCapture.prepare(
            profile, self.memory, {}, lambda: True)
        pool = ga.GlobalPool(self.memory, self.tmp.name, trainer_id='1' * 16,
                             table_sha256='2' * 64,
                             controller_guard=lambda: True)
        lease = pool.acquire(profile, record_id=9, activation='act-8',
                             symbols=resolved['symbols'])
        program = pool.binding(lease)
        with self.assertRaisesRegex(
                ga.GlobalError,
                r'The exact consumer transaction has not published\.'):
            pool.confirm_enabled(lease, program)


if __name__ == '__main__':
    unittest.main()
