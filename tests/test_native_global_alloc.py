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
from ct2trainer.native import aa_program as aa
from ct2trainer.native.address_expression import AddressExpressionError
from test_native_hooks import _Memory, _Coordinator


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


# WP-20: the NASM current-address cursor ('@@:') inside globalalloc sources.
CURSOR_INITIALIZER_SOURCE = (
    '[ENABLE]\n'
    'label(done)\n'
    'globalalloc(shared,8)\n'
    'shared:\n'
    'dd #11\n'
    '@@:\n'
    'dd #22\n'
    'alloc(cave,1000)\n'
    'cave:\n'
    'mov rcx,shared\n'
    'mov eax,[rcx]\n'
    'jmp done\n'
    '0x1000:\n'
    'jmp cave\n'
    'done:\n'
    '[DISABLE]\n'
    '0x1000:\n'
    'db B8 01 00 00 00\n'
    'dealloc(cave)\n'
    'dealloc(shared)\n'
)

CURSOR_ANONYMOUS_LABEL_SOURCE = (
    '[ENABLE]\n'
    'label(done)\n'
    'globalalloc(stash,16)\n'
    'stash:\n'
    'dq #42\n'
    '@@:\n'
    'dq #43\n'
    'alloc(cave,1000)\n'
    'cave:\n'
    'jmp @f\n'
    'nop\n'
    '@@:\n'
    'mov rcx,stash\n'
    'mov eax,[rcx]\n'
    'jmp done\n'
    '0x1000:\n'
    'jmp cave\n'
    'done:\n'
    '[DISABLE]\n'
    '0x1000:\n'
    'db B8 01 00 00 00\n'
    'dealloc(cave)\n'
    'dealloc(stash)\n'
)


class CursorLabelTests(unittest.TestCase):
    """WP-20: '@@:' is the NASM current-address cursor, never a named global."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.memory = _Memory()
        self.pool = ga.GlobalPool(self.memory, self.tmp.name, trainer_id='1'*16,
                                  table_sha256='2'*64, controller_guard=lambda: True)
        self.counter = 0

    def acquire(self, text):
        self.counter += 1
        return self.pool.acquire(ga.prepare_global_program(text), record_id=63,
                                 activation=f'activation-{self.counter}')

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

    def test_cursor_initializer_line_compiles_and_round_trips(self):
        profile = ga.prepare_global_program(CURSOR_INITIALIZER_SOURCE)
        # Data on both sides of the cursor line belongs to the enclosing
        # global cursor ('dd #11'/'dd #22' are decimal literals: 0x0B/0x16);
        # the cursor line itself emits no plan operation.
        self.assertEqual(profile['globals'][0]['initializer'], '0b00000016000000')
        self.assertTrue(profile['globals'][0]['initializer_present'])
        self.assertEqual(len(profile['globals']), 1)
        self.assertEqual(profile['globals'][0]['name'], 'shared')
        self.assertEqual(profile['globals'][0]['size'], 8)
        self.assertEqual(profile['provides'], ['shared'])
        # Inside the initializer region the marker is consumed with the data
        # lines (its offset lives in the pool allocation, not the consumer).
        self.assertNotIn('@@:', profile['consumer_source'])
        self.assertNotIn('dd #22', profile['consumer_source'])
        # Plan metadata is byte-verifiable against the exact original source.
        rebuilt = ga.validate_global_program(profile)
        self.assertEqual(json.dumps(rebuilt, sort_keys=True),
                         json.dumps(profile, sort_keys=True))

    def test_cursor_line_keeps_enclosing_global_cursor_context(self):
        profile = ga.prepare_global_program(CURSOR_INITIALIZER_SOURCE)
        self.assertEqual(profile['globals'][0]['initializer'], '0b00000016000000')
        # The cursor line must not open a second cursor/initializer: exactly
        # one global exists and the second data line was consumed by it.
        self.assertEqual([g['name'] for g in profile['globals']], ['shared'])
        self.assertNotIn('dd #11', profile['consumer_source'])
        self.assertNotIn('dd #22', profile['consumer_source'])

    def test_anonymous_label_consumption_keeps_code_cursor_in_consumer(self):
        profile = ga.prepare_global_program(CURSOR_ANONYMOUS_LABEL_SOURCE)
        self.assertEqual(profile['globals'][0]['initializer'],
                         '2a000000000000002b00000000000000')
        # Exactly one '@@:' survives into the consumer source: the code one.
        # The initializer one was consumed with its data lines.
        self.assertEqual(profile['consumer_source'].count('@@:'), 1)
        ga.validate_global_program(profile)

    def test_cursor_engine_activation_is_byte_exact_and_reversible(self):
        lease = self.acquire(CURSOR_INITIALIZER_SOURCE)
        manager = self.publish(lease)
        base = self.pool.diagnostic()['members'][0]['address']
        self.assertEqual(self.memory.read(base, 8), b'\x0b\x00\x00\x00\x16\x00\x00\x00')
        self.assertEqual(self.memory.read(0x1000, 1), b'\xE9')
        manager.disable()
        self.assertEqual(self.memory.read(0x1000, 5), b'\xB8\x01\x00\x00\x00')
        self.assertEqual(self.memory.read(base, 8), b'\x0b\x00\x00\x00\x16\x00\x00\x00')
        self.pool.release(lease)
        self.assertEqual(self.memory.releases, [])

    def test_cursor_anonymous_label_links_to_the_exact_atat_position(self):
        lease = self.acquire(CURSOR_ANONYMOUS_LABEL_SOURCE)
        manager = self.publish(lease)
        base = self.pool.diagnostic()['members'][0]['address']
        self.assertEqual(self.memory.read(base, 16),
                         b'\x2a\x00\x00\x00\x00\x00\x00\x00'
                         b'\x2b\x00\x00\x00\x00\x00\x00\x00')
        # 'jmp @f' is assembled as a 2-byte short jump (EB 01) and 'nop' is
        # one byte, so the '@@:' target sits at cave+3: EB 01 jumps from +2
        # to +3, i.e. exactly the '@@:' marker.  A fallback to a later named
        # label (e.g. 'done') would produce a different offset.
        cave = manager.allocation_map()['cave']['address']
        self.assertEqual(self.memory.read(cave, 2), b'\xEB\x01')
        self.assertEqual(self.memory.read(cave + 2, 1), b'\x90')  # nop before '@@:'
        self.assertEqual(self.memory.read(cave + 3, 1), b'\xB9')  # 'mov' at '@@:'
        manager.disable()
        self.pool.release(lease)
        self.assertEqual(self.memory.releases, [])

    def test_cursor_outside_label_line_stays_fail_closed_with_named_error(self):
        # Expression-like cursor line is not the exact '@@:' marker: the
        # named global-profile refusal is raised before the AA parser sees it.
        text = source(initializer=False).replace(
            'alloc(cave,1000)', '@@+1:\ndd #19\nalloc(cave,1000)')
        with self.assertRaisesRegex(ga.GlobalError, 'current-address cursor'):
            ga.prepare_global_program(text)
        # Alias closure reaching the cursor through a define: the define
        # value is parsed by the AA dialect as an address expression, so the
        # named ProgramError is the visible (still per-record-contained)
        # refusal; it must never be a raw AddressExpressionError.
        text = source(initializer=False).replace(
            'alloc(cave,1000)', 'define(x,@@)\nx:\ndd #19\nalloc(cave,1000)')
        with self.assertRaises(aa.ProgramError) as context:
            ga.prepare_global_program(text)
        self.assertIn('@@', str(context.exception))

    def test_cursor_as_staged_readmem_address_is_named(self):
        text = source().replace('dd #17', 'readmem(@@,4)')
        # Parsed as an address expression before the staged shape check, so
        # the named AA-dialect refusal (ProgramError) is the visible error;
        # assertRaises(aa.ProgramError) also proves it is not a raw
        # AddressExpressionError (ProgramError is not its subclass).
        with self.assertRaises(aa.ProgramError) as context:
            ga.prepare_global_program(text)
        self.assertIn('@@', str(context.exception))

    def test_cursor_in_declaration_size_is_named(self):
        text = source().replace('globalalloc(shared,4)', 'globalalloc(shared,@@)')
        with self.assertRaisesRegex(ga.GlobalError,
                                    'Global declaration size is not a bounded integer'):
            ga.prepare_global_program(text)

    def test_cursor_as_initializer_value_is_named(self):
        # Unparseable cursor token: the AA dialect refuses it with the
        # named ProgramError at parse time (still per-record contained,
        # never a raw AddressExpressionError).
        text = source().replace('dd #17', 'dd @@')
        with self.assertRaises(aa.ProgramError) as context:
            ga.prepare_global_program(text)
        self.assertIn('@@', str(context.exception))
        # Parseable but non-scalar expression under the cursor: the global
        # profile refuses non-literal initializer values with its named error.
        text = source().replace('dd #17', 'dd [rax]')
        with self.assertRaisesRegex(ga.GlobalError,
                                    'Only scalar/string db/dw/dd/dq initializers'):
            ga.prepare_global_program(text)


if __name__ == '__main__':
    unittest.main()
