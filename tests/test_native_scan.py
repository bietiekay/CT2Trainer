"""All-match scan boundaries, filtering, completeness caps and owned pages."""
import ctypes
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from ct2trainer.native.memory import (MEM_COMMIT, MEM_FREE, PAGE_GUARD, ProcessMemory,
                                        ProcessMemoryError, _SYSTEM_INFO)
from tests.test_native_memory import _memory, _region


def _scan_memory(regions):
    """Regions are (start, bytes, protection, state), and cover one interval."""
    memory = _memory()
    base, last = regions[0][0], regions[-1][0] + len(regions[-1][1])
    def information(pointer):
        info = ctypes.cast(pointer, ctypes.POINTER(_SYSTEM_INFO)).contents
        info.minimum_address = 0
        info.maximum_address = last - 1
    memory._kernel.GetSystemInfo = information
    def query(address):
        if address < base:
            return _region(0, base, 0, MEM_FREE)
        for start, raw, protection, state in regions:
            if start <= address < start + len(raw):
                return _region(start, len(raw), protection, state)
        raise AssertionError("Scan queried outside the exclusive range")
    memory._query = query
    memory.read_calls = []
    def read(address, size):
        memory.read_calls.append((address, size))
        for start, raw, protection, state in regions:
            if start <= address and address + size <= start + len(raw):
                return raw[address - start:address - start + size]
        raise AssertionError("Scanner read across an unqualified gap")
    memory._read_exact = read
    return memory, base, last


class AllMatchTests(unittest.TestCase):
    def test_overlapping_sorted_matches_are_complete_with_exclusive_end(self):
        memory, base, end = _scan_memory([(0x1000, b"AAA", 0x04, MEM_COMMIT)])
        self.assertEqual(memory.scan_matches("41 41", base, end), [base, base + 1])
        self.assertEqual(memory.scan_matches("41 41", base, end - 1), [base])
        self.assertEqual(memory.scan_matches("41 41", base + 1, end), [base + 1])
        self.assertEqual(memory.scan_matches("41", end, end), [])

    def test_matches_bridge_qualified_regions_and_chunks_but_not_protection_gaps(self):
        memory, base, end = _scan_memory([(0x1000, b"xxA", 0x04, MEM_COMMIT),
                                         (0x1003, b"Bxx", 0x20, MEM_COMMIT)])
        with patch("ct2trainer.native.memory.SCAN_CHUNK_SIZE", 2):
            self.assertEqual(memory.scan_matches("41 42", base, end), [base + 2])
            self.assertEqual(memory.scan_matches("41 42", base, end, protection="+W"), [])
        for protection, state in ((0x04 | PAGE_GUARD, MEM_COMMIT), (0x01, MEM_COMMIT), (0x04, MEM_FREE)):
            memory, base, end = _scan_memory([(0x1000, b"A", 0x04, MEM_COMMIT),
                                             (0x1001, b"B", protection, state)])
            self.assertEqual(memory.scan_matches("41 42", base, end), [])

    def test_required_excluded_and_any_execute_write_copy_flags(self):
        regions = [(0x1000, b"AA", 0x02, MEM_COMMIT), (0x1002, b"AA", 0x04, MEM_COMMIT),
                   (0x1004, b"AA", 0x08, MEM_COMMIT), (0x1006, b"AA", 0x20, MEM_COMMIT),
                   (0x1008, b"AA", 0x40, MEM_COMMIT), (0x100A, b"AA", 0x80, MEM_COMMIT)]
        memory, base, end = _scan_memory(regions)
        self.assertEqual(memory.scan_matches("41", base, end, "+W-C"), [0x1002, 0x1003, 0x1008, 0x1009])
        self.assertEqual(memory.scan_matches("41", base, end, "+X-W"), [0x1006, 0x1007])
        self.assertEqual(memory.scan_matches("41", base, end, "*X*W+C"), [0x1004, 0x1005, 0x100A, 0x100B])

    def test_divisible_and_last_hex_digit_alignment_modes(self):
        raw = bytearray(b"\xBB" * 48)
        for offset in (0, 4, 16, 20):
            raw[offset] = 0xAA
        memory, base, end = _scan_memory([(0x1000, bytes(raw), 0x04, MEM_COMMIT)])
        self.assertEqual(memory.scan_matches("AA", base, end, alignment_type=1,
                                             alignment_parameter="10"), [0x1000, 0x1010])
        self.assertEqual(memory.scan_matches("AA", base, end, alignment_type=2,
                                             alignment_parameter="04"), [0x1004])

    def test_result_candidate_read_region_and_time_caps_never_return_partial_matches(self):
        memory, base, end = _scan_memory([(0x1000, b"AA", 0x04, MEM_COMMIT),
                                         (0x1002, b"AA", 0x04, MEM_COMMIT)])
        with self.assertRaisesRegex(ProcessMemoryError, "result bound"):
            memory.scan_matches("41", base, end, max_results=1)
        for constant, value, message in (("MAX_SCAN_CANDIDATES", 1, "candidate/time"),
                                          ("MAX_PROCESS_SCAN_BYTES", 3, "byte-read"),
                                          ("MAX_PROCESS_SCAN_REGIONS", 1, "region/time")):
            with self.subTest(constant=constant), patch("ct2trainer.native.memory." + constant, value):
                with self.assertRaisesRegex(ProcessMemoryError, message):
                    memory.scan_matches("41", base, end)
        with patch("ct2trainer.native.memory.time.monotonic", side_effect=[0, 31]):
            with self.assertRaisesRegex(ProcessMemoryError, "time bound"):
                memory.scan_matches("41", base, end)

    def test_full_scan_stops_at_real_user_range_even_for_ce_unsigned_stop_limit(self):
        memory, base, end = _scan_memory([(0x1000, b"AB", 0x04, MEM_COMMIT)])
        self.assertEqual(memory.scan_matches("41 42"), [base])
        self.assertEqual(memory.scan_matches("41 42", 0, 0x10000000000000000), [base])
        self.assertEqual(memory.scan_matches("41 42", end + 1, None), [])

    def test_invalid_filters_alignment_and_ranges_are_rejected_before_any_read(self):
        memory, base, end = _scan_memory([(0x1000, b"AA", 0x04, MEM_COMMIT)])
        cases = [{"start": -1}, {"start": True}, {"start": end, "end": base},
                 {"end": 0x10000000000000001}, {"protection": "+X-W+X"},
                 {"protection": "RX"}, {"alignment_type": 3},
                 {"alignment_type": 1, "alignment_parameter": "0"},
                 {"alignment_type": 2, "alignment_parameter": 8}, {"max_results": 0}]
        for kwargs in cases:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                memory.scan_matches("41", **kwargs)
        self.assertEqual(memory.read_calls, [])


@unittest.skipUnless(sys.platform == "win32", "owned Win32 allmatches scan")
class OwnedWindowsScanTests(unittest.TestCase):
    def test_owned_rw_and_rx_pages_nibble_patterns_alignment_and_all_matches(self):
        memory = ProcessMemory(Path(sys.executable).name, os.getpid())
        self.addCleanup(memory.close)
        address = memory.allocate(128)
        self.addCleanup(lambda: memory.release(address))
        data = bytearray(128)
        data[8:12], data[40:44] = bytes.fromhex("A14200FF"), bytes.fromhex("A44277FF")
        memory.write(address, bytes(data))
        pattern = "A? 42 ?? FF"
        expected = [address + 8, address + 40]
        self.assertEqual(memory.scan_matches(pattern, address, address + 128), expected)
        self.assertEqual(memory.scan_matches(pattern, address, address + 128, "+W-C", 1, "8"), expected)
        self.assertEqual(memory.scan_matches(pattern, address, address + 128, "+X"), [])
        memory.protect_allocation(address)
        self.assertEqual(memory.scan_matches(pattern, address, address + 128, "+X-W-C"), expected)
        self.assertEqual(memory.scan_matches(pattern, address, address + 128, "+W"), [])

    def test_owned_mixed_rwx_code_can_store_its_own_result(self):
        memory = ProcessMemory(Path(sys.executable).name, os.getpid())
        self.addCleanup(memory.close)
        address = memory.allocate(4096)
        self.addCleanup(lambda: memory.release(address))
        # mov eax,42; mov rdx,owneddata; mov [rdx],eax; ret -- self-owned fixture.
        code = bytes.fromhex("B82A00000048BA") + (address + 0x100).to_bytes(8, "little") + bytes.fromhex("8902C3")
        memory.write(address, code)
        memory.protect_allocation(address, executable=True, writable=True)
        self.assertEqual(ctypes.WINFUNCTYPE(ctypes.c_int)(address)(), 42)
        self.assertEqual(memory.read(address + 0x100, 4), (42).to_bytes(4, "little"))


if __name__ == "__main__":
    unittest.main()
