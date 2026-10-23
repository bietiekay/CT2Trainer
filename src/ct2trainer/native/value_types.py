"""Independent bounded codecs for CT byte arrays and little-endian bit fields.

Published MemoryRecord documentation defines Aob.Size and Binary.Startbit/Size.
The Native profile maps their CT ByteLength and BitStart/BitLength properties;
it does not import CE implementations. Literal policies below are explicit
Native limits, not a claim to emulate every CE input or display convention.
https://wiki.cheatengine.org/index.php?title=Lua:Class:MemoryRecord
https://www.cheatengine.org/help/Scriptengine.htm

Mask merging preserves the supplied snapshot's adjacent bits. It is not an
atomic remote-memory transaction; the runtime owns rereads, target identity,
conflict checks, confirmation and cancellation before publishing any bytes.
"""

from __future__ import annotations

from collections.abc import Mapping
import json
import re
from typing import Any


SCHEMA = 'ct2trainer-value-profile/v1'
MAX_BYTE_LENGTH = 65536
MAX_BIT_LENGTH = 64
_SPACES = ' \t\r\n'
_BYTE_TEXT = re.compile(r'[0-9a-fA-F]{2}(?:[ \t\r\n]+[0-9a-fA-F]{2})*\Z')


class ValueTypeError(ValueError):
    """Unsupported metadata, incomplete memory snapshots or invalid literals."""


def _integer_property(properties: Mapping, key: str, minimum: int, maximum: int) -> int:
    value = properties.get(key)
    if isinstance(value, str) and len(value) <= 20:
        text = value.strip(_SPACES)
        if re.fullmatch(r'[0-9]+', text):
            value = int(text)
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueTypeError(f'{key} must be a decimal integer between {minimum} and {maximum}')
    return value


def _flag(properties: Mapping, key: str) -> bool:
    value = properties.get(key)
    if value is None:
        return False
    if type(value) is bool:
        return value
    if type(value) is int and value in {0, 1}:
        return bool(value)
    if isinstance(value, str) and len(value) <= 8:
        value = value.strip(_SPACES)
        if value in {'0', '1'}:
            return value == '1'
    raise ValueTypeError(key + ' must be 0 or 1')


def prepare_value_profile(variable_type: str, xml_properties: Mapping[str, Any]) -> dict:
    """Create canonical JSON metadata without reading or writing any memory.

    Required lengths/offsets must be explicit decimal values. Unrelated XML
    record properties are ignored; the canonical profile stores only relevant
    normalized fields. Byte arrays always display exact hexadecimal byte pairs,
    independent of their generic ShowAsHex/ShowAsSigned flags. A zero length is
    a non-actionable, read-only placeholder: callers should present navigation
    and must not invent a target read/write range for it.

    Binary fields use LSB0 within their starting byte, then little-endian bytes.
    Decimal signed mode uses two's complement of BitLength bits. Binary/hex modes
    are raw unsigned patterns, even if ShowAsSigned is set. Binary output has
    exactly BitLength digits, most significant first; hex output is uppercase.
    Simultaneous binary/hex modes are rejected rather than assigning precedence.
    """
    if variable_type == 'String':
        from .string_values import prepare
        try:
            properties = dict(xml_properties)
            display = {key: _flag(properties, key) for key in ('ShowAsHex','ShowAsSigned','ShowAsBinary')}
            if display['ShowAsHex']:
                # RT-4.4 (O7): a ShowAsHex string record exposes the bounded
                # byte buffer of the string as a byte-array value.  The
                # canonical length bounds of the string codec still apply
                # (Length, Unicode, CodePage, ZeroTerminate); the write path
                # accepts exact hex byte sequences over the full buffer and
                # the display is the raw byte view.  The literal-text codec
                # and its encoding rules do not apply to this presentation.
                base = prepare(properties)
                result = {'kind': 'byte_array', 'size': base['size'],
                          'byte_order': 'address', 'display': 'hex_bytes',
                          'signed': False, 'actionable': base['actionable'],
                          'read_only': not base['actionable'],
                          'reason': ('Zero-length string is a non-actionable table placeholder.'
                                     if not base['actionable'] else '')}
                return {'schema': SCHEMA, 'variable_type': 'String',
                        'properties': {**base['properties'], **display}, **result}
            if display['ShowAsBinary']:
                # WP-34: name the display flag so the catalog reason reads as
                # a hex-string byte-view boundary, not a generic display rule.
                raise ValueTypeError('Strings require literal text display; the '
                                     + 'ShowAsBinary byte view is unsupported.')
            result = prepare(properties)
            return {**result, 'schema':SCHEMA, 'variable_type':'String',
                    'properties':{**result['properties'], **display},
                    'byte_order':'little' if result['unit_bytes']==2 else 'address',
                    'signed':False, 'read_only':not result['actionable'],
                    'reason':'Zero-length string is a non-actionable table placeholder.' if not result['actionable'] else ''}
        except (TypeError,ValueError) as error:
            raise ValueTypeError(str(error)) from error
    if not isinstance(xml_properties, Mapping):
        raise ValueTypeError('Value properties must be a mapping')
    hex_mode = _flag(xml_properties, 'ShowAsHex')
    signed_mode = _flag(xml_properties, 'ShowAsSigned')
    binary_mode = _flag(xml_properties, 'ShowAsBinary')
    properties = {'ShowAsHex': hex_mode, 'ShowAsSigned': signed_mode,
                  'ShowAsBinary': binary_mode}
    if variable_type == 'Array of byte':
        length = _integer_property(xml_properties, 'ByteLength', 0, MAX_BYTE_LENGTH)
        if binary_mode:
            raise ValueTypeError('Byte arrays use hex byte pairs; binary display is unsupported')
        properties['ByteLength'] = length
        result = {'kind': 'byte_array', 'size': length, 'byte_order': 'address',
                  'display': 'hex_bytes', 'signed': False, 'actionable': length > 0,
                  'read_only': length == 0,
                  'reason': 'Zero-length byte array is a non-actionable table placeholder.' if length == 0 else ''}
    elif variable_type == 'Binary':
        start = _integer_property(xml_properties, 'BitStart', 0, 7)
        length = _integer_property(xml_properties, 'BitLength', 1, MAX_BIT_LENGTH)
        if binary_mode and hex_mode:
            raise ValueTypeError('Binary and hexadecimal display flags conflict')
        properties.update(BitStart=start, BitLength=length)
        display = 'binary' if binary_mode else 'hex' if hex_mode else 'decimal'
        result = {'kind': 'bitfield', 'size': (start + length + 7) // 8,
                  'byte_order': 'little', 'bit_order': 'lsb0', 'display': display,
                  'signed': signed_mode and display == 'decimal',
                  'actionable': True, 'read_only': False, 'reason': ''}
    else:
        raise ValueTypeError('Unsupported value type: ' + str(variable_type))
    return {'schema': SCHEMA, 'variable_type': variable_type,
            'properties': properties, **result}


def validate_value_profile(profile: dict) -> None:
    """Reconstruct every derived field; reject extra or forged JSON metadata."""
    if not isinstance(profile, dict) or profile.get('schema') != SCHEMA:
        raise ValueTypeError('Invalid value profile schema')
    expected = prepare_value_profile(profile.get('variable_type'), profile.get('properties'))
    try:
        actual_json = json.dumps(profile, sort_keys=True, separators=(',', ':'), allow_nan=False)
        expected_json = json.dumps(expected, sort_keys=True, separators=(',', ':'), allow_nan=False)
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ValueTypeError('Value profile must contain valid JSON primitives') from exc
    if actual_json != expected_json:
        raise ValueTypeError('Value profile metadata does not match its properties')


def profile_size(profile: dict) -> int:
    """Required complete memory span, or zero for a non-actionable placeholder."""
    validate_value_profile(profile)
    return profile['size']


def _raw(profile: dict, value: Any, label: str) -> bytes:
    if not isinstance(value, (bytes, bytearray)) or len(value) != profile['size']:
        raise ValueTypeError(label + ' must contain the exact complete value span')
    return bytes(value)


def _mask(profile: dict) -> bytes:
    if profile['kind'] in {'byte_array','string'}:
        return b'\xff' * profile['size']
    properties = profile['properties']
    value = ((1 << properties['BitLength']) - 1) << properties['BitStart']
    return value.to_bytes(profile['size'], 'little')


def profile_mask(profile: dict) -> bytes:
    """Ownership bits per byte; zero-length placeholders return an empty mask."""
    validate_value_profile(profile)
    return _mask(profile)


def _actionable(profile: dict) -> None:
    if not profile['actionable']:
        raise ValueTypeError('Zero-length byte array is a non-actionable placeholder')


def merge_profile_value(profile: dict, desired_bytes: bytes, current_bytes: bytes) -> bytes:
    """Merge owned bits into a fresh snapshot for each write/freeze tick.

    Desired bytes may contain stale adjacent bits from an earlier parse; those
    bits are ignored. The caller must acquire and confirm current_bytes freshly
    and use overlapping ownership masks, rather than whole-byte equality, when
    admitting simultaneous bit fields or testing their current frozen state.
    """
    validate_value_profile(profile)
    _actionable(profile)
    if profile['kind']=='string':
        _string_match(profile, desired_bytes, _raw(profile,current_bytes,'Current bytes'))
        return desired_bytes
    desired = _raw(profile, desired_bytes, 'Desired bytes')
    current = _raw(profile, current_bytes, 'Current bytes')
    return bytes((old & (~mask & 0xff)) | (new & mask)
                 for old, new, mask in zip(current, desired, _mask(profile)))


def profile_value_matches(profile: dict, desired_bytes: bytes, current_bytes: bytes) -> bool:
    """Compare only owned bits, permitting unrelated adjacent-bit changes."""
    validate_value_profile(profile)
    _actionable(profile)
    if profile['kind']=='string':
        return _string_match(profile,desired_bytes,_raw(profile,current_bytes,'Current bytes'))
    desired = _raw(profile, desired_bytes, 'Desired bytes')
    current = _raw(profile, current_bytes, 'Current bytes')
    return all((old & mask) == (new & mask)
               for old, new, mask in zip(current, desired, _mask(profile)))


def parse_profile_value(profile: dict, text: str, current_bytes: bytes | None = None) -> bytes:
    """Parse bounded complete literals; no expressions, wildcards or evaluation.

    Byte arrays require exactly ByteLength two-digit hex tokens separated by
    ASCII whitespace. Bit fields require a complete current snapshot to preserve
    all unowned bits. Decimal accepts signed literals only within the configured
    signed/unsigned field range; binary accepts 1..BitLength digits; hex accepts
    1..ceil(BitLength/4) digits with an optional 0x prefix. No mode auto-detection.
    """
    validate_value_profile(profile)
    _actionable(profile)
    if not isinstance(text, str):
        raise ValueTypeError('Value must be a literal string')
    if profile['kind']=='string':
        from .string_values import prepare, parse
        if current_bytes is not None:_raw(profile,current_bytes,'Current bytes')
        try:return parse(prepare(profile['properties']),text).replacement
        except ValueError as error:raise ValueTypeError(str(error)) from error
    if profile['kind'] == 'byte_array':
        if len(text) > profile['size'] * 3 + 64:
            raise ValueTypeError('Byte array literal exceeds its size bound')
        literal = text.strip(_SPACES)
        if _BYTE_TEXT.fullmatch(literal) is None:
            raise ValueTypeError('Enter exact hex byte pairs without wildcards')
        values = literal.split()
        if len(values) != profile['size']:
            raise ValueTypeError('Byte array must contain exactly ByteLength hex bytes')
        if current_bytes is not None:
            _raw(profile, current_bytes, 'Current bytes')
        return bytes(int(value, 16) for value in values)
    if len(text) > 66:
        raise ValueTypeError('Bit-field literal exceeds its size bound')
    current = _raw(profile, current_bytes, 'Current bytes')
    literal = text.strip(_SPACES)
    length = profile['properties']['BitLength']
    display = profile['display']
    if display == 'binary':
        if re.fullmatch(r'[01]{1,' + str(length) + '}', literal) is None:
            raise ValueTypeError('Enter binary digits within BitLength')
        number = int(literal, 2)
    elif display == 'hex':
        if re.fullmatch(r'(?:0[xX])?[0-9a-fA-F]{1,' + str((length + 3) // 4) + '}', literal) is None:
            raise ValueTypeError('Enter hexadecimal digits within BitLength')
        number = int(literal, 16)
    else:
        if re.fullmatch(r'[+-]?[0-9]+', literal) is None:
            raise ValueTypeError('Enter a whole decimal number')
        number = int(literal, 10)
    minimum = -(1 << (length - 1)) if profile['signed'] else 0
    maximum = (1 << (length - int(profile['signed']))) - 1
    if not minimum <= number <= maximum:
        raise ValueTypeError(f'Bit-field value must be between {minimum} and {maximum}')
    field = number & ((1 << length) - 1)
    field <<= profile['properties']['BitStart']
    desired = field.to_bytes(profile['size'], 'little')
    mask = _mask(profile)
    return bytes((old & (~owned & 0xff)) | (new & owned)
                 for old, new, owned in zip(current, desired, mask))


def format_profile_value(profile: dict, raw: bytes) -> str:
    """Format a complete snapshot using the explicit canonical display policy."""
    validate_value_profile(profile)
    value = _raw(profile, raw, 'Read bytes')
    if profile['kind']=='string':
        from .string_values import prepare,format_value
        try:return format_value(prepare(profile['properties']),value)
        except ValueError as error:raise ValueTypeError(str(error)) from error
    if profile['kind'] == 'byte_array':
        return ' '.join(f'{byte:02X}' for byte in value)
    length = profile['properties']['BitLength']
    number = (int.from_bytes(value, 'little') >> profile['properties']['BitStart']) & ((1 << length) - 1)
    if profile['display'] == 'binary':
        return format(number, '0' + str(length) + 'b')
    if profile['display'] == 'hex':
        return format(number, 'X')
    if profile['signed'] and number & (1 << (length - 1)):
        number -= 1 << length
    return str(number)


def _string_match(profile,desired,current):
    from .string_values import prepare,LiteralWrite,desired_matches
    try:
        codec=prepare(profile['properties'])
        return desired_matches(codec,LiteralWrite(desired,codec['size'],codec['unit_bytes']),current)
    except ValueError as error:raise ValueTypeError(str(error)) from error


def format_written_profile_value(profile,raw):
    """Canonical written intent display; padded bytes are never a write span."""
    validate_value_profile(profile)
    if profile['kind']!='string':return format_profile_value(profile,raw)
    _string_match(profile,raw,bytes(profile['size']))
    return format_profile_value(profile,raw+bytes(profile['size']-len(raw)))
