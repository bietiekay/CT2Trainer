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
LOCAL_CE_TABLE_VERSION = 45
ADVANCED_VALUE_TYPES = frozenset({"Array of byte", "Binary", "Custom"})
SIMPLE_VALUE_TYPES = frozenset({"Byte", "2 Bytes", "4 Bytes", "8 Bytes", "Float", "Double"})
HEX_INTEGER_TYPES = frozenset({"Byte", "2 Bytes", "4 Bytes", "8 Bytes"})
HEX_DIGITS_BY_TYPE = {"Byte": 2, "2 Bytes": 4, "4 Bytes": 8, "8 Bytes": 16}


class TableError(ValueError):
    """A table cannot be safely represented by the current inspector."""


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
    custom_type_known: bool = False
    dropdown_link_empty: bool = False

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


def _script_has_external_action(script: str) -> bool:
    return bool(re.search(r"\b(?:shellExecute|messageDialog)\s*\(", script, re.IGNORECASE))


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
    return "unsupported"


def read_table(path: str | Path) -> Table:
    """Parse a .CT without evaluating any embedded Lua or Auto Assembler.

    DTDs and entity declarations are refused. IDs must be unique because the
    generated CE UI locates records by ID, not by their mutable descriptions.
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
            raise TableError(f"Duplicate CheatEntry ID: {entry_id}.")
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
            script_external_action=_script_has_external_action(script),
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
        warnings.append("At least one Auto Assembler script contains {$LUA}.")
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
        warnings.append("At least one script invokes a dialog or external action and needs review.")
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
    )
