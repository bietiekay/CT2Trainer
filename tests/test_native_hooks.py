"""Owned-hook lifecycle, real decoder, and Win32 allocation safety checks."""
from contextlib import contextmanager
import ctypes
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from ct2trainer.native.hooks import (
    HookError, HookUncertain, HookManager, MAX_HOOK_ALLOCATIONS,
    QuiescenceProof, validate_instruction_boundary,
)
from ct2trainer.native.memory import ProcessMemory, ProcessMemoryError


class _Memory:
    identity = (123, 456)
    pointer_size = 8

    def __init__(self):
        self.alive = True
        self.data = {0x1000: b"\xB8\x01\x00\x00\x00", 0x2000: b"\x90" * 5}
        self.allocations = {}
        self.writes = []
        self.protections = []
        self.allocation_protections = {}
        self.releases = []
        self.before_write = None
        self.failure = None

    def is_alive(self):
        return self.alive

    def read(self, address, size):
        for base, raw in self.data.items():
            if base <= address and address + size <= base + len(raw):
                return raw[address - base:address - base + size]
        raise HookError("unmapped test range")

    def write(self, address, raw):
        if self.before_write:
            self.before_write(address, raw)
        for base, data in self.data.items():
            if base <= address and address + len(raw) <= base + len(data):
                offset = address - base
                changed = raw
                failure, self.failure = self.failure, None
                if failure == "partial":
                    changed = raw[:2] + data[offset + 2:offset + len(raw)]
                self.data[base] = data[:offset] + changed + data[offset + len(raw):]
                self.writes.append((address, raw))
                if failure:
                    raise OSError("injected post-write failure")
                return
        raise HookError("unmapped test write")

    def allocate(self, size, near=None):
        address = 0x10000 + len(self.allocations) * 0x10000
        self.allocations[address] = (size + 4095) // 4096 * 4096
        self.data[address] = bytes(self.allocations[address])
        return address

    def allocation_size(self, address):
        return self.allocations[address]

    def protect_allocation(self, address, executable=True, writable=False):
        self.protections.append((address, executable))
        self.allocation_protections[address] = (0x40 if writable else 0x20) if executable else 0x04

    def _query(self, address):
        for base, size in self.allocations.items():
            if base <= address < base + size:
                return SimpleNamespace(BaseAddress=base, AllocationBase=base, RegionSize=size,
                                       State=0x1000, Protect=self.allocation_protections.get(base, 0x04))
        raise HookError("unmapped test protection range")

    def release(self, address):
        self.releases.append(address)
        del self.data[address]

    def is_executable(self, address, size):
        if address in {0x1000, 0x2000}:
            return True
        return any(base <= address and address + size <= base + length
                   and self.allocation_protections.get(base, 0x04) in {0x20, 0x40}
                   for base, length in self.allocations.items())


class _Coordinator:
    def __init__(self):
        self.held = False
        self.proof_ranges = None
        self.proof_identity = None
        self.release_failure = False
        self.calls = 0

    @contextmanager
    def hold(self, memory, ranges):
        self.calls += 1
        self.held = True
        try:
            yield QuiescenceProof(self.proof_identity or memory.identity,
                                  tuple(ranges if self.proof_ranges is None else self.proof_ranges),
                                  "owned-test-safe-point", lambda: self.held)
        finally:
            self.held = False
            if self.release_failure:
                raise OSError("safe point release failed")


class _LiteralCoordinator(_Coordinator):
    def __init__(self):
        super().__init__()
        self.receipts = []
        self.omit_exclusions = False
        self.before_hold = None

    def hold_entries(self, memory, windows, *, literal_windows=(), exclusion_ranges=()):
        if self.before_hold:
            self.before_hold()
        self.receipts.append((windows, literal_windows, exclusion_ranges))
        ranges = [(address, len(original)) for address, original, _, _ in windows + literal_windows]
        if not self.omit_exclusions:
            ranges += list(exclusion_ranges)
        return self.hold(memory, ranges)


def _block(address, raw, original, allocation=False, executable=True):
    return {"address": address, "bytes": raw.hex(), "original": original.hex(),
            "is_allocation": allocation, "executable": executable,
            "requires_coordinator": not allocation}


class HookTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "hook.json"
        self.memory = _Memory()
        self.coordinator = _Coordinator()
        self.manager = HookManager(self.memory, self.path, self.coordinator, "test-activation")

    def prepare(self, second=False):
        base = self.manager.allocate("newmem", 32, near=0x1000)
        blocks = [_block(base, b"\xB8\x02\x00\x00\x00\xC3", bytes(6), True),
                  _block(0x1000, b"\xE9\xFB\xEF\x00\x00", self.memory.data[0x1000])]
        if second:
            blocks.append(_block(0x2000, b"\xE9\xFB\xDF\x00\x00", self.memory.data[0x2000]))
        self.manager.stage(blocks, {"newmem": base})
        return base, blocks

    def test_replacement_calls_and_interrupts_are_rejected_before_staging_writes(self):
        for replacement in (bytes.fromhex("E800000000"), bytes.fromhex("CC90909090")):
            with self.subTest(replacement=replacement.hex()), self.assertRaisesRegex(HookError, "return-context"):
                self.manager.stage([_block(0x1000, replacement, self.memory.data[0x1000])])
        self.assertEqual(self.memory.writes, [])
        self.assertEqual(self.manager.state, "preparing")

    def test_controller_receipts_cover_exact_original_and_installed_far_jump(self):
        original = b"\x90" * 15
        replacement = bytes.fromhex("FF2500000000") + (0x7FFFE8CCCCCC).to_bytes(8, "little") + b"\x90"
        self.memory.data[0x1000] = original
        windows = []
        class ReceiptCoordinator(_Coordinator):
            def hold_entries(controller, memory, entries):
                windows.append(entries)
                return controller.hold(memory, [(address, len(previous)) for address, previous, _, _ in entries])
        self.manager.coordinator = ReceiptCoordinator()
        self.manager.stage([_block(0x1000, replacement, original)])
        self.manager.publish()
        self.manager.disable()
        self.assertEqual(windows[0], ((0x1000, original, replacement, original),))
        self.assertEqual(windows[1], ((0x1000, original, replacement, replacement),))
        self.assertEqual(self.memory.data[0x1000], original)

    def test_staging_never_changes_entry_and_publication_requires_safe_point(self):
        original = self.memory.data[0x1000]
        base, blocks = self.prepare()
        self.assertEqual(self.memory.data[0x1000], original)
        self.assertEqual(self.memory.protections, [(base, True)])
        self.assertEqual(self.manager.state, "staged")
        def verify(address, raw):
            if address == 0x1000:
                self.assertTrue(self.coordinator.held)
                journal = json.loads(self.path.read_bytes())
                self.assertEqual(journal["state"], "publication-intent")
                self.assertEqual(journal["entries"][0]["original"], original.hex())
        self.memory.before_write = verify
        receipt = self.manager.publish()
        self.assertEqual(receipt["state"], "enabled")
        self.assertEqual(self.memory.read(0x1000, 5).hex(), blocks[1]["bytes"])

    def test_disable_restores_original_and_retains_code_until_exact_target_exit(self):
        original = self.memory.data[0x1000]
        base, _ = self.prepare()
        self.manager.publish()
        self.manager.disable()
        self.assertEqual(self.memory.data[0x1000], original)
        self.assertEqual(self.manager.state, "retired")
        self.assertEqual(self.manager.allocations["newmem"]["state"], "retained")
        self.assertIn(base, self.memory.data)
        self.assertEqual(self.memory.releases, [])
        self.assertTrue(self.path.exists())
        with self.assertRaisesRegex(HookError, "exact target"):
            self.manager.finish_after_exit()
        self.memory.alive = False
        self.manager.finish_after_exit()
        self.assertFalse(self.path.exists())

    def test_uncoordinated_game_hook_is_refused_without_entry_write(self):
        self.prepare()
        self.manager.coordinator = None
        writes = list(self.memory.writes)
        with self.assertRaisesRegex(HookError, "coordinator"):
            self.manager.publish()
        self.assertEqual(self.memory.writes, writes)
        self.assertEqual(self.manager.state, "staged")

    def test_partial_safe_point_or_wrong_pid_cannot_publish(self):
        self.prepare(second=True)
        writes = list(self.memory.writes)
        self.coordinator.proof_ranges = [(0x1000, 5)]
        with self.assertRaisesRegex(HookError, "every changed"):
            self.manager.publish()
        self.coordinator.proof_ranges = None
        self.coordinator.proof_identity = (999, 456)
        with self.assertRaisesRegex(HookError, "safe point"):
            self.manager.publish()
        self.assertEqual(self.memory.writes, writes)

    def test_actual_executable_page_forces_decode_even_when_block_claims_data(self):
        self.memory.data[0x1000] = bytes.fromhex("488B050000")  # truncated seven-byte instruction
        block = _block(0x1000, b"\x90" * 5, self.memory.data[0x1000], executable=False)
        with self.assertRaisesRegex(HookError, "instruction"):
            self.manager.stage([block])
        self.assertEqual(self.memory.writes, [])

    def test_foreign_entry_before_publish_is_never_overwritten(self):
        self.prepare()
        writes = list(self.memory.writes)
        self.memory.data[0x1000] = b"\xCC" * 5
        with self.assertRaisesRegex(HookError, "guard changed"):
            self.manager.publish()
        self.assertEqual(self.memory.writes, writes)
        self.assertEqual(self.manager.state, "staged")

    def test_foreign_entry_before_disable_blocks_and_preserves_journal(self):
        self.prepare()
        self.manager.publish()
        self.memory.data[0x1000] = b"\xCC" * 5
        writes = list(self.memory.writes)
        with self.assertRaisesRegex(HookUncertain, "externally"):
            self.manager.disable()
        self.assertEqual(self.memory.writes, writes)
        self.assertTrue(self.manager.uncertain)
        self.assertTrue(self.path.exists())

    def test_exact_full_write_failure_can_restore_under_same_held_safe_point(self):
        original = self.memory.data[0x1000]
        self.prepare()
        self.memory.failure = "full"
        with self.assertRaisesRegex(HookError, "original entries verified"):
            self.manager.publish()
        self.assertEqual(self.memory.data[0x1000], original)
        self.assertFalse(self.manager.uncertain)
        self.assertEqual(self.manager.state, "retired")
        self.assertEqual(self.memory.releases, [])

    def test_partial_entry_failure_is_sticky_and_cannot_be_retried(self):
        self.prepare()
        self.memory.failure = "partial"
        with self.assertRaisesRegex(HookUncertain, "partial/foreign"):
            self.manager.publish()
        writes = list(self.memory.writes)
        with self.assertRaises(HookUncertain):
            self.manager.publish()
        with self.assertRaises(HookUncertain):
            self.manager.disable()
        self.assertEqual(self.memory.writes, writes)
        self.assertTrue(json.loads(self.path.read_bytes())["uncertain"])

    def test_safe_point_release_failure_after_entry_mutation_keeps_uncertain_receipt(self):
        self.prepare()
        self.coordinator.release_failure = True
        with self.assertRaisesRegex(HookUncertain, "release failed"):
            self.manager.publish()
        self.assertTrue(self.path.exists())
        self.assertTrue(self.manager.uncertain)

    def test_durable_allocation_intent_precedes_remote_mutation(self):
        original = self.memory.allocate
        def allocate(size, near=None):
            journal = json.loads(self.path.read_bytes())
            self.assertEqual(journal["allocations"]["code"]["state"], "allocation-intent")
            self.assertIsNone(journal["allocations"]["code"]["address"])
            return original(size, near)
        self.memory.allocate = allocate
        self.manager.allocate("Code", 32)

    def test_changed_missing_or_preexisting_journal_cannot_admit_writes(self):
        with self.assertRaisesRegex(HookError, "already exists"):
            HookManager(self.memory, self.path)
        self.path.write_text("external replacement", encoding="utf-8")
        with self.assertRaisesRegex(HookUncertain, "changed externally"):
            self.manager.allocate("code", 32)
        self.assertEqual(self.memory.allocations, {})

    def test_duplicate_case_ambiguous_or_over_budget_allocations_are_rejected(self):
        self.manager.allocate("NewMem", 32)
        with self.assertRaisesRegex(HookError, "duplicate"):
            self.manager.allocate("newmem", 32)
        self.manager.allocations.update({"reserved" + str(index): {"budget_size": 65536}
                                         for index in range(MAX_HOOK_ALLOCATIONS)})
        with self.assertRaisesRegex(HookError, "budget"):
            self.manager.allocate("extra", 32)

    def test_linked_ownership_overlap_and_missing_original_guards_are_rejected(self):
        base = self.manager.allocate("code", 32)
        invalid = [
            [_block(base, b"\x90", b"\x00", False)],
            [_block(0x1000, b"\x90" * 5, b"\x00", False)],
            [_block(base, b"\x90" * 4, bytes(4), True),
             _block(base + 2, b"\x90" * 4, bytes(4), True)],
        ]
        for blocks in invalid:
            with self.subTest(blocks=blocks), self.assertRaises(HookError):
                self.manager.stage(blocks)
        self.assertEqual(self.memory.writes, [])

    def test_process_creation_identity_must_match_for_recovery_after_exit(self):
        self.prepare()
        self.manager.publish()
        self.memory.alive = False
        self.memory.identity = (123, 999)
        with self.assertRaisesRegex(HookError, "exact target"):
            self.manager.finish_after_exit()
        self.assertTrue(self.path.exists())

    def test_link_failure_can_abandon_only_never_published_owned_allocations(self):
        base = self.manager.allocate("code", 32)
        self.manager.abandon_unpublished()
        self.assertEqual(self.memory.releases, [base])
        self.assertNotIn(base, self.memory.data)
        self.assertFalse(self.path.exists())
        self.assertEqual(self.manager.state, "abandoned")

    def test_staged_but_unpublished_rx_code_can_be_abandoned_without_entry_write(self):
        original = self.memory.data[0x1000]
        base, _ = self.prepare()
        self.manager.abandon_unpublished()
        self.assertEqual(self.memory.data[0x1000], original)
        self.assertEqual(self.memory.releases, [base])
        self.assertFalse(self.path.exists())

    def test_even_briefly_published_then_restored_allocations_cannot_be_abandoned(self):
        self.prepare()
        self.memory.failure = "full"
        with self.assertRaises(HookError):
            self.manager.publish()
        with self.assertRaisesRegex(HookError, "cannot be abandoned"):
            self.manager.abandon_unpublished()
        self.assertEqual(self.memory.releases, [])
        self.assertTrue(self.path.exists())

    def test_check_entries_detects_foreign_bytes_and_blocks_later_actions(self):
        self.prepare()
        self.manager.publish()
        self.manager.check_entries()
        self.memory.data[0x1000] = b"\xCC" * 5
        with self.assertRaisesRegex(HookUncertain, "changed externally"):
            self.manager.check_entries()
        with self.assertRaises(HookUncertain):
            self.manager.disable()
        self.assertTrue(self.path.exists())

    def test_owned_rw_data_requires_private_controller_provenance_not_serialized_flags(self):
        data = self.memory.allocate(64)
        block = _block(data + 8, b"\x01", b"\x00", executable=False)
        block["requires_coordinator"] = False
        with self.assertRaisesRegex(HookError, "controller-proven"):
            self.manager.stage([block])
        manager = HookManager(self.memory, self.path.with_name("child-data.json"),
                              owned_data_ranges=[(data, 64)])
        manager.stage([block])
        manager.publish()
        self.assertEqual(self.memory.read(data + 8, 1), b"\x01")
        self.assertEqual(self.coordinator.calls, 0)
        manager.disable()
        self.assertEqual(self.memory.read(data + 8, 1), b"\x00")

    def test_claimed_data_range_must_cover_whole_block_and_remain_nonexecutable(self):
        data = self.memory.allocate(64)
        block = _block(data + 8, b"\x01\x02", b"\x00\x00", executable=False)
        block["requires_coordinator"] = False
        manager = HookManager(self.memory, self.path.with_name("partial-data.json"),
                              owned_data_ranges=[(data + 8, 1)])
        with self.assertRaisesRegex(HookError, "controller-proven"):
            manager.stage([block])
        manager = HookManager(self.memory, self.path.with_name("changed-data.json"),
                              owned_data_ranges=[(data, 64)])
        manager.stage([block])
        self.memory.is_executable = lambda address, length: True
        with self.assertRaisesRegex(HookError, "safe point"):
            manager.publish()
        self.assertEqual(self.memory.read(data + 8, 2), bytes(2))

    def _literal_provider(self, name="literal-parent"):
        memory = _Memory()
        parent = HookManager(memory, self.path.with_name(name + ".json"), _Coordinator())
        base = parent.allocate("cave", 32, executable=True, writable=True)
        body = bytes.fromhex("B82A000000C39090") + bytes(4) + b"\x90" * 4
        allocation = _block(base, body, bytes(len(body)), allocation=True)
        allocation["literal_data_ranges"] = [{"address": base + 8, "size": 4, "allocation": "cave"}]
        parent.stage([allocation, _block(0x1000, bytes.fromhex("E9FBEF0000"), memory.data[0x1000])])
        parent.publish()
        return memory, parent, base

    def test_precise_literal_provenance_is_journaled_and_excludes_only_data_holes(self):
        memory, parent, base = self._literal_provider()
        expected = ((base + 8, 4, base, memory.allocation_size(base)),)
        self.assertEqual(parent.data_ranges(), expected)
        receipt = parent.receipt()
        self.assertEqual(receipt["allocations"]["cave"]["literal_data_ranges"],
                         [{"address": base + 8, "size": 4, "allocation": "cave"}])
        memory.write(base + 8, b"\xCC\xE8\x00\xFF")
        parent.check_entries()  # Data deliberately resembles unsafe/incomplete instructions.
        self.assertEqual(parent.data_ranges(), expected)

    def test_child_literal_write_requires_receipts_and_full_cave_ip_exclusion(self):
        memory, parent, base = self._literal_provider()
        coordinator = _LiteralCoordinator()
        child = HookManager(memory, self.path.with_name("literal-child.json"), coordinator,
                            owned_executable_data_ranges=parent.data_ranges())
        flag = _block(base + 8, b"\x01", b"\x00")
        flag.update(literal_data=True, data_semantics=True)
        child.stage([flag])  # Single flag bytes cannot be decoded as instructions.
        self.assertTrue(child.entries[0]["executable"])
        self.assertTrue(child.entries[0]["data_semantics"])
        child.publish()
        self.assertEqual(memory.read(base + 8, 1), b"\x01")
        self.assertEqual(coordinator.receipts[0][0], ())
        self.assertEqual(coordinator.receipts[0][2], ((base, memory.allocation_size(base)),))
        parent.check_entries()
        child.disable()
        self.assertEqual(memory.read(base + 8, 1), b"\x00")
        parent.check_entries()

    def test_serialized_or_partial_literal_claim_never_avoids_instruction_validation(self):
        memory, parent, base = self._literal_provider()
        for name, spans, address, raw in (("missing", (), base + 8, b"\x01"),
                                          ("crossing", parent.data_ranges(), base + 11, b"\x01\x02"),
                                          ("code", parent.data_ranges(), base, b"\xCC")):
            child = HookManager(memory, self.path.with_name(name + ".json"), _LiteralCoordinator(),
                                owned_executable_data_ranges=spans)
            flag = _block(address, raw, memory.read(address, len(raw)))
            flag.update(literal_data=True, data_semantics=True)
            with self.subTest(name=name), self.assertRaises(HookError):
                child.stage([flag])
            self.assertEqual(child.state, "preparing")

    def test_uncoordinated_or_uncovered_executable_literal_proof_cannot_publish(self):
        memory, parent, base = self._literal_provider()
        flag = _block(base + 8, b"\x01", b"\x00")
        flag.update(literal_data=True, data_semantics=True)
        child = HookManager(memory, self.path.with_name("no-literal-coordinator.json"), _Coordinator(),
                            owned_executable_data_ranges=parent.data_ranges())
        child.stage([flag])
        with self.assertRaisesRegex(HookError, "owned data receipts"):
            child.publish()
        coordinator = _LiteralCoordinator()
        coordinator.omit_exclusions = True
        child = HookManager(memory, self.path.with_name("uncovered-literal.json"), coordinator,
                            owned_executable_data_ranges=parent.data_ranges())
        child.stage([flag])
        with self.assertRaisesRegex(HookError, "cover every"):
            child.publish()
        self.assertEqual(memory.read(base + 8, 1), b"\x00")

    def test_immutable_cave_code_and_unwritten_padding_are_sticky_guards(self):
        for name, offset in (("changed-code", 1), ("changed-padding", 0x100)):
            memory, parent, base = self._literal_provider(name)
            memory.write(base + offset, b"\xCC")
            with self.subTest(name=name), self.assertRaisesRegex(HookUncertain, "code or padding"):
                parent.data_ranges()
            self.assertTrue(parent.uncertain)
            self.assertTrue(parent.path.exists())

    def test_changed_protection_or_retired_parent_cannot_mint_literal_permits(self):
        memory, parent, base = self._literal_provider("changed-protection")
        memory.allocation_protections[base] = 0x20
        with self.assertRaisesRegex(HookUncertain, "protection changed"):
            parent.data_ranges()
        memory, parent, base = self._literal_provider("retired-literal")
        parent.disable()
        with self.assertRaisesRegex(HookError, "confirmed enabled"):
            parent.data_ranges()

    def test_linked_literal_spans_require_exact_allocation_and_block_bounds(self):
        base = self.manager.allocate("cave", 32, writable=True)
        for span in ({"address": base - 1, "size": 1, "allocation": "cave"},
                     {"address": base + 4, "size": 2, "allocation": "cave"},
                     {"address": base, "size": 1, "allocation": "other"}):
            block = _block(base, bytes.fromhex("B802000000"), bytes(5), allocation=True)
            block["literal_data_ranges"] = [span]
            with self.subTest(span=span), self.assertRaises(HookError):
                self.manager.stage([block])
        self.assertEqual(self.memory.writes, [])

    def test_serialized_literal_bounds_cannot_reconstruct_a_live_permit(self):
        memory, parent, base = self._literal_provider()
        bounds = json.loads(json.dumps(parent.data_ranges()))
        self.assertEqual(bounds, [[base + 8, 4, base, memory.allocation_size(base)]])
        with self.assertRaisesRegex(HookError, "live issuer permit"):
            HookManager(memory, self.path.with_name("serialized-permit.json"), _LiteralCoordinator(),
                        owned_executable_data_ranges=bounds)

    def test_cached_literal_permit_revalidates_code_padding_and_journal_while_held(self):
        for name, corrupt in (("code-after-mint", lambda memory, parent, base: memory.write(base + 1, b"\xCC")),
                              ("padding-after-mint", lambda memory, parent, base: memory.write(base + 0x100, b"\xCC")),
                              ("journal-after-mint", lambda memory, parent, base: parent.path.write_text("foreign"))):
            memory, parent, base = self._literal_provider(name)
            coordinator = _LiteralCoordinator()
            child = HookManager(memory, self.path.with_name(name + "-child.json"), coordinator,
                                owned_executable_data_ranges=parent.data_ranges())
            flag = _block(base + 8, b"\x01", b"\x00")
            flag.update(literal_data=True, data_semantics=True)
            child.stage([flag])
            coordinator.before_hold = lambda: corrupt(memory, parent, base)
            with self.subTest(name=name), self.assertRaises(HookUncertain):
                child.publish()
            self.assertEqual(memory.read(base + 8, 1), b"\x00")

    def test_retirement_revokes_cached_permit_and_unpublished_child_can_be_abandoned(self):
        memory, parent, base = self._literal_provider()
        child = HookManager(memory, self.path.with_name("revoked-child.json"), _LiteralCoordinator(),
                            owned_executable_data_ranges=parent.data_ranges())
        flag = _block(base + 8, b"\x01", b"\x00")
        flag.update(literal_data=True, data_semantics=True)
        child.stage([flag])
        parent.disable()
        with self.assertRaisesRegex(HookError, "confirmed enabled"):
            child.publish()
        self.assertEqual(memory.read(base + 8, 1), b"\x00")
        child.abandon_unpublished()
        self.assertFalse(child.path.exists())

    def test_literal_issuer_cycle_is_bounded_and_cannot_admit_a_write(self):
        memory, parent, base = self._literal_provider()
        permit = parent.data_ranges()[0]
        child = HookManager(memory, self.path.with_name("cyclic-literal.json"), _LiteralCoordinator(),
                            owned_executable_data_ranges=(permit,))
        flag = _block(base + 8, b"\x01", b"\x00")
        flag.update(literal_data=True, data_semantics=True)
        child.stage([flag])
        permit._issuer = child  # Simulate an internal ownership-graph bug.
        with self.assertRaisesRegex(HookUncertain, "cycle or depth"):
            child.publish()
        self.assertTrue(child.uncertain)

    def test_data_commit_keeps_numeric_value_and_durable_terminal_receipt(self):
        memory, parent, base = self._literal_provider()
        child = HookManager(memory, self.path.with_name("numeric-commit.json"), _LiteralCoordinator(),
                            owned_executable_data_ranges=parent.data_ranges())
        flag = _block(base + 8, b"\x07", b"\x00")
        flag.update(literal_data=True, data_semantics=True)
        child.stage([flag])
        child.publish()
        self.assertTrue(child.depends_on_provider(parent))
        before = list(memory.writes)
        child.commit_data_only()
        self.assertEqual(memory.writes, before)
        self.assertEqual(memory.read(base + 8, 1), b"\x07")
        self.assertEqual(child.state, "abandoned")
        self.assertFalse(child.depends_on_provider(parent))
        self.assertTrue(child.receipt()["data_commit"])
        self.assertEqual(child.receipt()["entries"][0]["state"], "committed")
        parent.disable()
        self.assertTrue(child.receipt()["data_commit"])
        self.assertEqual(memory.read(base + 8, 1), b"\x07")
        with self.assertRaisesRegex(HookError, "confirmed enabled"):
            child.disable()
        child.path.write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(HookUncertain, "journal changed"):
            child.receipt()

    def test_data_commit_rejects_code_allocations_and_ordinary_rw_transactions(self):
        self.prepare()
        self.manager.publish()
        with self.assertRaisesRegex(HookError, "proven literal transaction"):
            self.manager.commit_data_only()
        memory = _Memory()
        data = memory.allocate(32)
        ordinary = HookManager(memory, self.path.with_name("ordinary-commit.json"),
                               owned_data_ranges=[(data, 32)])
        flag = _block(data + 8, b"\x01", b"\x00", executable=False)
        flag["requires_coordinator"] = False
        ordinary.stage([flag])
        ordinary.publish()
        with self.assertRaisesRegex(HookError, "proven literal transaction"):
            ordinary.commit_data_only()
        self.assertEqual(ordinary.state, "enabled")

    def test_data_commit_rejects_mixed_code_literal_entries_and_foreign_values(self):
        memory, parent, base = self._literal_provider()
        flag = _block(base + 8, b"\x01", b"\x00")
        flag.update(literal_data=True, data_semantics=True)
        mixed = HookManager(memory, self.path.with_name("mixed-commit.json"), _LiteralCoordinator(),
                            owned_executable_data_ranges=parent.data_ranges())
        mixed.stage([flag, _block(0x2000, bytes.fromhex("E9FBEF0000"), memory.data[0x2000])])
        mixed.publish()
        with self.assertRaisesRegex(HookError, "proven literal transaction"):
            mixed.commit_data_only()
        mixed.disable()
        numeric = HookManager(memory, self.path.with_name("foreign-numeric.json"), _LiteralCoordinator(),
                              owned_executable_data_ranges=parent.data_ranges())
        numeric.stage([flag])
        numeric.publish()
        memory.write(base + 8, b"\x02")
        with self.assertRaises(HookError):
            numeric.commit_data_only()
        self.assertFalse(numeric.data_commit)
        self.assertEqual(memory.read(base + 8, 1), b"\x02")

    def test_second_allocation_page_protection_must_remain_exact(self):
        memory = _Memory()
        parent = HookManager(memory, self.path.with_name("multipage-parent.json"), _Coordinator())
        base = parent.allocate("cave", 8192, writable=True)
        block = _block(base, bytes.fromhex("C3909090") + bytes(4), bytes(8), allocation=True)
        block["literal_data_ranges"] = [{"address": base + 4, "size": 4, "allocation": "cave"}]
        parent.stage([block])
        parent.publish()
        self.assertEqual(parent.data_ranges()[0][3], 8192)
        def changed_query(address):
            page = base if address < base + 4096 else base + 4096
            return SimpleNamespace(BaseAddress=page, AllocationBase=base, RegionSize=4096,
                                   State=0x1000, Protect=0x40 if page == base else 0x20)
        memory._query = changed_query
        with self.assertRaisesRegex(HookUncertain, "protection changed"):
            parent.data_ranges()

    def test_private_staged_code_change_blocks_entry_publication(self):
        base, _ = self.prepare()
        self.memory.write(base + 1, b"\xCC")
        original = self.memory.read(0x1000, 5)
        with self.assertRaisesRegex(HookUncertain, "code or padding"):
            self.manager.publish()
        self.assertEqual(self.memory.read(0x1000, 5), original)
        self.assertEqual(self.manager.state, "uncertain")

    def test_unused_provider_candidates_do_not_create_hidden_dependencies(self):
        memory, parent, base = self._literal_provider()
        unrelated = HookManager(memory, self.path.with_name("unrelated-code.json"), _LiteralCoordinator(),
                                owned_executable_data_ranges=parent.data_ranges())
        unrelated.stage([_block(0x2000, b"\x90" * 5, memory.data[0x2000])])
        unrelated.publish()
        self.assertEqual(unrelated.owned_executable_data_ranges, ())
        self.assertFalse(unrelated.depends_on_provider(parent))
        parent.disable()
        unrelated.check_entries()
        unrelated.disable()

    def test_numeric_commit_release_failure_or_expired_final_proof_keeps_uncertainty(self):
        for name in ("commit-release-failed", "commit-proof-expired"):
            memory, parent, base = self._literal_provider(name)
            coordinator = _LiteralCoordinator()
            numeric = HookManager(memory, self.path.with_name(name + "-numeric.json"), coordinator,
                                  owned_executable_data_ranges=parent.data_ranges())
            flag = _block(base + 8, b"\x07", b"\x00")
            flag.update(literal_data=True, data_semantics=True)
            numeric.stage([flag])
            numeric.publish()
            before = list(memory.writes)
            if name == "commit-release-failed":
                coordinator.release_failure = True
            else:
                save = numeric._save
                def expire_on_terminal_save():
                    save()
                    if numeric.state == "abandoned":
                        coordinator.held = False
                numeric._save = expire_on_terminal_save
            with self.subTest(name=name), self.assertRaises(HookUncertain):
                numeric.commit_data_only()
            self.assertEqual(memory.writes, before)
            self.assertEqual(memory.read(base + 8, 1), b"\x07")
            journal = json.loads(numeric.path.read_bytes())
            self.assertEqual(journal["state"], "uncertain")
            self.assertTrue(journal["data_commit"])
            self.assertTrue(numeric.uncertain)

    def test_numeric_commit_cannot_discard_exported_symbol_ownership(self):
        memory, parent, base = self._literal_provider()
        numeric = HookManager(memory, self.path.with_name("exported-numeric.json"), _LiteralCoordinator(),
                              owned_executable_data_ranges=parent.data_ranges())
        flag = _block(base + 8, b"\x01", b"\x00")
        flag.update(literal_data=True, data_semantics=True)
        numeric.stage([flag], {"childFlag": base + 8})
        numeric.publish()
        with self.assertRaisesRegex(HookError, "proven literal transaction"):
            numeric.commit_data_only()
        self.assertEqual(numeric.state, "enabled")


class DecoderTests(unittest.TestCase):
    def test_real_mit_decoder_accepts_full_sequences_and_rejects_partial_tail(self):
        validate_instruction_boundary(0x1000, bytes.fromhex("488B050000000090"), 64)
        validate_instruction_boundary(0x1000, bytes.fromhex("558BEC"), 32)
        for raw in (bytes.fromhex("488B050000"), bytes.fromhex("0F")):
            with self.subTest(raw=raw), self.assertRaises(HookError):
                validate_instruction_boundary(0x1000, raw, 64)


class EntryPrefixPatchTests(unittest.TestCase):
    """Byte-patch prefixes that cut the first original instruction.

    Classic field case (TheGreatCircle stealth/reload tables): ``db 90 E9``
    over a 6-byte conditional jump turns it into ``nop; jmp`` reusing the
    original displacement. Validation must prove that against the live
    target bytes, and keep failing closed on every other shape.
    """

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "hook.json"
        self.memory = _Memory()
        self.coordinator = _Coordinator()
        self.manager = HookManager(self.memory, self.path, self.coordinator,
                                  "prefix-patch-test")

    def _stage(self, code, replacement, address=0x1000, prefix_cut=True):
        # prefix_cut mirrors what link_program sets after its live
        # link-time verification; these tests exercise the stage-time
        # re-verification in _normalize.
        self.memory.data[address] = code
        original = bytes(code[:len(replacement)])
        block = _block(address, replacement, original, executable=True)
        if prefix_cut:
            block["prefix_cut"] = True
        self.manager.stage([block])
        return address

    def test_two_byte_cut_reusing_original_displacement_is_accepted(self):
        # jae rel32 (6 bytes) at the entry; db 90 E9 -> nop; jmp rel32.
        self._stage(bytes.fromhex("0F87DEAD0000") + bytes(64),
                    bytes.fromhex("90E9"))
        self.assertEqual(self.manager.state, "staged")

    def test_one_byte_cut_of_two_byte_jump_is_accepted(self):
        # jnz rel8 (2 bytes) at the entry; db EB -> jmp rel8.
        self._stage(bytes.fromhex("7505") + bytes(64),
                    bytes.fromhex("EB"))
        self.assertEqual(self.manager.state, "staged")

    def test_cut_across_two_instructions_is_accepted_when_post_stream_is_valid(self):
        # jnz rel8 (2) + add [rax],al (2); a 3-byte cut must end on the
        # second original instruction boundary with a valid post stream.
        self._stage(bytes.fromhex("75050000") + bytes(64),
                    bytes.fromhex("909000"))
        self.assertEqual(self.manager.state, "staged")

    def test_unflagged_prefix_cut_keeps_the_strict_contract(self):
        # Without the linker's live proof (no prefix_cut flag) the historical
        # strict rejection stands: incomplete original bytes are refused.
        with self.assertRaisesRegex(HookError, "cuts or contains"):
            self._stage(bytes.fromhex("0F87DEAD0000") + bytes(64),
                        bytes.fromhex("90E9"), prefix_cut=False)

    def test_complete_instruction_replacement_is_still_accepted(self):
        # inc eax (2 bytes) replaced by a 2-byte nop; strict path unchanged.
        self._stage(bytes.fromhex("FFC890") + bytes(64),
                    bytes.fromhex("6690"))
        self.assertEqual(self.manager.state, "staged")

    def test_cut_leaving_an_invalid_entry_stream_is_rejected(self):
        # mov [rip+0], imm32 (10 bytes); a 2-byte cut leaves the tail
        # undecodable as a complete instruction at the old boundary.
        code = bytes.fromhex("C70500000000DEADBE") + bytes(64)
        with self.assertRaisesRegex(HookError, "invalid instruction"):
            self._stage(code, bytes.fromhex("90C3"))

    def test_cut_reusing_a_call_displacement_is_rejected_by_flow_check(self):
        # nop + call rel32 (6 bytes); a 3-byte cut that re-encodes the
        # displacement into a call at the entry.
        code = bytes.fromhex("90E805020190") + bytes(64)
        with self.assertRaisesRegex(HookError, "return-context"):
            self._stage(code, bytes.fromhex("E80502"))

    def test_byte_drift_before_validation_is_rejected(self):
        code = bytes.fromhex("0F87DEAD0000") + bytes(64)
        address = 0x1000
        self.memory.data[address] = code
        block = _block(address, bytes.fromhex("90E9"), bytes.fromhex("0F84"),
                       executable=True)
        block["prefix_cut"] = True
        with self.assertRaisesRegex(HookError, "changed before validation"):
            self.manager.stage([block])

    def test_unreadable_tail_fails_closed(self):
        # Region ends inside the first original instruction; the tail cannot
        # be read back, so the cut cannot be proven.
        code = bytes.fromhex("488B050000")
        address = 0x1000
        self.memory.data[address] = code
        block = _block(address, bytes(len(code)), code, executable=True)
        block["prefix_cut"] = True
        with self.assertRaisesRegex(HookError, "instruction"):
            self.manager.stage([block])

    def test_linker_extended_receipt_publishes_through_strict_window_check(self):
        # Field regression (0.15-ext2 Great Circle log): Stealth and No
        # Reload toggles failed in the debug coordinator's
        # _check_overwrite_windows because the 2-byte receipt fragment
        # (0F 87 / 90 E9) is not a complete instruction sequence. The linker
        # now extends the receipt to the full original instruction; publish
        # through a coordinator running the real strict window check must
        # succeed and write the extended replacement.
        from ct2trainer.native.debug_coordinator import _check_overwrite_windows

        class _StrictCoordinator(_Coordinator):
            def hold_entries(self, memory, windows, *, literal_windows=(),
                             exclusion_ranges=()):
                ranges = [(address, len(original))
                          for address, original, _, _ in windows]
                _check_overwrite_windows(memory, ranges, tuple(windows))
                return self.hold(memory, ranges)

        address = 0x1000
        self.memory.data[address] = bytes.fromhex("0F8783000000") + bytes(64)
        block = _block(address, bytes.fromhex("90E983000000"),
                       bytes.fromhex("0F8783000000"), executable=True)
        block["prefix_cut"] = True
        strict_path = Path(self.temporary.name) / "strict-window-hook.json"
        manager = HookManager(self.memory, strict_path, _StrictCoordinator(),
                              "prefix-patch-strict-window")
        manager.stage([block])
        manager.publish()
        self.assertEqual(manager.state, "enabled")
        written = dict(self.memory.writes)
        self.assertEqual(written[address], bytes.fromhex("90E983000000"))


@unittest.skipUnless(sys.platform == "win32", "real owned Win32 allocation gate")
class OwnedWin32AllocationTests(unittest.TestCase):
    def test_current_process_allocation_staging_rx_retirement_and_owned_release(self):
        # Only our own process. No hook or executable function is run here.
        memory = ProcessMemory(Path(sys.executable).name, pid=os.getpid())
        self.addCleanup(memory.close)
        anchor_buffer = ctypes.create_string_buffer(1)
        anchor = ctypes.addressof(anchor_buffer)
        address = memory.allocate(64, near=anchor)
        self.addCleanup(lambda: memory.release(address))
        self.assertLessEqual(abs(address - anchor), 0x7FFF0000)
        self.assertEqual(memory.read(address, 64), bytes(64))
        code = bytes.fromhex("B82A000000C3")
        memory.write(address, code)
        memory.protect_allocation(address, executable=True)
        self.assertEqual(memory.read(address, len(code)), code)
        self.assertTrue(memory.is_executable(address, len(code)))
        with self.assertRaisesRegex(ProcessMemoryError, "not owned"):
            memory.release(address + 1)
        with self.assertRaisesRegex(ProcessMemoryError, "intact owned RW"):
            memory.protect_allocation(address)


if __name__ == "__main__":
    unittest.main()
