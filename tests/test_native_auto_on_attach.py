"""Auto-on wishes requested while disconnected, fulfilled at the next attach.

Covers the user-visible contract: while no target is attached the user can
queue any supported script switch for auto-on at the next game launch
(``request_auto_on``) and cancel it again (``clear_desired``). Regular
switches restore as before; one-shot wishes stay pending until their first
confirmed publish at attach time (exactly one publish), and a failed pending
wish is never saved as a wish but stays in the saved state and is retried on
the next attach. Pinned statuses and the saved-marker invariant (saved implies
auto-on, pending is legitimate, saved-without-wish is refused) are covered.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from test_native_engine import FakeMemory
from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import NativeRuntimeError, TrainerEngine


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


class AutoOnAttachTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.shared = self.directory / 'shared'
        self.plan = compile_table(FIXTURE, 'FixtureTarget.exe')
        self.memory = Memory()
        self.factory = lambda _name: self.memory
        self.engine = None
        self.engines = []

    def tearDown(self):
        for engine in self.engines:
            if not engine.closed:
                engine.close()

    def start(self, attach=True):
        engine = TrainerEngine(self.plan, self.directory, self.factory, self.shared)
        self.engine = engine
        self.engines.append(engine)
        if attach:
            engine.poll()
            self.assertTrue(engine.connected, engine.status)
        return engine

    def detach(self, engine):
        self.memory.alive = False
        engine.poll()
        self.assertIsNone(engine.memory)

    def reattach(self, engine):
        self.memory.alive = True
        engine.poll()
        self.assertTrue(engine.connected, engine.status)

    def test_request_auto_on_is_refused_while_attached(self):
        engine = self.start()
        with self.assertRaisesRegex(
                NativeRuntimeError,
                "Auto-on can only be requested while safely disconnected"):
            engine.request_auto_on(5)
        self.assertNotIn(5, engine.desired)
        self.assertEqual(engine.desired, set())

    def test_regular_record_auto_on_applies_exactly_once_at_attach(self):
        engine = self.start(attach=False)
        engine.request_auto_on(5)
        self.assertIn(5, engine.desired)
        self.assertEqual(engine.status,
                         "Two-phase script (control): auto-on requested for next game launch")
        self.assertNotIn(5, engine.applied)
        self.assertEqual(self.memory.read(0x1020, 1), b'\x00')

        self.memory.alive = True
        engine.poll()
        self.assertTrue(engine.connected, engine.status)
        self.assertIn(5, engine.applied)
        self.assertIn(5, engine.desired)
        self.assertEqual(self.memory.read(0x1020, 1), b'\x05')

        # A second attach generation re-applies the saved switch (CE parity).
        self.detach(engine)
        self.memory.data[32:33] = b'\x00'  # fresh target memory
        self.reattach(engine)
        self.assertIn(5, engine.applied)
        self.assertEqual(self.memory.read(0x1020, 1), b'\x05')

    def test_one_shot_pending_wish_fulfilled_exactly_once_at_attach(self):
        engine = self.start(attach=False)
        engine.request_auto_on(0)
        self.assertIn(0, engine.desired)
        self.assertNotIn(0, engine.one_shot.saved_wish_ids())
        self.assertNotIn(0, engine.applied)
        self.assertEqual(self.memory.read(0x1014, 4), bytes(4))

        self.memory.alive = True
        engine.poll()
        self.assertTrue(engine.connected, engine.status)
        self.assertIn(0, engine.applied)
        self.assertIn(0, engine.desired)
        self.assertIn(0, engine.one_shot.saved_wish_ids())
        self.assertEqual(self.memory.read(0x1014, 4), b'\x01\x00\x00\x00')
        self.assertEqual(engine.one_shot.attempts, [(0, 1, 'explicit', 'confirmed')])

        # Re-attach generation: the saved wish is replayed exactly once.
        self.detach(engine)
        self.memory.data[20:24] = bytes(4)  # fresh target memory
        self.reattach(engine)
        self.assertEqual(self.memory.read(0x1014, 4), b'\x01\x00\x00\x00')
        self.assertEqual(engine.one_shot.attempts,
                         [(0, 1, 'explicit', 'confirmed'),
                          (0, 2, 'replay', 'confirmed')])

    def test_failed_pending_wish_stays_desired_and_retries_after_fix(self):
        engine = self.start(attach=False)
        self.memory.data[20:24] = b'\x99' * 4  # corrupt the expected original bytes
        engine.request_auto_on(0)
        self.memory.alive = True
        engine.poll()
        self.assertTrue(engine.connected, engine.status)
        self.assertNotIn(0, engine.applied)
        self.assertIn(0, engine.desired, 'a failed pending wish is not saved, stays desired')
        self.assertNotIn(0, engine.one_shot.saved_wish_ids())
        self.assertIn(0, engine.entry_errors)
        self.assertEqual(self.memory.read(0x1014, 4), b'\x99' * 4)
        self.assertEqual([(a[0], a[1], a[2], a[3]) for a in engine.one_shot.attempts
                          if a[0] == 0],
                         [(0, 1, 'explicit', 'failed')])

        # Next attach (fresh target memory) retries the pending wish.
        self.detach(engine)
        self.memory.data[20:24] = bytes(4)
        self.reattach(engine)
        self.assertIn(0, engine.applied)
        self.assertIn(0, engine.one_shot.saved_wish_ids())
        self.assertEqual(self.memory.read(0x1014, 4), b'\x01\x00\x00\x00')

    def test_request_auto_on_is_idempotent(self):
        engine = self.start(attach=False)
        engine.request_auto_on(0)
        first_status = engine.status
        engine.request_auto_on(0)
        self.assertEqual(first_status,
                         "One-shot write, missing DISABLE: auto-on requested for next game launch")
        self.assertEqual(engine.status,
                         "One-shot write, missing DISABLE: already auto-on for next game launch")
        self.assertEqual(engine.desired, {0})

    def test_clear_desired_cancels_pending_wish_before_attach(self):
        engine = self.start(attach=False)
        engine.request_auto_on(0)
        engine.clear_desired(0)
        self.assertNotIn(0, engine.desired)
        self.assertNotIn(0, engine.one_shot.saved_wish_ids())
        self.memory.alive = True
        engine.poll()
        self.assertTrue(engine.connected, engine.status)
        self.assertNotIn(0, engine.applied)
        self.assertEqual(self.memory.read(0x1014, 4), bytes(4))

    def test_request_auto_on_refuses_blocked_entry(self):
        engine = self.start(attach=False)
        with self.assertRaisesRegex(
                NativeRuntimeError,
                "Both ENABLE and DISABLE sections are required"):
            engine.request_auto_on(6)
        self.assertEqual(engine.desired, set())

    def test_pending_wish_survives_controller_restart(self):
        engine = self.start(attach=False)
        engine.request_auto_on(0)
        self.assertTrue((self.directory / 'state.json').exists())
        self.assertFalse((self.directory / 'oneshot.json').exists())
        self.assertTrue(engine.close())

        self.memory.alive = True
        engine2 = TrainerEngine(self.plan, self.directory, self.factory, self.shared)
        self.engines.append(engine2)
        self.assertIn(0, engine2.desired, 'the pending wish comes from state.json only')
        engine2.poll()
        self.assertTrue(engine2.connected, engine2.status)
        self.assertIn(0, engine2.applied)
        self.assertIn(0, engine2.one_shot.saved_wish_ids())
        self.assertEqual(engine2.one_shot.attempts, [(0, 1, 'explicit', 'confirmed')])
        self.assertEqual(self.memory.read(0x1014, 4), b'\x01\x00\x00\x00')

    def test_saved_and_pending_wishes_attach_independently(self):
        engine = self.start()
        self.assertTrue(engine.toggle(1, True))  # explicit saved wish for one-shot 1
        self.detach(engine)
        engine.request_auto_on(0)  # pending wish for one-shot 0
        self.memory.data[20:28] = bytes(8)  # fresh target memory for re-attach
        self.reattach(engine)
        self.assertIn(0, engine.applied)
        self.assertIn(1, engine.applied)
        self.assertEqual(self.memory.read(0x1014, 4), b'\x01\x00\x00\x00')
        self.assertEqual(self.memory.read(0x1018, 4), b'\x02\x00\x00\x00')
        self.assertEqual([(a[0], a[1], a[2], a[3]) for a in engine.one_shot.attempts],
                         [(1, 1, 'explicit', 'confirmed'),
                          (0, 2, 'explicit', 'confirmed'),
                          (1, 2, 'replay', 'confirmed')])


if __name__ == "__main__":
    unittest.main()
