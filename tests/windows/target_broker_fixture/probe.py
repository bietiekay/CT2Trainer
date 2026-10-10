"""Actual x86/AMD64 gates for the independently owned preloaded DLL broker.

Only our source-pinned build report is accepted; there is no game/process-name
argument and no arbitrary address invocation. Fresh reports survive failures.
"""
from __future__ import annotations
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import time
import subprocess

from ct2trainer.native.target_broker import (BrokerError, BrokerCancelled, BrokerUncertain,
    CallContext, Command, Operation, OwnedFixture, Status)
from ct2trainer.native.target_broker.protocol import MAIN_COMPLETE, WORKER_COMPLETE, TLS_CLEARED


def run(build_report, output_directory):
    directory = Path(output_directory).absolute()
    directory.mkdir(parents=True, exist_ok=False)
    report = {"schema": "ct2trainer-owned-target-broker-verification/v1", "status": "running",
        "build_report": str(Path(build_report).absolute()), "build_sha256": hashlib.sha256(Path(build_report).read_bytes()).hexdigest(),
        "checks": [], "scope": "Preloaded own DLL and owned Windows targets only; no Mono, IL2CPP, injection or game execution.",
        "one_shot": True, "saved_toggle": False}
    destination = directory / "verification.json"

    def save():
        raw = json.dumps(report, sort_keys=True, indent=2).encode("utf-8")
        if destination.exists():
            destination.write_bytes(raw)
        else:
            with destination.open("xb") as stream:
                stream.write(raw)

    def check(name, condition, **evidence):
        report["checks"].append({"name": name, "passed": bool(condition), **evidence})
        save()
        if not condition:
            raise AssertionError(name)

    save()
    active = None
    try:
        for architecture in ("x64", "x86"):
            active = OwnedFixture(build_report, architecture, directory / f"{architecture}-abi-receipts")
            broker = active.broker
            check(f"{architecture}:exact-process-and-ABI", broker.pointer_bits == (64 if architecture == "x64" else 32),
                  target=active.target, main_thread=broker.main_tid)
            vectors = [(Operation.CDECL_ADD, (-300, 319), 19),
                       (Operation.STDCALL_ADD, (-199, 222), 23),
                       (Operation.WIDE_RETURN, (0xFEDCBA98, 0x87654321), 0xFEDCBA9887654321),
                       (Operation.MIXED_FIVE, (1, 2.5, 3, 4.25, 5), 15.75),
                       (Operation.UTF16_ECHO, ("counted\0猫🙂",), "counted\0猫🙂")]
            last = None
            for operation, arguments, expected in vectors:
                context = CallContext.seconds(2)
                submitted = broker.submit(operation, arguments, context)
                result = broker.wait(submitted.request_id, context)
                last = result
                check(f"{architecture}:typed-{operation.name}", result.result() == expected and
                    result.flags & WORKER_COMPLETE and result.flags & TLS_CLEARED and result.tls_marker == result.request_id and
                    result.thread_id != broker.main_tid and result.thread_created > 0,
                    result=result.result(), thread=[result.thread_id, result.thread_created], call_count=result.call_count)
            for value in (True, False):
                context = CallContext.seconds(2)
                submitted = broker.submit(Operation.MAIN_BOOLEAN, (value,), context)
                result = broker.wait(submitted.request_id, context)
                check(f"{architecture}:host-main-{value}", result.result() == int(value) and
                    result.flags & MAIN_COMPLETE and result.thread_id == broker.main_tid and result.tls_marker == result.request_id,
                    thread=[result.thread_id, result.thread_created], call_count=result.call_count)
                last = result
            context = CallContext.seconds(2)
            submitted = broker.submit(Operation.MAIN_BOOLEAN_ON_WORKER, (True,), context)
            try:
                broker.wait(submitted.request_id, context)
                raise AssertionError("Wrong-affinity call succeeded")
            except BrokerError:
                refused = broker.observe(submitted.request_id, CallContext.seconds(1))
                check(f"{architecture}:wrong-affinity-refused-before-call", refused.status == Status.REFUSED and
                    refused.completed and refused.call_count == last.call_count,
                    status=int(refused.status), error=refused.error, call_count=refused.call_count)
                last = refused
            # The server, independently of client bookkeeping, rejects exact ID replay.
            original = broker.requests[1]
            duplicate = broker.transport.exchange(original, CallContext.seconds(1))
            check(f"{architecture}:target-replay-refused", duplicate.status == Status.REFUSED and duplicate.call_count == last.call_count,
                  replay_id=1, call_count=duplicate.call_count)
            for name, change in (("generation", {"generation": 2}), ("owner-created", {"owner_created": original.owner_created + 1}),
                                 ("target-created", {"target_created": original.target_created + 1}), ("nonce", {"nonce": bytes(16)})):
                foreign = broker.transport.exchange(replace(original, **change), CallContext.seconds(1))
                check(f"{architecture}:foreign-{name}-refused", foreign.status == Status.REFUSED and foreign.call_count == last.call_count)
            context = CallContext.seconds(2)
            submitted = broker.submit(Operation.CDECL_ADD, (4, 5), context, hold_start=True)
            broker.observe(submitted.request_id, CallContext.seconds(1), Command.CANCEL)
            try:
                broker.wait(submitted.request_id, context)
                raise AssertionError("Prestart cancellation ran")
            except BrokerCancelled:
                cancelled = broker.observe(submitted.request_id, CallContext.seconds(1))
                check(f"{architecture}:target-CAS-prestart-no-call", cancelled.status == Status.CANCELLED_BEFORE_START and
                    cancelled.completed and cancelled.call_count == last.call_count and not broker.uncertain,
                    request_id=cancelled.request_id, call_count=cancelled.call_count)
            # Original target admission deadline expires while gate is held.
            context = CallContext.seconds(0.15)
            submitted = broker.submit(Operation.CDECL_ADD, (8, 9), context, hold_start=True)
            time.sleep(0.18)
            try:
                broker.wait(submitted.request_id, CallContext.seconds(1))
                raise AssertionError("Expired target admission ran")
            except BrokerCancelled:
                cancelled = broker.observe(submitted.request_id, CallContext.seconds(1))
                check(f"{architecture}:absolute-target-deadline-no-call", cancelled.completed and
                    cancelled.status == Status.CANCELLED_BEFORE_START and cancelled.call_count == last.call_count,
                    absolute_deadline=broker.requests[submitted.request_id].deadline_qpc)
            check(f"{architecture}:continued-after-proven-no-call", broker.invoke(Operation.STDCALL_ADD, (3, 14), CallContext.seconds(2)) == 17)
            active.stop()
            check(f"{architecture}:ledger-and-handles-retained-to-exit", active.retention["requests"] == len(broker.requests) and
                  active.retention["worker_handles"] == len(broker.requests) - 2 and active.retention["live_workers"] == 0,
                  retention=active.retention)
            active = None
            check(f"{architecture}:normal-target-exit-receipt", bool(list((directory / f"{architecture}-abi-receipts").glob("*-target-exit.json"))))

            active = OwnedFixture(build_report, architecture, directory / f"{architecture}-timeout-receipts")
            broker = active.broker
            submitted = broker.submit(Operation.WAIT_ADD, (8, 11), CallContext.seconds(2))
            running = broker.observe(submitted.request_id, CallContext.seconds(1))
            while running.status == Status.PREPARED:
                time.sleep(0.001); running = broker.observe(submitted.request_id, CallContext.seconds(1))
            check(f"{architecture}:wait-call-running", running.status == Status.RUNNING and running.call_count == 1)
            try:
                broker.wait(submitted.request_id, CallContext(time.monotonic() - 1))
                raise AssertionError("Running timeout was treated as success")
            except BrokerUncertain:
                check(f"{architecture}:running-timeout-retained", broker.uncertain and bool(broker.requests), target=active.target)
            broker.observe(submitted.request_id, CallContext.seconds(1), Command.RELEASE)
            late = broker.wait(submitted.request_id, CallContext.seconds(1))
            check(f"{architecture}:late-completion-does-not-clear-uncertainty", late.result() == 19 and broker.uncertain and late.call_count == 1)
            try:
                broker.submit(Operation.CDECL_ADD, (1, 2), CallContext.seconds(1))
                raise AssertionError("Uncertain session accepted more work")
            except BrokerUncertain:
                check(f"{architecture}:new-work-blocked-after-timeout", True)
            active.stop()
            check(f"{architecture}:timeout-owned-buffer-retained-to-exit", active.retention["requests"] == 1 and
                  active.retention["worker_handles"] == 1 and active.retention["calls"] == 1,
                  retention=active.retention)
            active = None

            active = OwnedFixture(build_report, architecture, directory / f"{architecture}-ackloss-receipts")
            broker = active.broker
            try:
                broker.submit(Operation.CDECL_ADD, (10, 13), CallContext.seconds(2), drop_ack=True)
                raise AssertionError("Lost ACK was treated as success")
            except BrokerUncertain:
                pass
            observed = broker.observe(1, CallContext.seconds(1))
            deadline = time.monotonic() + 1
            while not observed.completed and time.monotonic() < deadline:
                observed = broker.observe(1, CallContext.seconds(1)); time.sleep(0.002)
            check(f"{architecture}:ACK-loss-exactly-once-observable", observed.completed and observed.result() == 23 and observed.call_count == 1 and broker.uncertain)
            replay = broker.transport.exchange(broker.requests[1], CallContext.seconds(1))
            check(f"{architecture}:ACK-loss-not-replayed", replay.status == Status.REFUSED and replay.call_count == 1)
            active.stop()
            check(f"{architecture}:ACK-loss-owned-buffer-retained-to-exit", active.retention["requests"] == 1 and
                  active.retention["worker_handles"] == 1 and active.retention["calls"] == 1,
                  retention=active.retention)
            active = None
            check(f"{architecture}:uncertain-target-exit-retains-receipts", bool(list((directory / f"{architecture}-ackloss-receipts").glob("*-uncertain.json"))) and
                  bool(list((directory / f"{architecture}-ackloss-receipts").glob("*-target-exit.json"))))
            # Independently terminate the owner, never the target. The child has
            # one prepared held request. The DLL alone owns no-call cancellation.
            owner_receipts = directory / f"{architecture}-owner-loss-receipts"
            helper = Path(__file__).with_name("owner_loss.py")
            owner = subprocess.Popen([sys.executable, str(helper), "--build-report", str(Path(build_report).absolute()),
                "--architecture", architecture, "--receipt-directory", str(owner_receipts)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                owner_stdout, owner_stderr = owner.communicate(timeout=8)
            except subprocess.TimeoutExpired:
                raise BrokerUncertain("Owner-loss diagnostic child did not finish; its exact evidence is retained.")
            check(f"{architecture}:owner-loss-fixture-created", owner.returncode == 0 and not owner_stderr,
                  owner_stdout=owner_stdout.decode("utf-8", errors="replace"), owner_stderr=owner_stderr.decode("utf-8", errors="replace"))
            metadata = json.loads(owner_stdout)
            from ct2trainer.native.target_broker.client import _Windows
            windows = _Windows()
            target_handle = windows.open_process(metadata["target"][0])
            try:
                check(f"{architecture}:owner-loss-exact-target-identity", windows.created(target_handle) == metadata["target"][1])
                check(f"{architecture}:owner-loss-target-exit-proven", windows.k.WaitForSingleObject(target_handle, 3000) == 0,
                      target=metadata["target"])
                lines = [json.loads(line) for line in (owner_receipts / "target.stdout.jsonl").read_bytes().splitlines()]
                retained = lines[-1]
                check(f"{architecture}:owner-loss-target-cancelled-before-call", retained["owner_alive"] == 0 and
                    retained["calls"] == 0 and retained["requests"] == 1 and retained["cancelled"] == 1 and
                    retained["worker_handles"] == 1 and retained["live_workers"] == 0, retention=retained)
            finally:
                windows.k.CloseHandle(target_handle); windows.k.CloseHandle(windows.owner_handle)
        report["status"] = "passed"
        report["check_count"] = len(report["checks"])
        save()
        return report
    except Exception as exc:
        report["status"] = "failed"
        report["failure"] = {"type": type(exc).__name__, "message": str(exc)}
        if active is not None:
            try:
                active.stop()
            except Exception as stop_error:
                report["stop_failure"] = str(stop_error)
        save()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-report", required=True)
    parser.add_argument("--output-directory", required=True)
    args = parser.parse_args()
    result = run(args.build_report, args.output_directory)
    print(json.dumps({"status": result["status"], "checks": result["check_count"]}))


if __name__ == "__main__":
    main()
