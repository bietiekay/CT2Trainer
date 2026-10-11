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
"""

from __future__ import annotations

import re

# Bounded safety valve: a record that "registers" more distinct symbols
# than this is treated as unproven (empty result), never truncated.
MAX_PROVIDERS = 64

# registerSymbol('Name', <anything>) / registerSymbol("Name", <anything>)
# The lookbehind keeps unregisterSymbol('Name') from matching as a
# registration (it contains "registerSymbol" as a suffix).
_REGISTER_CALL = re.compile(
    r"(?<![A-Za-z0-9_])registerSymbol\s*\(\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s*[),]",
    re.IGNORECASE)
# unregisterSymbol('Name')
_UNREGISTER_CALL = re.compile(
    r"(?<![A-Za-z0-9_])unregisterSymbol\s*\(\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s*\)",
    re.IGNORECASE)
# symbol='Name' table field (the PRAGMATA AOB-table shape)
_SYMBOL_FIELD = re.compile(
    r"(?<![A-Za-z0-9_])symbol\s*=\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]")


def _without_comments(text: str) -> str:
    """Drop Lua ``--`` comments line-wise (same discipline as the
    activation-set extractor); ``--[[ ]]`` blocks are not modelled and
    their content simply does not match the constant-string patterns."""
    return "\n".join(line.split("--", 1)[0] for line in text.splitlines())


def extract_lua_symbol_providers(parts) -> list[str]:
    """Return the symbol names a record's embedded Lua proves to register
    while active and release on deactivation.

    ``parts`` are the parsed ``_Part`` objects from ``lua_program._parse``;
    only parts with ``kind == 'lua'`` are inspected.  Registration evidence
    is collected from the ``enable`` phase, release evidence from the
    ``disable`` phase; the result is their intersection, sorted
    case-insensitively.  Returns an empty list when nothing is proven.
    """
    registered: set[str] = set()
    released: set[str] = set()
    for part in parts:
        if part.kind != "lua" or not part.text:
            continue
        text = _without_comments(part.text)
        if part.phase == "enable":
            registered.update(
                match.group(1) for match in _REGISTER_CALL.finditer(text))
            registered.update(
                match.group(1) for match in _SYMBOL_FIELD.finditer(text))
        elif part.phase == "disable":
            released.update(
                match.group(1) for match in _UNREGISTER_CALL.finditer(text))
    adopted = registered & released
    if len(adopted) > MAX_PROVIDERS:
        return []
    return sorted(adopted, key=str.casefold)
