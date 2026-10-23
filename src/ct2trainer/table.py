"""Read the presentation metadata of a Cheat Engine XML table.

The Auto Assembler and Lua bodies remain opaque input. Cheat Engine itself owns
their execution later; this module intentionally does not interpret them.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from hashlib import sha256
from pathlib import Path
import math
import re
import xml.etree.ElementTree as ET


MAX_TABLE_BYTES = 32 * 1024 * 1024
MAX_ENTRIES = 20_000
MAX_ENTRY_DEPTH = 64
# WP-40: a source record may declare several hotkeys; the plan projection is
# bounded per record (the plan validators enforce the same bound).
MAX_HOTKEYS_PER_RECORD = 16
HOTKEY_ACTION_DEFAULT = "Toggle Activation"
# Legacy pre-XML binary tables (CE 5.x era) start with this 11-byte magic
# header.  WP-25 detected the 12-byte accidental "CHEATENGINE" + tab prefix
# (byte 12 is the low byte of the little-endian format-version DWORD, which
# is a tab for version 9) and refused it with a named error.  RT-3 detects
# the true 11-byte magic and parses the legacy layout through the
# clean-room converter in ct2trainer.legacy_ct.
LEGACY_BINARY_CT_HEADER = b"CHEATENGINE"
# Newest table version verified in the field.  CE 7.5 (the behavior
# reference) writes 45 (OpenSave.pas _CurrentTableVersion); 46 is issued
# by newer CE builds and is field-verified to load and compile unchanged
# (The Sinking City 2 table, 2026-10-21; 13 of the 30 pinned corpus
# tables are already v46).  Tables newer than this keep the
# unverified-reference warning.
LOCAL_CE_TABLE_VERSION = 46
ADVANCED_VALUE_TYPES = frozenset({"Array of byte", "Binary", "Custom"})
SIMPLE_VALUE_TYPES = frozenset({"Byte", "2 Bytes", "4 Bytes", "8 Bytes", "Float", "Double"})
HEX_INTEGER_TYPES = frozenset({"Byte", "2 Bytes", "4 Bytes", "8 Bytes"})
HEX_DIGITS_BY_TYPE = {"Byte": 2, "2 Bytes": 4, "4 Bytes": 8, "8 Bytes": 16}
# WP-46 (part 1): bound and fail-closed address grammar for the table-level
# <UserdefinedSymbols> section.  CE stores these addresses as hexadecimal
# absolute integers; an optional 0x/$ prefix is tolerated, at most 16 hex
# digits (64 bits).  A decimal-looking string is read as hex, matching how
# CE stores and displays the section.
MAX_UDS_ENTRIES = 4096
_UDS_ADDRESS = re.compile(r"^(?:0[xX]|\$)?[0-9A-Fa-f]{1,16}\Z")


class TableError(ValueError):
    """A table cannot be safely represented by the current inspector."""


@dataclass(frozen=True)
class RecordHotkey:
    """One <Hotkey> element of a source record (WP-40).

    ``keys`` holds the source decimal Windows virtual-key codes normalized to
    a sorted unique tuple (empty when nothing parsed); ``action`` is the
    source action text, with the missing-Action CE contract default applied;
    ``active`` mirrors the source ``Active`` attribute (default True).  Long
    text fields are projected to their bounded plan lengths (the full source
    text stays in the CT file itself).
    """

    keys: tuple[int, ...]
    action: str
    value: str
    description: str
    active: bool


@dataclass(frozen=True)
class UserDefinedSymbol:
    """One accepted <SymbolEntry> of the table-level <UserdefinedSymbols> section.

    Cheat Engine 7.x writes the (often empty) section into every table; a
    non-empty section defines static symbol addresses that act as table-level
    symbol definitions for every record.  Accepted entries are available to
    address-expression and AA symbol resolution (casefold-insensitive) only
    while no supported record provides the same symbol — record providers
    always win, and the compiler seeds exactly that residual set.
    """

    name: str
    address: int


@dataclass(frozen=True)
class Entry:
    id: int
    label: str
    path: str
    depth: int
    parent_id: int | None
    variable_type: str | None
    address: str | None
    kind: str
    is_group_header: bool
    activation_safe: bool
    has_checkbox: bool
    has_children: bool
    has_assembler_lua: bool
    assembler_sha256: str | None
    has_enable_section: bool
    has_disable_section: bool
    async_script: bool
    hotkey_count: int
    pointer_offsets: tuple[str, ...]
    options: tuple[str, ...]
    has_dropdown: bool
    dropdown_read_only: bool
    dropdown_choices: tuple[tuple[str, str], ...]
    dropdown_link: str | None
    show_as_hex: bool
    show_as_signed: bool | None
    custom_type_name: str | None
    script_external_action: bool
    external_action_apis: tuple[str, ...] = ()
    custom_type_known: bool = False
    dropdown_link_empty: bool = False
    # WP-14 static review signals (derived from the record's own script text;
    # the native compiler performs the strict cross-record contract checks).
    registers_symbols: bool = False
    activation_set_lua: bool = False
    hotkeys: tuple[RecordHotkey, ...] = ()

    def to_dict(self) -> dict:
        return asdict(self)


def prototype_value_editable(entry: Entry) -> bool:
    """Only formats with a defined v0.1 text/choice write path are editable."""
    return (entry.kind == "value" and entry.variable_type in SIMPLE_VALUE_TYPES
            and bool(entry.address and entry.address.strip())
            and (not entry.dropdown_link or entry.dropdown_link_empty)
            and not (entry.has_children and "moRecursiveSetValue" in entry.options)
            and (not entry.show_as_hex or entry.variable_type in HEX_INTEGER_TYPES)
            and all(value == "*" or numeric_literal_safe(
                value, entry.variable_type, entry.show_as_hex, entry.show_as_signed)
                    for value, _ in entry.dropdown_choices)
            and (not entry.dropdown_read_only
                 or any(value != "*" for value, _ in entry.dropdown_choices)))


def numeric_literal_safe(value: str, value_type: str | None, show_as_hex: bool,
                         show_as_signed: bool | None) -> bool:
    """Admit only literals CE cannot reinterpret as a Lua expression."""
    if not value or len(value) > 64:
        return False
    if show_as_hex:
        maximum = HEX_DIGITS_BY_TYPE.get(value_type or "")
        if maximum is None:
            return False
        sign = r"-?" if show_as_signed is True else ""
        match = re.fullmatch(sign + r"(?:0x)?([0-9A-Fa-f]+)", value)
        return match is not None and len(match.group(1)) <= maximum
    if value_type in HEX_INTEGER_TYPES:
        return re.fullmatch(r"-?[0-9]+", value) is not None
    if value_type in {"Float", "Double"}:
        if re.fullmatch(
            r"-?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?",
            value,
        ) is None:
            return False
        return math.isfinite(float(value))
    return False


def prototype_toggle_available(entry: Entry) -> bool:
    """Whether v0.1 renders a CE Active switch for this record."""
    if not entry.has_checkbox or not entry.activation_safe:
        return False
    if entry.has_children and any(option in entry.options for option in
                                  ("moActivateChildrenAsWell", "moDeactivateChildrenAsWell",
                                   "moBindActivation")):
        return False  # CE parent Active does not confirm every child action.
    if entry.kind == "script":
        return (entry.has_enable_section and entry.has_disable_section
                and not entry.async_script)
    if entry.kind == "group":
        return True
    return prototype_value_editable(entry)


@dataclass(frozen=True)
class SectionSummary:
    """Fingerprint of a table-level CT section, without executable text."""

    name: str
    child_count: int
    text_bytes: int
    xml_sha256: str


@dataclass(frozen=True)
class Table:
    source: Path
    source_sha256: str
    table_version: int
    entries: tuple[Entry, ...]
    has_table_lua: bool
    has_forms: bool
    has_custom_types: bool
    has_custom_type_records: bool
    custom_types: tuple
    sections: tuple[SectionSummary, ...]
    warnings: tuple[str, ...]
    user_defined_symbols: tuple[UserDefinedSymbol, ...] = ()
    # RT-3: for legacy binary sources this carries the clean-room converted
    # XML document that the XML pipeline actually parsed; the original
    # binary bytes remain the source identity (source/source_sha256).
    # XML sources keep None.  Not serialized by to_dict(): it is derivable
    # from the source bytes through ct2trainer.legacy_ct.
    converted_xml: bytes | None = None

    @property
    def counts(self) -> dict[str, int]:
        counts = {"total": len(self.entries), "headings": 0, "toggles": 0,
                  "raw_checkboxes": 0,
                  "values": 0, "unsupported": 0, "assembler_lua": 0,
                  "hotkeys": 0, "pointer_offsets": 0,
                  "async_scripts": 0, "dropdowns": 0, "dropdown_links": 0}
        for entry in self.entries:
            counts["raw_checkboxes"] += int(entry.has_checkbox)
            if entry.kind == "heading":
                counts["headings"] += 1
            elif entry.kind in ("script", "group"):
                counts["toggles"] += int(prototype_toggle_available(entry))
            elif entry.kind == "value":
                counts["values"] += 1
                counts["toggles"] += int(prototype_toggle_available(entry))
            else:
                counts["unsupported"] += 1
            counts["assembler_lua"] += int(entry.has_assembler_lua)
            counts["hotkeys"] += entry.hotkey_count
            counts["pointer_offsets"] += len(entry.pointer_offsets)
            counts["async_scripts"] += int(entry.async_script)
            counts["dropdowns"] += int(bool(entry.dropdown_choices))
            counts["dropdown_links"] += int(entry.dropdown_link is not None)
        return counts

    def to_dict(self) -> dict:
        return {
            "source": str(self.source),
            "source_sha256": self.source_sha256,
            "table_version": self.table_version,
            "local_ce_table_version": LOCAL_CE_TABLE_VERSION,
            "has_table_lua": self.has_table_lua,
            "has_forms": self.has_forms,
            "has_custom_types": self.has_custom_types,
            "has_custom_type_records": self.has_custom_type_records,
            "custom_types": [
                {"name": c.name, "format": c.format_text, "size": c.size,
                 "endianness": c.endianness, "inverse": c.inverse,
                 "signed": c.signed, "element_count": c.element_count,
                 "fields": [
                     {"size": f.size, "count": f.count, "offset": f.offset}
                     for f in c.fields]}
                for c in self.custom_types],
            "sections": [asdict(section) for section in self.sections],
            "counts": self.counts,
            "warnings": list(self.warnings),
            "user_defined_symbols": [
                {"name": symbol.name, "address": symbol.address}
                for symbol in self.user_defined_symbols
            ],
            "entries": [entry.to_dict() for entry in self.entries],
        }


def _label(raw: str | None, entry_id: int) -> str:
    label = (raw or "").strip()
    if len(label) >= 2 and label[0] == label[-1] == '"':
        label = label[1:-1]
    return label or f"Entry {entry_id}"


def _activates_children(element: ET.Element) -> bool:
    options = element.find("Options")
    return options is not None and any(options.attrib.get(name) == "1" for name in
                                       ("moActivateChildrenAsWell", "moBindActivation"))


def _deactivates_children(element: ET.Element) -> bool:
    options = element.find("Options")
    return options is not None and any(options.attrib.get(name) == "1" for name in
                                       ("moDeactivateChildrenAsWell", "moBindActivation"))


_EXTERNAL_ACTION_API_NAMES = {
    "shellexecute": "shellExecute",
    "messagedialog": "messageDialog",
}


def _script_external_action_apis(script: str) -> tuple[str, ...]:
    """Named external-action APIs a record script invokes.

    ``shellExecute`` is implemented by the native trainer as a safe no-op
    (WP-56); ``messageDialog`` is not implemented and fails activation
    with a named refusal.  The split keeps the table-level warnings
    accurate instead of one blanket "needs review" line.
    """
    return tuple(sorted({_EXTERNAL_ACTION_API_NAMES[match.group(1).casefold()]
                         for match in re.finditer(
                             r"\b(shellExecute|messageDialog)\s*\(", script, re.IGNORECASE)}))


def _script_has_external_action(script: str) -> bool:
    return bool(_script_external_action_apis(script))


def _script_registers_symbols(script: str) -> bool:
    """WP-14 signal: the record registers Auto Assembler symbols.

    Records that register (and release) symbols are staged providers for the
    native compiler; the static review report surfaces them so the reviewer
    can cross-check against the plan's ``provides`` field.
    """
    return bool(re.search(r"\bregistersymbol\s*\(", script, re.IGNORECASE))


def _script_activation_set_lua(script: str) -> bool:
    """WP-14 signal: embedded Lua toggles sibling records by record id.

    The native compiler statically extracts such loops into an activation
    set when every referenced id exists in the table; the static review
    report surfaces the pattern per record.
    """
    if not re.search(r"getMemoryRecordByID\s*\(", script):
        return False
    return bool(re.search(r"\.Active\s*=\s*(?:true|false)\b", script, re.IGNORECASE))


def _node_activation_safe(element: ET.Element, depth: int = 0) -> bool:
    """Include every child CE can toggle with this parent in either direction."""
    if depth > MAX_ENTRY_DEPTH:
        return False
    if element.findtext("GroupHeader") != "1":
        value_type = element.findtext("VariableType")
        if value_type == "Auto Assembler Script":
            script_element = element.find("AssemblerScript")
            if script_element is not None and script_element.attrib.get("Async") == "1":
                return False
            script = element.findtext("AssemblerScript") or ""
            if (_script_has_external_action(script)
                    or not re.search(r"\[\s*ENABLE\s*\]", script, re.IGNORECASE)
                    or not re.search(r"\[\s*DISABLE\s*\]", script, re.IGNORECASE)):
                return False
        elif not (value_type in SIMPLE_VALUE_TYPES and
                  (element.findtext("Address") or "").strip()
                  and element.findtext("DropDownListLink") is None
                  and (element.findtext("ShowAsHex") != "1"
                       or value_type in HEX_INTEGER_TYPES)):
            return False
        options = element.find("Options")
        if (options is not None and options.attrib.get("moRecursiveSetValue") == "1"
                and element.findall("./CheatEntries/CheatEntry")):
            return False
        dropdown = element.find("DropDownList")
        if dropdown is not None:
            parsed_choices = [line.partition(":")[0].strip()
                              for line in (dropdown.text or "").splitlines()
                              if line.strip() and ":" in line]
            if any(value != "*" and not numeric_literal_safe(
                    value, value_type, element.findtext("ShowAsHex") == "1",
                    None if element.find("ShowAsSigned") is None else
                    element.findtext("ShowAsSigned") == "1")
                    for value in parsed_choices):
                return False
        if dropdown is not None and dropdown.attrib.get("ReadOnly") == "1":
            if not any(line.strip() and ":" in line and line.partition(":")[0].strip() != "*"
                       for line in (dropdown.text or "").splitlines()):
                return False
    if not (_activates_children(element) or _deactivates_children(element)):
        return True
    return all(_node_activation_safe(child, depth + 1)
               for child in element.findall("./CheatEntries/CheatEntry"))


def _group_has_builtin_on_effect(element: ET.Element, depth: int = 0) -> bool:
    """Follow only CE's built-in direct-child activation option.

    A GroupHeader can have a checkbox without changing any child. A nested
    GroupHeader is not a recursive toggle unless it opts in independently.
    Lua callbacks may add effects at runtime and are outside this proof.
    """
    if depth > MAX_ENTRY_DEPTH:
        return False
    if element.findtext("GroupHeader") != "1":
        own_effect = (element.findtext("VariableType") == "Auto Assembler Script"
                      or bool(element.findtext("VariableType") and element.findtext("Address")))
        if own_effect:
            return True
    if not _activates_children(element):
        return False
    return any(_group_has_builtin_on_effect(child, depth + 1)
               for child in element.findall("./CheatEntries/CheatEntry"))


def _entry_kind(element: ET.Element, variable_type: str | None,
                has_children: bool) -> str:
    if element.findtext("GroupHeader") == "1":
        return "group" if (element.attrib.get("NoCheckbox") != "1"
                           and _group_has_builtin_on_effect(element)) else "heading"
    if variable_type == "Auto Assembler Script":
        return "script"
    if variable_type and (element.findtext("Address") or has_children):
        return "value"
    # WP-32: an addressless record that carries a value variable type is still
    # a value record (template/placeholder row); the compiler's entry policy
    # demotes it to a non-actionable placeholder heading.  Only records
    # without a value type (or with an unknown one) stay "unsupported".
    if variable_type in SIMPLE_VALUE_TYPES or variable_type in ADVANCED_VALUE_TYPES \
            or variable_type == "String":
        return "value"
    return "unsupported"


def _entry_hotkeys(element: ET.Element) -> tuple[RecordHotkey, ...]:
    """Parse a record's <Hotkeys> block into bounded, canonical records.

    The CT contract (CE 4.x+ format) stores up to five decimal Windows
    virtual-key codes per hotkey under <Keys>, the action text under
    <Action>, an optional value/description, and an optional Active
    attribute (missing means active).  Unparsable key codes are dropped,
    the key list is normalized to a sorted unique tuple capped at five
    codes, and missing action text falls back to the CE contract default
    ("Toggle Activation").  The result is sorted so plan output is
    deterministic independent of the source document order.
    """
    container = element.find("Hotkeys")
    if container is None:
        return ()
    hotkeys: list[RecordHotkey] = []
    for node in container.findall("Hotkey"):
        raw_keys: list[int] = []
        keys_node = node.find("Keys")
        if keys_node is not None:
            for key_node in keys_node.findall("Key"):
                text = (key_node.text or "").strip()
                if not text:
                    continue
                try:
                    code = int(text, 10)
                except ValueError:
                    continue
                if 0 < code <= 255:
                    raw_keys.append(code)
        keys = tuple(sorted(set(raw_keys))[:5])
        action = (node.findtext("Action") or "").strip() or HOTKEY_ACTION_DEFAULT
        hotkeys.append(RecordHotkey(
            keys=keys,
            action=action[:64],
            value=(node.findtext("Value") or "").strip()[:512],
            description=(node.findtext("Description") or "").strip()[:512],
            active=node.attrib.get("Active", "1") != "0",
        ))
    hotkeys.sort(key=lambda item: (item.keys, item.action, item.value,
                                   item.description, item.active))
    return tuple(hotkeys)


def read_table(path: str | Path) -> Table:
    """Parse a .CT without evaluating any embedded Lua or Auto Assembler.

    DTDs and entity declarations are refused.  Legacy pre-XML binary tables
    (``CHEATENGINE`` magic header, CE 5.x era) are parsed by the clean-room
    reader in :mod:`ct2trainer.legacy_ct` and loaded through the standard
    XML pipeline; unparseable legacy input is still refused with a named
    error that is distinct from the malformed-XML reason.  Duplicate
    CheatEntry IDs are tolerated (CE loads them without any check): the
    first occurrence owns the ID and later duplicates are dropped from the
    table with a per-ID warning, because the plan, the by_id map and
    selection persistence are ID-keyed and require exactly one addressable
    record per ID.
    """
    source = Path(path).expanduser().resolve()
    if source.suffix.lower() != ".ct":
        raise TableError("Input must be a .CT file.")
    try:
        size = source.stat().st_size
    except OSError as exc:
        raise TableError(f"Cannot read table: {source}: {exc}") from exc
    if size > MAX_TABLE_BYTES:
        raise TableError(f"Table exceeds {MAX_TABLE_BYTES} Bytes.")
    data = source.read_bytes()
    if data.startswith(LEGACY_BINARY_CT_HEADER):
        # RT-3: the legacy binary layout is parsed and converted
        # clean-room; the resulting standard XML document flows through
        # the unchanged XML pipeline below.
        from .legacy_ct import legacy_ct_to_table
        return legacy_ct_to_table(source, data)
    return _parse_xml_table(source, data)


def _parse_xml_table(source: Path, data: bytes) -> Table:
    """The XML .CT pipeline (bounded, DTD-free), dispatched by read_table."""
    if re.search(rb"<!\s*(DOCTYPE|ENTITY)\b", data, re.IGNORECASE):
        raise TableError("DTD/ENTITY is not allowed in .CT input.")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise TableError(f"Invalid CT XML: {exc}") from exc
    if root.tag != "CheatTable":
        raise TableError(f"Expected <CheatTable>, found <{root.tag}>.")
    try:
        version = int(root.attrib["CheatEngineTableVersion"])
    except (KeyError, ValueError) as exc:
        raise TableError("CheatEngineTableVersion is missing or invalid.") from exc

    seen_ids: set[int] = set()
    entries: list[Entry] = []
    duplicate_names: dict[int, list[str]] = {}

    from .native.custom_types import CustomTypeError, custom_types_from_ct_root
    custom_types: tuple = ()
    custom_type_parse_error: str | None = None
    if root.find("CustomTypes") is not None:
        try:
            custom_types = custom_types_from_ct_root(root)
        except CustomTypeError as exc:
            custom_type_parse_error = f"{exc.code}: {exc.reason}"
    known_custom_types = {profile.name for profile in custom_types}

    from .native.custom_types import CustomTypeError, custom_types_from_ct_root
    custom_types: tuple = ()
    custom_type_parse_error: str | None = None
    try:
        custom_types = custom_types_from_ct_root(root)
    except CustomTypeError as exc:
        custom_type_parse_error = f"{exc.code}: {exc.reason}"
    known_custom_types = {profile.name for profile in custom_types}

    def visit(element: ET.Element, depth: int, parent_id: int | None,
              labels: tuple[str, ...]) -> None:
        if depth > MAX_ENTRY_DEPTH:
            raise TableError(f"CheatEntry nesting exceeds {MAX_ENTRY_DEPTH} levels.")
        if len(entries) >= MAX_ENTRIES:
            raise TableError(f"More than {MAX_ENTRIES} CheatEntries.")
        try:
            entry_id = int(element.findtext("ID") or "")
        except ValueError as exc:
            raise TableError("A CheatEntry has no valid numeric ID.") from exc
        if entry_id < 0:
            raise TableError(f"Negative CheatEntry-ID: {entry_id}.")
        if entry_id in seen_ids:
            # WP-25 keep-first: the plan, the by_id map and selection
            # persistence are ID-keyed, so exactly one addressable record
            # per ID is mandatory.  The first occurrence owns the ID; this
            # later duplicate is dropped from the table.  It is NOT
            # re-parented to the kept entry (that would merge two distinct
            # records and change the kept entry's semantics).  Any children
            # of the dropped duplicate stay addressable at the duplicate's
            # own tree position (re-parented to the duplicate's parent), so
            # no unique-ID record is lost and the plan total stays equal to
            # the unique source-ID count.  The dropped record is named in
            # the per-ID table warning emitted after the walk.
            duplicate_names.setdefault(entry_id, []).append(
                _label(element.findtext("Description"), entry_id))
            for child in element.findall("./CheatEntries/CheatEntry"):
                visit(child, depth + 1, parent_id, labels)
            return
        seen_ids.add(entry_id)
        label = _label(element.findtext("Description"), entry_id)
        child_nodes = element.findall("./CheatEntries/CheatEntry")
        variable_type = element.findtext("VariableType")
        kind = _entry_kind(element, variable_type, bool(child_nodes))
        address = element.findtext("Address")
        script_element = element.find("AssemblerScript")
        script = (script_element.text or "") if script_element is not None else ""
        dropdown = element.find("DropDownList")
        dropdown_choices = tuple(
            (line.partition(":")[0].strip(), line.partition(":")[2].strip())
            for line in (dropdown.text or "").splitlines()
            if line.strip() and ":" in line
        ) if dropdown is not None else ()
        dropdown_link = element.findtext("DropDownListLink")
        options_element = element.find("Options")
        external_action_apis = _script_external_action_apis(script)
        entries.append(Entry(
            id=entry_id,
            label=label,
            path=" / ".join((*labels, label)),
            depth=depth,
            parent_id=parent_id,
            variable_type=variable_type,
            address=address,
            kind=kind,
            is_group_header=element.findtext("GroupHeader") == "1",
            activation_safe=_node_activation_safe(element),
            has_checkbox=element.attrib.get("NoCheckbox") != "1",
            has_children=bool(child_nodes),
            has_assembler_lua="{$LUA}" in script.upper(),
            assembler_sha256=sha256(script.encode("utf-8")).hexdigest()
                    if script_element is not None else None,
            has_enable_section=bool(re.search(r"\[\s*ENABLE\s*\]", script, re.IGNORECASE)),
            has_disable_section=bool(re.search(r"\[\s*DISABLE\s*\]", script, re.IGNORECASE)),
            async_script=script_element is not None and script_element.attrib.get("Async") == "1",
            hotkey_count=len(element.findall("./Hotkeys/Hotkey")),
            hotkeys=_entry_hotkeys(element),
            pointer_offsets=tuple(offset.text or "" for offset in element.findall("./Offsets/Offset")),
            options=tuple(key for key, value in options_element.attrib.items() if value == "1")
                    if options_element is not None else (),
            has_dropdown=dropdown is not None or dropdown_link is not None,
            dropdown_read_only=dropdown is not None and dropdown.attrib.get("ReadOnly") == "1",
            dropdown_choices=dropdown_choices,
            dropdown_link=dropdown_link,
            show_as_hex=element.findtext("ShowAsHex") == "1",
            show_as_signed=(None if element.find("ShowAsSigned") is None else
                            element.findtext("ShowAsSigned") == "1"),
            custom_type_name=element.findtext("CustomType"),
            custom_type_known=(element.findtext("CustomType") in known_custom_types),
            script_external_action=bool(external_action_apis),
            external_action_apis=external_action_apis,
            registers_symbols=_script_registers_symbols(script),
            activation_set_lua=_script_activation_set_lua(script),
        ))
        for child in child_nodes:
            visit(child, depth + 1, entry_id, (*labels, label))

    for element in root.findall("./CheatEntries/CheatEntry"):
        visit(element, 0, None, ())
    by_label: dict[str, list[Entry]] = {}
    for entry in entries:
        by_label.setdefault(entry.label.casefold(), []).append(entry)
    entries = [
        replace(entry, dropdown_link_empty=True)
        if (entry.dropdown_link and len(by_label.get(entry.dropdown_link.casefold(), ())) == 1
            and not by_label[entry.dropdown_link.casefold()][0].has_dropdown)
        else entry
        for entry in entries
    ]
    lua = root.find("LuaScript")
    has_table_lua = lua is not None and bool("".join(lua.itertext()).strip())
    warnings: list[str] = []
    if version > LOCAL_CE_TABLE_VERSION:
        warnings.append(
            f"Table version {version} is newer than the local CE reference "
            f"({LOCAL_CE_TABLE_VERSION}); CE loading is unverified."
        )
    if has_table_lua:
        warnings.append("Table Lua can run when Cheat Engine loads the table.")
    if any(entry.has_assembler_lua for entry in entries):
        warnings.append("At least one Auto Assembler script contains {$LUA}; the embedded Lua runs in the trainer's built-in Lua runtime when the record activates.")
    if any(entry.kind == "unsupported" for entry in entries):
        warnings.append("Some entries have no supported control type.")
    if root.find("Forms") is not None:
        warnings.append("Embedded CE forms are present; check UI conflicts.")
    if root.find("CustomTypes") is not None:
        if custom_types:
            warnings.append("Custom data types are statically defined; the Native write path remains gated.")
        else:
            warnings.append(f"Custom data type section is present but does not parse: {custom_type_parse_error}.")
    if any(entry.variable_type == "Custom" for entry in entries):
        if all(entry.custom_type_known for entry in entries if entry.variable_type == "Custom"):
            warnings.append("Custom Type records are statically defined; the Native write path remains gated.")
        else:
            warnings.append("Custom Type records need a CE runtime test; definitions may come from table Lua.")
    if any(entry.script_external_action for entry in entries):
        apis = {api for entry in entries for api in entry.external_action_apis}
        if "shellExecute" in apis:
            warnings.append("At least one script calls ShellExecute; the native trainer runs it as a safe no-op (no external program or URL is launched).")
        if "messageDialog" in apis:
            warnings.append("At least one script calls messageDialog, which the native Lua runtime does not implement; affected records fail at activation with a named refusal.")
    for entry_id, names in duplicate_names.items():
        warnings.append(
            f"Duplicate CheatEntry ID: {entry_id} (kept first occurrence; "
            f"dropped {len(names)} duplicate record(s): {', '.join(names)})")
    # WP-46 (part 1): interpret the table-level <UserdefinedSymbols> section.
    # CE 7.x writes the tag (usually empty) into every table, so an empty or
    # absent section yields no symbols and no warning.  Every entry is judged
    # fail-closed: a rejected entry is dropped with a named per-entry warning
    # and the remaining entries (and the table itself) still compile.
    uds_symbols: list[UserDefinedSymbol] = []
    uds_section = root.find("UserdefinedSymbols")
    if uds_section is not None:
        uds_nodes = uds_section.findall("SymbolEntry")
        if len(uds_nodes) > MAX_UDS_ENTRIES:
            warnings.append(
                f"UserdefinedSymbols section exceeds {MAX_UDS_ENTRIES} "
                f"entries; section ignored.")
        else:
            from .native.aa import AAError, validate_symbol
            uds_seen: set[str] = set()
            for index, node in enumerate(uds_nodes, start=1):
                name = (node.findtext("Name") or "").strip()
                if not name:
                    warnings.append(
                        f"UserdefinedSymbols entry {index}: missing <Name>; "
                        f"entry ignored.")
                    continue
                try:
                    validate_symbol(name)
                except AAError as exc:
                    warnings.append(
                        f"UserdefinedSymbols entry '{name}': invalid symbol "
                        f"name ({exc}); entry ignored.")
                    continue
                key = name.casefold()
                if key in uds_seen:
                    warnings.append(
                        f"UserdefinedSymbols entry '{name}': duplicate symbol "
                        f"name (kept first occurrence); later entry ignored.")
                    continue
                address_text = (node.findtext("Address") or "").strip()
                if not address_text:
                    warnings.append(
                        f"UserdefinedSymbols entry '{name}': missing or empty "
                        f"<Address>; entry ignored.")
                    continue
                if _UDS_ADDRESS.fullmatch(address_text) is None:
                    warnings.append(
                        f"UserdefinedSymbols entry '{name}': address "
                        f"'{address_text}' is not a hexadecimal absolute "
                        f"integer; entry ignored.")
                    continue
                uds_seen.add(key)
                uds_symbols.append(UserDefinedSymbol(
                    name=name,
                    address=int(address_text.removeprefix("$").removeprefix("0x")
                                .removeprefix("0X"), 16),
                ))
    sections = tuple(
        SectionSummary(
            name=element.tag,
            child_count=len(element),
            text_bytes=len("".join(element.itertext()).encode("utf-8")),
            xml_sha256=sha256(ET.tostring(element, encoding="utf-8")).hexdigest(),
        )
        for element in root
        if element.tag != "CheatEntries"
    )
    return Table(
        source=source,
        source_sha256=sha256(data).hexdigest(),
        table_version=version,
        entries=tuple(entries),
        has_table_lua=has_table_lua,
        has_forms=root.find("Forms") is not None,
        has_custom_types=root.find("CustomTypes") is not None,
        has_custom_type_records=any(entry.variable_type == "Custom" for entry in entries),
        custom_types=custom_types,
        sections=sections,
        warnings=tuple(warnings),
        user_defined_symbols=tuple(uds_symbols),
    )
