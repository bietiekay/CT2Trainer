"""Bounded, independently implemented address arithmetic; never uses eval."""

from __future__ import annotations

import re
from collections.abc import Mapping


class AddressExpressionError(ValueError):
    pass


# Managed method label: Class:Method (IL2CPP injection label), the
# double-colon alias Class::Method (WP-23), and — since WP-30 — the
# module-prefixed forms Module.Class::Method / Module.Class:Method, where
# the module prefix is one or more dotted basename segments (digits and
# hyphens allowed, e.g. Kena-Win64-Shipping.UMochiState::execHasItem).
# RT-4.5 (O18) / RT-4.3 (O27): the colon-separated tail is bounded to one
# or two separators, admitting the three-segment namespace form
# Namespace.Class:BaseClass:Method (e.g.
# FailBetter.Core.QAssoc.BaseClasses:BaseQAssocWithLevel:get_Level or
# Failbetter.Core.QAssoc.BaseClasses:BaseQPossession:set_EffectiveLevelM)
# while keeping the two-segment forms and the double-colon alias
# unchanged; deeper colon chains fail closed.  Offsets attach like any
# other base atom.  The full name is kept verbatim, classified as kind
# "managed" and resolved through the injected symbol map, never as a
# module export and never as symbol requires.
_MANAGED_LABEL = re.compile(r"(?:[A-Za-z0-9_$][A-Za-z0-9_$\-]*\.)*[A-Za-z_$][A-Za-z0-9_]*(?:::?[A-Za-z_$][A-Za-z0-9_]*){1,2}\Z")


def is_managed_label(text: str) -> bool:
    """RT-4.3 (O4): True when the text is exactly one managed method label
    (``Class:Method``, ``Class::Method``, ``Module.Class::Method``, or the
    three-segment ``Namespace.Class:BaseClass:Method`` form).  Managed
    labels resolve through the injected symbol map, never through module
    exports and never through the ordinary symbol table."""
    return type(text) is str and _MANAGED_LABEL.fullmatch(text) is not None
# Module basenames that start with a digit (WP-22): 20XX.exe, 1234.dll, ...
# The .exe/.dll suffix is what disambiguates them from a bare integer, and
# the alternative is ordered BEFORE the bare-integer alternative in _TOKEN
# so the full basename tokenizes as one atom; a bare digit run without the
# suffix still tokenizes and parses as an integer, exactly as before.
# Interior identifier segments are allowed (e.g. 1234.Game.dll) to mirror
# the letter-leading dotted basename handling; a non-module dot run after
# the suffix (20XX.exe.foo) still fails closed because the tokenizer stops
# at the .exe/.dll suffix.
_DIGIT_MODULE = re.compile(r"[0-9][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*\.(?:[Ee][Xx][Ee]|[Dd][Ll][Ll])")
# The module-prefixed managed-label alternative must come BEFORE the dotted
# symbol alternative: at the same start position it wins the leftmost match,
# so "Mod.Class::Method" tokenizes as one managed atom instead of a symbol
# followed by an untokenizable "::*".  The plain two-segment forms and all
# other tokens (module basenames, digit-leading modules, bare integers) are
# unaffected: the prefix requires a terminating colon.  RT-4.5 (O18): the
# tail admits one or two colon (or double-colon) separators, so the
# three-segment namespace form tokenizes as one managed atom instead of a
# two-segment atom plus an untokenizable ":Method" tail.  RT-4.3 (O10):
# digit-leading symbol names (8PathSteal, 20XXstyle) are valid CE
# identifiers (label() val('$'+name) check: the name stops parsing as hex
# at the first non-hex character); the alternative requires a non-hex
# character after the leading digit run, so a fully hex token keeps
# tokenizing as a bare integer and never changes integer parsing.  It
# sits after _DIGIT_MODULE (the .exe/.dll suffix form still wins) and
# before the bare-integer alternative.  The hyphen-module alternative
# anchors on the .exe/.dll suffix; its trailing negative lookahead keeps
# module-qualified exports (Kernel32.dll.GetTickCount64,
# NativeHookFixture.exe.fixture_result) out of reach, so the whole atom
# still tokenizes as one export through the letter-leading alternative
# exactly as before this alternative was introduced.
_DIGIT_LEADING_SYMBOL = r"[0-9][0-9a-fA-F]*[g-zG-Z_.$][A-Za-z0-9_.$]*"
_HYPHEN_MODULE = r"[A-Za-z_$][A-Za-z0-9_$\-]*(?:\.[A-Za-z0-9_$\-]+)*\.(?:[Ee][Xx][Ee]|[Dd][Ll][Ll])(?!\.[A-Za-z_$])"
_TOKEN = re.compile(r'\s*("[^"\r\n]+"|0[xX][0-9a-fA-F]+|\$[0-9a-fA-F]+|#[0-9]+|(?:[A-Za-z0-9_$][A-Za-z0-9_$\-]*\.)*[A-Za-z_$][A-Za-z0-9_]*(?:::?[A-Za-z_$][A-Za-z0-9_]*){1,2}|' + _HYPHEN_MODULE + r'|@?[A-Za-z_$][A-Za-z0-9_.$]*|' + _DIGIT_MODULE.pattern + '|' + _DIGIT_LEADING_SYMBOL + r'|[0-9][0-9a-fA-F]*|[+\-*/()\[\]])')
MAX_ADDRESS = 0xFFFFFFFFFFFFFFFF
# Closed set of bounded type-cast names (WP-30).  Matched case-insensitive
# at the token level; a cast never changes the symbol set or plan metadata.
CAST_TYPES = frozenset(
    ("byte", "word", "dword", "qword", "int", "uint",
     "short", "ushort", "long", "ulong", "float", "double"))
# Read width a cast imposes when it directly wraps a dereference: the read
# pulls exactly this many bytes instead of the configured pointer size.
# long/ulong follow the 64-bit pointer convention.
_CAST_WIDTHS = {
    "byte": 1,
    "word": 2,
    "short": 2,
    "ushort": 2,
    "dword": 4,
    "int": 4,
    "uint": 4,
    "float": 4,
    "qword": 8,
    "double": 8,
    "long": 8,
    "ulong": 8,
}


def integer(text: str) -> int:
    """AA integers are hexadecimal; # explicitly selects decimal."""
    text = text.strip()
    sign = -1 if text.startswith("-") else 1
    text = text.lstrip("+-")
    if not text or len(text) > 18:
        raise AddressExpressionError("Integer is empty or exceeds 64 bits.")
    try:
        value = int(text[1:], 10) if text.startswith("#") else int(text.removeprefix("$").removeprefix("0x").removeprefix("0X"), 16)
    except ValueError as exc:
        raise AddressExpressionError("Invalid AA integer.") from exc
    if value > MAX_ADDRESS:
        raise AddressExpressionError("Integer exceeds 64 bits.")
    return sign * value


def parse_expression(text: str, *, max_deref: int = 32) -> dict:
    if not isinstance(text, str) or not text.strip() or len(text) > 1024:
        raise AddressExpressionError("Address expression must contain 1–1024 characters.")
    if type(max_deref) is not int or max_deref < 1:
        raise AddressExpressionError("Pointer dereference bound must be a positive integer.")
    tokens = []
    position = 0
    while position < len(text.rstrip()):
        match = _TOKEN.match(text, position)
        if match is None:
            raise AddressExpressionError(f"Invalid address expression near {text[position:position + 20]!r}.")
        tokens.append(match.group(1))
        position = match.end()
    if len(tokens) > 256:
        raise AddressExpressionError("Address expression contains too many tokens.")
    if tokens.count("[") > max_deref:
        raise AddressExpressionError(f"Address expressions allow at most {max_deref} pointer dereferences.")
    cursor = 0

    def expression(priority=0, depth=0):
        nonlocal cursor
        if depth > 128 or cursor >= len(tokens):
            raise AddressExpressionError("Incomplete or deeply nested address expression.")
        token = tokens[cursor]
        cursor += 1
        if token in {"+", "-"}:
            # Leading + is a parent-relative CT address, unless no parent is supplied.
            value = {"kind": "unary", "operator": token, "value": expression(3, depth + 1)}
        elif token in {"(", "["}:
            if (token == "(" and cursor + 1 < len(tokens)
                    and tokens[cursor].casefold() in CAST_TYPES
                    and tokens[cursor + 1] == ")"):
                # Bounded type cast (WP-30): (type)operand.  The operand binds
                # at multiplicative precedence, so (int)a*b casts the product
                # while (int)a+b casts only a.  At resolution the cast is a
                # value no-op (symbol extraction and plan metadata ignore
                # it); when it directly wraps a dereference it selects that
                # dereference's read width.
                cast_type = tokens[cursor].casefold()
                cursor += 2
                if cursor >= len(tokens):
                    raise AddressExpressionError("Cast expression has no operand.")
                value = expression(1, depth + 1)
                value = {"kind": "cast", "type": cast_type, "value": value}
            else:
                value = expression(0, depth + 1)
                closing = ")" if token == "(" else "]"
                if cursor >= len(tokens) or tokens[cursor] != closing:
                    raise AddressExpressionError("Unbalanced address brackets.")
                cursor += 1
                if token == "[":
                    value = {"kind": "deref", "value": value}
        elif re.fullmatch(r"(?:0[xX]|\$)?[0-9a-fA-F]+|#[0-9]+", token):
            value = {"kind": "integer", "value": integer(token)}
        elif token.startswith('"'):
            atom = token[1:-1]
            if any(char in atom for char in "/\\:") or not atom.casefold().endswith((".exe", ".dll")):
                raise AddressExpressionError(
                    f"Quoted atom '{atom}' must be a module basename (.exe/.dll).")
            value = {"kind": "module", "name": atom}
        elif _MANAGED_LABEL.fullmatch(token):
            # IL2CPP injection label (Class:Method or the Class::Method
            # alias); resolved through the injected symbol map, never
            # through module exports.
            value = {"kind": "managed", "name": token}
        elif _DIGIT_MODULE.fullmatch(token):
            # Module basename starting with a digit (WP-22); same module
            # resolution path as letter-leading basenames.
            value = {"kind": "module", "name": token}
        elif re.fullmatch(_DIGIT_LEADING_SYMBOL, token):
            # Digit-leading symbol name (RT-4.3 O10): a non-hex character is
            # guaranteed inside the token, so it can never be a hex constant;
            # it resolves through the ordinary symbol table.
            value = {"kind": "symbol", "name": token}
        elif re.fullmatch(_HYPHEN_MODULE, token):
            # Hyphenated module basename (RT-4.3 O10); the .exe/.dll suffix
            # anchors it, so it can never be a symbol or a hex constant.
            value = {"kind": "module", "name": token}
        elif re.fullmatch(r"@?[A-Za-z_$][A-Za-z0-9_.$]*", token):
            if token.casefold().endswith((".exe", ".dll")) or token == "$process":
                kind = "module"
            elif "." in token:
                module_part = token.rsplit(".", 1)[0]
                if (not token.startswith("@") and token.count(".") >= 2
                        and not module_part.casefold().endswith((".exe", ".dll"))):
                    # Managed method label (Namespace.Class.Method): never a
                    # module-prefixed export and no local @-label. Resolved
                    # through the injected symbol map.
                    kind = "managed"
                else:
                    kind = "export"
            else:
                kind = "symbol"
            value = {"kind": kind, "name": token}
        else:
            raise AddressExpressionError("Unexpected address expression token.")
        while cursor < len(tokens):
            operator = tokens[cursor]
            precedence = 1 if operator in {"+", "-"} else 2 if operator in {"*", "/"} else 0
            if precedence <= priority:
                break
            cursor += 1
            right = expression(precedence, depth + 1)
            value = {"kind": "binary", "operator": operator, "left": value, "right": right}
        return value

    parsed = expression()
    if cursor != len(tokens):
        raise AddressExpressionError("Unexpected trailing address expression tokens.")
    return parsed


def expression_symbols(text: str) -> list[str]:
    found = {}

    def visit(node):
        if node["kind"] == "symbol":
            found.setdefault(node["name"].casefold(), node["name"])
        for key in ("value", "left", "right"):
            if isinstance(node.get(key), dict):
                visit(node[key])

    visit(parse_expression(text))
    return list(found.values())


def resolve_expression(text: str, memory, symbols: Mapping[str, int] | None = None, *, parent: int | None = None, process_name: str | None = None, pointer_size: int = 8) -> int:
    symbols = {} if symbols is None else symbols
    if not isinstance(symbols, Mapping) or any(not isinstance(key, str) or type(value) is not int for key, value in symbols.items()):
        raise AddressExpressionError("Symbols must map string names to integer addresses.")
    folded = {key.casefold(): value for key, value in symbols.items()}
    if len(folded) != len(symbols):
        raise AddressExpressionError("Ambiguous case-insensitive symbol mapping.")
    if pointer_size not in {4, 8}:
        raise AddressExpressionError("Pointer size must be 4 or 8 bytes.")

    def evaluate(node, deref_width=None):
        kind = node["kind"]
        if kind == "integer":
            return node["value"]
        if kind == "symbol":
            try:
                return folded[node["name"].casefold()]
            except KeyError as exc:
                raise AddressExpressionError(f"Unresolved symbol: {node['name']}.") from exc
        if kind == "managed":
            try:
                return folded[node["name"].casefold()]
            except KeyError as exc:
                raise AddressExpressionError(f"Unresolved managed method label: {node['name']}.") from exc
        if kind == "module":
            name = node["name"]
            if name == "$process":
                if process_name is None:
                    raise AddressExpressionError("$process requires an exact process name.")
                name = process_name
            return memory.module(name)[0]
        if kind == "export":
            # CE symhandler order (RT-4.3 O10): the symbol table is consulted
            # before the module export table, so a registered symbol whose
            # name carries a dot shadows the export lookup of the same
            # spelled atom.  Parse-time classification and the plan symbol
            # set are unchanged; only the runtime lookup order differs.
            symbol_key = node["name"].casefold()
            if symbol_key in folded:
                return folded[symbol_key]
            if not hasattr(memory, "resolve_export"):
                raise AddressExpressionError("The memory backend has no remote PE export resolver.")
            module, export = node["name"].rsplit(".", 1)
            return memory.resolve_export(module if module.casefold().endswith((".exe", ".dll")) else module + ".dll", export)
        if kind == "deref":
            width = pointer_size if deref_width is None else deref_width
            address = evaluate(node["value"])
            if not 0 < address <= MAX_ADDRESS - width + 1:
                raise AddressExpressionError("Dereference address is out of range.")
            data = memory.read(address, width)
            if len(data) != width:
                raise AddressExpressionError("Pointer read was incomplete.")
            pointer = int.from_bytes(data, "little")
            if pointer == 0:
                raise AddressExpressionError("Address expression dereferences a null pointer.")
            return pointer
        if kind == "cast":
            # Bounded type cast (WP-30): value-identical to its operand; the
            # cast node carries profile metadata, not arithmetic.  The one
            # exception is a cast that directly wraps a dereference, which
            # selects that dereference's read width (byte=1, word=2,
            # dword=4, qword=8); a plain cast over a deref keeps the
            # configured pointer size.
            inner = node["value"]
            if inner.get("kind") == "deref":
                width = _CAST_WIDTHS.get(node["type"])
                if width is not None:
                    return evaluate(inner, width)
            return evaluate(node["value"])
        if kind == "unary":
            value = evaluate(node["value"])
            return value if node["operator"] == "+" else -value
        left, right = evaluate(node["left"]), evaluate(node["right"])
        operator = node["operator"]
        if operator == "+":
            result = left + right
        elif operator == "-":
            result = left - right
        elif operator == "*":
            result = left * right
        else:
            if right == 0 or left % right:
                raise AddressExpressionError("Address division must be exact and nonzero.")
            result = left // right
        if abs(result) > MAX_ADDRESS:
            raise AddressExpressionError("Intermediate address arithmetic overflows 64 bits.")
        return result

    result = evaluate(parse_expression(text))
    if parent is not None and text.lstrip().startswith(("+", "-")):
        result += parent
    if not 0 <= result <= MAX_ADDRESS:
        raise AddressExpressionError("Resolved address is out of range.")
    return result
