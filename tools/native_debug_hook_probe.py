"""Owned x86/x64 debugger-coordinated hook stress, timeout, and detach gate."""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import queue
import struct
import subprocess
import threading
import time

from ct2trainer.native.assembler import NasmAssembler
from ct2trainer.native.debug_coordinator import DebugEventCoordinator
from ct2trainer.native.hooks import HookError, HookManager
from ct2trainer.native.memory import ProcessMemory


ROOT = Path(__file__).resolve().parents[1]


def _wait(check, message, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(0.002)
    raise AssertionError(message)


def _handles():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.GetProcessHandleCount.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetProcessHandleCount.restype = wintypes.BOOL
    count = wintypes.DWORD()
    if not kernel.GetProcessHandleCount(kernel.GetCurrentProcess(), ctypes.byref(count)):
        raise ctypes.WinError(ctypes.get_last_error())
    return count.value


def probe(target: Path, report_path: Path, cycles=10):
    target, report_path = target.resolve(), report_path.resolve()
    if target.name not in {"NativeDebugHookFixture-x64.exe", "NativeDebugHookFixture-x86.exe",
                           "NativeDebugFarHookFixture-x64.exe"}:
        raise ValueError("Only the owned built debugger stress fixture is accepted")
    far_jump = target.name == "NativeDebugFarHookFixture-x64.exe"
    if type(cycles) is not int or not 1 <= cycles <= 32:
        raise ValueError("Stress cycles require a bounded 1..32 count")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if report_path.exists():
        raise FileExistsError(report_path)
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    report = {"schema": "ct2trainer-debug-hook-fixture/v1", "checks": [],
              "fixture_source_sha256": digest(ROOT / ("tests/windows/debug_hook_fixture/hook_far_target.c"
                                                        if far_jump else "tests/windows/debug_hook_fixture/hook_stress_target.c")),
              "probe_sha256": digest(Path(__file__)), "target_sha256": digest(target), "ce_inputs": [],
              "game_runtime_verified": False, "saved_exception_contexts_verified": False,
              "future_interior_branches_verified": False, "far_jump": far_jump,
              "cycles": cycles, "observations": []}
    child = subprocess.Popen([str(target)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, creationflags=0x08000000)
    memory = None
    managers = []
    try:
        metadata_queue = queue.Queue()
        threading.Thread(target=lambda: metadata_queue.put(child.stdout.readline()), daemon=True).start()
        metadata = json.loads(metadata_queue.get(timeout=3))
        if metadata["pid"] != child.pid:
            raise AssertionError("Fixture metadata PID differs from this launched child")
        memory = ProcessMemory(target.name, child.pid)
        if memory.pointer_size != metadata["pointer_size"]:
            raise AssertionError("Held target and fixture pointer widths differ")
        report["pointer_size"] = memory.pointer_size
        get = lambda key: struct.unpack("<i", memory.read(metadata[key], 4))[0]
        _wait(lambda: get("calls") >= 30 and get("churn") >= 1 and get("result") == 4,
              "Concurrent owned callers did not reach original result")
        original = memory.read(metadata["entry"], metadata["entry_size"])
        expected = ("8bc183c001" + "90" * 9 if far_jump else
                    "8bc183c0019090" if memory.pointer_size == 8 else "8b44240483c0019090")
        if original.hex() != expected:
            raise AssertionError("The owned fixture instruction entry changed")
        report["checks"].append("concurrent_callers_and_dynamic_thread_churn_original_result_4")
        coordinator = DebugEventCoordinator()
        with coordinator.hold(memory, [(metadata["entry"], metadata["entry_size"])]) as proof:
            proof.verify(memory, [(metadata["entry"], metadata["entry_size"])])
            calls, churn = get("calls"), get("churn")
            time.sleep(0.05)
            if get("calls") != calls or get("churn") != churn:
                raise AssertionError("The OS debug event did not stop all owned callers/churn")
            try:
                with DebugEventCoordinator().hold(memory, [(metadata["entry"], metadata["entry_size"])]):
                    raise AssertionError("A conflicting debugger coordinator was admitted")
            except HookError as exc:
                if "already has a debugger" not in str(exc):
                    raise
        report["checks"].append("held_os_debug_event_freezes_all_calls_and_thread_creation")
        report["checks"].append("conflicting_debugger_refused_without_stealing_connection")
        expiry = DebugEventCoordinator(hold_timeout=0.05)
        with expiry.hold(memory, [(metadata["entry"], metadata["entry_size"])]) as proof:
            calls = get("calls")
            time.sleep(0.08)
            if proof.check() is not False or get("calls") != calls:
                raise AssertionError("Expired proof remained valid or resumed beneath the writer")
        _wait(lambda: get("calls") > calls, "Expired hold did not orderly detach/resume on context exit")
        report["checks"].append("lease_expiry_invalidates_proof_without_resuming_pending_writer")
        refused = HookManager(memory, report_path.with_name(report_path.stem + "-refused-call.journal.json"),
                              coordinator, "owned-call-refusal")
        replacement_call = bytes.fromhex("E800000000") + b"\x90" * (metadata["entry_size"] - 5)
        try:
            refused.stage([{"address": metadata["entry"], "bytes": replacement_call.hex(),
                            "original": original.hex(), "is_allocation": False,
                            "executable": True, "requires_coordinator": True}])
            raise AssertionError("A replacement entry call was admitted before publication")
        except HookError as exc:
            if "stronger return-context proof" not in str(exc):
                raise
        finally:
            refused.abandon_unpublished()
        if memory.read(metadata["entry"], metadata["entry_size"]) != original:
            raise AssertionError("Rejected replacement call altered the entry")
        report["checks"].append("replacement_entry_call_refused_before_any_live_mutation")
        before_handles = _handles()
        assembler = NasmAssembler()
        for cycle in range(cycles):
            manager = HookManager(memory,
                report_path.with_name(report_path.stem + f"-{cycle:02d}.journal.json"), coordinator,
                f"owned-debug-stress-{cycle}")
            managers.append(manager)
            cave = manager.allocate("newmem", 4096, near=metadata["entry"], writable=True)
            load = "mov eax,ecx" if memory.pointer_size == 8 else "mov eax,[esp+4]"
            bitness = memory.pointer_size * 8
            register = "rdx" if memory.pointer_size == 8 else "edx"
            code = assembler.assemble(f"bits {bitness}\norg {cave}\n{load}\nadd eax,100\n"
                                      f"mov {register},{cave + 0x300}\nmov dword [{register}],eax\n"
                                      f"jmp {metadata['entry'] + metadata['entry_size']}\n")
            patch = assembler.assemble(f"bits {bitness}\norg {metadata['entry']}\n"
                                       + (f"jmp qword [rel pointer]\npointer: dq {cave}\n" if far_jump else f"jmp near {cave}\n")
                                       + "nop\n" * (metadata["entry_size"] - (14 if far_jump else 5)))
            if len(patch) != metadata["entry_size"]:
                raise AssertionError("Fixture entry jump/padding size differs")
            manager.stage([
                {"address": cave, "bytes": code.hex(), "original": memory.read(cave, len(code)).hex(),
                 "is_allocation": True, "executable": True, "requires_coordinator": False},
                {"address": cave + 0x300, "bytes": bytes(4).hex(), "original": bytes(4).hex(),
                 "is_allocation": True, "executable": False, "requires_coordinator": False,
                 "literal_data_ranges": [{"address": cave + 0x300, "size": 4, "allocation": "newmem"}]},
                {"address": metadata["entry"], "bytes": patch.hex(), "original": original.hex(),
                 "is_allocation": False, "executable": True, "requires_coordinator": True}], {"newmem": cave})
            manager.publish()
            _wait(lambda: get("result") == 103, "Published concurrent hook did not return103")
            if struct.unpack("<i", memory.read(cave + 0x300, 4))[0] != 103:
                raise AssertionError("Mixed executable cave could not store its own live data")
            report["observations"].append(coordinator.last_observation)
            manager.check_entries()
            manager.disable()
            _wait(lambda: get("result") == 4, "Restored concurrent hook did not return4")
            if memory.read(metadata["entry"], metadata["entry_size"]) != original:
                raise AssertionError("Exact original instructions did not restore")
            if memory.read(cave, len(code)) != code or not memory.is_executable(cave, len(code)):
                raise AssertionError("A retired executable cave was reclaimed before target exit")
            if get("bad") != 0:
                raise AssertionError("A concurrent caller observed a torn/incorrect function result")
            report["observations"].append(coordinator.last_observation)
        after_handles = _handles()
        if after_handles > before_handles + 2:
            raise AssertionError(f"Debugger repeated holds leaked handles: {before_handles}->{after_handles}")
        report["checks"].append("repeated_debug_event_install_disable_preserves_all_concurrent_callers")
        report["checks"].append("mixed_rwx_cave_executes_and_stores_result_without_access_fault")
        report["checks"].append("retired_executable_caves_retained_and_no_debugger_handle_growth")
        if far_jump:
            report["checks"].append("exact_14_byte_inline_pointer_jump_installs_and_restores_with_full_ip_coverage")
        # Reject overwritten calls even if every present IP happens to be outside
        # their range; saved return addresses would otherwise remain unproven.
        uncalled = memory.allocate(64, near=metadata["entry"])
        try:
            memory.write(uncalled, bytes.fromhex("e800000000c3"))
            memory.protect_allocation(uncalled)
            try:
                with coordinator.hold(memory, [(uncalled, 5)]):
                    raise AssertionError("A displaced call lacked return-context refusal")
            except HookError as exc:
                if "stronger return-context proof" not in str(exc):
                    raise
        finally:
            memory.release(uncalled)
        report["checks"].append("displaced_call_refused_without_entry_write_or_target_kill")
        report["handles"] = {"before": before_handles, "after": after_handles}
        report["target_identity"] = list(memory.identity)
        report["final_counters"] = {key: get(key) for key in ("calls", "churn", "bad", "result")}
        # Controlled own fixture exit exercises debugger lifetime/cleanup without
        # terminating a process we did not launch.
        memory.write(metadata["stop"], struct.pack("<i", 1))
        child.wait(timeout=5)
        if child.returncode != 0 or memory.is_alive():
            raise AssertionError("The owned target did not exit normally with zero bad results")
        try:
            with coordinator.hold(memory, [(metadata["entry"], metadata["entry_size"])]):
                raise AssertionError("An exited target admitted a debugger write proof")
        except HookError as exc:
            if "exited" not in str(exc):
                raise
        for manager in managers:
            manager.finish_after_exit()
        report["checks"].append("target_exit_refuses_new_proof_and_finalizes_retained_receipts")
        report["status"] = "passed"
    except Exception as exc:
        report["status"], report["error"] = "failed", repr(exc)
        raise
    finally:
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=5)
        if memory:
            memory.close()
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--cycles", type=int, default=10)
    arguments = parser.parse_args()
    print(probe(arguments.target, arguments.report, arguments.cycles)["status"])
