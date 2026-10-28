"""Static canonical profile for explicitly requested read-only Lua helpers.

Preparation does not execute source or establish that its top-level calls are
supported. A private activation installs the source under the host's read-only
gate; a failed installation cancels that activation. No automatic table load.

WP-41 (table-Lua bootstrap, phase 1) adds the static surface of the per-table
load-time contract: the read-only broker allowlist extracted from the
``EngineLuaBroker.call`` dispatch by classification (reads stay; every call
that mutates target memory, the symbol table or host session state, executes
target code, or registers a callback is refused), the named refusal taxonomy,
the top-level global extraction that drives the record-dependency rule, and
the strict plan metadata validation shared by both plan gates.
"""
from __future__ import annotations

import hashlib
import re


SCHEMA = "ct2trainer-lua-bootstrap/v1"
PROFILE = "activation-read-only/v1"
MAX_SOURCE_BYTES = 1024 * 1024

#: Read-only broker names admitted in the per-table bootstrap scope. Extracted
#: from the EngineLuaBroker.call dispatch by the WP-41 classification: reads
#: stay (this set), every mutation-family call is refused with a named reason
#: (TABLE_LUA_REFUSAL_CLASSES). ``print`` is the only message surface kept:
#: ``showMessage`` is a UI callback and stays refused.
TABLE_LUA_READ_ONLY_NAMES = frozenset({
    'getAddress', 'getAddressSafe', 'getModuleSize',
    'getAddressOfSymbol', 'getAddressOfSymbolSafe',
    'luaEngine.snapshot',
    'getProcHandle', 'getOpenProcessID',
    'readInteger', 'readSmallInteger', 'readQword', 'readFloat',
    'readDouble', 'readPointer', 'readString', 'readBytes',
    'AOBScan', 'scan.firstScan',
    'mono_enumDomains', 'mono_findMethod',
    'addresslist.Count', 'addresslist.at',
    'addresslist.getMemoryRecordByID', 'addresslist.getMemoryRecordByDescription',
    'record.get',
    'isKeyPressed', 'getXBox360ControllerState',
    'speedhack_getSpeed',
    'print',
    # RT-5 item A: embedded <Files> lookups (plan data) and string-stream
    # access (per-scope host state) never touch target memory, so the
    # table scope admits them exactly like the other read-class names.
    'findTableFile', 'readStringLocal',
    'stringstream.create', 'stringstream.copyFrom', 'stringstream.dataString',
    'stringstream.size', 'stringstream.destroy',
    # RT-5 item C: bounded single-target process-info queries (plan data
    # plus the attached target's identity/architecture; disassemble is a
    # bounded read-only target probe).  Like the other read-class names
    # they never write target memory and are admitted in the table scope.
    'getProcessIDFromProcessName', 'getProcessList', 'targetIs64Bit',
    'enumModules', 'disassemble',
})

#: Named block reasons per refused API class (activation block, never parse
#: block — the table still parses and plans). Exact strings are part of the
#: WP-41 contract.
TABLE_LUA_REFUSAL_CLASSES = (
    ("Table Lua uses a write API: ",
     frozenset({'writeInteger', 'writeSmallInteger', 'writeQword',
                'writeFloat', 'writeDouble', 'writeString', 'writeBytes',
                'record.set'})),
    ("Table Lua writes the symbol table: ",
     frozenset({'registerSymbol', 'unregisterSymbol'})),
    ("Table Lua executes assembler patches: ",
     frozenset({'autoAssemble'})),
    ("Table Lua invokes target code: ",
     frozenset({'executeCodeEx', 'mono_invoke_method'})),
    ("Table Lua registers a UI callback: ",
     frozenset({'showMessage', 'luaEngine.close', 'luaEngine.menuClick'})),
    ("Table Lua mutates host session state: ",
     frozenset({'attachProcess', 'detachProcess', 'LaunchMonoDataCollector',
                'speedhack_setSpeed'})),
)

TABLE_LUA_UNCLASSIFIED_REFUSAL = "Table Lua calls an unsupported API: "
TABLE_LUA_TOP_LEVEL_FAILURE = "Table Lua top-level execution failed: "
TABLE_LUA_RECORD_REFUSAL = ("Table Lua was not executed on load; record script "
                            "references table-level ")

MAX_TABLE_LUA_REASONS = 64
MAX_TABLE_LUA_REASON_CHARS = 512


class LuaBootstrapError(ValueError):
    """Malformed, oversized, changed, or unsupported bootstrap profile."""


def prepare_lua_bootstrap(source: str) -> dict:
    if type(source) is not str:
        raise LuaBootstrapError("Lua bootstrap source must be text")
    try:
        raw = source.encode("utf-8")
    except UnicodeError as exc:
        raise LuaBootstrapError("Lua bootstrap source must be valid UTF-8 text") from exc
    if len(raw) > MAX_SOURCE_BYTES:
        raise LuaBootstrapError("Lua bootstrap source exceeds its 1 MiB bound")
    return {"schema": SCHEMA, "profile": PROFILE, "source": source,
            "source_sha256": hashlib.sha256(raw).hexdigest()}


def validate_lua_bootstrap(profile: dict) -> dict:
    if (type(profile) is not dict or set(profile) != {"schema", "profile", "source", "source_sha256"}
            or any(type(value) is not str for value in profile.values())
            or profile["schema"] != SCHEMA or profile["profile"] != PROFILE):
        raise LuaBootstrapError("Unknown or malformed Lua bootstrap profile")
    canonical = prepare_lua_bootstrap(profile["source"])
    if profile != canonical:
        raise LuaBootstrapError("Lua bootstrap source or hash differs from its canonical profile")
    return canonical


def table_lua_refusal_reason(name: str) -> str:
    """Exact WP-41 refusal reason for one refused broker call name."""
    if not isinstance(name, str) or not name:
        raise LuaBootstrapError("Table-Lua refusal reason requires a broker name")
    for prefix, members in TABLE_LUA_REFUSAL_CLASSES:
        if name in members:
            return prefix + name + "."
    return TABLE_LUA_UNCLASSIFIED_REFUSAL + name + "."


_LUA_KEYWORDS = frozenset({
    'and', 'break', 'do', 'else', 'elseif', 'end', 'false', 'for', 'function',
    'goto', 'if', 'in', 'local', 'nil', 'not', 'or', 'repeat', 'return',
    'then', 'true', 'until', 'while',
})

# File-scope assignments: a bare identifier (or comma-separated bare
# identifiers) directly followed by a single '='.  'local x = 1' never
# matches: the capture ends at 'local', which is not followed by '='.
_TOP_ASSIGN = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*(?:\s*,\s*[A-Za-z_][A-Za-z0-9_]*)*)\s*=(?!=)')
# The global-creating function-definition sugar 'function name(...)' /
# 'function name:...'; dotted targets ('function t.f(...)') only read the
# table and are deliberately not treated as a bare-global assignment.
_TOP_GLOBAL_FUNCTION = re.compile(r'^\s*function\s+([A-Za-z_][A-Za-z0-9_]*)\s*[(:]')
_FUNCTION_OPEN = re.compile(r'^\s*(?:local\s+)?function\s')
_ASSIGNED_FUNCTION = re.compile(r'=\s*function\b')
_END_WORD = re.compile(r'\bend\b')
_END_LINE = re.compile(r'^\s*end\b')
_LONG_BRACKET = re.compile(r'\[(=*)\[')
_IDENTIFIER = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')


def table_top_level_globals(source: str) -> tuple[str, ...]:
    """Top-level non-local global names created by a combined table-Lua source.

    Line-oriented static scan: an assignment at file scope (outside function
    bodies) creates a global, and so does the 'function name(...)' sugar.
    'local' declarations, function-body statements and keywords are excluded.
    Multi-assignments with dotted targets are not tracked (documented
    limitation); a name assigned twice is listed once, in first-seen order.
    """
    if not isinstance(source, str):
        raise LuaBootstrapError("Table-Lua source must be text")
    names: list[str] = []
    seen: set[str] = set()
    depth = 0
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('--'):
            continue
        if depth == 0:
            match = _TOP_ASSIGN.match(line)
            if match is not None:
                for name in match.group(1).split(','):
                    name = name.strip()
                    if name in _LUA_KEYWORDS or name in seen:
                        continue
                    seen.add(name)
                    names.append(name)
            else:
                match = _TOP_GLOBAL_FUNCTION.match(line)
                if match is not None:
                    name = match.group(1)
                    if name not in _LUA_KEYWORDS and name not in seen:
                        seen.add(name)
                        names.append(name)
        if _FUNCTION_OPEN.match(line) or _ASSIGNED_FUNCTION.search(line):
            # A function body opened on this line; a same-line 'end' (e.g.
            # 'x = function() end') closes it again immediately.
            depth = max(0, depth + 1 - len(_END_WORD.findall(line)))
        elif depth > 0 and _END_LINE.match(line):
            depth -= 1
    return tuple(names)


def _lua_identifier_tokens(source: str) -> frozenset[str]:
    """Bare identifier tokens of a Lua source, case-sensitive.

    Comments (line and long), quoted strings and long strings are stripped
    first, so names appearing only inside literals are not tokens.
    """
    tokens: set[str] = set()
    i, n = 0, len(source)
    while i < n:
        if source.startswith('--', i):
            opener = _LONG_BRACKET.match(source, i + 2)
            if opener is not None:
                close = ']' + opener.group(1) + ']'
                end = source.find(close, i + opener.end())
                i = len(source) if end < 0 else end + len(close)
            else:
                newline = source.find('\n', i)
                i = len(source) if newline < 0 else newline + 1
            continue
        if source[i] in ('"', "'"):
            quote = source[i]
            i += 1
            while i < n:
                if source[i] == '\\' and i + 1 < n:
                    i += 2
                    continue
                if source[i] == quote or source[i] == '\n':
                    i += 1
                    break
                i += 1
            continue
        opener = _LONG_BRACKET.match(source, i) if source[i] == '[' else None
        if opener is not None:
            close = ']' + opener.group(1) + ']'
            end = source.find(close, i + opener.end())
            i = len(source) if end < 0 else end + len(close)
            continue
        match = _IDENTIFIER.match(source, i)
        if match is not None:
            tokens.add(match.group(0))
            i = match.end()
            continue
        i += 1
    return frozenset(tokens)


def record_table_lua_references(record_source: str,
                                table_globals) -> tuple[str, ...]:
    """Case-sensitive table top-level globals referenced by a record source.

    The record's bare identifier tokens (comments/strings stripped) are
    intersected with the table's top-level global names; the result is
    deterministically sorted.  The intersection is deliberately conservative:
    a name that only appears as the record's own local or as AA label text
    still counts (a dependent record stays fail-closed, never a silent nil).
    """
    if not isinstance(record_source, str):
        raise LuaBootstrapError("Record source must be text")
    if not isinstance(table_globals, (set, frozenset, list, tuple)):
        raise LuaBootstrapError("Table globals must be an iterable of names")
    tokens = _lua_identifier_tokens(record_source)
    return tuple(sorted(tokens.intersection(set(table_globals))))


def table_lua_bootstrap_gate(bootstrap_source: str, record_source: str,
                             meta) -> tuple[str, str | None]:
    """Decide one record-Lua activation against the table bootstrap state.

    Returns ('replay', None) when the table source must be replayed into the
    record scope as today (no bootstrap state yet, or the bootstrap executed
    cleanly), ('skip', None) when there is no table source or this record
    references no table-level global, and ('block', reason) when the table
    bootstrap did not execute and the record references table-level globals.
    """
    if not isinstance(bootstrap_source, str):
        raise LuaBootstrapError("Table-Lua source must be text")
    if meta is None:
        # Legacy plan without bootstrap state: keep the pre-bootstrap replay.
        return ('replay', None) if bootstrap_source.strip() else ('skip', None)
    if meta.get('executed') is True:
        return ('replay', None)
    references = record_table_lua_references(record_source,
                                             table_top_level_globals(bootstrap_source))
    if not references:
        return ('skip', None)
    if len(references) == 1:
        label = 'global ' + references[0]
    else:
        label = 'globals ' + ', '.join(references)
    return ('block', TABLE_LUA_RECORD_REFUSAL + label + '.')


def validate_table_lua_meta(meta) -> dict:
    """Strict shape for plan["table_lua"] (both plan gates).

    Exactly the keys executed/reasons/record_scripts_inactive; reasons is a
    bounded, ordered list of non-empty strings; an executed bootstrap carries
    no refusal reasons.
    """
    if (type(meta) is not dict
            or set(meta) != {"executed", "reasons", "record_scripts_inactive"}
            or type(meta["executed"]) is not bool
            or type(meta["reasons"]) is not list
            or len(meta["reasons"]) > MAX_TABLE_LUA_REASONS
            or any(type(reason) is not str or not reason
                   or len(reason) > MAX_TABLE_LUA_REASON_CHARS
                   for reason in meta["reasons"])
            or type(meta["record_scripts_inactive"]) is not int
            or meta["record_scripts_inactive"] < 0
            or (meta["executed"] and meta["reasons"])):
        raise LuaBootstrapError("Invalid table-Lua bootstrap metadata")
    return meta
