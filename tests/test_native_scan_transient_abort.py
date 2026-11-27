"""Native memory 0.52.5: bounded scans abort on the first transient read failure.

Field case 2026-11-24 (The Great Circle): every trainer build after 0.41
crashed the game during the steady-state window while the bounded rearm
module scan was in flight.  The static replay proved activation and
steady-state target traffic byte-identical between 0.41 and 0.52.3; the
only new target-touching behaviour in the window is the 0.39 bounded
transient-read retry, which now also applied to every scan chunk.  A
transient ReadProcessMemory failure inside the 122 MB scan could add up
to three extra target reads plus backoff sleeps under the memory lock
before the scan gave up; before 0.39 the scan aborted on the first
attempt and backed off for the full rearm interval.

The 0.52.5 fix restores the pre-0.39 abort-on-first-transient-read
behaviour for the bounded scan paths only:

- ``read(..., retry_transient=False)`` raises the original error on the
  first transient failure (one kernel call, no backoff sleep);
- the default ``read()`` keeps the 0.39 retry (one-shot reads such as
  patch verification, pointer chains and write readback are unchanged);
- a non-transient code (e.g. 5, access denied) fails immediately in both
  modes, and a partial transfer is never retried;
- ``scan_module`` and ``scan_matches`` abort on the first transient read
  failure and record the abort context (address, module offset, Win32
  code, bytes scanned so far) in ``last_scan_diagnostics``;
- a completed scan replaces any stale abort context, so the engine's
  fresh-diagnostics identity check can distinguish "this scan died" from
  "an earlier scan died".

The kernel ``ReadProcessMemory`` is a Mock whose side effects set the
Win32 last error via ``ctypes.set_last_error``; the backoff sleep is
patched, so the tests stay fast and can assert the exact schedule.
"""
from __future__ import annotations

import ctypes
import sys
import unittest
from unittest.mock import Mock, patch

from ct2trainer.native.memory import (
    SCAN_CHUNK_SIZE,
    MEM_COMMIT,
    MEM_FREE,
    ProcessMemoryError,
    _SYSTEM_INFO,
)
from test_native_memory import _memory, _region

DATA = bytes.fromhex("1122334455667788")


def _failing_read(code):
    """A kernel read that fails with the given Win32 error code."""

    def read(handle, address, buffer, size, transferred):
        ctypes.set_last_error(code)
        return False

    return read


def _succeeding_read(data, base):
    """A kernel read that copies ``size`` bytes from ``data`` at ``address``."""

    def read(handle, address, buffer, size, transferred):
        offset = address - base
        ctypes.memmove(buffer, data[offset:offset + size], size)
        ctypes.cast(transferred,
                    ctypes.POINTER(ctypes.c_size_t)).contents.value = size
        return True

    return read


def _partial_read(size, transferred_count):
    """A kernel read that succeeds but transfers too few bytes."""

    def read(handle, address, buffer, size, transferred):
        ctypes.memmove(buffer, b"\x00" * size, size)
        ctypes.cast(transferred,
                    ctypes.POINTER(ctypes.c_size_t)).contents.value = \
            transferred_count
        return True

    return read


def _sequence(*reads):
    """A side effect that delegates one call to each read in order."""

    state = {"n": 0}

    def side_effect(*args):
        read = reads[state["n"]]
        state["n"] += 1
        return read(*args)

    return side_effect


def _scan_memory(regions, read_side_effect, module_name="owned.exe"):
    """A ProcessMemory with faked region queries and kernel reads.

    Keeps the real ``_read_exact`` so the transient-retry contract under
    test is the real one; only the kernel call is mocked.
    """
    memory = _memory()
    base, last = regions[0][0], regions[-1][0] + len(regions[-1][1])
    module_size = last - base

    def information(pointer):
        info = ctypes.cast(pointer, ctypes.POINTER(_SYSTEM_INFO)).contents
        info.minimum_address = 0
        info.maximum_address = last - 1

    memory._kernel.GetSystemInfo = information
    memory._kernel.ReadProcessMemory = Mock(side_effect=read_side_effect)

    def query(address):
        if address < base:
            return _region(0, base, 0, MEM_FREE)
        for start, raw, protection, state in regions:
            if start <= address < start + len(raw):
                return _region(start, len(raw), protection, state)
        raise AssertionError("Scan queried outside the exclusive range")

    memory._query = query
    memory.module = Mock(return_value=(base, module_size))
    return memory, base, last


@unittest.skipUnless(sys.platform == "win32",
                     "the Win32 last-error API is required")
class ReadRetryContractTests(unittest.TestCase):
    """The retry contract of 0.39, now with an explicit opt-out switch."""

    def _memory_with_read(self, side_effect):
        memory = _memory()
        memory._kernel.ReadProcessMemory = Mock(side_effect=side_effect)
        return memory, memory._kernel.ReadProcessMemory

    def test_retry_transient_disabled_aborts_on_first_failure(self):
        memory, read = self._memory_with_read(_failing_read(299))
        with patch("ct2trainer.native.memory.time.sleep") as sleeper:
            with self.assertRaisesRegex(ProcessMemoryError,
                                       "Win32 error 299"):
                memory.read(0x1000, 8, retry_transient=False)
        self.assertEqual(read.call_count, 1)
        sleeper.assert_not_called()

    def test_default_read_keeps_the_bounded_retry_and_backoff(self):
        memory, read = self._memory_with_read(
            _sequence(_failing_read(299), _failing_read(119),
                      _succeeding_read(DATA, 0x1000)))
        with patch("ct2trainer.native.memory.time.sleep") as sleeper:
            self.assertEqual(memory.read(0x1000, 8), DATA)
        self.assertEqual(read.call_count, 3)
        self.assertEqual([call.args[0] for call in sleeper.call_args_list],
                         [0.05, 0.1])

    def test_non_transient_code_fails_immediately_in_both_modes(self):
        for retry in (True, False):
            with self.subTest(retry_transient=retry):
                memory, read = self._memory_with_read(_failing_read(5))
                with patch("ct2trainer.native.memory.time.sleep") \
                        as sleeper:
                    with self.assertRaisesRegex(ProcessMemoryError,
                                                "Win32 error 5"):
                        memory.read(0x1000, 8, retry_transient=retry)
                self.assertEqual(read.call_count, 1)
                sleeper.assert_not_called()

    def test_partial_result_is_not_retried_with_retry_disabled(self):
        memory, read = self._memory_with_read(_partial_read(8, 4))
        with patch("ct2trainer.native.memory.time.sleep") as sleeper:
            with self.assertRaisesRegex(ProcessMemoryError, "partial"):
                memory.read(0x1000, 8, retry_transient=False)
        self.assertEqual(read.call_count, 1)
        sleeper.assert_not_called()


@unittest.skipUnless(sys.platform == "win32",
                     "the Win32 last-error API is required")
class ScanTransientAbortTests(unittest.TestCase):
    """The bounded scan paths abort on the first transient read failure."""

    def test_scan_module_aborts_on_transient_read_failure(self):
        memory, base, _ = _scan_memory(
            [(0x1000, b"\x00" * 4096, 0x04, MEM_COMMIT)],
            _failing_read(299))
        with patch("ct2trainer.native.memory.time.sleep") as sleeper:
            with self.assertRaisesRegex(ProcessMemoryError,
                                       "Win32 error 299"):
                memory.scan_module("owned.exe", "4142")
        # One chunk read, aborted on the first attempt: no retry, no sleep.
        self.assertEqual(memory._kernel.ReadProcessMemory.call_count, 1)
        sleeper.assert_not_called()
        diagnostics = memory.last_scan_diagnostics
        self.assertEqual(diagnostics["aborted_at"], hex(base))
        self.assertEqual(diagnostics["aborted_offset"], "0x0")
        self.assertEqual(diagnostics["aborted_win32"], 299)
        self.assertEqual(diagnostics["bytes_scanned"], 0)
        self.assertEqual(diagnostics["module"], "owned.exe")
        self.assertEqual(diagnostics["module_base"], base)
        self.assertEqual(diagnostics["match_count"], 0)

    def test_scan_module_aborts_immediately_on_non_transient_read(self):
        memory, _, _ = _scan_memory(
            [(0x1000, b"\x00" * 4096, 0x04, MEM_COMMIT)],
            _failing_read(5))
        with patch("ct2trainer.native.memory.time.sleep") as sleeper:
            with self.assertRaisesRegex(ProcessMemoryError, "Win32 error 5"):
                memory.scan_module("owned.exe", "4142")
        self.assertEqual(memory._kernel.ReadProcessMemory.call_count, 1)
        sleeper.assert_not_called()
        self.assertEqual(memory.last_scan_diagnostics["aborted_win32"], 5)

    def test_scan_module_success_records_bytes_scanned(self):
        data = b"\x00" * 10 + b"\x41\x42" + b"\x00" * (4096 - 12)
        base = 0x1000
        memory, _, _ = _scan_memory(
            [(base, data, 0x04, MEM_COMMIT)],
            _succeeding_read(data, base))
        address = memory.scan_module("owned.exe", "41 42")
        self.assertEqual(address, base + 10)
        diagnostics = memory.last_scan_diagnostics
        self.assertNotIn("aborted_at", diagnostics)
        self.assertEqual(diagnostics["bytes_scanned"], 4096)
        self.assertEqual(diagnostics["match_count"], 1)
        self.assertEqual(diagnostics["match_addresses"], [base + 10])

    def test_successful_scan_replaces_stale_abort_diagnostics(self):
        data = b"\x00" * 10 + b"\x41\x42" + b"\x00" * (4096 - 12)
        memory, _, _ = _scan_memory(
            [(0x1000, data, 0x04, MEM_COMMIT)],
            _failing_read(299))
        with self.assertRaises(ProcessMemoryError):
            memory.scan_module("owned.exe", "41 42")
        self.assertIn("aborted_at", memory.last_scan_diagnostics)
        memory._kernel.ReadProcessMemory = \
            Mock(side_effect=_succeeding_read(data, 0x1000))
        memory.scan_module("owned.exe", "41 42")
        self.assertNotIn("aborted_at", memory.last_scan_diagnostics)

    def test_scan_matches_aborts_on_transient_read_in_first_chunk(self):
        memory, base, last = _scan_memory(
            [(0x1000, b"\x00" * (2 * SCAN_CHUNK_SIZE), 0x04, MEM_COMMIT)],
            _failing_read(299))
        with patch("ct2trainer.native.memory.time.sleep") as sleeper:
            with self.assertRaisesRegex(ProcessMemoryError,
                                       "Win32 error 299"):
                memory.scan_matches("4142", start=base, end=last)
        self.assertEqual(memory._kernel.ReadProcessMemory.call_count, 1)
        sleeper.assert_not_called()
        diagnostics = memory.last_scan_diagnostics
        self.assertEqual(diagnostics["bytes_scanned"], 0)
        self.assertEqual(diagnostics["aborted_at"], hex(base))
        self.assertEqual(diagnostics["aborted_win32"], 299)

    def test_scan_matches_aborts_after_a_successful_chunk(self):
        data = b"\x00" * (2 * SCAN_CHUNK_SIZE)
        base = 0x1000
        memory, _, last = _scan_memory(
            [(base, data, 0x04, MEM_COMMIT)],
            _sequence(_succeeding_read(data, base), _failing_read(299)))
        with patch("ct2trainer.native.memory.time.sleep") as sleeper:
            with self.assertRaisesRegex(ProcessMemoryError,
                                       "Win32 error 299"):
                memory.scan_matches("4142", start=base, end=last)
        self.assertEqual(memory._kernel.ReadProcessMemory.call_count, 2)
        sleeper.assert_not_called()
        diagnostics = memory.last_scan_diagnostics
        self.assertEqual(diagnostics["bytes_scanned"], SCAN_CHUNK_SIZE)
        self.assertEqual(diagnostics["aborted_at"],
                         hex(base + SCAN_CHUNK_SIZE))
        self.assertEqual(diagnostics["aborted_win32"], 299)


if __name__ == "__main__":
    unittest.main()
