"""Read-only independent crash-recovery eligibility and exact process evidence.

No assessment deletes, renames, restores memory, or releases a lock. A later
recovery transaction must take an exclusive claim and revalidate this evidence.
PID absence is corroborated with a successful complete process snapshot; failed
access is never treated as death. Legacy owner locks lack creation time and
therefore cannot qualify for automatic recovery.

Primary Win32 contracts:
https://learn.microsoft.com/windows/win32/api/processthreadsapi/nf-processthreadsapi-openprocess
https://learn.microsoft.com/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocesstimes
https://learn.microsoft.com/windows/win32/api/synchapi/nf-synchapi-waitforsingleobject
https://learn.microsoft.com/windows/win32/api/tlhelp32/nf-tlhelp32-createtoolhelp32snapshot
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
from typing import Callable


MAX_FILES = 4096
MAX_SNAPSHOT_BYTES = 128 * 1024 * 1024
MAX_JOURNAL_BYTES = 72 * 1024 * 1024
MAX_IDENTITIES = 256
MAX_ASSESS_SECONDS = 15
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SYNCHRONIZE = 0x100000
WAIT_OBJECT_0, WAIT_TIMEOUT = 0, 258
ERROR_INVALID_PARAMETER, ERROR_NO_MORE_FILES = 87, 18
_DWORD = ctypes.c_uint32
_HEX32, _HEX64 = re.compile(r"[0-9a-f]{32}"), re.compile(r"[0-9a-f]{64}")
_SYMBOL = re.compile(r"[A-Za-z_][A-Za-z0-9_.$]{0,127}")


@dataclass(frozen=True, order=True)
class ProcessIdentity:
    pid: int
    created: int | None

    def __post_init__(self):
        if (type(self.pid) is not int or not 0 < self.pid <= 0xFFFFFFFF
                or self.created is not None and (type(self.created) is not int
                                                or not 0 < self.created <= 0xFFFFFFFFFFFFFFFF)):
            raise ValueError("An exact process identity needs a positive PID and FILETIME creation value.")


@dataclass(frozen=True)
class ProcessObservation:
    identity: ProcessIdentity
    status: str  # alive, dead, reused, absent, unknown
    observed_created: int | None = None
    wait_result: int | None = None
    detail: str = ""
    error: int | None = None

    @property
    def proven_dead(self) -> bool:
        if self.identity.created is None:
            return False
        if self.status == "dead":
            return (type(self.observed_created) is int and self.observed_created == self.identity.created
                    and type(self.wait_result) is int and self.wait_result == WAIT_OBJECT_0)
        if self.status == "reused":
            return (type(self.observed_created) is int and 0 < self.observed_created <= 0xFFFFFFFFFFFFFFFF
                    and self.observed_created != self.identity.created
                    and type(self.wait_result) is int and self.wait_result in {WAIT_OBJECT_0, WAIT_TIMEOUT})
        return self.status == "absent" and self.observed_created is None


@dataclass(frozen=True)
class ProcessEvidence:
    roles: tuple[str, ...]
    identity: ProcessIdentity
    observations: tuple[ProcessObservation, ...]

    @property
    def proven_dead(self) -> bool:
        return len(self.observations) == 2 and all(item.proven_dead for item in self.observations)


@dataclass(frozen=True)
class FileSnapshot:
    path: Path
    kind: str
    size: int
    sha256: str
    identity: tuple[int, int, int, int, int]  # device, inode, size, mtime_ns, birthtime/ctime_ns


@dataclass(frozen=True)
class RecoveryAssessment:
    state_directory: Path
    process_lock_directory: Path
    status: str
    eligible: bool
    reasons: tuple[str, ...]
    files: tuple[FileSnapshot, ...]
    inventory_sha256: str
    processes: tuple[ProcessEvidence, ...]
    candidate_paths: tuple[Path, ...]
    next_steps: tuple[str, ...]
    directory_identities: tuple[tuple[str, tuple[int, int, int, int, int] | None], ...] = ()
    read_only: bool = True
    mutation_authorized: bool = False


class _FileTime(ctypes.Structure):
    _fields_ = [("low", _DWORD), ("high", _DWORD)]


class _ProcessEntry(ctypes.Structure):
    _fields_ = [("size", _DWORD), ("usage", _DWORD), ("pid", _DWORD),
                ("heap", ctypes.c_size_t), ("module", _DWORD), ("threads", _DWORD),
                ("parent", _DWORD), ("priority", ctypes.c_int32), ("flags", _DWORD),
                ("name", ctypes.c_wchar * 260)]


def _api():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    signatures = {
        "OpenProcess": ([ _DWORD, wintypes.BOOL, _DWORD], wintypes.HANDLE),
        "GetProcessTimes": ([wintypes.HANDLE] + [ctypes.POINTER(_FileTime)] * 4, wintypes.BOOL),
        "WaitForSingleObject": ([wintypes.HANDLE, _DWORD], _DWORD),
        "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
        "CreateToolhelp32Snapshot": ([_DWORD, _DWORD], wintypes.HANDLE),
        "Process32FirstW": ([wintypes.HANDLE, ctypes.POINTER(_ProcessEntry)], wintypes.BOOL),
        "Process32NextW": ([wintypes.HANDLE, ctypes.POINTER(_ProcessEntry)], wintypes.BOOL),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(kernel, name)
        function.argtypes, function.restype = arguments, result
    return kernel


def _last_error(kernel):
    if hasattr(kernel, "last_error"):
        return int(kernel.last_error)
    return getattr(ctypes, "get_last_error", lambda: 0)()


def _pid_absent(kernel, pid):
    snapshot = kernel.CreateToolhelp32Snapshot(0x02, 0)
    if not snapshot or snapshot == ctypes.c_void_p(-1).value:
        return None, "Process snapshot failed", _last_error(kernel)
    result, detail, error = None, "Process enumeration was incomplete", None
    try:
        entry = _ProcessEntry()
        entry.size = ctypes.sizeof(entry)
        if not kernel.Process32FirstW(snapshot, ctypes.byref(entry)):
            return None, "Empty/failed snapshot cannot corroborate PID absence", _last_error(kernel)
        deadline = time.monotonic() + 2
        count = 0
        while True:
            count += 1
            if entry.pid == pid:
                result, detail = False, "PID is present despite failed OpenProcess"
                break
            if count > 131072 or time.monotonic() > deadline:
                detail = "Process snapshot exceeded its count/time bound"
                break
            if not kernel.Process32NextW(snapshot, ctypes.byref(entry)):
                error = _last_error(kernel)
                if error == ERROR_NO_MORE_FILES:
                    result, detail, error = True, "Successful complete process snapshot omits this PID", None
                break
    finally:
        if not kernel.CloseHandle(snapshot):
            result, detail, error = None, "Process snapshot handle cleanup failed", _last_error(kernel)
    return result, detail, error


class WindowsProcessProbe:
    """Query held process times and signal state, without privilege changes."""
    def __init__(self, kernel=None):
        self.kernel = kernel

    def __call__(self, identity: ProcessIdentity) -> ProcessObservation:
        if not isinstance(identity, ProcessIdentity):
            raise ValueError("The probe requires an explicit ProcessIdentity.")
        if sys.platform != "win32" and self.kernel is None:
            return ProcessObservation(identity, "unknown", detail="Exact process proof requires Windows")
        kernel = self.kernel or _api()
        handle = kernel.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, identity.pid)
        if not handle:
            error = _last_error(kernel)
            if error == ERROR_INVALID_PARAMETER:
                absent, detail, snapshot_error = _pid_absent(kernel, identity.pid)
                if absent is True:
                    return ProcessObservation(identity, "absent", detail=detail, error=error)
                return ProcessObservation(identity, "unknown", detail=detail, error=snapshot_error or error)
            return ProcessObservation(identity, "unknown", detail="Process access failed; death is unproven", error=error)
        result = ProcessObservation(identity, "unknown", detail="Process query did not complete")
        try:
            creation, exit_time, kernel_time, user_time = (_FileTime() for _ in range(4))
            if not kernel.GetProcessTimes(handle, ctypes.byref(creation), ctypes.byref(exit_time),
                                          ctypes.byref(kernel_time), ctypes.byref(user_time)):
                result = ProcessObservation(identity, "unknown", detail="GetProcessTimes failed",
                                            error=_last_error(kernel))
            else:
                created = creation.low | creation.high << 32
                waited = int(kernel.WaitForSingleObject(handle, 0))
                if not created or waited not in {WAIT_OBJECT_0, WAIT_TIMEOUT}:
                    result = ProcessObservation(identity, "unknown", created or None, waited,
                                                "Creation time or process signal is uncertain", _last_error(kernel))
                elif identity.created is not None and created != identity.created:
                    result = ProcessObservation(identity, "reused", created, waited,
                                                "PID now names a different creation identity; the recorded identity ended")
                else:
                    result = ProcessObservation(identity, "dead" if waited == WAIT_OBJECT_0 else "alive",
                                                created, waited, "Held process object signal and creation time verified")
        finally:
            if not kernel.CloseHandle(handle):
                result = ProcessObservation(identity, "unknown", result.observed_created, result.wait_result,
                                            "Process handle cleanup failed", _last_error(kernel))
        return result

    probe = __call__


def current_process_identity(process_probe=None) -> ProcessIdentity:
    """Return own FILETIME identity, or an explicit unproven legacy identity.

    A query failure never fabricates a creation time. New state locks should use
    {schema:2,owner_pid,owner_created,nonce} only when ``created`` is available;
    otherwise preserve {owner_pid,nonce}, which recovery deliberately blocks.
    """
    identity = ProcessIdentity(os.getpid(), None)
    probe = process_probe or WindowsProcessProbe()
    try:
        observed = probe(identity) if callable(probe) else probe.probe(identity)
        if (isinstance(observed, ProcessObservation) and observed.identity == identity
                and observed.status == "alive" and observed.wait_result == WAIT_TIMEOUT
                and type(observed.observed_created) is int
                and 0 < observed.observed_created <= 0xFFFFFFFFFFFFFFFF):
            return ProcessIdentity(identity.pid, observed.observed_created)
    except Exception:
        pass
    return identity


class _AssessmentError(ValueError):
    pass


_FENCE_AUTHORITY = object()


class _FenceAllowance:
    """Controller-only lease for one held recovery fence; never JSON input."""
    def __init__(self, authority, path, raw, checker):
        if authority is not _FENCE_AUTHORITY:
            raise ValueError("Recovery fence evidence requires its held controller lease")
        self.path, self.raw, self.checker = path, raw, checker


def _issue_fence_allowance(path, raw, checker):
    return _FenceAllowance(_FENCE_AUTHORITY, path, raw, checker)


def _fingerprint(information):
    # Windows path stat and fstat can differ in legacy st_ctime. Use the
    # explicit birthtime shared by both, with POSIX ctime as the fallback.
    return (information.st_dev, information.st_ino, information.st_size,
            information.st_mtime_ns, getattr(information, "st_birthtime_ns", information.st_ctime_ns))


def _safe_stat(path, *, directory=False):
    information = path.lstat()
    if (stat.S_ISLNK(information.st_mode) or getattr(information, "st_file_attributes", 0) & 0x400
            or directory and not stat.S_ISDIR(information.st_mode)
            or not directory and not stat.S_ISREG(information.st_mode)
            or not directory and information.st_nlink != 1):
        raise _AssessmentError(f"Unsafe reparse, linked, or nonregular recovery path: {path.name}")
    return information


def _inventory(state_directory, process_directory):
    files, directories = {}, []
    for root, shared in ((state_directory, False), (process_directory, True)):
        if not os.path.lexists(root):
            if not shared:
                raise _AssessmentError("The state directory is absent")
            directories.append((str(root), None))
            continue
        directories.append((str(root), _fingerprint(_safe_stat(root, directory=True))))
        with os.scandir(root) as items:
            for item in items:
                path = root / item.name
                if not shared and item.name == "hooks":
                    directories.append((str(path), _fingerprint(_safe_stat(path, directory=True))))
                    with os.scandir(path) as journals:
                        for journal in journals:
                            child = path / journal.name
                            files[child] = "journal"
                            _safe_stat(child)
                            if len(files) > MAX_FILES:
                                raise _AssessmentError("Recovery inventory exceeded its file-count bound")
                else:
                    files[path] = "shared" if shared else "state-file"
                    _safe_stat(path)
                    if len(files) > MAX_FILES:
                        raise _AssessmentError("Recovery inventory exceeded its file-count bound")
    return files, tuple(sorted(directories))


def _snapshots(files, deadline, fence=None):
    snapshots, raw = [], {}
    total = 0
    for path, kind in sorted(files.items(), key=lambda item: str(item[0])):
        before = _safe_stat(path)
        limit = MAX_JOURNAL_BYTES if kind == "journal" else 1024 * 1024
        total += before.st_size
        if before.st_size > limit or total > MAX_SNAPSHOT_BYTES:
            raise _AssessmentError("Recovery files exceeded their individual/total byte bounds")
        if fence is not None and path == fence.path:
            held_identity = fence.checker()
            if held_identity != _fingerprint(before) or len(fence.raw) != before.st_size:
                raise _AssessmentError("Held recovery fence identity changed")
            raw[path] = fence.raw
            snapshots.append(FileSnapshot(path, kind, len(fence.raw), hashlib.sha256(fence.raw).hexdigest(), held_identity))
            continue
        parts, digest, size = [], hashlib.sha256(), 0
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                    or _fingerprint(opened) != _fingerprint(before)):
                raise _AssessmentError("An opened recovery file differs from the inspected path identity")
            while True:
                if time.monotonic() > deadline:
                    raise _AssessmentError("Recovery snapshot exceeded its elapsed-time bound")
                part = stream.read(1024 * 1024)
                if not part:
                    break
                size += len(part)
                if size > limit or size > before.st_size:
                    raise _AssessmentError("A recovery file grew while being read")
                digest.update(part)
                parts.append(part)
            closed_read = os.fstat(stream.fileno())
            if (_fingerprint(closed_read) != _fingerprint(before)
                    or closed_read.st_ctime_ns != opened.st_ctime_ns):
                raise _AssessmentError("The held recovery file changed while being read")
        after = _safe_stat(path)
        if _fingerprint(before) != _fingerprint(after) or size != before.st_size:
            raise _AssessmentError("A recovery file changed identity or size while being read")
        raw[path] = b"".join(parts)
        snapshots.append(FileSnapshot(path, kind, size, digest.hexdigest(), _fingerprint(after)))
    return tuple(snapshots), raw


def _document(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise _AssessmentError("Duplicate JSON keys are not recovery evidence")
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=pairs,
                           parse_constant=lambda value: (_ for _ in ()).throw(_AssessmentError("Nonfinite JSON value")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise _AssessmentError("Recovery JSON is corrupt or ambiguous") from exc
    if not isinstance(value, dict):
        raise _AssessmentError("Recovery evidence must be a JSON object")
    return value


def _fields(document, required, optional=()):
    if not set(required) <= set(document) or set(document) - set(required) - set(optional):
        raise _AssessmentError("Recovery record contains missing or unknown schema fields")


def _identity(document, pid="target_pid", created="target_created"):
    try:
        result = ProcessIdentity(document[pid], document[created])
    except (KeyError, ValueError) as exc:
        raise _AssessmentError("Recovery target has no exact PID/creation identity") from exc
    if result.created is None:
        raise _AssessmentError("Recovery target creation time is missing")
    return result


def _owner(document):
    _fields(document, {"owner_pid", "nonce"}, {"owner_created", "schema"})
    if (not isinstance(document["nonce"], str) or not _HEX32.fullmatch(document["nonce"])
            or "schema" in document and (type(document["schema"]) is not int or document["schema"] != 2)
            or "schema" in document and document.get("owner_created") is None):
        raise _AssessmentError("Unknown or corrupt native owner-lock schema")
    try:
        return ProcessIdentity(document["owner_pid"], document.get("owner_created"))
    except ValueError as exc:
        raise _AssessmentError("Invalid native owner identity") from exc


def _trainer(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{16}", value):
        raise _AssessmentError("Invalid native trainer identity")
    return value


def _state(document):
    _fields(document, {"payload", "sha256"})
    payload = document["payload"]
    if not isinstance(payload, dict):
        raise _AssessmentError("Native state payload is malformed")
    _fields(payload, {"schema", "engine", "trainer_id", "table_sha256", "process_name", "desired"})
    desired = payload["desired"]
    if (type(payload["schema"]) is not int or payload["schema"] != 1 or payload["engine"] != "ct2trainer"
            or not isinstance(payload["table_sha256"], str) or not _HEX64.fullmatch(payload["table_sha256"])
            or not isinstance(payload["process_name"], str)
            or not re.fullmatch(r'[^\\/:*?"<>|\x00-\x1f]+\.exe', payload["process_name"], re.I)
            or not isinstance(desired, list) or len(desired) > 20000
            or any(type(item) is not int or item < 0 for item in desired)
            or desired != sorted(set(desired))):
        raise _AssessmentError("Native state schema or desired IDs are invalid")
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if document["sha256"] != hashlib.sha256(canonical).hexdigest():
        raise _AssessmentError("Native state checksum is invalid")
    return _trainer(payload["trainer_id"]), payload["table_sha256"]


def _session(document):
    _fields(document, {"schema", "owner", "trainer_id", "target_pid", "target_created"})
    if type(document["schema"]) is not int or document["schema"] != 1 or not isinstance(document["owner"], dict):
        raise _AssessmentError("Unknown native session schema")
    return _owner(document["owner"]), _trainer(document["trainer_id"]), _identity(document)


def _range(address, size, limit=4 * 1024 * 1024):
    if (type(address) is not int or type(size) is not int or not 0 < size <= limit
            or not 0 < address <= 0x7FFFFFFFFFFF or size - 1 > 0x7FFFFFFFFFFF - address):
        raise _AssessmentError("Receipt contains an invalid memory range")


def _bytes(value, maximum):
    if (not isinstance(value, str) or not value or len(value) > maximum * 2
            or not re.fullmatch(r"(?:[0-9a-fA-F]{2})+", value)):
        raise _AssessmentError("Receipt bytes are invalid or oversized")
    return len(value) // 2


def _symbols(value):
    if (not isinstance(value, dict) or len(value) > 4096
            or any(not _SYMBOL.fullmatch(name) for name in value)):
        raise _AssessmentError("Receipt symbols are invalid")
    for address in value.values():
        _range(address, 1)


def _literal_spans(value, start, size, allocation):
    if not isinstance(value, list) or len(value) > 4096:
        raise _AssessmentError("Literal receipt spans are invalid")
    spans = []
    for item in value:
        if not isinstance(item, dict):
            raise _AssessmentError("Literal receipt span is malformed")
        _fields(item, {"address", "size", "allocation"})
        _range(item["address"], item["size"])
        if (item["allocation"] != allocation or not start <= item["address"]
                or item["address"] + item["size"] > start + size):
            raise _AssessmentError("Literal receipt span crosses its owner")
        spans.append((item["address"], item["size"]))
    ordered = sorted(spans)
    if any(address + length > next_address for (address, length), (next_address, _) in zip(ordered, ordered[1:])):
        raise _AssessmentError("Literal receipt spans overlap")


def _hook(document, trainer_id):
    _fields(document, {"schema", "engine", "owner", "target_pid", "target_created", "state", "uncertain",
                       "allocations", "blocks", "entries", "exports", "retirement_policy"},
            {"data_commit", "owned_data_ranges", "owned_executable_data_ranges", "external_data_program"})
    if (type(document["schema"]) is not int or document["schema"] != 1
            or document["engine"] != "ct2trainer-hooks"
            or not isinstance(document["owner"], str) or not 0 < len(document["owner"]) <= 256
            or trainer_id is not None and not document["owner"].startswith(trainer_id + ":")
            or document["state"] not in {"preparing", "staging-intent", "staged", "publication-intent", "enabled",
                                        "disable-intent", "retired", "uncertain", "abandon-intent", "abandoned",
                                        "target-exited", "data-commit-intent"}
            or type(document["uncertain"]) is not bool
            or type(document.get("data_commit", False)) is not bool
            or document["retirement_policy"] != "retain-published-allocations-until-target-exit"):
        raise _AssessmentError("Unknown or unbound owned-hook schema")
    external_program = document.get("external_data_program")
    if "external_data_program" in document and external_program is None:
        raise _AssessmentError("External data source profile cannot be null")
    if external_program is not None:
        try:
            from .aa_program import validate_program, _pure_literal_profile
            validate_program(external_program)
            if not _pure_literal_profile(external_program):
                raise ValueError("not pure literal")
        except Exception as exc:
            raise _AssessmentError("External data source profile is invalid") from exc
        if (document["allocations"] or document["blocks"] or document.get("data_commit", False)
                or document.get("owned_data_ranges") or document.get("owned_executable_data_ranges")):
            raise _AssessmentError("External data diagnostics cannot mix allocation/code provenance")
    allocations = document["allocations"]
    if not isinstance(allocations, dict) or len(allocations) > 128:
        raise _AssessmentError("Hook allocation inventory is invalid")
    for name, item in allocations.items():
        if not _SYMBOL.fullmatch(name) or not isinstance(item, dict):
            raise _AssessmentError("Hook allocation is malformed")
        _fields(item, {"address", "size", "budget_size", "near", "executable", "state"},
                {"writable", "actual_size", "literal_data_ranges"})
        if (type(item["size"]) is not int or not 0 < item["size"] <= 4 * 1024 * 1024
                or type(item["budget_size"]) is not int or not item["size"] <= item["budget_size"] <= 16 * 1024 * 1024
                or type(item["executable"]) is not bool or type(item.get("writable", False)) is not bool
                or item["state"] not in {"allocation-intent", "allocated", "staged", "published", "retained",
                                         "released-unpublished"}):
            raise _AssessmentError("Hook allocation policy is invalid")
        if item["near"] is not None:
            _range(item["near"], 1)
        actual = item.get("actual_size")
        if actual is not None and (type(actual) is not int or not item["size"] <= actual <= 4 * 1024 * 1024):
            raise _AssessmentError("Hook actual allocation size is invalid")
        if item["address"] is not None:
            _range(item["address"], actual or item["size"])
            _literal_spans(item.get("literal_data_ranges", []), item["address"], item["size"], name)
        elif item.get("literal_data_ranges"):
            raise _AssessmentError("Unlocated allocation cannot have literal spans")
    total = 0
    for kind in ("blocks", "entries"):
        values = document[kind]
        if not isinstance(values, list) or len(values) > 4096:
            raise _AssessmentError("Hook block inventory is invalid")
        for item in values:
            if not isinstance(item, dict):
                raise _AssessmentError("Hook block is malformed")
            _fields(item, {"address", "bytes", "original", "is_allocation", "executable",
                           "requires_coordinator", "allocation"},
                    {"state", "literal_data", "literal_data_ranges", "data_semantics", "data_allocation", "external_data", "external_source_sha256"})
            size = _bytes(item["bytes"], 4 * 1024 * 1024 if kind == "blocks" else 65536)
            if _bytes(item["original"], size) != size:
                raise _AssessmentError("Hook original and replacement sizes differ")
            total += size
            _range(item["address"], size)
            if (any(type(item[key]) is not bool for key in ("is_allocation", "executable", "requires_coordinator"))
                    or any(type(item.get(key, False)) is not bool for key in ("literal_data", "data_semantics"))
                    or item["is_allocation"] != (kind == "blocks")
                    or kind == "entries" and item.get("state") not in {"unpublished", "installed", "restored", "committed"}):
                raise _AssessmentError("Hook block classification is invalid")
            if kind == "blocks":
                allocation = allocations.get(item["allocation"])
                if (allocation is None or allocation["address"] is None
                        or not allocation["address"] <= item["address"]
                        or item["address"] + size > allocation["address"] + allocation["size"]):
                    raise _AssessmentError("Hook block exceeds its allocation")
                _literal_spans(item.get("literal_data_ranges", []), item["address"], size, item["allocation"])
            elif item["allocation"] is not None or item.get("literal_data_ranges"):
                raise _AssessmentError("External hook entries cannot mint allocation spans")
            if "external_data" in item or "external_source_sha256" in item:
                if (external_program is None or kind != "entries" or item.get("external_data") is not True
                        or item.get("external_source_sha256") != external_program["source_sha256"]
                        or item["executable"] or not item["requires_coordinator"]
                        or item.get("literal_data") is not True or item.get("data_semantics", False)
                        or item.get("data_allocation") is not None):
                    raise _AssessmentError("External data classification is unbound or malformed")
            elif external_program is not None:
                raise _AssessmentError("External data source profile has an unclassified entry")
            owner_range = item.get("data_allocation")
            if item.get("data_semantics", False):
                if (not item["executable"] or not item["requires_coordinator"] or not item.get("literal_data")
                        or not isinstance(owner_range, list) or len(owner_range) != 2):
                    raise _AssessmentError("Executable literal entry has no owning range")
                _range(*owner_range)
                if not owner_range[0] <= item["address"] or item["address"] + size > sum(owner_range):
                    raise _AssessmentError("Executable literal entry crosses its owner")
            elif owner_range is not None:
                raise _AssessmentError("Code entries cannot claim data-owner bounds")
    if external_program is not None and not document["entries"]:
        raise _AssessmentError("External data source diagnostics require nonempty entries")
    if total > 16 * 1024 * 1024:
        raise _AssessmentError("Hook byte inventory exceeds its bound")
    _symbols(document["exports"])
    for field, width in (("owned_data_ranges", 2), ("owned_executable_data_ranges", 4)):
        values = document.get(field, [])
        if not isinstance(values, list) or len(values) > 4096:
            raise _AssessmentError("Hook provenance range inventory is invalid")
        for item in values:
            if not isinstance(item, list) or len(item) != width:
                raise _AssessmentError("Hook provenance range is malformed")
            _range(*item[:2])
            if width == 4:
                _range(*item[2:])
                if not item[2] <= item[0] or item[0] + item[1] > item[2] + item[3]:
                    raise _AssessmentError("Hook provenance exceeds its owner")
    if document.get("data_commit", False) and (allocations or document["exports"] or not document["entries"]
            or any(not item.get("data_semantics", False) for item in document["entries"])
            or document["state"] not in {"abandoned", "uncertain"}):
        raise _AssessmentError("Data-commit receipt is not a terminal literal transaction")
    return _identity(document)


def _lua(document, trainer_id, table_sha256):
    _fields(document, {"schema", "engine", "trainer_id", "table_sha256", "state", "target", "owner",
                       "data", "symbols", "assemblies", "pending"}, {'nth_aob_results'})
    if (document["schema"] != "ct2trainer-lua-activation/v1" or document["engine"] != "ct2trainer-lua"
            or _trainer(document["trainer_id"]) != trainer_id
            or document["table_sha256"] != table_sha256 or not isinstance(table_sha256, str)
            or not _HEX64.fullmatch(table_sha256)
            or document["state"] not in {"open", "data-write-intent", "closing", "uncertain", "abandoned", "target-exited"}
            or type(document["owner"]) is not int or document["owner"] < 0
            or not isinstance(document["target"], list) or len(document["target"]) != 2):
        raise _AssessmentError("Unknown or unbound Lua activation receipt")
    target = _identity(dict(zip(("target_pid", "target_created"), document["target"])))
    if 'nth_aob_results' in document:
        from .nth_aob import MAX_DEFINITIONS, validate_result
        scans=document['nth_aob_results']
        if type(scans) is not list or not 1<=len(scans)<=MAX_DEFINITIONS:
            raise _AssessmentError('Invalid bounded nth-AOB Lua evidence inventory')
        symbols=set()
        for result in scans:
            try:
                validate_result(result)
            except (ValueError,TypeError,KeyError) as exc:
                raise _AssessmentError('Malformed nth-AOB Lua evidence') from exc
            symbol=result['definition']['symbol'].casefold()
            if result['target']!=document['target'] or symbol in symbols:
                raise _AssessmentError('Nth-AOB Lua evidence has foreign target or duplicate symbol')
            symbols.add(symbol)
    values = document["data"]
    if not isinstance(values, list) or len(values) > 1024:
        raise _AssessmentError("Lua data-undo inventory is invalid")
    total = 0
    for item in values:
        if not isinstance(item, dict):
            raise _AssessmentError("Lua data undo is malformed")
        _fields(item, {"address", "original", "current"})
        size = _bytes(item["original"], 65536)
        if _bytes(item["current"], 65536) != size:
            raise _AssessmentError("Lua data-undo sizes differ")
        _range(item["address"], size)
        total += size
        if document["state"] == "abandoned" and item["original"] != item["current"]:
            raise _AssessmentError("Abandoned Lua receipt contains an unfinished undo")
    if total > 1024 * 1024:
        raise _AssessmentError("Lua data-undo inventory exceeds its byte bound")
    _symbols(document["symbols"])
    assemblies = document["assemblies"]
    if not isinstance(assemblies, dict) or len(assemblies) > 128:
        raise _AssessmentError("Lua assembler receipt inventory is invalid")
    for token, item in assemblies.items():
        if not _HEX32.fullmatch(token) or not isinstance(item, dict):
            raise _AssessmentError("Lua assembler reference is malformed")
        _fields(item, {"source_sha256", "journal"})
        if not isinstance(item["source_sha256"], str) or not _HEX64.fullmatch(item["source_sha256"]) or not isinstance(item["journal"], str):
            raise _AssessmentError("Lua assembler reference has invalid hash/path")
    pending = document["pending"]
    if pending is not None:
        if not isinstance(pending, dict):
            raise _AssessmentError("Lua pending mutation is malformed")
        _fields(pending, {"address", "before", "after"})
        size = _bytes(pending["before"], 65536)
        if _bytes(pending["after"], 65536) != size:
            raise _AssessmentError("Lua pending mutation sizes differ")
        _range(pending["address"], size)
    if document["state"] in {"abandoned", "target-exited"} and (assemblies or document["symbols"] or pending is not None):
        raise _AssessmentError("Terminal Lua receipt retains active resources")
    return target, tuple(item["journal"] for item in assemblies.values())


_RECOVERY_PLAN = (
    "Acquire exclusive CREATE_NEW recovery claims with current PID, creation time, and nonce; normal controllers must honor these claims.",
    "Reassess all exact owner/target identities and every file hash, file identity, and directory inventory under the exclusive claims; reject any change.",
    "Create an exclusive evidence archive and manifest, flush it durably, and verify its hashes before releasing any ownership artifact.",
    "Use a durable recovery transaction journal and same-directory atomic quarantine renames of exact expected files; multiple renames are not one atomic transaction.",
    "Release only the verified obsolete shared process claims, local session, and hook/Lua artifacts; release state.lock last and preserve committed state.json.",
    "Preserve incomplete state/journal temporary files as evidence; never silently promote them, restore remote memory, or infer saved ON state from a crash.",
)


def assess_recovery(state_directory: str | Path, process_lock_directory: str | Path | None = None,
                    *, process_probe: Callable[[ProcessIdentity], ProcessObservation] | None = None,
                    expected_trainer_id: str | None = None,
                    expected_table_sha256: str | None = None,
                    exclusive_controller_claim: bool = False,
                    _fence_allowance: _FenceAllowance | None = None) -> RecoveryAssessment:
    """Assess only recorded identities and stable evidence; perform no mutation.

    Three file snapshots surround two independent process observations. Every
    exact recorded target and the current owner must be proven dead in both
    observations. This is eligibility for a future exclusive transaction, not
    permission to delete files or a substitute for transaction-time revalidation.

    ``exclusive_controller_claim`` documents that the caller exclusively holds
    the state claim for this directory, so no other controller can act on it.
    Only then may orphaned ownership artifacts without a bound state/session
    owner document (e.g. an unfinalized receipt left by a crashed session) be
    eligible once their recorded owner and target pass the normal death proof.
    The default ``False`` preserves the conservative legacy behavior.
    """
    directory = Path(os.path.abspath(state_directory))
    shared = Path(os.path.abspath(process_lock_directory)) if process_lock_directory is not None else directory.parent / "_process_sessions"
    reasons, candidates, roles, first_observations, final_observations = [], set(), {}, {}, {}
    snapshots, raw, directories = (), {}, ()
    trainer_id, table_sha256 = expected_trainer_id, expected_table_sha256
    deadline = time.monotonic() + MAX_ASSESS_SECONDS
    probe = process_probe or WindowsProcessProbe()
    ownership_artifacts = False
    fence_owner_document = None

    def problem(message):
        if message not in reasons:
            reasons.append(message)

    def identity_role(identity, role):
        roles.setdefault(identity, set()).add(role)
        if len(roles) > MAX_IDENTITIES:
            raise _AssessmentError("Recovery identities exceed the bounded process count")

    def bind_identity(found_trainer, found_table=None):
        nonlocal trainer_id, table_sha256
        if trainer_id is None:
            trainer_id = found_trainer
        elif found_trainer != trainer_id:
            raise _AssessmentError("Evidence belongs to another trainer identity")
        if found_table is not None:
            if table_sha256 is None:
                table_sha256 = found_table
            elif found_table != table_sha256:
                raise _AssessmentError("Evidence belongs to another table hash")

    def observe(identity):
        if time.monotonic() > deadline:
            return ProcessObservation(identity, "unknown", detail="Recovery process proof exceeded its time bound")
        try:
            result = probe(identity) if callable(probe) else probe.probe(identity)
            if (not isinstance(result, ProcessObservation) or result.identity != identity
                    or result.status not in {"alive", "dead", "reused", "absent", "unknown"}):
                raise ValueError("Injected probe returned foreign or invalid identity evidence")
            return result
        except Exception as exc:
            return ProcessObservation(identity, "unknown", detail=f"Process proof failed: {type(exc).__name__}")

    try:
        if trainer_id is not None:
            _trainer(trainer_id)
        if table_sha256 is not None and (not isinstance(table_sha256, str) or not _HEX64.fullmatch(table_sha256)):
            raise _AssessmentError("Expected table hash is invalid")
        if directory == shared or directory in shared.parents or shared in directory.parents:
            raise _AssessmentError("State and shared-lock directories must have separate ownership scopes")
        fence = _fence_allowance
        if fence is not None:
            if type(fence) is not _FenceAllowance or fence.path != directory / "recovery.lock":
                raise _AssessmentError("Foreign or serialized recovery fences cannot be exempted")
            document = _document(fence.raw)
            _fields(document, {"schema", "engine", "owner_pid", "owner_created", "nonce", "trainer_id",
                               "table_sha256", "assessment_sha256"})
            if (document["schema"] != 1 or type(document["schema"]) is not int
                    or document["engine"] != "ct2trainer-recovery-fence"
                    or document["trainer_id"] != trainer_id or document["table_sha256"] != table_sha256
                    or not isinstance(document["nonce"], str) or not _HEX32.fullmatch(document["nonce"])
                    or not isinstance(document["assessment_sha256"], str) or not _HEX64.fullmatch(document["assessment_sha256"])):
                raise _AssessmentError("Held recovery fence schema or identity is invalid")
            _identity(document, "owner_pid", "owner_created")
        files, directories = _inventory(directory, shared)
        if fence is not None and fence.path not in files:
            raise _AssessmentError("Held recovery fence disappeared from the state inventory")
        snapshots, raw = _snapshots(files, deadline, fence)
        documents = {}
        for path, kind in files.items():
            recognized = ((kind == "state-file" and path.name in {"state.lock", "state.json", "state.json.tmp",
                                                                   "session.json", "oneshot.json", "oneshot.json.tmp",
                                                                   "recovery.lock"})
                          or kind == "state-file" and re.fullmatch(
                              r"(?:state|oneshot)\.json\.corrupt-\d{8}T\d{6}Z(?:-\d{2})?", path.name)
                          or fence is not None and path == fence.path
                          or kind == "shared" and path.suffix == ".json"
                          or kind == "journal" and re.fullmatch(r"[^/\\]+\.json(?:\.[0-9a-f]{32}\.tmp)?", path.name))
            if not recognized:
                problem(f"Unknown recovery artifact: {path.name}")
                continue
            # One-shot marker files are inert per-trainer data without a
            # process identity, and quarantined corrupt- files are preserved
            # evidence bytes; the engine quarantines unreadable state at
            # startup, so neither gates the assessment itself.
            if path.name in ("oneshot.json", "oneshot.json.tmp") or re.fullmatch(
                    r"(?:state|oneshot)\.json\.corrupt-\d{8}T\d{6}Z(?:-\d{2})?", path.name):
                continue
            try:
                documents[path] = _document(raw[path])
            except _AssessmentError as exc:
                problem(f"{path.name}: {exc}")

        for name in ("state.json", "state.json.tmp"):
            path = directory / name
            if path in files and name.endswith(".tmp"):
                ownership_artifacts = True
                candidates.add(path)
            if path in documents:
                try:
                    bind_identity(*_state(documents[path]))
                except (ValueError, TypeError, KeyError) as exc:
                    problem(f"{name}: {exc}")
        if (directory / "oneshot.json.tmp") in files:
            # Incomplete marker write from a crashed save; released with the
            # other artifacts once every recorded owner is proven dead.
            ownership_artifacts = True
            candidates.add(directory / "oneshot.json.tmp")
        for path, kind in files.items():
            if kind == "state-file" and re.fullmatch(
                    r"(?:state|oneshot)\.json\.corrupt-\d{8}T\d{6}Z(?:-\d{2})?", path.name):
                # Quarantined corrupt bytes left by a healed startup; the exact
                # bytes are preserved in the archive when released.
                ownership_artifacts = True
                candidates.add(path)

        owner_document, session_document, session_target = None, None, None
        lock_path, session_path = directory / "state.lock", directory / "session.json"
        if lock_path in files:
            ownership_artifacts = True
            candidates.add(lock_path)
        if lock_path in documents:
            try:
                owner_document = documents[lock_path]
                identity_role(_owner(owner_document), "state owner")
            except (ValueError, TypeError, KeyError) as exc:
                owner_document = None
                problem(f"state.lock: {exc}")
        if session_path in files:
            ownership_artifacts = True
            candidates.add(session_path)
        if session_path in documents:
            try:
                session_document = documents[session_path]
                owner, found_trainer, session_target = _session(session_document)
                bind_identity(found_trainer)
                identity_role(owner, "session owner")
                identity_role(session_target, "session target")
                if owner_document is None and lock_path not in files:
                    owner_document = session_document["owner"]
                elif owner_document != session_document["owner"]:
                    problem("Session owner differs from the state-lock owner")
            except (ValueError, TypeError, KeyError) as exc:
                session_document = None
                problem(f"session.json: {exc}")

        fence_path = directory / "recovery.lock"
        if fence_path in files:
            ownership_artifacts = True
        if fence_path in documents:
            try:
                fence_document = documents[fence_path]
                _fields(fence_document, {"schema", "engine", "owner_pid", "owner_created", "nonce",
                                         "trainer_id", "table_sha256", "assessment_sha256"})
                if (type(fence_document["schema"]) is not int or fence_document["schema"] != 1
                        or fence_document["engine"] != "ct2trainer-recovery-fence"
                        or not isinstance(fence_document["nonce"], str) or not _HEX32.fullmatch(fence_document["nonce"])
                        or not isinstance(fence_document["assessment_sha256"], str)
                        or not _HEX64.fullmatch(fence_document["assessment_sha256"])):
                    raise _AssessmentError("Recovery fence schema or identity is invalid")
                bind_identity(_trainer(fence_document["trainer_id"]), fence_document["table_sha256"])
                fence_owner_document = fence_document
                fence_owner = _identity(fence_document, "owner_pid", "owner_created")
                if fence_owner != current_process_identity():
                    # A fence owned by another (crashed) process is a stale
                    # artifact: release it with the other candidates once its
                    # exact owner is proven dead. The operator's own active
                    # fence is its lease, never a recovery candidate.
                    candidates.add(fence_path)
                    identity_role(fence_owner, "recovery-fence owner")
            except (ValueError, TypeError, KeyError) as exc:
                fence_owner_document = None
                problem(f"recovery.lock: {exc}")

        related_shared = {}
        for path, kind in files.items():
            if kind != "shared" or path not in documents:
                continue
            try:
                document = documents[path]
                owner, found_trainer, target = _session(document)
                if path.name != f"{target.pid}-{target.created}.json":
                    raise _AssessmentError("Shared lock filename differs from its exact target identity")
                same_owner = owner_document is not None and document["owner"] == owner_document
                if same_owner:
                    bind_identity(found_trainer)
                matches = same_owner and found_trainer == trainer_id
                if matches:
                    ownership_artifacts = True
                    related_shared[path] = document
                    candidates.add(path)
                    identity_role(owner, "shared-lock owner")
                    identity_role(target, "shared-lock target")
                elif owner_document is None and found_trainer == trainer_id:
                    ownership_artifacts = True
                    if exclusive_controller_claim:
                        # The caller exclusively holds the state claim for this
                        # directory, so the orphaned claim is released with the
                        # other verified artifacts; its recorded owner and
                        # target still pass the normal two-observation proof.
                        related_shared[path] = document
                        candidates.add(path)
                        identity_role(owner, "shared-lock owner")
                        identity_role(target, "shared-lock target")
                    else:
                        problem("A matching shared claim has no bound state/session owner")
            except (ValueError, TypeError, KeyError) as exc:
                problem(f"{path.name}: {exc}")
        if session_document is not None and session_target is not None:
            expected = shared / f"{session_target.pid}-{session_target.created}.json"
            if expected not in related_shared or raw.get(expected) != raw[session_path]:
                problem("Session has no byte-identical shared target claim")

        # Bind a first valid Lua table identity when a crash preceded state save.
        for path, document in documents.items():
            if files[path] == "journal" and document.get("engine") == "ct2trainer-lua":
                try:
                    if not isinstance(document.get("table_sha256"), str) or not _HEX64.fullmatch(document["table_sha256"]):
                        raise _AssessmentError("Lua table identity is invalid")
                    bind_identity(_trainer(document.get("trainer_id")), document["table_sha256"])
                except (ValueError, TypeError, KeyError) as exc:
                    problem(f"{path.name}: {exc}")
        hook_targets, lua_references = {}, []
        for path, kind in files.items():
            if kind != "journal":
                continue
            ownership_artifacts = True
            candidates.add(path)
            if path not in documents:
                continue
            try:
                document = documents[path]
                if document.get("engine") == "ct2trainer-hooks":
                    target = _hook(document, trainer_id)
                    hook_targets[os.path.normcase(str(path))] = target
                elif document.get("engine") == "ct2trainer-lua":
                    target, references = _lua(document, trainer_id, table_sha256)
                    lua_references.extend((path, target, reference) for reference in references)
                else:
                    raise _AssessmentError("Unknown hook/Lua journal engine or schema")
                identity_role(target, "journal target: " + path.name)
            except (ValueError, TypeError, KeyError) as exc:
                problem(f"{path.name}: {exc}")
        for path, target, reference in lua_references:
            declared = Path(reference)
            key = os.path.normcase(os.path.abspath(declared))
            if (not declared.is_absolute() or declared.parent != directory / "hooks"
                    or hook_targets.get(key) != target):
                problem(f"{path.name}: Lua assembly refers to a missing, foreign, or different-target hook journal")

        if ownership_artifacts and owner_document is None and fence_owner_document is None and not exclusive_controller_claim:
            problem("Recovery owner identity is unknown; no ownership artifacts may be released")
        if owner_document is not None and _owner(owner_document).created is None:
            problem("Legacy owner lock has no creation time; automatic recovery cannot prove the exact owner dead")
        ordered = sorted(roles, key=lambda identity: (identity.pid, identity.created or 0))
        for identity in ordered:
            first_observations[identity] = observe(identity)

        second_files, second_directories = _inventory(directory, shared)
        second_snapshots, _ = _snapshots(second_files, deadline, fence)
        if second_files != files or second_directories != directories or second_snapshots != snapshots:
            raise _AssessmentError("Recovery hashes, file identities, or directory inventory changed during process proof")
        for identity in ordered:
            final_observations[identity] = observe(identity)
        last_files, last_directories = _inventory(directory, shared)
        last_snapshots, _ = _snapshots(last_files, deadline, fence)
        if last_files != files or last_directories != directories or last_snapshots != snapshots:
            raise _AssessmentError("Recovery hashes or inventory changed after the final process proof")
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        problem(str(exc) or type(exc).__name__)

    evidence = tuple(ProcessEvidence(tuple(sorted(roles[identity])), identity,
        tuple(observation for observation in (first_observations.get(identity), final_observations.get(identity))
              if observation is not None)) for identity in sorted(roles, key=lambda identity: (identity.pid, identity.created or 0)))
    for process in evidence:
        if not process.proven_dead:
            statuses = ", ".join(item.status for item in process.observations) or "unprobed"
            problem(f"Exact process {process.identity.pid}/{process.identity.created} is not proven dead in both observations ({statuses})")
    eligible = ownership_artifacts and bool(evidence) and not reasons
    status = "eligible-read-only" if eligible else "blocked" if ownership_artifacts or reasons else "clean"
    digest_input = {"directories": directories, "files": [(str(item.path), item.kind, item.size, item.sha256, item.identity) for item in snapshots]}
    digest = hashlib.sha256(json.dumps(digest_input, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return RecoveryAssessment(directory, shared, status, eligible, tuple(reasons), snapshots, digest, evidence,
                              tuple(sorted(candidates, key=str)), _RECOVERY_PLAN, directory_identities=directories)
