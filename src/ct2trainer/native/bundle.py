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
# An Authenticode certificate table may legally sit after the plan footer
# (signtool appends it); the footer scanner never looks further back than
# this bounded tail window.
MAX_CERTIFICATE_TAIL = 1024 * 1024


def canonical_bytes(plan: dict) -> bytes:
    return json.dumps(plan, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


def _find_footer(data: bytes) -> tuple[int, int, bool]:
    """Locate the plan footer inside raw trainer file bytes.

    Returns ``(footer_start, length, corrupted)``: ``footer_start >= 0``
    names a verified footer; ``footer_start == -1`` with ``corrupted``
    True means the only checksum-failing candidate inside the tail
    window (the named plan-corruption condition); ``footer_start == -1``
    with ``corrupted`` False means no footer candidate at all.
    A code signature may legally sit after the footer, so the footer is
    not necessarily at the end of the file: the scanner searches backwards
    from the end for the magic within the bounded certificate tail, and
    every candidate is proved against the plan checksum - a magic
    occurrence that does not verify is skipped, never accepted.
    """
    size = len(data)
    limit = max(0, size - MAX_CERTIFICATE_TAIL)
    pos = size - 8
    corrupted = None
    while pos >= 0:
        if pos - 40 >= limit and data[pos:pos + 8] == MAGIC:
            fstart = pos - 40
            length = struct.unpack_from("<Q", data, pos - 8)[0]
            if 0 < length <= MAX_PLAN_BYTES and fstart - length >= 0:
                payload = data[fstart - length:fstart]
                if hashlib.sha256(payload).digest() == data[fstart:fstart + 32]:
                    return fstart, length, False
                if corrupted is None:
                    corrupted = (fstart, length)
        if pos < limit + 40:
            break
        pos = data.rfind(MAGIC, 0, pos)
    if corrupted is not None:
        return -1, corrupted[1], True
    return -1, 0, False


def read_embedded_plan(executable: str | Path) -> dict:
    path = Path(executable)
    data = path.read_bytes()
    if len(data) < FOOTER_SIZE:
        raise ValueError("No independent CT2Trainer plan in this executable.")
    fstart, length, corrupted = _find_footer(data)
    if fstart < 0:
        if corrupted:
            raise ValueError("Independent trainer payload checksum mismatch.")
        raise ValueError("Missing or invalid independent trainer payload.")
    payload = data[fstart - length:fstart]
    result = json.loads(payload)
    if not isinstance(result, dict) or result.get("engine") != "ct2trainer":
        raise ValueError("Unsupported trainer payload engine.")
    return result


def template_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "native-template" / "CT2Trainer-Template.exe"
    raise ValueError("Supply --template from a native build, or use the portable native converter.")


def build_trainer(plan: dict, output: str | Path, template: str | Path | None = None,
                  *, force: bool = False, sign=None) -> tuple[Path, Path]:
    """Append a checked declarative plan to the independent PyInstaller template.

    PyInstaller locates its archive cookie backwards, so a PE overlay can hold
    the plan without changing its archive. The real EXE smoke gate tests this.

    ``sign`` is the injectable signing seam (defaults to the environment-
    driven ``code_signing.sign_if_configured``): the generated trainer is
    signed before publication when a PFX certificate is configured, and the
    roundtrip re-reads the signed file, so the plan must survive the
    certificate table that signtool appends after the footer.
    """
    from .engine import validate_plan
    from .code_signing import sign_if_configured
    signer = sign_if_configured if sign is None else sign
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
        signing = signer(temporary)
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
              "ce_payload": False, "signed": bool(signing.get("signed", False)),
              "table_sha256": plan["table_sha256"],
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
