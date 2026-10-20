"""Canonical owned profile for explicit or phase/EOF-ended CT Lua sections.

Preparation and validation are entirely static. This lexer recognizes language
boundaries, not Lua semantics. Ordinary AA is delegated to the independently
authored AA grammar. Returned Lua text is AA text, never recursively executed.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any

from .aa_program import ProgramError, prepare_program, _CONDITIONAL_DIRECTIVES, _NOOP_DIRECTIVES


SCHEMA = 'ct2trainer-lua-program/v1'
MAX_SOURCE_BYTES = 1024 * 1024
MAX_LUA_CHUNKS = 64
MAX_SOURCE_LINES = 65536
_MODE = re.compile(r'\s*\{\$(lua|asm)\}\s*\Z', re.I)
_PHASE = re.compile(r'\[(ENABLE|DISABLE)\]\Z', re.I)
_LONG_OPEN = re.compile(r'\[(=*)\[')
_LUA_CALL = re.compile(r'luacall(?=\s|\(|\Z)', re.I)


class LuaProgramError(ValueError):
    """Malformed, forged or out-of-profile source, with no source execution."""


class AutoAssembleProofError(LuaProgramError):
    """A non-executable static envelope whose autoAssemble proof fails (WP-51)."""


AUTOASSEMBLE_PROOF_SCHEMA = 'ct2trainer-autoassemble-proof/v1'
_NO_CONTENT_REASON = 'Enable section has no executable patch or data.'
_MAX_PROOF_BODIES = 128
_PROOF_ESCAPES = {'\\\\': '\\', '\\"': '"', "\\'": "'", '\\n': '\n', '\\t': '\t', '\\r': '\r'}
_PROOF_IDENT = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
_UNPROVABLE = 'Auto-assembled program body is not statically provable.'


def _bounded_source(source: Any) -> str:
    if not isinstance(source, str):
        raise LuaProgramError('Lua program source must be text')
    try:
        size = len(source.encode('utf-8'))
    except UnicodeError as exc:
        raise LuaProgramError('Lua program source must be valid UTF-8 text') from exc
    source = source.replace('\r\n', '\n').replace('\r', '\n')
    if size > MAX_SOURCE_BYTES or source.count('\n') >= MAX_SOURCE_LINES:
        raise LuaProgramError('Lua program source exceeds its size/line bound')
    return source


class _LuaLex:
    """Lua53 lexical state sufficient to protect standalone mode markers."""

    def __init__(self):
        self.quote: str | None = None
        self.long_close: str | None = None
        self.z_space = False

    @property
    def neutral(self) -> bool:
        return self.quote is None and self.long_close is None

    def line(self, text: str) -> None:
        index = 0
        while index < len(text):
            if self.long_close is not None:
                end = text.find(self.long_close, index)
                if end < 0:
                    return
                index = end + len(self.long_close)
                self.long_close = None
                continue
            char = text[index]
            if self.quote is not None:
                if self.z_space:
                    if char.isspace():
                        index += 1
                        continue
                    self.z_space = False
                if char == '\\':
                    if index + 1 < len(text):
                        self.z_space = text[index + 1] == 'z'
                        index += 2
                        continue
                elif char == self.quote:
                    self.quote = None
                elif char == '\n':
                    raise LuaProgramError('Unescaped newline in a Lua quoted string')
                index += 1
                continue
            if char in {'"', "'"}:
                self.quote = char
                index += 1
                continue
            if text.startswith('--', index):
                opener = _LONG_OPEN.match(text, index + 2)
                if opener is None:
                    return
                self.long_close = ']' + opener.group(1) + ']'
                index = opener.end()
                continue
            opener = _LONG_OPEN.match(text, index) if char == '[' else None
            if opener is not None:
                self.long_close = ']' + opener.group(1) + ']'
                index = opener.end()
                continue
            index += 1


class _AALex:
    """The AA comment/string rules, preserving only visible code."""

    def __init__(self):
        self.block: str | None = None
        self.quote = False

    @property
    def neutral(self) -> bool:
        return self.block is None and not self.quote

    def line(self, text: str, *, allow_lua_call: bool = False) -> str:
        output, index, visible_started = [], 0, False
        while index < len(text):
            pair, char = text[index:index + 2], text[index]
            if self.block is not None:
                if self.block == 'brace' and char == '}':
                    self.block = None
                elif self.block == 'c' and pair == '*/':
                    self.block = None
                    index += 1
                output.append(' ')
            elif char == '"':
                self.quote = not self.quote
                output.append(char)
                visible_started = True
            elif not self.quote and pair == '//':
                break
            elif not self.quote and pair == '/*':
                self.block = 'c'
                output.append(' ')
                index += 1
            elif not self.quote and pair == '*/':
                raise LuaProgramError('Unmatched AA block comment terminator')
            elif (allow_lua_call and not self.quote and not visible_started
                  and _LUA_CALL.match(text, index) is not None):
                # Preserve the Lua grammar inside the wrapper. AA comment rules
                # cannot safely lex Lua quoted strings, tables or long strings.
                return text[index:].strip()
            elif not self.quote and pair == '{$':
                end = text.find('}', index)
                token = text[index:end + 1].strip() if end > index else None
                if token is None:
                    raise LuaProgramError('Lua/ASM delimiters must occupy standalone lines')
                if any(pattern.fullmatch(token) for pattern in _CONDITIONAL_DIRECTIVES.values()):
                    output.append(token)
                    visible_started = True
                elif token.casefold() not in _NOOP_DIRECTIVES:
                    raise LuaProgramError('Non-profile {$...} directive: ' + token[2:-1].strip())
                index = end + 1
                continue
            elif not self.quote and char == '{':
                self.block = 'brace'
                output.append(' ')
            elif not self.quote and char == '}':
                raise LuaProgramError('Unmatched AA brace comment terminator')
            else:
                output.append(char)
                visible_started = visible_started or not char.isspace()
            index += 1
        return ''.join(output).strip()

    def finish(self) -> None:
        if self.block is not None or self.quote:
            raise LuaProgramError('Unterminated AA comment or quoted string')


def _lua_call_source(text: str, aa: _AALex) -> str:
    """Extract one documented single-line luaCall script, without executing it.

    Parentheses inside Lua quotes/long strings/comments do not close the AA
    wrapper. Trailing text must be an AA comment, processed in the same lexer
    so a multiline trailing comment keeps shielding following AA lines.
    Public syntax: https://wiki.cheatengine.org/index.php?title=Auto_Assembler:luaCall
    """
    command = _LUA_CALL.match(text)
    index = command.end() if command is not None else 0
    while index < len(text) and text[index].isspace():
        index += 1
    if command is None or index >= len(text) or text[index] != '(':
        raise LuaProgramError('luaCall requires a parenthesized single-line Lua script')
    start, depth, quote, long_close = index + 1, 1, None, None
    index += 1
    while index < len(text):
        if long_close is not None:
            end = text.find(long_close, index)
            if end < 0:
                break
            index, long_close = end + len(long_close), None
            continue
        char = text[index]
        if quote is not None:
            if char == '\\':
                index += 2
                continue
            if char == quote:
                quote = None
            index += 1
            continue
        if char in {'"', "'"}:
            quote = char
        elif text.startswith('--', index):
            opener = _LONG_OPEN.match(text, index + 2)
            if opener is None:
                break  # A single-line Lua comment hides the wrapper's close.
            long_close, index = ']' + opener.group(1) + ']', opener.end()
            continue
        elif char == '[' and (opener := _LONG_OPEN.match(text, index)) is not None:
            long_close, index = ']' + opener.group(1) + ']', opener.end()
            continue
        elif char == '(':
            depth += 1
            if depth > 64:
                raise LuaProgramError('luaCall parentheses exceed the nesting bound')
        elif char == ')':
            depth -= 1
            if depth == 0:
                body = text[start:index].strip()
                if not body:
                    raise LuaProgramError('luaCall requires nonempty Lua code')
                if aa.line(text[index + 1:]):
                    raise LuaProgramError('luaCall must occupy its own AA command line')
                return body
        index += 1
    raise LuaProgramError('Unterminated luaCall parentheses, Lua string or comment')


def _lua_non_code_spans(text: str) -> list[tuple[int, int]]:
    """Half-open [start, end) intervals of Lua string/comment text.

    Quoted strings honor backslash escapes, long strings honor any ``=``
    level, line comments end at the newline, and ``--[=]*[`` opens a block
    comment with the matching ``]=]*``.  Everything outside these spans is
    code; unterminated strings/comments extend to the end of the text.
    """
    spans: list[tuple[int, int]] = []
    index, length = 0, len(text)
    quote: str | None = None
    quote_start = 0
    long_level: str | None = None
    long_start = 0
    while index < length:
        if long_level is not None:
            close = ']' + long_level + ']'
            end = text.find(close, index)
            if end < 0:
                spans.append((long_start, length))
                break
            spans.append((long_start, end + len(close)))
            index = end + len(close)
            long_level = None
            continue
        char = text[index]
        if quote is not None:
            if char == '\\' and index + 1 < length:
                index += 2
                continue
            if char == quote:
                spans.append((quote_start, index + 1))
                quote = None
            index += 1
            continue
        if char in {'"', "'"}:
            quote, quote_start = char, index
            index += 1
            continue
        if text.startswith('--', index):
            opener = _LONG_OPEN.match(text, index + 2)
            if opener is None:
                newline = text.find('\n', index)
                spans.append((index, length if newline < 0 else newline))
                index = length if newline < 0 else newline + 1
            else:
                long_level, long_start = opener.group(1), index
                index = opener.end()
            continue
        if char == '[' and (opener := _LONG_OPEN.match(text, index)) is not None:
            long_level, long_start = opener.group(1), index
            index = opener.end()
            continue
        index += 1
    if quote is not None:
        spans.append((quote_start, length))
    return spans


def _code_mask(text: str) -> bytearray:
    """One per text position; nonzero exactly at code positions."""
    mask = bytearray(b'\x01') * len(text)
    for start, end in _lua_non_code_spans(text):
        mask[start:end] = b'\x00' * (end - start)
    return mask


def _code_view(text: str, mask: bytearray) -> str:
    """Raw text with non-code characters NULed, newlines preserved."""
    chars = list(text)
    for i in range(len(text)):
        if not mask[i] and text[i] != '\n':
            chars[i] = '\x00'
    return ''.join(chars)


def _block_depth_at(view: str, position: int) -> int:
    """End-block nesting depth at position: function/then/do open, end closes.

    ``elseif ... then`` shares the enclosing ``if`` block (one ``end``), so
    its ``then`` reopens nothing.  The rare unpaired corner cases fail
    closed, never widening the proven scope.
    """
    depth, index, length = 0, 0, len(view)
    pending_elseif = False
    while index < length and index < position:
        char = view[index]
        if char in ' \t\n\x00':
            index += 1
            continue
        token = _PROOF_IDENT.match(view, index)
        if token is None:
            index += 1
            continue
        word = token.group()
        index += len(word)
        if word == 'elseif':
            pending_elseif = True
        elif word == 'then':
            if not pending_elseif:
                depth += 1
            pending_elseif = False
        elif word in {'function', 'do'}:
            depth += 1
        elif word == 'end':
            depth = max(0, depth - 1)
            pending_elseif = False
    return depth


def _auto_assemble_call_positions(text: str, mask: bytearray) -> list[tuple[int, int]]:
    """(name index, first-argument index) pairs of code-context calls.

    Only the bare global spelling counts: a preceding identifier character,
    ``.`` or ``:`` belongs to a member call and is not the CE global.
    """
    positions: list[tuple[int, int]] = []
    index = 0
    length = len(text)
    while True:
        index = text.find('autoAssemble', index)
        if index < 0:
            break
        after = index + len('autoAssemble')
        before = text[index - 1] if index else ''
        if index == 0 or (not before.isalnum() and before not in '_.:'):
            j = after
            while j < length and text[j] in ' \t':
                j += 1
            if j < length and text[j] == '(' and mask[index] and mask[j]:
                positions.append((index, j + 1))
        index = after
    return positions


def _proof_literal(text: str, index: int, mask: bytearray) -> tuple[str, int]:
    """Parse one code-context string literal (quoted or long) at index.

    Quoted strings accept exactly the pinned escape set; any other escape,
    an unescaped newline or an unterminated literal refuses the proof.
    """
    length = len(text)
    while index < length and text[index] in ' \t\r\n':
        index += 1
    if index >= length:
        raise AutoAssembleProofError(_UNPROVABLE)
    char = text[index]
    if char in {'"', "'"}:
        index += 1
        chars: list[str] = []
        while index < length:
            c = text[index]
            if c == '\\' and index + 1 < length:
                escape = text[index:index + 2]
                if escape not in _PROOF_ESCAPES:
                    raise AutoAssembleProofError(_UNPROVABLE)
                chars.append(_PROOF_ESCAPES[escape])
                index += 2
                continue
            if c == char:
                return ''.join(chars), index + 1
            if c == '\n':
                raise AutoAssembleProofError(_UNPROVABLE)
            chars.append(c)
            index += 1
        raise AutoAssembleProofError(_UNPROVABLE)
    if char == '[' and (opener := _LONG_OPEN.match(text, index)) is not None:
        close = ']' + opener.group(1) + ']'
        end = text.find(close, opener.end())
        if end < 0:
            raise AutoAssembleProofError(_UNPROVABLE)
        return text[opener.end():end], end + len(close)
    raise AutoAssembleProofError(_UNPROVABLE)


def _literal_chain(text: str, view: str, mask: bytearray, start: int) -> str:
    """A ``..``-concatenated chain of string literals, statement-terminated."""
    value, index = _proof_literal(text, start, mask)
    length = len(text)
    while True:
        j = index
        while j < length and text[j] in ' \t\r\n':
            j += 1
        if j < length and view[j:j + 2] == '..' and not (j + 2 < length and view[j + 2] == '.'):
            piece, index = _proof_literal(text, j + 2, mask)
            value += piece
        else:
            break
    k = index
    while k < length and text[k] in ' \t':
        k += 1
    if k < length and text[k] not in '\n;' and text[k:k + 2] != '--':
        raise AutoAssembleProofError(_UNPROVABLE)
    return value


def _assigned_literal_chain(text: str, view: str, mask: bytearray, name: str,
                            call_index: int, call_depth: int) -> str:
    """Single-level indirection: the last statement assignment of ``name``
    before the call whose block scope still encloses it and whose right-hand
    side is a literal concatenation chain.  Multi-assign, member and out-of-
    scope assignments stay unprovable (fail-closed).
    """
    pattern = re.compile(r'(?:\blocal\s+|(?<![A-Za-z0-9_.:\x00]))' + re.escape(name) + r'\s*=(?!=)')
    candidates = [match for match in pattern.finditer(view, 0, call_index)
                  if match.group().startswith('local') or _statement_start(view, match.start())]
    for match in reversed(candidates):
        if _block_depth_at(view, match.start()) == call_depth:
            return _literal_chain(text, view, mask, match.end())
    raise AutoAssembleProofError(_UNPROVABLE)


def _statement_start(view: str, index: int) -> bool:
    j = index - 1
    while j >= 0 and view[j] in ' \t':
        j -= 1
    return j < 0 or view[j] in '\n;('


def _proof_first_argument(text: str, mask: bytearray, view: str, start: int,
                          call_depth: int) -> tuple[str, str | None]:
    """Classify one autoAssemble first argument.

    ``nil`` is a retire call (``'retire', None``); a quoted literal, a long
    string, or an identifier bound earlier to a literal concatenation chain
    proves the body; anything else refuses with the named reason.
    """
    index = start
    length = len(text)
    while index < length and text[index] in ' \t\r\n':
        index += 1
    if index >= length:
        raise AutoAssembleProofError(_UNPROVABLE)
    if (text[index:index + 3] == 'nil'
            and (index + 3 >= length or not (text[index + 3].isalnum() or text[index + 3] == '_'))):
        return ('retire', None)
    char = text[index]
    if char in {'"', "'"} or (char == '[' and _LONG_OPEN.match(text, index) is not None):
        return ('body', _proof_literal(text, index, mask)[0])
    if char.isalpha() or char == '_':
        ident = _PROOF_IDENT.match(text, index)
        if ident is None:
            raise AutoAssembleProofError(_UNPROVABLE)
        return ('body', _assigned_literal_chain(text, view, mask, ident.group(),
                                                index, call_depth))
    raise AutoAssembleProofError(_UNPROVABLE)


def _auto_assemble_proof(parts: list[_Part], process_name: str, bitness: int):
    """WP-51: prove the enable Lua's autoAssemble bodies, statically.

    Scans exactly the enable-attributed chunks: every enable-phase Lua part,
    with the shared preamble folded in the same way ``phase_expansion`` folds
    it.  A ``nil`` first argument is a retire call and is ignored.  Returns
    the proof report when at least one body is proven, ``None`` when the
    record carries no autoAssemble call at all, and raises
    ``AutoAssembleProofError`` with a named reason when a present body cannot
    be proven.  Raw bodies never leave the report: only their SHA-256 and
    byte count do.  Symbols/requires come from a plain ``prepare_program`` of
    each body without ``external_owned`` so validation regeneration matches;
    a body that fails static preparation contributes no symbols and does not
    block admission (the record stays admitted, its consumers keep the
    existing named provider refusal).
    """
    common = '\n'.join(part.text for part in parts
                       if part.kind == 'lua' and part.phase == 'preamble' and part.shared)
    calls: list[dict] = []
    bodies: dict[str, str] = {}
    for part in parts:
        if part.kind != 'lua' or part.phase not in {'preamble', 'enable'}:
            continue
        if part.phase == 'preamble' and not part.shared:
            continue
        chunk = common + '\n' + part.text if part.shared and part.phase != 'preamble' else part.text
        if not chunk.strip():
            continue
        mask = _code_mask(chunk)
        view = _code_view(chunk, mask)
        for name_index, arg_index in _auto_assemble_call_positions(chunk, mask):
            verdict, value = _proof_first_argument(
                chunk, mask, view, arg_index, _block_depth_at(view, name_index))
            if verdict == 'retire':
                continue
            body = value
            if not body:
                raise AutoAssembleProofError('Auto-assembled program body is empty.')
            size = len(body.encode('utf-8'))
            if size > MAX_SOURCE_BYTES:
                raise AutoAssembleProofError('Auto-assembled program body exceeds its size bound.')
            if len(calls) >= _MAX_PROOF_BODIES:
                raise AutoAssembleProofError('Auto-assembled program call count exceeds its bound.')
            digest = hashlib.sha256(body.encode('utf-8')).hexdigest()
            calls.append({'body_sha256': digest, 'body_bytes': size})
            bodies[digest] = body
    if not calls:
        return None
    body_symbols: set[str] = set()
    body_requires: set[str] = set()
    for body in bodies.values():
        try:
            body_program = prepare_program(body, process_name, bitness=bitness)
        except ProgramError:
            continue
        body_symbols.update(body_program['provides'])
        body_requires.update(body_program['requires'])
    return {'schema': AUTOASSEMBLE_PROOF_SCHEMA, 'calls': calls,
            'body_symbols': sorted(body_symbols, key=str.casefold),
            'body_requires': sorted(body_requires, key=str.casefold)}


def has_lua_sections(source: str) -> bool:
    """Route standalone Lua openers or luaCall without validating AA operations.

    Phase headers/order and ordinary AA validity belong to the chosen compiler.
    Inert marker text in AA comments or quoted strings is ignored. Lexical or
    size errors can raise ``LuaProgramError``; no source is ever executed.
    """
    source = _bounded_source(source)
    aa = _AALex()
    for line in source.split('\n'):
        marker = _MODE.fullmatch(line)
        if aa.neutral and marker is not None and marker.group(1).casefold() == 'lua':
            return True
        was_quoted = aa.quote
        visible = aa.line(line, allow_lua_call=True)
        if not was_quoted and _LUA_CALL.match(visible) is not None:
            return True
    return False


@dataclass(frozen=True)
class _Part:
    kind: str
    phase: str
    text: str
    call: bool = False
    shared: bool = False


def _explicit_lua_end(lines: list[str], start: int) -> bool:
    """Preserve existing explicitly closed chunks; never execute their text.

    In-block [ENABLE]/[DISABLE] phase markers are structural boundaries, not
    part of this look-ahead (WP-26). A new neutral Lua opener terminates this
    look-ahead: it can belong to the next open-ended phase, not this one.
    At most 64 bounded chunks each inspect a <=1 MiB source.
    """
    lex = _LuaLex()
    for line in lines[start:]:
        marker = _MODE.fullmatch(line)
        if lex.neutral and marker is not None:
            return marker.group(1).casefold() == 'asm'
        lex.line(line + '\n')
    return False


def _parse(source: str) -> tuple[list[_Part], str, bool]:
    source = _bounded_source(source)
    if len(source.split('\n')) > MAX_SOURCE_LINES:
        raise LuaProgramError('Lua program source exceeds its line bound')
    parts: list[_Part] = []
    aa = _AALex()
    lua: _LuaLex | None = None
    body: list[str] = []
    phase, seen, chunks, static_body = 'preamble', [], 0, False
    common_lua, implicit_lua, inherited_lua, shared_lua = False, False, False, False
    lines = source.split('\n')
    for line_index, line in enumerate(lines):
        marker = _MODE.fullmatch(line)
        if lua is not None:
            header = _PHASE.fullmatch(line.strip()) if lua.neutral else None
            if header is not None:
                next_phase = header.group(1).casefold()
                fresh = (next_phase not in seen
                         and (next_phase == 'enable' or seen == ['enable']))
                if not fresh and not implicit_lua:
                    # WP-26: an explicitly closed chunk keeps its legacy
                    # contract - a phase-appearing line that is not a fresh
                    # transition (duplicate or out of order) stays Lua body
                    # text; open-ended chunks keep the structural
                    # recognition so such markers stay fail-closed there.
                    header = None
            if header is not None:
                if next_phase in seen or next_phase == 'disable' and seen != ['enable']:
                    raise LuaProgramError('Lua program phases are duplicated or out of order')
                parts.append(_Part('lua', phase, '\n'.join(body), shared=shared_lua or phase == 'preamble'))
                if phase == 'preamble':
                    common_lua = True
                phase = next_phase
                seen.append(phase)
                parts.append(_Part('phase', phase, '[' + phase.upper() + ']'))
                body = []
                if common_lua:
                    chunks += 1
                    if chunks > MAX_LUA_CHUNKS:
                        raise LuaProgramError('Lua program contains too many Lua sections')
                    # WP-26: an in-block phase marker is structural in both
                    # open-ended and explicitly closed chunks.  The chunk keeps
                    # its own end rule (implicit_lua stays as found); its Lua
                    # stays shared so the preamble folds into every phase.
                    lua, implicit_lua, inherited_lua, shared_lua = _LuaLex(), implicit_lua, True, True
                else:
                    lua, implicit_lua, inherited_lua, shared_lua = None, False, False, False
                continue
            if lua.neutral and marker is not None:
                if marker.group(1).casefold() == 'lua':
                    if not inherited_lua or any(item.strip() for item in body):
                        raise LuaProgramError('Nested Lua section')
                    # A phase may explicitly restate an inherited common mode.
                    implicit_lua = not _explicit_lua_end(lines, line_index + 1)
                    inherited_lua, body = False, []
                    continue
                parts.append(_Part('lua', phase, '\n'.join(body), shared=shared_lua or phase == 'preamble' and implicit_lua))
                lua, body, implicit_lua, inherited_lua, shared_lua = None, [], False, False, False
                continue
            body.append(line)
            lua.line(line + '\n')
            inherited_lua = inherited_lua and not line.strip()
            continue
        if aa.neutral and marker is not None:
            if marker.group(1).casefold() != 'lua':
                # WP-26: a redundant {$asm} outside any Lua section is a CE
                # no-op; the section openers that matter are {$lua} only.
                continue
            chunks += 1
            if chunks > MAX_LUA_CHUNKS:
                raise LuaProgramError('Lua program contains too many Lua sections')
            lua = _LuaLex()
            implicit_lua = not _explicit_lua_end(lines, line_index + 1)
            inherited_lua, shared_lua = False, False
            continue
        was_quoted = aa.quote
        visible = aa.line(line, allow_lua_call=True)
        header = _PHASE.fullmatch(visible) if not was_quoted else None
        if header is not None:
            phase = header.group(1).casefold()
            if phase in seen or phase == 'disable' and seen != ['enable']:
                raise LuaProgramError('Lua program phases are duplicated or out of order')
            seen.append(phase)
            parts.append(_Part('phase', phase, '[' + phase.upper() + ']'))
            if common_lua:
                chunks += 1
                if chunks > MAX_LUA_CHUNKS:
                    raise LuaProgramError('Lua program contains too many Lua sections')
                lua = _LuaLex()
                implicit_lua = not _explicit_lua_end(lines, line_index + 1)
                inherited_lua, shared_lua = True, True
        elif not was_quoted and _LUA_CALL.match(visible) is not None:
            chunks += 1
            if chunks > MAX_LUA_CHUNKS:
                raise LuaProgramError('Lua program contains too many Lua sections/calls')
            parts.append(_Part('lua', phase, _lua_call_source(visible, aa), call=True))
        elif visible:
            parts.append(_Part('asm', phase, visible))
            static_body = True
    if lua is not None:
        if not implicit_lua or not lua.neutral:
            raise LuaProgramError('Unterminated Lua section or Lua string/comment')
        parts.append(_Part('lua', phase, '\n'.join(body), shared=shared_lua or phase == 'preamble' and implicit_lua))
    aa.finish()
    if seen not in (['enable'], ['enable', 'disable']):
        raise LuaProgramError('Lua program requires exactly ENABLE then DISABLE')
    if seen == ['enable']:
        # One-shot: a missing [DISABLE] marker becomes an explicit empty phase
        # so the static program and phase expansion share one canonical shape.
        # An empty enable is still rejected: a one-shot must carry an action.
        if not any(part.phase == 'enable' and part.kind != 'phase' for part in parts):
            raise LuaProgramError('Lua program requires exactly ENABLE then DISABLE')
        parts.append(_Part('phase', 'disable', '[DISABLE]'))
    static_source = '\n'.join(part.text for part in parts if part.kind != 'lua')
    return parts, static_source, static_body


def lua_symbol_provides(source: str, *, one_shot: bool | None = None) -> list[str]:
    """WP-37: the symbol names a record's embedded Lua proves to own.

    Pure-text re-derivation of the WP-14 C1 extraction (``registerSymbol`` /
    ``Register.symbol`` / ``symbol='...'`` in the ENABLE Lua,
    ``unregisterSymbol`` in the DISABLE Lua) so the table compiler can
    separate Lua-owned providers from static AA registrations without
    re-preparing the record's whole Lua program.  ``one_shot`` defaults to
    the record's own one-shot classification; a caller with a prepared
    program passes its canonical flag to stay byte-consistent with the
    entry's ``provides`` (WP-46 part 2).
    """
    parts, _static_source, _static_body = _parse(source)
    from .lua_symbol_providers import extract_lua_symbol_providers, parts_are_one_shot
    if one_shot is None:
        one_shot = parts_are_one_shot(parts)
    return extract_lua_symbol_providers(parts, one_shot=one_shot)


# WP-50 (GC-E8): bounded static extraction of the direct address-write
# idioms by which a record's Lua publishes a live base into a sibling
# record's address field (``AddressList['<label>'].address = <expr>`` or a
# constant-index array bound to such elements, ``mr[K].address = <expr>``).
# Bounded safety valve: more distinct targets than this are unproven (empty
# result), never truncated.
MAX_DYNAMIC_ADDRESS_TARGETS = 64

_AL_DIRECT = re.compile(
    r"\bAddressList\s*\[\s*(['\"])([^'\"]+)\1\s*\]\s*\.\s*address\s*=")
_AL_ARRAY = re.compile(
    r"\blocal\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\{([^{}]+)\}")
_AL_ELEMENT = re.compile(
    r"\s*AddressList\s*\[\s*(['\"])([^'\"]+)\1\s*\]\s*")
_AL_INDEX_WRITE = re.compile(
    r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\[\s*(\d+)\s*\]\s*\.\s*address\s*=")


_AL_WS = re.compile(r"\s*")


def _constant_addresslist_labels(body: str) -> list[str] | None:
    """Exact constant ``AddressList['label']`` elements only, or None."""
    labels: list[str] = []
    cursor, length = 0, len(body)
    while True:
        cursor = _AL_WS.match(body, cursor).end()
        if cursor >= length:
            break
        element = _AL_ELEMENT.match(body, cursor)
        if element is None:
            return None
        labels.append(element.group(2))
        cursor = _AL_WS.match(body, element.end()).end()
        if cursor >= length:
            break
        if body[cursor] != ",":
            return None
        cursor += 1
    return labels or None


def lua_dynamic_address_targets(source: str) -> list[str]:
    """Record descriptions a record's embedded Lua writes a live address to.

    Pure-text, bounded, case-sensitive.  Admits exactly two idioms:

    (a) direct writes:  ``AddressList['<label>'].address = <expr>``
    (b) constant arrays: ``local <name> = { AddressList['<label>'], ... }``
        (constant string elements only) followed by
        ``<name>[K].address = <expr>`` with a constant 1-based K.

    ``= nil`` counterparts (the expected DISABLE clearing) match too; their
    absence does not invalidate the extraction because clearing also
    happens at scope retirement.  Returns a sorted label list, or an empty
    list when nothing is proven (unparseable source, non-constant elements,
    out-of-range K, or more than the bound).
    """
    targets: set[str] = set()
    try:
        parts, _static_source, _static_body = _parse(source)
    except LuaProgramError:
        return []
    from .lua_symbol_providers import _without_comments
    arrays: dict[str, list[str]] = {}
    for part in parts:
        if part.kind != "lua" or not part.text:
            continue
        text = _without_comments(part.text)
        targets.update(match.group(2) for match in _AL_DIRECT.finditer(text))
        for definition in _AL_ARRAY.finditer(text):
            name, body = definition.group(1), definition.group(2)
            labels = _constant_addresslist_labels(body)
            if labels is not None:
                arrays.setdefault(name, []).extend(labels)
        for assignment in _AL_INDEX_WRITE.finditer(text):
            name, index = assignment.group(1), int(assignment.group(2))
            labels = arrays.get(name, [])
            if 1 <= index <= len(labels):
                targets.add(labels[index - 1])
    if len(targets) > MAX_DYNAMIC_ADDRESS_TARGETS:
        return []
    return sorted(targets)


def prepare_lua_program(source: str, process_name: str, bitness: int = 64, *,
                        nth_aob_helper=None,
                        external_owned: frozenset[str] = frozenset()) -> dict:
    """Prepare canonical metadata without compiling or executing original Lua.

    ``static_source`` uses LF, canonical phase markers and visible AA code only.
    Lua bodies and AA comments are absent. Literal, explicitly proven nth-scan
    definitions partition static dependencies; arbitrary runtime Lua symbols
    are never claimed. The unmodified static program retains every dependency.
    A phase/comment-only AA envelope has no static program or dependencies.
    A missing or contentless [DISABLE] marks the result ``one_shot`` so the
    runtime treats its single publish as irreversible (wish-save contract).
    """
    if (not isinstance(process_name, str) or not process_name or process_name != process_name.strip()
            or len(process_name) > 255 or process_name.casefold() in {'.exe', '..exe'}
            or not process_name.casefold().endswith('.exe')
            or any(char in '<>:"/\\|?*' or ord(char) < 32 for char in process_name)):
        raise LuaProgramError('Process name must be an exact .exe basename')
    if type(bitness) is not int or bitness not in {32, 64}:
        raise LuaProgramError('Only 32/64-bit Lua programs are supported')
    parts, static_source, static_body = _parse(source)
    from .nth_aob import (NthAOBError, definition_from_call, validate_helper_contract,
                          MAX_DEFINITIONS)
    definitions = []
    try:
        if nth_aob_helper is not None:
            nth_aob_helper = validate_helper_contract(nth_aob_helper)
        for index, part in enumerate(parts):
            definition = definition_from_call(part.text, index, nth_aob_helper) if part.call else None
            if definition is None:
                continue
            if part.phase != 'enable':
                raise NthAOBError('Nth-AOB source definitions are restricted to ENABLE')
            if len(definitions) >= MAX_DEFINITIONS:
                raise NthAOBError('Lua program contains too many nth-AOB definitions')
            if any(item['symbol'].casefold() == definition['symbol'].casefold() for item in definitions):
                raise NthAOBError('Nth-AOB symbol is defined more than once')
            definitions.append(definition)
    except NthAOBError as exc:
        raise LuaProgramError(str(exc)) from exc
    auto_assemble = None
    try:
        static_program = prepare_program(static_source, process_name, bitness=bitness,
                                         external_owned=external_owned) if static_body else None
    except ProgramError as exc:
        # WP-51: a non-executable static envelope is still plan-admissible
        # when the record Lua provably assembles the program itself.
        if static_body and str(exc) == _NO_CONTENT_REASON:
            auto_assemble = _auto_assemble_proof(parts, process_name, bitness)
            if auto_assemble is None:
                raise LuaProgramError('Static AA envelope: ' + str(exc)) from exc
            static_program = None
        else:
            raise LuaProgramError('Static AA envelope: ' + str(exc)) from exc
    if static_program is None and auto_assemble is None:
        # WP-51 shape C (no static envelope): plan-level admission is already
        # in effect, so the proof is additive — a provable autoAssemble body
        # contributes symbols, an unprovable one leaves the profile untouched
        # (the runtime assembler refusal stays fail-closed at activation).
        try:
            auto_assemble = _auto_assemble_proof(parts, process_name, bitness)
        except AutoAssembleProofError:
            pass
    from .lua_symbol_providers import parts_are_one_shot
    one_shot = parts_are_one_shot(parts)
    if static_program is not None:
        one_shot = one_shot and bool(static_program.get('one_shot', False))
    result = {'schema': SCHEMA, 'source': source,
            'source_sha256': hashlib.sha256(source.encode('utf-8')).hexdigest(),
            'process_name': process_name, 'bitness': bitness,
            'static_source': static_source, 'static_program': static_program,
            'one_shot': bool(one_shot),
            'requires': list(static_program['requires']) if static_program is not None else [],
            'provides': list(static_program['provides']) if static_program is not None else []}
    # WP-14 (C1): PRAGMATA-class tables register their base symbols inside
    # the embedded Lua (registerSymbol / symbol='...' table field) and
    # release them on disable; static proof of that pair makes the record
    # a provider for staged dependency analysis.  Pure text, no execution.
    # WP-46 part 2 (GC-E12): one-shot records adopt the ENABLE registration
    # without a matching unregister (the owner scope releases the symbol at
    # detach); the canonical one_shot flag above drives that branch.
    from .lua_symbol_providers import extract_lua_symbol_providers
    lua_provides = extract_lua_symbol_providers(parts, one_shot=one_shot)
    if lua_provides:
        result['provides'] = sorted(set(result['provides']) | set(lua_provides),
                                    key=str.casefold)
    if definitions:
        locals_ = set()
        for node in [] if static_program is None else static_program['preamble'] + static_program['enable']:
            if node['op'] in {'alloc', 'globalalloc', 'define', 'scan', 'scan_region'}:
                locals_.add(node['symbol'].casefold())
            elif node['op'] == 'label':
                locals_.update(name.casefold() for name in node['symbols'])
        owned = {definition['symbol'].casefold() for definition in definitions}
        if owned & locals_:
            raise LuaProgramError('Nth-AOB definition collides with a static AA local symbol')
        result['dynamic_definitions'] = definitions
        result['requires'] = [name for name in result['requires'] if name.casefold() not in owned]
        result['provides'] = sorted(result['provides'] + [item['symbol'] for item in definitions], key=str.casefold)
        if any(item['helper'] == 'lua_aobscan' for item in definitions):
            result['nth_aob_helper'] = nth_aob_helper
    # WP-48: luaCall(lua_aobscan(...)) symbols are static symbol providers
    # from the record's own Lua, resolved through the pinned luaCall plan
    # model.  The model's domain exclusion (mode sections, malformed call
    # syntax, in-record conflicting definitions) leaves the record on its
    # existing profile with the symbol unavailable (the downstream named
    # provider refusal is unchanged).
    from .aa_luacall import LuaCallError, analyze_luacall_program
    try:
        aob_symbols = analyze_luacall_program(source).aob_symbols
    except LuaCallError:
        aob_symbols = ()
    if aob_symbols:
        # A name the record's own static program declares as a positional
        # label is local to that program (WP-28): its runtime registration by
        # the binding-gated luaCall stays in the luacall plan domain, so it
        # is not claimed as a static provider here (the proven
        # dynamic_definitions merge above owns that case instead).
        local_labels = set()
        if static_program is not None:
            local_labels = {label.casefold()
                            for label in static_program.get('positional_labels', [])}
        merged = [symbol for symbol in aob_symbols
                  if symbol.casefold() not in local_labels]
        if merged:
            keys = {symbol.casefold() for symbol in merged}
            result['requires'] = [name for name in result['requires']
                                  if name.casefold() not in keys]
            result['provides'] = sorted(set(result['provides']) | set(merged),
                                        key=str.casefold)
    # WP-51: attach the proof report (admitted shape B + provable shape C)
    # and merge the proven bodies' registered symbols into provides.
    if auto_assemble is not None:
        result['auto_assemble'] = auto_assemble
        if auto_assemble['body_symbols']:
            result['provides'] = sorted(set(result['provides']) | set(auto_assemble['body_symbols']),
                                        key=str.casefold)
    return result


def validate_lua_program(program: dict) -> None:
    """Reconstruct all metadata from the original bounded source and context."""
    if not isinstance(program, dict) or program.get('schema') != SCHEMA:
        raise LuaProgramError('Invalid Lua program schema')
    regenerated = prepare_lua_program(program.get('source'), program.get('process_name'), program.get('bitness'),
                                     nth_aob_helper=program.get('nth_aob_helper'))
    try:
        actual = json.dumps(program, sort_keys=True, separators=(',', ':'), allow_nan=False)
        expected = json.dumps(regenerated, sort_keys=True, separators=(',', ':'), allow_nan=False)
    except (ValueError, TypeError, OverflowError, RecursionError) as exc:
        raise LuaProgramError('Lua program metadata must contain valid JSON primitives') from exc
    if actual != expected:
        raise LuaProgramError('Lua program metadata does not match its source')


def _returned_text(value: Any) -> str:
    if value is None:
        return ''
    if not isinstance(value, str):
        raise LuaProgramError('A Lua section must return AA text or nil')
    text = _bounded_source(value)
    aa = _AALex()
    for line in text.split('\n'):
        was_quoted = aa.quote
        visible = aa.line(line, allow_lua_call=True)
        if not was_quoted and _LUA_CALL.match(visible) is not None:
            raise LuaProgramError('Returned AA text cannot introduce luaCall')
        if not was_quoted and _PHASE.fullmatch(visible):
            raise LuaProgramError('Returned AA text cannot introduce phase sections')
    aa.finish()
    return text


def phase_expansion(host: Any, program: dict, phase: str, syntaxcheck: bool = False, *, nth_resolver=None) -> str:
    """Run preamble/selected Lua chunks and return the complete AA envelope.

    The host owns authorization and generation/context. Normal execution calls
    ``host.execute`` for each selected chunk. Syntax checking uses its public
    ``check_sources`` so explicit preamble helpers share one disposable state.
    Host execution errors propagate. Full expanded AA still needs runtime
    validation, including comparison with the captured enable-time inverse.
    """
    validate_lua_program(program)
    if type(phase) is not str or phase not in {'enable', 'disable'} or type(syntaxcheck) is not bool:
        raise LuaProgramError('Expansion requires enable/disable and a boolean syntaxcheck')
    parts, _, _ = _parse(program['source'])
    dynamic = {item['part_index']: item for item in program.get('dynamic_definitions', [])}
    if phase == 'enable' and dynamic and not callable(nth_resolver):
        raise LuaProgramError('Nth-AOB expansion requires the owned read/scan resolver')
    common = '\n'.join(part.text for part in parts
                       if part.kind == 'lua' and part.phase == 'preamble' and part.shared)
    def selected_source(part):
        # An implicit common mode is one Lua lexical chunk with the selected
        # phase. Preserve locals and an early syntaxcheck return across it.
        return common + '\n' + part.text if part.shared and part.phase != 'preamble' else part.text
    selected = [part for index, part in enumerate(parts)
                if part.kind == 'lua' and part.phase in {'preamble', phase}
                and not (part.phase == 'preamble' and part.shared) and index not in dynamic]
    if syntaxcheck and phase == 'enable':
        for definition in dynamic.values():
            if nth_resolver(dict(definition), True) is not None:
                raise LuaProgramError('Nth-AOB resolver cannot return arbitrary AA text')
    if syntaxcheck and selected:
        values = host.check_sources([selected_source(part) for part in selected])
        if not isinstance(values, list) or len(values) != len(selected):
            raise LuaProgramError('Syntax checker returned invalid chunk results')
        values = iter(values)
    else:
        values = None
    # WP-51: an admitted record's static AA envelope is non-executable; the
    # proven autoAssemble call owns the actual patch.  Skip the static asm
    # parts (phase markers stay, so the runtime section split sees the
    # canonical ENABLE/DISABLE pair around the nil Lua returns).
    drop_static = (program.get('auto_assemble') is not None
                   and program.get('static_program') is None)
    output, size = [], 0
    for index, part in enumerate(parts):
        if part.kind == 'lua':
            if part.phase not in {'preamble', phase} or part.phase == 'preamble' and part.shared:
                continue
            if index in dynamic:
                if not syntaxcheck and nth_resolver(dict(dynamic[index]), False) is not None:
                    raise LuaProgramError('Nth-AOB resolver cannot return arbitrary AA text')
                continue
            value = next(values) if values is not None else host.execute(selected_source(part), syntaxcheck=False)
            text = _returned_text(value)
        elif drop_static and part.kind == 'asm':
            continue
        else:
            text = part.text
        if not text:
            continue
        size += len(text.encode('utf-8')) + bool(output)
        if size > MAX_SOURCE_BYTES:
            raise LuaProgramError('Expanded AA source exceeds its size bound')
        output.append(text)
    return '\n'.join(output)
