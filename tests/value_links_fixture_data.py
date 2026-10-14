"""Synthetic record-table fixtures for the value-link lane (AP-10).

Self-contained (no TableReferences, no game inputs, no CE data):

- re2-style ``moRecursiveSetValue`` Byte/Float trees, including mixed
  child types, a cycle case, a self-parent cycle, the depth > 64
  rejection case and the depth == 64 acceptance case;
- Silent-Hill-Townfall-rml-style cross-record ``DropDownListLink``
  tables, including a valid link, a case-fold identity link, a cycle
  link (chained and self), a missing target, an ambiguous case-fold
  twin, a group-header target (the pinned corpus shape), a
  non-numeric target, an empty dropdown and an unusable choice literal.

Record dicts use the input schema of ``value_links._normalize_table``:
id (mapping key), kind, parent_id, label, selected, supported,
variable_type, show_as_hex, show_as_signed, value_profile,
dropdown_choices, dropdown_link, dropdown_read_only, current_bytes,
address, recursive.  Builders keep the tables readable and let tests
mutate copies without touching the shared fixtures.
"""

from __future__ import annotations

import copy

from ct2trainer.native.value_types import prepare_value_profile

__all__ = [
    "build_deep_chain",
    "build_table",
    "blocked_record",
    "DROPDOWN_AMBIGUOUS_TABLE",
    "DROPDOWN_BAD_CHOICE_TABLE",
    "DROPDOWN_CHAIN_TABLE",
    "DROPDOWN_EMPTY_TABLE",
    "DROPDOWN_FLOAT_TARGET_TABLE",
    "DROPDOWN_GROUP_TARGET_TABLE",
    "DROPDOWN_HEX_FLOAT_TABLE",
    "DROPDOWN_HEX_TARGET_TABLE",
    "DROPDOWN_INACTIVE_TABLE",
    "DROPDOWN_INDEX_SEMANTICS_TABLE",
    "DROPDOWN_LINK_NOT_VALUE_TABLE",
    "DROPDOWN_MISSING_TABLE",
    "DROPDOWN_NO_LINK_NAME_TABLE",
    "DROPDOWN_NON_NUMERIC_TABLE",
    "DROPDOWN_READONLY_TABLE",
    "DROPDOWN_SCRIPT_TARGET_TABLE",
    "DROPDOWN_SELF_LINK_TABLE",
    "DROPDOWN_VALID_TABLE",
    "heading_record",
    "RECURSIVE_BITFIELD_TABLE",
    "RECURSIVE_CYCLE_TABLE",
    "RECURSIVE_DEEP_OK_TABLE",
    "RECURSIVE_DEEP_REJECT_TABLE",
    "RECURSIVE_INACTIVE_TABLE",
    "RECURSIVE_MIXED_TABLE",
    "RECURSIVE_NO_FLAG_TABLE",
    "RECURSIVE_NO_PROFILE_TABLE",
    "RECURSIVE_SELF_PARENT_TABLE",
    "RECURSIVE_TORSO_TABLE",
    "script_record",
    "value_record",
]


def value_record(label, *, kind="value", parent_id=None, variable_type="Byte",
                 show_as_hex=False, show_as_signed=None, address="",
                 selected=True, supported=True, recursive=False, **extra):
    record = {
        "label": label,
        "kind": kind,
        "parent_id": parent_id,
        "selected": selected,
        "supported": supported,
        "variable_type": variable_type,
        "show_as_hex": show_as_hex,
        "show_as_signed": show_as_signed,
        "address": address,
        "recursive": recursive,
    }
    record.update(extra)
    return record


def heading_record(label, *, parent_id=None, address=""):
    return value_record(label, kind="heading", parent_id=parent_id,
                        variable_type=None, address=address)


def script_record(label, *, parent_id=None):
    return value_record(label, kind="script", parent_id=parent_id,
                        variable_type=None)


def blocked_record(label, *, parent_id=None):
    return value_record(label, kind="blocked", parent_id=parent_id,
                        variable_type=None)


def build_table(spec):
    """{(id, record) -> record} -> {id: record}; deep-copies the records."""
    return {record_id: copy.deepcopy(record) for record_id, record in spec}


_TWO_BYTE_HEX_PROFILE = prepare_value_profile(
    "Array of byte", {"ByteLength": 2, "ShowAsHex": True})
_ONE_BYTE_HEX_PROFILE = prepare_value_profile(
    "Array of byte", {"ByteLength": 1, "ShowAsHex": True})
_FLAG_BITFIELD_PROFILE = prepare_value_profile(
    "Binary", {"BitStart": 0, "BitLength": 4,
               "ShowAsHex": False, "ShowAsSigned": False, "ShowAsBinary": False})


def _two_byte_hex_record(label, parent_id, address):
    return value_record(
        label, parent_id=parent_id, variable_type="Array of byte",
        show_as_hex=True, show_as_signed=False, address=address,
        value_profile=copy.deepcopy(_TWO_BYTE_HEX_PROFILE))


# ---------------------------------------------------------------------------
# RecursiveSetValue fixtures (re2.CT shape: "x +-" / "torso")
# ---------------------------------------------------------------------------

# "x +-" tree: Float parent with mixed child types (Float + Byte), one
# script child, one heading child that still collects its value
# descendant, one unsupported and one unselected value child whose
# own value descendant is still collected.
RECURSIVE_MIXED_TABLE = build_table([
    (100, value_record("x +-", variable_type="Float", address="pPlayerBase+30+18+10", recursive=True)),
    (101, value_record("x offset", parent_id=100, variable_type="Float", address="+80")),
    (102, value_record("x toggle", parent_id=100, address="+84")),
    (103, script_record("script kid", parent_id=100)),
    (104, heading_record("sub heading", parent_id=100)),
    (105, value_record("deep float", parent_id=104, variable_type="Float", address="+88")),
    (106, value_record("unsupported kid", parent_id=100, supported=False)),
    (107, value_record("unselected kid", parent_id=100, selected=False)),
    (108, value_record("unselected grandkid", parent_id=107)),
    (110, blocked_record("blocked kid", parent_id=100)),
])

# "torso" tree: two-byte hex byte-array parent (re2 shape) with two
# byte-array value children.  Value text "01 00" is valid for every
# profile record in the closure.
RECURSIVE_TORSO_TABLE = build_table([
    (200, value_record("torso", variable_type="Array of byte", show_as_hex=True,
                       show_as_signed=False, address="bWeakTorso", recursive=True,
                       value_profile=copy.deepcopy(_TWO_BYTE_HEX_PROFILE))),
    (201, _two_byte_hex_record("torso byte A", 200, "bTorsoA")),
    (202, _two_byte_hex_record("torso byte B", 200, "bTorsoB")),
])

# Cycle: 300's parent is 301 and 301's parent is 300.  Planning from 300
# must refuse with the named path (300, 301, 300).
RECURSIVE_CYCLE_TABLE = build_table([
    (300, value_record("alpha", parent_id=301, address="a", recursive=True)),
    (301, value_record("beta", parent_id=300, address="b")),
])

# Self-parent: 400 is its own parent.
RECURSIVE_SELF_PARENT_TABLE = build_table([
    (400, value_record("self", parent_id=400, address="s", recursive=True)),
])


def build_deep_chain(base, depth):
    """Target at ``base`` plus a straight value chain of ``depth`` children
    (relative depths 1..depth), all Byte/decimal."""
    table = {}
    for offset in range(depth + 1):
        record_id = base + offset
        table[record_id] = value_record(
            f"chain{offset}",
            parent_id=None if offset == 0 else record_id - 1,
            address=f"chain{offset}",
            recursive=offset == 0,
        )
    return table


# Deepest relative depth 65 -> must be rejected.
RECURSIVE_DEEP_REJECT_TABLE = build_deep_chain(500, 65)
# Deepest relative depth 64 -> the boundary case that must be accepted.
RECURSIVE_DEEP_OK_TABLE = build_deep_chain(600, 64)

# Targets without any usable value profile.
RECURSIVE_NO_PROFILE_TABLE = build_table([
    (700, value_record("no type", variable_type=None, address="t0", recursive=True)),
    (701, value_record("custom", variable_type="Custom", address="t1", recursive=True)),
])

# Recursive flag missing: a plain value record with a child.
RECURSIVE_NO_FLAG_TABLE = build_table([
    (800, value_record("plain", address="p", recursive=False)),
    (801, value_record("plain kid", parent_id=800, address="pk")),
])

# Flagged targets that are not activatable at all.
RECURSIVE_INACTIVE_TABLE = build_table([
    (900, value_record("unselected", address="u", recursive=True, selected=False)),
    (901, value_record("unsupported", address="s", recursive=True, supported=False)),
])

# Bit-field target: one without a snapshot (refused) and one with a
# snapshot whose unowned bits (bits 4..7 of byte 0) must survive.
RECURSIVE_BITFIELD_TABLE = build_table([
    (1000, value_record("flags", variable_type="Binary", show_as_hex=False,
                        show_as_signed=False, address="flags", recursive=True,
                        value_profile=copy.deepcopy(_FLAG_BITFIELD_PROFILE))),
    (1001, value_record("flags snap", variable_type="Binary", show_as_hex=False,
                        show_as_signed=False, address="flags2", recursive=True,
                        current_bytes=b"\x0f",
                        value_profile=copy.deepcopy(_FLAG_BITFIELD_PROFILE))),
])


# ---------------------------------------------------------------------------
# DropDownListLink fixtures (case-12, origin: Silent Hill Townfall rml, shape)
# ---------------------------------------------------------------------------

# Valid SHT-rml-shape pair: the Byte target "Achievement Related" holds
# the dropdown (choice value literals equal their indices, as in the
# pinned corpus); "Scored Kill By Bottle/Brick" are Byte link records.
DROPDOWN_VALID_TABLE = build_table([
    (1100, value_record("Achievement Related", address="[pStatistics]+A10",
                        dropdown_choices=[("0", "Kill By Bottle"), ("1", "Kill By Brick"),
                                          ("2", "Kill By Bomb"), ("3", "Kill By Melee")])),
    (1101, value_record("Scored Kill By Bottle", address="+1",
                        dropdown_link="Achievement Related")),
    (1102, value_record("Scored Kill By Brick", address="+2",
                        dropdown_link="Achievement Related")),
    (1103, value_record("Casefold Linker", address="+3",
                        dropdown_link="achievement related")),
])

# Case-fold twins: two records differ only by case, so "score" is
# ambiguous and must never be merged silently.
DROPDOWN_AMBIGUOUS_TABLE = build_table([
    (1200, value_record("Score", address="a",
                        dropdown_choices=[("0", "low")])),
    (1201, value_record("SCORE", address="b",
                        dropdown_choices=[("0", "high")])),
    (1202, value_record("Linker", address="c", dropdown_link="score")),
])

# Link name names no record in the table.
DROPDOWN_MISSING_TABLE = build_table([
    (1300, value_record("Linker", address="m", dropdown_link="Nowhere")),
])

# The record links to itself.
DROPDOWN_SELF_LINK_TABLE = build_table([
    (1400, value_record("Self", address="s", dropdown_link="Self",
                        dropdown_choices=[("0", "only")])),
])

# Chained links: 1500 -> 1501 and 1501 -> 1500 (both directions refuse).
DROPDOWN_CHAIN_TABLE = build_table([
    (1500, value_record("A", address="a", dropdown_link="B",
                        dropdown_choices=[("0", "x")])),
    (1501, value_record("B", address="b", dropdown_link="A",
                        dropdown_choices=[("0", "y")])),
])

# Pinned corpus shape: the link target is a group header, not a numeric
# value record -> refused (fail-closed, as the compiler does today).
DROPDOWN_GROUP_TARGET_TABLE = build_table([
    (1600, heading_record("Achievement Related", address="[pStatistics]+A10")),
    (1601, value_record("Scored Kill By Bottle", parent_id=1600, address="+1",
                        dropdown_link="Achievement Related")),
])

# Target is a byte array (profile-backed, not a simple numeric type).
DROPDOWN_NON_NUMERIC_TABLE = build_table([
    (1700, value_record("Array Target", address="arr", variable_type="Array of byte",
                        show_as_hex=True, show_as_signed=False,
                        value_profile=copy.deepcopy(_ONE_BYTE_HEX_PROFILE),
                        dropdown_choices=[("00", "zero")])),
    (1701, value_record("Linker", address="lk", dropdown_link="Array Target")),
])

# Target is a script record.
DROPDOWN_SCRIPT_TARGET_TABLE = build_table([
    (1800, script_record("Scripty")),
    (1801, value_record("Linker", address="lk", dropdown_link="Scripty")),
])

# Empty dropdowns: no choices at all, and only the "*" placeholder.
DROPDOWN_EMPTY_TABLE = build_table([
    (1900, value_record("No Choices", address="n")),
    (1901, value_record("Linker A", address="la", dropdown_link="No Choices")),
    (1902, value_record("Star Only", address="s",
                        dropdown_choices=[("*", "placeholder")])),
    (1903, value_record("Linker B", address="lb", dropdown_link="Star Only")),
])

# One choice literal is not parseable under the target type.
DROPDOWN_BAD_CHOICE_TABLE = build_table([
    (2000, value_record("Bad Target", address="bt",
                        dropdown_choices=[("0", "ok"), ("xyz", "bad")])),
    (2001, value_record("Linker", address="lk", dropdown_link="Bad Target")),
])

# Non-activatable pairs: link not selected, target unsupported.
DROPDOWN_INACTIVE_TABLE = build_table([
    (2100, value_record("Target A", address="ta",
                        dropdown_choices=[("0", "a"), ("1", "b")])),
    (2101, value_record("Linker Unselected", address="lu", selected=False,
                        dropdown_link="Target A")),
    (2102, value_record("Target B", address="tb", supported=False,
                        dropdown_choices=[("0", "a")])),
    (2103, value_record("Linker B", address="lb", dropdown_link="Target B")),
])

# Hex-display target ("2 Bytes"): index encoding must be a raw bit
# pattern in the target's full span.
DROPDOWN_HEX_TARGET_TABLE = build_table([
    (2200, value_record("Hex Target", address="hx", variable_type="2 Bytes",
                        show_as_hex=True,
                        dropdown_choices=[("00", "Zero"), ("01", "One"), ("02", "Two")])),
    (2201, value_record("Hex Linker", address="hl", dropdown_link="Hex Target")),
])

# Binding model decision pin: the stored value is the index, not the
# choice value literal (here literals 10/20/30 differ from 0/1/2).
DROPDOWN_INDEX_SEMANTICS_TABLE = build_table([
    (2300, value_record("Offset Target", address="base+10", variable_type="4 Bytes",
                        dropdown_choices=[("10", "Low"), ("20", "High"), ("30", "Max")])),
    (2301, value_record("Offset Linker", address="lk", dropdown_link="Offset Target")),
])

# The link carrier is not a value record at all.
DROPDOWN_LINK_NOT_VALUE_TABLE = build_table([
    (2400, dict(script_record("Script With Link"), dropdown_link="Some Target")),
    (2401, value_record("Some Target", address="st",
                        dropdown_choices=[("0", "a")])),
])

# Value record without any dropdown link name.
DROPDOWN_NO_LINK_NAME_TABLE = build_table([
    (2500, value_record("Plain Value", address="pv")),
])

# Read-only target dropdown: still inspectable, still activatable in the
# model (the model plans writes; the runtime gates the interaction).
DROPDOWN_READONLY_TABLE = build_table([
    (2600, value_record("RO Target", address="ro", dropdown_read_only=True,
                        dropdown_choices=[("0", "a"), ("1", "b")])),
    (2601, value_record("RO Linker", address="rl", dropdown_link="RO Target")),
])

# Float target: whole-index values only.
DROPDOWN_FLOAT_TARGET_TABLE = build_table([
    (2700, value_record("Float Target", address="ft", variable_type="Float",
                        dropdown_choices=[("1.0", "One"), ("2.0", "Two")])),
    (2701, value_record("Float Linker", address="fl", dropdown_link="Float Target")),
])

# WP-33: hex-float targets are raw IEEE-754 bit patterns; choice literals are
# fixed-width (8 hex digits for Float) little-endian raw bytes, so the stored
# value (the choice index) encodes to the bit pattern of the float index.
DROPDOWN_HEX_FLOAT_TABLE = build_table([
    (2800, value_record("Hex Float", address="hf", variable_type="Float",
                        show_as_hex=True,
                        dropdown_choices=[("00000000", "zero"),
                                          ("3F800000", "one"),
                                          ("40000000", "two")])),
    (2801, value_record("Hex Float Linker", address="hfl",
                        dropdown_link="Hex Float")),
])
