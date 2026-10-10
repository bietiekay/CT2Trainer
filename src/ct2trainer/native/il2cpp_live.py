"""IL2CPP live address-resolution model (AP-05 stage 1, pure Python).

Builds on the bounded static parser of :mod:`ct2trainer.native.il2cpp_static`
(``WindowsPE`` file mapping, ``MetadataV29`` exact identity rows) to model how
a live GameAssembly module binding resolves registration-table pointers to
virtual addresses.  There is no live-process interaction, no CE
implementation code and no native invocation: every check operates on bounded
byte snapshots, and every refusal is a named exception.

Semantics (explicit Native contract, stage 1; plan AP-05 items 2 and 3):

- a :class:`ModuleBinding` pins the *observed* live base address, the module
  SHA-256, the bitness and the generation taken from a module snapshot.  The
  binding is anchored at construction time against the static PE (bitness
  must match, the module hash must equal the PE file hash, and base plus
  image size must fit the bound address width) and every later observation is
  re-checked with :meth:`Il2CppLiveResolver.observe`: a diverging base, hash
  or generation is refused (``BaseChangedRefused`` /
  ``ModuleShaMismatchRefused`` / ``StaleBindingRefused``) and the binding is
  never silently re-resolved against another module incarnation.  The
  RVA/VA/file-extent proof (this module) and the actual remote-module proof
  (the binding observation) stay separate, as the plan requires.
- RVA-to-VA proof: the RVA must be backed by raw source bytes of a *unique*
  PE section (virtual zero-fill is ``OutOfExtentRefused`` — a live resolver
  never maps bytes it cannot prove in the file) and the section must be
  executable (``NonExecutableLocationRefused``).  The VA is
  ``live_base + rva`` and must stay inside the bound address width.
- registration tables (method pointers, invokers, generic invokers) are read
  with ``read_rva`` and decoded per the table's declared pointer mode
  (``va`` = absolute virtual address as loaded, ``rva`` = relative to the
  live base).  Extents must be pairwise disjoint at construction, and a
  pointer that resolves into a *different* table's extent is
  ``TableConfusionRefused`` — generics, invokers and method pointers are
  never interchanged.
- method identity comes from the exact metadata-v29 snapshot (bound by its
  SHA-256); the pointer-table slot is the method's ``method_index``; the
  expected static/instance and parameter-count signature model is validated
  against the ``MethodIdentity`` row, never guessed (GameAssembly-AOB alone
  is not sufficient; IL2CPP AOT is not Mono JIT).
- ``snapshot()`` stays responsive and deterministic: binding, PE and metadata
  identity, table extents and every resolved proof entry; no mutation.

Invocation (broker/GC/affinity/exception/no-replay) follows the AP-04 broker
contract and is modeled separately in :mod:`ct2trainer.native.mono_broker`.
Stage-1 fixtures are own synthetic PE/metadata bytes (plan AP-05 item 4);
real pinned Unity files are recorded read-only with hash/build, later.
"""
from __future__ import annotations

from dataclasses import dataclass
import struct

from .il2cpp_static import FormatError, MethodIdentity, MetadataV29, WindowsPE

SCHEMA = 'ct2trainer-il2cpp-live/v1'

POINTER_MODE_VA = 'va'
POINTER_MODE_RVA = 'rva'
POINTER_MODES = (POINTER_MODE_VA, POINTER_MODE_RVA)

TABLE_METHOD_POINTERS = 'method_pointers'
TABLE_INVOKERS = 'invokers'
TABLE_GENERIC_INVOKERS = 'generic_invokers'

IMAGE_SCN_MEM_EXECUTE = 0x20000000


class Il2CppLiveError(ValueError):
    """Base class for named live-resolution refusals."""


class BitnessMismatchRefused(Il2CppLiveError):
    """PE and binding disagree about the module bitness."""


class ModuleShaMismatchRefused(Il2CppLiveError):
    """The observed module hash does not match the bound PE file hash."""


class BaseChangedRefused(Il2CppLiveError):
    """The observed live base diverges from the bound live base."""


class StaleBindingRefused(Il2CppLiveError):
    """The observed generation is stale relative to the bound generation."""


class OutOfExtentRefused(Il2CppLiveError):
    """An address cannot be proven inside the bound image extent."""


class NonExecutableLocationRefused(Il2CppLiveError):
    """An address is provable but not inside an executable section."""


class TableConfusionRefused(Il2CppLiveError):
    """A pointer target resolves into a different registration table."""


class MethodIdentityRefused(Il2CppLiveError):
    """The exact method identity is missing or ambiguous in the metadata."""


class SignatureMismatchRefused(Il2CppLiveError):
    """The resolved identity contradicts the expected signature model."""


def _require_int(value, what: str) -> int:
    if type(value) is not int:
        raise Il2CppLiveError(f'{what} must be an integer')
    return value


def _require_sha256(value, what: str) -> str:
    if (not isinstance(value, str) or len(value) != 64
            or any(character not in '0123456789abcdef' for character in value)):
        raise Il2CppLiveError(f'{what} must be 64 lowercase hex characters')
    return value


@dataclass(frozen=True)
class ModuleBinding:
    """Live module observation that anchors every resolution."""

    live_base: int
    module_sha256: str
    generation: int
    bitness: int

    def __post_init__(self) -> None:
        _require_int(self.live_base, 'live_base')
        if self.live_base < 0:
            raise Il2CppLiveError('live_base must be nonnegative')
        _require_sha256(self.module_sha256, 'module_sha256')
        _require_int(self.generation, 'generation')
        if self.generation < 1:
            raise Il2CppLiveError('generation must be positive')
        if self.bitness not in (32, 64):
            raise Il2CppLiveError('bitness must be 32 or 64')


@dataclass(frozen=True)
class PointerTable:
    """One registration table observed in the live image."""

    name: str
    rva: int
    count: int
    pointer_mode: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise Il2CppLiveError('table name must be a nonempty string')
        _require_int(self.rva, 'rva')
        if self.rva < 0:
            raise Il2CppLiveError('rva must be nonnegative')
        _require_int(self.count, 'count')
        if self.count < 0:
            raise Il2CppLiveError('count must be nonnegative')
        if self.pointer_mode not in POINTER_MODES:
            raise Il2CppLiveError(
                f'pointer_mode must be one of {POINTER_MODES}')


@dataclass(frozen=True)
class MethodResolution:
    """One proven live address for an exactly identified method."""

    method: MethodIdentity
    va: int
    live_base: int
    module_sha256: str
    metadata_sha256: str
    generation: int
    section: str
    pointer_mode: str
    slot_rva: int

    @property
    def is_static(self) -> bool:
        return self.method.is_static

    def to_dict(self) -> dict:
        return {
            'method_token': self.method.token,
            'image': self.method.image,
            'namespace': self.method.namespace,
            'class': self.method.class_name,
            'name': self.method.name,
            'method_index': self.method.method_index,
            'is_static': self.is_static,
            'parameter_count': len(self.method.parameters),
            'va': self.va,
            'live_base': self.live_base,
            'section': self.section,
            'pointer_mode': self.pointer_mode,
            'slot_rva': self.slot_rva,
            'module_sha256': self.module_sha256,
            'metadata_sha256': self.metadata_sha256,
            'generation': self.generation,
        }


class Il2CppLiveResolver:
    """Bounded live resolver over a static PE and metadata-v29 snapshot."""

    def __init__(self, pe: WindowsPE, metadata: MetadataV29,
                 binding: ModuleBinding, *, method_pointers: PointerTable,
                 invokers: PointerTable,
                 generic_invokers: PointerTable) -> None:
        self._pe = pe
        self._metadata = metadata
        self._binding = binding
        self._pointer_size = 8 if binding.bitness == 64 else 4
        self._tables = {
            TABLE_METHOD_POINTERS: method_pointers,
            TABLE_INVOKERS: invokers,
            TABLE_GENERIC_INVOKERS: generic_invokers,
        }
        if pe.bitness != binding.bitness:
            raise BitnessMismatchRefused(
                f'PE bitness {pe.bitness} does not match binding '
                f'bitness {binding.bitness}')
        if binding.module_sha256 != pe.sha256:
            raise ModuleShaMismatchRefused(
                'module hash does not match the static PE file hash')
        if binding.live_base + pe.image_size > (1 << pe.bitness):
            raise OutOfExtentRefused(
                f'live base {binding.live_base:#x} plus image size '
                f'{pe.image_size:#x} overflows the {pe.bitness}-bit '
                'address space')
        items = list(self._tables.items())
        for a in range(len(items)):
            for b in range(a + 1, len(items)):
                name_a, table_a = items[a]
                name_b, table_b = items[b]
                start_a, end_a = self._extent(table_a)
                start_b, end_b = self._extent(table_b)
                if start_a < end_b and start_b < end_a:
                    raise TableConfusionRefused(
                        f'table {name_a!r} [{start_a:#x},{end_a:#x}) overlaps '
                        f'table {name_b!r} [{start_b:#x},{end_b:#x})')
        self._proofs: list[MethodResolution] = []

    # -- binding re-verification --------------------------------------------

    def observe(self, *, live_base: int, module_sha256: str,
                generation: int) -> None:
        """Re-check a fresh module observation; divergence is refused.

        The binding is never silently rebased: a changed base, hash or
        generation is a named refusal, so stale resolutions can never be
        published after a module reload or relocation.
        """
        _require_int(live_base, 'live_base')
        _require_int(generation, 'generation')
        if generation != self._binding.generation:
            raise StaleBindingRefused(
                f'generation {generation} does not match bound generation '
                f'{self._binding.generation}')
        if module_sha256 != self._binding.module_sha256:
            raise ModuleShaMismatchRefused(
                'observed module hash does not match the bound module hash')
        if live_base != self._binding.live_base:
            raise BaseChangedRefused(
                f'observed base {live_base:#x} does not match bound base '
                f'{self._binding.live_base:#x}')

    # -- RVA/VA proof ---------------------------------------------------------

    def _extent(self, table: PointerTable) -> tuple[int, int]:
        return table.rva, table.rva + table.count * self._pointer_size

    def _section_for_rva(self, rva: int):
        for section in self._pe.sections:
            if section.rva <= rva < section.rva + section.virtual_size:
                return section
        return None

    def prove_rva(self, rva: int, size: int = 1) -> tuple[int, str]:
        """Prove that [rva, rva+size) is raw-backed, unique-section and executable.

        Returns ``(va, section_name)``.  Virtual zero-fill, out-of-image RVAs
        and non-executable sections are refused with named errors.
        """
        _require_int(rva, 'rva')
        _require_int(size, 'size')
        if rva < 0 or size < 1:
            raise OutOfExtentRefused(
                'rva must be nonnegative and size positive')
        virtual_address = self._binding.live_base + rva
        if virtual_address >= (1 << self._binding.bitness):
            raise OutOfExtentRefused(
                f'VA {virtual_address:#x} overflows the '
                f'{self._binding.bitness}-bit address space')
        try:
            self._pe.rva_to_offset(rva, size)
        except FormatError as error:
            raise OutOfExtentRefused(
                f'rva {rva:#x} is not provable source bytes: {error}') from error
        section = self._section_for_rva(rva)
        if section is None:
            raise OutOfExtentRefused(
                f'rva {rva:#x} is not inside any PE section')
        if not section.characteristics & IMAGE_SCN_MEM_EXECUTE:
            raise NonExecutableLocationRefused(
                f'rva {rva:#x} is inside non-executable section '
                f'{section.name.decode("ascii", "replace")!r}')
        return virtual_address, section.name.decode('ascii', 'replace')

    # -- registration tables ---------------------------------------------------

    def read_table_slot(self, table: PointerTable, index: int) -> tuple[int, int]:
        """Read one pointer slot; returns ``(decoded value, slot rva)``.

        The slot must be provable source bytes of the live image; a table
        placed in virtual zero-fill is refused, not read as zeros.
        """
        if type(index) is not int or index < 0 or index >= table.count:
            raise OutOfExtentRefused(
                f'slot {index!r} is outside table {table.name!r} '
                f'(count {table.count})')
        slot_rva = table.rva + index * self._pointer_size
        try:
            raw = self._pe.read_rva(slot_rva, self._pointer_size)
        except FormatError as error:
            raise OutOfExtentRefused(
                f'table {table.name!r} slot {index} is not provable source '
                f'bytes: {error}') from error
        value, = struct.unpack_from('<Q' if self._binding.bitness == 64 else '<I', raw)
        return value, slot_rva

    def resolve_table_pointer(self, table: PointerTable,
                              index: int) -> tuple[int, str]:
        """Resolve one table slot to a proven live VA.

        The decoded target must be raw-backed and executable, and it must not
        fall into another registration table's extent (anti-confusion).
        Returns ``(va, section_name)``.
        """
        value, _slot_rva = self.read_table_slot(table, index)
        if table.pointer_mode == POINTER_MODE_RVA:
            target_rva = value
        elif value < self._binding.live_base:
            raise OutOfExtentRefused(
                f'table {table.name!r} pointer {value:#x} is below the live '
                'base')
        else:
            target_rva = value - self._binding.live_base
        virtual_address, section = self.prove_rva(target_rva)
        for other_name, other in self._tables.items():
            if other_name == table.name:
                continue
            start, end = self._extent(other)
            if start <= target_rva < end:
                raise TableConfusionRefused(
                    f'table {table.name!r} slot {index} target {target_rva:#x} '
                    f'resolves inside {other_name!r} extent '
                    f'[{start:#x},{end:#x})')
        return virtual_address, section

    # -- method resolution -------------------------------------------------------

    def resolve_method(self, image: str, namespace: str, class_name: str,
                       name: str, *,
                       parameter_type_indices: tuple[int, ...] | None = None,
                       return_type_index: int | None = None,
                       expected_static: bool | None = None,
                       expected_parameter_count: int | None = None
                       ) -> MethodResolution:
        """Resolve one exactly identified method to a proven live address.

        Identity comes from the bounded metadata-v29 snapshot (never from
        pattern scans); the pointer-table slot is the method's
        ``method_index``; the optional expected signature model is validated
        against the identity row.  The proof is recorded for ``snapshot()``.
        """
        try:
            method = self._metadata.find_method(
                image, namespace, class_name, name,
                parameter_type_indices=parameter_type_indices,
                return_type_index=return_type_index)
        except (FormatError, ValueError) as error:
            raise MethodIdentityRefused(str(error)) from error
        if expected_static is not None and method.is_static != expected_static:
            raise SignatureMismatchRefused(
                f'method {name!r} is static={method.is_static}; '
                f'expected static={expected_static}')
        if (expected_parameter_count is not None
                and len(method.parameters) != expected_parameter_count):
            raise SignatureMismatchRefused(
                f'method {name!r} has {len(method.parameters)} parameter(s); '
                f'expected {expected_parameter_count}')
        table = self._tables[TABLE_METHOD_POINTERS]
        if method.method_index >= table.count:
            raise OutOfExtentRefused(
                f'method index {method.method_index} is outside the '
                f'method-pointer table (count {table.count})')
        virtual_address, section = self.resolve_table_pointer(
            table, method.method_index)
        resolution = MethodResolution(
            method=method,
            va=virtual_address,
            live_base=self._binding.live_base,
            module_sha256=self._binding.module_sha256,
            metadata_sha256=self._metadata.sha256,
            generation=self._binding.generation,
            section=section,
            pointer_mode=table.pointer_mode,
            slot_rva=table.rva + method.method_index * self._pointer_size,
        )
        self._proofs.append(resolution)
        return resolution

    # -- introspection ------------------------------------------------------------

    def snapshot(self) -> dict:
        """Responsive, deterministic read of binding, identity and proofs."""
        binding = self._binding
        return {
            'schema': SCHEMA,
            'binding': {
                'live_base': binding.live_base,
                'module_sha256': binding.module_sha256,
                'generation': binding.generation,
                'bitness': binding.bitness,
            },
            'pe': {
                'sha256': self._pe.sha256,
                'image_base': self._pe.image_base,
                'image_size': self._pe.image_size,
                'bitness': self._pe.bitness,
            },
            'metadata_sha256': self._metadata.sha256,
            'tables': {
                name: {
                    'rva': table.rva,
                    'count': table.count,
                    'pointer_mode': table.pointer_mode,
                    'extent_bytes': table.count * self._pointer_size,
                }
                for name, table in self._tables.items()
            },
            'proofs': [proof.to_dict() for proof in self._proofs],
            'counts': {'proofs': len(self._proofs)},
        }
