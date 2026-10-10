"""Bounded static Python adaptation of a pinned MIT LibCpp2IL subset.

Upstream: SamboyCoding/Cpp2IL b5ad444b82267cb1e4b88b8b373c008105bdea52.
Copyright (c) 2020 Sam Byass; MIT (retained in upstream/LICENSE).
Local adaptation copyright (c) 2026 CT2Trainer contributors; MIT.
Only PE file mapping and declared metadata-v29 identity rows are interpreted.
There is no loader, live pointer/JIT resolver, native invocation or target write.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import struct

MAX_PE_BYTES = 256 * 1024 * 1024
MAX_METADATA_BYTES = 64 * 1024 * 1024
MAX_ROWS = 100_000
MAX_STRING_BYTES = 4096
MAX_DECODED_NAME_BYTES = 16 * 1024 * 1024


class FormatError(ValueError):
    pass


def _range(offset: int, size: int, length: int) -> None:
    if type(offset) is not int or type(size) is not int or offset < 0 or size < 0 or offset > length or size > length - offset:
        raise FormatError('File extent is negative, overflowing or truncated')


def _unpack(data: bytes, offset: int, fmt: str):
    _range(offset, struct.calcsize(fmt), len(data))
    return struct.unpack_from(fmt, data, offset)


def _bytes(data, maximum):
    if type(data) is not bytes or not 64 <= len(data) <= maximum:
        raise FormatError('An immutable bounded file snapshot is required')
    return data


def read_snapshot(path: str | Path, maximum: int) -> bytes:
    if type(maximum) is not int or not 64 <= maximum <= MAX_PE_BYTES:
        raise ValueError('Invalid file snapshot bound')
    with Path(path).open('rb') as stream:
        data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise FormatError('File exceeds the explicit snapshot bound')
    return data


@dataclass(frozen=True)
class PESection:
    name: bytes
    rva: int
    virtual_size: int
    raw_offset: int
    raw_size: int
    characteristics: int


class WindowsPE:
    """Preferred-image file mapping; source bytes never become live addresses."""
    def __init__(self, data: bytes):
        self.data = _bytes(data, MAX_PE_BYTES)
        if data[:2] != b'MZ':
            raise FormatError('Missing DOS signature')
        pe, = _unpack(data, 60, '<I')
        if not 64 <= pe <= 1024 * 1024 or data[pe:pe + 4] != b'PE\0\0':
            raise FormatError('Invalid bounded PE signature offset')
        machine, count, _, _, _, optional_size, _ = _unpack(data, pe + 4, '<HHIIIHH')
        optional = pe + 24
        _range(optional, optional_size, len(data))
        magic, = _unpack(data, optional, '<H')
        if (machine, magic) == (0x14C, 0x10B):
            self.bitness, minimum, directory_count_at = 32, 96, 92
            self.image_base, = _unpack(data, optional + 28, '<I')
        elif (machine, magic) == (0x8664, 0x20B):
            self.bitness, minimum, directory_count_at = 64, 112, 108
            self.image_base, = _unpack(data, optional + 24, '<Q')
        else:
            raise FormatError('Only matching Windows I386/PE32 and AMD64/PE32+ are admitted')
        if not minimum <= optional_size <= 4096 or not 1 <= count <= 96:
            raise FormatError('Optional header or section count exceeds the declared PE subset')
        alignment, file_alignment = _unpack(data, optional + 32, '<II')
        self.image_size, self.header_size = _unpack(data, optional + 56, '<II')
        directories, = _unpack(data, optional + directory_count_at, '<I')
        if directories > 16 or minimum + 8 * directories > optional_size:
            raise FormatError('PE data directories exceed optional-header extent')
        if (not alignment or alignment & (alignment - 1) or not 512 <= file_alignment <= 65536
                or file_alignment & (file_alignment - 1) or alignment < file_alignment):
            raise FormatError('Unsupported PE section/file alignment')
        sections_at = optional + optional_size
        _range(sections_at, count * 40, len(data))
        if (self.header_size < sections_at + count * 40 or self.header_size > len(data)
                or self.header_size % file_alignment or not self.image_size or self.image_size % alignment
                or self.image_base > (1 << self.bitness) - self.image_size):
            raise FormatError('Invalid header/image size or image-base overflow')
        sections = []
        virtual_extents = [(0, self.header_size)]
        raw_extents = [(0, self.header_size)]
        for index in range(count):
            name, virtual_size, rva, raw_size, raw, _, _, _, _, characteristics = _unpack(
                data, sections_at + index * 40, '<8sIIIIIIHHI')
            extent = virtual_size or raw_size
            if (not extent or rva % alignment or rva > self.image_size or extent > self.image_size - rva
                    or raw_size % file_alignment or raw_size and raw % file_alignment):
                raise FormatError('Invalid section extent/alignment')
            _range(raw, raw_size, len(data))
            if not raw_size and raw:
                raise FormatError('Empty raw section has a nonzero file pointer')
            for start, size in virtual_extents:
                if rva < start + size and start < rva + extent:
                    raise FormatError('Overlapping virtual sections or headers')
            if raw_size:
                for start, size in raw_extents:
                    if raw < start + size and start < raw + raw_size:
                        raise FormatError('Overlapping raw sections or headers')
                raw_extents.append((raw, raw_size))
            virtual_extents.append((rva, extent))
            sections.append(PESection(name.rstrip(b'\0'), rva, extent, raw, raw_size, characteristics))
        self.sections = tuple(sections)
        self.sha256 = sha256(data).hexdigest()

    def rva_to_offset(self, rva: int, size: int = 1) -> int:
        _range(rva, size, self.image_size)
        if not size:
            raise FormatError('A mapping requires positive extent')
        if rva < self.header_size and size <= self.header_size - rva:
            return rva
        matches = [section for section in self.sections
                   if section.rva <= rva and size <= section.virtual_size - (rva - section.rva)]
        if len(matches) != 1:
            raise FormatError('RVA range crosses or misses a unique section')
        section = matches[0]
        displacement = rva - section.rva
        if displacement > section.raw_size or size > section.raw_size - displacement:
            raise FormatError('RVA refers to virtual zero-fill rather than source bytes')
        return section.raw_offset + displacement

    def va_to_offset(self, preferred_va: int, size: int = 1) -> int:
        if type(preferred_va) is not int or preferred_va < self.image_base or preferred_va >= 1 << self.bitness:
            raise FormatError('Preferred VA is outside the declared image width/base')
        return self.rva_to_offset(preferred_va - self.image_base, size)

    def read_rva(self, rva: int, size: int) -> bytes:
        offset = self.rva_to_offset(rva, size)
        return self.data[offset:offset + size]


# v29: two signed 32-bit fields per section; no >=38 count or variable-width indices.
METADATA_SECTIONS = (
    'stringLiteral', 'stringLiteralData', 'string', 'events', 'properties', 'methods',
    'parameterDefaultValues', 'fieldDefaultValues', 'fieldAndParameterDefaultValueData',
    'fieldMarshaledSizes', 'parameters', 'fields', 'genericParameters',
    'genericParameterConstraints', 'genericContainers', 'nestedTypes', 'interfaces',
    'vtableMethods', 'interfaceOffsets', 'typeDefinitions', 'images', 'assemblies',
    'fieldRefs', 'referencedAssemblies', 'attributeData', 'attributeDataRange',
    'unresolvedVirtualCallParameterTypes', 'unresolvedVirtualCallParameterRanges',
    'windowsRuntimeTypeNames', 'windowsRuntimeStrings', 'exportedTypeDefinitions',
)
HEADER_SIZE = 8 + len(METADATA_SECTIONS) * 8


@dataclass(frozen=True)
class ParameterIdentity:
    name: str
    token: int
    type_index: int


@dataclass(frozen=True)
class MethodIdentity:
    metadata_sha256: str
    image: str
    namespace: str
    class_name: str
    name: str
    method_index: int
    token: int
    return_type_index: int
    parameters: tuple[ParameterIdentity, ...]
    flags: int
    implementation_flags: int
    generic_container_index: int

    @property
    def is_static(self) -> bool:
        return bool(self.flags & 0x10)


def _row_range(first: int, count: int, total: int) -> range:
    if not count and first == -1:
        return range(0)
    _range(first, count, total)
    return range(first, first + count)


class MetadataV29:
    """Exact static image/type/method identity; raw type indices stay unresolved."""
    def __init__(self, data: bytes):
        self.data = _bytes(data, MAX_METADATA_BYTES)
        magic, version = _unpack(data, 0, '<Ii')
        if magic != 0xFAB11BAF or version != 29:
            raise FormatError('Only explicitly declared IL2CPP metadata version 29 is supported')
        _range(0, HEADER_SIZE, len(data))
        self.sha256 = sha256(data).hexdigest()
        sections, extents = {}, []
        for index, name in enumerate(METADATA_SECTIONS):
            offset, size = _unpack(data, 8 + index * 8, '<ii')
            _range(offset, size, len(data))
            if size:
                if offset < HEADER_SIZE:
                    raise FormatError('Metadata section intersects the header')
                if any(offset < start + count and start < offset + size for start, count in extents):
                    raise FormatError('Metadata sections overlap')
                extents.append((offset, size))
            elif offset and offset < HEADER_SIZE:
                raise FormatError('Empty metadata section points inside the header')
            sections[name] = (offset, size)
        self._sections = sections
        self._strings = data[sections['string'][0]:sum(sections['string'])]
        strides = {'images': 40, 'typeDefinitions': 88, 'methods': 32, 'parameters': 12}
        counts = []
        for name, stride in strides.items():
            size = sections[name][1]
            if size % stride:
                raise FormatError('Metadata row bytes violate exact v29 layout: ' + name)
            counts.append(size // stride)
        if sum(counts) > MAX_ROWS:
            raise FormatError('Aggregate identity rows exceed the work bound')
        self._string_cache = {}
        self._decoded_name_bytes = 0
        self._images = self._rows('images', '<iiiIiIiIiI')
        self._types = self._rows('typeDefinitions', '<7iI8i8HII')
        self._methods = self._rows('methods', '<5iI4H')
        self._parameters = self._rows('parameters', '<iIi')
        total = sum(map(len, (self._images, self._types, self._methods, self._parameters)))
        if total > MAX_ROWS:
            raise FormatError('Aggregate identity rows exceed the work bound')
        if not self._images:
            raise FormatError('Metadata has no declared images')
        owners = {}
        for image_index, image in enumerate(self._images):
            self._string(image[0])
            if image[1] < 0:
                raise FormatError('Image assembly index is negative')
            for type_index in _row_range(image[2], image[3], len(self._types)):
                if type_index in owners:
                    raise FormatError('Type belongs to multiple images')
                owners[type_index] = image_index
        if len(owners) != len(self._types):
            raise FormatError('Orphan type identity row')
        method_owners, parameter_owners = {}, set()
        for type_index, row in enumerate(self._types):
            self._string(row[0]); self._string(row[1])
            for method_index in _row_range(row[9], row[16], len(self._methods)):
                if method_index in method_owners or self._methods[method_index][1] != type_index:
                    raise FormatError('Method owner/range disagrees with its declaring type')
                method_owners[method_index] = type_index
        if len(method_owners) != len(self._methods):
            raise FormatError('Orphan method identity row')
        identities = []
        for index, row in enumerate(self._methods):
            name, _, return_index, first_parameter, generic, token, flags, iflags, _, count = row
            if return_index < 0 or generic < -1 or not token:
                raise FormatError('Invalid method type/generic index or token')
            parameters = []
            for parameter_index in _row_range(first_parameter, count, len(self._parameters)):
                if parameter_index in parameter_owners:
                    raise FormatError('Parameter identity belongs to multiple methods')
                parameter_owners.add(parameter_index)
                parameter_name, parameter_token, type_index = self._parameters[parameter_index]
                if type_index < 0 or not parameter_token:
                    raise FormatError('Invalid parameter type index or token')
                parameters.append(ParameterIdentity(self._string(parameter_name), parameter_token, type_index))
            declaring = self._types[method_owners[index]]
            image = self._images[owners[method_owners[index]]]
            identities.append(MethodIdentity(self.sha256, self._string(image[0]), self._string(declaring[1]),
                                             self._string(declaring[0]), self._string(name), index, token,
                                             return_index, tuple(parameters), flags, iflags, generic))
        if len(parameter_owners) != len(self._parameters):
            raise FormatError('Orphan parameter identity row')
        self.methods = tuple(identities)

    def _rows(self, section: str, fmt: str) -> tuple[tuple, ...]:
        offset, size = self._sections[section]
        stride = struct.calcsize(fmt)
        if size % stride or size // stride > MAX_ROWS:
            raise FormatError('Metadata row bytes violate exact v29 layout or row limit: ' + section)
        return tuple(_unpack(self.data, offset + index, fmt) for index in range(0, size, stride))

    def _string(self, index: int) -> str:
        if index in self._string_cache:
            return self._string_cache[index]
        if type(index) is not int or not 0 <= index < len(self._strings):
            raise FormatError('Metadata string index is outside its bounded pool')
        end = self._strings.find(b'\0', index, min(len(self._strings), index + MAX_STRING_BYTES + 1))
        if end < 0:
            raise FormatError('Metadata name is not bounded and NUL terminated')
        try:
            result = self._strings[index:end].decode('utf-8', errors='strict')
        except UnicodeError as error:
            raise FormatError('Metadata name is not valid UTF-8') from error
        if any(ord(character) < 32 for character in result):
            raise FormatError('Metadata name contains control characters')
        size = end - index
        if size > MAX_DECODED_NAME_BYTES - self._decoded_name_bytes:
            raise FormatError('Aggregate decoded identity names exceed their byte bound')
        self._decoded_name_bytes += size
        self._string_cache[index] = result
        return result

    def find_method(self, image: str, namespace: str, class_name: str, name: str, *,
                    parameter_type_indices: tuple[int, ...] | None = None,
                    return_type_index: int | None = None) -> MethodIdentity:
        if any(type(text) is not str or len(text.encode('utf-8')) > MAX_STRING_BYTES
               for text in (image, namespace, class_name, name)):
            raise ValueError('Bounded exact identity strings are required')
        if parameter_type_indices is not None and (type(parameter_type_indices) is not tuple
                or len(parameter_type_indices) > 65535 or any(type(item) is not int or item < 0 for item in parameter_type_indices)):
            raise ValueError('Raw parameter indices must be an explicit bounded tuple')
        if return_type_index is not None and (type(return_type_index) is not int or return_type_index < 0):
            raise ValueError('A nonnegative raw return type index is required')
        matches = [method for method in self.methods
                   if (method.image, method.namespace, method.class_name, method.name) == (image, namespace, class_name, name)
                   and (parameter_type_indices is None or tuple(p.type_index for p in method.parameters) == parameter_type_indices)
                   and (return_type_index is None or method.return_type_index == return_type_index)]
        if len(matches) != 1:
            raise FormatError('Method identity is missing or ambiguous; specify exact raw signature indices')
        return matches[0]
