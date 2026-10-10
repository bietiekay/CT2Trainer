"""Independent N11 contract tests, using first-party fake target ownership."""
from __future__ import annotations
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from ct2trainer.native import global_alloc as ga
from test_native_hooks import _Memory, _Coordinator
from ct2trainer.native import aa_program as aa


def source(*, entry=0x1000, initializer=True, size=4, name='shared', near=None, bitness=64):
    declaration = f'globalalloc({name},{size:X}' + (f',0x{near:X}' if near is not None else '') + ')'
    original = 'B8 01 00 00 00' if entry == 0x1000 else '90 90 90 90 90'
    init = f'{name}:\ndd #17\n' if initializer else ''
    register = 'rcx' if bitness == 64 else 'ecx'
    return f'[ENABLE]\nlabel(done)\n{declaration}\n{init}alloc(cave,1000)\ncave:\nmov {register},{name}\nmov eax,[{register}]\njmp done\n0x{entry:X}:\njmp cave\ndone:\n[DISABLE]\n0x{entry:X}:\ndb {original}\ndealloc(cave)\ndealloc({name})'


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.memory = _Memory()
        self.pool = ga.GlobalPool(self.memory, self.tmp.name, trainer_id='1'*16,
                                  table_sha256='2'*64, controller_guard=lambda: True)
        self.counter = 0

    def acquire(self, text=None, **kwargs):
        self.counter += 1
        return self.pool.acquire(ga.prepare_global_program(text or source()), record_id=63,
                                 activation=f'activation-{self.counter}', **kwargs)

    def publish(self, lease):
        program = self.pool.binding(lease)
        manager = self.pool.make_consumer(lease, Path(self.tmp.name)/f'consumer-{self.counter}.json',
                                          coordinator=_Coordinator())
        preflight = aa.preflight_program(program, self.memory)
        for request in preflight['allocation_requests']:
            manager.allocate(request['name'], request['size'], request['near'],
                             executable=request['executable'], writable=request['writable'])
        linked = aa.link_program(program, self.memory, preflight['symbols'], manager.allocation_map())
        manager.stage(linked['blocks'], linked['exports'])
        manager.publish()
        self.pool.confirm_enabled(lease, program)
        return manager

    def test_source_bound_literal_ir_and_no_pointer_input(self):
        p = ga.prepare_global_program(source())
        self.assertEqual(p['globals'][0]['initializer'], '11000000')
        self.assertNotIn('globalalloc', p['consumer_source'])
        self.assertNotIn('shared:\n', p['consumer_source'])
        self.assertNotIn('dealloc(shared)', p['consumer_source'])
        changed = copy.deepcopy(p)
        changed['globals'][0]['size'] = 0x1000
        with self.assertRaisesRegex(ga.GlobalError, 'exact original source'):
            ga.validate_global_program(changed)
        with self.assertRaises(ga.GlobalError):
            ga.GlobalLease(object(), self.pool, p, 63, 'fake')
        with self.assertRaises(ga.GlobalError):
            self.pool.binding({'address': 0x10000})

    def test_active_real_manager_release_and_pointer_retention(self):
        lease = self.acquire()
        manager = self.publish(lease)
        base = self.pool.diagnostic()['members'][0]['address']
        with self.assertRaisesRegex(ga.GlobalError, 'must be restored'):
            self.pool.release(lease)
        manager.disable()
        self.pool.release(lease)
        self.assertEqual(self.memory.releases, [])
        self.assertEqual(self.memory.read(base, 4), b'\x11\0\0\0')
        again = self.acquire()
        self.assertEqual(self.pool.binding(again)['preamble'][0]['expression'], f'0x{base:X}')
        self.assertEqual(len(self.pool.members), 1)

    def test_second_consumer_reuses_only_without_initializer(self):
        one = self.acquire()
        first = self.publish(one)
        with self.assertRaisesRegex(ga.GlobalError, 'another consumer'):
            self.acquire()
        two = self.acquire(source(entry=0x2000, initializer=False))
        second = self.publish(two)
        self.assertEqual(len(self.pool.members), 1)
        first.disable()
        self.pool.release(one)
        self.assertEqual(two.state, 'enabled')
        second.check_entries()
        second.disable()
        self.pool.release(two)
        self.assertEqual(self.memory.releases, [])

    def test_changed_initializer_refused_after_last_consumer(self):
        one = self.acquire()
        self.pool.release(one)
        base = self.pool.members['shared']['address']
        self.memory.write(base, b'\x13\0\0\0')
        with self.assertRaisesRegex(ga.GlobalError, 'Changed global reinitialization'):
            self.acquire()
        reader = self.acquire(source(initializer=False))
        self.assertEqual(self.pool.members['shared']['address'], base)
        self.pool.release(reader)

    def test_size_near_protection_names_and_foreign_provider_collisions(self):
        lease = self.acquire(source(near=0x1000))
        self.pool.release(lease)
        for altered in (source(size=8, near=0x1000), source(near=0x2000), source()):
            with self.assertRaisesRegex(ga.GlobalError, 'resized, relocated'):
                self.acquire(altered)
        self.pool.external_symbols = lambda: {'SHARED': 0x1234}
        with self.assertRaises(ga.GlobalUncertain):
            self.pool.diagnostic()

    def test_changed_allocation_protection_blocks_with_receipts_retained(self):
        self.acquire()
        base = self.pool.members['shared']['address']
        self.memory.allocation_protections[base] = 0x40
        with self.assertRaises(ga.GlobalUncertain):
            self.pool.diagnostic()
        self.assertEqual(self.memory.releases, [])
        self.assertTrue(self.pool.path.exists())

    def test_bitness_mismatch_before_allocation_and_pid_reuse_fail_closed(self):
        with self.assertRaisesRegex(ga.GlobalError, 'architecture'):
            self.pool.acquire(ga.prepare_global_program(source(), bitness=32),
                              record_id=1, activation='x86')
        self.assertEqual(self.memory.allocations, {})
        self.memory.identity = (123, 789)
        with self.assertRaises(ga.GlobalUncertain):
            self.pool.diagnostic()
        with self.assertRaises(ga.GlobalError):
            self.pool.finish_after_exit()

    def test_failed_enable_releases_lease_only_after_exact_abandon(self):
        one = self.acquire()
        self.pool.binding(one)
        manager = self.pool.make_consumer(one, Path(self.tmp.name)/'consumer-failed.json')
        with self.assertRaises(ga.GlobalError):
            self.pool.release(one)
        manager.abandon_unpublished()
        self.pool.release(one)
        self.assertEqual(one.state, 'released')
        self.assertEqual(self.memory.releases, [])
        self.assertTrue(self.pool.members['shared']['manager'].path.exists())

    def test_foreign_manager_and_tampered_binding_do_not_confirm(self):
        one = self.acquire()
        program = self.pool.binding(one)
        altered = copy.deepcopy(program)
        altered['source'] = altered['source'].replace('mov eax', 'mov ebx')
        with self.assertRaises(Exception):
            self.pool.confirm_enabled(one, altered)
        with self.assertRaisesRegex(ga.GlobalError, 'has not published'):
            self.pool.confirm_enabled(one, program)
        other = ga.GlobalPool(self.memory, Path(self.tmp.name)/'other', trainer_id='3'*16,
                               table_sha256='4'*64, controller_guard=lambda: True)
        with self.assertRaisesRegex(ga.GlobalError, 'exact live consumer'):
            other.binding(one)

    def test_crash_reopen_and_journal_mutation_preserve_storage(self):
        self.acquire()
        before = self.pool.path.read_bytes()
        with self.assertRaises(FileExistsError):
            ga.GlobalPool(self.memory, self.tmp.name, trainer_id='1'*16,
                          table_sha256='2'*64, controller_guard=lambda: True)
        self.assertEqual(self.pool.path.read_bytes(), before)
        self.pool.path.write_bytes(b'foreign journal')
        with self.assertRaises(ga.GlobalUncertain):
            self.pool.diagnostic()
        self.assertEqual(self.pool.path.read_bytes(), b'foreign journal')
        self.assertEqual(self.memory.releases, [])

    def test_exact_target_exit_only_finishes_receipts_no_remote_free(self):
        self.acquire()
        with self.assertRaises(ga.GlobalError):
            self.pool.finish_after_exit()
        self.memory.alive = False
        self.pool.finish_after_exit()
        self.assertEqual(self.pool.state, 'target-exited')
        self.assertEqual(self.memory.releases, [])
        self.assertTrue(self.pool.path.exists())

    def test_bound_counts_and_cross_thread_refusal(self):
        self.acquire()
        errors = []
        def run():
            try: self.pool.diagnostic()
            except Exception as exc: errors.append(exc)
        thread = threading.Thread(target=run)
        thread.start(); thread.join(2)
        self.assertIsInstance(errors[0], ga.GlobalError)
        with self.assertRaises(ga.GlobalError):
            ga.prepare_global_program(source(size=65537))
        with self.assertRaises(ga.GlobalError):
            ga.prepare_global_program(source().replace('dealloc(shared)', 'dealloc(*)'))

    def test_code_readmem_symbolic_and_cross_range_initializers_refused(self):
        for value in ('readmem(0x1000,4)', 'nop', 'dq 0', 'dd shared', 'align 10', 'dd 1 2'):
            with self.assertRaises(Exception):
                ga.prepare_global_program(source().replace('dd #17', value))
        with self.assertRaises(ga.GlobalError):
            ga.prepare_global_program(source().replace('shared:', 'shared+1:'))

    def test_alias_cursors_and_stripped_cleanup_cannot_bypass_initializer_policy(self):
        for declarations, cursor in (('define(alias,shared)', 'alias'),
                                     ('define(alias,shared+1)', 'alias'),
                                     ('define(alias,other)\ndefine(other,shared)', 'alias')):
            text = source(initializer=False).replace('alloc(cave,1000)', declarations + f'\n{cursor}:\ndd #19\nalloc(cave,1000)')
            with self.assertRaisesRegex(ga.GlobalError, 'direct global cursor'):
                ga.prepare_global_program(text)
        text = source().replace('globalalloc(shared,4)', 'globalalloc(shared,4)\nunregistersymbol(shared)')
        with self.assertRaisesRegex(ga.GlobalError, 'ENABLE/DISABLE'):
            ga.prepare_global_program(text)

    def test_numeric_global_alias_write_refused_before_target_mutation(self):
        owner = self.acquire()
        self.pool.release(owner)
        base = self.pool.members['shared']['address']
        # Numeric source binding cannot conceal a global entry from the exact
        # publication range gate, even though static alias closure has no name.
        text = f'[ENABLE]\nglobalalloc(shared,4)\n0x{base:X}:\ndd #19\n[DISABLE]\n0x{base:X}:\ndd #17\ndealloc(shared)'
        lease = self.acquire(text)
        with self.assertRaisesRegex(ga.GlobalError, 'cannot rewrite pool globals'):
            self.publish(lease)
        self.assertEqual(self.memory.read(base,4), (17).to_bytes(4,'little'))

    def test_same_entry_consumer_overlap_refused_before_second_publication(self):
        one = self.acquire()
        first = self.publish(one)
        original = self.memory.read(0x1000,5)
        two = self.acquire(source(initializer=False))
        with self.assertRaisesRegex(ga.GlobalError, 'cannot overlap live entry'):
            self.publish(two)
        self.assertEqual(self.memory.read(0x1000,5), original)
        first.check_entries()

    def test_unknown_owner_probe_and_failed_journal_commit_are_sticky(self):
        self.pool.controller_guard = lambda: (_ for _ in ()).throw(OSError('unknown owner proof'))
        with self.assertRaises(ga.GlobalUncertain):
            self.pool.diagnostic()
        self.pool.controller_guard = lambda: True
        with self.assertRaises(ga.GlobalUncertain):
            self.pool.diagnostic()

    def test_replace_failure_keeps_original_and_temp_receipts_no_allocation(self):
        original = self.pool.path.read_bytes()
        with patch.object(ga.os, 'replace', side_effect=OSError('fixture journal replace failure')):
            with self.assertRaises(ga.GlobalUncertain):
                self.acquire()
        self.assertEqual(self.pool.path.read_bytes(), original)
        self.assertTrue(list(self.pool.path.parent.glob('global-pool.json.*.tmp')))
        self.assertEqual(self.memory.allocations, {})
        self.assertEqual(self.pool.state, 'uncertain')

    def test_allocation_uncertainty_preserves_exact_intent_and_never_frees(self):
        original_allocate = self.memory.allocate
        def ambiguous(size, near=None):
            original_allocate(size, near)
            raise OSError('fixture post-allocation unknown receipt')
        self.memory.allocate = ambiguous
        with self.assertRaises(ga.GlobalUncertain):
            self.acquire()
        journal = json.loads(self.pool.path.read_bytes())
        self.assertEqual(journal['state'], 'uncertain')
        self.assertEqual(journal['pending'][0]['name'], 'shared')
        self.assertTrue(Path(journal['pending'][0]['journal']).exists())
        self.assertEqual(self.memory.releases, [])

    def test_alias_graph_shared_references_are_memoized_and_cycles_refuse(self):
        declarations = ['define(alias0,0)'] + [f'define(alias{i},alias{i-1}+alias{i-1})' for i in range(1,32)]
        text = source(initializer=False).replace('alloc(cave,1000)', '\n'.join(declarations)+'\nalias31:\ndd 0\nalloc(cave,1000)')
        ga.prepare_global_program(text)  # bounded DAG: no exponential closure expansion
        cyclic = source(initializer=False).replace('alloc(cave,1000)', 'define(aliasOne,aliasTwo)\ndefine(aliasTwo,aliasOne)\naliasOne:\ndd 0\nalloc(cave,1000)')
        with self.assertRaisesRegex(ga.GlobalError, 'Cyclic cursor aliases'):
            ga.prepare_global_program(cyclic)

    def test_combined_retained_consumer_budget_refuses_before_new_allocation(self):
        one = self.acquire()
        first = self.publish(one)
        two = self.acquire(source(entry=0x2000,initializer=False))
        self.pool.binding(two)
        before = dict(self.memory.allocations)
        with patch.object(ga, 'MAX_HOOK_ALLOCATIONS', 2):
            with self.assertRaisesRegex(ga.GlobalError, 'Combined global and retained consumer'):
                self.pool.make_consumer(two, Path(self.tmp.name)/'over-budget.json')
        self.assertEqual(self.memory.allocations, before)
        self.assertFalse((Path(self.tmp.name)/'over-budget.json').exists())
        first.check_entries()

    def test_oversized_foreign_journal_is_bounded_and_retained(self):
        self.acquire()
        self.pool.path.write_bytes(b'X' * 4097)
        with patch.object(ga, 'MAX_POOL_JOURNAL_BYTES', 4096):
            with self.assertRaises(ga.GlobalUncertain):
                self.pool.diagnostic()
        self.assertEqual(self.pool.path.stat().st_size,4097)
        self.assertEqual(self.memory.releases,[])

    def test_owned_synthetic_global_profiles_do_not_need_game_sources(self):
        # First-party grammar contracts keep the redistributable test suite
        # independent of the locally inspected, separately owned CT corpus.
        for bitness, initializer in ((32, 17), (64, 160)):
            with self.subTest(bitness=bitness, initializer=initializer):
                program = ga.prepare_global_program(
                    source(bitness=bitness).replace('dd #17', f'dd #{initializer}'),
                    bitness=bitness)
                self.assertEqual(program['globals'][0]['initializer'],
                                 initializer.to_bytes(4, 'little').hex())
        unbound = ga.prepare_global_program(source(bitness=32).replace(
            'mov ecx,shared', 'call UnboundOwnedAPI\nmov ecx,shared'), bitness=32)
        self.assertEqual(unbound['requires'], ['UnboundOwnedAPI'])
        refused = {
            'empty_initializer': source().replace('dd #17', ''),
            'readmem_initializer': source().replace('dd #17', 'readmem(0x3000,4)'),
            'executable_initializer': source().replace('dd #17', 'mov eax,#17'),
        }
        for name, text in refused.items():
            with self.subTest(profile=name):
                with self.assertRaises((ga.GlobalError, aa.ProgramError)):
                    ga.prepare_global_program(text)


if __name__ == '__main__':
    unittest.main()
