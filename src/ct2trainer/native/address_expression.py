"""Bounded, independently implemented address arithmetic; never uses eval."""

from __future__ import annotations

import re
from collections.abc import Mapping


class AddressExpressionError(ValueError):
    pass


# Managed method label: Class:Method (IL2CPP injection label). Exactly two
# identifier segments separated by one colon; offsets attach like any other
# base atom.
_MANAGED_LABEL = re.compile(r"[A-Za-z_$][A-Za-z0-9_]*:[A-Za-z_$][A-Za-z0-9_]*\Z")
_TOKEN = re.compile(r'\s*("[^"\r\n]+"|0[xX][0-9a-fA-F]+|\$[0-9a-fA-F]+|#[0-9]+|[A-Za-z_$][A-Za-z0-9_]*:[A-Za-z_$][A-Za-z0-9_]*|@?[A-Za-z_$][A-Za-z0-9_.$]*|[0-9][0-9a-fA-F]*|[+\-*/()\[\]])')
MAX_ADDRESS = 0xFFFFFFFFFFFFFFFF


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


def parse_expression(text: str) -> dict:
    if not isinstance(text, str) or not text.strip() or len(text) > 1024:
        raise AddressExpressionError("Address expression must contain 1–1024 characters.")
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
    if tokens.count("[") > 32:
        raise AddressExpressionError("Address expressions allow at most 32 pointer dereferences.")
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
                raise AddressExpressionError("Quoted atoms must be module basenames.")
            value = {"kind": "module", "name": atom}
        elif _MANAGED_LABEL.fullmatch(token):
            # IL2CPP injection label (Class:Method); resolved through the
            # injected symbol map, never through module exports.
            value = {"kind": "managed", "name": token}
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

    def evaluate(node):
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
            if not hasattr(memory, "resolve_export"):
                raise AddressExpressionError("The memory backend has no remote PE export resolver.")
            module, export = node["name"].rsplit(".", 1)
            return memory.resolve_export(module if module.casefold().endswith((".exe", ".dll")) else module + ".dll", export)
        if kind == "deref":
            address = evaluate(node["value"])
            if not 0 < address <= MAX_ADDRESS - pointer_size + 1:
                raise AddressExpressionError("Dereference address is out of range.")
            data = memory.read(address, pointer_size)
            if len(data) != pointer_size:
                raise AddressExpressionError("Pointer read was incomplete.")
            pointer = int.from_bytes(data, "little")
            if pointer == 0:
                raise AddressExpressionError("Address expression dereferences a null pointer.")
            return pointer
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
