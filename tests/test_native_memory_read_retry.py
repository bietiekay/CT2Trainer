"""Native memory 0.39: the bounded transient-read retry.

Covers the 0.39 reliability lane in ``memory.ProcessMemory`` (the
``_read_exact`` retry loop, closing the documented open issue of the
0.38 ledger - the field-observed transient "ReadProcessMemory failed
(Win32 error 299)" on Proton):

- a transient read failure (the field-observed Win32 299 plus the
  snapshot-retry transient set 119 / 1116 / 24) is retried with the
  bounded exponential backoff until the read succeeds (through both
  the private ``_read_exact`` and the public ``read`` path);
- the budget is exactly four attempts; after the budget the ORIGINAL
  error is raised unchanged (fail-closed, no silent success);
- the backoff schedule is 0.05 / 0.1 / 0.2 seconds (capped at 0.25 s
  per attempt);
- a non-transient code (e.g. 5, access denied) fails immediately
  without a retry;
- a partial result (a successful call that transferred fewer bytes)
  is NOT retried - it is an unexpected state, not a transient error
  code.

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
    ERROR_BAD_LENGTH,
    ERROR_INVALID_ID,
    ERROR_MORE_DATA,
    ProcessMemoryError,
    _READ_MAX_ATTEMPTS,
)
from test_native_memory import _memory

DATA = bytes.fromhex("1122334455667788")


def _failing_read(code):
    """A kernel read that fails with the given Win32 error code."""
    def read(handle, address, buffer, size, transferred):
        ctypes.set_last_error(code)
        return False
    return read


def _succeeding_read(data=DATA):
    """A kernel read that transfers the full range."""
    def read(handle, address, buffer, size, transferred):
        assert size == len(data)
        ctypes.memmove(buffer, data, size)
        ctypes.cast(transferred,
                    ctypes.POINTER(ctypes.c_size_t)).contents.value = size
        return True
    return read


def _partial_read(size=8, transferred_count=4):
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


@unittest.skipUnless(sys.platform == "win32",
                     "the Win32 last-error API is required")
class TransientReadRetryTests(unittest.TestCase):
    """The bounded transient-read retry of 0.39."""

    def _memory_with_read(self, side_effect):
        memory = _memory()
        memory._kernel.ReadProcessMemory = Mock(side_effect=side_effect)
        return memory, memory._kernel.ReadProcessMemory

    def test_a_transient_read_is_retried_until_success(self):
        memory, read = self._memory_with_read(
            _sequence(_failing_read(299), _succeeding_read()))
        with patch("ct2trainer.native.memory.time.sleep") as sleeper:
            self.assertEqual(memory.read(0x1000, 8), DATA)
        self.assertEqual(read.call_count, 2)
        sleeper.assert_called_once_with(0.05)

    def test_a_transient_read_is_retried_on_the_public_read_path(self):
        # read() keeps the range check + the alive guards around the
        # retried _read_exact; the retry applies there too.
        memory, read = self._memory_with_read(
            _sequence(_failing_read(299), _failing_read(119),
                      _succeeding_read()))
        with patch("ct2trainer.native.memory.time.sleep"):
            self.assertEqual(memory.read(0x3000, 8), DATA)
        self.assertEqual(read.call_count, 3)

    def test_every_transient_code_gets_the_full_budget(self):
        for code in (299, ERROR_MORE_DATA, ERROR_BAD_LENGTH,
                     ERROR_INVALID_ID):
            with self.subTest(code=code):
                memory, read = self._memory_with_read(_failing_read(code))
                with patch("ct2trainer.native.memory.time.sleep") \
                        as sleeper:
                    with self.assertRaisesRegex(
                            ProcessMemoryError,
                            "Win32 error %d" % code):
                        memory.read(0x1000, 8)
                self.assertEqual(read.call_count,
                                 _READ_MAX_ATTEMPTS)
                self.assertEqual(len(sleeper.call_args_list),
                                 _READ_MAX_ATTEMPTS - 1)

    def test_the_backoff_is_exponential_and_bounded(self):
        memory, _ = self._memory_with_read(_failing_read(299))
        with patch("ct2trainer.native.memory.time.sleep") as sleeper:
            with self.assertRaises(ProcessMemoryError):
                memory.read(0x1000, 8)
        self.assertEqual([call.args[0] for call in sleeper.call_args_list],
                         [0.05, 0.1, 0.2])

    def test_a_non_transient_code_fails_immediately(self):
        memory, read = self._memory_with_read(_failing_read(5))
        with patch("ct2trainer.native.memory.time.sleep") as sleeper:
            with self.assertRaisesRegex(ProcessMemoryError,
                                        "Win32 error 5"):
                memory.read(0x1000, 8)
        self.assertEqual(read.call_count, 1)
        sleeper.assert_not_called()

    def test_a_partial_result_is_not_retried(self):
        memory, read = self._memory_with_read(_partial_read())
        with patch("ct2trainer.native.memory.time.sleep") as sleeper:
            with self.assertRaisesRegex(ProcessMemoryError, "partial"):
                memory.read(0x1000, 8)
        self.assertEqual(read.call_count, 1)
        sleeper.assert_not_called()


if __name__ == "__main__":
    unittest.main()
