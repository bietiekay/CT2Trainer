"""Independent bounded AA byte-pattern grammar from published API behavior.

Bytes may be adjacent or separated by whitespace. A standalone x/?/* is
one entire wildcard byte; pairs use hexadecimal or wildcard nibbles. Parsing
never joins an odd token across whitespace, so ``F F`` cannot become ``FF``.
"""
from __future__ import annotations

import re

MAX_PATTERN_BYTES = 4096
MAX_PATTERN_TEXT = MAX_PATTERN_BYTES * 3
_NIBBLES = re.compile(r'[0-9A-Fa-fxX?*]+\Z')


def normalize_pattern(pattern: str) -> str:
    if type(pattern) is not str or not pattern or len(pattern) > MAX_PATTERN_TEXT:
        raise ValueError('AOB pattern must be bounded text.')
    result = []
    for token in pattern.split():
        if _NIBBLES.fullmatch(token) is None:
            raise ValueError('AOB pattern contains an invalid hexadecimal/wildcard nibble.')
        token = token.upper().replace('X', '?').replace('*', '?')
        if token == '?':
            result.append('??')
        else:
            if len(token) % 2:
                raise ValueError('AOB compact tokens require complete pairs of nibbles.')
            result.extend(token[index:index + 2] for index in range(0, len(token), 2))
        if len(result) > MAX_PATTERN_BYTES:
            raise ValueError('AOB pattern exceeds its 4096-byte bound.')
    if not result or not any(token != '??' for token in result):
        raise ValueError('An entirely wildcard pattern cannot identify an address.')
    return ' '.join(result)


def pattern_matches(pattern: str, raw: bytes) -> bool:
    tokens = normalize_pattern(pattern).split()
    return (type(raw) is bytes and len(raw) == len(tokens)
            and all(all(nibble == '?' or nibble == f'{byte:02X}'[index]
                        for index, nibble in enumerate(token))
                    for token, byte in zip(tokens, raw)))
