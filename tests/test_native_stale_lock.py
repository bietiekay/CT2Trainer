"""Startup detection of stale state locks and the user-confirmed recovery path."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import (
    StateError,
    StaleStateRecoverable,
    TrainerEngine,
    perform_stale_recovery,
)
from ct2trainer.native.recovery import ProcessObservation, WAIT_OBJECT_0


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "windows" / "fixture_target" / "fixture.ct"

OWNER_PID, OWNER_CREATED = 333, 3333
TARGET_PID, TARGET_CREATED = 444, 4444


def _json(document):
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode()


def _probe(status="dead", status_for_pid=None):
    """Deterministic process probe: per-PID override, default status otherwise."""

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


class StaleLockStartupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="native-stale-lock-")
        self.addCleanup(self.temp.cleanup)
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

    def _write_state(self, with_session=True, lock_doc=None, lock_bytes=None):
        payload = {"schema": 1, "engine": "ct2trainer", "trainer_id": self.plan["trainer_id"],
                   "table_sha256": self.plan["table_sha256"], "process_name": self.plan["process_name"],
                   "desired": [self.desired_id]}
        (self.state / "state.json").write_bytes(
            _json({"payload": payload, "sha256": hashlib.sha256(_json(payload)).hexdigest()}))
        if lock_bytes is not None:
            (self.state / "state.lock").write_bytes(lock_bytes)
        else:
            (self.state / "state.lock").write_bytes(_json(lock_doc or self.lock_doc))
        if with_session:
            session = {"schema": 1, "owner": self.lock_doc, "trainer_id": self.plan["trainer_id"],
                       "target_pid": TARGET_PID, "target_created": TARGET_CREATED}
            (self.state / "session.json").write_bytes(_json(session))
            (self.shared / f"{TARGET_PID}-{TARGET_CREATED}.json").write_bytes(_json(session))

    def _engine(self, probe):
        return TrainerEngine(self.plan, self.state, lambda _name: None, self.shared,
                             process_probe=probe)

    def test_dead_owner_offers_confirmed_recovery_and_preserves_saved_state(self):
        state_bytes_before = None
        self._write_state()
        state_bytes_before = (self.state / "state.json").read_bytes()
        with self.assertRaises(StaleStateRecoverable) as ctx:
            self._engine(_probe())
        stale = ctx.exception
        self.assertTrue(stale.assessment.eligible, stale.assessment.reasons)
        self.assertEqual(stale.archive_directory, self.root / "archives")
        self.assertTrue((self.state / "state.lock").exists())  # probe is read-only
        ok, detail = perform_stale_recovery(stale, process_probe=_probe())
        self.assertTrue(ok, detail)
        self.assertFalse((self.state / "state.lock").exists())
        self.assertFalse((self.state / "session.json").exists())
        self.assertFalse((self.shared / f"{TARGET_PID}-{TARGET_CREATED}.json").exists())
        self.assertEqual((self.state / "state.json").read_bytes(), state_bytes_before)
        self.assertTrue(any(stale.archive_directory.glob("native-recovery-*.zip")))
        engine = self._engine(_probe())
        try:
            self.assertEqual(engine.desired, {self.desired_id})  # saved switch survives
        finally:
            engine.close()

    def test_absent_owner_is_recoverable(self):
        self._write_state(with_session=False)
        with self.assertRaises(StaleStateRecoverable) as ctx:
            self._engine(_probe("absent"))
        self.assertTrue(ctx.exception.assessment.eligible, ctx.exception.assessment.reasons)

    def test_reused_owner_is_recoverable(self):
        self._write_state(with_session=False)
        with self.assertRaises(StaleStateRecoverable) as ctx:
            self._engine(_probe("reused"))
        self.assertTrue(ctx.exception.assessment.eligible, ctx.exception.assessment.reasons)

    def test_live_owner_still_blocks(self):
        self._write_state()
        with self.assertRaises(StateError) as ctx:
            self._engine(_probe("alive"))
        self.assertNotIsInstance(ctx.exception, StaleStateRecoverable)
        self.assertTrue((self.state / "state.lock").exists())

    def test_unproven_owner_still_blocks(self):
        self._write_state()
        with self.assertRaises(StateError) as ctx:
            self._engine(_probe("unknown"))
        self.assertNotIsInstance(ctx.exception, StaleStateRecoverable)

    def test_legacy_lock_without_creation_time_still_blocks(self):
        self._write_state(lock_doc={"schema": 1, "owner_pid": OWNER_PID, "nonce": "c" * 32})
        with self.assertRaises(StateError) as ctx:
            self._engine(_probe())
        self.assertNotIsInstance(ctx.exception, StaleStateRecoverable)

    def test_corrupt_lock_still_blocks(self):
        self._write_state(lock_bytes=b"\x01\x02not-json")
        with self.assertRaises(StateError) as ctx:
            self._engine(_probe())
        self.assertNotIsInstance(ctx.exception, StaleStateRecoverable)

    def test_live_target_blocks_recovery(self):
        self._write_state()
        with self.assertRaises(StateError) as ctx:
            self._engine(_probe(status_for_pid={TARGET_PID: "alive"}))
        self.assertNotIsInstance(ctx.exception, StaleStateRecoverable)
        self.assertTrue((self.state / "state.lock").exists())


class StaleRecoveryRefusalTests(unittest.TestCase):
    def test_perform_stale_recovery_rejects_a_foreign_handle(self):
        ok, detail = perform_stale_recovery("not-a-handle")
        self.assertFalse(ok)
        self.assertEqual(detail, "Not a recoverable stale-state handle")


@unittest.skipUnless(sys.platform == "win32", "Windows held-file recovery required")
class StaleRecoveryFailureTests(StaleLockStartupTests):
    def test_state_change_after_assessment_never_releases_silently(self):
        self._write_state()
        before = (self.state / "state.json").read_bytes()
        with self.assertRaises(StaleStateRecoverable) as ctx:
            self._engine(_probe())
        stale = ctx.exception
        (self.state / "foreign.txt").write_bytes(b"x")  # state changed after the assessment
        ok, detail = perform_stale_recovery(stale, process_probe=_probe())
        self.assertFalse(ok, detail)
        self.assertTrue((self.state / "state.lock").exists())  # no silent release
        self.assertEqual(before, (self.state / "state.json").read_bytes())
