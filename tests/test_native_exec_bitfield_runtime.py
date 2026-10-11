"""WP-15 (L2-37): masked bit-field writes/freezes on executable literal spans.

Fully permit-covered executable bit fields route through the live provider
literal-permit hook path (the masked mirror of the full-span numeric literal
write); mixed, uncovered, crossing and coordinator-less transactions keep
their named fail-closed refusals.  The synthetic provider owns one executable
cave page with source-proven literal holes; the fake keeps that page
executable after the issuer retires so the permit check, not the page
protection, decides the revocation case.
"""
from contextlib import contextmanager
from pathlib import Path
import json
import tempfile
import unittest
from types import SimpleNamespace

from test_native_engine import FakeMemory
from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import TrainerEngine, NativeRuntimeError
from ct2trainer.native.hooks import HookError, QuiescenceProof


CAVE = 0x10000
CAVE_SIZE = 0x1000
FLAG = CAVE + 1        # one nop byte into the cave
FLAG2 = CAVE + 5       # second literal hole (double-hole provider)
ORDINARY = 0x1040      # ordinary data page, never executable


PROVIDER_SINGLE = """[ENABLE]
alloc(cave,64)
label(flag)
cave:
nop
flag:
dd 0
ret
registersymbol(flag)
[DISABLE]
unregistersymbol(*)
dealloc(*)"""

PROVIDER_DOUBLE = """[ENABLE]
alloc(cave,64)
label(flag,flag2)
cave:
nop
flag:
dd 0
flag2:
dd 0
ret
registersymbol(flag,flag2)
[DISABLE]
unregistersymbol(*)
dealloc(*)"""


def _table(provider):
    return ('<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
            '<CheatEntry><ID>1</ID><Description>Provider</Description>'
            '<VariableType>Auto Assembler Script</VariableType>'
            f'<AssemblerScript>{provider}</AssemblerScript></CheatEntry>'
            '<CheatEntry><ID>2</ID><Description>Whole flag</Description>'
            '<VariableType>4 Bytes</VariableType><Address>10001</Address>'
            '<ShowAsHex>1</ShowAsHex></CheatEntry>'
            '<CheatEntry><ID>3</ID><Description>Low twelve bits</Description>'
            '<VariableType>Binary</VariableType><Address>10001</Address>'
            '<BitStart>0</BitStart><BitLength>12</BitLength>'
            '<ShowAsHex>1</ShowAsHex></CheatEntry>'
            '<CheatEntry><ID>4</ID><Description>Upper nibble</Description>'
            '<VariableType>Binary</VariableType><Address>10002</Address>'
            '<BitStart>4</BitStart><BitLength>4</BitLength>'
            '<ShowAsHex>1</ShowAsHex></CheatEntry>'
            '<CheatEntry><ID>5</ID><Description>Ordinary field</Description>'
            '<VariableType>Binary</VariableType><Address>1040</Address>'
            '<BitStart>0</BitStart><BitLength>4</BitLength>'
            '<ShowAsHex>1</ShowAsHex></CheatEntry>'
            '<CheatEntry><ID>6</ID><Description>Crossing field</Description>'
            '<VariableType>Binary</VariableType><Address>10003</Address>'
            '<BitStart>0</BitStart><BitLength>32</BitLength>'
            '<ShowAsHex>1</ShowAsHex></CheatEntry>'
            '</CheatEntries></CheatTable>')


class CaveMemory(FakeMemory):
    """Flat fake target with one executable cave page and ordinary data."""

    def __init__(self):
        super().__init__()
        # FakeMemory covers [0x1000, 0x1100); extend the flat buffer to the
        # end of the cave page [0x10000, 0x11000) as zero-filled memory.
        extended = bytearray(CAVE_SIZE + CAVE - self.base)
        extended[:len(self.data)] = self.data
        self.data = extended
        self.allocations = {}
        self.allocation_protections = {}
        self.protect_calls = []
        self.releases = []

    @property
    def identity(self):
        return self.pid, self.creation_time

    def is_executable(self, address, size):
        # The cave page is executable; the page protection outlives the
        # issuer in this fake, so a revoked provider still routes to the
        # permit check instead of the ordinary data path.
        return CAVE <= address and address + size <= CAVE + CAVE_SIZE

    def allocate(self, size, near=None):
        self.allocations[CAVE] = CAVE_SIZE
        return CAVE

    def allocation_size(self, address):
        return self.allocations[address]

    def protect_allocation(self, address, executable=True, writable=False):
        self.protect_calls.append((address, executable, writable))
        self.allocation_protections[address] = \
            (0x40 if writable else 0x20) if executable else 0x04

    def _query(self, address):
        for base, size in self.allocations.items():
            if base <= address < base + size:
                return SimpleNamespace(BaseAddress=base, AllocationBase=base,
                                       RegionSize=size, State=0x1000,
                                       Protect=self.allocation_protections.get(base, 0x04))
        raise HookError('unmapped test protection range')

    def release(self, address):
        self.releases.append(address)


class SafePointCoordinator:
    """Records every safe-point hold; can expire proofs from a hold index on."""

    def __init__(self):
        self.holds = []
        self.held = False
        self.expire_from_hold = None

    def _expired(self, index):
        return self.expire_from_hold is not None and index >= self.expire_from_hold

    @contextmanager
    def hold(self, memory, ranges):
        index = len(self.holds)
        self.holds.append(tuple(ranges))
        self.held = True
        try:
            yield QuiescenceProof(memory.identity, tuple(ranges), 'wp15-safe-point',
                                  lambda: self.held and not self._expired(index))
        finally:
            self.held = False

    def hold_entries(self, memory, windows, *, literal_windows=(), exclusion_ranges=()):
        ranges = [(address, len(original))
                  for address, original, _, _ in windows + literal_windows]
        ranges.extend(exclusion_ranges)
        return self.hold(memory, ranges)

    def hold_data(self, memory, ranges):
        return self.hold(memory, ranges)


class ExecBitfieldRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.memory = None
        self.coordinator = None
        self.engine = None

    def tearDown(self):
        if self.engine is not None:
            self.engine.close()

    def _make_engine(self, name, provider='single'):
        self.table = self.root / (name + '.ct')
        self.table.write_text(_table(PROVIDER_SINGLE if provider == 'single'
                                     else PROVIDER_DOUBLE), encoding='utf-8')
        self.memory = CaveMemory()
        self.coordinator = SafePointCoordinator()
        plan = compile_table(self.table, 'FixtureTarget.exe')
        engine = TrainerEngine(plan, state_dir=self.root / name,
                               process_lock_dir=self.root / name / 'shared',
                               memory_factory=lambda _n: self.memory,
                               hook_coordinator=self.coordinator)
        engine.poll()
        self.assertTrue(engine.connected, engine.status)
        self.engine = engine
        return engine

    def test_numeric_full_span_template_on_live_provider(self):
        engine = self._make_engine('template')
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.memory.read(FLAG, 4), b'\x00' * 4)
        self.assertEqual(engine.set_value(2, '0x11223344'), '11223344')
        self.assertEqual(self.memory.read(FLAG, 4), b'\x44\x33\x22\x11')
        self.assertEqual(self.memory.read(FLAG - 1, 1), b'\x90')
        self.assertEqual(self.memory.read(FLAG + 4, 1), b'\xC3')
        self.assertEqual(engine.hooks[1].receipt()['state'], 'enabled')
        transient = engine.retired_hooks[-1]
        self.assertTrue(transient.owner_id.endswith(':literal-value'))
        self.assertIs(transient.receipt()['data_commit'], True)
        self.assertFalse(engine.blocked, engine.error)

    def test_bitfield_writes_preserve_unowned_bits_and_commit(self):
        engine = self._make_engine('bitfield')
        self.assertTrue(engine.toggle(1, True))
        self.memory.write(CAVE + 3, b'\xAB')  # unowned byte inside the hole
        self.assertEqual(engine.set_value(3, '0xABC'), 'ABC')
        self.assertEqual(engine.set_value(4, 'C'), 'C')
        self.assertEqual(self.memory.read(FLAG, 4), b'\xBC\xCA\xAB\x00')
        self.assertEqual(self.memory.read(CAVE, 1), b'\x90')
        self.assertEqual(self.memory.read(FLAG2, 1), b'\xC3')  # ret intact
        self.assertEqual(engine.hooks[1].receipt()['state'], 'enabled')
        transient = engine.retired_hooks[-1]
        self.assertTrue(transient.owner_id.endswith(':bitfield-value'))
        self.assertIs(transient.receipt()['data_commit'], True)
        # The last safe-point hold carried the literal allocation exclusion.
        self.assertIn((CAVE, CAVE_SIZE), self.coordinator.holds[-1])
        self.assertFalse(engine.blocked, engine.error)

    def test_freeze_ticks_remerge_fresh_unowned_bits(self):
        engine = self._make_engine('freeze')
        self.assertTrue(engine.toggle(1, True))
        self.memory.write(CAVE + 3, b'\xAB')
        engine.set_value(3, '0xABC')
        engine.set_value(4, 'C')
        self.assertTrue(engine.set_freeze(3, True))
        self.assertTrue(engine.set_freeze(4, True))
        self.memory.write(FLAG, b'\x5A')
        self.memory.write(FLAG + 1, b'\x40')
        engine.poll()
        self.assertFalse(engine.blocked, engine.error)
        self.assertEqual(self.memory.read(FLAG, 4), b'\xBC\xCA\xAB\x00')
        self.assertIn(3, engine.frozen)
        self.assertIn(4, engine.frozen)

    def test_refused_without_live_permit(self):
        engine = self._make_engine('no-permit')  # provider never enabled
        writes_before = len(self.memory.writes)
        with self.assertRaisesRegex(NativeRuntimeError,
                                    'cannot alter executable pages without live provider literal provenance'):
            engine.set_value(2, '0x11223344')
        self.assertEqual(len(self.memory.writes), writes_before)
        self.assertFalse(engine.blocked)

    def test_refused_with_partial_permit_coverage(self):
        engine = self._make_engine('partial')
        self.assertTrue(engine.toggle(1, True))
        engine._owned_provider_data = lambda: ([], [(FLAG, 1, CAVE, CAVE_SIZE)])
        writes_before = len(self.memory.writes)
        with self.assertRaisesRegex(NativeRuntimeError,
                                    'fully covered live provider literal permit'):
            engine.set_value(3, '0xABC')
        self.assertEqual(len(self.memory.writes), writes_before)
        self.assertFalse(engine.blocked)

    def test_refused_when_span_crosses_permit_boundary(self):
        engine = self._make_engine('crossing', provider='double')
        self.assertTrue(engine.toggle(1, True))
        writes_before = len(self.memory.writes)
        with self.assertRaisesRegex(NativeRuntimeError,
                                    'fully covered live provider literal permit'):
            engine.set_value(6, '0x00000007')
        self.assertEqual(len(self.memory.writes), writes_before)
        self.assertFalse(engine.blocked)

    def test_mixed_ordinary_executable_batch_is_refused_and_quarantined(self):
        engine = self._make_engine('mixed')
        self.assertTrue(engine.toggle(1, True))
        self.assertTrue(engine.set_freeze(3, True))  # executable bit field
        self.assertTrue(engine.set_freeze(5, True))  # ordinary data-page bit field
        writes_before = len(self.memory.writes)
        engine.poll()
        self.assertTrue(engine.blocked)
        self.assertIn('Mixed ordinary/executable bit-field transactions are unsupported',
                      engine.error)
        self.assertEqual(len(self.memory.writes), writes_before)
        # Only the provider publication hold ever happened.
        self.assertEqual(len(self.coordinator.holds), 1)

    def test_tick_after_permit_revocation_refuses_and_quarantines(self):
        engine = self._make_engine('revoked')
        self.assertTrue(engine.toggle(1, True))
        self.memory.write(FLAG, b'\x07\x00\x00\x00')
        self.assertTrue(engine.set_freeze(3, True))
        self.memory.write(FLAG, b'\x55\x00\x00\x00')
        engine.poll()
        self.assertFalse(engine.blocked, engine.error)
        self.assertEqual(self.memory.read(FLAG, 4), b'\x07\x00\x00\x00')
        self.assertFalse(engine.toggle(1, False))
        self.memory.write(FLAG, b'\x55\x00\x00\x00')
        writes_before = len(self.memory.writes)
        engine.poll()
        self.assertTrue(engine.blocked)
        self.assertIn('fully covered live provider literal permit', engine.error)
        self.assertEqual(len(self.memory.writes), writes_before)
        self.assertIn(3, engine.frozen)  # the failed tick keeps the frozen wish

    def test_expired_proof_after_write_blocks_and_retains_journal(self):
        engine = self._make_engine('expired')
        self.assertTrue(engine.toggle(1, True))
        # Hold 0: provider publication. Hold 1: transient publication (the
        # write lands). Hold 2: commit_data_only, whose proof check is expired.
        self.coordinator.expire_from_hold = 2
        with self.assertRaisesRegex(NativeRuntimeError, 'safe point is absent'):
            engine.set_value(3, '0xABC')
        self.assertTrue(engine.blocked)
        self.assertIn('Bit-field literal mutation is uncertain', engine.error)
        self.assertEqual(self.memory.read(FLAG, 2), b'\xBC\x0A')
        journals = [json.loads(path.read_text(encoding='utf-8'))
                    for path in (self.root / 'expired' / 'hooks').glob('*.json')]
        bitfield_receipt = next(item for item in journals
                                if item['owner'].endswith(':bitfield-value'))
        self.assertEqual(bitfield_receipt['state'], 'enabled')
        self.assertFalse(bitfield_receipt['data_commit'])
        self.assertFalse(bitfield_receipt['uncertain'])
        writes_before = len(self.memory.writes)
        with self.assertRaises(NativeRuntimeError):
            engine.set_value(3, '0xDEF')
        self.assertEqual(len(self.memory.writes), writes_before)
        self.assertEqual(self.memory.read(FLAG, 2), b'\xBC\x0A')


if __name__ == '__main__':
    unittest.main()
