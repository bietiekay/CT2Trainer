"""Independent bounded AA byte-pattern grammar from published API behavior.

Bytes may be adjacent or separated by whitespace. A standalone x/?/* is
one entire wildcard byte; pairs use hexadecimal or wildcard nibbles. Parsing
never joins an odd token across whitespace, so ``F F`` cannot become ``FF``.

Placeholder tokens (WP-57 / GC-E20): a scan pattern may define bounded
capture tokens ``s<N>.<M>`` with index 1-9999 (no leading zeros) and
M in {1, 2}; each token occupies M bytes of the pattern and matches any
bytes there. The canonical form keeps them as single uppercase
``S<N>.<M>`` tokens, so every consumer detects them without re-parsing.
``pattern_matches`` and the scan compilers treat a placeholder span as M
wildcard bytes; the bytes captured at scan time are substituted for bare
``s<N>`` patch-side references by the program-dialect linker only. At most
16 placeholder tokens may be defined per pattern, each exactly once.
"""
from __future__ import annotations

import re
from collections.abc import Mapping

MAX_PATTERN_BYTES = 4096
MAX_PATTERN_TEXT = MAX_PATTERN_BYTES * 3
MAX_PLACEHOLDER_TOKENS = 16
_NIBBLES = re.compile(r'[0-9A-Fa-fxX?*]+\Z')
# Definition form s<N>.<M> with M in {1, 2}, full token, case-insensitive.
_PLACEHOLDER_DEFINITION = re.compile(r'(?i)s([1-9][0-9]{0,3})\.(1|2)\Z')
# Broader shape s<N>.<M> (any digit count) used to name the byte-count
# refusal before falling back to the nibble grammar.
_PLACEHOLDER_SHAPE = re.compile(r'(?i)s([1-9][0-9]{0,3})\.(\d{1,3})\Z')
# Bare patch-side reference s<N>, full token, case-insensitive.
_PLACEHOLDER_REF = re.compile(r'(?i)s([1-9][0-9]{0,3})\Z')
# Canonical uppercase placeholder token S<N>.<M>.
_PLACEHOLDER_SPAN = re.compile(r'S([1-9][0-9]{0,3})\.(1|2)\Z')
# Any placeholder-shaped token (definition, bare reference, or unknown M) —
# used by the fixed-byte consumers (nth-AOB, luaCall AOB) to keep their
# pre-placeholder refusal text byte-identical.
_PLACEHOLDER_ANY = re.compile(r'(?i)s([1-9][0-9]{0,3})(?:\.(\d{1,3}))?\Z')


def _placeholder_name(index: str) -> str:
    return f"s{int(index)}"


def is_placeholder_token(token) -> bool:
    """True for a full token in definition (``s<N>.<M>``) or reference (``s<N>``) form."""
    return (type(token) is str
            and (_PLACEHOLDER_DEFINITION.fullmatch(token) is not None
                 or _PLACEHOLDER_REF.fullmatch(token) is not None))


def is_placeholder_ref_token(token) -> bool:
    """True for a bare patch-side reference ``s<N>`` (case-insensitive)."""
    return type(token) is str and _PLACEHOLDER_REF.fullmatch(token) is not None


def pattern_has_placeholder_token(pattern) -> bool:
    """True when any whitespace token is placeholder-shaped (any M)."""
    if type(pattern) is not str:
        return False
    return any(_PLACEHOLDER_ANY.fullmatch(token) for token in pattern.split())


def _validated_tokens(pattern: str) -> list[tuple[str, int]]:
    """Validate one pattern, returning canonical tokens with byte counts.

    Nibble tokens expand to one entry per byte; placeholder definitions stay
    single canonical ``S<N>.<M>`` tokens that count M bytes toward the bound
    and act as wildcards for matching.
    """
    if type(pattern) is not str or not pattern or len(pattern) > MAX_PATTERN_TEXT:
        raise ValueError('AOB pattern must be bounded text.')
    tokens: list[tuple[str, int]] = []
    defined: set[int] = set()
    total = 0
    for token in pattern.split():
        definition = _PLACEHOLDER_DEFINITION.fullmatch(token)
        if definition is not None:
            index = int(definition.group(1))
            if index in defined:
                raise ValueError(
                    f'Placeholder token {_placeholder_name(definition.group(1))} '
                    'is defined more than once in the pattern.')
            defined.add(index)
            if len(defined) > MAX_PLACEHOLDER_TOKENS:
                raise ValueError('More than 16 placeholder tokens in one pattern.')
            count = int(definition.group(2))
            tokens.append((f"S{index}.{definition.group(2)}", count))
            total += count
            if total > MAX_PATTERN_BYTES:
                raise ValueError('AOB pattern exceeds its 4096-byte bound.')
            continue
        if _PLACEHOLDER_SHAPE.fullmatch(token) is not None:
            raise ValueError('Placeholder token byte count must be 1 or 2.')
        if _PLACEHOLDER_REF.fullmatch(token) is not None:
            raise ValueError(
                f"Placeholder token {_placeholder_name(_PLACEHOLDER_REF.fullmatch(token).group(1))} "
                'is not defined in the scan pattern.')
        if _NIBBLES.fullmatch(token) is None:
            raise ValueError('AOB pattern contains an invalid hexadecimal/wildcard nibble.')
        token = token.upper().replace('X', '?').replace('*', '?')
        if token == '?':
            tokens.append(('??', 1))
        else:
            if len(token) % 2:
                raise ValueError('AOB compact tokens require complete pairs of nibbles.')
            tokens.extend((pair, 1) for pair in (token[index:index + 2]
                                                 for index in range(0, len(token), 2)))
        total += 1 if token == '??' else len(token) // 2
        if total > MAX_PATTERN_BYTES:
            raise ValueError('AOB pattern exceeds its 4096-byte bound.')
    if not tokens or not any(count == 1 and token != '??' for token, count in tokens):
        raise ValueError('An entirely wildcard pattern cannot identify an address.')
    return tokens


def normalize_pattern(pattern: str) -> str:
    return ' '.join(token for token, _ in _validated_tokens(pattern))


def expanded_pattern(pattern: str) -> str:
    """Per-byte token form; every placeholder span expands to M wildcard bytes."""
    tokens = []
    for token, count in _validated_tokens(pattern):
        if _PLACEHOLDER_SPAN.fullmatch(token) is not None:
            tokens.extend(['??'] * count)
        else:
            tokens.append(token)
    return ' '.join(tokens)


def pattern_byte_length(pattern: str) -> int:
    """Total byte length of the pattern, counting placeholder spans as M bytes."""
    return sum(count for _, count in _validated_tokens(pattern))


def placeholder_spans(pattern: str) -> dict[str, tuple[int, int]]:
    """Byte spans of placeholder definitions: name -> (byte_offset, byte_count)."""
    spans: dict[str, tuple[int, int]] = {}
    offset = 0
    for token, count in _validated_tokens(pattern):
        match = _PLACEHOLDER_SPAN.fullmatch(token)
        if match is None:
            offset += count
            continue
        spans[_placeholder_name(match.group(1))] = (offset, count)
        offset += count
    return spans


def symbol_is_placeholder_shaped(name) -> bool:
    """True for any identifier in a placeholder token shape (``s<N>`` with an
    optional dotted byte count, any digit count).

    Expression positions (addresses, defines, scan bounds) must fail closed
    before the expression grammar is asked to resolve a placeholder-shaped
    symbol as an ordinary name.
    """
    return type(name) is str and _PLACEHOLDER_ANY.fullmatch(name) is not None


def validate_placeholder_captures(captures) -> dict[str, str]:
    """Validate captured placeholder bytes; return canonical ``{name: UPPER-HEX}``.

    Names are casefolded ``s<N>`` token names (index 1-9999, no leading
    zeros); values are exactly 1 or 2 hex bytes. ``None`` and empty mappings
    validate to an empty dict. Case-ambiguous names (the same token spelled
    with different case) are refused.
    """
    if captures is None:
        return {}
    if not isinstance(captures, Mapping):
        raise ValueError("Placeholder captures must be a bounded mapping of token name to hex bytes.")
    if len(captures) > MAX_PLACEHOLDER_TOKENS:
        raise ValueError("More than 16 placeholder captures supplied.")
    result: dict[str, str] = {}
    for name, value in captures.items():
        if type(name) is not str or _PLACEHOLDER_REF.fullmatch(name.casefold()) is None:
            raise ValueError(f"Invalid placeholder capture name: {name!r}.")
        key = name.casefold()
        if key in result:
            raise ValueError(f"Placeholder captures define {key} more than once with different case.")
        if type(value) is not str or not re.fullmatch(r"[0-9A-Fa-f]{2}|[0-9A-Fa-f]{4}", value):
            raise ValueError(f"Placeholder capture {key} must be 1 or 2 hex bytes.")
        result[key] = value.upper()
    return result


def pattern_matches(pattern: str, raw: bytes) -> bool:
    tokens = expanded_pattern(pattern).split()
    return (type(raw) is bytes and len(raw) == len(tokens)
            and all(all(nibble == '?' or nibble == f'{byte:02X}'[index]
                        for index, nibble in enumerate(token))
                    for token, byte in zip(tokens, raw)))
