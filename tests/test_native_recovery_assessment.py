"""GUI recovery assessment: read-only classification mapped 1:1 to the CLI ops."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from ct2trainer.native import recovery
from ct2trainer.native.recovery import ProcessIdentity, ProcessObservation, WAIT_OBJECT_0
from ct2trainer.native.recovery_assessment import (
    assess_for_gui,
    to_json_document,
)


TRAINER_ID = "a" * 16
TABLE_SHA = "b" * 64
OWNER_PID, OWNER_CREATED = 333, 3333
TARGET_PID, TARGET_CREATED = 444, 4444


def _canonical(document):
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode()


def _probe(status="dead", by_pid=None):
    """Deterministic probe: per-PID override, default status otherwise."""

    def probe(identity):
        chosen = by_pid.get(identity.pid, status) if by_pid is not None else status
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


class _Fixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="native-recovery-gui-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / "state"
        self.shared = self.root / "_process_sessions"
        self.state.mkdir()
        self.shared.mkdir()
        (self.state / "hooks").mkdir()
        self.write_evidence()

    def write_evidence(self, *, lock_bytes=None, extra_files=()):
        lock = {"schema": 2, "owner_pid": OWNER_PID, "owner_created": OWNER_CREATED,
                "nonce": "c" * 32}
        session = {"schema": 1, "owner": lock, "trainer_id": TRAINER_ID,
                   "target_pid": TARGET_PID, "target_created": TARGET_CREATED}
        payload = {"schema": 1, "engine": "ct2trainer", "trainer_id": TRAINER_ID,
                   "table_sha256": TABLE_SHA, "process_name": "Fixture.exe", "desired": [1]}
        state = {"payload": payload, "sha256": hashlib.sha256(_canonical(payload)).hexdigest()}
        self.claim = self.shared / f"{TARGET_PID}-{TARGET_CREATED}.json"
        documents = {
            self.state / "state.json": state,
            self.state / "session.json": session,
            self.claim: session,
        }
        if lock_bytes is None:
            documents[self.state / "state.lock"] = lock
        for path, document in documents.items():
            path.write_bytes(_canonical(document))
        if lock_bytes is not None:
            (self.state / "state.lock").write_bytes(lock_bytes)
        for name, raw in extra_files:
            (self.state / name).write_bytes(raw)

    def snapshot(self):
        return {str(path): path.read_bytes()
                for directory in (self.state, self.shared)
                for path in directory.rglob("*") if path.is_file()}

    def assess(self, probe=None, **extra):
        return assess_for_gui(self.state, self.shared,
                              process_probe=probe or _probe(),
                              expected_trainer_id=TRAINER_ID,
                              expected_table_sha256=TABLE_SHA, **extra)


class GuiAssessmentEligibilityTests(_Fixture, unittest.TestCase):
    def test_dead_owner_and_target_are_eligible_with_stale_classifications(self):
        before = self.snapshot()
        result = self.assess()
        self.assertEqual(result.status, "eligible-read-only")
        self.assertTrue(result.eligible)
        self.assertTrue(result.recovery_allowed)
        self.assertEqual(result.operation["recover_allowed"], True)
        self.assertEqual(result.operation["recover_operation"],
                         "recovery_operation.recover_assessment")
        by_name = {Path(item.path).name: item for item in result.artifacts}
        self.assertEqual(by_name["state.lock"].classification, "stale")
        self.assertTrue(by_name["state.lock"].recoverable)
        self.assertEqual(by_name["state.lock"].owner, (OWNER_PID, OWNER_CREATED))
        self.assertEqual(by_name["state.lock"].process_status, "dead")
        self.assertEqual(by_name["session.json"].classification, "stale")
        self.assertEqual(by_name[self.claim.name].classification, "stale")
        self.assertEqual(by_name["state.json"].classification, "saved-state")
        self.assertFalse(by_name["state.json"].recoverable)
        self.assertNotIn(str(self.state / "state.json"), result.candidate_paths)
        self.assertEqual(before, self.snapshot(), "assessment must not change any byte")
        self.assertFalse((self.state / "recovery.lock").exists())

    def test_absent_owner_is_eligible(self):
        result = self.assess(_probe("absent"))
        self.assertTrue(result.eligible, result.reasons)
        by_name = {Path(item.path).name: item for item in result.artifacts}
        self.assertEqual(by_name["state.lock"].classification, "stale")
        self.assertEqual(by_name["state.lock"].process_status, "absent")

    def test_reused_owner_is_eligible(self):
        result = self.assess(_probe("reused"))
        self.assertTrue(result.eligible, result.reasons)
        by_name = {Path(item.path).name: item for item in result.artifacts}
        self.assertEqual(by_name["state.lock"].classification, "stale")

    def test_live_owner_blocks_with_live_classification(self):
        before = self.snapshot()
        result = self.assess(_probe("alive"))
        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.recovery_allowed)
        self.assertTrue(result.operation["blocked_reasons"])
        by_name = {Path(item.path).name: item for item in result.artifacts}
        self.assertEqual(by_name["state.lock"].classification, "live")
        self.assertFalse(by_name["state.lock"].recoverable)
        self.assertEqual(before, self.snapshot())

    def test_live_target_blocks_even_with_dead_owner(self):
        result = self.assess(_probe(by_pid={OWNER_PID: "dead", TARGET_PID: "alive"}))
        self.assertFalse(result.eligible)
        by_name = {Path(item.path).name: item for item in result.artifacts}
        self.assertEqual(by_name["state.lock"].classification, "stale")
        self.assertEqual(by_name["session.json"].classification, "live")
        self.assertEqual(by_name[self.claim.name].classification, "live")

    def test_unproven_owner_is_hard_blocked_as_unsafe(self):
        result = self.assess(_probe("unknown"))
        self.assertFalse(result.eligible)
        by_name = {Path(item.path).name: item for item in result.artifacts}
        self.assertEqual(by_name["state.lock"].classification, "unsafe")
        self.assertFalse(by_name["state.lock"].recoverable)


class GuiAssessmentArtifactTests(_Fixture, unittest.TestCase):
    def test_legacy_lock_without_creation_time_is_blocked(self):
        self.write_evidence(lock_bytes=_canonical(
            {"schema": 1, "owner_pid": OWNER_PID, "nonce": "c" * 32}))
        result = self.assess()
        self.assertFalse(result.eligible)
        by_name = {Path(item.path).name: item for item in result.artifacts}
        self.assertEqual(by_name["state.lock"].classification, "legacy")
        self.assertIn(OWNER_PID, by_name["state.lock"].owner)
        self.assertIsNone(by_name["state.lock"].owner[1])

    def test_corrupt_lock_bytes_are_blocked(self):
        self.write_evidence(lock_bytes=b"\x01\x02not-json")
        result = self.assess()
        self.assertFalse(result.eligible)
        by_name = {Path(item.path).name: item for item in result.artifacts}
        self.assertEqual(by_name["state.lock"].classification, "corrupted")

    def test_state_json_with_bad_checksum_is_corrupted_and_never_a_candidate(self):
        payload = {"schema": 1, "engine": "ct2trainer", "trainer_id": TRAINER_ID,
                   "table_sha256": TABLE_SHA, "process_name": "Fixture.exe", "desired": [1]}
        bad = {"payload": payload, "sha256": "0" * 64}
        (self.state / "state.json").write_bytes(_canonical(bad))
        result = self.assess()
        self.assertFalse(result.eligible)
        by_name = {Path(item.path).name: item for item in result.artifacts}
        self.assertEqual(by_name["state.json"].classification, "corrupted")
        self.assertNotIn(str(self.state / "state.json"), result.candidate_paths)

    def test_unknown_file_is_visible_but_blocks_recovery(self):
        self.write_evidence(extra_files=[("foreign.txt", b"x")])
        result = self.assess()
        self.assertFalse(result.eligible)
        self.assertTrue(any("Unknown recovery artifact" in reason for reason in result.reasons))
        by_name = {Path(item.path).name: item for item in result.artifacts}
        self.assertEqual(by_name["foreign.txt"].classification, "unknown-artifact")

    def test_interrupted_state_snapshot_is_corrupted_evidence(self):
        (self.state / "state.json.tmp").write_bytes(b'{"partial":')
        result = self.assess()
        self.assertFalse(result.eligible)
        by_name = {Path(item.path).name: item for item in result.artifacts}
        self.assertEqual(by_name["state.json.tmp"].classification, "corrupted")

    def test_journals_are_classified_and_bound_to_their_target(self):
        lua = {"schema": "ct2trainer-lua-activation/v1", "engine": "ct2trainer-lua",
               "trainer_id": TRAINER_ID, "table_sha256": TABLE_SHA,
               "state": "open", "target": [TARGET_PID, TARGET_CREATED], "owner": 1,
               "data": [], "symbols": {}, "assemblies": {}, "pending": None}
        hook = {"schema": 1, "engine": "ct2trainer-hooks", "owner": TRAINER_ID + ":fixture",
                "target_pid": TARGET_PID, "target_created": TARGET_CREATED, "state": "enabled",
                "uncertain": False, "allocations": {}, "blocks": [], "entries": [], "exports": {},
                "retirement_policy": "retain-published-allocations-until-target-exit"}
        (self.state / "hooks" / "lua.json").write_bytes(_canonical(lua))
        (self.state / "hooks" / "hook.json").write_bytes(_canonical(hook))
        result = self.assess()
        self.assertTrue(result.eligible, result.reasons)
        by_name = {Path(item.path).name: item for item in result.artifacts}
        for name in ("lua.json", "hook.json"):
            self.assertEqual(by_name[name].classification, "journal", name)
            self.assertEqual(by_name[name].target, (TARGET_PID, TARGET_CREATED))
            self.assertFalse(by_name[name].recoverable, "journals are released only by the CLI op")
        # a live target keeps the journals blocked
        live = self.assess(_probe(by_pid={OWNER_PID: "dead", TARGET_PID: "alive"}))
        live_by_name = {Path(item.path).name: item for item in live.artifacts}
        self.assertEqual(live_by_name["lua.json"].classification, "live")
        self.assertEqual(live_by_name["hook.json"].classification, "live")

    def test_clean_directory_reports_clean_and_no_operation(self):
        for path in list(self.state.rglob("*")) + list(self.shared.iterdir()):
            if path.is_file() and path.name != "state.json":
                path.unlink()
        result = self.assess()
        self.assertEqual(result.status, "clean")
        self.assertFalse(result.recovery_allowed)
        self.assertEqual(len(result.artifacts), 1)
        self.assertEqual(result.artifacts[0].classification, "saved-state")
        self.assertEqual(result.artifacts[0].recoverable, False)
        self.assertEqual(result.candidate_paths, ())
        self.assertEqual(result.processes, ())


class GuiAssessmentJsonTests(_Fixture, unittest.TestCase):
    def test_json_document_is_serializable_and_deterministic(self):
        result = self.assess()
        document = to_json_document(result)
        raw = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
        self.assertEqual(document["schema"], 1)
        self.assertEqual(document["engine"], "ct2trainer-recovery-assessment")
        self.assertEqual(document["status"], "eligible-read-only")
        self.assertEqual(len(document["inventory_sha256"]), 64)
        self.assertEqual(len(document["artifacts"]), 4)
        self.assertTrue(all(item["process_status"] in {"dead", None} for item in document["artifacts"]))
        # a fresh assessment of the same untouched evidence is byte-identical
        again = to_json_document(self.assess())
        self.assertEqual(
            json.dumps(again, sort_keys=True, separators=(",", ":")).encode(), raw)

    def test_json_document_uses_strict_process_evidence(self):
        result = self.assess()
        document = to_json_document(result)
        processes = {item["pid"]: item for item in document["processes"]}
        self.assertEqual(processes[OWNER_PID]["proven_dead"], True)
        self.assertEqual(processes[OWNER_PID]["observations"][0]["status"], "dead")
        self.assertEqual(processes[TARGET_PID]["proven_dead"], True)

    def test_blocked_reasons_are_forwarded_into_the_operation_mapping(self):
        result = self.assess(_probe("alive"))
        document = to_json_document(result)
        self.assertFalse(document["operation"]["recover_allowed"])
        self.assertTrue(document["operation"]["blocked_reasons"])
        self.assertEqual(document["operation"]["assess_command"], "assess-recovery")
        self.assertEqual(document["operation"]["recover_command"], "recover")


if __name__ == "__main__":
    unittest.main()
