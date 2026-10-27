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
    if one_shot:
        adopted = registered - released
    else:
        adopted = registered & released
    if len(adopted) > MAX_PROVIDERS:
        return []
    return sorted(adopted, key=str.casefold)
