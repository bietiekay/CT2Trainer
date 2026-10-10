"""Focused tests for the AA rest-directives plan-operation contracts.

Covers the five capacity contracts of ``ct2trainer.native.aa_directives``:
createThread/threadWait (thread lifecycle + strict rejections),
protect/unprotect (page constants, alignment, bounds, overlap, idempotency,
unprotect-warning), getprocaddress/getmodulehandle (read-only pe_exports
reuse, missing-export context), disassemble (DI port contract, gapless /
ordered / size / count validation, stub roundtrip) and the
missing/empty ENABLE-DISABLE section edge cases pinned against the actual
fail-closed behavior of ``aa_program.prepare_program`` /
``aa.compile_script`` (contrarian negative model; no behavior change).
"""
import json
import tempfile
from pathlib import Path
import unittest

from ct2trainer.native.aa import AAError, compile_script
from ct2trainer.native.aa_directives import (
    ADDRESS_LIMIT_32,
    ADDRESS_LIMIT_64,
    AADirectivesError,
    CASE_COMPLETE,
    CASE_DISABLE_WITHOUT_ENABLE,
    CASE_DUPLICATE_OR_OUT_OF_ORDER,
    CASE_EMPTY_ENABLE,
    CASE_EMPTY_DISABLE,
    CASE_EOF_AFTER_ENABLE,
    CASE_MISSING_DISABLE,
    CASE_NO_MARKERS,
    DisassembleDirectiveModel,
    DisassemblerError,
    DirectivesPlan,
    GRAMMAR_FULL,
    GRAMMAR_SMALL,
    MAX_DISASSEMBLE_COUNT,
    PAGE_EXECUTE_READ,
    PAGE_EXECUTE_READWRITE,
    PAGE_READONLY,
    PAGE_READWRITE,
    ProtectionDirectiveModel,
    ProtectionError,
    SCHEMA,
    SUPPORTED_PAGES,
    SectionAnalysis,
    SectionStructureError,
    TargetApiDirectiveModel,
    TargetApiError,
    ThreadDirectiveModel,
    ThreadError,
    ThreadHandle,
    ThreadPoll,
    ThreadBackend,
    THREAD_CREATED,
    THREAD_EXITED,
    THREAD_RUNNING,
    analyze_sections,
    check_sections,
)
from ct2trainer.native.aa_program import ProgramError, prepare_program
from ct2trainer.native.compiler import compile_table

try:
    from aa_directives_fixture_data import (
        DriftingExportBackend,
        HeldExportBackend,
        ScriptedProtectionBackend,
        ScriptedThreadBackend,
        SECTION_SOURCES,
        StubDisassembler,
        fixture_images,
    )
except ModuleNotFoundError:  # invoked as tests.test_native_aa_directives
    from tests.aa_directives_fixture_data import (
        DriftingExportBackend,
        HeldExportBackend,
        ScriptedProtectionBackend,
        ScriptedThreadBackend,
        SECTION_SOURCES,
        StubDisassembler,
        fixture_images,
    )


class ThreadDirectiveTests(unittest.TestCase):
    def _model(self, **backend_kwargs):
        backend = ScriptedThreadBackend(**backend_kwargs)
        model = ThreadDirectiveModel(backend)
        return model, backend

    def test_create_thread_lifecycle_and_plan_operation(self):
        model, backend = self._model()
        handle = model.create_thread(0x140001000)
        self.assertEqual(handle, ThreadHandle(ordinal=1, entry_address=0x140001000))
        self.assertEqual(model.transitions,
                         [(THREAD_CREATED, 1), (THREAD_RUNNING, 1)])
        self.assertEqual(backend.calls, [("spawn", 1)])
        wait = model.thread_wait(1)
        self.assertEqual(wait, {"op": "thread_wait", "thread": 1,
                                "address": 0x140001000, "exited": True,
                                "exit_code": 0, "polls": 1})
        self.assertEqual(model.transitions,
                         [(THREAD_CREATED, 1), (THREAD_RUNNING, 1),
                          (THREAD_EXITED, 1)])
        self.assertEqual(model.state(1), THREAD_EXITED)
        self.assertEqual(model.operations[-1], wait)

    def test_thread_wait_blocks_until_deterministic_exit_event(self):
        model, backend = self._model(pending_polls=3, exit_code=7)
        model.create_thread(0x1000)
        wait = model.thread_wait(1)
        self.assertEqual(wait["polls"], 4)
        self.assertEqual(wait["exit_code"], 7)
        self.assertEqual(model.blocked_polls, 3)
        self.assertEqual([call for call in backend.calls if call[0] == "poll"],
                         [("poll", 1)] * 4)
        self.assertEqual(model.state(1), "exited")

    def test_sequential_thread_identity_and_wait_order(self):
        model, backend = self._model()
        handles = [model.create_thread(0x1000 + index * 0x10) for index in range(3)]
        self.assertEqual([handle.ordinal for handle in handles], [1, 2, 3])
        self.assertEqual(model.threads(), tuple(handles))
        model.thread_wait(2)
        model.thread_wait(1)
        self.assertEqual([op["thread"] for op in model.operations
                           if op["op"] == "thread_wait"], [2, 1])
        # Strictly sequential backend flow: spawn1, spawn2, spawn3, polls.
        self.assertEqual(backend.calls,
                         [("spawn", 1), ("spawn", 2), ("spawn", 3),
                          ("poll", 2), ("poll", 1)])

    def test_create_thread_rejects_unresolvable_addresses(self):
        model, backend = self._model()
        for address in (None, "0x1000", 0, -1, 1.0, True,
                        ADDRESS_LIMIT_64 + 1):
            with self.subTest(address=address), self.assertRaises(ThreadError):
                model.create_thread(address)
        self.assertFalse(backend.calls)
        self.assertFalse(model.threads())
        self.assertFalse(model.operations)
        # The ordinal space stays clean after a rejection.
        self.assertEqual(model.create_thread(0x1000).ordinal, 1)

    def test_64_bit_plan_accepts_addresses_above_32_bit_range(self):
        model, _ = self._model()
        self.assertEqual(model.create_thread(ADDRESS_LIMIT_32 + 0x1000).ordinal, 1)

    def test_32_bit_plan_rejects_addresses_above_its_width(self):
        backend = ScriptedThreadBackend()
        model = ThreadDirectiveModel(backend, bitness=32)
        with self.assertRaisesRegex(ThreadError, "resolved bounded"):
            model.create_thread(ADDRESS_LIMIT_32 + 1)
        self.assertFalse(backend.calls)

    def test_thread_wait_unknown_identity_rejected(self):
        model, _ = self._model()
        model.create_thread(0x1000)
        for ordinal in (0, 2, 99, "1", None,
                        ThreadHandle(ordinal=5, entry_address=0x1000)):
            with self.subTest(ordinal=ordinal), self.assertRaises(ThreadError):
                model.thread_wait(ordinal)
        self.assertEqual(model.state(1), "running")

    def test_spawn_refusal_rolls_back_identity_and_state(self):
        model, backend = self._model(spawn_refusals={2})
        model.create_thread(0x1000)
        with self.assertRaisesRegex(ThreadError, "refused"):
            model.create_thread(0x2000)
        self.assertEqual([handle.ordinal for handle in model.threads()], [1])
        self.assertEqual(model.transitions, [(THREAD_CREATED, 1), (THREAD_RUNNING, 1)])
        self.assertFalse(model.warnings)
        handle = model.create_thread(0x3000)
        self.assertEqual(handle.ordinal, 2)

    def test_double_thread_wait_rejected(self):
        model, _ = self._model()
        model.create_thread(0x1000)
        model.thread_wait(1)
        with self.assertRaisesRegex(ThreadError, "once per plan thread"):
            model.thread_wait(1)
        self.assertEqual([op["op"] for op in model.operations],
                         ["create_thread", "thread_wait"])

    def test_wait_poll_bound_enforced_without_state_change(self):
        backend = ScriptedThreadBackend(pending_polls=2)
        model = ThreadDirectiveModel(backend, max_wait_polls=2)
        model.create_thread(0x1000)
        with self.assertRaisesRegex(ThreadError, "poll bound"):
            model.thread_wait(1)
        self.assertEqual(model.state(1), "running")
        self.assertEqual(model.blocked_polls, 2)
        # The plan thread can still be waited on afterwards; the backend had
        # already reached its deterministic exit event.
        operation = model.thread_wait(1)
        self.assertEqual(operation["polls"], 1)
        self.assertEqual(model.state(1), "exited")

    def test_invalid_exit_code_rejected(self):

        class BadExitCode(ThreadBackend):
            def spawn(self, handle):
                pass

            def poll(self, handle):
                return ThreadPoll(exited=True, exit_code=0x100000000)

        model = ThreadDirectiveModel(BadExitCode())
        model.create_thread(0x1000)
        with self.assertRaisesRegex(ThreadError, "exit code"):
            model.thread_wait(1)
        self.assertEqual(model.state(1), "running")

    def test_thread_count_bound(self):
        backend = ScriptedThreadBackend()
        model = ThreadDirectiveModel(backend, max_threads=2)
        model.create_thread(0x1000)
        model.create_thread(0x2000)
        with self.assertRaisesRegex(ThreadError, "count bound"):
            model.create_thread(0x3000)
        self.assertEqual(len(model.threads()), 2)

    def test_backend_contract_checked_in_constructor(self):
        with self.assertRaisesRegex(AADirectivesError, "thread backend"):
            ThreadDirectiveModel(object())
        with self.assertRaisesRegex(AADirectivesError, "32/64"):
            ThreadDirectiveModel(ScriptedThreadBackend(), bitness=16)

    def test_report_is_json_safe(self):
        model, _ = self._model(pending_polls=1)
        model.create_thread(0x1000)
        model.thread_wait(1)
        document = model.report()
        self.assertEqual(document["schema"], SCHEMA)
        self.assertEqual([op["op"] for op in document["operations"]],
                         ["create_thread", "thread_wait"])
        self.assertEqual(json.dumps(document, sort_keys=True)[:1], "{")


class ProtectionDirectiveTests(unittest.TestCase):
    def _model(self, foreign=(), **backend_kwargs):
        backend = ScriptedProtectionBackend(foreign, **backend_kwargs)
        model = ProtectionDirectiveModel(backend)
        return model, backend

    def test_protect_applies_and_registers_region(self):
        model, backend = self._model()
        operation = model.protect(0x1000, 0x1000, PAGE_READWRITE)
        self.assertEqual(operation, {"op": "protect", "address": 0x1000,
                                     "size": 0x1000, "page": PAGE_READWRITE})
        self.assertEqual(backend.applies, [(0x1000, 0x1000, PAGE_READWRITE)])
        self.assertEqual(model.owned_regions, ((0x1000, 0x1000, PAGE_READWRITE),))

    def test_page_constants_are_checked_values(self):
        model, backend = self._model()
        for page in sorted(SUPPORTED_PAGES):
            with self.subTest(page=hex(page)):
                model.protect(0x1000, 0x1000, page)
                model.unprotect(0x1000, 0x1000, page)
        for page in (0x00, 0x01, 0x08, 0x10, 0x80, 0x200, -4, "4", None, True):
            with self.subTest(page=page), self.assertRaises(ProtectionError):
                model.protect(0x2000, 0x1000, page)
        self.assertEqual(len(backend.applies), 4)

    def test_alignment_and_page_multiple_validation(self):
        model, backend = self._model()
        for address, size in ((0x1010, 0x1000), (0x1000, 0x1004),
                              (0x1000, 0), (0x1000, -0x1000)):
            with self.subTest(address=hex(address), size=size), \
                    self.assertRaises(ProtectionError):
                model.protect(address, size, PAGE_READWRITE)
        self.assertFalse(backend.applies)

    def test_bounds_and_overflow_rejected_without_backend_calls(self):
        model, backend = self._model()
        for address, size in ((0, 0x1000), (-0x1000, 0x1000),
                              (ADDRESS_LIMIT_64, 0x1000),
                              (ADDRESS_LIMIT_64 - 0xFFF, 0x2000),
                              (0x1000, 16 * 0x100000 + 0x1000)):
            with self.subTest(address=hex(address), size=size), \
                    self.assertRaises(ProtectionError):
                model.protect(address, size, PAGE_READWRITE)
        self.assertFalse(backend.applies)
        self.assertEqual(model.owned_regions, ())

    def test_foreign_overlap_rejected_with_owner_context(self):
        model, backend = self._model(
            foreign=[(0x1000, 0x2000, "hooks")])
        for address in (0x1000, 0x2000):
            with self.subTest(address=hex(address)), \
                    self.assertRaises(ProtectionError) as context:
                model.protect(address, 0x1000, PAGE_EXECUTE_READWRITE)
            self.assertEqual(context.exception.owner, "hooks")
            self.assertIn("foreign region", str(context.exception))
        self.assertEqual(len(backend.applies), 0)
        # Adjacent to the foreign region is not an overlap.
        model.protect(0x3000, 0x1000, PAGE_EXECUTE_READWRITE)
        self.assertEqual(backend.applies,
                         [(0x3000, 0x1000, PAGE_EXECUTE_READWRITE)])

    def test_overlapping_own_region_rejected(self):
        model, _ = self._model()
        model.protect(0x1000, 0x4000, PAGE_READONLY)
        with self.assertRaisesRegex(ProtectionError, "overlaps an active plan"):
            model.protect(0x2000, 0x1000, PAGE_READONLY)
        # Adjacent own regions remain independent.
        model.protect(0x5000, 0x1000, PAGE_READWRITE)
        self.assertEqual(model.owned_regions,
                         ((0x1000, 0x4000, PAGE_READONLY),
                          (0x5000, 0x1000, PAGE_READWRITE)))

    def test_idempotent_identical_protect_applies_backend_once(self):
        model, backend = self._model()
        first = model.protect(0x1000, 0x2000, PAGE_EXECUTE_READWRITE)
        second = model.protect(0x1000, 0x2000, PAGE_EXECUTE_READWRITE)
        self.assertEqual(backend.applies,
                         [(0x1000, 0x2000, PAGE_EXECUTE_READWRITE)])
        self.assertNotIn("idempotent", first)
        self.assertTrue(second["idempotent"])
        with self.assertRaisesRegex(ProtectionError, "conflicting"):
            model.protect(0x1000, 0x2000, PAGE_READWRITE)
        self.assertEqual(model.owned_regions,
                         ((0x1000, 0x2000, PAGE_EXECUTE_READWRITE),))

    def test_unprotect_reverts_owned_region(self):
        model, backend = self._model()
        model.protect(0x1000, 0x1000, PAGE_READWRITE)
        operation = model.unprotect(0x1000, 0x1000, PAGE_READWRITE)
        self.assertTrue(operation["reverted"])
        self.assertNotIn("warning", operation)
        self.assertEqual(backend.releases, [(0x1000, 0x1000)])
        self.assertEqual(model.owned_regions, ())
        self.assertFalse(model.warnings)

    def test_unprotect_without_prior_protect_is_a_plan_warning(self):
        model, backend = self._model()
        operation = model.unprotect(0x1000, 0x1000, PAGE_EXECUTE_READ)
        self.assertFalse(operation["reverted"])
        self.assertIn("0x1000", operation["warning"])
        self.assertIn("no matching prior protect", model.warnings[0])
        self.assertEqual(backend.releases, [])
        self.assertEqual(model.owned_regions, ())
        # The warning stays in the plan report.
        self.assertEqual(model.report()["warnings"], model.warnings)

    def test_unprotect_partial_overlap_is_not_the_same_region(self):
        model, backend = self._model()
        model.protect(0x1000, 0x2000, PAGE_READWRITE)
        operation = model.unprotect(0x2000, 0x1000, PAGE_READWRITE)
        self.assertFalse(operation["reverted"])
        self.assertEqual(backend.releases, [])
        self.assertEqual(model.owned_regions, ((0x1000, 0x2000, PAGE_READWRITE),))

    def test_backend_apply_refusal_is_wrapped_and_not_registered(self):
        backend = ScriptedProtectionBackend(
            apply_refusals={(0x1000, 0x1000, PAGE_READWRITE)})
        model = ProtectionDirectiveModel(backend)
        with self.assertRaisesRegex(ProtectionError, "refused the range"):
            model.protect(0x1000, 0x1000, PAGE_READWRITE)
        self.assertEqual(model.owned_regions, ())
        self.assertEqual(model.operations, [])

    def test_backend_release_refusal_keeps_region_owned(self):
        backend = ScriptedProtectionBackend(
            release_refusals={(0x1000, 0x1000)})
        model = ProtectionDirectiveModel(backend)
        model.protect(0x1000, 0x1000, PAGE_READONLY)
        with self.assertRaisesRegex(ProtectionError, "refused the release"):
            model.unprotect(0x1000, 0x1000, PAGE_READONLY)
        self.assertEqual(model.owned_regions,
                         ((0x1000, 0x1000, PAGE_READONLY),))

    def test_malformed_foreign_regions_are_rejected(self):
        from ct2trainer.native.aa_directives import ProtectionBackend

        class BadRegions(ProtectionBackend):
            def foreign_regions(self, start, size):
                return (42,)

            def apply(self, base, size, page):
                pass

            def release(self, base, size):
                pass

        model = ProtectionDirectiveModel(BadRegions())
        with self.assertRaisesRegex(ProtectionError, "malformed foreign region"):
            model.protect(0x1000, 0x1000, PAGE_READONLY)

    def test_page_size_is_injectable(self):
        model = ProtectionDirectiveModel(ScriptedProtectionBackend(),
                                         page_size=0x100)
        model.protect(0x10100, 0x100, PAGE_READONLY)
        with self.assertRaisesRegex(ProtectionError, "page-aligned"):
            model.protect(0x10104, 0x100, PAGE_READONLY)
        with self.assertRaisesRegex(ProtectionError, "multiple"):
            model.protect(0x10100, 0x104, PAGE_READONLY)
        for bad in (0, 3, 0x100001):
            with self.subTest(page_size=bad), self.assertRaises(ProtectionError):
                ProtectionDirectiveModel(ScriptedProtectionBackend(),
                                         page_size=bad)

    def test_backend_contract_checked_in_constructor(self):
        with self.assertRaisesRegex(AADirectivesError, "protection backend"):
            ProtectionDirectiveModel(object())
        with self.assertRaisesRegex(AADirectivesError, "32/64"):
            ProtectionDirectiveModel(ScriptedProtectionBackend(), bitness=16)


class TargetApiDirectiveTests(unittest.TestCase):
    def _model(self, backend=None):
        if backend is None:
            backend = HeldExportBackend(fixture_images(64))
        model = TargetApiDirectiveModel(backend)
        return model, backend

    def test_getmodulehandle_returns_held_range(self):
        model, backend = self._model()
        operation = model.getmodulehandle("fixture")
        self.assertEqual(operation, {"op": "getmodulehandle",
                                     "module": "fixture.dll",
                                     "base": 0x710000, "size": 0x2000})
        self.assertEqual(model.operations, [operation])

    def test_module_name_normalization_appends_dll(self):
        model, _ = self._model()
        operation = model.getmodulehandle("fixture")
        self.assertEqual(operation["module"], "fixture.dll")
        operation = model.getmodulehandle("SECOND.dll")
        self.assertEqual(operation["module"], "SECOND.dll")
        self.assertEqual(operation["base"], 0x930000)

    def test_getmodulehandle_missing_module_rejected_with_context(self):
        model, _ = self._model()
        with self.assertRaises(TargetApiError) as context:
            model.getmodulehandle("ghost")
        self.assertEqual(context.exception.module, "ghost.dll")
        self.assertIsNone(context.exception.export)
        self.assertIn("not uniquely held", str(context.exception))
        self.assertEqual(model.operations, [])

    def test_invalid_module_names_rejected(self):
        model, _ = self._model()
        for name in (None, "", "a/b", "a.dll ", " a.dll", ".", "..",
                    "x" * 256, "a\\b.dll", "a?b.dll"):
            with self.subTest(name=name), self.assertRaises(TargetApiError):
                model.getmodulehandle(name)
        self.assertEqual(model.operations, [])

    def test_getprocaddress_named_export(self):
        model, backend = self._model()
        operation = model.getprocaddress("fixture", "Alpha")
        self.assertEqual(operation, {"op": "getprocaddress",
                                     "module": "fixture.dll",
                                     "export": "Alpha",
                                     "base": 0x710000,
                                     "address": 0x711100,
                                     "rva": 0x1100,
                                     "forwarded": False})
        self.assertTrue(backend.reads)

    def test_getprocaddress_ordinal_export(self):
        model, _ = self._model()
        operation = model.getprocaddress("second", "#9")
        self.assertEqual(operation["address"], 0x931200)
        self.assertEqual(operation["rva"], 0x1200)
        self.assertEqual(operation["module"], "second.dll")
        self.assertFalse(operation["forwarded"])

    def test_getprocaddress_ordinal_out_of_range_rejected(self):
        model, _ = self._model()
        # ordinal_base is 7; #5 maps to a negative index.
        with self.assertRaisesRegex(TargetApiError, "outside the address table"):
            model.getprocaddress("fixture", "#5")
        self.assertEqual(model.operations, [])

    def test_getprocaddress_missing_export_rejected_with_context(self):
        model, _ = self._model()
        with self.assertRaisesRegex(TargetApiError, "was not found") as context:
            model.getprocaddress("fixture", "Ghost")
        self.assertEqual(context.exception.module, "fixture.dll")
        self.assertEqual(context.exception.export, "Ghost")
        self.assertIn("fixture.dll", str(context.exception))
        self.assertEqual(model.operations, [])

    def test_invalid_export_names_rejected(self):
        model, _ = self._model()
        for name in ("Gh\x01st", "#12345678901", "", "#"):
            with self.subTest(name=name), self.assertRaises(TargetApiError):
                model.getprocaddress("fixture", name)
        self.assertEqual(model.operations, [])

    def test_forwarded_export_by_name_is_reported_not_rejected(self):
        model, _ = self._model()
        operation = model.getprocaddress("forwarder", "ByName")
        self.assertEqual(operation["module"], "forwarder.dll")
        self.assertEqual(operation["base"], 0xA00000)
        self.assertEqual(operation["address"], 0x931200)
        self.assertEqual(operation["rva"], 0x931200 - 0xA00000)
        self.assertTrue(operation["forwarded"])

    def test_forwarded_export_by_ordinal_is_reported_not_rejected(self):
        model, _ = self._model()
        operation = model.getprocaddress("forwarder", "ByOrdinal")
        self.assertEqual(operation["address"], 0x931200)
        self.assertTrue(operation["forwarded"])
        self.assertEqual(operation["export"], "ByOrdinal")

    def test_module_drift_during_resolution_rejected(self):
        model, _ = self._model(DriftingExportBackend(fixture_images(64)))
        with self.assertRaisesRegex(TargetApiError, "changed"):
            model.getprocaddress("fixture", "Alpha")
        self.assertEqual(model.operations, [])

    def test_backend_contract_checked_in_constructor(self):
        with self.assertRaisesRegex(AADirectivesError, "export backend"):
            TargetApiDirectiveModel(object())

    def test_operations_and_report_are_recorded(self):
        model, _ = self._model()
        model.getmodulehandle("fixture")
        model.getprocaddress("second", "Target")
        document = model.report()
        self.assertEqual(document["schema"], SCHEMA)
        self.assertEqual([op["op"] for op in document["operations"]],
                         ["getmodulehandle", "getprocaddress"])
        self.assertEqual(json.dumps(document, sort_keys=True)[:1], "{")


class DisassemblerDirectiveTests(unittest.TestCase):
    def _model(self, port=None, **kwargs):
        if port is None:
            port = StubDisassembler()
        model = DisassembleDirectiveModel(port, **kwargs)
        return model, port

    def test_disassemble_happy_path_output_shape(self):
        model, port = self._model()
        operation = model.disassemble(0x1000, 4)
        self.assertEqual(operation["op"], "disassemble")
        self.assertEqual(operation["address"], 0x1000)
        self.assertEqual(operation["count"], 4)
        self.assertEqual(
            [(item["address"], item["size"], item["mnemonic"])
             for item in operation["output"]],
            [(0x1000, 5, "nop"), (0x1005, 5, "nop"),
             (0x100A, 5, "nop"), (0x100F, 5, "nop")])
        self.assertEqual(port.calls, [(0x1000, 4, 64)])
        self.assertEqual(model.operations, [operation])

    def test_disassemble_gap_rejected(self):
        model, _ = self._model(StubDisassembler(defect="gap"))
        with self.assertRaisesRegex(DisassemblerError, "gapless"):
            model.disassemble(0x1000, 3)
        self.assertEqual(model.operations, [])

    def test_disassemble_reordered_rejected(self):
        model, _ = self._model(StubDisassembler(defect="reordered"))
        with self.assertRaisesRegex(DisassemblerError, "address-ordered"):
            model.disassemble(0x1000, 3)
        self.assertEqual(model.operations, [])

    def test_disassemble_short_output_rejected(self):
        model, _ = self._model(StubDisassembler(defect="short"))
        with self.assertRaisesRegex(DisassemblerError, "exactly 3 instructions"):
            model.disassemble(0x1000, 3)
        self.assertEqual(model.operations, [])

    def test_disassemble_long_output_rejected(self):
        model, _ = self._model(StubDisassembler(defect="long"))
        with self.assertRaisesRegex(DisassemblerError, "exactly 2 instructions"):
            model.disassemble(0x1000, 2)
        self.assertEqual(model.operations, [])

    def test_disassemble_zero_size_rejected(self):
        model, _ = self._model(StubDisassembler(defect="zero_size"))
        with self.assertRaisesRegex(
                DisassemblerError, "positive"):
            model.disassemble(0x1000, 2)
        self.assertEqual(model.operations, [])

    def test_disassemble_bad_mnemonic_rejected(self):
        model, _ = self._model(StubDisassembler(defect="bad_mnemonic"))
        with self.assertRaisesRegex(DisassemblerError, "mnemonic"):
            model.disassemble(0x1000, 2)
        self.assertEqual(model.operations, [])

    def test_disassemble_address_validation(self):
        model, port = self._model()
        for address in (0, -1, None, "0x1000", 1.0,
                        ADDRESS_LIMIT_64 + 1):
            with self.subTest(address=address), \
                    self.assertRaises(DisassemblerError):
                model.disassemble(address, 2)
        self.assertEqual(port.calls, [])

    def test_disassemble_count_validation(self):
        model, port = self._model()
        for count in (0, -1, MAX_DISASSEMBLE_COUNT + 1, None, "4", True):
            with self.subTest(count=count), \
                    self.assertRaises(DisassemblerError):
                model.disassemble(0x1000, count)
        self.assertEqual(port.calls, [])

    def test_32_bit_plan_rejects_64_bit_addresses(self):
        model, port = self._model(bitness=32)
        with self.assertRaisesRegex(DisassemblerError, "resolved bounded"):
            model.disassemble(ADDRESS_LIMIT_32 + 1, 2)
        self.assertEqual(port.calls, [])

    def test_disassemble_port_failure_wrapped(self):
        from ct2trainer.native.aa_directives import DisassemblerPort

        class FailingPort(DisassemblerPort):
            def disassemble(self, address, count, bitness):
                raise RuntimeError("port exploded")

        model, _ = self._model(FailingPort())
        with self.assertRaisesRegex(DisassemblerError, "port failed"):
            model.disassemble(0x1000, 2)
        self.assertEqual(model.operations, [])

    def test_instruction_size_boundaries(self):
        # 15-byte instructions are the maximum.
        model, _ = self._model(StubDisassembler(instruction_size=15))
        operation = model.disassemble(0x1000, 2)
        self.assertEqual(operation["output"][1]["address"], 0x1000 + 15)

        from ct2trainer.native.aa_directives import DisassemblerPort

        class TooLongPort(DisassemblerPort):
            def disassemble(self, address, count, bitness):
                return [{"address": address, "size": 16,
                         "mnemonic": "nop"} for _ in range(count)]

        model, _ = self._model(TooLongPort())
        with self.assertRaisesRegex(
                DisassemblerError, "positive bounded integer"):
            model.disassemble(0x1000, 2)

    def test_mnemonic_length_and_charset_boundaries(self):
        from ct2trainer.native.aa_directives import DisassemblerPort

        class LongMnemonicPort(DisassemblerPort):
            def __init__(self, mnemonic):
                self._mnemonic = mnemonic

            def disassemble(self, address, count, bitness):
                return [{"address": address + index, "size": 1,
                         "mnemonic": self._mnemonic}
                        for index in range(count)]

        model, _ = self._model(LongMnemonicPort("n" * 64))
        model.disassemble(0x1000, 2)
        model, _ = self._model(LongMnemonicPort("n" * 65))
        with self.assertRaisesRegex(DisassemblerError, "mnemonic"):
            model.disassemble(0x1000, 2)
        model, _ = self._model(LongMnemonicPort("n\x01"))
        with self.assertRaisesRegex(DisassemblerError, "mnemonic"):
            model.disassemble(0x1000, 2)

    def test_non_object_items_rejected(self):
        from ct2trainer.native.aa_directives import DisassemblerPort

        class ScalarPort(DisassemblerPort):
            def disassemble(self, address, count, bitness):
                return [42] * count

        model, _ = self._model(ScalarPort())
        with self.assertRaisesRegex(DisassemblerError, "objects"):
            model.disassemble(0x1000, 1)

    def test_disassembly_run_may_not_leave_bounded_space(self):
        from ct2trainer.native.aa_directives import DisassemblerPort

        class EdgePort(DisassemblerPort):
            def disassemble(self, address, count, bitness):
                return [{"address": address + index, "size": 1,
                         "mnemonic": "nop"}
                        for index in range(count)]

        model, _ = self._model(EdgePort(), bitness=32)
        # Ending exactly at the bounded limit is still in-bounds.
        operation = model.disassemble(ADDRESS_LIMIT_32 - 1, 2)
        self.assertEqual(operation["output"][1]["address"], ADDRESS_LIMIT_32)
        # One more instruction leaves the bounded target address space.
        with self.assertRaisesRegex(
                DisassemblerError, "bounded target address space"):
            model.disassemble(ADDRESS_LIMIT_32 - 1, 3)

    def test_constructor_validation(self):
        with self.assertRaisesRegex(
                DisassemblerError, "injectable DisassemblerPort"):
            DisassembleDirectiveModel(None)
        with self.assertRaisesRegex(DisassemblerError, "32/64"):
            DisassembleDirectiveModel(StubDisassembler(), bitness=16)

    def test_report_is_json_safe(self):
        model, _ = self._model()
        model.disassemble(0x1000, 3)
        document = model.report()
        self.assertEqual(document["schema"], SCHEMA)
        self.assertEqual(len(document["operations"]), 1)
        self.assertEqual(json.dumps(document, sort_keys=True)[:1], "{")


class SectionContractTests(unittest.TestCase):
    """Fail-closed section contract, pinned against the real pipelines.

    The structural model (analyze_sections/check_sections) is the negative
    model of this lane. The real grammars (aa_program.prepare_program /
    aa.compile_script) are pinned case by case with their exact messages —
    contrarian evidence that no behavior change occurred.
    """

    def test_analyze_classifies_all_fixture_cases(self):
        expected = {
            "eof_after_enable":
                (CASE_EOF_AFTER_ENABLE, True, False, 0, 0, 0),
            "empty_enable":
                (CASE_EMPTY_ENABLE, True, True, 0, 0, 3),
            "disable_without_enable":
                (CASE_DISABLE_WITHOUT_ENABLE, False, True, 0, 0, 3),
            "missing_disable":
                (CASE_MISSING_DISABLE, True, False, 0, 3, 0),
            "empty_disable":
                (CASE_EMPTY_DISABLE, True, True, 0, 3, 0),
            "complete":
                (CASE_COMPLETE, True, True, 0, 3, 3),
            "both_empty":
                (CASE_EMPTY_ENABLE, True, True, 0, 0, 0),
            "missing_disable_with_preamble":
                (CASE_MISSING_DISABLE, True, False, 1, 3, 0),
            "no_markers":
                (CASE_NO_MARKERS, False, False, 3, 0, 0),
            "duplicate_enable":
                (CASE_DUPLICATE_OR_OUT_OF_ORDER, True, True, 0, 3, 3),
            "disable_before_enable":
                (CASE_DUPLICATE_OR_OUT_OF_ORDER, True, True, 0, 3, 3),
            "symbol_only_empty_disable":
                (CASE_COMPLETE, True, True, 0, 2, 1),
        }
        for name, (case, e, d, pre, el, dl) in expected.items():
            with self.subTest(name=name):
                analysis = analyze_sections(SECTION_SOURCES[name])
                self.assertEqual(analysis.case, case)
                self.assertEqual(analysis.enable_present, e)
                self.assertEqual(analysis.disable_present, d)
                self.assertEqual(analysis.preamble_lines, pre)
                self.assertEqual(analysis.enable_lines, el)
                self.assertEqual(analysis.disable_lines, dl)

    def test_check_sections_rejects_structural_cases_in_both_grammars(self):
        rejected = {
            "eof_after_enable": CASE_EOF_AFTER_ENABLE,
            "empty_enable": CASE_EMPTY_ENABLE,
            "both_empty": CASE_EMPTY_ENABLE,
            "disable_without_enable": CASE_DISABLE_WITHOUT_ENABLE,
            "missing_disable": CASE_MISSING_DISABLE,
            "missing_disable_with_preamble": CASE_MISSING_DISABLE,
            "no_markers": CASE_NO_MARKERS,
            "duplicate_enable": CASE_DUPLICATE_OR_OUT_OF_ORDER,
            "disable_before_enable": CASE_DUPLICATE_OR_OUT_OF_ORDER,
        }
        for name, case in rejected.items():
            for grammar in (GRAMMAR_FULL, GRAMMAR_SMALL):
                with self.subTest(name=name, grammar=grammar):
                    with self.assertRaises(SectionStructureError) as ctx:
                        check_sections(SECTION_SOURCES[name], grammar=grammar)
                    self.assertEqual(ctx.exception.case, case)
                    self.assertEqual(ctx.exception.grammar, grammar)
                    self.assertIsNotNone(ctx.exception.analysis)

    def test_check_sections_accepts_structurally_complete_sources(self):
        for name in ("complete", "empty_disable", "symbol_only_empty_disable"):
            for grammar in (GRAMMAR_FULL, GRAMMAR_SMALL):
                with self.subTest(name=name, grammar=grammar):
                    analysis = check_sections(
                        SECTION_SOURCES[name], grammar=grammar)
                    self.assertIsInstance(analysis, SectionAnalysis)

    def test_check_sections_unknown_grammar_rejected(self):
        with self.assertRaisesRegex(SectionStructureError,
                                    "Unknown section grammar"):
            check_sections("[ENABLE]\n[DISABLE]", grammar="weird")

    def test_non_string_source_rejected(self):
        for bad in (None, 123, b"[ENABLE]"):
            with self.subTest(bad=bad), \
                    self.assertRaises(SectionStructureError):
                analyze_sections(bad)

    # -- Real full grammar (aa_program.prepare_program) pins ----------------

    def test_full_eof_after_enable_rejected(self):
        with self.assertRaisesRegex(
                ProgramError,
                "Program requires explicit ENABLE and DISABLE sections"):
            prepare_program(SECTION_SOURCES["eof_after_enable"], "Target.exe")

    def test_full_marker_missing_variants_rejected(self):
        # All three missing-marker variants fail with the same message.
        for name in ("disable_without_enable", "missing_disable",
                     "missing_disable_with_preamble", "no_markers"):
            with self.subTest(name=name), self.assertRaisesRegex(
                    ProgramError,
                    "Program requires explicit ENABLE and DISABLE sections"):
                prepare_program(SECTION_SOURCES[name], "Target.exe")

    def test_full_empty_enable_rejected(self):
        for name in ("empty_enable", "both_empty"):
            with self.subTest(name=name), self.assertRaisesRegex(
                    ProgramError,
                    "Enable section has no executable patch or data"):
                prepare_program(SECTION_SOURCES[name], "Target.exe")

    def test_full_symbol_only_empty_disable_rejected(self):
        # Structurally complete, content-dependently rejected: the full
        # grammar requires an executable patch or data in [ENABLE].
        with self.assertRaisesRegex(
                ProgramError,
                "Enable section has no executable patch or data"):
            prepare_program(
                SECTION_SOURCES["symbol_only_empty_disable"], "Target.exe")

    def test_full_duplicate_and_out_of_order_rejected(self):
        for name in ("duplicate_enable", "disable_before_enable"):
            with self.subTest(name=name), self.assertRaisesRegex(
                    ProgramError,
                    "AA sections are duplicated or out of order"):
                prepare_program(SECTION_SOURCES[name], "Target.exe")

    def test_full_empty_disable_accepted(self):
        # Documented content-dependent split: the full grammar accepts an
        # empty [DISABLE] (enable=3, disable=0) — pinned, unchanged.
        result = prepare_program(SECTION_SOURCES["empty_disable"],
                                 "Target.exe")
        self.assertEqual(len(result["enable"]), 3)
        self.assertEqual(len(result["disable"]), 0)

    def test_full_complete_accepted(self):
        result = prepare_program(SECTION_SOURCES["complete"], "Target.exe")
        self.assertEqual(len(result["enable"]), 3)
        self.assertEqual(len(result["disable"]), 3)

    # -- Real small language (aa.compile_script) pins -----------------------

    def test_small_missing_markers_rejected(self):
        for name in ("eof_after_enable", "disable_without_enable",
                     "missing_disable", "missing_disable_with_preamble"):
            with self.subTest(name=name), self.assertRaisesRegex(
                    AAError,
                    "Both ENABLE and DISABLE sections are required"):
                compile_script(SECTION_SOURCES[name])

    def test_small_empty_enable_rejected_asymmetric(self):
        # Empty [ENABLE] with patch content in [DISABLE] fails the
        # symmetric-patch guard (content-dependent, not structural).
        with self.assertRaisesRegex(
                AAError,
                "Enable and disable must patch the same address ranges"):
            compile_script(SECTION_SOURCES["empty_enable"])

    def test_small_empty_disable_with_patch_rejected(self):
        # The documented content-dependent split: an empty [DISABLE] with a
        # byte patch in [ENABLE] is rejected by the symmetric-patch guard.
        with self.assertRaisesRegex(
                AAError,
                "Enable and disable must patch the same address ranges"):
            compile_script(SECTION_SOURCES["empty_disable"])

    def test_small_no_markers_rejected_in_preamble(self):
        with self.assertRaisesRegex(
                AAError,
                "Only define/label declarations are allowed before ENABLE"):
            compile_script(SECTION_SOURCES["no_markers"])

    def test_small_both_empty_rejected_no_actions(self):
        with self.assertRaisesRegex(
                AAError,
                "Script has no registered symbols or guarded byte-patch action"):
            compile_script(SECTION_SOURCES["both_empty"])

    def test_small_duplicate_and_out_of_order_rejected(self):
        for name in ("duplicate_enable", "disable_before_enable"):
            with self.subTest(name=name), self.assertRaisesRegex(
                    AAError,
                    "Require exactly one ENABLE section followed by one "
                    "DISABLE section"):
                compile_script(SECTION_SOURCES[name])

    def test_small_complete_accepted(self):
        result = compile_script(SECTION_SOURCES["complete"])
        self.assertEqual(result["requires"], [])
        self.assertEqual(result["provides"], [])

    def test_small_symbol_only_empty_disable_accepted(self):
        # Documented positive exception: symbol-only scripts register and
        # release their symbol with an empty [DISABLE].
        result = compile_script(
            SECTION_SOURCES["symbol_only_empty_disable"])
        self.assertEqual(result["requires"], [])
        self.assertEqual(result["provides"], ["Anchor"])

    # -- End-to-end compile_table pin ----------------------------------------

    def test_compile_table_missing_disable_blocked_record(self):
        import pathlib
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            p = pathlib.Path(tmp) / "s.CT"
            p.write_text(
                '<CheatTable CheatEngineTableVersion="52"><CheatEntries>'
                '<CheatEntry><ID>1</ID><Description>t</Description>'
                '<VariableType>Auto Assembler Script</VariableType>'
                '<AssemblerScript>[ENABLE]\n1000:\ndb 01</AssemblerScript>'
                '</CheatEntry></CheatEntries></CheatTable>',
                encoding="utf-8")
            plan = compile_table(p, "Target.exe")
            entry = plan["entries"][0]
            self.assertEqual(entry["kind"], "blocked")
            self.assertFalse(entry["supported"])
            self.assertEqual(
                entry["reason"],
                "Both ENABLE and DISABLE sections are required. "
                "Native assembly: Program requires explicit ENABLE and "
                "DISABLE sections.")
            self.assertNotIn("enable", entry)
            self.assertNotIn("disable", entry)
            self.assertNotIn("program", entry)


class DirectivesPlanTests(unittest.TestCase):
    def test_plan_aggregates_operations_and_warnings_in_order(self):
        threads = ThreadDirectiveModel(ScriptedThreadBackend())
        threads.create_thread(0x1000)
        protection = ProtectionDirectiveModel(ScriptedProtectionBackend())
        protection.protect(0x2000, 0x1000, PAGE_READWRITE)
        protection.unprotect(0x4000, 0x1000, PAGE_READWRITE)  # warning
        exports = TargetApiDirectiveModel(HeldExportBackend(fixture_images(64)))
        exports.getmodulehandle("fixture")
        disassembler = DisassembleDirectiveModel(StubDisassembler())
        disassembler.disassemble(0x1000, 2)
        plan = DirectivesPlan(threads=threads, protection=protection,
                              exports=exports, disassembler=disassembler)
        document = plan.report()
        self.assertEqual(document["schema"], SCHEMA)
        self.assertEqual([op["op"] for op in document["operations"]],
                         ["create_thread", "protect", "unprotect",
                          "getmodulehandle", "disassemble"])
        self.assertEqual(len(document["warnings"]), 1)
        self.assertIn("0x4000", document["warnings"][0])

    def test_plan_with_partial_models(self):
        exports = TargetApiDirectiveModel(HeldExportBackend(fixture_images(64)))
        exports.getprocaddress("fixture", "Alpha")
        plan = DirectivesPlan(exports=exports)
        document = plan.report()
        self.assertEqual(len(document["operations"]), 1)
        self.assertEqual(document["operations"][0]["op"], "getprocaddress")
        self.assertEqual(document["warnings"], [])

    def test_plan_rejects_models_without_contracts(self):
        class NotAModel:
            pass

        plan = DirectivesPlan(threads=NotAModel())
        with self.assertRaisesRegex(AADirectivesError, "operations and warnings"):
            plan.report()

    def test_plan_report_stays_json_safe(self):
        threads = ThreadDirectiveModel(ScriptedThreadBackend(pending_polls=1))
        threads.create_thread(0x1000)
        threads.thread_wait(1)
        plan = DirectivesPlan(threads=threads)
        document = plan.report()
        self.assertEqual(json.dumps(document, sort_keys=True,
                                    allow_nan=False)[:1], "{")
        self.assertEqual(document["operations"][1]["polls"], 2)
