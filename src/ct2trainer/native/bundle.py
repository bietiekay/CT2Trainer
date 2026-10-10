"""Independent trainer packaging. Payload is data, never Python/Lua source."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile

MAGIC = b"CT2NATV1"
TEMPLATE_MAGIC = b"CT2BASE1"
MAX_PLAN_BYTES = 16 * 1024 * 1024
FOOTER_SIZE = 48  # sha256 + little-endian length + magic


def canonical_bytes(plan: dict) -> bytes:
    return json.dumps(plan, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


def read_embedded_plan(executable: str | Path) -> dict:
    path = Path(executable)
    with path.open("rb") as source:
        size = source.seek(0, os.SEEK_END)
        if size < FOOTER_SIZE:
            raise ValueError("No independent CT2Trainer plan in this executable.")
        source.seek(-FOOTER_SIZE, os.SEEK_END)
        footer = source.read(FOOTER_SIZE)
        length = struct.unpack("<Q", footer[32:40])[0]
        if footer[40:] != MAGIC or not 0 < length <= MAX_PLAN_BYTES or length > size - FOOTER_SIZE:
            raise ValueError("Missing or invalid independent trainer payload.")
        source.seek(-FOOTER_SIZE - length, os.SEEK_END)
        payload = source.read(length)
    if hashlib.sha256(payload).digest() != footer[:32]:
        raise ValueError("Independent trainer payload checksum mismatch.")
    result = json.loads(payload)
    if not isinstance(result, dict) or result.get("engine") != "ct2trainer":
        raise ValueError("Unsupported trainer payload engine.")
    return result


def template_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "native-template" / "CT2Trainer-Template.exe"
    raise ValueError("Supply --template from a native build, or use the portable native converter.")


def build_trainer(plan: dict, output: str | Path, template: str | Path | None = None,
                  *, force: bool = False) -> tuple[Path, Path]:
    """Append a checked declarative plan to the independent PyInstaller template.

    PyInstaller locates its archive cookie backwards, so a PE overlay can hold
    the plan without changing its archive. The real EXE smoke gate tests this.
    """
    from .engine import validate_plan
    validate_plan(plan)
    from .architecture import plan_architecture
    architecture = plan_architecture(plan)
    target = Path(output).expanduser().resolve()
    if target.suffix.casefold() != ".exe":
        raise ValueError("Trainer output must end in .exe.")
    report_path = target.with_suffix(".build.json")
    if not force and (target.exists() or report_path.exists()):
        raise FileExistsError("Output EXE or report already exists; use --force.")
    template = Path(template) if template is not None else template_path()
    stub = template.read_bytes()
    if (len(stub) < 104 or stub[-8:] != TEMPLATE_MAGIC
            or hashlib.sha256(stub[:-40]).digest() != stub[-40:-8]):
        raise ValueError("Template must be a checked independent CT2Trainer build.")
    if len(stub) < 64 or stub[:2] != b"MZ":
        raise ValueError("Native template must be a Windows PE executable.")
    pe_offset = struct.unpack_from("<I", stub, 0x3C)[0]
    if pe_offset + 6 > len(stub) or stub[pe_offset:pe_offset + 4] != b"PE\0\0" or struct.unpack_from("<H", stub, pe_offset + 4)[0] != 0x8664:
        raise ValueError("Native template must have an x64 PE header.")
    payload = canonical_bytes(plan)
    if len(payload) > MAX_PLAN_BYTES:
        raise ValueError("Trainer plan exceeds size limit.")
    data = stub + payload + hashlib.sha256(payload).digest() + struct.pack("<Q", len(payload)) + MAGIC
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=target.stem + "-", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if read_embedded_plan(temporary) != plan:
            raise ValueError("Trainer payload roundtrip failed.")
        if force:
            os.replace(temporary, target)
        else:
            if sys.platform == "win32":
                os.rename(temporary, target)  # Windows: fails if destination exists, also on FAT/exFAT
            else:
                os.link(temporary, target)  # POSIX no-overwrite publication
                os.unlink(temporary)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    report = {"schema": "ct2trainer-build/v1", "engine": "ct2trainer",
              "ce_payload": False, "table_sha256": plan["table_sha256"],
              "target_architecture": architecture, "controller_architecture": "x64",
              "template_sha256": hashlib.sha256(stub).hexdigest(),
              "plan_sha256": hashlib.sha256(payload).hexdigest(),
              "exe_sha256": hashlib.sha256(data).hexdigest(), "exe_bytes": len(data),
              "entries": len(plan["entries"]),
              "supported": sum(bool(e["supported"]) for e in plan["entries"]),
              "selected_ids": plan.get("selected_ids", [e["id"] for e in plan["entries"] if e.get("selected", True)]),
              "runtime_unverified": True, "proton_unverified": True}
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return target, report_path
