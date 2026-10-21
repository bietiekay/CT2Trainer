"""Self-healing state-lock / shutdown behaviour after the 2026-10-20 field case.

Sinking City 2 (0.16) re-cut: the trainer could not be restarted after a
failed close because a blocked engine refused ``close()`` while its target was
exiting, which orphaned ``state.lock`` (the atexit net could not release it
either, because ``store.close()`` refuses while a process session remains).

These tests pin the three fixes:

1. ``close()`` completes when the engine is blocked but the target is gone -
   nothing is left to restore, so the state lock and session are released and
   the saved wishes survive in ``state.json``. A blocked engine with a still-
   alive target keeps the fail-closed refusal.
2. the atexit net releases the session and lock at interpreter exit once the
   target is provably gone, and preserves the state while the target is alive.
3. the stale-lock probe retries a transient ``unknown`` owner probe once, and -
   when the owner is proven dead but the full assessment is not eligible (most
   commonly: the previous session's target is still running) - the startup
   refusal is actionable instead of the generic "delete that folder" line.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import StateError, StaleStateRecoverable, TrainerEngine
from ct2trainer.native.recovery import ProcessObservation, WAIT_OBJECT_0
from test_native_engine import FakeMemory


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "windows" / "fixture_target" / "fixture.ct"

OWNER_PID, OWNER_CREATED = 333, 3333
TARGET_PID, TARGET_CREATED = 444, 4444


def _json(document):
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode()


# ---------------------------------------------------------------------------
# Fix 1 + Fix 2: engine-level close() and atexit behaviour
# ---------------------------------------------------------------------------

class BlockedCloseSelfHealTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.shared = self.directory / "shared"
        self.plan = compile_table(FIXTURE, "FixtureTarget.exe")
        self.memory = FakeMemory()
        self.engine = None

    def tearDown(self):
        if self.engine is not None and not self.engine.closed:
            self.engine.close()
        self.temp.cleanup()

    def start(self):
        self.engine = TrainerEngine(self.plan, self.directory,
                                    lambda _name: self.memory, self.shared)
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)
        return self.engine

    def test_close_completes_when_blocked_and_target_gone(self):
        engine = self.start()
        engine.toggle(1, True)
        self.assertTrue(engine.connected)
        # Field sequence: the target exits mid-receipt-read, the poll tick
        # classifies it as a PatchConflict and blocks the engine; by the time
        # the user closes the trainer the target is gone.
        engine.blocked = True
        engine.error = ("An executable hook receipt changed: ReadProcessMemory "
                        "failed (Win32 error 299).")
        self.memory.alive = False
        self.assertTrue(engine.close())
        self.assertTrue(engine.closed)
        self.assertFalse((self.directory / "state.lock").exists())
        self.assertFalse((self.directory / "session.json").exists())
        self.assertFalse((self.shared /
                          f"{self.memory.pid}-{self.memory.creation_time}.json").exists())
        # Saved wishes survive in state.json for the next attach.
        self.assertTrue((self.directory / "state.json").exists())

    def test_close_refused_when_blocked_and_target_alive(self):
        engine = self.start()
        engine.toggle(1, True)
        engine.blocked = True
        engine.error = "An executable hook receipt changed."
        self.memory.alive = True  # the target is still running
        self.assertFalse(engine.close())
        # Fail-closed: the state is preserved for manual recovery after the
        # target restarts, so no silent release happens while patches may be
        # still live in the running target.
        self.assertTrue((self.directory / "state.lock").exists())
        self.assertTrue((self.directory / "session.json").exists())

    def test_atexit_releases_session_and_lock_when_target_gone(self):
        engine = self.start()
        engine.toggle(1, True)
        # White-box the atexit net: the interpreter is exiting with the engine
        # already closed, the session still held, and the target provably gone
        # (the memory object is still open but reports dead). close() itself
        # never nulls the memory while leaving the session, so this branch is
        # only reachable in a "process died without completing close()" shape
        # and is pinned here directly.
        engine.memory.alive = False
        engine.closed = True
        engine._atexit_close()
        self.assertFalse((self.directory / "state.lock").exists())
        self.assertFalse((self.directory / "session.json").exists())
        self.assertFalse((self.shared /
                          f"{self.memory.pid}-{self.memory.creation_time}.json").exists())
        self.assertTrue((self.directory / "state.json").exists())

    def test_atexit_preserves_state_when_target_alive(self):
        engine = self.start()
        engine.toggle(1, True)
        engine.blocked = True
        engine.error = "An executable hook receipt changed."
        engine.close()  # target alive -> refused; the failure path drops the handle
        self.memory.alive = True
        engine._atexit_close()
        # With the target still alive the session and lock stay preserved for
        # the verified stale-state recovery on the next start.
        self.assertTrue((self.directory / "state.lock").exists())
        self.assertTrue((self.directory / "session.json").exists())


# ---------------------------------------------------------------------------
# Fix 3: stale-lock startup classification
# ---------------------------------------------------------------------------

class StaleLockSelfHealStartupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="native-stale-lock-selfheal-")
        self.root = Path(self.temp.name)
        self.state = self.root / "state"
        self.shared = self.root / "shared"
        self.state.mkdir()
        self.shared.mkdir()
        self.plan = compile_table(FIXTURE, "FixtureTarget.exe")
        script_ids = [e["id"] for e in self.plan["entries"]
                      if e["selected"] and e["supported"] and e["kind"] == "script"]
        if not script_ids:
            self.skipTest("fixture plan has no script entries")
        self.desired_id = script_ids[0]
        self.lock_doc = {"schema": 2, "owner_pid": OWNER_PID, "owner_created": OWNER_CREATED,
                         "nonce": "c" * 32}

    def tearDown(self):
        self.temp.cleanup()

    def _write_state(self, with_session=True):
        payload = {"schema": 1, "engine": "ct2trainer", "trainer_id": self.plan["trainer_id"],
                   "table_sha256": self.plan["table_sha256"],
                   "process_name": self.plan["process_name"],
                   "desired": [self.desired_id]}
        (self.state / "state.json").write_bytes(
            _json({"payload": payload, "sha256": hashlib.sha256(_json(payload)).hexdigest()}))
        (self.state / "state.lock").write_bytes(_json(self.lock_doc))
        if with_session:
            session = {"schema": 1, "owner": self.lock_doc,
                       "trainer_id": self.plan["trainer_id"],
                       "target_pid": TARGET_PID, "target_created": TARGET_CREATED}
            (self.state / "session.json").write_bytes(_json(session))
            (self.shared / f"{TARGET_PID}-{TARGET_CREATED}.json").write_bytes(_json(session))

    def _engine(self, probe):
        return TrainerEngine(self.plan, self.state, lambda _name: None, self.shared,
                             process_probe=probe)

    def test_transient_unknown_owner_probe_is_retried_and_recoverable(self):
        self._write_state()
        owner_probes = []

        def probe(identity):
            if identity.pid == OWNER_PID:
                owner_probes.append(identity.created)
                if len(owner_probes) == 1:
                    # First observation is a transient, non-conclusive probe.
                    return ProcessObservation(identity, "unknown", None, None)
                return ProcessObservation(identity, "dead", identity.created, WAIT_OBJECT_0)
            return ProcessObservation(identity, "dead", identity.created, WAIT_OBJECT_0)

        # A single transient "unknown" is retried; without the retry the first
        # observation would have produced the conservative refusal, not this
        # recoverable handle.
        with self.assertRaises(StaleStateRecoverable) as ctx:
            self._engine(probe)
        self.assertGreaterEqual(len(owner_probes), 2)
        self.assertTrue(ctx.exception.assessment.eligible,
                        ctx.exception.assessment.reasons)

    def test_persistent_unknown_owner_still_blocks(self):
        self._write_state()

        def probe(identity):
            return ProcessObservation(identity, "unknown", None, None)

        # Even with the retry, a never-conclusive owner keeps the conservative
        # refusal so a second running instance is never displaced silently.
        with self.assertRaises(StateError) as ctx:
            self._engine(probe)
        self.assertNotIsInstance(ctx.exception, StaleStateRecoverable)
        self.assertTrue((self.state / "state.lock").exists())

    def test_ineligible_assessment_yields_actionable_refusal(self):
        self._write_state()

        def probe(identity):
            # The owner is dead, but the previous session's target is still
            # running (field case 2026-10-20 at the 19:18 restart).
            if identity.pid == TARGET_PID:
                return ProcessObservation(identity, "alive", identity.created, WAIT_OBJECT_0)
            return ProcessObservation(identity, "dead", identity.created, WAIT_OBJECT_0)

        with self.assertRaises(StateError) as ctx:
            self._engine(probe)
        self.assertNotIsInstance(ctx.exception, StaleStateRecoverable)
        msg = str(ctx.exception)
        # The refusal is actionable: it names the verified-dead owner, surfaces
        # the concrete assessment reason (the still-alive target), and points to
        # the state directory - instead of the bare "delete that folder" line.
        self.assertIn(str(OWNER_PID), msg)
        self.assertIn("verified as terminated", msg)
        self.assertIn("not proven dead", msg)
        self.assertIn("State directory:", msg)
        self.assertTrue((self.state / "state.lock").exists())


if __name__ == "__main__":
    unittest.main()
