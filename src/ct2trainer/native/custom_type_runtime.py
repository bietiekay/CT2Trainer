"""Bounded custom-type write/convert gate, Lua abort path and RE2 registry
(AP-08.7).

Builds exact byte-level write plans from parsed CustomTypeProfiles using the
owned custom_types codec: byte order, endianness, signedness and value ranges
are fixed by the profile. Every plan is deterministic and passes an inverse
readback check: re-decoding the plan bytes with the profile must yield the
original value, re-encoding it must reproduce the identical span, and for
inverse types reversing the span must yield the exact non-inverse encoding.
Plans are pure model objects; this module never reads or writes process
memory, so the gate is a converter contract, not a live write.

The Lua abort path mirrors the lua_host wiring contract without touching
lua_host.py: a CustomTypeError becomes a named, JSON-capable abort payload
(schema/code/reason/offset/stage) plus a bounded host error message that
never carries a Python traceback.

RE2-style custom records register with a named block reason: the write gate
stays closed, but the reason is visible in reports. Registration carries an
owning scope, rejects duplicate record ids, and tears down idempotently.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from .custom_types import (ABORT_SCHEMA, MAX_NAME_LENGTH, CustomTypeAbort,
                           CustomTypeError, CustomTypeProfile,
                           decode_custom_fields, decode_custom_value,
                           encode_custom_fields, encode_custom_value,
                           parse_custom_type_definition, validate_custom_type)


SCHEMA = 'ct2trainer-custom-type-runtime/v1'
PLAN_SCHEMA = 'ct2trainer-custom-type-write-plan/v1'
MAX_SCOPE_LENGTH = 128
MAX_RECORD_ID = 2 ** 31 - 1

BLOCK_WRITE_GATE = 'custom-write-gate-closed'
BLOCK_RUNTIME_DEFINITION = 'custom-runtime-definition-blocked'
_SPACES = ' \t\r\n'


class CustomTypeRuntimeError(ValueError):
    """Named bounded rejection: stable code plus reason, optional stage/offset."""

    def __init__(self, reason: str, *, code: str, stage: str = 'gate',
                 offset: int | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.code = code
        self.stage = stage
        self.offset = offset

    def to_abort_dict(self) -> dict:
        """Stable named abort payload for host boundaries."""
        return {'schema': ABORT_SCHEMA, 'code': self.code,
                'reason': self.reason, 'offset': self.offset,
                'stage': self.stage}


@dataclass(frozen=True)
class CustomTypeElement:
    """One element of the span: byte offset within the pre-inverse span."""

    offset: int
    size: int
    value: int


@dataclass(frozen=True)
class CustomTypeWritePlan:
    """Deterministic byte-level write plan for one custom type value.

    raw is the exact byte sequence in memory order (profile endianness plus
    inverse transformation applied). value is set for whole-value plans,
    field_values for per-element plans; exactly one of the two is present.
    """

    schema: str
    profile_name: str
    format_text: str
    endianness: str
    inverse: bool
    signed: bool
    size: int
    address: int
    pointer_size: int
    value: int | None
    field_values: tuple
    elements: tuple
    raw: bytes
    plan_id: str

    def to_dict(self) -> dict:
        return {'schema': self.schema, 'profile_name': self.profile_name,
                'format_text': self.format_text, 'endianness': self.endianness,
                'inverse': self.inverse, 'signed': self.signed, 'size': self.size,
                'address': self.address, 'pointer_size': self.pointer_size,
                'value': self.value,
                'field_values': list(self.field_values),
                'elements': [[e.offset, e.size, e.value] for e in self.elements],
                'raw': self.raw.hex(), 'plan_id': self.plan_id}


def _width_limit(pointer_size: int) -> int:
    if pointer_size == 4:
        return 0xFFFFFFFF
    return 0x7FFFFFFFFFFF


def _check_profile(profile) -> None:
    if type(profile) is not CustomTypeProfile:
        raise CustomTypeRuntimeError(
            'Write plans require a parsed CustomTypeProfile',
            code='custom-plan-profile-invalid')
    validate_custom_type(profile)


def _check_address(address, pointer_size: int, size: int) -> None:
    if type(pointer_size) is not int or isinstance(pointer_size, bool) \
            or pointer_size not in (4, 8):
        raise CustomTypeRuntimeError(
            'Pointer size must be 4 or 8 bytes',
            code='custom-plan-width-invalid')
    if type(address) is not int or isinstance(address, bool) or address <= 0:
        raise CustomTypeRuntimeError(
            'Write plan address must be a positive integer',
            code='custom-plan-address-invalid')
    limit = _width_limit(pointer_size)
    if address + size > limit + 1:
        raise CustomTypeRuntimeError(
            f'Write plan span {size} bytes leaves the {pointer_size * 8}-bit '
            f'address space at {hex(address)}',
            code='custom-plan-address-invalid')


def _plan_id(profile: CustomTypeProfile, address: int, pointer_size: int,
             value: int | None, field_values: tuple, raw: bytes) -> str:
    basis = '|'.join([
        PLAN_SCHEMA, profile.name, profile.format_text, profile.endianness,
        str(int(profile.inverse)), str(int(profile.signed)),
        f'{pointer_size:x}', f'{address:x}',
        '-' if value is None else str(value),
        ','.join(str(item) for item in field_values),
        raw.hex(),
    ])
    return hashlib.sha256(basis.encode('ascii')).hexdigest()


def _element_layout(profile: CustomTypeProfile, elements: tuple) -> tuple:
    """Pair every decoded element with its (offset, size) in span order."""
    layout = []
    for field in profile.fields:
        for index in range(field.count):
            layout.append((field.offset + index * field.size, field.size))
    if len(layout) != len(elements):
        raise CustomTypeRuntimeError(
            f'Element layout ({len(layout)}) does not match the decoded span '
            f'({len(elements)})',
            code='custom-plan-layout-mismatch', stage='readback')
    return tuple(zip(layout, elements))


def _element_layout(profile: CustomTypeProfile, elements: tuple) -> tuple:
    """Pair every decoded element with its (offset, size) in span order."""
    layout = []
    for field in profile.fields:
        for index in range(field.count):
            layout.append((field.offset + index * field.size, field.size))
    if len(layout) != len(elements):
        raise CustomTypeRuntimeError(
            f'Element layout ({len(layout)}) does not match the decoded span '
            f'({len(elements)})',
            code='custom-plan-layout-mismatch', stage='readback')
    return tuple(zip(layout, elements))


def build_write_plan(profile, address, *, pointer_size: int = 8,
                     value: int | None = None,
                     field_values=None) -> CustomTypeWritePlan:
    """Build the exact byte-level write plan for one custom type value.

    Exactly one of value (whole span as one integer) or field_values (one
    integer per element) may be given. The plan is verified against the
    codec before it is returned: inverse readback must reproduce the value
    and the original bytes exactly; failures raise the named CustomTypeError
    of the codec, so gate rejections carry the same contract as the codec.
    """
    _check_profile(profile)
    _check_address(address, pointer_size, profile.size)
    if value is not None and field_values is not None:
        raise CustomTypeRuntimeError(
            'A write plan needs exactly one of value or field_values',
            code='custom-plan-input-ambiguous')
    if value is None and field_values is None:
        raise CustomTypeRuntimeError(
            'A write plan needs exactly one of value or field_values',
            code='custom-plan-input-missing')
    if value is not None:
        if type(value) is not int or isinstance(value, bool):
            raise CustomTypeRuntimeError(
                'Whole value must be an integer',
                code='custom-plan-value-invalid')
        raw = encode_custom_value(profile, value)
    else:
        if not isinstance(field_values, (tuple, list)):
            raise CustomTypeRuntimeError(
                'Field values must be a tuple or list of integers',
                code='custom-plan-field-input-invalid')
        values = tuple(field_values)
        for item in values:
            if type(item) is not int or isinstance(item, bool):
                raise CustomTypeRuntimeError(
                    'Field values must be integers',
                    code='custom-plan-field-input-invalid')
        raw = encode_custom_fields(profile, values)
    # Inverse readback: decoding with the profile must return the original
    # value(s), re-encoding must reproduce the exact bytes, and reversing an
    # inverse span must yield the exact non-inverse encoding.
    elements = decode_custom_fields(profile, raw)
    if value is not None and decode_custom_value(profile, raw) != value:
        raise CustomTypeRuntimeError(
            'Inverse readback did not reproduce the planned value',
            code='custom-plan-readback-mismatch', stage='readback')
    if value is not None and encode_custom_value(profile, value) != raw:
        raise CustomTypeRuntimeError(
            'Re-encoding the readback value changed the plan bytes',
            code='custom-plan-determinism-mismatch', stage='readback')
    if value is None and (decode_custom_fields(profile, raw) != values
                          or encode_custom_fields(profile, values) != raw):
        raise CustomTypeRuntimeError(
            'Inverse readback did not reproduce the planned field values',
            code='custom-plan-readback-mismatch', stage='readback')
    if profile.inverse:
        twin = parse_custom_type_definition(
            profile.name, profile.format_text,
            endianness=profile.endianness, inverse=False, signed=profile.signed)
        if value is not None:
            non_inverse = encode_custom_value(twin, value)
        else:
            non_inverse = encode_custom_fields(twin, values)
        if non_inverse[::-1] != raw:
            raise CustomTypeRuntimeError(
                'Inverse bytes do not reproduce the original span exactly',
                code='custom-plan-inverse-mismatch', stage='readback')
    plan_elements = tuple(CustomTypeElement(offset, size, value_item)
                          for (offset, size), value_item
                          in _element_layout(profile, elements))
    return CustomTypeWritePlan(
        schema=PLAN_SCHEMA, profile_name=profile.name,
        format_text=profile.format_text, endianness=profile.endianness,
        inverse=profile.inverse, signed=profile.signed, size=profile.size,
        address=address, pointer_size=pointer_size,
        value=value if value is not None else None,
        field_values=() if value is not None else values,
        elements=plan_elements, raw=raw,
        plan_id=_plan_id(profile, address, pointer_size, value,
                        () if value is not None else values, raw))


def verify_write_plan(plan) -> CustomTypeWritePlan:
    """Re-verify a plan from its own fields; rejects forged or tampered plans.

    Reconstructs the profile from the embedded definition, re-runs the whole
    readback battery and recomputes the plan id. Any divergence is a named
    CustomTypeRuntimeError, never a silent acceptance.
    """
    if type(plan) is not CustomTypeWritePlan:
        raise CustomTypeRuntimeError(
            'A write plan must be a CustomTypeWritePlan', code='custom-plan-invalid')
    if plan.schema != PLAN_SCHEMA:
        raise CustomTypeRuntimeError(
            'Write plan schema differs', code='custom-plan-invalid')
    try:
        profile = parse_custom_type_definition(
            plan.profile_name, plan.format_text, endianness=plan.endianness,
            inverse=plan.inverse, signed=plan.signed)
    except CustomTypeError as exc:
        raise CustomTypeRuntimeError(
            f'Embedded plan definition does not parse: {exc.reason}',
            code='custom-plan-invalid', stage='parse') from exc
    if plan.size != profile.size or plan.endianness != profile.endianness \
            or plan.inverse != profile.inverse or plan.signed != profile.signed:
        raise CustomTypeRuntimeError(
            'Write plan metadata does not match its embedded definition',
            code='custom-plan-invalid')
    _check_address(plan.address, plan.pointer_size, plan.size)
    if not isinstance(plan.raw, (bytes, bytearray)) or len(plan.raw) != plan.size:
        raise CustomTypeRuntimeError(
            'Write plan bytes do not cover the profile span',
            code='custom-plan-invalid', offset=len(plan.raw) if plan.raw else 0)
    raw = bytes(plan.raw)
    try:
        if plan.value is not None:
            if plan.field_values:
                raise CustomTypeRuntimeError(
                    'Write plan must carry exactly one of value or field_values',
                    code='custom-plan-invalid')
            if decode_custom_value(profile, raw) != plan.value \
                    or encode_custom_value(profile, plan.value) != raw:
                raise CustomTypeRuntimeError(
                    'Write plan bytes do not re-encode to their value',
                    code='custom-plan-readback-mismatch', stage='readback')
        else:
            values = tuple(plan.field_values)
            if not values or len(values) != profile.element_count:
                raise CustomTypeRuntimeError(
                    'Write plan field values do not match the layout',
                    code='custom-plan-invalid')
            if decode_custom_fields(profile, raw) != values \
                    or encode_custom_fields(profile, values) != raw:
                raise CustomTypeRuntimeError(
                    'Write plan bytes do not re-encode to their field values',
                    code='custom-plan-readback-mismatch', stage='readback')
    except CustomTypeError as exc:
        raise CustomTypeRuntimeError(
            f'Write plan value no longer encodes: {exc.reason}',
            code='custom-plan-invalid', stage='readback') from exc
    plan_elements = tuple(CustomTypeElement(offset, size, value_item)
                          for (offset, size), value_item
                          in _element_layout(profile, tuple(
                              decode_custom_fields(profile, raw))))
    if tuple((e.offset, e.size, e.value) for e in plan.elements) \
            != tuple((e.offset, e.size, e.value) for e in plan_elements):
        raise CustomTypeRuntimeError(
            'Write plan element binding does not match its bytes',
            code='custom-plan-invalid')
    expected_id = _plan_id(profile, plan.address, plan.pointer_size,
                           plan.value, () if plan.value is not None else
                           tuple(plan.field_values), raw)
    if plan.plan_id != expected_id:
        raise CustomTypeRuntimeError(
            'Write plan id does not match its contents', code='custom-plan-invalid')
    return plan


def plan_to_dict(plan) -> dict:
    verify_write_plan(plan)
    return plan.to_dict()


def plan_from_dict(payload) -> CustomTypeWritePlan:
    """Rebuild and re-verify a plan from its stable JSON dictionary form."""
    required = {'schema', 'profile_name', 'format_text', 'endianness',
                'inverse', 'signed', 'size', 'address', 'pointer_size',
                'value', 'field_values', 'elements', 'raw', 'plan_id'}
    if type(payload) is not dict or set(payload) != required:
        raise CustomTypeRuntimeError(
            'Plan payload must carry exactly the plan fields', code='custom-plan-invalid')
    for key in ('schema', 'profile_name', 'format_text', 'endianness', 'plan_id'):
        if type(payload[key]) is not str:
            raise CustomTypeRuntimeError(
                f'Plan field {key} must be text', code='custom-plan-invalid')
    for key in ('inverse', 'signed'):
        if type(payload[key]) is not bool:
            raise CustomTypeRuntimeError(
                f'Plan field {key} must be a boolean', code='custom-plan-invalid')
    for key in ('size', 'address', 'pointer_size'):
        if type(payload[key]) is not int or isinstance(payload[key], bool) \
                or payload[key] <= 0:
            raise CustomTypeRuntimeError(
                f'Plan field {key} must be a positive integer', code='custom-plan-invalid')
    if payload['pointer_size'] not in (4, 8):
        raise CustomTypeRuntimeError(
            'Plan pointer size must be 4 or 8', code='custom-plan-invalid')
    for element in payload['elements']:
        if (type(element) is not list or len(element) != 3
                or any(type(item) is not int or isinstance(item, bool)
                       for item in element)):
            raise CustomTypeRuntimeError(
                'Plan elements must be [offset, size, value] integer triples',
                code='custom-plan-invalid')
    if payload['value'] is not None and (
            type(payload['value']) is not int or isinstance(payload['value'], bool)):
        raise CustomTypeRuntimeError(
            'Plan value must be an integer or null', code='custom-plan-invalid')
    if type(payload['field_values']) is not list or type(payload['elements']) is not list:
        raise CustomTypeRuntimeError(
            'Plan field_values/elements must be lists', code='custom-plan-invalid')
    try:
        raw = bytes.fromhex(payload['raw'])
    except ValueError as exc:
        raise CustomTypeRuntimeError(
            'Plan raw bytes are not hex text', code='custom-plan-invalid') from exc
    plan = CustomTypeWritePlan(
        schema=payload['schema'], profile_name=payload['profile_name'],
        format_text=payload['format_text'], endianness=payload['endianness'],
        inverse=payload['inverse'], signed=payload['signed'],
        size=payload['size'], address=payload['address'],
        pointer_size=payload['pointer_size'], value=payload['value'],
        field_values=tuple(payload['field_values']),
        elements=tuple(CustomTypeElement(offset, size, value) for offset, size, value
                       in payload['elements']), raw=raw, plan_id=payload['plan_id'])
    return verify_write_plan(plan)


class CustomTypeHostAbort(RuntimeError):
    """Bounded host-boundary error mirroring the lua_host CustomTypeError path.

    str() is the stable 'code: reason' message; abort_payload carries the
    named JSON abort. No Python traceback is part of the message.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.abort_payload: dict | None = None


def lua_abort_payload(exc) -> dict:
    """Named JSON abort payload for one codec error, exactly as wired in lua_host.

    The contract (tests/test_native_custom_type_wiring.py) is: payload equals
    exc.to_abort().to_dict(), schema ct2trainer-custom-type-abort/v1, and the
    host-visible message is 'code: reason' without a traceback.
    """
    if not isinstance(exc, CustomTypeError):
        raise CustomTypeRuntimeError(
            'Only CustomTypeError carries the custom-type abort contract; '
            f'got {type(exc).__name__}',
            code='custom-abort-wrong-error')
    return exc.to_abort().to_dict()


def lua_host_error(exc) -> CustomTypeHostAbort:
    """Build the bounded host error for a codec abort (wiring contract)."""
    if not isinstance(exc, CustomTypeError):
        raise CustomTypeRuntimeError(
            'Only CustomTypeError becomes a named host abort',
            code='custom-abort-wrong-error')
    error = CustomTypeHostAbort(f'{exc.code}: {exc.reason}')
    error.abort_payload = exc.to_abort().to_dict()
    return error


def host_call(func, *args, **kwargs):
    """Pure host-call wrapper used by the abort-path contract.

    Returns ('ok', result) on success and ('abort', payload) for a
    CustomTypeError. Other exceptions propagate unchanged: only codec
    rejections produce the named abort, mirroring the Lua boundary where
    every other failure stays a plain host error.
    """
    try:
        return ('ok', func(*args, **kwargs))
    except CustomTypeError as exc:
        return ('abort', exc.to_abort().to_dict())


@dataclass(frozen=True)
class CustomTypeRecordRegistration:
    """One registered custom record with its visible block reason."""

    schema: str
    record_id: int
    name: str
    scope: str
    profile_name: str | None
    profile_size: int | None
    block_reason: str
    block_reason_text: str
    ordinal: int

    def to_dict(self) -> dict:
        return {'schema': self.schema, 'record_id': self.record_id,
                'name': self.name, 'scope': self.scope,
                'profile_name': self.profile_name,
                'profile_size': self.profile_size,
                'block_reason': self.block_reason,
                'block_reason_text': self.block_reason_text,
                'ordinal': self.ordinal}


class CustomTypeRegistry:
    """Named, visible registration of custom records; the write gate stays closed.

    Registration is scope-bound: the scope names the owning context (for
    example the table-Lua install scope or the controller session). Duplicate
    record ids are refused even across scopes, because a record must never
    be claimed twice by two live owners. teardown() removes one scope (or
    everything without one) and is idempotent. The registry only models
    visibility and ownership; it performs no memory access.
    """

    def __init__(self) -> None:
        self._registrations: dict[int, CustomTypeRecordRegistration] = {}

    @staticmethod
    def _validate_record_id(record_id) -> None:
        if type(record_id) is not int or isinstance(record_id, bool) \
                or not 0 < record_id <= MAX_RECORD_ID:
            raise CustomTypeRuntimeError(
                'Record id must be a positive integer', code='custom-record-id-invalid')

    @staticmethod
    def _validate_text(value, field: str, max_length: int, code: str) -> str:
        if type(value) is not str or not value or len(value) > max_length:
            raise CustomTypeRuntimeError(
                f'{field} must be 1..{max_length} characters', code=code)
        if value != value.strip(_SPACES) or any(not 32 <= ord(c) <= 126 for c in value):
            raise CustomTypeRuntimeError(
                f'{field} must be printable ASCII without surrounding whitespace',
                code=code)
        return value

    def register(self, record_id, name, scope, *, profile=None) -> CustomTypeRecordRegistration:
        """Register one custom record under an owning scope.

        With a static profile the named block reason is the still-open write
        gate; without one (RE2-style runtime Lua definition) the record is
        blocked until a converter/write gate exists. Both stay visible.
        """
        self._validate_record_id(record_id)
        self._validate_text(name, 'Record name', MAX_NAME_LENGTH, 'custom-record-name-invalid')
        self._validate_text(scope, 'Scope', MAX_SCOPE_LENGTH, 'custom-scope-invalid')
        if profile is not None:
            if type(profile) is not CustomTypeProfile:
                raise CustomTypeRuntimeError(
                    'Registration profile must be a parsed CustomTypeProfile',
                    code='custom-registration-profile-invalid')
            validate_custom_type(profile)
            block_reason = BLOCK_WRITE_GATE
            block_reason_text = (
                f"Custom record '{name}' (id {record_id}) uses statically defined "
                f"custom type '{profile.name}'; the native converter write gate is "
                'not implemented yet (AP-08.7). Registration is visibility-only; '
                'no process write is issued.')
        else:
            block_reason = BLOCK_RUNTIME_DEFINITION
            block_reason_text = (
                f"Custom record '{name}' (id {record_id}) has no static definition "
                '(runtime Lua definition, RE2-style); blocked until a converter/'
                'write gate exists (AP-08.7). No process write is issued.')
        existing = self._registrations.get(record_id)
        if existing is not None:
            raise CustomTypeRuntimeError(
                f"Custom record id {record_id} is already registered under scope "
                f"'{existing.scope}'",
                code='custom-record-duplicate')
        registration = CustomTypeRecordRegistration(
            schema=SCHEMA, record_id=record_id, name=name, scope=scope,
            profile_name=profile.name if profile is not None else None,
            profile_size=profile.size if profile is not None else None,
            block_reason=block_reason, block_reason_text=block_reason_text,
            ordinal=len(self._registrations))
        self._registrations[record_id] = registration
        return registration

    def teardown(self, scope=None) -> int:
        """Remove all registrations of one scope (or all without scope); idempotent."""
        if scope is not None:
            self._validate_text(scope, 'Scope', MAX_SCOPE_LENGTH, 'custom-scope-invalid')
        if scope is None:
            removed = len(self._registrations)
            self._registrations = {}
            return removed
        doomed = [record_id for record_id, registration
                  in self._registrations.items() if registration.scope == scope]
        for record_id in doomed:
            del self._registrations[record_id]
        return len(doomed)

    def registrations(self, scope=None) -> tuple[CustomTypeRecordRegistration, ...]:
        if scope is not None:
            self._validate_text(scope, 'Scope', MAX_SCOPE_LENGTH, 'custom-scope-invalid')
            items = [r for r in self._registrations.values() if r.scope == scope]
        else:
            items = list(self._registrations.values())
        return tuple(sorted(items, key=lambda item: item.ordinal))

    def report(self) -> dict:
        """Stable JSON-visible state: gate closed plus every registration."""
        return {'schema': SCHEMA, 'write_gate': 'closed',
                'registrations': [r.to_dict() for r in self.registrations()]}


__all__ = [
    'SCHEMA', 'PLAN_SCHEMA', 'MAX_SCOPE_LENGTH', 'MAX_RECORD_ID',
    'BLOCK_WRITE_GATE', 'BLOCK_RUNTIME_DEFINITION',
    'CustomTypeRuntimeError', 'CustomTypeHostAbort', 'CustomTypeElement',
    'CustomTypeWritePlan', 'CustomTypeRecordRegistration', 'CustomTypeRegistry',
    'build_write_plan', 'verify_write_plan', 'plan_to_dict', 'plan_from_dict',
    'lua_abort_payload', 'lua_host_error', 'host_call',
]
