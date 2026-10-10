"""Compile CT presentation and a bounded subset into a native JSON plan.

The existing first-party XML inspector supplies bounded metadata. Source bytes
are rechecked before script extraction. No CE implementation or binary is used,
and original Lua, hotkeys, forms and embedded files are never executed.
"""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
import math
import struct
import xml.etree.ElementTree as ET

from ..table import (MAX_ENTRIES, MAX_TABLE_BYTES, SIMPLE_VALUE_TYPES, Entry,
                     numeric_literal_safe, read_table)
from .aa import (AAError, MAX_OPERATIONS, MAX_PATCH_BYTES, compile_one_shot,
                 compile_script, expression_symbols, normalize_pattern,
                 validate_expression, validate_one_shot_guards,
                 validate_patch_guards, validate_symbol)
from .aa_blocks import BlockStructureError, extract_label_definitions
from .address_expression import (AddressExpressionError,
                                expression_symbols as advanced_expression_symbols,
                                parse_expression)
from .lua_program import (LuaProgramError, has_lua_sections, prepare_lua_program,
                          validate_lua_program)
from .value_links import RecursiveSetValueError, recursive_write_closure
from .value_types import (ValueTypeError, parse_profile_value,
                          prepare_value_profile, validate_value_profile)


from .architecture import (ArchitectureError, plan_architecture, prepare_architecture)


_PROFILE_VALUE_TYPES = {"Array of byte", "Binary", "String"}


class NativeCompileError(ValueError):
    """Invalid compiler inputs or a malformed serialized plan."""


def validate_process_name(name: str) -> str:
    if (not isinstance(name, str) or name != name.strip() or not name
            or len(name) > 255 or name in {".exe", "..exe"}
            or not name.casefold().endswith(".exe")
            or any(character in name for character in '<>:"/\\|?*')
            or any(ord(character) < 32 for character in name)):
        raise NativeCompileError("Process name must be an exact .exe basename without a path.")
    return name


def _block(entry: dict, reason: str) -> None:
    entry.update(kind="blocked", supported=False, reason=reason)
    entry.pop("enable", None)
    entry.pop("disable", None)
    entry.pop("program", None)
    entry.pop("lua_program", None)
    entry.pop("global_program", None)
    entry.pop("value_profile", None)
    entry["provides"] = []


def _offsets(offsets: tuple[str, ...]) -> list[int]:
    if len(offsets) > 32:
        raise AAError("Pointer chains are limited to 32 offsets.")
    result = []
    for text in offsets:
        if len(text) > 18 or re.fullmatch(r"-?(?:0x)?[0-9a-fA-F]+", text) is None:
            raise AAError("Pointer offset must be a hexadecimal integer literal.")
        negative = text.startswith("-")
        number = int(text.removeprefix("-").removeprefix("0x"), 16)
        if number > 0x7FFFFFFFFFFFFFFF:
            raise AAError("Pointer offset exceeds signed 64 bits.")
        result.append(-number if negative else number)
    return result


def _effective_address(source: Entry, sources: dict[int, Entry], stack: tuple[int, ...] = ()) -> str:
    """Flatten relative addresses and XML pointer offsets, without reading memory."""
    if source.id in stack or len(stack) >= 64:
        raise AAError("Inherited address ancestry is cyclic or exceeds 64 records.")
    raw = source.address or ""
    if not raw.strip():
        raise AAError("Value record has no address expression.")
    raw = raw.strip()
    try:
        parse_expression(raw)
    except AddressExpressionError as exc:
        raise AAError(str(exc)) from exc
    if raw.startswith(("+", "-")):
        parent_id = source.parent_id
        visited = set(stack) | {source.id}
        parent_source = None
        while parent_id is not None:
            if parent_id in visited or len(visited) >= 64:
                raise AAError("Inherited address ancestry is cyclic or exceeds 64 records.")
            visited.add(parent_id)
            candidate = sources.get(parent_id)
            if candidate is None:
                raise AAError("Relative address ancestor is missing.")
            if candidate.address and candidate.address.strip():
                parent_source = candidate
                break
            if not candidate.is_group_header:
                raise AAError("Relative address cannot skip an addressless script/value ancestor.")
            if candidate.pointer_offsets:
                raise AAError("Relative address cannot skip an addressless heading with pointer offsets; its inherited base is ambiguous.")
            parent_id = candidate.parent_id
        if parent_source is None:
            raise AAError("Relative address has no address-bearing ancestor.")
        base = _effective_address(parent_source, sources, stack + (source.id,))
        raw = "(" + base + ")" + raw
    for offset in reversed(_offsets(source.pointer_offsets)):
        raw = "[" + raw + "]" + (f"+{offset:X}" if offset > 0 else f"-{abs(offset):X}" if offset < 0 else "")
    try:
        parse_expression(raw)
    except AddressExpressionError as exc:
        raise AAError(str(exc)) from exc
    return raw


def _dropdown(entry: Entry, entries: tuple[Entry, ...], value_profile: dict | None = None) -> dict:
    source = entry
    if entry.dropdown_link:
        if value_profile is not None:
            raise AAError("Linked dropdowns for byte arrays and bit fields are unsupported.")
        matches = [candidate for candidate in entries
                   if candidate.label.casefold() == entry.dropdown_link.casefold()]
        if len(matches) != 1:
            raise AAError("Dropdown link target is missing or ambiguous.")
        source = matches[0]
        if source.dropdown_link:
            raise AAError("Chained dropdown links are unsupported.")
    choices = []
    for value, label in source.dropdown_choices:
        if value == "*":
            continue  # Placeholder is metadata, never a selectable memory value.
        if not _value_literal_safe(value, entry.variable_type, entry.show_as_hex,
                                   entry.show_as_signed, value_profile):
            raise AAError("Dropdown contains an unsupported value expression.")
        choices.append({"value": value, "description": label})
    if source.dropdown_read_only and not choices:
        raise AAError("Read-only dropdown has no concrete literal choices.")
    result = {"choices": choices, "read_only": source.dropdown_read_only}
    if entry.dropdown_link:
        result["link_target_id"] = source.id
    return result


def _string_dropdown(entry: Entry, nodes: dict, profile: dict) -> dict:
    """Preserve raw XML String literals; numeric inspector trimming is unsuitable."""
    if entry.dropdown_link:
        raise AAError('Linked String dropdowns require a separate literal profile.')
    element=nodes[entry.id].find('DropDownList')
    if element is None:return {'choices':[],'read_only':False}
    flag=element.attrib.get('ReadOnly','0')
    if flag not in {'0','1'}:raise AAError('String dropdown ReadOnly must be 0 or 1.')
    choices=[]
    for line in (element.text or '').split('\n'):
        if ':' not in line:
            if line.strip():raise AAError('String dropdown items require explicit literal:description lines.')
            continue
        value,description=line.split(':',1)
        if value=='*':
            raise AAError("String dropdown '*' requires an explicit placeholder/literal contract.")
        if not _value_literal_safe(value,'String',entry.show_as_hex,entry.show_as_signed,profile):
            raise AAError('String dropdown contains an unsupported literal.')
        choices.append({'value':value,'description':description})
    if flag=='1' and not choices:
        raise AAError('Read-only String dropdown has no concrete literal choices.')
    return {'choices':choices,'read_only':flag=='1'}


def _value_literal_safe(value: str, value_type: str, hexadecimal: bool,
                        signed: bool | None, value_profile: dict | None = None) -> bool:
    if value_profile is None:
        return _native_literal_safe(value, value_type, hexadecimal, signed)
    try:
        # A synthetic snapshot is only for literal validation during conversion;
        # the runtime must reread actual adjacent bits before every write.
        parse_profile_value(value_profile, value, b"\0" * value_profile["size"])
    except ValueTypeError:
        return False
    return True


def _compile_value_address(entry: dict, source: Entry, sources: dict[int, Entry],
                           allow_empty: bool = False) -> None:
    if allow_empty and not (source.address or "").strip():
        if source.pointer_offsets:
            raise AAError("An addressless placeholder cannot carry pointer offsets.")
        entry["address"] = ""
        return
    try:
        entry["address"] = validate_expression(source.address or "")
        entry["pointer_offsets"] = _offsets(source.pointer_offsets)
        entry["requires"] = expression_symbols(entry["address"])
    except AAError:
        entry["address"] = _effective_address(source, sources)
        entry["address_profile"] = "expression/v1"
        entry["pointer_offsets"] = []
        required = advanced_expression_symbols(entry["address"])
        for symbol in required:
            validate_symbol(symbol)
        entry["requires"] = required


def _validate_value_address(entry: dict, allow_empty: bool = False) -> None:
    profile = entry.get("address_profile")
    if allow_empty and entry.get("address") == "" and profile is None:
        address_symbols = []
        if entry.get("pointer_offsets") != []:
            raise NativeCompileError("An addressless placeholder cannot carry pointer offsets.")
    elif profile is None:
        validate_expression(entry.get("address"))
        address_symbols = expression_symbols(entry["address"])
    elif profile == "expression/v1":
        parse_expression(entry.get("address"))
        if entry["address"].lstrip().startswith(("+", "-")):
            raise NativeCompileError("Expression-profile addresses must have resolved inherited bases.")
        if entry.get("pointer_offsets") != [] or not isinstance(entry.get("source_address"), str):
            raise NativeCompileError("Expression-profile values require flattened offsets and original address metadata.")
        address_symbols = advanced_expression_symbols(entry["address"])
    else:
        raise NativeCompileError("Unknown native value address profile.")
    if {symbol.casefold() for symbol in entry["requires"]} != {symbol.casefold() for symbol in address_symbols} or entry["provides"]:
        raise NativeCompileError("Value symbol dependencies do not match the address.")
    offsets = entry.get("pointer_offsets")
    if (not isinstance(offsets, list) or len(offsets) > 32
            or any(type(offset) is not int or abs(offset) > 0x7FFFFFFFFFFFFFFF for offset in offsets)):
        raise NativeCompileError("Invalid pointer offsets.")


def _native_literal_safe(value: str, value_type: str, hexadecimal: bool,
                         signed: bool | None) -> bool:
    """Native numeric policy: missing signed means unsigned; hex is bit-pattern."""
    if not isinstance(value, str) or not numeric_literal_safe(
            value, value_type, hexadecimal, False if hexadecimal else signed is True):
        return False
    if value_type in {"Float", "Double"}:
        try:
            code = "f" if value_type == "Float" else "d"
            return math.isfinite(struct.unpack("<" + code, struct.pack("<" + code, float(value)))[0])
        except (ValueError, OverflowError, struct.error):
            return False
    bits = {"Byte": 8, "2 Bytes": 16, "4 Bytes": 32, "8 Bytes": 64}[value_type]
    number = int(value, 16 if hexadecimal else 10)
    native_signed = signed is True and not hexadecimal
    return (-(1 << (bits - 1)) if native_signed else 0) <= number <= (1 << (bits - int(native_signed))) - 1


def _dependencies(entries: list[dict], selected: set[int] | None = None) -> None:
    """Reject missing/ambiguous symbol providers and their dependent records."""
    providers: dict[str, list[dict]] = {}
    for entry in entries:
        if entry["supported"] and entry["kind"] == "script":
            for symbol in entry["provides"]:
                providers.setdefault(symbol.casefold(), []).append(entry)
    by_id = {entry["id"]: entry for entry in entries}
    for symbol, candidates in providers.items():
        if len(candidates) > 1:
            from .global_alloc import shared_provider_compatible
            if shared_provider_compatible(candidates,symbol):
                continue
            chosen=[candidate for candidate in candidates if selected is not None and candidate['id'] in selected]
            if chosen and shared_provider_compatible(chosen,symbol):
                # Explicit global selection can exclude a table's older,
                # ordinary provider alternative. It cannot select both or
                # silently import an unselected conflicting definition.
                for candidate in candidates:
                    if candidate not in chosen:
                        _block(candidate,f"Unselected symbol provider conflicts with the selected shared global: {symbol}.")
                continue
            for entry in candidates:
                _block(entry, f"Symbol provider is ambiguous: {symbol}.")
    while True:
        changed = False
        for entry in entries:
            if not entry["supported"] or entry["kind"] == "heading":
                continue
            entry["dependency_ids"] = []
            for symbol in entry["requires"]:
                candidates = [candidate for candidate in providers.get(symbol.casefold(), [])
                              if candidate["supported"]]
                if len(candidates) != 1:
                    _block(entry, f"Required symbol has no unique supported provider: {symbol}.")
                    changed = True
                    break
                entry["dependency_ids"].append(candidates[0]["id"])
        if not changed:
            break
    # Symbol dependencies, not XML parents, determine activation order.
    visiting: set[int] = set()
    complete: set[int] = set()
    cyclic: set[int] = set()
    stack: list[int] = []

    for entry in entries:
        if not entry["supported"] or entry["id"] in complete:
            continue
        frames = [(entry["id"], False)]
        while frames:
            entry_id, exiting = frames.pop()
            if exiting:
                stack.pop()
                visiting.remove(entry_id)
                complete.add(entry_id)
                continue
            if entry_id in visiting:
                cyclic.update(stack[stack.index(entry_id):])
                continue
            if entry_id in complete:
                continue
            if len(stack) >= 64:
                _block(by_id[entry_id], "Symbol dependency chain exceeds 64 levels.")
                continue
            visiting.add(entry_id)
            stack.append(entry_id)
            frames.append((entry_id, True))
            for dependency_id in reversed(by_id[entry_id].get("dependency_ids", [])):
                frames.append((dependency_id, False))
    for entry_id in cyclic:
        _block(by_id[entry_id], "Symbol dependency cycle is unsupported.")
    changed = True
    while changed:
        changed = False
        for entry in entries:
            if entry["supported"] and any(not by_id[dependency]["supported"]
                                          for dependency in entry.get("dependency_ids", [])):
                _block(entry, "Required symbol provider is blocked.")
                changed = True


def compile_table(path: str | Path, process_name: str, title: str | None = None,
                  selected_ids: list[int] | set[int] | tuple[int, ...] | None = None,
                  *, architecture: str = "x64") -> dict:
    """Return all records with explicit supported/blocked states and reasons."""
    validate_process_name(process_name)
    try:
        target_architecture = prepare_architecture(architecture)
    except ArchitectureError as exc:
        raise NativeCompileError(str(exc)) from exc
    bitness = target_architecture["bitness"]
    table = read_table(path)
    data = table.source.read_bytes()
    if len(data) > MAX_TABLE_BYTES or sha256(data).hexdigest() != table.source_sha256:
        raise NativeCompileError("CT source changed during compilation.")
    root = ET.fromstring(data)  # Identical to the bounded, DTD-free reader input.
    nodes = {int(node.findtext("ID") or "-1"): node
             for node in root.findall(".//CheatEntry")}
    scripts = {identifier: node.findtext("AssemblerScript") or ""
               for identifier, node in nodes.items()}
    # Table-level nested-assembly label registry: `name:` definitions inside
    # AssemblerScript records are shared candidates for autoAssemble()/
    # autoasm() invocations in other records.  A name defined by more than
    # one record is ambiguous and refused (the invoking record is blocked
    # with the resolver's visible unknown-label reason, never first-wins).
    # Records whose own definitions are unresolvable (duplicate labels) do
    # not contribute labels and receive no registry of their own.
    label_owner: dict[str, int] = {}
    table_labels: dict[str, tuple[str, str]] = {}
    for record_id in sorted(scripts):
        text = scripts[record_id]
        if not text or not text.strip():
            continue
        try:
            definitions = extract_label_definitions(text)
        except BlockStructureError:
            continue
        for name, body in definitions.items():
            key = name.casefold()
            owner = label_owner.get(key)
            if owner is None:
                label_owner[key] = record_id
                table_labels[key] = (name, body)
            elif owner != record_id:
                label_owner.pop(key, None)
                table_labels.pop(key, None)
    title = title or f"{table.source.stem} — Native Trainer"
    if not isinstance(title, str) or len(title) > 512 or any(ord(ch) < 32 for ch in title):
        raise NativeCompileError("Trainer title must be printable text up to 512 characters.")
    known_ids = {entry.id for entry in table.entries}
    if selected_ids is not None and (any(type(item) is not int for item in selected_ids)
                                     or not set(selected_ids) <= known_ids):
        raise NativeCompileError("Selection contains unknown or noninteger CT record IDs.")
    selected = set(known_ids if selected_ids is None else selected_ids)
    bootstrap = None
    if table.has_table_lua:
        from .lua_bootstrap import prepare_lua_bootstrap
        bootstrap = prepare_lua_bootstrap(root.findtext('LuaScript') or '')
    from .nth_aob import prepare_helper_contract
    nth_helper=prepare_helper_contract(bootstrap) if bootstrap is not None else None
    entries: list[dict] = []
    sources = {source.id: source for source in table.entries}
    for source in table.entries:
        entry = {"id": source.id, "label": source.label, "path": source.path,
                 "parent_id": source.parent_id, "source_kind": source.kind,
                 "kind": "heading" if source.is_group_header else source.kind,
                 "supported": True, "reason": "", "selected": source.id in selected,
                 "address": source.address or "", "source_address": source.address or "", "pointer_offsets": [],
                 "variable_type": source.variable_type, "show_as_hex": source.show_as_hex,
                 "show_as_signed": source.show_as_signed,
                 "dropdown": {"choices": [], "read_only": False},
                 "requires": [], "provides": [], "dependency_ids": [],
                 "source_hotkey_count": source.hotkey_count,
                 "runtime_verified": False}
        entries.append(entry)
        try:
            if source.is_group_header:
                entry["reason"] = "Navigation heading; CE group activation is not executed."
                if source.has_children and any(option in source.options for option in
                                               ("moActivateChildrenAsWell", "moDeactivateChildrenAsWell", "moBindActivation")):
                    # Parent/child activation propagation (AP-07 stage 3):
                    # the tested flag classes from the CT options.  Both
                    # flags make children follow the parent unconditionally;
                    # activate-only children keep their own wish;
                    # deactivate-only turns off only explicitly active
                    # children; moBindActivation has no derived contract and
                    # stays a named ActivationBlocked refusal.  The flag
                    # class inherits down the whole subtree of the flagged
                    # parent (computed after the selection closure below).
                    if "moBindActivation" in source.options:
                        entry["parent_mo_bind"] = True
                        entry["reason"] += (" moBindActivation has no derived contract; activation "
                                            "stays blocked (named ActivationBlocked refusal).")
                    elif ("moActivateChildrenAsWell" in source.options
                          and "moDeactivateChildrenAsWell" in source.options):
                        flag = "required_dependency"
                    elif "moActivateChildrenAsWell" in source.options:
                        flag = "direct_activation"
                    else:
                        flag = "collective_off"
                    if "parent_mo_bind" not in entry:
                        entry["parent_activation"] = flag
                        entry["reason"] += (" Native parent activation: " + flag
                                            + " flag class applies to the whole subtree.")
                continue
            if source.has_children and any(option in source.options for option in
                                           ("moActivateChildrenAsWell", "moDeactivateChildrenAsWell", "moBindActivation")):
                raise AAError("Parent/child activation propagation is unsupported.")
            if source.kind == "script":
                # Async records (CT Async="1") keep their regular profile; the
                # lifecycle marker is attached after dependency analysis (see
                # async_ids pass below).
                if has_lua_sections(scripts[source.id]):
                    program = prepare_lua_program(scripts[source.id], process_name, bitness=bitness,nth_aob_helper=nth_helper)
                    entry.update(lua_program=program, requires=program['requires'], provides=program['provides'],
                                 enable=[], disable=[], one_shot=bool(program.get('one_shot', False)),
                                 reason="Native Lua/AA; Lua runs during this record's owned activation.")
                    # Static luaCall plan: pure-AA records whose luaCall
                    # expressions fit the pinned single-call grammar carry a
                    # deterministic plan report, which the engine gates behind
                    # an injected LuaCallBinding at activation time.
                    # Expressions outside that grammar (multi-statement calls,
                    # function definitions, return expressions) stay in the
                    # Lua program profile domain: no plan, no gate, existing
                    # host execution behavior unchanged.
                    from .aa_luacall import (LuaCallError,
                                             analyze_luacall_program, has_luacall)
                    if has_luacall(scripts[source.id]):
                        try:
                            luacall_plan = analyze_luacall_program(scripts[source.id])
                        except LuaCallError:
                            pass
                        else:
                            if luacall_plan.operations:
                                entry['lua_call_plan'] = luacall_plan.report()
                    continue
                from .global_alloc import has_global_alloc,prepare_global_program
                if has_global_alloc(scripts[source.id]):
                    program=prepare_global_program(scripts[source.id],process_name,bitness=bitness)
                    if program.get('staged_ops'):
                        reason=('Native shared RW globals with staged readmem '
                                'pairs; original target bytes are captured at '
                                'enable and restored at disable; changed '
                                'reinitialization and unpaired readmem globals '
                                'remain blocked.')
                    else:
                        reason=('Native shared literal RW globals; changed '
                                'reinitialization and readmem globals remain '
                                'blocked.')
                    entry.update(global_program=program,requires=program['requires'],provides=program['provides'],
                                 enable=[],disable=[],reason=reason)
                    continue
                try:
                    entry.update(compile_script(scripts[source.id]))
                except AAError as bounded_error:
                    one_shot = None
                    try:
                        one_shot = compile_one_shot(scripts[source.id])
                    except AAError:
                        pass
                    if one_shot is not None:
                        entry.update(one_shot=True, requires=one_shot['requires'], provides=one_shot['provides'],
                                     enable=one_shot['enable'], disable=one_shot['disable'],
                                     reason='Native one-shot; guarded writes are applied once with no disable phase.')
                        continue
                    from .aa_program import prepare_program
                    labels_arg = None
                    if table_labels:
                        try:
                            own_keys = {name.casefold() for name in extract_label_definitions(scripts[source.id])}
                        except BlockStructureError:
                            own_keys = None
                        if own_keys is not None:
                            filtered = {key: value for key, value in table_labels.items() if key not in own_keys}
                            if filtered:
                                labels_arg = {value[0]: value[1] for value in filtered.values()}
                    try:
                        program = prepare_program(scripts[source.id], process_name, bitness=bitness,
                                                  labels=labels_arg)
                    except AAError as program_error:
                        raise AAError(str(bounded_error) + ' Native assembly: ' + str(program_error)) from program_error
                    if program.get('one_shot', False):
                        entry.update(program=program, requires=program['requires'], provides=program['provides'],
                                     enable=[], disable=[], one_shot=True,
                                     reason='Native one-shot assembly; applied once with no disable phase.')
                    else:
                        entry.update(program=program, requires=program['requires'], provides=program['provides'],
                                     enable=[], disable=[], reason='Native assembly; activation requires a verified target safe point.')
            elif source.kind == "value" or source.variable_type in _PROFILE_VALUE_TYPES:
                if source.variable_type not in SIMPLE_VALUE_TYPES | _PROFILE_VALUE_TYPES:
                    if source.variable_type == "Custom":
                        name = source.custom_type_name or "(no name)"
                        if source.custom_type_known:
                            raise AAError(
                                f"Custom value type '{name}' is statically defined; the "
                                "native converter write gate is not implemented yet (AP-08.3).")
                        raise AAError(
                            f"Custom value type '{name}' has no static definition; blocked "
                            "until a converter/write gate exists (AP-08.3).")
                    raise AAError(f"Unsupported value type: {source.variable_type}.")
                if source.show_as_hex and source.variable_type in {"Float", "Double"}:
                    raise AAError("Hexadecimal floating-point bit patterns are unsupported.")
                # moRecursiveSetValue parents compile like ordinary value
                # records; the deterministic write closure is emitted as
                # entry["recursive_value"] in the post-pass below, where the
                # final supported/selected state is known.
                if source.variable_type in _PROFILE_VALUE_TYPES:
                    properties = {key: nodes[source.id].findtext(key)
                                  for key in ("ByteLength", "BitStart", "BitLength", "ShowAsBinary", "Length", "Unicode", "CodePage", "ZeroTerminate")}
                    properties.update(ShowAsHex=source.show_as_hex, ShowAsSigned=source.show_as_signed)
                    if source.variable_type == 'String':
                        properties={key:value for key,value in properties.items() if value is not None}
                    entry["value_profile"] = prepare_value_profile(source.variable_type, properties)
                    if not entry["value_profile"]["actionable"]:
                        entry.update(kind="heading", reason=entry["value_profile"]["reason"])
                        _compile_value_address(entry, source, sources, allow_empty=True)
                        continue
                    entry["kind"] = "value"
                _compile_value_address(entry, source, sources)
                entry["dropdown"] = (_string_dropdown(source,nodes,entry['value_profile'])
                                     if source.variable_type=='String'
                                     else _dropdown(source, table.entries, entry.get("value_profile")))
            else:
                raise AAError("Record has no implemented native action or address.")
        except (AAError, LuaProgramError, ValueTypeError) as exc:
            _block(entry, str(exc))
    async_ids = {source.id for source in table.entries
                 if source.kind == "script" and source.async_script}
    _dependencies(entries,selected)
    # Async records (CT Async="1") keep their regular profile. The lifecycle
    # marker is attached after dependency analysis so only entries that are
    # still supported in their final state carry it; every supported shape
    # (Lua, global, one-shot, program, byte patch) gets the same contract
    # for the engine, independent of the branch that prepared it.
    for entry in entries:
        if entry["id"] in async_ids and entry["supported"]:
            entry["async"] = True
            prefix = entry["reason"] + " " if entry["reason"] else ""
            entry["reason"] = prefix + (
                "Async activation: runs only after a confirmed attach, "
                "pending until the effect is confirmed."
            )
    by_id = {entry["id"]: entry for entry in entries}
    pending = list(selected)
    while pending:
        current = by_id[pending.pop()]
        needed = current.get("dependency_ids", []) + ([current["parent_id"]] if current["parent_id"] is not None else [])
        for entry_id in needed:
            if entry_id not in selected:
                selected.add(entry_id)
                pending.append(entry_id)
    for entry in entries:
        entry["selected"] = entry["id"] in selected
    # moRecursiveSetValue parents carry their deterministic write closure
    # (deepest-first, ties by ascending ID, target last) as byte-verifiable
    # plan metadata; the engine replays it through the value runtime at
    # set-value time.  The closure follows the final supported/selected
    # state, so it is computed here, after dependency analysis and the
    # selection closure.
    for entry in entries:
        if (entry["kind"] != "value" or not entry["supported"] or not entry["selected"]
                or "moRecursiveSetValue" not in sources[entry["id"]].options):
            continue
        try:
            entry["recursive_value"] = {"write_ids": recursive_write_closure(by_id, entry["id"])}
        except RecursiveSetValueError as exc:
            _block(entry, str(exc))
    # Parent/child activation (AP-07 stage 3): a flagged heading routes its
    # whole selected/supported subtree through the tested activation policy;
    # the flagged parent's class inherits down the entire subtree, while
    # unsupported or unselected descendants stay outside the topology.
    # Markers that end up without any cascade target are dropped, so the
    # plan only promises activation where the engine has targets.
    children_by_parent = {}
    for entry in entries:
        if entry["parent_id"] is not None:
            children_by_parent.setdefault(entry["parent_id"], []).append(entry["id"])
    parent_relations = {}
    for entry in entries:
        flag = entry.get("parent_activation")
        if (flag is None or entry["kind"] != "heading"
                or not entry["supported"] or not entry["selected"]):
            continue
        children = {}
        stack = [entry["id"]]
        while stack:
            node_id = stack.pop()
            for child_id in children_by_parent.get(node_id, ()):
                child = by_id[child_id]
                if child["supported"] and child["selected"]:
                    children[child_id] = flag
                stack.append(child_id)
        if children:
            parent_relations[entry["id"]] = children
    for entry in entries:
        # A flagged parent without any supported+selected cascade target
        # promises nothing, so it stays a plain navigation heading.  A
        # moBindActivation marker is never dropped: the tested contract is a
        # visible named refusal, whether or not the group sits in a cascade.
        if entry.get("parent_activation") is not None and entry["id"] not in parent_relations:
            entry.pop("parent_activation")
            entry["reason"] = "Navigation heading; CE group activation is not executed."
    warnings = []
    omitted = []
    if table.has_table_lua:
        warnings.append("Table Lua is not executed on load. Read-only helpers replay in each Lua activation; top-level writes, callbacks and unsupported APIs block activation.")
    for section in table.sections:
        if section.name not in {"CheatEntries", "LuaScript"}:
            omitted.append(section.name)
    if omitted:
        warnings.append("Table-level sections not interpreted: " + ", ".join(sorted(set(omitted))) + ".")
    if any(entry.hotkey_count for entry in table.entries):
        warnings.append("Original CE record hotkeys are metadata only and are not registered.")
    identity = json.dumps({"engine": "ct2trainer", "schema": 2,
                           "target_architecture": target_architecture,
                           "table_sha256": table.source_sha256,
                           "process_name": process_name.casefold(), "selected_ids": sorted(selected)},
                          sort_keys=True, separators=(",", ":")).encode("utf-8")
    plan = {"schema": 2, "engine": "ct2trainer", "table_sha256": table.source_sha256,
            "target_architecture": target_architecture,
            "table_version": table.table_version, "source_name": table.source.name,
            "process_name": process_name, "title": title,
            "trainer_id": sha256(identity).hexdigest()[:16], "entries": entries,
            "selected_ids": sorted(selected), "warnings": warnings,
            "numeric_policy": {"missing_signed": "unsigned", "hexadecimal": "unsigned-bit-pattern"},
            "ignored_sections": sorted(set(omitted)),
            "counts": {"total": len(entries), "supported": sum(entry["supported"] for entry in entries),
                       "actionable": sum(entry["supported"] and entry["kind"] in {"script", "value"} for entry in entries),
                       "blocked": sum(not entry["supported"] for entry in entries),
                       "headings": sum(entry["kind"] == "heading" for entry in entries)},
            "blocked_reasons": dict(Counter(entry["reason"] for entry in entries if not entry["supported"])),
            "runtime_verified": False}
    if bootstrap is not None:
        plan['lua_bootstrap'] = bootstrap
    if parent_relations:
        plan["parent_relations"] = {str(parent_id): {str(child_id): flag
                                                     for child_id, flag in children.items()}
                                    for parent_id, children in sorted(parent_relations.items())}
    validate_plan(plan)
    return plan


def validate_plan(plan: dict) -> None:
    """Validate serialized action boundaries before a runtime consumes a plan."""
    if not isinstance(plan, dict) or type(plan.get("schema")) is not int or plan["schema"] not in {1, 2} or plan.get("engine") != "ct2trainer":
        raise NativeCompileError("Unsupported native plan schema or engine.")
    validate_process_name(plan.get("process_name"))
    try:
        target_architecture = plan_architecture(plan)
    except ArchitectureError as exc:
        raise NativeCompileError(str(exc)) from exc
    if 'lua_bootstrap' in plan:
        from .lua_bootstrap import validate_lua_bootstrap
        validate_lua_bootstrap(plan['lua_bootstrap'])
    for name, size in (("table_sha256", 64), ("trainer_id", 16)):
        if not isinstance(plan.get(name), str) or re.fullmatch("[0-9a-f]{" + str(size) + "}", plan[name]) is None:
            raise NativeCompileError(f"Invalid native plan {name}.")
    entries = plan.get("entries")
    if not isinstance(entries, list) or not entries or len(entries) > MAX_ENTRIES:
        raise NativeCompileError("Plan entries must be a bounded list.")
    ids: set[int] = set()
    try:
        for entry in entries:
            if not isinstance(entry, dict) or type(entry.get("id")) is not int or entry["id"] < 0 or entry["id"] in ids:
                raise NativeCompileError("Plan record IDs must be unique nonnegative integers.")
            ids.add(entry["id"])
            if entry.get("kind") not in {"script", "value", "heading", "blocked"} or type(entry.get("supported")) is not bool:
                raise NativeCompileError("Invalid native record kind or supported flag.")
            if (entry["kind"] == "blocked") != (entry["supported"] is False):
                raise NativeCompileError("Blocked records must be unsupported.")
            if "async" in entry:
                if (type(entry["async"]) is not bool or entry["async"] is not True
                        or entry["kind"] != "script" or not entry["supported"]):
                    raise NativeCompileError("Invalid async record marker.")
            for key in ("label", "path", "reason"):
                if not isinstance(entry.get(key), str):
                    raise NativeCompileError(f"Record {key} must be text.")
            if len(entry["label"]) > 10000:
                raise NativeCompileError("Record labels exceed the 10,000-character native runtime bound.")
            for key in ("requires", "provides"):
                if not isinstance(entry.get(key), list) or len(entry[key]) > MAX_OPERATIONS:
                    raise NativeCompileError("Symbol requirements/providers must be bounded lists.")
                for symbol in entry[key]:
                    validate_symbol(symbol)
                if len({symbol.casefold() for symbol in entry[key]}) != len(entry[key]):
                    raise NativeCompileError("Duplicate symbol requirement/provider.")
            if ('program' in entry or 'lua_program' in entry) and (not entry['supported'] or entry['kind'] != 'script'):
                raise NativeCompileError("Executable source profiles require a supported script record.")
            if sum(key in entry for key in ('program','lua_program','global_program')) > 1:
                raise NativeCompileError("A script cannot carry both native assembly and Lua source profiles.")
            if 'global_program' in entry and (not entry['supported'] or entry['kind']!='script'):
                raise NativeCompileError('Global profiles require a supported script record.')
            value_profile = entry.get("value_profile")
            if "value_profile" in entry:
                if not entry["supported"] or entry["kind"] not in {"value", "heading"}:
                    raise NativeCompileError("Value profiles require a supported value or placeholder heading.")
                validate_value_profile(value_profile)
                if (entry.get("variable_type") != value_profile["variable_type"]
                        or type(entry.get("show_as_hex")) is not bool
                        or entry.get("show_as_signed") is not None and type(entry["show_as_signed"]) is not bool
                        or entry["show_as_hex"] != value_profile["properties"]["ShowAsHex"]
                        or (entry.get("show_as_signed") is True) != value_profile["properties"]["ShowAsSigned"]
                        or not isinstance(entry.get("source_address"), str)):
                    raise NativeCompileError("Value profile type/display flags do not match the record.")
                if (entry["kind"] == "value") != value_profile["actionable"]:
                    raise NativeCompileError("Only positive value profiles may be writable value records.")
                if any(key in entry for key in ("enable", "disable", "program", "lua_program")):
                    raise NativeCompileError("Value profiles cannot carry executable script operations.")
            if not entry["supported"]:
                if not entry["reason"] or entry.get("enable") or entry.get("disable"):
                    raise NativeCompileError("Blocked record must have a reason and no executable operations.")
                continue
            if entry["kind"] == "script":
                if 'global_program' in entry:
                    from .global_alloc import validate_global_program
                    profile=validate_global_program(entry['global_program'])
                    if (profile['bitness']!=target_architecture['bitness'] or profile['process_name']!=plan['process_name']
                            or entry['provides']!=profile['provides'] or entry['requires']!=profile['requires']
                            or entry.get('enable')!=[] or entry.get('disable')!=[]):
                        raise NativeCompileError('Global metadata differs from its original source and target context.')
                    continue
                if 'lua_program' in entry:
                    validate_lua_program(entry['lua_program'])
                    if entry['lua_program']['bitness'] != target_architecture['bitness']:
                        raise NativeCompileError('Lua profile differs from the declared target architecture.')
                    if 'nth_aob_helper' in entry['lua_program']:
                        from .nth_aob import prepare_helper_contract
                        actual_helper=(prepare_helper_contract(plan['lua_bootstrap'])
                                       if 'lua_bootstrap' in plan else None)
                        if entry['lua_program']['nth_aob_helper']!=actual_helper:
                            raise NativeCompileError('Nth-AOB table helper is not bound to the actual table bootstrap.')
                    if (entry['lua_program']['process_name'] != plan['process_name']
                            or entry['requires'] != entry['lua_program']['requires']
                            or entry['provides'] != entry['lua_program']['provides']
                            or entry.get('enable') != [] or entry.get('disable') != []
                            or bool(entry.get('one_shot')) != bool(entry['lua_program'].get('one_shot', False))):
                        raise NativeCompileError('Native Lua metadata does not match its source.')
                    continue
                if 'program' in entry:
                    from .aa_program import validate_program
                    validate_program(entry['program'])
                    if entry['program']['bitness'] != target_architecture['bitness']:
                        raise NativeCompileError('Assembly profile differs from the declared target architecture.')
                    if (entry['program']['process_name'] != plan['process_name']
                            or entry['requires'] != entry['program']['requires']
                            or entry['provides'] != entry['program']['provides']
                            or entry.get('enable') != [] or entry.get('disable') != []
                            or bool(entry.get('one_shot')) != bool(entry['program'].get('one_shot', False))):
                        raise NativeCompileError('Native assembly metadata does not match its source.')
                    continue
                for phase in ("enable", "disable"):
                    operations = entry.get(phase)
                    if not isinstance(operations, list) or len(operations) > MAX_OPERATIONS:
                        raise NativeCompileError("Script phase must contain bounded operations.")
                    for operation in operations:
                        if not isinstance(operation, dict):
                            raise NativeCompileError("Script operation must be an object.")
                        op = operation.get("op")
                        if op in {"scan", "define", "register", "unregister"}:
                            validate_symbol(operation.get("symbol"))
                        if op == "scan":
                            module = operation.get("module")
                            if not isinstance(module, str):
                                raise NativeCompileError("Scan module must be a basename.")
                            validate_expression('"' + module + '"')
                            normalize_pattern(operation.get("pattern"))
                        elif op == "define":
                            validate_expression(operation.get("expression"))
                        elif op in {"assert", "write"}:
                            validate_expression(operation.get("address"))
                            data = operation.get("bytes")
                            if not isinstance(data, str) or not data or len(data) > 2 * MAX_PATCH_BYTES or re.fullmatch(r"(?:[0-9a-f]{2})+", data) is None:
                                raise NativeCompileError("Patch/assert bytes must be bounded exact hexadecimal bytes.")
                        elif op not in {"register", "unregister"}:
                            raise NativeCompileError("Unknown native script operation.")
                if entry.get("one_shot"):
                    if entry.get("disable"):
                        raise NativeCompileError("One-shot script must have an empty disable phase.")
                    validate_one_shot_guards(entry["enable"])
                else:
                    validate_patch_guards(entry["enable"], entry["disable"])
                local: set[str] = set()
                required: set[str] = set()
                registered: set[str] = set()
                unregistered: set[str] = set()
                for phase in ("enable", "disable"):
                    for operation in entry[phase]:
                        op = operation["op"]
                        if op == "scan":
                            if phase != "enable":
                                raise NativeCompileError("Disable cannot rescan module bytes.")
                            local.add(operation["symbol"].casefold())
                        elif op == "define":
                            required.update(symbol.casefold() for symbol in expression_symbols(operation["expression"])
                                            if symbol.casefold() not in local)
                            local.add(operation["symbol"].casefold())
                        elif op in {"assert", "write"}:
                            required.update(symbol.casefold() for symbol in expression_symbols(operation["address"])
                                            if symbol.casefold() not in local)
                        elif op == "register":
                            if phase != "enable" or operation["symbol"].casefold() not in local:
                                raise NativeCompileError("Only enable-local symbols can be registered.")
                            registered.add(operation["symbol"].casefold())
                        elif op == "unregister":
                            if phase != "disable":
                                raise NativeCompileError("Only disable may unregister symbols.")
                            unregistered.add(operation["symbol"].casefold())
                if (registered != unregistered or registered != {symbol.casefold() for symbol in entry["provides"]}
                        or required != {symbol.casefold() for symbol in entry["requires"]}):
                    raise NativeCompileError("Script symbol dependency/registration metadata does not match its operations.")
                if not registered and not any(operation["op"] == "write" for operation in entry["enable"]):
                    raise NativeCompileError("Script must provide a symbol or guarded patch action.")
            elif entry["kind"] == "value":
                _validate_value_address(entry)
                if value_profile is None and entry.get("variable_type") not in SIMPLE_VALUE_TYPES:
                    raise NativeCompileError("Unsupported native value type.")
                if (type(entry.get("show_as_hex")) is not bool
                        or entry.get("show_as_signed") is not None and type(entry["show_as_signed"]) is not bool):
                    raise NativeCompileError("Invalid numeric display flags.")
                if entry["show_as_hex"] and entry["variable_type"] in {"Float", "Double"}:
                    raise NativeCompileError("Hexadecimal floating-point values are unsupported.")
                dropdown = entry.get("dropdown")
                if (not isinstance(dropdown, dict) or not isinstance(dropdown.get("choices"), list)
                        or type(dropdown.get("read_only")) is not bool):
                    raise NativeCompileError("Invalid dropdown plan.")
                if dropdown["read_only"] and not dropdown["choices"]:
                    raise NativeCompileError("Read-only dropdown has no numeric choices.")
                for choice in dropdown["choices"]:
                    if (not isinstance(choice, dict) or not isinstance(choice.get("description"), str)
                            or not _value_literal_safe(choice.get("value"), entry["variable_type"],
                                                      entry["show_as_hex"], entry["show_as_signed"], value_profile)):
                        raise NativeCompileError("Dropdown values must be exact supported literals.")
            elif entry["kind"] == "heading" and "value_profile" in entry:
                # The only profile-backed navigation record is a canonical
                # zero-byte placeholder. Its address still anchors children.
                if (entry["variable_type"] not in {"Array of byte","String"} or value_profile["size"] != 0
                        or entry.get("dropdown") != {"choices": [], "read_only": False}
                        or entry.get("dependency_ids") != []
                        or entry.get("source_kind") not in {"value", "unsupported"}
                        or entry["reason"] != value_profile["reason"]):
                    raise NativeCompileError("Invalid non-actionable byte-array placeholder heading.")
                _validate_value_address(entry, allow_empty=True)
            elif (entry["kind"] == "heading" and entry.get("source_kind") in {"value", "unsupported"}
                  and entry.get("variable_type") in _PROFILE_VALUE_TYPES):
                raise NativeCompileError("Value-type placeholder headings require canonical value metadata.")
        for entry in entries:
            parent = entry.get("parent_id")
            if parent is not None and (type(parent) is not int or parent not in ids or parent == entry["id"]):
                raise NativeCompileError("Invalid record parent ID.")
            dropdown = entry.get("dropdown")
            if isinstance(dropdown, dict):
                link_target = dropdown.get("link_target_id")
                if (link_target is not None and (type(link_target) is not int
                        or link_target not in ids or link_target == entry["id"])):
                    raise NativeCompileError("Dropdown link target must reference another plan record.")
            recursive = entry.get("recursive_value")
            if isinstance(recursive, dict):
                write_ids = recursive.get("write_ids")
                if (not isinstance(write_ids, list)
                        or any(type(item) is not int for item in write_ids)
                        or len({item for item in write_ids}) != len(write_ids)):
                    raise NativeCompileError("Recursive value metadata must list unique record IDs.")
                try:
                    expected = recursive_write_closure({e["id"]: e for e in entries}, entry["id"])
                except RecursiveSetValueError as exc:
                    raise NativeCompileError(str(exc)) from exc
                if write_ids != expected:
                    raise NativeCompileError("Recursive value metadata does not match the record structure.")
            dependencies = entry.get("dependency_ids", [])
            if (not isinstance(dependencies, list) or len(dependencies) > MAX_OPERATIONS
                    or any(type(item) is not int or item not in ids for item in dependencies)):
                raise NativeCompileError("Invalid record dependency IDs.")
        selected = plan.get("selected_ids")
        if selected is None:
            raise NativeCompileError("Native plans require exact selected record IDs.")
        if selected is not None:
            if (not isinstance(selected, list) or any(type(item) is not int for item in selected)
                    or selected != sorted(set(selected)) or not set(selected) <= ids):
                raise NativeCompileError("Invalid selected record ID list.")
            for entry in entries:
                if type(entry.get("selected")) is not bool or entry["selected"] != (entry["id"] in selected):
                    raise NativeCompileError("Selected record flags do not match selected IDs.")
            # Parent/child activation plan data: the flag markers on
            # supported headings and the derived subtree relations must
            # re-derive byte-exactly from the entries' own parent links.
            by_id = {entry["id"]: entry for entry in entries}
            children_by_parent = {}
            for entry in entries:
                if entry.get("parent_id") is not None:
                    children_by_parent.setdefault(entry["parent_id"], []).append(entry["id"])
            expected_relations = {}
            for entry in entries:
                flag = entry.get("parent_activation")
                if flag is not None:
                    if (flag not in ("required_dependency", "direct_activation", "collective_off")
                            or entry["kind"] != "heading" or not entry["supported"]
                            or entry["id"] not in selected):
                        raise NativeCompileError("Parent flag class requires a supported selected heading.")
                    children = {}
                    stack = [entry["id"]]
                    while stack:
                        node_id = stack.pop()
                        for child_id in children_by_parent.get(node_id, ()):
                            child = by_id[child_id]
                            if child["supported"] and child["id"] in selected:
                                children[child_id] = flag
                            stack.append(child_id)
                    if not children:
                        raise NativeCompileError("Parent flag class without any cascade target.")
                    expected_relations[entry["id"]] = children
            for entry in entries:
                if entry.get("parent_mo_bind") is True and (entry["kind"] != "heading"
                        or not entry["supported"] or entry["id"] not in selected):
                    raise NativeCompileError("moBindActivation marker requires a supported selected heading.")
            stored = plan.get("parent_relations")
            if stored is None:
                stored = {}
            if not isinstance(stored, dict):
                raise NativeCompileError("parent_relations must be a mapping.")
            normalized = {}
            for parent_key, children in stored.items():
                if not isinstance(parent_key, str) or not isinstance(children, dict):
                    raise NativeCompileError("parent_relations must map record IDs to child mappings.")
                normalized[int(parent_key)] = {}
                for child_key, flag in children.items():
                    if (not isinstance(child_key, str) or type(flag) is not str
                            or flag not in ("required_dependency", "direct_activation", "collective_off")):
                        raise NativeCompileError("parent_relations children must map to a flag class.")
                    normalized[int(parent_key)][int(child_key)] = flag
            if normalized != expected_relations:
                raise NativeCompileError("parent_relations do not re-derive from the plan entries.")
        identity_fields = {"engine": "ct2trainer", "schema": plan["schema"],
                           "table_sha256": plan["table_sha256"],
                           "process_name": plan["process_name"].casefold(), "selected_ids": selected}
        if plan["schema"] == 2:
            identity_fields["target_architecture"] = target_architecture
        identity = json.dumps(identity_fields, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if plan["trainer_id"] != sha256(identity).hexdigest()[:16]:
            raise NativeCompileError("Trainer identity differs from its source, selection or target architecture.")
    except (AAError, AddressExpressionError, LuaProgramError, ValueTypeError) as exc:
        raise NativeCompileError(str(exc)) from exc
