"""Read-only crash eligibility, exact Win32 identity, and changing evidence."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ct2trainer.native import recovery
from ct2trainer.native.recovery import (
    ProcessIdentity, ProcessObservation, WindowsProcessProbe, assess_recovery,
    current_process_identity, PROCESS_QUERY_LIMITED_INFORMATION, SYNCHRONIZE,
    WAIT_OBJECT_0, WAIT_TIMEOUT,
)


TRAINER = "a" * 16
TABLE = "b" * 64
OWNER = ProcessIdentity(111, 1111)
TARGET = ProcessIdentity(222, 2222)


def _json(document):
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode()


def _dead(identity):
    return ProcessObservation(identity, "dead", identity.created, WAIT_OBJECT_0)


def _hook(target=TARGET):
    return {"schema": 1, "engine": "ct2trainer-hooks", "owner": TRAINER + ":fixture",
            "target_pid": target.pid, "target_created": target.created, "state": "enabled", "uncertain": False,
            "allocations": {}, "blocks": [], "entries": [{"address": 0x1000, "bytes": "9090",
                "original": "9090", "is_allocation": False, "executable": True,
                "requires_coordinator": True, "allocation": None, "state": "installed"}],
            "exports": {}, "retirement_policy": "retain-published-allocations-until-target-exit"}


def _lua(target=TARGET):
    return {"schema": "ct2trainer-lua-activation/v1", "engine": "ct2trainer-lua",
            "trainer_id": TRAINER, "table_sha256": TABLE, "state": "open",
            "target": [target.pid, target.created], "owner": 1, "data": [{"address": 0x2000,
                "original": "0000", "current": "0100"}], "symbols": {}, "assemblies": {}, "pending": None}


class RecoveryAssessmentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="native-recovery-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.state = self.root / "trainer"
        self.shared = self.root / "_process_sessions"
        self.state.mkdir()
        self.shared.mkdir()
        self.hooks = self.state / "hooks"
        self.hooks.mkdir()
        self.owner = {"schema": 2, "owner_pid": OWNER.pid, "owner_created": OWNER.created, "nonce": "c" * 32}
        self.session = {"schema": 1, "owner": self.owner, "trainer_id": TRAINER,
                        "target_pid": TARGET.pid, "target_created": TARGET.created}
        payload = {"schema": 1, "engine": "ct2trainer", "trainer_id": TRAINER,
                   "table_sha256": TABLE, "process_name": "fixture.exe", "desired": [1, 2]}
        self.write(self.state / "state.json", {"payload": payload, "sha256": hashlib.sha256(_json(payload)).hexdigest()})
        self.write(self.state / "state.lock", self.owner)
        self.write(self.state / "session.json", self.session)
        self.write(self.claim(), self.session)

    def write(self, path, document):
        path.write_bytes(_json(document))

    def claim(self, target=TARGET):
        return self.shared / f"{target.pid}-{target.created}.json"

    def assess(self, probe=_dead, **kwargs):
        return assess_recovery(self.state, self.shared, process_probe=probe,
                               expected_trainer_id=TRAINER, expected_table_sha256=TABLE, **kwargs)

    def assertBlocked(self, result, phrase=None):
        self.assertFalse(result.eligible)
        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.mutation_authorized)
        if phrase:
            self.assertTrue(any(phrase in item for item in result.reasons), result.reasons)

    def test_exact_dead_owner_and_target_qualify_without_any_mutation(self):
        self.write(self.hooks / "hook.json", _hook())
        self.write(self.hooks / "lua.json", _lua())
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob("*") if p.is_file()}
        calls = []
        def probe(identity):
            calls.append(identity)
            return _dead(identity)
        result = self.assess(probe)
        self.assertTrue(result.eligible, result.reasons)
        self.assertEqual(result.status, "eligible-read-only")
        self.assertTrue(result.read_only)
        self.assertFalse(result.mutation_authorized)
        self.assertEqual(calls.count(OWNER), 2)
        self.assertEqual(calls.count(TARGET), 2)
        self.assertTrue(all(p.proven_dead for p in result.processes))
        self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob("*") if p.is_file()})
        self.assertNotIn(self.state / "state.json", result.candidate_paths)
        self.assertEqual(len(result.inventory_sha256), 64)
        self.assertEqual(result.inventory_sha256, self.assess().inventory_sha256)
        self.assertEqual(len(result.files), 6)
        self.assertTrue(any("state.lock last" in step for step in result.next_steps))

    def test_hook_journal_with_captured_placeholders_stays_eligible(self):
        # Field case 2026-10-21 (The Sinking City 2, 0.16-series build):
        # WP-57 journals persist captured_placeholders; the assessment must
        # accept the field, not refuse recovery with "missing or unknown
        # schema fields".
        doc = _hook()
        doc["captured_placeholders"] = {"s1": "6002", "s2": "31"}
        self.write(self.hooks / "captured.json", doc)
        result = self.assess()
        self.assertTrue(result.eligible, result.reasons)

    def test_hook_journal_with_malformed_captured_placeholders_blocks(self):
        for bad in ({"s1": "GGGG"}, {"x1": "6002"}, {"s1": "600"}):
            with self.subTest(bad=bad):
                doc = _hook()
                doc["captured_placeholders"] = bad
                self.write(self.hooks / "bad.json", doc)
                self.assertBlocked(self.assess(), "placeholder captures")
        self.write(self.hooks / "bad.json", _hook())

    def test_nth_scan_receipts_are_bounded_to_the_same_dead_target(self):
        from copy import deepcopy
        definition={'op':'nth_aobscan','symbol':'ownedScan','module':'fixture.exe','pattern':'11 00',
                    'occurrence':2,'part_index':1,'helper':'ct2trainerNthAOB'}
        result={'schema':'ct2trainer-nth-aob-result/v1','definition':definition,
                'target':[TARGET.pid,TARGET.created],'module':[0x1000,256],
                'address':0x1060,'bytes':'1100','match_count':3}
        document=_lua()
        document['nth_aob_results']=[result]
        path=self.hooks/'lua-nth.json'
        self.write(path,document)
        self.assertTrue(self.assess().eligible)
        for mutate in (lambda doc:doc['nth_aob_results'][0].update(target=[333,3333]),
                       lambda doc:doc['nth_aob_results'].append(deepcopy(result)),
                       lambda doc:doc['nth_aob_results'][0].update(bytes='2200')):
            with self.subTest(mutate=mutate):
                changed=deepcopy(document)
                mutate(changed)
                self.write(path,changed)
                self.assertBlocked(self.assess(),'Nth-AOB' if changed['nth_aob_results'][0]['bytes']=='1100' else 'nth-AOB')

    def test_saved_state_alone_is_clean_and_never_promoted_or_deleted(self):
        for path in (self.state / "state.lock", self.state / "session.json", self.claim()):
            path.unlink()
        result = self.assess()
        self.assertEqual(result.status, "clean")
        self.assertFalse(result.eligible)
        self.assertEqual(result.candidate_paths, ())
        self.assertTrue((self.state / "state.json").exists())

    def test_legacy_owner_is_blocked_even_when_pid_is_absent(self):
        legacy = {"owner_pid": OWNER.pid, "nonce": "c" * 32}
        self.session["owner"] = legacy
        self.write(self.state / "state.lock", legacy)
        self.write(self.state / "session.json", self.session)
        self.write(self.claim(), self.session)
        result = self.assess(lambda identity: ProcessObservation(identity, "absent"))
        self.assertBlocked(result, "Legacy owner lock has no creation time")

    def test_owner_or_any_target_live_unknown_or_failed_access_blocks(self):
        for who in (OWNER, TARGET):
            for status in ("alive", "unknown"):
                with self.subTest(who=who, status=status):
                    def probe(identity):
                        return (ProcessObservation(identity, status, identity.created, WAIT_TIMEOUT,
                                                   "Access is denied", 5) if identity == who else _dead(identity))
                    self.assertBlocked(self.assess(probe), "not proven dead")

    def test_pid_reuse_proves_only_recorded_identity_dead(self):
        def reused(identity):
            return ProcessObservation(identity, "reused", identity.created + 1, WAIT_TIMEOUT)
        result = self.assess(reused)
        self.assertTrue(result.eligible, result.reasons)
        self.assertTrue(all(p.proven_dead for p in result.processes))
        self.assertTrue(all(p.observations[0].wait_result == WAIT_TIMEOUT for p in result.processes))
        self.assertFalse(ProcessObservation(OWNER, "reused", OWNER.created + 1, False).proven_dead)
        self.assertFalse(ProcessObservation(ProcessIdentity(OWNER.pid, None), "reused", 9999, WAIT_TIMEOUT).proven_dead)

    def test_all_old_journal_targets_must_also_be_dead(self):
        old = ProcessIdentity(333, 3333)
        self.write(self.hooks / "retired.json", _hook(old))
        self.write(self.hooks / "lua-old.json", _lua(old))
        def probe(identity):
            return ProcessObservation(identity, "alive", identity.created, WAIT_TIMEOUT) if identity == old else _dead(identity)
        result = self.assess(probe)
        self.assertBlocked(result, "333/3333")
        self.assertEqual(len(result.processes), 3)

    def test_partial_shared_claim_is_bound_even_before_local_session_write(self):
        (self.state / "session.json").unlink()
        result = self.assess()
        self.assertTrue(result.eligible, result.reasons)
        self.assertIn(self.claim(), result.candidate_paths)
        self.assertEqual({p.identity for p in result.processes}, {OWNER, TARGET})

    def test_valid_foreign_shared_owner_stays_untouched_and_unprobed(self):
        foreign = {"schema": 1, "owner": {"schema": 2, "owner_pid": 444, "owner_created": 4444, "nonce": "d" * 32},
                   "trainer_id": "e" * 16, "target_pid": 555, "target_created": 5555}
        path = self.shared / "555-5555.json"
        self.write(path, foreign)
        calls = []
        def probe(identity):
            calls.append(identity)
            return _dead(identity)
        result = self.assess(probe)
        self.assertTrue(result.eligible, result.reasons)
        self.assertNotIn(path, result.candidate_paths)
        self.assertNotIn(555, [identity.pid for identity in calls])
        self.assertTrue(path.exists())

    def test_session_requires_byte_identical_shared_target_claim(self):
        self.claim().unlink()
        self.assertBlocked(self.assess(), "byte-identical")
        self.claim().write_text(json.dumps(self.session, indent=2))
        self.assertBlocked(self.assess(), "byte-identical")

    def test_wrong_session_owner_and_wrong_shared_filename_block(self):
        session = json.loads(_json(self.session))
        session["owner"]["nonce"] = "d" * 32
        self.write(self.state / "session.json", session)
        self.assertBlocked(self.assess(), "differs")
        self.write(self.state / "session.json", self.session)
        self.claim().rename(self.shared / "wrong.json")
        self.assertBlocked(self.assess(), "filename")

    def test_changes_during_first_or_final_probe_block_the_snapshot(self):
        for at_call in (1, 4):
            with self.subTest(at_call=at_call):
                calls = 0
                self.write(self.state / "state.lock", self.owner)
                def probe(identity):
                    nonlocal calls
                    calls += 1
                    if calls == at_call:
                        changed = dict(self.owner, nonce="d" * 32)
                        self.write(self.state / "state.lock", changed)
                    return _dead(identity)
                self.assertBlocked(self.assess(probe), "changed")

    def test_same_bytes_replaced_file_and_added_file_also_block(self):
        def replace(identity):
            if not hasattr(replace, "done"):
                replace.done = True
                path = self.state / "state.lock"
                replacement = self.state / "replacement.tmp"
                replacement.write_bytes(path.read_bytes())
                os.replace(replacement, path)
            return _dead(identity)
        self.assertBlocked(self.assess(replace), "changed")
        def added(identity):
            (self.state / "new-file").write_bytes(b"x")
            return _dead(identity)
        self.assertBlocked(self.assess(added), "changed")

    def test_swapped_open_handle_is_rejected_even_with_identical_bytes(self):
        outside = self.root / "outside-lock"
        outside.write_bytes((self.state / "state.lock").read_bytes())
        original_open = Path.open
        def swapped(path, *args, **kwargs):
            return original_open(outside if path == self.state / "state.lock" else path, *args, **kwargs)
        with patch.object(Path, "open", swapped):
            self.assertBlocked(self.assess(), "opened recovery file differs")

    def test_corrupt_duplicate_newschema_and_unknown_artifacts_block(self):
        for raw in (b'{"owner_pid":111,"owner_pid":111}', b'{', _json(dict(self.owner, schema=3)),
                    _json(dict(self.owner, future=True)), _json(dict(self.owner, owner_created=None)),
                    _json(dict(self.owner, owner_pid=True))):
            with self.subTest(raw=raw):
                (self.state / "state.lock").write_bytes(raw)
                self.assertBlocked(self.assess())
        self.write(self.state / "state.lock", self.owner)
        (self.hooks / "future.bin").write_bytes(b"x")
        self.assertBlocked(self.assess(), "Unknown recovery artifact")

    def test_state_checksum_and_expected_binding_fail_closed(self):
        state_path = self.state / "state.json"
        doc = json.loads(state_path.read_bytes())
        doc["sha256"] = "0" * 64
        self.write(state_path, doc)
        self.assertBlocked(self.assess(), "checksum")
        result = assess_recovery(self.state, self.shared, process_probe=_dead,
                                 expected_trainer_id="e" * 16, expected_table_sha256=TABLE)
        self.assertBlocked(result)

    def test_unbound_hook_or_nested_directory_or_hardlink_blocks(self):
        self.write(self.hooks / "foreign.json", dict(_hook(), owner="e" * 16 + ":foreign"))
        self.assertBlocked(self.assess(), "unbound")
        (self.hooks / "foreign.json").unlink()
        (self.hooks / "nested").mkdir()
        self.assertBlocked(self.assess(), "Unsafe")
        (self.hooks / "nested").rmdir()
        original = self.state / "state.lock"
        linked = self.root / "linked-lock"
        try:
            os.link(original, linked)
        except OSError as exc:
            self.skipTest("Hard links unavailable: " + str(exc))
        self.assertBlocked(self.assess(), "Unsafe")

    def test_symlink_and_broken_shared_symlink_are_not_followed(self):
        destination = self.root / "outside.json"
        destination.write_bytes(b"secret")
        link = self.hooks / "linked.json"
        try:
            link.symlink_to(destination)
        except OSError as exc:
            self.skipTest("Symlink creation unavailable: " + str(exc))
        self.assertBlocked(self.assess(), "Unsafe")
        link.unlink()
        for path in self.shared.iterdir():
            path.unlink()
        self.shared.rmdir()
        self.shared.symlink_to(self.root / "does-not-exist", target_is_directory=True)
        self.assertBlocked(self.assess(), "Unsafe")

    def test_lua_hook_references_need_same_exact_target_and_local_path(self):
        hook_path = self.hooks / "owned.json"
        lua = _lua()
        lua["assemblies"] = {"f" * 32: {"source_sha256": "1" * 64, "journal": str(hook_path)}}
        self.write(self.hooks / "lua.json", lua)
        self.assertBlocked(self.assess(), "missing, foreign")
        self.write(hook_path, _hook())
        self.assertTrue(self.assess().eligible)
        self.write(hook_path, _hook(ProcessIdentity(333, 3333)))
        self.assertBlocked(self.assess(), "different-target")
        lua["assemblies"]["f" * 32]["journal"] = str(self.root / "outside.json")
        self.write(self.hooks / "lua.json", lua)
        self.assertBlocked(self.assess(), "foreign")

    def test_first_save_crash_can_bind_identity_from_lua_receipt(self):
        (self.state / "state.json").unlink()
        self.write(self.hooks / "lua.json", _lua())
        result = assess_recovery(self.state, self.shared, process_probe=_dead)
        self.assertTrue(result.eligible, result.reasons)

    def test_partial_claim_binds_trainer_before_first_state_or_session_save(self):
        (self.state / "state.json").unlink()
        (self.state / "session.json").unlink()
        result = assess_recovery(self.state, self.shared, process_probe=_dead)
        self.assertTrue(result.eligible, result.reasons)
        self.assertIn(self.claim(), result.candidate_paths)
        self.assertEqual({p.identity for p in result.processes}, {OWNER, TARGET})
        foreign = dict(self.session, trainer_id="e" * 16)
        self.write(self.shared / "333-3333.json", dict(foreign, target_pid=333, target_created=3333))
        self.assertBlocked(assess_recovery(self.state, self.shared, process_probe=_dead), "another trainer")

    def test_hook_and_lua_unknown_schema_or_unsafe_ranges_block(self):
        documents = [dict(_hook(), schema=2), dict(_hook(), future=True), dict(_lua(), schema="future")]
        bad = _hook()
        bad["entries"][0]["address"] = -1
        documents.append(bad)
        for doc in documents:
            with self.subTest(doc=doc):
                self.write(self.hooks / "journal.json", doc)
                self.assertBlocked(self.assess())

    def test_injected_probe_errors_foreign_identity_or_partial_death_do_not_qualify(self):
        probes = [lambda identity: _dead(ProcessIdentity(999, 9999)), lambda identity: True,
                  lambda identity: ProcessObservation(identity, "dead", identity.created, WAIT_TIMEOUT)]
        def raises(identity):
            raise OSError("Access failed")
        probes.append(raises)
        for probe in probes:
            with self.subTest(probe=probe):
                self.assertBlocked(self.assess(probe), "not proven dead")

    def test_incomplete_state_and_journal_temporary_files_remain_evidence(self):
        (self.state / "state.json.tmp").write_bytes(b"{")
        self.assertBlocked(self.assess(), "corrupt")
        self.assertEqual((self.state / "state.json.tmp").read_bytes(), b"{")
        (self.state / "state.json.tmp").unlink()
        self.write(self.hooks / ("owned.json." + "f" * 32 + ".tmp"), _hook())
        self.assertTrue(self.assess().eligible)

    def test_explicit_budgets_and_separate_directory_scopes(self):
        with patch.object(recovery, "MAX_FILES", 2):
            self.assertBlocked(self.assess(), "file-count")
        with patch.object(recovery, "MAX_SNAPSHOT_BYTES", 8):
            self.assertBlocked(self.assess(), "byte bounds")
        with patch.object(recovery, "MAX_ASSESS_SECONDS", -1):
            self.assertBlocked(self.assess(), "elapsed-time")
        result = assess_recovery(self.state, self.state, process_probe=_dead)
        self.assertBlocked(result, "separate ownership scopes")

    def test_reparse_attributes_fail_closed_without_following_the_path(self):
        information = SimpleNamespace(st_mode=0o100600, st_file_attributes=0x400, st_nlink=1)
        with patch.object(Path, "lstat", return_value=information):
            with self.assertRaisesRegex(ValueError, "Unsafe reparse"):
                recovery._safe_stat(self.state / "state.lock")

    @unittest.skipUnless(sys.platform == "win32", "Exact Windows owner/target exit assessment")
    def test_real_dead_target_still_blocks_until_exact_owner_exits(self):
        children = [subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.readline()"],
                                    stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    creationflags=0x08000000) for _ in range(2)]
        try:
            identities = []
            for child in children:
                observed = WindowsProcessProbe()(ProcessIdentity(child.pid, None))
                self.assertEqual(observed.status, "alive")
                identities.append(ProcessIdentity(child.pid, observed.observed_created))
            owner, target = identities
            lock = {"schema": 2, "owner_pid": owner.pid, "owner_created": owner.created, "nonce": "c" * 32}
            session = {"schema": 1, "owner": lock, "trainer_id": TRAINER,
                       "target_pid": target.pid, "target_created": target.created}
            self.claim().unlink()
            self.write(self.state / "state.lock", lock)
            self.write(self.state / "session.json", session)
            self.write(self.claim(target), session)
            self.write(self.hooks / "hook.json", _hook(target))
            self.write(self.hooks / "lua.json", _lua(target))
            children[1].stdin.close()
            children[1].wait(timeout=5)
            pending = assess_recovery(self.state, self.shared)
            self.assertBlocked(pending, f"{owner.pid}/{owner.created}")
            children[0].stdin.close()
            children[0].wait(timeout=5)
            original = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
            ready = assess_recovery(self.state, self.shared)
            self.assertTrue(ready.eligible, ready.reasons)
            self.assertTrue(all(p.proven_dead for p in ready.processes))
            self.assertEqual(original, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()})
        finally:
            for child in children:
                if child.poll() is None:
                    child.terminate()
                    child.wait(timeout=5)
                if child.stdin and not child.stdin.closed:
                    child.stdin.close()


class _Kernel:
    """Injectable Win32 contract, including incomplete process enumeration."""
    def __init__(self, created=1111, wait=WAIT_TIMEOUT, open_error=None, pids=(1, 2)):
        self.created, self.wait, self.open_error, self.pids = created, wait, open_error, list(pids)
        self.last_error = 0
        self.calls = []
        self.query_ok = True
        self.snapshot_ok = True
        self.first_ok = True
        self.end_error = recovery.ERROR_NO_MORE_FILES
        self.close_failed = set()

    def OpenProcess(self, rights, inherit, pid):
        self.calls.append(("OpenProcess", rights, inherit, pid))
        if self.open_error is not None:
            self.last_error = self.open_error
            return None
        return 42

    def GetProcessTimes(self, handle, creation, exit_time, kernel_time, user_time):
        self.calls.append(("GetProcessTimes", handle))
        if not self.query_ok:
            self.last_error = 5
            return False
        value = ctypes.cast(creation, ctypes.POINTER(recovery._FileTime)).contents
        value.low, value.high = self.created & 0xFFFFFFFF, self.created >> 32
        return True

    def WaitForSingleObject(self, handle, milliseconds):
        self.calls.append(("WaitForSingleObject", handle, milliseconds))
        return self.wait

    def CloseHandle(self, handle):
        self.calls.append(("CloseHandle", handle))
        self.last_error = 5 if handle in self.close_failed else self.last_error
        return handle not in self.close_failed

    def CreateToolhelp32Snapshot(self, flags, pid):
        self.calls.append(("CreateToolhelp32Snapshot", flags, pid))
        return 43 if self.snapshot_ok else ctypes.c_void_p(-1).value

    def Process32FirstW(self, snapshot, entry):
        self.calls.append(("Process32FirstW", snapshot))
        self.index = 0
        if not self.first_ok or not self.pids:
            self.last_error = recovery.ERROR_NO_MORE_FILES
            return False
        target = ctypes.cast(entry, ctypes.POINTER(recovery._ProcessEntry)).contents
        self.entry_size = target.size
        target.pid = self.pids[0]
        return True

    def Process32NextW(self, snapshot, entry):
        self.index += 1
        if self.index == len(self.pids):
            self.last_error = self.end_error
            return False
        ctypes.cast(entry, ctypes.POINTER(recovery._ProcessEntry)).contents.pid = self.pids[self.index]
        return True


class WindowsProcessProofTests(unittest.TestCase):
    def test_limited_rights_held_times_signal_and_handle_close(self):
        kernel = _Kernel(created=0x12345678ABCDEF01, wait=WAIT_OBJECT_0)
        identity = ProcessIdentity(111, kernel.created)
        observed = WindowsProcessProbe(kernel)(identity)
        self.assertTrue(observed.proven_dead)
        self.assertEqual(observed.observed_created, kernel.created)
        self.assertEqual(kernel.calls[0], ("OpenProcess", PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, 111))
        self.assertIn(("WaitForSingleObject", 42, 0), kernel.calls)
        self.assertEqual(kernel.calls[-1], ("CloseHandle", 42))

    def test_alive_reuse_and_unknown_legacy_creation(self):
        kernel = _Kernel()
        observed = WindowsProcessProbe(kernel)(OWNER)
        self.assertEqual(observed.status, "alive")
        self.assertFalse(observed.proven_dead)
        observed = WindowsProcessProbe(kernel)(ProcessIdentity(111, 2222))
        self.assertEqual(observed.status, "reused")
        self.assertTrue(observed.proven_dead)
        observed = WindowsProcessProbe(kernel)(ProcessIdentity(111, None))
        self.assertEqual(observed.observed_created, 1111)
        self.assertFalse(observed.proven_dead)

    def test_failed_open_does_not_treat_access_denied_as_absence(self):
        kernel = _Kernel(open_error=5)
        observed = WindowsProcessProbe(kernel)(OWNER)
        self.assertEqual(observed.status, "unknown")
        self.assertFalse(observed.proven_dead)
        self.assertEqual(len(kernel.calls), 1)

    def test_invalid_pid_needs_successful_complete_snapshot_omission(self):
        kernel = _Kernel(open_error=87, pids=(0, 1, 2))
        observed = WindowsProcessProbe(kernel)(OWNER)
        self.assertEqual(observed.status, "absent")
        self.assertTrue(observed.proven_dead)
        self.assertEqual(kernel.entry_size, ctypes.sizeof(recovery._ProcessEntry))
        self.assertIn(("CreateToolhelp32Snapshot", 2, 0), kernel.calls)
        self.assertEqual(kernel.calls[-1], ("CloseHandle", 43))

    def test_failed_or_incomplete_snapshot_or_pid_present_remain_unknown(self):
        kernels = [_Kernel(open_error=87, pids=(1, 111)), _Kernel(open_error=87, pids=())]
        for attribute, value in (("snapshot_ok", False), ("first_ok", False), ("end_error", 5), ("close_failed", {43})):
            kernel = _Kernel(open_error=87)
            setattr(kernel, attribute, value)
            kernels.append(kernel)
        for kernel in kernels:
            with self.subTest(kernel=kernel.__dict__):
                observed = WindowsProcessProbe(kernel)(OWNER)
                self.assertEqual(observed.status, "unknown")
                self.assertFalse(observed.proven_dead)

    def test_query_signal_creation_and_cleanup_failures_remain_unknown(self):
        kernels = [_Kernel(created=0), _Kernel(wait=0xFFFFFFFF)]
        for attribute, value in (("query_ok", False), ("close_failed", {42})):
            kernel = _Kernel(wait=WAIT_OBJECT_0)
            setattr(kernel, attribute, value)
            kernels.append(kernel)
        for kernel in kernels:
            with self.subTest(kernel=kernel.__dict__):
                observed = WindowsProcessProbe(kernel)(OWNER)
                self.assertEqual(observed.status, "unknown")
                self.assertFalse(observed.proven_dead)
                self.assertEqual(kernel.calls[-1], ("CloseHandle", 42))

    def test_current_identity_helper_never_fabricates_creation_time(self):
        def alive(identity):
            return ProcessObservation(identity, "alive", 98765, WAIT_TIMEOUT)
        self.assertEqual(current_process_identity(alive), ProcessIdentity(os.getpid(), 98765))
        self.assertEqual(current_process_identity(lambda identity: ProcessObservation(identity, "unknown")),
                         ProcessIdentity(os.getpid(), None))
        def failed(identity):
            raise OSError("denied")
        self.assertEqual(current_process_identity(failed).created, None)
        self.assertEqual(current_process_identity(lambda identity: _dead(identity)).created, None)

    def test_invalid_process_identity_is_rejected(self):
        for pid, created in ((0, 1), (-1, 1), (True, 1), (1, False), (1, 0), (1, 2 ** 64)):
            with self.subTest(pid=pid, created=created):
                with self.assertRaises(ValueError):
                    ProcessIdentity(pid, created)

    @unittest.skipUnless(sys.platform == "win32", "Owned real process identity proof requires Windows")
    def test_real_owned_process_liveness_then_exit_and_own_identity(self):
        own = current_process_identity()
        self.assertIsNotNone(own.created)
        self.assertEqual(WindowsProcessProbe()(own).status, "alive")
        child = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.readline()"], stdin=subprocess.PIPE,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)
        try:
            observed = WindowsProcessProbe()(ProcessIdentity(child.pid, None))
            self.assertEqual(observed.status, "alive")
            exact = ProcessIdentity(child.pid, observed.observed_created)
            self.assertFalse(WindowsProcessProbe()(exact).proven_dead)
            child.stdin.close()
            child.wait(timeout=5)
            self.assertEqual(child.returncode, 0)
            after = WindowsProcessProbe()(exact)
            self.assertTrue(after.proven_dead, after)
        finally:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=5)
            if child.stdin and not child.stdin.closed:
                child.stdin.close()


if __name__ == "__main__":
    unittest.main()
