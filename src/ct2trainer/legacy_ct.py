"""RT-3: clean-room reader for the legacy pre-XML binary CT table format.

CE 5.x-era tables are not XML.  The on-disk layout, verified byte-level
against the local-only version-9 reference table (SuperMeatBoy.CT) and the
behavior reference's own legacy-converter contract, is::

  +--------------------+---------------------------------------------+
  | 11 bytes           | literal magic b"CHEATENGINE"                |
  | 4 bytes LE         | format version (6..9 verified; <6 too old)  |
  | 4 bytes LE         | record count                               |
  | per record:        |                                             |
  |   4 bytes LE       | description length                         |
  |   N bytes          | description (ANSI)                         |
  |   4 bytes LE       | static address DWORD                       |
  |   4 bytes LE       | interpretable-address length               |
  |   M bytes          | interpretable address (ANSI)               |
  |   1 byte           | variable-type code (see _VARIABLE_TYPES)   |
  |   1 byte           | unicode flag (0/1)                         |
  |   1 byte           | length (also reused as bitstart)           |
  |   4 bytes LE       | bit length                                 |
  |   1 byte           | group index (0..6, anything else top level)|
  |   1 byte           | show-as-hex flag (0/1)                     |
  |   1 byte           | is-pointer flag (unused; count governs)    |
  |   4 bytes LE       | pointer count                              |
  |   per pointer:     |                                             |
  |     4 bytes LE     |   pointer address DWORD (informational)    |
  |     4 bytes LE     |   pointer offset DWORD                     |
  |     4 bytes LE     |   pointer interpretable-address length     |
  |     K bytes        |   pointer interpretable address (ANSI)     |
  |   4 bytes LE       | Auto Assembler script length               |
  |   K bytes          | Auto Assembler script (ANSI)               |
  | 4 bytes LE         | code-record count                          |
  | per code record:   |                                             |
  |   4 bytes LE       |   address DWORD                            |
  |   1 byte + bytes   |   module name                              |
  |   4 bytes LE       |   module name offset DWORD                 |
  |   1 byte + bytes   |   "before" bytes                           |
  |   1 byte + bytes   |   "actual" bytes                           |
  |   1 byte + bytes   |   "after" bytes                            |
  |   1 byte + bytes   |   description                              |
  +--------------------+---------------------------------------------+

Anything after the code-record section is a trailer that the behavior
reference ignores (the version-9 reference table carries a "NOTES:" text
block); it is surfaced as a table warning instead of being refused.

Record identity and data are preserved through a clean-room conversion to
the standard XML table document, which then flows through the existing
tested XML pipeline: every record keeps its description, address, variable
type, display flags, pointer offsets and script text; code records keep
their address, module binding, byte arrays and description.  The binary
format stores no record IDs, so the conversion assigns sequential IDs in
final document order: top-level records in file order, then "Group N"
headers in numeric order with their members in file order.  The legacy
binary format version becomes the XML ``CheatEngineTableVersion``
attribute and a table warning records the conversion.

Pointer record note: the XML format only expresses a base address plus the
offset chain, so the conversion (like the behavior reference's own
converter) takes the last pointer's address or interpretable string as the
record address and writes every pointer offset; the intermediate pointer
addresses are informational in the legacy format and are not expressible
in the XML format.

Every refusal raises ``LegacyCTError`` (a named ``TableError`` subclass),
so inspection diagnostics keep the G4a "Malformed or unreadable CT table"
classification for unparseable legacy input.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from xml.sax.saxutils import escape

from .table import (MAX_ENTRIES, LEGACY_BINARY_CT_HEADER, Table, TableError,
                    _parse_xml_table)

MAGIC = LEGACY_BINARY_CT_HEADER  # 11-byte b"CHEATENGINE"
MIN_FORMAT_VERSION = 6           # below this the behavior reference refuses
MAX_VERIFIED_FORMAT_VERSION = 9  # verified reference layout version

MAX_DESCRIPTION_BYTES = 4096
MAX_INTERPRETABLE_BYTES = 4096
MAX_SCRIPT_BYTES = 4 * 1024 * 1024
MAX_POINTER_COUNT = 256
MAX_CODE_RECORDS = 4096

# Old variable-type code -> XML VariableType spelling (behavior-reference
# OldVarTypeToNewVarType / VariableTypeToString contract); unknown codes
# fall back to Dword, as in the behavior reference.
_VARIABLE_TYPES = {
    0: "Byte",
    1: "2 Bytes",
    2: "4 Bytes",
    3: "Float",
    4: "Double",
    5: "Binary",
    6: "8 Bytes",
    7: "String",
    8: "Array of byte",
    10: "Custom",
    255: "Auto Assembler Script",
}
_DEFAULT_VARIABLE_TYPE = "4 Bytes"


class LegacyCTError(TableError):
    """A legacy binary CT table cannot be parsed (named, fail-closed)."""


def _decode_ansi(raw: bytes) -> str:
    """Decode a legacy ANSI string field deterministically, losslessly.

    Legacy tables predate the UTF-8 XML format and store single-byte ANSI
    text.  UTF-8 is tried first (modern resaves), then the Western ANSI
    code page, then Latin-1, which is a byte-bijective fallback so no input
    is ever lost or rejected on this axis.
    """
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    try:
        return raw.decode("cp1252")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


@dataclass(frozen=True)
class LegacyPointer:
    """One legacy pointer entry (informational address, offset, string)."""

    address: int
    offset: int
    interpretable: str


@dataclass(frozen=True)
class LegacyRecord:
    """One parsed legacy table record, field values verbatim."""

    description: str
    address: int
    interpretable: str
    variable_type: int
    unicode: bool
    length: int
    bit_length: int
    group: int
    show_as_hex: bool
    is_pointer: bool
    pointers: tuple[LegacyPointer, ...]
    script: str


@dataclass(frozen=True)
class LegacyCodeRecord:
    """One parsed legacy code-record (CheatCodes) entry."""

    address: int
    module_name: str
    module_offset: int
    before: tuple[int, ...]
    actual: tuple[int, ...]
    after: tuple[int, ...]
    description: str


@dataclass(frozen=True)
class LegacyTable:
    """The full parsed legacy binary table."""

    version: int
    records: tuple[LegacyRecord, ...]
    code_records: tuple[LegacyCodeRecord, ...]
    trailing_bytes: int


class _Reader:
    """Bounded little-endian byte reader with named truncation refusals."""

    __slots__ = ("data", "pos")

    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def take(self, count: int, what: str) -> bytes:
        end = self.pos + count
        if end > len(self.data):
            raise LegacyCTError(
                f"Legacy binary CT table is truncated: {what} needs "
                f"{count} byte(s) at offset {self.pos} but only "
                f"{len(self.data) - self.pos} remain.")
        chunk = self.data[self.pos:end]
        self.pos = end
        return chunk

    def d32(self, what: str) -> int:
        return int.from_bytes(self.take(4, what), "little")

    def byte(self, what: str) -> int:
        return self.take(1, what)[0]

    def length_prefixed(self, what: str, limit: int) -> bytes:
        """Read a 4-byte LE length + payload, bounded by ``limit``."""
        length = self.d32(what + " length")
        if length > limit:
            raise LegacyCTError(
                f"Legacy binary CT table holds an implausible {what} "
                f"length {length} (bounded to {limit}).")
        return self.take(length, what)


def parse_legacy_ct(data: bytes) -> LegacyTable:
    """Parse a legacy binary CT table; every refusal is named fail-closed."""
    if data[:len(MAGIC)] != MAGIC:
        raise LegacyCTError(
            "Legacy binary CT table has a corrupt magic header: "
            "expected the 11-byte CHEATENGINE header.")
    if len(data) < len(MAGIC) + 8:
        raise LegacyCTError(
            "Legacy binary CT table is truncated: the header needs 19 "
            f"bytes but only {len(data)} are present.")
    reader = _Reader(data)
    reader.pos = len(MAGIC)
    version = reader.d32("the format version")
    if version < MIN_FORMAT_VERSION:
        raise LegacyCTError(
            f"Legacy binary CT table version {version} is older than "
            f"{MIN_FORMAT_VERSION}; the pre-converter layout is not supported.")
    count = reader.d32("the record count")
    if count > MAX_ENTRIES:
        raise LegacyCTError(
            f"Legacy binary CT table holds an implausible record count "
            f"{count} (bounded to {MAX_ENTRIES}).")
    records: list[LegacyRecord] = []
    for index in range(count):
        prefix = f"record {index} "
        description = _decode_ansi(reader.length_prefixed(
            prefix + "description", MAX_DESCRIPTION_BYTES))
        address = reader.d32(prefix + "static address")
        interpretable = _decode_ansi(reader.length_prefixed(
            prefix + "interpretable address", MAX_INTERPRETABLE_BYTES))
        variable_type = reader.byte(prefix + "variable type")
        unicode_flag = reader.byte(prefix + "unicode flag")
        length = reader.byte(prefix + "length")
        bit_length = reader.d32(prefix + "bit length")
        group = reader.byte(prefix + "group index")
        show_as_hex = reader.byte(prefix + "show-as-hex flag")
        is_pointer = reader.byte(prefix + "is-pointer flag")
        pointer_count = reader.d32(prefix + "pointer count")
        if pointer_count > MAX_POINTER_COUNT:
            raise LegacyCTError(
                f"Legacy binary CT table record {index} holds an "
                f"implausible pointer count {pointer_count} "
                f"(bounded to {MAX_POINTER_COUNT}).")
        pointers: list[LegacyPointer] = []
        for slot in range(pointer_count):
            what = f"record {index} pointer {slot} "
            pointer_address = reader.d32(what + "address")
            pointer_offset = reader.d32(what + "offset")
            pointer_string = _decode_ansi(reader.length_prefixed(
                what + "interpretable address", MAX_INTERPRETABLE_BYTES))
            pointers.append(LegacyPointer(
                address=pointer_address,
                offset=pointer_offset,
                interpretable=pointer_string))
        script = _decode_ansi(reader.length_prefixed(
            prefix + "Auto Assembler script", MAX_SCRIPT_BYTES))
        records.append(LegacyRecord(
            description=description,
            address=address,
            interpretable=interpretable,
            variable_type=variable_type,
            unicode=bool(unicode_flag),
            length=length,
            bit_length=bit_length,
            group=group,
            show_as_hex=bool(show_as_hex),
            is_pointer=bool(is_pointer),
            pointers=tuple(pointers),
            script=script))
    code_count = reader.d32("the code-record count")
    if code_count > MAX_CODE_RECORDS:
        raise LegacyCTError(
            f"Legacy binary CT table holds an implausible code-record "
            f"count {code_count} (bounded to {MAX_CODE_RECORDS}).")
    code_records: list[LegacyCodeRecord] = []
    for index in range(code_count):
        prefix = f"code record {index} "
        address = reader.d32(prefix + "address")
        module_name = _decode_ansi(reader.take(
            reader.byte(prefix + "module-name length"), prefix + "module name"))
        module_offset = reader.d32(prefix + "module-name offset")
        before = reader.take(reader.byte(prefix + '"before" length'),
                             prefix + '"before" bytes')
        actual = reader.take(reader.byte(prefix + '"actual" length'),
                             prefix + '"actual" bytes')
        after = reader.take(reader.byte(prefix + '"after" length'),
                            prefix + '"after" bytes')
        description = _decode_ansi(reader.take(
            reader.byte(prefix + "description length"), prefix + "description"))
        code_records.append(LegacyCodeRecord(
            address=address,
            module_name=module_name,
            module_offset=module_offset,
            before=tuple(before),
            actual=tuple(actual),
            after=tuple(after),
            description=description))
    return LegacyTable(
        version=version,
        records=tuple(records),
        code_records=tuple(code_records),
        trailing_bytes=len(data) - reader.pos,
    )


def _entry_xml(record: LegacyRecord, entry_id: int) -> str:
    variable_type = _VARIABLE_TYPES.get(record.variable_type,
                                        _DEFAULT_VARIABLE_TYPE)
    if record.pointers:
        last = record.pointers[-1]
        address = last.interpretable or format(last.address, "08X")
    else:
        address = record.interpretable or format(record.address, "08X")
    parts = [
        "<CheatEntry>",
        f"<ID>{entry_id}</ID>",
        f"<Description>{escape(record.description)}</Description>",
        f"<VariableType>{variable_type}</VariableType>",
        f"<Unicode>{1 if record.unicode else 0}</Unicode>",
        f"<Length>{record.length}</Length>",
        f"<ByteLength>{record.length}</ByteLength>",
        f"<BitStart>{record.length}</BitStart>",
        f"<BitLength>{record.bit_length}</BitLength>",
        f"<Address>{escape(address)}</Address>",
    ]
    if record.pointers:
        parts.append("<Offsets>")
        parts.extend(f"<Offset>{pointer.offset:X}</Offset>"
                     for pointer in record.pointers)
        parts.append("</Offsets>")
    parts.extend([
        f"<ShowAsHex>{1 if record.show_as_hex else 0}</ShowAsHex>",
        f"<AssemblerScript>{escape(record.script)}</AssemblerScript>",
        "</CheatEntry>",
    ])
    return "\n".join(parts)


def _code_record_xml(code: LegacyCodeRecord) -> str:
    def byte_block(tag: str, values: tuple[int, ...]) -> str:
        if not values:
            return f"<{tag}/>"
        inner = "".join(f"<Byte>{value:02X}</Byte>" for value in values)
        return f"<{tag}>{inner}</{tag}>"

    return "\n".join([
        "<CodeEntry>",
        f"<Description>{escape(code.description)}</Description>",
        f"<Address>{code.address:08X}</Address>",
        f"<ModuleName>{escape(code.module_name)}</ModuleName>",
        f"<ModuleNameOffset>{code.module_offset:X}</ModuleNameOffset>",
        byte_block("Before", code.before),
        byte_block("Actual", code.actual),
        byte_block("After", code.after),
        "</CodeEntry>",
    ])


def legacy_ct_to_xml(parsed: LegacyTable) -> bytes:
    """Convert a parsed legacy table to a standard XML table document.

    Document order mirrors the behavior reference's converter output:
    top-level records in file order, then used "Group N" headers in
    numeric order with their members in file order, and CheatCodes last.
    Sequential IDs are assigned over that document order.
    """
    top_level = [record for record in parsed.records
                 if record.group == 0 or record.group > 6]
    groups = {group_index: [record for record in parsed.records
                            if record.group == group_index]
              for group_index in range(1, 7)}
    items: list[tuple[LegacyRecord | None, int | None]] = \
        [(record, None) for record in top_level]
    items += [(None, group_index) for group_index in range(1, 7)
              if groups[group_index]]

    parts = [
        '<?xml version="1.0" encoding="utf-8"?>',
        f'<CheatTable CheatEngineTableVersion="{parsed.version}">',
        "<CheatEntries>",
    ]
    entry_id = 0
    for record, group_index in items:
        if record is not None:
            entry_id += 1
            parts.append(_entry_xml(record, entry_id))
        else:
            entry_id += 1
            parts.append("\n".join([
                "<CheatEntry>",
                f"<ID>{entry_id}</ID>",
                f"<Description>Group {group_index}</Description>",
                "<GroupHeader>1</GroupHeader>",
                "<CheatEntries>",
            ]))
            for member in groups[group_index]:
                entry_id += 1
                parts.append(_entry_xml(member, entry_id))
            parts.append("</CheatEntries>")
            parts.append("</CheatEntry>")
    parts.append("</CheatEntries>")
    if parsed.code_records:
        parts.append("<CheatCodes>")
        parts.extend(_code_record_xml(code) for code in parsed.code_records)
        parts.append("</CheatCodes>")
    parts.append("</CheatTable>")
    return "\n".join(parts).encode("utf-8")


def legacy_ct_to_table(source: Path, data: bytes) -> Table:
    """Load a legacy binary CT table through the standard XML pipeline.

    The original binary bytes remain the source identity: the table's
    ``source_sha256`` is the binary hash (matching the reference manifest)
    and the converted XML is carried on the table for the compiler, which
    re-reads the source file bytes.
    """
    parsed = parse_legacy_ct(data)
    xml_bytes = legacy_ct_to_xml(parsed)
    table = _parse_xml_table(source, xml_bytes)
    warnings: list[str] = [
        f"Converted from the legacy binary CT format (CE 5.x era, binary "
        f"format version {parsed.version}); record IDs are synthesized "
        f"sequentially in document order.",
    ]
    if parsed.version > MAX_VERIFIED_FORMAT_VERSION:
        warnings.append(
            f"Legacy binary table version {parsed.version} is newer than "
            f"the verified reference layout "
            f"({MAX_VERIFIED_FORMAT_VERSION}); the field layout is assumed "
            f"unchanged.")
    if parsed.trailing_bytes:
        warnings.append(
            f"{parsed.trailing_bytes} trailing byte(s) after the "
            f"code-record section are ignored (legacy trailer).")
    return replace(
        table,
        source_sha256=sha256(data).hexdigest(),
        warnings=tuple(warnings) + table.warnings,
        converted_xml=xml_bytes,
    )
