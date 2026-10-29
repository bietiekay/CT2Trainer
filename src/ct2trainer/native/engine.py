"""Independent, deliberately bounded trainer controller.

Validated source profiles and declarative plans use the same owned controller.
No Cheat Engine implementation is loaded by this module.
"""
from __future__ import annotations
from .restoration_budget import restoration_entry, restoration_region, _clock_for

import atexit
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
import sys
import uuid
import time
from dataclasses import dataclass
from typing import Any, Callable

from .aa import (AAError, expression_symbols, normalize_pattern,
                 validate_expression, validate_one_shot_guards,
                 validate_patch_guards, validate_symbol)
from .one_shot_contract import (OneShotContract, OneShotContractError,
                                OneShotReceipt)
from .activation_policy import ActivationPolicyError
from .debug_log import TrainerDebugLog, create_debug_log
from .typed_call import TypedCallNotAttached, execute_code_ex
from .debugger_session import (
    DebuggerAlreadyAttached, DebuggerBadPid, DebuggerNotAttached)
from .managed_session import (
    ManagedSessionBadPid, ManagedSessionError, ManagedSessionNotAttached,
    ManagedValueRefused)


from .architecture import ArchitectureError, require_target_architecture
from .hotkey_bridge import HotkeyRegistrationError
from .hotkey_model import (ACTIVATION_HOTKEY_ACTIONS, VALUE_HOTKEY_ACTIONS,
                           HotkeyController, HotkeyModelError, HotKeySpec,
                           ToggleOutcome, ToggleOutcomeStatus, format_hotkey_keys,
                           vk_to_spec)
from .memory import ScanMiss
from .patterns import pattern_byte_length, placeholder_spans


class NativeRuntimeError(RuntimeError):
    """A failed action with a diagnostic suitable for the trainer UI."""


class StateError(NativeRuntimeError):
    """Persistence or ownership is uncertain; further writes are forbidden."""


class _OwnedArtifactRefusal(StateError):
    """Startup refusal caused by prior-session ownership artifacts.

    Internal marker: the state claim itself succeeded, but pre-existing
    receipts, session files, or shared claims block a clean start. The
    conservative message is preserved; only a verified assessment upgrades
    the refusal to a recoverable handle.
    """


class PatchConflict(NativeRuntimeError):
    """A patch no longer has the bytes this trainer owns."""


class RetryableAction(NativeRuntimeError):
    """A verified pre-write refusal that can be retried without recovery."""


class StaleStateRecoverable(NativeRuntimeError):
    """State lock owned by a process proven dead; verified recovery can release it.

    Carries the fresh read-only assessment and the directories an explicit,
    user-confirmed ``perform_stale_recovery`` call needs. The state itself is
    not touched until that call succeeds.
    """

    def __init__(self, assessment: Any, state_directory: str | Path, process_lock_directory: str | Path,
                 archive_directory: str | Path, trainer_id: str, table_sha256: str):
        self.assessment = assessment
        self.state_directory = Path(state_directory)
        self.process_lock_directory = Path(process_lock_directory)
        self.archive_directory = Path(archive_directory)
        self.trainer_id = trainer_id
        self.table_sha256 = table_sha256
        self.exclusive_controller_claim = False
        super().__init__("state.lock is owned by a process proven dead; verified recovery is available for "
                         + str(state_directory))


class StaleArtifactsRecoverable(NativeRuntimeError):
    """Prior-session state artifacts are stale; every recorded process is proven dead.

    Covers startup refusals caused by orphaned ownership artifacts: unfinished
    executable receipts, incomplete session files, or leftover shared process
    claims. Carries the fresh read-only assessment and the directories an
    explicit, user-confirmed ``perform_stale_recovery`` call needs. The state
    itself is not touched until that call succeeds.
    """

    def __init__(self, assessment: Any, state_directory: str | Path, process_lock_directory: str | Path,
                 archive_directory: str | Path, trainer_id: str, table_sha256: str):
        self.assessment = assessment
        self.state_directory = Path(state_directory)
        self.process_lock_directory = Path(process_lock_directory)
        self.archive_directory = Path(archive_directory)
        self.trainer_id = trainer_id
        self.table_sha256 = table_sha256
        self.exclusive_controller_claim = True
        super().__init__("prior session artifacts are stale and their exact processes are proven dead; "
                         "verified recovery is available for " + str(state_directory))


class LiveStateConflict(StateError):
    """State lock held by a trainer process that is proven alive.

    Carries the exact owner identity so the UI can offer a user-confirmed
    termination and takeover. The state files are not touched by this
    exception; an unprovable owner keeps the plain conservative refusal.
    """

    def __init__(self, owner_pid: int, owner_created: int,
                 state_directory: str | Path, detail: str = ""):
        self.owner_pid = owner_pid
        self.owner_created = owner_created
        self.state_directory = Path(state_directory)
        self.detail = detail
        super().__init__(
            f"state.lock is held by live trainer process PID {owner_pid} "
            f"(creation identity verified); state directory: {state_directory}")


def perform_stale_recovery(stale, process_probe: Any = None) -> tuple[bool, str]:
    """Archive and release stale state after the user confirms recovery.

    Accepts a ``StaleStateRecoverable`` (dead state-lock owner) or a
    ``StaleArtifactsRecoverable`` (stale orphaned receipts/sessions). Returns
    ``(completed, detail)``. Callers may retry engine startup only after
    ``completed`` is true; failed runs leave the state in place for manual
    recovery.
    """
    if not isinstance(stale, (StaleStateRecoverable, StaleArtifactsRecoverable)):
        return False, "Not a recoverable stale-state handle"
    from .recovery_operation import RecoveryOperationError, recover_assessment
    try:
        report = recover_assessment(stale.assessment, stale.archive_directory,
                                    expected_trainer_id=stale.trainer_id,
                                    expected_table_sha256=stale.table_sha256,
                                    process_probe=process_probe,
                                    exclusive_controller_claim=stale.exclusive_controller_claim)
    except (RecoveryOperationError, OSError) as exc:
        return False, str(exc) or type(exc).__name__
    if not report.completed:
        return False, "; ".join(report.reasons[:4]) or report.status
    return True, f"Archived stale state to {report.archive_path}"


def terminate_live_session(owner_pid: int, owner_created: int | None = None,
                           timeout_ms: int = 10000) -> tuple[bool, str]:
    """Terminate one proven-alive trainer session by exact process identity.

    The PID is opened with terminate rights only. When ``owner_created`` is
    known, its FILETIME creation time is re-verified after the handle is
    opened, so a reused PID is never killed. Returns ``(terminated, detail)``;
    every false first value leaves the target untouched.
    """
    if type(owner_pid) is not int or not 0 < owner_pid <= 0xFFFFFFFF:
        return False, "Invalid owner PID"
    if owner_created is not None and (type(owner_created) is not int
                                      or not 0 < owner_created <= 0xFFFFFFFFFFFFFFFF):
        return False, "Invalid owner creation identity"
    if type(timeout_ms) is not int or not 0 < timeout_ms <= 60000:
        return False, "Invalid termination timeout"
    if sys.platform != "win32":
        return False, "Live session termination requires Windows"
    import ctypes
    from ctypes import wintypes

    class _FileTime(ctypes.Structure):
        _fields_ = [("low", ctypes.c_uint32), ("high", ctypes.c_uint32)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    signatures = {
        "OpenProcess": ([ctypes.c_uint32, wintypes.BOOL, ctypes.c_uint32], wintypes.HANDLE),
        "GetProcessTimes": ([wintypes.HANDLE] + [ctypes.POINTER(_FileTime)] * 4, wintypes.BOOL),
        "WaitForSingleObject": ([wintypes.HANDLE, ctypes.c_uint32], ctypes.c_uint32),
        "TerminateProcess": ([wintypes.HANDLE, ctypes.c_uint32], wintypes.BOOL),
        "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(kernel, name)
        function.argtypes, function.restype = arguments, result
    handle = kernel.OpenProcess(0x0001 | 0x00100000 | 0x00001000, False, owner_pid)
    if not handle:
        return False, (f"Owner process PID {owner_pid} could not be opened "
                       f"(Win32 error {ctypes.get_last_error()}); it may have exited already")
    try:
        if owner_created is not None:
            times = [_FileTime() for _ in range(4)]
            if not kernel.GetProcessTimes(handle, *[ctypes.byref(item) for item in times]):
                return False, (f"Owner identity verification failed "
                               f"(Win32 error {ctypes.get_last_error()})")
            created = times[0].low | times[0].high << 32
            if created != owner_created:
                return False, ("PID now names a different process (creation identity mismatch); "
                               "termination refused")
        if not kernel.TerminateProcess(handle, 1):
            return False, f"TerminateProcess failed (Win32 error {ctypes.get_last_error()})"
        waited = int(kernel.WaitForSingleObject(handle, timeout_ms))
        if waited == 0:
            return True, f"Terminated trainer session PID {owner_pid}"
        return False, f"Termination wait ended with code {waited}; verify the session manually"
    finally:
        kernel.CloseHandle(handle)


_INTEGER_TYPES = {"Byte": 1, "2 Bytes": 2, "4 Bytes": 4, "8 Bytes": 8}
_FLOAT_TYPES = {"Float": "f", "Double": "d"}
_OPS = {"scan", "define", "register", "unregister", "assert", "write"}
# RT-5 item C2: the in-memory journal of runtime-created MemoryRecords
# (createMemoryRecord, table-Lua scope) is bounded per session so a table
# loop cannot grow unbounded host state; the journal is cleared on target
# exit and close and is never persisted.
MAX_DYNAMIC_RECORDS = 4096
# Synthetic dynamic-record IDs start here: above every plan-record ID that
# the plan validator and the state store admit (state store refuses IDs
# >= 2**31), so a journal ID can never collide with a plan ID.
_DYNAMIC_RECORD_ID_BASE = 2 ** 31
# RT-5 item C2: numeric value types a runtime MemoryRecord can read/write
# (CE vtByte..vtDouble ordinals) mapped to little-endian struct codes.
_DYNAMIC_VALUE_CODES = {0: ("B", 1), 1: ("H", 2), 2: ("I", 4),
                        3: ("Q", 8), 4: ("f", 4), 5: ("d", 8)}
# RT-5 item C2: display-only record metadata the corpus sets on runtime
# records (dropdown/Aob display fields).  Stored verbatim in the journal's
# inert map; they never touch target memory.
_DYNAMIC_INERT_KEYS = frozenset({
    "dropdownlist.text", "aob.size", "dropdownreadonly",
    "dropdowndescriptiononly", "displayasdropdownlistitem", "color",
})
# RT-5 item C2: display-mutation keys the corpus sets on plan records (CE
# UI metadata - no target effect).  The session stores them verbatim in
# record_display_meta for later reads; the compiled plan is untouched.
# Journal records carry the same keys as first-class entry fields.
_PLAN_DISPLAY_KEYS = frozenset({
    "color", "options", "showashex", "dontsave", "collapsed",
    "isgroupheader",
}) | _DYNAMIC_INERT_KEYS
# RT-5 item C2: function tokens registered into a host's _ct2_dyn_fns table.
_DYNAMIC_FN_TOKEN_RE = re.compile(r"ct2fn:\d+\Z")


def _lua_string_literal(text: str) -> str:
    """Quote a string as a Lua 5.3 string literal (byte-wise UTF-8 escapes).

    Printable ASCII passes through; everything else becomes a three-digit
    octal escape per UTF-8 byte, so the literal survives any source encoding
    the host loader applies.
    """
    out = ['"']
    for byte in text.encode("utf-8"):
        if byte in (0x22, 0x5C):
            out.append("\\" + chr(byte))
        elif byte == 0x0A:
            out.append("\\n")
        elif byte == 0x0D:
            out.append("\\r")
        elif byte == 0x09:
            out.append("\\t")
        elif 0x20 <= byte <= 0x7E:
            out.append(chr(byte))
        else:
            out.append("\\%03o" % byte)
    out.append('"')
    return "".join(out)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def validate_plan(plan: dict) -> None:
    """Reject malformed embedded input before any filesystem or process access."""
    from .compiler import validate_plan as validate_source_profiles
    try:
        validate_source_profiles(plan)
    except ValueError as exc:
        raise NativeRuntimeError(str(exc)) from exc
    if not isinstance(plan, dict) or type(plan.get("schema")) is not int or plan["schema"] not in {1, 2} or plan.get("engine") != "ct2trainer":
        raise NativeRuntimeError("Unsupported native trainer plan")
    if not isinstance(plan.get("table_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", plan["table_sha256"]):
        raise NativeRuntimeError("Invalid table identity")
    if not isinstance(plan.get("trainer_id"), str) or not re.fullmatch(r"[0-9a-f]{16}", plan["trainer_id"]):
        raise NativeRuntimeError("Invalid trainer identity")
    if not isinstance(plan.get("process_name"), str) or not re.fullmatch(r"[^\\/:*?\"<>|\x00-\x1f]+\.exe", plan["process_name"], re.I):
        raise NativeRuntimeError("A process EXE basename is required")
    if not isinstance(plan.get("title"), str) or len(plan["title"]) > 1000:
        raise NativeRuntimeError("Invalid trainer title")
    entries = plan.get("entries")
    if not isinstance(entries, list) or not entries or len(entries) > 20000:
        raise NativeRuntimeError("Invalid native entry list")
    # WP-38: plan-level ancestor walks (dynamic address provider binding)
    # need the full ID map before the per-entry pass; malformed entries
    # simply stay out of the map and are refused by the checks below.
    by_id = {}
    for entry in entries:
        if (isinstance(entry, dict) and type(entry.get("id")) is int
                and entry["id"] >= 0 and entry["id"] not in by_id):
            by_id[entry["id"]] = entry
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict) or type(entry.get("id")) is not int or entry["id"] < 0 or entry["id"] in seen:
            raise NativeRuntimeError("Invalid or duplicate entry ID")
        seen.add(entry["id"])
        if entry.get("kind") not in {"script", "value", "heading", "blocked"} or type(entry.get("supported")) is not bool:
            raise NativeRuntimeError("Invalid native entry capability")
        if type(entry.get("selected")) is not bool:
            raise NativeRuntimeError("Invalid native selection flag")
        if (entry["kind"] == "blocked") != (not entry["supported"]):
            raise NativeRuntimeError("Blocked records must be unsupported")
        if not isinstance(entry.get("label"), str) or len(entry["label"]) > 10000:
            raise NativeRuntimeError("Invalid entry label")
        if not isinstance(entry.get("path"), str) or not isinstance(entry.get("reason"), str):
            raise NativeRuntimeError("Entry path and reason must be text")
        for key in ("requires", "provides"):
            values = entry.get(key, [])
            if (not isinstance(values, list) or len(values) > 4096
                    or len({v.casefold() for v in values if isinstance(v, str)}) != len(values)):
                raise NativeRuntimeError("Invalid symbol dependency")
            try:
                for value in values:
                    validate_symbol(value)
            except AAError as exc:
                raise NativeRuntimeError(str(exc)) from exc
        # WP-38/WP-50: the additive address_provider field is shape-checked
        # here (a symbol marker rides on a supported addressless heading;
        # a symbol-null marker rides on the supported addressless target
        # itself, heading or script); the provider cross-checks run in the
        # plan-wide pass below where the full ID map is available.
        marker = entry.get("address_provider")
        if marker is not None:
            from .compiler import _is_addressless_placeholder
            if (not isinstance(marker, dict) or set(marker) != {"provider_id", "symbol"}
                    or type(marker.get("provider_id")) is not int
                    or marker.get("provider_id", -1) < 0
                    or (marker.get("symbol") is not None
                        and not isinstance(marker["symbol"], str))):
                raise NativeRuntimeError("Invalid dynamic address provider metadata.")
            if marker["symbol"] is not None:
                if (entry["kind"] != "heading" or not entry["supported"]
                        or entry.get("address") != "" or entry.get("pointer_offsets") != []
                        or _is_addressless_placeholder(entry)):
                    raise NativeRuntimeError(
                        "Dynamic address provider requires a supported addressless heading.")
                try:
                    validate_symbol(marker["symbol"])
                except AAError as exc:
                    raise NativeRuntimeError(str(exc)) from exc
            else:
                # WP-50 (GC-E8): direct address-write provider; the target is
                # the addressless record the provider's Lua writes the live
                # base into (group heading or addressless script).
                if (entry["kind"] not in {"heading", "script"} or not entry["supported"]
                        or entry.get("address") != "" or entry.get("pointer_offsets") != []
                        or _is_addressless_placeholder(entry)):
                    raise NativeRuntimeError(
                        "Dynamic address provider requires a supported addressless target record.")
        if 'lua_program' in entry and (entry['kind'] != 'script' or not entry['supported']):
            raise NativeRuntimeError('Lua source profiles require a supported script record')
        if 'value_profile' in entry:
            from .value_types import validate_value_profile
            try:
                validate_value_profile(entry['value_profile'])
            except ValueError as exc:
                raise NativeRuntimeError(str(exc)) from exc
            profile = entry['value_profile']
            if (not entry['supported'] or entry['kind'] not in {'value', 'heading'}
                    or entry.get('variable_type') != profile['variable_type']
                    or bool(entry.get('show_as_signed')) != profile['properties']['ShowAsSigned']
                    or entry.get('show_as_hex') != profile['properties']['ShowAsHex']
                    or (entry['kind'] == 'value') != profile['actionable']):
                raise NativeRuntimeError('Value profile does not match its record metadata')
        if 'lua_call_plan' in entry:
            from .aa_luacall import plan_from_report
            try:
                plan_from_report(entry['lua_call_plan'])
            except ValueError as exc:
                raise NativeRuntimeError(str(exc)) from exc
        if not entry["supported"]:
            if not entry["reason"] or entry.get("enable") or entry.get("disable"):
                raise NativeRuntimeError("Blocked records need a reason and cannot carry operations")
            continue
        if entry["kind"] == "script":
            if 'global_program' in entry:
                from .global_alloc import validate_global_program
                profile=validate_global_program(entry['global_program'])
                if (profile['process_name']!=plan['process_name'] or entry['requires']!=profile['requires']
                        or entry['provides']!=profile['provides'] or entry.get('enable')!=[] or entry.get('disable')!=[]):
                    raise NativeRuntimeError('Global metadata differs from its source context')
                continue
            if 'lua_program' in entry:
                from .lua_program import validate_lua_program
                try:
                    validate_lua_program(entry['lua_program'])
                except ValueError as exc:
                    raise NativeRuntimeError(str(exc)) from exc
                if ('program' in entry or entry.get('enable') != [] or entry.get('disable') != []
                        or entry['lua_program']['process_name'] != plan['process_name']
                        or entry['requires'] != entry['lua_program']['requires']
                        or entry['provides'] != entry['lua_program']['provides']
                        or bool(entry.get('one_shot')) != bool(entry['lua_program'].get('one_shot', False))):
                    raise NativeRuntimeError('Lua AA metadata does not match its validated source')
                continue
            if 'program' in entry:
                from .aa_program import validate_program
                try:
                    validate_program(entry['program'])
                except AAError as exc:
                    raise NativeRuntimeError(str(exc)) from exc
                if (entry['program']['process_name'] != plan['process_name']
                        or entry.get('requires') != entry['program']['requires']
                        or entry.get('provides') != entry['program']['provides']
                        or entry.get('enable') or entry.get('disable')
                        or bool(entry.get('one_shot')) != bool(entry['program'].get('one_shot', False))):
                    raise NativeRuntimeError('Native assembly metadata does not match its source')
                continue
            for section in ("enable", "disable"):
                operations = entry.get(section)
                if not isinstance(operations, list) or len(operations) > 10000:
                    raise NativeRuntimeError("Invalid script operation list")
                for operation in operations:
                    if not isinstance(operation, dict) or operation.get("op") not in _OPS:
                        raise NativeRuntimeError("Unknown native operation")
                    op = operation["op"]
                    if op in {"scan", "define", "register", "unregister"}:
                        try:
                            validate_symbol(operation.get("symbol"))
                        except AAError as exc:
                            raise NativeRuntimeError(str(exc)) from exc
                    if op in {"assert", "write"}:
                        raw = operation.get("bytes")
                        if not isinstance(raw, str) or not re.fullmatch(r"(?:[0-9a-fA-F]{2}){1,65536}", raw):
                            raise NativeRuntimeError("Invalid patch bytes")
                        if not isinstance(operation.get("address"), str):
                            raise NativeRuntimeError("Invalid patch address")
                        try:
                            validate_expression(operation["address"])
                        except AAError as exc:
                            raise NativeRuntimeError(str(exc)) from exc
                    if op == "define" and not isinstance(operation.get("expression"), str):
                        raise NativeRuntimeError("Invalid symbol expression")
                    if op == "scan" and (not isinstance(operation.get("module"), str) or not isinstance(operation.get("pattern"), str)):
                        raise NativeRuntimeError("Invalid module pattern")
                    try:
                        if op == "define":
                            validate_expression(operation["expression"])
                        elif op == "scan":
                            # WP-19: the $process token names the main module of
                            # the attached process; the runtime maps it to the
                            # plan's process_name at activation time.
                            if operation["module"] != "$process":
                                validate_expression('"' + operation["module"] + '"')
                            normalize_pattern(operation["pattern"])
                    except AAError as exc:
                        raise NativeRuntimeError(str(exc)) from exc
            try:
                if entry.get("one_shot"):
                    if entry.get("disable"):
                        raise AAError("One-shot script must have an empty disable phase.")
                    validate_one_shot_guards(entry["enable"])
                else:
                    validate_patch_guards(entry["enable"], entry["disable"])
            except AAError as exc:
                raise NativeRuntimeError(str(exc)) from exc
            local: set[str] = set()
            required: set[str] = set()
            registered: set[str] = set()
            removed: set[str] = set()
            for phase in ("enable", "disable"):
                for operation in entry[phase]:
                    op = operation["op"]
                    if op == "scan":
                        if phase != "enable":
                            raise NativeRuntimeError("Disable cannot rescan module bytes")
                        local.add(operation["symbol"].casefold())
                    elif op == "define":
                        required.update(symbol.casefold() for symbol in expression_symbols(operation["expression"])
                                        if symbol.casefold() not in local)
                        local.add(operation["symbol"].casefold())
                    elif op in {"assert", "write"}:
                        required.update(symbol.casefold() for symbol in expression_symbols(operation["address"])
                                        if symbol.casefold() not in local)
                    elif op == "register":
                        if phase != "enable" or operation["symbol"].casefold() not in local:
                            raise NativeRuntimeError("Only enable-local symbols can be registered")
                        registered.add(operation["symbol"].casefold())
                    elif op == "unregister":
                        if phase != "disable":
                            raise NativeRuntimeError("Only disable may unregister symbols")
                        removed.add(operation["symbol"].casefold())
            provides_cf = {name.casefold() for name in entry.get("provides", [])}
            if entry.get("one_shot"):
                # WP-46 part 2 (GC-E12): a one-shot record has an empty
                # disable phase by contract (checked above), so the
                # unregister side is empty by construction; the
                # registration evidence alone must equal the claimed
                # provides (the owner scope releases the symbol at detach).
                mismatch = registered != provides_cf
            else:
                mismatch = (registered != removed
                            or registered != provides_cf)
            if (mismatch
                    or required != {name.casefold() for name in entry.get("requires", [])}):
                raise NativeRuntimeError("Script symbol dependency/registration metadata does not match its operations")
            if not registered and not any(operation["op"] == "write" for operation in entry["enable"]):
                raise NativeRuntimeError("Script must provide a symbol or guarded patch action")
        elif entry["kind"] == "value":
            if 'value_profile' not in entry and entry.get("variable_type") not in _INTEGER_TYPES | _FLOAT_TYPES:
                raise NativeRuntimeError("Unsupported numeric type in native plan")
            if not isinstance(entry.get("address"), str) or not entry["address"]:
                raise NativeRuntimeError("Missing value address")
            try:
                if entry.get('address_profile') == 'expression/v1':
                    from .address_expression import parse_expression, expression_symbols as expression_refs
                    from .compiler import (_dynamic_address_binding,
                                          _dynamic_provider_binding,
                                          _runtime_base_marker_ok)
                    parse_expression(entry['address'])
                    if entry['address'].lstrip().startswith(('+','-')):
                        # WP-38/WP-50/RT-4.3: relative expression addresses
                        # are valid only when the plan-level ancestor walk
                        # binds the dynamic address provider of the nearest
                        # marked ancestor (a symbol provider heading, or a
                        # symbol-null direct address-write target) — or the
                        # row is staged on the runtime-base marker of an
                        # addressless group heading (RT-4.3 O9/O1).
                        if (_dynamic_provider_binding(by_id, entry) is None
                                and _dynamic_address_binding(by_id, entry) is None
                                and not _runtime_base_marker_ok(by_id, entry)):
                            raise NativeRuntimeError('Flattened address profiles require resolved inherited bases')
                    if entry.get('pointer_offsets') != [] or not isinstance(entry.get('source_address'),str):
                        raise NativeRuntimeError('Flattened address profiles require original source addresses and empty offsets')
                elif 'address_profile' in entry:
                    raise NativeRuntimeError('Unknown value address profile')
                else:
                    validate_expression(entry["address"])
                    expression_refs=expression_symbols
            except (AAError, ValueError) as exc:
                raise NativeRuntimeError(str(exc)) from exc
            offsets = entry.get("pointer_offsets", [])
            if not isinstance(offsets, list) or len(offsets) > 32:
                raise NativeRuntimeError("Invalid pointer offsets")
            offset_refs = []
            for offset in offsets:
                if type(offset) is int:
                    if abs(offset) > 0x7FFFFFFFFFFFFFFF:
                        raise NativeRuntimeError("Invalid pointer offsets")
                elif isinstance(offset, str):
                    # RT-4.3 (O3): expression offset slots must stay
                    # parseable; their symbol-kind atoms join the plan
                    # requires set.
                    from .address_expression import parse_expression
                    try:
                        parse_expression(offset)
                    except ValueError as exc:
                        raise NativeRuntimeError(str(exc)) from exc
                    offset_refs.extend(expression_refs(offset))
                else:
                    raise NativeRuntimeError("Invalid pointer offsets")
            expected = {name.casefold() for name in expression_refs(entry["address"])}
            expected.update(name.casefold() for name in offset_refs)
            if ({name.casefold() for name in entry.get("requires", [])} != expected
                    or entry.get("provides")):
                raise NativeRuntimeError("Value symbol dependencies do not match its address")
            if (type(entry.get("show_as_hex")) is not bool
                    or entry.get("show_as_signed") is not None and type(entry["show_as_signed"]) is not bool):
                raise NativeRuntimeError("Invalid numeric display flags")
            # WP-33: ShowAsHex Float/Double entries carry fixed-size raw
            # bit-pattern writes; the plan validator no longer refuses them.
            dropdown = entry.get("dropdown")
            if not isinstance(dropdown, dict) or not isinstance(dropdown.get("choices"), list) or type(dropdown.get("read_only")) is not bool:
                raise NativeRuntimeError("Invalid numeric dropdown")
            # RT-4.4 (O6/O8/O26): mirror the compiler validator with the
            # dual-base literal classification; display-only rows and
            # expression choices carry their own markers, and a read-only
            # list may stage zero writable choices.
            for choice in dropdown["choices"]:
                if not isinstance(choice, dict) or not isinstance(choice.get("description"), str):
                    raise NativeRuntimeError("Invalid dropdown choice")
                if choice.get("separator") is True:
                    # WP-24 separator rows are display-only metadata; they are
                    # never selectable and never written.
                    if choice.get("value") != "":
                        raise NativeRuntimeError("Separator dropdown choices must carry the empty value")
                    continue
                if "separator" in choice:
                    raise NativeRuntimeError("Dropdown separator marker must be true")
                if choice.get("writable") is False:
                    # RT-4.4 (O8/O26): display-only choice staged by a
                    # read-only (description-only) list; never selectable.
                    if not dropdown["read_only"]:
                        raise NativeRuntimeError("Display-only dropdown choices require a read-only dropdown.")
                    continue
                if "writable" in choice:
                    raise NativeRuntimeError("Dropdown writable marker must be false.")
                if choice.get("expression") is True:
                    # RT-4.4 (O8): bracketed expression choice; syntax is
                    # plan-checked, semantics resolve at write time.
                    if 'value_profile' in entry:
                        raise NativeRuntimeError("Dropdown expression choices require a simple numeric record.")
                    try:
                        from .address_expression import parse_expression, AddressExpressionError
                        parse_expression(choice.get("value", ""))
                    except AddressExpressionError as exc:
                        raise NativeRuntimeError("Dropdown expression choice is not a valid address expression.") from exc
                    continue
                if "expression" in choice:
                    raise NativeRuntimeError("Dropdown expression marker must be true.")
                from .compiler import _dropdown_choice_status
                status, _refusal = _dropdown_choice_status(
                    choice.get("value"), entry["variable_type"],
                    entry["show_as_hex"], entry.get("show_as_signed"),
                    entry.get("value_profile"))
                if status == "refusal":
                    raise NativeRuntimeError("Dropdown values must be exact supported literals.")
    # WP-37: mirror the compiler gate — the external-ownership map is
    # optional on schema 2 and must name supported script providers that
    # actually carry the symbol before any runtime use.  (Reuses the WP-38
    # by_id map; the per-entry pass above already refused malformed or
    # duplicate IDs, so it is complete here.)
    external_owned = plan.get("external_owned_providers")
    if external_owned is not None:
        if plan["schema"] != 2:
            raise NativeRuntimeError("external_owned_providers requires schema 2")
        if not isinstance(external_owned, dict):
            raise NativeRuntimeError("external_owned_providers must be a symbol-to-provider map")
        for symbol, owner_id in external_owned.items():
            if not isinstance(symbol, str) or not symbol:
                raise NativeRuntimeError("external_owned_providers keys must be symbol names")
            if type(owner_id) is not int or owner_id not in by_id:
                raise NativeRuntimeError("external_owned_providers must reference known provider IDs")
            owner = by_id[owner_id]
            if not owner["supported"] or owner["kind"] != "script":
                raise NativeRuntimeError("external_owned_providers must name supported script records")
            if symbol.casefold() not in {name.casefold() for name in owner.get("provides", [])}:
                raise NativeRuntimeError("external_owned_providers entries must match the provider's symbols")
    providers: dict[str, int] = {}
    for entry in entries:
        parent = entry.get("parent_id")
        if parent is not None and (type(parent) is not int or parent not in by_id or parent == entry["id"]):
            raise NativeRuntimeError("Invalid parent identity")
        # WP-38/WP-50: the address_provider field must name a supported
        # addressless script; a symbol marker's provider provides the symbol
        # and must not sit below the heading it serves (provider-to-base
        # cycle); a symbol-null marker's provider must statically name the
        # target by exact description and neither side may sit below the
        # other.  The relative-address allowance for provider-bound values
        # was checked in the per-entry address validation above.
        marker = entry.get("address_provider")
        if marker is not None:
            from .compiler import _is_descendant
            provider = by_id.get(marker["provider_id"])
            if provider is None:
                raise NativeRuntimeError("Dynamic address provider references an unknown record.")
            if (provider is entry or provider["kind"] != "script"
                    or not provider["supported"] or provider.get("address")
                    or provider.get("pointer_offsets")):
                raise NativeRuntimeError(
                    "Dynamic address provider must name a supported addressless script record.")
            if marker["symbol"] is not None:
                if marker["symbol"].casefold() not in {name.casefold() for name in provider.get("provides", [])}:
                    raise NativeRuntimeError("Dynamic address provider does not provide the named symbol.")
                if _is_descendant(by_id, provider["id"], entry["id"]):
                    raise NativeRuntimeError(
                        "Dynamic address provider must not be a descendant of the heading it serves.")
            else:
                # WP-50 (GC-E8): symbol-null marker — the provider's
                # embedded Lua must statically name the target record by
                # exact description (re-derived from the embedded source,
                # both idioms), and neither side may sit below the other
                # (base/provider cycle).
                from .lua_program import lua_dynamic_address_targets
                lua_source = (provider.get("lua_program") or {}).get("source")
                targets = (lua_dynamic_address_targets(lua_source)
                           if isinstance(lua_source, str) else [])
                if entry.get("label") not in targets:
                    raise NativeRuntimeError(
                        "Dynamic address provider does not write the target record's address.")
                if _is_descendant(by_id, provider["id"], entry["id"]):
                    raise NativeRuntimeError(
                        "Dynamic address provider must not be a descendant of the target it serves.")
                if _is_descendant(by_id, entry["id"], provider["id"]):
                    raise NativeRuntimeError(
                        "Dynamic address target must not be a descendant of its provider.")
        dropdown = entry.get("dropdown")
        if isinstance(dropdown, dict):
            link_target = dropdown.get("link_target_id")
            if (link_target is not None and (type(link_target) is not int
                    or link_target not in by_id or link_target == entry["id"])):
                raise NativeRuntimeError("Dropdown link target must reference another plan record.")
        recursive = entry.get("recursive_value")
        if isinstance(recursive, dict):
            write_ids = recursive.get("write_ids")
            if (not isinstance(write_ids, list)
                    or any(type(item) is not int for item in write_ids)
                    or len({item for item in write_ids}) != len(write_ids)):
                raise NativeRuntimeError("Recursive value metadata must list unique record IDs")
            try:
                from .value_links import RecursiveSetValueError, recursive_write_closure
                expected = recursive_write_closure(by_id, entry["id"])
            except RecursiveSetValueError as exc:
                raise NativeRuntimeError(str(exc)) from exc
            if write_ids != expected:
                raise NativeRuntimeError("Recursive value metadata does not match the record structure")
        if entry["selected"] and entry["supported"] and entry["kind"] == "script":
            for name in entry.get("provides", []):
                key = name.casefold()
                if key in providers:
                    # RT-4.1 (CE dupIgnore narrowing): the plan may carry
                    # multiple selected providers of one symbol.  The
                    # runtime resolves keep-first through
                    # TrainerEngine.registered_by (first activated
                    # registrant owns the symbol; later duplicates are
                    # silent no-ops), so the ambiguity is no longer a
                    # plan defect.  The map keeps the first occurrence in
                    # plan order so the dependency walk below agrees with
                    # the compiler's keep-first resolution.
                    continue
                providers[key] = entry["id"]
    # RT-4.1 (CE dupIgnore narrowing): multiple selected providers of one
    # symbol are legal.  The runtime resolves keep-first through
    # TrainerEngine.registered_by, so a consumer no longer requires one
    # unambiguous selected declarer.  The provider map above keeps the
    # first occurrence in plan order for deterministic dependency walks.
    visiting, completed = set(), set()
    # WP-46 (part 1): table-level <UserdefinedSymbols> provide required
    # symbols without owning a record.  The engine seeds them into the
    # runtime symbol table at init, so they count as available providers
    # here (the strict map checks already ran in the compiler validator
    # this function delegates to first).
    uds_available = {name.casefold() for name in (plan.get("user_defined_symbols") or {})}
    # RT-4.6: imported user symbols are seeded into the runtime symbol
    # table at engine init and on every confirmed attach (after the UDS
    # seed, so an import overrides a table-level definition of the same
    # name), so they cover required symbols exactly like the UDS fallback
    # — no record dependency is needed.
    user_available = {name.casefold() for name in (plan.get("user_symbols") or {})}
    # WP-54 (c): table-Lua registered symbols are live for the whole attach
    # (the table-scope bootstrap precedes wish restore), so they cover
    # required symbols exactly like the UDS fallback — no record dependency
    # is needed.
    table_lua_available = {name.casefold() for name in (plan.get("table_lua_symbols") or [])}

    def visit(identifier: int) -> None:
        if identifier in visiting:
            raise NativeRuntimeError("Symbol dependency cycle")
        if identifier in completed:
            return
        if len(visiting) >= 64:
            raise NativeRuntimeError("Symbol dependency chain exceeds 64 levels")
        visiting.add(identifier)
        entry = by_id[identifier]
        # WP-49 (GC-E7): a record's own registration satisfies its own
        # reference to a symbol it provides; no self-edge exists in the plan
        # and the DFS must not fabricate one from the raw metadata.
        own_provided = {name.casefold() for name in entry.get("provides", [])}
        # RT-4.2 (R7): the api_exports plan marker covers bare API call
        # targets that no record or table-level provider serves; the engine
        # resolves each export against the attached target's live PE export
        # table at link time, so the marker carries no record dependency.
        api_covered = {export.casefold() for export in (entry.get("api_exports") or {})}
        for name in entry.get("requires", []):
            if name.casefold() in own_provided:
                continue
            if name.casefold() in api_covered:
                continue
            provider = providers.get(name.casefold())
            if provider is None:
                if (name.casefold() in uds_available
                        or name.casefold() in table_lua_available
                        or name.casefold() in user_available):
                    continue
                raise NativeRuntimeError(f"Selected entry requires an unavailable symbol: {name}")
            visit(provider)
        visiting.remove(identifier)
        completed.add(identifier)

    for entry in entries:
        if entry["selected"] and entry["supported"]:
            visit(entry["id"])
    if "selected_ids" in plan and plan["selected_ids"] != sorted(e["id"] for e in entries if e["selected"]):
        raise NativeRuntimeError("Selected IDs do not match entry flags")


def parse_value(entry: dict, text: str, current_bytes: bytes | None = None) -> bytes:
    if 'value_profile' in entry:
        from .value_types import parse_profile_value
        try:
            result = parse_profile_value(entry['value_profile'], text, current_bytes)
        except ValueError as exc:
            raise NativeRuntimeError(str(exc)) from exc
        dropdown = entry.get('dropdown') or {}
        if dropdown.get('read_only') and result not in {
                parse_profile_value(entry['value_profile'], item['value'], current_bytes)
                for item in dropdown.get('choices', [])
                if item.get('separator') is not True  # WP-24: separator rows are display-only
                and item.get('writable') is not False  # RT-4.4 (O8/O26): display-only rows
                and item.get('expression') is not True  # RT-4.4 (O8): expression rows
                }:
            raise NativeRuntimeError('Choose a value from the supplied list')
        return result
    """Parse complete numeric literals, never expressions or executable input."""
    if not isinstance(text, str) or len(text) > 64:
        raise NativeRuntimeError("Enter a numeric literal")
    literal = text.strip()
    kind = entry["variable_type"]
    if kind in _INTEGER_TYPES:
        size = _INTEGER_TYPES[kind]
        if entry.get("show_as_hex", False):
            if not re.fullmatch(r"(?:0[xX])?[0-9a-fA-F]+", literal):
                raise NativeRuntimeError("Enter hexadecimal digits only")
            number = int(literal.removeprefix("0x").removeprefix("0X"), 16)
        else:
            # RT-4.4 (O6/O8): decimal mode accepts a hex literal of the
            # other base as well (corpus P4G: hex skill IDs listed on a
            # decimal-mode record), mirroring the compiler's dual-base
            # choice classification; hex mode stays hex-only.
            if re.fullmatch(r"[+-]?[0-9]+", literal) is not None:
                number = int(literal, 10)
            elif re.fullmatch(r"(?:0[xX])?[0-9A-Fa-f]+", literal) is not None:
                number = int(literal.removeprefix("0x").removeprefix("0X"), 16)
            else:
                raise NativeRuntimeError("Enter a whole decimal number")
        # RT-4.4 (O6): out-of-width integer literals are truncated at
        # write time, matching the CE typed-pointer store (SetValue
        # StrToQWordEx low-width bits); the old "Value must be between"
        # refusal is gone for integer writes.
        result = (number & ((1 << (size * 8)) - 1)).to_bytes(size, "little")
    elif kind in _FLOAT_TYPES:
        if entry.get("show_as_hex", False):
            # WP-33: fixed-size raw IEEE-754 bit-pattern edit.  The literal
            # must be exactly the type's pattern width; the bytes are written
            # raw and proven to round-trip through the IEEE-754 codec.
            digits = 8 if kind == "Float" else 16
            pattern = re.fullmatch(
                r"(?:0[xX])?([0-9a-fA-F]{" + str(digits) + r"})", literal)
            if pattern is None:
                raise NativeRuntimeError(
                    "Enter exactly %d hexadecimal digits for the %s bit pattern"
                    % (digits, kind))
            number = int(pattern.group(1), 16)
            size = 4 if kind == "Float" else 8
            result = number.to_bytes(size, "little")
            if (struct.pack("<" + _FLOAT_TYPES[kind],
                            struct.unpack("<" + _FLOAT_TYPES[kind], result)[0])
                    != result):
                raise NativeRuntimeError(
                    "Hexadecimal floating-point bit pattern is not representable")
        else:
            if not re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", literal):
                raise NativeRuntimeError("Enter a finite decimal number")
            number = float(literal)
            if not math.isfinite(number):
                raise NativeRuntimeError("Value must be finite")
            try:
                result = struct.pack("<" + _FLOAT_TYPES[kind], number)
            except (OverflowError, struct.error) as exc:
                raise NativeRuntimeError("Value exceeds this floating point type") from exc
            if not math.isfinite(struct.unpack("<" + _FLOAT_TYPES[kind], result)[0]):
                raise NativeRuntimeError("Value exceeds this floating point type")
    else:
        raise NativeRuntimeError("Unsupported numeric type")
    dropdown = entry.get("dropdown") or {}
    if dropdown.get("read_only"):
        # RT-4.4 (O8/O26): display-only rows (writable: False) and
        # bracketed expression choices never enter the allowed set; an
        # empty writable set refuses every write (the O26 contract).
        allowed = set()
        for choice in dropdown.get("choices", []):
            if choice.get("separator") is True:
                continue  # WP-24 separator rows are display-only; never selectable.
            if choice.get("writable") is False:
                continue  # RT-4.4 (O8/O26): display-only row; never selectable.
            if choice.get("expression") is True:
                continue  # RT-4.4 (O8): expression choice; resolved in set_value.
            plain = dict(entry, dropdown=None)
            allowed.add(parse_value(plain, choice["value"]))
        if result not in allowed:
            raise NativeRuntimeError("Choose a value from the supplied list")
    return result


def format_value(entry: dict, raw: bytes) -> str:
    if 'value_profile' in entry:
        from .value_types import format_profile_value
        return format_profile_value(entry['value_profile'], raw)
    kind = entry["variable_type"]
    if kind in _INTEGER_TYPES:
        if len(raw) != _INTEGER_TYPES[kind]:
            raise NativeRuntimeError("Short numeric read")
        number = int.from_bytes(raw, "little", signed=bool(entry.get("show_as_signed")) and not entry.get("show_as_hex", False))
        return format(number, "X") if entry.get("show_as_hex", False) else str(number)
    if kind in _FLOAT_TYPES:
        if entry.get("show_as_hex", False):
            # WP-33: the display is the raw bit pattern, uppercase, exactly
            # the type's pattern width.
            width = 4 if kind == "Float" else 8
            if len(raw) != width:
                raise NativeRuntimeError("Short numeric read")
            return format(int.from_bytes(raw, "little"), "08X" if kind == "Float" else "016X")
    number = struct.unpack("<" + _FLOAT_TYPES[kind], raw)[0]
    return format(number, ".9g" if kind == "Float" else ".17g")


class _StateStore:
    """Exclusive owner plus atomic, checksum-bound snapshots and crash journal."""

    def __init__(self, directory: Path, plan: dict, wish_ids: set[int], process_lock_dir: Path,
                 process_probe: Any = None):
        self.directory = directory
        self.plan = plan
        # Wish IDs: every record whose saved wish the state payload may
        # carry.  Script records hold wishes on their own; flagged parent
        # headings hold the cascade wish (save boundary of the parent
        # activation contract).  Anything else is refused on decode.
        self.wish_ids = wish_ids
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "state.json"
        self.temp = directory / "state.json.tmp"
        self.lock = directory / "state.lock"
        self.recovery_lock = directory / 'recovery.lock'
        self.session = directory / "session.json"
        self.oneshot = directory / "oneshot.json"
        self.oneshot_temp = directory / "oneshot.json.tmp"
        self.expected_markers: bytes | None = None
        from .recovery import current_process_identity
        owner = current_process_identity()
        lock_owner = {"owner_pid": owner.pid, "nonce": uuid.uuid4().hex}
        if owner.created is not None:
            lock_owner.update(schema=2, owner_created=owner.created)
        self.lock_bytes = _canonical(lock_owner)
        self.session_bytes: bytes | None = None
        self.process_lock_dir = process_lock_dir
        self.process_probe = process_probe
        self.process_lock: Path | None = None
        self.owned = False
        self.expected: bytes | None = None
        try:
            self._recovery_guard()
            self._exclusive(self.lock, self.lock_bytes)
            self.owned = True
            self._recovery_guard()
            if self.temp.exists() or self.session.exists() or self.oneshot_temp.exists():
                raise _OwnedArtifactRefusal("A prior incomplete session exists. Preserve these files and restart the target before manual recovery.")
            if (directory/'hooks'/'global-pool.json').exists():
                raise _OwnedArtifactRefusal('A prior shared-global pool cannot be revived from JSON. Preserve its exact receipts; verified target/owner death recovery is required.')
            for journal in (directory / 'hooks').glob('*.json'):
                from .hooks import MAX_JOURNAL_BYTES
                if journal.stat().st_size > MAX_JOURNAL_BYTES:
                    raise _OwnedArtifactRefusal('An oversized prior executable-hook journal requires manual recovery')
                try:
                    receipt=json.loads(journal.read_bytes())
                except (ValueError,OSError) as exc:
                    raise _OwnedArtifactRefusal('A prior executable-hook receipt is unreadable; preserve it for recovery') from exc
                from .lua_activation import finalized_receipt
                finalized_hook = (isinstance(receipt, dict) and receipt.get('engine') == 'ct2trainer-hooks'
                                  and receipt.get('state') in {'target-exited', 'abandoned'})
                if not finalized_hook and not finalized_receipt(receipt, plan):
                    raise _OwnedArtifactRefusal('Prior executable allocations still have an unfinalized receipt. Restart the exact target and verify recovery before another controller claims this state.')
            self.expected = self._read(self.path)
            if self.expected is not None:
                try:
                    self.desired = self._decode(self.expected)
                except StateError as decode_error:
                    # A corrupt state.json cannot be decoded in place.
                    # Quarantine its exact bytes (preserved for forensics)
                    # and start with an empty wish set instead of
                    # dead-ending every startup. A failed quarantine
                    # re-raises the original decode error.
                    if self._quarantine_corrupt(self.path) is None:
                        raise decode_error
                    self.expected = None
                    self.desired = set()
            else:
                self.desired = set()
            self.expected_markers = self._read(self.oneshot)
        except Exception as exc:
            if self.owned:
                self._remove(self.lock, self.lock_bytes)
                self.owned = False
            classified = self._stale_fence_probe(exc)
            if classified is None:
                classified = self._stale_lock_probe(exc)
            if classified is None:
                classified = self._stale_artifacts_probe(exc)
            if classified is not None:
                raise classified from exc
            if isinstance(exc, StateError) and isinstance(exc.__cause__, FileExistsError) \
                    and getattr(exc.__cause__, "filename", None) == str(self.lock):
                raise StateError(
                    "state.lock already exists; another trainer or a prior crash owns this state. "
                    f"State directory: {self.directory}. Delete that folder to start fresh.") from exc
            raise

    def _stale_fence_probe(self, exc: Exception):
        """Classify a leftover recovery fence without touching it.

        A fence blocks every controller before the state claim, so while it
        exists no other process can act on this state directory; the
        read-only assessment therefore carries the exclusive controller
        claim. Only a fence whose exact owner is proven dead in two
        independent observations yields the recoverable handle; anything
        unproven keeps the conservative refusal.
        """
        if (not isinstance(exc, StateError)
                or "A recovery transaction owns this state" not in str(exc)
                or not self.recovery_lock.exists()):
            return None
        probe = self.process_probe
        if probe is None:
            if sys.platform != "win32":
                return None
            from .recovery import WindowsProcessProbe
            probe = WindowsProcessProbe()
        try:
            from .recovery import assess_recovery
            assessment = assess_recovery(self.directory, self.process_lock_dir,
                                         process_probe=probe,
                                         expected_trainer_id=self.plan["trainer_id"],
                                         expected_table_sha256=self.plan["table_sha256"],
                                         exclusive_controller_claim=True)
        except Exception:
            return None
        if not assessment.eligible:
            return None
        return StaleArtifactsRecoverable(assessment, self.directory, self.process_lock_dir,
                                         self.directory.parent / "archives",
                                         self.plan["trainer_id"], self.plan["table_sha256"])

    def _stale_lock_probe(self, exc: Exception):
        """Classify a held state lock without touching the lock file.

        A proven-dead owner yields the recoverable stale-state handle; a
        proven-alive owner yields a LiveStateConflict (a user-confirmed
        takeover candidate); anything still unverifiable after one retry
        returns None, keeping the conservative refusal so a second running
        instance can never be displaced silently. A single "unknown" probe
        is treated as a transient failure and retried once (field case
        2026-10-20: first startup attempt plain refusal, eight seconds
        later the same lock classified recoverable). A proven-dead owner
        whose full assessment is not eligible (most commonly: the previous
        session's target process still running) yields an actionable
        StateError carrying the assessment reasons instead of falling back
        to the generic "delete that folder" line.
        """
        if not (isinstance(exc, StateError) and isinstance(exc.__cause__, FileExistsError)):
            return None
        probe = self.process_probe
        if probe is None:
            if sys.platform != "win32":
                return None
            from .recovery import WindowsProcessProbe
            probe = WindowsProcessProbe()
        try:
            from .recovery import ProcessIdentity, assess_recovery
            document = json.loads(self.lock.read_bytes())
            identity = None
            if isinstance(document, dict):
                pid = document.get("owner_pid")
                created = document.get("owner_created")
                if isinstance(pid, int) and 0 < pid <= 0xFFFFFFFF and (
                        created is None or (isinstance(created, int) and 0 < created <= 0xFFFFFFFFFFFFFFFF)):
                    identity = ProcessIdentity(pid, created)
            if identity is None or identity.created is None:
                return None
            observation = probe(identity)
            if observation.status == "unknown":
                # Transient probe failure: one retry before falling back to
                # the conservative refusal (field case 2026-10-20: first
                # startup attempt plain refusal, eight seconds later the
                # same lock classified recoverable).
                time.sleep(1.5)
                observation = probe(identity)
            if observation.status == "alive":
                return LiveStateConflict(identity.pid, identity.created, self.directory,
                                         detail=observation.detail)
            if not observation.proven_dead:
                return None
            assessment = assess_recovery(self.directory, self.process_lock_dir, process_probe=probe,
                                         expected_trainer_id=self.plan["trainer_id"],
                                         expected_table_sha256=self.plan["table_sha256"])
        except Exception:
            return None
        if not assessment.eligible:
            # Owner is proven dead but the full assessment is not eligible
            # (most commonly: the previous session's target process is still
            # alive, so its still-applied patches must stay recoverable).
            # Surface the concrete reasons so the startup refusal is
            # actionable instead of a generic "delete that folder" line.
            reasons = "\n".join("  - " + reason for reason in assessment.reasons[:3]) \
                      or "  - (assessment produced no reason)"
            return StateError(
                "state.lock already exists; the previous trainer process "
                f"(PID {identity.pid}) is verified as terminated, but automatic "
                "recovery is not possible yet:\n"
                + reasons + "\n"
                + "Action: if the previous session's target process is still "
                "running, close it and start the trainer again - once every "
                "recorded process is verified as terminated, the state is "
                "offered as verified recovery. As a last resort, delete the "
                "state folder to start fresh.\n"
                f"State directory: {self.directory}")
        return StaleStateRecoverable(assessment, self.directory, self.process_lock_dir,
                                     self.directory.parent / "archives",
                                     self.plan["trainer_id"], self.plan["table_sha256"])

    def _stale_artifacts_probe(self, exc: Exception):
        """Classify stale prior-session artifacts after the claim was released.

        The failed claim belongs exclusively to this process, so no other
        controller can act on the state directory while the refusal is being
        classified. The read-only assessment still requires every exact
        recorded process identity - owners and targets alike - to be proven
        dead in two independent observations before any artifact may be
        archived and released. Anything unproven keeps the conservative
        refusal, so live or unknown state is never overridden.
        """
        if not isinstance(exc, _OwnedArtifactRefusal):
            return None
        probe = self.process_probe
        if probe is None:
            if sys.platform != "win32":
                return None
            from .recovery import WindowsProcessProbe
            probe = WindowsProcessProbe()
        try:
            from .recovery import assess_recovery
            assessment = assess_recovery(self.directory, self.process_lock_dir,
                                         process_probe=probe,
                                         expected_trainer_id=self.plan["trainer_id"],
                                         expected_table_sha256=self.plan["table_sha256"],
                                         exclusive_controller_claim=True)
        except Exception:
            return None
        if not assessment.eligible:
            return None
        return StaleArtifactsRecoverable(assessment, self.directory, self.process_lock_dir,
                                         self.directory.parent / "archives",
                                         self.plan["trainer_id"], self.plan["table_sha256"])

    @staticmethod
    def _read(path: Path) -> bytes | None:
        try:
            if path.stat().st_size > 1024 * 1024:
                raise StateError("State file exceeds its size limit")
            return path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise StateError(f"Cannot read {path.name}: {exc}") from exc

    def _recovery_guard(self) -> None:
        try:
            self.recovery_lock.lstat()
        except FileNotFoundError:
            return
        except OSError as exc:
            raise StateError('Recovery fence status is unavailable') from exc
        raise StateError('A recovery transaction owns this state; preserve its fence and evidence')

    @staticmethod
    def _exclusive(path: Path, raw: bytes) -> None:
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise StateError(f"{path.name} already exists; another trainer or a prior crash owns this state") from exc
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if path.read_bytes() != raw:
            raise StateError(f"Could not confirm ownership of {path.name}")

    @staticmethod
    def _remove(path: Path, expected: bytes) -> None:
        if _StateStore._read(path) != expected:
            raise StateError(f"Ownership of {path.name} changed")
        path.unlink()

    def _payload(self, desired: set[int]) -> dict:
        return {"schema": 1, "engine": "ct2trainer", "trainer_id": self.plan["trainer_id"],
                "table_sha256": self.plan["table_sha256"], "process_name": self.plan["process_name"],
                "desired": sorted(desired)}

    def _decode(self, raw: bytes) -> set[int]:
        try:
            document = json.loads(raw)
            payload = document["payload"]
            desired = payload["desired"]
            if not isinstance(desired, list) or any(type(i) is not int for i in desired) or desired != sorted(set(desired)):
                raise ValueError("Invalid desired IDs")
            if not set(desired) <= self.wish_ids or payload != self._payload(set(desired)):
                raise ValueError("State identity does not match this trainer")
            if document.get("sha256") != hashlib.sha256(_canonical(payload)).hexdigest() or set(document) != {"payload", "sha256"}:
                raise ValueError("State checksum does not match")
            return set(desired)
        except (ValueError, TypeError, KeyError, UnicodeError) as exc:
            raise StateError(f"Invalid native state: {exc}") from exc

    def guard(self) -> None:
        self._recovery_guard()
        if not self.owned or self._read(self.lock) != self.lock_bytes:
            raise StateError("State lock ownership changed")
        if self.temp.exists() or self._read(self.path) != self.expected:
            raise StateError("State bytes changed outside this trainer")
        if self._read(self.oneshot) != self.expected_markers:
            raise StateError("One-shot marker bytes changed outside this trainer")
        if self._read(self.session) != self.session_bytes:
            raise StateError("Process session ownership changed")
        if self.process_lock is not None and self._read(self.process_lock) != self.session_bytes:
            raise StateError("Shared target process ownership changed")

    def save(self, desired: set[int]) -> None:
        self.guard()
        payload = self._payload(desired)
        raw = _canonical({"payload": payload, "sha256": hashlib.sha256(_canonical(payload)).hexdigest()}) + b"\n"
        self._exclusive(self.temp, raw)
        os.replace(self.temp, self.path)
        self.expected = raw
        if self._read(self.path) != raw:
            raise StateError("Saved state could not be confirmed")
        self.desired = set(desired)

    def save_one_shot_markers(self, raw: bytes) -> None:
        self.guard()
        if len(raw) > 1024 * 1024:
            raise StateError("One-shot markers exceed their size limit")
        self._exclusive(self.oneshot_temp, raw)
        os.replace(self.oneshot_temp, self.oneshot)
        self.expected_markers = raw
        if self._read(self.oneshot) != raw:
            raise StateError("Saved one-shot markers could not be confirmed")

    def _quarantine_corrupt(self, path: Path) -> Path | None:
        """Rename an unreadable state artifact out of the way; None on failure.

        The exact bytes are preserved under a ``<name>.corrupt-<UTC stamp>``
        suffix (with a counter on stamp collisions) for forensics. Recovery
        recognizes these quarantined files and may release them later. A
        failed rename leaves the original untouched so callers stay
        fail-closed.
        """
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        target = self.directory / f"{path.name}.corrupt-{stamp}"
        counter = 1
        while target.exists():
            target = self.directory / f"{path.name}.corrupt-{stamp}-{counter:02d}"
            counter += 1
        try:
            os.replace(path, target)
        except OSError:
            return None
        if path.exists() or not target.exists():
            return None
        return target

    def quarantine_one_shot_markers(self) -> Path | None:
        """Quarantine unreadable or mismatched one-shot marker bytes.

        One-shots may run once more after a quarantine; the documented
        trade-off is preferable to refusing startup over stale marker data.
        Returns the quarantine path, or None when the rename failed (the
        marker file is then preserved untouched).
        """
        self.guard()
        quarantined = self._quarantine_corrupt(self.oneshot)
        if quarantined is not None:
            self.expected_markers = None
        return quarantined

    def claim_session(self, memory: Any) -> None:
        self.guard()
        raw = _canonical({"schema": 1, "owner": json.loads(self.lock_bytes), "trainer_id": self.plan["trainer_id"],
                          "target_pid": memory.pid, "target_created": memory.creation_time})
        self.process_lock_dir.mkdir(parents=True, exist_ok=True)
        process_lock = self.process_lock_dir / f"{memory.pid}-{memory.creation_time}.json"
        self._exclusive(process_lock, raw)
        self.process_lock = process_lock
        self.session_bytes = raw
        self._exclusive(self.session, raw)

    def release_session(self) -> None:
        self.guard()
        if self.session_bytes is not None:
            self._remove(self.session, self.session_bytes)
            if self.process_lock is not None:
                self._remove(self.process_lock, self.session_bytes)
                self.process_lock = None
            self.session_bytes = None

    def close(self) -> None:
        self.guard()
        if self.session_bytes is not None:
            raise StateError("Cannot release state ownership while a process session remains")
        self._remove(self.lock, self.lock_bytes)
        self.owned = False


@dataclass(frozen=True)
class _Patch:
    address: int
    original: bytes
    changed: bytes


class _OneShotBackend:
    """Synchronous one-shot publish backend with no pending state.

    Every publish is one bounded activation attempt; the engine resolves it
    into a confirmed or failed receipt immediately.  A failure never leaks a
    partial write because each underlying enable path is itself fail-closed
    with its journal intact.
    """

    def __init__(self, engine: "TrainerEngine"):
        self.engine = engine
        self.last_error: Exception | None = None

    def publish(self, record_id: int, program: bytes) -> OneShotReceipt:
        try:
            self.engine._one_shot_activate(self.engine.entries[record_id])
            confirmed = True
        except Exception as exc:
            self.last_error = exc
            confirmed = False
        return OneShotReceipt(record_id=record_id, confirmed=confirmed)


class _HotkeyGate:
    """Adapter from the protected engine toggle path to the model gate contract.

    The hotkey model dispatches through this gate when no binding handler
    is set: a pressed combination flips the bound record through the
    ordinary toggle transaction (state save included) and is reported as a
    confirmed, saved outcome; a failed transaction is a failed outcome and
    the published binding is left in place for the next attempt.
    """

    def __init__(self, engine: "TrainerEngine"):
        self._engine = engine

    @property
    def blocked(self) -> bool:
        return self._engine.blocked

    def toggle(self, identifier: int) -> ToggleOutcome:
        try:
            self._engine.toggle(identifier)
        except NativeRuntimeError as exc:
            return ToggleOutcome(ToggleOutcomeStatus.FAILED, False, str(exc))
        return ToggleOutcome(ToggleOutcomeStatus.CONFIRMED, True)


class TrainerEngine:
    """Synchronous controller used identically by UI and headless fixture tests."""

    # No-op fallback for instances constructed without __init__ (e.g. via
    # object.__new__ in unit tests); __init__ always replaces it per instance.
    debug_log = TrainerDebugLog(enabled=False)

    def __init__(self, plan: dict, state_dir: str | Path | None = None, memory_factory: Callable | None = None,
                 process_lock_dir: str | Path | None = None, hook_coordinator: Any = 'debug-event',
                 process_probe: Any = None, il2cpp_resolver: Any = None,
                 call_broker_factory: Callable | None = None,
                 clock_factory: Callable | None = None,
                 luacall_binding_factory: Callable | None = None,
                 disassembler_factory: Callable | None = None,
                 thread_backend_factory: Callable | None = None,
                 protection_backend_factory: Callable | None = None,
                 export_backend_factory: Callable | None = None,
                 debugger_factory: Callable | None = None,
                  managed_runtime_factory: Callable | None = None):
        validate_plan(plan)
        self.plan = plan
        # Optional debug log: only active when the plan carries debug_log.
        # The header is written immediately so the file is meaningful even if
        # startup later fails (state claim, provider checks, ...).
        self.debug_log = create_debug_log(plan)
        self.entries = {entry["id"]: entry for entry in plan["entries"]}
        # WP-40: record hotkey registration (first-wins policy over the
        # protected toggle path) plus the live record set the controller was
        # last reconciled against.  Warnings are deduplicated, monotonic and
        # surfaced by the trainer UI; the plan keeps every original binding.
        self.hotkey_warnings: list[str] = []
        self._hotkey_live: set[int] = set()
        self._hotkey_owner = plan["trainer_id"]
        self.hotkey_controller = HotkeyController(
            _HotkeyGate(self),
            focus_provider=lambda: self.memory is not None,
            text_focus_provider=lambda: False,
            binding_handler=self._hotkey_dispatch,
        )
        # WP-53 (GC-D7): optional OS hotkey capture bridge. The trainer UI
        # attaches a started bridge at trainer start (Windows only;
        # non-Windows stays None and dispatch is programmatic-only). The
        # steady poll tick mirrors every published binding into it and
        # drains its captured-spec queue back into dispatch_hotkey. The
        # drain source is a pluggable attribute so tests can inject fake
        # specs without a real window.
        self.hotkey_bridge = None
        self.hotkey_spec_source = None
        self._hotkey_os: dict[int, set[HotKeySpec]] = {}
        # RT-4.1 (CE dupIgnore narrowing): multiple selected providers of
        # one symbol are legal; the runtime resolves keep-first through
        # registered_by at activation.  The map keeps the first selected
        # provider in plan order for the auto-enable dependency walk,
        # matching the compiler's keep-first resolution.
        self.providers: dict[str, int] = {}
        for entry in plan["entries"]:
            if entry["selected"] and entry["supported"] and entry["kind"] == "script":
                for name in entry.get("provides", []):
                    key = name.casefold()
                    if key not in self.providers:
                        self.providers[key] = entry["id"]
        if memory_factory is None:
            from .memory import ProcessMemory
            memory_factory = ProcessMemory
        self.memory_factory = memory_factory
        if state_dir is None:
            base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_STATE_HOME")
            state_dir = Path(base) if base else Path.home() / ".local" / "state"
            state_dir = state_dir / "CT2Trainer" / "native" / plan["trainer_id"]
        directory = Path(state_dir)
        shared = Path(process_lock_dir) if process_lock_dir is not None else directory.parent / "_process_sessions"
        # Wish-carrying records: script records on their own, plus every
        # supported group heading (WP-53: flagged headings own the cascade
        # wish at the parent-activation save boundary; plain headings own
        # their own active state).  The state payload refuses any other ID
        # on decode.
        wish_ids = {i for i, e in self.entries.items()
                    if e["selected"] and e["supported"]
                    and (e["kind"] == "script"
                         or e["kind"] == "heading")}
        try:
            self.store = _StateStore(directory, plan, wish_ids, shared, process_probe)
        except Exception as exc:
            self.debug_log.error("engine-init-failed", exc, stage="state-claim",
                                 state_dir=str(directory))
            raise
        # If the rest of startup fails after the state claim, release the lock
        # again so a failed start cannot leave a stale lock behind the next
        # attempt; the atexit net covers process exit without an explicit
        # close().
        atexit.register(self._atexit_close)
        try:
            self.desired = set(self.store.desired)
            self.applied: dict[int, list[_Patch]] = {}
            self.local_symbols: dict[int, dict[str, int]] = {}
            self.symbols: dict[str, int] = {}
            # RT-5 item A: embedded <Files> registry rebuilt from the plan.
            # The plan is validated (raw Ascii85 text re-decoded, hash and
            # size re-derived) before this point, so the decode below is
            # trusted; content is inert input data for table/record Lua,
            # never target memory.  Lookup is case-sensitive and first-match,
            # matching CE's findTableFile resolution order.
            from .embedded_files import decode_embedded_file
            self._embedded_files: list[bytes] = []
            self._embedded_by_name: dict[str, int] = {}
            for _index, _stored in enumerate(plan.get("embedded_files") or ()):
                _content = decode_embedded_file(
                    _stored["text"], _stored["encoding"])
                self._embedded_files.append(_content)
                self._embedded_by_name.setdefault(_stored["name"], _index)
            # RT-4.1 (CE dupIgnore narrowing, WP-37 keep-first): per-entry
            # ownership of the symbols each entry actually registered.
            # A symbol owned by one active entry keeps that binding when a
            # later duplicate registers it; the duplicate registers a
            # silent no-op and releases nothing on disable.  Table-level
            # seeds (UDS, table-Lua) are not entry-owned, so a record
            # registration still overwrites them (WP-46/WP-54 seed policy).
            self.registered_by: dict[int, set[str]] = {}
            # WP-57: scan-time captured placeholder bytes per active entry
            # (classic dialect bookkeeping + program-dialect disable restore
            # input); dropped with the entry on disable.
            self.placeholder_captures: dict[int | str, dict[str, str]] = {}
            # WP-46 (part 1): seed the runtime symbol table with the
            # table-level <UserdefinedSymbols> static definitions (plan
            # field, casefolded keys).  Without this seed, records whose
            # only provider is a UDS symbol would fail link/activation
            # resolution (fail-closed).  Record-registered symbols
            # overwrite these seeds at runtime registration
            # (self.symbols.update), matching CE's resolution order:
            # program registrations beat the userdefined symbol table.
            self._seed_user_defined_symbols()
            self.frozen: dict[int, tuple[int, bytes]] = {}
            # WP-50 (GC-E8): live bases written by a provider's record-Lua
            # into its symbol-null target; read fresh by the target's
            # expression-profile children at every activation.
            self.dynamic_addresses: dict[int, int] = {}
            # RT-5 item C2: engine-owned dynamic addresslist records created
            # at runtime through the table-Lua createMemoryRecord surface.
            # Session-scoped: journal entries live in self.entries (so the
            # generic record surface sees them) but are never persisted -
            # the synthetic IDs (>= 2**31) are refused by the state store,
            # and the journal is cleared on target exit and close.
            self.dynamic_records: dict[int, dict] = {}
            self._dynamic_next_id = 0
            # RT-5 item C2: plan-record OnActivate/OnDeactivate function
            # tokens registered at runtime (CE MemoryRecord.OnActivate):
            # record ID -> field -> ('ct2fn:<n>' token, scope); scope None
            # is the table-Lua host, an int the owning record scope
            # (lua_activations key).  Session-scoped: never part of the
            # plan; cleared with the runtime journal on target exit/close.
            self.record_callbacks: dict[int, dict[str, tuple]] = {}
            # RT-5 item C2: plan-record display mutations (CE UI metadata)
            # stored verbatim for later record.get reads; the plan is
            # untouched and the map dies with the session.
            self.record_display_meta: dict[int, dict[str, Any]] = {}
            self.memory: Any = None
            self.status = "Waiting for " + plan["process_name"]
            self.error = ""
            self.entry_errors: dict[int, str] = {}
            self.blocked = False
            self.busy = False
            self.closed = False
            self.lua_sessions: list[tuple[Any, Any]] = []
            self.lua_activations: dict[int, Any] = {}
            # WP-41: the per-table bootstrap scope (host, broker), present
            # only while a table-Lua bootstrap executed cleanly for the
            # current attach; retired on target exit, close and re-attach.
            self.table_lua_scope = None
            from .lua_host import LuaMemoryPool
            self.lua_memory_pool = LuaMemoryPool()
            self._lua_tick_time = time.monotonic()
            if hook_coordinator == 'debug-event':
                from .debug_coordinator import DebugEventCoordinator
                hook_coordinator=DebugEventCoordinator()
            self.hook_coordinator = hook_coordinator
            self.il2cpp_resolver = il2cpp_resolver
            # Typed target call route (N-14): the injected factory owns the
            # broker construction; the engine owns its lifecycle (created at
            # attach, invalidated on target exit and close). Without a
            # factory the executeCodeEx profile call stays fail-closed.
            self.call_broker_factory = call_broker_factory
            self.call_broker = None
            # Per-attach clock/speed binding (N-16): created on each confirmed
            # attach, finished on detach/close. The injected factory owns the
            # raw counter; the default refuses visibly until the owned Windows
            # clock route exists (AP-11).
            self.clock_factory = clock_factory
            self.clock = None
            # luaCall binding (N-?): records whose AA envelope carries
            # luaCall(...) lines are gated at activation: the embedded
            # lua_call_plan must be covered by an injected LuaCallBinding
            # before the record's Lua may run. The default refuses visibly
            # until an owned runtime binding exists (AP-11), mirroring the
            # clock binding.
            self.luacall_binding_factory = luacall_binding_factory
            # disassemble() port (aa_debugger_api): programs carrying
            # disassemble(...) nodes run the bounded read-only inspection
            # through a DisassemblerPort at preflight. The default route is
            # the owned iced-x86 backend bound to the linked memory; an
            # injected disassembler_factory may replace it or return None to
            # refuse visibly fail-closed before any allocation or write.
            self.disassembler_factory = disassembler_factory
            # createThread()/threadWait() binding (aa_createthread_threadwait):
            # records carrying these nodes gate activation on an injected
            # thread backend (spawn + deterministic completion polls). The
            # default route refuses visibly fail-closed before any allocation
            # or write; the owned Windows CreateRemoteThread route stays open
            # (AP-11).
            self.thread_backend_factory = thread_backend_factory
            # protect()/unprotect() binding (aa_protection_control): same
            # shape; the owned Windows VirtualProtect route stays open
            # (AP-11).
            self.protection_backend_factory = protection_backend_factory
            # getmodulehandle()/getprocaddress() binding (aa_target_api_
            # binding): the default route is the read-only PE export resolver
            # over the linked memory itself (bounded read + module identity);
            # an injected export_backend_factory may replace it or refuse by
            # returning None.
            self.export_backend_factory = export_backend_factory
            # attachProcess()/detachProcess() surface (lua_debugger_api):
            # at most one session binding per attached target, created
            # lazily through the injected factory on attachProcess and
            # retired on confirmed target exit and close. The default
            # route (no factory) refuses visibly fail-closed; the owned
            # Windows debug attach route stays open (AP-11).
            self.debugger_factory = debugger_factory
            self.debugger_session = None
            # LaunchMonoDataCollector()/mono_* surface (lua_managed_runtime):
            # at most one managed-runtime session per attached target, created
            # lazily through the injected factory on managed_attach and
            # retired on confirmed target exit and close. The default route
            # (no factory) refuses visibly fail-closed; the tested Mono stack
            # (mono_broker/mono_runtime) stays the typed stage model.
            self.managed_runtime_factory = managed_runtime_factory
            self.managed_session = None
            self.hooks: dict[int, Any] = {}
            self.retired_hooks: list[Any] = []
            self._hook_lifetime_bytes = 0
            self._hook_lifetime_count = 0
            self.global_pool=None
            self.global_leases={}
            self._global_aliases={}
            self._one_shot_ids = {entry["id"] for entry in plan["entries"]
                                  if entry.get("one_shot") and entry.get("selected")
                                  and entry.get("supported") and entry["kind"] == "script"}
            self.one_shot = None
            self._one_shot_generation = 0
            self._one_shot_backend = None
            if self._one_shot_ids:
                try:
                    self.one_shot = OneShotContract(
                        [(record_id, "script") for record_id in sorted(self._one_shot_ids)],
                        plan["table_sha256"], plan["process_name"])
                except OneShotContractError as exc:
                    raise StateError("One-shot contract is invalid for this trainer: " + str(exc)) from exc
                markers = self.store.expected_markers
                marker_problem = None
                if markers is not None:
                    try:
                        self.one_shot.restore_markers(markers)
                    except OneShotContractError as exc:
                        marker_problem = "One-shot markers are invalid: " + str(exc)
                    else:
                        # Pending auto-on wishes live only in the saved state,
                        # so the markers must be a subset of the desired set.
                        if not set(self.one_shot.saved_wish_ids()) <= (self.desired & self._one_shot_ids):
                            marker_problem = "One-shot markers disagree with the saved state"
                if marker_problem is not None:
                    # Damaged or stale marker data must not hold startup
                    # hostage: quarantine the exact bytes and continue with a
                    # fresh contract. Documented trade-off: a one-shot whose
                    # effect already ran may run once more if it is re-enabled.
                    if self.store.quarantine_one_shot_markers() is None:
                        raise StateError(marker_problem + "; quarantine failed, marker file preserved")
                    self.one_shot = OneShotContract(
                        [(record_id, "script") for record_id in sorted(self._one_shot_ids)],
                        plan["table_sha256"], plan["process_name"])
                self._one_shot_backend = _OneShotBackend(self)
            # Async lifecycle (AP-07-2 slice B): plan entries carrying the
            # compiler marker async=True are routed through the tested
            # ActivationController (attach gate, ownership, safety holds,
            # save boundary). The desired set (state.json) is the cross-session
            # wish store; controller holds are session-scoped on purpose.
            self._async_ids = {entry["id"] for entry in plan["entries"]
                               if entry.get("async") is True and entry.get("selected")
                               and entry.get("supported") and entry["kind"] == "script"}
            self.async_policy = None
            if self._async_ids:
                from .activation_policy import (ActivationController, RecordSpec,
                                                RecordTable, RECORD_ACTION,
                                                RECORD_ASYNC, RECORD_NAVIGATION,
                                                RECORD_VALUE_ONLY)
                records = []
                for entry in plan["entries"]:
                    if not (entry.get("selected") and entry.get("supported")):
                        continue
                    kind = entry["kind"]
                    if kind == "script":
                        spec_kind = RECORD_ASYNC if entry.get("async") is True else RECORD_ACTION
                    elif kind == "heading":
                        spec_kind = RECORD_NAVIGATION
                    elif kind == "value":
                        spec_kind = RECORD_VALUE_ONLY
                    else:
                        continue
                    # Controller record IDs are positive; plan entry IDs start
                    # at 0. Parent propagation stays out of the cascade
                    # (relations empty): provider dependencies are already
                    # handled by _dependencies.
                    records.append(RecordSpec(entry["id"] + 1, spec_kind, ()))
                self.async_policy = ActivationController(RecordTable(records, {}))
            # Parent/child activation (AP-07 stage 3): flagged group headings
            # route their whole subtree through a second tested
            # ActivationController.  The compiler-derived relations (flag
            # class inherited down the flagged parent's subtree, restricted
            # to selected+supported descendants) were re-derived by both
            # plan validators before this point, so the engine trusts them.
            # moBindActivation records carry the named flag so every request
            # touching them is refused before any effect.
            self.parent_policy = None
            parent_relations = {}
            # The plan carries entry IDs (0-based); the tested table uses
            # record IDs (entry ID + 1, same convention as async_policy).
            for parent_key, children in (plan.get("parent_relations") or {}).items():
                parent_relations[int(parent_key) + 1] = {
                    int(child_id) + 1: relation
                    for child_id, relation in children.items()}
            flagged_headings = any(
                (entry.get("parent_activation") is not None
                 or entry.get("parent_mo_bind") is True)
                and entry.get("selected") and entry.get("supported")
                for entry in plan["entries"])
            if parent_relations or flagged_headings:
                from .activation_policy import (ActivationController,
                                                FLAG_MO_BIND_ACTIVATION,
                                                RecordSpec, RecordTable,
                                                RECORD_ACTION, RECORD_ASYNC,
                                                RECORD_NAVIGATION,
                                                RECORD_VALUE_ONLY)
                records = []
                for entry in plan["entries"]:
                    if not (entry.get("selected") and entry.get("supported")):
                        continue
                    kind = entry["kind"]
                    if kind == "script":
                        spec_kind = (RECORD_ASYNC
                                     if entry.get("async") is True
                                     else RECORD_ACTION)
                    elif kind == "heading":
                        spec_kind = (RECORD_ACTION
                                     if (entry.get("parent_activation") is not None
                                         or entry.get("parent_mo_bind") is True)
                                     else RECORD_NAVIGATION)
                    elif kind == "value":
                        spec_kind = RECORD_VALUE_ONLY
                    else:
                        continue
                    parent_ids = tuple(sorted(parent_id
                                              for parent_id, children
                                              in parent_relations.items()
                                              if entry["id"] + 1 in children))
                    records.append(RecordSpec(entry["id"] + 1, spec_kind,
                                              parent_ids))
                relations = {parent_id: dict(children)
                             for parent_id, children in parent_relations.items()}
                flags = {entry["id"] + 1: {FLAG_MO_BIND_ACTIVATION}
                         for entry in plan["entries"]
                         if entry.get("parent_mo_bind") is True
                         and entry.get("selected") and entry.get("supported")}
                self.parent_policy = ActivationController(
                    RecordTable(records, relations, flags=flags))
            self.debug_log.log(
                "engine-init",
                state_dir=str(directory),
                shared_lock_dir=str(shared),
                wishes=sorted(self.desired),
                providers=sorted(self.providers.values()),
            )
        except Exception as init_exc:
            self.debug_log.error("engine-init-failed", init_exc, stage="startup")
            store = getattr(self, "store", None)
            if store is not None:
                try:
                    store.close()
                except Exception:
                    pass
            raise

    def open_lua_session(self, **broker_handlers: Any) -> Any:
        """Create a CE API adapter bound to this confirmed target session.

        Opening a session does not execute table Lua. The caller owns explicit
        source execution and must cancel its host when its activation retires.
        Raw script writes require an activation-owned mutation handler.
        """
        self._guard()
        from .lua_host import EngineLuaBroker, LuaHost
        broker = EngineLuaBroker(self, **broker_handlers)
        host = LuaHost(broker, memory_pool=self.lua_memory_pool)
        self.lua_sessions.append((host, broker))
        return host

    def open_lua_activation(self, identifier: int) -> Any:
        """Bind a Lua scope to a confirmed active record and its exact target.

        Scope memory/symbol/AA receipts are checked with ordinary controller
        receipts. Disable cancels callbacks before restoring scope mutations.
        """
        self._entry(identifier, 'script')
        self._guard()
        self._check_patches()
        if identifier not in self.applied:
            raise NativeRuntimeError('Lua activation requires a confirmed active owner record')
        if identifier in self.lua_activations:
            raise NativeRuntimeError('The record already owns a Lua activation')
        from .lua_activation import LuaActivation
        scope = LuaActivation(self, identifier)
        self.lua_activations[identifier] = scope
        self.lua_sessions.append((scope.host, scope.broker))
        return scope.host

    def _cancel_lua_sessions(self) -> None:
        # WP-54 (d): record sessions only.  The table scope's host retires
        # through _retire_table_lua_scope — ordered after every record
        # consumer has retired — so its timers and symbols live exactly as
        # long as the attach.  The surviving entry is dropped there.
        table_host = self.table_lua_scope[0] if self.table_lua_scope is not None else None
        for host, broker in self.lua_sessions:
            if host is table_host:
                continue
            broker.invalidate()
            host.cancel()
        self.lua_sessions = [entry for entry in self.lua_sessions
                             if entry[0] is table_host]

    def _retire_table_lua_scope(self) -> None:
        """WP-41/WP-54: drop the bootstrap scope (idempotent).

        WP-54 (d): the table scope retires only after every record consumer
        scope has retired, so the table-owned symbols (WP-54 (b)) are
        released exactly once at the end of the teardown — release, then
        cancel the host (its timers die with it), then drop the scope.
        Cancelling the host is idempotent, as is the owner's release, so a
        re-attach starts from a fresh scope; safe to call after
        ``_cancel_lua_sessions`` already retired every record session.
        """
        scope = self.table_lua_scope
        if scope is None:
            return
        host, broker = scope
        # RT-5 item C2: the table-scope custom AA directive registry dies
        # with the scope (CE registrations are session-scoped; no
        # cross-table or cross-attach leakage).
        aa_commands = getattr(broker, "aa_commands", None)
        if isinstance(aa_commands, dict):
            aa_commands.clear()
        broker.owner.release()
        broker.invalidate()
        host.cancel()
        self.lua_sessions = [(item_host, item_broker)
                             for item_host, item_broker in self.lua_sessions
                             if item_host is not host]
        self.table_lua_scope = None

    def _seed_user_defined_symbols(self) -> None:
        """WP-46 (part 1) + WP-54 (e) + RT-4.6: seed the runtime symbol table
        from the plan's table-level <UserdefinedSymbols> map (casefolded
        keys), then from the optional user-symbol import map
        (plan field ``user_symbols``).

        Called at engine init and again on every confirmed attach: the
        confirmed target-exit path clears ``self.symbols`` wholesale, so
        without the reseed table-level-backed records would stop resolving
        after a re-attach within one trainer session.  The call happens
        before any wish restore and before the table-Lua bootstrap (a
        table-scope registerSymbol then keeps CE order and overwrites both
        seeds).  User symbols are seeded after the UDS seed, so an explicit
        operator import overrides a table-level definition of the same
        name; record registrations overwrite both at runtime registration
        (program registrations beat the user-defined symbol table).
        """
        for symbol, address in (self.plan.get("user_defined_symbols") or {}).items():
            self.symbols[symbol.casefold()] = address
        for symbol, address in (self.plan.get("user_symbols") or {}).items():
            self.symbols[symbol.casefold()] = address

    def _dispatch_table_callbacks(self) -> None:
        """RT-5 item D: fire the table's onOpenProcess/onTableLoad callbacks.

        Runs only on a clean table-Lua bootstrap, on the table-scope host,
        in the CE sequence: onOpenProcess with the attached target PID,
        then onTableLoad with the Lua literal false.  Each callback is
        invoked through one pcall-wrapped chunk with the argument
        injected as a literal (the PID as an int, false for
        onTableLoad), so a throwing callback is contained, logged as
        ``table-callback-error`` and cannot touch ``plan["table_lua"]``
        (the clean bootstrap stays clean for the dependent record
        scripts).  A missing or non-function callback is ``absent``: no
        dispatch and no event.  Fail-soft: a Python-level host failure
        logs the same ``table-callback-error`` event and the attach
        continues unblocked.  Bounded deviation vs CE: the
        once-per-attach bootstrap has no before-load phase, so
        onTableLoad only ever sees false.
        """
        scope = self.table_lua_scope
        if scope is None or self.memory is None:
            return
        pid = self.memory.pid
        if type(pid) is not int or pid <= 0:
            return
        host = scope[0]
        for name, argument in (('onOpenProcess', str(pid)),
                               ('onTableLoad', 'false')):
            chunk = ("local function ct2_dispatch()\n"
                     "local fn = rawget(_G, '" + name + "')\n"
                     "if type(fn) ~= 'function' then return 'absent' end\n"
                     "local ok, err = pcall(fn, " + argument + ")\n"
                     "if not ok then return 'error: ' .. tostring(err) end\n"
                     "return 'ok'\n"
                     "end\n"
                     "return ct2_dispatch()")
            try:
                result = host.execute(chunk)
            except Exception as exc:  # fail-soft: log, never block the attach
                self.debug_log.log('table-callback-error', callback=name,
                                   error=str(exc))
                continue
            if type(result) is not str:
                # The dispatch chunk returns only the three tagged
                # strings; anything else is not a callback outcome.
                continue
            if result == 'ok':
                self.debug_log.log('table-callback', callback=name)
            elif result.startswith('error: '):
                self.debug_log.log('table-callback-error', callback=name,
                                   error=result[len('error: '):])
            # 'absent' (missing or not a function) produces no event.

    def _run_table_lua_bootstrap(self) -> None:
        """WP-41: execute the table Lua exactly once per confirmed attach.

        Runs the combined table source in a dedicated read-only scope.
        Refused API calls are recorded with their exact named reason (the
        call is answered with nil so the read-only remainder of the source
        still runs); a genuine execution failure stops the run and appends
        the top-level failure reason.  The outcome fills
        ``plan["table_lua"]``: a clean run persists the scope for the
        table's lifetime, a refused or failed run destroys it and marks
        the activation as not executed.  Fail-soft: the outcome never
        blocks the attach.

        RT-5 item D: after a clean run the table's ``onOpenProcess`` and
        ``onTableLoad`` callbacks are dispatched on the table-scope host
        in CE order (onOpenProcess with the attached PID, then
        onTableLoad with the literal false).  Each callback runs inside
        one pcall-wrapped chunk; a throwing callback is contained and
        logged as ``table-callback-error`` without touching this plan
        metadata, and a missing or non-function callback produces no
        event.  Bounded deviation vs CE: the once-per-attach bootstrap
        has no before-load phase, so onTableLoad only ever sees false;
        the dispatch runs only when the bootstrap itself was clean
        (refused or failed runs retire the scope and skip it).
        """
        from .lua_bootstrap import (MAX_TABLE_LUA_REASONS,
                                    TABLE_LUA_TOP_LEVEL_FAILURE,
                                    record_table_lua_references,
                                    table_top_level_globals,
                                    validate_table_lua_meta)
        from .lua_host import TableLuaBroker, LuaHost
        bootstrap = self.plan.get('lua_bootstrap')
        if bootstrap is None:
            return
        source = bootstrap['source']
        meta = self.plan.get('table_lua')
        if meta is None:
            # Legacy plan without bootstrap metadata: derive the static
            # inactive-record count with the compiler's own algorithm.
            table_globals = table_top_level_globals(source)
            meta = {'executed': False, 'reasons': [],
                    'record_scripts_inactive': sum(
                        1 for entry in self.plan['entries']
                        if 'lua_program' in entry
                        and record_table_lua_references(
                            entry['lua_program']['source'], table_globals))}
            validate_table_lua_meta(meta)
            self.plan['table_lua'] = meta
        else:
            validate_table_lua_meta(meta)
        self._retire_table_lua_scope()
        meta['executed'] = False
        meta['reasons'] = []
        broker = TableLuaBroker(self)
        host = LuaHost(broker, memory_pool=self.lua_memory_pool)
        self.lua_sessions.append((host, broker))
        self.table_lua_scope = (host, broker)
        failure = None
        try:
            host.execute(source)
        except Exception as exc:  # fail-soft: record, never block the attach
            failure = str(exc)
        reasons = list(broker.reasons)
        if failure is not None:
            # Recorded refusals never raise (they are answered with nil), so
            # a top-level failure is always a distinct runtime error. The
            # bounded list drops the failure reason only when the refusal
            # bound is already saturated; the full detail stays in the
            # table-lua-refused debug event.
            if len(reasons) < MAX_TABLE_LUA_REASONS:
                reasons.append(TABLE_LUA_TOP_LEVEL_FAILURE + failure)
        meta['reasons'] = reasons
        meta['executed'] = failure is None and not reasons
        if meta['executed']:
            self.debug_log.log('table-lua-executed',
                               record_scripts_inactive=meta['record_scripts_inactive'])
            # RT-5 item D: the table's onOpenProcess/onTableLoad callbacks
            # dispatch only after a clean bootstrap (see the method).
            self._dispatch_table_callbacks()
        else:
            self.debug_log.log('table-lua-refused', error=failure,
                               reasons=reasons,
                               record_scripts_inactive=meta['record_scripts_inactive'])
            self._retire_table_lua_scope()

    def _release_call_broker(self) -> None:
        """Retire the session-owned call-broker binding (target exit or close).

        Retirement is local bookkeeping only (caves retire with the target,
        the journal stays durable); the discarded binding is replaced by a
        fresh one at the next confirmed attach, never reused across exits.
        """
        if self.call_broker is not None:
            self.call_broker.close()
            self.call_broker = None

    def _release_debugger_session(self) -> None:
        """Retire the session-owned debugger binding (target exit/close).

        The binding contract requires a total detach: even when the
        target already exited, the call must not raise into the poll
        or close path; the binding records its own uncertainty.
        """
        if self.debugger_session is not None:
            self.debugger_session.detach()
            self.debugger_session = None

    def _release_managed_session(self, target_ended: bool) -> None:
        """Retire the session-owned managed-runtime binding (target exit/close).

        Retirement never raises into poll/close: confirmed target exit calls
        the binding's total ``target_ended()`` (which itself must not raise
        and records any uncertainty), while close retires via ``release()``
        only; the tested Mono contract keeps the module hold through
        process exit, so no close is attempted here.
        """
        if self.managed_session is not None:
            session, self.managed_session = self.managed_session, None
            try:
                if target_ended:
                    session.target_ended()
                else:
                    session.release()
            except Exception:
                # Retirement is best-effort by contract; the session is
                # already detached from the engine regardless.
                pass

    def debugger_attach(self, pid: int | None = None) -> None:
        """Attach the owned debugger session to the confirmed target.

        The binding is engine-owned: created on demand through the
        injected debugger_factory and invalidated on target exit and
        close. Every refusal is visible and effect-free; without a
        configured factory the surface stays fail-closed (AP-11).
        """
        if self.closed:
            raise DebuggerNotAttached(
                'The trainer is closed; debugger attach is unavailable')
        if self.memory is None:
            raise DebuggerNotAttached(
                'Target process is not connected; debugger attach requires '
                'an attached session')
        self._guard()
        if pid is not None:
            if type(pid) is not int:
                raise DebuggerBadPid('attachProcess requires an integer PID')
            if pid != self.memory.pid:
                raise DebuggerBadPid(
                    'attachProcess must target the attached game process')
        if self.debugger_session is not None:
            raise DebuggerAlreadyAttached(
                'A debugger session is already attached')
        if self.debugger_factory is None:
            raise DebuggerNotAttached(
                'Debugger attach is not available for this trainer: no '
                'debugger binding was provided. The target process state '
                'is unchanged.')
        session = self.debugger_factory(self, self.memory)
        if session is None:
            raise DebuggerNotAttached(
                'The debugger binding produced no session; attach refused '
                'fail-closed')
        if getattr(session, 'pid', None) != self.memory.pid:
            raise DebuggerBadPid(
                'The debugger session binds a different target identity '
                'than the attached process')
        self.debugger_session = session

    def debugger_detach(self) -> None:
        """Detach the active debugger session; a second detach is visible."""
        if self.closed:
            raise DebuggerNotAttached('The trainer is closed')
        if self.debugger_session is None:
            raise DebuggerNotAttached('No debugger session is attached')
        self.debugger_session.detach()
        self.debugger_session = None

    @property
    def debugger_attached(self) -> bool:
        """Whether a debugger session is currently attached to the target."""
        return self.debugger_session is not None

    def managed_attach(self) -> None:
        """Attach the managed-runtime session to the confirmed target.

        The session is engine-owned: created on demand through the injected
        managed_runtime_factory and retired on confirmed target exit and
        close. Every refusal is visible and effect-free; a second attach
        with a live session is idempotent. Without a configured factory the
        surface stays fail-closed (AP-11).
        """
        if self.closed:
            raise ManagedSessionNotAttached(
                'The trainer is closed; managed runtime attach is unavailable')
        if self.memory is None:
            raise ManagedSessionNotAttached(
                'Target process is not connected; managed runtime attach '
                'requires an attached session')
        self._guard()
        if self.managed_session is not None:
            return
        if self.managed_runtime_factory is None:
            raise ManagedSessionNotAttached(
                'Managed runtime is not available for this trainer: no binding '
                'was provided. The target process state is unchanged.')
        session = self.managed_runtime_factory(self, self.memory)
        if session is None:
            raise ManagedSessionNotAttached(
                'The managed runtime binding produced no session; attach '
                'refused fail-closed')
        if getattr(session, 'pid', None) != self.memory.pid:
            raise ManagedSessionBadPid(
                'The managed runtime session binds a different target '
                'identity than the attached process')
        self.managed_session = session

    def managed_detach(self) -> None:
        """Retire the active managed-runtime session; a second detach is visible."""
        if self.closed:
            raise ManagedSessionNotAttached('The trainer is closed')
        if self.managed_session is None:
            raise ManagedSessionNotAttached('No managed runtime session is attached')
        self.managed_session.release()
        self.managed_session = None

    @property
    def managed_attached(self) -> bool:
        """Whether a managed-runtime session is currently attached to the target."""
        return self.managed_session is not None

    def managed_domains(self) -> list:
        """List the bound route's visible domains as {'id','ptr','generation'} entries."""
        if self.closed:
            raise ManagedSessionNotAttached(
                'The trainer is closed; managed domain listing is unavailable')
        if self.memory is None:
            raise ManagedSessionNotAttached(
                'Target process is not connected; managed domain listing '
                'requires an attached session')
        self._guard()
        if self.managed_session is None:
            raise ManagedSessionNotAttached('No managed runtime session is attached')
        return list(self.managed_session.domains())

    def managed_find_method(self, namespace: str, class_name: str, method_name: str) -> int:
        """Resolve one managed method token through the attached session."""
        if self.closed:
            raise ManagedSessionNotAttached(
                'The trainer is closed; managed method lookup is unavailable')
        if self.memory is None:
            raise ManagedSessionNotAttached(
                'Target process is not connected; managed method lookup '
                'requires an attached session')
        self._guard()
        if self.managed_session is None:
            raise ManagedSessionNotAttached('No managed runtime session is attached')
        for value, name in ((namespace, 'namespace'),
                            (class_name, 'class'),
                            (method_name, 'method')):
            if not isinstance(value, str) or not value:
                raise ManagedValueRefused(name + ' must be non-empty text')
        return self.managed_session.find_method(namespace, class_name, method_name)

    def managed_invoke(self, domain_id: int, method_token: int,
                       is_static: bool, arguments) -> bool:
        """Route one managed invocation through the attached session."""
        if self.closed:
            raise ManagedSessionNotAttached(
                'The trainer is closed; managed invocations are unavailable')
        if self.memory is None:
            raise ManagedSessionNotAttached(
                'Target process is not connected; managed invocations '
                'require an attached session')
        self._guard()
        if self.managed_session is None:
            raise ManagedSessionNotAttached('No managed runtime session is attached')
        if type(domain_id) is not int:
            raise ManagedValueRefused('domain id must be an integer')
        if type(method_token) is not int:
            raise ManagedValueRefused('method token must be an integer')
        if type(is_static) is not bool and (
                type(is_static) is not int or is_static not in (0, 1)):
            raise ManagedValueRefused('is_static must be boolean or 0/1')
        if not isinstance(arguments, (list, tuple)):
            raise ManagedValueRefused('arguments must be a list or tuple')
        return self.managed_session.invoke(
            domain_id=domain_id, method_token=method_token,
            is_static=bool(is_static), arguments=tuple(arguments))

    def typed_call(self, arguments: tuple) -> Any:
        """Route one CE-shaped executeCodeEx typed call through the owned call broker.

        The binding is engine-owned: created at attach through the injected
        call_broker_factory, invalidated on target exit and close. Without a
        configured backend or an attached session the call is refused with a
        named error and has no side effects.
        """
        if self.closed:
            raise TypedCallNotAttached('The trainer is closed; typed calls are unavailable')
        if self.memory is None:
            raise TypedCallNotAttached(
                'Target process is not connected; typed calls require an attached session')
        self._guard()
        broker = self.call_broker
        if broker is None:
            raise TypedCallNotAttached('No call-broker binding is configured for this trainer')
        if broker.image.pid != self.memory.pid:
            raise TypedCallNotAttached(
                'The call-broker binding does not match the attached target identity')
        return execute_code_ex(broker, tuple(arguments))

    @property
    def connected(self) -> bool:
        return self.memory is not None and not self.blocked and not self.closed

    def _block(self, exc: Exception) -> None:
        entry_errors = getattr(self, "entry_errors", {})
        self.debug_log.error("engine-blocked", exc,
                             entry_errors={str(k): v for k, v in sorted(entry_errors.items())})
        self.blocked = True
        self.error = str(exc)
        self.status = "Writes blocked: " + self.error

    def _guard(self) -> None:
        if self.closed or self.blocked:
            raise StateError(self.error or "Trainer is closed")
        try:
            self.store.guard()
            if self.memory is None:
                raise NativeRuntimeError("Target process is not connected")
            if not self.memory.is_alive():
                raise NativeRuntimeError("Target process ended; wait for reconnection")
            require_target_architecture(self.plan, self.memory)
        except StateError as exc:
            self._block(exc)
            raise
        except NativeRuntimeError:
            raise
        except Exception as exc:
            self._block(exc)
            raise NativeRuntimeError(str(exc)) from exc

    def _entry(self, identifier: int, kind: str) -> dict:
        entry = self.entries.get(identifier)
        if entry is None or not entry["selected"] or not entry["supported"] or entry["kind"] != kind:
            raise NativeRuntimeError((entry or {}).get("reason") or f"Entry {identifier} has no supported {kind} action")
        return entry

    def _dependencies(self, entry: dict, trail: set[int] | None = None, persist: bool = True) -> None:
        trail = set() if trail is None else set(trail)
        if entry["id"] in trail:
            raise NativeRuntimeError("Symbol dependency cycle")
        trail.add(entry["id"])
        # RT-4.2 (R7): requirements covered by this record's own api_exports
        # marker are resolved at link time against the target's live export
        # table; no record provider exists for them, so the dependency walk
        # skips them (fail-closed resolution happens in _install_program).
        api_served = {export.casefold() for export in (entry.get("api_exports") or {})}
        for symbol in entry.get("requires", []):
            key = symbol.casefold()
            if key in self.symbols or key in api_served:
                continue
            provider = self.providers.get(key)
            if provider is None:
                raise NativeRuntimeError(f"Missing symbol provider: {symbol}")
            dependency = self.entries[provider]
            self._dependencies(dependency, trail, persist)
            self._enable(dependency, persist)

    def _symbol_consumers(self, names, *, exclude_scope=None, exclude_token=None, exclude_entry=None):
        names = {name.casefold() for name in names}
        consumers = []
        for identifier in set(self.applied) | set(self.frozen):
            if identifier != exclude_entry and names.intersection(name.casefold() for name in self.entries[identifier].get('requires', [])):
                consumers.append('record ' + str(identifier))
        for identifier, scope in self.lua_activations.items():
            if identifier == exclude_scope:
                continue
            for token, item in scope.assemblies.items():
                if (identifier, token) != exclude_token and names.intersection(name.casefold() for name in item['requires']):
                    consumers.append('Lua receipt ' + str(identifier) + ':' + token)
        return consumers

    def _provider_consumers(self, manager, *, exclude_scope=None, exclude_token=None):
        consumers = ['record ' + str(identifier) for identifier, child in self.hooks.items()
                     if child is not manager and child.depends_on_provider(manager)]
        for identifier, scope in self.lua_activations.items():
            if identifier == exclude_scope:
                continue
            for token, item in scope.assemblies.items():
                if (identifier, token) != exclude_token and item['manager'].depends_on_provider(manager):
                    consumers.append('Lua receipt ' + str(identifier) + ':' + token)
        return consumers

    def _owner_consumers(self, identifier):
        names = set(self.entries[identifier].get('provides', []))
        scope = self.lua_activations.get(identifier)
        if scope:
            names.update(scope.symbols)
        consumers = self._symbol_consumers(names, exclude_scope=identifier, exclude_entry=identifier)
        managers = ([self.hooks[identifier]] if identifier in self.hooks else []) + (scope.managers() if scope else [])
        for manager in managers:
            consumers.extend(self._provider_consumers(manager, exclude_scope=identifier))
        return consumers

    def _log_attach_failure(self, event: str, exc: Exception, **details: Any) -> None:
        """Attach-stage failures repeat on every poll; log each distinct cause once.

        The signature is cleared on a confirmed attach so the same cause
        recurring in a later attach attempt is reported again.
        """
        key = (event, type(exc).__name__, str(exc))
        if getattr(self, "_last_attach_failure", None) == key:
            return
        self._last_attach_failure = key
        self.debug_log.error(event, exc, **details)

    @restoration_entry
    def poll(self) -> str:
        if self.closed or self.blocked or self.busy:
            return self.status
        try:
            self.store.guard()
            if self.memory is not None:
                if not self.memory.is_alive():
                    self.debug_log.log("target-exited",
                                       pid=getattr(self.memory, "pid", None),
                                       process_name=self.plan["process_name"])
                    # WP-54 (d): record scopes retire leaves-first as before;
                    # the table scope retires after every record consumer,
                    # releasing its symbols exactly once at that point.
                    self._cancel_lua_sessions()
                    for scope in self.lua_activations.values():
                        scope.finish_after_exit()
                    self.lua_activations.clear()
                    self._retire_table_lua_scope()
                    for manager in list(self.hooks.values()) + self.retired_hooks:
                        manager.finish_after_exit()
                    self.hooks.clear()
                    self.retired_hooks.clear()
                    if self.global_pool is not None:
                        self.global_pool.finish_after_exit(remove_journal=True)
                        self.global_pool=None
                        self.global_leases.clear()
                        self._global_aliases.clear()
                    self._hook_lifetime_bytes = self._hook_lifetime_count = 0
                    if self.one_shot is not None:
                        self.one_shot.detach()
                        self._persist_one_shot_markers()
                    if self.async_policy is not None:
                        # Confirmed target exit: no async effect can persist;
                        # active flags drain, saved wishes survive in state.json.
                        self.async_policy.detach()
                    if self.parent_policy is not None:
                        # Confirmed target exit: no cascade effect persists.
                        self.parent_policy.detach()
                    self._release_call_broker()
                    self._release_debugger_session()
                    self._release_managed_session(True)
                    if self.clock is not None:
                        # Confirmed target exit: no speed state survives the
                        # session; the binding retires visibly (fence plus
                        # lease close back to 1x) and is dropped.
                        self.clock.finish()
                        self.clock = None
                    self.store.release_session()
                    self.memory.close()
                    self.memory = None
                    self.applied.clear()
                    self.local_symbols.clear()
                    self.symbols.clear()
                    self.registered_by.clear()
                    self.frozen.clear()
                    # WP-50 (GC-E8): no live base survives the target exit.
                    self.dynamic_addresses.clear()
                    # RT-5 item C2: no runtime journal survives the target exit
                    # (hook/symbol cleanup above already ran for live records).
                    self._clear_dynamic_records()
                    self._hotkey_sync()
                    self.status = "Target ended; waiting for " + self.plan["process_name"]
                    return self.status
                require_target_architecture(self.plan, self.memory)
                self._check_patches()
                now = time.monotonic()
                elapsed = min(60000, max(0, int((now - self._lua_tick_time) * 1000)))
                self._lua_tick_time = now
                for host, broker in list(self.lua_sessions):
                    if not host.cancelled:
                        host.tick(elapsed)
                if self.clock is not None:
                    self.clock.tick()
                bitfields = []
                strings = []
                for identifier, (address, raw) in list(self.frozen.items()):
                    if self._value_address(self.entries[identifier]) != address:
                        raise PatchConflict("Frozen pointer changed; unfreeze and reconnect before further writes")
                    if self.entries[identifier].get('value_profile', {}).get('kind') == 'bitfield':
                        bitfields.append((identifier, address, raw))
                    elif self.entries[identifier].get('value_profile',{}).get('kind')=='string':
                        strings.append((identifier,address,raw))
                    elif self.memory.read(address, len(raw)) != raw:
                        self._write_transaction([_Patch(address, self.memory.read(address, len(raw)), raw)])
                if bitfields:
                    self._write_bitfields(bitfields)
                if strings:
                    from .string_runtime import write_strings
                    write_strings(self,strings)
                # WP-53 (GC-D7): drain the OS hotkey bridge queue (or the
                # injected test source) and route every captured
                # combination through the tested dispatch path (focus
                # gate, first-wins dedupe, tone policy).  Dispatch runs
                # before the steady liveness sync so bindings published
                # by the just-fired toggle reconcile on this same tick.
                for spec in self._hotkey_drain():
                    self.dispatch_hotkey(spec)
                self._hotkey_sync()
                return self.status
            try:
                memory = self.memory_factory(self.plan["process_name"])
            except Exception as exc:
                self._log_attach_failure("attach-attempt-failed", exc,
                                         process_name=self.plan["process_name"])
                self.error = str(exc)
                self.status = "Waiting / hook into game unavailable: " + self.error
                return self.status
            try:
                if not memory.is_alive():
                    memory.close()
                    return self.status
                try:
                    require_target_architecture(self.plan, memory)
                except ArchitectureError as exc:
                    memory.close()
                    self._log_attach_failure("attach-architecture-refused", exc,
                                             process_name=self.plan["process_name"],
                                             pointer_size=getattr(memory, "pointer_size", None))
                    self.error = str(exc)
                    self.status = "Hook into game refused: " + self.error
                    return self.status
                self.store.claim_session(memory)
            except Exception as exc:
                self._log_attach_failure("attach-session-claim-failed", exc,
                                         process_name=self.plan["process_name"])
                memory.close()
                raise
            if self.call_broker_factory is not None:
                # Session-scoped call-broker binding: a failed factory keeps
                # the trainer waiting (retry on the next poll) instead of
                # attaching without its typed-call backend.
                try:
                    broker = self.call_broker_factory(self, memory)
                    if broker.image.pid != memory.pid:
                        raise NativeRuntimeError(
                            'The call broker binds a different target identity than the attached process')
                except Exception as exc:
                    self._log_attach_failure("attach-call-broker-failed", exc,
                                             process_name=self.plan["process_name"])
                    self.store.release_session()
                    memory.close()
                    self.error = str(exc)
                    self.status = 'Waiting / call broker unavailable: ' + self.error
                    return self.status
            else:
                broker = None
            self.memory = memory
            self.call_broker = broker
            self._lua_tick_time = time.monotonic()
            # Fresh clock binding per confirmed attach: a previous session's
            # owner/lease/fence state must never survive a reattach.
            from .clock_binding import default_speed_binding
            self.clock = (self.clock_factory(self.plan['process_name'])
                          if self.clock_factory is not None else default_speed_binding())
            self.error = ""
            self.status = f"Connected to {self.plan['process_name']} (PID {memory.pid})"
            self.debug_log.log("attached",
                               pid=memory.pid,
                               process_name=self.plan["process_name"],
                               image_path=getattr(memory, "image_path", None),
                               pointer_size=getattr(memory, "pointer_size", None),
                               creation_time=getattr(memory, "creation_time", None))
            self._last_attach_failure = None
            # WP-54 (e): the confirmed target-exit path cleared the runtime
            # symbol table, so the table-level user-defined symbols are
            # reseeded on every confirmed attach — before any wish restore
            # and before the table-Lua bootstrap, whose table-scope
            # registerSymbol then keeps CE order over the UDS seed.
            self._seed_user_defined_symbols()
            # WP-41: the per-table Lua bootstrap runs exactly once per
            # confirmed attach, before any saved wish restore, so record
            # activations already see the final plan["table_lua"] state.
            self._run_table_lua_bootstrap()
            if self.one_shot is not None:
                self._one_shot_generation += 1
                wishes = self.one_shot.attach(self._one_shot_generation)
                # Pending auto-on wishes are in the desired set but not saved
                # yet; they are fulfilled below in this attach. A saved wish
                # without its auto-on entry stays fail-closed.
                if not set(wishes) <= (self.desired & self._one_shot_ids):
                    raise StateError("One-shot markers disagree with the saved state; attach is refused")
            if self.async_policy is not None:
                # Async records run only after this confirmed attach; saved
                # wishes in the desired set are replayed in the restore loop below.
                self.async_policy.attach_confirmed()
            if self.parent_policy is not None:
                # Parent cascade targets only after a confirmed attach; mirror
                # the persisted wish store so direct-activation expansion sees
                # saved child wishes, then replay in the restore loop below.
                self.parent_policy.attach_confirmed()
                for identifier in sorted(self.desired):
                    self._mirror_parent_state(identifier)
            self.busy = True
            self.debug_log.log("restore-start", wishes=sorted(self.desired))
            try:
                for identifier in sorted(self.desired):
                    entry = self.entries[identifier]
                    try:
                        # Field case 2026-10-23 (Sinking City 2, 0.16.3):
                        # mark every wish restore start so a hard process
                        # exit mid-restore leaves the last in-progress
                        # entry identifiable in the debug log.
                        self.debug_log.log("restore-entry-start",
                                           identifier=identifier,
                                           label=entry["label"])
                        if entry.get("one_shot") and entry.get("async") is not True:
                            self._dependencies(entry, persist=False)
                            if (self.one_shot is not None
                                    and identifier not in self.one_shot.saved_wish_ids()):
                                # Pending auto-on wish: fulfill it exactly once for
                                # this attach generation; a failed attempt stays in
                                # the saved state (not saved as a wish) and is
                                # retried on the next attach.
                                self._enable_one_shot(entry, persist=False)
                                self.debug_log.log("wish-restored", identifier=identifier,
                                                   label=entry["label"], one_shot=True)
                            continue
                        self._dependencies(entry, persist=False)
                        self._enable(entry, persist=False)
                        self.debug_log.log("wish-restored", identifier=identifier,
                                           label=entry["label"])
                    except RetryableAction:
                        # A safe-data-write wait is a session-level condition,
                        # not a per-record failure: re-raise so the outer
                        # handler sets the waiting status and the next poll
                        # retries the remaining wishes.
                        raise
                    except (NativeRuntimeError, ScanMiss) as exc:
                        # One record's failed restore (stale pattern, missing
                        # provider, …) fails that record only; the remaining
                        # saved wishes keep restoring and the engine stays
                        # usable.  The fail-close rule mirrors interactive
                        # toggle: PatchConflict/StateError blocks the engine
                        # (a StateError from _guard() or _save() has already
                        # called _block()), and the loop then stops because
                        # further writes are forbidden.
                        if (isinstance(exc, (PatchConflict, StateError))
                                and not self.blocked):
                            self._block(exc)
                        self.debug_log.error("restore-failed", exc,
                                             identifier=identifier, label=entry["label"])
                        self.entry_errors[identifier] = str(exc)
                        if self.blocked:
                            break
                        self.error = str(exc)
                        self.status = "Restore failed: " + self.error
                if self.one_shot is not None and not self.blocked:
                    attempted, _skipped = self.one_shot.replay_saved_wishes(self._one_shot_backend)
                    for record_id in attempted:
                        if self.one_shot.query(record_id)["last_outcome"] == "failed":
                            self.entry_errors[record_id] = "One-shot replay failed; the wish is not re-saved"
                    self._persist_one_shot_markers()
            except NativeRuntimeError as exc:
                self.debug_log.error("restore-failed", exc, identifier=identifier)
                self.error = str(exc)
                self.entry_errors[identifier] = self.error
                self.status = "Restore failed: " + self.error
            finally:
                self.busy = False
        except RetryableAction as exc:
            self.error = str(exc)
            self.status = 'Waiting for a safe data-write point: ' + self.error
        except Exception as exc:
            self._block(exc)
        self._hotkey_sync()
        return self.status

    def _check_patches(self) -> None:
        if self.global_pool is not None:
            try: self.global_pool.diagnostic()
            except Exception as exc: raise StateError('Shared-global ownership is uncertain: '+str(exc)) from exc
        for scope in self.lua_activations.values():
            scope.check()
        for manager in self.retired_hooks:
            try:
                manager.receipt()
            except Exception as exc:
                raise StateError('A retired executable allocation receipt changed: '+str(exc)) from exc
        for manager in self.hooks.values():
            if manager.uncertain:
                raise StateError('An executable hook receipt is uncertain')
            try:
                manager.check_entries()
            except Exception as exc:
                raise PatchConflict('An executable hook receipt changed: '+str(exc)) from exc
        for patches in self.applied.values():
            for patch in patches:
                if self.memory.read(patch.address, len(patch.changed)) != patch.changed:
                    raise PatchConflict(f"Active patch changed externally at 0x{patch.address:X}; it will not be overwritten")

    def _operations(self, entry: dict, section: str) -> tuple[dict[str, int], set[str], list[_Patch]]:
        symbols = dict(self.symbols)
        symbols.update(self.local_symbols.get(entry["id"], {}))
        registered: set[str] = set()
        assertions: list[tuple[int, bytes]] = []
        patches: list[_Patch] = []
        for op in entry[section]:
            operation = op["op"]
            if operation == "scan":
                module = self.plan["process_name"] if op["module"] == "$process" else op["module"]
                try:
                    address = self.memory.scan_module(module, op["pattern"])
                except Exception as exc:
                    self.debug_log.error("scan-failed", exc, entry_id=entry["id"],
                                         symbol=op["symbol"],
                                         module=module, pattern=op["pattern"],
                                         section=section)
                    raise
                scan_details = {"entry_id": entry["id"], "symbol": op["symbol"],
                                "module": module,
                                "pattern": op["pattern"], "address": hex(address),
                                "section": section}
                # Multi-match module scans resolve to the lowest address (CE
                # parity): record the full match evidence; single-match scans
                # keep the 0.14 log shape byte-identical.
                diagnostics = getattr(self.memory, "last_scan_diagnostics", None)
                if isinstance(diagnostics, dict) and diagnostics.get("match_count", 0) > 1:
                    scan_details["match_count"] = diagnostics["match_count"]
                    scan_details["match_offsets"] = [hex(offset) for offset in diagnostics.get("match_addresses", [])]
                # WP-57: capture placeholder spans of the matched bytes so the
                # scan evidence is visible in the debug log.
                spans = placeholder_spans(op["pattern"])
                if spans:
                    raw = self.memory.read(address, pattern_byte_length(op["pattern"]))
                    scan_details["captured_placeholders"] = {
                        name: raw[offset:offset + count].hex().upper()
                        for name, (offset, count) in spans.items()}
                if self.debug_log.enabled:
                    try:
                        base, size = self.memory.module(module)
                        scan_details["module_base"] = hex(base)
                        scan_details["module_size"] = size
                        scan_details["rva"] = hex(address - base)
                    except Exception:
                        pass
                self.debug_log.log("scan", **scan_details)
                symbols[op["symbol"].casefold()] = address
            elif operation == "define":
                address = self.memory.resolve(op["expression"], symbols)
                symbols[op["symbol"].casefold()] = address
                self.debug_log.log("define", symbol=op["symbol"],
                                   expression=op["expression"],
                                   address=hex(address), section=section)
            elif operation == "register":
                key = op["symbol"].casefold()
                if key not in symbols:
                    raise NativeRuntimeError(f"Cannot register undefined symbol {op['symbol']}")
                registered.add(key)
                self.debug_log.log("symbol-registered", symbol=op["symbol"], section=section)
            elif operation == "unregister":
                registered.discard(op["symbol"].casefold())
                self.debug_log.log("symbol-unregistered", symbol=op["symbol"], section=section)
            elif operation == "assert":
                address = self.memory.resolve(op["address"], symbols)
                expected = bytes.fromhex(op["bytes"])
                actual = self.memory.read(address, len(expected))
                if actual != expected:
                    self.debug_log.log("assert-failed", address=hex(address),
                                       expected=expected.hex(" "),
                                       actual=actual.hex(" "), section=section)
                    raise NativeRuntimeError(f"Byte assertion failed at 0x{address:X}")
                assertions.append((address, expected))
                self.debug_log.log("assert", address=hex(address), section=section)
            elif operation == "write":
                address = self.memory.resolve(op["address"], symbols)
                changed = bytes.fromhex(op["bytes"])
                original = None
                for start, expected in reversed(assertions):
                    offset = address - start
                    if 0 <= offset and offset + len(changed) <= len(expected):
                        original = expected[offset:offset + len(changed)]
                        break
                if original is None:
                    raise NativeRuntimeError("Every patch requires a preceding byte assertion")
                if any(address < patch.address + len(patch.changed) and patch.address < address + len(changed) for patch in patches):
                    raise NativeRuntimeError("Overlapping patches in one script are unsupported")
                patches.append(_Patch(address, original, changed))
                self.debug_log.log("patch-planned", address=hex(address),
                                   original=original.hex(" "), changed=changed.hex(" "),
                                   section=section)
        return symbols, registered, patches

    @restoration_entry
    def _write_transaction(self, patches: list[_Patch], *, proof=None, before_write=None, transaction_guard=None) -> None:
        # Controller-only forward admission. Exact rollback keeps its own
        # target/byte/proof guards and does not inherit an expired Lua slice.
        if before_write is None:
            from .lua_work_budget import broker_checkpoint
            before_write = broker_checkpoint
        elif not callable(before_write):
            raise NativeRuntimeError('Write admission requires a private callable')
        if transaction_guard is not None and not callable(transaction_guard):
            raise NativeRuntimeError('Transaction guard must be a private callable')
        self._guard()
        if any(self._is_executable(p.address,len(p.changed)) for p in patches):
            if proof is not None or transaction_guard is not None:
                raise NativeRuntimeError('Held data-only transactions cannot dispatch executable mutations')
            self._write_owned_literal_values(patches)
            return
        for patch in patches:
            current = self.memory.read(patch.address, len(patch.original))
            if current != patch.original:
                self.debug_log.log("write-refused", address=hex(patch.address),
                                   expected_original=patch.original.hex(" "),
                                   found=current.hex(" "))
                raise PatchConflict(f"Bytes changed before write at 0x{patch.address:X}")
        attempted: list[_Patch] = []
        def guard():
            self._guard()
            if proof is not None:
                proof.verify(self.memory, proof.ranges)
            if transaction_guard is not None:
                transaction_guard()
        try:
            for patch in patches:
                guard()
                if self.memory.read(patch.address, len(patch.original)) != patch.original:
                    raise PatchConflict(f"Bytes changed immediately before write at 0x{patch.address:X}")
                before_write()
                attempted.append(patch)
                from .memory import _checked_write
                def admit(patch=patch):
                    guard()
                    if self.memory.read(patch.address, len(patch.original)) != patch.original:
                        raise PatchConflict("Bytes changed at the final kernel write boundary")
                    before_write()
                    if proof is not None and proof.check() is not True:
                        raise PatchConflict("Data write lease expired before kernel mutation")
                _checked_write(self.memory, patch.address, patch.changed, before_kernel=admit)
                if self.memory.read(patch.address, len(patch.changed)) != patch.changed:
                    raise NativeRuntimeError("Write readback failed")
                self.debug_log.log("patch-written", address=hex(patch.address),
                                   original=patch.original.hex(" "),
                                   changed=patch.changed.hex(" "))
            guard()
            for patch in patches:
                if self.memory.read(patch.address, len(patch.changed)) != patch.changed:
                    raise PatchConflict("Patch changed before confirmation")
        except Exception as exc:
            failed = attempted[-1] if attempted else None
            self.debug_log.error("write-failed", exc,
                                 attempted_addresses=[hex(p.address) for p in attempted],
                                 failed_address=hex(failed.address) if failed else None)
            if not attempted:
                raise NativeRuntimeError('Write refused before mutation: ' + str(exc)) from exc
            try:
                with restoration_region(guard,_clock_for(self)):
                    guard()
                    for patch in reversed(attempted):
                        guard()
                        current = self.memory.read(patch.address, len(patch.changed))
                        if current == patch.original:
                            continue  # A clean last-kernel refusal needs no write.
                        if any(c not in (a, b) for c, a, b in zip(current, patch.original, patch.changed)):
                            raise PatchConflict("Rollback would overwrite foreign bytes")
                        from .memory import _checked_write
                        def admit_undo(patch=patch, expected=current):
                            guard()
                            if self.memory.read(patch.address, len(expected)) != expected:
                                raise PatchConflict("Rollback bytes changed at the final kernel boundary")
                            if proof is not None and proof.check() is not True:
                                raise PatchConflict("Rollback lease expired before kernel mutation")
                        _checked_write(self.memory, patch.address, patch.original,
                                       before_kernel=admit_undo, rollback=True)
                        if self.memory.read(patch.address, len(patch.original)) != patch.original:
                            raise NativeRuntimeError("Rollback readback failed")
            except Exception as rollback_error:
                self.debug_log.error("rollback-failed", rollback_error,
                                     address=hex(failed.address) if failed else None)
                self._block(NativeRuntimeError(f"Write failed and rollback is uncertain: {exc}; {rollback_error}"))
                raise NativeRuntimeError(self.error) from exc
            raise NativeRuntimeError(f"Write failed; original bytes restored: {exc}") from exc

    def _abandon_after_failure(self, manager, primary: Exception) -> None:
        """Keep failed unpublished reclamation owned and block the controller."""
        try:
            manager.abandon_unpublished()
        except Exception as cleanup:
            if manager not in self.retired_hooks:
                self.retired_hooks.append(manager)
            error = StateError(str(primary) + "; unpublished compensation is uncertain: " + str(cleanup))
            self._block(error)
            raise NativeRuntimeError(str(error)) from primary

    def _write_owned_literal_values(self, patches: list[_Patch]) -> None:
        from .hooks import HookManager, HookUncertain
        if not all(self._is_executable(p.address, len(p.changed)) for p in patches):
            raise NativeRuntimeError('Mixed ordinary/executable value transactions are unsupported')
        _, permits = self._owned_provider_data()
        if not all(any(start <= p.address and p.address + len(p.changed) <= start + size
                       for start, size, _, _ in permits) for p in patches):
            raise NativeRuntimeError('Executable pages require exact live provider literal-data provenance')
        manager = HookManager(self.memory, self.store.directory / 'hooks' / (uuid.uuid4().hex + '.json'),
                              self.hook_coordinator, owner_id=self.plan['trainer_id'] + ':literal-value',
                              owned_executable_data_ranges=permits)
        try:
            manager.stage([{'address': p.address, 'bytes': p.changed.hex(), 'original': p.original.hex(),
                            'is_allocation': False, 'executable': True, 'requires_coordinator': True,
                            'literal_data': True, 'data_semantics': True} for p in patches])
            manager.publish()
            manager.commit_data_only()
            self.retired_hooks.append(manager)
        except Exception as exc:
            if manager.uncertain or isinstance(exc, HookUncertain) or manager.state == 'enabled':
                self._block(StateError('Literal value mutation is uncertain: ' + str(exc)))
                raise NativeRuntimeError(str(exc)) from exc
            self._abandon_after_failure(manager, exc)
            raise RetryableAction(str(exc)) from exc

    def _save(self, desired: set[int]) -> None:
        try:
            self._guard()
            self._check_patches()
            # RT-5 item C2: journal IDs are synthetic session state (>= 2**31,
            # refused by the state store); they can never be saved wishes.
            # The journal enable paths pass persist=False, so this filter is
            # belt-and-braces only.
            desired = {i for i in desired if i not in self.dynamic_records}
            self.store.save(desired)
            self.desired = set(desired)
            self.debug_log.log("state-save", desired=sorted(desired))
        except Exception as exc:
            self.debug_log.error("state-save-failed", exc, desired=sorted(desired))
            self._block(exc)
            raise NativeRuntimeError(str(exc)) from exc

    def _enable(self, entry: dict, persist: bool = True) -> None:
        identifier = entry["id"]
        # WP-14 (C2): a flagged parent always cascades through the parent
        # policy, even when its own effect is async; the cascade controller
        # carries the attach gate, safety holds and the save boundary.
        if (entry.get("parent_activation") is not None
                or entry.get("parent_mo_bind") is True):
            self._enable_parent(entry, persist)
            return
        if entry["kind"] == "heading":
            # WP-53 (GC-D7): a plain group heading (no cascade flags)
            # carries no effect of its own; activation flips the group's
            # own active state only - no child propagation and no
            # target-memory operation (CE parity).
            if identifier in self.applied:
                return
            self.applied[identifier] = []
            if persist:
                self._save(self.desired | {identifier})
            self._mirror_parent_state(identifier)
            return
        if entry.get("async") is True:
            self._enable_async(entry, persist)
            return
        if entry.get("one_shot"):
            self._enable_one_shot(entry, persist)
            return
        if identifier in self.applied:
            return
        self._guard()
        self._check_patches()
        self._enable_dispatch(entry, persist)
        self._mirror_parent_state(identifier)

    def _apply_activation_set(self, entry: dict, enabled: bool, persist: bool) -> None:
        """WP-14 (C3): master-toggle effect through the static record-ID set.

        Instead of executing the CE-coupled embedded Lua (contract C3), the
        record's statically extracted enable/disable set is applied through
        the ordinary per-record activation path:

        - targets are processed in plan order and symbol providers are
          auto-enabled through dependency resolution;
        - value targets are availability-only (no effect to run) and are
          skipped;
        - already-live targets are left alone (idempotent re-toggle);
        - on disable, dependents are torn down before their symbol
          providers so every disable phase can still resolve its symbols;
        - the first failure stops the application and is re-raised so the
          caller's hold/failure classification applies; already applied
          targets stay applied (visible partial state, no silent success).

        Save boundary: only the master record's own wish is persisted.
        """
        identifier = entry["id"]
        if enabled:
            for target_id in entry["activation_sets"]["enable"]:
                target_entry = self.entries.get(target_id)
                if (target_entry is None or not target_entry["selected"]
                        or not target_entry["supported"]):
                    raise NativeRuntimeError(
                        "Activation set target %d is not a supported selected record"
                        % target_id)
                if target_entry["kind"] == "value":
                    # Availability derives from provider liveness; no effect to run.
                    continue
                if (target_id in self.applied
                        or self._parent_effect_live(target_id)):
                    continue
                self._dependencies(target_entry, persist=False)
                self._enable(target_entry, persist=False)
        else:
            # Dependents before providers: a target's disable phase may still
            # resolve symbols another live target registers, and the
            # dependent guard refuses to tear down a provider with live
            # dependents.  A target is ready once no other remaining target
            # requires a symbol it provides.
            remaining = [target for target in entry["activation_sets"]["disable"]
                         if self._parent_effect_live(target)]
            while remaining:
                required_by = set()
                for other in remaining:
                    required_by.update(self.entries[other].get("dependency_ids", ()))
                ready = [target for target in remaining
                         if target not in required_by]
                if not ready:
                    # Defensive fallback; symbol cycles are compile-time
                    # errors, so this never happens for valid plans.
                    ready = [min(remaining)]
                target_id = min(ready)
                target_entry = self.entries.get(target_id)
                if (target_entry is None or not target_entry["selected"]
                        or not target_entry["supported"]):
                    raise NativeRuntimeError(
                        "Activation set target %d is not a supported selected record"
                        % target_id)
                self._disable(target_entry, persist=False)
                remaining.remove(target_id)
        if enabled:
            self.applied[identifier] = []
        else:
            self.applied.pop(identifier, None)
        if persist:
            if enabled:
                self._save(self.desired | {identifier})
            else:
                self._save(self.desired - {identifier})
        self._mirror_parent_state(identifier)

    def _enable_dispatch(self, entry: dict, persist: bool) -> None:
        """Activation dispatch shared by the sync and async enable paths."""
        if entry.get("activation_sets") is not None:
            self._apply_activation_set(entry, True, persist)
        elif 'lua_program' in entry:
            self._enable_lua_program(entry, persist)
        elif 'global_program' in entry:
            self._enable_global_program(entry,persist)
        elif 'program' in entry:
            self._enable_program(entry, persist)
        else:
            self._enable_byte_patch(entry, persist, one_shot=False)
        # RT-5 item C2: plan-record OnActivate (CE MemoryRecord.OnActivate)
        # fires once the effect is fully applied.  Journal records fire
        # their own callbacks from dynamic_record_active; the 'dynamic'
        # marker excludes them here, so no double fire.
        if not entry.get("dynamic"):
            self._fire_plan_record_callback(entry["id"], "on_activate", False, True)

    def _owned_symbols(self, identifier: int, registered: set[str]) -> set[str]:
        """RT-4.1 keep-first ownership for one entry's registration.

        A symbol owned by another active entry (``registered_by``) keeps
        that entry's binding: the duplicate registration is a silent
        no-op and ownership never transfers (CE dupIgnore narrowing on
        top of the WP-37 keep-first policy — static resolution and
        runtime registration agree on the first registrant).  Table-level
        seeds (UDS/table-Lua) are not entry-owned, so a record
        registration still overwrites them (WP-46/WP-54 seed policy).
        Re-enabling an already-active entry keeps its existing ownership.
        """
        if identifier in self.registered_by:
            return set(self.registered_by[identifier])
        entry_owned = {key for keys in self.registered_by.values() for key in keys}
        return {key for key in registered if key not in entry_owned}

    def _enable_byte_patch(self, entry: dict, persist: bool, *, one_shot: bool) -> None:
        identifier = entry["id"]
        symbols, registered, patches = self._operations(entry, "enable")
        # RT-4.1 (CE dupIgnore narrowing, WP-37 keep-first): a symbol
        # another active entry already registered keeps that entry's
        # binding; this entry's duplicate registration is a silent no-op
        # while its non-duplicate registrations still take effect.
        owned = self._owned_symbols(identifier, registered)
        for existing in self.applied.values():
            for ours in patches:
                if any(ours.address < other.address + len(other.changed) and other.address < ours.address + len(ours.changed) for other in existing):
                    raise NativeRuntimeError("A patch overlaps another enabled entry")
        for address, raw in self.frozen.values():
            if any(patch.address < address + len(raw) and address < patch.address + len(patch.changed) for patch in patches):
                raise NativeRuntimeError("A patch overlaps a frozen value; unfreeze that entry first")
        for scope in self.lua_activations.values():
            if any(scope.overlaps(patch.address, len(patch.changed)) for patch in patches):
                raise NativeRuntimeError('A record patch overlaps a Lua-owned mutation')
        if not one_shot:
            # Evaluate disable against the prospective symbol bindings before
            # writing. Its asserts are checked during the actual disable, while
            # exact reversal is checked here from the declarative operation
            # bytes. One-shots have no disable phase; their close-time restore
            # is derived from the applied journal instead.
            simulated = dict(symbols)
            reversal: list[tuple[int, bytes]] = []
            for op in entry["disable"]:
                if op["op"] == "define":
                    simulated[op["symbol"].casefold()] = self.memory.resolve(op["expression"], simulated)
                elif op["op"] == "write":
                    reversal.append((self.memory.resolve(op["address"], simulated), bytes.fromhex(op["bytes"])))
            if sorted(reversal) != sorted((p.address, p.original) for p in patches):
                raise NativeRuntimeError("Disable must restore exactly the asserted original bytes")
        executable=[self._is_executable(p.address,len(p.changed)) for p in patches]
        if any(executable):
            if not all(executable):
                raise NativeRuntimeError('A literal script mixing executable and external data patches requires the full assembler transaction profile')
            self._enable_literal_code(entry,patches,{key:symbols[key] for key in registered})
        else:
            self._write_transaction(patches)
        self.local_symbols[identifier] = symbols
        self.applied[identifier] = patches
        self.symbols.update({key: symbols[key] for key in owned})
        self.registered_by[identifier] = owned
        if persist:
            self._save(self.desired | {identifier})

    def _is_executable(self,address: int,size: int) -> bool:
        # Injected test backends predate allocation support; the real Win32
        # backend always supplies this page-protection classifier.
        method=getattr(self.memory,'is_executable',None)
        return bool(method(address,size)) if method else False

    def _enable_literal_code(self,entry: dict,patches: list[_Patch],exports: dict) -> None:
        from .hooks import HookManager,HookUncertain
        if self.hook_coordinator is None:
            raise NativeRuntimeError('Executable literal patches require a verified target thread coordinator')
        manager=HookManager(self.memory,self.store.directory/'hooks'/(uuid.uuid4().hex+'.json'),
                            self.hook_coordinator,owner_id=self.plan['trainer_id']+':'+str(entry['id']))
        try:
            manager.stage([{'address':p.address,'bytes':p.changed.hex(),'original':p.original.hex(),
                            'is_allocation':False,'executable':True,'requires_coordinator':True}
                           for p in patches],exports)
            manager.publish()
            self.hooks[entry['id']]=manager
        except Exception as exc:
            if manager.uncertain or isinstance(exc,HookUncertain):
                self._block(StateError('Executable literal mutation is uncertain: '+str(exc)))
            elif manager.state not in {'enabled','retired','target-exited','abandoned'}:
                self._abandon_after_failure(manager, exc)
            raise NativeRuntimeError(str(exc)) from exc

    def _enable_program(self, entry: dict, persist: bool,
                        custom_commands: dict | None = None) -> None:
        manager, linked, live = self._install_program(entry['program'], entry['id'],
                                                      api_exports=entry.get("api_exports"),
                                                      custom_commands=custom_commands)
        self.hooks[entry['id']] = manager
        self.applied[entry['id']] = [_Patch(b['address'], bytes.fromhex(b['original']), bytes.fromhex(b['bytes'])) for b in live]
        self.local_symbols[entry['id']] = linked['symbols']
        exports = {k.casefold(): v for k, v in linked['exports'].items()}
        owned = self._owned_symbols(entry['id'], set(exports))
        self.symbols.update({k: exports[k] for k in owned})
        self.registered_by[entry['id']] = owned
        if persist:
            self._save(self.desired | {entry['id']})

    def _enable_one_shot(self, entry: dict, persist: bool = True) -> None:
        """Enable a one-shot record: one publish, wish saved only on confirmation."""
        identifier = entry["id"]
        receipt = self.one_shot.request_on(self._one_shot_backend, identifier)
        if receipt is None:
            raise NativeRuntimeError("One-shot publish is pending; a backend receipt is required")
        if not receipt.confirmed:
            self._persist_one_shot_markers()
            error = self._one_shot_backend.last_error
            self._one_shot_backend.last_error = None
            if isinstance(error, NativeRuntimeError):
                raise error
            raise NativeRuntimeError("One-shot enable failed") from error
        self.one_shot.save(identifier)
        if persist:
            self._save(self.desired | {identifier})
        self._persist_one_shot_markers()

    def _one_shot_activate(self, entry: dict) -> None:
        """Perform the single bounded publish for one one-shot attempt.

        A record that still owns its effect is re-enabled by verification
        alone: Lua/assembly ownership is re-checked, and a byte patch is
        republished once only when the target no longer holds either the
        applied or the original bytes (anything foreign fails closed).
        """
        identifier = entry["id"]
        self._guard()
        self._check_patches()
        if identifier in self.applied:
            if 'lua_program' in entry:
                scope = self.lua_activations.get(identifier)
                if scope is None:
                    raise NativeRuntimeError('One-shot Lua activation is missing; refusing to re-enable')
                scope.check()
            elif 'program' in entry:
                manager = self.hooks.get(identifier)
                if manager is None or manager.uncertain:
                    raise NativeRuntimeError('One-shot assembly receipt is missing or uncertain; refusing to re-enable')
                manager.check_entries()
            else:
                patches = self.applied[identifier]
                intact = True
                reverted = True
                for patch in patches:
                    current = self.memory.read(patch.address, len(patch.changed))
                    if current != patch.changed:
                        intact = False
                    if current != patch.original:
                        reverted = False
                if intact:
                    return
                if not reverted:
                    raise NativeRuntimeError("One-shot effect bytes are neither applied nor original; refusing to re-enable")
                del self.applied[identifier]
                self.local_symbols.pop(identifier, None)
                self._enable_byte_patch(entry, persist=False, one_shot=True)
            return
        if 'lua_program' in entry:
            self._enable_lua_program(entry, persist=False)
        elif 'program' in entry:
            self._enable_program(entry, persist=False)
        else:
            self._enable_byte_patch(entry, persist=False, one_shot=True)

    def _one_shot_off(self, entry: dict, persist: bool = True) -> None:
        """One-shot OFF: zero backend operations; the saved wish is cleared only.

        The applied effect stays visible in the target as effect_persists;
        trainer ownership of all receipts is preserved until close or the
        target exits.
        """
        identifier = entry["id"]
        self._guard()
        self.one_shot.request_off(self._one_shot_backend, identifier)
        if persist:
            self._save(self.desired - {identifier})
        self._persist_one_shot_markers()

    def _persist_one_shot_markers(self) -> None:
        if self.one_shot is None:
            return
        try:
            raw = self.one_shot.encode_markers()
        except OneShotContractError as exc:
            raise StateError("One-shot markers cannot be encoded: " + str(exc)) from exc
        self.store.save_one_shot_markers(raw)

    def _enable_async(self, entry: dict, persist: bool = True) -> None:
        """Async record ON through the ActivationController.

        The controller gates attach, ownership and safety holds. The effect is
        confirmed with the request generation before the wish may be saved -
        One-Shot save-boundary parity. A record that still owns its effect is
        re-enabled by verification alone.
        """
        identifier = entry["id"]
        record_id = identifier + 1
        try:
            request_id = self.async_policy.request(record_id, "activate")
            self.async_policy.dispatch(request_id)
            self.async_policy.publish(request_id)
            generation = self.async_policy.request_generation(request_id)
        except ActivationPolicyError as exc:
            raise NativeRuntimeError(str(exc)) from exc
        try:
            self._guard()
            self._check_patches()
            if entry.get("one_shot"):
                self._enable_one_shot(entry, persist=False)
            elif identifier in self.applied:
                self._async_verify_effect(entry)
            else:
                self._enable_dispatch(entry, persist=False)
        except Exception as exc:
            if self._async_effect_landed(entry):
                self.async_policy.fail_after_effect(request_id)
            else:
                self.async_policy.fail_before_effect(request_id)
            raise
        self.async_policy.confirm_success(request_id, generation)
        # The desired set (state.json) is the cross-session wish store; it is
        # only ever written after this confirmed success, so a failed attempt
        # never persists as a wish (One-Shot save-boundary parity).
        if persist:
            self._save(self.desired | {identifier})
        self._mirror_parent_state(identifier)

    def _disable_async(self, entry: dict, persist: bool = True) -> None:
        """Async record OFF through the ActivationController.

        A confirmed deactivate clears the saved wish before the desired set is
        persisted; a failed restore fails the request after effect and holds
        the record under safety review.
        """
        identifier = entry["id"]
        record_id = identifier + 1
        try:
            request_id = self.async_policy.request(record_id, "deactivate")
            self.async_policy.dispatch(request_id)
            self.async_policy.publish(request_id)
            generation = self.async_policy.request_generation(request_id)
        except ActivationPolicyError as exc:
            raise NativeRuntimeError(str(exc)) from exc
        try:
            if entry.get("one_shot"):
                self._one_shot_off(entry, persist=False)
            else:
                self._disable_non_one_shot(entry, persist=False, run_lua_disable=True)
        except Exception:
            self.async_policy.fail_after_effect(request_id)
            raise
        self.async_policy.confirm_success(request_id, generation)
        if persist:
            self._save(self.desired - {identifier})
        self._mirror_parent_state(identifier)

    def _async_verify_effect(self, entry: dict) -> None:
        """Re-enable of an async record that still owns its effect.

        Byte-patch records were already re-verified by the caller through
        _check_patches; Lua and assembly activations get their own check.
        """
        identifier = entry["id"]
        if entry.get("activation_sets") is not None:
            # A set effect owns no memory footprint of its own; the applied
            # mark plus the targets' own effects are the verifiable state.
            return
        if 'lua_program' in entry:
            scope = self.lua_activations.get(identifier)
            if scope is None:
                raise NativeRuntimeError('Async Lua activation is missing; refusing to re-enable')
            scope.check()
        elif 'program' in entry:
            manager = self.hooks.get(identifier)
            if manager is None or manager.uncertain:
                raise NativeRuntimeError('Async assembly receipt is missing or uncertain; refusing to re-enable')
            manager.check_entries()

    def _async_effect_landed(self, entry: dict) -> bool:
        """True when a failed async attempt left a verifiable effect in place.

        Purely observational: the intended enable writes are resolved without
        executing their assertions (a failed assertion proves that no write
        preceded it), and the target bytes are compared against the intended
        changed bytes. Unresolvable addresses fail closed to a hold.
        """
        identifier = entry["id"]
        if entry.get("activation_sets") is not None:
            # The set "lands" as soon as any enabled target is live.
            return any(target in self.applied
                       for target in entry["activation_sets"]["enable"])
        if identifier in self.hooks or identifier in self.lua_activations \
                or identifier in self.global_leases:
            return True
        if 'program' in entry or 'global_program' in entry or 'lua_program' in entry:
            return False
        try:
            writes = self._async_enable_writes(entry)
        except Exception:
            return True
        for address, changed in writes:
            try:
                if self.memory.read(address, len(changed)) == changed:
                    return True
            except Exception:
                return True
        return False

    def _async_enable_writes(self, entry: dict) -> list[tuple[int, bytes]]:
        """Intended byte writes of an enable, resolved without asserting."""
        symbols = dict(self.symbols)
        symbols.update(self.local_symbols.get(entry["id"], {}))
        writes = []
        for op in entry["enable"]:
            operation = op["op"]
            if operation == "scan":
                module = self.plan["process_name"] if op["module"] == "$process" else op["module"]
                symbols[op["symbol"].casefold()] = self.memory.scan_module(module, op["pattern"])
            elif operation == "define":
                symbols[op["symbol"].casefold()] = self.memory.resolve(op["expression"], symbols)
            elif operation == "write":
                address = self.memory.resolve(op["address"], symbols)
                writes.append((address, bytes.fromhex(op["bytes"])))
        return writes

    def async_query(self, identifier: int) -> dict:
        """Controller state for one async record (active, hold, saved wish).

        The saved wish is reported from the persisted desired set, which is
        the engine's cross-session wish store; the controller only enforces
        the lifecycle around it.
        """
        entry = self._entry(identifier, "script")
        if entry.get("async") is not True or self.async_policy is None:
            raise NativeRuntimeError("Entry %d has no async lifecycle" % identifier)
        state = self.async_policy.query(identifier + 1)
        state["saved_wish"] = identifier in self.desired
        return state

    def parent_query(self, identifier: int) -> dict:
        """Controller state for one parent-activation record (active, hold,
        saved wish).

        The saved wish is reported from the persisted desired set, which is
        the engine's cross-session wish store; the controller only enforces
        the lifecycle around it.
        """
        entry = self._entry(identifier, "heading")
        if (entry.get("parent_activation") is None
                and entry.get("parent_mo_bind") is not True
                or self.parent_policy is None):
            raise NativeRuntimeError("Entry %d has no parent-activation lifecycle" % identifier)
        state = self.parent_policy.query(identifier + 1)
        state["saved_wish"] = identifier in self.desired
        return state

    def _parent_effect_live(self, identifier: int) -> bool:
        """True while the engine still owns a verifiable effect for a record.

        Byte-patch, program, Lua and global-lease effects all live in the
        engine's own registries; one-shot effects are deliberately excluded
        because their persistence is owned by the one-shot contract, not by
        the parent cascade.
        """
        return (identifier in self.applied
                or identifier in self.lua_activations
                or identifier in self.hooks
                or identifier in self.global_leases)

    def _dynamic_targets_of(self, identifier: int) -> list[int]:
        """WP-50 (GC-E8): plan targets this record serves as symbol-null
        provider (re-derived from the entries' own markers, bounded)."""
        return [entry["id"] for entry in self.entries.values()
                if isinstance(entry.get("address_provider"), dict)
                and entry["address_provider"].get("symbol") is None
                and entry["address_provider"].get("provider_id") == identifier]

    def set_dynamic_address(self, identifier: int, value: int | None, *,
                            scope: int | None = None) -> None:
        """WP-50 (GC-E8): record-Lua live-base write into a plan target.

        Only the plan-named provider scope may write the target it serves
        (the symbol-null marker's contract, re-checked against the plan at
        every call, so a forged runtime write is refused by name).  ``None``
        clears the live base; an integer must stay inside the target memory
        range.  The write is effect-free beyond the live-base registry.

        RT-4.3 (O9/O1): a planned ``runtime_base_target`` heading (the anchor
        of a staged relative value) accepts the write from any supported
        addressless script record of the plan — the table's own
        base-finding scripts — with the same per-call plan re-check.
        """
        if type(identifier) is not int or identifier not in self.entries:
            raise NativeRuntimeError("Dynamic address target is not a plan record.")
        if value is not None:
            if type(value) is not int:
                raise NativeRuntimeError("Dynamic address must be an integer in address range.")
            if self.memory is not None:
                try:
                    self.memory._range(value, 1)
                except Exception as exc:
                    raise NativeRuntimeError(
                        "Dynamic address must be an integer in address range.") from exc
        target = self.entries[identifier]
        if target.get("runtime_base_target") is True:
            # RT-4.3 (O9/O1): planned runtime-base anchor for a staged
            # relative value.  The live group base is written by the
            # table's own supported addressless scripts (the base-finding
            # scripts of the group); the writer is re-checked against the
            # plan at every call, mirroring the marker contract above.
            writer = self.entries.get(scope) if type(scope) is int else None
            if (writer is None or not writer.get("supported")
                    or writer.get("kind") != "script" or writer.get("address")
                    or writer.get("pointer_offsets")):
                raise NativeRuntimeError(
                    "Runtime-base anchor write outside the planned provider contract.")
        else:
            marker = target.get("address_provider")
            if (not isinstance(marker, dict) or marker.get("symbol") is not None
                    or type(marker.get("provider_id")) is not int
                    or scope != marker.get("provider_id")):
                raise NativeRuntimeError("Dynamic address write outside the planned provider contract.")
        if value is None:
            self.dynamic_addresses.pop(identifier, None)
            return
        self.dynamic_addresses[identifier] = value

    def _mirror_parent_state(self, *identifiers: int) -> None:
        """Mirror engine-side effect and wish state into the parent-policy
        controller for the given records.

        The controller's OFF expansion deactivates only explicitly active
        children and its direct-activation ON expansion reads saved wishes;
        both must reflect the engine's live effects and the persisted
        desired set, whether a child was driven through the cascade or
        through its own toggle.  Records outside the topology are no-ops
        (they have no parent relation to mirror).  Headings and values carry
        no engine-side effect, so they are never mirrored: their active
        state is owned by the controller (set symmetrically by
        confirm_success/fail_*), and mirroring a missing engine effect
        would overwrite a confirmed cascade state.
        """
        if self.parent_policy is None:
            return
        for identifier in identifiers:
            entry = self.entries.get(identifier)
            if entry is None or entry["kind"] in {"heading", "value"}:
                continue
            try:
                self.parent_policy.mirror_effect(identifier + 1,
                                                self._parent_effect_live(identifier))
                self.parent_policy.mirror_wish(identifier + 1,
                                               identifier in self.desired)
            except ActivationPolicyError:
                continue

    # ------------------------------------------------- RT-5 item C2: runtime
    # dynamic addresslist records (createMemoryRecord, table-Lua scope).
    #
    # Journal entries are FRESH dicts that live in self.entries only, so the
    # generic record surface (addresslist.Count / .at / record.get) sees
    # them; they are never part of the compiled plan, never persisted (the
    # state store refuses the synthetic IDs) and the whole journal is
    # cleared on target exit and close.  Script records run through the
    # ordinary AA publication path with persist=False; value and heading
    # records are display-only journal state (bounded deviation from CE,
    # which publishes the last UI-edited value on toggle; the clean-room
    # trainer has no value UI for runtime records).

    def _clear_dynamic_records(self) -> None:
        """Drop the session journal (target exit, close, re-attach)."""
        for identifier in list(self.dynamic_records):
            self.entries.pop(identifier, None)
        self.dynamic_records.clear()
        self._dynamic_next_id = 0
        # RT-5 item C2: the runtime-registered plan-record callbacks and
        # display mutations die with the session too (their registering
        # scopes retire with the target).
        self.record_callbacks.clear()
        self.record_display_meta.clear()

    def _dynamic_record_kind(self, entry: dict) -> str:
        """Re-derive the journal kind after a Type/Script/marker change."""
        if entry["is_group_header"]:
            return "heading"
        if entry["variable_type"] == 11:
            return "script"
        return "value"

    def dynamic_record_create(self) -> int:
        """createMemoryRecord: append one vtDword journal entry, return ID."""
        self._guard()
        self._check_patches()
        if len(self.dynamic_records) >= MAX_DYNAMIC_RECORDS:
            raise NativeRuntimeError("Dynamic record journal is at its bound")
        self._dynamic_next_id += 1
        identifier = _DYNAMIC_RECORD_ID_BASE + self._dynamic_next_id
        entry = {
            "id": identifier,
            "label": "",
            "kind": "value",
            "selected": True,
            "supported": True,
            "parent_id": None,
            "variable_type": 2,
            "address": 0,
            "script": None,
            "show_as_hex": False,
            "show_as_signed": False,
            "dont_save": False,
            "collapsed": False,
            "is_group_header": False,
            "options": "",
            "offset_count": 0,
            "offsets": {},
            "offset_texts": {},
            "inert": {},
            "on_activate": None,
            "on_deactivate": None,
            "enable": [],
            "disable": [],
            "provides": [],
            "requires": [],
            "dynamic": True,
        }
        self.entries[identifier] = entry
        self.dynamic_records[identifier] = entry
        self.debug_log.log("dynamic-record-create", identifier=identifier)
        return identifier

    def dynamic_record_set(self, identifier: int, key: Any, value: Any, *,
                           scope: int | None = None) -> Any:
        """record.set on a journal entry (CE MemoryRecord property contract)."""
        self._guard()
        self._check_patches()
        if identifier not in self.dynamic_records:
            raise NativeRuntimeError("Dynamic record is not live: " + str(identifier))
        entry = self.entries[identifier]
        if type(key) is not str or not key:
            raise NativeRuntimeError("Unsupported MemoryRecord mutation: " + str(key))
        normalized = key.casefold()
        if normalized == "description":
            if type(value) is not str:
                raise NativeRuntimeError("Dynamic record Description requires text")
            entry["label"] = value
            return None
        if normalized == "type":
            if type(value) is not int or isinstance(value, bool) or not 0 <= value <= 15:
                raise NativeRuntimeError("Dynamic record Type requires an integer 0..15")
            entry["variable_type"] = value
            entry["kind"] = self._dynamic_record_kind(entry)
            return None
        if normalized == "address":
            if type(value) is int and not isinstance(value, bool):
                if value < 0:
                    raise NativeRuntimeError(
                        "Dynamic record Address must be an integer in address range.")
                try:
                    self.memory._range(value, 1)
                except ValueError:
                    raise NativeRuntimeError(
                        "Dynamic record Address must be an integer in address range.")
                entry["address"] = value
            elif type(value) is str and value.strip():
                # Unresolvable expression text (corpus '+%X' shape) is stored
                # verbatim and re-resolved at read/write time.
                from .address_expression import (AddressExpressionError,
                                                 resolve_expression)
                try:
                    resolved = resolve_expression(value, self.memory, self.symbols,
                                                  process_name=self.plan["process_name"],
                                                  pointer_size=self.memory.pointer_size)
                except AddressExpressionError:
                    entry["address"] = value
                else:
                    try:
                        self.memory._range(resolved, 1)
                    except ValueError:
                        raise NativeRuntimeError(
                            "Dynamic record Address must be an integer in address range.")
                    entry["address"] = resolved
            else:
                raise NativeRuntimeError(
                    "Dynamic record Address must be an integer in address range.")
            return None
        if normalized == "script":
            if type(value) is not str or not value:
                raise NativeRuntimeError("Dynamic record Script requires non-empty text")
            entry["script"] = value
            entry["variable_type"] = 11
            entry["kind"] = "script"
            return None
        if normalized in {"showashex", "dontsave", "collapsed", "isgroupheader"}:
            if type(value) is not bool:
                raise NativeRuntimeError("Dynamic record " + key + " requires a boolean")
            if normalized == "showashex":
                entry["show_as_hex"] = value
            elif normalized == "dontsave":
                entry["dont_save"] = value
            elif normalized == "collapsed":
                entry["collapsed"] = value
            else:
                entry["is_group_header"] = value
                entry["kind"] = self._dynamic_record_kind(entry)
            return None
        if normalized == "options":
            if type(value) is not str:
                raise NativeRuntimeError("Dynamic record Options requires text")
            entry["options"] = value
            return None
        if normalized == "parent":
            return self.dynamic_record_reparent(identifier, value)
        if normalized == "active":
            if type(value) is not bool:
                raise NativeRuntimeError("Dynamic record Active requires a boolean")
            return self.dynamic_record_active(identifier, value, scope=scope)
        if normalized == "offsetcount":
            if type(value) is not int or isinstance(value, bool) or not 0 <= value <= 1024:
                raise NativeRuntimeError(
                    "Dynamic record OffsetCount requires an integer 0..1024")
            entry["offset_count"] = value
            for index in [i for i in entry["offsets"] if i >= value]:
                del entry["offsets"][index]
            for index in [i for i in entry["offset_texts"] if i >= value]:
                del entry["offset_texts"][index]
            return None
        if normalized in {"onactivate", "ondeactivate"}:
            field = "on_activate" if normalized == "onactivate" else "on_deactivate"
            return self._dynamic_callback_set(entry, field, value, scope)
        if normalized == "id":
            raise NativeRuntimeError("Dynamic record ID is engine-owned.")
        if normalized == "index":
            raise NativeRuntimeError("Unsupported MemoryRecord mutation: Index")
        if normalized == "value":
            return self.dynamic_value_write(identifier, value)
        if normalized in _DYNAMIC_INERT_KEYS:
            entry["inert"][normalized] = value
            return None
        raise NativeRuntimeError("Unsupported MemoryRecord mutation: " + str(key))

    def dynamic_record_active(self, identifier: int, active: bool, *,
                              scope: int | None = None) -> None:
        """Active on/off for a journal entry (the corpus enable switch).

        Script entries run the ordinary AA publication path (persist=False);
        value/heading entries flip the journal flag only.  The OnActivate /
        OnDeactivate callbacks fire on the real transition only.
        """
        self._guard()
        self._check_patches()
        if identifier not in self.dynamic_records:
            raise NativeRuntimeError("Dynamic record is not live: " + str(identifier))
        entry = self.entries[identifier]
        if bool(entry.get("active", False)) == active:
            return
        if active:
            if entry["kind"] == "script":
                if identifier not in self.applied:
                    registry = self._aa_command_registry()
                    bitness = self.memory.pointer_size * 8
                    from .aa_program import ProgramError, prepare_program
                    try:
                        prepare_program(entry["script"], self.plan["process_name"],
                                        bitness=bitness, custom_commands=registry,
                                        syntaxcheck=True)
                        program = prepare_program(entry["script"], self.plan["process_name"],
                                                  bitness=bitness, custom_commands=registry,
                                                  syntaxcheck=False)
                    except ProgramError as exc:
                        raise NativeRuntimeError(
                            "Dynamic AA record script refused: " + str(exc)) from exc
                    entry["program"] = program
                    try:
                        self._enable_program(entry, persist=False,
                                             custom_commands=registry)
                    except Exception:
                        entry.pop("program", None)
                        raise
            entry["active"] = True
            self._fire_dynamic_callback(entry, "on_activate", False, True)
        else:
            self._fire_dynamic_callback(entry, "on_deactivate", True, False)
            if identifier in self.applied:
                self._disable(entry, persist=False, run_lua_disable=False)
            entry["active"] = False

    def dynamic_record_delete(self, identifier: int) -> None:
        self._guard()
        self._check_patches()
        if identifier not in self.dynamic_records:
            raise NativeRuntimeError("Dynamic record is not live: " + str(identifier))
        entry = self.entries[identifier]
        # RT-5 item C2 (CE delete contract, brief #5): deleting an active
        # record runs the disable phase first, so the AA restore / symbol
        # release happens before the journal row drops.  The delete itself
        # does not fire the OnDeactivate callback (CE delete is not a
        # deactivate); the journal callback fires from dynamic_record_active
        # only.
        if identifier in self.applied or identifier in self.frozen:
            self._disable(entry, persist=False, run_lua_disable=False)
        grandparent = entry["parent_id"]
        for other in self.entries.values():
            if other.get("parent_id") == identifier:
                other["parent_id"] = grandparent
        del self.entries[identifier]
        del self.dynamic_records[identifier]
        self.debug_log.log("dynamic-record-delete", identifier=identifier)

    def dynamic_record_reparent(self, identifier: int, new_parent: Any) -> None:
        self._guard()
        self._check_patches()
        if identifier not in self.dynamic_records:
            raise NativeRuntimeError("Dynamic record is not live: " + str(identifier))
        if new_parent is None:
            self.entries[identifier]["parent_id"] = None
            return
        if type(new_parent) is not int or isinstance(new_parent, bool):
            raise NativeRuntimeError("Dynamic record Parent requires a record ID")
        if new_parent == identifier or new_parent not in self.entries:
            raise NativeRuntimeError(
                "Dynamic record Parent is not a live record: " + str(new_parent))
        # Bounded ancestor walk: the new parent may not descend from the
        # record being moved (a cycle would break the sibling walk).
        ancestor = self.entries[new_parent].get("parent_id")
        seen = {identifier}
        while ancestor is not None:
            if ancestor in seen:
                raise NativeRuntimeError("Dynamic record Parent would create a cycle")
            seen.add(ancestor)
            target = self.entries.get(ancestor)
            if target is None:
                break
            ancestor = target.get("parent_id")
        self.entries[identifier]["parent_id"] = new_parent

    def dynamic_record_child(self, identifier: int, index: Any) -> int | None:
        """Child[i] (CE array semantics, 0-based) over the live entries.

        An out-of-range or negative index answers nil (CE parity: the
        corpus guards lookups with 'if rec.Child[i] ~= nil'); the
        'MemoryRecord index is out of bounds' refusal stays bound to
        offset writes.
        """
        if identifier not in self.entries:
            raise NativeRuntimeError("MemoryRecord is not live: " + str(identifier))
        if type(index) is not int or isinstance(index, bool) or index < 0:
            return None
        children = [item["id"] for item in self.entries.values()
                    if item.get("parent_id") == identifier]
        if index >= len(children):
            return None
        return children[index]

    def dynamic_offset_get(self, identifier: int, index: Any, *,
                           text: bool = False) -> Any:
        """Offset[i] / OffsetText[i] read: journal dicts for runtime records,
        the plan pointer_offsets for plan records (out of range answers nil)."""
        entry = self.entries.get(identifier)
        if entry is None:
            raise NativeRuntimeError("MemoryRecord is not live: " + str(identifier))
        if type(index) is not int or isinstance(index, bool) or index < 0:
            raise NativeRuntimeError("MemoryRecord index is out of bounds")
        if identifier in self.dynamic_records:
            store = entry["offset_texts"] if text else entry["offsets"]
            return store.get(index)
        offsets = entry.get("pointer_offsets") or []
        if index >= len(offsets):
            return None
        value = offsets[index]
        if text and type(value) is int:
            return format(value, "X")
        return value

    def dynamic_offset_set(self, identifier: int, index: Any, value: Any, *,
                           text: bool = False) -> None:
        self._guard()
        self._check_patches()
        if identifier not in self.dynamic_records:
            raise NativeRuntimeError(
                "MemoryRecord offset mutation is only supported for runtime records")
        entry = self.entries[identifier]
        if type(index) is not int or isinstance(index, bool) or index < 0:
            raise NativeRuntimeError("MemoryRecord index is out of bounds")
        if index >= entry["offset_count"]:
            raise NativeRuntimeError("MemoryRecord index is out of bounds")
        if text:
            if type(value) is not str:
                raise NativeRuntimeError("Dynamic record OffsetText requires text")
            entry["offset_texts"][index] = value
        else:
            if type(value) is not int or isinstance(value, bool):
                raise NativeRuntimeError("Dynamic record Offset requires an integer")
            entry["offsets"][index] = value
        return None

    def _dynamic_value_address(self, entry: dict, size: int) -> int:
        raw = entry.get("address")
        if type(raw) is int:
            try:
                self.memory._range(raw, size)
            except ValueError:
                raise NativeRuntimeError(
                    "Dynamic record address is outside the target range.")
            return raw
        if type(raw) is str and raw.strip():
            from .address_expression import (AddressExpressionError,
                                             resolve_expression)
            try:
                resolved = resolve_expression(raw, self.memory, self.symbols,
                                              process_name=self.plan["process_name"],
                                              pointer_size=self.memory.pointer_size)
            except AddressExpressionError as exc:
                raise NativeRuntimeError(
                    "Dynamic record address does not resolve: " + raw) from exc
            try:
                self.memory._range(resolved, size)
            except ValueError:
                raise NativeRuntimeError(
                    "Dynamic record address is outside the target range.")
            return resolved
        raise NativeRuntimeError("Dynamic record address does not resolve: " + str(raw))

    def dynamic_value_read(self, identifier: int) -> Any:
        entry = self.entries.get(identifier)
        if entry is None or identifier not in self.dynamic_records:
            raise NativeRuntimeError("MemoryRecord is not live: " + str(identifier))
        code = _DYNAMIC_VALUE_CODES.get(entry["variable_type"])
        if code is None:
            raise NativeRuntimeError(
                "Dynamic record Value requires a numeric value type 0..5")
        self._guard()
        self._check_patches()
        address = self._dynamic_value_address(entry, code[1])
        return struct.unpack("<" + code[0], self.memory.read(address, code[1]))[0]

    def dynamic_value_write(self, identifier: int, value: Any) -> None:
        entry = self.entries.get(identifier)
        if entry is None or identifier not in self.dynamic_records:
            raise NativeRuntimeError("MemoryRecord is not live: " + str(identifier))
        code = _DYNAMIC_VALUE_CODES.get(entry["variable_type"])
        if code is None:
            raise NativeRuntimeError(
                "Dynamic record Value requires a numeric value type 0..5")
        size = code[1]
        if code[0] in "BHIQ":
            if type(value) is not int or not 0 <= value <= (1 << (8 * size)) - 1:
                raise NativeRuntimeError(
                    "Dynamic record Value requires an integer in range")
        else:
            if isinstance(value, bool) or type(value) not in (int, float):
                raise NativeRuntimeError(
                    "Dynamic record Value requires a numeric value")
        self._guard()
        self._check_patches()
        address = self._dynamic_value_address(entry, size)
        packed = struct.pack("<" + code[0], value)
        self._write_transaction(
            [_Patch(address, self.memory.read(address, size), packed)])

    def _dynamic_callback_set(self, entry: dict, field: str, value: Any,
                              scope: int | None) -> None:
        if value is None:
            entry[field] = None
            return None
        if type(value) is not str or _DYNAMIC_FN_TOKEN_RE.fullmatch(value) is None:
            raise NativeRuntimeError(
                "Dynamic record callback must be a registered function token")
        if scope is None:
            if self.table_lua_scope is None:
                raise NativeRuntimeError("Dynamic record callback scope has retired")
        elif scope not in self.lua_activations:
            raise NativeRuntimeError("Dynamic record callback scope has retired")
        entry[field] = (value, scope)
        return None

    def _fire_callback(self, callback, identifier: int, field: str, ante: bool,
                       current: bool) -> None:
        """One OnActivate/OnDeactivate callback, contained: a dead or
        cancelled scope logs a stale event and never kills the session."""
        if callback is None:
            return
        token, scope = callback
        host = None
        if scope is None:
            if self.table_lua_scope is not None:
                host = self.table_lua_scope[0]
        else:
            activation = self.lua_activations.get(scope)
            if activation is not None:
                host = activation.host
        if host is None or getattr(host, "cancelled", False):
            self.debug_log.log("dynamic-callback-stale",
                               identifier=identifier, key=field)
            return
        source = ("return _ct2_fire_dyn_fn(" + _lua_string_literal(token)
                  + ", " + str(identifier) + ", " + ("true" if ante else "false")
                  + ", " + ("true" if current else "false") + ")")
        try:
            result = host.execute(source)
        except Exception:
            self.debug_log.log("dynamic-callback-stale",
                               identifier=identifier, key=field)
            return
        if isinstance(result, str) and result.startswith("error: "):
            self.debug_log.log("dynamic-callback-error",
                               identifier=identifier, key=field, error=result)

    def _fire_dynamic_callback(self, entry: dict, field: str, ante: bool,
                               current: bool) -> None:
        """Journal-record OnActivate/OnDeactivate (dynamic_record_active)."""
        self._fire_callback(entry.get(field), entry["id"], field, ante, current)

    def _fire_plan_record_callback(self, identifier: int, field: str,
                                   ante: bool, current: bool) -> None:
        """Plan-record OnActivate/OnDeactivate (session-registered tokens)."""
        self._fire_callback(self.record_callbacks.get(identifier, {}).get(field),
                            identifier, field, ante, current)

    def _aa_command_registry(self) -> dict[str, Any]:
        """The table-scope custom AA directive registry as callables, or {}."""
        scope = self.table_lua_scope
        if scope is None:
            return {}
        host, broker = scope
        commands = getattr(broker, "aa_commands", None)
        if not isinstance(commands, dict) or not commands:
            return {}
        return {name: self._aa_command_callable(token, host)
                for name, token in commands.items()}

    @staticmethod
    def _aa_command_callable(token: str, host: Any) -> Callable:
        def handler(args: str, syntaxcheck: bool) -> Any:
            source = ("return _ct2_aa_command(" + _lua_string_literal(token)
                      + ", " + _lua_string_literal(args) + ")")
            if syntaxcheck:
                return host.execute_live_check(source)
            return host.execute(source)
        return handler

    def record_callback_set(self, identifier: int, field: str, value: Any,
                            scope: int | None = None) -> None:
        """Store a plan-record OnActivate/OnDeactivate function token.

        ``scope`` is None for the table-Lua host, an int for the owning
        record scope (resolved against ``lua_activations`` at fire time).
        ``value is None`` clears the callback.
        """
        self._guard()
        if field not in ("on_activate", "on_deactivate"):
            raise NativeRuntimeError(
                "Unsupported MemoryRecord callback field: " + str(field))
        if identifier in self.dynamic_records:
            raise NativeRuntimeError(
                "Dynamic record callbacks are set through the record surface")
        entry = self.entries.get(identifier)
        if entry is None:
            raise NativeRuntimeError("MemoryRecord is not live: " + str(identifier))
        if value is None:
            self.record_callbacks.get(identifier, {}).pop(field, None)
            return None
        if type(value) is not str or _DYNAMIC_FN_TOKEN_RE.fullmatch(value) is None:
            raise NativeRuntimeError(
                "MemoryRecord callback must be a registered function token")
        if scope is None:
            if self.table_lua_scope is None:
                raise NativeRuntimeError("MemoryRecord callback scope has retired")
        elif scope not in self.lua_activations:
            raise NativeRuntimeError("MemoryRecord callback scope has retired")
        self.record_callbacks.setdefault(identifier, {})[field] = (value, scope)
        return None

    def record_display_set(self, identifier: int, key: str, value: Any) -> None:
        """Store a plan-record display mutation (CE UI metadata) verbatim.

        Plan records are compiled at plan time; these keys (Color, Options,
        ShowAsHex, DontSave, Collapsed, isGroupHeader and the dotted
        DropDownList/Aob display fields) mutate no target state, so the
        session records the value for later reads without touching the plan.
        """
        self._guard()
        normalized = key.casefold() if type(key) is str else ""
        if normalized not in _PLAN_DISPLAY_KEYS:
            raise NativeRuntimeError("Unsupported MemoryRecord mutation: " + str(key))
        if identifier in self.dynamic_records:
            raise NativeRuntimeError(
                "Dynamic record display keys are set through the record surface")
        if identifier not in self.entries:
            raise NativeRuntimeError("MemoryRecord is not live: " + str(identifier))
        self.record_display_meta.setdefault(identifier, {})[normalized] = value
        return None

    def record_display_get(self, identifier: int, key: str) -> Any:
        """Read back a record display field (session value, else default)."""
        self._guard()
        normalized = key.casefold() if type(key) is str else ""
        if normalized not in _PLAN_DISPLAY_KEYS:
            raise NativeRuntimeError("Unsupported MemoryRecord property: " + str(key))
        entry = self.entries.get(identifier)
        if entry is None:
            raise NativeRuntimeError("MemoryRecord is not live: " + str(identifier))
        if identifier in self.dynamic_records:
            if normalized == "showashex":
                return entry["show_as_hex"]
            if normalized == "dontsave":
                return entry["dont_save"]
            if normalized == "collapsed":
                return entry["collapsed"]
            if normalized == "isgroupheader":
                return entry["is_group_header"]
            if normalized == "options":
                return entry["options"]
            return entry.get("inert", {}).get(normalized)
        stored = self.record_display_meta.get(identifier, {}).get(normalized)
        if stored is not None:
            return stored
        if normalized == "showashex":
            return entry["show_as_hex"]
        if normalized == "isgroupheader":
            return entry["kind"] == "heading"
        return None

    def _enable_parent(self, entry: dict, persist: bool = True) -> None:
        """Parent-heading ON through the parent-policy ActivationController.

        The controller expands the cascade from the compiler-derived
        relations (flag class, mirrored wishes, mirrored live effects) and
        gates ownership, safety holds and the named moBindActivation
        refusal.  The engine executes every effect through the ordinary
        per-record path with persistence disabled, so a confirmed ON saves
        only the requested heading's wish (save boundary).  Effect-less
        children (headings, values) are skipped; one-shot children run
        through their contract path but keep contract-owned wishes.
        """
        identifier = entry["id"]
        record_id = identifier + 1
        if self.parent_policy is None:
            raise NativeRuntimeError("Parent activation policy is unavailable")
        try:
            request_id = self.parent_policy.request(record_id, "activate")
            self.parent_policy.dispatch(request_id)
            self.parent_policy.publish(request_id)
            generation = self.parent_policy.request_generation(request_id)
            effects = self.parent_policy.effects(request_id)
        except ActivationPolicyError as exc:
            raise NativeRuntimeError(str(exc)) from exc
        effect_ids = [effect - 1 for effect in effects]
        live_before = {child for child in effect_ids
                       if child != identifier and self._parent_effect_live(child)}
        try:
            self._guard()
            self._check_patches()
            # WP-14 (C2): a script parent's own effect (symbol provider,
            # AOB patch, ...) must land before the cascade, because the
            # children resolve their addresses through the parent's symbols.
            # The controller already lists the parent in its effects and the
            # failure classification below covers it via _parent_effect_live.
            if entry["kind"] == "script" and not self._parent_effect_live(identifier):
                self._dependencies(entry, persist=False)
                self._enable_dispatch(entry, persist=False)
            for child in effect_ids:
                if child == identifier:
                    continue
                child_entry = self.entries.get(child)
                if child_entry is None or child_entry["kind"] in {"heading", "value"}:
                    continue
                self._dependencies(child_entry, persist=False)
                self._enable(child_entry, persist=False)
        except Exception:
            landed = {child for child in effect_ids
                      if child not in live_before and self._parent_effect_live(child)}
            if landed:
                self.parent_policy.fail_after_effect(request_id)
            else:
                self.parent_policy.fail_before_effect(request_id)
            raise
        self.parent_policy.confirm_success(request_id, generation)
        # Save boundary: only the requested heading's wish persists; cascade
        # children keep (or lack) their own wishes.
        if persist:
            self._save(self.desired | {identifier})
        self._mirror_parent_state(identifier)

    def _disable_parent(self, entry: dict, persist: bool = True, *, run_lua_disable: bool = True) -> None:
        """Parent-heading OFF through the parent-policy ActivationController.

        The controller expands the active cascade bottom-up (explicitly
        active required descendants and direct/collective-off children,
        mirrored from the engine's live effects).  The engine restores each
        active child through the ordinary per-record path with persistence
        disabled; a confirmed OFF then clears the wishes of every
        deactivated child plus the requested heading (save boundary).
        Effect-less children (headings, values) and one-shot children (their
        wish lifecycle stays with the one-shot contract) are skipped.

        WP-14 (C1/C2) extends this to script parents: freeze is released on
        every staged value descendant whose provider sits in the cascade
        before any provider effect is torn down, and the script parent's
        own effect (the symbol provider) is disabled last, bottom-up.
        """
        identifier = entry["id"]
        record_id = identifier + 1
        if self.parent_policy is None:
            raise NativeRuntimeError("Parent activation policy is unavailable")
        try:
            request_id = self.parent_policy.request(record_id, "deactivate")
            self.parent_policy.dispatch(request_id)
            self.parent_policy.publish(request_id)
            generation = self.parent_policy.request_generation(request_id)
            effects = self.parent_policy.effects(request_id)
        except ActivationPolicyError as exc:
            raise NativeRuntimeError(str(exc)) from exc
        deactivated = []
        try:
            self._guard()
            self._check_patches()
            # WP-14 (C1/C2): staged value descendants lose their provider's
            # symbols once this cascade deactivates the provider.  Release
            # every such freeze visibly before any provider effect is torn
            # down, so the bottom-up disables see no frozen dependents.
            cascade = {effect - 1 for effect in effects} | {identifier}
            for frozen_id in list(self.frozen):
                staged = (self.entries.get(frozen_id) or {}).get("staged")
                if staged is not None and set(staged["provider_ids"]) & cascade:
                    self.frozen.pop(frozen_id, None)
            for effect in effects:
                child = effect - 1
                if child == identifier:
                    continue
                child_entry = self.entries.get(child)
                if child_entry is None or child_entry["kind"] in {"heading", "value"}:
                    continue
                if child_entry.get("one_shot"):
                    continue
                self._disable(child_entry, persist=False)
                deactivated.append(child)
            # WP-14 (C2): a script parent's own effect (the symbol provider)
            # is torn down last, bottom-up, after every cascade child was
            # restored through the ordinary per-record path.
            if entry["kind"] == "script" and self._parent_effect_live(identifier):
                self._disable_non_one_shot(entry, persist=False,
                                           run_lua_disable=run_lua_disable)
        except Exception:
            self.parent_policy.fail_after_effect(request_id)
            raise
        self.parent_policy.confirm_success(request_id, generation)
        if persist:
            self._save(self.desired - set(deactivated) - {identifier})
        self._mirror_parent_state(identifier, *deactivated)

    def _global_controller_guard(self):
        self.store.guard()
        if self.closed or self.blocked or self.memory is None or self.store.session_bytes is None:
            raise StateError('Shared-global target/controller session is not live')
        require_target_architecture(self.plan,self.memory)
        return True

    def _global_external_symbols(self):
        return {name:address for name,address in self.symbols.items()
                if self._global_aliases.get(name)!=address}

    def _refresh_global_symbols(self):
        for name in self._global_aliases: self.symbols.pop(name,None)
        self._global_aliases=self.global_pool.symbols() if self.global_pool is not None else {}
        self.symbols.update(self._global_aliases)

    @restoration_entry
    def _enable_global_program(self,entry,persist):
        from .global_alloc import GlobalPool,GlobalUncertain,GlobalScanCapture
        profile=entry['global_program']
        if profile['bitness']!=self.memory.pointer_size*8:
            raise NativeRuntimeError('Global source differs from the exact target architecture')
        if self.hook_coordinator is None and profile['consumer_shape']['requires_coordinator']:
            raise NativeRuntimeError('Global code consumer requires a verified coordinator before allocation')
        capture,resolved=GlobalScanCapture.prepare(profile,self.memory,self.symbols,self._global_controller_guard)
        existing=self.global_pool.members if self.global_pool is not None else {}
        new=[x for x in profile['globals'] if x['name'].casefold() not in existing]
        sizes=[((x['size']+65535)//65536)*65536 for x in new+resolved['allocation_requests']]
        if self._hook_lifetime_count+len(sizes)>128 or self._hook_lifetime_bytes+sum(sizes)>16*1024*1024:
            raise NativeRuntimeError('Shared globals and consumer exceed the complete target-lifetime allocation budget before pool claim')
        if self.global_pool is None:
            try:
                self.global_pool=GlobalPool(self.memory,self.store.directory/'hooks',trainer_id=self.plan['trainer_id'],
                                           table_sha256=self.plan['table_sha256'],controller_guard=self._global_controller_guard,
                                           external_symbols=self._global_external_symbols)
            except Exception as exc:
                # A constructor may have durably claimed its journal before a
                # local IO failure. Never retry through a raw file/JSON claim.
                self._block(StateError('Shared-global pool claim is uncertain: '+str(exc)))
                raise NativeRuntimeError(str(exc)) from exc
        pool=self.global_pool
        lease=None
        try:
            before=set(pool.members)
            lease=pool.acquire(profile,record_id=entry['id'],activation=uuid.uuid4().hex,symbols=resolved['symbols'])
            self.global_leases[entry['id']]=lease  # retained even if later publication is uncertain
            for name in set(pool.members)-before:
                allocation=next(iter(pool.members[name]['manager'].allocations.values()))
                self._hook_lifetime_count+=1
                self._hook_lifetime_bytes+=allocation['budget_size']
            # Staged ENABLE readmem copies must read the original target bytes
            # before the consumer install publishes the patch over them; the
            # AOB symbol addresses are already known from the scan capture.
            self._run_staged_readmem(entry,lease,capture=capture,phase='enable',scan_symbols=resolved['symbols'])
            if profile.get('consumer_empty'):
                # RT-4.5 (O19): the pool acquisition itself is the entire
                # activation; the canonical empty consumer is confirmed
                # against its binding without the AA install path, whose
                # no-content refusal is exactly why the empty shape exists.
                program=pool.binding(lease)
                capture.bind(profile,program)
                pool.confirm_enabled(lease,program)
                self.applied[entry['id']]=[]
                self.local_symbols[entry['id']]={}
                exports={}
            else:
                program=pool.binding(lease)
                scan_memory=capture.bind(profile,program)
                def factory(path,**kwargs):
                    return pool.make_consumer(lease,path,coordinator=kwargs.pop('coordinator'),**kwargs)
                manager,linked,live=self._install_program(program,entry['id'],manager_factory=factory,
                                                        scan_memory=scan_memory,publication_guard=capture.recheck,
                                                        api_exports=entry.get("api_exports"),
                                                        staged_restore=tuple(self._staged_copy_ranges(entry,'disable',scan_symbols=resolved['symbols'])))
                pool.confirm_enabled(lease,program)
                self.hooks[entry['id']]=manager
                self.applied[entry['id']]=[_Patch(b['address'],bytes.fromhex(b['original']),bytes.fromhex(b['bytes'])) for b in live]
                self.local_symbols[entry['id']]=linked['symbols']
                exports={k.casefold():v for k,v in linked['exports'].items()}
            # RT-4.1: globalalloc names are pool-managed (their
            # self.symbols entries are the aliases refreshed from the pool
            # on every change), but they are claimed in keep-first order
            # like any other registration so the disable dependency
            # checks and the released set match the other enable paths;
            # the alias survives other active leases via _refresh_global
            # _symbols after the lease release below.
            globals_names={g['name'].casefold() for g in profile['globals']}
            owned=self._owned_symbols(entry['id'],set(exports)|globals_names)
            self.symbols.update({k:exports[k] for k in owned if k in exports})
            self.registered_by[entry['id']]=owned
            self._refresh_global_symbols()
            if persist:self._save(self.desired|{entry['id']})
        except Exception as exc:
            if lease is not None and lease._manager is not None and lease._manager.state != 'abandoned':
                # Publication may have succeeded before final pool/save receipt
                # failure. Preserve the actual object as well as its lease.
                manager=lease._manager
                if manager not in self.retired_hooks and manager not in self.hooks.values():
                    self.retired_hooks.append(manager)
            if pool.state=='uncertain' or isinstance(exc,GlobalUncertain) or self.blocked:
                self._block(StateError('Shared-global activation is uncertain: '+str(exc)))
            elif lease is not None:
                try:
                    pool.release(lease)
                    self.global_leases.pop(entry['id'],None)
                except Exception as undo:
                    self._block(StateError('Shared-global consumer release is uncertain: '+str(exc)+'; '+str(undo)))
            raise NativeRuntimeError(str(exc)) from exc

    def _staged_copy_ranges(self, entry, phase, scan_symbols=None):
        """Resolve the concrete (address, size) of each staged readmem of one phase.

        ENABLE reads the original target bytes before the consumer install
        overwrites them; DISABLE writes them back. The scan-capture symbols
        stand in for scan addresses until the install refreshes the engine map;
        diagnostic alias addresses can never shadow live global names.
        """
        from .address_expression import resolve_expression
        profile = entry.get('global_program') or {}
        global_names = {x['name'].casefold() for x in profile.get('globals', ())}
        symbols = dict(self.symbols)
        if scan_symbols:
            for name, address in scan_symbols.items():
                if name not in global_names:
                    symbols[name] = address
        ranges = []
        for op in profile.get('staged_ops', ()):
            if op.get('phase') != phase:
                continue
            address = resolve_expression(op['address'], self.memory, symbols,
                                         process_name=self.plan['process_name'],
                                         pointer_size=self.memory.pointer_size)
            if type(address) is not int or not 0 <= address < (1 << (self.memory.pointer_size * 8)):
                raise NativeRuntimeError('Staged global readmem address is outside the target width: ' + op['address'])
            ranges.append((address, int(op['size'])))
        return ranges

    def _run_staged_readmem(self, entry, lease, *, capture=None, phase, scan_symbols=None):
        """Execute the staged readmem copies for one phase of a global program.

        ENABLE ops copy the original target bytes into the live global
        allocation before the consumer install overwrites them; DISABLE ops
        copy the live global bytes back to the target after the consumer patch
        is restored. Every access runs under the pool guard; ENABLE
        ops additionally under the original scan capture identity recheck.
        """
        profile = entry.get('global_program') or {}
        staged = [op for op in profile.get('staged_ops', ()) if op.get('phase') == phase]
        if not staged:
            return
        memory = self.memory
        for op, (address, size) in zip(staged, self._staged_copy_ranges(entry, phase, scan_symbols)):
            if capture is not None:
                capture.recheck()
            if op['direction'] == 'target_to_global':
                data = memory.read(address, size)
                if len(data) != size:
                    raise NativeRuntimeError('Staged global readmem returned incomplete target bytes')
                if capture is not None:
                    capture.recheck()
                self.global_pool.staged_write(lease, op['global'], data)
            elif op['direction'] == 'global_to_target':
                data = self.global_pool.staged_read(lease, op['global'], size)
                memory.write(address, data)
                if memory.read(address, len(data)) != data:
                    raise NativeRuntimeError('Staged global readmem write did not verify at its target address')
            else:
                raise NativeRuntimeError('Staged global readmem direction is not supported at runtime: ' + str(op['direction']))
        if capture is not None:
            capture.recheck()

    @restoration_entry
    def _require_luacall_binding(self, entry: dict) -> None:
        """Gate records with luaCall references behind an explicit binding.

        The compiler embeds a static luaCall plan (lua_call_plan) into pure-AA
        records whose envelope contains luaCall lines. Before the record's Lua
        may run, the engine must prove that an injected binding covers every
        referenced Lua function and that AOB references have an AOB port.
        Without a luacall_binding_factory the record is refused visibly; the
        owned runtime route for such bindings is still open (AP-11), so the
        default stays fail-closed like the clock and call-broker bindings.
        """
        report = entry.get('lua_call_plan')
        if report is None:
            return
        from .aa_luacall import LuaCallError, plan_from_report, validate_luacall_binding
        try:
            plan = plan_from_report(report)
        except LuaCallError as exc:
            raise NativeRuntimeError(str(exc)) from exc
        if self.luacall_binding_factory is None:
            raise NativeRuntimeError(
                'This record executes luaCall references, but no luacall '
                'binding factory was provided for this trainer. '
                'No target memory was allocated or changed.')
        binding = self.luacall_binding_factory(self)
        if binding is None:
            raise NativeRuntimeError(
                'The luacall binding factory returned no binding; the record '
                'was not activated. No target memory was allocated or changed.')
        try:
            validate_luacall_binding(plan, binding)
        except LuaCallError as exc:
            raise NativeRuntimeError(str(exc)) from exc

    def _disassembler_for(self, memory):
        """Create the DisassemblerPort used for disassemble() inspections.

        The default route is the owned iced-x86 backend bound to the given
        memory; an injected disassembler_factory may replace it or refuse by
        returning None (visible fail-closed refusal at preflight, before any
        allocation or write).
        """
        if self.disassembler_factory is not None:
            port = self.disassembler_factory(memory)
        else:
            from .iced_disassembler import IcedDisassemblerPort
            port = IcedDisassemblerPort(memory.read)
        if port is None or not callable(getattr(port, "disassemble", None)):
            return None
        return port

    def _thread_model_for(self, memory):
        """Create the ThreadDirectiveModel for createThread()/threadWait().

        The default route has no owned spawn/poll backend yet, so it refuses
        visibly fail-closed (the engine gate reports the missing binding); an
        injected thread_backend_factory may supply a backend-backed model.
        The owned Windows CreateRemoteThread route is open (AP-11).
        """
        if self.thread_backend_factory is None:
            return None
        model = self.thread_backend_factory(memory)
        if model is None or not callable(getattr(model, "create_thread", None)) \
                or not callable(getattr(model, "thread_wait", None)):
            return None
        return model

    def _protection_model_for(self, memory):
        """Create the ProtectionDirectiveModel for protect()/unprotect().

        The default route has no owned protection backend yet, so it refuses
        visibly fail-closed; an injected protection_backend_factory may supply
        a backend-backed model. The owned Windows VirtualProtect route is open
        (AP-11).
        """
        if self.protection_backend_factory is None:
            return None
        model = self.protection_backend_factory(memory)
        if model is None or not callable(getattr(model, "protect", None)) \
                or not callable(getattr(model, "unprotect", None)):
            return None
        return model

    def _export_model_for(self, memory):
        """Create the TargetApiDirectiveModel for getmodulehandle()/
        getprocaddress().

        The default route is the read-only PE export resolver bound to the
        linked memory itself (bounded read plus module identity lookups); an
        injected export_backend_factory may replace it or refuse by returning
        None (visible fail-closed refusal, before any allocation or write).
        """
        if self.export_backend_factory is not None:
            model = self.export_backend_factory(memory)
        else:
            from .aa_directives import TargetApiDirectiveModel
            model = TargetApiDirectiveModel(memory)
        if model is None or not callable(getattr(model, "getprocaddress", None)) \
                or not callable(getattr(model, "getmodulehandle", None)):
            return None
        return model

    def _enable_lua_program(self, entry: dict, persist: bool) -> None:
        from .lua_activation import LuaActivation
        identifier = entry['id']
        if identifier in self.lua_activations:
            raise NativeRuntimeError('A previous Lua activation still owns this record')
        self._require_luacall_binding(entry)
        scope = LuaActivation(self, identifier)
        self.lua_activations[identifier] = scope
        self.lua_sessions.append((scope.host, scope.broker))
        try:
            scope.start_program(entry['lua_program'])
            self.applied[identifier] = []
            self.local_symbols[identifier] = dict(scope.symbols)
            # RT-4.1: scope-registered symbols are entry-owned, so a later
            # record registering the same name is a keep-first no-op.
            self.registered_by[identifier] = {name.casefold() for name in scope.symbols}
            if persist:
                self._save(self.desired | {identifier})
        except Exception as exc:
            if not self.blocked:
                try:
                    scope.close()
                    self.lua_sessions = [(host, broker) for host, broker in self.lua_sessions if host is not scope.host]
                    del self.lua_activations[identifier]
                    self.applied.pop(identifier, None)
                    self.local_symbols.pop(identifier, None)
                except Exception as undo_error:
                    self._block(StateError('Lua enable failed and compensation is uncertain: ' +
                                           str(exc) + '; ' + str(undo_error)))
            raise NativeRuntimeError(str(exc)) from exc

    def _owned_provider_data(self) -> tuple[list, list]:
        ordinary, executable = [], []
        pool=getattr(self,'global_pool',None)
        if pool is not None:
            ordinary.extend(pool.active_data_ranges())
        for parent in self.hooks.values():
            parent.check_entries()
            for allocation in parent.allocation_map().values():
                if not allocation['executable']:
                    ordinary.append((allocation['address'], allocation['size']))
            executable.extend(parent.data_ranges())
        for scope in self.lua_activations.values():
            for manager in scope.managers():
                manager.check_entries()
                executable.extend(manager.data_ranges())
                for allocation in manager.allocation_map().values():
                    if not allocation['executable']:
                        ordinary.append((allocation['address'], allocation['size']))
        return ordinary, executable

    @restoration_entry
    def _install_program(self, program: dict, owner: int | str, *, publication_guard=None,manager_factory=None,scan_memory=None,staged_restore=(),api_exports=None,custom_commands=None) -> tuple[Any, dict, list]:
        """Shared owned AA publication path for records and Lua child receipts.

        staged_restore carries the concrete (address, size) pairs of staged
        global_to_target copies; those entries are restored by the staged
        readmem at disable time, so the consumer's own disable text must not
        repeat them.

        api_exports is the record entry's RT-4.2 (R7) plan marker: the
        exact export name -> owning module basename mapping of bare API
        call targets that no record, table-Lua or user-symbol provider
        serves.  Each name is resolved against the attached target's live
        PE export table and injected into the per-install symbol overlay
        (a live registered symbol of the same name always wins; an absent
        export fails closed with a named refusal before any target memory
        is touched).  None for non-record installs (Lua child receipts).

        custom_commands is the RT-5 item C2 runtime registry of custom AA
        directives (uppercase name -> callable) the program was prepared
        with; it is forwarded so validate_program regenerates the identical
        plan from the same registry.  None for every plan-record install,
        which keeps the pre-C2 plan shape byte-identical.
        """
        from .aa_program import preflight_program, link_program
        from .hooks import HookManager, HookUncertain
        if self.hook_coordinator is None and (any(program['allocation_executable'].values())
                or any(n['op'] in {'instruction','reassemble'} for n in program['enable'])):
            raise NativeRuntimeError('This executable script requires a verified target thread coordinator. No target memory was allocated or changed.')
        if program['bitness'] != self.memory.pointer_size * 8:
            raise NativeRuntimeError('Assembler program bitness differs from the attached target')
        # Managed method labels (IL2CPP injection labels such as Class:Method)
        # are not module symbols: they resolve through the injected resolver,
        # which carries the live binding proof, and are exposed to the linker
        # as a per-install symbol overlay without polluting the shared map.
        managed = program.get('managed_method_labels', [])
        symbols = self.symbols
        if managed:
            if self.il2cpp_resolver is None:
                raise NativeRuntimeError('Managed method labels require an IL2CPP resolver; no resolver binding was provided for this trainer.')
            symbols = dict(self.symbols)
            for label in managed:
                address = self.il2cpp_resolver(label)
                if type(address) is not int or not 0 <= address <= 0xFFFFFFFFFFFFFFFF:
                    raise NativeRuntimeError(f'IL2CPP resolver returned an invalid address for {label}.')
                if label.casefold() in self.symbols:
                    raise NativeRuntimeError(f'Managed method label {label} conflicts with an active symbol.')
                symbols[label.casefold()] = address
        # RT-4.2 (R7): the plan-level api_exports marker names the bare
        # Windows API export call targets no provider record serves.  Each
        # name resolves against the attached target's live PE export table
        # and joins the per-install symbol overlay so the assembler link
        # finds it.  A live registered symbol of the same name always wins
        # (the shared map is the source of truth for live registrations);
        # an absent export fails closed with a named, actionable refusal
        # before any target memory is allocated or changed.
        if api_exports:
            if symbols is self.symbols:
                symbols = dict(self.symbols)
            for export, module in api_exports.items():
                key = export.casefold()
                if key in symbols:
                    continue
                try:
                    address = self.memory.resolve_export(module, export)
                except Exception as exc:
                    raise NativeRuntimeError(
                        f"Windows API export '{export}' (module {module}) "
                        f"is not resolvable in the attached target process: "
                        f"{exc} The record was not activated; no target "
                        f"memory was changed.") from exc
                if self.debug_log.enabled:
                    self.debug_log.log("api-export", **{"entry_id": owner,
                                                        "export": export,
                                                        "module": module,
                                                        "address": hex(address)})
                symbols[key] = address
        link_memory=self.memory if scan_memory is None else scan_memory
        disassembler = None
        thread_model = None
        protection_model = None
        export_model = None
        capabilities = set(program.get('capabilities', ()))
        if 'disassemble' in capabilities:
            disassembler = self._disassembler_for(link_memory)
            if disassembler is None:
                raise NativeRuntimeError(
                    'This record uses disassemble(), but the disassembler '
                    'binding was not provided for this trainer. The record '
                    'was not activated. No target memory was allocated or '
                    'changed.')
        if {'createthread', 'threadwait'} & capabilities:
            thread_model = self._thread_model_for(link_memory)
            if thread_model is None:
                raise NativeRuntimeError(
                    'This record uses createThread()/threadWait(), but the '
                    'thread binding was not provided for this trainer. The '
                    'record was not activated. No target memory was '
                    'allocated or changed.')
        if {'protect', 'unprotect'} & capabilities:
            protection_model = self._protection_model_for(link_memory)
            if protection_model is None:
                raise NativeRuntimeError(
                    'This record uses protect()/unprotect(), but the '
                    'protection binding was not provided for this trainer. '
                    'The record was not activated. No target memory was '
                    'allocated or changed.')
        if {'getmodulehandle', 'getprocaddress'} & capabilities:
            export_model = self._export_model_for(link_memory)
            if export_model is None:
                raise NativeRuntimeError(
                    'This record uses getmodulehandle()/getprocaddress(), '
                    'but the export binding was not provided for this '
                    'trainer. The record was not activated. No target '
                    'memory was allocated or changed.')
        # Log program (AA script) scans the same way the byte-patch path logs
        # them in _operations, so a stale pattern is diagnosable from the
        # debug log (symbol, module, pattern, address/RVA on success; full
        # traceback on failure).
        def _preflight_scan_log(symbol, module, pattern, *, address=None,
                                error=None, extra=None):
            details = {"entry_id": owner, "symbol": symbol, "pattern": pattern,
                       "section": "program"}
            if module is not None:
                details["module"] = module
            if extra:
                details.update(extra)
            if error is not None:
                self.debug_log.error("scan-failed", error, **details)
                return
            details["address"] = hex(address)
            # Multi-match scans resolve to the lowest address (CE parity):
            # record the full match evidence so a stale pattern with several
            # occurrences is diagnosable from the log.  Single-match scans
            # keep the 0.14 log shape byte-identical.
            diagnostics = getattr(link_memory, "last_scan_diagnostics", None)
            if isinstance(diagnostics, dict) and diagnostics.get("match_count", 0) > 1:
                details["match_count"] = diagnostics["match_count"]
                details["match_offsets"] = [hex(offset) for offset in diagnostics.get("match_addresses", [])]
            if self.debug_log.enabled:
                try:
                    base, size = link_memory.module(module)
                    details["module_base"] = hex(base)
                    details["module_size"] = size
                    details["rva"] = hex(address - base)
                except Exception:
                    pass
            self.debug_log.log("scan", **details)
        preflight = preflight_program(program, link_memory, symbols,
                                      disassembler=disassembler,
                                      thread_model=thread_model,
                                      protection_model=protection_model,
                                      export_model=export_model,
                                      on_scan=_preflight_scan_log,
                                      custom_commands=custom_commands)
        requests = preflight['allocation_requests']
        sizes = [((r['size'] + 65535) // 65536) * 65536 for r in requests]
        if (self._hook_lifetime_count + len(sizes) > 128
                or self._hook_lifetime_bytes + sum(sizes) > 16 * 1024 * 1024):
            raise NativeRuntimeError('The target-lifetime executable allocation budget is exhausted; restart the target')
        # RT-4.1 (CE dupIgnore narrowing): exported symbols that another
        # active record (or table-level seed) already holds are not a
        # publication conflict anymore.  Entry-level keep-first ownership
        # is settled afterwards in _enable_* via _owned_symbols; the
        # duplicate registration becomes a silent no-op there.
        owned_data_ranges, executable_data = self._owned_provider_data()
        captured_scans = tuple(preflight['scan_results'])
        def recheck_scans():
            from .aob_scan import recheck_result
            for result in captured_scans:
                recheck_result(result, self.memory, program['source_sha256'])
            if publication_guard is not None:
                publication_guard()
        manager_path=self.store.directory/'hooks'/(uuid.uuid4().hex+'.json')
        manager = (manager_factory(manager_path,coordinator=self.hook_coordinator,owned_data_ranges=owned_data_ranges,
                                   owned_executable_data_ranges=executable_data,publication_guard=recheck_scans)
                   if manager_factory is not None else HookManager(self.memory, manager_path,
                              self.hook_coordinator, owner_id=self.plan['trainer_id'] + ':' + str(owner),
                              owned_data_ranges=owned_data_ranges, owned_executable_data_ranges=executable_data,
                              publication_guard=recheck_scans))
        try:
            for request in requests:
                manager.allocate(request['name'],request['size'],near=request['near'],
                                 executable=request['executable'],writable=request.get('writable',False))
                self._hook_lifetime_count += 1
                self._hook_lifetime_bytes += manager.allocations[request['name'].casefold()]['budget_size']
            linked = link_program(program,link_memory,symbols,manager.allocation_map(),owned_data_ranges=owned_data_ranges,
                                  owned_executable_data_ranges=executable_data, scan_results=preflight['scan_results'],
                                  disassembler=disassembler, thread_model=thread_model,
                                  protection_model=protection_model, export_model=export_model,
                                  execute_side_effects=False, _allow_external_literals=True,
                                  custom_commands=custom_commands)
            # WP-57: hold the scan-time placeholder captures for the enable
            # lifetime (journal persistence + disable-phase restore input).
            captures_by_entry = getattr(self, 'placeholder_captures', None)
            if captures_by_entry is None:
                self.placeholder_captures = captures_by_entry = {}
            captures_by_entry[owner] = dict(linked['captured_placeholders'])
            live = [b for b in linked['blocks'] if not b['is_allocation']]
            for block in live:
                start,size=block['address'],len(bytes.fromhex(block['bytes']))
                for patches in self.applied.values():
                    if any(start < p.address+len(p.changed) and p.address < start+size for p in patches):
                        raise NativeRuntimeError('An executable hook overlaps another active patch')
                for address,raw in self.frozen.values():
                    if start<address+len(raw) and address<start+size:
                        raise NativeRuntimeError('An executable hook overlaps a frozen value')
                for scope in self.lua_activations.values():
                    if scope.overlaps(start, size):
                        raise NativeRuntimeError('An assembler patch overlaps a Lua-owned mutation')
            allocation_only = bool(program.get('allocation_only')) and all(
                block['is_allocation'] for block in linked['blocks'])
            if allocation_only:
                # Allocation-only plans own no live entry: there is nothing to
                # stage, so the hook-layer nonempty-block guard stays untouched
                # and the manager commits the allocation (protection + journal)
                # and publishes the registered symbols directly.  The disable
                # text is still checked against the owned original entries
                # before publication (trivially [] == [] for a pure
                # allocation-only plan).
                if not program.get('one_shot'):
                    inverse=link_program(program,link_memory,linked['symbols'],manager.allocation_map(),phase='disable',owned_data_ranges=owned_data_ranges,
                                         owned_executable_data_ranges=executable_data, disassembler=disassembler,
                                         thread_model=thread_model, protection_model=protection_model,
                                         export_model=export_model, execute_side_effects=True,
                                         captured_placeholders=linked['captured_placeholders'],
                                         custom_commands=custom_commands)
                    restored=sorted((b['address'],bytes.fromhex(b['bytes'])) for b in inverse['blocks'] if not b['is_allocation'])
                    expected=sorted((b['address'],bytes.fromhex(b['original'])) for b in live)
                    if restored!=expected:
                        raise NativeRuntimeError('Assembler disable must restore the captured original entry bytes')
                manager.commit(linked['exports'], captured_placeholders=linked['captured_placeholders'])
            else:
                manager.stage(linked['blocks'],linked['exports'],
                              captured_placeholders=linked['captured_placeholders'],
                              _external_literal_permits=linked.pop('_external_literal_permits', ()))
                # Disable text is checked against the owned original entries before publication.
                # One-shot programs have no disable phase by contract; their close-time
                # restore is derived from the applied journal instead.
                if not program.get('one_shot'):
                    inverse=link_program(program,link_memory,linked['symbols'],manager.allocation_map(),phase='disable',owned_data_ranges=owned_data_ranges,
                                         owned_executable_data_ranges=executable_data, disassembler=disassembler,
                                         thread_model=thread_model, protection_model=protection_model,
                                         export_model=export_model, execute_side_effects=True,
                                         captured_placeholders=linked['captured_placeholders'],
                                         custom_commands=custom_commands)
                    restored=sorted((b['address'],bytes.fromhex(b['bytes'])) for b in inverse['blocks'] if not b['is_allocation'])
                    expected=sorted((b['address'],bytes.fromhex(b['original'])) for b in live)
                    if staged_restore:
                        # Staged global_to_target copies restore their own live
                        # entries at disable time; the consumer source carries no
                        # db restore for them. Every staged range must match a live
                        # entry exactly, and every such entry is exempt from the
                        # consumer-side restore comparison.
                        staged=set(staged_restore)
                        remaining=[]
                        for address,original in expected:
                            pair=(address,len(original))
                            if pair in staged:
                                staged.discard(pair)
                            else:
                                remaining.append((address,original))
                        expected=sorted(remaining)
                        if staged:
                            raise NativeRuntimeError('Staged global restoration does not cover a live entry: '+', '.join(hex(a) for a,_ in sorted(staged)))
                    if restored!=expected:
                        raise NativeRuntimeError('Assembler disable must restore the captured original entry bytes')
                manager.publish()
            return manager, linked, live
        except Exception as exc:
            if manager.uncertain or isinstance(exc,HookUncertain):
                self._block(StateError('Executable mutation is uncertain: ' + str(exc)))
            elif manager.state not in {'enabled','retired','target-exited','abandoned'}:
                self._abandon_after_failure(manager, exc)
            raise NativeRuntimeError(str(exc)) from exc

    def _disable(self, entry: dict, persist: bool = True, *, run_lua_disable: bool = True) -> None:
        with restoration_region(self._guard,_clock_for(self),emergency=False):
            return self._disable_body(entry,persist,run_lua_disable=run_lua_disable)

    def _disable_body(self, entry: dict, persist: bool = True, *, run_lua_disable: bool = True) -> None:
        identifier = entry["id"]
        # WP-14 (C2): parent routing first, so a flagged script parent tears
        # down its cascade (children bottom-up, then its own provider effect)
        # instead of only its own async effect.
        if (entry.get("parent_activation") is not None
                or entry.get("parent_mo_bind") is True):
            self._disable_parent(entry, persist, run_lua_disable=run_lua_disable)
            return
        if entry["kind"] == "heading":
            # WP-53 (GC-D7): a plain group heading clears its own active
            # state only (no cascade, no effect to restore).
            if identifier in self.applied:
                del self.applied[identifier]
            if persist and identifier in self.desired:
                self._save(self.desired - {identifier})
            self._mirror_parent_state(identifier)
            return
        if entry.get("async") is True and run_lua_disable:
            self._disable_async(entry, persist)
            return
        if entry.get("one_shot") and run_lua_disable:
            # Contract: OFF performs no backend operations; it only clears the
            # saved wish. Ownership of the applied effect is kept so the record
            # stays visible as active until close/exit.
            self._one_shot_off(entry, persist)
            return
        self._disable_non_one_shot(entry, persist, run_lua_disable=run_lua_disable)
        self._mirror_parent_state(identifier)

    def _disable_non_one_shot(self, entry: dict, persist: bool, *, run_lua_disable: bool = True) -> None:
        identifier = entry["id"]
        if entry.get("activation_sets") is not None:
            self._apply_activation_set(entry, False, persist)
            return
        if identifier not in self.applied:
            if persist and identifier in self.desired:
                self._save(self.desired - {identifier})
            return
        self._guard()
        provided = {name.casefold() for name in entry.get("provides", [])}
        if identifier in self.lua_activations:
            provided.update(self.lua_activations[identifier].symbols)
        # RT-4.1 (CE dupIgnore ownership narrowing): only the symbols this
        # entry actually registered are released on disable; a shadowed
        # duplicate keeps the kept provider's binding.  Entries enabled
        # through a path without ownership tracking (record-Lua scopes)
        # fall back to the plan's provides set.  The ownership record is
        # popped with the symbols at the end so a partially failed disable
        # stays retryable with the same released set.
        owned = self.registered_by.get(identifier)
        if owned is None:
            released = provided
        else:
            released = set(owned)
            if identifier in self.lua_activations:
                released.update(self.lua_activations[identifier].symbols)
        dependents = [i for i in self.applied if i != identifier and released.intersection(name.casefold() for name in self.entries[i].get("requires", []))]
        dependents += [i for i in self.frozen if released.intersection(name.casefold() for name in self.entries[i].get("requires", []))]
        if dependents:
            raise NativeRuntimeError("Disable dependent entries first: " + ", ".join(map(str, sorted(set(dependents)))))
        consumers = self._owner_consumers(identifier)
        if consumers:
            raise NativeRuntimeError('Disable dynamic symbol consumers first: ' + ', '.join(consumers))
        # RT-5 item C2: plan-record OnDeactivate (CE MemoryRecord.OnDeactivate)
        # fires once the record is confirmed live-disabling: after the
        # dependent/consumer gates and before the record Lua scope (if any)
        # closes, so the callback can still resolve this record's symbols.
        # Journal records fire their own callbacks from
        # dynamic_record_active/delete; their IDs are absent from
        # record_callbacks, so this is a no-op for them.
        self._fire_plan_record_callback(identifier, "on_deactivate", True, False)
        if identifier in self.lua_activations:
            scope = self.lua_activations[identifier]
            if run_lua_disable:
                scope.stop_program()
            scope.close()
            self.lua_sessions = [(host, broker) for host, broker in self.lua_sessions if host is not scope.host]
            del self.lua_activations[identifier]
        patches = self.applied[identifier]
        one_shot_bytes = bool(entry.get("one_shot")) and 'lua_program' not in entry and identifier not in self.hooks
        if one_shot_bytes:
            # A one-shot effect may have been externally reverted; restore only
            # the ranges still holding the published bytes.
            for patch in patches:
                current = self.memory.read(patch.address, len(patch.changed))
                if current != patch.changed and current != patch.original:
                    raise PatchConflict(f"One-shot patch changed externally at 0x{patch.address:X}; refusing to restore foreign bytes")
        else:
            for patch in patches:
                if self.memory.read(patch.address, len(patch.changed)) != patch.changed:
                    raise PatchConflict("Active patch changed externally; refusing to restore foreign bytes")
        if identifier in self.hooks:
            manager=self.hooks[identifier]
            try:
                manager.disable()
            except Exception as exc:
                if manager.uncertain or manager.state != 'enabled':
                    self._block(StateError('Executable disable is uncertain: '+str(exc)))
                raise NativeRuntimeError(str(exc)) from exc
            self.retired_hooks.append(manager)
            del self.hooks[identifier]
            staged_disable=[op for op in (entry.get('global_program') or {}).get('staged_ops', ())
                            if op.get('phase')=='disable']
            if staged_disable and identifier in self.global_leases:
                # Staged DISABLE readmem copies the live global bytes back to
                # the target after the consumer patch is restored, before the
                # lease is released.
                try:
                    self._run_staged_readmem(entry,self.global_leases[identifier],phase='disable')
                except Exception as exc:
                    self._block(StateError('Staged global readmem restoration failed; the record stays enabled: '+str(exc)))
                    raise NativeRuntimeError(str(exc)) from exc
            if identifier in self.global_leases:
                try:
                    self.global_pool.release(self.global_leases[identifier])
                    del self.global_leases[identifier]
                except Exception as exc:
                    self._block(StateError('Shared-global disable ownership is uncertain: '+str(exc)))
                    raise
            reversal=None
        elif identifier in self.global_leases:
            # RT-4.5 (O19): an empty-consumer global record owns no hook
            # manager; the staged restore plus the pool lease release is the
            # entire disable.
            staged_disable=[op for op in (entry.get('global_program') or {}).get('staged_ops', ())
                            if op.get('phase')=='disable']
            if staged_disable:
                try:
                    self._run_staged_readmem(entry,self.global_leases[identifier],phase='disable')
                except Exception as exc:
                    self._block(StateError('Staged global readmem restoration failed; the record stays enabled: '+str(exc)))
                    raise NativeRuntimeError(str(exc)) from exc
            try:
                self.global_pool.release(self.global_leases[identifier])
                del self.global_leases[identifier]
            except Exception as exc:
                self._block(StateError('Shared-global disable ownership is uncertain: '+str(exc)))
                raise
            reversal=None
        elif one_shot_bytes:
            # No disable phase exists; restore exactly the ranges that still
            # hold the published one-shot bytes.
            reversal = [_Patch(p.address, p.changed, p.original) for p in patches
                        if self.memory.read(p.address, len(p.changed)) == p.changed]
        elif 'lua_program' not in entry:
            _, _, reversal = self._operations(entry, "disable")
        else:
            reversal = None  # The activation scope restored its captured AA/data.
        if reversal is not None and not one_shot_bytes and sorted((p.address, p.original, p.changed) for p in reversal) != sorted((p.address, p.changed, p.original) for p in patches):
            raise PatchConflict("Disable no longer matches the enabled patch")
        if reversal is not None:
            self._write_transaction(reversal)
        del self.applied[identifier]
        self.local_symbols.pop(identifier, None)
        # WP-57: placeholder captures live with the entry.
        self.placeholder_captures.pop(identifier, None)
        for name in released:
            self.symbols.pop(name, None)
        self.registered_by.pop(identifier, None)
        if self.global_pool is not None:
            self._refresh_global_symbols()
        # WP-50 (GC-E8): deactivating the provider retires the live bases
        # it wrote; the target's children now refuse with the provider
        # phrase on every read/write.
        for target_id in self._dynamic_targets_of(identifier):
            self.dynamic_addresses.pop(target_id, None)
        if persist:
            self._save(self.desired - {identifier})

    def _action_kind(self, identifier: int) -> str:
        """Plan action kind for a toggle target.

        Flagged group headings (parent_activation/moBindActivation) route
        through the parent-activation lifecycle; WP-14 extends the lifecycle
        to script parents, which keep their script kind so entry validation
        passes.  Plain group headings (WP-53) route to the heading kind so
        their own-state toggle works without a cascade; every other target
        uses the ordinary script path.
        """
        entry = self.entries.get(identifier)
        if isinstance(entry, dict) and entry.get("kind") == "heading":
            return "heading"
        if isinstance(entry, dict) and (entry.get("parent_activation") is not None
                                        or entry.get("parent_mo_bind") is True):
            if entry.get("parent_activation") is not None and entry["kind"] == "script":
                return "script"
        return "script"

    def _toggle_direction(self, entry: dict) -> bool:
        """Direction for a directionless toggle request.

        Flagged group headings keep their own active state in the
        parent-activation controller, never in ``self.applied``; every
        other toggle target (scripts, plain headings - WP-53) derives the
        direction from the applied set.
        """
        if (entry.get("parent_activation") is not None
                or entry.get("parent_mo_bind") is True) \
                and entry["kind"] == "heading":
            if self.parent_policy is None:
                raise NativeRuntimeError("Parent activation policy is unavailable")
            return not self.parent_policy.query(entry["id"] + 1)["active"]
        return entry["id"] not in self.applied

    @restoration_entry
    def toggle(self, identifier: int, enabled: bool | None = None) -> bool:
        if self.busy:
            raise NativeRuntimeError("Another trainer action is in progress")
        entry = self._entry(identifier, self._action_kind(identifier))
        enabled = self._toggle_direction(entry) if enabled is None else bool(enabled)
        self.debug_log.log("toggle", identifier=identifier, label=entry["label"],
                           kind=entry["kind"], direction=enabled)
        self.busy = True
        try:
            self._guard()
            self._check_patches()
            if enabled:
                self._dependencies(entry)
                self._enable(entry)
            else:
                self._disable(entry)
            self.entry_errors.pop(identifier, None)
            if entry.get("one_shot"):
                state = self.one_shot.query(identifier)
                if enabled:
                    message = "one-shot enabled and saved" if state["saved_wish"] else "one-shot failed; nothing saved"
                elif state["effect_persists"]:
                    message = "one-shot wish cleared; effect persists in target"
                else:
                    message = "one-shot inactive; nothing to disable"
                self.status = f"{entry['label']}: {message}"
            else:
                self.status = f"{entry['label']}: {'enabled and saved' if enabled else 'disabled and saved'}"
            self.debug_log.log("toggle-ok", identifier=identifier, label=entry["label"],
                               direction=enabled)
            self._hotkey_sync()
            return enabled
        except Exception as exc:
            self.debug_log.error("toggle-failed", exc, identifier=identifier,
                                 label=entry["label"], direction=enabled)
            self.entry_errors[identifier] = str(exc)
            if isinstance(exc, (PatchConflict, StateError)):
                self._block(exc)
            raise NativeRuntimeError(str(exc)) from exc
        finally:
            self.busy = False

    def request_auto_on(self, identifier: int) -> None:
        """Save an auto-on wish for the next attach while safely disconnected.

        The switch executes only when the target attaches; the wish persists
        like a saved ON and survives controller restarts. One-shot entries
        keep the wish pending until the first confirmed publish at attach
        time, so the saved-marker invariant (saved implies auto-on) holds.
        """
        entry = self._entry(identifier, self._action_kind(identifier))
        if self.memory is not None or self.blocked or self.busy:
            raise NativeRuntimeError("Auto-on can only be requested while safely disconnected")
        if identifier in self.desired:
            self.status = f"{entry['label']}: already auto-on for next game launch"
            return
        try:
            self.store.save(self.desired | {identifier})
            self.desired.add(identifier)
        except Exception as exc:
            self.debug_log.error("auto-on-request-failed", exc, identifier=identifier,
                                 label=entry["label"])
            self._block(exc)
            raise NativeRuntimeError(str(exc)) from exc
        self._mirror_parent_state(identifier)
        self.status = f"{entry['label']}: auto-on requested for next game launch"
        self.debug_log.log("auto-on-requested", identifier=identifier, label=entry["label"],
                           desired=sorted(self.desired))

    def clear_desired(self, identifier: int) -> None:
        self._entry(identifier, self._action_kind(identifier))
        if self.memory is not None or self.blocked or self.busy:
            raise NativeRuntimeError("Cancel auto-on is available only while safely disconnected")
        try:
            if self.one_shot is not None and self.entries[identifier].get("one_shot"):
                self.one_shot.request_off(self._one_shot_backend, identifier)
                self._persist_one_shot_markers()
            self.store.save(self.desired - {identifier})
            self.desired.discard(identifier)
        except Exception as exc:
            self.debug_log.error("auto-on-clear-failed", exc, identifier=identifier,
                                 label=self.entries[identifier]["label"])
            self._block(exc)
            raise NativeRuntimeError(str(exc)) from exc
        self._mirror_parent_state(identifier)
        self.debug_log.log("auto-on-cleared", identifier=identifier,
                           label=self.entries[identifier]["label"],
                           desired=sorted(self.desired))

    def _value_address(self, entry: dict) -> int:
        if entry.get('address_profile') == 'expression/v1':
            from .address_expression import resolve_expression
            from .compiler import (_dynamic_address_binding,
                                   _dynamic_provider_binding)
            address = entry['address']
            if address.lstrip().startswith(('+','-')):
                # WP-38: a relative expression address inherits its base from
                # the dynamic address provider named by the nearest marked
                # heading; the live base is read fresh from the runtime symbol
                # table at every activation, never cached from attach time.
                binding = _dynamic_provider_binding(self.entries, entry)
                if binding is not None:
                    provider_id, symbol = binding
                    symbol_key = symbol.casefold()
                    if (symbol_key not in self.symbols
                            or not self._parent_effect_live(provider_id)):
                        raise NativeRuntimeError(f"Address provider {provider_id} is not active.")
                    return resolve_expression(address, self.memory, self.symbols,
                                              parent=self.symbols[symbol_key],
                                              process_name=self.plan['process_name'],
                                              pointer_size=self.memory.pointer_size)
                # WP-50 (GC-E8): a symbol-null marker binds the base to the
                # target record's live address, written at runtime by the
                # provider's record-Lua; read fresh from the live-base
                # registry and gated on the provider's liveness.
                address_binding = _dynamic_address_binding(self.entries, entry)
                if address_binding is not None:
                    target_id, provider_id = address_binding
                    if (target_id not in self.dynamic_addresses
                            or not self._parent_effect_live(provider_id)):
                        raise NativeRuntimeError(f"Address provider {provider_id} is not active.")
                    return resolve_expression(address, self.memory, self.symbols,
                                              parent=self.dynamic_addresses[target_id],
                                              process_name=self.plan['process_name'],
                                              pointer_size=self.memory.pointer_size)
                # RT-4.3 (O9/O1): a staged relative value on the
                # runtime-base marker; the anchor heading's live base is
                # written at runtime by the table's own scripts into the
                # dynamic-address registry (set_dynamic_address) and read
                # fresh here, never cached from attach time.
                if entry.get("runtime_base_required") is True:
                    anchor_id = entry.get("runtime_base_anchor")
                    if type(anchor_id) is not int or anchor_id not in self.entries:
                        raise NativeRuntimeError(
                            "Staged runtime-base row has an invalid anchor record.")
                    if anchor_id in self.dynamic_addresses:
                        return resolve_expression(address, self.memory, self.symbols,
                                                  parent=self.dynamic_addresses[anchor_id],
                                                  process_name=self.plan['process_name'],
                                                  pointer_size=self.memory.pointer_size)
                    anchor_entry = self.entries[anchor_id]
                    raise NativeRuntimeError(
                        f"Runtime base for group record {anchor_id} "
                        f"('{anchor_entry.get('label', '')}') is not provided yet: "
                        "the table scripts that write the group base must run "
                        "first; activation names the anchor while it is missing.")
                raise NativeRuntimeError('Flattened address profiles require resolved inherited bases')
            return resolve_expression(entry['address'],self.memory,self.symbols,
                                      process_name=self.plan['process_name'],pointer_size=self.memory.pointer_size)
        offsets = [self._resolve_pointer_offset(offset) if isinstance(offset, str) else offset
                   for offset in entry.get("pointer_offsets", [])]
        return self.memory.resolve_pointer(entry["address"], offsets, self.symbols)

    def _resolve_pointer_offset(self, text: str) -> int:
        """RT-4.3 (O3): resolve an address-expression pointer-offset slot
        against the live symbol table and memory (CE pointer-chain
        semantics); the value is applied as a signed 64-bit offset."""
        from .address_expression import resolve_expression
        value = resolve_expression(text, self.memory, self.symbols,
                                   process_name=self.plan['process_name'],
                                   pointer_size=self.memory.pointer_size)
        if abs(value) > 0x7FFFFFFFFFFFFFFF:
            raise NativeRuntimeError("Pointer offset exceeds signed 64 bits.")
        return value

    @staticmethod
    def _value_size(entry: dict) -> int:
        if 'value_profile' in entry:
            from .value_types import profile_size
            return profile_size(entry['value_profile'])
        return _INTEGER_TYPES.get(entry["variable_type"], 4 if entry["variable_type"] == "Float" else 8)

    def _value_mask(self, entry: dict) -> bytes:
        if 'value_profile' in entry:
            from .value_types import profile_mask
            return profile_mask(entry['value_profile'])
        return b'\xff' * self._value_size(entry)

    def _frozen_matches(self, identifier, address, desired):
        profile = self.entries[identifier].get('value_profile')
        size=profile['size'] if profile and profile['kind']=='string' else len(desired)
        current = self.memory.read(address,size)
        profile = self.entries[identifier].get('value_profile')
        if profile is not None:
            from .value_types import profile_value_matches
            return profile_value_matches(profile, desired, current)
        return current == desired

    def _write_bitfields(self, items, *, text_values=False):
        """Merge all owned fields under one OS-held event, preserving neighbors.

        Overlapping byte spans are coalesced; ownership masks must be disjoint.
        Every desired bit is merged with the freshly held snapshot. A batch
        whose spans are all executable is routed to the live provider
        literal-permit path (``_write_bitfields_owned_literal``); mixed
        ordinary/executable batches are refused; ordinary data pages keep
        the data-only coordinator hold.
        """
        from .value_types import merge_profile_value
        from .hooks import QuiescenceProof, HookError, HookUncertain
        item_spans = []
        for identifier, address, value in items:
            size = self._value_size(self.entries[identifier])
            item_spans.append((identifier, address, size))
        executable = [self._is_executable(address, size) for _, address, size in item_spans]
        if any(executable):
            if not all(executable):
                raise NativeRuntimeError('Mixed ordinary/executable bit-field transactions are unsupported')
            return self._write_bitfields_owned_literal(items, text_values=text_values)
        hold = getattr(self.hook_coordinator, 'hold_data', None)
        if hold is None:
            raise NativeRuntimeError('Bit-field writes require a verified data-only thread coordinator')
        merged = []
        for _identifier, address, size in sorted(item_spans, key=lambda item: item[1]):
            start, end = address, address + size
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
            else:
                merged.append((start, end))
        ranges = tuple((start, end-start) for start, end in merged)
        mutation_attempted = False
        try:
            with hold(self.memory, ranges) as proof:
                if not isinstance(proof, QuiescenceProof):
                    raise NativeRuntimeError('Data coordinator did not return a target-bound proof')
                proof.verify(self.memory, ranges)
                self._guard()
                self._check_patches()
                original = {position: byte for start, size in ranges
                            for position, byte in enumerate(self.memory.read(start, size), start)}
                current, ownership = dict(original), {}
                results = {}
                for identifier, address, value in items:
                    entry = self.entries[identifier]
                    if self._value_address(entry) != address:
                        raise PatchConflict('Bit-field pointer changed under the held data event')
                    size = self._value_size(entry)
                    self._check_value_ownership(identifier, address, size)
                    mask = self._value_mask(entry)
                    for index, owned in enumerate(mask):
                        position = address + index
                        if ownership.get(position, 0) & owned:
                            raise NativeRuntimeError('Masked value transaction contains overlapping bit ownership')
                        ownership[position] = ownership.get(position, 0) | owned
                    before = bytes(current[position] for position in range(address, address+size))
                    desired = parse_value(entry, value, before) if text_values else merge_profile_value(entry['value_profile'], value, before)
                    results[identifier] = desired
                    for index, byte in enumerate(desired):
                        current[address+index] = byte
                patches = []
                for start, size in ranges:
                    before = bytes(original[position] for position in range(start, start+size))
                    after = bytes(current[position] for position in range(start, start+size))
                    if before != after:
                        patches.append(_Patch(start, before, after))
                proof.verify(self.memory, ranges)
                mutation_attempted = bool(patches)
                self._write_transaction(patches, proof=proof)
                proof.verify(self.memory, ranges)
                return results
        except HookUncertain as exc:
            self._block(StateError('Data coordinator cleanup is uncertain: ' + str(exc)))
            raise NativeRuntimeError(str(exc)) from exc
        except HookError as exc:
            if mutation_attempted:
                self._block(StateError('Masked data-write proof became uncertain: ' + str(exc)))
                raise NativeRuntimeError(str(exc)) from exc
            raise RetryableAction(str(exc)) from exc

    def _write_bitfields_owned_literal(self, items, *, text_values: bool = False):
        """Masked RMW for bit-field spans fully covered by live literal permits.

        Mirrors ``_write_owned_literal_values`` for the masked path: every
        merged span must be contained in one live permit from
        ``_owned_provider_data()``. A fresh snapshot is taken, each field is
        merged with ``merge_profile_value`` (fresh snapshot as old bytes,
        never the desired value), the merged spans are staged on a transient
        literal-data HookManager bound to the permits, published under the
        safe-point hold and terminated with ``commit_data_only()``.
        Uncertainty quarantines the controller with the journal retained;
        no follow-up write is attempted.
        """
        from .value_types import merge_profile_value
        from .hooks import HookManager, HookUncertain
        if self.hook_coordinator is None:
            raise NativeRuntimeError(
                'Masked bit-field writes to executable provider data '
                'require a verified target thread coordinator')
        _, permits = self._owned_provider_data()
        items = [(identifier, address, self._value_size(self.entries[identifier]), value)
                 for identifier, address, value in items]
        merged = []
        for _identifier, address, size, _value in sorted(items, key=lambda item: item[1]):
            start, end = address, address + size
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
            else:
                merged.append((start, end))
        for start, end in merged:
            if not any(p_start <= start and end <= p_start + p_size
                       for p_start, p_size, _, _ in permits):
                raise NativeRuntimeError(
                    'Masked bit-field writes to executable provider data require '
                    'a fully covered live provider literal permit')
        original = {position: byte for start, end in merged
                    for position, byte in enumerate(self.memory.read(start, end - start), start)}
        current, ownership = dict(original), {}
        results = {}
        for identifier, address, size, value in items:
            entry = self.entries[identifier]
            if self._value_address(entry) != address:
                raise PatchConflict('Bit-field pointer changed before the staged literal write')
            self._check_value_ownership(identifier, address, size)
            mask = self._value_mask(entry)
            for index, owned in enumerate(mask):
                position = address + index
                if ownership.get(position, 0) & owned:
                    raise NativeRuntimeError('Masked value transaction contains overlapping bit ownership')
                ownership[position] = ownership.get(position, 0) | owned
            before = bytes(current[position] for position in range(address, address + size))
            desired = (parse_value(entry, value, before) if text_values
                       else merge_profile_value(entry['value_profile'], value, before))
            results[identifier] = desired
            for index, byte in enumerate(desired):
                current[address + index] = byte
        patches = []
        for start, end in merged:
            before = bytes(original[position] for position in range(start, end))
            after = bytes(current[position] for position in range(start, end))
            if before != after:
                patches.append(_Patch(start, before, after))
        if not patches:
            return results
        manager = HookManager(self.memory,
                              self.store.directory / 'hooks' / (uuid.uuid4().hex + '.json'),
                              self.hook_coordinator,
                              owner_id=self.plan['trainer_id'] + ':bitfield-value',
                              owned_executable_data_ranges=permits)
        try:
            manager.stage([{'address': p.address, 'bytes': p.changed.hex(),
                            'original': p.original.hex(), 'is_allocation': False,
                            'executable': True, 'requires_coordinator': True,
                            'literal_data': True, 'data_semantics': True}
                           for p in patches])
            manager.publish()
            manager.commit_data_only()
            self.retired_hooks.append(manager)
            return results
        except Exception as exc:
            if manager.uncertain or isinstance(exc, HookUncertain) or manager.state == 'enabled':
                self._block(StateError('Bit-field literal mutation is uncertain: ' + str(exc)))
                raise NativeRuntimeError(str(exc)) from exc
            self._abandon_after_failure(manager, exc)
            raise RetryableAction(str(exc)) from exc

    def _check_value_ownership(self, identifier: int, address: int, size: int) -> None:
        if self._is_executable(address,size):
            _, permits = self._owned_provider_data()
            if not any(start <= address and address + size <= start + length for start, length, _, _ in permits):
                raise NativeRuntimeError('Numeric writes and freezes cannot alter executable pages without live provider literal provenance')
        for patches in self.applied.values():
            if any(address < patch.address + len(patch.changed) and patch.address < address + size for patch in patches):
                raise NativeRuntimeError("This value overlaps an active script patch; disable that script first")
        for other, (start, raw) in self.frozen.items():
            if other != identifier and address < start + len(raw) and start < address + size:
                ours, theirs = self._value_mask(self.entries[identifier]), self._value_mask(self.entries[other])
                if any(ours[position-address] & theirs[position-start]
                       for position in range(max(address,start), min(address+size,start+len(raw)))):
                    raise NativeRuntimeError("This value overlaps another frozen entry; unfreeze that entry first")
        for scope in self.lua_activations.values():
            if scope.overlaps(address, size):
                raise NativeRuntimeError('This value overlaps a Lua-owned mutation')
        self._declare_value_data(address, size)

    def _declare_value_data(self, address: int, size: int) -> None:
        """Record a value write range inside an owned provider allocation.

        Value records that resolve into a provider's owned writable
        allocation are declared data, not foreign mutation: the owning
        manager records the exact span so its executable-allocation
        integrity guard skips it, the same contract as source literal
        spans (allocation-only providers exist precisely to host consumer
        values).  Addresses outside owned allocations are no-ops.
        """
        managers = list(self.hooks.values())
        for scope in self.lua_activations.values():
            managers.extend(scope.managers())
        for manager in managers:
            if manager.declare_value_data(address, size):
                return

    def _require_staged_live(self, entry: dict) -> None:
        """WP-14 (C1): refuse value access on a staged record while pending.

        A staged record's address needs symbols its provider registers at
        activation; while any provider is not live the record is pending,
        so value reads, writes and freezes are refused with a named error.
        This is a state, not a fault: the poll/UI layer renders it as a
        pending card, and the provider stays owned by its ordinary
        activation path (the value path never auto-enables it).
        """
        staged = entry.get("staged")
        if not staged:
            return
        for provider_id in staged["provider_ids"]:
            if not self._parent_effect_live(provider_id):
                provider = self.entries[provider_id]
                raise NativeRuntimeError(
                    "Staged record '%s' requires active provider '%s'"
                    % (entry.get("label") or str(entry["id"]),
                       provider.get("label") or str(provider_id)))

    def read_value(self, identifier: int) -> str:
        entry = self._entry(identifier, "value")
        self._guard()
        self._require_staged_live(entry)
        # Reading does not activate providers or persist a new wish.
        address = self._value_address(entry)
        return format_value(entry, self.memory.read(address, self._value_size(entry)))

    # ----------------------------------------------------------- WP-40: record hotkeys
    #
    # The plan carries every original <Hotkey> binding (byte-verified by
    # both plan validators).  The engine publishes the live subset through
    # the tested hotkey_model controller with the first-wins conflict
    # policy; every refusal is a named, deduplicated entry of
    # self.hotkey_warnings, and the losing record stays fully functional.

    def _hotkey_record_live(self, record_id: int) -> bool:
        """True while the record's hotkeys may be published.

        Script records are live while applied (their activation effect is
        present in the target).  Group-heading bindings register while the
        session is attached (WP-53: CE registers group hotkeys at table
        load) - neither the heading's own active state nor any
        child-liveness requirement gates them.  Value records are live
        while selected, supported and - when staged - every provider
        effect is live; a staged-pending value row keeps its
        value-operation hotkeys unregistered until the provider activates
        (the steady poll re-syncs the controller).  No binding exists
        without an attached session.
        """
        if self.memory is None:
            return False
        entry = self.entries[record_id]
        if not (entry.get("selected") and entry.get("supported")):
            return False
        if entry["kind"] == "value":
            staged = entry.get("staged")
            if staged:
                for provider_id in staged["provider_ids"]:
                    if not self._parent_effect_live(provider_id):
                        return False
            return True
        if entry["kind"] in {"script", "heading"}:
            if entry["kind"] == "heading":
                return True
            return record_id in self.applied
        return False

    @staticmethod
    def _hotkey_toggleable(entry: dict) -> bool:
        """Activation hotkeys exist on script records and every supported
        group heading (WP-53).

        Flagged headings run the existing parent-activation cascade over
        their subtree; plain moHideChildren headings toggle their own
        active state only, with no child propagation (CE parity).  Blocked
        or non-toggleable rows keep the named refusal.
        """
        return bool(entry.get("supported") and (
            entry["kind"] == "script"
            or entry["kind"] == "heading"))

    @staticmethod
    def _hotkey_value_actionable(entry: dict) -> bool:
        """Value-operation hotkeys map only to actionable value rows."""
        return bool(entry.get("selected") and entry.get("supported")
                    and entry["kind"] == "value")

    def _hotkey_warn(self, message: str) -> None:
        if message not in self.hotkey_warnings:
            self.hotkey_warnings.append(message)

    def _hotkey_register_record(self, record_id: int) -> None:
        """Publish one newly live record's declared hotkeys (first-wins).

        Unregisterable cases surface as named warnings in
        self.hotkey_warnings (the plan keeps the original binding either
        way); an already-owned combination loses by first-wins with a
        warning that names both records, and the losing record keeps its
        ordinary UI actions.
        """
        entry = self.entries[record_id]
        label = entry.get("label") or str(record_id)
        for hotkey in entry.get("hotkeys", ()):
            if not hotkey.get("active", True):
                continue
            action = hotkey.get("action") or ""
            keys = list(hotkey.get("keys", ()))
            try:
                spec = vk_to_spec(keys)
            except HotkeyModelError:
                self._hotkey_warn(
                    f"Record {record_id} ('{label}'): hotkey ({action}) "
                    f"not registered: no parsable key.")
                continue
            key_text = format_hotkey_keys(keys)
            if action in VALUE_HOTKEY_ACTIONS:
                if entry.get("kind") == "heading":
                    # WP-53 (GC-D7): group headings carry no value of their
                    # own; a value-operation hotkey on a heading is not
                    # applicable rather than a registration failure (CE
                    # parity: group rows only expose activation).  The
                    # plan-level warning already names this at compile time,
                    # so the runtime stays quiet.
                    continue
                if not self._hotkey_value_actionable(entry):
                    self._hotkey_warn(
                        f"Record {record_id} ('{label}'): hotkey {key_text} ({action}) "
                        f"not registered: value row is not actionable.")
                    continue
            elif action in ACTIVATION_HOTKEY_ACTIONS:
                if not self._hotkey_toggleable(entry):
                    reason = ("record is blocked" if not entry.get("supported")
                              else "record has no activation action")
                    self._hotkey_warn(
                        f"Record {record_id} ('{label}'): hotkey {key_text} ({action}) "
                        f"not registered: {reason}.")
                    continue
            else:
                self._hotkey_warn(
                    f"Record {record_id} ('{label}'): hotkey {key_text} ({action!r}) "
                    f"not registered: unsupported action.")
                continue
            registered, winner = self.hotkey_controller.register_first_wins(
                self._hotkey_owner, record_id, spec)
            if not registered:
                winner_entry = self.entries.get(winner.record_id)
                winner_label = (winner_entry or {}).get("label") or str(winner.record_id)
                self._hotkey_warn(
                    f"Record {record_id} ('{label}'): hotkey {key_text} not registered: "
                    f"key already bound to record {winner.record_id} "
                    f"('{winner_label}') by first-wins")
            else:
                # WP-53 (GC-D7): mirror the published binding into the OS
                # bridge (attached by the trainer on Windows); the binding
                # is registered exactly once per unique combination.
                self._hotkey_os_register(record_id, spec)

    def _hotkey_sync(self) -> None:
        """Reconcile the published hotkey bindings with the live record set.

        Called on toggle success, attach/restore completion, every steady
        poll tick and confirmed target exit.  Records register in
        activation order (applied insertion order, value rows by record
        id).  Deliberate scope limit: no automatic re-claim - when the
        winning record disables, its binding is dropped and the losing
        claimant keeps no binding until its own liveness changes again.
        """
        if self.closed:
            return
        live = {record_id for record_id in self.entries
                if self._hotkey_record_live(record_id)}
        for record_id in sorted(self._hotkey_live - live):
            self.hotkey_controller.unregister(self._hotkey_owner, record_id)
            # WP-53 (GC-D7): release the OS registrations the record had
            # mirrored into the bridge, so no hotkey outlives its binding.
            self._hotkey_os_release(record_id)
        newly = live - self._hotkey_live
        self._hotkey_live = live
        if not newly:
            return
        activation_order = [record_id for record_id in self.applied if record_id in newly]
        rest = sorted(newly - set(activation_order))
        for record_id in activation_order + rest:
            self._hotkey_register_record(record_id)

    def _hotkey_os_register(self, record_id: int, spec: HotKeySpec) -> None:
        """WP-53 (GC-D7): mirror one published binding into the OS bridge.

        A RegisterHotKey failure (another process owns the combination,
        invalid parameter) is named and deduplicated in hotkey_warnings;
        the binding stays published for the programmatic dispatch path.
        A bridge-less session (non-Windows, tests) is a clean no-op.
        """
        bridge = self.hotkey_bridge
        if bridge is None:
            return
        try:
            bridge.register(spec)
        except HotkeyRegistrationError as exc:
            self._hotkey_warn(str(exc))
            return
        self._hotkey_os.setdefault(record_id, set()).add(spec)

    def _hotkey_os_release(self, record_id: int) -> None:
        """Release every OS registration one record published."""
        bridge = self.hotkey_bridge
        specs = self._hotkey_os.pop(record_id, None)
        if bridge is None or not specs:
            return
        for spec in sorted(specs, key=lambda item: (item.key, sorted(item.modifiers))):
            bridge.unregister(spec)

    def _hotkey_release_all_os(self) -> None:
        """Trainer close: release every OS registration and the window."""
        bridge = self.hotkey_bridge
        if bridge is None:
            return
        self._hotkey_os.clear()
        bridge.close()
        self.hotkey_bridge = None

    def _hotkey_drain(self) -> tuple:
        """WP-53 (GC-D7): the poll-tick drain of OS-captured hotkey specs.

        The source is the attached bridge's queue; the pluggable
        ``hotkey_spec_source`` attribute (test seam) takes precedence so
        tests can inject fake specs without a real window.  Every item
        must be a canonical HotKeySpec (named refusal otherwise).
        """
        if self.hotkey_spec_source is not None:
            source = self.hotkey_spec_source
        elif self.hotkey_bridge is not None:
            source = self.hotkey_bridge.take_specs
        else:
            return ()
        specs = list(source())
        for spec in specs:
            if not isinstance(spec, HotKeySpec):
                raise NativeRuntimeError(
                    "Hotkey spec source yielded a non-HotKeySpec item.")
        return tuple(specs)

    def _hotkey_for_binding(self, entry: dict, spec: HotKeySpec) -> dict | None:
        """The record's declared hotkey carrying exactly this key combination."""
        for hotkey in entry.get("hotkeys", ()):
            try:
                if vk_to_spec(list(hotkey.get("keys", ()))) == spec:
                    return hotkey
            except HotkeyModelError:
                continue
        return None

    def _hotkey_dispatch(self, binding) -> ToggleOutcome:
        """Route one published binding to the record hotkey that declared it.

        One record may hold several bindings; the full binding identifies
        the exact declared action.  Activation actions flip the record
        through the ordinary toggle transaction; value actions write
        through set_value (staged provider checks and ownership rules
        included).  Failures are named, visible FAILED outcomes; the
        binding stays published so the record remains fully functional.
        """
        entry = self.entries.get(binding.record_id)
        if entry is None:
            return ToggleOutcome(ToggleOutcomeStatus.FAILED, False, "Unknown hotkey record")
        hotkey = self._hotkey_for_binding(entry, binding.spec)
        if hotkey is None:
            return ToggleOutcome(ToggleOutcomeStatus.FAILED, False, "Binding has no declared record hotkey")
        action = hotkey.get("action") or ""
        try:
            if action in ACTIVATION_HOTKEY_ACTIONS:
                self.toggle(binding.record_id)
                return ToggleOutcome(ToggleOutcomeStatus.CONFIRMED, True)
            if action in VALUE_HOTKEY_ACTIONS:
                if action == "Set Value":
                    self.set_value(binding.record_id, hotkey.get("value") or "")
                else:
                    self._hotkey_value_step(binding.record_id, action, hotkey)
                return ToggleOutcome(ToggleOutcomeStatus.CONFIRMED, False)
            return ToggleOutcome(ToggleOutcomeStatus.FAILED, False, "Unsupported hotkey action")
        except Exception as exc:
            return ToggleOutcome(ToggleOutcomeStatus.FAILED, False, str(exc))

    def _hotkey_value_step(self, record_id: int, action: str, hotkey: dict) -> None:
        """Increase/Decrease Value hotkeys: one step through set_value.

        The source Value element carries the step literal: a decimal
        integer for byte/word/dword/quad rows (ShowAsHex rows are written
        back as lowercase hex without a 0x prefix) and a finite decimal
        number for decimal Float/Double rows.  Hexadecimal float
        bit-pattern rows and profile-backed rows (string, byte array,
        bit field) have no bounded numeric step and refuse with a named
        reason before any write.
        """
        entry = self.entries[record_id]
        direction = 1 if action == "Increase Value" else -1
        step_text = (hotkey.get("value") or "").strip()
        profile = entry.get("value_profile") or {}
        if profile.get("kind") in {"string", "byte_array", "bitfield"}:
            raise NativeRuntimeError(
                f"Hotkey value step is not defined for {profile['kind']} rows")
        if entry.get("show_as_hex") and entry.get("variable_type") in ("Float", "Double"):
            raise NativeRuntimeError("Hotkey value step is not defined for hex float rows")
        current = self.read_value(record_id)
        if entry.get("variable_type") in ("Float", "Double"):
            if not re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", step_text):
                raise NativeRuntimeError("Hotkey value step must be a finite decimal number")
            step = float(step_text)
            if not math.isfinite(step):
                raise NativeRuntimeError("Hotkey value step must be finite")
            candidate = str(float(current) + direction * step)
        elif entry.get("show_as_hex"):
            if not re.fullmatch(r"[+-]?[0-9]+", step_text):
                raise NativeRuntimeError("Hotkey value step must be a decimal integer")
            candidate = format(int(current, 16) + direction * int(step_text, 10), "x")
        else:
            if not re.fullmatch(r"[+-]?[0-9]+", step_text):
                raise NativeRuntimeError("Hotkey value step must be a decimal integer")
            candidate = str(int(current) + direction * int(step_text, 10))
        self.set_value(record_id, candidate)

    def hotkey_registered_keys(self, identifier: int) -> tuple[tuple[str, bool], ...]:
        """Display contract input: the record's original bindings.

        Returns ``(key_text, registered)`` per declared hotkey in plan
        order; ``registered`` is True while the first-wins policy has the
        combination published for this record.  Pure state read - plan
        metadata plus the published binding list, no memory access.
        """
        entry = self.entries.get(identifier)
        if entry is None:
            raise NativeRuntimeError(f"Unknown record id {identifier}")
        owned = {item.spec for item in self.hotkey_controller.registrations()
                 if item.record_id == identifier}
        rows = []
        for hotkey in entry.get("hotkeys", ()):
            keys = list(hotkey.get("keys", ()))
            try:
                registered = vk_to_spec(keys) in owned
            except HotkeyModelError:
                registered = False
            rows.append((format_hotkey_keys(keys), registered))
        return tuple(rows)

    def dispatch_hotkey(self, spec: HotKeySpec):
        """Route one pressed key combination through the hotkey controller.

        The OS hotkey callback (owned Windows RegisterHotKey route, AP-11
        gate) feeds the parsed combination here; dispatch enforces the
        model focus/text-focus/block checks and routes through the
        binding handler to the record's declared action.
        """
        return self.hotkey_controller.dispatch(spec)

    def _set_recursive_value(self, identifier: int, entry: dict, text: str) -> str:
        """Apply one moRecursiveSetValue write across the value-descendant closure.

        Byte-exact bytes come from the tested RecursiveSetValueModel plan
        (deepest records first, target last); every write goes through the
        ordinary value-runtime ownership checks and one all-or-nothing
        transaction, so a partial closure can never be left behind. Frozen
        closure records keep the new bytes so the freeze loop cannot roll
        the recursive write back. Bit-field or string records in the write
        set are refused fail-closed: their ordinary write paths need
        coordinator-held snapshots or the string writer, which the static
        closure plan does not carry.
        """
        from .value_links import RecursiveSetValueError, RecursiveSetValueModel
        if self.busy:
            raise NativeRuntimeError("Another trainer action is in progress")
        self.busy = True
        try:
            self._guard()
            self._check_patches()
            if entry.get("staged"):
                self._require_staged_live(entry)
            else:
                self._dependencies(entry)
            records = {}
            for item in self.plan["entries"]:
                signed = item.get("show_as_signed")
                records[item["id"]] = {
                    "id": item["id"],
                    "label": item["label"],
                    "parent_id": item.get("parent_id"),
                    "kind": item["kind"],
                    "supported": item["supported"],
                    "selected": item["selected"],
                    "variable_type": item.get("variable_type"),
                    "show_as_hex": item["show_as_hex"],
                    "show_as_signed": False if signed is None else signed,
                    "value_profile": item.get("value_profile"),
                    "address": item["address"],
                    "recursive": item.get("recursive_value") is not None,
                }
            try:
                plan = RecursiveSetValueModel(records).plan_writes(identifier, text)
            except RecursiveSetValueError as exc:
                raise NativeRuntimeError(str(exc)) from exc
            write_ids = [element["record_id"] for element in plan["writes"]]
            if write_ids != entry["recursive_value"]["write_ids"]:
                raise NativeRuntimeError(
                    "Recursive value plan differs from the compiled write closure")
            patches = []
            for element in plan["writes"]:
                write_entry = self.entries[element["record_id"]]
                profile = write_entry.get("value_profile")
                if profile is not None and profile.get("kind") in ("bitfield", "string"):
                    raise NativeRuntimeError(
                        "Recursive value closure cannot write a "
                        + profile["kind"] + " record (masked bit-field and "
                        "string propagation are unsupported)")
                if write_entry.get("staged"):
                    self._require_staged_live(write_entry)
                else:
                    self._dependencies(write_entry)
                address = self._value_address(write_entry)
                raw = bytes.fromhex(element["bytes_hex"])
                self._check_value_ownership(element["record_id"], address, len(raw))
                patches.append(_Patch(address, self.memory.read(address, len(raw)), raw))
            self._write_transaction(patches)
            for element in plan["writes"]:
                record_id = element["record_id"]
                if record_id in self.frozen:
                    self.frozen[record_id] = (self._value_address(self.entries[record_id]),
                                              bytes.fromhex(element["bytes_hex"]))
            display = format_value(entry, bytes.fromhex(plan["writes"][-1]["bytes_hex"]))
            self.status = f"{entry['label']}: value confirmed ({display})"
            return display
        except Exception as exc:
            self.entry_errors[identifier] = str(exc)
            if isinstance(exc, (StateError, PatchConflict)):
                self._block(exc)
            raise NativeRuntimeError(str(exc)) from exc
        finally:
            self.busy = False

    @restoration_entry
    def set_value(self, identifier: int, text: str) -> str:
        entry = self._entry(identifier, "value")
        if entry.get("recursive_value") is not None:
            return self._set_recursive_value(identifier, entry, text)
        bitfield = entry.get('value_profile', {}).get('kind') == 'bitfield'
        string = entry.get('value_profile', {}).get('kind') == 'string'
        # RT-4.4 (O8): a bracketed dropdown choice is an address
        # expression; it is resolved against the live symbol table at
        # write time, mirroring CE, which evaluates such values in the
        # table's scripting context before the store.  Resolution happens
        # before any parse or memory access so a failed expression never
        # touches the target (named refusal, no partial write).
        if not bitfield and not string:
            expression_choice = next(
                (choice for choice in (entry.get("dropdown") or {}).get("choices", [])
                 if choice.get("expression") is True
                 and choice.get("value") == str(text).strip()), None)
            if expression_choice is not None:
                from .address_expression import (AddressExpressionError,
                                                 resolve_expression)
                if self.memory is None:
                    raise NativeRuntimeError(
                        "Expression dropdown choices require an attached target.")
                try:
                    resolved = resolve_expression(
                        str(text).strip(), self.memory, self.symbols,
                        process_name=self.plan["process_name"],
                        pointer_size=self.memory.pointer_size)
                except AddressExpressionError as exc:
                    raise NativeRuntimeError(str(exc)) from exc
                text = str(resolved)
        raw = None if bitfield else parse_value(entry, text)
        if bitfield:
            parse_value(entry, text, bytes(self._value_size(entry)))
        if self.busy:
            raise NativeRuntimeError("Another trainer action is in progress")
        self.debug_log.log("value-write", identifier=identifier, label=entry["label"],
                           text=text)
        self.busy = True
        try:
            self._guard()
            self._check_patches()
            # WP-14 (C1): staged values gate on provider liveness; records
            # without staged metadata keep the legacy auto-enable behaviour.
            if entry.get("staged"):
                self._require_staged_live(entry)
            else:
                self._dependencies(entry)
            address = self._value_address(entry)
            if bitfield:
                raw = self._write_bitfields([(identifier, address, text)], text_values=True)[identifier]
            elif string:
                from .string_runtime import write_strings
                write_strings(self,[(identifier,address,raw)])
            else:
                self._check_value_ownership(identifier, address, len(raw))
                self._write_transaction([_Patch(address, self.memory.read(address, len(raw)), raw)])
            if identifier in self.frozen:
                self.frozen[identifier] = (address, raw)
            if string:
                from .value_types import format_written_profile_value
                display=format_written_profile_value(entry['value_profile'],raw)
            else:display=format_value(entry,raw)
            self.status = f"{entry['label']}: value confirmed ({display})"
            self.debug_log.log("value-write-ok", identifier=identifier,
                               label=entry["label"], address=hex(address),
                               display=display)
            return display
        except Exception as exc:
            self.debug_log.error("value-write-failed", exc, identifier=identifier,
                                 label=entry["label"], text=text)
            self.entry_errors[identifier] = str(exc)
            if isinstance(exc, (StateError, PatchConflict)):
                self._block(exc)
            raise NativeRuntimeError(str(exc)) from exc
        finally:
            self.busy = False

    @restoration_entry
    def set_freeze(self, identifier: int, enabled: bool = True) -> bool:
        entry = self._entry(identifier, "value")
        self._guard()
        if self.busy:
            raise NativeRuntimeError("Another trainer action is in progress")
        self.debug_log.log("freeze-request", identifier=identifier,
                           label=entry["label"], enabled=enabled)
        self.busy = True
        try:
            self._check_patches()
            if enabled:
                # WP-14 (C1): staged values gate on provider liveness; records
                # without staged metadata keep the legacy auto-enable behaviour.
                if entry.get("staged"):
                    self._require_staged_live(entry)
                else:
                    self._dependencies(entry)
                if entry.get('value_profile',{}).get('kind')=='string':
                    from .string_runtime import admit_freeze
                    admit_freeze(self,identifier)
                address = self._value_address(entry)
                if (entry.get('value_profile', {}).get('kind') == 'bitfield'
                        and self._is_executable(address, self._value_size(entry))):
                    # Refuse before recording so a failed enable never
                    # becomes a saved wish; the tick re-checks live permits
                    # per write.
                    _, permits = self._owned_provider_data()
                    if not any(start <= address and address + self._value_size(entry) <= start + length
                               for start, length, _, _ in permits):
                        raise NativeRuntimeError(
                            'Masked bit-field freezes on executable provider data require '
                            'a fully covered live provider literal permit')
                if entry.get('value_profile',{}).get('kind')=='string':
                    from .string_runtime import snapshot_freeze
                    raw=snapshot_freeze(self,identifier,address)
                    admit_freeze(self,identifier)
                    from .lua_work_budget import broker_checkpoint, _mutation_checkpoint
                    broker_checkpoint()
                    _mutation_checkpoint()
                    self.frozen[identifier]=(address,raw)
                else:
                    self._check_value_ownership(identifier, address, self._value_size(entry))
                    self.frozen[identifier] = (address, self.memory.read(address, self._value_size(entry)))
            else:
                self.frozen.pop(identifier, None)
            self.status = f"{entry['label']}: {'current value frozen for this session' if enabled else 'unfrozen'}"
            freeze_details = {"identifier": identifier, "label": entry["label"],
                              "enabled": enabled}
            if enabled:
                freeze_details["address"] = hex(address)
            self.debug_log.log("freeze-changed", **freeze_details)
            return enabled
        except Exception as exc:
            self.debug_log.error("freeze-failed", exc, identifier=identifier,
                                 label=entry["label"], enabled=enabled)
            self.entry_errors[identifier] = str(exc)
            if isinstance(exc, (StateError, PatchConflict)):
                self._block(exc)
            raise NativeRuntimeError(str(exc)) from exc
        finally:
            self.busy = False

    @restoration_entry
    def close(self) -> bool:
        """Restore owned patches; preserve every journal if cleanup is uncertain."""
        if self.closed:
            return not self.blocked
        try:
            if self.busy:
                raise StateError("An action is still in progress")
            if self.blocked:
                # A blocked engine cannot verify or restore its owned
                # receipts. While the target is still alive that refusal
                # stands (fail-closed: the state stays recoverable after a
                # target restart). If the target is gone, nothing is left
                # to restore, so the exit cleanup below completes instead
                # of dead-ending the shutdown and orphaning state.lock
                # (field case 2026-10-20, Sinking City 2 0.16: the target
                # exit raced a hook-receipt read -> PatchConflict -> engine
                # blocked -> close refused -> state.lock orphaned -> the
                # trainer could not be restarted).
                if self.memory is not None and self.memory.is_alive():
                    raise StateError(self.error or "An action is still in progress")
                self.debug_log.log("close-after-blocked", error=self.error)
            self.store.guard()
            # WP-54 (d): cancel the record sessions now (their callbacks
            # must not fire during cleanup); the table scope retires only
            # after the record scopes below, so table symbols outlive every
            # record consumer.
            self._cancel_lua_sessions()
            if self.memory is not None:
                if self.memory.is_alive():
                    require_target_architecture(self.plan, self.memory)
                    self._check_patches()
                    self.frozen.clear()
                    while self.applied:
                        leaves = [i for i in self.applied if not self._owner_consumers(i)]
                        if not leaves:
                            # Manual Lua symbols may have mutually consuming
                            # scopes while their AA receipts remain individually
                            # retireable. All callbacks were cancelled above.
                            receipts = [(identifier, token) for identifier, scope in self.lua_activations.items()
                                        for token, item in scope.assemblies.items()
                                        if not self._symbol_consumers(item['exports'], exclude_token=(identifier, token))
                                        and not self._provider_consumers(item['manager'], exclude_token=(identifier, token))]
                            if not receipts:
                                raise StateError('Cannot order combined record/Lua cleanup')
                            for identifier, token in receipts:
                                self.lua_activations[identifier]._retire(token)
                            continue
                        for identifier in leaves:
                            self._disable(self.entries[identifier], persist=False, run_lua_disable=False)
                else:
                    for scope in self.lua_activations.values():
                        scope.finish_after_exit()
                    self.lua_activations.clear()
                    for manager in list(self.hooks.values()) + self.retired_hooks:
                        manager.finish_after_exit()
                    self.hooks.clear()
                    self.retired_hooks.clear()
                    if self.global_pool is not None:
                        self.global_pool.finish_after_exit(remove_journal=True)
                        self.global_pool=None
                        self.global_leases.clear()
                        self._global_aliases.clear()
                if self.global_pool is not None and not self.global_pool.members:
                    self.global_pool.finish_unexposed()
                    self.global_pool=None
                if self.global_pool is not None and self.global_pool.members:
                    raise StateError('Shared globals and their retired consumers remain owned until exact target exit. Preserve the session and receipts.')
                from .restoration_budget import checkpoint
                checkpoint()
                self.memory.close()
                checkpoint()
                self.store.release_session()
                self.memory = None
            # WP-54 (d): the table scope retires last — after every record
            # scope above — so its symbols release exactly once, only after
            # all record consumers have retired.
            self._retire_table_lua_scope()
            # WP-50 (GC-E8): the live-base registry dies with the session;
            # provider deactivation already retired per-provider targets.
            self.dynamic_addresses.clear()
            # RT-5 item C2: the runtime journal dies with the session; any
            # still-active dynamic record was restored above through the
            # ordinary disable pass (applied map) before this point.
            self._clear_dynamic_records()
            if self.one_shot is not None:
                self.one_shot.detach()
                self._persist_one_shot_markers()
            if self.async_policy is not None:
                # Trainer session ends with all owned effects restored above;
                # drain controller state, saved wishes stay in state.json.
                self.async_policy.detach()
            if self.parent_policy is not None:
                # Trainer session ends with all owned effects restored above;
                # drain parent controller state, saved wishes stay in state.json.
                self.parent_policy.detach()
            self._release_call_broker()
            self._release_debugger_session()
            self._release_managed_session(False)
            if self.clock is not None:
                # Stopped target keeps no speed state: retire the binding
                # (fence plus lease close) before the session ends.
                self.clock.finish()
                self.clock = None
            self.hotkey_controller.close(self._hotkey_owner)
            self._hotkey_live.clear()
            self._hotkey_release_all_os()
            self.store.close()
            self.closed = True
            self.status = "Trainer closed; saved switches will restore on the next game launch"
            self.debug_log.log("engine-close", clean=True, status=self.status,
                               still_applied=sorted(self.applied))
            self.debug_log.close()
            return True
        except Exception as exc:
            self.debug_log.error("engine-close-failed", exc)
            self._cancel_lua_sessions()
            self._retire_table_lua_scope()
            self._release_call_broker()
            self._release_debugger_session()
            self._release_managed_session(False)
            self._block(exc)
            if self.memory is not None:
                try:
                    self.memory.close()
                except Exception as close_error:
                    self._block(NativeRuntimeError(f"{exc}; process handle close also failed: {close_error}"))
                self.memory = None
            if self.clock is not None:
                self.clock.finish()
                self.clock = None
            self.hotkey_controller.close(self._hotkey_owner)
            self._hotkey_live.clear()
            self._hotkey_release_all_os()
            self.closed = True
            self.debug_log.close()
            return False

    def _atexit_close(self) -> None:
        """Best-effort interpreter-shutdown cleanup for the state lock.

        close() is the authoritative path; this only covers processes that
        exit without calling close(). It never raises from the atexit hook;
        a failed release falls back to the verified stale-state and stale-
        artifact recovery paths on the next start.
        """
        try:
            if not getattr(self, "closed", True):
                self.close()
        except Exception:
            pass
        try:
            store = getattr(self, "store", None)
            if store is not None and store.owned:
                if store.session_bytes is not None:
                    # The session still holds the lock because close() was
                    # refused or never completed. It may only be released
                    # once the target is provably gone: while the target is
                    # alive, its still-applied patches must stay
                    # recoverable, so the state is preserved for the
                    # verified stale-state recovery on the next start
                    # (field case 2026-10-20: a blocked close left session
                    # plus lock behind because store.close() refuses while
                    # a session remains).
                    memory = getattr(self, "memory", None)
                    if memory is not None and not memory.is_alive():
                        store.release_session()
                store.close()
        except Exception:
            pass
