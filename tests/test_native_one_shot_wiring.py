"""Root wiring for one-shot records: compiler classification and engine lifecycle.

Covers the feature ``one_shot_save_contract`` end to end: the compiler
classifies missing/empty [DISABLE] scripts as one-shot entries, the engine
executes exactly one bounded publish per ON, saves the wish only after a
confirmed ON, performs zero backend operations on OFF (the effect persists
in the target), replays saved wishes exactly once per attach generation,
and persists a tamper-evident marker file bound to the table.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from test_native_engine import FakeMemory
from test_native_engine_code import CodeMemory, Coordinator
from ct2trainer.native.compiler import NativeCompileError, compile_table, validate_plan
from ct2trainer.native.engine import (TrainerEngine, NativeRuntimeError, StateError,
                                        _canonical)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "windows" / "fixture_target" / "fixture_one_shot.ct"


class Memory(FakeMemory):
    @property
    def identity(self):
        return self.pid, self.creation_time

    def _range(self, address, size):
        if not self.base <= address or address + size > self.base + len(self.data):
            raise ValueError('Outside owned fixture memory')

    def is_executable(self, address, size):
        return False


class OneShotClassificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = compile_table(FIXTURE, 'FixtureTarget.exe')
        cls.entries = {entry['id']: entry for entry in cls.plan['entries']}

    def test_small_grammar_one_shots_are_classified_without_program(self):
        for record_id in (0, 1):
            entry = self.entries[record_id]
            self.assertIs(entry['supported'], True, entry['reason'])
            self.assertIs(entry.get('one_shot'), True)
            self.assertNotIn('program', entry)
            self.assertNotIn('lua_program', entry)
            self.assertEqual(entry['disable'], [])
            self.assertTrue(any(op['op'] == 'write' for op in entry['enable']))
            self.assertEqual(entry['requires'], [])

    def test_full_grammar_one_shot_carries_the_program_flag(self):
        entry = self.entries[2]
        self.assertIs(entry['supported'], True, entry['reason'])
        self.assertIs(entry.get('one_shot'), True)
        self.assertIs(entry['program']['one_shot'], True)
        self.assertEqual(entry['enable'], [])
        self.assertEqual(entry['disable'], [])

    def test_lua_one_shots_carry_the_program_flag(self):
        for record_id in (3, 4):
            entry = self.entries[record_id]
            self.assertIs(entry['supported'], True, entry['reason'])
            self.assertIs(entry.get('one_shot'), True)
            self.assertIs(entry['lua_program']['one_shot'], True)
            self.assertEqual(entry['enable'], [])
            self.assertEqual(entry['disable'], [])

    def test_two_phase_script_is_not_one_shot(self):
        entry = self.entries[5]
        self.assertIsNone(entry.get('one_shot'))
        self.assertTrue(entry['enable'])
        self.assertTrue(entry['disable'])
        self.assertNotIn('program', entry)

    def test_unguarded_one_shot_stays_blocked_with_pinned_reason(self):
        entry = self.entries[6]
        self.assertIs(entry['supported'], False)
        self.assertIn('Both ENABLE and DISABLE sections are required.', entry['reason'])
        self.assertIn('Program requires explicit ENABLE and DISABLE sections.',
                      entry['reason'])

    def test_forged_one_shot_flag_with_disable_phase_is_rejected(self):
        plan = deepcopy(self.plan)
        for entry in plan['entries']:
            if entry['id'] == 5:
                entry['one_shot'] = True
        with self.assertRaisesRegex(NativeCompileError, 'empty disable phase'):
            validate_plan(plan)

    def test_forged_program_flag_mismatch_is_rejected(self):
        plan = deepcopy(self.plan)
        for entry in plan['entries']:
            if entry['id'] == 2:
                entry['one_shot'] = False
        with self.assertRaisesRegex(NativeCompileError, 'does not match its source'):
            validate_plan(plan)


class OneShotEngineWiringTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.shared = self.directory / 'shared'
        self.plan = compile_table(FIXTURE, 'FixtureTarget.exe')
        self.memory = Memory()
        self.factory = lambda _name: self.memory
        self.engine = None

    def tearDown(self):
        if self.engine is not None and not self.engine.closed:
            self.engine.close()
        self.temp.cleanup()

    def start(self, attach=True, coordinator=None):
        self.engine = TrainerEngine(self.plan, self.directory, self.factory,
                                    self.shared,
                                    hook_coordinator=coordinator or 'debug-event')
        if attach:
            self.engine.poll()
            self.assertTrue(self.engine.connected, self.engine.status)
        return self.engine

    def detach(self):
        self.memory.alive = False
        self.engine.poll()
        self.assertIsNone(self.engine.memory)

    def reattach(self):
        self.memory.alive = True
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)

    def replay_attempts(self, record_id, source='replay'):
        return [attempt for attempt in self.engine.one_shot.attempts
                if attempt[0] == record_id and attempt[2] == source]

    def test_on_saves_wish_off_keeps_effect_without_backend_operations(self):
        engine = self.start()
        self.assertEqual(self.memory.read(0x1014, 4), bytes(4))

        self.assertTrue(engine.toggle(0, True))
        self.assertEqual(self.memory.read(0x1014, 4), b'\x01\x00\x00\x00')
        self.assertIn(0, engine.desired)
        self.assertIn(0, engine.applied)
        self.assertEqual(engine.status,
                         'One-shot write, missing DISABLE: one-shot enabled and saved')
        self.assertTrue((self.directory / 'oneshot.json').exists())
        state = engine.one_shot.query(0)
        self.assertEqual(state['phase'], 'EXECUTED')
        self.assertTrue(state['saved_wish'])
        self.assertTrue(state['effect_persists'])
        self.assertEqual(self.replay_attempts(0), [])

        writes = len(self.memory.writes)
        self.assertFalse(engine.toggle(0, False))
        self.assertEqual(len(self.memory.writes), writes,
                         'OFF must perform no backend operations')
        self.assertEqual(self.memory.read(0x1014, 4), b'\x01\x00\x00\x00')
        self.assertNotIn(0, engine.desired)
        self.assertIn(0, engine.applied, 'ownership stays until close or exit')
        state = engine.one_shot.query(0)
        self.assertFalse(state['saved_wish'])
        self.assertTrue(state['effect_persists'])
        self.assertEqual(engine.status,
                         'One-shot write, missing DISABLE: one-shot wish cleared; '
                         'effect persists in target')

        self.assertTrue(engine.toggle(0, True))
        self.assertEqual(len(self.memory.writes), writes,
                         're-ON re-confirms the intact effect without re-publishing')
        self.assertIn(0, engine.desired)

        self.assertTrue(engine.close())
        self.assertEqual(self.memory.read(0x1014, 4), bytes(4),
                         'close restores the owned patch')
        self.assertIn(0, engine.desired, 'the saved wish survives close')

    def test_off_without_effect_reports_nothing_to_disable(self):
        engine = self.start()
        writes = len(self.memory.writes)
        self.assertFalse(engine.toggle(0, False))
        self.assertEqual(len(self.memory.writes), writes)
        self.assertNotIn(0, engine.desired)
        self.assertEqual(engine.status,
                         'One-shot write, missing DISABLE: one-shot inactive; '
                         'nothing to disable')

    def test_failed_on_is_never_saved_and_never_replayed(self):
        engine = self.start()
        self.memory.data[20:24] = b'\x99' * 4
        with self.assertRaises(NativeRuntimeError):
            engine.toggle(0, True)
        self.assertNotIn(0, engine.desired)
        self.assertNotIn(0, engine.applied)
        self.assertEqual(self.memory.read(0x1014, 4), b'\x99' * 4)
        state = engine.one_shot.query(0)
        self.assertEqual(state['phase'], 'FAILED')
        self.assertFalse(state['saved_wish'])
        self.assertFalse(state['effect_persists'])
        self.assertEqual(self.replay_attempts(0), [])
        self.assertEqual(
            [attempt for attempt in engine.one_shot.attempts if attempt[0] == 0],
            [(0, 1, 'explicit', 'failed')])
        self.assertTrue((self.directory / 'oneshot.json').exists())

        # Re-attach: the failed attempt is never replayed, wish not re-saved.
        self.detach()
        self.reattach()
        self.assertEqual(self.memory.read(0x1014, 4), b'\x99' * 4)
        self.assertEqual(self.replay_attempts(0), [])
        self.assertNotIn(0, engine.one_shot.saved_wish_ids())

    def test_saved_wish_replays_once_per_attach_and_failed_replay_is_final(self):
        engine = self.start()
        self.assertTrue(engine.toggle(0, True))
        self.assertEqual(self.memory.read(0x1014, 4), b'\x01\x00\x00\x00')

        # Second attach generation: exactly one replay attempt. The persisted
        # effect means the guarded assert fails; the wish is not re-saved.
        self.detach()
        writes = len(self.memory.writes)
        self.reattach()
        self.assertEqual(len(self.memory.writes), writes)
        self.assertEqual(self.memory.read(0x1014, 4), b'\x01\x00\x00\x00')
        self.assertEqual(self.replay_attempts(0), [(0, 2, 'replay', 'failed')])
        self.assertIn(0, engine.entry_errors)
        self.assertIn(0, engine.one_shot.saved_wish_ids())

        # Third generation: the failed replay is never replayed again.
        self.detach()
        self.reattach()
        self.assertEqual(self.replay_attempts(0), [(0, 2, 'replay', 'failed')])
        self.assertEqual(self.memory.read(0x1014, 4), b'\x01\x00\x00\x00')

    def test_replay_after_external_revert_reapplies_once(self):
        engine = self.start()
        self.assertTrue(engine.toggle(0, True))
        self.assertEqual(self.memory.read(0x1014, 4), b'\x01\x00\x00\x00')

        self.detach()
        self.memory.data[20:24] = bytes(4)  # effect reverted while target was gone
        self.reattach()
        self.assertEqual(self.memory.read(0x1014, 4), b'\x01\x00\x00\x00',
                         'the replay re-applies the guarded write once')
        self.assertEqual(self.replay_attempts(0), [(0, 2, 'replay', 'confirmed')])
        self.assertNotIn(0, engine.entry_errors)

    def test_lua_one_shot_enables_and_off_keeps_ownership(self):
        engine = self.start()
        writes = len(self.memory.writes)

        self.assertTrue(engine.toggle(3, True))
        self.assertIn(3, engine.desired)
        self.assertIn(3, engine.applied)
        self.assertEqual(engine.status,
                         'One-shot Lua, empty DISABLE: one-shot enabled and saved')
        self.assertEqual(len(self.memory.writes), writes,
                         'a pure-Lua one-shot performs no owned memory write')
        state = engine.one_shot.query(3)
        self.assertTrue(state['saved_wish'])
        self.assertTrue(state['effect_persists'])

        self.assertFalse(engine.toggle(3, False))
        self.assertNotIn(3, engine.desired)
        self.assertIn(3, engine.applied,
                      'the owned scope stays open until close or exit')
        self.assertIn(3, engine.lua_activations)
        state = engine.one_shot.query(3)
        self.assertFalse(state['saved_wish'])
        self.assertTrue(state['effect_persists'])
        self.assertEqual(len(self.memory.writes), writes)

        self.assertTrue(engine.close())
        self.assertNotIn(3, engine.lua_activations)

    def test_program_one_shot_off_keeps_effect_and_close_restores(self):
        # The existing conservative link classification treats untrusted
        # non-allocation blocks as potentially executable, so both the target
        # byte and the published byte must form complete valid instructions
        # (same pattern as the executable literal tests). Use NOP/SBB to
        # isolate the one-shot wiring from the hook classification.
        self.memory.data[28] = 0x90
        engine = self.start(coordinator=Coordinator())
        self.assertEqual(self.memory.read(0x101C, 1), b'\x90')

        self.assertTrue(engine.toggle(2, True))
        self.assertEqual(self.memory.read(0x101C, 1), b'\x99')
        self.assertIn(2, engine.desired)
        state = engine.one_shot.query(2)
        self.assertTrue(state['saved_wish'])
        self.assertTrue(state['effect_persists'])

        self.assertFalse(engine.toggle(2, False))
        self.assertEqual(self.memory.read(0x101C, 1), b'\x99',
                         'OFF performs no backend operation for a one-shot program')
        self.assertNotIn(2, engine.desired)
        self.assertIn(2, engine.applied)

        self.assertTrue(engine.close())
        self.assertEqual(self.memory.read(0x101C, 1), b'\x90',
                         'close retires the owned assembly and restores it')

    def test_marker_roundtrip_survives_a_new_controller(self):
        engine = self.start()
        self.assertTrue(engine.toggle(0, True))
        self.assertEqual(self.memory.read(0x1014, 4), b'\x01\x00\x00\x00')
        self.assertTrue(engine.close())

        # A new controller restores the wish from the marker file and state.
        self.memory.closed = False
        second = TrainerEngine(self.plan, self.directory, self.factory, self.shared)
        self.assertIn(0, second.desired)
        self.assertIn(0, second.one_shot.saved_wish_ids())
        second.poll()
        self.assertTrue(second.connected, second.status)
        self.assertEqual(self.memory.read(0x1014, 4), b'\x01\x00\x00\x00',
                         'the saved wish is replayed on the new attach')
        self.assertEqual([a for a in second.one_shot.attempts if a[2] == 'replay'],
                         [(0, 1, 'replay', 'confirmed')])
        self.assertFalse(second.blocked)
        second.close()

    def test_tampered_markers_are_quarantined_and_engine_starts(self):
        engine = self.start()
        self.assertTrue(engine.toggle(0, True))
        self.assertTrue(engine.close())
        raw = bytearray((self.directory / 'oneshot.json').read_bytes())
        raw[-3] ^= 0xFF  # damage the marker CRC
        (self.directory / 'oneshot.json').write_bytes(bytes(raw))

        # Damaged marker data no longer holds startup hostage: the exact
        # bytes are quarantined and the engine starts with a fresh contract.
        # Documented trade-off: the saved wish survives in state.json, and a
        # re-enabled one-shot may run once more.
        self.memory.closed = False
        self.engine = TrainerEngine(self.plan, self.directory, self.factory,
                                    self.shared)
        quarantined = sorted(self.directory.glob('oneshot.json.corrupt-*'))
        self.assertEqual(len(quarantined), 1,
                         'the damaged marker file must be quarantined')
        self.assertEqual(quarantined[0].read_bytes(), bytes(raw))
        self.assertFalse((self.directory / 'oneshot.json').exists())
        self.assertIn(0, self.engine.desired,
                      'the saved wish survives in state.json')
        self.assertNotIn(0, self.engine.one_shot.saved_wish_ids(),
                         'marker memory is fresh after quarantine')

    def test_state_marker_mismatch_is_quarantined_and_engine_starts(self):
        engine = self.start()
        self.assertTrue(engine.toggle(0, True))
        self.assertTrue(engine.close())

        # Drop the wish from the state while the marker still carries it.
        document = json.loads((self.directory / 'state.json').read_bytes())
        document['payload']['desired'] = []
        document['sha256'] = hashlib.sha256(
            _canonical(document['payload'])).hexdigest()
        (self.directory / 'state.json').write_bytes(
            json.dumps(document).encode('utf-8'))
        marker_bytes = (self.directory / 'oneshot.json').read_bytes()

        # The stale marker is quarantined; no auto-on wish is restored, so the
        # dangerous direction (marker wish without saved-state entry) cannot
        # persist. The one-shot may run once more if the user re-enables it.
        self.memory.closed = False
        self.engine = TrainerEngine(self.plan, self.directory, self.factory,
                                    self.shared)
        quarantined = sorted(self.directory.glob('oneshot.json.corrupt-*'))
        self.assertEqual(len(quarantined), 1)
        self.assertEqual(quarantined[0].read_bytes(), marker_bytes)
        self.assertFalse((self.directory / 'oneshot.json').exists())
        self.assertEqual(self.engine.desired, set())
        self.assertNotIn(0, self.engine.one_shot.saved_wish_ids(),
                         'no stale auto-on wish may be restored')

    def test_clear_desired_clears_the_saved_one_shot_wish(self):
        engine = self.start()
        self.assertTrue(engine.toggle(0, True))
        self.assertIn(0, engine.one_shot.saved_wish_ids())

        self.detach()
        engine.clear_desired(0)
        self.assertNotIn(0, engine.desired)
        self.assertNotIn(0, engine.one_shot.saved_wish_ids())
        self.assertEqual(engine.one_shot.query(0)['saved_wish'], False)

        # The cleared wish is not replayed on the next attach.
        self.reattach()
        self.assertEqual(self.replay_attempts(0), [])
        self.assertNotIn(0, engine.one_shot.saved_wish_ids())


if __name__ == '__main__':
    unittest.main()
