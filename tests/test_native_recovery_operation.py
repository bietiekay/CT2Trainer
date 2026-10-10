"""Verified held-file release, evidence retention, and actual process death."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from ct2trainer.native import recovery, recovery_operation as operation
from ct2trainer.native.recovery import ProcessIdentity, ProcessObservation, WindowsProcessProbe, assess_recovery, WAIT_OBJECT_0
from ct2trainer.native.recovery_operation import recover_assessment


TRAINER, TABLE = "a" * 16, "b" * 64


def _json(document):
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode()


def _dead(identity):
    return ProcessObservation(identity, "dead", identity.created, WAIT_OBJECT_0)


class _Fixture:
    def __init__(self, root, owner=ProcessIdentity(111, 1111), target=ProcessIdentity(222, 2222)):
        self.state, self.shared, self.archive = root / "state", root / "shared", root / "evidence"
        self.state.mkdir()
        self.shared.mkdir()
        self.archive.mkdir()
        (self.state / "hooks").mkdir()
        lock = {"schema": 2, "owner_pid": owner.pid, "owner_created": owner.created, "nonce": "c" * 32}
        session = {"schema": 1, "owner": lock, "trainer_id": TRAINER,
                   "target_pid": target.pid, "target_created": target.created}
        payload = {"schema": 1, "engine": "ct2trainer", "trainer_id": TRAINER,
                   "table_sha256": TABLE, "process_name": "fixture.exe", "desired": [7]}
        state = {"payload": payload, "sha256": hashlib.sha256(_json(payload)).hexdigest()}
        hook = {"schema": 1, "engine": "ct2trainer-hooks", "owner": TRAINER + ":fixture",
                "target_pid": target.pid, "target_created": target.created, "state": "enabled", "uncertain": False,
                "allocations": {}, "blocks": [], "entries": [], "exports": {},
                "retirement_policy": "retain-published-allocations-until-target-exit"}
        lua = {"schema": "ct2trainer-lua-activation/v1", "engine": "ct2trainer-lua",
               "trainer_id": TRAINER, "table_sha256": TABLE, "state": "open", "owner": 7,
               "target": [target.pid, target.created], "data": [], "symbols": {}, "assemblies": {}, "pending": None}
        self.claim = self.shared / f"{target.pid}-{target.created}.json"
        for path, document in ((self.state / "state.lock", lock), (self.state / "state.json", state),
                               (self.state / "session.json", session), (self.claim, session),
                               (self.state / "hooks" / "hook.json", hook), (self.state / "hooks" / "lua.json", lua)):
            path.write_bytes(_json(document))

    def assess(self, probe=_dead):
        return assess_recovery(self.state, self.shared, process_probe=probe,
                               expected_trainer_id=TRAINER, expected_table_sha256=TABLE)

    def recover(self, assessment=None, probe=_dead, archive=None):
        return recover_assessment(assessment or self.assess(probe), archive or self.archive,
                                  expected_trainer_id=TRAINER, expected_table_sha256=TABLE, process_probe=probe)

    def originals(self):
        return {path: path.read_bytes() for directory in (self.state, self.shared)
                for path in directory.rglob("*") if path.is_file()}


class RecoveryRefusalTests(unittest.TestCase):
    def test_nonwindows_refusal_never_creates_a_fence_or_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = _Fixture(Path(directory))
            original = fixture.originals()
            assessment = fixture.assess()
            with patch.object(operation.sys, "platform", "linux"):
                report = fixture.recover(assessment)
            self.assertEqual(report.status, "refused")
            self.assertFalse(report.remote_writes)
            self.assertEqual(original, fixture.originals())
            self.assertEqual(list(fixture.archive.iterdir()), [])
            self.assertFalse(report.fence_path.exists())

    def test_arbitrary_serialized_fence_cannot_be_ignored_by_assessment(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = _Fixture(Path(directory))
            fence = fixture.state / "recovery.lock"
            fence.write_bytes(b'{"schema":1,"owner_pid":111}')
            result = fixture.assess()
            self.assertFalse(result.eligible)
            # The fence name is recognized, but the malformed document must
            # still block the assessment with a fence-specific reason.
            self.assertTrue(any("recovery.lock" in reason for reason in result.reasons),
                            result.reasons)
            result = assess_recovery(fixture.state, fixture.shared, process_probe=_dead,
                                     _fence_allowance={"path": str(fence), "raw": fence.read_bytes()})
            self.assertFalse(result.eligible)
            self.assertTrue(any("serialized" in reason for reason in result.reasons))
            with self.assertRaises(ValueError):
                recovery._FenceAllowance(object(), fence, b"{}", lambda: None)


@unittest.skipUnless(sys.platform == "win32", "Real Windows held-file disposition profile")
class WindowsRecoveryOperationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="native-recovery-operation-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.fixture = _Fixture(self.root)

    def test_verified_archive_then_release_preserves_saved_state_and_uses_no_path_unlink(self):
        originals = self.fixture.originals()
        assessment = self.fixture.assess()
        self.assertTrue(assessment.eligible, assessment.reasons)
        with patch.object(Path, "unlink", side_effect=AssertionError("Recovery must use held dispositions")):
            report = self.fixture.recover(assessment)
        self.assertTrue(report.completed, report.reasons)
        self.assertFalse(report.remote_writes)
        self.assertEqual(set(report.released), set(assessment.candidate_paths))
        self.assertEqual(report.released[-1], self.fixture.state / "state.lock")
        self.assertFalse(report.fence_path.exists())
        self.assertEqual((self.fixture.state / "state.json").read_bytes(), originals[self.fixture.state / "state.json"])
        self.assertEqual(self.fixture.assess().status, "clean")
        self.assertEqual(hashlib.sha256(report.archive_path.read_bytes()).hexdigest(), report.archive_sha256)
        self.assertEqual(hashlib.sha256(report.journal_path.read_bytes()).hexdigest(), report.journal_sha256)
        with zipfile.ZipFile(report.archive_path) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(len(manifest["files"]), len(originals))
            for item in manifest["files"]:
                self.assertEqual(archive.read(item["member"]), originals[Path(item["path"])])
                self.assertEqual(item["sha256"], hashlib.sha256(originals[Path(item["path"])]).hexdigest())
        records = [json.loads(line) for line in report.journal_path.read_bytes().splitlines()]
        self.assertEqual(records[-1]["state"], "release-complete")
        self.assertTrue(records[-1]["fence_release_pending"])

    def test_every_original_is_held_against_write_rename_and_delete_during_archive(self):
        archive_function = operation._archive
        observations = []
        def inspect(assessment, held, archive, deadline):
            path = self.fixture.state / "state.lock"
            replacement = self.root / "replacement"
            replacement.write_bytes(b"foreign")
            for action in (lambda: path.write_bytes(b"foreign"), lambda: os.replace(replacement, path), lambda: path.unlink()):
                with self.assertRaises(OSError):
                    action()
                observations.append(True)
            # Directory parents are pinned against substitution too.
            with self.assertRaises(OSError):
                self.fixture.state.rename(self.root / "renamed")
            return archive_function(assessment, held, archive, deadline)
        with patch.object(operation, "_archive", inspect):
            report = self.fixture.recover()
        self.assertTrue(report.completed, report.reasons)
        self.assertEqual(len(observations), 3)

    def test_changed_assessment_is_rejected_after_fencing_with_all_originals_kept(self):
        assessment = self.fixture.assess()
        path = self.fixture.state / "state.lock"
        changed = json.loads(path.read_bytes())
        changed["nonce"] = "d" * 32
        path.write_bytes(_json(changed))
        originals = self.fixture.originals()
        report = self.fixture.recover(assessment)
        self.assertEqual(report.status, "uncertain")
        self.assertEqual(report.released, ())
        self.assertTrue(report.fence_path.exists())
        self.assertTrue(report.journal_path.exists())
        for path, raw in originals.items():
            self.assertEqual(path.read_bytes(), raw)
        self.assertFalse(self.fixture.assess().eligible)

    def test_live_or_unknown_process_after_assessment_keeps_fence_and_originals(self):
        assessment = self.fixture.assess()
        originals = self.fixture.originals()
        report = self.fixture.recover(assessment, probe=lambda identity: ProcessObservation(identity, "unknown", detail="denied", error=5))
        self.assertEqual(report.status, "uncertain")
        self.assertEqual(report.released, ())
        self.assertTrue(report.fence_path.exists())
        self.assertTrue(report.journal_path.exists())
        for path, raw in originals.items():
            self.assertEqual(path.read_bytes(), raw)

    def test_final_process_proof_failure_after_archiving_prevents_every_release(self):
        assessment = self.fixture.assess()
        originals = self.fixture.originals()
        calls = 0
        def probe(identity):
            nonlocal calls
            calls += 1
            return _dead(identity) if calls <= 4 else ProcessObservation(identity, "unknown", detail="query failed")
        report = self.fixture.recover(assessment, probe)
        self.assertEqual(report.status, "uncertain")
        self.assertIsNotNone(report.archive_sha256)
        self.assertTrue(report.archive_path.exists())
        self.assertTrue(report.fence_path.exists())
        self.assertEqual(report.released, ())
        for path, raw in originals.items():
            self.assertEqual(path.read_bytes(), raw)

    def test_fence_write_failure_is_journaled_and_keeps_the_exclusive_gate(self):
        originals = self.fixture.originals()
        write = operation._File.write
        def fail_fence(held, raw):
            if held.path.name == "recovery.lock":
                raise OSError("Injected durable fence write failure")
            return write(held, raw)
        with patch.object(operation._File, "write", fail_fence):
            report = self.fixture.recover()
        self.assertEqual(report.status, "uncertain")
        self.assertTrue(report.fence_path.exists())
        self.assertTrue(report.journal_path.exists())
        self.assertEqual(report.released, ())
        self.assertEqual(json.loads(report.journal_path.read_bytes().splitlines()[-1])["state"], "uncertain")
        for path, raw in originals.items():
            self.assertEqual(path.read_bytes(), raw)

    def test_held_file_identity_substitution_before_acquisition_is_not_deleted(self):
        initialize = operation._File.__init__
        assessment = self.fixture.assess()
        victim = self.fixture.state / "state.lock"
        def substitute(held, kernel, path, **kwargs):
            if path == victim and not kwargs.get("create", False):
                replacement = self.root / "substituted"
                replacement.write_bytes(victim.read_bytes())
                os.replace(replacement, victim)
            return initialize(held, kernel, path, **kwargs)
        with patch.object(operation._File, "__init__", substitute):
            report = self.fixture.recover(assessment)
        self.assertEqual(report.status, "uncertain")
        self.assertEqual(report.released, ())
        self.assertTrue(report.fence_path.exists())
        self.assertTrue(victim.exists())
        self.assertTrue(any("changed identity" in reason for reason in report.reasons), report.reasons)

    def test_failed_close_is_reported_before_fence_release(self):
        close = operation._File.close
        fired = False
        def fail_after_close(held):
            nonlocal fired
            was_open = held.stream is not None
            close(held)
            if was_open and not fired and held.path.suffix == ".zip":
                fired = True
                raise OSError("Injected archive handle close failure")
        with patch.object(operation._File, "close", fail_after_close):
            report = self.fixture.recover()
        self.assertEqual(report.status, "uncertain")
        self.assertTrue(report.fence_path.exists())
        self.assertIsNotNone(report.archive_sha256)
        self.assertTrue(report.journal_path.exists())
        self.assertTrue(any("handle close failure" in reason for reason in report.reasons), report.reasons)

    def test_directory_close_failure_after_fence_release_is_explicit(self):
        close = operation._Directory.close
        fired = False
        def fail_after_close(directory):
            nonlocal fired
            was_open = directory.handle is not None
            close(directory)
            if was_open and not fired and directory.path == self.fixture.state:
                fired = True
                raise OSError("Injected final directory close failure")
        with patch.object(operation._Directory, "close", fail_after_close):
            report = self.fixture.recover()
        self.assertEqual(report.status, "uncertain")
        self.assertTrue(report.fence_released)
        self.assertFalse(report.fence_path.exists())
        self.assertTrue(report.archive_path.exists())
        self.assertTrue(any("after confirmed fence release" in reason for reason in report.reasons), report.reasons)

    def test_archive_readback_corruption_prevents_every_release(self):
        originals = self.fixture.originals()
        read = zipfile.ZipFile.read
        def corrupt(bundle, name, *args, **kwargs):
            raw = read(bundle, name, *args, **kwargs)
            return raw + b"x" if name == "state/state.lock" else raw
        with patch.object(zipfile.ZipFile, "read", corrupt):
            report = self.fixture.recover()
        self.assertEqual(report.status, "uncertain")
        self.assertEqual(report.released, ())
        self.assertTrue(report.archive_path.exists())
        self.assertTrue(report.fence_path.exists())
        self.assertTrue(any("original-byte verification failed" in reason for reason in report.reasons), report.reasons)
        for path, raw in originals.items():
            self.assertEqual(path.read_bytes(), raw)

    def test_partial_disposition_failure_keeps_lock_last_and_all_bytes_in_archive(self):
        originals = self.fixture.originals()
        delete = operation._File.delete
        def fail_hook(held):
            if held.path.name == "hook.json":
                raise OSError("Injected held disposition refusal")
            return delete(held)
        with patch.object(operation._File, "delete", fail_hook):
            report = self.fixture.recover()
        self.assertEqual(report.status, "uncertain")
        self.assertTrue(report.released)
        self.assertTrue(report.fence_path.exists())
        self.assertTrue((self.fixture.state / "state.lock").exists())
        self.assertNotIn(self.fixture.state / "state.lock", report.released)
        with zipfile.ZipFile(report.archive_path) as archive:
            for item in json.loads(archive.read("manifest.json"))["files"]:
                self.assertEqual(archive.read(item["member"]), originals[Path(item["path"])])
        for path, raw in originals.items():
            if path not in report.released:
                self.assertEqual(path.read_bytes(), raw)

    def test_existing_fence_collision_is_refused_without_touching_its_owner(self):
        assessment = self.fixture.assess()
        fence = self.fixture.state / "recovery.lock"
        fence.write_bytes(b"prior owner fence")
        originals = self.fixture.originals()
        report = self.fixture.recover(assessment)
        self.assertEqual(report.status, "refused")
        self.assertEqual(report.released, ())
        self.assertEqual(originals, self.fixture.originals())
        self.assertIsNotNone(report.journal_path)
        self.assertEqual(list(self.fixture.archive.iterdir()), [report.journal_path])

    def test_archive_scope_and_file_budget_refusals_make_no_claim(self):
        originals = self.fixture.originals()
        report = self.fixture.recover(archive=self.fixture.state / "evidence")
        self.assertEqual(report.status, "refused")
        self.assertFalse(report.fence_path.exists())
        with patch.object(operation, "MAX_OPERATION_FILES", 2):
            report = self.fixture.recover()
        self.assertEqual(report.status, "refused")
        self.assertFalse(report.fence_path.exists())
        self.assertEqual(originals, self.fixture.originals())

    def test_foreign_shared_claim_is_archived_but_never_released(self):
        foreign = self.fixture.shared / "444-4444.json"
        foreign.write_bytes(_json({"schema": 1, "owner": {"schema": 2, "owner_pid": 333, "owner_created": 3333,
                                                       "nonce": "d" * 32}, "trainer_id": "e" * 16,
                                  "target_pid": 444, "target_created": 4444}))
        original = foreign.read_bytes()
        report = self.fixture.recover()
        self.assertTrue(report.completed, report.reasons)
        self.assertNotIn(foreign, report.released)
        self.assertEqual(foreign.read_bytes(), original)

    def test_real_owner_and_target_exit_allow_verified_recovery(self):
        real_root = self.root / "real"
        real_root.mkdir()
        children = [subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.readline()"],
                                    stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    creationflags=0x08000000) for _ in range(2)]
        try:
            identities = []
            for child in children:
                observed = WindowsProcessProbe()(ProcessIdentity(child.pid, None))
                self.assertEqual(observed.status, "alive")
                identities.append(ProcessIdentity(child.pid, observed.observed_created))
            fixture = _Fixture(real_root, identities[0], identities[1])
            for child in children:
                child.stdin.close()
                child.wait(timeout=5)
            assessment = fixture.assess(WindowsProcessProbe())
            self.assertTrue(assessment.eligible, assessment.reasons)
            report = fixture.recover(assessment, WindowsProcessProbe())
            self.assertTrue(report.completed, report.reasons)
            self.assertEqual(fixture.assess(WindowsProcessProbe()).status, "clean")
            self.assertTrue(report.archive_path.exists())
            self.assertFalse(report.fence_path.exists())
        finally:
            for child in children:
                if child.poll() is None:
                    child.terminate()
                    child.wait(timeout=5)
                if child.stdin and not child.stdin.closed:
                    child.stdin.close()


if __name__ == "__main__":
    unittest.main()
