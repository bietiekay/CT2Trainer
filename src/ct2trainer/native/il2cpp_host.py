"""IL2CPP registration host over the live resolver (AP-05 stage 2, pure Python).

Builds on :mod:`ct2trainer.native.il2cpp_static` (PE mapping, metadata-v29
identity rows) and :mod:`ct2trainer.native.il2cpp_live` (the bounded live
resolver) to model a *registration host*: the place where a trainer's named
aliases (Engine/Lua alias provider input) are bound to a live GameAssembly
module incarnation and resolved to proven addresses with identity proof.

There is no live-process interaction, no CE implementation code and no native
invocation: modules are deterministically injectable byte snapshots plus
explicit observations, and every refusal is a named exception.

Semantics (explicit Native contract, stage 2; plan AP-05 items 2, 3 and 4):

- the host binds one *primary* module (the IL2CPP module carrying metadata)
  by constructing an :class:`Il2CppLiveResolver` from injected PE bytes,
  metadata bytes and a :class:`ModuleBinding`.  Foreign schemas are refused
  exactly as in stage 1: the static parser admits only PE32/PE32+ and
  metadata-v29 (``FormatError``), and the resolver admits only matching
  bitness/SHA/base (``BitnessMismatchRefused`` /
  ``ModuleShaMismatchRefused`` / ``OutOfExtentRefused`` /
  ``TableConfusionRefused`` — all reused, never reinvented).
- the host keeps the generation/SHA/base binding and re-checks every fresh
  observation with :meth:`Il2CppRegistrationHost.observe`: a diverging base,
  hash or generation raises the same named refusal as the live resolver
  (``BaseChangedRefused`` / ``ModuleShaMismatchRefused`` /
  ``StaleBindingRefused``) and the host latches *stale*.  A stale host never
  serves aliases again and never accepts another observation; the only
  recovery is a fresh host for the fresh binding (no silent rebase, ever).
- the alias provider interface maps an alias name to ``(address, identity
  proof)``.  Aliases carry no address of their own: ``method`` aliases
  resolve through the exact metadata-v29 identity row and the
  method-pointer table (``method_index`` slot), ``invoker``/
  ``generic_invoker`` aliases resolve through their table slot.  Both go
  through the live binding only, honouring the table's declared pointer
  mode (``va``/``rva``) and the stage-1 proof rules (raw-backed, unique,
  executable section).  Cross-table confusion stays
  ``TableConfusionRefused`` via the resolver.
- cross-module confusion: the host can register *other* observed modules
  (deterministic byte snapshots + observations) as an address-attribution
  map.  An alias whose target module is not the bound module, or whose
  resolved VA falls into another observed module's image extent, is refused
  with the same ``TableConfusionRefused`` — an alias is never served from
  the identity proof of a different module.
- :meth:`snapshot` stays responsive and deterministic: module map, binding,
  PE/metadata identity, tables, registered aliases, every resolution proof
  and the observation state; no timestamps, no mutation.

Open (recorded, not modeled): real pinned Unity files (read-only with
hash/build), Engine/Lua alias-provider wiring and Frozen evidence.  Those are
explicit AP-05 gates after this stage-2 model.
"""
from __future__ import annotations

from dataclasses import dataclass
import struct

from .il2cpp_live import (
    BitnessMismatchRefused,
    Il2CppLiveError,
    Il2CppLiveResolver,
    ModuleBinding,
    ModuleShaMismatchRefused,
    OutOfExtentRefused,
    PointerTable,
    StaleBindingRefused,
    TableConfusionRefused,
    TABLE_GENERIC_INVOKERS,
    TABLE_INVOKERS,
    TABLE_METHOD_POINTERS,
)
from .il2cpp_static import FormatError, MetadataV29, WindowsPE

SCHEMA = 'ct2trainer-il2cpp-host/v1'

MAX_ALIAS_BYTES = 128
MAX_MODULE_NAME_BYTES = 128

ALIAS_KINDS = ('method', 'invoker', 'generic_invoker')
KIND_TABLES = {
    'method': TABLE_METHOD_POINTERS,
    'invoker': TABLE_INVOKERS,
    'generic_invoker': TABLE_GENERIC_INVOKERS,
}

METADATA_MAGIC = 0xFAB11BAF
METADATA_VERSION = 29


class Il2CppHostError(Il2CppLiveError):
    """Host-level named refusal beyond the live-resolver contract."""


class AliasRegistrationRefused(Il2CppHostError):
    """An alias spec is malformed, duplicate or outside the bound tables."""


class AliasNotRegistered(Il2CppHostError):
    """The requested alias is not registered with this host."""


class ModuleRegistrationRefused(Il2CppHostError):
    """A module observation is malformed or duplicate for this host."""


@dataclass(frozen=True)
class AliasSpec:
    """One registered alias: name, kind and the identity it must match.

    ``method`` aliases carry the exact metadata identity plus the optional
    signature model (validated against the identity row at resolution).
    ``invoker``/``generic_invoker`` aliases carry the table slot index.  No
    field may carry an address or RVA: resolution happens only through the
    live binding.
    """

    alias: str
    kind: str
    image: str = ''
    namespace: str = ''
    class_name: str = ''
    name: str = ''
    parameter_type_indices: tuple[int, ...] | None = None
    return_type_index: int | None = None
    expected_static: bool | None = None
    expected_parameter_count: int | None = None
    slot_index: int = -1
    module: str = ''

    def __post_init__(self) -> None:
        if type(self.alias) is not str or not self.alias:
            raise AliasRegistrationRefused('alias must be a nonempty string')
        if len(self.alias.encode('utf-8')) > MAX_ALIAS_BYTES:
            raise AliasRegistrationRefused(
                f'alias exceeds {MAX_ALIAS_BYTES} bytes')
        if any(ord(character) < 32 for character in self.alias):
            raise AliasRegistrationRefused(
                'alias contains control characters')
        if self.kind not in ALIAS_KINDS:
            raise AliasRegistrationRefused(
                f'kind must be one of {ALIAS_KINDS}')
        if type(self.module) is not str and self.module is not None:
            raise AliasRegistrationRefused('module must be a string')
        if self.parameter_type_indices is not None and (
                type(self.parameter_type_indices) is not tuple
                or any(type(item) is not int or item < 0
                       for item in self.parameter_type_indices)):
            raise AliasRegistrationRefused(
                'parameter_type_indices must be a tuple of nonnegative ints')
        if self.return_type_index is not None and (
                type(self.return_type_index) is not int
                or self.return_type_index < 0):
            raise AliasRegistrationRefused(
                'return_type_index must be a nonnegative int')
        if self.expected_static is not None and type(self.expected_static) is not bool:
            raise AliasRegistrationRefused('expected_static must be a bool')
        if self.expected_parameter_count is not None and (
                type(self.expected_parameter_count) is not int
                or self.expected_parameter_count < 0):
            raise AliasRegistrationRefused(
                'expected_parameter_count must be a nonnegative int')
        if self.kind == 'method':
            if self.slot_index != -1:
                raise AliasRegistrationRefused(
                    'method alias must not set slot_index')
            identity = (self.image, self.namespace, self.class_name, self.name)
            if not all(type(text) is str and text for text in identity):
                raise AliasRegistrationRefused(
                    'method alias requires image, namespace, class and name')
        else:
            if type(self.slot_index) is not int or self.slot_index < 0:
                raise AliasRegistrationRefused(
                    'table alias requires a nonnegative integer slot_index')
            identity = (self.image, self.namespace, self.class_name, self.name)
            extras = (self.parameter_type_indices, self.return_type_index,
                      self.expected_static, self.expected_parameter_count)
            if any(identity) or any(item is not None for item in extras):
                raise AliasRegistrationRefused(
                    'table alias must not carry method identity fields')


@dataclass(frozen=True)
class AliasResolution:
    """One proven live address for an alias, with its identity proof."""

    alias: str
    kind: str
    table: str
    slot_index: int
    va: int
    section: str
    live_base: int
    module_sha256: str
    metadata_sha256: str
    generation: int
    pointer_mode: str
    method_token: int | None = None
    image: str | None = None
    namespace: str | None = None
    class_name: str | None = None
    method_name: str | None = None
    is_static: bool | None = None
    parameter_count: int | None = None

    def to_dict(self) -> dict:
        result = {
            'alias': self.alias,
            'kind': self.kind,
            'table': self.table,
            'slot_index': self.slot_index,
            'va': self.va,
            'section': self.section,
            'live_base': self.live_base,
            'module_sha256': self.module_sha256,
            'metadata_sha256': self.metadata_sha256,
            'generation': self.generation,
            'pointer_mode': self.pointer_mode,
        }
        if self.kind == 'method':
            result.update({
                'method_token': self.method_token,
                'image': self.image,
                'namespace': self.namespace,
                'class': self.class_name,
                'name': self.method_name,
                'is_static': self.is_static,
                'parameter_count': self.parameter_count,
            })
        return result


def _module_name(name, what: str) -> str:
    if type(name) is not str or not name:
        raise ModuleRegistrationRefused(f'{what} must be a nonempty string')
    if len(name.encode('utf-8')) > MAX_MODULE_NAME_BYTES:
        raise ModuleRegistrationRefused(
            f'{what} exceeds {MAX_MODULE_NAME_BYTES} bytes')
    return name


class Il2CppRegistrationHost:
    """Alias provider bound to one IL2CPP module observation.

    Construction anchors the binding exactly like the live resolver;
    ``observe()`` re-checks fresh observations and refuses divergence with
    the stage-1 named classes, latching the host stale forever after any
    refusal.
    """

    def __init__(self, module_name: str, pe_bytes: bytes,
                 metadata_bytes: bytes, binding: ModuleBinding, *,
                 method_pointers: PointerTable,
                 invokers: PointerTable,
                 generic_invokers: PointerTable) -> None:
        self._module_name = _module_name(module_name, 'module name')
        # Foreign schemas are refused exactly as in stage 1: FormatError
        # from the bounded static parsers, no host-level reinterpretation.
        self._pe = WindowsPE(pe_bytes)
        self._metadata = MetadataV29(metadata_bytes)
        magic, version = struct.unpack_from('<Ii', self._metadata.data, 0)
        if magic != METADATA_MAGIC or version != METADATA_VERSION:
            raise FormatError(
                'Only explicitly declared IL2CPP metadata version 29 is '
                'supported')
        self._binding = binding
        self._tables = {
            TABLE_METHOD_POINTERS: method_pointers,
            TABLE_INVOKERS: invokers,
            TABLE_GENERIC_INVOKERS: generic_invokers,
        }
        # Bitness/SHA/extent/overlap refusals reuse the stage-1 classes.
        self._resolver = Il2CppLiveResolver(
            self._pe, self._metadata, binding,
            method_pointers=method_pointers,
            invokers=invokers,
            generic_invokers=generic_invokers)
        # Address-attribution map: the bound primary module plus other
        # deterministically injected observations.  This is a module map,
        # not a layout validator: real loaders never map overlapping
        # images, and a confused observation is caught at resolution, where
        # the alias target must stay inside the bound module.
        self._modules: dict[str, ModuleBinding] = {module_name: binding}
        self._module_image_sizes: dict[str, int] = {
            module_name: self._pe.image_size}
        self._aliases: dict[str, AliasSpec] = {}
        self._proofs: list[AliasResolution] = []
        self._observe_count = 0
        self._stale: tuple[type[Il2CppLiveError], str] | None = None

    # -- properties ------------------------------------------------------------

    @property
    def module_name(self) -> str:
        return self._module_name

    @property
    def binding(self) -> ModuleBinding:
        return self._binding

    @property
    def pe(self) -> WindowsPE:
        return self._pe

    @property
    def metadata(self) -> MetadataV29:
        return self._metadata

    @property
    def resolver(self) -> Il2CppLiveResolver:
        return self._resolver

    @property
    def tables(self) -> dict[str, PointerTable]:
        return dict(self._tables)

    @property
    def alias_names(self) -> tuple[str, ...]:
        return tuple(self._aliases)

    @property
    def is_stale(self) -> bool:
        return self._stale is not None

    # -- module map --------------------------------------------------------------

    def register_module(self, module_name: str, binding: ModuleBinding,
                        pe_bytes: bytes) -> None:
        """Register another observed module for cross-module attribution.

        The observation is deterministic (bytes + binding); validation reuses
        the stage-1 named classes: only matching bitness, matching SHA and a
        fitting image are admitted.  Duplicate names are refused.
        """
        name = _module_name(module_name, 'module name')
        if name in self._modules:
            raise ModuleRegistrationRefused(
                f'module {name!r} is already registered')
        pe = WindowsPE(pe_bytes)
        if pe.bitness != self._binding.bitness:
            raise BitnessMismatchRefused(
                f'module {name!r} bitness {pe.bitness} does not match bound '
                f'bitness {self._binding.bitness}')
        if binding.module_sha256 != pe.sha256:
            raise ModuleShaMismatchRefused(
                f'module {name!r} hash does not match its PE file hash')
        if binding.live_base + pe.image_size > (1 << binding.bitness):
            raise OutOfExtentRefused(
                f'module {name!r} live base {binding.live_base:#x} plus '
                f'image size {pe.image_size:#x} overflows the '
                f'{binding.bitness}-bit address space')
        self._modules[name] = binding
        self._module_image_sizes[name] = pe.image_size

    # -- binding re-verification ---------------------------------------------------

    def observe(self, *, live_base: int, module_sha256: str,
                generation: int) -> None:
        """Re-check a fresh module observation; divergence is refused.

        The stage-1 named classes are reused verbatim.  After any refusal
        the host latches stale: no further observation or alias resolution
        is accepted, because the binding proof is no longer trustworthy and
        the host never silently rebases.
        """
        if self._stale is not None:
            stale_class, message = self._stale
            raise stale_class(
                f'host binding is stale and refuses further observations: '
                f'{message}')
        try:
            self._resolver.observe(
                live_base=live_base,
                module_sha256=module_sha256,
                generation=generation)
        except Il2CppLiveError as error:
            self._stale = (type(error), str(error))
            raise
        self._observe_count += 1

    # -- alias registry ------------------------------------------------------------

    def register_alias(self, spec: AliasSpec) -> None:
        """Register one alias; duplicate names and slot bounds are refused.

        The target module must be the bound module: an alias that claims
        another module is cross-module confusion and is refused with the
        stage-1 ``TableConfusionRefused``.
        """
        if spec.alias in self._aliases:
            raise AliasRegistrationRefused(
                f'alias {spec.alias!r} is already registered')
        target_module = spec.module or self._module_name
        if target_module != self._module_name:
            raise TableConfusionRefused(
                f'alias {spec.alias!r} targets module {target_module!r} '
                f'but the host is bound to {self._module_name!r}')
        table = self._tables[KIND_TABLES[spec.kind]]
        if spec.kind != 'method':
            if spec.slot_index < 0 or spec.slot_index >= table.count:
                raise AliasRegistrationRefused(
                    f'alias {spec.alias!r} slot {spec.slot_index} is outside '
                    f'table {table.name!r} (count {table.count})')
        self._aliases[spec.alias] = spec

    def resolve_alias(self, alias: str) -> AliasResolution:
        """Resolve one registered alias through the live binding.

        Returns the proven ``(address, identity proof)`` as an
        :class:`AliasResolution`.  A stale host refuses with the latched
        stage-1 class; a resolved target inside another observed module's
        extent is cross-module confusion (``TableConfusionRefused``).
        """
        if self._stale is not None:
            stale_class, message = self._stale
            raise stale_class(
                f'cannot resolve {alias!r}: host binding is stale ({message})')
        spec = self._aliases.get(alias)
        if spec is None:
            raise AliasNotRegistered(
                f'alias {alias!r} is not registered')
        binding = self._binding
        if spec.kind == 'method':
            resolution = self._resolver.resolve_method(
                spec.image, spec.namespace, spec.class_name, spec.name,
                parameter_type_indices=spec.parameter_type_indices,
                return_type_index=spec.return_type_index,
                expected_static=spec.expected_static,
                expected_parameter_count=spec.expected_parameter_count)
            virtual_address = resolution.va
            section = resolution.section
            slot_index = resolution.method.method_index
            proof = AliasResolution(
                alias=alias,
                kind=spec.kind,
                table=KIND_TABLES[spec.kind],
                slot_index=slot_index,
                va=virtual_address,
                section=section,
                live_base=binding.live_base,
                module_sha256=binding.module_sha256,
                metadata_sha256=self._metadata.sha256,
                generation=binding.generation,
                pointer_mode=resolution.pointer_mode,
                method_token=resolution.method.token,
                image=resolution.method.image,
                namespace=resolution.method.namespace,
                class_name=resolution.method.class_name,
                method_name=resolution.method.name,
                is_static=resolution.method.is_static,
                parameter_count=len(resolution.method.parameters),
            )
        else:
            table = self._tables[KIND_TABLES[spec.kind]]
            virtual_address, section = self._resolver.resolve_table_pointer(
                table, spec.slot_index)
            proof = AliasResolution(
                alias=alias,
                kind=spec.kind,
                table=KIND_TABLES[spec.kind],
                slot_index=spec.slot_index,
                va=virtual_address,
                section=section,
                live_base=binding.live_base,
                module_sha256=binding.module_sha256,
                metadata_sha256=self._metadata.sha256,
                generation=binding.generation,
                pointer_mode=table.pointer_mode,
            )
        for name, other in self._modules.items():
            if name == self._module_name:
                continue
            image_size = self._module_image_sizes[name]
            if other.live_base <= virtual_address < other.live_base + image_size:
                raise TableConfusionRefused(
                    f'alias {alias!r} target {virtual_address:#x} resolves '
                    f'into module {name!r} extent '
                    f'[{other.live_base:#x},{other.live_base + image_size:#x})')
        self._proofs.append(proof)
        return proof

    # -- introspection ---------------------------------------------------------------

    def snapshot(self) -> dict:
        """Responsive, deterministic read of the whole host state."""
        resolver_snapshot = self._resolver.snapshot()
        return {
            'schema': SCHEMA,
            'module': {
                'name': self._module_name,
                'live_base': self._binding.live_base,
                'module_sha256': self._binding.module_sha256,
                'generation': self._binding.generation,
                'bitness': self._binding.bitness,
            },
            'pe': resolver_snapshot['pe'],
            'metadata': {
                'sha256': resolver_snapshot['metadata_sha256'],
                'version': METADATA_VERSION,
            },
            'tables': resolver_snapshot['tables'],
            'modules': {
                name: {
                    'live_base': module.live_base,
                    'module_sha256': module.module_sha256,
                    'generation': module.generation,
                    'bitness': module.bitness,
                    'image_size': self._module_image_sizes[name],
                }
                for name, module in self._modules.items()
            },
            'aliases': {
                name: {
                    'kind': spec.kind,
                    'table': KIND_TABLES[spec.kind],
                    'slot_index': spec.slot_index
                    if spec.kind != 'method' else None,
                    'module': spec.module or self._module_name,
                    **(({
                        'image': spec.image,
                        'namespace': spec.namespace,
                        'class': spec.class_name,
                        'name': spec.name,
                    }) if spec.kind == 'method' else {}),
                }
                for name, spec in self._aliases.items()
            },
            'proofs': [proof.to_dict() for proof in self._proofs],
            'observations': {
                'count': self._observe_count,
                'stale': self._stale is not None,
            },
            'counts': {
                'modules': len(self._modules),
                'aliases': len(self._aliases),
                'proofs': len(self._proofs),
            },
        }
