"""Static extraction of embedded-Lua symbol providers (WP-14, C1).

Multi-step tables resolve base addresses at activation time and register
the result as a named symbol that child records reference.  In the
PRAGMATA-class pattern the registration happens inside the record's
embedded Lua rather than in the Auto Assembler envelope::

    [ENABLE]
    {$lua}
    local AOBs = {
      {name='Manager', aob='...', pos=3, aoblen=7,
       symbol='InventoryManager_addr'},
    }
    for _, entry in ipairs(AOBs) do
      -- scan, compute, then:
      registerSymbol(entry.symbol, final_addr)
    end
    {$asm}
    [DISABLE]
    {$lua}
    unregisterSymbol('InventoryManager_addr')
    {$asm}

Only constant-string evidence is adopted, and only when the same symbol
name appears (a) as a ``registerSymbol('<name>', ...)`` literal call or a
``symbol='<name>'`` table field in an ENABLE-phase Lua section, and (b) as
an ``unregisterSymbol('<name>')`` literal call in a DISABLE-phase Lua
section.  Dynamic names without a constant binding, a registration without
a matching unregister, and an unregister without a matching registration
all stay unproven: the record then keeps its ordinary (empty) Lua
provides, so dependent records remain blocked with their named provider
reason.  The extraction is pure text; no Lua is executed.

WP-46 part 2 (GC-E12) extends the evidence without weakening the rest:
the CE helper form ``Register.symbol('<name>', ...)`` (case-insensitive
dotted form) counts as registration evidence alongside
``registerSymbol``, and ``unregisterSymbol('<name>')`` accepts one
optional trailing argument (e.g. ``unregisterSymbol('<name>', false)``)
whose value carries no static meaning.  For records classified one-shot
(missing or contentless ``[DISABLE]``), the ENABLE-phase registration
evidence is adopted *without* a matching unregister: the symbol is
released by the owner scope at detach instead of by a disable phase, so
requiring the pair would keep every genuine one-shot provider unproven.
Non-one-shot records keep the strict register ∩ unregister rule.

RT-4.2 (R4) adds the mixed-dialect release form seen in the corpus:
records that register their symbols in the ENABLE Lua
(``unregisterSymbol("X")``/``registerSymbol("X", addr, true)``
re-entrance pairs) and release them in an ``{$asm}`` [DISABLE] section
(``unregistersymbol( X )``, unquoted).  Release evidence is therefore
collected from the static AA dialect parts of the disable phase as well.
The AA directive is the multi-name form (CE 7.5 autoassembler.pas:2492:
the argument list is split on commas/whitespace, so several names per
call are valid) and ``unregistersymbol(*)`` expands to the program's own
registered symbols at runtime, so the wildcard contributes no named
evidence.  The extraction is restricted to ``kind == 'asm'`` parts: in
the Lua dialect the same spelling is the Lua API call that CE 7.5 only
honors with exactly one argument (LuaHandler.pas:5292: the symbol is
deleted only when parameters:=lua_gettop(L) == 1; a 2-/3-argument call
is a no-op), so the strict-pair regex stays the only Lua release
evidence.  The strict intersection rule (and the MAX_PROVIDERS valve) is
unchanged.
"""

from __future__ import annotations

import re

# Bounded safety valve: a record that "registers" more distinct symbols
# than this is treated as unproven (empty result), never truncated.
MAX_PROVIDERS = 64

# registerSymbol('Name', <anything>) / registerSymbol("Name", <anything>),
# plus the CE helper form Register.symbol('Name', <anything>) — the
# case-insensitive dotted form counts as the same registration evidence
# (WP-46 part 2, GC-E12).  The lookbehind keeps unregisterSymbol('Name')
# from matching as a registration (it contains "registerSymbol" as a
# suffix); the dotted form keeps its own dotted boundary.
_REGISTER_CALL = re.compile(
    r"(?<![A-Za-z0-9_.])(?:registerSymbol|Register\.symbol)\s*\(\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s*[),]",
    re.IGNORECASE)
# unregisterSymbol('Name') with one optional trailing argument
# (WP-46 part 2: the corpus shows unregisterSymbol('Name', false)); the
# argument is a single bounded scalar (constant, number or short string)
# whose value carries no static meaning.
_UNREGISTER_TAIL = (
    r"(?:true|false|nil|null|[A-Za-z_][A-Za-z0-9_]*|\d+(?:\.\d+)?"
    r"|['\"][^'\"]{0,64}['\"])")
_UNREGISTER_CALL = re.compile(
    r"(?<![A-Za-z0-9_])unregisterSymbol\s*\(\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]"
    r"\s*(?:,\s*" + _UNREGISTER_TAIL + r")?\s*\)",
    re.IGNORECASE)
# symbol='Name' table field (the PRAGMATA AOB-table shape)
_SYMBOL_FIELD = re.compile(
    r"(?<![A-Za-z0-9_])symbol\s*=\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]")
# RT-4.2 (R4): the AA release form — unquoted names, optionally several per
# call, optionally quoted (CE's AA unregistersymbol accepts both spellings).
# The wildcard argument (*) expands to the program's own phase-owned names
# at runtime, so it contributes no named evidence.
_AA_UNREGISTER_CALL = re.compile(
    r"(?i)(?<![A-Za-z0-9_])unregistersymbol\s*\(([^)]*)\)")
_AA_UNREGISTER_NAME = re.compile(
    r"[\"']?([A-Za-z_][A-Za-z0-9_]*)[\"']?")
# Scalar keywords that are never symbol names; the Lua form
# ``unregisterSymbol('Name', false)`` must not contribute its trailing
# argument as a release.
_AA_UNREGISTER_SCALARS = {"true", "false", "nil"}


def _without_comments(text: str) -> str:
    """Drop Lua ``--`` comments line-wise (same discipline as the
    activation-set extractor); ``--[[ ]]`` blocks are not modelled and
    their content simply does not match the constant-string patterns."""
    return "\n".join(line.split("--", 1)[0] for line in text.splitlines())


# Lane A (shape 2): bounded derivation of the symbol names a record's Lua
# registers through a literal name list, i.e. a ``registerSymbol(X[i][k],
# addr)`` / ``unregisterSymbol(X[i][k])`` call where ``X`` is (through a
# same-source ``local X = f()`` binding) a literal table of string tuples.
# The extraction is strictly bounded: literal tables only, string
# constants only, the exact indexing pattern ``X[i][k]`` with a constant
# integer ``k`` only, and one hop of function-return resolution.  No
# arbitrary Lua semantics are modelled; anything outside the bound is
# unproven (the name contributes no evidence).
#
# ``_lua_words`` yields (word, start) pairs for the code words of a
# comment-stripped Lua source, skipping string literals (both quotes),
# line comments (``--``) and block comments (``--[[ ]]`` / ``--[=[ ]]``).
# Only whole-word matches count, so identifiers containing a keyword
# (``endless``) never trigger a block boundary.


def _lua_words(text: str):
    words: list[tuple[str, int]] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch in "'\"":
            j = i + 1
            while j < n and text[j] != ch:
                j += 1
            i = j + 1 if j < n else n
            continue
        if ch == '-' and i + 1 < n and text[i + 1] == '-':
            if text.startswith('--[[', i):
                j = text.find(']]', i + 4)
                i = n if j < 0 else j + 2
            else:
                j = text.find('\n', i)
                i = n if j < 0 else j + 1
            continue
        if ch.isalpha() or ch == '_':
            j = i
            while j < n and (text[j].isalnum() or text[j] == '_'):
                j += 1
            words.append((text[i:j], i))
            i = j
            continue
        i += 1
    return words


# Bounded Lua block matcher: the openers that require a matching ``end``
# are ``function`` (immediately), ``if``/``elseif`` via their ``then``,
# ``for``/``while`` via their ``do``, and a standalone ``do``.  ``else`` /
# ``elseif`` / ``until`` change no depth.  The word list comes from
# ``_lua_words`` so comments and strings never count.
_LUA_OPENERS = {"function"}


def _lua_block_end(text: str, keyword_pos: int) -> int | None:
    """The index of the ``end`` word closing the block opened at the
    ``function`` keyword at ``keyword_pos``, or None when unbalanced.

    ``do`` opens a block in every form (the ``for``/``while`` loop body and
    the standalone ``do`` block alike), so the loop keyword needs no
    pending flag; only ``if``/``elseif`` defer their open to the ``then``
    (an ``elseif ... then`` re-opens no new block).
    """
    words = _lua_words(text)
    start_index = None
    for index, (_word, pos) in enumerate(words):
        if pos >= keyword_pos:
            start_index = index
            break
    if start_index is None:
        return None
    depth = 0
    for index in range(start_index, len(words)):
        word, pos = words[index]
        if word in _LUA_OPENERS:
            depth += 1
        elif word == 'then':
            previous = words[index - 1][0] if index > start_index else ''
            if previous.casefold() != 'elseif':
                depth += 1
        elif word == 'do':
            depth += 1
        elif word == 'end':
            depth -= 1
            if depth == 0:
                return pos
            if depth < 0:
                return None
    return None


# Bounded table-literal cell parser.  A cell is a nested table (``row``), a
# string constant (``str``), an identifier (``ident``) or a numeric
# constant (``num``); anything else fails the whole literal (unproven).
_CELL_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_CELL_NUM = re.compile(r"-?\d+(?:\.\d+)?")
_WS = " \t\r\n"


def _parse_table_cells(text: str, start: int):
    """Parse the cells of a table literal opening at ``text[start] == '{'``.

    Returns ``(cells, end)`` where ``end`` is the index just past the
    matching ``}``, or ``(None, start)`` when the literal is malformed or
    carries a non-bounded cell (keyed form, nested call, ...).  ``cells``
    is a list of ``(kind, value)`` tuples; a nested table is
    ``('row', subcells)``.
    """
    if start >= len(text) or text[start] != '{':
        return None, start
    i, n = start + 1, len(text)
    cells: list[tuple[str, object]] = []
    while True:
        while i < n and text[i] in _WS:
            i += 1
        if i >= n:
            return None, start
        if text[i] == '}':
            return cells, i + 1
        if text[i] == '{':
            sub, i = _parse_table_cells(text, i)
            if sub is None:
                return None, start
            cells.append(('row', sub))
        elif text[i] in "'\"":
            quote, j = text[i], i + 1
            while j < n and text[j] != quote:
                j += 1
            if j >= n:
                return None, start
            cells.append(('str', text[i + 1:j]))
            i = j + 1
        else:
            ident = _CELL_IDENT.match(text, i)
            if ident is not None:
                cells.append(('ident', ident.group(0)))
                i = ident.end()
            else:
                number = _CELL_NUM.match(text, i)
                if number is not None:
                    cells.append(('num', number.group(0)))
                    i = number.end()
                else:
                    return None, start
        while i < n and text[i] in _WS:
            i += 1
        if i >= n:
            return None, start
        if text[i] == ',':
            i += 1
        elif text[i] != '}':
            return None, start


def _table_rows(cells) -> list | None:
    """The row tables of a table literal's cells, or None when the literal
    is not a plain list of row tables (an array of string tuples)."""
    if not cells:
        return None
    rows = []
    for kind, value in cells:
        if kind != 'row':
            return None
        rows.append(value)
    return rows


def _tuple_column(rows, column: int) -> list[str] | None:
    """The ``column``-th (1-based) element of every row, adopted only when
    every row carries a string constant there (constant-string evidence)."""
    if not rows:
        return None
    values: list[str] = []
    for row in rows:
        if column < 1 or column > len(row):
            return None
        kind, value = row[column - 1]
        if kind != 'str':
            return None
        values.append(value)
    return values or None


# ``local <name> = <name>()``: the function-call binding that aliases a
# same-source function's returned literal table.  Bounded: one call, no
# arguments, identifier name.
_LOCAL_FUNC_BINDING = re.compile(
    r"\blocal\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
    r"([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*\)")
# ``function <name>(...)``: the function head whose body is inspected for
# the returned literal table.
_FUNCTION_HEAD = re.compile(r"\bfunction\s+([A-Za-z_][A-Za-z0-9_]*)")
# ``return { ... }`` / ``return <name>``: the function's return shape.
_RETURN_TABLE = re.compile(r"\breturn\s+(?=\{)")
_RETURN_IDENT = re.compile(r"\breturn\s+([A-Za-z_][A-Za-z0-9_]*)\s*[;\n]")
# ``local <name> = { ... }``: the local table definition inside a body.
_LOCAL_TABLE = re.compile(r"\blocal\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?=\{)")
# The indexed name argument of a register/unregister call:
# ``X[i][k]`` with a constant integer k (i is the loop variable).
_INDEX_NAME = re.compile(
    r"([A-Za-z_][A-Za-z0-9_]*)\s*\[\s*[A-Za-z_][A-Za-z0-9_]*\s*\]\s*\[\s*(\d+)\s*\]")
# The call forms mirror the house literal-string evidence regexes
# (_REGISTER_CALL / _UNREGISTER_CALL): the CE helper dotted form counts
# alongside the plain form, case-insensitively (WP-46 part 2; CE
# registers every Lua API on both first-letter spellings, WP-56, so
# record scripts use either).  The lookbehind keeps unregisterSymbol
# from matching as a registration.
_REGISTER_INDEX_CALL = re.compile(
    r"(?<![A-Za-z0-9_.])(?:registerSymbol|Register\.symbol)\s*\(\s*",
    re.IGNORECASE)
_UNREGISTER_INDEX_CALL = re.compile(
    r"(?<![A-Za-z0-9_])unregisterSymbol\s*\(\s*",
    re.IGNORECASE)


def _function_return_rows(text: str, function_name: str):
    """The literal-table rows a same-source ``function <name>`` returns, or
    None: admitted shapes are ``return { rows }`` directly and
    ``local <y> = { rows }`` ... ``return <y>`` (one hop).  ``<y>`` must be
    defined exactly once in the body."""
    head = None
    for match in _FUNCTION_HEAD.finditer(text):
        if match.group(1) == function_name:
            head = match
            break
    if head is None:
        return None
    end_pos = _lua_block_end(text, head.start())
    if end_pos is None:
        return None
    body = text[head.end():end_pos]
    direct = _RETURN_TABLE.search(body)
    if direct is not None:
        cells, _end = _parse_table_cells(body, body.index('{', direct.start()))
        if cells is None:
            return None
        return _table_rows(cells)
    returned_ident = _RETURN_IDENT.search(body)
    if returned_ident is None:
        return None
    ident = returned_ident.group(1)
    definitions = [m for m in _LOCAL_TABLE.finditer(body) if m.group(1) == ident]
    if len(definitions) != 1:
        return None
    cells, _end = _parse_table_cells(body, body.index('{', definitions[0].start()))
    if cells is None:
        return None
    return _table_rows(cells)


def _name_list_evidence(text: str, call_regex: re.Pattern) -> set[str]:
    """The names one call form (register or unregister) proves through
    literal name lists in this text: every ``X[i][k]`` name argument where
    ``X`` binds (``local X = f()``) a same-source function returning a
    literal table, every row carrying a string constant in column k."""
    names: set[str] = set()
    for call in call_regex.finditer(text):
        match = _INDEX_NAME.match(text, call.end())
        if match is None:
            continue
        source_name, column = match.group(1), int(match.group(2))
        binding = None
        for candidate in _LOCAL_FUNC_BINDING.finditer(text):
            if candidate.group(1) == source_name:
                binding = candidate
                break
        if binding is None:
            continue
        rows = _function_return_rows(text, binding.group(2))
        if rows is None:
            continue
        column_values = _tuple_column(rows, column)
        if column_values is not None:
            names.update(column_values)
    return names


def _extract_name_list_symbols(parts, call_regex: re.Pattern) -> set[str]:
    """The names the record's Lua proves to register/release through literal
    name lists (``X[i][k]`` indexing, one function hop).

    The call form (``registerSymbol`` vs ``unregisterSymbol``) already
    distinguishes registration from release, and the registration logic may
    live in preamble-defined functions (a record body's ``[ENABLE]`` part
    only *calls* them), so every ``lua`` part of the record is inspected —
    not only the enable/disable phase parts.
    """
    names: set[str] = set()
    for part in parts:
        if part.kind != 'lua' or not part.text:
            continue
        names.update(_name_list_evidence(_without_comments(part.text), call_regex))
    return names


def parts_are_one_shot(parts) -> bool:
    """The one-shot classification shared with ``prepare_lua_program``.

    A parsed program is one-shot when its DISABLE phase carries no content
    (no AA part, no non-empty Lua part) while at least one ENABLE part
    exists; a missing [DISABLE] marker is canonicalized into an explicit
    empty phase by the parser, so both shapes classify identically.
    """
    return (all(part.phase != 'disable' or part.kind == 'phase'
                or (part.kind == 'lua' and not part.text.strip())
                for part in parts)
            and any(part.phase == 'enable' and part.kind != 'phase' for part in parts))


def extract_table_lua_symbols(source: str) -> list[str]:
    """WP-54 (b): symbol names a combined table-Lua source proves to keep
    live for the table's lifetime.

    The table scope runs the combined source once at load and retires with
    the attach, so the module's one-shot adoption rule applies to the whole
    source: the same literal evidence (``registerSymbol('Name', ...)`` /
    ``Register.symbol(...)`` / ``symbol='Name'`` registrations plus
    ``unregisterSymbol('Name')`` releases) is collected over the unphased
    table text, and a name is adopted only while it is not released inside
    the source (the scope would not keep it live).  The same bounded safety
    valve as the record extractor applies: more than MAX_PROVIDERS distinct
    names are unproven (empty result), never truncated.  Pure text; no Lua
    is executed.
    """
    if not isinstance(source, str):
        raise ValueError("Table-Lua symbol source must be text")
    if not source.strip():
        return []
    text = _without_comments(source)
    registered = {match.group(1) for match in _REGISTER_CALL.finditer(text)}
    registered.update(match.group(1) for match in _SYMBOL_FIELD.finditer(text))
    released = {match.group(1) for match in _UNREGISTER_CALL.finditer(text)}
    adopted = registered - released
    if len(adopted) > MAX_PROVIDERS:
        return []
    return sorted(adopted, key=str.casefold)


def extract_lua_symbol_providers(parts, *, one_shot: bool = False) -> list[str]:
    """Return the symbol names a record's embedded Lua proves to register
    while active and release on deactivation.

    ``parts`` are the parsed ``_Part`` objects from ``lua_program._parse``;
    only parts with ``kind == 'lua'`` (and, for RT-4.2 (R4) release
    evidence, the ``kind == 'asm'`` parts of the ``disable`` phase) are
    inspected.  Registration evidence is collected from the ``enable``
    phase, release evidence from the ``disable`` phase (Lua
    ``unregisterSymbol`` and AA ``unregistersymbol`` alike); the result is
    their intersection, sorted case-insensitively.  Returns an empty list
    when nothing is proven.

    ``one_shot`` selects the WP-46 part 2 adoption rule for records
    classified one-shot (missing/empty [DISABLE]): the ENABLE-phase
    registration evidence is adopted without a matching unregister, because
    the symbol is released by the owner scope at detach instead of by a
    disable phase.  An unregister that does appear in such a record still
    cancels the adoption (the symbol would not stay live after activation).
    Non-one-shot records keep the strict register ∩ unregister rule.
    """
    registered: set[str] = set()
    released: set[str] = set()
    for part in parts:
        if part.kind not in ("lua", "asm") or not part.text:
            continue
        text = _without_comments(part.text)
        if part.phase == "enable" and part.kind == "lua":
            registered.update(
                match.group(1) for match in _REGISTER_CALL.finditer(text))
            registered.update(
                match.group(1) for match in _SYMBOL_FIELD.finditer(text))
        elif part.phase == "disable":
            released.update(
                match.group(1) for match in _UNREGISTER_CALL.finditer(text))
            # RT-4.2 (R4): mixed-dialect records release their Lua-
            # registered symbols in an {$asm} disable section with the
            # unquoted AA form; the named argument is release evidence.
            # Strictly static-AA dialect: in the Lua dialect the same
            # spelling is the Lua API call that CE 7.5 only honors with
            # exactly one argument (LuaHandler.pas:5292: the symbol is
            # deleted only when parameters:=lua_gettop(L) == 1, so a
            # 2-/3-argument call is a no-op and carries no release
            # evidence); the strict-pair regex above stays the only
            # Lua release evidence.  The AA directive is the multi-name
            # form (autoassembler.pas:2492 splits the argument list on
            # commas/whitespace) and the wildcard (*) expands to the
            # program's own registered symbols at runtime, so it
            # contributes no named evidence.
            if part.kind == "asm":
                for call in _AA_UNREGISTER_CALL.finditer(text):
                    for name in _AA_UNREGISTER_NAME.findall(call.group(1)):
                        if name.casefold() not in _AA_UNREGISTER_SCALARS:
                            released.add(name)
    # Lane A (shape 2): literal name-list registration/release.  A
    # ``registerSymbol(X[i][k], ...)`` / ``unregisterSymbol(X[i][k])`` call
    # whose name argument indexes a same-source literal table of string
    # tuples proves the column's string constants.  The call form decides
    # registration vs release, and the logic may live in preamble-defined
    # functions, so all lua parts are inspected (the strict-pair rule below
    # is unchanged: the derived names join the same sets).
    registered.update(_extract_name_list_symbols(parts, _REGISTER_INDEX_CALL))
    released.update(_extract_name_list_symbols(parts, _UNREGISTER_INDEX_CALL))
    if one_shot:
        adopted = registered - released
    else:
        adopted = registered & released
    if len(adopted) > MAX_PROVIDERS:
        return []
    return sorted(adopted, key=str.casefold)
