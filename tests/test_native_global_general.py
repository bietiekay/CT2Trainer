"""Native 0.9: aa_globalalloc_general staged-readmem profile contracts.

The pinned Fallout 4 records 1095/1096 are the corpus anchors of the
staged-readmem profile: their exact sources are embedded below and
cross-checked against the locally owned CT whenever it is present.
The literal Trine 61/63/65 profiles remain byte-identical to their
pre-stage canonical pins (no staged_ops key, literal profile name).
All runtime tests run against a first-party fake target: no game, no
CE inputs, no target API or managed invocation.
"""
from __future__ import annotations
import copy
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from pathlib import Path

from ct2trainer.native import global_alloc as ga
from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import NativeRuntimeError, TrainerEngine
from ct2trainer.native.hooks import QuiescenceProof
from ct2trainer.native.address_expression import resolve_expression
from test_native_hooks import _Memory

ROOT = Path(__file__).resolve().parents[1]
FALLOUT_CT = ROOT / 'TableReferences' / 'case-02.ct'  # origin: Fallout 4
TRINE_CT = ROOT / 'TableReferences' / 'case-01.ct'  # origin: Trine 2

FALLOUT4_1095 = '{\n  Game   : ct2synth02.exe\n  Date   : 2026-10-09\n  Author : CT2Trainer clean-room corpus\n}\n\n[ENABLE]\naobscanmodule(synTermGood,ct2synth02.exe,4C 89 64 24 00 0F 28 C8 E8)\nregistersymbol(synTermGood)\naobscanmodule(synTermBad,ct2synth02.exe,E8 00 00 00 00 80 0D 04 48)\nregistersymbol(synTermBad)\nglobalalloc(synTermStored,8)\n\nsynTermStored:\n  readmem(synTermBad+C,7) {staged capture: 7 original bytes}\n\nsynTermBad+C:\n  jmp synTermGood+D\n  db 90 90\n\n[DISABLE]\nsynTermBad+C:\n  readmem(synTermStored,7) {staged restore: original bytes back}\ndealloc(synTermStored)\nunregistersymbol(synTermBad)\nunregistersymbol(synTermGood)\n'
FALLOUT4_1096 = '{\n  Game   : ct2synth02.exe\n  Date   : 2026-10-09\n  Author : CT2Trainer clean-room corpus\n}\n\n[ENABLE]\n\naobscanmodule(synLockEnter,ct2synth02.exe,48 8B 93 40 00 00 00)\naobscanmodule(synLockFlag,ct2synth02.exe,FF 15 00 00 00 00)\nalloc(synLockAlloc,$1000,synLockEnter)\nregistersymbol(synLockEnter)\nlabel(synLockExit)\nglobalalloc(synLockStored,8)\n\nsynLockStored:\n  readmem(synLockEnter+F,7) {staged capture: 7 original bytes}\n\nsynLockAlloc:\n  reassemble(synLockEnter+F)\n  reassemble(synLockFlag+D)\n  jmp synLockExit\n\nsynLockEnter+F:\n  jmp synLockAlloc\n  db 90 90\nsynLockExit:\n\n[DISABLE]\nsynLockEnter+F:\n  readmem(synLockStored,7) {staged restore: original bytes back}\ndealloc(synLockStored)\nunregistersymbol(synLockEnter)\ndealloc(synLockAlloc)\n'

# Re-pinned 2026-10-09 for the clean-room synthetic corpus: the literal
# Trine records 61/63/65 now carry the synthetic Syn* scripts and the
# canonical profile is computed against ct2synth01.exe (32-bit).
TRINE_LITERAL_PINS = {
    '61': 'EAA2BC45B44B8F9221C6CB860A80E98BCC13C18EC35FB4F06E29C1BFA7397459',
    '63': '299BB5FD173183FCB3B6F5B781C68CB4B5795DE753231DE3202F0D4573AFEE61',
    '65': '10DEF733B73A5730481996974A401E276331B6EF2158C0B70583162B3DC06AEB',
}

ORIGINAL7 = bytes([0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B])

# Synthetic corpus-shaped staged source (two module scans, one global,
# the paired staged readmem, a patch overlapping the scan-adjacent
# region, and scan symbols that the patch jumps to).
STAGED_SOURCE = '''[ENABLE]
aobscanmodule(hitGood,Owned.exe,00 01 02 03 04)
registersymbol(hitGood)
aobscanmodule(hitBad,Owned.exe,48 8B 05 01 02)
registersymbol(hitBad)
globalalloc(stored,8)

stored:
  readmem(hitBad+C,7)

hitBad+C:
  jmp hitGood+D
  db 90 90

[DISABLE]
hitBad+C:
  readmem(stored,7)
dealloc(stored)
unregistersymbol(hitBad)
unregistersymbol(hitGood)
'''


def write_ct(texts, path):
    root = ET.Element('CheatTable', CheatEngineTableVersion='45')
    entries = ET.SubElement(root, 'CheatEntries')
    for index, text in enumerate(texts, 1):
        entry = ET.SubElement(entries, 'CheatEntry')
        for key, value in {
                'ID': str(index),
                'Description': 'Own ' + str(index),
                'VariableType': 'Auto Assembler Script',
                'AssemblerScript': text,
        }.items():
            ET.SubElement(entry, key).text = value
    path.write_bytes(ET.tostring(root, encoding='utf-8', xml_declaration=True))
    return path


class Memory(_Memory):
    """Fake 64-bit target: two code regions plus owned allocations."""

    pid = 123
    creation_time = 456
    closed = False

    def __init__(self):
        super().__init__()
        # 0x1000: hitBad pattern at +0, the staged original 7 bytes at +C.
        region_a = bytes([0x48, 0x8B, 0x05, 0x01, 0x02, 0x03, 0x04, 0x05,
                          0x06, 0x07, 0x08, 0x09]) + ORIGINAL7 + bytes([0x00, 0x00])
        self.data = {0x1000: region_a, 0x2000: bytes(range(20))}
        self.scan_calls = 0

    def close(self):
        self.closed = True

    def resolve(self, text, symbols):
        return resolve_expression(text, self, symbols)

    def resolve_pointer(self, text, offsets, symbols):
        if offsets:
            raise ValueError('No pointer chain in this fake fixture')
        return self.resolve(text, symbols)

    def _scan(self, pattern, start=0, end=1 << 64):
        from ct2trainer.native.patterns import pattern_matches
        self.scan_calls += 1
        size = len(pattern.split())
        found = [base + offset for base, raw in self.data.items()
                 for offset in range(len(raw) - size + 1)
                 if start <= base + offset < end
                 and pattern_matches(pattern, raw[offset:offset + size])]
        if len(found) != 1:
            raise ValueError('owned scan ambiguity: ' + pattern)
        return found[0]

    def scan_process(self, pattern):
        return self._scan(pattern)

    def scan_region(self, start, end, pattern):
        return self._scan(pattern, start, end)

    def scan_module(self, module, pattern):
        return self._scan(pattern)

    def module(self, name):
        return 0x1000, 0x2000

    def _query(self, address):
        # Fixture code regions are executable RWX (0x40), owned
        # allocations keep their exact protection; the external literal
        # sealing path therefore never engages for this fixture.
        from types import SimpleNamespace
        for base, size in self.allocations.items():
            if base <= address < base + size:
                return SimpleNamespace(BaseAddress=base, AllocationBase=base,
                                       RegionSize=size, State=0x1000,
                                       Protect=self.allocation_protections.get(base, 0x04))
        for base, raw in self.data.items():
            if base <= address < base + len(raw):
                return SimpleNamespace(BaseAddress=base, AllocationBase=base,
                                       RegionSize=len(raw), State=0x1000,
                                       Protect=0x40)
        raise Exception('unmapped test protection range')


class Coordinator:
    @contextmanager
    def hold(self, memory, ranges):
        held = [True]
        try:
            yield QuiescenceProof(memory.identity, tuple(ranges),
                                  'owned-fake-staged', lambda: held[0])
        finally:
            held[0] = False


class PinnedCorpusTests(unittest.TestCase):
    """Plan-level contracts for the two pinned Fallout 4 records."""

    def test_embedded_sources_match_local_corpus(self):
        if not FALLOUT_CT.exists():
            self.skipTest('case-02 (origin: Fallout 4) is absent from this checkout.')
        root = ET.parse(FALLOUT_CT).getroot()
        texts = {}
        for entry in root.iter('CheatEntry'):
            id_el = entry.find('ID')
            if id_el is not None and id_el.text.strip() in ('1095', '1096'):
                texts[id_el.text.strip()] = entry.find('AssemblerScript').text
        self.assertEqual(texts['1095'], FALLOUT4_1095)
        self.assertEqual(texts['1096'], FALLOUT4_1096)

    def test_1095_staged_profile_is_exact(self):
        p = ga.prepare_global_program(FALLOUT4_1095, 'ct2synth02.exe', bitness=64)
        self.assertEqual(p['profile'], 'staged-readmem-rw/v1')
        self.assertEqual(p['staged_ops'], [
            {'op': 'readmem', 'direction': 'target_to_global',
             'global': 'synTermStored',
             'address': 'synTermBad+C', 'size': 7,
             'phase': 'enable'},
            {'op': 'readmem', 'direction': 'global_to_target',
             'global': 'synTermStored',
             'address': 'synTermBad+C', 'size': 7,
             'phase': 'disable'},
        ])
        self.assertEqual(p['globals'], [{
            'name': 'synTermStored', 'size': 8, 'near': None,
            'initializer': '', 'executable': False, 'writable': True,
            'declaration_line': 12, 'initializer_present': True,
        }])
        self.assertEqual(p['provides'], [
            'synTermBad', 'synTermGood',
            'synTermStored'])
        self.assertEqual(p['requires'], [])
        self.assertTrue(p['consumer_shape']['requires_coordinator'])
        consumer = p['consumer_source']
        self.assertNotIn('globalalloc(', consumer)
        self.assertNotIn('readmem(', consumer)
        self.assertNotIn('synTermStored', consumer)
        self.assertIn('aobscanmodule(synTermGood,ct2synth02.exe,', consumer)
        self.assertIn('aobscanmodule(synTermBad,ct2synth02.exe,', consumer)
        self.assertIn('jmp synTermGood+D', consumer)
        self.assertIn('db 90 90', consumer)
        self.assertIn('unregistersymbol(synTermBad)', consumer)
        self.assertIn('unregistersymbol(synTermGood)', consumer)

    def test_1096_staged_profile_is_exact(self):
        p = ga.prepare_global_program(FALLOUT4_1096, 'ct2synth02.exe', bitness=64)
        self.assertEqual(p['profile'], 'staged-readmem-rw/v1')
        self.assertEqual(p['staged_ops'], [
            {'op': 'readmem', 'direction': 'target_to_global',
             'global': 'synLockStored',
             'address': 'synLockEnter+F', 'size': 7,
             'phase': 'enable'},
            {'op': 'readmem', 'direction': 'global_to_target',
             'global': 'synLockStored',
             'address': 'synLockEnter+F', 'size': 7,
             'phase': 'disable'},
        ])
        self.assertEqual(p['globals'], [{
            'name': 'synLockStored', 'size': 8, 'near': None,
            'initializer': '', 'executable': False, 'writable': True,
            'declaration_line': 14, 'initializer_present': True,
        }])
        self.assertEqual(p['provides'], [
            'synLockEnter', 'synLockStored'])
        self.assertEqual(p['requires'], [])
        consumer = p['consumer_source']
        self.assertNotIn('globalalloc(', consumer)
        self.assertNotIn('readmem(', consumer)
        self.assertNotIn('synLockStored', consumer)
        self.assertIn('alloc(synLockAlloc,$1000,synLockEnter)',
                      consumer)
        self.assertIn('label(synLockExit)', consumer)
        self.assertIn('reassemble(synLockEnter+F)', consumer)
        self.assertIn('reassemble(synLockFlag+D)', consumer)
        self.assertIn('jmp synLockAlloc', consumer)
        self.assertIn('db 90 90', consumer)
        self.assertIn('dealloc(synLockAlloc)', consumer)
        self.assertIn('unregistersymbol(synLockEnter)', consumer)

    def test_staged_profiles_round_trip_and_refuse_tamper(self):
        for name, text in (('1095', FALLOUT4_1095), ('1096', FALLOUT4_1096)):
            with self.subTest(record=name):
                p = ga.prepare_global_program(text, 'ct2synth02.exe', bitness=64)
                ga.validate_global_program(p)
                q = copy.deepcopy(p)
                q['staged_ops'][0]['size'] = 3
                with self.assertRaisesRegex(ga.GlobalError, 'exact original source'):
                    ga.validate_global_program(q)
                r = copy.deepcopy(p)
                del r['staged_ops']
                with self.assertRaisesRegex(ga.GlobalError, 'exact original source'):
                    ga.validate_global_program(r)
                s = copy.deepcopy(p)
                s['staged_ops'][1]['direction'] = 'target_to_global'
                with self.assertRaisesRegex(ga.GlobalError, 'exact original source'):
                    ga.validate_global_program(s)


class LiteralRegressionTests(unittest.TestCase):
    """The literal-only profiles keep their exact pre-stage byte shape."""

    def test_trine_literal_profiles_remain_byte_identical(self):
        if not TRINE_CT.exists():
            self.skipTest('case-01 (origin: Trine 2) is absent from this checkout.')
        root = ET.parse(TRINE_CT).getroot()
        scripts = {}
        for entry in root.iter('CheatEntry'):
            id_el = entry.find('ID')
            if id_el is not None and id_el.text in TRINE_LITERAL_PINS:
                scripts[id_el.text] = entry.findtext('AssemblerScript')
        self.assertEqual(sorted(scripts), sorted(TRINE_LITERAL_PINS))
        for record_id, expected in TRINE_LITERAL_PINS.items():
            with self.subTest(record=record_id):
                p = ga.prepare_global_program(scripts[record_id],
                                              'ct2synth01.exe', bitness=32)
                self.assertNotIn('staged_ops', p)
                self.assertEqual(p['profile'],
                                 'literal-rw-no-changed-reinitialization/v1')
                canon = json.dumps(p, sort_keys=True, separators=(',', ':'),
                                   ensure_ascii=True).encode('ascii')
                self.assertEqual(ga._hash(canon).upper(), expected)


class StagedRefusalTests(unittest.TestCase):
    """Unpaired or malformed global readmem shapes keep the visible refusal."""

    BASE = STAGED_SOURCE

    def _refuse(self, text, pattern):
        with self.assertRaisesRegex(ga.GlobalError, pattern):
            ga.prepare_global_program(text, 'Owned.exe', bitness=64)

    def test_self_referencing_enable_staged_readmem_refused(self):
        text = self.BASE.replace('readmem(hitBad+C,7)', 'readmem(stored,7)', 1)
        self._refuse(text, 'cannot reference a declared global')

    def test_assert_or_reassemble_on_global_refused(self):
        for replacement in ('assert(stored, FF)', 'reassemble(stored)'):
            with self.subTest(replacement=replacement):
                self._refuse(self.BASE.replace('  jmp hitGood+D',
                                               '  ' + replacement),
                             'future staged source profile')

    def test_staged_readmem_size_beyond_global_refused_both_directions(self):
        self._refuse(self.BASE.replace('readmem(hitBad+C,7)',
                                       'readmem(hitBad+C,9)', 1),
                     'exceeds the declared global allocation size')
        self._refuse(self.BASE.replace('readmem(stored,7)', 'readmem(stored,9)'),
                     'exceeds the declared global allocation size')

    def test_unpaired_staged_readmem_refused_both_ways(self):
        self._refuse(self.BASE.replace('  readmem(stored,7)\n', ''),
                     'unpaired global readmem remains blocked')
        self._refuse(self.BASE.replace('  readmem(hitBad+C,7)\n', ''),
                     'unpaired global readmem remains blocked')

    def test_offset_expression_in_disable_readmem_refused(self):
        self._refuse(self.BASE.replace('readmem(stored,7)',
                                       'readmem(stored+1,7)'),
                     'without offset or expression')

    def test_disable_readmem_without_target_cursor_refused(self):
        self._refuse(self.BASE.replace('[DISABLE]\nhitBad+C:\n', '[DISABLE]\n'),
                     'staged only under a target DISABLE cursor')

    def test_enable_readmem_of_global_under_target_cursor_refused(self):
        self._refuse(self.BASE.replace('  jmp hitGood+D', '  readmem(stored,7)'),
                     'staged only under a target DISABLE cursor')

    def test_literal_and_staged_mix_refused_both_orderings(self):
        first = self.BASE.replace('  readmem(hitBad+C,7)',
                                  '  dd #01020304\n  readmem(hitBad+C,4)')
        second = self.BASE.replace('  readmem(hitBad+C,7)',
                                   '  readmem(hitBad+C,4)\n  dd #01020304')
        for name, text in (('literal_first', first), ('staged_first', second)):
            with self.subTest(order=name):
                self._refuse(text, 'mix literal initializers with staged readmem')

    def test_duplicate_staged_readmem_refused_per_direction(self):
        self._refuse(self.BASE.replace('  readmem(hitBad+C,7)',
                                       '  readmem(hitBad+C,4)\n  readmem(hitBad+C,3)'),
                     'may stage bytes into each global')
        self._refuse(self.BASE.replace('  readmem(stored,7)',
                                       '  readmem(stored,4)\n  readmem(stored,3)'),
                     'may restore bytes from each global')

    def test_empty_initializer_cursor_with_staged_pair_elsewhere_refused(self):
        text = (self.BASE.replace('globalalloc(stored,8)',
                                  'globalalloc(stored,8)\nglobalalloc(empty,8)')
                .replace('stored:\n  readmem(hitBad+C,7)',
                         'stored:\nempty:\n  readmem(hitBad+C,7)')
                .replace('readmem(stored,7)', 'readmem(empty,7)')
                .replace('dealloc(stored)', 'dealloc(stored)\ndealloc(empty)'))
        self._refuse(text, 'must contain bounded literal data or staged readmem')


class StagedRuntimeTests(unittest.TestCase):
    """Runtime lifecycle of the paired staged readmem on a fake target."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.memory = Memory()
        path = write_ct((STAGED_SOURCE,), self.dir / 'own.ct')
        self.plan = compile_table(path, 'Owned.exe')

    def engine(self):
        e = TrainerEngine(self.plan, self.dir / 'state',
                          lambda name: self.memory, self.dir / 'shared',
                          hook_coordinator=Coordinator())
        e.poll()
        self.assertTrue(e.connected, e.error)
        return e

    def test_staged_enable_disable_round_trip_and_lease_lifecycle(self):
        e = self.engine()
        e.toggle(1, True)
        base = e.global_pool.members['stored']['address']
        self.assertEqual(self.memory.read(base, 8), ORIGINAL7 + b'\x00')
        patched = self.memory.read(0x100C, 7)
        self.assertEqual(patched[0:1], b'\xE9')
        self.assertEqual(patched[5:7], b'\x90\x90')
        self.assertEqual(e.applied[1][0].address, 0x100C)
        self.assertEqual(e.applied[1][0].original, ORIGINAL7)
        e.toggle(1, False)
        self.assertEqual(self.memory.read(0x100C, 7), ORIGINAL7)
        self.assertIn((0x100C, ORIGINAL7), self.memory.writes)
        self.assertEqual(e.global_leases, {})
        self.assertEqual(e.applied, {})
        self.assertIn('stored', e.global_pool.members)
        self.assertEqual(self.memory.releases, [])
        # Fresh target bytes are re-staged on re-activation.
        self.memory.write(0x100C, b'\x90' * 7)
        e.toggle(1, True)
        self.assertEqual(self.memory.read(base, 8), b'\x90' * 7 + b'\x00')
        e.toggle(1, False)
        self.assertEqual(self.memory.read(0x100C, 7), b'\x90' * 7)
        self.assertEqual(self.memory.scan_calls, 4)

    def test_scan_drift_during_staged_copy_is_clean_refusal(self):
        e = self.engine()
        original_read = self.memory.read
        drift = {'done': False}

        def read(address, size):
            if (address, size) == (0x100C, 7) and not drift['done']:
                drift['done'] = True
                data = self.memory.data[0x1000]
                # Corrupt only the captured hitBad scan bytes (0x1000..0x1004),
                # leaving the staged source range at 0x100C intact.
                self.memory.data[0x1000] = b'\xff' * 5 + data[5:]
            return original_read(address, size)

        self.memory.read = read
        with self.assertRaisesRegex(NativeRuntimeError,
                                    'Original shared scan bytes changed'):
            e.toggle(1, True)
        self.assertFalse(e.blocked, e.error)
        self.assertEqual(e.applied, {})
        self.assertEqual(e.desired, set())
        self.assertEqual(e.global_leases, {})
        self.assertIn('stored', e.global_pool.members)
        self.assertEqual(e.global_pool.state, 'live')
        self.assertEqual(self.memory.writes, [])
        self.assertEqual(self.memory.read(0x100C, 7), ORIGINAL7)
        self.assertEqual(self.memory.scan_calls, 2)

    def test_target_exit_during_global_allocation_blocks(self):
        e = self.engine()
        original_allocate = self.memory.allocate

        def allocate(size, near=None):
            self.memory.alive = False
            return original_allocate(size, near)

        self.memory.allocate = allocate
        with self.assertRaises(NativeRuntimeError):
            e.toggle(1, True)
        self.assertTrue(e.blocked)
        self.assertEqual(e.applied, {})
        self.assertEqual(e.desired, set())
        # The engine never registered the lease (acquire raised first); the
        # pool itself retains the single uncertain lease and no storage is
        # freed, so the trainer stays blocked fail-closed.
        self.assertEqual(e.global_leases, {})
        leases = list(e.global_pool.leases.values())
        self.assertEqual(len(leases), 1)
        self.assertEqual(leases[0].record_id, 1)
        self.assertEqual(leases[0].state, 'uncertain')
        self.assertEqual(self.memory.releases, [])
        self.assertEqual(e.global_pool.state, 'uncertain')
        journal = json.loads(e.global_pool.path.read_bytes())
        self.assertEqual(journal['state'], 'uncertain')
        self.assertNotIn('stored', e.global_pool.members)

    def test_partial_staged_write_blocks_with_uncertain_pool(self):
        e = self.engine()
        self.memory.failure = 'partial'
        with self.assertRaises(NativeRuntimeError):
            e.toggle(1, True)
        self.assertTrue(e.blocked)
        self.assertEqual(e.applied, {})
        self.assertEqual(e.desired, set())
        self.assertIn(1, e.global_leases)
        self.assertEqual(e.global_pool.state, 'uncertain')
        journal = json.loads(e.global_pool.path.read_bytes())
        self.assertEqual(journal['state'], 'uncertain')
        self.assertEqual(self.memory.read(0x100C, 7), ORIGINAL7)

    def test_disable_side_failure_blocks_and_retains_lease(self):
        e = self.engine()
        e.toggle(1, True)
        base = e.global_pool.members['stored']['address']
        del self.memory.data[base]
        with self.assertRaises(NativeRuntimeError):
            e.toggle(1, False)
        self.assertTrue(e.blocked)
        self.assertIn(1, e.applied)
        self.assertIn(1, e.global_leases)
        # The consumer manager restored the target before the staged
        # read-back failed, so the original bytes are back at 0x100C.
        self.assertEqual(self.memory.read(0x100C, 7), ORIGINAL7)
        self.assertEqual(self.memory.releases, [])


if __name__ == '__main__':
    unittest.main()
