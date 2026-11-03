"""Live-target takeover: the owner is proven dead, the recorded game still runs.

Field case 2026-11-03 (Indiana Jones and the Great Circle, 0.22 log): the
hotkey-bridge AV during ``engine.close()`` left the state lock behind while
the game kept running, so the strict all-dead recovery proof could never
pass and the only option was a manual state-folder delete. The user-confirmed
takeover archives the stale state and attaches to the running target: the
owner must stay proven dead, only target-side identities may remain alive.
"""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import (
    LiveStateConflict,
    StateError,
    StaleStateRecoverable,
    TrainerEngine,
    perform_stale_recovery,
)
from ct2trainer.native.recovery import (
    ProcessObservation,
    assess_recovery,
    is_target_role,
    WAIT_OBJECT_0,
)
from ct2trainer.native.recovery_operation import recover_assessment


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "windows" / "fixture_target" / "fixture.ct"

TRAINER, TABLE = "a" * 16, "b" * 64
OWNER_PID, OWNER_CREATED = 111, 1111
TARGET_PID, TARGET_CREATED = 222, 2222


def _json(document):
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode()


def _observation(identity, status):
    if status == "dead":
        return ProcessObservation(identity, "dead", identity.created, WAIT_OBJECT_0)
    if status == "alive":
        return ProcessObservation(identity, "alive", identity.created, WAIT_OBJECT_0)
    if status == "absent":
        return ProcessObservation(identity, "absent", None, None)
    return ProcessObservation(identity, "unknown", None, None)


def _split_probe(owner_status, target_status):
    """Probe by exact PID: owner and target carry separate statuses."""
    def probe(identity):
        if identity.pid == OWNER_PID:
            return _observation(identity, owner_status)
        if identity.pid == TARGET_PID:
            return _observation(identity, target_status)
        return _observation(identity, "dead")
    return probe


def _fixture(root):
    """A crashed-session state: lock + session + shared claim + journals."""
    state, shared, archive = root / "state", root / "shared", root / "evidence"
    state.mkdir()
    shared.mkdir()
    archive.mkdir()
    (state / "hooks").mkdir()
    lock = {"schema": 2, "owner_pid": OWNER_PID, "owner_created": OWNER_CREATED, "nonce": "c" * 32}
    session = {"schema": 1, "owner": lock, "trainer_id": TRAINER,
               "target_pid": TARGET_PID, "target_created": TARGET_CREATED}
    payload = {"schema": 1, "engine": "ct2trainer", "trainer_id": TRAINER,
               "table_sha256": TABLE, "process_name": "fixture.exe", "desired": [7]}
    state_document = {"payload": payload, "sha256": hashlib.sha256(_json(payload)).hexdigest()}
    hook = {"schema": 1, "engine": "ct2trainer-hooks", "owner": TRAINER + ":fixture",
            "target_pid": TARGET_PID, "target_created": TARGET_CREATED, "state": "enabled",
            "uncertain": False, "allocations": {}, "blocks": [], "entries": [], "exports": {},
            "retirement_policy": "retain-published-allocations-until-target-exit"}
    lua = {"schema": "ct2trainer-lua-activation/v1", "engine": "ct2trainer-lua",
           "trainer_id": TRAINER, "table_sha256": TABLE, "state": "open", "owner": 7,
           "target": [TARGET_PID, TARGET_CREATED], "data": [], "symbols": {},
           "assemblies": {}, "pending": None}
    claim = shared / f"{TARGET_PID}-{TARGET_CREATED}.json"
    for path, document in ((state / "state.lock", lock), (state / "state.json", state_document),
                           (state / "session.json", session), (claim, session),
                           (state / "hooks" / "hook.json", hook), (state / "hooks" / "lua.json", lua)):
        path.write_bytes(_json(document))
    return state, shared, archive


class RoleClassificationTests(unittest.TestCase):
    def test_target_roles_are_recognized(self):
        for role in ("session target", "shared-lock target", "journal target: hook.json"):
            self.assertTrue(is_target_role(role), role)

    def test_trainer_side_and_unknown_roles_are_not_target_roles(self):
        for role in ("state owner", "session owner", "shared-lock owner",
                     "recovery-fence owner", "unknown role"):
            self.assertFalse(is_target_role(role), role)


class AssessmentLiveTargetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="native-live-target-assess-")
        self.addCleanup(self.temp.cleanup)
        self.state, self.shared, self.archive = _fixture(Path(self.temp.name))

    def assess(self, owner, target):
        return assess_recovery(self.state, self.shared,
                               process_probe=_split_probe(owner, target),
                               expected_trainer_id=TRAINER, expected_table_sha256=TABLE)

    def test_dead_owner_live_target_is_live_target_eligible(self):
        result = self.assess("dead", "alive")
        self.assertFalse(result.eligible, result.reasons)
        self.assertTrue(result.live_target_eligible, result.reasons)
        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reasons, (
            f"Exact process {TARGET_PID}/{TARGET_CREATED} is not proven dead "
            "in both observations (alive, alive)",))

    def test_dead_owner_dead_target_stays_plain_eligible(self):
        result = self.assess("dead", "dead")
        self.assertTrue(result.eligible, result.reasons)
        self.assertFalse(result.live_target_eligible)

    def test_live_owner_is_never_live_target_eligible(self):
        result = self.assess("alive", "alive")
        self.assertFalse(result.eligible, result.reasons)
        self.assertFalse(result.live_target_eligible, result.reasons)

    def test_unprovable_owner_keeps_strict_refusal(self):
        result = self.assess("unknown", "alive")
        self.assertFalse(result.eligible, result.reasons)
        self.assertFalse(result.live_target_eligible, result.reasons)

    def test_unprovable_target_is_still_live_target_eligible(self):
        # A transient target probe failure is no worse for the takeover than
        # an alive target: the relaxation is safe in either world (the new
        # session either attaches to the running game or waits for it).
        result = self.assess("dead", "unknown")
        self.assertFalse(result.eligible, result.reasons)
        self.assertTrue(result.live_target_eligible, result.reasons)

    def test_foreign_artifact_blocks_the_qualification(self):
        (self.state / "foreign.bin").write_bytes(b"foreign")
        result = self.assess("dead", "alive")
        self.assertFalse(result.eligible, result.reasons)
        self.assertFalse(result.live_target_eligible, result.reasons)


class EngineClassificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="native-live-target-engine-")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.state = root / "state"
        self.shared = root / "shared"
        self.state.mkdir()
        self.shared.mkdir()
        self.plan = compile_table(FIXTURE, "FixtureTarget.exe")

    def _write_state(self):
        payload = {"schema": 1, "engine": "ct2trainer",
                   "trainer_id": self.plan["trainer_id"],
                   "table_sha256": self.plan["table_sha256"],
                   "process_name": self.plan["process_name"], "desired": []}
        (self.state / "state.json").write_bytes(
            _json({"payload": payload, "sha256": hashlib.sha256(_json(payload)).hexdigest()}))
        lock = {"schema": 2, "owner_pid": OWNER_PID, "owner_created": OWNER_CREATED, "nonce": "c" * 32}
        (self.state / "state.lock").write_bytes(_json(lock))
        session = {"schema": 1, "owner": lock, "trainer_id": self.plan["trainer_id"],
                   "target_pid": TARGET_PID, "target_created": TARGET_CREATED}
        (self.state / "session.json").write_bytes(_json(session))
        # The session must carry its byte-identical shared target claim.
        (self.shared / f"{TARGET_PID}-{TARGET_CREATED}.json").write_bytes(_json(session))

    def _engine(self, probe):
        return TrainerEngine(self.plan, self.state, lambda _name: None, self.shared,
                             process_probe=probe)

    def test_dead_owner_live_target_yields_live_target_handle(self):
        self._write_state()
        with self.assertRaises(StaleStateRecoverable) as ctx:
            self._engine(_split_probe("dead", "alive"))
        self.assertTrue(ctx.exception.live_target_takeover)
        self.assertFalse(ctx.exception.assessment.eligible)
        self.assertTrue(ctx.exception.assessment.live_target_eligible,
                        ctx.exception.assessment.reasons)
        self.assertIn("still running", str(ctx.exception))

    def test_dead_owner_dead_target_keeps_plain_handle(self):
        self._write_state()
        with self.assertRaises(StaleStateRecoverable) as ctx:
            self._engine(_split_probe("dead", "dead"))
        self.assertFalse(ctx.exception.live_target_takeover)
        self.assertTrue(ctx.exception.assessment.eligible,
                        ctx.exception.assessment.reasons)

    def test_live_owner_still_yields_conflict(self):
        self._write_state()
        with self.assertRaises(LiveStateConflict) as ctx:
            self._engine(_split_probe("alive", "alive"))
        self.assertEqual(ctx.exception.owner_pid, OWNER_PID)
        self.assertNotIsInstance(ctx.exception, StaleStateRecoverable)

    def test_unprovable_owner_keeps_conservative_refusal(self):
        self._write_state()
        with self.assertRaises(StateError) as ctx:
            self._engine(_split_probe("unknown", "alive"))
        self.assertNotIsInstance(ctx.exception, StaleStateRecoverable)
        self.assertIn("Delete that folder to start fresh", str(ctx.exception))


@unittest.skipUnless(sys.platform == "win32", "Real Windows held-file disposition profile")
class LiveTargetTransactionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="native-live-target-op-")
        self.addCleanup(self.temporary.cleanup)
        self.state, self.shared, self.archive = _fixture(Path(self.temporary.name))

    def originals(self):
        return {path: path.read_bytes() for directory in (self.state, self.shared)
                for path in directory.rglob("*") if path.is_file()}

    def assess(self, probe):
        return assess_recovery(self.state, self.shared, process_probe=probe,
                               expected_trainer_id=TRAINER, expected_table_sha256=TABLE)

    def test_refused_without_the_live_target_flag(self):
        probe = _split_probe("dead", "alive")
        assessment = self.assess(probe)
        self.assertTrue(assessment.live_target_eligible, assessment.reasons)
        originals = self.originals()
        report = recover_assessment(assessment, self.archive,
                                    expected_trainer_id=TRAINER, expected_table_sha256=TABLE,
                                    process_probe=probe)
        self.assertFalse(report.completed)
        self.assertEqual(report.status, "refused")
        self.assertIn("eligible read-only death proof", "; ".join(report.reasons))
        self.assertEqual(originals, self.originals())
        self.assertFalse(report.fence_path.exists())
        self.assertEqual(list(self.archive.iterdir()), [])

    def test_live_target_takeover_archives_and_releases(self):
        probe = _split_probe("dead", "alive")
        originals = self.originals()
        report = recover_assessment(self.assess(probe), self.archive,
                                    expected_trainer_id=TRAINER, expected_table_sha256=TABLE,
                                    process_probe=probe,
                                    allow_live_target=True)
        self.assertTrue(report.completed, report.reasons)
        self.assertFalse(report.remote_writes)
        self.assertEqual(set(report.released),
                         {path for path in originals if path.name != "state.json"})
        self.assertFalse(report.fence_path.exists())
        self.assertEqual((self.state / "state.json").read_bytes(),
                         originals[self.state / "state.json"])

    def test_target_exiting_mid_operation_completes(self):
        # The target may die between the initial assessment and the
        # transaction: the fresh reassessment is then fully eligible and the
        # operation completes as the ordinary recovery.
        calls = {"n": 0}
        def probe(identity):
            calls["n"] += 1
            if identity.pid == TARGET_PID and calls["n"] > 4:
                return ProcessObservation(identity, "absent", None, None)
            return _split_probe("dead", "alive")(identity)
        report = recover_assessment(self.assess(probe), self.archive,
                                    expected_trainer_id=TRAINER, expected_table_sha256=TABLE,
                                    process_probe=probe,
                                    allow_live_target=True)
        self.assertTrue(report.completed, report.reasons)

    def test_final_probe_refuses_when_owner_comes_back(self):
        # The owner may exit during the assessment and come back alive only
        # at the final probe pass: the trainer-side identity must stay proven
        # dead even for the live-target takeover, and the state stays held.
        calls = {"n": 0}
        def probe(identity):
            calls["n"] += 1
            if identity.pid == OWNER_PID and calls["n"] >= 9:
                return ProcessObservation(identity, "alive", identity.created, WAIT_OBJECT_0)
            return _split_probe("dead", "alive")(identity)
        originals = self.originals()
        report = recover_assessment(self.assess(probe), self.archive,
                                    expected_trainer_id=TRAINER, expected_table_sha256=TABLE,
                                    process_probe=probe,
                                    allow_live_target=True)
        self.assertFalse(report.completed)
        self.assertIn("not proven dead before file release", "; ".join(report.reasons))
        # The original state stays intact; only the transaction's own fence
        # (and archive evidence) remain behind as durable proof of the
        # refused release.
        for path, raw in originals.items():
            self.assertEqual(path.read_bytes(), raw, str(path))
        self.assertTrue(report.fence_path.exists())

    def test_perform_stale_recovery_passes_the_live_target_flag(self):
        probe = _split_probe("dead", "alive")
        handle = StaleStateRecoverable(self.assess(probe), self.state, self.shared,
                                       self.archive, TRAINER, TABLE,
                                       live_target_takeover=True)
        ok, detail = perform_stale_recovery(handle, process_probe=probe)
        self.assertTrue(ok, detail)
        self.assertIn("Archived stale state to", detail)

    def test_perform_stale_recovery_refuses_without_the_flag(self):
        probe = _split_probe("dead", "alive")
        handle = StaleStateRecoverable(self.assess(probe), self.state, self.shared,
                                       self.archive, TRAINER, TABLE)
        ok, detail = perform_stale_recovery(handle, process_probe=probe)
        self.assertFalse(ok)
        self.assertIn("eligible read-only death proof", detail)


if __name__ == "__main__":
    unittest.main()
