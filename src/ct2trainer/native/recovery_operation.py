"""Explicit, archived release of proven obsolete Native ownership artifacts.

Windows files are held without read/write/delete sharing, verified against the
assessment, and deleted by their held handle. No remote process memory is read
or changed. Multiple file dispositions are deliberately not an atomic operation.
Failure before confirmed fence release retains the evidence, journal, and fence.
Final directory cleanup uncertainty explicitly reports an already released fence.

Primary contracts:
https://learn.microsoft.com/windows/win32/api/fileapi/nf-fileapi-createfilew
https://learn.microsoft.com/windows/win32/api/fileapi/nf-fileapi-setfileinformationbyhandle
https://learn.microsoft.com/windows/win32/api/winbase/ns-winbase-file_disposition_info
https://learn.microsoft.com/windows/win32/api/winbase/ns-winbase-file_id_info
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import time
import uuid
import zipfile

from .recovery import (
    RecoveryAssessment, ProcessObservation, WindowsProcessProbe, current_process_identity,
    assess_recovery, _fingerprint, _HEX32, _HEX64, _document, _fields, _identity,
    _inventory, _safe_stat, _issue_fence_allowance,
)


MAX_OPERATION_FILES = 512
MAX_OPERATION_BYTES = 128 * 1024 * 1024
MAX_MANIFEST_BYTES = 8 * 1024 * 1024
MAX_OPERATION_SECONDS = 45
GENERIC_READ, GENERIC_WRITE, DELETE = 0x80000000, 0x40000000, 0x10000
OPEN_EXISTING, CREATE_NEW = 3, 1
OPEN_REPARSE_POINT, BACKUP_SEMANTICS = 0x00200000, 0x02000000
_DWORD = ctypes.c_uint32


@dataclass(frozen=True)
class RecoveryReport:
    status: str  # completed, refused, uncertain
    state_directory: Path
    fence_path: Path
    archive_path: Path | None
    archive_sha256: str | None
    journal_path: Path | None
    journal_sha256: str | None
    assessment_sha256: str
    released: tuple[Path, ...]
    reasons: tuple[str, ...]
    preserved_state: Path
    remote_writes: bool = False
    fence_released: bool = False

    @property
    def completed(self):
        return self.status == "completed"


class RecoveryOperationError(RuntimeError):
    pass


class _FileId(ctypes.Structure):
    _fields_ = [("volume", ctypes.c_uint64), ("identifier", ctypes.c_ubyte * 16)]


class _AttributeTag(ctypes.Structure):
    _fields_ = [("attributes", _DWORD), ("tag", _DWORD)]


class _Disposition(ctypes.Structure):
    _fields_ = [("delete", wintypes.BOOL)]


def _kernel():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    signatures = {
        "CreateFileW": ([wintypes.LPCWSTR, _DWORD, _DWORD, ctypes.c_void_p, _DWORD, _DWORD, wintypes.HANDLE], wintypes.HANDLE),
        "GetFileInformationByHandleEx": ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, _DWORD], wintypes.BOOL),
        "SetFileInformationByHandle": ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, _DWORD], wintypes.BOOL),
        "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
        "GetDriveTypeW": ([wintypes.LPCWSTR], _DWORD),
        "GetVolumeInformationW": ([wintypes.LPCWSTR, wintypes.LPWSTR, _DWORD, ctypes.c_void_p,
                                   ctypes.c_void_p, ctypes.c_void_p, wintypes.LPWSTR, _DWORD], wintypes.BOOL),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(kernel, name)
        function.argtypes, function.restype = arguments, result
    return kernel


def _fail(message):
    raise RecoveryOperationError(message)


def _check_time(deadline):
    if time.monotonic() > deadline:
        _fail("Recovery exceeded its elapsed-time bound; retain its fence and evidence")


def _canonical(document):
    return json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _local_volume(kernel, path):
    if not path.drive or path.drive.startswith("\\") or kernel.GetDriveTypeW(path.anchor) != 3:
        _fail("Verified recovery requires local fixed Windows volumes")
    filesystem = ctypes.create_unicode_buffer(64)
    if not kernel.GetVolumeInformationW(path.anchor, None, 0, None, None, None, filesystem, len(filesystem)):
        _fail("The recovery filesystem could not be verified")
    if filesystem.value.upper() not in {"NTFS", "REFS"}:
        _fail("Verified recovery currently requires NTFS or ReFS file identity and disposition support")


def _file_identity(kernel, handle):
    identity, attributes = _FileId(), _AttributeTag()
    if (not kernel.GetFileInformationByHandleEx(handle, 18, ctypes.byref(identity), ctypes.sizeof(identity))
            or not kernel.GetFileInformationByHandleEx(handle, 9, ctypes.byref(attributes), ctypes.sizeof(attributes))):
        _fail("Held Windows file identity or reparse information is unavailable")
    if attributes.attributes & 0x400:
        _fail("Recovery never follows or deletes reparse objects")
    return identity.volume, int.from_bytes(bytes(identity.identifier), "little"), attributes.attributes


class _Directory:
    """Deny ancestor rename/delete while permitting ordinary child operations."""
    def __init__(self, kernel, path):
        self.kernel, self.path, self.handle = kernel, path, None
        before = _safe_stat(path, directory=True)
        handle = kernel.CreateFileW(str(path), 0x80, 3, None, OPEN_EXISTING,
                                    OPEN_REPARSE_POINT | BACKUP_SEMANTICS, None)
        if not handle or handle == ctypes.c_void_p(-1).value:
            _fail("A recovery directory cannot be pinned against rename/delete")
        self.handle = handle
        try:
            volume, identifier, attributes = _file_identity(kernel, handle)
            if (not attributes & 0x10 or (volume, identifier) != (before.st_dev, before.st_ino)
                    or _fingerprint(_safe_stat(path, directory=True)) != _fingerprint(before)):
                _fail("Pinned recovery directory differs from its inspected identity")
        except Exception:
            self.close()
            raise

    def close(self):
        if self.handle is not None:
            handle, self.handle = self.handle, None
            if not self.kernel.CloseHandle(handle):
                _fail("Pinned recovery directory handle cleanup failed")


class _File:
    def __init__(self, kernel, path, *, create=False):
        import msvcrt
        self.kernel, self.path, self.stream = kernel, path, None
        rights = GENERIC_READ | DELETE | (GENERIC_WRITE if create else 0)
        handle = kernel.CreateFileW(str(path), rights, 0, None, CREATE_NEW if create else OPEN_EXISTING,
                                    OPEN_REPARSE_POINT | 0x08000000, None)
        if not handle or handle == ctypes.c_void_p(-1).value:
            _fail("Exclusive held file acquisition failed for " + path.name)
        descriptor = None
        try:
            volume, identifier, attributes = _file_identity(kernel, handle)
            if attributes & 0x10:
                _fail("A recovery file path names a directory")
            descriptor = msvcrt.open_osfhandle(handle, os.O_BINARY | (os.O_RDWR if create else os.O_RDONLY))
            handle = None  # CRT descriptor owns it from this point.
            self.stream = os.fdopen(descriptor, "w+b" if create else "rb", buffering=0)
            descriptor = None
            information = os.fstat(self.stream.fileno())
            if (not stat.S_ISREG(information.st_mode) or information.st_nlink != 1
                    or (volume, identifier) != (information.st_dev, information.st_ino)):
                _fail("Held recovery file is linked, nonregular, or has an inconsistent identifier")
        except Exception as failure:
            try:
                if descriptor is not None:
                    os.close(descriptor)
                if handle is not None:
                    kernel.CloseHandle(handle)
                self.close()
            finally:
                if create:
                    error = RecoveryOperationError("New evidence object could not be verified: " + str(failure))
                    error.created_path = path
                    raise error from failure
            raise

    def identity(self):
        if self.stream is None:
            _fail("Held recovery file has already been closed")
        return _fingerprint(os.fstat(self.stream.fileno()))

    def read(self, maximum, deadline):
        _check_time(deadline)
        before = self.identity()
        if before[2] > maximum:
            _fail("Held recovery file exceeds its byte bound")
        self.stream.seek(0)
        parts, count = [], 0
        while True:
            _check_time(deadline)
            raw = self.stream.read(1024 * 1024)
            if not raw:
                break
            parts.append(raw)
            count += len(raw)
            if count > maximum:
                _fail("Held recovery file grew beyond its byte bound")
        if self.identity() != before or count != before[2]:
            _fail("Held recovery file changed during reading")
        return b"".join(parts)

    def write(self, raw):
        self.stream.seek(0, 2)
        if self.stream.write(raw) != len(raw):
            _fail("A durable recovery evidence write was incomplete")
        self.stream.flush()
        os.fsync(self.stream.fileno())

    def delete(self):
        import msvcrt
        handle = msvcrt.get_osfhandle(self.stream.fileno())
        information = _Disposition(True)
        if not self.kernel.SetFileInformationByHandle(handle, 4, ctypes.byref(information), ctypes.sizeof(information)):
            _fail("Held file disposition failed for " + self.path.name)
        self.close()
        if os.path.lexists(self.path):
            _fail("A recovery path remains or was substituted after held-file deletion: " + self.path.name)

    def close(self):
        if self.stream is not None:
            stream, self.stream = self.stream, None
            stream.close()


def _directory_objects(assessment):
    return {path: None if identity is None else (identity[0], identity[1], identity[4])
            for path, identity in assessment.directory_identities}


def _same_assessment(original, fresh, fence):
    if not fresh.eligible:
        _fail("Recovery reassessment blocks release: " + "; ".join(fresh.reasons[:8]))
    # A fence that already existed at assessment time is part of both
    # inventories and must compare equal on both sides; a fence the operator
    # created now is excluded from the fresh file inventory, as before.
    # Candidate lists are compared without the held fence in either case.
    fence_preexisting = any(item.path == fence for item in original.files)
    fresh_files = fresh.files if fence_preexisting else tuple(item for item in fresh.files if item.path != fence)
    if (fresh_files != original.files
            or tuple(item for item in fresh.candidate_paths if item != fence)
               != tuple(item for item in original.candidate_paths if item != fence)
            or _directory_objects(fresh) != _directory_objects(original)
            or {(p.identity, p.roles) for p in fresh.processes} != {(p.identity, p.roles) for p in original.processes}):
        _fail("Recovery evidence, directory identity, ownership, or process eligibility changed after fencing")


def _inventory_guard(assessment, fence, released):
    files, directories = _inventory(assessment.state_directory, assessment.process_lock_directory)
    expected = {item.path: item.kind for item in assessment.files if item.path not in released}
    if fence not in released:
        expected[fence] = "state-file"
    if files != expected:
        _fail("Recovery directory inventory changed during the held transaction")
    objects = {path: None if identity is None else (identity[0], identity[1], identity[4]) for path, identity in directories}
    if objects != _directory_objects(assessment):
        _fail("Recovery directory objects changed during the held transaction")


def _archive_name(assessment, path):
    if path.is_relative_to(assessment.state_directory):
        return "state/" + path.relative_to(assessment.state_directory).as_posix()
    if path.is_relative_to(assessment.process_lock_directory):
        return "shared/" + path.relative_to(assessment.process_lock_directory).as_posix()
    _fail("Recovery assessment includes a file outside its explicit scopes")


def _archive(assessment, held, archive, deadline):
    manifest = {"schema": 1, "engine": "ct2trainer-recovery-evidence",
                "assessment_sha256": assessment.inventory_sha256,
                "files": [{"path": str(item.path), "member": _archive_name(assessment, item.path),
                           "size": item.size, "sha256": item.sha256, "identity": item.identity}
                          for item in assessment.files]}
    raw_manifest = _canonical(manifest)
    if len(raw_manifest) > MAX_MANIFEST_BYTES:
        _fail("Recovery archive manifest exceeds its byte bound")
    with zipfile.ZipFile(archive.stream, "w", compression=zipfile.ZIP_STORED, allowZip64=False) as bundle:
        bundle.writestr("manifest.json", raw_manifest)
        for item in assessment.files:
            raw = held[item.path].read(item.size, deadline)
            if held[item.path].identity() != item.identity or hashlib.sha256(raw).hexdigest() != item.sha256:
                _fail("Held original bytes differ from the recovery assessment")
            bundle.writestr(_archive_name(assessment, item.path), raw)
    archive.stream.flush()
    os.fsync(archive.stream.fileno())
    archive.stream.seek(0)
    with zipfile.ZipFile(archive.stream, "r") as bundle:
        expected = {"manifest.json"} | {item["member"] for item in manifest["files"]}
        if set(bundle.namelist()) != expected or len(bundle.namelist()) != len(expected):
            _fail("Recovery archive inventory verification failed")
        if bundle.read("manifest.json") != raw_manifest:
            _fail("Recovery archive manifest verification failed")
        for item in manifest["files"]:
            _check_time(deadline)
            info = bundle.getinfo(item["member"])
            if info.file_size != item["size"] or info.compress_type != zipfile.ZIP_STORED:
                _fail("Recovery archive member bounds or encoding changed")
            raw = bundle.read(item["member"])
            if hashlib.sha256(raw).hexdigest() != item["sha256"]:
                _fail("Recovery archive original-byte verification failed")
    return hashlib.sha256(archive.read(MAX_OPERATION_BYTES + MAX_MANIFEST_BYTES + 1024 * 1024, deadline)).hexdigest()


def recover_assessment(assessment: RecoveryAssessment, archive_directory: str | Path, *,
                       expected_trainer_id: str, expected_table_sha256: str,
                       process_probe=None,
                       exclusive_controller_claim: bool = False) -> RecoveryReport:
    """Explicitly archive and release only one fresh, eligible assessment.

    A refused operation has made no ownership changes. Failure while fenced is
    uncertain and retains the fence, archive and operation journal. Directory
    cleanup failure after release explicitly reports ``fence_released=True``.
    Already released original objects remain represented in the verified archive.
    Saved ``state.json`` is preserved; no remote writes or automatic activation.

    ``exclusive_controller_claim`` must repeat the claim flag the assessment was
    produced with, so the fenced reassessment reproduces the same candidates;
    mixing the two views refuses the operation.

    An already present ``recovery.lock`` left by a crashed earlier operation is
    taken over: its exact bytes are opened without creating, its document is
    verified against this assessment (schema, trainer/table identity, and the
    fence owner must be part of the verified death proof), and the fence is
    kept byte-identical until it is released in the final held-object step.
    An unreadable, foreign, or unowned pre-existing fence refuses the run.
    """
    if not isinstance(assessment, RecoveryAssessment):
        raise ValueError("Verified recovery requires a RecoveryAssessment")
    fence_path = assessment.state_directory / "recovery.lock"
    archive_path = journal_path = archive_hash = journal_hash = None
    released, reasons, directories, held = [], [], [], {}
    fence = archive = journal = None
    claimed, fence_released, status = False, False, "refused"
    deadline = time.monotonic() + MAX_OPERATION_SECONDS

    def record(state, **fields):
        nonlocal journal_hash
        journal_hash = None
        raw = _canonical({"schema": 1, "engine": "ct2trainer-recovery-operation",
                          "state": state, "assessment_sha256": assessment.inventory_sha256,
                          "released": [str(path) for path in released], **fields}) + b"\n"
        if journal.identity()[2] + len(raw) > MAX_MANIFEST_BYTES:
            _fail("Recovery operation journal exceeds its byte bound")
        journal.write(raw)
        journal_hash = hashlib.sha256(journal.read(MAX_MANIFEST_BYTES, deadline)).hexdigest()

    try:
        if sys.platform != "win32":
            _fail("Held-file verified recovery is implemented only for Windows")
        if (not assessment.eligible or assessment.status != "eligible-read-only" or not assessment.read_only
                or assessment.mutation_authorized or assessment.reasons or not assessment.processes
                or any(not process.proven_dead for process in assessment.processes)
                or not assessment.directory_identities):
            _fail("The supplied assessment is not an eligible read-only death proof")
        if (len(assessment.files) > MAX_OPERATION_FILES or sum(item.size for item in assessment.files) > MAX_OPERATION_BYTES
                or not assessment.candidate_paths or assessment.state_directory / "state.json" in assessment.candidate_paths):
            _fail("Recovery candidates or evidence exceed the verified operation profile")
        candidate_set = set(assessment.candidate_paths)
        if not candidate_set <= {item.path for item in assessment.files}:
            _fail("Recovery candidates are not contained in the assessed file inventory")
        destination = Path(os.path.abspath(archive_directory))
        scopes = (assessment.state_directory, assessment.process_lock_directory)
        if any(destination == scope or destination.is_relative_to(scope) for scope in scopes):
            _fail("Recovery archives must be outside the state and shared-lock scopes")
        kernel = _kernel()
        for path in (*scopes, destination):
            _local_volume(kernel, path)
        # Pin each existing ancestor before creating the archive directory or fence.
        pin_paths = set()
        for path in (*scopes, destination):
            pin_paths.update(parent for parent in (path, *path.parents) if os.path.lexists(parent))
        for path, identity in assessment.directory_identities:
            if identity is not None:
                pin_paths.add(Path(path))
        for path in sorted(pin_paths, key=lambda item: (len(item.parts), str(item))):
            _check_time(deadline)
            directories.append(_Directory(kernel, path))
        if not destination.exists():
            if not destination.parent.exists():
                _fail("Recovery archive directory needs an existing pinned parent")
            destination.mkdir()
            directories.append(_Directory(kernel, destination))
        own = current_process_identity()
        if own.created is None:
            _fail("Recovery cannot fence without its exact owner creation identity")
        nonce = uuid.uuid4().hex
        journal_path = destination / ("native-recovery-" + nonce + ".jsonl")
        _check_time(deadline)
        journal = _File(kernel, journal_path, create=True)
        pre_existing_fence = any(item.path == fence_path for item in assessment.files)
        if pre_existing_fence:
            # Take over the stale fence left by a crashed earlier operation.
            # Its exact bytes are the fence: open it without creating, verify
            # its document against this assessment, and keep it byte-identical
            # until the final held-object release below.
            fence = _File(kernel, fence_path)
            fence_raw = fence.read(MAX_OPERATION_BYTES, deadline)
            try:
                fence_document = _document(fence_raw)
                _fields(fence_document, {"schema", "engine", "owner_pid", "owner_created", "nonce",
                                         "trainer_id", "table_sha256", "assessment_sha256"})
                if (type(fence_document["schema"]) is not int or fence_document["schema"] != 1
                        or fence_document["engine"] != "ct2trainer-recovery-fence"
                        or fence_document["trainer_id"] != expected_trainer_id
                        or fence_document["table_sha256"] != expected_table_sha256
                        or not isinstance(fence_document["nonce"], str) or not _HEX32.fullmatch(fence_document["nonce"])
                        or not isinstance(fence_document["assessment_sha256"], str)
                        or not _HEX64.fullmatch(fence_document["assessment_sha256"])):
                    raise ValueError("Pre-existing recovery fence schema or identity is invalid")
                fence_owner = _identity(fence_document, "owner_pid", "owner_created")
            except (ValueError, TypeError, KeyError) as exc:
                _fail("Pre-existing recovery fence cannot be taken over: " + str(exc))
            if not any(process.identity == fence_owner and "recovery-fence owner" in process.roles
                       for process in assessment.processes):
                _fail("Pre-existing recovery fence owner is missing from the verified death proof")
            record("fence-taken-over", fence=str(fence_path), owner=[fence_owner.pid, fence_owner.created],
                   fence_sha256=hashlib.sha256(fence_raw).hexdigest())
            claimed, status = True, "uncertain"
            allowance = _issue_fence_allowance(fence_path, fence_raw, fence.identity)
        else:
            fence_raw = _canonical({"schema": 1, "engine": "ct2trainer-recovery-fence",
                                    "owner_pid": own.pid, "owner_created": own.created, "nonce": nonce,
                                    "trainer_id": expected_trainer_id, "table_sha256": expected_table_sha256,
                                    "assessment_sha256": assessment.inventory_sha256})
            record("fence-claim-intent", fence=str(fence_path), owner=[own.pid, own.created])
            fence = _File(kernel, fence_path, create=True)
            claimed, status = True, "uncertain"
            fence.write(fence_raw)
            allowance = _issue_fence_allowance(fence_path, fence_raw, fence.identity)
            record("fenced", fence=str(fence_path), owner=[own.pid, own.created])
        fresh = assess_recovery(assessment.state_directory, assessment.process_lock_directory,
                                process_probe=process_probe, expected_trainer_id=expected_trainer_id,
                                expected_table_sha256=expected_table_sha256,
                                exclusive_controller_claim=exclusive_controller_claim,
                                _fence_allowance=allowance)
        _same_assessment(assessment, fresh, fence_path)
        _check_time(deadline)
        for item in assessment.files:
            _check_time(deadline)
            if item.path == fence_path and pre_existing_fence:
                held[item.path] = fence
            else:
                held[item.path] = _File(kernel, item.path)
            if held[item.path].identity() != item.identity:
                _fail("A held original file changed identity after reassessment")
        _inventory_guard(assessment, fence_path, released)
        archive_path = destination / ("native-recovery-" + nonce + ".zip")
        archive = _File(kernel, archive_path, create=True)
        archive_hash = _archive(assessment, held, archive, deadline)
        record("archive-verified", archive=str(archive_path), archive_sha256=archive_hash)
        _inventory_guard(assessment, fence_path, released)
        # Every original object is now held and archived. Probe all exact recorded
        # identities once more; no path reopen is required for this proof pass.
        probe = process_probe or WindowsProcessProbe()
        for process in assessment.processes:
            _check_time(deadline)
            observation = probe(process.identity) if callable(probe) else probe.probe(process.identity)
            if (not isinstance(observation, ProcessObservation) or observation.identity != process.identity
                    or not observation.proven_dead):
                _fail("An exact owner or target is not proven dead before file release")
        # The fence itself (own or taken over) is released in the final
        # held-object step below, never inside the candidate release loop.
        ordered = sorted(candidate_set - {fence_path},
                         key=lambda path: (path == assessment.state_directory / "state.lock", str(path)))
        for path in ordered:
            _check_time(deadline)
            _inventory_guard(assessment, fence_path, released)
            original = next(item for item in assessment.files if item.path == path)
            raw = held[path].read(original.size, deadline)
            if held[path].identity() != original.identity or hashlib.sha256(raw).hexdigest() != original.sha256:
                _fail("An original changed before its held-object release")
            record("release-intent", path=str(path), original_sha256=original.sha256)
            held[path].delete()
            released.append(path)
            record("released", path=str(path))
        _inventory_guard(assessment, fence_path, released)
        record("release-complete", archive_sha256=archive_hash, saved_state_preserved=True, fence_release_pending=True)
        # Finish every other evidence write and nondirectory resource close
        # while fenced. Directory pins survive the final fence deletion.
        # The durable last record explicitly describes
        # a pending fence release; there is no post-release write to fail.
        # The taken-over fence handle must stay open until the final
        # identity check and delete below (it doubles as the held object);
        # the operator-created fence is not part of held at all.
        for resource in (*[r for r in held.values() if r is not fence], archive, journal):
            if resource is not None:
                resource.close()
        if fence.identity() != _fingerprint(_safe_stat(fence_path)) or fence.read(65536, deadline) != fence_raw:
            _fail("Recovery fence changed before its final held-object release")
        fence.delete()
        fence = None
        fence_released = True
        status = "completed"
    except Exception as exc:
        claimed = claimed or getattr(exc, "created_path", None) == fence_path
        reasons.append(str(exc) or type(exc).__name__)
        status = "uncertain" if claimed else "refused"
        if journal is not None and journal.stream is not None:
            try:
                record(status, detail=reasons[-1], fence_retained=claimed)
            except Exception as failure:
                reasons.append("Operation uncertainty could not be durably appended: " + str(failure))
    finally:
        for resource in (*held.values(), archive, journal, fence, *reversed(directories)):
            if resource is not None:
                try:
                    resource.close()
                except Exception as exc:
                    phase = " after confirmed fence release; no own fence remains" if fence_released else " while fenced"
                    reasons.append("Recovery handle cleanup is uncertain" + phase + ": " + str(exc))
                    status = "uncertain" if claimed else "refused"
    return RecoveryReport(status, assessment.state_directory, fence_path, archive_path, archive_hash,
                          journal_path, journal_hash, assessment.inventory_sha256, tuple(released), tuple(reasons),
                          assessment.state_directory / "state.json", fence_released=fence_released)
