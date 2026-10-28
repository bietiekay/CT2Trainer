"""Embedded table-file extraction and validation (RT-5 item A).

Cheat Engine embeds auxiliary files (Lua scripts, text) in a table's
``<Files>`` section.  With the exact ``Encoding="Ascii85"`` attribute the
entry is stored as Ascii85 text in CE's custom 85-character alphabet; the
decoded bytes are a raw (RFC 1951) deflate stream that expands to a
4-byte little-endian size prefix followed by the file content.  Any other
or missing ``Encoding`` value takes CE's hex branch: hex text -> raw
deflate, read until EOF, no size prefix.  This is a clean-room
reimplementation of the observed corpus format and the CE reference
semantics (verified byte-exact on the reference tables); no CE source is
used.

The module is used at three levels:

- table load (``ct2trainer.table``): decode every entry fail-closed;
  a single undecodable entry aborts the table load with a named
  ``TableError`` (CE itself fails to load such a table);
- compile (``native.compiler``): the raw stored text plus the derived
  ``sha256``/``size`` ride in the plan so the runtime can re-derive the
  content without the CT file;
- plan validation (both plan gates): ``validate_embedded_files``
  re-decodes the stored text and refuses forged hashes, sizes,
  encodings or oversized sections.
"""
from __future__ import annotations

import hashlib
import re
import zlib


# CE's Ascii85 alphabet: digits, uppercase, lowercase, then the
# punctuation run ! # $ % ( ) * + , - . / : ; = ? @ [ ] ^ _ { }.
# (The standard base64.b85 alphabet is different and must not be used.)
CE_BASE85_ALPHABET = (
    "0123456789"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
    "!#$%()*+,-./:;=?@[]^_{}"
)
_CE_BASE85_INDEX = {char: index for index, char in enumerate(CE_BASE85_ALPHABET)}
# A short final block is padded with the alphabet's value-84 character
# ('}') so the 5-to-4 expansion is total; the expansion's trailing
# padding bytes are discarded (keep the first n-1 bytes of an n-char
# block).
_CE_BASE85_PAD = 84

MAX_EMBEDDED_FILES = 64
# Per-file content bound: one readStringLocal call must always be able to
# return the whole file, so the bound tracks the 4 MiB per-call transport
# limit.  The per-table total stays at 16 MiB.
MAX_EMBEDDED_FILE_BYTES = 4 * 1024 * 1024
MAX_EMBEDDED_TOTAL_BYTES = 16 * 1024 * 1024
MAX_EMBEDDED_FILE_NAME_CHARS = 255
#: Per-Lua-scope string streams (createStringStream): CE creates a fresh
#: TStringStream per call, so the native profile mirrors that with a
#: bounded per-scope registry.
MAX_STRING_STREAMS = 256
MAX_STRING_STREAM_BYTES = 16 * 1024 * 1024


class EmbeddedFileError(ValueError):
    """An embedded file cannot be decoded or is outside the accepted contract."""


def decode_ascii85(text: str) -> bytes:
    """Decode CE-alphabet Ascii85 text (whitespace stripped) to bytes.

    Five alphabet characters hold four bytes MSB-first; a trailing block
    of n characters (n in {2, 3, 4}) is padded with value 84 and yields
    n-1 bytes.  A single trailing character is undecodable.
    """
    if not isinstance(text, str):
        raise EmbeddedFileError("Embedded file text must be text.")
    chars = [char for char in text if not char.isspace()]
    if not chars:
        raise EmbeddedFileError("Embedded file text is empty.")
    out = bytearray()
    total = len(chars)
    index = 0
    while index < total:
        block = chars[index:index + 5]
        index += 5
        size = len(block)
        if size == 1:
            raise EmbeddedFileError(
                "Embedded file Ascii85 text ends with a single character.")
        value = 0
        for char in block:
            digit = _CE_BASE85_INDEX.get(char)
            if digit is None:
                raise EmbeddedFileError(
                    "Embedded file Ascii85 text contains character %r "
                    "outside the CE alphabet." % char)
            value = value * 85 + digit
        for _ in range(5 - size):
            value = value * 85 + _CE_BASE85_PAD
        out.extend(value.to_bytes(4, "big")[: size - 1])
    return bytes(out)


_HEX_CHARS = frozenset("0123456789abcdefABCDEF")


def decode_embedded_file(text: str, encoding: str = "Ascii85") -> bytes:
    """Full pipeline for one stored embedded file.

    ``encoding == "Ascii85"`` (CE createFromXML: the exact attribute value
    ``Ascii85``): CE-alphabet Ascii85 -> raw deflate -> content with a
    4-byte little-endian size prefix that must match the remaining
    payload exactly.

    Any other or missing encoding takes CE's hex branch: hex decode ->
    raw deflate, read until EOF, no size prefix (CE's HexToBin path).
    """
    if encoding == "Ascii85":
        raw = decode_ascii85(text)
        try:
            payload = zlib.decompress(raw, -15)
        except zlib.error as exc:
            raise EmbeddedFileError(
                "Embedded file payload is not a valid raw-deflate stream: %s" % exc) from exc
        if len(payload) < 4:
            raise EmbeddedFileError(
                "Embedded file payload is shorter than the 4-byte size prefix.")
        size = int.from_bytes(payload[:4], "little")
        content = payload[4:]
        if size > MAX_EMBEDDED_FILE_BYTES:
            raise EmbeddedFileError(
                "Embedded file size prefix exceeds the 4 MiB bound.")
        if size != len(content):
            raise EmbeddedFileError(
                "Embedded file size prefix (%d) does not match the payload length (%d)."
                % (size, len(content)))
        return content
    # CE hex branch (Encoding attribute missing or not exactly 'Ascii85'):
    # hex decode, raw deflate, read until EOF — no size prefix.
    if not isinstance(text, str):
        raise EmbeddedFileError("Embedded file text must be text.")
    chars = [char for char in text if not char.isspace()]
    if not chars:
        raise EmbeddedFileError("Embedded file text is empty.")
    if len(chars) % 2 != 0:
        raise EmbeddedFileError(
            "Embedded file hex text has an odd character count.")
    for char in chars:
        if char not in _HEX_CHARS:
            raise EmbeddedFileError(
                "Embedded file hex text contains non-hex character %r." % char)
    raw = bytes.fromhex("".join(chars))
    try:
        payload = zlib.decompress(raw, -15)
    except zlib.error as exc:
        raise EmbeddedFileError(
            "Embedded file payload is not a valid raw-deflate stream: %s" % exc) from exc
    if len(payload) > MAX_EMBEDDED_FILE_BYTES:
        raise EmbeddedFileError(
            "Embedded file content exceeds the 4 MiB bound.")
    return payload


def validate_embedded_files(entries: list) -> list:
    """Strict plan-level validation, re-deriving everything from the stored text.

    Each entry must be exactly ``{"name", "encoding", "text", "sha256",
    "size"}``; the stored raw ``text`` is re-decoded (Ascii85 branch when
    the stored encoding is exactly ``Ascii85``, CE hex branch otherwise)
    and its sha256 and size must match the stored metadata (forged plan
    fields are refused by both plan gates).  Duplicate names are
    tolerated, matching the CE table load (the runtime lookup resolves
    the first occurrence).  Per-file and total sizes are bounded.
    """
    if not isinstance(entries, list):
        raise EmbeddedFileError("embedded_files must be a list.")
    if len(entries) > MAX_EMBEDDED_FILES:
        raise EmbeddedFileError(
            "More than %d embedded files." % MAX_EMBEDDED_FILES)
    total = 0
    for index, entry in enumerate(entries):
        if (not isinstance(entry, dict)
                or set(entry) != {"name", "encoding", "text", "sha256", "size"}):
            raise EmbeddedFileError(
                "Invalid embedded file entry shape (entry %d)." % index)
        name = entry["name"]
        if (not isinstance(name, str) or not name
                or len(name) > MAX_EMBEDDED_FILE_NAME_CHARS):
            raise EmbeddedFileError("Invalid embedded file name.")
        if type(entry["encoding"]) is not str:
            raise EmbeddedFileError(
                "Embedded file %r encoding must be text." % name)
        if not isinstance(entry["text"], str) or not entry["text"]:
            raise EmbeddedFileError(
                "Embedded file %r text must be non-empty." % name)
        if (not isinstance(entry["sha256"], str)
                or re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) is None):
            raise EmbeddedFileError(
                "Embedded file %r carries an invalid sha256." % name)
        if (type(entry["size"]) is not int or not 0 <= entry["size"] <= MAX_EMBEDDED_FILE_BYTES):
            raise EmbeddedFileError(
                "Embedded file %r carries an invalid size." % name)
        content = decode_embedded_file(entry["text"], entry["encoding"])
        if hashlib.sha256(content).hexdigest() != entry["sha256"]:
            raise EmbeddedFileError(
                "Embedded file %r content does not match its stored hash." % name)
        if len(content) != entry["size"]:
            raise EmbeddedFileError(
                "Embedded file %r size does not match its stored content." % name)
        total += len(content)
        if total > MAX_EMBEDDED_TOTAL_BYTES:
            raise EmbeddedFileError(
                "Embedded files exceed their 16 MiB total bound.")
    return entries
