"""Engine attach pause / user hold (MT-12, 0.25).

Field request (2026-11-02, Master Trainer): the user must be able to
detach a running trainer session and choose later - and, in "ask"
attach mode, which process to attach to.  The engine gains the hold:

- ``pause_attach()`` gates the poll attach branch (no attach attempts
  while paused) without touching session state, journal or wishes;
- ``resume_attach()`` releases the hold; the next poll tick attempts
  the ordinary attach (honoring the injected memory factory, e.g. the
  Master's pinned PID);
- an explicit detach running under the hold (``reattach()``) keeps the
  paused status visible in the status line;
- refusals: paused while closed / blocked / busy is named.

Debug events: ``attach-paused`` / ``attach-resumed``.  The scenarios
reuse the rearm fixture table and fake memory; no real process is
touched.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_native_engine_code import Coordinator
from test_native_rearm import REARM_CT, RearmMemory

from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import NativeRuntimeError, TrainerEngine

LOG_NAME = "ct2trainer-debug.log"


class AttachPauseEngineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.cwd = self.root / "cwd"
        self.cwd.mkdir()
        table = self.root / "pause.ct"
        table.write_text(REARM_CT, encoding="utf-8")
        self.plan = compile_table(table, "FixtureTarget.exe", debug_log=True)
        self.memory = RearmMemory()
        self.memory.plant()
        self.engine = None
        self.factory_calls = 0

    def tearDown(self):
        if self.engine is not None and not self.engine.closed:
            self.engine.close()

    def _factory(self, name):
        self.factory_calls += 1
        return self.memory

    def start(self, attach=True):
        with patch("pathlib.Path.cwd", return_value=self.cwd):
            self.engine = TrainerEngine(
                self.plan, state_dir=self.root / "state",
                process_lock_dir=self.root / "shared",
                memory_factory=self._factory,
                hook_coordinator=Coordinator())
        if attach:
            self.engine.poll()
            self.assertTrue(self.engine.connected, self.engine.status)
        return self.engine

    def events(self):
        log = self.cwd / LOG_NAME
        if not log.exists():
            return []
        return [json.loads(line) for line in
                log.read_text(encoding="utf-8").splitlines() if line.strip()]

    def event(self, name):
        return [e for e in self.events() if e["event"] == name]

    # -- scenarios ---------------------------------------------------------

    def test_pause_hold_blocks_the_attach_branch_until_resumed(self):
        engine = self.start()
        engine.pause_attach()
        self.assertTrue(engine.attach_paused)
        self.assertEqual(engine.status, "Detached; waiting for user attach")
        self.assertEqual(len(self.event("attach-paused")), 1)

        # The explicit detach under the hold keeps the paused status.
        engine.reattach()
        self.assertIsNone(engine.memory)
        self.assertEqual(engine.status, "Detached; waiting for user attach")
        self.assertTrue(self.event("reattach-detached"))

        # Poll ticks must not attempt any attach while the hold stands.
        calls = self.factory_calls
        engine.poll()
        engine.poll()
        self.assertEqual(self.factory_calls, calls)
        self.assertIsNone(engine.memory)

        # Resume: the ordinary wait resumes and re-attaches.
        engine.resume_attach()
        self.assertFalse(engine.attach_paused)
        self.assertEqual(engine.status, "Waiting for FixtureTarget.exe")
        self.assertEqual(len(self.event("attach-resumed")), 1)
        engine.poll()
        self.assertTrue(engine.connected, engine.status)

    def test_pause_is_idempotent_and_resume_noop_when_not_paused(self):
        engine = self.start()
        engine.pause_attach()
        engine.pause_attach()  # idempotent
        self.assertEqual(len(self.event("attach-paused")), 1)
        engine.resume_attach()
        engine.resume_attach()  # no-op when not paused
        self.assertEqual(len(self.event("attach-resumed")), 1)
        self.assertFalse(engine.attach_paused)

    def test_pause_refused_while_busy_blocked_or_closed(self):
        engine = self.start()
        engine.busy = True
        with self.assertRaisesRegex(NativeRuntimeError, "in progress"):
            engine.pause_attach()
        engine.busy = False
        engine.blocked = True
        engine.error = "forced block for test"
        with self.assertRaisesRegex(NativeRuntimeError, "blocked"):
            engine.pause_attach()
        engine.blocked = False
        engine.error = ""
        engine.close()
        with self.assertRaisesRegex(NativeRuntimeError, "closed"):
            engine.pause_attach()
        with self.assertRaisesRegex(NativeRuntimeError, "closed"):
            engine.resume_attach()

    def test_reattach_unattached_with_active_hold_shows_paused_status(self):
        engine = self.start(attach=False)
        engine.pause_attach()
        engine.reattach()  # unattached: just re-arms the wait
        self.assertEqual(engine.status, "Detached; waiting for user attach")
        self.assertIsNone(engine.memory)
        engine.poll()
        self.assertEqual(self.factory_calls, 0)  # the hold gates the attach branch
        self.assertIsNone(engine.memory)
        engine.resume_attach()
        engine.poll()
        self.assertTrue(engine.connected, engine.status)

    def test_target_exit_while_attached_is_unaffected_by_the_hold(self):
        # The hold gates the wait-to-attach transition only; a live
        # target still exits through the ordinary poll path.
        engine = self.start()
        engine.pause_attach()
        self.memory.alive = False
        engine.poll()
        self.assertIsNone(engine.memory)
        self.assertTrue(self.event("target-exited"))
        # The hold survives: no re-attach while paused.
        self.memory.alive = True
        calls = self.factory_calls
        engine.poll()
        self.assertEqual(self.factory_calls, calls)
        self.assertIsNone(engine.memory)


if __name__ == "__main__":
    unittest.main()
