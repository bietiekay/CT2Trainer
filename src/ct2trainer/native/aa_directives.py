"""Stage-1 plan-operation contracts for the remaining AA directive families.

This lane models the five features the corpus feature matrix
(``tools/corpus_denominator/feature_matrix.py``) lists as missing/partial
without pinned corpus records (pure capacity contracts):

* ``aa_createthread_threadwait`` -> :class:`ThreadDirectiveModel`
  (``createThread`` / ``threadWait``)
* ``aa_protection_control`` -> :class:`ProtectionDirectiveModel`
  (``protect`` / ``unprotect``)
* ``aa_target_api_binding`` -> :class:`TargetApiDirectiveModel`
  (``getprocaddress`` / ``getmodulehandle``)
* ``aa_debugger_api`` -> :class:`DisassembleDirectiveModel`
  (``disassemble`` behind the injectable :class:`DisassemblerPort`)
* ``aa_sections_incomplete`` -> :func:`analyze_sections` /
  :func:`check_sections` (structural fail-closed contract)

The existing grammar (``aa.py`` / ``aa_program.py``) still rejects these
directives fail-closed and nothing in this module changes that behavior.
All target-side effects are routed through injectable backends; no process,
no network and no CE input is touched.

Open boundary: the disassembler contract is a dependency-inversion port
only. Conformance against a real disassembler stays open (AP-11/Root).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import json

from .pe_exports import (ExportResolutionError, MAX_IMAGE_SIZE,
                         resolve_remote_export)


SCHEMA = "ct2trainer-aa-directives/v1"
ADDRESS_LIMIT_32 = 0xFFFFFFFF
ADDRESS_LIMIT_64 = 0x7FFFFFFFFFFF


class AADirectivesError(ValueError):
    """Residual-directive contract violation; fail-closed, no partial plan."""


class ThreadError(AADirectivesError):
    def __init__(self, message, *, thread=None, address=None, polls=None):
        self.thread = thread
        self.address = address
        self.polls = polls
        super().__init__(message)


class ProtectionError(AADirectivesError):
    def __init__(self, message, *, address=None, size=None, page=None,
                 owner=None):
        self.address = address
        self.size = size
        self.page = page
        self.owner = owner
        super().__init__(message)


class TargetApiError(AADirectivesError):
    def __init__(self, message, *, module=None, export=None):
        self.module = module
        self.export = export
        super().__init__(message)


class DisassemblerError(AADirectivesError):
    def __init__(self, message, *, address=None, count=None, index=None):
        self.address = address
        self.count = count
        self.index = index
        super().__init__(message)


class SectionStructureError(AADirectivesError):
    def __init__(self, message, *, case=None, analysis=None, grammar=None):
        self.case = case
        self.analysis = analysis
        self.grammar = grammar
        super().__init__(message)


# ---------------------------------------------------------------------------
# createThread / threadWait
# ---------------------------------------------------------------------------

THREAD_CREATED = "created"
THREAD_RUNNING = "running"
THREAD_EXITED = "exited"
THREAD_LIFECYCLE = (THREAD_CREATED, THREAD_RUNNING, THREAD_EXITED)
MAX_THREADS = 256
MAX_THREAD_WAIT_POLLS = 4096


@dataclass(frozen=True)
class ThreadHandle:
    """Sequential thread identity: ordinal 1..N in creation order."""
    ordinal: int
    entry_address: int


@dataclass(frozen=True)
class ThreadPoll:
    """Deterministic completion event from the injected thread backend."""
    exited: bool
    exit_code: int = 0


class ThreadBackend(ABC):
    """Injectable thread backend; the plan flow is strictly sequential."""

    @abstractmethod
    def spawn(self, handle: "ThreadHandle") -> None:
        """Spawn acknowledgment; called once per plan thread while the
        thread is in the ``created`` state."""

    @abstractmethod
    def poll(self, handle: "ThreadHandle") -> "ThreadPoll":
        """Deterministic completion event; ``exited`` stays ``False``
        until the thread has exited."""


class ThreadDirectiveModel:
    """Plan-operation model for ``createThread(address)`` / ``threadWait``.

    Thread lifecycle is ``created -> running -> exited``. ``threadWait``
    blocks the plan flow until the injected backend reports a
    deterministic completion event. Thread identity is a single sequence
    (no race model). An unresolvable (non-integer or out-of-bounds) target
    address and a wait on an unknown thread are strict rejections.
    """

    def __init__(self, backend, *, bitness=64, max_threads=MAX_THREADS,
                 max_wait_polls=MAX_THREAD_WAIT_POLLS):
        if type(bitness) is not int or bitness not in (32, 64):
            raise ThreadError("Thread plan supports only 32/64-bit targets")
        if (backend is None
                or not callable(getattr(backend, "spawn", None))
                or not callable(getattr(backend, "poll", None))):
            raise ThreadError(
                "thread backend must provide callable spawn() and poll()")
        self._backend = backend
        self._limit = ADDRESS_LIMIT_32 if bitness == 32 else ADDRESS_LIMIT_64
        self._max_threads = max_threads
        self._max_wait_polls = max_wait_polls
        self._threads: dict[int, ThreadHandle] = {}
        self._states: dict[int, str] = {}
        self._next_ordinal = 1
        self.transitions: list[tuple[str, int]] = []
        self.operations: list[dict] = []
        self.warnings: list[str] = []
        self.blocked_polls = 0

    def _check_address(self, address) -> int:
        if type(address) is not int or not 0 < address <= self._limit:
            raise ThreadError(
                "createThread requires a resolved bounded integer address",
                address=address)
        return address

    def state(self, ordinal) -> str:
        if type(ordinal) is not int or ordinal not in self._states:
            raise ThreadError("threadWait references an unknown thread",
                              thread=ordinal if type(ordinal) is int else None)
        return self._states[ordinal]

    def threads(self) -> tuple[ThreadHandle, ...]:
        return tuple(self._threads[ordinal] for ordinal in sorted(self._threads))

    def create_thread(self, address) -> ThreadHandle:
        address = self._check_address(address)
        if self._next_ordinal > self._max_threads:
            raise ThreadError("plan thread count bound exceeded",
                              address=address)
        ordinal = self._next_ordinal
        self._next_ordinal += 1
        handle = ThreadHandle(ordinal=ordinal, entry_address=address)
        self._threads[ordinal] = handle
        self._states[ordinal] = THREAD_CREATED
        self.transitions.append((THREAD_CREATED, ordinal))
        try:
            self._backend.spawn(handle)
        except Exception as exc:
            del self._threads[ordinal]
            del self._states[ordinal]
            self._next_ordinal -= 1
            self.transitions.pop()
            raise ThreadError(
                "createThread spawn was refused by the backend",
                thread=ordinal, address=address) from exc
        self._states[ordinal] = THREAD_RUNNING
        self.transitions.append((THREAD_RUNNING, ordinal))
        self.operations.append(
            {"op": "create_thread", "thread": ordinal, "address": address})
        return handle

    def thread_wait(self, reference) -> dict:
        if isinstance(reference, ThreadHandle):
            ordinal = reference.ordinal
        else:
            ordinal = reference
        if type(ordinal) is not int or ordinal not in self._threads:
            raise ThreadError("threadWait references an unknown thread",
                              thread=ordinal if type(ordinal) is int else None)
        handle = self._threads[ordinal]
        if self._states[ordinal] == THREAD_EXITED:
            raise ThreadError(
                "threadWait may only be used once per plan thread",
                thread=ordinal)
        polls = 0
        while True:
            polls += 1
            if polls > self._max_wait_polls:
                raise ThreadError(
                    "threadWait exceeded its deterministic poll bound",
                    thread=ordinal, polls=polls - 1)
            result = self._backend.poll(handle)
            if not isinstance(result, ThreadPoll) or type(result.exited) is not bool:
                raise ThreadError(
                    "thread backend poll must return a ThreadPoll event",
                    thread=ordinal)
            if not result.exited:
                self.blocked_polls += 1
                continue
            if (type(result.exit_code) is not int
                    or not 0 <= result.exit_code <= 0xFFFFFFFF):
                raise ThreadError(
                    "thread completion event carries an invalid exit code",
                    thread=ordinal)
            self._states[ordinal] = THREAD_EXITED
            self.transitions.append((THREAD_EXITED, ordinal))
            operation = {"op": "thread_wait", "thread": ordinal,
                         "address": handle.entry_address, "exited": True,
                         "exit_code": result.exit_code, "polls": polls}
            self.operations.append(operation)
            return operation

    def report(self) -> dict:
        return plan_report(self.operations, self.warnings)


# ---------------------------------------------------------------------------
# protect / unprotect
# ---------------------------------------------------------------------------

PAGE_READONLY = 0x02
PAGE_READWRITE = 0x04
PAGE_EXECUTE_READ = 0x20
PAGE_EXECUTE_READWRITE = 0x40
SUPPORTED_PAGES = frozenset(
    {PAGE_READONLY, PAGE_READWRITE, PAGE_EXECUTE_READ, PAGE_EXECUTE_READWRITE})
PAGE_NAMES = {
    PAGE_READONLY: "PAGE_READONLY",
    PAGE_READWRITE: "PAGE_READWRITE",
    PAGE_EXECUTE_READ: "PAGE_EXECUTE_READ",
    PAGE_EXECUTE_READWRITE: "PAGE_EXECUTE_READWRITE",
}
DEFAULT_PAGE_SIZE = 0x1000
MAX_PROTECTION_SIZE = 16 * 0x100000
MAX_PROTECTION_REGIONS = 256


@dataclass(frozen=True)
class ForeignRegion:
    """Region owned by a component other than the protection plan."""
    base: int
    size: int
    owner: str


class ProtectionBackend(ABC):
    """Injectable protection backend over held target regions."""

    @abstractmethod
    def foreign_regions(self, start: int, size: int) -> tuple[ForeignRegion, ...]:
        """Regions owned by other components that overlap [start, start+size)."""

    @abstractmethod
    def apply(self, base: int, size: int, page: int) -> None:
        """Apply protection to a validated range; must raise on refusal."""

    @abstractmethod
    def release(self, base: int, size: int) -> None:
        """Release a previously applied protection; must raise on refusal."""


class ProtectionDirectiveModel:
    """Plan-operation model for ``protect(address, size, page)`` /
    ``unprotect(address, size, page)``.

    Exact validation: page-aligned addresses, page-multiple sizes, bounded
    ranges, checked ``PAGE_*`` constants, no overlap with foreign regions or
    other active plan regions. A repeated identical ``protect`` is
    idempotent (the backend is applied once). ``unprotect`` without a prior
    ``protect`` on the same region is a plan warning, not an error.
    """

    def __init__(self, backend, *, bitness=64, page_size=DEFAULT_PAGE_SIZE):
        if type(bitness) is not int or bitness not in (32, 64):
            raise ProtectionError("Protection plan supports only 32/64-bit targets")
        for name in ("foreign_regions", "apply", "release"):
            if not callable(getattr(backend, name, None)):
                raise ProtectionError(
                    f"protection backend must provide callable {name}()")
        if (type(page_size) is not int or page_size < 1 or page_size > 0x100000
                or page_size & (page_size - 1)):
            raise ProtectionError(
                "page size must be a power of two within the bounded range")
        self._backend = backend
        self._limit = ADDRESS_LIMIT_32 if bitness == 32 else ADDRESS_LIMIT_64
        self._page_size = page_size
        self._owned: dict[tuple[int, int], int] = {}
        self.operations: list[dict] = []
        self.warnings: list[str] = []

    def _check_range(self, address, size) -> None:
        if type(address) is not int or type(size) is not int:
            raise ProtectionError(
                "protect range requires integer address and size",
                address=address, size=size)
        if address <= 0:
            raise ProtectionError("protect address must be positive",
                                  address=address, size=size)
        if size <= 0:
            raise ProtectionError("protect size must be positive",
                                  address=address, size=size)
        if size > MAX_PROTECTION_SIZE:
            raise ProtectionError("protect size exceeds its bound",
                                  address=address, size=size)
        if address > self._limit or size - 1 > self._limit - address:
            raise ProtectionError(
                "protect range exceeds the bounded target address space",
                address=address, size=size)
        if address % self._page_size:
            raise ProtectionError("protect address must be page-aligned",
                                  address=address, size=size)
        if size % self._page_size:
            raise ProtectionError(
                "protect size must be a multiple of the page size",
                address=address, size=size)

    def _check_page(self, page) -> None:
        if type(page) is not int or page not in SUPPORTED_PAGES:
            raise ProtectionError(
                "page constant must be one of the supported PAGE_* values",
                page=page)

    @property
    def owned_regions(self) -> tuple[tuple[int, int, int], ...]:
        return tuple(sorted((base, size, page)
                            for (base, size), page in self._owned.items()))

    def protect(self, address, size, page) -> dict:
        self._check_range(address, size)
        self._check_page(page)
        key = (address, size)
        if key in self._owned:
            if self._owned[key] == page:
                operation = {"op": "protect", "address": address, "size": size,
                             "page": page, "idempotent": True}
                self.operations.append(operation)
                return operation
            raise ProtectionError(
                "conflicting protection already active on the same region",
                address=address, size=size, page=page)
        if len(self._owned) >= MAX_PROTECTION_REGIONS:
            raise ProtectionError("protection region bound exceeded",
                                  address=address, size=size)
        for other_base, other_size in self._owned:
            if other_base < address + size and address < other_base + other_size:
                raise ProtectionError(
                    "protect range overlaps an active plan region",
                    address=address, size=size)
        foreign = self._backend.foreign_regions(address, size)
        if not isinstance(foreign, (list, tuple)):
            raise ProtectionError(
                "protection backend returned a malformed foreign region list",
                address=address, size=size)
        for region in foreign:
            if (not isinstance(region, ForeignRegion)
                    or type(region.base) is not int or type(region.size) is not int
                    or region.base <= 0 or region.size <= 0
                    or not isinstance(region.owner, str) or not region.owner):
                raise ProtectionError(
                    "protection backend returned a malformed foreign region",
                    address=address, size=size)
            if region.base < address + size and address < region.base + region.size:
                raise ProtectionError(
                    "protect range overlaps a foreign region",
                    address=address, size=size, owner=region.owner)
        try:
            self._backend.apply(address, size, page)
        except Exception as exc:
            raise ProtectionError("protection backend refused the range",
                                  address=address, size=size, page=page) from exc
        self._owned[key] = page
        operation = {"op": "protect", "address": address, "size": size,
                     "page": page}
        self.operations.append(operation)
        return operation

    def unprotect(self, address, size, page) -> dict:
        self._check_range(address, size)
        self._check_page(page)
        key = (address, size)
        if key in self._owned:
            try:
                self._backend.release(address, size)
            except Exception as exc:
                raise ProtectionError(
                    "protection backend refused the release",
                    address=address, size=size, page=page) from exc
            del self._owned[key]
            operation = {"op": "unprotect", "address": address, "size": size,
                         "page": page, "reverted": True}
        else:
            warning = (f"unprotect {address:#x}+{size:#x} has no matching "
                       "prior protect in this plan")
            self.warnings.append(warning)
            operation = {"op": "unprotect", "address": address, "size": size,
                         "page": page, "reverted": False, "warning": warning}
        self.operations.append(operation)
        return operation

    def report(self) -> dict:
        return plan_report(self.operations, self.warnings)


# ---------------------------------------------------------------------------
# getprocaddress / getmodulehandle
# ---------------------------------------------------------------------------


class ExportBackend(ABC):
    """Held-target export surface consumed by the read-only ``pe_exports``
    model (bounded ``read`` plus ``module`` identity lookups)."""

    @abstractmethod
    def read(self, address: int, size: int) -> bytes:
        """Bounded read inside a held module image."""

    @abstractmethod
    def module(self, name: str) -> tuple[int, int]:
        """Return (base, size) for a normalized module base name."""


class TargetApiDirectiveModel:
    """Plan-operation model for ``getprocaddress(module, export)`` /
    ``getmodulehandle(module)``.

    Resolution delegates to the existing read-only ``pe_exports`` model:
    exact held-target PE export metadata, bounded forwarder chains, and
    unchanged-image re-verification. Missing exports are strict rejections
    carrying the module/export name context. ``rva`` is measured from the
    requested module base; for forwarded exports ``address`` is the final
    target and ``forwarded`` is ``True``.

    Re-run dedup: identical repeated calls (the link flow re-runs
    preflight) return the cached operation without re-reading the target
    or appending a duplicate operation.
    """

    def __init__(self, backend):
        if (backend is None
                or not callable(getattr(backend, "read", None))
                or not callable(getattr(backend, "module", None))):
            raise TargetApiError(
                "export backend must provide callable read() and module()")
        self._backend = backend
        self.operations: list[dict] = []
        self.warnings: list[str] = []
        self._export_cache: dict[tuple, dict] = {}

    @staticmethod
    def _module_name(value) -> str:
        # Mirrors the pe_exports module-name contract so argument
        # validation matches the read-only resolver exactly.
        if (not isinstance(value, str) or not value or len(value) > 255
                or value != value.strip()
                or any(ord(char) < 32 or char in '\\/:<>|*?"' for char in value)
                or value in {".", ".."}):
            raise TargetApiError(
                "getprocaddress/getmodulehandle require an exact module base name")
        return value if "." in value else value + ".dll"

    def getmodulehandle(self, module_name) -> dict:
        name = self._module_name(module_name)
        key = ("getmodulehandle", name)
        cached = self._export_cache.get(key)
        if cached is not None:
            return cached
        try:
            base, size = self._backend.module(name)
        except Exception as exc:
            raise TargetApiError(
                f"getmodulehandle({name}) failed: module is not uniquely held "
                "in the target", module=name) from exc
        if (type(base) is not int or type(size) is not int
                or not 0 < base <= ADDRESS_LIMIT_64
                or not 64 <= size <= MAX_IMAGE_SIZE
                or size - 1 > ADDRESS_LIMIT_64 - base):
            raise TargetApiError("Invalid held module range for getmodulehandle",
                                 module=name)
        operation = {"op": "getmodulehandle", "module": name,
                     "base": base, "size": size}
        self._export_cache[key] = operation
        self.operations.append(operation)
        return operation

    def getprocaddress(self, module_name, export_name) -> dict:
        name = self._module_name(module_name)
        key = ("getprocaddress", name, export_name)
        cached = self._export_cache.get(key)
        if cached is not None:
            return cached
        try:
            address = resolve_remote_export(
                self._backend.read, self._backend.module, name, export_name)
        except ExportResolutionError as exc:
            raise TargetApiError(
                f"getprocaddress({name}, {export_name!r}) failed: {exc}",
                module=name, export=export_name) from exc
        try:
            base, size = self._backend.module(name)
        except Exception as exc:
            raise TargetApiError(
                f"getprocaddress({name}, {export_name!r}) failed: module "
                "changed after export resolution", module=name,
                export=export_name) from exc
        if (type(base) is not int or type(size) is not int
                or not 0 < base <= ADDRESS_LIMIT_64
                or not 64 <= size <= MAX_IMAGE_SIZE
                or size - 1 > ADDRESS_LIMIT_64 - base):
            raise TargetApiError("Invalid held module range for getprocaddress",
                                 module=name, export=export_name)
        operation = {"op": "getprocaddress", "module": name,
                     "export": export_name, "base": base, "address": address,
                     "rva": address - base,
                     "forwarded": not (base <= address < base + size)}
        self._export_cache[key] = operation
        self.operations.append(operation)
        return operation

    def report(self) -> dict:
        return plan_report(self.operations, self.warnings)


# ---------------------------------------------------------------------------
# disassemble
# ---------------------------------------------------------------------------

MAX_DISASSEMBLE_COUNT = 4096
MAX_INSTRUCTION_BYTES = 15
MAX_MNEMONIC_CHARS = 64


class DisassemblerPort(ABC):
    """Dependency-inversion port for a real disassembler (AP-11/Root)."""

    @abstractmethod
    def disassemble(self, address: int, count: int, bitness: int) -> list:
        """Return exactly ``count`` items of ``{"address", "size",
        "mnemonic"}``: the first item starts at ``address``, each later
        item starts exactly at the previous ``address + size`` (gapless
        and address-ordered), and ``size`` is positive."""


class DisassembleDirectiveModel:
    """Plan-operation model for the ``disassemble(address, count)`` directive.

    No disassembler is embedded in this module. The injected
    :class:`DisassemblerPort` result is validated (gapless, address-ordered,
    ``size`` > 0, count compliance, bounded printable mnemonics) before it
    becomes the plan operation
    ``{"op": "disassemble", "address": ..., "count": ..., "output": ...}``.
    Direct conformance against a real disassembler stays documented open
    (AP-11/Root).
    """

    def __init__(self, port, *, bitness=64):
        if type(bitness) is not int or bitness not in (32, 64):
            raise DisassemblerError(
                "Disassembler plan supports only 32/64-bit targets")
        if port is None or not callable(getattr(port, "disassemble", None)):
            raise DisassemblerError(
                "disassemble requires an injectable DisassemblerPort")
        self._port = port
        self._bitness = bitness
        self._limit = ADDRESS_LIMIT_32 if bitness == 32 else ADDRESS_LIMIT_64
        self.operations: list[dict] = []
        self.warnings: list[str] = []

    def disassemble(self, address, count) -> dict:
        if type(address) is not int or not 0 < address <= self._limit:
            raise DisassemblerError(
                "disassemble requires a resolved bounded integer address",
                address=address)
        if type(count) is not int or not 1 <= count <= MAX_DISASSEMBLE_COUNT:
            raise DisassemblerError(
                "disassemble count must be within its bounded range",
                count=count)
        try:
            raw = self._port.disassemble(address, count, self._bitness)
        except Exception as exc:
            raise DisassemblerError("disassembler port failed",
                                    address=address, count=count) from exc
        output = self._validate_output(raw, address, count)
        operation = {"op": "disassemble", "address": address, "count": count,
                     "output": output}
        self.operations.append(operation)
        return operation

    def _validate_output(self, raw, address, count) -> list[dict]:
        if not isinstance(raw, list) or len(raw) != count:
            actual = len(raw) if isinstance(raw, list) else None
            raise DisassemblerError(
                f"disassembler output must contain exactly {count} "
                f"instructions (got {actual})", count=count)
        cursor = address
        output = []
        for index, item in enumerate(raw):
            if not isinstance(item, dict):
                raise DisassemblerError(
                    "disassembler output items must be objects", index=index)
            start = item.get("address")
            size = item.get("size")
            mnemonic = item.get("mnemonic")
            if type(size) is not int or not 0 < size <= MAX_INSTRUCTION_BYTES:
                raise DisassemblerError(
                    "disassembler instruction size must be a positive "
                    "bounded integer", index=index)
            if type(start) is not int or start != cursor:
                raise DisassemblerError(
                    "disassembler output must be gapless and "
                    "address-ordered", index=index)
            if (type(mnemonic) is not str or not mnemonic
                    or len(mnemonic) > MAX_MNEMONIC_CHARS
                    or any(32 > ord(char) or char > "~" for char in mnemonic)):
                raise DisassemblerError(
                    "disassembler mnemonic must be bounded printable ASCII",
                    index=index)
            cursor += size
            if cursor - 1 > self._limit:
                raise DisassemblerError(
                    "disassembly run exceeds the bounded target address space",
                    count=count)
            output.append({"address": start, "size": size,
                           "mnemonic": mnemonic})
        return output

    def report(self) -> dict:
        return plan_report(self.operations, self.warnings)


# ---------------------------------------------------------------------------
# Missing/empty ENABLE-DISABLE section contract
# ---------------------------------------------------------------------------

CASE_COMPLETE = "complete"
CASE_EMPTY_ENABLE = "empty_enable"
CASE_EMPTY_DISABLE = "empty_disable"
CASE_EOF_AFTER_ENABLE = "eof_after_enable"
CASE_MISSING_DISABLE = "missing_disable"
CASE_DISABLE_WITHOUT_ENABLE = "disable_without_enable"
CASE_NO_MARKERS = "no_markers"
CASE_DUPLICATE_OR_OUT_OF_ORDER = "duplicate_or_out_of_order"

GRAMMAR_FULL = "full"    # aa_program.prepare_program
GRAMMAR_SMALL = "small"  # aa.compile_script


@dataclass(frozen=True)
class SectionAnalysis:
    case: str
    enable_present: bool
    disable_present: bool
    preamble_lines: int
    enable_lines: int
    disable_lines: int


def analyze_sections(source: str) -> SectionAnalysis:
    """Classify the raw AA source structurally (marker presence, order,
    body line counts).

    Line handling mirrors the existing grammars: lines are stripped,
    empty lines are skipped, and the markers ``[ENABLE]`` / ``[DISABLE]``
    match case-insensitively. Comments are not interpreted here; comment
    semantics are owned by the grammars themselves.
    """
    if not isinstance(source, str):
        raise SectionStructureError("AA section source must be text",
                                    case=CASE_NO_MARKERS)
    content = [line.strip() for line in source.splitlines() if line.strip()]
    buckets = {"preamble": [], "enable": [], "disable": []}
    markers: list[str] = []
    current = "preamble"
    for line in content:
        folded = line.casefold()
        if folded in {"[enable]", "[disable]"}:
            marker = folded[1:-1]
            markers.append(marker)
            current = marker
            continue
        buckets[current].append(line)
    enable_count = markers.count("enable")
    disable_count = markers.count("disable")
    if enable_count == 0 and disable_count == 0:
        case = CASE_NO_MARKERS
    elif disable_count == 0:
        case = (CASE_EOF_AFTER_ENABLE if not buckets["enable"]
                else CASE_MISSING_DISABLE)
    elif enable_count == 0:
        case = CASE_DISABLE_WITHOUT_ENABLE
    elif enable_count > 1 or disable_count > 1 or markers[0] == "disable":
        case = CASE_DUPLICATE_OR_OUT_OF_ORDER
    elif not buckets["enable"]:
        case = CASE_EMPTY_ENABLE
    elif not buckets["disable"]:
        case = CASE_EMPTY_DISABLE
    else:
        case = CASE_COMPLETE
    return SectionAnalysis(
        case=case, enable_present=enable_count > 0,
        disable_present=disable_count > 0,
        preamble_lines=len(buckets["preamble"]),
        enable_lines=len(buckets["enable"]),
        disable_lines=len(buckets["disable"]))


# Structural rejection surface: exactly the cases in which the existing
# grammars (aa_program.prepare_program / aa.compile_script) reject before
# any content-level check, in both grammars. An empty [DISABLE] is
# structurally accepted here: the full grammar has no static body check for
# it, and the small byte-patch language rejects it content-dependently via
# the symmetric patch guard (a symbol-only script is the documented positive
# exception). The dedicated tests pin both actual outcomes.
_STRUCTURAL_REJECTIONS = frozenset({
    CASE_EOF_AFTER_ENABLE,
    CASE_MISSING_DISABLE,
    CASE_DISABLE_WITHOUT_ENABLE,
    CASE_NO_MARKERS,
    CASE_EMPTY_ENABLE,
    CASE_DUPLICATE_OR_OUT_OF_ORDER,
})

_REJECTION_MESSAGES = {
    CASE_EOF_AFTER_ENABLE:
        "Program ends at [ENABLE]; both ENABLE and DISABLE sections are required.",
    CASE_MISSING_DISABLE:
        "The [DISABLE] section is missing.",
    CASE_DISABLE_WITHOUT_ENABLE:
        "[DISABLE] appears without a preceding [ENABLE] section.",
    CASE_NO_MARKERS:
        "Both ENABLE and DISABLE sections are required.",
    CASE_EMPTY_ENABLE:
        "The [ENABLE] section has no content.",
    CASE_DUPLICATE_OR_OUT_OF_ORDER:
        "Sections must be exactly one [ENABLE] followed by one [DISABLE].",
}


def check_sections(source: str, *, grammar: str = GRAMMAR_FULL) -> SectionAnalysis:
    """Fail-closed structural section contract, mirrored from the existing
    grammar behavior (negative model; no behavior change)."""
    if grammar not in {GRAMMAR_FULL, GRAMMAR_SMALL}:
        raise SectionStructureError(
            f"Unknown section grammar {grammar!r}", case=CASE_NO_MARKERS)
    analysis = analyze_sections(source)
    if analysis.case in _STRUCTURAL_REJECTIONS:
        raise SectionStructureError(
            _REJECTION_MESSAGES[analysis.case], case=analysis.case,
            analysis=analysis, grammar=grammar)
    return analysis


# ---------------------------------------------------------------------------
# Plan report
# ---------------------------------------------------------------------------


def plan_report(operations, warnings=(), *, schema: str = SCHEMA) -> dict:
    """JSON-safe plan report shared by all family models."""
    document = {"schema": schema, "operations": list(operations),
                "warnings": list(warnings)}
    try:
        json.dumps(document, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise AADirectivesError("plan report must stay JSON-safe") from exc
    return document


class DirectivesPlan:
    """Aggregates the family models into one plan report (Root wiring)."""

    def __init__(self, *, threads=None, protection=None, exports=None,
                 disassembler=None):
        self.threads = threads
        self.protection = protection
        self.exports = exports
        self.disassembler = disassembler

    def report(self) -> dict:
        operations: list[dict] = []
        warnings: list[str] = []
        for model in (self.threads, self.protection, self.exports,
                      self.disassembler):
            if model is None:
                continue
            if (not isinstance(getattr(model, "operations", None), list)
                    or not isinstance(getattr(model, "warnings", None), list)):
                raise AADirectivesError(
                    "plan models must expose operations and warnings lists")
            operations.extend(model.operations)
            warnings.extend(model.warnings)
        return plan_report(operations, warnings)


