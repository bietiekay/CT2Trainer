"""Native memory 0.40: the bounded zero-transfer transient-write retry.

Covers the 0.40 reliability lane in ``memory.ProcessMemory`` (the
``_write_checked`` WPM retry loop, the write-side symmetry of the
0.39 transient-read retry):

- a write that FAILED with a transient code (the field-observed Win32
  299 plus the snapshot-retry transient set 119 / 1116 / 24) and
  transferred NOTHING is retried with the bounded exponential
  backoff until the write succeeds;
- the budget is exactly four attempts; after the budget the ORIGINAL
  error is raised unchanged into the existing uncertain-write
  protocol (fail-closed, no silent success; further writes are
  blocked by ``_write_uncertain``);
- the backoff schedule is 0.05 / 0.1 / 0.2 seconds (capped at 0.25 s);
- a write that FAILED with a transient code but transferred ANY bytes
  is NOT retried (a partial transfer is never retried - the "never
  silently retries" contract holds for every partial or non-
  transient failure);
- a non-transient code (e.g. 5, access denied) fails immediately
  without a retry;
- a successful call that transferred fewer bytes (a partial write) is
  NOT retried - it lands in the partial error as before.

The kernel ``WriteProcessMemory`` is a Mock whose side effects set the
Win32 last error via ``ctypes.set_last_error``; the backoff sleep is
patched, so the tests stay fast and can assert the exact schedule.
"""
from __future__ import annotations

import ctypes
import sys
import unittest
from unittest.mock import Mock, patch

from ct2trainer.native.memory import (
    ERROR_BAD_LENGTH,
    ERROR_INVALID_ID,
    ERROR_MORE_DATA,
    ProcessMemoryError,
    _WRITE_MAX_ATTEMPTS,
)
from test_native_memory import _memory, _region

DATA = bytes.fromhex("1122334455667788")


def _writer():
    """A memory whose write range is a single writable (0x04) region,
    so only the WriteProcessMemory call is exercised (no protection
    changes, no instruction flush; the readback verify is mocked)."""
    memory = _memory()
    memory._query = Mock(return_value=_region(0x1000, 4096, 0x04))
    memory._read_exact = Mock(return_value=DATA)
    return memory


def _failing_write(code, transferred_count=0):
    """A kernel write that fails with the given Win32 error code."""
    def write(handle, address, buffer, size, transferred):
        ctypes.set_last_error(code)
        ctypes.cast(transferred,
                    ctypes.POINTER(ctypes.c_size_t)).contents.value = \
            transferred_count
        return False
    return write


def _succeeding_write():
    """A kernel write that transfers the full range."""
    def write(handle, address, buffer, size, transferred):
        ctypes.memmove(buffer, DATA, size)
        ctypes.cast(transferred,
                    ctypes.POINTER(ctypes.c_size_t)).contents.value = size
        return True
    return write


def _partial_success():
    """A kernel write that succeeds but transfers too few bytes."""
    def write(handle, address, buffer, size, transferred):
        ctypes.memmove(buffer, DATA[:size - 1], size - 1)
        ctypes.cast(transferred,
                    ctypes.POINTER(ctypes.c_size_t)).contents.value = \
            size - 1
        return True
    return write


def _sequence(*writes):
    """A side effect that delegates one call to each write in order."""
    state = {"n": 0}

    def side_effect(*args):
        write = writes[state["n"]]
        state["n"] += 1
        return write(*args)
    return side_effect


@unittest.skipUnless(sys.platform == "win32",
                     "the Win32 last-error API is required")
class TransientWriteRetryTests(unittest.TestCase):
    """The bounded zero-transfer transient-write retry of 0.40."""

    def _memory_with_write(self, side_effect):
        memory = _writer()
        memory._kernel.WriteProcessMemory = Mock(side_effect=side_effect)
        return memory, memory._kernel.WriteProcessMemory

    def test_a_transient_write_failure_is_retried_until_success(self):
        memory, write = self._memory_with_write(
            _sequence(_failing_write(299), _succeeding_write()))
        with patch("ct2trainer.native.memory.time.sleep") as sleeper:
            memory.write(0x1000, DATA)
        self.assertEqual(write.call_count, 2)
        sleeper.assert_called_once_with(0.05)
        # The verified write left no uncertainty behind.
        self.assertFalse(memory._write_uncertain)
        memory._read_exact.assert_called_once_with(0x1000, len(DATA))

    def test_later_attempts_are_retried_with_the_growing_backoff(self):
        memory, write = self._memory_with_write(
            _sequence(_failing_write(299), _failing_write(119),
                      _succeeding_write()))
        with patch("ct2trainer.native.memory.time.sleep") as sleeper:
            memory.write(0x1000, DATA)
        self.assertEqual(write.call_count, 3)
        self.assertEqual([call.args[0] for call in sleeper.call_args_list],
                         [0.05, 0.1])

    def test_every_transient_code_gets_the_full_budget(self):
        for code in (299, ERROR_MORE_DATA, ERROR_BAD_LENGTH,
                     ERROR_INVALID_ID):
            with self.subTest(code=code):
                memory, write = self._memory_with_write(_failing_write(code))
                with patch("ct2trainer.native.memory.time.sleep") \
                        as sleeper:
                    with self.assertRaisesRegex(
                            ProcessMemoryError,
                            "Win32 error %d" % code):
                        memory.write(0x1000, DATA)
                self.assertEqual(write.call_count, _WRITE_MAX_ATTEMPTS)
                self.assertEqual(len(sleeper.call_args_list),
                                 _WRITE_MAX_ATTEMPTS - 1)
                # The original error landed in the uncertain protocol:
                # the memory is now write-blocked.
                self.assertTrue(memory._write_uncertain)
                with self.assertRaisesRegex(ProcessMemoryError,
                                            "previous write"):
                    memory.write(0x1000, DATA)
                self.assertEqual(write.call_count, _WRITE_MAX_ATTEMPTS)

    def test_the_backoff_is_exponential_and_bounded(self):
        memory, _ = self._memory_with_write(_failing_write(299))
        with patch("ct2trainer.native.memory.time.sleep") as sleeper:
            with self.assertRaises(ProcessMemoryError):
                memory.write(0x1000, DATA)
        self.assertEqual([call.args[0] for call in sleeper.call_args_list],
                         [0.05, 0.1, 0.2])

    def test_a_non_transient_code_fails_immediately(self):
        memory, write = self._memory_with_write(_failing_write(5))
        with patch("ct2trainer.native.memory.time.sleep") as sleeper:
            with self.assertRaisesRegex(ProcessMemoryError,
                                        "Win32 error 5"):
                memory.write(0x1000, DATA)
        self.assertEqual(write.call_count, 1)
        sleeper.assert_not_called()
        self.assertTrue(memory._write_uncertain)

    def test_a_failed_call_that_transferred_any_bytes_is_not_retried(self):
        # The transient code is not enough: the call must have moved
        # NOTHING for the retry to run (a partial transfer is never
        # retried - the original error lands in the uncertain
        # protocol, the "never silently retries" contract holds).
        memory, write = self._memory_with_write(
            _failing_write(299, transferred_count=3))
        with patch("ct2trainer.native.memory.time.sleep") as sleeper:
            with self.assertRaisesRegex(ProcessMemoryError,
                                        "Win32 error 299"):
                memory.write(0x1000, DATA)
        self.assertEqual(write.call_count, 1)
        sleeper.assert_not_called()

    def test_a_partial_success_is_not_retried(self):
        memory, write = self._memory_with_write(_partial_success())
        with patch("ct2trainer.native.memory.time.sleep") as sleeper:
            with self.assertRaisesRegex(ProcessMemoryError, "partial"):
                memory.write(0x1000, DATA)
        self.assertEqual(write.call_count, 1)
        sleeper.assert_not_called()


if __name__ == "__main__":
    unittest.main()
