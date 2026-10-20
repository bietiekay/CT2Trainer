"""Independent, bounded module nth-match scans with source helper provenance.

Only fingerprints of the reviewed third-party table input are retained here;
its Lua implementation is not redistributed. The reserved owned helper is a
source adapter, not an arbitrary Lua function-name inference.
"""
from __future__ import annotations

import hashlib
import re

from .aa import AAError, normalize_pattern, validate_symbol
from .patterns import pattern_has_placeholder_token


HELPER_SCHEMA = 'ct2trainer-nth-aob-helper/v1'
RESULT_SCHEMA = 'ct2trainer-nth-aob-result/v1'
REVIEWED_HELPER_SHA256 = 'f13c05d08b883a47694a6c52b4fe4b0edc643e110d776eccc81eeefbdf9c194e'
REVIEWED_BOOTSTRAP_SHA256 = 'e5dad28260f591cb9b48d868340815ea826af0d504693c2f234463c9a7818931'
MAX_RESULTS = 65536
MAX_DEFINITIONS = 64
_USER_LIMIT = 0x7FFFFFFFFFFF
_HELPER_BODY = re.compile(r'(?m)^function lua_aobscan\(name,module,bytes,index\)\n(?:(?!^end[ \t]*$).*\n)*end[ \t]*$')
_HELPER_START = re.compile(r'\s*(ct2trainerNthAOB|lua_aobscan)(?=\s|\(|\Z)')
_STRING = r'("[^"\\\r\n]*"|\'[^\'\\\r\n]*\')'
_CALL = re.compile(r'\s*(ct2trainerNthAOB|lua_aobscan)\s*\(\s*' + _STRING +
                   r'\s*,\s*' + _STRING + r'\s*,\s*' + _STRING +
                   r'\s*,\s*([0-9]{1,5})\s*\)\s*;?\s*\Z')


class NthAOBError(ValueError):
    pass


def _module_name(value):
    if (type(value) is not str or not value or len(value) > 255 or value != value.strip()
            or not value.casefold().endswith(('.exe', '.dll'))
            or value.casefold() in {'.exe', '.dll', '..exe', '..dll'}
            or any(char in '<>:"/\\|?*' or ord(char) < 32 for char in value)):
        raise NthAOBError('Nth-AOB requires a nonempty exact .exe/.dll module basename')
    return value


def validate_helper_contract(contract):
    if (type(contract) is not dict or set(contract) != {'schema', 'helper', 'helper_sha256', 'bootstrap_sha256'}
            or contract.get('schema') != HELPER_SCHEMA or contract.get('helper') != 'lua_aobscan'
            or contract.get('helper_sha256') != REVIEWED_HELPER_SHA256
            or contract.get('bootstrap_sha256') not in {REVIEWED_HELPER_SHA256, REVIEWED_BOOTSTRAP_SHA256}):
        raise NthAOBError('Unknown or forged nth-AOB table helper provenance')
    return dict(contract)


def prepare_helper_contract(bootstrap):
    """Opt into the exact reviewed helper-only or original table source.

    Other original table actions remain present in the bootstrap and subject to
    its normal read-only installation gate. Nothing is stripped or executed.
    Unknown source returns None, rather than conferring helper semantics.
    """
    from .lua_bootstrap import validate_lua_bootstrap
    profile = validate_lua_bootstrap(bootstrap)
    if profile['source_sha256'] not in {REVIEWED_HELPER_SHA256, REVIEWED_BOOTSTRAP_SHA256}:
        return None
    source = profile['source'].replace('\r\n', '\n').replace('\r', '\n')
    matches = list(_HELPER_BODY.finditer(source))
    if (len(matches) != 1 or hashlib.sha256(matches[0].group().encode('utf-8')).hexdigest()
            != REVIEWED_HELPER_SHA256):
        return None
    return {'schema': HELPER_SCHEMA, 'helper': 'lua_aobscan',
            'helper_sha256': REVIEWED_HELPER_SHA256, 'bootstrap_sha256': profile['source_sha256']}


def definition_from_call(source, part_index, helper_contract=None):
    """Recognize one complete literal call, without parsing arbitrary Lua."""
    start = _HELPER_START.match(source)
    if start is None:
        return None
    if start.group(1) == 'lua_aobscan' and helper_contract is None:
        return None  # Ordinary unknown Lua remains subject to runtime admission.
    if helper_contract is not None:
        validate_helper_contract(helper_contract)
    match = _CALL.fullmatch(source)
    if match is None:
        raise NthAOBError('Nth-AOB source adapter requires exactly three unescaped string literals and one decimal occurrence')
    helper, symbol, module, pattern, occurrence = match.groups()
    try:
        symbol = validate_symbol(symbol[1:-1])
        module = _module_name(module[1:-1])
        raw = pattern[1:-1].replace('*', '?')
        # WP-57: nth-AOB keeps its fixed-byte contract; placeholder tokens
        # keep the pre-placeholder nibble refusal, byte-identical.
        if pattern_has_placeholder_token(raw):
            raise AAError('AOB pattern contains an invalid hexadecimal/wildcard nibble.')
        pattern = normalize_pattern(raw)
    except AAError as exc:
        raise NthAOBError(str(exc)) from exc
    occurrence = int(occurrence)
    if not 1 <= occurrence <= MAX_RESULTS or type(part_index) is not int or not 0 <= part_index < 65536:
        raise NthAOBError('Nth-AOB occurrence/index is outside its bounded range')
    return {'op': 'nth_aobscan', 'symbol': symbol, 'module': module, 'pattern': pattern,
            'occurrence': occurrence, 'part_index': part_index, 'helper': helper}


def validate_definition(definition):
    if (type(definition) is not dict or set(definition) != {'op', 'symbol', 'module', 'pattern', 'occurrence', 'part_index', 'helper'}
            or definition.get('op') != 'nth_aobscan'
            or definition.get('helper') not in {'ct2trainerNthAOB', 'lua_aobscan'}
            or type(definition.get('occurrence')) is not int or not 1 <= definition['occurrence'] <= MAX_RESULTS
            or type(definition.get('part_index')) is not int or not 0 <= definition['part_index'] < 65536):
        raise NthAOBError('Malformed nth-AOB source definition')
    try:
        validate_symbol(definition['symbol'])
        _module_name(definition['module'])
        # WP-57: fixed-byte contract — placeholder tokens keep the
        # pre-placeholder nibble refusal, byte-identical.
        if pattern_has_placeholder_token(definition['pattern']):
            raise AAError('AOB pattern contains an invalid hexadecimal/wildcard nibble.')
        if normalize_pattern(definition['pattern']) != definition['pattern']:
            raise NthAOBError('Nth-AOB pattern is not canonical')
    except AAError as exc:
        raise NthAOBError(str(exc)) from exc
    return definition


def _identity(memory, expected=None):
    identity = memory.identity
    if (not isinstance(identity, tuple) or len(identity) != 2
            or any(type(item) is not int or item <= 0 for item in identity)
            or identity[0] > 0xFFFFFFFF or identity[1] > 0xFFFFFFFFFFFFFFFF
            or expected is not None and identity != tuple(expected)
            or memory.is_alive() is not True):
        raise NthAOBError('Nth-AOB target identity/liveness changed or is uncertain')
    return identity


def _bounds(memory, module):
    bounds = memory.module(module)
    limit = 0xFFFFFFFF if memory.pointer_size == 4 else _USER_LIMIT
    if (type(memory.pointer_size) is not int or memory.pointer_size not in {4, 8}
            or not isinstance(bounds, tuple) or len(bounds) != 2
            or any(type(item) is not int or item <= 0 for item in bounds)
            or bounds[0] > limit or bounds[1] - 1 > limit - bounds[0]):
        raise NthAOBError('Nth-AOB module bounds exceed the target address width')
    return bounds


def _matches(pattern, raw):
    tokens = pattern.split()
    return (type(raw) is bytes and len(raw) == len(tokens)
            and all(all(nibble == '?' or nibble == format(byte, '02X')[index]
                        for index, nibble in enumerate(token)) for token, byte in zip(tokens, raw)))


def scan_nth(definition, memory, *, expected_identity=None):
    """Read a complete bounded module scan, then recheck its selected bytes."""
    validate_definition(definition)
    identity = _identity(memory, expected_identity)
    base, size = _bounds(memory, definition['module'])
    length = len(definition['pattern'].split())
    matches = memory.scan_matches(definition['pattern'], start=base, end=base + size, max_results=MAX_RESULTS)
    if (type(matches) is not list or len(matches) > MAX_RESULTS
            or any(type(address) is not int or not base <= address <= base + size - length for address in matches)
            or len(set(matches)) != len(matches)):
        raise NthAOBError('Nth-AOB backend returned malformed or out-of-module matches')
    matches = sorted(matches)
    if len(matches) < definition['occurrence']:
        raise NthAOBError('Nth-AOB requested occurrence was not found in the complete module scan')
    address = matches[definition['occurrence'] - 1]
    raw = memory.read(address, length)
    if not _matches(definition['pattern'], raw):
        raise NthAOBError('Nth-AOB selected bytes changed before publication')
    if _bounds(memory, definition['module']) != (base, size):
        raise NthAOBError('Nth-AOB module identity/bounds changed during scan')
    _identity(memory, identity)
    return {'schema': RESULT_SCHEMA, 'definition': dict(definition), 'target': list(identity),
            'module': [base, size], 'address': address, 'bytes': raw.hex(), 'match_count': len(matches)}


def validate_result(result):
    """Bound diagnostic journal data without trusting it as live authority."""
    if (type(result) is not dict or set(result) != {'schema', 'definition', 'target', 'module', 'address', 'bytes', 'match_count'}
            or result.get('schema') != RESULT_SCHEMA):
        raise NthAOBError('Malformed nth-AOB result receipt')
    definition = validate_definition(result['definition'])
    target, module = result['target'], result['module']
    if (type(target) is not list or len(target) != 2
            or any(type(item) is not int or item <= 0 for item in target)
            or target[0] > 0xFFFFFFFF or target[1] > 0xFFFFFFFFFFFFFFFF
            or type(module) is not list or len(module) != 2
            or any(type(item) is not int or item <= 0 for item in module)
            or module[0] > _USER_LIMIT or module[1] - 1 > _USER_LIMIT - module[0]
            or type(result['address']) is not int
            or not module[0] <= result['address'] <= module[0] + module[1] - len(definition['pattern'].split())
            or type(result['match_count']) is not int
            or not definition['occurrence'] <= result['match_count'] <= MAX_RESULTS
            or type(result['bytes']) is not str
            or len(result['bytes']) != len(definition['pattern'].split()) * 2
            or not re.fullmatch(r'(?:[0-9a-f]{2})+', result['bytes'])):
        raise NthAOBError('Invalid nth-AOB receipt bounds or bytes')
    if not _matches(definition['pattern'], bytes.fromhex(result['bytes'])):
        raise NthAOBError('Nth-AOB receipt bytes do not match its source pattern')
    return result


def recheck_result(result, memory, *, before_publication=True):
    """Captured addresses survive disable; a later scan must never replace them."""
    validate_result(result)
    _identity(memory, result['target'])
    if _bounds(memory, result['definition']['module']) != tuple(result['module']):
        raise NthAOBError('Nth-AOB captured module bounds changed')
    if before_publication:
        raw = memory.read(result['address'], len(result['bytes']) // 2)
        if not _matches(result['definition']['pattern'], raw):
            raise NthAOBError('Nth-AOB selected bytes changed before publication')
    _identity(memory, result['target'])
