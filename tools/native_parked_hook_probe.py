"""Verify disable while the owned fixture's sole caller is parked in a cave.

The parked coordinator is deliberately private to this test and this exact
launched fixture. It is not a generic game or suspended-thread coordinator.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import queue
import struct
import subprocess
import sys
import threading
import time

from ct2trainer.native.assembler import NasmAssembler
from ct2trainer.native.hooks import HookError, HookManager, QuiescenceProof
from ct2trainer.native.memory import ProcessMemory


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests/windows/hook_fixture"))
from coordinator import OwnedFixtureCoordinator


class ParkedCaveCoordinator:
    """Only the byte-pinned fixture's single caller can reach this cave.

    The first installed execution sets entered then loops without any call or
    entry jump while release is zero. This test never reuses that entered flag.
    Restoring the entry while the caller is in this loop is safe only because
    the executable cave is retained and the fixture has no second caller.
    """
    def __init__(self, target: Path, digest: str, identity: tuple[int, int],
                 entry: int, flags: int):
        self.target, self.digest = target.resolve(), digest
        self.identity, self.entry, self.flags = identity, entry, flags

    @contextmanager
    def hold(self, memory, ranges):
        if (memory.identity != self.identity or Path(memory._image_path()).resolve() != self.target
                or hashlib.sha256(self.target.read_bytes()).hexdigest() != self.digest
                or list(ranges) != [(self.entry, 7)]):
            raise HookError("The parked proof is restricted to this owned fixture entry.")
        check = lambda: (memory.identity == self.identity and memory.is_alive()
                         and memory.read(self.flags, 2) == b"\x01\x00")
        if check() is not True:
            raise HookError("The fixture caller is not parked inside this cave.")
        yield QuiescenceProof(self.identity, tuple(ranges), "owned-single-caller-parked-cave", check)
        if check() is not True:
            raise HookError("The fixture caller left its cave before entry restoration completed.")


def _wait(check, label, seconds=3):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(0.002)
    raise AssertionError(label)


def probe(target: Path, report_path: Path) -> dict:
    target, report_path = target.resolve(), report_path.resolve()
    if target.name != "NativeHookFixture.exe" or not target.is_file():
        raise ValueError("Only the owned built NativeHookFixture.exe is accepted")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if report_path.exists():
        raise FileExistsError(report_path)
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    report = {"schema": "ct2trainer-parked-cave-fixture/v1",
              "target_sha256": digest(target),
              "fixture_source_sha256": digest(ROOT / "tests/windows/hook_fixture/hook_target.c"),
              "probe_sha256": digest(Path(__file__)), "checks": [], "ce_inputs": [],
              "game_runtime_verified": False, "general_quiescence_verified": False}
    child = subprocess.Popen([str(target)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, creationflags=0x08000000)
    memory = None
    manager = None
    try:
        output = queue.Queue()
        threading.Thread(target=lambda: output.put(child.stdout.readline()), daemon=True).start()
        metadata = json.loads(output.get(timeout=3))
        if metadata["pid"] != child.pid:
            raise AssertionError("Fixture metadata PID differs from this launched child")
        memory = ProcessMemory("NativeHookFixture.exe", child.pid)
        result = lambda: struct.unpack("<i", memory.read(metadata["result"], 4))[0]
        calls = lambda: struct.unpack("<i", memory.read(metadata["calls"], 4))[0]
        _wait(lambda: result() == 4, "Original fixture function did not return 4")
        original = memory.read(metadata["entry"], 7)
        if original != bytes.fromhex("8bc183c0019090"):
            raise AssertionError("Owned fixture entry bytes changed")
        report["checks"].append("original_single_caller_function_returns_4")
        manager = HookManager(memory, report_path.with_suffix(".journal.json"),
                              OwnedFixtureCoordinator(target, report["target_sha256"]),
                              "owned-parked-cave-test")
        cave = manager.allocate("parkedcave", 4096, near=metadata["entry"])
        flags = manager.allocate("parkflags", 4096, near=metadata["entry"], executable=False)
        assembler = NasmAssembler()
        code = assembler.assemble(
            f"bits 64\norg {cave}\n"
            "push rdx\n"
            f"mov rdx,{flags}\n"
            "mov byte [rdx],1\n"
            "park:\ncmp byte [rdx+1],0\nje park\n"
            "mov eax,ecx\nadd eax,100\n"
            "mov dword [rdx+4],eax\nmov byte [rdx+2],1\n"
            "pop rdx\n"
            f"jmp {metadata['entry']+7}\n")
        entry = assembler.assemble(f"bits 64\norg {metadata['entry']}\njmp near {cave}\nnop\nnop\n")
        if len(entry) != 7:
            raise AssertionError("The owned fixture entry patch must be exactly seven bytes")
        manager.stage([
            {"address": cave, "bytes": code.hex(), "original": memory.read(cave, len(code)).hex(),
             "is_allocation": True, "executable": True, "requires_coordinator": False},
            {"address": flags, "bytes": bytes(8).hex(), "original": bytes(8).hex(),
             "is_allocation": True, "executable": False, "requires_coordinator": False},
            {"address": metadata["entry"], "bytes": entry.hex(), "original": original.hex(),
             "is_allocation": False, "executable": True, "requires_coordinator": True}],
            {"parkedcave": cave, "parkflags": flags})
        manager.publish()
        _wait(lambda: memory.read(flags, 2) == b"\x01\x00", "Caller did not park in injected cave")
        parked_calls = calls()
        time.sleep(0.025)
        if calls() != parked_calls:
            raise AssertionError("The fixture caller advanced while parked inside its cave")
        report["checks"].append("caller_parked_in_injected_cave_before_return")
        # Its normal event safe point waits for the sole caller to leave the
        # function. That must refuse here, without touching the entry bytes.
        try:
            manager.disable()
            raise AssertionError("Ordinary fixture safe point admitted a parked caller")
        except RuntimeError as exc:
            if "did not acknowledge" not in str(exc):
                raise
        if manager.state != "enabled" or memory.read(metadata["entry"], 7) != entry:
            raise AssertionError("Failed safe-point acquisition changed the installed entry")
        report["checks"].append("ordinary_safe_point_refuses_parked_caller_without_entry_write")
        manager.coordinator = ParkedCaveCoordinator(target, report["target_sha256"], memory.identity,
                                                    metadata["entry"], flags)
        manager.disable()
        if memory.read(metadata["entry"], 7) != original or memory.read(flags, 2) != b"\x01\x00":
            raise AssertionError("Entry was not restored while caller remained parked")
        if (memory.read(cave, len(code)) != code or not memory.is_executable(cave, len(code))
                or manager.allocations["parkedcave"]["state"] != "retained"):
            raise AssertionError("The executing cave was freed or made nonexecutable")
        report["checks"].append("entry_restored_while_caller_still_inside_retained_rx_cave")
        memory.write(flags + 1, b"\x01")
        _wait(lambda: calls() > parked_calls, "The in-flight call did not return after cave release")
        if (memory.read(flags + 2, 1) != b"\x01"
                or struct.unpack("<i", memory.read(flags + 4, 4))[0] != 103):
            raise AssertionError("The retained cave did not finish with its intended result")
        report["checks"].append("in_flight_call_finishes_103_through_retained_cave")
        _wait(lambda: calls() >= parked_calls + 2 and result() == 4,
              "Subsequent calls did not use the restored function")
        report["checks"].append("subsequent_calls_use_original_entry_and_return_4")
        report["target_identity"] = list(memory.identity)
        report["allocation"] = manager.allocation_map()
        report["observations"] = {"parked_calls": parked_calls, "final_calls": calls(),
                                  "cave_result": struct.unpack("<i", memory.read(flags + 4, 4))[0],
                                  "restored_result": result()}
        child.terminate()
        child.wait(timeout=5)
        manager.finish_after_exit()
        report["checks"].append("retained_journal_finalized_only_after_exact_target_exit")
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
    arguments = parser.parse_args()
    print(probe(arguments.target, arguments.report)["status"])
