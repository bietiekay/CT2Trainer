"""Translate a deliberately small AA-compatible data-patch language.

Written for CT2Trainer from its own grammar and tests. No machine instruction
assembler, Lua, allocation, includes, remote threads, or CE implementation is
used. Unknown syntax rejects the entire record. Integer data directives use
hexadecimal literals by default; ``#`` explicitly selects decimal.
"""

from __future__ import annotations

import re

from .address_expression import CAST_TYPES, AddressExpressionError, parse_expression
from .patterns import normalize_pattern as _normalize_byte_pattern


MAX_SCRIPT_BYTES = 1024 * 1024
MAX_OPERATIONS = 4096
MAX_PATCH_BYTES = 65536
MAX_PATTERN_BYTES = 4096
_SYMBOL = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_HEX = re.compile(r"(?:0x|\$)?[0-9a-fA-F]+\Z", re.IGNORECASE)
_BASE = r'(?:"[A-Za-z0-9_ .()\-]+"|[A-Za-z_][A-Za-z0-9_.]*|(?:0x|\$)?[0-9A-Fa-f]+)'
_EXPRESSION = re.compile(r"(?P<base>" + _BASE + r")(?P<tail>(?:\s*[+-]\s*(?:0x|\$)?[0-9A-Fa-f]+)*)\Z", re.IGNORECASE)
_BASE_RE = re.compile(r"(?:" + _BASE + r")\Z")


class AAError(ValueError):
    """Unsupported or ambiguous script syntax, with no partial plan returned."""


def validate_symbol(symbol: str) -> str:
    if not isinstance(symbol, str) or len(symbol) > 128 or not _SYMBOL.fullmatch(symbol):
        raise AAError("Symbol must contain ASCII letters, digits or underscores.")
    if _HEX.fullmatch(symbol):
        raise AAError("All-hexadecimal symbol names are ambiguous and unsupported.")
    return symbol


def _hex_integer(value: str) -> int:
    value = value.strip()
    if not _HEX.fullmatch(value) or len(value) > 18:
        raise AAError("Expected a bounded hexadecimal address or offset.")
    return int(value.removeprefix("$").removeprefix("0x").removeprefix("0X"), 16)


def _strip_leading_casts(expression: str) -> str:
    """Drop bounded type-cast prefixes such as ``(dword)`` (WP-30).

    A cast is a value no-op, so ``(dword)Sym+10`` splits as the flat base
    ``Sym`` with offset ``0x10``.  Only an exact cast-name token with no
    interior whitespace is stripped; anything else stays for the bounded
    parser to judge.
    """
    while expression.startswith("("):
        closing = expression.find(")")
        if closing < 2 or expression[1:closing].casefold() not in CAST_TYPES:
            return expression
        expression = expression[closing + 1:].lstrip()
    return expression


def _flat_expression_shape(node: dict) -> bool:
    """Bounded expression shapes the strict static resolver can evaluate.

    The flat data dialect resolves one base atom plus signed hex
    displacements at runtime.  The bounded expression profile may add up
    to two pointer dereferences and value-identical casts, but no unary
    signs or multiplications/divisions the strict resolver cannot
    evaluate.
    """
    kind = node["kind"]
    if kind in {"integer", "symbol", "module", "managed"}:
        return True
    if kind in {"cast", "deref"}:
        return _flat_expression_shape(node["value"])
    if kind == "binary" and node["operator"] in {"+", "-"}:
        return _flat_expression_shape(node["left"]) and _flat_expression_shape(node["right"])
    return False


def split_expression(expression: str) -> tuple[str, int]:
    """Return one base atom and a signed hexadecimal displacement.

    Cast-only groups strip down to their flat base and tail.  Beyond the
    flat dialect, bounded expressions with up to two pointer dereferences
    are admitted verbatim with a zero displacement; callers route them to
    the expression profile instead of the strict static resolver.
    """
    if not isinstance(expression, str) or len(expression) > 256:
        raise AAError("Address expression exceeds 256 characters.")
    expression = expression.strip()
    stripped = _strip_leading_casts(expression)
    match = _EXPRESSION.fullmatch(stripped)
    if match is None:
        if stripped.count("[") > 2:
            raise AAError(
                "Address expression exceeds the bounded indirection depth "
                f"(2 pointer dereferences): {expression!r}.")
        if stripped != expression:
            expression = stripped
        try:
            node = parse_expression(expression, max_deref=2)
        except AddressExpressionError as exc:
            raise AAError(str(exc)) from exc
        if not _flat_expression_shape(node):
            raise AAError(f"Unsupported address expression: {expression!r}.")
        return expression, 0
    base = match.group("base")
    bare = base.strip('"')
    if base.startswith('"'):
        if not bare.casefold().endswith((".exe", ".dll")):
            raise AAError("Quoted addresses must be module basenames (.exe/.dll).")
    elif "." in base:
        if not base.casefold().endswith((".exe", ".dll")):
            raise AAError("Dotted address atoms must be module basenames (.exe/.dll).")
    elif not _HEX.fullmatch(base):
        validate_symbol(base)
    elif _hex_integer(base) > 0xFFFFFFFFFFFFFFFF:
        raise AAError("Absolute address exceeds 64 bits.")
    offset = 0
    for sign, number in re.findall(r"([+-])\s*((?:0x|\$)?[0-9A-Fa-f]+)", match.group("tail"), re.IGNORECASE):
        term = _hex_integer(number)
        if term > 0x7FFFFFFFFFFFFFFF:
            raise AAError("Address displacement exceeds signed 64 bits.")
        offset += term if sign == "+" else -term
    if abs(offset) > 0x7FFFFFFFFFFFFFFF:
        raise AAError("Combined address displacement exceeds signed 64 bits.")
    return base, offset


def _with_offset(base: str, offset: int) -> str:
    return base + (f"+{offset:X}" if offset > 0 else f"-{abs(offset):X}" if offset < 0 else "")


def validate_expression(expression: str) -> str:
    base, offset = split_expression(expression)
    return _with_offset(base, offset)


def is_flat_expression(expression: str) -> bool:
    """True when a canonical address keeps the static flat base/tail shape.

    Flat canonicals stay on the strict static (base, offset) resolver;
    anything the bounded parser admitted beyond the flat dialect
    (indirection, bounded grouping) requires the expression profile.
    """
    if not isinstance(expression, str) or len(expression) > 256:
        return False
    return _EXPRESSION.fullmatch(expression.strip()) is not None


def expression_symbols(expression: str) -> list[str]:
    match = _EXPRESSION.fullmatch(expression.strip()) if isinstance(expression, str) else None
    if match is not None:
        base = match.group("base")
        if base.startswith('"') or "." in base or _HEX.fullmatch(base):
            return []
        return [base]
    # Bounded expression form (cast, indirection, grouping): collect the
    # symbol atoms from the bounded parser AST, case-insensitive, first
    # spelling wins.
    found = {}

    def visit(node):
        if node["kind"] == "symbol":
            found.setdefault(node["name"].casefold(), node["name"])
        for key in ("value", "left", "right"):
            if isinstance(node.get(key), dict):
                visit(node[key])

    visit(parse_expression(expression))
    return list(found.values())


def normalize_pattern(pattern: str) -> str:
    try:
        return _normalize_byte_pattern(pattern)
    except ValueError as exc:
        raise AAError(str(exc)) from exc


def _exact_bytes(text: str) -> str:
    pattern = normalize_pattern(text)
    if "?" in pattern:
        raise AAError("Assertions require exact bytes; wildcards are unsupported.")
    return pattern.replace(" ", "").lower()


def _data_tokens(text: str) -> list[str]:
    """Split a data-directive value list on whitespace/commas, keeping
    quoted strings (both quote styles, WP-43) intact as single tokens so
    string literals may contain spaces."""
    tokens: list[str] = []
    current = ""
    quote = None
    for char in text:
        if quote is None:
            if char in {'"', "'"}:
                quote = char
                current = char
            elif char in " \t,":
                if current:
                    tokens.append(current)
                    current = ""
            else:
                current += char
        else:
            current += char
            if char == quote:
                tokens.append(current)
                current = ""
                quote = None
    if quote is not None:
        raise AAError("Unterminated quoted data literal.")
    if current:
        tokens.append(current)
    return tokens


def _data_bytes(directive: str, text: str) -> str:
    width = {"db": 1, "dw": 2, "dd": 4, "dq": 8}[directive]
    tokens = _data_tokens(text)
    if not tokens or len(tokens) * width > MAX_PATCH_BYTES:
        raise AAError("Data directive must contain bounded integer literals.")
    data = bytearray()
    for token in tokens:
        if token.startswith('"') or token.startswith("'"):
            # WP-43: quoted ASCII string literals (both quote styles) are
            # accepted exactly where integer literals are; only db may carry
            # them, and backslash escapes are refused fail-closed.
            if directive != "db" or any(ord(char) > 127 for char in token[1:-1]):
                raise AAError("Only db supports ASCII string constants.")
            if "\\" in token[1:-1]:
                raise AAError("Quoted data literals must not contain backslash escapes.")
            data.extend(token[1:-1].encode("ascii"))
            continue
        if len(token) > 32 or re.fullmatch(r"-?(?:(?:0x|\$)?[0-9A-Fa-f]+|#[0-9]+)", token) is None:
            raise AAError(f"Unsupported {directive} integer literal: {token!r}.")
        sign = -1 if token.startswith("-") else 1
        bare = token.removeprefix("-")
        value = sign * (int(bare[1:], 10) if bare.startswith("#") else _hex_integer(bare))
        bits = width * 8
        if not -(1 << (bits - 1)) <= value < (1 << bits):
            raise AAError(f"{directive} literal exceeds {bits} bits: {token!r}.")
        data.extend((value & ((1 << bits) - 1)).to_bytes(width, "little"))
    return data.hex()


def _without_comments(script: str) -> str:
    # The accepted dialect has //, non-nested {...} and non-nested /* */
    # comments.  Compiler directives such as {$LUA} must be rejected before
    # comment removal.
    if "{$" in script:
        raise AAError("Lua, C and compiler/preprocessor directives are unsupported.")
    output: list[str] = []
    in_comment = False
    in_block = False
    for line in script.splitlines():
        clean: list[str] = []
        index = 0
        while index < len(line):
            if in_block:
                if line[index:index + 2] == "*/":
                    in_block = False
                    clean.append(" ")
                    index += 2
                else:
                    clean.append(" ")
                    index += 1
                continue
            if not in_comment and line[index:index + 2] == "/*":
                in_block = True
                clean.append(" ")
                index += 2
                continue
            if not in_comment and line[index:index + 2] == "*/":
                raise AAError("Unmatched C block comment terminator.")
            if not in_comment and line[index:index + 2] == "//":
                break
            ch = line[index]
            if ch == "{":
                if in_comment:
                    raise AAError("Nested AA comments are unsupported.")
                in_comment = True
                clean.append(" ")
            elif ch == "}":
                if not in_comment:
                    raise AAError("Unmatched AA comment terminator.")
                in_comment = False
            elif not in_comment:
                clean.append(ch)
            index += 1
        output.append("".join(clean))
    if in_comment:
        raise AAError("Unterminated AA comment.")
    if in_block:
        raise AAError("Unterminated C block comment.")
    return "\n".join(output)


def _arguments(text: str, count: int) -> list[str]:
    values = [value.strip() for value in text.split(",")]
    if len(values) != count or any(not value for value in values):
        raise AAError(f"Expected exactly {count} nonempty directive arguments.")
    return values


def _section(lines: list[str], inherited: set[str]) -> tuple[list[dict], set[str], set[str], dict[str, str]]:
    operations: list[dict] = []
    defined = set(inherited)
    required: set[str] = set()
    registered: set[str] = set()
    declared: set[str] = set()
    spellings: dict[str, str] = {}
    current: str | None = None

    def need(expression: str) -> str:
        expression = expression.strip()
        base, _ = split_expression(expression)
        if _BASE_RE.fullmatch(base) is None:
            # The data dialect resolves one base atom plus signed hex
            # displacements at runtime; indirection and any other bounded
            # expression shape stay fail-closed with a named reason.
            if "[" in expression:
                raise AAError(
                    "Indirect address expressions are not supported in the data dialect: "
                    f"{expression!r}.")
            raise AAError(f"Unsupported address expression: {expression!r}.")
        expression = validate_expression(expression)
        for symbol in expression_symbols(expression):
            spellings[symbol.casefold()] = symbol
            if symbol.casefold() not in defined:
                required.add(symbol.casefold())
        return expression

    def introduce(symbol: str) -> None:
        validate_symbol(symbol)
        if symbol.casefold() in defined - inherited:
            raise AAError(f"Duplicate local symbol: {symbol}.")
        defined.add(symbol.casefold())
        spellings[symbol.casefold()] = symbol

    for line in lines:
        if len(operations) >= MAX_OPERATIONS:
            raise AAError("Too many AA operations.")
        command = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)", line)
        if command:
            name, args = command.group(1).casefold(), command.group(2)
            if name == "aobscanmodule":
                symbol, module, pattern = _arguments(args, 3)
                if module.startswith('"') or module.endswith('"'):
                    if not (module.startswith('"') and module.endswith('"') and module.count('"') == 2):
                        raise AAError("Scan module quotes must be balanced.")
                    module = module[1:-1]
                # Reuse the address grammar to reject paths and executable
                # text.  The $process token names the main module of the
                # attached process and bypasses the module-basename grammar.
                if module != "$process":
                    validate_expression('"' + module + '"')
                introduce(symbol)
                operations.append({"op": "scan", "symbol": symbol, "module": module,
                                   "pattern": normalize_pattern(pattern)})
            elif name == "define":
                symbol, expression = _arguments(args, 2)
                expression = need(expression)
                introduce(symbol)
                operations.append({"op": "define", "symbol": symbol, "expression": expression})
            elif name in {"registersymbol", "registerlabel", "unregistersymbol"}:
                tokens = [symbol for argument in args.split(",") for symbol in argument.split()]
                if not tokens:
                    raise AAError("Expected one or more nonempty directive arguments.")
                if len(operations) + len(tokens) > MAX_OPERATIONS:
                    raise AAError("Too many AA operations.")
                op = "unregister" if name == "unregistersymbol" else "register"
                for symbol in tokens:
                    validate_symbol(symbol)
                    spellings[symbol.casefold()] = symbol
                    if symbol.casefold() not in defined:
                        required.add(symbol.casefold())
                    if op == "register":
                        registered.add(symbol.casefold())
                    operations.append({"op": op, "symbol": symbol})
            elif name == "assert":
                address, data = _arguments(args, 2)
                operations.append({"op": "assert", "address": need(address), "bytes": _exact_bytes(data)})
            elif name == "label":
                symbol = _arguments(args, 1)[0]
                validate_symbol(symbol)
                if symbol.casefold() in declared:
                    raise AAError(f"Duplicate label declaration: {symbol}.")
                declared.add(symbol.casefold())
            else:
                raise AAError(f"Unsupported AA directive: {name}.")
            continue
        if line.endswith(":"):
            address = line[:-1].strip()
            if address.casefold() in declared and address.casefold() not in defined:
                if current is None:
                    raise AAError("A declared label requires a known data cursor.")
                introduce(address)
                operations.append({"op": "define", "symbol": address, "expression": current})
                current = address
            else:
                current = need(address)
            continue
        directive = re.fullmatch(r"(db|dw|dd|dq)\s+(.+)", line, re.IGNORECASE)
        if directive:
            if current is None:
                raise AAError("Data directive requires a preceding address label.")
            data = _data_bytes(directive.group(1).casefold(), directive.group(2))
            operations.append({"op": "write", "address": current, "bytes": data})
            base, offset = split_expression(current)
            current = _with_offset(base, offset + len(data) // 2)
            continue
        raise AAError(f"Unsupported AA syntax or machine instruction: {line[:120]!r}.")
    if declared - defined:
        raise AAError("Declared labels must be defined by a known data cursor.")
    return operations, required, registered, {key: spellings[key] for key in required | registered}


def _location(expression: str, aliases: dict[str, str] | None = None) -> tuple[str, int]:
    base, offset = split_expression(expression)
    seen: set[str] = set()
    while aliases and base.casefold() in aliases:
        if base.casefold() in seen or len(seen) >= 64:
            raise AAError("Cyclic or excessively deep local address aliases are unsupported.")
        seen.add(base.casefold())
        base, displacement = split_expression(aliases[base.casefold()])
        offset += displacement
    return base.strip('"').casefold(), offset


def _guarded_writes(operations: list[dict], aliases: dict[str, str]) -> dict[tuple[str, int], tuple[str, str]]:
    """Collect guarded byte writes of one phase keyed by (base, offset)."""
    assertions: list[tuple[str, int, bytes]] = []
    writes: dict[tuple[str, int], tuple[str, str]] = {}
    occupied: list[tuple[str, int, int]] = []
    for operation in operations:
        if operation["op"] == "define":
            aliases[operation["symbol"].casefold()] = operation["expression"]
            continue
        if operation["op"] not in {"assert", "write"}:
            continue
        base, offset = _location(operation["address"], aliases)
        data = bytes.fromhex(operation["bytes"])
        if operation["op"] == "assert":
            assertions.append((base, offset, data))
            continue
        original = None
        for target, start, expected in reversed(assertions):
            if target == base and start <= offset and offset + len(data) <= start + len(expected):
                original = expected[offset - start:offset - start + len(data)]
                break
        if original is None:
            raise AAError("Every byte write requires a preceding exact assertion covering its range.")
        if any(target == base and offset < end and start < offset + len(data)
               for target, start, end in occupied):
            raise AAError("Overlapping byte writes within one script phase are unsupported.")
        occupied.append((base, offset, offset + len(data)))
        writes[(base, offset)] = (original.hex(), data.hex())
    return writes


def validate_patch_guards(enable: list[dict], disable: list[dict]) -> None:
    """Require prior exact assertions and a symmetric byte restoration plan."""
    aliases: dict[str, str] = {}
    enabling, disabling = _guarded_writes(enable, aliases), _guarded_writes(disable, aliases)
    if enabling.keys() != disabling.keys():
        raise AAError("Enable and disable must patch the same address ranges.")
    for address, (original, patched) in enabling.items():
        if disabling[address] != (patched, original):
            raise AAError("Disable must assert enabled bytes and restore the exact enable assertion bytes.")


def validate_one_shot_guards(enable: list[dict]) -> None:
    """Require prior exact assertions for a one-shot enable phase."""
    _guarded_writes(enable, {})


def compile_script(script: str, external_owned: frozenset[str] = frozenset()) -> dict:
    """Compile a data-dialect AA script into enable/disable operation lists.

    ``external_owned`` carries the casefolded names of externally owned
    symbols (WP-37: registered by another record's Lua or allocation-only
    program).  A disable phase releasing one of those names is refused with
    the named handover reason instead of the generic cleanup-ownership
    refusal, because the owning record releases it on deactivation.
    """
    if not isinstance(script, str) or len(script.encode("utf-8")) > MAX_SCRIPT_BYTES:
        raise AAError("AA script exceeds 1 MiB.")
    clean = _without_comments(script)
    phases: dict[str, list[str]] = {"common": [], "enable": [], "disable": []}
    phase = "common"
    seen: set[str] = set()
    for raw in clean.splitlines():
        line = raw.strip()
        if not line:
            continue
        marker = re.fullmatch(r"\[\s*(ENABLE|DISABLE)\s*\]", line, re.IGNORECASE)
        if marker:
            phase = marker.group(1).casefold()
            if phase in seen or (phase == "enable" and "disable" in seen):
                raise AAError("Require exactly one ENABLE section followed by one DISABLE section.")
            seen.add(phase)
        else:
            if phase == "common" and re.fullmatch(r"(?:define|label|registersymbol|registerlabel)\s*\(.*\)", line, re.IGNORECASE) is None:
                raise AAError("Only define, label and register declarations are allowed before ENABLE.")
            phases[phase].append(line)
    if seen != {"enable", "disable"}:
        raise AAError("Both ENABLE and DISABLE sections are required.")
    # WP-44: pre-ENABLE register declarations register at activation and are
    # released by the disable phase, so they join the ENABLE section only;
    # define/label declarations stay shared by both phases.
    common_declarations = []
    common_registers = []
    for line in phases["common"]:
        if re.fullmatch(r"(?:registersymbol|registerlabel)\s*\(.*\)", line, re.IGNORECASE):
            common_registers.append(line)
        else:
            common_declarations.append(line)
    enable, requires, provides, names = _section(common_declarations + common_registers + phases["enable"], set())
    local = {operation["symbol"].casefold() for operation in enable if operation["op"] in {"scan", "define"}}
    disable, disable_requires, _, disable_names = _section(common_declarations + phases["disable"], local)
    # Disable-only requirements still need a known external provider.
    requires |= disable_requires - local
    names.update(disable_names)
    unregister = {operation["symbol"].casefold() for operation in disable if operation["op"] == "unregister"}
    if provides != unregister:
        foreign = sorted(
            (operation["symbol"] for operation in disable if operation["op"] == "unregister"
             and operation["symbol"].casefold() in external_owned
             and operation["symbol"].casefold() not in provides),
            key=str.casefold,
        )
        if foreign:
            # WP-37: releasing a symbol owned by another record races its
            # deactivation path, so the named handover refusal is reported.
            raise AAError(
                f"Program may not unregister or deallocate the externally owned symbol {foreign[0]}.")
        raise AAError("Exactly the registered enable symbols must be unregistered on disable.")
    if any(operation["op"] == "scan" for operation in disable):
        raise AAError("Disable must reuse the original resolved symbols; rescanning is unsupported.")
    if any(operation["op"] == "unregister" for operation in enable) or any(operation["op"] == "register" for operation in disable):
        raise AAError("Symbols register only on enable and unregister only on disable.")
    if not provides <= local:
        raise AAError("Only locally defined/scanned symbols can be registered.")
    validate_patch_guards(enable, disable)
    if not provides and not any(operation["op"] == "write" for operation in enable):
        raise AAError("Script has no registered symbols or guarded byte-patch action.")
    return {"enable": enable, "disable": disable,
            "requires": [names[key] for key in sorted(requires)],
            "provides": [names[key] for key in sorted(provides)]}


def compile_one_shot(script: str) -> dict:
    """Compile an ENABLE-only one-shot script (missing or empty DISABLE).

    A one-shot applies its enable program once and has no disable phase to
    undo it, so the dialect is stricter than ``compile_script``: there is no
    second phase, no symbol registration could ever be released, and every
    byte write still requires a preceding exact assertion.  The result keeps
    an empty disable list so engine and plan validators share one shape.
    """
    if not isinstance(script, str) or len(script.encode("utf-8")) > MAX_SCRIPT_BYTES:
        raise AAError("AA script exceeds 1 MiB.")
    clean = _without_comments(script)
    phases: dict[str, list[str]] = {"common": [], "enable": [], "disable": []}
    phase = "common"
    seen: set[str] = set()
    for raw in clean.splitlines():
        line = raw.strip()
        if not line:
            continue
        marker = re.fullmatch(r"\[\s*(ENABLE|DISABLE)\s*\]", line, re.IGNORECASE)
        if marker:
            next_phase = marker.group(1).casefold()
            if next_phase in seen or (next_phase == "enable" and "disable" in seen):
                raise AAError("Require exactly one ENABLE section followed by one DISABLE section.")
            seen.add(next_phase)
            phase = next_phase
        else:
            if phase == "common" and re.fullmatch(r"(?:define|label)\s*\(.*\)", line, re.IGNORECASE) is None:
                raise AAError("Only define/label declarations are allowed before ENABLE.")
            phases[phase].append(line)
    if "enable" not in seen:
        raise AAError("Both ENABLE and DISABLE sections are required.")
    if "disable" in seen and phases["disable"]:
        raise AAError("One-shot scripts may only carry an empty or missing DISABLE section.")
    enable, requires, provides, names = _section(phases["common"] + phases["enable"], set())
    if provides or any(operation["op"] == "unregister" for operation in enable):
        raise AAError("One-shot scripts cannot register or unregister symbols; there is no disable phase to release them.")
    validate_one_shot_guards(enable)
    if not any(operation["op"] == "write" for operation in enable):
        raise AAError("One-shot script has no guarded byte-patch action.")
    return {"enable": enable, "disable": [],
            "requires": [names[key] for key in sorted(requires)],
            "provides": []}
