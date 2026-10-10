"""Debugger thread ownership and cleanup on rejected/uncertain OS operations."""
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

from ct2trainer.native.debug_coordinator import (
    DBG_CONTINUE, DebugEventCoordinator, _DebugEvent, _check_overwrite_windows, _check_literal_windows,
    _check_data_windows,
)
from ct2trainer.native.hooks import HookError, HookUncertain


class _Memory:
    pid = 17
    identity = (17, 123)
    pointer_size = 8
    _handle = 91

    def is_alive(self):
        return True

    def resolve_export(self, module, export, **kwargs):
        return 0x500000


class LiteralWindowTests(unittest.TestCase):
    def test_owned_literal_call_bytes_are_data_with_full_executable_exclusion(self):
        class Memory:
            def is_executable(self, address, size):
                return 0x1000 <= address and address + size <= 0x2000
            def read(self, address, size):
                return b'\xE8\xCC\xFF\x00'[:size]
        original = b'\xE8\xCC\xFF\x00'
        windows = ((0x1100, original, b'\x01\x00\x00\x00', original),)
        # E8/CC would be refused as displaced instructions, but exact
        # linker-proven literals require owner-allocation IP exclusion instead.
        _check_literal_windows(Memory(), windows, ((0x1000, 0x1000),))
        with self.assertRaisesRegex(HookError, 'owner exclusion'):
            _check_literal_windows(Memory(), windows, ((0x1000, 0x100),))
        with self.assertRaisesRegex(HookError, 'exact data'):
            _check_literal_windows(Memory(), ((0x1100, original, b'\x01' * 4, b'\x01' * 4),),
                                   ((0x1000, 0x1000),))

    def test_overlapping_code_data_receipts_are_refused_before_debug_attach(self):
        coordinator = DebugEventCoordinator()
        original = b'\x90' * 4
        with self.assertRaisesRegex(HookError, 'overlap'):
            coordinator.hold_entries(_Memory(), ((0x1100, original, original, original),),
                                     literal_windows=((0x1102, original, original, original),),
                                     exclusion_ranges=((0x1000, 0x1000),))


class _DataMemory(_Memory):
    def __init__(self):
        self.queries, self.reads = [], []

    def is_executable(self, address, size):
        self.queries.append((address, size))
        return False

    def read(self, address, size):
        self.reads.append((address, size))
        return (b'\xE8\xCC\xFF\x00' * ((size + 3) // 4))[:size]

    def write(self, *args):
        raise AssertionError('A data coordinator must never write target memory')


class DataWindowTests(unittest.TestCase):
    def test_literal_instruction_like_bytes_are_admitted_without_instruction_decoding(self):
        memory = _DataMemory()
        with patch('ct2trainer.native.debug_coordinator.validate_entry_control_flow', side_effect=AssertionError('decoded data')):
            _check_data_windows(memory, [(0x1000, 4), (0x1004, 2)])
        self.assertEqual(memory.queries, [(0x1000, 4), (0x1004, 2)])
        self.assertEqual(memory.reads, memory.queries)

    def test_data_bounds_overlap_and_total_are_rejected_without_target_access(self):
        malformed = (None, [], [(0, 1)], [(True, 1)], [(0x1000, True)], [(0x1000, 0)],
                     [(0x1000, 65537)], [(0x7FFFFFFFFFFF, 2)], [(0x1000,)],
                     [(0x1000, 4), (0x1003, 2)], [(0x1000, 4), (0x1000, 4)],
                     [(0x1000 + index * 65536, 65536) for index in range(17)])
        for ranges in malformed:
            memory = _DataMemory()
            with self.subTest(ranges=ranges), self.assertRaises(HookError):
                _check_data_windows(memory, ranges)
            self.assertFalse(memory.queries)
            self.assertFalse(memory.reads)

    def test_executable_unknown_uncommitted_and_unreadable_windows_are_refused(self):
        for result in (True, None, 0):
            memory = _DataMemory()
            memory.is_executable = lambda *args: result
            with self.subTest(classification=result), self.assertRaisesRegex(HookError, 'Executable or unclassified'):
                _check_data_windows(memory, [(0x1000, 4)])
        for error in (OSError('region is not committed'), OSError('PAGE_GUARD'), OSError('PAGE_NOACCESS')):
            memory = _DataMemory()
            memory.is_executable = lambda *args: (_ for _ in ()).throw(error)
            with self.subTest(error=error), self.assertRaisesRegex(HookError, 'committed readable'):
                _check_data_windows(memory, [(0x1000, 4)])
            self.assertFalse(memory.reads)
        for result in (b'\x00', bytearray(4), None):
            memory = _DataMemory()
            memory.read = lambda *args: result
            with self.subTest(transfer=result), self.assertRaisesRegex(HookError, 'exact readable'):
                _check_data_windows(memory, [(0x1000, 4)])


class _Kernel:
    def __init__(self):
        self.calls = []
        self.attach_ok = self.detach_ok = self.kill_policy_ok = True
        self.debugger_present = False
        self.events = []
        create = _DebugEvent()
        create.code, create.pid, create.tid = 3, 17, 19
        create.info.create_process.file = 101
        create.info.create_process.process = 102
        create.info.create_process.thread = 103
        initial = _DebugEvent()
        initial.code, initial.pid, initial.tid = 1, 17, 19
        initial.info.exception.record.code = 0x80000003
        initial.info.exception.record.address = 0x500000
        self.events.extend([create, initial])

    def record(self, name, *args):
        self.calls.append((name, threading.get_ident(), args))

    def CheckRemoteDebuggerPresent(self, handle, present):
        self.record("CheckRemoteDebuggerPresent", handle)
        ctypes.cast(present, ctypes.POINTER(ctypes.c_long)).contents.value = self.debugger_present
        return True

    def DebugActiveProcess(self, pid):
        self.record("DebugActiveProcess", pid)
        return self.attach_ok

    def DebugSetProcessKillOnExit(self, value):
        self.record("DebugSetProcessKillOnExit", value)
        return self.kill_policy_ok

    def WaitForDebugEvent(self, destination, milliseconds):
        self.record("WaitForDebugEvent", milliseconds)
        if self.events:
            event = self.events.pop(0)
            ctypes.memmove(destination, ctypes.byref(event), ctypes.sizeof(event))
            return True
        ctypes.set_last_error(121)
        time.sleep(0.001)
        return False

    def ContinueDebugEvent(self, pid, tid, status):
        self.record("ContinueDebugEvent", pid, tid, status)
        return True

    def DebugActiveProcessStop(self, pid):
        self.record("DebugActiveProcessStop", pid)
        return self.detach_ok

    def CloseHandle(self, handle):
        self.record("CloseHandle", handle)
        return True


class EntryWindowTests(unittest.TestCase):
    def test_inline_jump_data_is_admitted_only_with_exact_owned_receipt(self):
        original = b"\x90" * 15
        replacement = bytes.fromhex("FF2500000000") + (0x7FFFE8CCCCCC).to_bytes(8, "little") + b"\x90"
        memory = _Memory()
        memory.is_executable = lambda address, size: True
        memory.read = lambda address, size: replacement
        with self.assertRaises(HookError):
            _check_overwrite_windows(memory, [(0x1000, 15)])
        _check_overwrite_windows(memory, [(0x1000, 15)], ((0x1000, original, replacement, replacement),))
        memory.read = lambda address, size: b"\x90" * size
        with self.assertRaisesRegex(HookError, "receipt differs"):
            _check_overwrite_windows(memory, [(0x1000, 15)], ((0x1000, original, replacement, replacement),))

    def test_receipt_original_call_and_replacement_call_are_both_refused(self):
        nop = b"\x90" * 14
        call = bytes.fromhex("E800000000") + b"\x90" * 9
        memory = _Memory()
        memory.is_executable = lambda address, size: True
        for original, replacement in ((call, nop), (nop, call)):
            memory.read = lambda address, size: replacement
            with self.subTest(original=original.hex()), self.assertRaisesRegex(HookError, "return-context"):
                _check_overwrite_windows(memory, [(0x1000, 14)], ((0x1000, original, replacement, replacement),))


@unittest.skipUnless(sys.platform == "win32", "Win32 debugger cleanup API contract")
class DebugCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.kernel = _Kernel()
        self.memory = _Memory()
        self.api = patch("ct2trainer.native.debug_coordinator._api", return_value=self.kernel)
        self.windows = patch("ct2trainer.native.debug_coordinator._check_overwrite_windows")
        self.contexts = patch("ct2trainer.native.debug_coordinator._check_contexts", return_value={19: 0x700000})
        self.api.start()
        self.windows.start()
        self.contexts.start()
        self.addCleanup(self.api.stop)
        self.addCleanup(self.windows.stop)
        self.addCleanup(self.contexts.stop)

    def test_attach_event_continue_and_detach_have_one_dedicated_owner_thread(self):
        caller = threading.get_ident()
        coordinator = DebugEventCoordinator()
        with coordinator.hold(self.memory, [(0x1000, 5)]) as proof:
            self.assertTrue(proof.check())
            names = [name for name, _, _ in self.kernel.calls]
            self.assertEqual(names[:3], ["CheckRemoteDebuggerPresent", "DebugActiveProcess", "DebugSetProcessKillOnExit"])
            self.assertNotIn("DebugActiveProcessStop", names)
        self.assertFalse(proof.check())
        owners = {owner for _, owner, _ in self.kernel.calls}
        self.assertEqual(len(owners), 1)
        self.assertNotIn(caller, owners)
        self.assertIn(("DebugSetProcessKillOnExit", False),
                      [(name, args[0]) for name, _, args in self.kernel.calls if args])
        self.assertIn("DebugActiveProcessStop", [name for name, _, _ in self.kernel.calls])

    def test_expired_lease_does_not_continue_pending_event_until_context_exit(self):
        coordinator = DebugEventCoordinator(hold_timeout=0.05)
        with coordinator.hold(self.memory, [(0x1000, 5)]) as proof:
            continued = len([name for name, _, _ in self.kernel.calls if name == "ContinueDebugEvent"])
            expired = time.monotonic() + 1
            with patch('ct2trainer.native.debug_coordinator.time.monotonic', return_value=expired):
                self.assertFalse(proof.check())
            self.assertEqual(continued, len([name for name, _, _ in self.kernel.calls if name == "ContinueDebugEvent"]))
        self.assertFalse(proof.check())

    def test_context_failure_continues_owned_attach_break_and_orderly_detaches(self):
        self.contexts.stop()
        with patch("ct2trainer.native.debug_coordinator._check_contexts", side_effect=HookError("context uncertain")):
            with self.assertRaisesRegex(HookError, "context uncertain"):
                with DebugEventCoordinator().hold(self.memory, [(0x1000, 5)]):
                    self.fail("An uncertain context must not expose a write proof")
        statuses = [args[-1] for name, _, args in self.kernel.calls if name == "ContinueDebugEvent"]
        self.assertTrue(statuses)
        self.assertEqual(statuses[-1], DBG_CONTINUE)
        self.assertIn("DebugActiveProcessStop", [name for name, _, _ in self.kernel.calls])

    def test_acquisition_timeout_detaches_without_proof(self):
        self.kernel.events = []
        with self.assertRaisesRegex(HookError, "timed out"):
            with DebugEventCoordinator(acquire_timeout=0.05).hold(self.memory, [(0x1000, 5)]):
                self.fail("A timed-out acquisition must not expose a proof")
        self.assertIn("DebugActiveProcessStop", [name for name, _, _ in self.kernel.calls])

    def test_existing_debugger_is_refused_before_attach(self):
        self.kernel.debugger_present = True
        with self.assertRaisesRegex(HookError, "already has a debugger"):
            with DebugEventCoordinator().hold(self.memory, [(0x1000, 5)]):
                self.fail("A debugger conflict must not expose a proof")
        self.assertNotIn("DebugActiveProcess", [name for name, _, _ in self.kernel.calls])

    def test_kill_policy_failure_attempts_detach_before_owner_thread_exits(self):
        self.kernel.kill_policy_ok = False
        with self.assertRaisesRegex(HookError, "KillOnExit"):
            with DebugEventCoordinator().hold(self.memory, [(0x1000, 5)]):
                self.fail("A default kill-on-exit policy must not expose a proof")
        self.assertIn("DebugActiveProcessStop", [name for name, _, _ in self.kernel.calls])

    def test_failed_detach_returns_uncertainty_to_controller(self):
        self.kernel.detach_ok = False
        with self.assertRaisesRegex(HookUncertain, "detach cleanup"):
            with DebugEventCoordinator().hold(self.memory, [(0x1000, 5)]) as proof:
                self.assertTrue(proof.check())

    def test_default_kill_policy_and_detach_failure_keep_owner_alive_until_detach_succeeds(self):
        self.kernel.kill_policy_ok = False
        attempts = []
        def detach(pid):
            self.kernel.record("DebugActiveProcessStop", pid)
            attempts.append(threading.get_ident())
            return len(attempts) >= 3
        self.kernel.DebugActiveProcessStop = detach
        with self.assertRaisesRegex(HookUncertain, "detach cleanup"):
            with DebugEventCoordinator().hold(self.memory, [(0x1000, 5)]):
                self.fail("Unsafe default policy must never expose a proof")
        self.assertEqual(len(attempts), 3)
        self.assertEqual(len(set(attempts)), 1)
        self.assertNotEqual(attempts[0], threading.get_ident())

    def test_unknown_liveness_does_not_exit_owner_under_default_kill_policy(self):
        self.kernel.kill_policy_ok = False
        observations = []
        def alive():
            if not observations:
                observations.append(True)
                return True
            raise OSError("liveness query became unavailable")
        self.memory.is_alive = alive
        attempts = []
        def detach(pid):
            attempts.append(pid)
            return len(attempts) >= 3
        self.kernel.DebugActiveProcessStop = detach
        with self.assertRaisesRegex(HookUncertain, "detach cleanup"):
            with DebugEventCoordinator().hold(self.memory, [(0x1000, 5)]):
                self.fail("Uncertain default kill policy must never expose a proof")
        self.assertEqual(len(attempts), 3)

    def test_caller_exception_still_continues_and_detaches(self):
        with self.assertRaisesRegex(HookError, "caller failed"):
            with DebugEventCoordinator().hold(self.memory, [(0x1000, 5)]):
                raise HookError("caller failed")
        self.assertIn("DebugActiveProcessStop", [name for name, _, _ in self.kernel.calls])

    def test_own_trainer_process_cannot_be_debug_paused(self):
        self.memory.pid = os.getpid()
        with self.assertRaisesRegex(HookError, "own Python"):
            with DebugEventCoordinator().hold(self.memory, [(0x1000, 5)]):
                self.fail("The trainer must not pause itself")
        self.assertEqual(self.kernel.calls, [])

    def test_data_hold_rechecks_regions_at_real_event_and_observes_all_contexts(self):
        memory = _DataMemory()
        coordinator = DebugEventCoordinator()
        ranges = ((0x1000, 4), (0x2000, 2))
        with patch('ct2trainer.native.debug_coordinator._check_overwrite_windows', side_effect=AssertionError('decoded data')):
            with coordinator.hold_data(memory, list(ranges)) as proof:
                self.assertTrue(proof.check())
                self.assertEqual(proof.ranges, ranges)
                self.assertEqual(proof.identity, memory.identity)
                self.assertEqual(proof.mechanism, 'win32-debug-event-data-IP-checked')
                proof.verify(memory, ranges)
        self.assertEqual(memory.queries, list(ranges) * 2)
        self.assertEqual(memory.reads, list(ranges) * 2)
        self.assertFalse(proof.check())
        self.assertEqual(coordinator.last_observation['thread_contexts'], {19: 0x700000})
        self.assertEqual(coordinator.last_observation['context_policy'], 'all-IP-outside-committed-nonexecutable-data')

    def test_executable_data_hold_is_refused_before_attach_and_cannot_bypass_recheck(self):
        memory = _DataMemory()
        memory.is_executable = lambda *args: True
        with self.assertRaisesRegex(HookError, 'Executable'):
            with DebugEventCoordinator().hold_data(memory, [(0x1000, 4)]):
                self.fail('Executable pages cannot be admitted as ordinary data')
        self.assertFalse(self.kernel.calls)
        responses = iter((False, True))
        memory.is_executable = lambda *args: next(responses)
        with self.assertRaisesRegex(HookError, 'Executable'):
            with DebugEventCoordinator().hold_data(memory, [(0x1000, 4)]):
                self.fail('A changed page protection must not expose a proof')
        names = [name for name, _, _ in self.kernel.calls]
        self.assertIn('DebugActiveProcessStop', names)
        self.assertEqual(names.count('ContinueDebugEvent'), 2)

    def test_data_lease_expiry_waits_for_caller_release_and_cleanup_survives_caller_error(self):
        coordinator = DebugEventCoordinator(hold_timeout=.05)
        with self.assertRaisesRegex(HookError, 'caller failed'):
            with coordinator.hold_data(_DataMemory(), [(0x1000, 4)]) as proof:
                continued = sum(name == 'ContinueDebugEvent' for name, _, _ in self.kernel.calls)
                with patch('ct2trainer.native.debug_coordinator.time.monotonic', return_value=time.monotonic() + 1):
                    self.assertFalse(proof.check())
                self.assertEqual(continued, sum(name == 'ContinueDebugEvent' for name, _, _ in self.kernel.calls))
                raise HookError('caller failed')
        self.assertFalse(proof.check())
        self.assertIn('DebugActiveProcessStop', [name for name, _, _ in self.kernel.calls])


@unittest.skipUnless(sys.platform == 'win32' and ctypes.sizeof(ctypes.c_void_p) == 8, 'owned real Windows data quiescence gate')
class OwnedDataQuiescenceTests(unittest.TestCase):
    def test_real_owned_process_buffer_stops_while_debug_event_is_held_and_resumes(self):
        from ct2trainer.native.memory import ProcessMemory
        source = '''import ctypes,json,os,sys,threading,time
value=ctypes.c_uint64(0)
k=ctypes.WinDLL('kernel32',use_last_error=True)
k.VirtualAlloc.argtypes=(ctypes.c_void_p,ctypes.c_size_t,ctypes.c_uint32,ctypes.c_uint32)
k.VirtualAlloc.restype=ctypes.c_void_p
k.VirtualFree.argtypes=(ctypes.c_void_p,ctypes.c_size_t,ctypes.c_uint32)
k.VirtualFree.restype=ctypes.c_int
executable=k.VirtualAlloc(None,4096,0x3000,0x40)
reserved=k.VirtualAlloc(None,4096,0x2000,0x04)
inaccessible=k.VirtualAlloc(None,4096,0x3000,0x01)
assert executable and reserved and inaccessible
stop=threading.Event()
def update():
    while not stop.is_set():
        value.value+=1
        time.sleep(.002)
worker=threading.Thread(target=update)
worker.start()
print(json.dumps({'pid':os.getpid(),'address':ctypes.addressof(value),
                  'executable':executable,'reserved':reserved,'inaccessible':inaccessible}),flush=True)
sys.stdin.read(1)
stop.set()
worker.join()
for address in (executable,reserved,inaccessible):
    assert k.VirtualFree(address,0,0x8000)
'''
        # Windows venv python.exe is a launcher with a different child PID.
        # Start its actual interpreter so our owned target identity is exact.
        executable = Path(getattr(sys, '_base_executable', sys.executable))
        child = subprocess.Popen([str(executable), '-u', '-c', source], stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        memory = None
        try:
            metadata = json.loads(child.stdout.readline())
            self.assertEqual(metadata['pid'], child.pid)
            memory = ProcessMemory(executable.name, pid=child.pid)
            address = metadata['address']
            coordinator = DebugEventCoordinator()
            for field in ('executable', 'reserved', 'inaccessible'):
                with self.subTest(real_region=field), self.assertRaises(HookError):
                    with coordinator.hold_data(memory, [(metadata[field], 4)]):
                        self.fail('A forbidden real target region exposed a data proof')
                self.assertFalse(coordinator.last_observation, 'Invalid regions must be rejected before debugger attach')
                self.assertTrue(memory.is_alive())
            with coordinator.hold_data(memory, [(address, 8)]) as proof:
                proof.verify(memory, [(address, 8)])
                value = memory.read(address, 8)
                time.sleep(.05)
                self.assertEqual(memory.read(address, 8), value)
                self.assertTrue(memory.is_alive())
                self.assertTrue(proof.check())
            self.assertFalse(proof.check())
            self.assertGreaterEqual(len(coordinator.last_observation['thread_contexts']), 2)
            deadline = time.monotonic() + 2
            while memory.read(address, 8) == value and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertNotEqual(memory.read(address, 8), value)
            self.assertTrue(memory.is_alive())
        finally:
            if child.poll() is None:
                child.stdin.write('q')
                child.stdin.flush()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.terminate()
                    child.wait(timeout=5)
            if memory is not None:
                memory.close()
            child.stdin.close()
            child.stdout.close()


if __name__ == "__main__":
    unittest.main()
