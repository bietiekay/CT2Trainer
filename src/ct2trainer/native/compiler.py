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

from ..table import (MAX_ENTRIES, MAX_TABLE_BYTES, MAX_HOTKEYS_PER_RECORD,
                     MAX_UDS_ENTRIES, SIMPLE_VALUE_TYPES, Entry,
                     numeric_literal_safe, read_table)
from .hotkey_model import (ACTIVATION_HOTKEY_ACTIONS, VALUE_HOTKEY_ACTIONS,
                           format_hotkey_keys)
from .aa import (AAError, MAX_OPERATIONS, MAX_PATCH_BYTES, compile_one_shot,
                 compile_script, expression_symbols, is_flat_expression,
                normalize_pattern,
                 validate_expression, validate_one_shot_guards,
                 validate_patch_guards, validate_symbol)
from .aa_blocks import BlockStructureError, extract_label_definitions
from .address_expression import (AddressExpressionError,
                                expression_symbols as advanced_expression_symbols,
                                parse_expression)
from .lua_program import (LuaProgramError, has_lua_sections, lua_dynamic_address_targets,
                          lua_symbol_provides, prepare_lua_program, validate_lua_program)
from .value_links import RecursiveSetValueError, recursive_write_closure
from .value_types import (ValueTypeError, parse_profile_value,
                          prepare_value_profile, validate_value_profile)


from .architecture import (ArchitectureError, plan_architecture, prepare_architecture)


_PROFILE_VALUE_TYPES = {"Array of byte", "Binary", "String"}

_ADDRESSLESS_PLACEHOLDER_REASON = (
    "Addressless value record is a non-actionable table placeholder.")

# WP-44: canonical inert-script demotion.  A script record whose source has
# no executable effect in either dialect (no registered symbols and no
# guarded byte-patch) is demoted to a supported, non-actionable heading so
# tables with inert comment-only or banner scripts compile fully supported;
# the record carries no enable actions and no cascade promise.
_INERT_SCRIPT_REASON = (
    "Inert script: no registered symbols and no guarded byte-patch action; "
    "activation is a verified no-op.")
_DATA_NO_ACTION_REASON = (
    "Script has no registered symbols or guarded byte-patch action.")
_NATIVE_NO_CONTENT_REASON = "Enable section has no executable patch or data."
_LUA_ENVELOPE_PREFIX = "Static AA envelope: "


def _is_inert_no_action(message: str) -> bool:
    """WP-44: both dialects must independently report the no-action refusal.

    Direct scripts reach the handler as ``<data reason> Native assembly:
    <native reason>``; a Lua envelope carries the ``Static AA envelope: ``
    prefix on the native side only, and its embedded Lua still runs at
    activation, so an envelope record is never demoted inert.  Only the
    combination of the two canonical no-action reasons demotes; any other
    failure stays blocked.
    """
    message = message.removeprefix(_LUA_ENVELOPE_PREFIX)
    return (_DATA_NO_ACTION_REASON in message
            and _NATIVE_NO_CONTENT_REASON in message)

# WP-37: canonical handover reason strings.  The named release reason is
# raised by the AA and program dialects; the two generic cleanup reasons
# below are the wave-A error texts that wave B1 re-derives with the
# external-ownership context.  (RT-4.1 removed the wildcard-cleanup
# static guard: the wildcard sweep expands to the program's own
# phase-owned names only, so the wave-B wildcard re-derivation loop and
# its reason/source constants are gone as well.)
_EXTERNAL_RELEASE_REASON = (
    "Program may not unregister or deallocate the externally owned symbol")
_UNREGISTER_EXACT_REASON = (
    "Exactly the registered enable symbols must be unregistered on disable.")
_CLEANUP_OWNED_REASON = (
    "Cleanup may only release symbols/allocations owned by this program.")


def _is_addressless_placeholder(entry: dict) -> bool:
    """WP-32: canonical shape of a demoted addressless value record.

    Demoted placeholders are supported navigation rows without address or
    effect; they are never parent-activation cascade targets (the plan only
    promises activation where the engine has a target) and never carry
    activation markers.
    """
    return (entry["kind"] == "heading"
            and entry.get("source_kind") in {"value", "unsupported"}
            and entry.get("variable_type") in SIMPLE_VALUE_TYPES | _PROFILE_VALUE_TYPES
            and entry.get("source_address") == ""
            and entry.get("reason") == _ADDRESSLESS_PLACEHOLDER_REASON)


def _is_inert_script(entry: dict) -> bool:
    """WP-44: canonical shape of a demoted no-action script record.

    A supported navigation heading (kind=heading, source_kind=script) with
    the exact inert reason and no executable metadata; it is never a
    cascade target, never carries an async marker, and promises no
    activation (mirror of the WP-32 addressless placeholder).
    """
    return (entry["kind"] == "heading"
            and entry.get("source_kind") == "script"
            and entry.get("reason") == _INERT_SCRIPT_REASON)


class NativeCompileError(ValueError):
    """Invalid compiler inputs or a malformed serialized plan."""


class DropdownLinkMissingError(AAError):
    """A dropdown link target matched no record label (WP-45, GC-E9).

    Unlike a generic AAError this refusal demotes the linked dropdown to an
    empty plain list (CE shows an empty list) instead of blocking the
    record: the value record itself stays supported and actionable, with a
    named plan warning.  Ambiguous and chained link refusals stay hard
    AAErrors (byte-stable).
    """


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
    # RT-4.2 (R7): a blocked record cannot carry the api_exports marker —
    # resolution may have set it for an earlier symbol before a later one
    # (or a later pass) blocked the record, and the plan validator refuses
    # the marker on anything but a supported script record.
    entry.pop("api_exports", None)
    entry["provides"] = []


# RT-4.6: registration evidence for the actionable per-symbol report.  A
# symbol counts as "registered anywhere in the table source" when any of
# these markers names it (case rules per marker, CE semantics): the AA
# registersymbol()/registerlabel() forms (one or more space/comma-separated
# names, optionally quoted), the Lua registerSymbol(...) variant, the
# line-anchored label() directive, define() and the {$define ...}
# directive, positional `name:` label definitions, and the first argument
# of aobscan*(...).  The final plan cannot make this distinction itself
# because _block() clears the provider's `provides`, so the raw source
# survey reproduces the human R5/R6 split (provider exists but blocked vs
# never registered at all).
_REGISTRATION_CALL = re.compile(
    r"(?i)\b(?:registersymbol|registerlabel|registerSymbol)\s*\(([^)]*)\)")
_LABEL_DIRECTIVE = re.compile(r"(?m)^\s*label\s*\(([^)]*)\)")
_DEFINE_CALL = re.compile(r"(?im)^\s*define\s*\(([^,]+),")
_DEFINE_DIRECTIVE = re.compile(r"(?im)\{\$define\s+([A-Za-z_][A-Za-z0-9_]*)")
_POSITIONAL_LABEL = re.compile(r"(?m)^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:")
_AOBSKAN_LABEL = re.compile(
    r"(?im)\baobscan(?:module|float|double|byte|qword|dword|region)?\s*\(\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)")
# A bare call target (Windows API export territory, RT-4.2/R7): the name
# must not continue with identifier, dot or hyphen characters, so
# `call user32.GetAsyncKeyState` and `call ctts-...` do not contribute a
# bare-target entry.
_CALL_TARGET = re.compile(
    r"\bcall\s+(?:(?:near|short|abs|far)\s+)*([A-Za-z_$][A-Za-z0-9_]*)(?![A-Za-z0-9_.$\-])",
    re.IGNORECASE)

# RT-4.2 (R7): bounded Windows API export registry.  A bare call target
# (no record, table-Lua or user-symbol provider) that names one of these
# system exports is a static known target: the plan carries an explicit
# ``api_exports`` marker (exact source spelling + owning module basename),
# the engine resolves it against the attached target's live PE export
# table at link time, and an absent export fails closed with a named,
# actionable refusal before any target memory is touched.  The registry is
# deliberately minimal (the corpus only needs user32 entries) and
# extensible by adding a casefolded name; names outside it keep the
# classic unsupported-provider refusal.
_API_EXPORT_MODULES = {
    "getasynckeystate": ("user32.dll", "GetAsyncKeyState"),
    "findwindowa": ("user32.dll", "FindWindowA"),
}


def _symbol_source_survey(scripts: dict[int, str]) -> tuple[set[str], set[str]]:
    """Scan raw record scripts for symbol-registration evidence.

    Returns ``(registered, call_targets)`` as casefolded name sets.  The
    scan is pure text: it never parses the scripts, so malformed or
    unsupported syntax can only add evidence, never remove it (the
    fail-safe direction for the report classification).
    """
    text = "\n".join(scripts.values())
    registered: set[str] = set()
    for pattern in (_REGISTRATION_CALL, _LABEL_DIRECTIVE, _DEFINE_CALL):
        for match in pattern.finditer(text):
            names = re.split(r"[, \t]+", match.group(1).strip())
            registered.update(name.strip("'\"").casefold()
                              for name in names if name.strip().strip("'\""))
    for match in _DEFINE_DIRECTIVE.finditer(text):
        registered.add(match.group(1).casefold())
    for match in _AOBSKAN_LABEL.finditer(text):
        registered.add(match.group(1).casefold())
    for match in _POSITIONAL_LABEL.finditer(text):
        registered.add(match.group(1).casefold())
    call_targets: set[str] = set()
    for match in _CALL_TARGET.finditer(text):
        call_targets.add(match.group(1).casefold())
    return registered, call_targets


def _normalize_user_symbols(user_symbols: dict[str, int] | None) -> dict[str, int]:
    """RT-4.6: validate and casefold the optional user-symbol import.

    The map mirrors the UDS shape contract: bounded, nonempty ASCII symbol
    names unique case-insensitively, 64-bit unsigned addresses.  The result
    is the residual plan field (record providers always win) and the engine
    seed input.
    """
    if user_symbols is None:
        return {}
    if not isinstance(user_symbols, dict) or len(user_symbols) > MAX_UDS_ENTRIES:
        raise NativeCompileError(
            "User-symbol import must be a mapping of at most "
            f"{MAX_UDS_ENTRIES} symbol names to addresses.")
    symbols: dict[str, int] = {}
    for name, address in user_symbols.items():
        if not isinstance(name, str) or not name:
            raise NativeCompileError(
                "User-symbol names must be nonempty text.")
        try:
            validate_symbol(name)
        except AAError as exc:
            raise NativeCompileError(str(exc)) from exc
        if type(address) is not int or not (0 <= address <= 0xFFFFFFFFFFFFFFFF):
            raise NativeCompileError(
                "User-symbol addresses must be 64-bit unsigned integers.")
        key = name.casefold()
        if key in symbols:
            raise NativeCompileError(
                f"Duplicate user-symbol name (case-insensitive): {name}.")
        symbols[key] = address
    return symbols


def load_user_symbols(path: str | Path) -> dict[str, int]:
    """RT-4.6: read an optional user-symbol import file.

    The file is a JSON object mapping symbol names to target addresses;
    addresses are decimal integers or 0x/$-prefixed hex strings.  The
    result is passed to ``compile_table(user_symbols=...)`` where the
    casefold/uniqueness/name rules are enforced.
    """
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise NativeCompileError(
            f"User-symbol import file is not readable JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise NativeCompileError(
            "User-symbol import file must be a JSON object mapping symbol "
            "names to addresses.")
    symbols: dict[str, int] = {}
    for name, address in raw.items():
        if isinstance(address, str):
            text = address.strip()
            if re.fullmatch(r"0[xX][0-9A-Fa-f]+|\$[0-9A-Fa-f]+", text):
                address = int(text[2:] if text[:2].lower() == "0x" else text[1:], 16)
            elif re.fullmatch(r"[0-9]+", text):
                address = int(text)
            else:
                raise NativeCompileError(
                    f"User-symbol address {address!r} must be a decimal "
                    "integer or a 0x/$ hex string.")
        symbols[name] = address
    return symbols


_OFFSET_SLOT_GRAMMAR = re.compile(
    r"^[+-]?(?:(?:0x)?[0-9A-Fa-f]+|#[+-]?[0-9]+)"
    r"(?:\s*[-+*]\s*(?:(?:0x)?[0-9A-Fa-f]+|#[+-]?[0-9]+))*$")
_OFFSET_SLOT_TOKEN = re.compile(r"[-+*]|(?:0x)?[0-9A-Fa-f]+|#[+-]?[0-9]+")
_OFFSET_ANNOTATION = re.compile(r"\([^()]*\)")


_OFFSET_REFUSAL = (
    "Pointer offset must be a hexadecimal integer literal or a supported "
    "address expression.")


def _fold_hex_offset(body: str) -> int:
    """Fold the hex/decimal arithmetic body of a literal offset slot."""
    first_sign = 1
    if body[0] in "+-":
        first_sign = -1 if body[0] == "-" else 1
        body = body[1:]
    tokens = _OFFSET_SLOT_TOKEN.findall(body)

    def slot_value(token: str) -> int:
        if token.startswith("#"):
            # CE offset convention (ConvertHexStrToRealStr): a '#' prefix
            # marks decimal; the sign may sit before or after the '#'.
            number = int(token[1:], 10)
        else:
            number = int(token.removeprefix("0x").removeprefix("0X"), 16)
        if abs(number) > 0x7FFFFFFFFFFFFFFF:
            raise AAError("Pointer offset exceeds signed 64 bits.")
        return number

    total = 0
    current = first_sign * slot_value(tokens[0])
    for index in range(1, len(tokens), 2):
        operator, term = tokens[index], tokens[index + 1]
        if operator == "*":
            current *= slot_value(term)
        elif operator == "+":
            total += current
            current = slot_value(term)
        else:  # "-"
            total += current
            current = -slot_value(term)
    total += current
    if abs(total) > 0x7FFFFFFFFFFFFFFF:
        raise AAError("Pointer offset exceeds signed 64 bits.")
    return total


def _expression_references(node) -> bool:
    """RT-4.3 (O3): true when an address expression names anything that
    must be resolved at runtime — a symbol, module-prefixed export,
    managed label, module base, or a memory read.  Pure constant
    arithmetic (e.g. "++10") is not an offset reference and stays
    fail-closed under the literal refusal."""
    if node.get("kind") in {"symbol", "export", "module", "managed", "deref"}:
        return True
    for key in ("value", "left", "right"):
        child = node.get(key)
        if isinstance(child, dict) and _expression_references(child):
            return True
    return False


def _parse_offset_slot(text: str) -> int | str:
    """Fold one <Offset> slot into a signed int64 or keep an expression.

    The reference corpus uses constant hexadecimal arithmetic in pointer-
    chase slots ("13A8+118", "A0+4*4", "1594+8+118") and annotated hex
    ("20 (Offset of the name pointer)").  The bounded grammar is: hex
    literals (optionally 0x-prefixed) and decimal literals
    ('#'-prefixed, with the sign before or after the '#', per the CE
    ConvertHexStrToRealStr convention) combined with '+', '-' and '*'
    using the usual precedence, an optional leading sign that binds to
    the first term, plus optional balanced, non-nested parenthesized
    annotation text that is stripped before evaluation.  WP-14 (C4)
    remains intact: "+28" is 0x28, "-0x10" is -16, and malformed forms
    ("++10", "+", bare "0x"), empty slots, nested or unbalanced
    parentheses and empty annotations stay rejected fail-closed.  A slot
    that happens to consist only of hex digits is evaluated as hex (the
    same ambiguity CE has in its hex-first offset parse).

    RT-4.3 (O3): a slot that is not literal arithmetic is accepted when
    it is a supported address expression — a symbol, module-prefixed
    export or managed label, or bounded arithmetic/dereferences over
    them.  The expression is kept verbatim in the plan and resolved at
    activation against the live symbol table and memory (CE
    pointer-chain semantics), so hex literals keep working byte-for-byte
    and expression offsets stay fail-closed only when the expression
    grammar itself refuses them.
    """
    if not isinstance(text, str):
        raise AAError(_OFFSET_REFUSAL)
    core = text.strip()
    if not core or len(core) > 64:
        raise AAError(_OFFSET_REFUSAL)
    if _OFFSET_SLOT_GRAMMAR.match(core) is not None:
        return _fold_hex_offset(core)
    depth = 0
    for char in core:
        if char == "(":
            depth += 1
        elif char == ")" and depth > 0:
            depth -= 1
    if depth == 0:
        annotations = _OFFSET_ANNOTATION.findall(core)
        if annotations and any(annotation[1:-1].strip() == ""
                               for annotation in annotations):
            raise AAError(_OFFSET_REFUSAL)
        if _OFFSET_ANNOTATION.search(core) is not None:
            stripped = _OFFSET_ANNOTATION.sub(" ", core).strip()
            if _OFFSET_SLOT_GRAMMAR.match(stripped) is not None:
                return _fold_hex_offset(stripped)
    try:
        node = parse_expression(core)
    except AddressExpressionError as exc:
        raise AAError(_OFFSET_REFUSAL) from exc
    if not _expression_references(node):
        raise AAError(_OFFSET_REFUSAL)
    return core


def _offsets(offsets: tuple[str, ...]) -> list[int | str]:
    if len(offsets) > 32:
        raise AAError("Pointer chains are limited to 32 offsets.")
    return [_parse_offset_slot(text) for text in offsets]


def _effective_address(source: Entry, sources: dict[int, Entry], stack: tuple[int, ...] = (),
                       *, skip: bool = False) -> str:
    """Flatten relative addresses and XML pointer offsets, without reading memory.

    RT-4.3 (O9/O1): with ``skip=True`` an addressless intermediate
    ancestor (an addressless script/value record) is transparent for the
    inherited-base walk, so the base of a farther-up address-bearing
    ancestor is used; an addressless heading with pointer offsets still
    refuses in both modes (its inherited base is genuinely ambiguous).
    The default behaviour is unchanged.
    """
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
            if candidate.pointer_offsets:
                raise AAError("Relative address cannot skip an addressless heading with pointer offsets; its inherited base is ambiguous.")
            if not skip and not candidate.is_group_header:
                raise AAError("Relative address cannot skip an addressless script/value ancestor.")
            parent_id = candidate.parent_id
        if parent_source is None:
            raise AAError("Relative address has no address-bearing ancestor.")
        base = _effective_address(parent_source, sources, stack + (source.id,), skip=skip)
        raw = "(" + base + ")" + raw
    for offset in reversed(_offsets(source.pointer_offsets)):
        if isinstance(offset, str):
            # RT-4.3 (O3): an expression offset cannot be folded into a hex
            # literal; it is inlined verbatim (parenthesized) so the runtime
            # expression evaluation resolves it against the live symbol
            # table and memory at activation.
            raw = f"[{raw}]+({offset})"
        else:
            raw = "[" + raw + "]" + (f"+{offset:X}" if offset > 0 else f"-{abs(offset):X}" if offset < 0 else "")
    try:
        parse_expression(raw)
    except AddressExpressionError as exc:
        raise AAError(str(exc)) from exc
    return raw


def _dropdown(entry: Entry, entries: tuple[Entry, ...], value_profile: dict | None = None) -> dict:
    source = entry
    if entry.dropdown_link:
        # WP-27: linked dropdowns work for profile value records as well as
        # simple types; every choice is resolved against the LINKED record's
        # own value type (simple literal policy or its value profile).
        matches = [candidate for candidate in entries
                   if candidate.label.casefold() == entry.dropdown_link.casefold()]
        if not matches:
            raise DropdownLinkMissingError("Dropdown link target is missing: '" + entry.dropdown_link
                          + "' matches no record label.")
        if len(matches) > 1:
            raise AAError("Dropdown link target is ambiguous: '" + entry.dropdown_link
                          + "' matches " + str(len(matches)) + " record labels.")
        source = matches[0]
        if source.dropdown_link:
            raise AAError("Chained dropdown links are unsupported.")
    choices = []
    for value, label in source.dropdown_choices:
        if value == "*":
            continue  # Placeholder is metadata, never a selectable memory value.
        if value == "":
            # WP-24: an empty value part is separator metadata, not a
            # writable choice.  It stays in the plan as a non-writable
            # display row and is skipped by writable-choice validation and
            # by the engine's choice lists.
            choices.append({"value": "", "description": label, "separator": True})
            continue
        # WP-34 (FLAG-2 follow-up 1): comma-decimal Float/Double choice
        # literals are normalized to the canonical dot form before
        # validation and stored in the plan.
        if (value_profile is None and entry.variable_type in {"Float", "Double"}
                and not entry.show_as_hex and _COMMA_DECIMAL.fullmatch(value)):
            value = value.replace(",", ".", 1)
        status, refusal = _dropdown_choice_status(value, entry.variable_type,
                                                  entry.show_as_hex,
                                                  entry.show_as_signed,
                                                  value_profile)
        if status != "refusal":
            # RT-4.4 (O6/O8): the literal is parseable in one of the
            # accepted integer bases ("own" or "alternate"); integer-width
            # overflow is a write-time truncation (O6), not a compile
            # refusal, matching the CE typed-pointer store.
            choices.append({"value": value, "description": label})
        elif (status == "refusal" and value_profile is None
                and entry.variable_type in SIMPLE_VALUE_TYPES
                and value.strip()[:1] == "["
                and value.strip()[-1:] == "]"
                and len(value.strip()) > 2):
            # RT-4.4 (O8): a bracketed dropdown choice is an address
            # expression evaluated against the runtime symbol table at
            # write time; syntax is validated here, semantics at write.
            try:
                parse_expression(value.strip())
            except AddressExpressionError as exc:
                raise AAError(
                    "Dropdown expression choice '%s' is not a valid address "
                    "expression: %s" % (value, exc)) from exc
            choices.append({"value": value, "description": label,
                            "expression": True})
        elif status == "refusal" and source.dropdown_read_only:
            # RT-4.4 (O8/O26): a read-only (description-only) list may
            # carry display sentinels (e.g. the CE '??' unreadable-value
            # marker) that the record's value type cannot parse.  They are
            # staged as non-writable display rows; the write path never
            # treats them as selectable choices.
            choices.append({"value": value, "description": label,
                            "writable": False})
        else:
            raise AAError(refusal)
    # RT-4.4 (O26): a read-only list without concrete writable choices
    # stages as an empty read-only view instead of a refusal; the record's
    # own value semantics are unchanged.  (Previously: "Read-only
    # dropdown has no concrete literal choices.")
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
        if value_type in {"Float", "Double"} and hexadecimal:
            # WP-33: fixed-width raw IEEE-754 bit patterns only.
            digits = 8 if value_type == "Float" else 16
            return re.fullmatch(r"(?:0[xX])?[0-9a-fA-F]{" + str(digits) + r"}",
                                value.strip()) is not None
        return _native_literal_safe(value, value_type, hexadecimal, signed)
    try:
        # A synthetic snapshot is only for literal validation during conversion;
        # the runtime must reread actual adjacent bits before every write.
        parse_profile_value(value_profile, value, b"\0" * value_profile["size"])
    except ValueTypeError:
        return False
    return True


_COMMA_DECIMAL = re.compile(r"[+-]?[0-9]+,[0-9]+\Z")
_INTEGER_WIDTHS = {"Byte": 8, "2 Bytes": 16, "4 Bytes": 32, "8 Bytes": 64}
_HEX_INTEGER_LITERAL = re.compile(r"(?:0[xX])?[0-9A-Fa-f]+\Z")


def _integer_choice_base(value: str, hexadecimal: bool) -> str | None:
    """RT-4.4 (O6/O8): which integer base an choice literal parses in.

    Returns "own" when the literal is an integer in the record's display
    base, "alternate" when it is an integer only in the other base (the
    corpus P4G skill list: hex IDs listed on a decimal-mode record), or
    None when it is an integer literal in neither base.  No width check:
    CE stores the parsed integer through the record's typed pointer, so
    out-of-width literals are written truncated (O6).
    """
    literal = value.strip()
    if hexadecimal:
        return "own" if _HEX_INTEGER_LITERAL.fullmatch(literal) is not None else None
    if re.fullmatch(r"-?[0-9]+", literal) is not None:
        return "own"
    if _HEX_INTEGER_LITERAL.fullmatch(literal) is not None:
        return "alternate"
    return None


def _dropdown_choice_status(value: str, value_type: str, hexadecimal: bool,
                            signed: bool | None,
                            value_profile: dict | None = None) -> tuple[str, str]:
    """Classify one dropdown choice literal for the record's value type.

    Returns (status, refusal): status is "literal" (writable in the
    record's own base; integer widths truncate at write time),
    "alternate" (integer literal of the other base; written as that
    number), or "refusal" with the exact message for a literal the
    record cannot write.

    WP-27/WP-34 (FLAG-2): byte-array and bit-field profiles name the
    offending choice with its length or range problem; every other
    unusable literal keeps the generic unsupported-expression refusal.
    RT-4.4 (O6): the old "exceeds the value-type width" refusal is gone;
    integer choices are always writable and the write truncates.
    """
    if value_profile is None and value_type in {"Float", "Double"} and hexadecimal:
        # WP-33: a ShowAsHex float choice must be the fixed-width IEEE-754
        # bit pattern (8 digits for Float, 16 for Double, optional 0x).
        digits = 8 if value_type == "Float" else 16
        if re.fullmatch(r"(?:0[xX])?[0-9a-fA-F]{" + str(digits) + r"}",
                        value.strip()) is None:
            return ("refusal", "Dropdown contains an unsupported value expression.")
        return "literal", ""
    if value_profile is not None:
        try:
            # A synthetic snapshot is only for literal validation during
            # conversion; the runtime must reread actual adjacent bits
            # before every write.
            parse_profile_value(value_profile, value, b"\0" * value_profile["size"])
        except ValueTypeError as exc:
            detail = str(exc)
            if value_profile["kind"] == "byte_array" and detail == (
                    "Byte array must contain exactly ByteLength hex bytes"):
                return ("refusal", "Dropdown choice '%s' must contain exactly %d hex bytes "
                                    "for this byte array record."
                        % (value, value_profile["size"]))
            if value_profile["kind"] == "bitfield" and detail.startswith(
                    "Bit-field value must be between "):
                return ("refusal", "Dropdown choice '%s' is outside the bit-field value "
                                    "range (must be between %s)."
                        % (value, detail.split("must be between ", 1)[1]))
            return ("refusal", "Dropdown contains an unsupported value expression.")
        return "literal", ""
    if value_type in _INTEGER_WIDTHS:
        base = _integer_choice_base(value, hexadecimal)
        if base is not None:
            return base, ""
        return ("refusal", "Dropdown contains an unsupported value expression.")
    if not _native_literal_safe(value, value_type, hexadecimal, signed):
        return ("refusal", "Dropdown contains an unsupported value expression.")
    return "literal", ""


def _offset_expression_symbols(offsets, known=()) -> list[str]:
    """RT-4.3 (O3): symbol-kind atoms contributed by expression offset slots.

    Returns each symbol once, in expression order, skipping atoms the
    address symbols already cover (case-insensitive).
    """
    known_cf = {name.casefold() for name in known}
    found = []
    for offset in offsets:
        if isinstance(offset, str):
            for symbol in expression_symbols(offset):
                if (symbol.casefold() not in known_cf
                        and symbol not in found):
                    found.append(symbol)
                    known_cf.add(symbol.casefold())
    return found


def _compile_value_address(entry: dict, source: Entry, sources: dict[int, Entry],
                           allow_empty: bool = False) -> None:
    if allow_empty and not (source.address or "").strip():
        if source.pointer_offsets:
            raise AAError("An addressless placeholder cannot carry pointer offsets.")
        entry["address"] = ""
        return
    try:
        canonical = validate_expression(source.address or "")
    except AAError as strict_error:
        # The strict split refused the shape.  Authored indirection beyond
        # the bound stays fail-closed with that named depth-limit refusal;
        # everything the strict split refused for another reason (e.g.
        # parent-relative bases) falls to the expression profile, which
        # _effective_address flattens.
        if (source.address or "").strip().count("[") > 2:
            raise strict_error
        _store_expression_profile(entry, source, sources)
        return
    if is_flat_expression(canonical):
        # The flat base/tail canonical stays on the strict static resolver.
        entry["address"] = canonical
        entry["pointer_offsets"] = _offsets(source.pointer_offsets)
        # RT-4.3 (O3): expression offset slots carry their own symbol
        # dependencies on top of the address symbols.
        address_symbols = expression_symbols(canonical)
        entry["requires"] = address_symbols + _offset_expression_symbols(
            entry["pointer_offsets"], address_symbols)
        return
    # Bounded non-flat shapes (indirection, casts that survive
    # canonicalization, managed method labels) are evaluated by the runtime
    # via resolve_expression instead of the strict atom+offset resolver
    # (WP-30).
    _store_expression_profile(entry, source, sources)


def _store_expression_profile(entry: dict, source: Entry, sources: dict[int, Entry]) -> None:
    """Route a value record to the runtime expression profile (WP-30)."""
    entry["address"] = _effective_address(source, sources)
    entry["address_profile"] = "expression/v1"
    entry["pointer_offsets"] = []
    required = advanced_expression_symbols(entry["address"])
    for symbol in required:
        validate_symbol(symbol)
    entry["requires"] = required


def _validate_value_address(entry: dict, allow_empty: bool = False,
                            by_id: dict[int, dict] | None = None) -> None:
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
            # WP-38/WP-50: a relative expression address is valid only when
            # its plan-level ancestor walk binds the dynamic address provider
            # of the nearest marked ancestor (a symbol provider, or a
            # symbol-null direct address-write target).  RT-4.3 (O9/O1) adds
            # the staged runtime-base marker (a relative value whose group
            # base is written at runtime by the table scripts); everything
            # else keeps the existing named refusal byte-for-byte.
            if (_dynamic_provider_binding(by_id or {}, entry) is None
                    and _dynamic_address_binding(by_id or {}, entry) is None
                    and not _runtime_base_marker_ok(by_id or {}, entry)):
                raise NativeCompileError("Expression-profile addresses must have resolved inherited bases.")
        if entry.get("pointer_offsets") != [] or not isinstance(entry.get("source_address"), str):
            raise NativeCompileError("Expression-profile values require flattened offsets and original address metadata.")
        address_symbols = advanced_expression_symbols(entry["address"])
    else:
        raise NativeCompileError("Unknown native value address profile.")
    offsets = entry.get("pointer_offsets")
    if not isinstance(offsets, list) or len(offsets) > 32:
        raise NativeCompileError("Invalid pointer offsets.")
    offset_symbols = _offset_expression_symbols(offsets, address_symbols)
    for offset in offsets:
        if type(offset) is int:
            if abs(offset) > 0x7FFFFFFFFFFFFFFF:
                raise NativeCompileError("Invalid pointer offsets.")
        elif isinstance(offset, str):
            # RT-4.3 (O3): expression offset slots must stay parseable.
            try:
                parse_expression(offset)
            except AddressExpressionError as exc:
                raise NativeCompileError(str(exc)) from exc
        else:
            raise NativeCompileError("Invalid pointer offsets.")
    expected = {symbol.casefold() for symbol in address_symbols}
    expected.update(symbol.casefold() for symbol in offset_symbols)
    if {symbol.casefold() for symbol in entry["requires"]} != expected or entry["provides"]:
        raise NativeCompileError("Value symbol dependencies do not match the address.")


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


def _dependencies(entries: list[dict], selected: set[int] | None = None,
                  uds_symbols: dict[str, int] | None = None,
                  table_lua_symbols: set[str] | None = None,
                  user_symbols: dict[str, int] | None = None,
                  source_registered: set[str] | None = None,
                  api_call_targets: set[str] | None = None) -> None:
    """Reject missing/ambiguous symbol providers and their dependent records.

    ``uds_symbols`` (WP-46, part 1) maps casefolded table-level
    <UserdefinedSymbols> names to their static addresses.  A user-defined
    symbol provides a requirement only when no supported record provides
    it: the fallback fires exclusively in the zero-candidate branch below,
    so the supported-provider rules (including the WP-37 keep-first
    duplicate policy) are untouched.  Records resolved this way gain no
    dependency_ids, so they cannot cascade from a later provider block;
    the static address itself is resolved at link/activation time from the
    runtime symbol table that the engine seeds from the plan field.

    ``table_lua_symbols`` (WP-54, part c) is the casefolded name set the
    table-Lua scope proves to register at bootstrap.  It covers a required
    name on exactly the same zero-candidate fallback as the UDS symbols:
    the table scope is live for the whole attach and its bootstrap
    precedes wish restore, so no record dependency arises.  Record
    providers still win in every non-zero-candidate branch.

    ``user_symbols`` (RT-4.6) is the optional user-symbol import map
    (casefolded names to static addresses); it joins the same
    zero-candidate fallback.  ``source_registered`` and
    ``api_call_targets`` are the raw-source survey sets (see
    ``_symbol_source_survey``) that decide the report wording in the
    zero-candidate branch: a symbol registered somewhere in the table
    source or a bare call target keeps the generic reason, any other
    missing definition gets the actionable per-symbol report.
    """
    providers: dict[str, list[dict]] = {}
    # RT-4.2 (R3): the ordered keep-first scope per symbol, retained so a
    # dependent can fall back to the first still-supported candidate when
    # the kept (document-order first) provider is itself blocked.  Only
    # non-compatible duplicate sets get an entry; the shared-global
    # (compatible) branch is untouched and keeps its ambiguity refusal.
    provider_alternatives: dict[str, list[dict]] = {}
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
            # WP-37 / RT-4.1: deterministic keep-first among supported
            # providers (document order, tiebreak entry ID).  The first
            # kept candidate stays the only visible provider for this
            # symbol, so dependents resolve against it.  Duplicate provider
            # entries are no longer blocked wholesale (RT-4.1, CE 7.5
            # dupIgnore semantics): the engine registers symbols keep-first
            # at activation — a later duplicate registration is a silent
            # no-op while the rest of the later script still runs — so the
            # duplicate entries stay supported and their non-duplicate
            # registrations still take effect.  They are dropped from this
            # symbol's provider list so resolution sees exactly one
            # supported provider.
            # CE 7.5 source note (read-only, 2026-10-22):
            # registeredsymbols.Duplicates := dupIgnore
            # (autoassembler.pas:338/345) dedupes the per-program disable
            # symbol list; AA runtime registration is delete-then-add on the
            # user-defined symbol list (autoassembler.pas:4164-4208,
            # last-wins across records).  CT2Trainer's keep-first is a
            # documented safe narrowing (runtime-parity-assessment.md):
            # static resolution and runtime registration agree on the
            # first registrant, so plans and activations never diverge.
            # WP-45 (GC-E4): keep-first is scoped to the user's selection.
            # When at least one candidate is selected, the selected
            # providers form the scope, so an explicit selection can
            # activate an alternative variant instead of the document-first
            # one.  With no selected provider the table-wide scope applies
            # (the default compile selects every record, so default plans
            # stay byte-stable).  Unselected duplicates stay supported:
            # the engine activates selected entries only, so the kept
            # provider cannot shadow them at runtime.
            scope = chosen if chosen else candidates
            kept = scope[0]
            # RT-4.2 (R3): keep the ordered scope for the dependency
            # fallback; the provider list below still collapses to the kept
            # first candidate (byte-stable plans while it stays supported).
            provider_alternatives[symbol] = scope
            for entry in scope[1:]:
                # RT-4.1: keep the duplicate entry supported; only its
                # registration of this symbol is shadowed by the kept
                # provider (first registration wins).
                if entry in providers[symbol]:
                    providers[symbol].remove(entry)
    # WP-28 two-stage label resolution: prepare_program keeps a program's
    # bare positional labels local (they are the program's own definitions),
    # but a table-wide registered symbol of the same name wins over the
    # local label definition.  Re-declare each program's positional labels
    # as external requirements whenever another supported entry provides the
    # same symbol, so the classic provider/dependency machinery (and the
    # staged-metadata rules) applies.  entry["requires"] is the same list
    # object as entry["program"]["requires"] — extend in place.
    for entry in entries:
        if not entry["supported"] or entry["kind"] != "script":
            continue
        program = entry.get("program")
        if not isinstance(program, dict):
            continue
        # WP-49 (GC-E7): a record's own registration satisfies its own
        # reference to a symbol it provides (CE resolves symbol dependencies
        # lazily at patch time), so its positional label is never re-declared
        # as an external requirement — no self-edge, record stays supported.
        own_provided = {name.casefold() for name in entry.get("provides", [])}
        known = {symbol.casefold() for symbol in entry["requires"]}
        for symbol in program.get("positional_labels", []):
            key = symbol.casefold()
            if key in known or key in own_provided:
                continue
            if any(provider["id"] != entry["id"] for provider in providers.get(key, [])):
                entry["requires"].append(symbol)
                known.add(key)
    def _resolve_entry(entry: dict) -> str | None:
        """Re-resolve one supported record's symbol requirements.

        Mutates ``entry["dependency_ids"]`` in place (reset first; the
        partial list up to the failing symbol is left on a block, matching
        the historical pass semantics).  Returns the block reason, or
        ``None`` when the record stays supported.  Per-symbol resolution
        order: keep-first supported provider -> keep-first scope fallback
        (RT-4.2 R3, when the kept provider was itself blocked) ->
        table-level provider (no record dependency) -> Windows API export
        registry (RT-4.2 R7, no record dependency, plan marker) -> named
        refusal.
        """
        entry["dependency_ids"] = []
        # WP-49 (GC-E7): a record's own registration satisfies its own
        # reference to a symbol it provides; no self-edge is emitted and
        # the record stays supported regardless of other providers.
        own_provided = {name.casefold() for name in entry.get("provides", [])}
        for symbol in entry["requires"]:
            key = symbol.casefold()
            if key in own_provided:
                continue
            supported = [candidate for candidate in providers.get(key, [])
                         if candidate["supported"] and candidate["id"] != entry["id"]]
            # WP-45 (GC-E4): selection-aware provider resolution — a
            # selected provider wins over the table-wide provider set, so
            # an explicitly chosen variant serves its dependents.  When no
            # provider of this symbol is selected, the full supported set
            # is kept: the selection closure below can still pull in an
            # initially unselected sole provider (byte-stable default).
            if selected is not None:
                selected_supported = [candidate for candidate in supported
                                       if candidate["id"] in selected]
                if selected_supported:
                    supported = selected_supported
            if len(supported) == 0:
                # RT-4.2 (R3): keep-first fallback.  When the kept
                # (document-order first) provider is itself blocked, the
                # first still-supported candidate in keep-first scope order
                # takes over the requirement; the dependent's activation
                # ordering follows that provider, so static resolution and
                # runtime registration stay in agreement.  The shared-global
                # branch never reaches here (its candidates stay in
                # ``providers`` and keep the unique-provider refusal).
                alternative = [candidate for candidate in
                               provider_alternatives.get(key, ())
                               if candidate["supported"] and candidate["id"] != entry["id"]]
                if selected is not None:
                    selected_alternative = [candidate for candidate in alternative
                                            if candidate["id"] in selected]
                    if selected_alternative:
                        alternative = selected_alternative
                if alternative:
                    supported = [alternative[0]]
            if len(supported) == 0:
                if ((uds_symbols and key in uds_symbols)
                        or (table_lua_symbols and key in table_lua_symbols)
                        or (user_symbols and key in user_symbols)):
                    # WP-46 (part 1) / WP-54 (c) / RT-4.6: no supported
                    # record provides this symbol, so a table-level
                    # provider covers the requirement; no record
                    # dependency arises and the record stays supported.
                    # The UDS address is seeded into the runtime symbol
                    # table by the engine from the plan field; the
                    # table-Lua address is registered live by the
                    # table-scope bootstrap, which precedes wish restore;
                    # the user-symbol address is seeded by the engine
                    # after the UDS seed (an explicit operator import
                    # overrides a table-level definition of the same
                    # name).
                    continue
                # RT-4.2 (R7): a bare Windows API export call target with
                # no record or table-level provider is a static known
                # target; the plan marker carries the owning module and
                # the engine resolves it against the attached target's
                # live PE export table at link time (a registered symbol
                # of the same name always wins; an absent export fails
                # closed with a named, actionable refusal).  The registry
                # is deliberately bounded (see _API_EXPORT_MODULES); names
                # outside it keep the classic unsupported-provider
                # refusals below.
                api_pair = _API_EXPORT_MODULES.get(key)
                if api_pair is not None and entry["kind"] == "script":
                    entry.setdefault("api_exports", {})[api_pair[1]] = api_pair[0]
                    continue
                # RT-4.6: with no supported provider and no table-level
                # fallback, the raw-source survey decides which report
                # the operator sees.  A symbol registered somewhere in
                # the table source (its provider record exists but is
                # blocked for another reason) or a bare call target
                # (Windows API export territory) keeps the generic
                # reason; anything else is a missing definition, and
                # the actionable per-symbol report names the referring
                # record and both remediations.
                if key not in source_registered and key not in api_call_targets:
                    symbol_path = entry["path"]
                    return (
                        f"Required symbol '{symbol}' is not registered "
                        f"anywhere in this table (referenced by '{symbol_path}'): "
                        f"no record defines it and it is not a "
                        f"user-defined symbol. Import it as a user "
                        f"symbol with its target address, or add a "
                        f"record that registers it "
                        f"(registersymbol/registerSymbol/label/aobscan).")
                return f"Required symbol has no unique supported provider: {symbol}."
            if len(supported) > 1:
                return f"Required symbol has no unique supported provider: {symbol}."
            entry["dependency_ids"].append(supported[0]["id"])
        return None

    while True:
        changed = False
        for entry in entries:
            if not entry["supported"] or entry["kind"] == "heading":
                continue
            reason = _resolve_entry(entry)
            if reason is not None:
                _block(entry, reason)
                changed = True
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
    # Final pass: after the resolution fixpoint and the cycle blocks, a
    # dependent's provider may still have been blocked in a later pass.
    # Re-resolve the dependent against the current supported state: with
    # the RT-4.2 (R3) fallback a still-supported keep-first alternative
    # may now serve the requirement, so the dependent stays supported with
    # the updated dependency; only without any remaining supported
    # provider, table-level provider or API-export marker does it block.
    changed = True
    while changed:
        changed = False
        for entry in entries:
            if not entry["supported"] or entry["kind"] == "heading":
                continue
            if all(by_id[dependency]["supported"]
                   for dependency in entry.get("dependency_ids", ())):
                continue
            reason = _resolve_entry(entry)
            if reason is not None:
                _block(entry, reason)
                changed = True
            else:
                changed = True


# ---------------------------------------------------------------------------
# Dynamic address provider (WP-38, GC-B6)
#
# A relative value whose ancestor walk is interrupted by an addressless
# script record keeps the named compile refusal.  When that record is a
# supported addressless script with exactly one proven symbol export, the
# interrupted base is the provider's computed address, read fresh from the
# runtime symbol table at every activation.  The heading closest to the
# value records the provider binding as the additive plan field
# "address_provider"; the value keeps its raw relative source expression
# and resolves against the live base.  Chains that skip any other concrete
# record, or providers that are blocked, non-addressless or export more
# than one symbol, keep the existing refusal byte-for-byte.
# ---------------------------------------------------------------------------

def _dynamic_provider_binding(by_id: dict[int, dict], entry: dict) -> tuple[int, str] | None:
    """(provider_id, symbol) a record's relative address inherits from.

    The walk follows plan parent links: the nearest marked heading names
    the provider, and the binding is valid only when that provider is
    exactly the first non-heading ancestor (any concrete record in between
    would own its own base).  Returns None when the chain binds no
    provider, including forged or truncated ancestry.
    """
    provider_id = None
    symbol = None
    current_id = entry["id"]
    visited = {current_id}
    while True:
        parent_id = by_id[current_id].get("parent_id")
        if (parent_id is None or not isinstance(parent_id, int)
                or parent_id not in by_id or parent_id in visited
                or len(visited) >= 64):
            break
        visited.add(parent_id)
        parent = by_id[parent_id]
        if parent["kind"] == "heading":
            if provider_id is None:
                marker = parent.get("address_provider")
                if isinstance(marker, dict):
                    provider_id = marker.get("provider_id")
                    symbol = marker.get("symbol")
        else:
            if (provider_id is not None and parent_id == provider_id
                    and isinstance(symbol, str)):
                return (provider_id, symbol)
            return None
        current_id = parent_id
    return None


def _dynamic_address_binding(by_id: dict[int, dict], entry: dict):
    """WP-50: (target_id, provider_id) of a direct address-write binding.

    The walk follows plan parent links to the nearest marked ancestor whose
    ``address_provider`` marker carries ``symbol: null``; that entry is the
    target T whose live base the named provider script S writes at runtime.
    Returns None when the chain carries no such marker (including forged or
    truncated ancestry).
    """
    current_id = entry["id"]
    visited = {current_id}
    while True:
        parent_id = by_id[current_id].get("parent_id")
        if (parent_id is None or not isinstance(parent_id, int)
                or parent_id not in by_id or parent_id in visited
                or len(visited) >= 64):
            return None
        visited.add(parent_id)
        parent = by_id[parent_id]
        marker = parent.get("address_provider")
        if (isinstance(marker, dict) and marker.get("symbol") is None
                and type(marker.get("provider_id")) is int):
            return (parent["id"], marker["provider_id"])
        current_id = parent_id


def _runtime_base_marker_ok(by_id: dict[int, dict], entry: dict) -> bool:
    """RT-4.3 (O9/O1): plan gate for a staged runtime-base value.

    True when the entry is marked ``runtime_base_required`` and the plan
    chain re-derives the marker contract: the anchor heading exists, is
    supported, addressless and itself marked ``runtime_base_target``;
    the entry sits below that anchor; and no ancestor carries an
    ``address_provider`` marker (a proven WP-38/WP-50 binding takes
    precedence over the staged marker, so both must never coexist on one
    chain).  A forged, truncated or dangling marker fails closed here.
    """
    if entry.get("runtime_base_required") is not True:
        return False
    anchor_id = entry.get("runtime_base_anchor")
    if type(anchor_id) is not int or anchor_id not in by_id:
        return False
    anchor = by_id[anchor_id]
    if (anchor.get("runtime_base_target") is not True
            or anchor["kind"] != "heading" or not anchor["supported"]
            or anchor.get("address") != ""
            or anchor.get("pointer_offsets") != []):
        return False
    current_id = entry["id"]
    visited = {current_id}
    while True:
        parent_id = by_id[current_id].get("parent_id")
        if (parent_id is None or not isinstance(parent_id, int)
                or parent_id not in by_id or parent_id in visited
                or len(visited) >= 64):
            return False
        visited.add(parent_id)
        parent = by_id[parent_id]
        if parent.get("address_provider") is not None:
            return False
        if parent_id == anchor_id:
            return True
        current_id = parent_id


def _is_descendant(by_id: dict[int, dict], descendant_id: int, ancestor_id: int) -> bool:
    """True when descendant_id sits below ancestor_id in the plan tree.

    Bounded parent walk (64 levels, cycle-safe); a missing or broken parent
    link is not a descendant relation.
    """
    current_id = descendant_id
    visited = {current_id}
    while True:
        parent_id = by_id[current_id].get("parent_id")
        if (parent_id is None or not isinstance(parent_id, int)
                or parent_id not in by_id or parent_id in visited
                or len(visited) >= 64):
            return False
        visited.add(parent_id)
        if parent_id == ancestor_id:
            return True
        current_id = parent_id


def _address_provider_qualifies(provider: dict) -> bool:
    """A proven runtime base: supported addressless script, one export."""
    return (provider["kind"] == "script" and provider["supported"]
            and not provider.get("address") and not provider.get("pointer_offsets")
            and len(provider.get("provides", ())) == 1)


def _adopt_dynamic_address_providers(entries: list[dict], sources: dict[int, Entry],
                                     nodes: dict) -> list[str]:
    """Bind blocked relative values to a proven runtime base, in place.

    Runs after dependency analysis so the provider's final supported state
    is known.  Two proven base shapes are adopted:

    - WP-38 (GC-B6): every eligible blocked relative value (the named skip
      refusal, no source pointer offsets) whose plan ancestor chain reaches
      a proven addressless provider script (exactly one proven symbol
      export) through at least one heading; the heading closest to the
      value records the symbol binding.
    - WP-50 (GC-E8): every eligible blocked relative value (the named
      no-address-bearing-ancestor refusal) whose nearest addressless
      markable ancestor T (a supported addressless heading or script, never
      a demoted placeholder) is named by exactly one supported addressless
      script S whose embedded Lua statically writes T's address through the
      two bounded AddressList idioms; T records the symbol-null binding.

    The adopted value is recompiled as an expression-profile value on its
    raw relative address and keeps ``requires: []`` /
    ``dependency_ids: []``.  The provider is never auto-selected or
    auto-enabled: it keeps its ordinary activation path, and the value path
    gates on its liveness at runtime.

    Returns the named plan warnings produced by adopted records whose
    linked dropdown target cannot be resolved (WP-45 GC-E9 demotion: the
    adopted value stays supported with an empty plain dropdown).
    """
    by_id = {entry["id"]: entry for entry in entries}
    all_sources = tuple(sources.values())
    adopted = []
    adopted_warnings = []
    # WP-50: static dynamic-address extraction per supported addressless
    # script record (cached; pure text, both AddressList idioms).
    dynamic_targets: dict[int, list[str]] = {}
    for entry in entries:
        if (entry["supported"] and entry["kind"] == "script"
                and not entry.get("address") and not entry.get("pointer_offsets")
                and isinstance(entry.get("lua_program"), dict)
                and isinstance(entry["lua_program"].get("source"), str)):
            dynamic_targets[entry["id"]] = lua_dynamic_address_targets(
                entry["lua_program"]["source"])

    def _wp50_providers(target: dict) -> list[dict]:
        """Supported addressless scripts whose extraction names the target.

        Neither side may sit below the other (base/provider cycle), and the
        target's label must be the exact (case-sensitive) description.
        """
        providers = []
        for candidate in entries:
            if (candidate["id"] == target["id"]
                    or not candidate["supported"] or candidate["kind"] != "script"
                    or candidate.get("address") or candidate.get("pointer_offsets")
                    or target.get("label") not in dynamic_targets.get(candidate["id"], [])):
                continue
            if (_is_descendant(by_id, candidate["id"], target["id"])
                    or _is_descendant(by_id, target["id"], candidate["id"])):
                continue
            providers.append(candidate)
        return providers

    for entry in entries:
        if (entry["kind"] != "blocked" or entry.get("source_kind") != "value"
                or sources[entry["id"]].pointer_offsets):
            continue
        reason = entry.get("reason")
        marker_target = None
        provider = None
        symbol = None
        if reason == "Relative address cannot skip an addressless script/value ancestor.":
            # WP-38: the nearest heading records the binding; the provider
            # must be exactly the first non-heading ancestor.
            heading = None
            current_id = entry["id"]
            visited = {current_id}
            while True:
                parent_id = by_id[current_id].get("parent_id")
                if (parent_id is None or not isinstance(parent_id, int)
                        or parent_id not in by_id or parent_id in visited
                        or len(visited) >= 64):
                    break
                visited.add(parent_id)
                parent = by_id[parent_id]
                if parent["kind"] == "heading":
                    if heading is None:
                        heading = parent
                else:
                    provider = parent
                    break
                current_id = parent_id
            if heading is None or provider is None or not _address_provider_qualifies(provider):
                continue
            marker_target, symbol = heading, provider["provides"][0]
        elif reason == "Relative address has no address-bearing ancestor.":
            # WP-50: the target is the nearest addressless markable
            # ancestor; exactly one supported script's static extraction
            # must name it.
            target = None
            current_id = entry["id"]
            visited = {current_id}
            while True:
                parent_id = by_id[current_id].get("parent_id")
                if (parent_id is None or not isinstance(parent_id, int)
                        or parent_id not in by_id or parent_id in visited
                        or len(visited) >= 64):
                    break
                visited.add(parent_id)
                parent = by_id[parent_id]
                if (parent["kind"] in {"heading", "script"} and parent["supported"]
                        and not parent.get("address") and not parent.get("pointer_offsets")
                        and not _is_addressless_placeholder(parent)):
                    target = parent
                    break
                current_id = parent_id
            if target is None:
                continue
            providers = _wp50_providers(target)
            if len(providers) != 1:
                continue
            provider, marker_target, symbol = providers[0], target, None
        else:
            continue
        # One marker per marker record: an already-bound heading keeps its
        # first binding (a colliding second shape would change the live
        # base of the first shape's children); the identical marker is
        # idempotent for sibling values.
        desired_marker = {"provider_id": provider["id"], "symbol": symbol}
        if marker_target.get("address_provider") not in (None, desired_marker):
            continue
        source = sources[entry["id"]]
        profile = None
        if source.variable_type in _PROFILE_VALUE_TYPES:
            properties = {key: nodes[entry["id"]].findtext(key)
                          for key in ("ByteLength", "BitStart", "BitLength",
                                      "ShowAsBinary", "Length", "Unicode",
                                      "CodePage", "ZeroTerminate")}
            properties.update(ShowAsHex=source.show_as_hex,
                              ShowAsSigned=source.show_as_signed)
            if source.variable_type == "String":
                properties = {key: value for key, value in properties.items()
                              if value is not None}
            profile = prepare_value_profile(source.variable_type, properties)
            if not profile["actionable"]:
                # The per-record path demotes a non-actionable profile to
                # a navigation placeholder; adoption re-writes actionable
                # values only, so the record keeps its blocked state.
                continue
        entry["kind"] = "value"
        entry["supported"] = True
        entry["reason"] = ("Native relative value; the inherited base is resolved "
                           "at runtime from the dynamic address provider.")
        entry["address"] = source.address or ""
        entry["address_profile"] = "expression/v1"
        entry["pointer_offsets"] = []
        entry["requires"] = []
        entry["dependency_ids"] = []
        if profile is not None:
            entry["value_profile"] = profile
        try:
            entry["dropdown"] = (_string_dropdown(source, nodes, profile)
                                 if source.variable_type == "String"
                                 else _dropdown(source, all_sources, profile))
        except DropdownLinkMissingError as exc:
            # WP-45 (GC-E9): same demotion as the per-record path -
            # the adopted value stays supported, the linked dropdown
            # becomes an empty plain list, and a named warning is
            # returned to the plan warnings.
            entry["dropdown"] = {"choices": [], "read_only": False}
            adopted_warnings.append(
                f"Record {source.id} ('{source.label}'): {exc} "
                "The linked dropdown is demoted to an empty list.")
        except AAError as exc:
            # Hard refusal with no demotion equivalent (e.g. linked String
            # dropdowns require a separate literal profile): re-block the
            # adopted value with the exact per-record refusal.
            entry["kind"] = "blocked"
            entry["supported"] = False
            entry["reason"] = str(exc)
            entry["dropdown"] = {"choices": [], "read_only": False}
            entry.pop("value_profile", None)
            continue
        marker_target["address_provider"] = {"provider_id": provider["id"],
                                             "symbol": symbol}
        adopted.append(entry["id"])
    # RT-4.3 (O9/O1): stage the remaining relative-address refusals that are
    # structurally clean (no ambiguous offsets on the chain): either an
    # address-bearing ancestor exists further up (skip-fold recompile) or the
    # base is runtime-supplied (staged marker on the nearest heading).
    _stage_runtime_base_markers(entries, sources, nodes, by_id)
    if not adopted:
        return []
    # The marker is plan metadata of the serving heading; keep the heading's
    # own navigation reason, which already explains its role.
    for entry in entries:
        if (entry["kind"] == "heading" and entry.get("address_provider") is not None
                and not entry["supported"]):
            entry.pop("address_provider")
    return adopted_warnings


_STAGE_RELATIVE_RE = re.compile(r"^[+-]?[0-9A-Fa-f]+\Z")


def _anchor_parent_provides_symbols(by_id: dict[int, dict],
                                    parent_id: int | None) -> bool:
    """RT-4.3 (O9/O1): the WP-38 provider-group-shape gate for staging.

    True when the anchor heading's direct parent is a supported
    addressless script with symbol-registration intent - either a proven
    symbol export (``provides``) or a raw ``registerSymbol`` call in the
    embedded Lua (a register without a proven release still proves the
    intent).  That parent-child shape is the WP-38 provider group: the
    table intends the script's runtime symbol as the group's base, so
    staging the group onto a runtime-base marker would silently rebase
    it and the named relative-address refusal stays fail-closed.
    """
    if parent_id is None:
        return False
    entry = by_id.get(parent_id)
    if (entry is None or not entry.get("supported")
            or entry.get("kind") != "script"
            or entry.get("address") or entry.get("pointer_offsets")):
        return False
    if entry.get("provides"):
        return True
    program = entry.get("lua_program")
    return (isinstance(program, dict)
            and isinstance(program.get("source"), str)
            and "registerSymbol(" in program["source"])


def _stage_runtime_base_markers(entries: list[dict], sources: dict[int, Entry],
                                nodes: dict[int, ET.Element],
                                by_id: dict[int, dict]) -> None:
    """RT-4.3 (O9/O1): stage structurally clean relative-address values.

    Runs after WP-38/WP-50 provider adoption over every remaining blocked
    value whose refusal is one of the two relative-address refusals:

    - address-bearing ancestor further up (plain or symbol base): the record
      is recompiled with the skip-fold, so addressless intermediates between
      the record and its base are transparent (``skip=True``).  The
      record's own pointer offsets are inlined into the folded expression
      by ``_effective_address``; a symbol base rides the ordinary
      dependency machinery.
    - no address-bearing ancestor at all, no pointer offsets on the record
      or anywhere on the chain: the record is staged on the runtime-base
      marker — its address becomes the folded signed-hex relative total on
      the expression profile, the nearest heading ancestor is marked
      ``runtime_base_target`` and the engine resolves
      ``anchor base + offset`` at activation once the table scripts have
      written the anchor's live base (``set_dynamic_address``).  Until then
      the row is visible but inert; activation names the missing anchor.

    An addressless heading carrying pointer offsets below a relative record
    keeps its byte-for-byte refusal (ambiguous inherited base); a relative
    ancestor with a non-hex address (symbol, cast, expression) is not
    folded and the record stays blocked.  Addressless script/value
    ancestors on the chain are transparent for the staging walk; the
    base-provenance question is decided per anchor: an anchor heading that
    hangs directly under a supported addressless script with
    symbol-registration intent is the WP-38 provider-group shape - the
    table intends that script's runtime symbol as the group's base - so
    its rows keep the named refusal fail-closed instead of being
    silently rebased onto a runtime-base marker.
    """
    all_sources = tuple(sources.values())
    for entry in entries:
        if entry["kind"] != "blocked" or entry.get("source_kind") != "value":
            continue
        reason = entry.get("reason")
        if reason not in (
                "Relative address cannot skip an addressless script/value ancestor.",
                "Relative address has no address-bearing ancestor."):
            continue
        source = sources[entry["id"]]
        own = (source.address or "").strip()
        if not _STAGE_RELATIVE_RE.match(own):
            continue
        # Walk the source ancestry once, classifying it (the source model
        # is canonical for addresses; the plan only contributes the
        # anchor's provider-marker state below).  Addressless
        # script/value records on the chain are transparent for the
        # staging walk; the base-provenance question is decided per
        # anchor by the provider-group-shape gate below.
        anchor_id = None
        address_ancestor = None
        intermediates: list[int] = []
        ambiguous = False
        cur = source
        visited = {source.id}
        while True:
            parent_id = cur.parent_id
            if (parent_id is None or parent_id not in sources
                    or parent_id in visited or len(visited) >= 64):
                break
            visited.add(parent_id)
            anc = sources[parent_id]
            if anc.pointer_offsets:
                ambiguous = True
            addr = (anc.address or "").strip()
            if addr:
                if addr.startswith(("+", "-")) and _STAGE_RELATIVE_RE.match(addr):
                    intermediates.append(parent_id)
                    cur = anc
                    continue
                address_ancestor = parent_id
                break
            if anc.is_group_header:
                if anchor_id is None:
                    anchor_id = parent_id
            cur = anc
        profile = None
        if source.variable_type in _PROFILE_VALUE_TYPES:
            properties = {key: nodes[entry["id"]].findtext(key)
                          for key in ("ByteLength", "BitStart", "BitLength",
                                      "ShowAsBinary", "Length", "Unicode",
                                      "CodePage", "ZeroTerminate")}
            properties.update(ShowAsHex=source.show_as_hex,
                              ShowAsSigned=source.show_as_signed)
            if source.variable_type == "String":
                properties = {key: value for key, value in properties.items()
                              if value is not None}
            try:
                profile = prepare_value_profile(source.variable_type, properties)
            except AAError:
                continue
            if not profile["actionable"]:
                continue
        if address_ancestor is not None:
            # Skip-fold: an address-bearing ancestor further up provides the
            # base; addressless intermediates are transparent.
            try:
                folded = _effective_address(source, sources, skip=True)
            except AAError:
                continue
            if not folded.strip():
                continue
            entry["kind"] = "value"
            entry["supported"] = True
            entry["reason"] = ("Native relative value; the inherited base is "
                               "resolved at runtime from the address-bearing "
                               "ancestor record.")
            entry["address"] = folded
            entry["address_profile"] = "expression/v1"
            entry["pointer_offsets"] = []
            required = advanced_expression_symbols(folded)
            for symbol in required:
                try:
                    validate_symbol(symbol)
                except AAError:
                    entry["kind"] = "blocked"
                    entry["supported"] = False
                    entry["reason"] = "Unsupported address expression in the " \
                                      "skipped relative base."
                    entry.pop("value_profile", None)
                    entry["dropdown"] = {"choices": [], "read_only": False}
                    continue
            entry["requires"] = required
            entry["dependency_ids"] = []
            if profile is not None:
                entry["value_profile"] = profile
            try:
                entry["dropdown"] = (_string_dropdown(source, nodes, profile)
                                      if source.variable_type == "String"
                                      else _dropdown(source, all_sources, profile))
            except DropdownLinkMissingError:
                entry["dropdown"] = {"choices": [], "read_only": False}
            except AAError as exc:
                entry["kind"] = "blocked"
                entry["supported"] = False
                entry["reason"] = str(exc)
                entry["dropdown"] = {"choices": [], "read_only": False}
                entry.pop("value_profile", None)
            continue
        if ambiguous or source.pointer_offsets:
            # An addressless heading with pointer offsets on the chain - or
            # the record's own pointer offsets - cannot be expressed as the
            # flat staged total; the named refusal stays byte-for-byte.
            continue
        if anchor_id is None:
            continue
        anchor = by_id[anchor_id]
        if anchor.get("address_provider") is not None:
            # A proven provider binding already serves this heading; the
            # WP-38/WP-50 adoption above owns those rows.
            continue
        if _anchor_parent_provides_symbols(by_id, sources[anchor_id].parent_id):
            # The WP-38 provider-group shape: the anchor hangs directly
            # under the script that registers the group's base symbol,
            # so the table intends a symbol base, not a heading base
            # written at runtime.  Staging here would silently rebase
            # the group; the named relative-address refusal stays
            # fail-closed.
            continue
        total = int(own.lstrip("+-") or "0", 16)
        if own[0] == "-":
            total = -total
        for mid_id in intermediates:
            mid_addr = (sources[mid_id].address or "").strip()
            if not _STAGE_RELATIVE_RE.match(mid_addr):
                continue
            value = int(mid_addr.lstrip("+-"), 16)
            if mid_addr[0] == "-":
                value = -value
            total += value
        if abs(total) > 0x7FFFFFFFFFFFFFFF:
            continue
        staged_address = f"+{total:X}" if total >= 0 else f"-{abs(total):X}"
        entry["kind"] = "value"
        entry["supported"] = True
        entry["reason"] = (
            f"Staged relative value: the group base (heading {anchor_id} "
            f"'{anchor['label']}') has no static address and no supported "
            f"provider; it is written at runtime by the table scripts. "
            f"Activation requires that live base and names the anchor "
            f"while it is missing.")
        entry["address"] = staged_address
        entry["address_profile"] = "expression/v1"
        entry["pointer_offsets"] = []
        entry["requires"] = []
        entry["dependency_ids"] = []
        entry["runtime_base_required"] = True
        entry["runtime_base_anchor"] = anchor_id
        if profile is not None:
            entry["value_profile"] = profile
        try:
            entry["dropdown"] = (_string_dropdown(source, nodes, profile)
                                  if source.variable_type == "String"
                                  else _dropdown(source, all_sources, profile))
        except DropdownLinkMissingError:
            entry["dropdown"] = {"choices": [], "read_only": False}
        except AAError as exc:
            entry["kind"] = "blocked"
            entry["supported"] = False
            entry["reason"] = str(exc)
            entry["dropdown"] = {"choices": [], "read_only": False}
            entry.pop("value_profile", None)
            continue
        anchor["runtime_base_target"] = True


def _table_lua_source(root) -> str:
    """Gather the table-Lua source per the load-time contract (L5-19).

    A table-Lua section may hold the main body as the direct text of
    <LuaScript> plus several named script tabs as direct child elements;
    CE combines them at load time.  The combined source is the direct text
    (main body), then, in document order, the full text of every direct
    child element.  Empty/whitespace-only parts are skipped and the
    remaining parts join with a single newline.  A main-body-only section
    yields exactly the legacy findtext result.
    """
    lua = root.find('LuaScript')
    if lua is None:
        return ''
    parts = [lua.text or '']
    for child in lua:
        parts.append(''.join(child.itertext()))
    return '\n'.join(part for part in parts if part.strip())


def _entry_node_maps(root) -> tuple[dict[int, ET.Element], dict[int, str]]:
    """Map CheatEntry IDs to their XML nodes and AssemblerScript texts.

    WP-25 follow-up: duplicate IDs resolve keep-first (the first occurrence
    wins), matching the table reader's keep-first model, so the body of the
    kept record is the one that gets compiled.  A last-wins dict
    comprehension would silently replace the kept record's body with the
    body of a dropped duplicate.
    """
    nodes: dict[int, ET.Element] = {}
    scripts: dict[int, str] = {}
    for node in root.findall(".//CheatEntry"):
        identifier = int(node.findtext("ID") or "-1")
        if identifier not in nodes:
            nodes[identifier] = node
            scripts[identifier] = node.findtext("AssemblerScript") or ""
    return nodes, scripts


def compile_table(path: str | Path, process_name: str, title: str | None = None,
                  selected_ids: list[int] | set[int] | tuple[int, ...] | None = None,
                  user_symbols: dict[str, int] | None = None,
                  *, architecture: str = "x64", debug_log: bool = False) -> dict:
    """Return all records with explicit supported/blocked states and reasons.

    ``user_symbols`` (RT-4.6) is an optional user-symbol import map: valid
    symbol names (case-insensitive) to static 64-bit addresses.  A symbol
    the operator imports covers a zero-candidate requirement exactly like
    a table-level user-defined symbol (no record dependency), and the
    engine seeds it after the UDS seed, so an import overrides a
    table-level definition of the same name.  Record providers always win.
    """
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
    # RT-3: legacy binary sources are not XML; the clean-room conversion
    # (carried on the table) is the bounded, DTD-free parser input, while
    # XML sources keep the raw file bytes.
    root = ET.fromstring(table.converted_xml if table.converted_xml is not None else data)
    nodes, scripts = _entry_node_maps(root)
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
        bootstrap = prepare_lua_bootstrap(_table_lua_source(root))
    from .nth_aob import prepare_helper_contract
    nth_helper=prepare_helper_contract(bootstrap) if bootstrap is not None else None
    entries: list[dict] = []
    labels_by_id: dict[int, dict] = {}
    # WP-45 (GC-E9): named plan warnings for dangling dropdown links that
    # demote to an empty list instead of blocking the record.
    dropdown_warnings: list[str] = []
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
        # WP-40: the plan mirrors the record's source <Hotkey> bindings
        # byte-exactly (the plan validators re-derive the list from
        # source_hotkey_count).  Records without source hotkeys keep the
        # legacy plan shape (no key) so pinned canonical plans of
        # hotkey-free tables stay byte-stable.
        if source.hotkeys:
            entry["hotkeys"] = [{"keys": list(hk.keys), "action": hk.action,
                                 "value": hk.value, "description": hk.description,
                                 "active": hk.active} for hk in source.hotkeys]
        entries.append(entry)
        try:
            # CE display parity (field fix 2026-10-30, South of Midnight):
            # moAlwaysHideChildren marks the flagged entry's whole subtree
            # as non-renderable in the trainer UI; the parent row stays the
            # interface and engine-side activation/cascade is unaffected.
            # Additive marker, set only for records that carry children.
            if source.has_children and "moAlwaysHideChildren" in source.options:
                entry["hidden_children"] = True
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
                # WP-14 (C2): multi-step tables attach child-activation
                # propagation to AA/Lua script records whose children
                # reference symbols the script registers at activation.
                # Script parents get the tested flag classes;
                # moBindActivation has no derived contract and stays a
                # visible named block.  Value parents (pointer-chain
                # "base" records) carry the same CT flags, but a value
                # has no activation of its own, so the flags are inert
                # there and the record compiles as an ordinary value;
                # other non-script, non-heading parents remain fail-closed
                # with a named reason.
                if source.kind == "value":
                    pass
                elif source.kind != "script":
                    raise AAError("Parent/child activation propagation is unsupported "
                                  "(script parents and group headings only).")
                else:
                    if "moBindActivation" in source.options:
                        raise AAError("moBindActivation on a script parent has no derived contract; "
                                      "activation stays blocked (named block).")
                    if ("moActivateChildrenAsWell" in source.options
                            and "moDeactivateChildrenAsWell" in source.options):
                        flag = "required_dependency"
                    elif "moActivateChildrenAsWell" in source.options:
                        flag = "direct_activation"
                    else:
                        flag = "collective_off"
                    entry["parent_activation"] = flag
            if source.kind == "script":
                # Async records (CT Async="1") keep their regular profile; the
                # lifecycle marker is attached after dependency analysis (see
                # async_ids pass below).
                if has_lua_sections(scripts[source.id]):
                    program = prepare_lua_program(scripts[source.id], process_name, bitness=bitness,nth_aob_helper=nth_helper)
                    entry.update(lua_program=program, requires=program['requires'], provides=program['provides'],
                                 enable=[], disable=[], one_shot=bool(program.get('one_shot', False)),
                                 reason="Native Lua/AA; Lua runs during this record's owned activation.")
                    # WP-14 (C3): statically extract a record-ID activation
                    # set (master-toggle pattern) from the embedded Lua.  The
                    # extraction is pure text; any ambiguity leaves the record
                    # on its ordinary Lua profile with no activation_sets.
                    from .lua_activation_sets import extract_activation_sets
                    sets = extract_activation_sets(program["source"], set(sources), own_id=source.id)
                    if sets is not None:
                        entry["activation_sets"] = sets
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
                    # WP-37: keep the exact label context of this attempt so
                    # the named-refusal re-derivation below reproduces the
                    # identical prepare call.
                    labels_by_id[source.id] = labels_arg
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
                                "native converter write gate is not implemented yet (AP-08.7).")
                        raise AAError(
                            f"Custom value type '{name}' has no static definition; blocked "
                            "until a converter/write gate exists (AP-08.7).")
                    raise AAError(f"Unsupported value type: {source.variable_type}.")
                # WP-33: ShowAsHex Float/Double records are raw IEEE-754
                # bit-pattern edits (fixed-size raw write, struct round-trip);
                # no longer refused here.
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
                # WP-32: a value record without any address cannot anchor a
                # write; demote it to a non-actionable navigation placeholder
                # (template row) instead of a blocked record.  The zero-length
                # profile placeholders above already demoted with their own
                # reason; this covers every other simple type and every
                # actionable profile.  Children whose expression needs the
                # missing base stay blocked (relative-address refusal).
                if entry["kind"] == "value" and not (source.address or "").strip():
                    if source.pointer_offsets:
                        raise AAError("An addressless placeholder cannot carry pointer offsets.")
                    entry.pop("value_profile", None)
                    entry["kind"] = "heading"
                    entry["reason"] = _ADDRESSLESS_PLACEHOLDER_REASON
                    entry["address"] = ""
                    continue
                _compile_value_address(entry, source, sources)
                entry["dropdown"] = (_string_dropdown(source,nodes,entry['value_profile'])
                                     if source.variable_type=='String'
                                     else _dropdown(source, table.entries, entry.get("value_profile")))
            else:
                raise AAError("Record has no implemented native action or address.")
        # AddressExpressionError is a plain ValueError (not an AAError), so it
        # is caught explicitly to keep a malformed expression per-record
        # instead of aborting the whole table (WP-20).
        except DropdownLinkMissingError as exc:
            # WP-45 (GC-E9): a dangling DropDownLink demotes the linked
            # dropdown to an empty plain list (CE shows an empty list and
            # keeps the record writable); the record itself stays supported
            # and actionable, with a named plan warning.
            entry["dropdown"] = {"choices": [], "read_only": False}
            dropdown_warnings.append(
                f"Record {source.id} ('{source.label}'): {exc} "
                "The linked dropdown is demoted to an empty list.")
        except (AAError, LuaProgramError, ValueTypeError, AddressExpressionError) as exc:
            if _is_inert_no_action(str(exc)):
                # WP-44: demote the no-action script to a supported inert
                # heading; the record keeps no executable metadata, no
                # cascade promise and no activation marker.
                entry["kind"] = "heading"
                entry["reason"] = _INERT_SCRIPT_REASON
                entry.pop("parent_activation", None)
            else:
                _block(entry, str(exc))
    # WP-37: Lua-owned symbol handover contract.  A symbol is *externally
    # owned* when exactly one supported record provides it through a
    # handover-capable mechanism: (a) embedded record Lua that proves a
    # registerSymbol/unregisterSymbol pair (WP-14 C1 extraction), and/or
    # (b) an allocation-only program (WP-29 profile) that registers its
    # allocation.  Consumers may require such symbols without registering
    # them themselves; the owning record becomes their activation
    # dependency and releases the symbol exactly once on its own
    # deactivation.  Contested symbols (two or more raw providers) stay out
    # of the map and keep the ordinary keep-first provider rule below.
    # Table-level Lua is scanned with the same extractor but can never
    # become a map value: it has no owning record to name as releaser, so
    # any symbol it proves to register also stays out of the published map.
    raw_providers: dict[str, list[int]] = {}
    for entry in entries:
        if not entry["supported"] or entry["kind"] != "script":
            continue
        record_text = scripts[entry["id"]]
        if "lua_program" in entry:
            try:
                # WP-46 part 2 (GC-E12): drive the one-shot adoption branch
                # with the entry's canonical flag so the map and the entry's
                # provides never diverge.
                lua_symbols = lua_symbol_provides(
                    record_text,
                    one_shot=entry["lua_program"].get("one_shot", False))
            except LuaProgramError:
                lua_symbols = []
            for symbol in lua_symbols:
                raw_providers.setdefault(symbol.casefold(), []).append(entry["id"])
            static = entry["lua_program"].get("static_program")
            if isinstance(static, dict) and static.get("allocation_only"):
                for symbol in static["provides"]:
                    raw_providers.setdefault(symbol.casefold(), []).append(entry["id"])
        elif "program" in entry and entry["program"].get("allocation_only"):
            for symbol in entry["program"]["provides"]:
                raw_providers.setdefault(symbol.casefold(), []).append(entry["id"])
    # WP-54 (b): table-scope symbol registration evidence - the module's
    # literal-pair extractor applied to the combined table source (one-shot
    # adoption over the whole unphased text: the table scope registers at
    # load and retires with the attach, so a name that is also unregistered
    # in the source does not stay live for the table lifetime).  Feeds the
    # zero-candidate consumer fallback in _dependencies and the plan field
    # emitted after the selection closure (residual rule).
    table_lua_symbols: set[str] = set()
    if bootstrap is not None:
        from .lua_symbol_providers import extract_table_lua_symbols
        table_lua_symbols = {symbol.casefold()
                             for symbol in extract_table_lua_symbols(bootstrap["source"])}
    # WP-37: the external-ownership exclusion keeps the baseline's
    # phase-aware claim semantics (the table source parsed as a program;
    # unparsable or unphased sources claim nothing), distinct from the
    # WP-54 attach-lifetime set above.
    table_lua_claimed: set[str] = set()
    if bootstrap is not None:
        try:
            table_lua_claimed = {symbol.casefold()
                                 for symbol in lua_symbol_provides(bootstrap["source"])}
        except LuaProgramError:
            table_lua_claimed = set()
    external_context = frozenset(symbol for symbol, owners in raw_providers.items()
                                 if len(owners) == 1 and symbol not in table_lua_claimed)
    # RT-4.5 (O5): the named handover refusals name the single owning
    # record; ambiguous (multi-owner) symbols and table-Lua claims keep
    # the generic refusal.
    external_owner_ids = {symbol: owners[0] for symbol, owners in raw_providers.items()
                          if len(owners) == 1 and symbol not in table_lua_claimed}
    # Wave B1: re-derive the generic cleanup refusals for blocked records
    # with the external-ownership context so the named handover reasons
    # surface; only a re-derivation that yields a WP-37 named reason
    # replaces the stored reason.  (RT-4.1: the wildcard-cleanup refusal
    # is gone — the sweep now scopes to the program's own names, so no
    # static re-derivation or block is needed for it.)
    from .aa_program import prepare_program
    from .global_alloc import has_global_alloc
    for entry in entries:
        if entry["supported"]:
            continue
        reason = entry.get("reason", "")
        if not (reason == _UNREGISTER_EXACT_REASON
                or reason.endswith(_CLEANUP_OWNED_REASON)):
            continue
        text = scripts.get(entry["id"])
        if text is None:
            continue
        new_reason = None
        try:
            if has_lua_sections(text):
                prepare_lua_program(text, process_name, bitness=bitness,
                                    nth_aob_helper=nth_helper,
                                    external_owned=external_context,
                                    external_owners=external_owner_ids)
            elif not has_global_alloc(text):
                try:
                    compile_script(text, external_owned=external_context,
                                   external_owners=external_owner_ids)
                except AAError as bounded_error:
                    one_shot = None
                    try:
                        one_shot = compile_one_shot(text)
                    except AAError:
                        pass
                    if one_shot is None:
                        try:
                            prepare_program(text, process_name, bitness=bitness,
                                            labels=labels_by_id.get(entry["id"]),
                                            external_owned=external_context,
                                            external_owners=external_owner_ids)
                        except AAError as program_error:
                            new_reason = (str(bounded_error) + " Native assembly: "
                                          + str(program_error))
        except (AAError, LuaProgramError) as exc:
            new_reason = str(exc)
        if new_reason is not None and _EXTERNAL_RELEASE_REASON in new_reason:
            entry["reason"] = new_reason
    async_ids = {source.id for source in table.entries
                 if source.kind == "script" and source.async_script}
    # WP-46 (part 1): table-level <UserdefinedSymbols> act as static symbol
    # definitions for every record; they provide a symbol only when no
    # supported record provides it (zero-candidate fallback inside
    # _dependencies), so record providers always win.
    uds_symbols = {symbol.name.casefold(): symbol.address
                   for symbol in table.user_defined_symbols}
    # RT-4.6: the optional user-symbol import (validated, casefolded) joins
    # the same zero-candidate fallback, and the raw-source registration
    # survey feeds the per-symbol report classification.
    user_symbols = _normalize_user_symbols(user_symbols)
    source_registered, api_call_targets = _symbol_source_survey(scripts)
    _dependencies(entries, selected, uds_symbols, table_lua_symbols,
                  user_symbols, source_registered, api_call_targets)
    # WP-38: adopt proven runtime bases for blocked relative values before
    # the selection closure and the staged/recursive post-passes see the
    # final supported state (the recompiled values carry no symbol
    # dependencies, so dependency analysis output stays intact).
    dropdown_warnings.extend(_adopt_dynamic_address_providers(entries, sources, nodes))
    # Async records (CT Async="1") keep their regular profile. The lifecycle
    # marker is attached after dependency analysis so only entries that are
    # still supported in their final state carry it; every supported shape
    # (Lua, global, one-shot, program, byte patch) gets the same contract
    # for the engine, independent of the branch that prepared it.
    for entry in entries:
        # WP-44: an inert demoted script has no activation to defer, so it
        # never receives the async lifecycle marker.
        if (entry["id"] in async_ids and entry["supported"]
                and not _is_inert_script(entry)):
            entry["async"] = True
            prefix = entry["reason"] + " " if entry["reason"] else ""
            entry["reason"] = prefix + (
                "Async activation: runs only after a confirmed attach, "
                "pending until the effect is confirmed."
            )
    by_id = {entry["id"]: entry for entry in entries}
    # WP-37: publish the external-ownership map.  A symbol enters only when
    # exactly one raw provider exists, that record survived keep-first,
    # wave B and the staged cascade, and the table Lua does not also
    # register it; contested or table-Lua-claimed symbols stay private to
    # the ordinary dependency machinery.
    external_owned_providers: dict[str, int] = {}
    for symbol, owners in raw_providers.items():
        if len(owners) != 1 or symbol in table_lua_claimed:
            continue
        owner_id = owners[0]
        if by_id[owner_id]["supported"]:
            external_owned_providers[symbol] = owner_id
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
    # Staged capability (WP-14, C1): every supported non-heading record
    # whose required symbols are all uniquely provided by other supported
    # records carries explicit staged metadata.  The engine gates value
    # reads, writes and freeze on provider liveness; scripts keep their
    # ordinary dependency-ordered activation.  Provider labels use the
    # entry path so the UI can name the unlock source.
    for entry in entries:
        if (entry["supported"] and entry["kind"] in ("script", "value")
                and entry.get("dependency_ids")):
            provider_ids = sorted(set(entry["dependency_ids"]))
            entry["staged"] = {
                "provider_ids": provider_ids,
                "provider_labels": [by_id[pid]["path"] for pid in provider_ids],
            }
    # Parent/child activation (AP-07 stage 3, extended by WP-14 C2): a
    # flagged heading or script parent routes its whole selected/supported
    # subtree through the tested activation policy; the flagged parent's
    # class inherits down the entire subtree, while unsupported, unselected
    # or non-actionable (WP-32 demoted addressless placeholder) descendants
    # stay outside the topology.
    # Markers that end up without any cascade target are dropped, so the
    # plan only promises activation where the engine has targets.
    children_by_parent = {}
    for entry in entries:
        if entry["parent_id"] is not None:
            children_by_parent.setdefault(entry["parent_id"], []).append(entry["id"])
    parent_relations = {}
    for entry in entries:
        flag = entry.get("parent_activation")
        if (flag is None or entry["kind"] not in ("heading", "script")
                or not entry["supported"] or not entry["selected"]):
            continue
        children = {}
        stack = [entry["id"]]
        while stack:
            node_id = stack.pop()
            for child_id in children_by_parent.get(node_id, ()):
                child = by_id[child_id]
                if (child["supported"] and child["selected"]
                        and not _is_addressless_placeholder(child)
                        and not _is_inert_script(child)):
                    children[child_id] = flag
                stack.append(child_id)
        if children:
            parent_relations[entry["id"]] = children
    for entry in entries:
        # A flagged parent without any supported+selected cascade target
        # promises nothing, so the marker is dropped.  Headings revert to
        # the plain navigation reason; script parents keep their own
        # reason.  A moBindActivation marker is never dropped: the tested
        # contract is a visible named refusal, whether or not the group
        # sits in a cascade.
        if entry.get("parent_activation") is not None and entry["id"] not in parent_relations:
            entry.pop("parent_activation")
            if entry["kind"] == "heading":
                entry["reason"] = "Navigation heading; CE group activation is not executed."
        elif (entry["kind"] == "script"
                and entry.get("parent_activation") is not None):
            # Script-parent flag-class note: the compile branches overwrite
            # entry["reason"] below/above, so it is appended here, after
            # the final supported/selected state is known.
            note = ("Native script parent activation: " + entry["parent_activation"]
                    + " flag class applies to the whole subtree.")
            if note not in entry["reason"]:
                entry["reason"] = (entry["reason"] + " " if entry["reason"] else "") + note
    # WP-25 follow-up (a): table-reader warnings (e.g. the per-duplicate-ID
    # "kept first occurrence" report, once the keep-first reader lands) are
    # forwarded into the plan so the creator UI can surface them; the
    # compile-level warnings below follow in document order.
    warnings = list(table.warnings)
    omitted = []
    if table.has_table_lua:
        warnings.append("Table Lua is not executed on load. Read-only helpers replay in each Lua activation; top-level writes, callbacks and unsupported APIs block activation.")
    for section in table.sections:
        # RT-5 item A: <Files> is interpreted (embedded_files plan field,
        # decoded fail-closed at table load); it no longer counts as
        # omitted.
        if section.name not in {"CheatEntries", "LuaScript", "UserdefinedSymbols",
                                "Files"}:
            omitted.append(section.name)
    if omitted:
        warnings.append("Table-level sections not interpreted: " + ", ".join(sorted(set(omitted))) + ".")
    # WP-45 (GC-E9): named warnings for dangling dropdown-link demotions,
    # in document order (per-record loop, then adoption pass).
    warnings.extend(dropdown_warnings)
    # WP-40: per-case named warnings for source hotkeys that cannot be
    # registered (the engine keeps the first-wins policy for conflicts at
    # runtime; the plan records every original binding either way).
    for entry in entries:
        for hotkey in entry.get("hotkeys", ()):
            if not hotkey["active"]:
                continue
            keys = hotkey["keys"]
            if not keys:
                warnings.append(
                    f"Record {entry['id']} ('{entry['label']}'): hotkey ({hotkey['action']}) "
                    f"not registered: no parsable key.")
                continue
            key_text = format_hotkey_keys(keys)
            action = hotkey["action"]
            if action in VALUE_HOTKEY_ACTIONS:
                if entry["supported"] and entry["kind"] == "value":
                    continue
                warnings.append(
                    f"Record {entry['id']} ('{entry['label']}'): hotkey {key_text} ({action}) "
                    f"not registered: value row is not actionable.")
            elif action in ACTIVATION_HOTKEY_ACTIONS:
                # WP-53: every supported group heading is toggleable -
                # flagged headings run the parent-activation cascade,
                # plain moHideChildren headings toggle their own state.
                toggleable = entry["supported"] and (
                    entry["kind"] == "script"
                    or entry["kind"] == "heading")
                if toggleable:
                    continue
                reason = "record is blocked" if not entry["supported"] \
                    else "record has no activation action"
                warnings.append(
                    f"Record {entry['id']} ('{entry['label']}'): hotkey {key_text} ({action}) "
                    f"not registered: {reason}.")
            else:
                warnings.append(
                    f"Record {entry['id']} ('{entry['label']}'): hotkey {key_text} ({action!r}) "
                    f"not registered: unsupported action.")
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
    if debug_log:
        plan["debug_log"] = True
    if bootstrap is not None:
        plan['lua_bootstrap'] = bootstrap
        # WP-41: static per-table bootstrap metadata.  Plan time records the
        # refusal-free default; the engine fills executed/reasons on each
        # confirmed attach.  record_scripts_inactive counts supported script
        # records whose embedded Lua references a table top-level global,
        # regardless of selection (the banner denominator is the plan, not
        # the saved wishes).
        from .lua_bootstrap import record_table_lua_references, table_top_level_globals
        table_globals = table_top_level_globals(bootstrap['source'])
        plan['table_lua'] = {
            'executed': False,
            'reasons': [],
            'record_scripts_inactive': sum(
                1 for entry in entries
                if 'lua_program' in entry
                and record_table_lua_references(entry['lua_program']['source'],
                                                table_globals)),
        }
    if parent_relations:
        plan["parent_relations"] = {str(parent_id): {str(child_id): flag
                                                     for child_id, flag in children.items()}
                                    for parent_id, children in sorted(parent_relations.items())}
    if external_owned_providers:
        plan["external_owned_providers"] = {symbol: external_owned_providers[symbol]
                                            for symbol in sorted(external_owned_providers)}
    # WP-46 (part 1): table-level static symbol definitions from
    # <UserdefinedSymbols>.  Emitted only when non-empty (byte-stable plans
    # otherwise, WP-40 convention).  A symbol enters only when no supported
    # script record provides it — record providers always win — so the
    # engine seeds the runtime symbol table with exactly this residual map.
    supported_provides = {symbol.casefold()
                          for entry in entries
                          if entry["supported"] and entry["kind"] == "script"
                          for symbol in entry["provides"]}
    uds_plan = {key: uds_symbols[key] for key in sorted(uds_symbols)
                if key not in supported_provides}
    if uds_plan:
        plan["user_defined_symbols"] = uds_plan
    # RT-4.6: the optional user-symbol import, same residual rule as the
    # table-level UDS field — emitted only when non-empty (byte-stable
    # plans otherwise, WP-40 convention) and only for symbols no supported
    # script record provides (record providers always win).  The engine
    # seeds it after the UDS seed, so an import overrides a table-level
    # definition of the same name at runtime.
    user_plan = {key: user_symbols[key] for key in sorted(user_symbols)
                 if key not in supported_provides}
    if user_plan:
        plan["user_symbols"] = user_plan
    # RT-5 item A: embedded <Files> content. The plan carries the raw stored
    # Ascii85 text plus derived metadata (name, encoding, sha256, size),
    # sorted by casefolded name; emitted only when non-empty (byte-stable
    # plans otherwise, WP-40 convention).  Both plan validators re-derive
    # sha256/size from the stored text, so forged entries are refused.
    embedded_plan = [
        {"name": f.name, "encoding": f.encoding, "text": f.text,
         "sha256": f.sha256, "size": f.size}
        for f in sorted(table.embedded_files, key=lambda f: f.name.casefold())
    ]
    if embedded_plan:
        plan["embedded_files"] = embedded_plan
    # WP-54 (b): table-scope symbol names the combined table source proves
    # to register, minus the symbols a supported script record provides —
    # record providers always win, so the bootstrap skips symbols a
    # supported record owns (no runtime collision); under partial selection
    # the table symbol registers anyway and consumers without a selected
    # record provider resolve through it.  Emitted only when non-empty
    # (byte-stable plans otherwise, WP-40 convention); both plan gates
    # re-derive the field from plan["lua_bootstrap"]["source"].
    table_lua_symbol_plan = [name for name in sorted(table_lua_symbols)
                             if name not in supported_provides]
    if table_lua_symbol_plan:
        plan["table_lua_symbols"] = table_lua_symbol_plan
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
    if 'table_lua' in plan:
        from .lua_bootstrap import validate_table_lua_meta
        validate_table_lua_meta(plan['table_lua'])
        if 'lua_bootstrap' not in plan:
            raise NativeCompileError("Plan table-Lua metadata requires the table bootstrap source.")
    for name, size in (("table_sha256", 64), ("trainer_id", 16)):
        if not isinstance(plan.get(name), str) or re.fullmatch("[0-9a-f]{" + str(size) + "}", plan[name]) is None:
            raise NativeCompileError(f"Invalid native plan {name}.")
    if "debug_log" in plan and type(plan["debug_log"]) is not bool:
        raise NativeCompileError("Plan debug_log flag must be a boolean.")
    entries = plan.get("entries")
    if not isinstance(entries, list) or not entries or len(entries) > MAX_ENTRIES:
        raise NativeCompileError("Plan entries must be a bounded list.")
    ids: set[int] = set()
    try:
        for entry in entries:
            if not isinstance(entry, dict) or type(entry.get("id")) is not int or entry["id"] < 0 or entry["id"] in ids:
                raise NativeCompileError("Plan record IDs must be unique nonnegative integers.")
            ids.add(entry["id"])
        # WP-38: the plan-level ancestor walks (dynamic address provider
        # binding) need the full ID map before the per-entry pass.
        by_id = {entry["id"]: entry for entry in entries}
        for entry in entries:
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
            # RT-4.2 (R7): api_exports is an additive plan marker on
            # supported AA script records — a bounded mapping of exact
            # export name -> owning module basename for bare call targets
            # that no record, table-Lua or user-symbol provider serves.
            # The engine resolves each name against the attached target's
            # live PE export table at link time; an absent export fails
            # closed with a named refusal.  Every marker key must be a
            # record requirement (the symbol the program actually
            # references), and the marker never rides on non-script or
            # blocked records.
            api_exports = entry.get("api_exports")
            if api_exports is not None:
                if (not isinstance(api_exports, dict) or not api_exports
                        or len(api_exports) > 32):
                    raise NativeCompileError("API export markers must be bounded nonempty mappings.")
                if entry["kind"] != "script" or not entry["supported"]:
                    raise NativeCompileError("API export markers require a supported script record.")
                for export, module in api_exports.items():
                    if not isinstance(export, str) or not isinstance(module, str):
                        raise NativeCompileError("API export markers must map export names to module basenames.")
                    validate_symbol(export)
                    if re.fullmatch(r"[A-Za-z0-9._-]+\.(?:dll|exe)", module) is None:
                        raise NativeCompileError("API export modules must be PE basenames.")
                    if export.casefold() not in {require.casefold() for require in entry["requires"]}:
                        raise NativeCompileError("API export markers must reference a record requirement.")
                if len({export.casefold() for export in api_exports}) != len(api_exports):
                    raise NativeCompileError("Duplicate API export marker.")
            # WP-38/WP-50: the additive address_provider field is shape-
            # checked here (a symbol marker rides on a supported addressless
            # heading; a symbol-null marker rides on the supported addressless
            # target itself, heading or script); the provider cross-checks run
            # in the plan-wide pass below where the full ID map is available.
            marker = entry.get("address_provider")
            if marker is not None:
                if (not isinstance(marker, dict) or set(marker) != {"provider_id", "symbol"}
                        or type(marker.get("provider_id")) is not int
                        or marker.get("provider_id", -1) < 0
                        or (marker.get("symbol") is not None
                            and not isinstance(marker["symbol"], str))):
                    raise NativeCompileError("Invalid dynamic address provider metadata.")
                if marker["symbol"] is not None:
                    if (entry["kind"] != "heading" or not entry["supported"]
                            or entry.get("address") != "" or entry.get("pointer_offsets") != []
                            or _is_addressless_placeholder(entry)):
                        raise NativeCompileError(
                            "Dynamic address provider requires a supported addressless heading.")
                    validate_symbol(marker["symbol"])
                else:
                    # WP-50 (GC-E8): direct address-write provider; the target
                    # is the addressless record the provider's Lua writes the
                    # live base into (group heading or addressless script).
                    if (entry["kind"] not in {"heading", "script"} or not entry["supported"]
                            or entry.get("address") != "" or entry.get("pointer_offsets") != []
                            or _is_addressless_placeholder(entry)):
                        raise NativeCompileError(
                            "Dynamic address provider requires a supported addressless target record.")
            # RT-4.3 (O9/O1): the runtime-base markers are additive plan
            # metadata; shape-checked here, cross-checked against the full
            # ID map in the plan-wide pass below.
            if entry.get("runtime_base_required") is True:
                if (entry["kind"] != "value" or not entry["supported"]
                        or entry.get("address_profile") != "expression/v1"
                        or type(entry.get("runtime_base_anchor")) is not int):
                    raise NativeCompileError("Invalid runtime-base staged value metadata.")
            if entry.get("runtime_base_target") is True:
                if (entry["kind"] != "heading" or not entry["supported"]
                        or entry.get("address") != ""
                        or entry.get("pointer_offsets") != []):
                    raise NativeCompileError("Runtime-base target requires a supported addressless heading.")
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
                            # WP-19: the $process token names the main module of
                            # the attached process; the engine maps it to the
                            # plan's process_name at activation time, so the
                            # module-basename grammar does not apply to it.
                            if module != "$process":
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
                provides_cf = {symbol.casefold() for symbol in entry["provides"]}
                if entry.get("one_shot"):
                    # WP-46 part 2 (GC-E12): a one-shot record has an empty
                    # disable phase by contract (checked above), so the
                    # unregister side is empty by construction; the
                    # registration evidence alone must equal the claimed
                    # provides (the owner scope releases the symbol at
                    # detach).  Mirrors the engine gate's branch.
                    mismatch = registered != provides_cf
                else:
                    mismatch = (registered != unregistered
                                or registered != provides_cf)
                if (mismatch
                        or required != {symbol.casefold() for symbol in entry["requires"]}):
                    raise NativeCompileError("Script symbol dependency/registration metadata does not match its operations.")
                if not registered and not any(operation["op"] == "write" for operation in entry["enable"]):
                    raise NativeCompileError("Script must provide a symbol or guarded patch action.")
            elif entry["kind"] == "value":
                _validate_value_address(entry, by_id=by_id)
                if value_profile is None and entry.get("variable_type") not in SIMPLE_VALUE_TYPES:
                    raise NativeCompileError("Unsupported native value type.")
                if (type(entry.get("show_as_hex")) is not bool
                        or entry.get("show_as_signed") is not None and type(entry["show_as_signed"]) is not bool):
                    raise NativeCompileError("Invalid numeric display flags.")
                # WP-33: ShowAsHex Float/Double entries carry fixed-size raw
                # bit-pattern writes; the validator no longer refuses them.
                dropdown = entry.get("dropdown")
                if (not isinstance(dropdown, dict) or not isinstance(dropdown.get("choices"), list)
                        or type(dropdown.get("read_only")) is not bool):
                    raise NativeCompileError("Invalid dropdown plan.")
                for choice in dropdown["choices"]:
                    if (not isinstance(choice, dict) or not isinstance(choice.get("description"), str)):
                        raise NativeCompileError("Invalid dropdown choice.")
                    if choice.get("separator") is True:
                        # WP-24: separator rows are display-only metadata
                        # (empty value part in the CT); they are never
                        # selectable and must carry no value.
                        if choice.get("value") != "":
                            raise NativeCompileError("Separator dropdown choices must carry the empty value.")
                        continue
                    if "separator" in choice:
                        raise NativeCompileError("Dropdown separator marker must be true.")
                    if choice.get("writable") is False:
                        # RT-4.4 (O8/O26): display-only choice staged by a
                        # read-only (description-only) list; never selectable.
                        if not dropdown["read_only"]:
                            raise NativeCompileError("Display-only dropdown choices require a read-only dropdown.")
                        continue
                    if "writable" in choice:
                        raise NativeCompileError("Dropdown writable marker must be false.")
                    if choice.get("expression") is True:
                        # RT-4.4 (O8): bracketed expression choice; syntax is
                        # plan-checked, semantics resolve at write time.
                        if value_profile is not None:
                            raise NativeCompileError("Dropdown expression choices require a simple numeric record.")
                        try:
                            parse_expression(choice.get("value", ""))
                        except AddressExpressionError as exc:
                            raise NativeCompileError("Dropdown expression choice is not a valid address expression.") from exc
                        continue
                    if "expression" in choice:
                        raise NativeCompileError("Dropdown expression marker must be true.")
                    status, _refusal = _dropdown_choice_status(choice.get("value"), entry["variable_type"],
                                                               entry["show_as_hex"], entry["show_as_signed"],
                                                               value_profile)
                    if status == "refusal":
                        raise NativeCompileError("Dropdown values must be exact supported literals.")
                # RT-4.4 (O26): a read-only dropdown may stage zero
                # writable choices (display-only rows, or an empty
                # read-only view); the write path refuses anything
                # outside the (possibly empty) writable set.
            elif entry["kind"] == "heading" and "value_profile" in entry:
                # The only profile-backed navigation record is a canonical
                # zero-byte placeholder. Its address still anchors children.
                if (entry["variable_type"] not in {"Array of byte","String"} or value_profile["size"] != 0
                        or entry.get("dropdown") != {"choices": [], "read_only": False}
                        or entry.get("dependency_ids") != []
                        or entry.get("source_kind") not in {"value", "unsupported"}
                        or entry["reason"] != value_profile["reason"]):
                    raise NativeCompileError("Invalid non-actionable byte-array placeholder heading.")
                _validate_value_address(entry, allow_empty=True, by_id=by_id)
            elif _is_addressless_placeholder(entry):
                # WP-32: demoted addressless value record — canonical shape is
                # a supported navigation heading without address, profile,
                # offsets, dependencies or dropdown metadata.
                if (entry.get("value_profile") is not None or entry.get("address") != ""
                        or entry.get("pointer_offsets") != []
                        or entry.get("requires") != [] or entry.get("provides") != []
                        or entry.get("dependency_ids") != []
                        or entry.get("dropdown") != {"choices": [], "read_only": False}):
                    raise NativeCompileError("Invalid addressless placeholder heading.")
            elif _is_inert_script(entry):
                # WP-44: demoted no-action script — canonical shape: supported
                # navigation heading with the exact inert reason and no
                # executable metadata, dependencies or dropdown payload.
                if (entry.get("value_profile") is not None
                        or entry.get("program") is not None
                        or entry.get("lua_program") is not None
                        or entry.get("global_program") is not None
                        or entry.get("enable") or entry.get("disable")
                        or entry.get("requires") != [] or entry.get("provides") != []
                        or entry.get("dependency_ids") != []
                        or entry.get("dropdown") != {"choices": [], "read_only": False}):
                    raise NativeCompileError("Invalid inert script heading.")
            elif (entry["kind"] == "heading" and entry.get("source_kind") in {"value", "unsupported"}
                  and entry.get("variable_type") in SIMPLE_VALUE_TYPES | _PROFILE_VALUE_TYPES):
                # WP-32: any remaining value-type heading is a tampered
                # demoted placeholder; the canonical shapes above already
                # matched, so everything left is forged metadata.
                raise NativeCompileError("Value-type placeholder headings require canonical value metadata.")
        if 'table_lua' in plan and 'lua_bootstrap' in plan:
            # WP-41: the static inactive-record count must re-derive from the
            # entries' own embedded sources (same compiler algorithm as the
            # plan-time emission), so a forged count is refused by both gates.
            from .lua_bootstrap import (record_table_lua_references,
                                        table_top_level_globals)
            try:
                table_globals = table_top_level_globals(plan['lua_bootstrap']['source'])
                expected_inactive = sum(
                    1 for entry in entries
                    if isinstance(entry, dict)
                    and isinstance(entry.get('lua_program'), dict)
                    and record_table_lua_references(
                        entry['lua_program'].get('source', ''), table_globals))
            except ValueError as exc:
                raise NativeCompileError(str(exc)) from exc
            if plan['table_lua']['record_scripts_inactive'] != expected_inactive:
                raise NativeCompileError(
                    "Plan table-Lua inactive record count does not match its entries.")
        for entry in entries:
            parent = entry.get("parent_id")
            if parent is not None and (type(parent) is not int or parent not in ids or parent == entry["id"]):
                raise NativeCompileError("Invalid record parent ID.")
            # WP-38: the address_provider field must name a supported
            # addressless script that provides the symbol, and that provider
            # must not sit below the heading it serves (provider-to-base
            # cycle).  The relative-address allowance for provider-bound
            # values was checked in the per-entry address validation above.
            marker = entry.get("address_provider")
            if marker is not None:
                provider = by_id.get(marker["provider_id"])
                if provider is None:
                    raise NativeCompileError("Dynamic address provider references an unknown record.")
                if (provider is entry or provider["kind"] != "script"
                        or not provider["supported"] or provider.get("address")
                        or provider.get("pointer_offsets")):
                    raise NativeCompileError(
                        "Dynamic address provider must name a supported addressless script record.")
                if marker["symbol"] is not None:
                    if marker["symbol"].casefold() not in {name.casefold() for name in provider.get("provides", [])}:
                        raise NativeCompileError("Dynamic address provider does not provide the named symbol.")
                    if _is_descendant(by_id, provider["id"], entry["id"]):
                        raise NativeCompileError(
                            "Dynamic address provider must not be a descendant of the heading it serves.")
                else:
                    # WP-50 (GC-E8): symbol-null marker — the provider's
                    # embedded Lua must statically name the target record by
                    # exact description (re-derived from the embedded source,
                    # both idioms), and neither side may sit below the other
                    # (base/provider cycle).
                    lua_source = (provider.get("lua_program") or {}).get("source")
                    targets = (lua_dynamic_address_targets(lua_source)
                               if isinstance(lua_source, str) else [])
                    if entry.get("label") not in targets:
                        raise NativeCompileError(
                            "Dynamic address provider does not write the target record's address.")
                    if _is_descendant(by_id, provider["id"], entry["id"]):
                        raise NativeCompileError(
                            "Dynamic address provider must not be a descendant of the target it serves.")
                    if _is_descendant(by_id, entry["id"], provider["id"]):
                        raise NativeCompileError(
                            "Dynamic address target must not be a descendant of its provider.")
            if entry.get("runtime_base_required") is True:
                # RT-4.3 (O9/O1): the staged row must re-derive its whole
                # anchor contract (anchor exists, is a supported addressless
                # heading marked runtime_base_target, the row sits below it,
                # no address_provider marker rides the same chain).
                if not _runtime_base_marker_ok(by_id, entry):
                    raise NativeCompileError(
                        "Staged runtime-base row does not re-derive its anchor contract.")
            if entry.get("runtime_base_target") is True:
                referenced = any(
                    e.get("runtime_base_required") is True
                    and e.get("runtime_base_anchor") == entry["id"]
                    for e in entries)
                if not referenced:
                    raise NativeCompileError(
                        "Runtime-base target without any staged value record.")
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
            # WP-40: source hotkey projection must be bounded and re-derive
            # byte-exactly from the record's raw <Hotkey> count; records
            # without source hotkeys keep the legacy plan shape (no key),
            # which stays valid only while the count stays zero.
            hotkeys = entry.get("hotkeys")
            if "hotkeys" in entry:
                if (not isinstance(hotkeys, list)
                        or len(hotkeys) > MAX_HOTKEYS_PER_RECORD):
                    raise NativeCompileError("Record hotkey metadata must be a bounded list.")
                for hotkey in hotkeys:
                    if (not isinstance(hotkey, dict)
                            or set(hotkey) != {"keys", "action", "value",
                                               "description", "active"}):
                        raise NativeCompileError("Hotkey metadata fields are fixed.")
                    keys = hotkey["keys"]
                    if (not isinstance(keys, list) or len(keys) > 5
                            or any(type(code) is not int or not 0 < code <= 255
                                   for code in keys)
                            or keys != sorted(set(keys))):
                        raise NativeCompileError(
                            "Hotkey keys must be sorted unique codes up to 255.")
                    if (not isinstance(hotkey["action"], str) or not hotkey["action"]
                            or len(hotkey["action"]) > 64):
                        raise NativeCompileError(
                            "Hotkey action must be bounded nonempty text.")
                    for text in ("value", "description"):
                        if not isinstance(hotkey[text], str) or len(hotkey[text]) > 512:
                            raise NativeCompileError(
                                f"Hotkey {text} must be bounded text.")
                    if type(hotkey["active"]) is not bool:
                        raise NativeCompileError("Hotkey active flag must be a boolean.")
                source_count = entry.get("source_hotkey_count")
                if type(source_count) is not int or source_count != len(hotkeys):
                    raise NativeCompileError(
                        "Hotkey metadata count differs from the source record.")
            elif entry.get("source_hotkey_count") not in (None, 0):
                raise NativeCompileError(
                    "Hotkey metadata count differs from the source record.")
            dependencies = entry.get("dependency_ids", [])
            if (not isinstance(dependencies, list) or len(dependencies) > MAX_OPERATIONS
                    or any(type(item) is not int or item not in ids for item in dependencies)):
                raise NativeCompileError("Invalid record dependency IDs.")
            # WP-49 (GC-E7): a self-edge is a cycle no one-pass plan can order;
            # the compile-time DFS blocks it and the gate refuses a forged
            # copy of it in the serialized dependency list.
            if entry["id"] in dependencies:
                raise NativeCompileError(
                    "Record dependency IDs must not contain a self-edge.")
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
            # WP-37: the external-ownership map is optional on schema 2; when
            # present, every key/value pair must name a real, supported
            # script record that actually provides that symbol.
            external_owned = plan.get("external_owned_providers")
            if external_owned is not None:
                if plan["schema"] != 2:
                    raise NativeCompileError("external_owned_providers requires schema 2")
                if not isinstance(external_owned, dict):
                    raise NativeCompileError("external_owned_providers must be a symbol-to-provider map")
                for symbol, owner_id in external_owned.items():
                    if not isinstance(symbol, str) or not symbol:
                        raise NativeCompileError("external_owned_providers keys must be symbol names")
                    if type(owner_id) is not int or owner_id not in by_id:
                        raise NativeCompileError("external_owned_providers must reference known provider IDs")
                    owner = by_id[owner_id]
                    if not owner["supported"] or owner["kind"] != "script":
                        raise NativeCompileError("external_owned_providers must name supported script records")
                    if symbol.casefold() not in {name.casefold() for name in owner.get("provides", [])}:
                        raise NativeCompileError("external_owned_providers entries must match the provider's symbols")
            children_by_parent = {}
            for entry in entries:
                if entry.get("parent_id") is not None:
                    children_by_parent.setdefault(entry["parent_id"], []).append(entry["id"])
            expected_relations = {}
            for entry in entries:
                flag = entry.get("parent_activation")
                if flag is not None:
                    if (flag not in ("required_dependency", "direct_activation", "collective_off")
                            or entry["kind"] not in ("heading", "script")
                            or not entry["supported"]
                            or _is_addressless_placeholder(entry)
                            or _is_inert_script(entry)
                            or entry["id"] not in selected):
                        raise NativeCompileError(
                            "Parent flag class requires a supported selected heading or script parent.")
                    children = {}
                    stack = [entry["id"]]
                    while stack:
                        node_id = stack.pop()
                        for child_id in children_by_parent.get(node_id, ()):
                            child = by_id[child_id]
                            if (child["supported"] and child["id"] in selected
                                    and not _is_addressless_placeholder(child)
                                    and not _is_inert_script(child)):
                                children[child_id] = flag
                            stack.append(child_id)
                    if not children:
                        raise NativeCompileError("Parent flag class without any cascade target.")
                    expected_relations[entry["id"]] = children
            for entry in entries:
                if entry.get("parent_mo_bind") is True and (entry["kind"] != "heading"
                        or not entry["supported"] or _is_addressless_placeholder(entry)
                        or _is_inert_script(entry)
                        or entry["id"] not in selected):
                    raise NativeCompileError("moBindActivation marker requires a supported selected heading.")
            # WP-14 (C1): staged metadata must re-derive byte-exactly from
            # each supported non-heading entry's own dependency IDs, and is
            # forbidden everywhere else (blocked/heading records and entries
            # without dependencies).
            for entry in entries:
                stored_staged = entry.get("staged")
                if (entry["supported"] and entry["kind"] in ("script", "value")
                        and entry.get("dependency_ids")):
                    provider_ids = sorted(set(entry["dependency_ids"]))
                    expected = {"provider_ids": provider_ids,
                                "provider_labels": [by_id[pid]["path"]
                                                    for pid in provider_ids]}
                    if stored_staged != expected:
                        raise NativeCompileError(
                            "Staged metadata does not re-derive from the record dependencies.")
                elif stored_staged is not None:
                    raise NativeCompileError(
                        "Staged metadata requires supported non-heading dependency IDs.")
            # WP-14 (C3): activation-set metadata must re-derive
            # byte-exactly from each supported Lua script record's own
            # embedded source; it is forbidden on all other records.
            from .lua_activation_sets import extract_activation_sets
            for entry in entries:
                stored_sets = entry.get("activation_sets")
                if (entry["supported"] and entry["kind"] == "script"
                        and "lua_program" in entry):
                    expected = extract_activation_sets(
                        entry["lua_program"]["source"], ids, own_id=entry["id"])
                    if stored_sets != expected:
                        raise NativeCompileError(
                            "Activation-set metadata does not re-derive from the embedded Lua.")
                elif stored_sets is not None:
                    raise NativeCompileError(
                        "Activation-set metadata requires a supported Lua script record.")
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
        # WP-46 (part 1): the table-level user-defined symbol map is
        # strict-validated like every other additive plan field: a bounded
        # casefold-unique mapping of valid symbol names to 64-bit unsigned
        # addresses, with no overlap against the symbols a supported script
        # record actually provides (a forged map that would shadow a record
        # provider at runtime is refused).
        uds_map = plan.get("user_defined_symbols")
        if uds_map is not None:
            if plan["schema"] != 2:
                raise NativeCompileError("user_defined_symbols requires schema 2")
            if not isinstance(uds_map, dict) or len(uds_map) > MAX_UDS_ENTRIES:
                raise NativeCompileError("user_defined_symbols must be a bounded symbol map.")
            uds_keys: set[str] = set()
            for key, value in uds_map.items():
                if not isinstance(key, str) or not key:
                    raise NativeCompileError("user_defined_symbols keys must be symbol names.")
                try:
                    validate_symbol(key)
                except AAError as exc:
                    raise NativeCompileError(str(exc)) from exc
                folded = key.casefold()
                if folded in uds_keys:
                    raise NativeCompileError("Duplicate user-defined symbol name.")
                uds_keys.add(folded)
                if type(value) is not int or not (0 <= value <= 0xFFFFFFFFFFFFFFFF):
                    raise NativeCompileError("user_defined_symbols values must be 64-bit unsigned integers.")
            record_provides = {symbol.casefold()
                               for entry in entries
                               if entry.get("supported") and entry.get("kind") == "script"
                               for symbol in entry.get("provides", [])}
            if uds_keys & record_provides:
                raise NativeCompileError(
                    "user_defined_symbols may not shadow a record-provided symbol.")
        # RT-4.6: the optional user-symbol import map is strict-validated
        # exactly like the table-level UDS map (bounded, casefold-unique,
        # valid symbol names, 64-bit unsigned addresses, no shadowing of a
        # supported record provider — record providers always win).
        user_map = plan.get("user_symbols")
        if user_map is not None:
            if plan["schema"] != 2:
                raise NativeCompileError("user_symbols requires schema 2")
            if not isinstance(user_map, dict) or len(user_map) > MAX_UDS_ENTRIES:
                raise NativeCompileError("user_symbols must be a bounded symbol map.")
            user_keys: set[str] = set()
            for key, value in user_map.items():
                if not isinstance(key, str) or not key:
                    raise NativeCompileError("user_symbols keys must be symbol names.")
                try:
                    validate_symbol(key)
                except AAError as exc:
                    raise NativeCompileError(str(exc)) from exc
                folded = key.casefold()
                if folded in user_keys:
                    raise NativeCompileError("Duplicate user symbol name.")
                user_keys.add(folded)
                if type(value) is not int or not (0 <= value <= 0xFFFFFFFFFFFFFFFF):
                    raise NativeCompileError("user_symbols values must be 64-bit unsigned integers.")
            record_provides = {symbol.casefold()
                               for entry in entries
                               if entry.get("supported") and entry.get("kind") == "script"
                               for symbol in entry.get("provides", [])}
            if user_keys & record_provides:
                raise NativeCompileError(
                    "user_symbols may not shadow a record-provided symbol.")
        # RT-5 item A: embedded <Files> metadata — strict-validated by
        # re-deriving sha256 and size from the stored raw encoded text
        # (Ascii85 branch when the stored encoding is exactly 'Ascii85',
        # CE hex branch otherwise; bounded counts, 4 MiB per file, 16 MiB
        # total, duplicate names tolerated with first-match-wins lookup).
        # Refused here and, through the engine validator's delegation, by
        # both plan gates.
        embedded = plan.get("embedded_files")
        if embedded is not None:
            from .embedded_files import (EmbeddedFileError,
                                         validate_embedded_files)
            if plan["schema"] != 2:
                raise NativeCompileError("embedded_files requires schema 2")
            try:
                validate_embedded_files(embedded)
            except EmbeddedFileError as exc:
                raise NativeCompileError(str(exc)) from exc
        # WP-54 (b): the table-Lua symbol list is re-derived byte-exactly
        # from the table bootstrap source — the same literal-pair
        # extraction (one-shot adoption) plus the record-provider residual
        # rule the compiler emits — so a forged list is refused here and,
        # through the engine validator's delegation, by both plan gates.
        table_symbol_list = plan.get("table_lua_symbols")
        if table_symbol_list is not None:
            from .lua_symbol_providers import (MAX_PROVIDERS,
                                               extract_table_lua_symbols)
            if plan["schema"] != 2:
                raise NativeCompileError("table_lua_symbols requires schema 2")
            if "lua_bootstrap" not in plan:
                raise NativeCompileError("table_lua_symbols requires the table bootstrap source.")
            if (not isinstance(table_symbol_list, list)
                    or len(table_symbol_list) > MAX_PROVIDERS
                    or any(type(item) is not str or not item
                           for item in table_symbol_list)
                    or len({item.casefold() for item in table_symbol_list}) != len(table_symbol_list)):
                raise NativeCompileError(
                    "table_lua_symbols must be a bounded casefold-unique name list.")
            record_provides = {symbol.casefold()
                               for entry in entries
                               if entry.get("supported") and entry.get("kind") == "script"
                               for symbol in entry.get("provides", [])}
            # Same set-plus-sort rule the compiler emission uses (casefold
            # collapses distinct spellings of one name, so the expectation
            # stays deterministic even for a source that registers both).
            expected = sorted({name.casefold()
                               for name in extract_table_lua_symbols(plan["lua_bootstrap"]["source"])
                               if name.casefold() not in record_provides})
            if table_symbol_list != expected:
                raise NativeCompileError(
                    "table_lua_symbols does not re-derive from the table bootstrap source.")
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
