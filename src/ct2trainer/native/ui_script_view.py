"""Pure text builders for the trainer row context menu.

``script_preview`` renders the executable source behind a plan entry (the
static Auto Assembler program, the embedded Lua program, the global
allocation program, or the normalized enable/disable operation list),
``entry_assessment`` produces the plain-language "what happens here" read
from plan metadata only, and ``entry_actions`` / ``row_details`` provide
the combined row-details window content (script + assessment + actions
used).  All builders are pure (no Tk, no engine) so the exact dialog text
is unit-testable; ``TrainerWindow`` shows the results in read-only
dialogs and uses the preview result to decide which menu items exist.
"""
from __future__ import annotations

import json
import re

from .ui_layout import STAGED_PENDING, activation_set_summary, staged_card_state

#: Display-only vocabulary of game-facing CE global API names, used by
#: ``lua_apis_used`` for the row-details "Actions used" section.  This is
#: NOT the host's functional allowlist (that lives in ``lua_host.py`` /
#: ``lua_bootstrap.py``); it exists so the UI can show which CE APIs a
#: record's embedded Lua calls without importing the runtime host.  Purely
#: informational - nothing here drives execution or refusals.
CE_ACTION_APIS = frozenset({
    # memory reads / writes
    "readInteger", "readSmallInteger", "readQword", "readFloat",
    "readDouble", "readPointer", "readString", "readBytes",
    "writeInteger", "writeSmallInteger", "writeQword", "writeFloat",
    "writeDouble", "writeString", "writeBytes",
    # address / symbols
    "getAddress", "getAddressSafe", "getAddressOfSymbol",
    "getAddressOfSymbolSafe", "registerSymbol", "unregisterSymbol",
    "getModuleSize", "getProcHandle",
    # process / target
    "openProcess", "attachProcess", "detachProcess", "getOpenProcessID",
    "getProcessIDFromProcessName", "getProcessList", "targetIs64Bit",
    "enumModules", "getCEVersion",
    # scans
    "aobscan", "aobscanmodule", "aobscanregion",
    # input / speedhack
    "isKeyPressed", "getXBox360ControllerState",
    "speedhack_setSpeed", "speedhack_getSpeed",
    # user-facing side effects
    "showMessage", "messageDialog", "executeCodeEx", "fullAccess",
    "shellExecute", "createTimer",
    # strings / table files / AA interaction
    "createStringList", "createStringStream", "findTableFile",
    "readStringLocal", "createTableFile", "autoAssemble",
    # managed resolution
    "LaunchMonoDataCollector", "mono_enumDomains", "mono_findMethod",
    "mono_invoke_method",
})

_CASEFOLD_LOOKUP = {name.casefold(): name for name in CE_ACTION_APIS}
_LUA_CALL_NAME = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")


def lua_apis_used(source: str) -> list[str]:
    """Game-facing CE API names called in an embedded-Lua source.

    Display-only extraction: every identifier directly followed by ``(``
    is matched against ``CE_ACTION_APIS`` (case-insensitive, since CE
    registers first-letter case-flipped variants); method calls on local
    objects (``sl.add(...)``, ``string.match(...)``) and plain Lua stdlib
    calls do not match.  Returns the canonical names, casefold-sorted.
    """
    found = set()
    for match in _LUA_CALL_NAME.finditer(source or ""):
        canonical = _CASEFOLD_LOOKUP.get(match.group(1).casefold())
        if canonical is not None:
            found.add(canonical)
    return sorted(found, key=str.casefold)


def _format_path(path) -> str:
    """The plan path in display form (list or string)."""
    if isinstance(path, list):
        return " / ".join(str(part) for part in path)
    if isinstance(path, str):
        return path
    return ""


def _names(values) -> str:
    return ", ".join(str(value) for value in values)


def script_backing(entry: dict) -> str | None:
    """The executable form carried by the entry, or None.

    Returns ``'program'`` (static Auto Assembler), ``'lua_program'``
    (embedded Lua), ``'global_program'`` (global allocation program) or
    ``'operations'`` (normalized enable/disable operation list).  Blocked
    records carry no executable source by plan contract
    ("Blocked record must have a reason and no executable operations"),
    so they return None and get an assessment without a preview.
    """
    if not isinstance(entry, dict) or entry.get("kind") != "script":
        return None
    program = entry.get("program")
    if isinstance(program, dict) and isinstance(program.get("source"), str):
        return "program"
    lua = entry.get("lua_program")
    if isinstance(lua, dict) and isinstance(lua.get("source"), str):
        return "lua_program"
    global_program = entry.get("global_program")
    if isinstance(global_program, dict) and isinstance(global_program.get("source"), str):
        return "global_program"
    if ((isinstance(entry.get("enable"), list) and entry["enable"])
            or (isinstance(entry.get("disable"), list) and entry["disable"])):
        return "operations"
    return None


def _render_operation(operation: dict) -> str:
    """One normalized plan operation as a human-readable line."""
    op = operation.get("op")
    if op == "scan":
        return (f"aobscan {operation.get('symbol')} "
                f"module={operation.get('module')} pattern={operation.get('pattern')}")
    if op == "define":
        return f"define {operation.get('symbol')} = {operation.get('expression')}"
    if op in ("register", "unregister"):
        verb = "registersymbol" if op == "register" else "unregistersymbol"
        return f"{verb} {operation.get('symbol')}"
    if op in ("assert", "write"):
        verb = "assert" if op == "assert" else "write"
        return f"{verb} {operation.get('address')} = {operation.get('bytes')}"
    return json.dumps(operation, ensure_ascii=False, sort_keys=True)


def script_preview(entry: dict) -> tuple[str, str] | None:
    """(window title, body text) for the entry's executable source.

    ``program`` and ``lua_program`` entries show the raw source exactly as
    it will run; ``global_program`` shows its raw source; ``operations``
    entries show the normalized phases rendered one operation per line.
    Returns None when the entry carries no executable source.
    """
    backing = script_backing(entry)
    if backing is None:
        return None
    label = str(entry.get("label", ""))
    ident = entry.get("id")
    one_shot = bool(entry.get("one_shot"))
    if backing == "program":
        program = entry["program"]
        suffix = " (one-shot)" if one_shot else ""
        title = (f"Script preview - {label} (id {ident}) - "
                 f"Auto Assembler {program.get('bitness', '?')}-bit{suffix}")
        return title, str(program["source"])
    if backing == "lua_program":
        suffix = " (one-shot)" if one_shot else ""
        title = f"Script preview - {label} (id {ident}) - embedded Lua{suffix}"
        return title, str(entry["lua_program"]["source"])
    if backing == "global_program":
        title = f"Script preview - {label} (id {ident}) - global program"
        return title, str(entry["global_program"]["source"])
    lines: list[str] = []
    for phase, key in (("ENABLE", "enable"), ("DISABLE", "disable")):
        operations = entry.get(key) or []
        if not operations:
            continue
        if lines:
            lines.append("")
        lines.append(f"[{phase}]")
        lines.extend(_render_operation(operation) for operation in operations)
    while lines and lines[-1] == "":
        lines.pop()
    title = f"Script preview - {label} (id {ident}) - operation list"
    return title, "\n".join(lines)


def entry_assessment(entry: dict, entries: dict,
                     applied=frozenset(), error: str | None = None) -> str:
    """Plain-language read of the entry from plan metadata (no engine).

    ``applied`` is the set of live entry ids (the engine applied set); it
    decides whether a staged gate is pending or satisfied.  ``error`` is
    the last action error published for the entry, if any.  The text is
    deterministic for a fixed (entry, entries, applied, error) input so
    the tests can pin it exactly.
    """
    label = str(entry.get("label", ""))
    ident = entry.get("id")
    lines = [f"{label} (id {ident})"]
    path = _format_path(entry.get("path"))
    if path:
        lines.append(path)
    lines.append("")

    supported = bool(entry.get("supported"))
    selected = bool(entry.get("selected"))
    staged = entry.get("staged")
    if not supported:
        status = "Status: blocked (converter refused this record)"
    elif not selected:
        status = "Status: not selected (excluded from the trainer build)"
    elif staged and staged_card_state(entry, applied) == STAGED_PENDING:
        status = "Status: staged (pending - providers not active yet)"
    elif staged:
        status = "Status: staged (gate satisfied - providers active)"
    else:
        status = "Status: supported"
    lines.append(status)
    if error:
        lines.append(f"Last error: {error}")
    reason = entry.get("reason")
    if reason:
        lines.append(f"Reason: {reason}")
    if staged:
        provider_labels = staged.get("provider_labels") or ()
        if provider_labels:
            lines.append("Staged: unlocks when active: " + _names(provider_labels))

    kind = entry.get("kind")
    if kind == "script":
        backing = script_backing(entry)
        if backing == "program":
            program = entry["program"]
            lines.append(f"Program: static Auto Assembler ({program.get('bitness', '?')}-bit)")
            lines.append(f"Enable phase: {len(program.get('enable') or [])} operation(s)")
            lines.append(f"Disable phase: {len(program.get('disable') or [])} operation(s)")
            capabilities = program.get("capabilities") or []
            if capabilities:
                lines.append("Capabilities: " + _names(capabilities))
        elif backing == "lua_program":
            lua = entry["lua_program"]
            source = lua.get("source") or ""
            lines.append(f"Program: embedded Lua (AssemblerScript, {lua.get('bitness', '?')}-bit)")
            lines.append(f"Embedded Lua source: {len(source.splitlines())} lines")
        elif backing == "global_program":
            globals_ = entry["global_program"].get("globals") or []
            lines.append(f"Program: global allocation program ({len(globals_)} global allocation(s))")
        elif backing == "operations":
            lines.append(f"Program: operation list ({len(entry.get('enable') or [])} enable / "
                         f"{len(entry.get('disable') or [])} disable operation(s))")
        else:
            lines.append("Program: none (record blocked; no executable source)")
        if entry.get("one_shot"):
            lines.append("One-shot: runs once on activation; no disable phase")
        provides = entry.get("provides") or []
        if provides:
            lines.append("Provides: " + _names(provides))
        requires = entry.get("requires") or []
        if requires:
            lines.append("Requires: " + _names(requires))
    elif kind == "value":
        variable_type = entry.get("variable_type")
        lines.append(f"Type: {variable_type if variable_type else 'value record'}")
        address = entry.get("address")
        if address:
            lines.append(f"Address: {address}")
        if entry.get("show_as_hex"):
            lines.append("Display: hex")
        provides = entry.get("provides") or []
        if provides:
            lines.append("Provides: " + _names(provides))
        requires = entry.get("requires") or []
        if requires:
            lines.append("Requires: " + _names(requires))
    elif kind == "heading":
        lines.append("Kind: group heading (no direct memory action)")
        if entry.get("parent_activation") is not None:
            lines.append("Group toggle: runs the parent-activation cascade on toggle")

    dependency_ids = entry.get("dependency_ids") or []
    if dependency_ids:
        labels = [str((entries.get(i) or {}).get("label") or i) for i in dependency_ids]
        lines.append("Depends on: " + _names(labels))
    provides_cf = {str(symbol).casefold() for symbol in (entry.get("provides") or [])}
    if provides_cf:
        required_by = []
        for other in entries.values():
            if not isinstance(other, dict) or other.get("id") == ident:
                continue
            if any(str(name).casefold() in provides_cf for name in (other.get("requires") or [])):
                required_by.append(str(other.get("label") or other.get("id")))
        if required_by:
            lines.append("Required by: " + _names(required_by))
    if entry.get("activation_sets") is not None:
        summary = activation_set_summary(entry, entries)
        if summary:
            source = (entry.get("activation_sets") or {}).get("source", "unknown")
            lines.append(f"Activation set: {summary} (source: {source})")
    hotkey_count = entry.get("source_hotkey_count")
    if hotkey_count:
        lines.append(f"Source hotkeys: {hotkey_count}")
    if kind == "script":
        lines.append("Runtime verified: " + ("yes" if entry.get("runtime_verified") else "no"))
    return "\n".join(lines)


def _operations_text(enable_operations, disable_operations) -> list[str]:
    """The two normalized phases as rendered operation lines."""
    lines: list[str] = []
    for phase, operations in (("ENABLE", enable_operations),
                              ("DISABLE", disable_operations)):
        operations = operations or []
        if not operations:
            continue
        if lines:
            lines.append("")
        lines.append(f"[{phase}]")
        lines.extend(_render_operation(operation) for operation in operations)
    return lines


def entry_actions(entry: dict) -> str:
    """The concrete actions the trainer performs for this entry.

    Plan metadata only: the normalized enable/disable operation list for
    Auto Assembler programs and plain operation entries, the static AA
    envelope operations plus the CE Lua API calls for embedded-Lua
    records, the global allocations, the memory write for value records
    and the group-activation cascade for flagged group headings.  The
    empty string means the entry performs no direct action (blocked
    records, plain section headings).
    """
    kind = entry.get("kind")
    lines: list[str] = []
    if kind == "script":
        backing = script_backing(entry)
        if backing == "program":
            program = entry["program"]
            lines.extend(_operations_text(program.get("enable"),
                                          program.get("disable")))
            capabilities = program.get("capabilities") or []
            if capabilities:
                lines.append("Capabilities: " + _names(capabilities))
        elif backing == "operations":
            lines.extend(_operations_text(entry.get("enable"),
                                          entry.get("disable")))
        elif backing == "lua_program":
            lua = entry["lua_program"]
            static = lua.get("static_program")
            if isinstance(static, dict):
                lines.extend(_operations_text(static.get("enable"),
                                              static.get("disable")))
            apis = lua_apis_used(lua.get("source") or "")
            if apis:
                lines.append("Lua APIs used: " + _names(apis))
        elif backing == "global_program":
            globals_ = entry["global_program"].get("globals") or []
            lines.append(f"Global allocation program: "
                         f"{len(globals_)} global allocation(s)")
    elif kind == "value":
        variable_type = entry.get("variable_type") or "value"
        address = entry.get("address")
        if address:
            lines.append(f"Write {variable_type} to {address} on Apply")
        else:
            lines.append(f"Write {variable_type} on Apply")
        if entry.get("show_as_hex"):
            lines.append("Display: hex")
    elif kind == "heading":
        if entry.get("parent_activation") is not None:
            lines.append("Group toggle: runs the parent-activation cascade "
                         "on toggle")
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def row_details(entry: dict, entries: dict,
                applied=frozenset(), error: str | None = None) -> dict:
    """Combined content of the row-details window (pure, no Tk).

    One window for the whole row read: the raw script source (when the
    entry carries an executable one), the plain-language assessment
    (what it does / what is known, via ``entry_assessment``) and the
    concrete actions used (via ``entry_actions``).  ``script`` is None for
    entries without an executable source; ``actions`` is the empty string
    when the entry performs no direct action.  Deterministic for a fixed
    (entry, entries, applied, error) input so the tests can pin it.
    """
    label = str(entry.get("label", ""))
    preview = script_preview(entry)
    script = None
    if preview is not None:
        script = {"title": preview[0], "body": preview[1]}
    return {
        "title": f"Row details - {label} (id {entry.get('id')})",
        "script": script,
        "assessment": entry_assessment(entry, entries, applied, error),
        "actions": entry_actions(entry),
    }
