#!/usr/bin/env python3
"""Scan one Auto Assembler script body statically (no execution).

Character-level state machine strips, before any token classification:
  * // line comments and ; line comments (string-aware),
  * CE { } comment blocks (nested),
  * C-style /* */ comments (possibly multi-line),
  * {$if}...{$endif} conditional blocks (flagged, content skipped),
  * {$lua}...{$asm} blocks (kept, classified only for CE Lua API names).
Remaining statement-leading tokens are classified against corpus_lib sets.
Everything is a syntax assumption, never a behavioral proof.
"""
import re
from collections import Counter
try:
    from .lib import (
        SUPPORTED_AA_DIRECTIVES, LOCKED_AA_DIRECTIVES, KNOWN_INSTRUCTION_TOKENS,
        LUA_API_GAPS, LUA_OPEN, LUA_CLOSE, BLOCK_IF, BLOCK_ENDIF,
        ENABLE_RE, DISABLE_RE, REG64, SIMD, REG32,
    )
except ImportError:
    from lib import (
        SUPPORTED_AA_DIRECTIVES, LOCKED_AA_DIRECTIVES, KNOWN_INSTRUCTION_TOKENS,
        LUA_API_GAPS, LUA_OPEN, LUA_CLOSE, BLOCK_IF, BLOCK_ENDIF,
        ENABLE_RE, DISABLE_RE, REG64, SIMD, REG32,
    )

_LABEL_DEF = re.compile(r"^[A-Za-z_][\w:.]*(\+[0-9A-Fa-f]+)?\s*:$")
_STMT = re.compile(r"^([A-Za-z_][\w]*)")
_MODREF = re.compile(r"[\w\-]+?\.(?:exe|dll)", re.I)


def _iter_code_lines(text):
    """Yield (kind, line) with kind in {'aa', 'lua'}; all comments removed."""
    state = "aa"  # aa | brace | lua | cond | c
    depth = 0
    for raw in (text or "").splitlines():
        i = 0
        n = len(raw)
        buf = []
        while i < n:
            c = raw[i]
            if state == "c":
                if c == "*" and i + 1 < n and raw[i + 1] == "/":
                    state = "aa"
                    i += 2
                    continue
                i += 1
                continue
            if state == "brace":
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth <= 0:
                        state = "aa"
                i += 1
                continue
            if state == "lua":
                m = LUA_CLOSE.search(raw, i)
                if m:
                    if i < m.start():
                        yield "lua", raw[i:m.start()]
                    state = "aa"
                    i = m.end()
                    continue
                if i < n:
                    yield "lua", raw[i:]
                break
            if state == "cond":
                m = BLOCK_ENDIF.search(raw, i)
                if m:
                    state = "aa"
                    i = m.end()
                    continue
                break
            # state == "aa"
            if c == "/" and i + 1 < n and raw[i + 1] == "/":
                break
            if c == ";" and (i == 0 or raw[i - 1] in " \t"):
                break
            if c == "{":
                m = LUA_OPEN.match(raw, i)
                if m:
                    state = "lua"
                    i = m.end()
                    continue
                m = BLOCK_IF.match(raw, i)
                if m:
                    state = "cond"
                    i = m.end()
                    continue
                state = "brace"
                depth = 1
                i += 1
                continue
            if c == "*" and i > 0 and raw[i - 1] == "/":
                state = "c"
                i += 1
                continue
            buf.append(c)
            i += 1
        if state == "aa" and "".join(buf).strip():
            yield "aa", "".join(buf).strip()


def scan_aa(text: str) -> dict:
    directives = Counter()
    locked = Counter()
    unknown = Counter()
    lua_gaps = Counter()
    modules = set()
    instr64 = instr32 = 0
    had_lua = False
    has_conditional = len(BLOCK_IF.findall(text or "")) > 0
    method_labels = set()
    globalalloc_symbols = []
    globalalloc_general = False

    for kind, line in _iter_code_lines(text):
        if kind == "lua":
            if line.strip():
                had_lua = True
            for pattern, gap in LUA_API_GAPS:
                if pattern.search(line):
                    lua_gaps[gap] += 1
            continue
        if _LABEL_DEF.match(line):
            base = line[:-1] if line.endswith(":") else line
            base = re.sub(r"\+[0-9A-Fa-f]+$", "", base)
            name = re.sub(r"\.(?:exe|dll)$", "", base, flags=re.I)
            if "." in name or ":" in name:
                method_labels.add(base)
            continue
        m = _STMT.match(line)
        if not m:
            continue
        tok = m.group(1).lower()
        if tok in LOCKED_AA_DIRECTIVES:
            locked[LOCKED_AA_DIRECTIVES[tok]] += 1
        elif tok not in SUPPORTED_AA_DIRECTIVES and tok not in KNOWN_INSTRUCTION_TOKENS:
            unknown[tok] += 1
        else:
            directives[tok] += 1
        if tok == "globalalloc" and not globalalloc_general:
            m2 = re.match(r"globalalloc\s*\(\s*([A-Za-z_]\w*)", line, re.I)
            if m2:
                globalalloc_symbols.append(m2.group(1).lower())
        elif globalalloc_symbols and tok not in (
                "db", "dw", "dd", "dq", "define", "label", "alloc",
                "registersymbol", "unregistersymbol"):
            for gs in globalalloc_symbols:
                if re.search(r"\b" + re.escape(gs) + r"\b", line, re.I):
                    locked["aa_globalalloc_general"] += 1
                    globalalloc_general = True
                    break
        for mod in _MODREF.findall(line):
            modules.add(mod.lower())
        # CE `luacall(...)` arguments are Lua: API names there need the host.
        for pattern, gap in LUA_API_GAPS:
            if pattern.search(line):
                lua_gaps[gap] += 1
        # Only 64-bit registers / qword are 64-bit-exclusive signals.
        # SSE (movss/movsd/...) exists in both x86 and x64 code and must not
        # count; 32-bit registers and dword are also valid in x64 code, so
        # instr32_lines is informational only, never an architecture signal.
        if REG64.search(line) or re.search(r"\bqword\b", line, re.I):
            instr64 += 1
        if REG32.search(line) or re.search(r"\bdword\b", line, re.I):
            instr32 += 1

    script = text or ""
    has_enable = bool(ENABLE_RE.search(script))
    has_disable = bool(DISABLE_RE.search(script))
    empty_disable = not has_disable
    if has_disable:
        body = script[DISABLE_RE.search(script).end():]
        empty_disable = not any(
            line.strip() for kind, line in _iter_code_lines(body)
        )

    return {
        "directives": dict(directives),
        "locked": dict(locked),
        "unknown": dict(unknown),
        "lua_gaps": dict(lua_gaps),
        "modules": sorted(modules),
        "method_labels": sorted(method_labels),
        "instr64_lines": instr64,
        "instr32_lines": instr32,
        "had_lua": had_lua,
        "has_conditional": has_conditional,
        "has_enable": has_enable,
        "has_disable": has_disable,
        "empty_disable": empty_disable,
    }
