"""Bounded decoder/encoder model for CT custom data types (AP-08.3 stage 1).

This module is a pure static model: it parses custom type definitions from
the CT <CustomTypes> section and decodes/encodes owned byte spans with
explicit size, endianness, value range, byte reversal (inverse) and array
limits. It never reads or writes process memory and never executes table
Lua. No Cheat Engine implementation code is used; the contract is derived
from the public CT file format, where <CustomTypes> holds
<CustomType name="...">format</CustomType> definitions and value records
reference them with VariableType "Custom" plus a <CustomType> name.
https://www.cheatengine.org/ (custom types reference)
https://wiki.cheatengine.org/index.php?title=Lua:Class:MemoryRecord

Tables may also create custom types at runtime from table Lua (for example
`registerCustomTypeAutoAssembler` in game tables). Runtime-only definitions
are not visible in this static model and must stay blocked until a
converter/write gate exists.

Numeric semantics are explicit Native limits, not a claim to emulate every
CE display convention. The whole value is one integer over the complete
span in the configured endianness; signed types use two's complement over
the full bit width. The per-element view exposes each element of a
composite/array layout individually. Every failure is a named
CustomTypeError carrying code, reason, stage and an optional input offset,
and a stable JSON abort payload (CustomTypeAbort) so a future Lua host call
can abort cleanly without partial state or half-set values.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import xml.etree.ElementTree as ET


SCHEMA = 'ct2trainer-custom-type-profile/v1'
ABORT_SCHEMA = 'ct2trainer-custom-type-abort/v1'
MAX_NAME_LENGTH = 64
MAX_FORMAT_LENGTH = 4096
MAX_CUSTOM_SIZE = 4096
MAX_ARRAY_COUNT = 1024
MAX_FIELDS = 256
MAX_TYPE_DEFINITIONS = 1024

_ELEMENT_SIZES = ('1', '2', '4', '8')
_ENDIANNESS = ('little', 'big')
_SPACES = ' \t\r\n'
_FORMAT_CHARSET = re.compile(r'[0-9\[\] \t\r\n]+\Z')
_TOKEN = re.compile(r'[^ \t\r\n]+')
_ENTITY = re.compile(rb'<!\s*(?:DOCTYPE|ENTITY)\b', re.IGNORECASE)
_ENTITY_TEXT = re.compile(r'<!\s*(?:DOCTYPE|ENTITY)\b', re.IGNORECASE)
_SECTION_ATTRIBUTES = ('name', 'Endian', 'Inverse', 'Signed')


class CustomTypeError(ValueError):
    """Named bounded rejection with stable code, reason, stage and offset."""

    def __init__(self, reason: str, *, code: str, stage: str,
                 offset: int | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.code = code
        self.stage = stage
        self.offset = offset

    def to_abort(self) -> "CustomTypeAbort":
        """Stable named abort payload for a Lua host call."""
        return CustomTypeAbort(self.code, self.reason, self.offset, self.stage)


@dataclass(frozen=True)
class CustomTypeAbort:
    """Named abort a host call can return without any partial state."""

    code: str
    reason: str
    offset: int | None
    stage: str

    def to_dict(self) -> dict:
        return {'schema': ABORT_SCHEMA, 'code': self.code,
                'reason': self.reason, 'offset': self.offset,
                'stage': self.stage}


@dataclass(frozen=True)
class CustomField:
    """One element group: count repetitions of size bytes at byte offset."""

    size: int
    count: int
    offset: int


@dataclass(frozen=True)
class CustomTypeProfile:
    """Strict data model of one custom type definition."""

    name: str
    format_text: str
    endianness: str
    inverse: bool
    signed: bool
    fields: tuple
    size: int
    element_count: int


def _reject(code: str, reason: str, stage: str, offset: int | None = None) -> None:
    raise CustomTypeError(reason, code=code, stage=stage, offset=offset)


def _name(name, stage: str = 'parse') -> str:
    if not isinstance(name, str) or not name or len(name) > MAX_NAME_LENGTH:
        _reject('custom-name-invalid',
                f'Custom type name must be 1..{MAX_NAME_LENGTH} characters', stage)
    if name != name.strip(_SPACES) or any(not 32 <= ord(c) <= 126 for c in name):
        _reject('custom-name-invalid',
                'Custom type name must be printable ASCII without surrounding whitespace',
                stage)
    return name


def _endianness(value, stage: str = 'parse') -> str:
    if isinstance(value, str):
        text = value.strip(_SPACES).casefold()
        if text in _ENDIANNESS:
            return text
    _reject('custom-endianness-invalid',
            f'Endianness must be one of {" / ".join(_ENDIANNESS)}', stage)


def _flag(key: str, value, stage: str = 'parse') -> bool:
    if isinstance(value, bool):
        return value
    if type(value) is int and value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.strip(_SPACES) in ('0', '1'):
        return value.strip(_SPACES) == '1'
    _reject('custom-flag-invalid', f'{key} must be 0 or 1', stage)


def _element(name: str, token: str) -> tuple[int, int]:
    if '[' in token or ']' in token:
        if token.count('[') != 1 or token.count(']') != 1 or not token.endswith(']'):
            _reject('custom-format-array-syntax',
                    f'Malformed array token {token!r} in format of {name}', 'parse')
        base, _, inner = token.partition('[')
        inner = inner[:-1]
        if base not in _ELEMENT_SIZES:
            _reject('custom-format-unknown-size',
                    f'Array base size {base!r} is not one of 1/2/4/8 in format of {name}',
                    'parse')
        if not inner:
            _reject('custom-format-array-syntax',
                    f'Malformed array token {token!r} in format of {name}', 'parse')
        if len(inner) > 1 and inner[0] == '0':
            _reject('custom-array-count-invalid',
                    f'Array count in {token!r} must be a positive number without leading zeros in format of {name}',
                    'parse')
        count = int(inner)
        if count == 0:
            _reject('custom-array-count-invalid',
                    f'Array count 0 in {token!r} is not a positive number in format of {name}',
                    'parse')
        if count > MAX_ARRAY_COUNT:
            _reject('custom-array-count-exceeded',
                    f'Array count {count} exceeds {MAX_ARRAY_COUNT} in format of {name}', 'parse')
        return int(base), count
    if token in _ELEMENT_SIZES:
        return int(token), 1
    _reject('custom-format-unknown-size',
            f'Element size {token!r} is not one of 1/2/4/8 in format of {name}', 'parse')


def _fields(name: str, format_text) -> tuple[tuple, int]:
    if not isinstance(format_text, str):
        _reject('custom-format-invalid', 'Custom type format must be a string', 'parse')
    if len(format_text) > MAX_FORMAT_LENGTH:
        _reject('custom-format-invalid',
                f'Custom type format must be at most {MAX_FORMAT_LENGTH} characters', 'parse')
    if not format_text.strip(_SPACES):
        _reject('custom-format-empty', f'Empty format for custom type {name}', 'parse', 0)
    if _FORMAT_CHARSET.fullmatch(format_text) is None:
        for index, character in enumerate(format_text):
            if _FORMAT_CHARSET.fullmatch(character) is None:
                _reject('custom-format-unknown-character',
                        f'Unknown character {character!r} in format of {name}',
                        'parse', index)
        _reject('custom-format-unknown-character',
                f'Unknown character in format of {name}', 'parse', 0)
    tokens = [(match.start(), match.group()) for match in _TOKEN.finditer(format_text)]
    if not tokens:
        _reject('custom-format-empty', f'Empty format for custom type {name}', 'parse', 0)
    fields: list[CustomField] = []
    offset = 0
    for position, token in tokens:
        size, count = _element(name, token)
        if len(fields) >= MAX_FIELDS:
            _reject('custom-field-limit-exceeded',
                    f'More than {MAX_FIELDS} fields in format of {name}', 'parse', position)
        fields.append(CustomField(size, count, offset))
        offset += size * count
    total = offset
    if total > MAX_CUSTOM_SIZE:
        _reject('custom-size-limit-exceeded',
                f'Format of {name} spans {total} bytes, limit is {MAX_CUSTOM_SIZE}',
                'parse', tokens[-1][0])
    return tuple(fields), total


def parse_custom_type_definition(name, format_text, *, endianness: str = 'little',
                                 inverse: bool = False, signed: bool = False) -> CustomTypeProfile:
    """Build the strict model of one definition.

    Unknown or invalid names, format tokens, endianness and flags are named
    rejections with code, reason, stage and optional input offset. No silent
    fallback values are invented.
    """
    clean_name = _name(name)
    clean_endianness = _endianness(endianness)
    clean_inverse = _flag('Inverse', inverse)
    clean_signed = _flag('Signed', signed)
    fields, total = _fields(clean_name, format_text)
    element_count = sum(field.count for field in fields)
    return CustomTypeProfile(name=clean_name, format_text=format_text,
                             endianness=clean_endianness, inverse=clean_inverse,
                             signed=clean_signed, fields=fields, size=total,
                             element_count=element_count)


def validate_custom_type(profile) -> None:
    """Reconstruct every derived field; reject forged or tampered metadata."""
    if not isinstance(profile, CustomTypeProfile):
        _reject('custom-profile-invalid',
                'Custom type profile must be a CustomTypeProfile', 'parse')
    try:
        expected = parse_custom_type_definition(profile.name, profile.format_text,
                                                endianness=profile.endianness,
                                                inverse=profile.inverse,
                                                signed=profile.signed)
    except CustomTypeError:
        _reject('custom-profile-invalid',
                'Custom type profile metadata is not valid', 'parse')
    if expected != profile:
        _reject('custom-profile-invalid',
                'Custom type profile metadata does not match its definition', 'parse')


def _section_element(source) -> ET.Element:
    if isinstance(source, ET.Element):
        if source.tag != 'CustomTypes':
            _reject('custom-section-invalid',
                    f'Expected <CustomTypes>, found <{source.tag}>', 'parse')
        return source
    if isinstance(source, bytes):
        if _ENTITY.search(source) is not None:
            _reject('custom-section-invalid',
                    'DTD/ENTITY is not allowed in custom type input', 'parse')
        try:
            text = source.decode('utf-8')
        except UnicodeDecodeError as exc:
            _reject('custom-section-invalid',
                    f'Custom type XML is not valid UTF-8: {exc}', 'parse')
    elif isinstance(source, str):
        text = source
    else:
        _reject('custom-section-invalid',
                'Custom type section must be an element or XML text', 'parse')
    if _ENTITY_TEXT.search(text) is not None:
        _reject('custom-section-invalid',
                'DTD/ENTITY is not allowed in custom type input', 'parse')
    try:
        element = ET.fromstring(text)
    except ET.ParseError as exc:
        _reject('custom-section-invalid', f'Invalid custom type XML: {exc}', 'parse')
    if element.tag != 'CustomTypes':
        _reject('custom-section-invalid',
                f'Expected <CustomTypes>, found <{element.tag}>', 'parse')
    return element


def parse_custom_types_section(source) -> tuple[CustomTypeProfile, ...]:
    """Parse every definition of a <CustomTypes> section, strictly.

    Names must be unique, attribute names are limited to
    name/Endian/Inverse/Signed, and unknown members, missing names or more
    than MAX_TYPE_DEFINITIONS definitions are named rejections.
    """
    element = _section_element(source)
    children = list(element)
    if len(children) > MAX_TYPE_DEFINITIONS:
        _reject('custom-definition-limit-exceeded',
                f'More than {MAX_TYPE_DEFINITIONS} custom type definitions', 'parse')
    profiles: list[CustomTypeProfile] = []
    seen: set[str] = set()
    for child in children:
        if child.tag != 'CustomType':
            _reject('custom-section-invalid',
                    f'Unknown <CustomTypes> member <{child.tag}>', 'parse')
        name = child.attrib.get('name')
        if name is None:
            _reject('custom-name-missing', 'A <CustomType> element has no name', 'parse')
        unknown = [key for key in child.attrib if key not in _SECTION_ATTRIBUTES]
        if unknown:
            _reject('custom-attribute-unknown',
                    f'Unknown custom type attributes: {", ".join(sorted(unknown))}',
                    'parse')
        endianness = _endianness(child.attrib.get('Endian') or 'little')
        inverse = _flag('Inverse', child.attrib.get('Inverse', '0'))
        signed = _flag('Signed', child.attrib.get('Signed', '0'))
        profile = parse_custom_type_definition(name, child.text or '',
                                               endianness=endianness,
                                               inverse=inverse, signed=signed)
        if profile.name in seen:
            _reject('custom-name-duplicate',
                    f'Duplicate custom type name: {profile.name}', 'parse')
        seen.add(profile.name)
        profiles.append(profile)
    return tuple(profiles)


def _ct_root_element(source) -> ET.Element:
    if isinstance(source, bytes):
        if _ENTITY.search(source) is not None:
            _reject('custom-section-invalid',
                    'DTD/ENTITY is not allowed in CT input', 'parse')
        try:
            text = source.decode('utf-8')
        except UnicodeDecodeError as exc:
            _reject('custom-section-invalid', f'CT XML is not valid UTF-8: {exc}', 'parse')
    else:
        text = source
    if _ENTITY_TEXT.search(text) is not None:
        _reject('custom-section-invalid',
                'DTD/ENTITY is not allowed in CT input', 'parse')
    try:
        return ET.fromstring(text)
    except ET.ParseError as exc:
        _reject('custom-section-invalid', f'Invalid CT XML: {exc}', 'parse')


def custom_types_from_ct_root(source) -> tuple[CustomTypeProfile, ...]:
    """Find and parse the optional <CustomTypes> section of a CheatTable root.

    Returns an empty tuple when the section is absent. This is the static
    hook for CT import wiring; runtime Lua definitions (for example
    registerCustomTypeAutoAssembler in re2.CT) do not appear here and must
    keep their blocked capability state.
    """
    if isinstance(source, ET.Element):
        root = source
    elif isinstance(source, (str, bytes)):
        root = _ct_root_element(source)
    else:
        _reject('custom-section-invalid',
                'CT root must be an element or XML text', 'parse')
    if root.tag != 'CheatTable':
        _reject('custom-section-invalid',
                f'Expected <CheatTable>, found <{root.tag}>', 'parse')
    section = root.find('CustomTypes')
    return parse_custom_types_section(section) if section is not None else ()


def _span(profile: CustomTypeProfile, raw, stage: str) -> bytes:
    if not isinstance(raw, (bytes, bytearray)):
        _reject('custom-input-invalid', 'Value span must be bytes', stage)
    data = bytes(raw)
    if len(data) != profile.size:
        _reject('custom-span-mismatch',
                f'Expected exactly {profile.size} bytes for {profile.name}, got {len(data)}',
                stage, len(data))
    return data


def _stored(profile: CustomTypeProfile, span: bytes) -> bytes:
    return span[::-1] if profile.inverse else span


def _signed(value: int, bits: int) -> int:
    if value & (1 << (bits - 1)):
        return value - (1 << bits)
    return value


def _range(profile: CustomTypeProfile, bits: int) -> tuple[int, int]:
    if profile.signed:
        return -(1 << (bits - 1)), (1 << (bits - 1)) - 1
    return 0, (1 << bits) - 1


def decode_custom_value(profile: CustomTypeProfile, raw) -> int:
    """Decode the complete owned span as one integer.

    Bytes are read in memory order, reversed first for inverse types, then
    interpreted as a single value in the configured endianness over the full
    bit width. Signed types use two's complement.
    """
    validate_custom_type(profile)
    span = _span(profile, raw, 'decode')
    bits = profile.size * 8
    value = int.from_bytes(_stored(profile, span), profile.endianness)
    return _signed(value, bits) if profile.signed else value


def encode_custom_value(profile: CustomTypeProfile, value) -> bytes:
    """Encode one integer to exactly profile.size bytes.

    Signed and unsigned ranges are the two's complement range of the full bit
    width; out-of-range values are named rejections. Bytes are written in the
    configured endianness and reversed for inverse types.
    """
    validate_custom_type(profile)
    if type(value) is not int:
        _reject('custom-value-invalid', 'Value must be an integer', 'encode')
    bits = profile.size * 8
    lowest, highest = _range(profile, bits)
    if not lowest <= value <= highest:
        _reject('custom-value-out-of-range',
                f'Value {value} is outside {lowest}..{highest} for {profile.name}', 'encode')
    raw = (value & ((1 << bits) - 1)).to_bytes(profile.size, profile.endianness)
    return raw[::-1] if profile.inverse else raw


def decode_custom_fields(profile: CustomTypeProfile, raw) -> tuple[int, ...]:
    """Decode every element of a composite/array layout separately.

    Inverse reverses the complete span first; each element is then read in
    the configured endianness and signed mode of the type.
    """
    validate_custom_type(profile)
    span = _stored(profile, _span(profile, raw, 'decode'))
    values: list[int] = []
    for field in profile.fields:
        for index in range(field.count):
            start = field.offset + index * field.size
            element = int.from_bytes(span[start:start + field.size], profile.endianness)
            bits = field.size * 8
            values.append(_signed(element, bits) if profile.signed else element)
    return tuple(values)


def encode_custom_fields(profile: CustomTypeProfile, values) -> bytes:
    """Encode one integer per element; element count and range are checked.

    Ranges are per element rather than the whole span; an out-of-range
    element is rejected with its byte offset in the span.
    """
    validate_custom_type(profile)
    if not isinstance(values, (tuple, list)):
        _reject('custom-field-input-invalid',
                'Fields must be a tuple or list of integers', 'encode')
    layout = [(field, index) for field in profile.fields for index in range(field.count)]
    if len(values) != len(layout):
        _reject('custom-field-count-mismatch',
                f'Expected {len(layout)} elements for {profile.name}, got {len(values)}',
                'encode', len(values))
    chunks: list[bytes] = []
    for position, (value, (field, index)) in enumerate(zip(values, layout)):
        offset = field.offset + index * field.size
        if type(value) is not int:
            _reject('custom-value-invalid', 'Field value must be an integer', 'encode', offset)
        bits = field.size * 8
        lowest, highest = _range(profile, bits)
        if not lowest <= value <= highest:
            _reject('custom-value-out-of-range',
                    f'Element {position} is outside {lowest}..{highest} for {profile.name}',
                    'encode', offset)
        chunks.append((value & ((1 << bits) - 1)).to_bytes(field.size, profile.endianness))
    raw = b''.join(chunks)
    return raw[::-1] if profile.inverse else raw


def format_custom_value(profile: CustomTypeProfile, raw) -> str:
    """Decimal display of the complete value; signed types show negatives."""
    return str(decode_custom_value(profile, raw))
