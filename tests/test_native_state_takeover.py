"""Live-owner state-lock takeover: user-confirmed termination instead of a dead end."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import (
    LiveStateConflict,
    StateError,
    StaleStateRecoverable,
    TrainerEngine,
    terminate_live_session,
)
from ct2trainer.native.recovery import ProcessObservation, WAIT_OBJECT_0


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "windows" / "fixture_target" / "fixture.ct"

OWNER_PID, OWNER_CREATED = 777, 7777
TARGET_PID, TARGET_CREATED = 888, 8888


def _json(document):
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode()


def _probe(status="dead", status_for_pid=None):
    def probe(identity):
        chosen = status_for_pid.get(identity.pid, status) if status_for_pid is not None else status
        if chosen == "dead":
            return ProcessObservation(identity, "dead", identity.created, WAIT_OBJECT_0)
        if chosen == "alive":
            return ProcessObservation(identity, "alive", identity.created, WAIT_OBJECT_0)
        if chosen == "reused":
            return ProcessObservation(identity, "reused", identity.created + 1, WAIT_OBJECT_0)
        if chosen == "absent":
            return ProcessObservation(identity, "absent", None, None)
        return ProcessObservation(identity, "unknown", None, None)

    return probe


class LiveOwnerClassificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="native-takeover-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / "state"
        self.shared = self.root / "shared"
        self.state.mkdir()
        self.shared.mkdir()
        self.plan = compile_table(FIXTURE, "FixtureTarget.exe")
        self.lock_doc = {"schema": 2, "owner_pid": OWNER_PID, "owner_created": OWNER_CREATED,
                         "nonce": "c" * 32}

    def _write_state(self, lock_doc=None, lock_bytes=None):
        payload = {"schema": 1, "engine": "ct2trainer",
                   "trainer_id": self.plan["trainer_id"],
                   "table_sha256": self.plan["table_sha256"],
                   "process_name": self.plan["process_name"], "desired": []}
        (self.state / "state.json").write_bytes(
            _json({"payload": payload, "sha256": hashlib.sha256(_json(payload)).hexdigest()}))
        if lock_bytes is not None:
            (self.state / "state.lock").write_bytes(lock_bytes)
        else:
            (self.state / "state.lock").write_bytes(_json(lock_doc or self.lock_doc))

    def _engine(self, probe):
        return TrainerEngine(self.plan, self.state, lambda _name: None, self.shared,
                             process_probe=probe)

    def test_live_owner_raises_actionable_conflict(self):
        self._write_state()
        with self.assertRaises(LiveStateConflict) as ctx:
            self._engine(_probe("alive"))
        self.assertEqual(ctx.exception.owner_pid, OWNER_PID)
        self.assertEqual(ctx.exception.owner_created, OWNER_CREATED)
        self.assertEqual(ctx.exception.state_directory, self.state)
        self.assertIsInstance(ctx.exception, StateError)
        self.assertNotIsInstance(ctx.exception, StaleStateRecoverable)
        self.assertTrue((self.state / "state.lock").exists())

    def test_dead_owner_still_offers_stale_recovery(self):
        self._write_state()
        with self.assertRaises(StaleStateRecoverable) as ctx:
            self._engine(_probe("dead"))
        self.assertNotIsInstance(ctx.exception, LiveStateConflict)
        self.assertTrue(ctx.exception.assessment.eligible, ctx.exception.assessment.reasons)

    def test_unprovable_owner_keeps_conservative_refusal(self):
        self._write_state()
        with self.assertRaises(StateError) as ctx:
            self._engine(_probe("unknown"))
        self.assertNotIsInstance(ctx.exception, LiveStateConflict)
        self.assertNotIsInstance(ctx.exception, StaleStateRecoverable)
        self.assertIn("Delete that folder to start fresh", str(ctx.exception))

    def test_legacy_lock_without_creation_time_keeps_conservative_refusal(self):
        self._write_state(lock_doc={"schema": 1, "owner_pid": OWNER_PID, "nonce": "c" * 32})
        with self.assertRaises(StateError) as ctx:
            self._engine(_probe("alive"))
        self.assertNotIsInstance(ctx.exception, LiveStateConflict)
        self.assertIn("Delete that folder to start fresh", str(ctx.exception))

    def test_corrupt_lock_keeps_conservative_refusal(self):
        self._write_state(lock_bytes=b"\x01\x02not-json")
        with self.assertRaises(StateError) as ctx:
            self._engine(_probe("alive"))
        self.assertNotIsInstance(ctx.exception, LiveStateConflict)
        self.assertIn("Delete that folder to start fresh", str(ctx.exception))


@unittest.skipUnless(sys.platform == "win32", "Live session termination requires Windows")
class TerminateLiveSessionTests(unittest.TestCase):
    def _spawn(self, sleep_s: float = 60) -> subprocess.Popen:
        return subprocess.Popen([sys.executable, "-c", f"import time; time.sleep({sleep_s})"])

    def test_rejects_invalid_arguments(self):
        ok, detail = terminate_live_session(0)
        self.assertFalse(ok)
        self.assertEqual(detail, "Invalid owner PID")
        ok, detail = terminate_live_session(123, timeout_ms=0)
        self.assertFalse(ok)
        self.assertEqual(detail, "Invalid termination timeout")
        ok, detail = terminate_live_session(123, owner_created=0)
        self.assertFalse(ok)
        self.assertEqual(detail, "Invalid owner creation identity")

    def test_refuses_a_reused_pid(self):
        proc = self._spawn()
        self.addCleanup(self._kill_quietly, proc)
        time.sleep(0.5)
        ok, detail = terminate_live_session(proc.pid, owner_created=OWNER_CREATED)
        self.assertFalse(ok)
        self.assertIn("creation identity mismatch", detail)
        self.assertIsNone(proc.poll())

    def test_terminates_a_live_process(self):
        proc = self._spawn()
        time.sleep(0.5)
        ok, detail = terminate_live_session(proc.pid)
        self.assertTrue(ok, detail)
        self.assertEqual(detail, f"Terminated trainer session PID {proc.pid}")
        deadline = time.monotonic() + 5
        while proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertIsNotNone(proc.poll())

    def test_reports_a_nonexistent_owner(self):
        # Windows never assigns a PID this high; OpenProcess must fail.
        ok, detail = terminate_live_session(0xFFFFFFFF)
        self.assertFalse(ok)
        self.assertIn("could not be opened", detail)

    @staticmethod
    def _kill_quietly(proc):
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()
