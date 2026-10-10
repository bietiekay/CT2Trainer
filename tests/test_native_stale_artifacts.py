"""Verified override for stale prior-session state artifacts.

Covers the startup refusal "Prior executable allocations still have an
unfinalized receipt. ..." and its artifact-family siblings (incomplete
session files, leftover shared claims): when every exact recorded process
identity is proven dead in two independent observations, the engine surfaces
a ``StaleArtifactsRecoverable`` handle that ``perform_stale_recovery`` can
archive and release while preserving ``state.json``. Anything unproven keeps
the conservative refusal so live or unknown state is never overridden.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import (StateError, StaleArtifactsRecoverable,
                                        StaleStateRecoverable, TrainerEngine,
                                        perform_stale_recovery)
from ct2trainer.native.recovery import (ProcessObservation, WAIT_OBJECT_0,
                                          WAIT_TIMEOUT, assess_recovery)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "windows" / "fixture_target" / "fixture.ct"
TARGET_PID = 990_001
TARGET_CREATED = 9_900_001


def _plan() -> dict:
    return compile_table(FIXTURE, "FixtureTarget.exe")


def _json(document) -> bytes:
    return json.dumps(document, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


class _DeadProbe:
    def __call__(self, identity):
        return ProcessObservation(identity, "dead", identity.created,
                                  WAIT_OBJECT_0)


class _AliveProbe:
    def __call__(self, identity):
        return ProcessObservation(identity, "alive", identity.created,
                                  WAIT_TIMEOUT)


def _hook_receipt(trainer_id: str, state: str = "enabled") -> dict:
    return {"schema": 1, "engine": "ct2trainer-hooks",
            "owner": trainer_id + ":fixture-owner",
            "target_pid": TARGET_PID, "target_created": TARGET_CREATED,
            "state": state, "uncertain": False,
            "allocations": {}, "blocks": [], "entries": [], "exports": {},
            "retirement_policy": "retain-published-allocations-until-target-exit"}


def _session_document(trainer_id: str, owner_pid: int = 990_002,
                      owner_created: int = 9_900_002) -> dict:
    return {"schema": 1,
            "owner": {"schema": 2, "owner_pid": owner_pid,
                      "owner_created": owner_created, "nonce": "c" * 32},
            "trainer_id": trainer_id,
            "target_pid": TARGET_PID, "target_created": TARGET_CREATED}


def _state_file(trainer_id: str, table_sha256: str) -> bytes:
    payload = {"schema": 1, "engine": "ct2trainer",
               "trainer_id": trainer_id, "table_sha256": table_sha256,
               "process_name": "FixtureTarget.exe", "desired": []}
    return json.dumps({"payload": payload,
                       "sha256": hashlib.sha256(_json(payload)).hexdigest()}) \
        .encode("utf-8")


def _layout(root: Path, trainer_id: str, table_sha256: str,
            with_session: bool = True, receipt_state: str = "enabled",
            journal_bytes: bytes | None = None):
    """Create sibling state/shared directories; never nested (assessment scope)."""
    state = root / "state"
    shared = root / "shared"
    (state / "hooks").mkdir(parents=True)
    shared.mkdir()
    (state / "state.json").write_bytes(_state_file(trainer_id, table_sha256))
    receipt = _json(_hook_receipt(trainer_id, state=receipt_state))
    (state / "hooks" / "hook.json").write_bytes(
        journal_bytes if journal_bytes is not None else receipt)
    if with_session:
        document = _json(_session_document(trainer_id))
        (state / "session.json").write_bytes(document)
        (shared / f"{TARGET_PID}-{TARGET_CREATED}.json").write_bytes(document)
    return state, shared


class AssessmentExclusiveClaimTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = _plan()
        cls.trainer_id = cls.plan["trainer_id"]
        cls.table_sha256 = cls.plan["table_sha256"]

    def _assess(self, state, shared, probe, claim):
        return assess_recovery(state, shared, process_probe=probe,
                               expected_trainer_id=self.trainer_id,
                               expected_table_sha256=self.table_sha256,
                               exclusive_controller_claim=claim)

    def test_journal_only_refused_without_claim_flag(self):
        with tempfile.TemporaryDirectory() as raw:
            state, shared = _layout(Path(raw), self.trainer_id,
                                    self.table_sha256, with_session=False)
            result = self._assess(state, shared, _DeadProbe(), claim=False)
            self.assertFalse(result.eligible)
            self.assertTrue(any("owner identity is unknown" in reason
                                for reason in result.reasons),
                            result.reasons)

    def test_journal_only_eligible_with_claim_flag_and_death_proof(self):
        with tempfile.TemporaryDirectory() as raw:
            state, shared = _layout(Path(raw), self.trainer_id,
                                    self.table_sha256, with_session=False)
            result = self._assess(state, shared, _DeadProbe(), claim=True)
            self.assertTrue(result.eligible, result.reasons)
            self.assertEqual(set(result.candidate_paths),
                             {state / "hooks" / "hook.json"})
            self.assertNotIn(state / "state.json", result.candidate_paths)

    def test_journal_only_flag_does_not_skip_target_death_proof(self):
        with tempfile.TemporaryDirectory() as raw:
            state, shared = _layout(Path(raw), self.trainer_id,
                                    self.table_sha256, with_session=False)
            result = self._assess(state, shared, _AliveProbe(), claim=True)
            self.assertFalse(result.eligible)

    def test_orphan_shared_claim_released_only_with_claim_flag(self):
        with tempfile.TemporaryDirectory() as raw:
            state, shared = _layout(Path(raw), self.trainer_id,
                                    self.table_sha256, with_session=False)
            document = _json(_session_document(self.trainer_id))
            (shared / f"{TARGET_PID}-{TARGET_CREATED}.json").write_bytes(document)
            claim = shared / f"{TARGET_PID}-{TARGET_CREATED}.json"
            without = self._assess(state, shared, _DeadProbe(), claim=False)
            self.assertFalse(without.eligible)
            self.assertTrue(any("no bound state/session owner" in reason
                                for reason in without.reasons),
                            without.reasons)
            with_flag = self._assess(state, shared, _DeadProbe(), claim=True)
            self.assertTrue(with_flag.eligible, with_flag.reasons)
            self.assertEqual(set(with_flag.candidate_paths),
                             {state / "hooks" / "hook.json", claim})


class StaleArtifactsEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.plan = _plan()
        self.trainer_id = self.plan["trainer_id"]
        self.table_sha256 = self.plan["table_sha256"]
        self.factory = lambda _name: None

    def _start(self, state, shared, probe):
        return TrainerEngine(self.plan, state, self.factory, shared,
                             process_probe=probe)

    def test_dead_target_yields_recoverable_handle_without_mutation(self):
        state, shared = _layout(self.root, self.trainer_id,
                                self.table_sha256, with_session=False)
        journal = state / "hooks" / "hook.json"
        before = journal.read_bytes()
        with self.assertRaises(StaleArtifactsRecoverable) as caught:
            self._start(state, shared, _DeadProbe())
        handle = caught.exception
        self.assertTrue(handle.assessment.eligible,
                        handle.assessment.reasons)
        self.assertTrue(handle.exclusive_controller_claim)
        self.assertEqual(handle.state_directory, state)
        self.assertEqual(handle.archive_directory, self.root / "archives")
        # The refusal is read-only: no artifact touched, no lock left behind.
        self.assertEqual(journal.read_bytes(), before)
        self.assertFalse((state / "state.lock").exists())
        self.assertFalse((state / "recovery.lock").exists())

    def test_live_target_keeps_conservative_refusal(self):
        state, shared = _layout(self.root, self.trainer_id,
                                self.table_sha256, with_session=False)
        with self.assertRaisesRegex(
                StateError,
                "Prior executable allocations still have an unfinalized receipt"):
            self._start(state, shared, _AliveProbe())

    def test_unreadable_receipt_keeps_conservative_refusal(self):
        state, shared = _layout(self.root, self.trainer_id,
                                self.table_sha256, with_session=False,
                                journal_bytes=b"not json at all")
        with self.assertRaisesRegex(
                StateError,
                "receipt is unreadable"):
            self._start(state, shared, _DeadProbe())

    def test_finalized_receipt_starts_cleanly(self):
        state, shared = _layout(self.root, self.trainer_id,
                                self.table_sha256, with_session=False,
                                receipt_state="target-exited")
        engine = self._start(state, shared, _DeadProbe())
        self.addCleanup(engine.close)
        self.assertTrue((state / "state.lock").exists(),
                        "a started engine holds the state lock")
        self.assertEqual(engine.desired, set())

    def test_session_backed_stale_state_yields_recoverable_handle(self):
        state, shared = _layout(self.root, self.trainer_id,
                                self.table_sha256, with_session=True)
        with self.assertRaises(StaleArtifactsRecoverable) as caught:
            self._start(state, shared, _DeadProbe())
        candidates = caught.exception.assessment.candidate_paths
        self.assertIn(state / "hooks" / "hook.json", candidates)
        self.assertIn(state / "session.json", candidates)
        self.assertIn(
            shared / f"{TARGET_PID}-{TARGET_CREATED}.json", candidates)

    def test_perform_stale_recovery_rejects_foreign_handle(self):
        ok, detail = perform_stale_recovery(object())
        self.assertFalse(ok)
        self.assertEqual(detail, "Not a recoverable stale-state handle")


@unittest.skipUnless(sys.platform == "win32",
                     "Real Windows held-file disposition profile")
class WindowsStaleArtifactsOperationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.plan = _plan()
        self.trainer_id = self.plan["trainer_id"]
        self.table_sha256 = self.plan["table_sha256"]
        self.factory = lambda _name: None

    def _handle(self, state, shared, with_session=True):
        with self.assertRaises(StaleArtifactsRecoverable) as caught:
            TrainerEngine(self.plan, state, self.factory, shared,
                          process_probe=_DeadProbe())
        return caught.exception

    def test_recovery_archives_releases_and_engine_starts(self):
        state, shared = _layout(self.root, self.trainer_id,
                                self.table_sha256, with_session=False)
        state_bytes = (state / "state.json").read_bytes()
        journal = state / "hooks" / "hook.json"
        journal_bytes = journal.read_bytes()
        handle = self._handle(state, shared)

        ok, detail = perform_stale_recovery(handle, process_probe=_DeadProbe())
        self.assertTrue(ok, detail)

        self.assertFalse(journal.exists(), "journal must be released")
        self.assertEqual((state / "state.json").read_bytes(), state_bytes,
                         "saved state must be preserved byte-for-byte")
        self.assertFalse((state / "state.lock").exists())
        self.assertFalse((state / "recovery.lock").exists())

        archives = sorted((self.root / "archives").glob("native-recovery-*.zip"))
        self.assertEqual(len(archives), 1, detail)
        with zipfile.ZipFile(archives[0]) as bundle:
            names = bundle.namelist()
            self.assertTrue(any(name.endswith("hook.json") for name in names),
                            names)
            member = [name for name in names
                      if name.endswith("hook.json")][0]
            self.assertEqual(bundle.read(member), journal_bytes)

        engine = TrainerEngine(self.plan, state, self.factory, shared)
        self.addCleanup(engine.close)
        self.assertEqual(engine.desired, set())

    def test_recovery_released_shared_claim_disappears(self):
        state, shared = _layout(self.root, self.trainer_id,
                                self.table_sha256, with_session=True)
        handle = self._handle(state, shared)
        ok, detail = perform_stale_recovery(handle, process_probe=_DeadProbe())
        self.assertTrue(ok, detail)
        self.assertFalse((shared / f"{TARGET_PID}-{TARGET_CREATED}.json").exists())
        self.assertFalse((state / "session.json").exists())

    def test_recovery_refused_without_death_proof_preserves_journal(self):
        state, shared = _layout(self.root, self.trainer_id,
                                self.table_sha256, with_session=False)
        journal = state / "hooks" / "hook.json"
        journal_bytes = journal.read_bytes()
        handle = self._handle(state, shared)

        ok, detail = perform_stale_recovery(handle, process_probe=_AliveProbe())
        self.assertFalse(ok)
        self.assertEqual(journal.read_bytes(), journal_bytes)
        self.assertTrue((state / "state.json").exists())


if __name__ == "__main__":
    unittest.main()
