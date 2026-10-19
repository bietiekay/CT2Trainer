"""Independent owned-allocation and hook publication transactions.

This module contains no CE implementation. iced-x86 (MIT) checks displaced
instruction boundaries. It deliberately has no default thread coordinator:
ordinary writes or a thread snapshot do not make an executable patch atomic.
The caller must hold a separately verified safe point for the exact target.
Published allocations are retained even after disable, because a thread may
still be executing their code. Target exit is the initial reclamation gate.
"""
from __future__ import annotations
from .restoration_budget import restoration_entry, restoration_region, _clock_for

from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
import json
import hashlib
import os
from pathlib import Path
import re
import threading
from typing import Any, Protocol
import uuid

from .lua_work_budget import broker_checkpoint
from .memory import _checked_write


MAX_HOOK_ALLOCATION = 4 * 1024 * 1024
MAX_HOOK_BYTES = 16 * 1024 * 1024
MAX_HOOK_ALLOCATIONS = 128
MAX_HOOK_BLOCKS = 4096
MAX_ENTRY_BYTES = 65536
_ENTRY_PATCH_TAIL = 64  # live bytes read past a cut patch (max x86 op is ~15)
MAX_JOURNAL_BYTES = 72 * 1024 * 1024
MAX_LITERAL_ISSUER_DEPTH = 64
_issuer_checks = threading.local()


class HookError(RuntimeError):
    """An action was rejected before a hook mutation became uncertain."""


class HookUncertain(HookError):
    """Keep the journal and block further mutation until target restart."""


class _LiteralDataPermit(tuple):
    """Ephemeral four-integer bounds bound to their live first-party issuer.

    JSON contains only the bounds and cannot reconstruct this capability.
    Neither the permit nor its issuer is exposed to table Lua or serialized CT.
    """
    def __new__(cls, issuer, start, size, allocation_start, allocation_size):
        permit = super().__new__(cls, (start, size, allocation_start, allocation_size))
        permit._issuer = issuer
        return permit


@dataclass(frozen=True)
class QuiescenceProof:
    """Proof supplied by a trusted coordinator while its safe point is held.

    Ranges use (start, byte_count), not inclusive end addresses. ``check`` must
    verify the safe point remains held, without releasing it. This is an
    internal first-party API, not a capability table scripts can manufacture.
    """
    identity: tuple[int, int]
    ranges: tuple[tuple[int, int], ...]
    mechanism: str
    check: Callable[[], bool]

    def verify(self, memory: Any, required: Sequence[tuple[int, int]]) -> None:
        if (self.identity != memory.identity or not self.mechanism
                or not callable(self.check) or not memory.is_alive()
                or self.check() is not True):
            raise HookError("The target safe point is absent, changed, or no longer held.")
        for address, size in required:
            if not any(start <= address and address + size <= start + length
                       for start, length in self.ranges):
                raise HookError("The coordinator did not cover every changed entry range.")


class HookCoordinator(Protocol):
    def hold(self, memory: Any, ranges: Sequence[tuple[int, int]]) -> AbstractContextManager[QuiescenceProof]:
        """Hold all threads that can execute the affected ranges outside them."""


def validate_instruction_boundary(address: int, original: bytes, bitness: int) -> None:
    """Require a complete valid x86/x64 instruction sequence to be displaced."""
    if bitness not in {32, 64} or not original or len(original) > MAX_ENTRY_BYTES:
        raise HookError("Invalid executable entry range or target bitness.")
    try:
        from iced_x86 import Decoder
    except ImportError as exc:
        raise HookError("Executable hooks require the pinned MIT iced-x86 decoder.") from exc
    decoder = Decoder(bitness, original, ip=address)
    decoded = 0
    for instruction in decoder:
        if instruction.is_invalid:
            raise HookError("Entry patch cuts or contains an invalid instruction.")
        decoded += instruction.len
    if decoded != len(original):
        raise HookError("Entry patch does not end on an instruction boundary.")


def validate_entry_control_flow(address: int, raw: bytes, bitness: int,
                                *, inline_jump: bool = False) -> None:
    """Check return-context hazards, recognizing one owned x64 far-jump form.

    Only replacements verified by their owning controller may use the inline
    pointer form. The whole overwrite, including its eight data bytes, remains
    an IP exclusion range; the pointer is never interpreted as instructions.
    """
    from iced_x86 import Decoder, FlowControl
    code = raw
    if inline_jump and bitness == 64 and raw.startswith(bytes.fromhex("FF2500000000")):
        if len(raw) < 14:
            raise HookError("An inline far jump needs its complete eight-byte pointer.")
        target = int.from_bytes(raw[6:14], "little")
        if not 0 < target <= 0x7FFFFFFFFFFF:
            raise HookError("An inline far jump needs a valid user-space destination.")
        # Recognize exactly JMP QWORD PTR [RIP+0], followed by its own pointer.
        # Any following padding must still form complete, safe instructions.
        code = raw[:6] + raw[14:]
    validate_instruction_boundary(address, code, bitness)
    for instruction in Decoder(bitness, code, ip=address):
        if instruction.flow_control in {FlowControl.CALL, FlowControl.INDIRECT_CALL,
                                        FlowControl.INTERRUPT, FlowControl.EXCEPTION}:
            raise HookError("Calls/interrupts in entry instructions need a stronger return-context proof.")


def validate_entry_prefix_cut(memory, address: int, raw: bytes, original: bytes,
                              bitness: int) -> None:
    """Live verification for a linked prefix-cut byte patch.

    Called only for executable entry blocks whose captured original bytes do
    not form a complete instruction sequence. The classic byte-patch shape:
    the replaced prefix plus the remaining bytes of the covered original
    instruction form a complete, valid instruction stream ending exactly on
    the first original instruction boundary at or past the patch length
    (for example ``db 90 E9`` over a 6-byte conditional jump becomes
    ``nop; jmp`` with the original displacement). Fails closed on
    unreadable targets, byte drift, unresolvable boundaries, decode
    failures, and call/interrupt hazards in the resulting entry stream.
    """
    if (bitness not in {32, 64} or not raw or not original
            or len(raw) != len(original) or len(raw) > MAX_ENTRY_BYTES):
        raise HookError("Invalid executable entry range or target bitness.")
    try:
        from iced_x86 import Decoder, FlowControl
    except ImportError as exc:
        raise HookError("Executable hooks require the pinned MIT iced-x86 decoder.") from exc
    # Fast path: the captured original already displaces complete
    # instructions, so the historical two-sided static contract applies —
    # the original keeps its own strict check (including the return-context
    # refusal for call/interrupt entries) and the replacement the inline
    # form. The live proof below only ever runs for genuine fragment
    # receipts (a prefix-cut byte patch whose original is the head of a
    # longer original instruction).
    try:
        validate_instruction_boundary(address, original, bitness)
    except HookError:
        pass
    else:
        validate_entry_control_flow(address, original, bitness)
        validate_entry_control_flow(address, raw, bitness, inline_jump=True)
        return
    try:
        window = memory.read(address, len(raw) + _ENTRY_PATCH_TAIL)
    except Exception as exc:
        raise HookError(
            "Entry patch cuts an instruction that cannot be fully read "
            "back for validation.") from exc
    if len(window) < len(raw) or bytes(window[:len(raw)]) != original:
        raise HookError(
            "Entry patch bytes changed before validation; recompile without mutating.")
    boundary = 0
    for instruction in Decoder(bitness, window, ip=address):
        if instruction.is_invalid:
            raise HookError("Entry patch cuts or contains an invalid instruction.")
        boundary += instruction.len
        if boundary >= len(raw):
            break
    if boundary < len(raw):
        raise HookError(
            "Entry patch boundary cannot be resolved in the target instruction stream.")
    post = raw + bytes(window[len(raw):boundary])
    decoded = 0
    for instruction in Decoder(bitness, post, ip=address):
        if instruction.is_invalid:
            raise HookError("Entry patch cuts or contains an invalid instruction.")
        if instruction.flow_control in {FlowControl.CALL, FlowControl.INDIRECT_CALL,
                                        FlowControl.INTERRUPT, FlowControl.EXCEPTION}:
            raise HookError(
                "Calls/interrupts in entry instructions need a stronger return-context proof.")
        decoded += instruction.len
    if decoded != len(post):
        raise HookError("Entry patch does not end on an instruction boundary.")


def _serialize(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _range(address: int, size: int, limit: int = MAX_HOOK_ALLOCATION) -> None:
    if (type(address) is not int or type(size) is not int or not 0 < size <= limit
            or not 0 < address <= 0x7FFFFFFFFFFF or size - 1 > 0x7FFFFFFFFFFF - address):
        raise HookError("Invalid or oversized hook range.")


def _hex(value: Any, maximum: int) -> bytes:
    if (not isinstance(value, str) or not value or len(value) > maximum * 2
            or len(value) % 2 or not re.fullmatch(r"[0-9a-fA-F]+", value)):
        raise HookError("Linked block bytes must be complete bounded hexadecimal pairs.")
    return bytes.fromhex(value)


def _overlap(first: tuple[int, int], second: tuple[int, int]) -> bool:
    return first[0] < second[0] + second[1] and second[0] < first[0] + first[1]


_EXTERNAL_LITERAL_ISSUER = object()


def _rw_inventory(memory, address, size):
    """Actual complete PAGE_READWRITE regions; neither JSON nor flags qualify."""
    _range(address, size, MAX_ENTRY_BYTES)
    query = getattr(memory, "_query", None)
    if not callable(query):
        raise HookError("External literals require actual backend region evidence.")
    cursor, end, result = address, address + size, []
    while cursor < end:
        if len(result) >= 256:
            raise HookError("External literal region inventory exceeds its bound.")
        region = query(cursor)
        base, length = int(region.BaseAddress or 0), int(region.RegionSize)
        values = (base, int(region.AllocationBase or 0), length,
                  int(region.State), int(region.Protect), int(region.Type))
        if (not base <= cursor < base + length or length <= 0
                or values[3] != 0x1000 or values[4] != 0x04):
            raise HookError("External literals require intact committed PAGE_READWRITE memory.")
        result.append(values)
        cursor = min(end, base + length)
    return tuple(result)


@dataclass(frozen=True)
class _ExternalLiteralPermit:
    """Ephemeral canonical-link capability; serialized diagnostics are inert."""
    _issuer: Any
    memory: Any
    identity: tuple[int, int]
    pointer_size: int
    program_json: bytes
    source_sha256: str
    address: int
    original: bytes
    replacement: bytes
    inventory: tuple

    def verify(self, memory, block=None):
        if (self._issuer is not _EXTERNAL_LITERAL_ISSUER or self.memory is not memory
                or self.identity != memory.identity or self.pointer_size != memory.pointer_size
                or not memory.is_alive()):
            raise HookError("External literal permit is absent or target-bound evidence changed.")
        if block is not None and (block.get("address") != self.address
                or _hex(block.get("original"), MAX_ENTRY_BYTES) != self.original
                or _hex(block.get("bytes"), MAX_ENTRY_BYTES) != self.replacement):
            raise HookError("Linked bytes differ from the sealed external literal source.")
        if _rw_inventory(memory, self.address, len(self.original)) != self.inventory:
            raise HookError("External literal region identity or protection changed.")


def _seal_external_literals(memory, program, blocks):
    # Called only by the first-party canonical linker after literal emission
    # and NASM metadata are checked. No public source flag can request this.
    from .aa_program import validate_program, _pure_literal_profile
    validate_program(program)
    if not _pure_literal_profile(program) or not blocks or any(
            item["is_allocation"] or not item["literal_data"] for item in blocks):
        raise HookError("Mixed code/external-data programs need a common stronger proof profile.")
    canonical = _serialize(program)
    permits = []
    for item in blocks:
        original, replacement = _hex(item["original"], MAX_ENTRY_BYTES), _hex(item["bytes"], MAX_ENTRY_BYTES)
        inventory = _rw_inventory(memory, item["address"], len(original))
        permit = _ExternalLiteralPermit(_EXTERNAL_LITERAL_ISSUER, memory, memory.identity,
            memory.pointer_size, canonical, program["source_sha256"], item["address"],
            original, replacement, inventory)
        permit.verify(memory, item)
        permits.append(permit)
    return tuple(permits)


class HookManager:
    """Own one activation, its staged allocations, patches and durable receipt.

    Instantiate only after the controller claims its shared target lock. The
    journal path must be new. It records allocation intent before allocation,
    code bytes before staging, and original/changed entries before publication.
    Any uncertainty after a mutation preserves the journal and forbids retry.
    Neither table Lua nor scripts receive this object or its coordinator.
    """

    def __init__(self, memory: Any, journal_path: Path | str,
                 coordinator: HookCoordinator | None = None, owner_id: str = "",
                 *, owned_data_ranges: Sequence[tuple[int, int]] = (),
                 owned_executable_data_ranges: Sequence[tuple[int, int, int, int]] = (),
                 publication_guard=None):
        if publication_guard is not None and not callable(publication_guard):
            raise HookError('Publication guards must be controller-owned callbacks')
        self.publication_guard=publication_guard
        self.memory = memory
        self.path = Path(journal_path)
        self.coordinator = coordinator
        self.owner_id = owner_id or uuid.uuid4().hex
        if not isinstance(owned_data_ranges, (list, tuple)) or len(owned_data_ranges) > MAX_HOOK_ALLOCATIONS:
            raise HookError("Invalid controller-owned data range proof.")
        for start, length in owned_data_ranges:
            _range(start, length)
        # This is supplied by the owning controller from its live allocation
        # receipts, never from CT JSON capability flags.
        self.owned_data_ranges = tuple(owned_data_ranges)
        if (not isinstance(owned_executable_data_ranges, (list, tuple))
                or len(owned_executable_data_ranges) > MAX_HOOK_BLOCKS):
            raise HookError("Invalid controller-owned executable literal ranges.")
        for item in owned_executable_data_ranges:
            if not isinstance(item, _LiteralDataPermit) or item._issuer.memory is not memory:
                raise HookError("Executable literals require a live issuer permit, not serialized bounds.")
            start, size, allocation_start, allocation_size = item
            _range(start, size)
            _range(allocation_start, allocation_size)
            if not allocation_start <= start or start + size > allocation_start + allocation_size:
                raise HookError("Executable literal proof lies outside its owning allocation.")
        for index, item in enumerate(owned_executable_data_ranges):
            if any(_overlap(item[:2], other[:2]) for other in owned_executable_data_ranges[:index]):
                raise HookError("Controller literal ranges overlap or have ambiguous ownership.")
        self.owned_executable_data_ranges = tuple(owned_executable_data_ranges)
        if not isinstance(self.owner_id, str) or not 1 <= len(self.owner_id) <= 256:
            raise HookError("Invalid hook activation owner.")
        if not memory.is_alive():
            raise HookError("The hook target has exited.")
        self.identity = memory.identity
        self._external_literal_permits = ()
        self.allocations: dict[str, dict[str, Any]] = {}
        self.entries: list[dict[str, Any]] = []
        self.blocks: list[dict[str, Any]] = []
        self.exports: dict[str, int] = {}
        self.state = "preparing"
        self.data_commit = False
        self.uncertain = False
        self._last_bytes: bytes | None = None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._save(initial=True)

    def _document(self) -> dict:
        result = {"schema": 1, "engine": "ct2trainer-hooks", "owner": self.owner_id,
                "target_pid": self.identity[0], "target_created": self.identity[1],
                "state": self.state, "uncertain": self.uncertain,
                "data_commit": self.data_commit,
                "allocations": self.allocations,
                "blocks": [block for block in self.blocks if block["is_allocation"]],
                "entries": self.entries, "exports": self.exports,
                "owned_data_ranges": self.owned_data_ranges,
                "owned_executable_data_ranges": self.owned_executable_data_ranges,
                "retirement_policy": "retain-published-allocations-until-target-exit"}
        if self._external_literal_permits and self.entries:
            result["external_data_program"] = json.loads(self._external_literal_permits[0].program_json)
        return result

    def _verify_journal(self) -> None:
        try:
            size = self.path.stat().st_size
            if size > MAX_JOURNAL_BYTES or self.path.read_bytes() != self._last_bytes:
                raise HookUncertain("The hook journal changed externally; writes are blocked.")
        except OSError as exc:
            raise HookUncertain("The hook journal is missing or unreadable; writes are blocked.") from exc

    def _save(self, initial: bool = False) -> None:
        data = _serialize(self._document())
        if len(data) > MAX_JOURNAL_BYTES:
            raise HookError("The hook journal exceeded its byte budget.")
        if initial:
            try:
                descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except OSError as exc:
                raise HookError("A hook journal already exists or cannot be claimed.") from exc
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
            except Exception as exc:
                self.uncertain = True
                raise HookUncertain("The new hook journal could not be durably written.") from exc
        else:
            self._verify_journal()
            temporary = self.path.with_name(self.path.name + "." + uuid.uuid4().hex + ".tmp")
            try:
                descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                self._verify_journal()
                os.replace(temporary, self.path)
            except Exception as exc:
                self.uncertain = True
                raise HookUncertain("The hook journal update is uncertain; preserve all evidence.") from exc
            finally:
                if temporary.exists():
                    temporary.unlink()
        self._last_bytes = data

    def _guard(self, *, check_data_issuers: bool = True) -> None:
        if self.uncertain:
            raise HookUncertain("A prior hook mutation is uncertain; restart the target before recovery.")
        try:
            self._verify_journal()
            if self.memory.identity != self.identity or not self.memory.is_alive():
                raise HookUncertain("The hook target identity changed or exited.")
            if check_data_issuers and self.state not in {"retired", "abandoned"}:
                for permit in self._external_literal_permits:
                    permit.verify(self.memory)
            if check_data_issuers and self.state not in {"retired", "abandoned"}:
                self._check_literal_issuers()
                for start, size in self._literal_exclusions():
                    try:
                        self._verify_allocation_protection(start, size, executable=True, writable=True)
                    except Exception as exc:
                        raise HookUncertain("Executable literal owner protection or allocation changed.") from exc
        except HookUncertain:
            self.uncertain = True
            raise

    def _check_literal_issuers(self) -> None:
        permits = self._used_literal_permits()
        if not permits:
            return
        context = getattr(_issuer_checks, "context", None)
        outer = context is None
        if outer:
            context = {"stack": [], "checked": set()}
            _issuer_checks.context = context
        identity = id(self)
        if identity in context["stack"] or len(context["stack"]) >= MAX_LITERAL_ISSUER_DEPTH:
            if outer:
                del _issuer_checks.context
            raise HookUncertain("Literal issuer dependency cycle or depth bound exceeded.")
        context["stack"].append(identity)
        try:
            issuers = {id(item._issuer): item._issuer for item in permits}
            for owner, issuer in issuers.items():
                if owner not in context["checked"]:
                    issuer.check_entries()
                    context["checked"].add(owner)
        finally:
            context["stack"].pop()
            if outer:
                del _issuer_checks.context

    def _fail_uncertain(self, error: Exception) -> HookUncertain:
        self.uncertain = True
        self.state = "uncertain"
        try:
            self._save()
        except Exception:
            # The previous durable intent still describes the possibly changed
            # memory. Never overwrite an externally changed or missing journal.
            pass
        return HookUncertain(f"Hook mutation is uncertain; retain journal and restart target: {error}")

    def allocate(self, name: str, size: int, near: int | None = None,
                 executable: bool = True, writable: bool = False) -> int:
        self._guard()
        if self.state != "preparing":
            raise HookError("Allocations are admitted only before hook staging.")
        if (not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.$]*", name)
                or name.casefold() in self.allocations or type(executable) is not bool
                or type(writable) is not bool):
            raise HookError("Invalid, duplicate, or case-ambiguous allocation name.")
        if type(size) is not int or not 0 < size <= MAX_HOOK_ALLOCATION:
            raise HookError("Owned hook allocations require 1 byte to 4 MiB.")
        # Charge a conservative 64 KiB minimum before allocation; actual rounded
        # size is charged afterwards. This also bounds reserve-granularity use.
        charged = (size + 65535) // 65536 * 65536
        if (len(self.allocations) >= MAX_HOOK_ALLOCATIONS
                or charged + sum(a["budget_size"] for a in self.allocations.values()) > MAX_HOOK_BYTES):
            raise HookError("Retained hook allocation budget exhausted; restart the target.")
        if near is not None:
            _range(near, 1)
        key = name.casefold()
        allocation = {"address": None, "size": size, "budget_size": charged,
                      "near": near, "executable": executable, "writable": writable,
                      "actual_size": None, "literal_data_ranges": [],
                      "state": "allocation-intent"}
        self.allocations[key] = allocation
        self._save()
        try:
            self._guard()
            broker_checkpoint()
            address = self.memory.allocate(size, near=near)
            _range(address, size)
            if any(other["address"] is not None
                   and _overlap((address, size), (other["address"], other["size"]))
                   for other_key, other in self.allocations.items() if other_key != key):
                raise HookError("A new allocation overlaps another owned range.")
            actual = self.memory.allocation_size(address)
            if type(actual) is not int or actual < size:
                raise HookError("Owned allocation size could not be verified.")
            allocation.update(address=address, actual_size=actual,
                              budget_size=max(charged, actual), state="allocated")
            if sum(a["budget_size"] for a in self.allocations.values()) > MAX_HOOK_BYTES:
                raise HookError("Actual remote allocations exceed the retained byte budget.")
            self._save()
            return address
        except Exception as exc:
            raise self._fail_uncertain(exc) from exc

    def allocation_map(self) -> dict[str, dict[str, Any]]:
        self._guard()
        return {name: {key: allocation[key] for key in ("address", "size", "executable", "writable")}
                for name, allocation in self.allocations.items() if allocation["address"] is not None}

    def _normalize(self, blocks: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        if not isinstance(blocks, (list, tuple)) or not blocks or len(blocks) > MAX_HOOK_BLOCKS:
            raise HookError("A hook needs a bounded nonempty linked block list.")
        result: list[dict[str, Any]] = []
        total = 0
        literal_count = 0
        for block in blocks:
            if not isinstance(block, Mapping):
                raise HookError("Invalid linked block.")
            raw = _hex(block.get("bytes"), MAX_HOOK_ALLOCATION)
            total += len(raw)
            if total > MAX_HOOK_BYTES:
                raise HookError("Linked hook blocks exceed the total byte budget.")
            original = _hex(block.get("original"), MAX_HOOK_ALLOCATION)
            address = block.get("address")
            _range(address, len(raw))
            if len(original) != len(raw):
                raise HookError("Every linked block needs exact original bytes of equal size.")
            for key in ("is_allocation", "executable", "requires_coordinator"):
                if type(block.get(key)) is not bool:
                    raise HookError("Linked block capability flags must be explicit booleans.")
            for key in ("literal_data", "data_semantics"):
                if key in block and type(block[key]) is not bool:
                    raise HookError("Linked literal classification must use explicit booleans.")
            permit = next((item for item in self._external_literal_permits
                           if item.address == address), None)
            if ("external_data" in block or "external_source_sha256" in block) and permit is None:
                raise HookError("Serialized external-data diagnostics cannot mint a live permit.")
            if permit is not None:
                permit.verify(self.memory, block)
                if (block["is_allocation"] or block["executable"] or not block["requires_coordinator"]
                        or block.get("literal_data") is not True or block.get("data_semantics", False)):
                    raise HookError("External literal block classification differs from its sealed permit.")
            data_semantics = False
            data_allocation = None
            allocation = next((name for name, item in self.allocations.items()
                               if item["address"] is not None and item["address"] <= address
                               and address + len(raw) <= item["address"] + item["size"]), None)
            if block["is_allocation"] != (allocation is not None):
                raise HookError("Linked allocation ownership differs from owned remote ranges.")
            if allocation is None:
                if len(raw) > MAX_ENTRY_BYTES:
                    raise HookError("Every live entry patch needs a bounded range.")
                if any(item["address"] is not None
                       and _overlap((address, len(raw)), (item["address"], item["size"]))
                       for item in self.allocations.values()):
                    raise HookError("A live entry patch partially overlaps an owned allocation.")
                executable = block["executable"] or self.memory.is_executable(address, len(raw))
                if permit is not None and executable:
                    raise HookError("External literal protection became executable before staging.")
                literal_owner = next((item for item in self.owned_executable_data_ranges
                                      if item[0] <= address and address + len(raw) <= item[0] + item[1]), None)
                if (executable and literal_owner is not None and block.get("literal_data") is True
                        and block.get("data_semantics") is True):
                    if not block["requires_coordinator"]:
                        raise HookError("Executable literal writes always require a held coordinator.")
                    data_semantics = True
                    data_allocation = literal_owner[2:]
                    literal_owner._issuer.check_entries()
                    self._verify_allocation_protection(*data_allocation, executable=True, writable=True)
                if not block["requires_coordinator"] and (executable or not any(
                        start <= address and address + len(raw) <= start + length
                        for start, length in self.owned_data_ranges)):
                    raise HookError("Uncoordinated writes require controller-proven owned nonexecutable data.")
                if executable and not data_semantics:
                    try:
                        validate_instruction_boundary(address, original, self.memory.pointer_size * 8)
                        validate_entry_control_flow(address, raw, self.memory.pointer_size * 8,
                                                    inline_jump=True)
                    except HookError:
                        # Only linked blocks whose AA source is a deliberate
                        # byte-patch prefix (verified live at link time) may
                        # cut their first original instruction; every other
                        # block keeps the strict complete-instruction contract.
                        if block.get("prefix_cut") is not True:
                            raise
                        validate_entry_prefix_cut(self.memory, address, raw, original,
                                                 self.memory.pointer_size * 8)
            else:
                executable = block["executable"]
                if executable and not self.allocations[allocation]["executable"]:
                    raise HookError("Executable bytes cannot be staged in a data-only allocation.")
            literal_ranges = block.get("literal_data_ranges", [])
            if not isinstance(literal_ranges, (list, tuple)) or len(literal_ranges) > MAX_HOOK_BLOCKS:
                raise HookError("Invalid source-derived literal span list.")
            literal_count += len(literal_ranges)
            if literal_count > MAX_HOOK_BLOCKS:
                raise HookError("Source-derived literal spans exceed the bounded total count.")
            if allocation is None and literal_ranges:
                raise HookError("External blocks cannot mint provider literal provenance.")
            normalized_ranges = []
            for item in literal_ranges:
                if not isinstance(item, Mapping) or not isinstance(item.get("allocation"), str):
                    raise HookError("Literal span needs its actual allocation name.")
                start, size = item.get("address"), item.get("size")
                _range(start, size)
                if (item["allocation"].casefold() != allocation or not address <= start
                        or start + size > address + len(raw)):
                    raise HookError("Source-derived literal span exceeds its block or allocation.")
                if any(_overlap((start, size), (other["address"], other["size"]))
                       for other in normalized_ranges):
                    raise HookError("Source-derived literal spans overlap.")
                normalized_ranges.append({"address": start, "size": size, "allocation": allocation})
            if any(_overlap((address, len(raw)), (item["address"], len(bytes.fromhex(item["bytes"]))))
                   for item in result):
                raise HookError("Linked hook blocks overlap.")
            result.append({"address": address, "bytes": raw.hex(), "original": original.hex(),
                           "is_allocation": block["is_allocation"], "executable": executable,
                           "requires_coordinator": block["requires_coordinator"],
                           "literal_data": block.get("literal_data", False),
                           "literal_data_ranges": normalized_ranges,
                           "data_semantics": data_semantics, "data_allocation": data_allocation,
                           "allocation": allocation})
            if permit is not None:
                result[-1].update(external_data=True, external_source_sha256=permit.source_sha256)
        return result

    def stage(self, blocks: Sequence[Mapping[str, Any]], exports: Mapping[str, int] | None = None,
              *, _external_literal_permits=()) -> None:
        """Stage all allocations and record exact live entries without publishing."""
        self._guard()
        if self.state != "preparing":
            raise HookError("A hook activation can be staged only once.")
        if _external_literal_permits:
            if (not isinstance(_external_literal_permits, tuple) or self.allocations
                    or len(_external_literal_permits) != len(blocks)
                    or any(not isinstance(item, _ExternalLiteralPermit) for item in _external_literal_permits)
                    or len({item.address for item in _external_literal_permits}) != len(blocks)
                    or len({item.program_json for item in _external_literal_permits}) != 1):
                raise HookError("Invalid or mixed external literal capability profile.")
            for permit in _external_literal_permits:
                permit.verify(self.memory)
            self._external_literal_permits = _external_literal_permits
            self.owned_data_ranges = ()
        try:
            normalized = self._normalize(blocks)
        except Exception:
            self._external_literal_permits = ()
            raise
        exports = dict(exports or {})
        if (any(not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.$]*", name)
                or type(address) is not int or not 0 < address <= 0x7FFFFFFFFFFF
                for name, address in exports.items())
                or len({name.casefold() for name in exports}) != len(exports)):
            raise HookError("Invalid or case-ambiguous exported symbols.")
        for block in normalized:
            original = bytes.fromhex(block["original"])
            if self.memory.read(block["address"], len(original)) != original:
                raise HookError("Linked bytes changed before staging; recompile without mutating.")
        self.blocks = normalized
        for name, allocation in self.allocations.items():
            allocation["literal_data_ranges"] = [dict(span) for block in normalized
                if block["allocation"] == name for span in block["literal_data_ranges"]]
        self.entries = [dict(block, state="unpublished") for block in normalized if not block["is_allocation"]]
        # Candidate permits were collected across active providers for linking.
        # Only actual literal borrowers retain a lease after normalization.
        self.owned_executable_data_ranges = self._used_literal_permits()
        self.exports = exports
        self.state = "staging-intent"
        self._save()
        try:
            for block in normalized:
                if not block["is_allocation"]:
                    continue
                self._guard()
                raw, original = bytes.fromhex(block["bytes"]), bytes.fromhex(block["original"])
                if self.memory.read(block["address"], len(original)) != original:
                    raise HookError("Owned staging bytes changed immediately before write.")
                broker_checkpoint()
                self.memory.write(block["address"], raw)
                if self.memory.read(block["address"], len(raw)) != raw:
                    raise HookError("Owned staged bytes did not verify.")
            for allocation in self.allocations.values():
                broker_checkpoint()
                self._guard()
                self.memory.protect_allocation(allocation["address"], executable=allocation["executable"],
                                               writable=allocation["writable"])
                allocation["state"] = "staged"
                self._save()
            self.state = "staged"
            self._save()
        except Exception as exc:
            raise self._fail_uncertain(exc) from exc

    def _coordinated(self) -> AbstractContextManager[QuiescenceProof]:
        if self._external_literal_permits:
            if (self.allocations or not self.entries
                    or any(not item.get("external_data", False) for item in self.entries)):
                raise HookError("Mixed code/external-data profiles are not admitted.")
            hold = getattr(self.coordinator, "hold_data", None)
            if not callable(hold):
                raise HookError("External literals require an actual held data coordinator.")
            return hold(self.memory, self._entry_ranges())
        if (all(not item["requires_coordinator"] for item in self.entries)
                and all(not allocation["executable"] for allocation in self.allocations.values())):
            # RW flags in known owned allocations have the same non-atomic data
            # contract as ordinary numeric value writes. No thread stop is
            # claimed or needed. The controller provenance was checked in stage.
            return nullcontext(QuiescenceProof(self.identity, tuple(self._entry_ranges()),
                "controller-owned-RW-data-only", lambda: self.memory.identity == self.identity
                and self.memory.is_alive()
                and all(not self.memory.is_executable(item["address"], len(bytes.fromhex(item["bytes"])))
                        for item in self.entries)
                and all(not self.memory.is_executable(allocation["address"], allocation["size"])
                        for allocation in self.allocations.values())))
        if self.coordinator is None:
            raise HookError("Executable/live hooks require a verified target quiescence coordinator.")
        ranges = [(item["address"], len(bytes.fromhex(item["bytes"]))) for item in self.entries]
        if callable(getattr(self.coordinator, "hold_entries", None)):
            # Immutable, first-party receipt bytes. CT data cannot supply code
            # spans or bypass original-instruction validation in the debugger.
            windows = [(item, (item["address"], bytes.fromhex(item["original"]),
                             bytes.fromhex(item["bytes"]), bytes.fromhex(item[
                                 "bytes" if self.state == "enabled" else "original"])))
                       for item in self.entries]
            literals = tuple(window for item, window in windows if item["data_semantics"])
            code = tuple(window for item, window in windows if not item["data_semantics"])
            if literals:
                exclusions = self._literal_exclusions()
                for start, size in exclusions:
                    self._verify_allocation_protection(start, size, executable=True, writable=True)
                return self.coordinator.hold_entries(self.memory, code, literal_windows=literals,
                                                     exclusion_ranges=exclusions)
            return self.coordinator.hold_entries(self.memory, code)
        if any(item["data_semantics"] for item in self.entries):
            raise HookError("Executable literals need a coordinator that verifies owned data receipts.")
        return self.coordinator.hold(self.memory, ranges)

    def _entry_ranges(self) -> list[tuple[int, int]]:
        return [(item["address"], len(bytes.fromhex(item["bytes"]))) for item in self.entries]

    def _literal_exclusions(self) -> tuple[tuple[int, int], ...]:
        return tuple(sorted({tuple(item["data_allocation"]) for item in self.entries
                             if item["data_semantics"]}))

    def _used_literal_permits(self) -> tuple[_LiteralDataPermit, ...]:
        return tuple(permit for permit in self.owned_executable_data_ranges if any(
            item["data_semantics"] and tuple(item["data_allocation"]) == tuple(permit[2:])
            and permit[0] <= item["address"]
            and item["address"] + len(bytes.fromhex(item["bytes"])) <= permit[0] + permit[1]
            for item in self.entries))

    def depends_on_provider(self, provider: Any) -> bool:
        """Expose actual live literal ownership to controller cleanup ordering."""
        return self.state == "enabled" and any(permit._issuer is provider
                                                for permit in self._used_literal_permits())

    def _required_ranges(self) -> list[tuple[int, int]]:
        return self._entry_ranges() + list(self._literal_exclusions())

    def _verify_allocation_protection(self, address, size, *, executable, writable) -> None:
        """Inspect the held owned allocation, including every actual page.

        ProcessMemory's private query is a first-party backend interface. A
        backend without the actual protection query cannot mint this permit.
        """
        query = getattr(self.memory, "_query", None)
        if not callable(query) or self.memory.allocation_size(address) != size:
            raise HookError("Literal provenance needs an intact owned allocation protection proof.")
        protection = (0x40 if writable else 0x20) if executable else 0x04
        with getattr(self.memory, "_lock", nullcontext()):
            cursor = address
            while cursor < address + size:
                region = query(cursor)
                end = int(region.BaseAddress or 0) + region.RegionSize
                if (region.State != 0x1000 or int(region.AllocationBase or 0) != address
                        or region.Protect != protection or not int(region.BaseAddress or 0) <= cursor < end):
                    raise HookError("Owned allocation identity or protection changed.")
                cursor = min(address + size, end)

    def _check_allocation_guards(self) -> None:
        """Guard executable bodies and padding, leaving only declared data mutable."""
        try:
            for name, allocation in self.allocations.items():
                if not allocation["executable"]:
                    continue
                start, size = allocation["address"], allocation["actual_size"]
                self._verify_allocation_protection(start, size, executable=True,
                                                   writable=allocation["writable"])
                expected = bytearray(size)  # Owned VirtualAllocEx zero-filled padding.
                for block in self.blocks:
                    if block["allocation"] == name:
                        raw = bytes.fromhex(block["bytes"])
                        offset = block["address"] - start
                        expected[offset:offset + len(raw)] = raw
                observed = self.memory.read(start, size)
                if len(observed) != size:
                    raise HookError("Owned executable allocation body could not be read exactly.")
                holes = sorted((item["address"] - start, item["size"])
                               for item in allocation["literal_data_ranges"]
                               if allocation["writable"])
                cursor = 0
                for offset, length in holes + [(size, 0)]:
                    if observed[cursor:offset] != expected[cursor:offset]:
                        raise HookError("Immutable owned cave code or padding changed externally.")
                    cursor = offset + length
        except Exception as exc:
            raise self._fail_uncertain(exc) from exc

    def data_ranges(self) -> tuple[tuple[int, int, int, int], ...]:
        """Return guarded literal permits only from this enabled provider.

        Source literal spans are precise byte holes, not writable code-page
        permissions. The owning controller passes them directly to its children.
        """
        self.check_entries()
        return tuple(_LiteralDataPermit(self, item["address"], item["size"],
                                       allocation["address"], allocation["actual_size"])
            for allocation in self.allocations.values()
            if allocation["executable"] and allocation["writable"] and allocation["state"] == "published"
            for item in allocation["literal_data_ranges"])

    def _write_entry(self, item, desired, expected, proof, *, rollback=False, on_admit=None):
        def admit():
            self._guard()
            proof.verify(self.memory, self._required_ranges())
            permit = next((p for p in self._external_literal_permits if p.address == item["address"]), None)
            if permit is not None:
                permit.verify(self.memory, item)
            if self.memory.read(item["address"], len(expected)) != expected:
                raise HookError("Exact entry bytes changed at the final kernel write boundary.")
            # A slow byte/region/identity read may outlast the held lease.
            proof.verify(self.memory, self._required_ranges())
            if not rollback:
                broker_checkpoint()
            if proof.check() is not True:
                raise HookError("The held write lease expired before the kernel mutation.")
            if on_admit is not None:
                on_admit()
        _checked_write(self.memory, item["address"], desired,
                       before_kernel=admit, rollback=rollback)

    @restoration_entry
    def publish(self) -> dict:
        """Install staged live entries while the verified safe point remains held."""
        self._guard()
        if self.state != "staged":
            raise HookError("Only fully staged hooks can be published.")
        # Provider-only code can expose executable addresses to children and
        # requires coordination. Proven RW-only data uses its separate permit.
        broker_checkpoint()
        context = self._coordinated()
        attempted: list[dict[str, Any]] = []
        mutation_started = False
        def mutation_admitted():
            nonlocal mutation_started
            mutation_started = True
        verified_rollback_error: HookError | None = None
        try:
            with context as proof:
                if not isinstance(proof, QuiescenceProof):
                    raise HookError("The coordinator did not supply a valid safe-point proof.")
                proof.verify(self.memory, self._required_ranges())
                self._check_allocation_guards()
                for item in self.entries:
                    original = bytes.fromhex(item["original"])
                    if self.memory.read(item["address"], len(original)) != original:
                        raise HookError("The live entry guard changed before hook publication.")
                if self.publication_guard is not None:
                    self.publication_guard()
                    proof.verify(self.memory, self._required_ranges())
                broker_checkpoint()
                self.state = "publication-intent"
                self._save()
                try:
                    for item in self.entries:
                        broker_checkpoint()
                        self._guard()
                        proof.verify(self.memory, self._required_ranges())
                        original, raw = bytes.fromhex(item["original"]), bytes.fromhex(item["bytes"])
                        if self.memory.read(item["address"], len(original)) != original:
                            raise HookError("The live entry changed immediately before publication.")
                        broker_checkpoint()
                        attempted.append(item)
                        self._write_entry(item, raw, original, proof, on_admit=mutation_admitted)
                        if self.memory.read(item["address"], len(raw)) != raw:
                            raise HookError("Published entry bytes did not verify.")
                        item["state"] = "installed"
                        self._save()
                    proof.verify(self.memory, self._required_ranges())
                    self._guard()
                    for item in self.entries:
                        if self.memory.read(item["address"], len(bytes.fromhex(item["bytes"]))) != bytes.fromhex(item["bytes"]):
                            raise HookError("An entry changed before final publication confirmation.")
                    for allocation in self.allocations.values():
                        allocation["state"] = "published"
                    self.state = "enabled"
                    self._save()
                    broker_checkpoint()
                except Exception as exc:
                    # Rollback is permitted only while the same safe point and
                    # exact full previous/replacement bytes are still verified.
                    try:
                        with restoration_region(self._guard,_clock_for(self)):
                            proof.verify(self.memory, self._required_ranges())
                            self._guard()
                            for item in reversed(attempted):
                                original, raw = bytes.fromhex(item["original"]), bytes.fromhex(item["bytes"])
                                current = self.memory.read(item["address"], len(raw))
                                if current == original:
                                    continue
                                if current != raw:
                                    raise HookError("A partial/foreign entry cannot be safely rolled back.")
                                proof.verify(self.memory, self._required_ranges())
                                self._write_entry(item, original, raw, proof, rollback=True)
                                if self.memory.read(item["address"], len(original)) != original:
                                    raise HookError("Entry rollback did not verify.")
                                item["state"] = "unpublished"
                            if self._external_literal_permits:
                                # No code/caves can remain reachable in this profile.
                                # Exact compensation uses the same live permits and
                                # held lease, without the expired ordinary deadline.
                                for permit in self._external_literal_permits:
                                    permit.verify(self.memory)
                                    if self.memory.read(permit.address, len(permit.original)) != permit.original:
                                        raise HookError("External literal compensation is not exact.")
                                proof.verify(self.memory, self._required_ranges())
                                if proof.check() is not True:
                                    raise HookError("External literal compensation lease expired.")
                                self.state = "abandoned"
                                self.exports = {}
                            else:
                                self.state = "retired" if mutation_started else "staged"
                            for allocation in self.allocations.values():
                                allocation["state"] = "retained" if mutation_started else "staged"
                            self._save()
                    except Exception as rollback_error:
                        raise self._fail_uncertain(HookError(f"{exc}; rollback: {rollback_error}")) from exc
                    verified_rollback_error = HookError(
                        f"Hook publication failed; exact original entries verified: {exc}")
                    raise verified_rollback_error from exc
        except HookUncertain:
            raise
        except Exception as exc:
            # Release failures after writes may leave the safe point held or
            # incomplete; keep receipt even if the entry bytes look correct.
            if mutation_started and exc is not verified_rollback_error:
                raise self._fail_uncertain(exc) from exc
            raise
        return self.receipt()

    @restoration_entry
    def commit(self) -> None:
        """Publish an allocation-only hook that owns no live entries.

        Retained global storage without a literal initializer writes no target
        bytes at publication time; its only publication path is this commit.
        The exact journal, identity, liveness and allocation-protection gates
        of stage/publish still apply.  A hook that already staged entries or
        exports must not mix this path with a normal publication.
        """
        self._guard()
        if self.state != "preparing":
            raise HookError("A hook activation can be committed only once.")
        if not self.allocations:
            raise HookError("An allocation-only commit needs an owned allocation.")
        if (self.entries or self.blocks or self.exports
                or self._external_literal_permits):
            raise HookError("Allocation-only commits cannot mix live entries or exports.")
        try:
            self.state = "publication-intent"
            self._save()
            for allocation in self.allocations.values():
                broker_checkpoint()
                self._guard()
                self.memory.protect_allocation(allocation["address"],
                                               executable=allocation["executable"],
                                               writable=allocation["writable"])
                allocation["state"] = "staged"
                self._save()
            for allocation in self.allocations.values():
                allocation["state"] = "published"
            self.state = "enabled"
            self._save()
            broker_checkpoint()
        except Exception as exc:
            raise self._fail_uncertain(exc) from exc

    def receipt(self) -> dict:
        self._guard()
        return json.loads(_serialize(self._document()))

    def check_entries(self) -> None:
        """Verify current enabled entries before another controller action."""
        self._guard()
        if self.state != "enabled":
            raise HookError("Only confirmed enabled entries can be checked.")
        for item in self.entries:
            raw = bytes.fromhex(item["bytes"])
            if self.memory.read(item["address"], len(raw)) != raw:
                raise self._fail_uncertain(HookError(
                    "An owned hook entry changed externally; further writes are blocked."))
        self._check_allocation_guards()

    def commit_data_only(self) -> None:
        """Commit confirmed numeric literal values without an active undo record.

        The terminal journal remains durable evidence. Its parent allocation
        journal remains the executable gate, while this receipt may outlive an
        orderly parent retirement without claiming the old numeric value is on.
        """
        self._guard()
        if (self.state != "enabled" or self.allocations or self.exports or not self.entries
                or any(not item["data_semantics"] or not item["executable"]
                       or not item["requires_coordinator"] for item in self.entries)):
            raise HookError("Only an enabled, allocation-free proven literal transaction can commit data.")
        transition = False
        try:
            with self._coordinated() as proof:
                if not isinstance(proof, QuiescenceProof):
                    raise HookError("The coordinator did not supply a valid safe-point proof.")
                proof.verify(self.memory, self._required_ranges())
                self.check_entries()
                self.state = "data-commit-intent"
                transition = True
                self._save()
                proof.verify(self.memory, self._required_ranges())
                self._guard()
                for item in self.entries:
                    raw = bytes.fromhex(item["bytes"])
                    if self.memory.read(item["address"], len(raw)) != raw:
                        raise HookUncertain("Numeric literal changed before durable data commit.")
                    item["state"] = "committed"
                self.data_commit = True
                self.state = "abandoned"
                self._save()
                proof.verify(self.memory, self._required_ranges())
        except Exception as exc:
            if transition or isinstance(exc, HookUncertain):
                raise self._fail_uncertain(exc) from exc
            raise

    @restoration_entry
    def abandon_unpublished(self) -> None:
        with restoration_region(lambda: self._guard(check_data_issuers=False),
                                _clock_for(self)):
            self._abandon_unpublished_body()
        # The region's final exact journal/identity checks run while the
        # terminal receipt still exists. Do not recursively verify a journal
        # after this controller has deliberately removed that exact receipt.
        from .restoration_budget import checkpoint
        checkpoint(full=False)
        self.path.unlink()
        checkpoint(full=False)

    def _abandon_unpublished_body(self) -> None:
        """Reclaim staging pages only when no entry or export was published.

        This handles linker/preflight failures without imposing target restart.
        A hook that was published and then rolled back is retired instead and
        remains subject to target-exit reclamation, however brief publication was.
        """
        self._guard(check_data_issuers=False)
        if self.state not in {"preparing", "staged"} or any(
                item["state"] in {"installed", "restored"} for item in self.entries):
            raise HookError("Published or uncertain allocations cannot be abandoned.")
        if any(allocation["state"] in {"published", "retained"}
               for allocation in self.allocations.values()):
            raise HookError("Previously reachable executable allocations must remain until target exit.")
        self.state = "abandon-intent"
        self._save()
        try:
            for allocation in self.allocations.values():
                self._guard(check_data_issuers=False)
                if allocation["address"] is not None:
                    from .memory import _checked_release
                    _checked_release(self.memory, allocation["address"], allocation["size"],
                                     lambda: self._guard(check_data_issuers=False))
                allocation["state"] = "released-unpublished"
                self._save()
                broker_checkpoint()
            self.exports = {}
            self.state = "abandoned"
            self._save()
            self._verify_journal()
            broker_checkpoint()
        except Exception as exc:
            raise self._fail_uncertain(exc) from exc

    @restoration_entry
    def disable(self) -> None:
        """Restore exact owned entries and retain every published allocation."""
        with restoration_region(self._guard,_clock_for(self),emergency=False):
            self._guard()
            if self.state == "retired" or self.state == "abandoned" and self._external_literal_permits:
                return
            if self.state != "enabled":
                raise HookError("Only a confirmed enabled hook can be disabled.")
            mutation_started = False
            def mutation_admitted():
                nonlocal mutation_started
                mutation_started = True
            try:
                with self._coordinated() as proof:
                    if not isinstance(proof, QuiescenceProof):
                        raise HookError("The coordinator did not supply a valid safe-point proof.")
                    proof.verify(self.memory, self._required_ranges())
                    self._check_allocation_guards()
                    for item in self.entries:
                        raw = bytes.fromhex(item["bytes"])
                        if self.memory.read(item["address"], len(raw)) != raw:
                            raise HookUncertain("An owned hook entry changed externally; it will not be overwritten.")
                    broker_checkpoint()
                    self.state = "disable-intent"
                    self._save()
                    for item in reversed(self.entries):
                        self._guard()
                        proof.verify(self.memory, self._required_ranges())
                        raw, original = bytes.fromhex(item["bytes"]), bytes.fromhex(item["original"])
                        if self.memory.read(item["address"], len(raw)) != raw:
                            raise HookUncertain("The hook entry changed immediately before disable.")
                        broker_checkpoint()
                        self._write_entry(item, original, raw, proof, on_admit=mutation_admitted)
                        if self.memory.read(item["address"], len(original)) != original:
                            raise HookUncertain("Restored hook entry bytes did not verify.")
                        item["state"] = "restored"
                        self._save()
                    proof.verify(self.memory, self._required_ranges())
                    for allocation in self.allocations.values():
                        allocation["state"] = "retained"
                    self.state = "retired"
                    self.exports = {}
                    if self._external_literal_permits:
                        for permit in self._external_literal_permits:
                            permit.verify(self.memory)
                            if self.memory.read(permit.address, len(permit.original)) != permit.original:
                                raise HookUncertain("External literal undo changed before terminal confirmation.")
                        proof.verify(self.memory, self._required_ranges())
                        broker_checkpoint()
                        if proof.check() is not True:
                            raise HookUncertain("External literal terminal undo lease expired.")
                        # Allocation-free, non-code entries have no reachable cave
                        # lifetime. Exact held undo leaves a terminal inert receipt.
                        self.state = "abandoned"
                    self._save()
                    proof.verify(self.memory, self._required_ranges())
            except HookUncertain as exc:
                raise self._fail_uncertain(exc) from exc
            except Exception as exc:
                if mutation_started:
                    raise self._fail_uncertain(exc) from exc
                raise

    def finish_after_exit(self) -> None:
        """Remove our journal only after held PID/creation identity confirms exit."""
        self._verify_journal()
        if self.memory.identity != self.identity or self.memory.is_alive():
            raise HookError("Published allocation journals remain until the exact target has exited.")
        self.path.unlink()
        self.state = "target-exited"
