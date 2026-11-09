"""0.38 --force: the forced state reclaim (state_force.force_reclaim).

The documented SteamOS dead end (a leftover recovery fence or any other
unclassifiable held state that fires the conservative refusal on every
start) gets a bounded escape hatch: every recorded trainer-side owner is
probed, a proven-alive owner refuses the reclaim (the one hard boundary
that stays even under --force), and every other case - proven-dead
owner, unprovable owner (transient probe failure, legacy lock without
creation identity, unparseable document) - quarantines the blocking
artifacts into a timestamped archive with a full evidence document
while the saved state.json is preserved.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from ct2trainer.native.recovery import ProcessIdentity, ProcessObservation
from ct2trainer.native.state_force import force_reclaim

TRAINER_ID = "a" * 16
TABLE_SHA = "b" * 64


def _plan():
    return {"trainer_id": TRAINER_ID, "table_sha256": TABLE_SHA}


def _lock(pid, created=None):
    document = {"owner_pid": pid, "nonce": "c" * 32}
    if created is not None:
        document.update(schema=2, owner_created=created)
    return json.dumps(document).encode()


def _fence(pid, created):
    return json.dumps({
        "schema": 1,
        "engine": "ct2trainer-recovery-fence",
        "owner_pid": pid,
        "owner_created": created,
        "nonce": "d" * 32,
        "trainer_id": TRAINER_ID,
        "table_sha256": TABLE_SHA,
        "assessment_sha256": "e" * 64,
    }).encode()


def _session(pid, created, trainer_id=TRAINER_ID,
             target_pid=900, target_created=901):
    return json.dumps({
        "schema": 1,
        "owner": {"owner_pid": pid, "owner_created": created,
                  "schema": 2, "nonce": "f" * 32},
        "trainer_id": trainer_id,
        "target_pid": target_pid,
        "target_created": target_created,
    }).encode()


class _Probe:
    """Deterministic probe: status per (pid, created); list values are
    consumed left to right so the single 'unknown' retry is coverable."""

    def __init__(self, statuses):
        self.remaining = {
            key: list(value) if isinstance(value, (list, tuple)) else [value]
            for key, value in statuses.items()
        }
        self.calls = []

    def __call__(self, identity):
        self.calls.append(identity)
        queue = self.remaining[(identity.pid, identity.created)]
        status = queue.pop(0) if len(queue) > 1 else queue[0]
        return ProcessObservation(identity, status, detail="probe " + status)


class ForceReclaimTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        self.native = self.home / "CT2Trainer" / "native"
        self.state_dir = self.native / TRAINER_ID
        self.shared_dir = self.native / "_process_sessions"
        self.state_dir.mkdir(parents=True)
        self.shared_dir.mkdir(parents=True)

    def _evidence(self) -> dict:
        archives = sorted((self.native / "forced-recovery").iterdir())
        self.assertEqual(len(archives), 1)
        return json.loads(
            (archives[0] / "force-reclaim.json").read_text(encoding="utf-8"))

    def test_live_state_lock_owner_refuses_state_untouched(self):
        (self.state_dir / "state.lock").write_bytes(_lock(500, 5000))
        (self.state_dir / "state.json").write_text('{"payload": 1}')
        probe = _Probe({(500, 5000): "alive"})
        completed, detail = force_reclaim(self.state_dir, self.shared_dir,
                                          _plan(), process_probe=probe)
        self.assertFalse(completed)
        self.assertIn("proven alive", detail)
        self.assertTrue((self.state_dir / "state.lock").is_file())
        self.assertTrue((self.state_dir / "state.json").is_file())
        self.assertFalse((self.native / "forced-recovery").exists())

    def test_dead_owners_quarantined_saved_state_preserved(self):
        (self.state_dir / "state.lock").write_bytes(_lock(500, 5000))
        (self.state_dir / "session.json").write_bytes(_session(500, 5000))
        (self.state_dir / "state.json").write_text('{"payload": 1}')
        (self.state_dir / "state.json.tmp").write_bytes(b"tmp")
        probe = _Probe({(500, 5000): "dead"})
        completed, detail = force_reclaim(self.state_dir, self.shared_dir,
                                          _plan(), process_probe=probe,
                                          retry_delay=0)
        self.assertTrue(completed)
        self.assertIn("the saved state was preserved", detail)
        self.assertFalse((self.state_dir / "state.lock").exists())
        self.assertFalse((self.state_dir / "session.json").exists())
        self.assertFalse((self.state_dir / "state.json.tmp").exists())
        self.assertTrue((self.state_dir / "state.json").is_file())
        evidence = self._evidence()
        self.assertEqual(evidence["schema"], "ct2trainer-forced-reclaim/v1")
        self.assertEqual(evidence["trainer_id"], TRAINER_ID)
        self.assertEqual(evidence["preserved"], ["state.json"])
        self.assertEqual(len(evidence["moved"]), 3)
        self.assertEqual({item["artifact"] for item in evidence["owners"]},
                         {"state lock", "session record"})
        self.assertTrue(all(item["status"] == "dead"
                            for item in evidence["owners"]))

    def test_dead_fence_owner_reclaimed(self):
        (self.state_dir / "recovery.lock").write_bytes(_fence(600, 6000))
        probe = _Probe({(600, 6000): "dead"})
        completed, detail = force_reclaim(self.state_dir, self.shared_dir,
                                          _plan(), process_probe=probe,
                                          retry_delay=0)
        self.assertTrue(completed)
        self.assertFalse((self.state_dir / "recovery.lock").exists())
        evidence = self._evidence()
        self.assertEqual(evidence["owners"][0]["artifact"], "recovery fence")
        self.assertEqual(evidence["owners"][0]["owner_pid"], 600)

    def test_own_shared_claim_moved_foreign_kept(self):
        (self.state_dir / "session.json").write_bytes(_session(500, 5000))
        (self.shared_dir / "900-901.json").write_bytes(_session(500, 5000))
        (self.shared_dir / "950-951.json").write_bytes(
            _session(700, 7000, trainer_id="f" * 16,
                     target_pid=950, target_created=951))
        probe = _Probe({(500, 5000): "dead"})
        completed, _ = force_reclaim(self.state_dir, self.shared_dir,
                                     _plan(), process_probe=probe,
                                     retry_delay=0)
        self.assertTrue(completed)
        self.assertFalse((self.shared_dir / "900-901.json").exists())
        self.assertTrue((self.shared_dir / "950-951.json").is_file())
        evidence = self._evidence()
        self.assertEqual({item["artifact"] for item in evidence["owners"]},
                         {"session record", "shared process claim"})

    def test_live_shared_claim_owner_refuses(self):
        (self.shared_dir / "900-901.json").write_bytes(_session(500, 5000))
        probe = _Probe({(500, 5000): "alive"})
        completed, detail = force_reclaim(self.state_dir, self.shared_dir,
                                          _plan(), process_probe=probe)
        self.assertFalse(completed)
        self.assertIn("proven alive", detail)
        self.assertTrue((self.shared_dir / "900-901.json").is_file())
        self.assertFalse((self.native / "forced-recovery").exists())

    def test_no_artifacts_nothing_moved(self):
        probe = _Probe({})
        completed, detail = force_reclaim(self.state_dir, self.shared_dir,
                                          _plan(), process_probe=probe)
        self.assertTrue(completed)
        self.assertEqual(detail,
                         "no blocking state artifacts present; "
                         "nothing was moved")
        self.assertFalse((self.native / "forced-recovery").exists())

    def test_unprovable_owner_quarantined_with_evidence(self):
        (self.state_dir / "state.lock").write_bytes(_lock(500, 5000))
        probe = _Probe({(500, 5000): ["unknown", "unknown"]})
        completed, detail = force_reclaim(self.state_dir, self.shared_dir,
                                          _plan(), process_probe=probe,
                                          retry_delay=0)
        self.assertTrue(completed)
        self.assertEqual(len(probe.calls), 2)
        evidence = self._evidence()
        self.assertEqual(evidence["owners"][0]["status"], "unknown")

    def test_non_windows_without_probe_refused(self):
        (self.state_dir / "state.lock").write_bytes(_lock(500, 5000))
        with patch("ct2trainer.native.state_force.sys.platform", "linux"):
            completed, detail = force_reclaim(self.state_dir, self.shared_dir,
                                              _plan())
        self.assertFalse(completed)
        self.assertIn("requires Windows", detail)
        self.assertTrue((self.state_dir / "state.lock").is_file())

    def test_corrupt_lock_quarantined_unprovable(self):
        (self.state_dir / "state.lock").write_bytes(b"not json")
        probe = _Probe({})
        completed, detail = force_reclaim(self.state_dir, self.shared_dir,
                                          _plan(), process_probe=probe,
                                          retry_delay=0)
        self.assertTrue(completed)
        self.assertEqual(probe.calls, [])
        evidence = self._evidence()
        self.assertEqual(evidence["owners"][0]["status"], "unprovable")

    def test_hooks_and_global_pool_reclaimed(self):
        hooks = self.state_dir / "hooks"
        hooks.mkdir()
        (hooks / "global-pool.json").write_text("{}")
        (hooks / "j1.json").write_text("{}")
        completed, _ = force_reclaim(self.state_dir, self.shared_dir,
                                     _plan(), process_probe=_Probe({}))
        self.assertTrue(completed)
        self.assertFalse(hooks.exists())
        evidence = self._evidence()
        names = {Path(item["archive"]).name for item in evidence["moved"]}
        self.assertEqual(names, {"global-pool.json", "j1.json"})
        archives = {Path(item["archive"]).as_posix()
                    for item in evidence["moved"]}
        self.assertTrue(all("hooks/" in name for name in archives))

    def test_legacy_lock_quarantined_unprovable(self):
        # A legacy owner lock (no creation identity) cannot be proven
        # dead; under --force it is quarantined and recorded as such.
        # The unknown observation triggers the documented single retry.
        (self.state_dir / "state.lock").write_bytes(_lock(500))
        probe = _Probe({(500, None): ["unknown", "unknown"]})
        completed, detail = force_reclaim(self.state_dir, self.shared_dir,
                                          _plan(), process_probe=probe,
                                          retry_delay=0)
        self.assertTrue(completed)
        self.assertEqual(probe.calls, [ProcessIdentity(500, None)] * 2)

    def test_moved_bytes_preserved_with_sha(self):
        payload = b"payload-bytes"
        (self.state_dir / "state.json.tmp").write_bytes(payload)
        completed, _ = force_reclaim(self.state_dir, self.shared_dir,
                                     _plan(), process_probe=_Probe({}))
        self.assertTrue(completed)
        entry = self._evidence()["moved"][0]
        target = Path(entry["archive"])
        self.assertEqual(target.read_bytes(), payload)
        self.assertEqual(entry["size"], len(payload))
        self.assertEqual(entry["sha256"],
                         hashlib.sha256(payload).hexdigest())

    def test_archive_collision_refused(self):
        class _Fixed(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 11, 9, 12, 0, 0,
                                tzinfo=tz or timezone.utc)

        stamp = "20261109T120000Z"
        (self.state_dir / "state.lock").write_bytes(_lock(500, 5000))
        probe = _Probe({(500, 5000): "dead"})
        with patch("ct2trainer.native.state_force.datetime", _Fixed):
            completed, _ = force_reclaim(self.state_dir, self.shared_dir,
                                         _plan(), process_probe=probe)
            self.assertTrue(completed)
            # A second blocked start in the same second hits the
            # existing archive: a named refusal, not a merge.
            (self.state_dir / "state.lock").write_bytes(_lock(500, 5000))
            completed, detail = force_reclaim(self.state_dir, self.shared_dir,
                                              _plan(), process_probe=probe)
        self.assertFalse(completed)
        self.assertIn("another forced reclaim", detail)
        self.assertTrue((self.state_dir / "state.lock").is_file())


if __name__ == "__main__":
    unittest.main()
