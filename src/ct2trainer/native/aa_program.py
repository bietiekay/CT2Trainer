"""Independent AA grammar and remote-address linker backed by BSD NASM.

Compilation and linking are read-only. Allocation, thread coordination,
installation and restoration belong to the runtime transaction layer.

Conditional blocks: ``{$define NAME LITERAL}`` macros are collected from
whole lines of the source, then the tested Stage-1 model
(:func:`ct2trainer.native.aa_blocks.prune_conditionals`) deterministically
prunes ``{$if <cond>}`` / ``{$else}`` / ``{$endif}`` before per-line parsing.
Only the selected branch survives; every decision is recorded in the
program's ``conditional_decisions`` (original line, condition, chosen
branch) and the macro set in ``defines``.  Macros are collected from the
whole cleaned source, so a define inside a pruned branch still counts;
branch selection never hides a macro.  All other ``{$...}`` directives,
undefined defines, unbalanced blocks, duplicate ``{$else}`` and nesting
beyond the model bound are refused fail-closed.

Nested assembly: ``autoAssemble("Label")`` / ``autoasm("Label")`` lines are
resolved during preparation by the tested Stage-1 model
(:func:`ct2trainer.native.aa_blocks.resolve_nested_assembly`), composed
after pruning exactly as :func:`ct2trainer.native.aa_blocks.analyze_blocks`
does.  The resolver engages only when such an invocation survives
conditional pruning, so every program without nested invocations keeps the
exact pre-wiring plan shape (plain ``name:`` address labels may still
repeat between sections; the resolver's single-definition rule applies
only to nested-assembly sources).  When active, label definitions
(``name:`` lines, bodies to the next label or end of source) and an
optional external label registry (``labels`` keyword, table-level label
bodies) are validated fail-closed (unknown labels, internal/external
collisions, duplicate invocations, cycles), and the resolved bodies are
inlined at the invocation sites in deterministic topological order (callee
before caller; nested calls expand inline).  The plan then carries additive
metadata: ``nested_invocations`` (label, original source line, depth),
``nested_label_order`` (topological order) and, when an external registry
was passed, ``external_labels`` (the normalized registry, so validation
re-preparation reproduces the identical plan).  Label bodies must not
contain ``[ENABLE]``/``[DISABLE]`` section markers.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import struct
from collections.abc import Mapping

from .aa import AAError, validate_symbol, normalize_pattern
from .aa_blocks import (BlockError, analyze_blocks, label_spans, parse_invocation,
                        parse_label, prune_conditionals, resolve_nested_assembly)
from .aa_directives import MAX_DISASSEMBLE_COUNT, MAX_PROTECTION_SIZE, PAGE_NAMES
from .address_expression import AddressExpressionError, expression_symbols, integer, parse_expression, resolve_expression
from .assembler import AssemblyError, NasmAssembler


SCHEMA = "ct2trainer-aa-program/v1"
MAX_NODES = 8192
MAX_PROCESS_SCANS = 16
MAX_BLOCK_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 4 * 1024 * 1024
_SYMBOL_TOKEN = re.compile(r"@?[A-Za-z_][A-Za-z0-9_]*\Z")
_REGISTERS = {"rax", "rbx", "rcx", "rdx", "rsi", "rdi", "rbp", "rsp", "eax", "ebx", "ecx", "edx", "esi", "edi", "ebp", "esp", "ax", "bx", "cx", "dx", "si", "di", "bp", "sp", "al", "bl", "cl", "dl", "ah", "bh", "ch", "dh", "sil", "dil", "bpl", "spl", "rip", "eip", "fs", "gs", "cs", "ds", "es", "ss"}
_REGISTERS |= {f"r{index}{suffix}" for index in range(8, 16) for suffix in ("", "d", "w", "b")}
_REGISTERS |= {f"{kind}{index}" for kind in ("xmm", "ymm", "zmm", "mm", "k", "st", "cr", "dr") for index in range(32)}
_KEYWORDS = {"byte", "word", "dword", "qword", "tword", "oword", "xmmword", "yword", "ymmword", "zword", "zmmword", "short", "near", "far", "strict", "rel", "abs", "to"}
_FORBIDDEN = {"bits", "org", "section", "segment", "global", "extern", "common", "equ", "times", "incbin", "include", "resw", "resd", "resq", "istruc", "struc", "endstruc", "iend", "absolute", "default", "cpu", "warning", "map", "alignb"}
_TOKEN_OPERAND = re.compile(r"'[^'\r\n\\]'|"+r'"[^"\r\n]+"|@[A-Za-z_][A-Za-z0-9_]*|0[xX][0-9a-fA-F]+|\$[0-9a-fA-F]+|#[0-9]+|[A-Za-z_$][A-Za-z0-9_.$]*|[0-9][0-9a-fA-F]*|\s+|[][+\-*/(),:]')
_FLOAT = re.compile(r"\((float|double)\)\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)", re.I)
# Conditional-block directives pass through cleaning; every other {$...} token
# stays a fail-closed refusal. Condition/define bodies are validated later by
# the pinned block model and the strict $define grammar below.
_CONDITIONAL_DIRECTIVES = {
    "if": re.compile(r"\{\$if\s.+\s*\}\Z", re.IGNORECASE),
    "else": re.compile(r"\{\$else\}\Z", re.IGNORECASE),
    "endif": re.compile(r"\{\$endif\}\Z", re.IGNORECASE),
    "define": re.compile(r"\{\$define\s.+\}\Z", re.IGNORECASE),
}
# CE 7.5 recognizes these {$...} directives in this profile as no-ops; they
# are stripped rather than refused (WP-26). The bare mode marker ``{$asm}``
# outside an explicit Lua section is a redundant no-op in the same sense.
_NOOP_DIRECTIVES = frozenset(
    ("{$asm}", "{$ccode}", "{$luacode}", "{$strict}", "{$try}", "{$except}"))
_DEFINE_DIRECTIVE = re.compile(
    r"\{\$define\s+([A-Za-z_][A-Za-z0-9_]*)\s+"
    r"([+-]?(?:0x[0-9A-Fa-f]+|\$[0-9A-Fa-f]+|[0-9]+))\s*\}\Z", re.IGNORECASE)
# These mnemonics have no implicit memory stores. Explicit destinations still
# undergo the owned-label/register-alias checks below. NASM admits many more
# instructions: their containing allocation stays writable unless we prove the
# relevant memory effects here, including instructions added in future NASM.
_NO_IMPLICIT_STORES = {
    "mov", "movsx", "movzx", "movsxd", "lea", "xchg",
    "add", "adc", "sub", "sbb", "and", "or", "xor", "cmp", "test",
    "inc", "dec", "neg", "not", "mul", "imul", "div", "idiv",
    "shl", "sal", "shr", "sar", "rol", "ror", "rcl", "rcr", "shld", "shrd",
    "bt", "bts", "btr", "btc", "bsf", "bsr", "bswap",
    "nop", "pause", "ret", "retn", "clc", "stc", "cmc", "cld", "std",
    "cbw", "cwde", "cdqe", "cwd", "cdq", "cqo", "lahf", "sahf",
    "jmp", "je", "jne", "jz", "jnz", "jb", "jbe", "ja", "jae", "jc", "jnc",
    "jo", "jno", "js", "jns", "jp", "jnp", "jpe", "jpo", "jg", "jge", "jl", "jle",
    "jna", "jnae", "jnb", "jnbe", "jng", "jnge", "jnl", "jnle", "jcxz", "jecxz", "jrcxz",
    "loop", "loope", "loopne", "loopz", "loopnz",
}
_RELATIVE_BRANCHES = {name for name in _NO_IMPLICIT_STORES if name.startswith("j") or name.startswith("loop")} | {"call", "xbegin"}


class ProgramError(AAError):
    pass


def _args(text: str) -> list[str]:
    output, start, depth, quote = [], 0, 0, None
    for index, char in enumerate(text):
        if char in {'"',"'"}:
            if quote is None:quote=char
            elif quote==char:quote=None
        elif not quote and char in "([":
            depth += 1
        elif not quote and char in ")]":
            depth -= 1
        elif not quote and depth == 0 and char == ",":
            output.append(text[start:index].strip())
            start = index + 1
        if depth < 0:
            raise ProgramError("Unbalanced directive arguments.")
    output.append(text[start:].strip())
    if depth or quote or any(not value for value in output):
        raise ProgramError("Malformed or empty directive arguments.")
    return output


def _pattern(text: str) -> str:
    try:
        return normalize_pattern(text)
    except AAError as exc:
        raise ProgramError(str(exc)) from exc


def _expression(text: str) -> str:
    try:
        parse_expression(text)
    except AddressExpressionError as exc:
        raise ProgramError(str(exc)) from exc
    return text.strip()


def _float_bits(text: str) -> tuple[int, int] | None:
    match = _FLOAT.fullmatch(text.strip())
    if match is None:
        return None
    size = 4 if match.group(1).casefold() == "float" else 8
    value = float(match.group(2))
    if not math.isfinite(value):
        raise ProgramError("Floating constants must be finite.")
    try:
        data = struct.pack("<f" if size == 4 else "<d", value)
    except (OverflowError, struct.error) as exc:
        raise ProgramError("Floating constant exceeds its representation.") from exc
    return int.from_bytes(data, "little"), size


def _scalar_expression(text: str) -> bool:
    if _float_bits(text) is not None:
        return True

    def scalar(node):
        return node["kind"] == "integer" or node["kind"] == "unary" and scalar(node["value"]) or node["kind"] == "binary" and scalar(node["left"]) and scalar(node["right"])

    return scalar(parse_expression(text))


def _data_values(text: str, directive: str) -> list[str]:
    values = re.findall(r'"[^"\r\n]*"|\((?:float|double)\)\s*[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?|[^\s,]+', text, re.I)
    if not values or len(values) > 65536:
        raise ProgramError("Data directives require a bounded nonempty value list.")
    reconstructed = re.sub(r"\s|,", "", text)
    if reconstructed != re.sub(r"\s|,", "", "".join(values)):
        raise ProgramError("Malformed data directive.")
    size = {"db": 1, "dw": 2, "dd": 4, "dq": 8}[directive]
    for value in values:
        if value.startswith('"'):
            if directive != "db" or any(ord(char) > 127 for char in value[1:-1]):
                raise ProgramError("Only db supports ASCII string constants.")
        elif _float_bits(value):
            if _float_bits(value)[1] > size:
                raise ProgramError("Floating bit-pattern does not fit the data directive.")
        else:
            _expression(value)
    return values


def _operand_tokens(text: str):
    text = re.sub(r"\bptr\b", "", text, flags=re.I)
    text = _FLOAT.sub(lambda match: "0x" + format(_float_bits(match.group())[0], "X"), text)
    position, values = 0, []
    while position < len(text):
        match = _TOKEN_OPERAND.match(text, position)
        if match is None:
            raise ProgramError(f"Unsupported instruction operand near {text[position:position + 25]!r}.")
        token=match.group()
        if token.startswith("'"):
            if not 32<=ord(token[1])<=126:
                raise ProgramError('Instruction character literals require one printable ASCII byte.')
            token='0x'+format(ord(token[1]),'X')
        values.append(token)
        position = match.end()
    return values


def _instruction(text: str) -> dict:
    match = re.fullmatch(r"([A-Za-z][A-Za-z0-9]*)\s*(.*)", text)
    if match is None or len(text) > 2048:
        raise ProgramError("Invalid or oversized machine instruction.")
    mnemonic, operands = match.group(1).casefold(), match.group(2)
    if mnemonic in _FORBIDDEN or mnemonic in {"db", "dw", "dd", "dq"}:
        raise ProgramError(f"Unsupported assembler directive: {mnemonic}.")
    if mnemonic in {"lock", "rep", "repe", "repne", "repz", "repnz"}:
        nested = _instruction(operands)
        nested["text"] = mnemonic + " " + nested["text"]
        return nested
    _operand_tokens(operands)
    if mnemonic == "nop" and operands:
        count = integer(operands)
        if not 1 <= count <= 65536:
            raise ProgramError("nop count must contain 1–65536 bytes.")
        return {"op": "nops", "count": count}
    return {"op": "instruction", "text": text.strip()}


def _clean_source(source: str) -> str:
    """Remove line, flat brace and C comments, retaining strings and line count."""
    if not isinstance(source, str) or len(source.encode("utf-8")) > 1024 * 1024:
        raise ProgramError("Program source exceeds its size bound.")
    output, index, quote, block = [], 0, None, None
    while index < len(source):
        pair = source[index:index + 2]
        if block is not None:
            if block == "line" and source[index] == "\n":
                block = None
                output.append("\n")
                index += 1
                continue
            if block == "brace" and source[index] == "}":
                block = None
                output.append(" ")
                index += 1
                continue
            if block == "c" and pair == "*/":
                block = None
                output.append(" ")
                index += 2
                continue
            output.append("\n" if source[index] == "\n" else " ")
        elif source[index] in {'"',"'"}:
            if quote is None:quote=source[index]
            elif quote==source[index]:quote=None
            output.append(source[index])
        elif not quote and pair in {"/*", "//"}:
            block = "c" if pair == "/*" else "line"
            output.append(" ")
            index += 2
            continue
        elif not quote and pair == "*/":
            raise ProgramError("Unmatched C block comment terminator.")
        elif not quote and pair == "{$":
            end = source.find("}", index)
            token = source[index:end + 1].strip() if end > index and "\n" not in source[index:end] else None
            if token is None:
                raise ProgramError("Lua, C and compiler/preprocessor directives are unsupported.")
            if any(pattern.fullmatch(token) for pattern in _CONDITIONAL_DIRECTIVES.values()):
                output.append(token)
            elif token.casefold() not in _NOOP_DIRECTIVES:
                raise ProgramError("Non-profile {$...} directive: " + token[2:-1].strip())
            index = end + 1
            continue
        elif not quote and source[index] == "{":
            block = "brace"
            output.append(" ")
        elif not quote and source[index] == "}":
            raise ProgramError("Unmatched brace comment terminator.")
        else:
            output.append(source[index])
        index += 1
    if block in {"c", "brace"}:
        raise ProgramError("Unterminated source block comment.")
    if quote:
        raise ProgramError("Unterminated quoted string.")
    return "".join(output)


def _quoted_name(text: str, what: str) -> str:
    """Exact quoted argument for module/export names, e.g. "kernel32"."""
    if (len(text) < 2 or not text.startswith('"') or not text.endswith('"')
            or '"' in text[1:-1] or not text[1:-1].strip()):
        raise ProgramError(f"getmodulehandle/getprocaddress require an exact quoted {what}.")
    return text[1:-1]


def _page_constant(text: str) -> int:
    """Page argument: PAGE_* name (case-insensitive) or integer constant."""
    label = text.strip().casefold()
    for page, name in PAGE_NAMES.items():
        if name.casefold() == label:
            return page
    try:
        return integer(text)
    except AddressExpressionError as exc:
        raise ProgramError(
            f"protect page must be a PAGE_* name or integer constant, got: {text}") from exc


def _numeric_token(token: str) -> int | None:
    """One bare numeric literal (hex, $hex, 0x or #decimal), else None."""
    if re.fullmatch(r"-?(?:0[xX]|\$)?[0-9A-Fa-f]+|-?#[0-9]+", token) is None:
        return None
    try:
        return integer(token)
    except AddressExpressionError:
        return None


def _parse_line(line: str) -> dict:
    if line.endswith(":"):
        expression = line[:-1].strip()
        return {"op": "cursor", "expression": "@@" if expression == "@@" else _expression(expression)}
    command = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)", line)
    if command:
        name = command.group(1).casefold()
        if name == "threadwait" and command.group(2).strip() == "":
            return {"op": "threadwait"}
        raw_args = command.group(2)
        if raw_args.strip() == "" and name in {"createthread", "protect", "unprotect", "getmodulehandle", "getprocaddress"}:
            args = []
        else:
            args = _args(raw_args)
        if name in {"aobscan", "aobscanmodule", "aobscanregion"}:
            expected = {"aobscan": 2, "aobscanmodule": 3, "aobscanregion": 4}[name]
            if len(args) != expected:
                raise ProgramError(f"{name} requires {expected} arguments.")
            symbol = validate_symbol(args[0])
            if name == "aobscan":
                return {"op": "scan_process", "symbol": symbol, "pattern": _pattern(args[1])}
            if name == "aobscanmodule":
                module = args[1].strip('"')
                if module != "$process":
                    _expression('"' + module + '"')
                return {"op": "scan", "symbol": symbol, "module": module, "pattern": _pattern(args[2])}
            return {"op": "scan_region", "symbol": symbol, "start": _expression(args[1]), "end": _expression(args[2]), "pattern": _pattern(args[3])}
        if name == "alloc":
            if len(args) not in {2, 3}:
                raise ProgramError("alloc requires symbol, hexadecimal size and optional near address.")
            size = integer(args[1])
            if not 1 <= size <= MAX_BLOCK_BYTES:
                raise ProgramError("Allocation size must contain 1–1048576 bytes.")
            return {"op": "alloc", "symbol": validate_symbol(args[0]), "size": size, "near": _expression(args[2]) if len(args) == 3 else None}
        if name == "define":
            if len(args) != 2:
                raise ProgramError("define requires two arguments.")
            if _float_bits(args[1]) is None:
                _expression(args[1])
            return {"op": "define", "symbol": validate_symbol(args[0]), "expression": args[1]}
        if name in {"label", "registersymbol", "unregistersymbol", "registerlabel"}:
            args = [symbol for argument in args for symbol in argument.split()]
            if args == ["*"] and name != "unregistersymbol":
                raise ProgramError("Wildcard is only supported for scoped cleanup.")
            if args != ["*"]:
                for symbol in args:
                    validate_symbol(symbol)
            return {"op": {"registersymbol": "register", "registerlabel": "register", "unregistersymbol": "unregister"}.get(name, name), "symbols": args}
        if name == "dealloc":
            if len(args) not in {1, 2}:
                raise ProgramError("dealloc requires one symbol and an optional byte size.")
            if args[0] == "*":
                if len(args) != 1:
                    raise ProgramError("Wildcard dealloc takes no size.")
                return {"op": "dealloc", "symbols": ["*"]}
            validate_symbol(args[0])
            if len(args) == 1:
                return {"op": "dealloc", "symbols": [args[0]]}
            size = _numeric_token(args[1])
            if size is None or not 1 <= size <= MAX_BLOCK_BYTES:
                raise ProgramError("dealloc size must contain 1–1048576 bytes.")
            return {"op": "dealloc", "symbols": [args[0]], "size": size}
        if name == "fullaccess":
            if len(args) != 2:
                raise ProgramError("fullaccess requires an address expression and a byte size.")
            size = _numeric_token(args[1])
            if size is None or not 1 <= size <= MAX_PROTECTION_SIZE:
                raise ProgramError("fullaccess size must contain 1–0x1000000 bytes.")
            return {"op": "fullaccess", "address": _expression(args[0]), "size": size}
        if name in {"readmem", "reassemble", "assert"}:
            if len(args) != (1 if name == "reassemble" else 2):
                raise ProgramError(f"{name} has an invalid argument count.")
            node = {"op": name, "address": _expression(args[0])}
            if name == "readmem":
                size = integer(args[1])
                if not 1 <= size <= 65536:
                    raise ProgramError("readmem size must contain 1–65536 bytes.")
                node["size"] = size
            elif name == "assert":
                node["pattern"] = _pattern(args[1])
            return node
        if name == "disassemble":
            if len(args) != 2:
                raise ProgramError("disassemble requires an address expression and an instruction count.")
            count = integer(args[1])
            if not 1 <= count <= MAX_DISASSEMBLE_COUNT:
                raise ProgramError("disassemble count must contain 1–4096 instructions.")
            return {"op": "disassemble", "address": _expression(args[0]), "count": count}
        if name == "createthread":
            if len(args) != 1:
                raise ProgramError("createThread requires one address expression.")
            return {"op": "createthread", "address": _expression(args[0])}
        if name == "threadwait":
            if len(args) != 0:
                raise ProgramError("threadWait takes no arguments.")
            return {"op": "threadwait"}
        if name in {"protect", "unprotect"}:
            if len(args) != 3:
                raise ProgramError(f"{name} requires an address expression, a byte size and a page constant.")
            size = integer(args[1])
            if not 1 <= size <= MAX_PROTECTION_SIZE:
                raise ProgramError("protect size must contain 1–0x1000000 bytes.")
            return {"op": name, "address": _expression(args[0]), "size": size, "page": _page_constant(args[2])}
        if name == "getmodulehandle":
            if len(args) != 1:
                raise ProgramError("getmodulehandle requires one quoted module name.")
            return {"op": "getmodulehandle", "module": _quoted_name(args[0], "module name")}
        if name == "getprocaddress":
            if len(args) != 2:
                raise ProgramError("getprocaddress requires a quoted module name and a quoted export name.")
            return {"op": "getprocaddress", "module": _quoted_name(args[0], "module name"), "export": _quoted_name(args[1], "export name")}
        raise ProgramError(f"Unsupported AA directive: {name}.")
    reserve = re.fullmatch(r"(dq|resb)\s*", line, re.I)
    if reserve:
        return {"op": "reserve", "directive": reserve.group(1).casefold(), "bytes": 8 if reserve.group(1).casefold() == "dq" else 1}
    resb_n = re.fullmatch(r"resb\s+(\S+)", line, re.I)
    if resb_n:
        count = _numeric_token(resb_n.group(1))
        if count is None or not 1 <= count <= MAX_BLOCK_BYTES:
            raise ProgramError("resb count must contain 1–1048576 bytes.")
        return {"op": "reserve", "directive": "resb", "bytes": count}
    data = re.fullmatch(r"(db|dw|dd|dq)\s+(.+)", line, re.I)
    if data:
        directive = data.group(1).casefold()
        return {"op": "data", "directive": directive, "values": _data_values(data.group(2), directive)}
    align = re.fullmatch(r"align\s+([^\s,]+)(?:[\s,]+([^\s,]+))?", line, re.I)
    if align:
        alignment, fill = integer(align.group(1)), integer(align.group(2) or "90")
        if not 1 <= alignment <= 4096 or alignment & (alignment - 1) or not 0 <= fill <= 255:
            raise ProgramError("align requires a power of two <=4096 and one fill byte.")
        return {"op": "align", "alignment": alignment, "fill": fill}
    return _instruction(line)


def _managed_labels_in(text: str) -> list[str]:
    """Managed method labels referenced by one address expression."""
    found = {}

    def visit(node):
        if node["kind"] == "managed":
            found.setdefault(node["name"].casefold(), node["name"])
        for key in ("value", "left", "right"):
            if isinstance(node.get(key), dict):
                visit(node[key])

    visit(parse_expression(text))
    return list(found.values())


def _node_refs(node: dict) -> list[str]:
    values = []
    for key in ("address", "expression", "near", "start", "end"):
        text = node.get(key)
        if text and text != "@@" and _float_bits(text) is None:
            values.extend(expression_symbols(text))
    if node["op"] == "data":
        for value in node["values"]:
            if not value.startswith('"') and _float_bits(value) is None:
                values.extend(expression_symbols(value))
    if node["op"] == "instruction":
        text = node["text"].split(None, 1)
        for token in _operand_tokens(text[1] if len(text) == 2 else ""):
            if _SYMBOL_TOKEN.fullmatch(token) and token.casefold() not in _REGISTERS | _KEYWORDS and not re.fullmatch("[0-9A-Fa-f]+", token) and token.casefold() not in {"@f", "@b"}:
                values.append(token)
    return values


def _literal_data(node: dict) -> bool:
    return node["op"] == "data" and all(value.startswith('"') or _scalar_expression(value) for value in node["values"])


def _pure_literal_profile(program):
    """The first external-RW profile has no allocations or code emitters."""
    if program["allocations"]:
        return False
    allowed = {"scan", "scan_process", "scan_region", "define", "assert", "location",
               "label", "cursor", "register", "unregister", "data"}
    return (any(node["op"] == "data" for node in program["enable"])
            and all(node["op"] in allowed and (node["op"] != "data" or _literal_data(node))
                    for phase in ("preamble", "enable", "disable") for node in program[phase]))


def _literal_bytes(node, memory, program):
    """Independently bind each pure scalar/string emitter to its exact bytes."""
    width = {"db": 1, "dw": 2, "dd": 4, "dq": 8}[node["directive"]]
    result = bytearray()
    def scalar(ast):
        kind = ast["kind"]
        if kind == "integer":
            return ast["value"]
        if kind == "unary":
            value = scalar(ast["value"])
            return value if ast["operator"] == "+" else -value
        left, right = scalar(ast["left"]), scalar(ast["right"])
        operator = ast["operator"]
        if operator == "+": value = left + right
        elif operator == "-": value = left - right
        elif operator == "*": value = left * right
        else:
            if right == 0 or left % right:
                raise ProgramError("Literal division must be exact and nonzero.")
            value = left // right
        if abs(value) > 0xFFFFFFFFFFFFFFFF:
            raise ProgramError("Literal arithmetic overflows the bounded scalar domain.")
        return value
    for text in node["values"]:
        if text.startswith('"'):
            result.extend(text[1:-1].encode("ascii"))
        else:
            floating = _float_bits(text)
            value = floating[0] if floating else scalar(parse_expression(text))
            result.extend((value & ((1 << (width * 8)) - 1)).to_bytes(width, "little"))
    return bytes(result)


def _allocation_capabilities(nodes: list[dict], allocations: list[str]) -> tuple[dict[str, bool], dict[str, bool]]:
    """Prove data/code and writable/code profiles; uncertainty stays RWX."""
    allocated = {name.casefold(): name for name in allocations}
    labels = {symbol.casefold() for node in nodes if node["op"] == "label" for symbol in node["symbols"]}
    labels.update(node["expression"].casefold() for node in nodes if node["op"] == "cursor" and node["expression"].startswith("@"))
    seen, unsafe, aliases = set(), set(), set()
    label_owners = {}
    direct_branches = []
    anonymous_owners = []
    instruction_owners = {}
    mutable = set()
    current = None
    for index, node in enumerate(nodes):
        op = node["op"]
        if op == "cursor":
            key = node["expression"].casefold()
            if key in allocated:
                current = key
                seen.add(key)
            elif key in labels or key == "@@":
                if current is not None:
                    label_owners[key] = current
                if key == "@@":
                    anonymous_owners.append((index, current))
                continue
            else:
                aliases.update(symbol.casefold() for symbol in expression_symbols(node["expression"]) if symbol.casefold() in allocated)
                current = None
        elif op in {"instruction", "nops", "data", "readmem", "reassemble", "align", "reserve"} and current is not None:
            # A reservation is uninitialized zero padding: it never makes an
            # allocation unsafe (code) but does make it writable data.
            if op not in {"align", "reserve"} and not _literal_data(node):
                unsafe.add(current)
            if op in {"data", "readmem", "align", "reassemble", "reserve"}:
                mutable.add(current)
        if op == "instruction":
            instruction_owners[index] = current
            pieces = node["text"].split(None, 1)
            if len(pieces) == 2 and (pieces[0].casefold().startswith("j") or pieces[0].casefold() in {"call", "loop", "loope", "loopne"}) and "[" not in pieces[1]:
                direct_branches.extend((index, token.casefold()) for token in _operand_tokens(pieces[1]) if _SYMBOL_TOKEN.fullmatch(token))
    for index, target in direct_branches:
        if target in allocated:
            unsafe.add(target)
        if target in label_owners:
            unsafe.add(label_owners[target])
        if target in {"@f", "@b"}:
            if target == "@f":
                owner = next((owner for position, owner in anonymous_owners if position > index), None)
            else:
                owner = next((owner for position, owner in reversed(anonymous_owners) if position < index), None)
            if owner is not None:
                unsafe.add(owner)
    owners = {**{name: name for name in allocated}, **label_owners}
    # Defined aliases into allocations are conservative. They may be used as
    # cursors, branch targets, or destinations, so preserve both permissions.
    for node in nodes:
        if node["op"] == "define" and _float_bits(node["expression"]) is None:
            targets = {owners[symbol.casefold()] for symbol in expression_symbols(node["expression"]) if symbol.casefold() in owners}
            if targets:
                aliases.update(targets)
                mutable.update(targets)
                if len(targets) == 1:
                    owners[node["symbol"].casefold()] = next(iter(targets))
    register_aliases = {}
    for index, node in enumerate(nodes):
        if node["op"] != "instruction":
            continue
        pieces = node["text"].split(None, 1)
        mnemonic = pieces[0].casefold()
        operands = pieces[1] if len(pieces) == 2 else ""
        if mnemonic in {"lock", "rep", "repe", "repne", "repz", "repnz"}:
            nested = operands.split(None, 1)
            mnemonic, operands = nested[0].casefold(), nested[1] if len(nested) == 2 else ""
        if mnemonic not in _NO_IMPLICIT_STORES:
            owner = instruction_owners[index]
            if owner is not None:
                mutable.add(owner)
            # An unknown implicit destination can also use a register pointing
            # into another owned allocation; retain those known aliases too.
            for targets in register_aliases.values():
                mutable.update(targets)
        arguments = _args(operands) if operands else []
        if mnemonic in {"mov", "lea"} and len(arguments) == 2 and arguments[0].casefold() in _REGISTERS:
            targets = {owners[token.casefold()] for token in _operand_tokens(arguments[1]) if token.casefold() in owners}
            targets.update(register_aliases.get(arguments[1].casefold(), set()))
            if targets:
                register_aliases.setdefault(arguments[0].casefold(), set()).update(targets)
        writes_memory = bool(arguments) and "[" in arguments[0] and mnemonic not in {"cmp", "test", "bt", "lea", "push", "call"} and not mnemonic.startswith("j")
        memory_operands = arguments[:1] if writes_memory else arguments if mnemonic == "xchg" else []
        for operand in memory_operands:
            tokens = [token.casefold() for token in _operand_tokens(operand)]
            mutable.update(owners[token] for token in tokens if token in owners)
            for token in tokens:
                mutable.update(register_aliases.get(token, set()))
                if token == "@f":
                    owner = next((owner for position, owner in anonymous_owners if position > index), None)
                elif token == "@b":
                    owner = next((owner for position, owner in reversed(anonymous_owners) if position < index), None)
                else:
                    owner = None
                if owner is not None:
                    mutable.add(owner)
            if "rip" in tokens or "eip" in tokens:
                mutable.update(allocated)
        if mnemonic.startswith(("stos", "movs")):
            mutable.update(register_aliases.get("rdi", set()))
            mutable.update(register_aliases.get("edi", set()))
        if mnemonic in {"push", "call"}:
            mutable.update(register_aliases.get("rsp", set()))
            mutable.update(register_aliases.get("esp", set()))
    executable = {name: key not in seen or key in unsafe or key in aliases for key, name in allocated.items()}
    writable = {name: key not in seen or key in mutable or key in aliases or not executable[name] for key, name in allocated.items()}
    return executable, writable


def _inline_nested_invocations(pruned, nested, labels, define_lines: set) -> dict:
    """Materialize the inlined program for a nested-assembly source.

    ``pruned`` is the tested BlockPlan and ``nested`` the tested NestedPlan
    of the same source; both models already validated the label graph.
    Every label span (definition line and body) is dropped from the top
    level, and each top-level invocation line is replaced by the fully
    expanded body of the invoked label: nested invocations inside a body
    expand inline, so callees always precede their callers in the result.
    Label bodies (internal spans and external registry entries) may not
    contain ``[ENABLE]``/``[DISABLE]`` markers.

    Returns ``lines`` as (original 1-based source line, text) tuples
    (external registry lines carry the invocation site's line as context),
    ``invocations`` as plan metadata and ``external`` as the full
    normalized registry, deterministically ordered (it is stored on the
    plan so validation re-preparation reproduces identical collision and
    topological behavior).
    """
    lines = list(pruned.lines)
    line_map = pruned.line_map
    spans = {name.casefold(): (first, last)
             for name, first, last in label_spans("\n".join(lines))}
    covered = set()
    for first, last in spans.values():
        covered.update(range(first, last + 1))
    for _key, (first, last) in sorted(spans.items(), key=lambda item: item[1][0]):
        for offset in range(first, last):  # body lines, 0-based
            if lines[offset].strip().casefold() in {"[enable]", "[disable]"}:
                raise ProgramError(
                    f"Line {line_map[offset]}: nested label body may not contain a section marker.")
    registry = {}
    if labels is not None:
        for name, body in labels.items():
            registry[name.casefold()] = (name, body.replace("\r\n", "\n").replace("\r", "\n"))

    def expand(key: str, context: int) -> list[tuple[str, int]]:
        if key in spans:
            first, last = spans[key]
            body = [(lines[i], line_map[i]) for i in range(first, last)]
        else:
            entry = registry.get(key)
            if entry is None:
                # The tested resolver guarantees that every invoked label is
                # known; reaching this point means the models diverged.
                raise ProgramError(f"Nested label '{key}' has no resolvable body.")
            name, text = entry
            body_lines = text.split("\n")
            label = parse_label(body_lines[0]) if body_lines else None
            if label is not None and label.casefold() == key:
                body_lines = body_lines[1:]  # the definition line is not program content
            for line in body_lines:
                if line.strip().casefold() in {"[enable]", "[disable]"}:
                    raise ProgramError(
                        f"Line {context}: external nested label '{name}' body may not contain a section marker.")
            body = [(line, context) for line in body_lines]
        out: list[tuple[str, int]] = []
        for text, origin in body:
            called = parse_invocation(text)
            if called is None:
                out.append((text, origin))
            else:
                out.extend(expand(called.casefold(), origin))
        return out

    inv_by_line = {inv.line: inv for inv in nested.invocations if inv.line > 0}
    result: list[tuple[str, int]] = []
    for index, raw in enumerate(lines):
        number = index + 1
        if number in covered:
            continue
        inv = inv_by_line.get(number)
        if inv is None:
            result.append((raw, line_map[index]))
        else:
            result.extend(expand(inv.label.casefold(), line_map[index]))
    result = [(number, text) for text, number in result if number not in define_lines]
    invocations = [{"label": inv.label,
                    "line": line_map[inv.line - 1] if inv.line > 0 else None,
                    "depth": inv.depth} for inv in nested.invocations]
    # Store the full normalized registry (not only the used subset): plan
    # validation re-prepares from the stored registry and must reproduce the
    # identical topological order and collision behavior.
    external = {registry[key][0]: registry[key][1]
                for key in sorted(registry, key=str.casefold)}
    return {"lines": result, "invocations": invocations, "external": external}


def prepare_program(source: str, process_name: str | None = None, *, bitness: int = 64,
                    labels: dict | None = None) -> dict:
    if type(bitness) is not int or bitness not in {32, 64}:
        raise ProgramError("Only 32/64-bit programs are supported.")
    if process_name is not None:
        _expression('"' + process_name + '"')
    clean = _clean_source(source)
    defines, define_lines = {}, set()
    for index, raw in enumerate(clean.split("\n")):
        stripped = raw.strip()
        if _CONDITIONAL_DIRECTIVES["define"].fullmatch(stripped) is None:
            continue
        match = _DEFINE_DIRECTIVE.fullmatch(stripped)
        if match is None:
            raise ProgramError(f"Line {index + 1}: $define requires an identifier name and one integer literal.")
        name = match.group(1)
        key = name.casefold()
        if key in defines:
            raise ProgramError(f"Line {index + 1}: define {name} is defined more than once.")
        if len(name) > 128:
            raise ProgramError(f"Line {index + 1}: define {name} exceeds its name bound.")
        value = match.group(2)
        sign = value[:1] if value[:1] in {"+", "-"} else ""
        body = value[len(sign):]
        if body.startswith("$"):
            defines[key] = int(sign + body[1:], 16)
        elif body[:2].lower() == "0x":
            defines[key] = int(value, 16)
        else:
            defines[key] = int(value, 10)
        define_lines.add(index + 1)
    try:
        pruned = prune_conditionals(clean, defines)
    except BlockError as exc:
        raise ProgramError(str(exc)) from exc
    # Nested assembly is resolved only when a pinned autoAssemble/autoasm
    # invocation survives conditional pruning (the tested analyze_blocks
    # composition).  Every other program keeps the exact pre-wiring plan
    # shape: plain address labels may repeat between sections and carry no
    # nested-label semantics, so the resolver's single-definition rule must
    # not apply to them.
    nested_invocation_present = any(parse_invocation(line) is not None
                                    for line in pruned.lines)
    nested = None
    if nested_invocation_present:
        analysis = analyze_blocks(clean, defines, labels)
        if analysis.errors:
            # Pruning already succeeded above; the remaining errors are
            # nested-assembly refusals with lines remapped to the source.
            raise ProgramError(str(analysis.errors[0]))
        nested = analysis.nested
    if nested is not None and nested.invocations:
        inlined = _inline_nested_invocations(pruned, nested, labels, define_lines)
        prepared = inlined["lines"]
        nested_invocations = inlined["invocations"]
        nested_label_order = list(nested.order)
        external_labels = inlined["external"]
    else:
        prepared = [(number, line) for line, number
                    in zip(pruned.lines, pruned.line_map)
                    if number not in define_lines]
        nested_invocations = []
        nested_label_order = []
        external_labels = {}
    sections = {"preamble": [], "enable": [], "disable": []}
    current = "preamble"
    seen = set()
    for number, raw in prepared:
        line = raw.strip()
        if not line:
            continue
        if line.casefold() in {"[enable]", "[disable]"}:
            current = line[1:-1].casefold()
            if current in seen or current == "enable" and "disable" in seen:
                raise ProgramError("AA sections are duplicated or out of order.")
            seen.add(current)
            continue
        try:
            sections[current].append(_parse_line(line))
        except (ValueError, OverflowError) as exc:
            raise ProgramError(f"Line {number}: {exc}") from exc
        if sum(map(len, sections.values())) > MAX_NODES:
            raise ProgramError("Program contains too many operations.")
    if seen != {"enable", "disable"}:
        raise ProgramError("Program requires explicit ENABLE and DISABLE sections.")
    one_shot = not sections["disable"]
    if any(node["op"] != "define" for node in sections["preamble"]):
        raise ProgramError("Only define is permitted before ENABLE.")
    if not any(node["op"] in {"data", "instruction", "nops", "readmem", "reassemble"} for node in sections["enable"]):
        # WP-29: an allocation-only ENABLE (registersymbol + alloc, no code or
        # data) is a valid named allocation-only init profile, but only as a
        # re-enabled program with a DISABLE phase; a one-shot may never be
        # allocation-only.
        if one_shot or not any(node["op"] in {"alloc", "reserve"} for node in sections["enable"]):
            raise ProgramError("Enable section has no executable patch or data.")
    # Per-program label scoping (WP-28, CE label semantics): a bare
    # positional label ("endp:") is local to this program.  Its cursor
    # tokens are collected in a pre-pass over all three phases and resolve
    # against the program's own patch position; they are exposed via
    # positional_labels so the table compiler can re-declare them as
    # external requirements when a table-wide registered symbol of the same
    # name exists (registered symbols win over local label definitions).
    # A bare cursor that is not one of the program's own label definitions
    # keeps the classic externally-provided semantics and stays in requires.
    # Only cursors to symbols this program itself owns (scans, allocs,
    # defines, declared labels) keep the classic symbol positioning.
    # An operand-less dq/resb reservation is only admitted inside such an
    # owned region.
    alloc_keys = {node["symbol"].casefold() for node in sections["preamble"] + sections["enable"]
                  if node["op"] == "alloc"}
    declared_labels = {symbol.casefold() for node in sections["preamble"] + sections["enable"]
                       if node["op"] == "label" for symbol in node["symbols"]}
    # WP-28 two-stage label resolution: casefolded bare positional cursor
    # tokens the program itself defines, across all three phases.
    own_label_defs = {node["expression"].casefold()
                      for node in sections["preamble"] + sections["enable"] + sections["disable"]
                      if node["op"] == "cursor" and node["expression"] != "@@"
                      and _SYMBOL_TOKEN.fullmatch(node["expression"])}
    local_labels = set()
    positional_labels = set()
    locals_ = {}
    provides = {}
    allocations = []
    # Per-phase allocation context mirroring the link walk: each phase
    # starts outside any owned region, an alloc moves the position into the
    # owned region, and any cursor target other than an alloc symbol or a
    # label defined inside the allocation leaves it.
    for phase in ("preamble", "enable", "disable"):
        in_alloc = False
        for node in sections[phase]:
            if node["op"] in {"scan", "scan_region", "scan_process", "alloc", "define"}:
                symbol = node["symbol"]
                key = symbol.casefold()
                if key in locals_ and node["op"] != "define":
                    raise ProgramError(f"Duplicate program symbol: {symbol}.")
                locals_[key] = symbol
                if node["op"] == "alloc":
                    allocations.append(symbol)
                    # An allocation moves the assembly position into the owned
                    # region, so subsequent plain labels are local definitions.
                    in_alloc = True
            if node["op"] == "dealloc":
                # Mirrors the link walk: releasing the allocation leaves the
                # owned region, but the cursor position itself persists.
                in_alloc = False
            if node["op"] == "label":
                for symbol in node["symbols"]:
                    key = symbol.casefold()
                    if key in locals_:
                        raise ProgramError(f"Duplicate label or program symbol: {symbol}.")
                    locals_[key] = symbol
            if node["op"] == "register":
                for symbol in node["symbols"]:
                    provides[symbol.casefold()] = symbol
            if node["op"] == "cursor":
                expression = node["expression"]
                if expression == "@@":
                    pass
                elif expression.startswith("@"):
                    symbol = expression
                    if not _SYMBOL_TOKEN.fullmatch(symbol):
                        raise ProgramError("Named @ labels may only contain letters, digits and underscores.")
                    locals_[symbol.casefold()] = symbol
                else:
                    key = expression.casefold()
                    if _SYMBOL_TOKEN.fullmatch(expression):
                        if key in declared_labels:
                            # A declared label keeps the current region.
                            pass
                        elif key in alloc_keys or key in local_labels:
                            in_alloc = True
                        elif key in locals_:
                            # A cursor to an owned program symbol positions the
                            # classic symbol address and leaves any allocation
                            # region.
                            in_alloc = False
                        elif key in own_label_defs:
                            # A bare positional label is per-program local
                            # (WP-28): it stays put in the current region and
                            # is not an external symbol requirement at the
                            # prepare level.  The table compiler re-declares
                            # it as an external requirement when another
                            # supported record provides the same symbol,
                            # because table-wide registered symbols win over
                            # local label definitions.
                            locals_[key] = expression
                            local_labels.add(key)
                            positional_labels.add(key)
                        else:
                            # A bare label that is not one of this program's
                            # own label definitions keeps the classic
                            # externally-provided semantics, leaves any
                            # allocation region and stays in requires.
                            in_alloc = False
                    else:
                        in_alloc = False
            if node["op"] == "reserve" and not in_alloc:
                raise ProgramError("Uninitialized reservation (dq/resb) requires a program-owned allocation.")
    # Anonymous-label validation with trailing-@f fallback: an explicit @@
    # cursor always wins for forward references; a forward reference without
    # a following @@ in the same phase falls back to the next positioned
    # named label (declared label, named @ label, or plain label inside a
    # program-owned allocation) — the same located criterion the generation
    # pass applies.  @b still requires a preceding explicit @@ cursor;
    # without any resolvable target the fail-closed refusal is kept.
    program_symbol_keys = {node["symbol"].casefold()
                           for node in sections["preamble"] + sections["enable"]
                           if node["op"] in {"scan", "scan_region", "scan_process", "alloc", "define"}}
    for phase in ("enable", "disable"):
        phase_nodes = sections[phase]
        anonymous_positions = [index for index, node in enumerate(phase_nodes)
                               if node["op"] == "cursor" and node["expression"] == "@@"]
        declared_for_phase = {symbol.casefold()
                              for node in sections["preamble"] + sections["enable"] + (sections[phase] if phase == "disable" else [])
                              if node["op"] == "label" for symbol in node["symbols"]}
        named_positions = []
        in_alloc = False
        for index, node in enumerate(phase_nodes):
            if node["op"] == "alloc":
                in_alloc = True
                continue
            elif node["op"] == "dealloc":
                in_alloc = False
                continue
            elif node["op"] != "cursor" or node["expression"] == "@@":
                continue
            expression = node["expression"]
            key = expression.casefold()
            if key in declared_for_phase or expression.startswith("@"):
                named_positions.append(index)
            elif _SYMBOL_TOKEN.fullmatch(expression) and key not in program_symbol_keys:
                # WP-28: every bare positional cursor token is one of this
                # program's own label definitions (own_label_defs pre-pass),
                # hence a local named position for the @f/@b fallback.
                # Table-level provider re-declaration happens in the
                # compiler, not here.
                named_positions.append(index)
            else:
                in_alloc = key in alloc_keys
        for index, node in enumerate(phase_nodes):
            if node["op"] == "instruction":
                tokens = _operand_tokens(node["text"].split(None, 1)[1] if len(node["text"].split(None, 1)) == 2 else "")
                for token in tokens:
                    if token.casefold() == "@f" and not any(position > index for position in anonymous_positions + named_positions) or token.casefold() == "@b" and not any(position < index for position in anonymous_positions):
                        raise ProgramError("Anonymous forward/backward label has no target.")
    for key, symbol in provides.items():
        if key not in locals_:
            # Registering a dependency does not confer ownership over it.
            raise ProgramError(f"Cannot register a symbol not owned by this program: {symbol}.")
    for node in sections["disable"]:
        if node["op"] in {"alloc", "register", "scan", "scan_region", "scan_process"}:
            raise ProgramError("Disable may not allocate, scan or register new symbols.")
        if node["op"] in {"unregister", "dealloc"}:
            owned = provides if node["op"] == "unregister" else {name.casefold(): name for name in allocations}
            if node["symbols"] == ["*"]:
                node["symbols"] = list(owned.values())
            elif any(symbol.casefold() not in owned for symbol in node["symbols"]):
                raise ProgramError("Cleanup may only release symbols/allocations owned by this program.")
    if sum(node["op"] == "scan_process" for node in sections["enable"]) > MAX_PROCESS_SCANS:
        raise ProgramError("Program exceeds its 16 complete process-scan bound.")
    managed = {}
    for phase in ("preamble", "enable", "disable"):
        for node in sections[phase]:
            for key in ("address", "expression", "near", "start", "end"):
                text = node.get(key)
                if text and text != "@@" and _float_bits(text) is None:
                    for label in _managed_labels_in(text):
                        managed.setdefault(label.casefold(), label)
    required = {}
    for node in sections["preamble"] + sections["enable"] + sections["disable"]:
        for symbol in _node_refs(node):
            if symbol.casefold() not in locals_:
                required.setdefault(symbol.casefold(), symbol)
    capabilities = sorted({node["op"] for nodes in sections.values() for node in nodes})
    if len(allocations) > 128:
        raise ProgramError("Program contains more than 128 allocations.")
    estimated_bytes = 0
    for nodes in sections.values():
        for node in nodes:
            op = node["op"]
            estimated_bytes += node["count"] if op == "nops" else node["size"] if op == "readmem" else node["alignment"] - 1 if op == "align" else node["bytes"] if op == "reserve" else 15 if op == "instruction" else 64 if op == "reassemble" else sum(len(value[1:-1]) if value.startswith('"') else {"db": 1, "dw": 2, "dd": 4, "dq": 8}[node["directive"]] for value in node["values"]) if op == "data" else 0
    if estimated_bytes > MAX_TOTAL_BYTES:
        raise ProgramError("Program exceeds its total generated-byte bound.")
    allocation_executable, allocation_writable = _allocation_capabilities(sections["enable"], allocations)
    program = {"schema": SCHEMA, "bitness": bitness, "process_name": process_name, "source": source, "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(), "defines": defines, "conditional_decisions": [{"line": decision.line, "condition": decision.condition, "chosen": decision.chosen} for decision in pruned.decisions], **sections, "one_shot": one_shot, "requires": sorted(required.values(), key=str.casefold), "provides": sorted(provides.values(), key=str.casefold), "managed_method_labels": sorted(managed.values(), key=str.casefold), "allocations": allocations, "allocation_executable": allocation_executable, "allocation_writable": allocation_writable, "capabilities": capabilities, "requires_coordinator": True}
    # WP-29: a named allocation-only init profile (ENABLE carries allocs and
    # registered symbols but no code/data).  The record stays a supported
    # provider for its registered symbols; consumers resolve as usual.
    if (not any(node["op"] in {"data", "instruction", "nops", "readmem", "reassemble"}
                for node in sections["enable"])
            and any(node["op"] == "alloc" for node in sections["enable"])):
        program["allocation_only"] = True
    # WP-28: bare positional label definitions (casefolded) the table
    # compiler may re-declare as external requirements when another record
    # provides the same symbol; emitted only when non-empty.
    if positional_labels:
        program["positional_labels"] = sorted(positional_labels, key=str.casefold)
    if nested_invocations:
        program["nested_invocations"] = nested_invocations
        program["nested_label_order"] = nested_label_order
        if external_labels:
            program["external_labels"] = external_labels
    return program


def validate_program(program: dict) -> None:
    if not isinstance(program, dict) or program.get("schema") != SCHEMA or not isinstance(program.get("source"), str):
        raise ProgramError("Invalid AA program schema.")
    regenerated = prepare_program(program["source"], program.get("process_name"), bitness=program.get("bitness"),
                                  labels=program.get("external_labels"))
    try:
        actual = json.dumps(program, sort_keys=True, separators=(",", ":"), allow_nan=False)
        expected = json.dumps(regenerated, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ProgramError("AA program must contain valid JSON primitives.") from exc
    if expected != actual:
        # WP-28: the table compiler re-declares program-local positional
        # labels as external requirements when another supported record
        # provides the same symbol.  That requires superset is the only
        # tolerated metadata difference; everything else must stay
        # byte-exact (positional_labels itself is re-derived, so unforgable).
        if not _requires_redeclaration_only(program, regenerated):
            raise ProgramError("AA program metadata/operations do not match their validated source.")
        if json.dumps({key: value for key, value in program.items() if key != "requires"},
                      sort_keys=True, separators=(",", ":"), allow_nan=False) != \
           json.dumps({key: value for key, value in regenerated.items() if key != "requires"},
                      sort_keys=True, separators=(",", ":"), allow_nan=False):
            raise ProgramError("AA program metadata/operations do not match their validated source.")


def _requires_redeclaration_only(program: dict, regenerated: dict) -> bool:
    """True if the only diff between program and regenerated requires is the
    WP-28 table-level re-declaration: every regenerated requirement is still
    present, and every extra requirement is one of the program's own
    positional labels."""
    actual = program.get("requires", [])
    expected = regenerated.get("requires", [])
    remaining = {symbol.casefold(): 0 for symbol in actual}
    for symbol in actual:
        remaining[symbol.casefold()] += 1
    for symbol in expected:
        key = symbol.casefold()
        if remaining.get(key, 0) == 0:
            return False
        remaining[key] -= 1
    positional = {label.casefold() for label in program.get("positional_labels", [])}
    return all(symbol.casefold() in positional for symbol in actual if remaining[symbol.casefold()] > 0)


def _symbol_map(symbols):
    if not isinstance(symbols, Mapping) or any(not isinstance(key, str) or type(value) is not int or not 0 <= value <= 0xFFFFFFFFFFFFFFFF for key, value in symbols.items()):
        raise ProgramError("Symbol mappings require names and unsigned 64-bit integer values.")
    folded = {key.casefold(): value for key, value in symbols.items()}
    if len(folded) != len(symbols):
        raise ProgramError("Symbol mappings differ only by case.")
    return folded


def _resolve(text, memory, symbols, program):
    floating = _float_bits(text)
    return floating[0] if floating else resolve_expression(text, memory, symbols, process_name=program["process_name"], pointer_size=program["bitness"] // 8)


def preflight_program(program: dict, memory, symbols: Mapping[str, int] | None = None, *, phase: str = "enable", scan_results=None, disassembler=None, thread_model=None, protection_model=None, export_model=None, execute_side_effects: bool = True) -> dict:
    validate_program(program)
    if phase not in {"enable", "disable"}:
        raise ProgramError("Invalid AA phase.")
    resolved = _symbol_map({} if symbols is None else symbols)
    requests = []
    deferred = []
    guards = []
    captured = []
    observations = []
    last_thread = None
    nodes = program["preamble"] + program[phase]
    process_nodes = [node for node in nodes if node["op"] == "scan_process"]
    if scan_results is not None:
        if type(scan_results) is not list or len(scan_results) != len(process_nodes):
            raise ProgramError("Captured process scans differ from the selected source phase.")
        from .aob_scan import validate_result
        for result, node in zip(scan_results, process_nodes):
            validate_result(result, program["source_sha256"], node)
    for node in nodes:
        op = node["op"]
        if op == "scan":
            module = program["process_name"] if node["module"] == "$process" else node["module"]
            if module is None:
                raise ProgramError("$process requires an exact process name.")
            resolved[node["symbol"].casefold()] = memory.scan_module(module, node["pattern"])
        elif op == "scan_process":
            if type(memory.pointer_size) is not int or memory.pointer_size != program["bitness"] // 8:
                raise ProgramError("Process scan source bitness differs from the held target.")
            from .aob_scan import capture_scan, recheck_result
            if scan_results is None:
                result = capture_scan(node, program["source_sha256"], memory)
            else:
                result = scan_results[len(captured)]
                recheck_result(result, memory, program["source_sha256"], node)
            captured.append(result)
            resolved[node["symbol"].casefold()] = result["address"]
            guards.append({"address": result["address"], "bytes": result["bytes"].upper()})
        elif op == "scan_region":
            if not hasattr(memory, "scan_region"):
                raise ProgramError("The memory backend has no bounded region scanner.")
            start = _resolve(node["start"], memory, resolved, program)
            end = _resolve(node["end"], memory, resolved, program)
            resolved[node["symbol"].casefold()] = memory.scan_region(start, end, node["pattern"])
        elif op == "define":
            try:
                resolved[node["symbol"].casefold()] = _resolve(node["expression"], memory, resolved, program)
            except AddressExpressionError:
                deferred.append(node)
        elif op == "alloc":
            near = _resolve(node["near"], memory, resolved, program) if node["near"] else None
            requests.append({"name": node["symbol"], "size": node["size"], "near": near, "executable": program["allocation_executable"][node["symbol"]], "writable": program["allocation_writable"][node["symbol"]]})
        elif op == "assert":
            address = _resolve(node["address"], memory, resolved, program)
            patterns = node["pattern"].split()
            actual = memory.read(address, len(patterns))
            if len(actual) != len(patterns) or any(any(nibble != "?" and nibble != format(byte, "02X")[index] for index, nibble in enumerate(pattern)) for byte, pattern in zip(actual, patterns)):
                raise ProgramError(f"Assertion failed at 0x{address:X}.")
            guards.append({"address": address, "bytes": actual.hex().upper()})
        elif op == "disassemble":
            address = _resolve(node["address"], memory, resolved, program)
            if disassembler is None:
                raise ProgramError(
                    "disassemble requires an injected DisassemblerPort; "
                    "record activation was refused before any effect.")
            output = disassembler.disassemble(address, node["count"], program["bitness"])
            observations.append({"address": address, "count": node["count"], "output": output})
        elif op == "createthread":
            address = _resolve(node["address"], memory, resolved, program)
            if thread_model is None:
                raise ProgramError(
                    "createThread requires an injected thread backend; "
                    "record activation was refused before any effect.")
            if execute_side_effects:
                handle = thread_model.create_thread(address)
                last_thread = handle
                observations.append(thread_model.operations[-1])
        elif op == "threadwait":
            if thread_model is None:
                raise ProgramError(
                    "threadWait requires an injected thread backend; "
                    "record activation was refused before any effect.")
            if execute_side_effects:
                if last_thread is None:
                    raise ProgramError(
                        "threadWait appears before any createThread in the "
                        "selected phase.")
                observations.append(thread_model.thread_wait(last_thread))
        elif op in {"protect", "unprotect"}:
            address = _resolve(node["address"], memory, resolved, program)
            if protection_model is None:
                raise ProgramError(
                    f"{op} requires an injected protection backend; "
                    "record activation was refused before any effect.")
            if execute_side_effects:
                observations.append(getattr(protection_model, op)(address, node["size"], node["page"]))
        elif op in {"getmodulehandle", "getprocaddress"}:
            if export_model is None:
                raise ProgramError(
                    f"{op} requires an injected export backend; "
                    "record activation was refused before any effect.")
            if op == "getmodulehandle":
                observations.append(export_model.getmodulehandle(node["module"]))
            else:
                observations.append(export_model.getprocaddress(node["module"], node["export"]))
    return {"symbols": resolved, "allocation_requests": requests, "requires": program["requires"], "deferred_defines": deferred, "guards": guards, "scan_results": captured, "observations": observations}


def _translate_operands(text: str, names: dict, memory, symbols, program, backward: str | None, forward: str | None) -> str:
    typed = _FLOAT.search(text)
    if typed and "[" in text and not re.search(r"\b(?:byte|word|dword|qword)\s+(?:ptr\s+)?\[", text, re.I):
        text = text.replace("[", ("dword " if typed.group(1).casefold() == "float" else "qword ") + "[", 1)
    output = []
    for token in _operand_tokens(text):
        key = token.casefold()
        if key in {"@f", "@b"}:
            label = forward if key == "@f" else backward
            if label is None:
                raise ProgramError("Anonymous forward/backward label has no target.")
            output.append(label)
        elif key in _REGISTERS and token in names and token != key:
            # A mixed-case local label such as aL may coexist with the al
            # register in input. Register spellings retain priority otherwise.
            output.append(names[token])
        elif key in _REGISTERS | _KEYWORDS:
            output.append({"xmmword": "oword", "ymmword": "yword", "zmmword": "zword"}.get(key, key))
        elif key in names:
            output.append(names[key])
        elif token.startswith('"') or token == "$process" or "." in token:
            output.append("0x" + format(_resolve(token, memory, symbols, program), "X"))
        elif re.fullmatch(r"(?:0[xX]|\$)?[0-9a-fA-F]+|#[0-9]+", token):
            output.append("0x" + format(integer(token), "X"))
        elif _SYMBOL_TOKEN.fullmatch(token):
            raise ProgramError(f"Unresolved instruction symbol: {token}.")
        else:
            output.append(token)
    return "".join(output)


def _relocate(memory, address, destination, bitness):
    try:
        from iced_x86 import BlockEncoder, Decoder, Code
    except ImportError as exc:
        raise ProgramError("MIT iced-x86 is required for reassemble.") from exc
    # Read at most one instruction. Byte-by-byte probing avoids requiring 15
    # readable bytes when a valid instruction ends at a region boundary.
    original = bytearray()
    instruction = None
    for offset in range(15):
        data = memory.read(address + offset, 1)
        if len(data) != 1:
            raise ProgramError("Incomplete instruction read for reassemble.")
        original.extend(data)
        candidate = Decoder(bitness, bytes(original), ip=address).decode()
        if candidate.code != Code.INVALID:
            instruction = candidate
            break
    if instruction is None:
        raise ProgramError("reassemble source is not a valid bounded x86 instruction.")
    encoder = BlockEncoder(bitness)
    encoder.add(instruction)
    try:
        encoded = encoder.encode(destination)
    except ValueError as exc:
        raise ProgramError("Cannot relocate this instruction to the allocated address.") from exc
    if not encoded or len(encoded) > 64:
        raise ProgramError("Relocated instruction exceeds its size bound.")
    return encoded


def _direct_branch_target(node, names):
    if node["op"] != "instruction":
        return None
    parts = node["text"].split(None, 1)
    if len(parts) != 2 or parts[0].casefold() not in _RELATIVE_BRANCHES:
        return None
    target = re.sub(r"^(?:(?:short|near|strict|word|dword|qword)\s+)+", "", parts[1], flags=re.I).strip()
    mixed_case_label = target in names and target != target.casefold()
    if target.casefold().startswith("far ") or "[" in target or target.casefold() in _REGISTERS and not mixed_case_label:
        return None
    return target


def _check_direct_branch(data, address, expected, bitness):
    try:
        from iced_x86 import Code, Decoder, OpKind
    except ImportError as exc:
        raise ProgramError("MIT iced-x86 is required for direct branch validation.") from exc
    instruction = Decoder(bitness, data, ip=address).decode()
    if (instruction.code == Code.INVALID or instruction.len != len(data)
            or instruction.op0_kind not in {OpKind.NEAR_BRANCH16, OpKind.NEAR_BRANCH32, OpKind.NEAR_BRANCH64}
            or instruction.near_branch_target != expected):
        raise ProgramError("Encoded direct branch does not reach its source target; its displacement is out of range.")


def _memory_operands(node, names):
    if node["op"] != "instruction" or len(node["text"].split(None, 1)) != 2:
        return []
    targets, current, depth = [], [], 0
    for token in _operand_tokens(node["text"].split(None, 1)[1]):
        if token == "[":
            if depth:
                current.append(token)
            depth += 1
        elif token == "]" and depth:
            depth -= 1
            if depth:
                current.append(token)
                continue
            text = re.sub(r"^(?:(?:abs|rel|word|dword|qword)\s+)+", "", "".join(current).strip(), flags=re.I)
            text = re.sub(r"^(?:fs|gs|cs|ds|es|ss)\s*:\s*", "", text, flags=re.I)
            # Registers contribute runtime values. Their constant displacement
            # remains checkable without knowing those values. Preserve the
            # existing mixed-case local-label/register rule.
            registers = {part for part in _operand_tokens(text) if part.casefold() in _REGISTERS
                         and not (part in names and part != part.casefold())}
            parse_expression(text)
            targets.append({"expression": text, "registers": registers})
            current = []
        elif depth:
            current.append(token)
    return targets


def _located_value(text, index, anonymous, locations, memory, symbols, program, registers=(), named=()):
    output = []
    for token in _operand_tokens(text):
        if token in registers:
            output.append("0")
        elif token.casefold() == "@b":
            label = next(name for position, name in reversed(anonymous) if position < index)
            output.append("0x" + format(locations[label], "X"))
        elif token.casefold() == "@f":
            label = next((name for position, name in anonymous if position > index), None)
            if label is None:
                # Trailing-@f fallback: no explicit @@ after this reference,
                # so target the next positioned named label of the phase.
                label = next((name for position, name in named if position > index), None)
            if label is None:
                raise ProgramError("Anonymous forward label has no target.")
            output.append("0x" + format(locations[label], "X"))
        elif token.casefold() in symbols and _SYMBOL_TOKEN.fullmatch(token):
            # Compare the exact bound symbol value used by the assembler.
            output.append("0x" + format(symbols[token.casefold()], "X"))
        elif token.startswith('"') or token == "$process" or "." in token:
            output.append("0x" + format(_resolve(token, memory, symbols, program), "X"))
        else:
            output.append(token)
    expression = "".join(output)
    if not registers:
        return _resolve(expression, memory, symbols, program)

    def scalar(node):
        if node["kind"] == "integer":
            value = node["value"]
        elif node["kind"] == "unary":
            value = scalar(node["value"])
            value = value if node["operator"] == "+" else -value
        elif node["kind"] == "binary":
            left, right = scalar(node["left"]), scalar(node["right"])
            op = node["operator"]
            if op == "+":
                value = left + right
            elif op == "-":
                value = left - right
            elif op == "*":
                value = left * right
            else:
                if not right or left % right:
                    raise ProgramError("Memory displacement division must be exact and nonzero.")
                value = left // right
        else:
            raise ProgramError("A machine memory displacement must contain only registers and scalar symbols.")
        if abs(value) > 0xFFFFFFFFFFFFFFFF:
            raise ProgramError("Memory displacement arithmetic exceeds its 64-bit bound.")
        return value

    return scalar(parse_expression(expression))


def _check_memory_displacement(data, address, expected, bitness, register_dependent):
    try:
        from iced_x86 import Code, Decoder, OpKind, Register, RegisterExt
    except ImportError as exc:
        raise ProgramError("MIT iced-x86 is required for static memory displacement validation.") from exc
    instruction = Decoder(bitness, data, ip=address).decode()
    valid = (instruction.code != Code.INVALID and instruction.len == len(data)
             and any(instruction.op_kind(index) == OpKind.MEMORY for index in range(instruction.op_count)))
    if valid and register_dependent and not instruction.is_ip_rel_memory_operand:
        sizes = {RegisterExt.size(reg) for reg in (instruction.memory_base, instruction.memory_index) if reg != Register.NONE}
        width = 16 if 2 in sizes else 32 if 4 in sizes else bitness
        if abs(expected) > (1 << width) - 1:
            raise ProgramError("Encoded memory displacement exceeds the target address width.")
        actual = instruction.memory_displacement
        expected &= (1 << width) - 1
    elif valid and not register_dependent and instruction.is_ip_rel_memory_operand:
        actual = instruction.ip_rel_memory_address
    elif valid and not register_dependent and instruction.memory_base == Register.NONE and instruction.memory_index == Register.NONE:
        actual = instruction.memory_displacement
    else:
        actual = None
    if actual != expected:
        kind = "memory displacement" if register_dependent else "static memory operand"
        raise ProgramError("Encoded " + kind + " does not reach its source address; its displacement is out of range.")


class _DryReadView:
    """Only read capabilities cross the dry link's private address space."""

    def __init__(self, memory, bitness):
        self._memory = memory
        self._limit = (1 << 32) - 1 if bitness == 32 else 0x7FFFFFFFFFFF
        self._virtual = []
        self._overlay = []
        self._reserved = []
        self._modules = {}
        self._exports = {}
        self._scans = {}

    def _range(self, address, size):
        if (type(address) is not int or type(size) is not int
                or not 0 < address <= self._limit or not 0 < size <= MAX_BLOCK_BYTES
                or address + size - 1 > self._limit):
            raise ProgramError("Dry link read exceeds the target address/byte bounds.")

    def reserve(self, address, size):
        if type(address) is not int or type(size) is not int or size <= 0:
            raise ProgramError("Invalid dry link reservation.")
        if 0 < address <= self._limit:
            self._reserved.append((address, min(address + size, self._limit + 1)))

    def read(self, address, size):
        self._range(address, size)
        touching = [(start, end) for start, end in self._virtual
                    if address < end and start < address + size]
        if touching:
            if len(touching) != 1 or not touching[0][0] <= address < address + size <= touching[0][1]:
                raise ProgramError("Dry read crosses a synthetic allocation boundary.")
            data = bytearray(size)
        else:
            raw = self._memory.read(address, size)
            if type(raw) is not bytes or len(raw) != size:
                raise ProgramError("Dry link could not read every original target byte.")
            data = bytearray(raw)
            self.reserve(address, size)
        for start, raw in self._overlay:
            left, right = max(address, start), min(address + size, start + len(raw))
            if left < right:
                data[left - address:right - address] = raw[left - start:right - start]
        return bytes(data)

    def module(self, name):
        key = name.casefold()
        if key not in self._modules:
            result = self._memory.module(name)
            if (not isinstance(result, (tuple, list)) or len(result) != 2
                    or any(type(value) is not int for value in result)
                    or not 0 < result[0] <= self._limit or not 0 < result[1]
                    or result[0] + result[1] - 1 > self._limit):
                raise ProgramError("Invalid module range in dry link.")
            self._modules[key] = tuple(result)
            self.reserve(*result)
        return self._modules[key]

    def resolve_export(self, module, symbol):
        key = module.casefold(), symbol
        if key not in self._exports:
            method = getattr(self._memory, "resolve_export", None)
            if method is None:
                raise ProgramError("The memory backend has no remote PE export resolver.")
            address = method(module, symbol)
            self._range(address, 1)
            self._exports[key] = address
            self.reserve(address, MAX_BLOCK_BYTES)
        return self._exports[key]

    def scan_module(self, module, pattern):
        key = "module", module.casefold(), pattern
        if key not in self._scans:
            # Reserving the loaded image keeps private allocation placeholders
            # outside it, without querying or allocating target pages.
            self.module(module)
            address = self._memory.scan_module(module, pattern)
            self._range(address, 1)
            self._scans[key] = address
            self.reserve(address, MAX_BLOCK_BYTES)
        return self._scans[key]

    @property
    def identity(self):
        return self._memory.identity

    @property
    def pointer_size(self):
        return self._memory.pointer_size

    def is_alive(self):
        return self._memory.is_alive()

    def scan_process(self, pattern):
        key = "process", pattern
        if key not in self._scans:
            method = getattr(self._memory, "scan_process", None)
            if not callable(method):
                raise ProgramError("The memory backend has no complete process scanner.")
            address = method(pattern)
            self._range(address, 1)
            self._scans[key] = address
            self.reserve(address, MAX_BLOCK_BYTES)
        return self._scans[key]

    def scan_region(self, start, end, pattern):
        if (type(start) is not int or type(end) is not int
                or not 0 < start < end <= self._limit + 1):
            raise ProgramError("Invalid scan region in dry link.")
        key = "region", start, end, pattern
        if key not in self._scans:
            method = getattr(self._memory, "scan_region", None)
            if method is None:
                raise ProgramError("The memory backend has no bounded region scanner.")
            address = method(start, end, pattern)
            self._range(address, 1)
            self._scans[key] = address
            self.reserve(start, end - start)
        return self._scans[key]


def _dry_allocation_address(view, size, near, reference):
    """Find a private aligned gap; never claim that the target has that gap."""
    granularity, distance = 0x10000, 0x7FFF0000
    if near is not None and (type(near) is not int or not 0 < near <= view._limit):
        raise ProgramError("Dry allocation near address exceeds the target width.")
    low = max(granularity, near - distance) if near is not None else granularity
    high = min(view._limit - size + 1, near + distance) if near is not None else view._limit - size + 1
    reserved = sorted(view._reserved + view._virtual)

    def gap(start):
        candidate = (max(start, low) + granularity - 1) // granularity * granularity
        for left, right in reserved:
            if candidate + size <= left:
                break
            if candidate < right and left < candidate + size:
                candidate = (right + granularity - 1) // granularity * granularity
        return candidate if candidate <= high else None

    preferred = (near if near is not None else reference) + granularity
    address = gap(preferred) or gap(low)
    if address is None:
        raise ProgramError("No bounded synthetic near-allocation placement is available for dry linking.")
    view._virtual.append((address, address + size))
    return address


def dry_link_program(program: dict, memory, symbols: Mapping[str, int] | None = None, *,
                     owned_data_ranges=None, owned_executable_data_ranges=None, assembler=None, disassembler=None,
                     thread_model=None, protection_model=None, export_model=None) -> dict:
    """NASM-check both phases with synthetic allocations and no target writes.

    The returned schema is diagnostic and cannot be an installation receipt.
    Allocations are private, zero-filled placeholders, selected outside known
    module, cursor, symbol and read ranges. Their addresses are hypothetical:
    branch/layout success here does not prove a later target allocation, live
    scan outcome or game compatibility. The enable bytes are overlaid privately
    for disable assertions/readmem, while all real memory is accessed read-only.
    No allocate, protect, write, flush, release or close API is exposed to linking.
    """
    validate_program(program)
    if owned_data_ranges is not None and (not isinstance(owned_data_ranges, (list, tuple)) or len(owned_data_ranges) > 4096):
        raise ProgramError("Trusted data provenance must be a bounded range list.")
    if owned_executable_data_ranges is not None and (not isinstance(owned_executable_data_ranges, (list, tuple)) or len(owned_executable_data_ranges) > MAX_NODES):
        raise ProgramError("Trusted executable-data provenance must be a bounded range list.")
    view = _DryReadView(memory, program["bitness"])
    preflight = preflight_program(program, view, symbols, disassembler=disassembler,
                                  thread_model=thread_model, protection_model=protection_model,
                                  export_model=export_model, execute_side_effects=False)
    resolved = preflight["symbols"]
    for address in resolved.values():
        view.reserve(address, MAX_BLOCK_BYTES)
    external = []
    for node in program["enable"] + program["disable"]:
        texts = ([node["expression"]] if node["op"] == "cursor" else
                 [node["address"]] if node["op"] in {"assert", "disassemble", "readmem", "reassemble"} else [])
        if node["op"] == "instruction":
            text = node["text"].split(None, 1)
            texts = [token for token in _operand_tokens(text[1])
                     if token.startswith('"') or token == "$process" or "." in token] if len(text) == 2 else []
        for text in texts:
            try:
                address = _resolve(text, view, resolved, program)
            except AddressExpressionError:
                # Local allocation/label cursors acquire positions only during
                # linking. Other unresolved references still fail in the linker.
                continue
            view.reserve(address, MAX_BLOCK_BYTES)
            if node["op"] == "cursor" and 0 < address <= view._limit:
                external.append(address)
    for data_range in [] if owned_data_ranges is None else owned_data_ranges:
        if isinstance(data_range, (list, tuple)) and len(data_range) == 2 and all(type(value) is int for value in data_range):
            view.reserve(*data_range)
    for data_range in [] if owned_executable_data_ranges is None else owned_executable_data_ranges:
        if isinstance(data_range, (list, tuple)) and len(data_range) == 4 and all(type(value) is int for value in data_range):
            view.reserve(data_range[2], data_range[3])
    reference = external[0] if external else next((value for value in resolved.values()
                                                  if 0 < value <= view._limit), 0x10000000)
    allocations = {}
    for request in preflight["allocation_requests"]:
        address = _dry_allocation_address(view, request["size"], request["near"], reference)
        allocations[request["name"].casefold()] = {"address": address, "size": request["size"],
            "executable": request["executable"], "writable": request["writable"]}
    enable = link_program(program, view, symbols, allocations, assembler=assembler,
                          owned_data_ranges=owned_data_ranges,
                          owned_executable_data_ranges=owned_executable_data_ranges,
                          disassembler=disassembler,
                          thread_model=thread_model, protection_model=protection_model,
                          export_model=export_model, execute_side_effects=False)
    view._overlay = [(block["address"], bytes.fromhex(block["bytes"])) for block in enable["blocks"]]
    disable = link_program(program, view, enable["symbols"], allocations, phase="disable", assembler=assembler,
                           owned_data_ranges=owned_data_ranges,
                           owned_executable_data_ranges=owned_executable_data_ranges,
                           disassembler=disassembler,
                           thread_model=thread_model, protection_model=protection_model,
                           export_model=export_model, execute_side_effects=False)
    expected = sorted((block["address"], block["original"]) for block in enable["blocks"] if not block["is_allocation"])
    restored = sorted((block["address"], block["bytes"]) for block in disable["blocks"] if not block["is_allocation"])
    if expected != restored:
        raise ProgramError("Dry assembler disable must restore the captured original entry bytes.")
    return {"schema": "ct2trainer-aa-dry-link/v1", "dry_run": True, "publishable": False,
            "enable": enable, "disable": disable, "synthetic_allocations": allocations,
            "observations": preflight["observations"],
            "diagnostics": ["Allocations use synthetic private addresses; successful branch/layout checking does not prove actual target placement, live scan outcomes or game compatibility."]}


def link_program(program: dict, memory, symbols: Mapping[str, int] | None = None, allocations: Mapping[str, dict] | None = None, *, phase: str = "enable", assembler=None, owned_data_ranges=None, owned_executable_data_ranges=None, scan_results=None, disassembler=None, thread_model=None, protection_model=None, export_model=None, execute_side_effects: bool = False, _allow_external_literals=False) -> dict:
    """Resolve at final remote addresses, without mutation.

    owned_data_ranges is controller-only provenance for live, owned RW memory;
    it is never part of the serializable program. The controller verifies page
    protections and live allocation ownership before passing these ranges.
    owned_executable_data_ranges contains (literal_start, literal_size,
    allocation_start, allocation_size) receipts from enabled parent managers.
    Those ranges preserve executable protection and require coordinated writes.
    Neither provenance argument can be serialized into the source program.
    """
    if type(_allow_external_literals) is not bool or _allow_external_literals and phase != "enable":
        raise ProgramError("Invalid private external literal link mode.")
    preflight = preflight_program(program, memory, symbols, phase=phase, scan_results=scan_results, disassembler=disassembler,
                                  thread_model=thread_model, protection_model=protection_model,
                                  export_model=export_model, execute_side_effects=execute_side_effects)
    resolved = preflight["symbols"]
    allocations = {} if allocations is None else allocations
    owned_data_ranges = [] if owned_data_ranges is None else owned_data_ranges
    if not isinstance(owned_data_ranges, (list, tuple)) or len(owned_data_ranges) > 4096:
        raise ProgramError("Trusted data provenance must be a bounded range list.")
    for data_range in owned_data_ranges:
        if not isinstance(data_range, (list, tuple)) or len(data_range) != 2 or any(type(value) is not int for value in data_range) or not 0 < data_range[0] <= 0xFFFFFFFFFFFFFFFF or not 1 <= data_range[1] <= MAX_TOTAL_BYTES or data_range[0] + data_range[1] > 0x10000000000000000:
            raise ProgramError("Invalid trusted owned-data provenance range.")
    owned_executable_data_ranges = [] if owned_executable_data_ranges is None else owned_executable_data_ranges
    if not isinstance(owned_executable_data_ranges, (list, tuple)) or len(owned_executable_data_ranges) > MAX_NODES:
        raise ProgramError("Trusted executable-data provenance must be a bounded range list.")
    for data_range in owned_executable_data_ranges:
        if not isinstance(data_range, (list, tuple)) or len(data_range) != 4 or any(type(value) is not int for value in data_range):
            raise ProgramError("Invalid trusted executable-data provenance range.")
        start, size, allocation_start, allocation_size = data_range
        if (not 0 < start <= 0xFFFFFFFFFFFFFFFF or not 1 <= size <= MAX_BLOCK_BYTES
                or not 0 < allocation_start <= 0xFFFFFFFFFFFFFFFF or not 1 <= allocation_size <= MAX_TOTAL_BYTES
                or allocation_start + allocation_size > 0x10000000000000000
                or not allocation_start <= start < start + size <= allocation_start + allocation_size):
            raise ProgramError("Literal provenance must fit its owned executable allocation.")
    owned = {}
    for name, allocation in allocations.items():
        validate_symbol(name)
        if not isinstance(allocation, dict) or type(allocation.get("address")) is not int or type(allocation.get("size")) is not int or not 0 < allocation["address"] <= 0xFFFFFFFFFFFFFFFF or not 1 <= allocation["size"] <= MAX_BLOCK_BYTES or allocation["address"] + allocation["size"] > 0x10000000000000000:
            raise ProgramError("Invalid supplied allocation metadata.")
        key = name.casefold()
        if key not in {name.casefold() for name in program["allocations"]}:
            raise ProgramError("Allocation mapping contains a resource not owned by this program.")
        if key in owned:
            raise ProgramError("Allocation names differ only by case.")
        expected_executable = next(executable for symbol, executable in program["allocation_executable"].items() if symbol.casefold() == key)
        if "executable" in allocation and type(allocation["executable"]) is not bool:
            raise ProgramError("Allocation executable metadata must be a boolean.")
        actual_executable = allocation.get("executable", expected_executable)
        if expected_executable and not actual_executable:
            raise ProgramError("Code/unknown allocation cannot be supplied as mutable data.")
        expected_writable = next(writable for symbol, writable in program["allocation_writable"].items() if symbol.casefold() == key)
        if "writable" in allocation and type(allocation["writable"]) is not bool:
            raise ProgramError("Allocation writable metadata must be a boolean.")
        actual_writable = allocation.get("writable", expected_writable)
        if expected_writable and not actual_writable:
            raise ProgramError("Mutable allocation cannot be supplied as read-only code.")
        owned[key] = dict(allocation, executable=actual_executable, writable=actual_writable)
        resolved[key] = allocation["address"]
    allocation_ranges = sorted((allocation["address"], allocation["address"] + allocation["size"]) for allocation in owned.values())
    if any(first[1] > second[0] for first, second in zip(allocation_ranges, allocation_ranges[1:])):
        raise ProgramError("Supplied owned allocations overlap.")
    for request in preflight["allocation_requests"]:
        allocation = owned.get(request["name"].casefold())
        if allocation is None or allocation["size"] < request["size"]:
            raise ProgramError(f"Missing or undersized allocation: {request['name']}.")
        if request["near"] is not None and abs(allocation["address"] - request["near"]) > 0x7FFF0000:
            raise ProgramError("Allocation is outside the requested relative-jump range.")
    nodes = program[phase]
    declared = {symbol.casefold(): symbol for node in program["enable"] + nodes for symbol in node.get("symbols", []) if node["op"] == "label"}
    declared.update({node["expression"].casefold(): node["expression"] for node in nodes if node["op"] == "cursor" and node["expression"].startswith("@") and node["expression"] != "@@"})
    names = {name: f"tf_sym_{index}" for index, name in enumerate(sorted(set(resolved) | set(declared) | {node['symbol'].casefold() for node in preflight['deferred_defines']}))}
    names.update({spelling: names[key] for key, spelling in declared.items() if key in _REGISTERS and spelling != key})
    atom_addresses = {}
    for node in nodes + preflight["deferred_defines"]:
        texts = [node["text"].split(None, 1)[1]] if node["op"] == "instruction" and len(node["text"].split(None, 1)) == 2 else node["values"] if node["op"] == "data" else [node["expression"]] if node["op"] == "define" else []
        for text in texts:
            if node["op"] == "data" and text.startswith('"'):
                continue
            for token in _operand_tokens(text):
                if (token.startswith('"') or token == "$process" or "." in token) and token.casefold() not in names:
                    name = f"tf_atom_{len(atom_addresses)}"
                    atom_addresses[name] = _resolve(token, memory, resolved, program)
                    names[token.casefold()] = name
    alloc_keys = {name.casefold() for name in program["allocations"]}
    local_labels = set()
    in_alloc = False
    current_alloc_key = None
    sections = []
    current = None
    anonymous = []
    located = set()
    for index, node in enumerate(nodes):
        op = node["op"]
        if op == "cursor":
            expression = node["expression"]
            key = expression.casefold()
            if expression == "@@":
                if current is None:
                    raise ProgramError("Anonymous label appears before any address cursor.")
                anonymous.append((index, f"tf_anon_{index}"))
                current["nodes"].append((index, {"op": "location", "name": f"tf_anon_{index}"}))
            elif key in declared and key not in resolved:
                if current is None or key in located:
                    raise ProgramError("Local label is duplicated or has no address cursor.")
                located.add(key)
                current["nodes"].append((index, {"op": "location", "name": names[key]}))
            elif _SYMBOL_TOKEN.fullmatch(expression) and key not in resolved:
                # A bare positional label is per-program local (WP-28): it
                # binds to this program's own patch position, never to an
                # externally provided symbol.  Inside a program-owned
                # allocation the first plain label may open the section
                # without an explicit cursor; elsewhere the cursor must
                # already be positioned.
                if key in located:
                    raise ProgramError("Local label is duplicated or has no address cursor.")
                if (current is None
                        or (current_alloc_key is not None
                            and current["root_symbol"] != current_alloc_key)):
                    if current_alloc_key is None:
                        raise ProgramError("Positional label appears before any address cursor.")
                    address = _resolve(current_alloc_key, memory, resolved, program)
                    current = {"address": address, "nodes": [],
                               "root_symbol": current_alloc_key}
                    sections.append(current)
                    if len(sections) > 1024:
                        raise ProgramError("Program contains too many patch sections.")
                located.add(key)
                local_labels.add(key)
                names.setdefault(key, f"tf_sym_{len(names)}")
                current["nodes"].append((index, {"op": "location", "name": names[key]}))
            else:
                address = _resolve(expression, memory, resolved, program)
                current = {"address": address, "nodes": [], "root_symbol": key if key in resolved else None}
                in_alloc = (current["root_symbol"] is not None
                            and current["root_symbol"] in alloc_keys)
                current_alloc_key = current["root_symbol"] if in_alloc else None
                sections.append(current)
                if len(sections) > 1024:
                    raise ProgramError("Program contains too many patch sections.")
        elif op == "alloc":
            in_alloc = True
            current_alloc_key = node["symbol"].casefold()
        elif op == "dealloc":
            in_alloc = False
            current_alloc_key = None
        elif op in {"instruction", "nops", "data", "readmem", "reassemble", "align", "reserve"}:
            if current is None:
                raise ProgramError("Machine code/data appears before any address cursor.")
            current["nodes"].append((index, node))
    # Fallback targets for a forward anonymous reference without a following
    # @@: the positioned named labels of this phase (declared/named-@ labels
    # and plain labels inside program-owned allocations) in program order.
    named_labels = [(number, label_node["name"])
                    for section in sections
                    for number, label_node in section["nodes"]
                    if label_node["op"] == "location"
                    and not label_node["name"].startswith("tf_anon_")]
    if not sections:
        if phase == "enable" and not program.get("allocation_only"):
            raise ProgramError("Program has no patch sections.")
        return {"blocks": [], "literal_data_ranges": [], "symbols": dict(resolved), "exports": {}, "requires": program["requires"], "guards": preflight["guards"], "allocation_requests": [], "deallocations": [symbol for node in nodes if node["op"] == "dealloc" for symbol in node["symbols"]], "unregister": [symbol for node in nodes if node["op"] == "unregister" for symbol in node["symbols"]], "nasm_source": "", "requires_coordinator": False}
    if phase == "enable" and set(declared) - located:
        raise ProgramError("Declared labels have no position: " + ", ".join(sorted(set(declared) - located)))
    assembler = NasmAssembler() if assembler is None else assembler
    relocations = {}
    deferred_values = {}
    instruction_checks = {}
    metadata_names = ([names[key] for key in sorted(located)] + [name for _, name in anonymous]
                      + [names[node["symbol"].casefold()] for node in preflight["deferred_defines"]])
    for section in sections:
        for index, node in section["nodes"]:
            if node["op"] == "reassemble":
                metadata_names.append(f"tf_reassemble_{index}")
                relocations[index] = _relocate(memory, _resolve(node["address"], memory, resolved, program), section["address"], program["bitness"])
            elif _literal_data(node):
                metadata_names.extend((f"tf_literal_start_{index}", f"tf_literal_end_{index}"))
            elif node["op"] == "instruction":
                branch, targets = _direct_branch_target(node, names), _memory_operands(node, names)
                if branch is not None or targets:
                    instruction_checks[index] = {"branch": branch, "memory": targets}
                    metadata_names.extend((f"tf_instruction_start_{index}", f"tf_instruction_end_{index}"))
    for iteration in range(8):
        lines = [f"bits {program['bitness']}", "default rel" if program["bitness"] == 64 else "default abs"]
        scalar_defines = {node["symbol"].casefold() for node in program["preamble"] + nodes if node["op"] == "define" and _scalar_expression(node["expression"])}
        for ordinal, (key, address) in enumerate(resolved.items()):
            if key in scalar_defines:
                lines.append(f"{names[key]} equ 0x{address:X}")
            else:
                # A label in an empty virtual section retains relocation type;
                # plain equ integers cannot encode RIP-relative memory reads.
                lines.extend([f"section tf_external_{ordinal} nobits vstart=0x{address:X}", names[key] + ":"])
        for name, address in atom_addresses.items():
            lines.extend([f"section {name}_section nobits vstart=0x{address:X}", name + ":"])
        for ordinal, node in enumerate(preflight["deferred_defines"]):
            key = node["symbol"].casefold()
            if key in deferred_values:
                # Cross-section label differences may retain NASM relocation
                # type unexpectedly. After locating labels, bind the actual
                # independently evaluated value in its own virtual section.
                value = deferred_values[key]
                lines.extend([f"section tf_definition_{ordinal} nobits vstart=0x{value:X}", names[key] + ":"])
            else:
                value = _translate_operands(node["expression"], names, memory, resolved, program, None, None)
                lines.append(f"{names[key]} equ {value}")
        for ordinal, section in enumerate(sections):
            section_name = f"tf_s{ordinal}"
            follows = f" follows=tf_s{ordinal - 1}" if ordinal else " start=0"
            lines.append(f"section {section_name} progbits align=1 vstart=0x{section['address']:X}{follows}")
            lines.append(f"tf_start_{ordinal}:")
            for index, node in section["nodes"]:
                op = node["op"]
                backward = next((label for number, label in reversed(anonymous) if number < index), None)
                forward = next((label for number, label in anonymous if number > index), None)
                if forward is None:
                    forward = next((label for number, label in named_labels if number > index), None)
                if op == "location":
                    lines.append(node["name"] + ":")
                elif op == "instruction":
                    if index in instruction_checks:
                        lines.append(f"tf_instruction_start_{index}:")
                    split = node["text"].split(None, 1)
                    mnemonic = split[0].casefold()
                    operands = split[1] if len(split) == 2 else ""
                    prefix = ""
                    if mnemonic in {"lock", "rep", "repe", "repne", "repz", "repnz"}:
                        nested = operands.split(None, 1)
                        prefix, mnemonic = mnemonic + " ", nested[0].casefold()
                        operands = nested[1] if len(nested) == 2 else ""
                    if program["bitness"] == 64 and mnemonic in {"jmp", "call"} and re.match(r"far\s+", operands, re.I):
                        target = _translate_operands(re.sub(r"^far\s+", "", operands, flags=re.I), names, memory, resolved, program, backward, forward)
                        if mnemonic == "jmp":
                            lines.extend(["db 0xFF,0x25,0,0,0,0", "dq " + target])
                        else:
                            lines.extend([f"call qword [rel tf_far_pointer_{index}]", f"jmp short tf_far_after_{index}", f"tf_far_pointer_{index}:", "dq " + target, f"tf_far_after_{index}:"])
                        continue
                    if mnemonic in {"mov", "cmp", "test", "add", "sub", "and", "or", "xor", "adc", "sbb", "inc", "dec", "shl", "shr", "sal", "sar", "rol", "ror"} and operands.lstrip().startswith("[") and not _FLOAT.search(operands):
                        pieces = _args(operands)
                        if len(pieces) == 1 or len(pieces) == 2 and not any(token.strip().casefold() in _REGISTERS for token in _operand_tokens(pieces[1])):
                            # CE's unsized integer memory operand is dword.
                            operands = "dword " + operands
                    lines.append(prefix + mnemonic + " " + _translate_operands(operands, names, memory, resolved, program, backward, forward))
                    if index in instruction_checks:
                        lines.append(f"tf_instruction_end_{index}:")
                elif op == "nops":
                    lines.append(f"times {node['count']} nop")
                elif op == "data":
                    if _literal_data(node):
                        lines.append(f"tf_literal_start_{index}:")
                    values = []
                    for value in node["values"]:
                        if value.startswith('"'):
                            values.extend(f"0x{ord(char):X}" for char in value[1:-1])
                        else:
                            values.append(_translate_operands(value, names, memory, resolved, program, backward, forward))
                    lines.append(node["directive"] + " " + ",".join(values))
                    if _literal_data(node):
                        lines.append(f"tf_literal_end_{index}:")
                elif op == "align":
                    # NASM align is section-relative; AA aligns the live address.
                    lines.append(f"times ((-{section['address']} - ($ - tf_start_{ordinal})) & {node['alignment'] - 1}) db 0x{node['fill']:X}")
                elif op == "reserve":
                    lines.append(f"times {node['bytes']} db 0x0")
                elif op == "readmem":
                    address = _resolve(node["address"], memory, resolved, program)
                    data = memory.read(address, node["size"])
                    if len(data) != node["size"]:
                        raise ProgramError("readmem returned incomplete data.")
                    lines.append("db " + ",".join(f"0x{byte:02X}" for byte in data))
                elif op == "reassemble":
                    lines.append(f"tf_reassemble_{index}:")
                    lines.append("db " + ",".join(f"0x{byte:02X}" for byte in relocations[index]))
            lines.append(f"tf_end_{ordinal}:")
        lines.append(f"section tf_footer progbits align=1 vstart=0 follows=tf_s{len(sections) - 1}")
        for ordinal in range(len(sections)):
            lines.append(f"dq section.tf_s{ordinal}.start, tf_end_{ordinal}-tf_start_{ordinal}")
        if metadata_names:
            lines.append("dq " + ",".join(metadata_names))
        nasm_source = "\n".join(lines) + "\n"
        try:
            binary = assembler.assemble(nasm_source)
        except AssemblyError as exc:
            raise ProgramError(str(exc)) from exc
        count = 2 * len(sections) + len(metadata_names)
        if len(binary) < count * 8 or len(binary) > MAX_TOTAL_BYTES:
            raise ProgramError("Assembler returned an invalid or oversized binary.")
        values = struct.unpack("<" + "Q" * count, binary[-count * 8:])
        locations = dict(zip(metadata_names, values[2 * len(sections):]))
        changed = False
        definition_symbols = dict(resolved)
        definition_symbols.update({key: locations[names[key]] for key in located})
        pending = list(preflight["deferred_defines"])
        next_values = {}
        while pending:
            remaining = []
            for node in pending:
                try:
                    value = _resolve(node["expression"], memory, definition_symbols, program)
                except AddressExpressionError:
                    remaining.append(node)
                    continue
                key = node["symbol"].casefold()
                next_values[key] = definition_symbols[key] = value
            if len(remaining) == len(pending):
                raise ProgramError("Deferred definitions cannot be independently resolved at the linked labels.")
            pending = remaining
        if next_values != deferred_values:
            deferred_values = next_values
            changed = True
        for section in sections:
            for index, node in section["nodes"]:
                if node["op"] == "reassemble":
                    data = _relocate(memory, _resolve(node["address"], memory, resolved, program), locations[f"tf_reassemble_{index}"], program["bitness"])
                    if data != relocations[index]:
                        relocations[index] = data
                        changed = True
        if not changed:
            break
    else:
        raise ProgramError("Remote assembly/relocation layout did not converge.")
    linked_symbols = dict(resolved)
    linked_symbols.update({key: locations[names[key]] for key in located})
    linked_symbols.update(deferred_values)
    blocks = []
    external_candidates = []
    literal_data_ranges = []
    payload_end = len(binary) - count * 8
    ranges = []
    for ordinal, section in enumerate(sections):
        offset, size = values[ordinal * 2:ordinal * 2 + 2]
        if not size:
            continue
        address = section["address"]
        if size > MAX_BLOCK_BYTES or offset + size > payload_end or address + size > 0x10000000000000000:
            raise ProgramError("Linked patch section is out of bounds.")
        if any(address < end and address + size > start for start, end in ranges):
            raise ProgramError("Linked patch sections overlap.")
        ranges.append((address, address + size))
        containing = [(name, allocation) for name, allocation in owned.items() if allocation["address"] <= address and address + size <= allocation["address"] + allocation["size"]]
        touching = [allocation for allocation in owned.values() if address < allocation["address"] + allocation["size"] and address + size > allocation["address"]]
        if len(containing) > 1 or touching and not containing:
            raise ProgramError("Patch spans overlapping allocations or crosses an allocation boundary.")
        is_allocation = bool(containing)
        literal_data = bool(section["nodes"]) and all(node["op"] == "location" or _literal_data(node) for _, node in section["nodes"])
        trusted_data = literal_data and any(start <= address and address + size <= start + length for start, length in owned_data_ranges)
        trusted_executable_data = literal_data and any(start <= address and address + size <= start + length
                                                       for start, length, _, _ in owned_executable_data_ranges)
        # Trust comes only from controller-provided live owned RW ranges. A CT
        # cannot declare provenance, and typed bytes alone never exempt code.
        executable = containing[0][1]["executable"] if is_allocation else trusted_executable_data or not trusted_data
        block_literal_ranges = []
        source_literal_bytes = bytearray()
        for index, node in section["nodes"]:
            if index in instruction_checks:
                start, end = (locations[f"tf_instruction_{kind}_{index}"] for kind in ("start", "end"))
                if not address <= start < end <= address + size or end - start > 15:
                    raise ProgramError("Assembled instruction metadata exceeds its source block bounds.")
                data = binary[offset + start - address:offset + end - address]
                check = instruction_checks[index]
                if check["branch"] is not None:
                    target = _located_value(check["branch"], index, anonymous, locations, memory, linked_symbols, program, named=named_labels)
                    _check_direct_branch(data, start, target, program["bitness"])
                for operand in check["memory"]:
                    target = _located_value(operand["expression"], index, anonymous, locations, memory, linked_symbols, program, operand["registers"], named=named_labels)
                    _check_memory_displacement(data, start, target, program["bitness"], bool(operand["registers"]))
            if not _literal_data(node):
                continue
            start, end = locations[f"tf_literal_start_{index}"], locations[f"tf_literal_end_{index}"]
            unit = {"db": 1, "dw": 2, "dd": 4, "dq": 8}[node["directive"]]
            expected_size = unit * sum(len(value) - 2 if value.startswith('"') else 1 for value in node["values"])
            if not address <= start <= end <= address + size or end - start != expected_size:
                raise ProgramError("Assembled literal data provenance differs from its source or block bounds.")
            if _allow_external_literals and literal_data:
                expected = _literal_bytes(node, memory, program)
                emitted = binary[offset + start - address:offset + end - address]
                if emitted != expected:
                    raise ProgramError("Literal emitted bytes differ from the independently evaluated source.")
                source_literal_bytes.extend(expected)
            if is_allocation and end > start:
                record = {"address": start, "size": end - start, "allocation": containing[0][0]}
                block_literal_ranges.append(record)
                literal_data_ranges.append(dict(record))
        if _allow_external_literals and literal_data and bytes(source_literal_bytes) != binary[offset:offset + size]:
            raise ProgramError("Pure literal source does not cover every emitted block byte.")
        if _allow_external_literals and not is_allocation and any(_literal_data(node) for _, node in section["nodes"]) and not trusted_data and not trusted_executable_data:
            query = getattr(memory, "_query", None)
            if callable(query):
                region = query(address)
                if int(region.State) == 0x1000 and int(region.Protect) == 0x04:
                    external_candidates.append(len(blocks))
        original = memory.read(address, size)
        if len(original) != size:
            raise ProgramError("Could not capture every original patch byte.")
        for guard in preflight["guards"]:
            guard_bytes = bytes.fromhex(guard["bytes"])
            start, end = max(address, guard["address"]), min(address + size, guard["address"] + len(guard_bytes))
            if start < end and original[start - address:end - address] != guard_bytes[start - guard["address"]:end - guard["address"]]:
                raise ProgramError("Asserted bytes changed while linking the patch.")
        blocks.append({"address": address, "bytes": binary[offset:offset + size].hex().upper(), "original": original.hex().upper(), "is_allocation": is_allocation, "executable": executable, "literal_data": literal_data, "data_semantics": bool(not is_allocation and trusted_executable_data), "literal_data_ranges": block_literal_ranges, "requires_coordinator": executable})
    external_permits = ()
    if external_candidates:
        from .hooks import _seal_external_literals
        if len(external_candidates) != len(blocks):
            raise ProgramError("Mixed code/external-data programs need a common stronger proof profile.")
        for block in blocks:
            block["executable"] = False
            block["requires_coordinator"] = True
        external_permits = _seal_external_literals(memory, program, blocks)
    exports = {symbol: linked_symbols[symbol.casefold()] for symbol in program["provides"]} if phase == "enable" else {}
    result = {"blocks": blocks, "literal_data_ranges": literal_data_ranges, "symbols": linked_symbols, "exports": exports, "requires": program["requires"], "guards": preflight["guards"], "allocation_requests": preflight["allocation_requests"], "deallocations": [symbol for node in nodes if node["op"] == "dealloc" for symbol in node["symbols"]], "unregister": [symbol for node in nodes if node["op"] == "unregister" for symbol in node["symbols"]], "nasm_source": nasm_source, "requires_coordinator": any(block["requires_coordinator"] for block in blocks)}
    if _allow_external_literals:
        result["_external_literal_permits"] = external_permits
    return result
