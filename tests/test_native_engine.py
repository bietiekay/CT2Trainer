"""Failure-oriented tests of the independent controller, without target access."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import struct
import tempfile
import unittest
from unittest.mock import patch

from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import (LiveStateConflict, NativeRuntimeError, StateError,
                                        TrainerEngine, format_value, parse_value, validate_plan)
from ct2trainer.native.recovery import ProcessObservation, WAIT_TIMEOUT


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "windows" / "fixture_target" / "fixture.ct"


class FakeMemory:
    def __init__(self, pid=123, creation_time=456):
        self.pid, self.creation_time = pid, creation_time
        self.pointer_size = 8
        self.alive, self.closed = True, False
        self.base = 0x1000
        self.data = bytearray(256)
        self.data[:16] = b"CT2T-FIX-2026-01"
        self.data[16:20] = struct.pack("<I", 1234)
        self.writes = []
        self.fail_once = False
        self.alive_error = False

    def is_alive(self):
        if self.alive_error:
            raise OSError("Liveness unavailable")
        return self.alive

    def close(self):
        self.closed = True

    def module(self, name):
        if name.casefold() != "fixturetarget.exe":
            raise OSError("Unknown module")
        return self.base, len(self.data)

    def read(self, address, size):
        offset = address - self.base
        if not 0 <= offset <= len(self.data) - size:
            raise OSError("Invalid address")
        return bytes(self.data[offset:offset + size])

    def write(self, address, raw):
        offset = address - self.base
        self.writes.append((address, raw))
        if self.fail_once:
            self.fail_once = False
            self.data[offset:offset + 1] = raw[:1]
            raise OSError("Injected partial write")
        self.data[offset:offset + len(raw)] = raw

    def scan_module(self, name, pattern):
        self.module(name)
        pattern = bytes.fromhex(pattern.replace(" ", ""))
        first = self.data.find(pattern)
        if first < 0 or self.data.find(pattern, first + 1) >= 0:
            raise OSError("Pattern has no unique match")
        return self.base + first

    def resolve(self, expression, symbols=None):
        symbols = {key.casefold(): value for key, value in (symbols or {}).items()}
        match = re.fullmatch(r'("[^"]+"|[A-Za-z_][\w.]*|[0-9a-fA-F]+)(?:([+-])([0-9a-fA-F]+))?', expression)
        if match is None:
            raise OSError("Invalid expression")
        base, sign, offset = match.groups()
        if base.strip('"').casefold() == "fixturetarget.exe":
            result = self.base
        elif base.casefold() in symbols:
            result = symbols[base.casefold()]
        else:
            try:
                result = int(base, 16)
            except ValueError as exc:
                raise OSError("Unknown symbol: " + base) from exc
        return result + (int(offset, 16) * (-1 if sign == "-" else 1) if offset else 0)

    def resolve_pointer(self, expression, offsets, symbols=None):
        address = self.resolve(expression, symbols)
        for offset in reversed(offsets):
            address = int.from_bytes(self.read(address, self.pointer_size), "little") + offset
        return address


class NativeEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.shared = self.directory / "shared"
        self.plan = compile_table(FIXTURE, "FixtureTarget.exe")
        self.memory = FakeMemory()
        self.factory = lambda _name: self.memory
        self.engine = None

    def tearDown(self):
        if self.engine is not None and not self.engine.closed:
            self.engine.close()
        self.temp.cleanup()

    def start(self, attach=True):
        self.engine = TrainerEngine(self.plan, self.directory, self.factory, self.shared)
        if attach:
            self.engine.poll()
            self.assertTrue(self.engine.connected, self.engine.status)
        return self.engine

    def test_dependencies_confirmed_save_and_reversible_cleanup(self):
        engine = self.start()
        engine.toggle(1, True)
        self.assertEqual(self.memory.read(0x1014, 4), b"\1\0\0\0")
        self.assertEqual(engine.desired, {0, 1})
        self.assertEqual(set(engine.applied), {0, 1})
        with self.assertRaisesRegex(NativeRuntimeError, "dependent"):
            engine.toggle(0, False)
        self.assertFalse(engine.blocked)
        self.assertTrue(engine.close())
        self.assertEqual(self.memory.read(0x1014, 4), b"\0\0\0\0")
        self.assertFalse((self.directory / "session.json").exists())
        self.assertFalse((self.directory / "state.lock").exists())
        self.assertEqual(engine.desired, {0, 1})

    def test_recovery_fence_blocks_constructor_before_state_claim(self):
        fence=self.directory/'recovery.lock'
        fence.write_bytes(b'owned recovery evidence')
        with self.assertRaisesRegex(StateError,'recovery transaction'):
            self.start(False)
        self.assertEqual(fence.read_bytes(),b'owned recovery evidence')
        self.assertFalse((self.directory/'state.lock').exists())

    def test_recovery_fence_claim_race_releases_only_our_state_lock(self):
        from ct2trainer.native.engine import _StateStore
        original=_StateStore._exclusive
        fence=self.directory/'recovery.lock'
        def claimed(path,raw):
            original(path,raw)
            if path.name=='state.lock':fence.write_bytes(b'recovery won')
        with patch.object(_StateStore,'_exclusive',side_effect=claimed):
            with self.assertRaisesRegex(StateError,'recovery transaction'):
                self.start(False)
        self.assertEqual(fence.read_bytes(),b'recovery won')
        self.assertFalse((self.directory/'state.lock').exists())

    def test_recovery_fence_observed_at_runtime_prevents_write_and_retains_session(self):
        engine=self.start()
        lock=engine.store.lock.read_bytes()
        (self.directory/'recovery.lock').write_bytes(b'external recovery fence')
        with self.assertRaisesRegex(NativeRuntimeError,'recovery transaction'):
            engine.set_value(2,'999')
        self.assertFalse(self.memory.writes)
        self.assertTrue(engine.blocked)
        self.assertEqual(engine.store.lock.read_bytes(),lock)
        self.assertTrue(engine.store.session.exists())

    def test_verified_owner_creation_time_is_retained_in_state_and_session(self):
        from ct2trainer.native.recovery import ProcessIdentity
        with patch('ct2trainer.native.recovery.current_process_identity',return_value=ProcessIdentity(314,1592)):
            engine=self.start()
        owner=json.loads(engine.store.lock.read_bytes())
        self.assertEqual((owner['schema'],owner['owner_pid'],owner['owner_created']),(2,314,1592))
        self.assertEqual(json.loads(engine.store.session.read_bytes())['owner'],owner)

    def test_failed_assert_does_not_save_requested_switch(self):
        engine = self.start()
        self.memory.data[20] = 8
        with self.assertRaisesRegex(NativeRuntimeError, "assertion"):
            engine.toggle(1, True)
        self.assertNotIn(1, engine.desired)
        self.assertNotIn(1, engine.applied)
        self.assertFalse(engine.blocked)
        self.assertEqual(self.memory.writes, [])

    def test_partial_write_rolls_back_and_allows_explicit_retry(self):
        engine = self.start()
        self.memory.fail_once = True
        with self.assertRaisesRegex(NativeRuntimeError, "original bytes restored"):
            engine.toggle(1, True)
        self.assertEqual(self.memory.read(0x1014, 4), bytes(4))
        self.assertNotIn(1, engine.desired)
        self.assertFalse(engine.blocked)
        engine.toggle(1, True)
        self.assertIn(1, engine.desired)

    def test_each_patch_is_rechecked_after_the_prior_patch_write(self):
        script = self.plan["entries"][1]
        script["enable"] += [{"op": "assert", "address": "FixtureAnchor+18", "bytes": "00000000"},
                             {"op": "write", "address": "FixtureAnchor+18", "bytes": "01000000"}]
        script["disable"] += [{"op": "assert", "address": "FixtureAnchor+18", "bytes": "01000000"},
                              {"op": "write", "address": "FixtureAnchor+18", "bytes": "00000000"}]
        engine = self.start()
        original_write = self.memory.write

        def racing_write(address, raw):
            original_write(address, raw)
            if address == 0x1014 and raw == b"\1\0\0\0":
                self.memory.data[24] = 9

        with patch.object(self.memory, "write", side_effect=racing_write):
            with self.assertRaisesRegex(NativeRuntimeError, "immediately before write"):
                engine.toggle(1, True)
        self.assertEqual(self.memory.read(0x1014, 4), bytes(4))
        self.assertEqual(self.memory.data[24], 9)
        self.assertFalse(any(address == 0x1018 for address, _ in self.memory.writes))
        self.assertNotIn(1, engine.desired)

    def test_external_patch_change_blocks_disable_and_preserves_journal(self):
        engine = self.start()
        engine.toggle(1, True)
        self.memory.data[20] = 7
        writes = len(self.memory.writes)
        with self.assertRaisesRegex(NativeRuntimeError, "externally"):
            engine.toggle(1, False)
        self.assertTrue(engine.blocked)
        self.assertEqual(len(self.memory.writes), writes)
        self.assertEqual(self.memory.data[20], 7)
        self.assertFalse(engine.close())
        self.assertTrue((self.directory / "session.json").exists())
        self.assertTrue((self.directory / "state.lock").exists())

    def test_same_process_polls_do_not_double_apply_and_pid_reuse_restores(self):
        engine = self.start()
        engine.toggle(1, True)
        writes = len(self.memory.writes)
        for _ in range(5):
            engine.poll()
        self.assertEqual(len(self.memory.writes), writes)
        self.memory.alive = False
        engine.poll()
        self.assertIsNone(engine.memory)
        self.assertEqual(engine.applied, {})
        self.memory = FakeMemory(pid=123, creation_time=999)
        engine.poll()
        self.assertTrue(engine.connected)
        self.assertEqual(self.memory.read(0x1014, 4), b"\1\0\0\0")
        journal = json.loads((self.directory / "session.json").read_bytes())
        self.assertEqual(journal["target_created"], 999)
        self.assertEqual(len(self.memory.writes), 1)

    def test_uncertain_liveness_blocks_without_rebinding(self):
        engine = self.start()
        engine.toggle(1, True)
        self.memory.alive_error = True
        engine.poll()
        self.assertTrue(engine.blocked)
        self.assertTrue((self.directory / "session.json").exists())
        self.assertEqual(len(self.memory.writes), 1)

    def test_handle_close_failure_cannot_escape_boolean_cleanup_api(self):
        engine = self.start()
        engine.toggle(1, True)
        with patch.object(self.memory, "close", side_effect=OSError("Invalid process handle")):
            self.assertFalse(engine.close())
        self.assertTrue(engine.closed)
        self.assertTrue(engine.blocked)
        self.assertIn("handle close also failed", engine.error)
        self.assertTrue((self.directory / "state.lock").exists())

    def test_save_failure_after_confirmed_patch_does_not_claim_saved_wish(self):
        engine = self.start()
        engine.toggle(0, True)
        with patch.object(engine.store, "save", side_effect=OSError("Injected disk failure")):
            with self.assertRaisesRegex(NativeRuntimeError, "disk failure"):
                engine.toggle(1, True)
        self.assertTrue(engine.blocked)
        self.assertNotIn(1, engine.desired)
        self.assertIn(1, engine.applied)
        self.assertFalse(engine.close())
        self.assertTrue((self.directory / "session.json").exists())

    def test_concurrent_instance_cannot_take_or_remove_ownership(self):
        engine = self.start(attach=False)
        owner = (self.directory / "state.lock").read_bytes()
        # A concurrent live owner is an actionable conflict, not a silent takeover.
        alive_probe = lambda identity: ProcessObservation(identity, "alive", identity.created, WAIT_TIMEOUT)
        with self.assertRaises(LiveStateConflict) as ctx:
            TrainerEngine(self.plan, self.directory, self.factory, process_probe=alive_probe)
        self.assertIsInstance(ctx.exception, StateError)
        self.assertEqual((self.directory / "state.lock").read_bytes(), owner)
        self.assertTrue(engine.close())

    def test_corrupted_state_is_quarantined_and_constructor_starts(self):
        # A corrupt state.json no longer dead-ends startup: the exact bytes
        # are quarantined under a .corrupt- stamp and the engine starts fresh.
        (self.directory / "state.json").write_bytes(b"not JSON")
        self.engine = TrainerEngine(self.plan, self.directory, self.factory)
        quarantined = sorted(self.directory.glob("state.json.corrupt-*"))
        self.assertEqual(len(quarantined), 1)
        self.assertEqual(quarantined[0].read_bytes(), b"not JSON")
        self.assertFalse((self.directory / "state.json").exists())
        self.assertEqual(self.engine.desired, set())
        self.assertFalse((self.directory / "session.json").exists())
        self.assertTrue(self.engine.close())
        self.assertFalse((self.directory / "state.lock").exists())

    def test_prior_session_is_preserved_and_blocks_constructor(self):
        (self.directory / "session.json").write_bytes(b"prior crash")
        with self.assertRaisesRegex(StateError, "incomplete session"):
            TrainerEngine(self.plan, self.directory, self.factory)
        self.assertEqual((self.directory / "session.json").read_bytes(), b"prior crash")
        self.assertFalse((self.directory / "state.lock").exists())

    def test_external_state_change_prevents_any_next_write(self):
        engine = self.start()
        (self.directory / "state.json").write_bytes(b"external")
        with self.assertRaisesRegex(NativeRuntimeError, "State bytes changed"):
            engine.toggle(1, True)
        self.assertTrue(engine.blocked)
        self.assertEqual(self.memory.writes, [])
        self.assertFalse(engine.close())

    def test_numeric_write_is_confirmed_but_value_is_not_persisted(self):
        engine = self.start()
        # WP-14 (C1): a staged value refuses value access while its
        # provider is inactive; the enable path activates the provider.
        with self.assertRaisesRegex(NativeRuntimeError,
                                    "requires active provider"):
            engine.set_value(2, "4321")
        self.assertEqual(engine.desired, set())
        self.assertEqual(self.memory.writes, [])
        engine.toggle(0, True)
        with self.assertRaises(NativeRuntimeError):
            engine.set_value(2, "1 + 2")
        self.assertEqual(engine.set_value(2, "4321"), "4321")
        self.assertEqual(engine.read_value(2), "4321")
        self.assertEqual(engine.desired, {0})
        self.assertNotIn(2, json.loads((self.directory / "state.json").read_bytes())["payload"]["desired"])

    def test_freeze_captures_actual_value_only_for_current_session(self):
        engine = self.start()
        engine.toggle(0, True)
        engine.set_freeze(2, True)
        self.assertEqual(self.memory.writes, [])
        self.memory.data[16:20] = struct.pack("<I", 9876)
        engine.poll()
        self.assertEqual(engine.read_value(2), "1234")
        self.assertEqual(engine.desired, {0})
        engine.set_freeze(2, False)
        self.memory.data[16:20] = struct.pack("<I", 9999)
        engine.poll()
        self.assertEqual(engine.read_value(2), "9999")

    def test_offline_cancel_saved_wish_survives_next_instance(self):
        engine = self.start()
        engine.toggle(1, True)
        engine.close()
        self.memory = FakeMemory()
        self.engine = TrainerEngine(self.plan, self.directory, self.factory, self.shared)
        self.engine.clear_desired(1)
        self.engine.poll()
        self.assertNotIn(1, self.engine.applied)
        self.assertEqual(self.engine.desired, {0})

    def test_restore_scan_miss_fails_wishes_without_blocking_engine(self):
        # Field case from the 0.13 debug log: a saved wish whose module AOB
        # pattern no longer exists in the target image (game update).  The
        # scan miss is a ScanMiss, so the restore fails the affected records
        # only; the engine stays usable instead of failing closed.
        from ct2trainer.native.memory import ScanMiss
        engine = self.start()
        engine.toggle(1, True)
        engine.close()
        self.memory = FakeMemory()
        anchor = "435432542D4649582D323032362D3031"
        original_scan = self.memory.scan_module

        def scan_module(name, pattern):
            if pattern.replace(" ", "").upper() == anchor:
                raise ScanMiss(
                    "The module byte pattern was not found in readable committed memory.")
            return original_scan(name, pattern)
        self.memory.scan_module = scan_module
        self.engine = TrainerEngine(self.plan, self.directory, self.factory, self.shared)
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)
        self.assertFalse(self.engine.blocked)
        self.assertEqual(self.engine.applied, {})
        self.assertIn(0, self.engine.entry_errors)
        self.assertIn(1, self.engine.entry_errors)
        self.assertIn("not found", self.engine.entry_errors[0])
        self.assertIn("Restore failed", self.engine.status)
        self.assertEqual(self.engine.desired, {0, 1})
        self.assertTrue(self.engine.close())

    def test_restore_continues_to_later_wishes_after_scan_miss(self):
        # Entry 1 carries its own scan so a stale anchor in wish 0 cannot mask
        # wish 1: per-wish isolation must let the later wish still restore.
        from ct2trainer.native.memory import ScanMiss
        entry = next(e for e in self.plan["entries"] if e["id"] == 1)
        entry["requires"] = []
        entry["dependency_ids"] = []
        entry.pop("staged", None)
        entry["enable"] = [
            {"op": "scan", "symbol": "Anchor2", "module": "FixtureTarget.exe",
             "pattern": "D2 04 00 00"},
            {"op": "assert", "address": "Anchor2+4", "bytes": "00000000"},
            {"op": "write", "address": "Anchor2+4", "bytes": "01000000"},
        ]
        entry["disable"] = [
            {"op": "assert", "address": "Anchor2+4", "bytes": "01000000"},
            {"op": "write", "address": "Anchor2+4", "bytes": "00000000"},
        ]
        engine = self.start()
        engine.toggle(0, True)
        engine.toggle(1, True)
        engine.close()
        self.memory = FakeMemory()
        anchor = "435432542D4649582D323032362D3031"
        original_scan = self.memory.scan_module

        def scan_module(name, pattern):
            if pattern.replace(" ", "").upper() == anchor:
                raise ScanMiss(
                    "The module byte pattern was not found in readable committed memory.")
            return original_scan(name, pattern)
        self.memory.scan_module = scan_module
        self.engine = TrainerEngine(self.plan, self.directory, self.factory, self.shared)
        self.engine.poll()
        self.assertFalse(self.engine.blocked)
        self.assertNotIn(0, self.engine.applied)
        self.assertIn(1, self.engine.applied)
        self.assertIn(0, self.engine.entry_errors)
        self.assertNotIn(1, self.engine.entry_errors)
        self.assertEqual(self.engine.desired, {0, 1})
        self.assertEqual(self.memory.read(0x1014, 4), b"\1\0\0\0")
        self.assertTrue(self.engine.close())
        self.assertEqual(self.memory.read(0x1014, 4), b"\0\0\0\0")

    def test_unselected_record_rejects_direct_actions(self):
        self.plan = compile_table(FIXTURE, "FixtureTarget.exe", selected_ids=[2])
        engine = self.start()
        self.assertFalse(engine.entries[1]["selected"])
        with self.assertRaises(NativeRuntimeError):
            engine.toggle(1, True)
        self.assertEqual(self.memory.writes, [])

    def test_different_trainer_variants_cannot_share_one_live_target(self):
        engine = self.start()
        other_plan = compile_table(FIXTURE, "FixtureTarget.exe", selected_ids=[2])
        self.assertNotEqual(other_plan["trainer_id"], self.plan["trainer_id"])
        other = TrainerEngine(other_plan, self.directory / "variant", self.factory, self.shared)
        winner = next(self.shared.glob("*.json"))
        owner = winner.read_bytes()
        other.poll()
        self.assertTrue(other.blocked)
        self.assertEqual(winner.read_bytes(), owner)
        self.assertEqual(self.memory.writes, [])
        self.assertFalse(other.close())
        self.assertEqual(winner.read_bytes(), owner)
        self.assertTrue(engine.close())
        self.assertFalse(winner.exists())

    def test_value_actions_cannot_overwrite_script_patch_or_other_freeze(self):
        self.plan["entries"][2]["address"] = "FixtureAnchor+14"
        engine = self.start()
        engine.toggle(1, True)
        writes = len(self.memory.writes)
        with self.assertRaisesRegex(NativeRuntimeError, "overlaps an active"):
            engine.set_value(2, "0")
        with self.assertRaisesRegex(NativeRuntimeError, "overlaps an active"):
            engine.set_freeze(2, True)
        self.assertEqual(len(self.memory.writes), writes)
        self.assertFalse(engine.blocked)
        engine.toggle(1, False)
        engine.set_freeze(2, True)
        engine.entries[3]["address"] = "FixtureAnchor+14"
        with self.assertRaisesRegex(NativeRuntimeError, "another frozen"):
            engine.set_value(3, "1")
        with self.assertRaisesRegex(NativeRuntimeError, "overlaps a frozen"):
            engine.toggle(1, True)
        self.assertFalse(engine.blocked)
        self.assertEqual(self.memory.read(0x1014, 4), bytes(4))

    def test_freeze_checks_existing_patch_before_activating_any_dependency(self):
        engine = self.start()
        engine.toggle(1, True)
        self.memory.data[20] = 7
        writes = len(self.memory.writes)
        with self.assertRaisesRegex(NativeRuntimeError, "externally"):
            engine.set_freeze(2, True)
        self.assertTrue(engine.blocked)
        self.assertEqual(len(self.memory.writes), writes)

    def test_invalid_plan_cannot_create_state_directory(self):
        invalid_plans = []
        plan = deepcopy(self.plan)
        plan["entries"][1]["enable"][1]["op"] = "execute"
        invalid_plans.append(plan)
        for key, value in (("pointer_offsets", [0] * 33),
                           ("pointer_offsets", [0x8000000000000000]),
                           ("pointer_offsets", [True]),
                           ("show_as_signed", 1), ("show_as_signed", 0)):
            plan = deepcopy(self.plan)
            plan["entries"][2][key] = value
            invalid_plans.append(plan)
        plan = deepcopy(self.plan)
        plan["schema"] = True
        invalid_plans.append(plan)
        for index, key in ((1, "requires"), (0, "provides")):
            plan = deepcopy(self.plan)
            plan["entries"][index][key] = []
            invalid_plans.append(plan)
        for index, plan in enumerate(invalid_plans):
            absent = self.directory / f"absent-{index}"
            with self.subTest(index=index), self.assertRaises(NativeRuntimeError):
                TrainerEngine(plan, absent, self.factory)
            self.assertFalse(absent.exists())

    def test_plan_missing_selected_dependency_and_cycles_rejected(self):
        plan = deepcopy(self.plan)
        plan["entries"][0]["selected"] = False
        plan['selected_ids'].remove(plan['entries'][0]['id'])
        with self.assertRaisesRegex(NativeRuntimeError, "unavailable symbol|dependency|Trainer identity"):
            validate_plan(plan)
        plan = deepcopy(self.plan)
        plan["entries"][0].update(requires=["OtherAnchor"], provides=["FixtureAnchor"],
                                 enable=[{"op": "define", "symbol": "FixtureAnchor", "expression": "OtherAnchor"},
                                         {"op": "register", "symbol": "FixtureAnchor"}],
                                 disable=[{"op": "unregister", "symbol": "FixtureAnchor"}])
        plan["entries"][1].update(requires=["FixtureAnchor"], provides=["OtherAnchor"],
                                 enable=[{"op": "define", "symbol": "OtherAnchor", "expression": "FixtureAnchor"},
                                         {"op": "register", "symbol": "OtherAnchor"}],
                                 disable=[{"op": "unregister", "symbol": "OtherAnchor"}])
        with self.assertRaisesRegex(NativeRuntimeError, "cycle"):
            validate_plan(plan)

    def test_hash_bound_foreign_table_state_is_quarantined(self):
        # A state file with a valid checksum but a foreign table identity is
        # evidence for another trainer, not this one: it is quarantined
        # byte-for-byte and can no longer dead-end startup.
        engine = self.start()
        engine.toggle(0, True)
        engine.close()
        path = self.directory / "state.json"
        document = json.loads(path.read_bytes())
        document["payload"]["table_sha256"] = "0" * 64
        canonical = json.dumps(document["payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        document["sha256"] = hashlib.sha256(canonical).hexdigest()
        foreign = json.dumps(document).encode("utf-8")
        path.write_bytes(foreign)
        self.engine = TrainerEngine(self.plan, self.directory, self.factory)
        quarantined = sorted(self.directory.glob("state.json.corrupt-*"))
        self.assertEqual(len(quarantined), 1)
        self.assertEqual(quarantined[0].read_bytes(), foreign)
        self.assertFalse(path.exists())
        self.assertEqual(self.engine.desired, set())


class NativeNumericTests(unittest.TestCase):
    def entry(self, kind="4 Bytes", **flags):
        return dict(variable_type=kind, show_as_hex=False, show_as_signed=False,
                    dropdown={"choices": [], "read_only": False}, **flags)

    def test_integer_extremes_signed_and_hex_roundtrip(self):
        for kind, size in (("Byte", 1), ("2 Bytes", 2), ("4 Bytes", 4), ("8 Bytes", 8)):
            entry = self.entry(kind)
            maximum = (1 << size * 8) - 1
            self.assertEqual(format_value(entry, parse_value(entry, str(maximum))), str(maximum))
            with self.assertRaises(NativeRuntimeError):
                parse_value(entry, str(maximum + 1))
            entry["show_as_signed"] = True
            minimum = -(1 << (size * 8 - 1))
            self.assertEqual(format_value(entry, parse_value(entry, str(minimum))), str(minimum))
            entry["show_as_hex"] = True
            self.assertEqual(format_value(entry, parse_value(entry, format(maximum, "X"))), format(maximum, "X"))
            with self.assertRaises(NativeRuntimeError):
                parse_value(entry, "-1")
            with self.assertRaises(NativeRuntimeError):
                parse_value(entry, "1" * 65)

    def test_float_finite_literals_and_overflow(self):
        for kind in ("Float", "Double"):
            entry = self.entry(kind)
            self.assertEqual(format_value(entry, parse_value(entry, "1.5e2")), "150")
            for text in ("NaN", "inf", "1/2", "1;os.execute()", "1e9999"):
                with self.assertRaises(NativeRuntimeError):
                    parse_value(entry, text)
        with self.assertRaises(NativeRuntimeError):
            parse_value(self.entry("Float"), "3.5e38")

    def test_read_only_dropdown_enforces_numeric_choice(self):
        entry = self.entry("Byte")
        entry["dropdown"] = {"choices": [{"value": "1", "description": "Enabled"}], "read_only": True}
        self.assertEqual(parse_value(entry, "1"), b"\1")
        with self.assertRaises(NativeRuntimeError):
            parse_value(entry, "2")


if __name__ == "__main__":
    unittest.main()
