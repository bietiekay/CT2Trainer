"""Self-healing startup paths for the Native state store and recovery.

Covers the recovery dead-end fixes:

- A leftover ``recovery.lock`` (fence) from a crashed recovery operation is
  recognized by ``assess_recovery`` (lone-fence eligibility, fence owner as
  an exact identity to be proven dead) and surfaced by the engine as a
  ``StaleArtifactsRecoverable`` handle; ``perform_stale_recovery`` takes the
  fence over byte-for-byte, archives it and releases it.
- A corrupt ``state.json`` is quarantined in place (exact bytes preserved
  under a ``.corrupt-`` stamp) instead of dead-ending every startup.
- Invalid or mismatched one-shot marker bytes are quarantined and the engine
  starts with a fresh one-shot contract (documented trade-off: a one-shot
  may run once more after re-enabling).
- A startup failure after the state claim releases the state lock again.
- The atexit safety net releases a still-open state store.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import (StateError, StaleArtifactsRecoverable,
                                        TrainerEngine, _StateStore,
                                        perform_stale_recovery)
from ct2trainer.native.one_shot_contract import encode_markers
from ct2trainer.native.recovery import (ProcessObservation, WAIT_OBJECT_0,
                                          WAIT_TIMEOUT, assess_recovery)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "windows" / "fixture_target" / "fixture.ct"
FIXTURE_ONESHOT = ROOT / "tests" / "windows" / "fixture_target" / "fixture_one_shot.ct"
PROCESS_NAME = "FixtureTarget.exe"
LOCK_OWNER = (990_001, 9_900_001)
FENCE_OWNER = (777_001, 7_770_001)


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


class _SplitProbe:
    """Alive exactly for the given identities, dead for everything else."""
    def __init__(self, alive_ids):
        self.alive_ids = set(alive_ids)

    def __call__(self, identity):
        if identity in self.alive_ids:
            return ProcessObservation(identity, "alive", identity.created,
                                      WAIT_TIMEOUT)
        return ProcessObservation(identity, "dead", identity.created,
                                  WAIT_OBJECT_0)


def _lock_document(owner_pid, owner_created):
    return {"schema": 2, "owner_pid": owner_pid, "owner_created": owner_created,
            "nonce": "aa" * 16}


def _fence_document(trainer_id, table_sha256, owner_pid, owner_created):
    return {"schema": 1, "engine": "ct2trainer-recovery-fence",
            "owner_pid": owner_pid, "owner_created": owner_created,
            "nonce": "ab" * 16, "trainer_id": trainer_id,
            "table_sha256": table_sha256,
            "assessment_sha256": "cd" * 32}


def _state_file(trainer_id, table_sha256):
    payload = {"schema": 1, "engine": "ct2trainer",
               "trainer_id": trainer_id, "table_sha256": table_sha256,
               "process_name": PROCESS_NAME, "desired": []}
    canonical = json.dumps(payload, sort_keys=True,
                          separators=(",", ":")).encode("utf-8")
    return json.dumps({"payload": payload,
                       "sha256": hashlib.sha256(canonical).hexdigest()}
                      ).encode("utf-8")


def _layout(root: Path, trainer_id, table_sha256, *,
            with_state: bool = True, with_lock: bool = True,
            fence_owner=None):
    """Sibling state/shared directories; the fence (when given) is the only
    extra artifact, mirroring a crashed recovery attempt."""
    state = root / "state"
    shared = root / "shared"
    state.mkdir(parents=True, exist_ok=True)
    shared.mkdir(exist_ok=True)
    if with_state:
        (state / "state.json").write_bytes(_state_file(trainer_id, table_sha256))
    if with_lock:
        (state / "state.lock").write_bytes(_json(_lock_document(*LOCK_OWNER)))
    if fence_owner is not None:
        (state / "recovery.lock").write_bytes(
            _json(_fence_document(trainer_id, table_sha256, *fence_owner)))
    return state, shared


class FenceAssessmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = compile_table(FIXTURE, PROCESS_NAME)
        cls.trainer_id = cls.plan["trainer_id"]
        cls.table_sha256 = cls.plan["table_sha256"]

    def _assess(self, state, shared, probe, claim):
        return assess_recovery(state, shared, process_probe=probe,
                               expected_trainer_id=self.trainer_id,
                               expected_table_sha256=self.table_sha256,
                               exclusive_controller_claim=claim)

    def test_lone_fence_dead_owner_is_eligible(self):
        with tempfile.TemporaryDirectory() as raw:
            state, shared = _layout(Path(raw), self.trainer_id,
                                    self.table_sha256, with_state=False,
                                    with_lock=False, fence_owner=FENCE_OWNER)
            result = self._assess(state, shared, _DeadProbe(), claim=True)
            self.assertTrue(result.eligible, result.reasons)
            self.assertEqual(set(result.candidate_paths),
                             {state / "recovery.lock"})
            fence_evidence = [p for p in result.processes
                              if p.identity.pid == FENCE_OWNER[0]]
            self.assertEqual(len(fence_evidence), 1, result.reasons)
            self.assertIn("recovery-fence owner", fence_evidence[0].roles)

    def test_lone_fence_dead_owner_eligible_without_claim_flag(self):
        # The fence document itself binds the owner identity, so the
        # "owner identity unknown" gate is satisfied even without the
        # exclusive controller claim.
        with tempfile.TemporaryDirectory() as raw:
            state, shared = _layout(Path(raw), self.trainer_id,
                                    self.table_sha256, with_state=False,
                                    with_lock=False, fence_owner=FENCE_OWNER)
            result = self._assess(state, shared, _DeadProbe(), claim=False)
            self.assertTrue(result.eligible, result.reasons)

    def test_lone_fence_live_owner_is_not_eligible(self):
        with tempfile.TemporaryDirectory() as raw:
            state, shared = _layout(Path(raw), self.trainer_id,
                                    self.table_sha256, with_state=False,
                                    with_lock=False, fence_owner=FENCE_OWNER)
            result = self._assess(state, shared, _AliveProbe(), claim=True)
            self.assertFalse(result.eligible)
            self.assertTrue(any("not proven dead" in reason
                                for reason in result.reasons),
                            result.reasons)

    def test_invalid_fence_document_is_not_eligible(self):
        with tempfile.TemporaryDirectory() as raw:
            state, shared = _layout(Path(raw), self.trainer_id,
                                    self.table_sha256, with_state=False,
                                    with_lock=False)
            document = _fence_document(self.trainer_id, self.table_sha256,
                                       *FENCE_OWNER)
            document["schema"] = 2
            (state / "recovery.lock").write_bytes(_json(document))
            result = self._assess(state, shared, _DeadProbe(), claim=True)
            self.assertFalse(result.eligible)
            self.assertTrue(any("recovery.lock" in reason
                                for reason in result.reasons),
                            result.reasons)

    def test_foreign_trainer_fence_is_not_eligible(self):
        with tempfile.TemporaryDirectory() as raw:
            state, shared = _layout(Path(raw), self.trainer_id,
                                    self.table_sha256, with_state=False,
                                    with_lock=False)
            (state / "recovery.lock").write_bytes(_json(
                _fence_document("f" * 16, self.table_sha256, *FENCE_OWNER)))
            result = self._assess(state, shared, _DeadProbe(), claim=True)
            self.assertFalse(result.eligible)
            self.assertTrue(any("recovery.lock" in reason
                                for reason in result.reasons),
                            result.reasons)

    def test_fence_with_dead_state_lock_is_eligible(self):
        with tempfile.TemporaryDirectory() as raw:
            state, shared = _layout(Path(raw), self.trainer_id,
                                    self.table_sha256, fence_owner=FENCE_OWNER)
            result = self._assess(state, shared, _DeadProbe(), claim=True)
            self.assertTrue(result.eligible, result.reasons)
            self.assertEqual(set(result.candidate_paths),
                             {state / "state.lock", state / "recovery.lock"})

    def test_fence_dead_but_live_lock_owner_is_not_eligible(self):
        with tempfile.TemporaryDirectory() as raw:
            state, shared = _layout(Path(raw), self.trainer_id,
                                    self.table_sha256, fence_owner=FENCE_OWNER)
            from ct2trainer.native.recovery import ProcessIdentity
            probe = _SplitProbe({ProcessIdentity(*LOCK_OWNER)})
            result = self._assess(state, shared, probe, claim=True)
            self.assertFalse(result.eligible)

    def test_quarantined_state_file_is_recognized_and_candidate(self):
        with tempfile.TemporaryDirectory() as raw:
            state, shared = _layout(Path(raw), self.trainer_id,
                                    self.table_sha256)
            quarantined = state / "state.json.corrupt-20261004T120000Z"
            quarantined.write_bytes(b"unrecoverable bytes")
            result = self._assess(state, shared, _DeadProbe(), claim=True)
            self.assertTrue(result.eligible, result.reasons)
            self.assertNotIn(
                "Unknown recovery artifact", "; ".join(result.reasons))
            self.assertIn(quarantined, result.candidate_paths)

    def test_oneshot_tmp_is_candidate_and_oneshot_is_inert(self):
        with tempfile.TemporaryDirectory() as raw:
            state, shared = _layout(Path(raw), self.trainer_id,
                                    self.table_sha256)
            (state / "oneshot.json").write_bytes(b"not json at all")
            (state / "oneshot.json.tmp").write_bytes(b"partial write")
            result = self._assess(state, shared, _DeadProbe(), claim=True)
            self.assertTrue(result.eligible, result.reasons)
            self.assertIn(state / "oneshot.json.tmp", result.candidate_paths)
            self.assertNotIn(state / "oneshot.json", result.candidate_paths)


class EngineSelfHealTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.plan = compile_table(FIXTURE, PROCESS_NAME)
        self.trainer_id = self.plan["trainer_id"]
        self.table_sha256 = self.plan["table_sha256"]
        self.factory = lambda _name: None

    def test_leftover_fence_yields_recoverable_handle(self):
        state, shared = _layout(self.root, self.trainer_id,
                                self.table_sha256, fence_owner=FENCE_OWNER)
        fence_before = (state / "recovery.lock").read_bytes()
        lock_before = (state / "state.lock").read_bytes()
        with self.assertRaises(StaleArtifactsRecoverable) as caught:
            TrainerEngine(self.plan, state, self.factory, shared,
                          process_probe=_DeadProbe())
        handle = caught.exception
        self.assertTrue(handle.assessment.eligible,
                        handle.assessment.reasons)
        self.assertIn(state / "recovery.lock",
                      handle.assessment.candidate_paths)
        # The probe is read-only: existing artifacts are byte-identical and
        # no new state claim was made.
        self.assertEqual((state / "recovery.lock").read_bytes(), fence_before)
        self.assertEqual((state / "state.lock").read_bytes(), lock_before)
        self.assertFalse((state / "state.json.tmp").exists())

    def test_leftover_fence_live_owner_keeps_conservative_refusal(self):
        state, shared = _layout(self.root, self.trainer_id,
                                self.table_sha256, fence_owner=FENCE_OWNER)
        with self.assertRaisesRegex(StateError,
                                    "recovery transaction owns this state"):
            TrainerEngine(self.plan, state, self.factory, shared,
                          process_probe=_AliveProbe())

    def test_foreign_fence_keeps_conservative_refusal(self):
        state, shared = _layout(self.root, self.trainer_id,
                                self.table_sha256, with_lock=False,
                                with_state=False)
        (state / "recovery.lock").write_bytes(_json(
            _fence_document("f" * 16, self.table_sha256, *FENCE_OWNER)))
        with self.assertRaisesRegex(StateError,
                                    "recovery transaction owns this state"):
            TrainerEngine(self.plan, state, self.factory, shared,
                          process_probe=_DeadProbe())

    def test_corrupt_state_json_is_quarantined_and_engine_starts(self):
        state, shared = _layout(self.root, self.trainer_id,
                                self.table_sha256, with_lock=False)
        corrupt = b'{"payload": {"desired": [1],'  # truncated JSON
        (state / "state.json").write_bytes(corrupt)
        engine = TrainerEngine(self.plan, state, self.factory, shared)
        self.addCleanup(engine.close)
        quarantined = sorted(state.glob("state.json.corrupt-*"))
        self.assertEqual(len(quarantined), 1,
                         "the corrupt state file must be quarantined")
        self.assertEqual(quarantined[0].read_bytes(), corrupt)
        self.assertFalse((state / "state.json").exists())
        self.assertEqual(engine.desired, set())
        # A subsequent save works against the fresh store.
        engine.store.save(set())
        self.assertTrue((state / "state.json").exists())

    def test_corrupt_state_json_quarantine_failure_keeps_refusal(self):
        state, shared = _layout(self.root, self.trainer_id,
                                self.table_sha256, with_lock=False)
        (state / "state.json").write_bytes(b"corrupt")
        with mock.patch.object(_StateStore, "_quarantine_corrupt",
                               return_value=None):
            with self.assertRaisesRegex(StateError, "Invalid native state"):
                TrainerEngine(self.plan, state, self.factory, shared)
        self.assertTrue((state / "state.json").exists(),
                        "a failed quarantine must preserve the original")
        self.assertFalse((state / "state.lock").exists(),
                         "the failed start must not keep the state lock")

    def test_invalid_oneshot_markers_are_quarantined_and_engine_starts(self):
        plan = compile_table(FIXTURE_ONESHOT, PROCESS_NAME)
        state, shared = _layout(self.root, plan["trainer_id"],
                                plan["table_sha256"], with_lock=False)
        (state / "oneshot.json").write_bytes(b"garbage marker bytes")
        engine = TrainerEngine(plan, state, self.factory, shared)
        self.addCleanup(engine.close)
        quarantined = sorted(state.glob("oneshot.json.corrupt-*"))
        self.assertEqual(len(quarantined), 1,
                         "the invalid marker file must be quarantined")
        self.assertEqual(quarantined[0].read_bytes(), b"garbage marker bytes")
        self.assertFalse((state / "oneshot.json").exists())
        self.assertIsNotNone(engine.one_shot)
        self.assertEqual(set(engine.one_shot.saved_wish_ids()), set())

    def test_mismatched_oneshot_markers_are_quarantined_and_engine_starts(self):
        plan = compile_table(FIXTURE_ONESHOT, PROCESS_NAME)
        trainer_id, table_sha256 = plan["trainer_id"], plan["table_sha256"]
        state, shared = _layout(self.root, trainer_id, table_sha256,
                                with_lock=False)
        # A valid marker blob carrying a saved wish for record 0, while the
        # saved state holds no wish at all: the stale marker is quarantined
        # and no auto-on wish is restored.
        blob = encode_markers([(0, "EXECUTED", 1, 1)], table_sha256,
                              PROCESS_NAME)
        (state / "oneshot.json").write_bytes(blob)
        engine = TrainerEngine(plan, state, self.factory, shared)
        self.addCleanup(engine.close)
        quarantined = sorted(state.glob("oneshot.json.corrupt-*"))
        self.assertEqual(len(quarantined), 1)
        self.assertEqual(quarantined[0].read_bytes(), blob)
        self.assertFalse((state / "oneshot.json").exists())
        self.assertEqual(engine.desired, set())
        self.assertNotIn(0, engine.one_shot.saved_wish_ids())

    def test_failed_startup_after_claim_releases_the_state_lock(self):
        plan = compile_table(FIXTURE_ONESHOT, PROCESS_NAME)
        state, shared = _layout(self.root, plan["trainer_id"],
                                plan["table_sha256"], with_lock=False)
        (state / "oneshot.json").write_bytes(b"garbage marker bytes")
        # Simulate an impossible rename so the marker quarantine fails and
        # startup refuses after the state claim was taken.
        with mock.patch.object(_StateStore, "quarantine_one_shot_markers",
                               return_value=None):
            with self.assertRaisesRegex(StateError, "One-shot markers"):
                TrainerEngine(plan, state, self.factory, shared)
        self.assertFalse((state / "state.lock").exists(),
                         "a failed start must not keep the state lock")
        self.assertTrue((state / "oneshot.json").exists(),
                        "the marker file is preserved when quarantine failed")
        # With the trigger removed the next start is clean.
        (state / "oneshot.json").unlink()
        engine = TrainerEngine(plan, state, self.factory, shared)
        self.addCleanup(engine.close)
        self.assertEqual(engine.desired, set())

    def test_atexit_handler_releases_an_open_store(self):
        state, shared = _layout(self.root, self.trainer_id,
                                self.table_sha256, with_lock=False)
        engine = TrainerEngine(self.plan, state, self.factory, shared)
        self.assertTrue((state / "state.lock").exists())
        engine._atexit_close()
        self.assertFalse((state / "state.lock").exists())
        self.assertTrue(engine.closed)
        # Idempotent: a second call must not raise.
        engine._atexit_close()


@unittest.skipUnless(sys.platform == "win32",
                     "Real Windows held-file disposition profile")
class WindowsFenceTakeoverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.plan = compile_table(FIXTURE, PROCESS_NAME)
        self.trainer_id = self.plan["trainer_id"]
        self.table_sha256 = self.plan["table_sha256"]
        self.factory = lambda _name: None

    def test_perform_stale_recovery_takes_over_a_leftover_fence(self):
        state, shared = _layout(self.root, self.trainer_id,
                                self.table_sha256, fence_owner=FENCE_OWNER)
        state_bytes = (state / "state.json").read_bytes()
        fence_bytes = (state / "recovery.lock").read_bytes()
        with self.assertRaises(StaleArtifactsRecoverable) as caught:
            TrainerEngine(self.plan, state, self.factory, shared,
                          process_probe=_DeadProbe())
        handle = caught.exception

        ok, detail = perform_stale_recovery(handle, process_probe=_DeadProbe())
        self.assertTrue(ok, detail)
        self.assertFalse((state / "recovery.lock").exists(), detail)
        self.assertFalse((state / "state.lock").exists(), detail)
        self.assertEqual((state / "state.json").read_bytes(), state_bytes,
                         "the saved state must be preserved byte-for-byte")

        archives = sorted((self.root / "archives").glob("native-recovery-*.zip"))
        self.assertEqual(len(archives), 1, detail)
        with zipfile.ZipFile(archives[0]) as bundle:
            names = bundle.namelist()
            self.assertTrue(any(name.endswith("recovery.lock") for name in names),
                            names)
            member = [name for name in names
                      if name.endswith("recovery.lock")][0]
            self.assertEqual(bundle.read(member), fence_bytes,
                             "the taken-over fence must be archived byte-for-byte")
        journals = sorted((self.root / "archives").glob("native-recovery-*.jsonl"))
        self.assertEqual(len(journals), 1, detail)
        text = journals[0].read_bytes().decode("utf-8")
        self.assertIn("fence-taken-over", text)
        self.assertNotIn("fence-claim-intent", text,
                         "a taken-over fence is never claimed as new")

        # A clean start afterwards.
        engine = TrainerEngine(self.plan, state, self.factory, shared)
        self.addCleanup(engine.close)
        self.assertEqual(engine.desired, set())

    def test_perform_stale_recovery_refuses_a_foreign_fence(self):
        state, shared = _layout(self.root, self.trainer_id,
                                self.table_sha256, with_lock=False,
                                with_state=False)
        (state / "recovery.lock").write_bytes(_json(
            _fence_document("f" * 16, self.table_sha256, *FENCE_OWNER)))
        # The engine keeps the conservative refusal; there is no handle.
        with self.assertRaisesRegex(StateError,
                                    "recovery transaction owns this state"):
            TrainerEngine(self.plan, state, self.factory, shared,
                          process_probe=_DeadProbe())
        self.assertTrue((state / "recovery.lock").exists(),
                        "an unverified fence must stay untouched")


if __name__ == "__main__":
    unittest.main()
