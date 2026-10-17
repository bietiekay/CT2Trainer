"""Check native memory bounds/identity failures and Windows-owned allocations."""

import ctypes
import os
import sys
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ct2trainer.local_processes import LocalProcess, list_local_processes
from ct2trainer.native.memory import (
    MAX_SCAN_SIZE, MAX_TRANSFER, MEM_COMMIT, PAGE_GUARD, WAIT_TIMEOUT,
    ProcessMemory, ProcessMemoryError, _MEMORY_BASIC_INFORMATION,
    _compile_pattern, _names_equal,
)


def _memory(pointer_size=8):
    memory = object.__new__(ProcessMemory)
    memory._lock = threading.RLock()
    memory._handle = 1
    memory._pid = 17
    memory._creation_time = 123
    memory._pointer_size = pointer_size
    memory._write_uncertain = False
    memory._start_time = Mock(return_value=123)
    memory._kernel = SimpleNamespace(
        WaitForSingleObject=Mock(return_value=WAIT_TIMEOUT),
        GetProcessId=Mock(return_value=17), CloseHandle=Mock(return_value=True),
    )
    return memory


def _region(base, size, protection=0x04, state=MEM_COMMIT):
    result = _MEMORY_BASIC_INFORMATION()
    result.BaseAddress = base
    result.RegionSize = size
    result.Protect = protection
    result.State = state
    return result


class PatternTests(unittest.TestCase):
    def test_pattern_matches_exact_wildcard_nibbles_and_overlaps(self):
        matcher, width = _compile_pattern("a? ?f ?? 0A")
        self.assertEqual(width, 4)
        self.assertEqual([item.start() for item in matcher.finditer(bytes.fromhex("A3 4F 00 0A A0 FF 0A 0A"))], [0, 4])
        matcher, width = _compile_pattern("41 41")
        self.assertEqual([item.start() for item in matcher.finditer(b"AAA")], [0, 1])
        self.assertEqual(width, 2)

    def test_regex_metacharacters_are_literal_pattern_bytes(self):
        matcher, _ = _compile_pattern("5B 2E 2A 5C 5D")
        self.assertEqual([item.start() for item in matcher.finditer(b"x[.*\\]y")], [1])

    def test_invalid_or_unconstrained_patterns_are_rejected(self):
        for pattern in ("", "?? ??", "*", "F", "FG", "001", "11|22", "AA " * 4097):
            with self.subTest(pattern=pattern[:20]), self.assertRaises(ValueError):
                _compile_pattern(pattern)


class MemoryIdentityTests(unittest.TestCase):
    def test_unicode_image_name_cannot_be_conflated_by_casefold_expansion(self):
        self.assertTrue(_names_equal("Game.exe", "GAME.EXE"))
        self.assertFalse(_names_equal("Straße.exe", "Strasse.exe"))
        self.assertFalse(_names_equal("İ.exe", "i\u0307.exe"))

    @unittest.skipUnless(sys.platform == "win32", "Windows ordinal Unicode comparison required")
    def test_windows_unicode_case_comparison_uses_ordinal_image_names(self):
        self.assertTrue(_names_equal("MÜNCHEN.exe", "München.EXE"))
        with patch("ct2trainer.native.memory._api") as api, patch("ct2trainer.native.memory.list_local_processes", return_value=[LocalProcess(17, "Strasse.exe")]):
            with self.assertRaisesRegex(ProcessMemoryError, "found 0"):
                ProcessMemory("Straße.exe")
            api.assert_not_called()

    def test_alive_requires_wait_and_original_pid_creation_time(self):
        memory = _memory()
        self.assertTrue(memory.is_alive())
        self.assertEqual(memory.identity, (17, 123))
        memory._kernel.WaitForSingleObject.return_value = 0
        self.assertFalse(memory.is_alive())
        memory._kernel.WaitForSingleObject.return_value = WAIT_TIMEOUT
        memory._start_time.return_value = 124
        with self.assertRaisesRegex(ProcessMemoryError, "identity"):
            memory.is_alive()
        memory._start_time.return_value = 123
        memory._kernel.GetProcessId.return_value = 18
        with self.assertRaisesRegex(ProcessMemoryError, "identity"):
            memory.is_alive()

    @unittest.skipUnless(sys.platform == "win32", "Win32 last-error API required")
    def test_failed_wait_is_uncertain_and_cannot_be_used_for_read(self):
        memory = _memory()
        memory._kernel.WaitForSingleObject.return_value = 0xFFFFFFFF
        memory._read_exact = Mock()
        with self.assertRaisesRegex(ProcessMemoryError, "WaitForSingleObject"):
            memory.read(0x1000, 4)
        memory._read_exact.assert_not_called()

    def test_close_is_idempotent_and_closed_handle_cannot_be_used(self):
        memory = _memory()
        memory.close()
        memory.close()
        memory._kernel.CloseHandle.assert_called_once_with(1)
        with self.assertRaisesRegex(ProcessMemoryError, "closed"):
            memory.is_alive()

    @unittest.skipUnless(sys.platform == "win32", "Win32 API required")
    def test_zero_or_multiple_exact_names_cannot_open_a_handle(self):
        candidates = [LocalProcess(1, "game.exe"), LocalProcess(2, "GAME.EXE")]
        with patch("ct2trainer.native.memory._api") as api:
            for processes in ([], candidates):
                with patch("ct2trainer.native.memory.list_local_processes", return_value=processes):
                    with self.assertRaisesRegex(ProcessMemoryError, "Expected one exact"):
                        ProcessMemory("game.exe")
            api.assert_not_called()

    @unittest.skipUnless(sys.platform == "win32", "Win32 API required")
    def test_opened_image_name_mismatch_closes_handle(self):
        kernel = SimpleNamespace(OpenProcess=Mock(return_value=1), GetProcessId=Mock(return_value=17), CloseHandle=Mock(return_value=True))
        with patch("ct2trainer.native.memory._api", return_value=kernel), patch("ct2trainer.native.memory.list_local_processes", return_value=[LocalProcess(17, "game.exe")]), patch.object(ProcessMemory, "_image_path", return_value=r"C:\wrong.exe"):
            with self.assertRaisesRegex(ProcessMemoryError, "image"):
                ProcessMemory("game.exe")
        kernel.CloseHandle.assert_called_once_with(1)


class MemoryBoundsTests(unittest.TestCase):
    def test_invalid_address_ranges_are_rejected_without_access(self):
        memory = _memory()
        memory._require_alive = Mock()
        memory._read_exact = Mock()
        for address, size in ((0, 1), (-1, 1), (True, 1), (1, False), (1, 0), (1, -1), (1, MAX_TRANSFER + 1), (0x7FFFFFFFFFFF, 2)):
            with self.subTest(address=address, size=size), self.assertRaises(ValueError):
                memory.read(address, size)
        memory._require_alive.assert_not_called()
        memory._read_exact.assert_not_called()
        memory._pointer_size = 4
        with self.assertRaises(ValueError):
            memory.read(0xFFFFFFFF, 2)

    def test_partial_read_cannot_be_accepted_as_exact(self):
        memory = _memory()
        def partial_read(handle, address, buffer, size, transferred):
            ctypes.cast(transferred, ctypes.POINTER(ctypes.c_size_t)).contents.value = size - 1
            return True
        memory._kernel.ReadProcessMemory = Mock(side_effect=partial_read)
        with self.assertRaisesRegex(ProcessMemoryError, "partial"):
            memory.read(0x1000, 4)

    def test_null_pointer_and_pointer_overflow_are_rejected(self):
        memory = _memory()
        memory.read = Mock(return_value=b"\0" * 8)
        with self.assertRaisesRegex(ProcessMemoryError, "null pointer"):
            memory.resolve_pointer(0x1000, [4])
        memory.read.return_value = (0x7FFFFFFFFFFF).to_bytes(8, "little")
        with self.assertRaises(ValueError):
            memory.resolve_pointer(0x1000, [1])
        with self.assertRaises(ValueError):
            memory.resolve_pointer(0x1000, [1] * 33)

    def test_pointer_offsets_are_reversed_and_width_follows_target(self):
        for width in (4, 8):
            with self.subTest(width=width):
                memory = _memory(width)
                memory.read = Mock(side_effect=[(0x2000).to_bytes(width, "little"), (0x3000).to_bytes(width, "little")])
                self.assertEqual(memory.resolve_pointer(0x1000, [0x10, 0x20]), 0x3010)
                self.assertEqual(memory.read.call_args_list[0].args, (0x1000, width))
                self.assertEqual(memory.read.call_args_list[1].args, (0x2020, width))

    def test_addresses_are_resolved_without_eval_or_unbounded_arithmetic(self):
        memory = _memory()
        memory.module = Mock(return_value=(0x1000, 0x100))
        self.assertEqual(memory.resolve('"my-game.exe"+10-4'), 0x100C)
        self.assertEqual(memory.resolve("Anchor+20", {"Anchor": 0x2000}), 0x2020)
        self.assertEqual(memory.resolve("Anchor+20", {"anchor": 0x2000}), 0x2020)
        self.assertEqual(memory.resolve("anchor+20", {"Anchor": 0x2000}), 0x2020)
        with self.assertRaisesRegex(ValueError, "Ambiguous symbol"):
            memory.resolve("Anchor+20", {"anchor": 0x2000, "Anchor": 0x3000})
        self.assertEqual(memory.resolve("0x3000+10"), 0x3010)
        self.assertEqual(memory.resolve("$3000+$10"), 0x3010)
        self.assertEqual(memory.resolve("DEAD"), 0xDEAD)
        for expression in ("__import__('os')", "[1000]", "game.exe*2", "1000/2", "1000 + -1", "0-1", "1000+FFFFFFFFFFFFFFFF", '"../game.exe"'):
            with self.subTest(expression=expression), self.assertRaises((ValueError, ProcessMemoryError)):
                # A mocked module cannot validate image basenames itself.
                if expression.startswith('"../'):
                    memory.module = ProcessMemory.module.__get__(memory)
                memory.resolve(expression)


class ModuleScanTests(unittest.TestCase):
    def scanner(self, regions, bytes_by_address, size=8):
        memory = _memory()
        memory.module = Mock(return_value=(0x1000, size))
        memory._query = Mock(side_effect=lambda address: next(region for region in regions if int(region.BaseAddress) <= address < int(region.BaseAddress) + region.RegionSize))
        memory.read = Mock(side_effect=lambda address, length: bytes_by_address[address][:length])
        return memory

    def test_scan_carries_overlap_across_contiguous_readable_regions(self):
        memory = self.scanner([_region(0x1000, 4), _region(0x1004, 4)], {0x1000: b"xxxA", 0x1004: b"BCyy"})
        self.assertEqual(memory.scan_module("game.exe", "41 42 43"), 0x1003)

    def test_scan_carries_overlap_across_chunk_boundaries(self):
        memory = self.scanner([_region(0x1000, 8)], {0x1000: b"xxxA", 0x1004: b"BCyy"})
        with patch("ct2trainer.native.memory.SCAN_CHUNK_SIZE", 4):
            self.assertEqual(memory.scan_module("game.exe", "41 42 43"), 0x1003)

    def test_scan_nibble_anchor_and_literal_anchor_with_offset(self):
        memory = self.scanner([_region(0x1000, 8)], {0x1000: b"xx\xA1\x2Fxxxx"})
        self.assertEqual(memory.scan_module("game.exe", "A? ?F"), 0x1002)
        self.assertEqual(memory.scan_module("game.exe", "?? A1 2F ??"), 0x1001)

    def test_scan_candidate_and_time_bounds_fail_closed(self):
        memory = self.scanner([_region(0x1000, 8)], {0x1000: b"A1A1A1A1"})
        with patch("ct2trainer.native.memory.MAX_SCAN_CANDIDATES", 2), self.assertRaisesRegex(ProcessMemoryError, "bound"):
            memory.scan_module("game.exe", "41 ?? ?? FF")
        with patch("ct2trainer.native.memory.time.monotonic", side_effect=[0, 31]), self.assertRaisesRegex(ProcessMemoryError, "time bound"):
            memory.scan_module("game.exe", "41 31")

    def test_scan_does_not_bridge_guarded_uncommitted_or_unreadable_gaps(self):
        for protection, state in ((PAGE_GUARD | 0x04, MEM_COMMIT), (0x01, MEM_COMMIT), (0x04, 0x2000)):
            with self.subTest(protection=protection, state=state):
                memory = self.scanner([_region(0x1000, 3), _region(0x1003, 2, protection, state), _region(0x1005, 3)], {0x1000: b"xxA", 0x1005: b"BCx"})
                with self.assertRaisesRegex(ProcessMemoryError, "not found"):
                    memory.scan_module("game.exe", "41 42 43")
                self.assertEqual([call.args[0] for call in memory.read.call_args_list], [0x1000, 0x1005])

    def test_scan_rejects_ambiguous_and_changed_modules(self):
        memory = self.scanner([_region(0x1000, 8)], {0x1000: b"ABxxAByy"})
        with self.assertRaisesRegex(ProcessMemoryError, "ambiguous"):
            memory.scan_module("game.exe", "41 42")
        memory = self.scanner([_region(0x1000, 8)], {0x1000: b"ABxxxxxx"})
        memory.module.side_effect = [(0x1000, 8), (0x2000, 8)]
        with self.assertRaisesRegex(ProcessMemoryError, "changed"):
            memory.scan_module("game.exe", "41 42")

    def test_scan_never_reads_beyond_module_size_or_scan_limit(self):
        memory = self.scanner([_region(0x1000, 4096)], {0x1000: b"xxxxxxxABC"})
        with self.assertRaisesRegex(ProcessMemoryError, "not found"):
            memory.scan_module("game.exe", "41 42 43")
        memory.read.assert_called_once_with(0x1000, 8)
        memory.module.return_value = (0x1000, MAX_SCAN_SIZE + 1)
        memory.read.reset_mock()
        with self.assertRaises(ValueError):
            memory.scan_module("game.exe", "41 42")
        memory.read.assert_not_called()

    def test_scan_result_failures_are_scan_miss_not_generic_memory_errors(self):
        # A stale table (pattern no longer in the image) is a scan-result
        # failure, not a target-level fault: it must surface as ScanMiss so
        # the engine can fail one record without blocking the whole session.
        from ct2trainer.native.memory import ScanMiss
        miss = self.scanner([_region(0x1000, 8)], {0x1000: b"xxxxxxxx"})
        with self.assertRaises(ScanMiss):
            miss.scan_module("game.exe", "41 42 43")
        ambiguous = self.scanner([_region(0x1000, 8)], {0x1000: b"ABxxAByy"})
        with self.assertRaises(ScanMiss):
            ambiguous.scan_module("game.exe", "41 42")
        changed = self.scanner([_region(0x1000, 8)], {0x1000: b"ABxxAByy"})
        changed.module.side_effect = [(0x1000, 8), (0x2000, 8)]
        with self.assertRaises(ScanMiss):
            changed.scan_module("game.exe", "41 42")
        self.assertFalse(isinstance(ProcessMemoryError("identity changed"), ScanMiss))


class MemoryWriteTests(unittest.TestCase):
    def writer(self, protection=0x20):
        memory = _memory()
        memory._query = Mock(return_value=_region(0x1000, 4096, protection))
        memory._read_exact = Mock(return_value=b"ABCD")
        def protect(handle, address, size, requested, previous):
            ctypes.cast(previous, ctypes.POINTER(ctypes.c_uint32)).contents.value = protection
            return True
        def write(handle, address, buffer, size, transferred):
            ctypes.cast(transferred, ctypes.POINTER(ctypes.c_size_t)).contents.value = size
            return True
        memory._kernel.VirtualProtectEx = Mock(side_effect=protect)
        memory._kernel.WriteProcessMemory = Mock(side_effect=write)
        memory._kernel.FlushInstructionCache = Mock(return_value=True)
        return memory

    def test_code_write_restores_original_protection_and_flushes(self):
        memory = self.writer()
        memory.write(0x1000, b"ABCD")
        self.assertEqual([call.args[3] for call in memory._kernel.VirtualProtectEx.call_args_list], [0x40, 0x20])
        memory._kernel.FlushInstructionCache.assert_called_once_with(1, 0x1000, 4)
        memory._read_exact.assert_called_once_with(0x1000, 4)

    def test_readback_failure_blocks_following_writes(self):
        memory = self.writer()
        memory._read_exact.return_value = b"ABCE"
        with self.assertRaisesRegex(ProcessMemoryError, "readback"):
            memory.write(0x1000, b"ABCD")
        memory._read_exact.return_value = b"ABCD"
        with self.assertRaisesRegex(ProcessMemoryError, "previous write"):
            memory.write(0x1000, b"ABCD")
        self.assertEqual(memory._kernel.WriteProcessMemory.call_count, 1)

    def test_partial_write_restores_protection_and_does_not_retry(self):
        memory = self.writer()
        def partial(handle, address, buffer, size, transferred):
            ctypes.cast(transferred, ctypes.POINTER(ctypes.c_size_t)).contents.value = size - 1
            return True
        memory._kernel.WriteProcessMemory.side_effect = partial
        with self.assertRaisesRegex(ProcessMemoryError, "partial"):
            memory.write(0x1000, b"ABCD")
        self.assertEqual(memory._kernel.VirtualProtectEx.call_count, 2)
        self.assertEqual(memory._kernel.FlushInstructionCache.call_count, 1)
        memory._read_exact.assert_not_called()

    @unittest.skipUnless(sys.platform == "win32", "Win32 last-error API required")
    def test_protection_restoration_or_flush_failure_blocks_more_writes(self):
        for failure in ("protection", "flush"):
            with self.subTest(failure=failure):
                memory = self.writer()
                if failure == "protection":
                    initial = memory._kernel.VirtualProtectEx.side_effect
                    def fail_restore(*args):
                        return initial(*args) if args[3] == 0x40 else False
                    memory._kernel.VirtualProtectEx.side_effect = fail_restore
                else:
                    memory._kernel.FlushInstructionCache.return_value = False
                with self.assertRaises(ProcessMemoryError):
                    memory.write(0x1000, b"ABCD")
                self.assertTrue(memory._write_uncertain)
                memory._read_exact.assert_not_called()

    def test_guarded_memory_is_rejected_before_any_write_or_protection(self):
        memory = self.writer(0x04 | PAGE_GUARD)
        with self.assertRaisesRegex(ProcessMemoryError, "guarded"):
            memory.write(0x1000, b"ABCD")
        memory._kernel.WriteProcessMemory.assert_not_called()
        memory._kernel.VirtualProtectEx.assert_not_called()
        self.assertFalse(memory._write_uncertain)


@unittest.skipUnless(sys.platform == "win32" and ctypes.sizeof(ctypes.c_void_p) == 8, "Windows x64 required")
class WindowsOwnedMemoryTests(unittest.TestCase):
    def setUp(self):
        self.name = next(process.name for process in list_local_processes() if process.pid == os.getpid())
        self.memory = ProcessMemory(self.name, os.getpid())

    def tearDown(self):
        self.memory.close()

    def test_real_handle_module_and_exact_read_write(self):
        buffer = ctypes.create_string_buffer(b"owned-fixture-data")
        address = ctypes.addressof(buffer)
        self.assertTrue(self.memory.is_alive())
        self.assertGreater(self.memory.creation_time, 0)
        self.assertEqual(self.memory.pointer_size, 8)
        self.assertEqual(self.memory.read(address, 5), b"owned")
        self.memory.write(address, b"OWNED")
        self.assertEqual(buffer.raw[:5], b"OWNED")
        base, size = self.memory.module(self.name)
        self.assertEqual(self.memory.read(base, 2), b"MZ")
        pattern = self.memory.read(base, 64).hex(" ")
        self.assertEqual(self.memory.scan_module(self.name, pattern), base)
        self.assertGreater(size, 64)

    def test_real_readonly_and_executable_page_protection_is_restored(self):
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.VirtualAlloc.argtypes = (ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_uint32)
        kernel.VirtualAlloc.restype = ctypes.c_void_p
        kernel.VirtualProtect.argtypes = (ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32))
        kernel.VirtualProtect.restype = ctypes.c_int
        kernel.VirtualFree.argtypes = (ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32)
        kernel.VirtualFree.restype = ctypes.c_int
        address = kernel.VirtualAlloc(None, 4096, 0x3000, 0x04)
        self.assertTrue(address)
        try:
            for protection in (0x02, 0x20):
                old = ctypes.c_uint32()
                self.assertTrue(kernel.VirtualProtect(address, 4096, protection, ctypes.byref(old)))
                self.memory.write(address, b"\x90\xC3")
                self.assertEqual(self.memory.read(address, 2), b"\x90\xC3")
                self.assertEqual(self.memory._query(address).Protect, protection)
        finally:
            self.assertTrue(kernel.VirtualFree(address, 0, 0x8000))

    def test_real_pointer_resolution_and_wrong_explicit_name(self):
        value = ctypes.c_uint32(5678)
        pointer = ctypes.c_uint64(ctypes.addressof(value) - 4)
        address = self.memory.resolve_pointer(ctypes.addressof(pointer), [4])
        self.assertEqual(address, ctypes.addressof(value))
        self.assertEqual(self.memory.read(address, 4), (5678).to_bytes(4, "little"))
        with self.assertRaises(ProcessMemoryError):
            ProcessMemory("DefinitelyNotTheRunningImage.exe", os.getpid())


if __name__ == "__main__":
    unittest.main()
