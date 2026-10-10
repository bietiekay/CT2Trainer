"""Optional integration gate restricted to CT2Trainer's byte-pinned owned CT."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

# Re-pinned 2026-10-07 after the TFRG->CT2T marker rename in fixture.ct.
FIXTURE_CT_SHA256 = "418ba44f2fbfd11c2a8857909a807e519c2a87d1e974e991d1fb268df6a0e92f"


def run_probe(plan: dict, target: str | Path, report: str | Path) -> dict:
    from .engine import TrainerEngine, NativeRuntimeError
    from .memory import ProcessMemory
    target = Path(target).resolve()
    report = Path(report).resolve()
    if plan.get("table_sha256") != FIXTURE_CT_SHA256 or target.name != "FixtureTarget.exe" or plan.get("process_name") != target.name:
        raise ValueError("Integration probe requires the owned, byte-pinned fixture CT and FixtureTarget.exe.")
    observations = []
    process = None
    engine = None
    reader = None
    state_dir = Path(tempfile.mkdtemp(prefix="ct2trainer-fixture-"))
    def start_target():
        return subprocess.Popen([str(target)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                creationflags=subprocess.CREATE_NO_WINDOW)
    def connect(trainer):
        for _ in range(30):
            trainer.poll()
            if trainer.connected:
                return
            time.sleep(0.1)
        raise AssertionError(trainer.status)
    def note(name, **fields):
        observations.append({"check": name, "passed": True, **fields})
    try:
        process = start_target()
        engine = TrainerEngine(plan, state_dir=state_dir)
        connect(engine)
        first_pid = process.pid
        assert engine.memory.pid == first_pid
        reader = ProcessMemory(target.name, pid=first_pid)
        address = reader.scan_module(target.name, "43 54 32 54 2D 46 49 58 2D 32 30 32 36 2D 30 31")
        assert int.from_bytes(reader.read(address + 16, 4), "little") == 1234
        note("unique-process-attach-and-aob", pid=first_pid, created=reader.creation_time, address=address)
        engine.toggle(0, True)
        assert engine.set_value(2, "4321") == "4321"
        assert int.from_bytes(reader.read(address + 16, 4), "little") == 4321
        note("independent-value-readback", value=4321)
        host = engine.open_lua_session()
        assert host.execute('return getAddressList().getMemoryRecordByID(2).Value') == '4321'
        host.execute('getAddressList().getMemoryRecordByID(2).Value="5432"')
        assert int.from_bytes(reader.read(address + 16, 4), 'little') == 5432
        host.execute('getAddressList().getMemoryRecordByID(2).Value="4321"')
        note('upstream-lua53-record-write-and-independent-readback', value=5432)
        host.execute('worker=createThread(function(thread) local r=getAddressList().getMemoryRecordByID(2); r.Value="6543"; sleep(10); r.Value="4321"; thread.terminate() end)')
        host.tick(0)
        assert reader.read(address+16,4)==(6543).to_bytes(4,'little')
        host.tick(10)
        assert reader.read(address+16,4)==(4321).to_bytes(4,'little')
        assert host.execute('return worker.Terminated') is True
        note('owned-lua-worker-sleep-write-and-termination')
        scan_source=('local m=createMemScan(); local f=createFoundList(m); '
                     'local base=getAddress("FixtureTarget.exe"); '
                     'm.firstScan(soExactValue,vtByteArray,rtRounded,"43 54 32 54 2D 46 49 58 2D 32 30 32 36 2D 30 31",nil,'
                     'base,base+getModuleSize("FixtureTarget.exe")-1,"",fsmNotAligned,"",true,false,false,false); '
                     'm.waitTillDone(); f.initialize(); local n,a=f.Count,f.Address[0]; m.destroy(); f.destroy(); return n,a')
        count,found=host.execute(scan_source)
        assert count==1 and int(found,16)==address
        note('real-lua-memscan-foundlist-index-and-owned-module-read')
        assert type(host.execute('return isKeyPressed(VK_SHIFT)')) is bool
        assert host.execute('local s=getXBox360ControllerState(); return s==nil or (type(s.GAMEPAD_A)=="boolean")') is True
        note('read-only-windows-keyboard-controller-api-no-physical-input-claim')
        from .assembler import NasmAssembler
        from .hooks import validate_instruction_boundary
        encoded=NasmAssembler().assemble('bits 64\nmov eax,ecx\nadd eax,100\nret\n')
        assert encoded == bytes.fromhex('89c883c064c3')
        validate_instruction_boundary(0x1000,encoded,64)
        note('pinned-bsd-nasm-and-mit-iced-machine-encoding', bytes=encoded.hex())
        engine.set_freeze(2, True)
        reader.write(address + 16, (2222).to_bytes(4, "little"))
        engine.poll()
        assert reader.read(address + 16, 4) == (4321).to_bytes(4, "little")
        engine.set_freeze(2, False)
        note("freeze-confirms-current-value")
        engine.toggle(1, True)
        ticks = reader.read(address + 24, 4)
        time.sleep(1.2)
        assert reader.read(address + 20, 4) == b"\x01\x00\x00\x00"
        assert reader.read(address + 24, 4) == ticks
        assert engine.desired == {0, 1}
        note("pause-patch-and-confirmed-persistence")
        try:
            other = TrainerEngine(plan, state_dir=state_dir)
        except NativeRuntimeError:
            note("concurrent-trainer-blocked")
        else:
            other.close()
            raise AssertionError("A concurrent trainer acquired the same state")
        engine.toggle(1, False)
        time.sleep(1.2)
        assert int.from_bytes(reader.read(address + 24, 4), "little") > int.from_bytes(ticks, "little")
        note("disable-resumes-ticks")
        engine.toggle(1, True)
        process.terminate()
        process.wait(timeout=5)
        reader.close()
        reader = None
        engine.poll()
        assert not engine.connected
        process = start_target()
        connect(engine)
        assert process.pid != first_pid
        reader = ProcessMemory(target.name, pid=process.pid)
        address = reader.scan_module(target.name, "43 54 32 54 2D 46 49 58 2D 32 30 32 36 2D 30 31")
        assert reader.read(address + 20, 4) == b"\x01\x00\x00\x00"
        assert reader.read(address + 16, 4) == (1234).to_bytes(4, "little")
        note("saved-switches-after-target-restart-values-not-restored", old_pid=first_pid, new_pid=process.pid)
        assert engine.close(), engine.error
        assert reader.read(address + 20, 4) == b"\x00" * 4
        assert not (state_dir / "session.json").exists() and not (state_dir / "state.lock").exists()
        engine = TrainerEngine(plan, state_dir=state_dir)
        connect(engine)
        assert reader.read(address + 20, 4) == b"\x01\x00\x00\x00"
        note("trainer-restart-restores-saved-switch")
        assert engine.close(), engine.error
        engine = None
        assert reader.read(address + 20, 4) == b"\x00" * 4
        assert not (state_dir / "session.json").exists() and not (state_dir / "state.lock").exists()
        note("close-restores-owned-patch-and-releases-lock")
        result = {"schema": "ct2trainer-fixture/v1", "status": "passed", "ce_runtime_used": False,
                  'frozen_runtime':bool(getattr(sys,'frozen',False)),
                  'runtime_executable':str(Path(sys.executable).resolve()),
                  'runtime_executable_sha256':hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
                  "fixture_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                  "table_sha256": plan["table_sha256"], "state_dir": str(state_dir), "observations": observations,
                  "game_unverified": True, "other_pc_unverified": True, "proton_unverified": True}
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        return result
    finally:
        if engine is not None:
            engine.close()
        if reader is not None:
            reader.close()
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
