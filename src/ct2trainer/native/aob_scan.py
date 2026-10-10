"""Source-bound process AA scan receipts, independently implemented.

Receipts are constructed by trusted Python while scanning a held backend. JSON
is diagnostic evidence, not a write permit. Programs cannot serialize receipts.
No address is rediscovered during allocation, linking, disable or publication.
"""
from __future__ import annotations

import re

from .patterns import normalize_pattern, pattern_matches
from .lua_work_budget import broker_checkpoint

SCHEMA = 'ct2trainer-aa-process-scan/v1'
_KEYS = {'schema', 'source_sha256', 'node', 'target', 'pointer_size', 'address', 'bytes'}


class AOBScanError(ValueError):
    pass


def _identity(memory, expected=None):
    identity = memory.identity
    if (type(identity) is not tuple or len(identity) != 2
            or any(type(value) is not int or value <= 0 for value in identity)
            or identity[0] > 0xFFFFFFFF or identity[1] > 0xFFFFFFFFFFFFFFFF
            or expected is not None and tuple(expected) != identity
            or memory.is_alive() is not True):
        raise AOBScanError('Process AOB target identity/liveness changed or is uncertain.')
    return identity


def _node(node):
    from .aa import validate_symbol
    if (type(node) is not dict or set(node) != {'op', 'symbol', 'pattern'}
            or node['op'] != 'scan_process'):
        raise AOBScanError('Invalid source-bound process scan node.')
    validate_symbol(node['symbol'])
    if normalize_pattern(node['pattern']) != node['pattern']:
        raise AOBScanError('Process scan requires a canonical source pattern.')
    return node


def validate_result(result, source_sha256=None, node=None):
    if (type(result) is not dict or set(result) != _KEYS or result.get('schema') != SCHEMA
            or type(result.get('source_sha256')) is not str
            or re.fullmatch(r'[0-9a-f]{64}', result['source_sha256']) is None):
        raise AOBScanError('Malformed source-bound process scan receipt.')
    _node(result['node'])
    if (source_sha256 is not None and result['source_sha256'] != source_sha256
            or node is not None and result['node'] != node):
        raise AOBScanError('Process scan receipt differs from its source hash/node/pattern.')
    target, width, address = result['target'], result['pointer_size'], result['address']
    limit = 0xFFFFFFFF if width == 4 else 0x7FFFFFFFFFFF
    size = len(result['node']['pattern'].split())
    if (type(target) is not list or len(target) != 2
            or any(type(value) is not int or value <= 0 for value in target)
            or target[0] > 0xFFFFFFFF or target[1] > 0xFFFFFFFFFFFFFFFF
            or type(width) is not int or width not in {4, 8}
            or type(address) is not int or not 0 < address <= limit
            or size - 1 > limit - address
            or type(result['bytes']) is not str
            or len(result['bytes']) != size * 2
            or re.fullmatch(r'(?:[0-9a-f]{2})+', result['bytes']) is None
            or not pattern_matches(result['node']['pattern'], bytes.fromhex(result['bytes']))):
        raise AOBScanError('Invalid captured process AOB target/address/bytes.')
    return result


def capture_scan(node, source_sha256, memory):
    _node(node)
    if type(source_sha256) is not str or re.fullmatch(r"[0-9a-f]{64}", source_sha256) is None:
        raise AOBScanError("The process scan source hash is invalid.")
    identity = _identity(memory)
    width = memory.pointer_size
    if type(width) is not int or width not in {4, 8}:
        raise AOBScanError('The held process AOB target width is unavailable.')
    method = getattr(memory, 'scan_process', None)
    if not callable(method):
        raise AOBScanError('The memory backend has no complete bounded process scanner.')
    broker_checkpoint()
    address = method(node['pattern'])
    broker_checkpoint()
    size = len(node['pattern'].split())
    limit = 0xFFFFFFFF if width == 4 else 0x7FFFFFFFFFFF
    if type(address) is not int or not 0 < address <= limit or size - 1 > limit - address:
        raise AOBScanError('The process scan address exceeds its target width.')
    raw = memory.read(address, size)
    if not pattern_matches(node['pattern'], raw):
        raise AOBScanError('Selected process AOB bytes changed before capture.')
    _identity(memory, identity)
    if memory.pointer_size != width:
        raise AOBScanError('The process AOB target architecture changed.')
    result = {'schema': SCHEMA, 'source_sha256': source_sha256, 'node': dict(node),
              'target': list(identity), 'pointer_size': width, 'address': address, 'bytes': raw.hex()}
    broker_checkpoint()
    return validate_result(result, source_sha256, node)


def recheck_result(result, memory, source_sha256=None, node=None):
    """Run under the existing held publication event, before any live write."""
    broker_checkpoint()
    validate_result(result, source_sha256, node)
    _identity(memory, result['target'])
    if memory.pointer_size != result['pointer_size']:
        raise AOBScanError('Captured process AOB architecture changed.')
    raw = memory.read(result['address'], len(result['bytes']) // 2)
    # Preserve every captured wildcard byte too: changed live context is refused.
    if raw != bytes.fromhex(result['bytes']):
        raise AOBScanError('Captured process AOB bytes changed before publication.')
    _identity(memory, result['target'])
    broker_checkpoint()
