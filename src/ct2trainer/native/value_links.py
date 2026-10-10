"""Standalone value-link models for the native trainer converter (AP-10 lane).

Two cross-record value semantics that the native compiler currently rejects
fail-closed are modeled here as pure static modules:

- ``recursive_parent_value``: a value record flagged with the CT option
  ``<Options moRecursiveSetValue="1"/>`` whose single value write propagates
  to every writable value descendant (corpus shape: re2.CT "x +-" Float
  pointer record with value children; "torso" two-byte hex array record).
- ``dropdown_link``: a value record whose CT ``<DropDownListLink>`` names
  another record in the same table (corpus shape: Silent Hill Townfall rml
  "Scored Kill By Bottle" -> "Achievement Related").  Binding model
  decision: the target record's stored value is the zero-based index into
  the target record's own dropdown choices (index 0 = first choice); in
  the pinned corpus the choice value literals equal those indices.

Both models are static: they consume a record table (mapping of record id
to a metadata mapping shaped like a compiler plan entry) and produce
byte-exact, deterministic write plans.  They never read or write process
memory, never execute table Lua, and never use Cheat Engine implementation
code or binaries.  Pinned CT bytes were read read-only for semantics
derivation only; no corpus data is embedded in any plan.

Input record fields (unknown keys are ignored):
    kind              "value" | "script" | "heading" | "blocked"
    parent_id         non-negative int or None (must name a record)
    label             bounded text
    selected          bool (must be True for writable/activatable records)
    supported         bool (must be True for writable/activatable records)
    variable_type     "Byte" | "2 Bytes" | "4 Bytes" | "8 Bytes" | "Float"
                      | "Double" | "Array of byte" | "Binary" | "String"
                      | None
    show_as_hex       bool (default False)
    show_as_signed    bool or None (None: native literal policy = unsigned)
    value_profile     validated value_types.py profile for Array of byte /
                      Binary / String records (must match type and display
                      flags; an optional ``size`` must equal the profile
                      span)
    dropdown_choices  list/tuple of (value, description) pairs
    dropdown_link     non-empty bounded text or None
    dropdown_read_only  bool (default False)
    current_bytes     bytes or None (bit-field profiles require a snapshot)
    address           bounded text
    recursive         bool (default False) - the moRecursiveSetValue flag

Guarantees:
- deterministic plans: identical inputs produce byte-identical plans and
  stable SHA-256 digests (no time, randomness, or identity components);
- the input mapping is deep-copied on construction and never mutated
  (deep-copy contract pinned by the tests);
- every rejection is fail-closed with a named error class carrying record
  id/label and, for cycles, the offending path.
"""

from __future__ import annotations

import copy
import json
import math
import re
import struct
from collections.abc import Mapping
from hashlib import sha256

from ..table import MAX_ENTRIES, SIMPLE_VALUE_TYPES
from .value_types import (ValueTypeError, parse_profile_value,
                          validate_value_profile)


SCHEMA_RECURSIVE_PLAN = "ct2trainer-recursive-value-plan/v1"
SCHEMA_DROPDOWN_PLAN = "ct2trainer-dropdown-link-plan/v1"
SCHEMA_DROPDOWN_INSPECTION = "ct2trainer-dropdown-link-inspection/v1"

MAX_RECURSIVE_DEPTH = 64
MAX_LABEL_LENGTH = 10000
MAX_ADDRESS_LENGTH = 1024
MAX_LINK_NAME_LENGTH = 10000
MAX_CHOICE_VALUE_LENGTH = 128

_SIMPLE_SIZES = {
    "Byte": 1,
    "2 Bytes": 2,
    "4 Bytes": 4,
    "8 Bytes": 8,
    "Float": 4,
    "Double": 8,
}

_PROFILE_VARIABLE_TYPES = {
    "byte_array": "Array of byte",
    "bitfield": "Binary",
    "string": "String",
}

_KNOWN_KINDS = {"value", "script", "heading", "blocked"}

_HEX_LITERAL = re.compile(r"(?:0[xX])?[0-9a-fA-F]+\Z")
_DECIMAL_LITERAL = re.compile(r"-?[0-9]+\Z")
_FLOAT_LITERAL = re.compile(
    r"-?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")


class ValueLinksError(ValueError):
    """Base error for the value-link models."""


class RecursiveSetValueError(ValueLinksError):
    """Base error for the recursive parent value model."""


class RecursiveTableError(RecursiveSetValueError):
    """Malformed record table input."""


class RecursiveTargetError(RecursiveSetValueError):
    """The target record is unknown or not a writable value record."""


class RecursiveNoValueProfileError(RecursiveSetValueError):
    """A record in the write set has no usable value profile."""


class RecursiveCycleError(RecursiveSetValueError):
    """The parent chain revisits a record; ``path`` names the cycle."""

    def __init__(self, message: str, path) -> None:
        super().__init__(message)
        self.path = tuple(path)


class RecursiveDepthError(RecursiveSetValueError):
    """The value closure exceeds the pinned depth bound."""


class RecursiveSnapshotRequiredError(RecursiveSetValueError):
    """A bit field child needs a current snapshot to preserve unowned bits."""


class RecursiveValueParseError(RecursiveSetValueError):
    """The target value text is not a valid literal for a record in the set."""


class DropdownLinkError(ValueLinksError):
    """Base error for the cross-record dropdown link model."""


class DropdownLinkTableError(DropdownLinkError):
    """Malformed record table input."""


class DropdownLinkTargetError(DropdownLinkError):
    """The dropdown link name is missing or does not resolve uniquely."""

    def __init__(self, message: str, *, link_name: str | None = None,
                 candidates=()) -> None:
        super().__init__(message)
        self.link_name = link_name
        self.candidates = tuple(candidates)


class DropdownLinkCycleError(DropdownLinkError):
    """The link target links again; ``path`` names the chain."""

    def __init__(self, message: str, path) -> None:
        super().__init__(message)
        self.path = tuple(path)


class DropdownLinkTypeRefused(DropdownLinkError):
    """A record in the pair is not a numeric value record."""


class DropdownLinkEmptyRefused(DropdownLinkError):
    """The target dropdown has no concrete usable choices."""


class DropdownLinkActivatableError(DropdownLinkError):
    """One of the pair is not selected/supported; ``problems`` names each."""

    def __init__(self, message: str, problems) -> None:
        super().__init__(message)
        self.problems = tuple(problems)


class DropdownLinkValueParseError(DropdownLinkError):
    """The target value text is not a valid literal for its type."""


class DropdownIndexError(DropdownLinkError):
    """The value/index falls outside the target's choice range."""

    def __init__(self, message: str, *, index: int | None = None,
                 choice_count: int | None = None) -> None:
        super().__init__(message)
        self.index = index
        self.choice_count = choice_count


def _simple_value_bytes(variable_type: str, show_as_hex: bool,
                        show_as_signed: bool | None, text: str) -> bytes:
    """Byte-exact encoding of one literal under the native literal policy.

    Missing signed means unsigned; hexadecimal literals are raw bit patterns.
    Raises ValueError with a stable message on any mismatch.
    """
    if not isinstance(text, str) or not 0 < len(text) <= 66:
        raise ValueError("value literal must be 1-66 characters")
    literal = text.strip(" \t\r\n")
    if not literal:
        raise ValueError("value literal must not be empty")
    if variable_type in {"Float", "Double"}:
        if show_as_hex:
            raise ValueError("hexadecimal floating-point values are unsupported")
        if _FLOAT_LITERAL.fullmatch(literal) is None:
            raise ValueError(f"enter a finite {variable_type} literal")
        number = float(literal)
        if not math.isfinite(number):
            raise ValueError(f"{variable_type} literal is not finite")
        return struct.pack("<f" if variable_type == "Float" else "<d", number)
    size = _SIMPLE_SIZES[variable_type]
    bits = 8 * size
    if show_as_hex:
        if _HEX_LITERAL.fullmatch(literal) is None:
            raise ValueError(f"enter an exact {variable_type} hex bit pattern")
        number = int(literal, 16)
        if number >= 1 << bits:
            raise ValueError(f"hex value exceeds {variable_type} bit width")
        return number.to_bytes(size, "little")
    if _DECIMAL_LITERAL.fullmatch(literal) is None:
        raise ValueError(f"enter an exact {variable_type} decimal integer")
    number = int(literal, 10)
    signed = show_as_signed is True
    if signed:
        if not -(1 << (bits - 1)) <= number <= (1 << (bits - 1)) - 1:
            raise ValueError(f"decimal value exceeds signed {variable_type} range")
    elif not 0 <= number <= (1 << bits) - 1:
        raise ValueError(f"decimal value exceeds {variable_type} range")
    return number.to_bytes(size, "little", signed=signed)


def _plan_element(record: dict, depth: int, value_text: str, raw: bytes) -> dict:
    """One deterministic write element; the SHA covers every other field."""
    payload = {
        "address": record["address"],
        "bytes_hex": raw.hex().upper(),
        "depth": depth,
        "label": record["label"],
        "record_id": record["id"],
        "size": len(raw),
        "value_text": value_text,
        "variable_type": record["variable_type"],
    }
    payload["sha256"] = sha256(json.dumps(payload, sort_keys=True,
                                         separators=(",", ":")).encode("utf-8")).hexdigest()
    return payload


def _plan_sha(plan: dict) -> str:
    """Stable plan digest over every field except the digest itself."""
    payload = {key: value for key, value in plan.items() if key != "plan_sha256"}
    return sha256(json.dumps(payload, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")).hexdigest()


def _normalize_table(records, table_error) -> dict:
    """Validate and deep-copy the input table; the caller's mapping is
    never mutated (deep-copy contract pinned by the tests)."""
    if not isinstance(records, Mapping) or not records:
        raise table_error("record table must be a non-empty mapping of record id to record")
    if len(records) > MAX_ENTRIES:
        raise table_error(f"record table exceeds the {MAX_ENTRIES} record bound")
    table: dict[int, dict] = {}
    for raw_id, raw in records.items():
        if type(raw_id) is not int or raw_id < 0:
            raise table_error(f"record ids must be non-negative integers, found {raw_id!r}")
        if not isinstance(raw, Mapping):
            raise table_error(f"record {raw_id!r} must be a mapping")
        record = copy.deepcopy(dict(raw))
        try:
            kind = record.get("kind")
            if kind not in _KNOWN_KINDS:
                raise table_error(f"record {raw_id} has unknown kind {kind!r}")
            parent_id = record.get("parent_id")
            if parent_id is not None and (type(parent_id) is not int or parent_id < 0):
                raise table_error(f"record {raw_id} has an invalid parent id {parent_id!r}")
            if type(record.get("selected")) is not bool:
                raise table_error(f"record {raw_id} must carry a boolean selected flag")
            if type(record.get("supported")) is not bool:
                raise table_error(f"record {raw_id} must carry a boolean supported flag")
            label = record.get("label", "")
            if not isinstance(label, str) or len(label) > MAX_LABEL_LENGTH:
                raise table_error(f"record {raw_id} label is not bounded printable text")
            address = record.get("address", "")
            if not isinstance(address, str) or len(address) > MAX_ADDRESS_LENGTH:
                raise table_error(f"record {raw_id} address is not bounded text")
            show_as_hex = record.get("show_as_hex", False)
            if type(show_as_hex) is not bool:
                raise table_error(f"record {raw_id} show_as_hex must be a boolean")
            show_as_signed = record.get("show_as_signed")
            if show_as_signed is not None and type(show_as_signed) is not bool:
                raise table_error(f"record {raw_id} show_as_signed must be a boolean or null")
            variable_type = record.get("variable_type")
            if variable_type is not None and (not isinstance(variable_type, str)
                                              or len(variable_type) > 64):
                raise table_error(f"record {raw_id} variable_type is not bounded text")
            choices: list[tuple[str, str]] = []
            raw_choices = record.get("dropdown_choices", ())
            if not isinstance(raw_choices, (list, tuple)):
                raise table_error(f"record {raw_id} dropdown choices must be a list or tuple")
            for item in raw_choices:
                if (not isinstance(item, (list, tuple)) or len(item) != 2
                        or not isinstance(item[0], str)
                        or len(item[0]) > MAX_CHOICE_VALUE_LENGTH
                        or not isinstance(item[1], str)
                        or len(item[1]) > MAX_LABEL_LENGTH):
                    raise table_error(f"record {raw_id} has a malformed dropdown choice")
                choices.append((item[0], item[1]))
            link_name = record.get("dropdown_link")
            if link_name is not None and (not isinstance(link_name, str)
                                          or not link_name.strip()
                                          or len(link_name) > MAX_LINK_NAME_LENGTH):
                raise table_error(f"record {raw_id} dropdown link name is not bounded text")
            read_only = record.get("dropdown_read_only", False)
            if type(read_only) is not bool:
                raise table_error(f"record {raw_id} dropdown_read_only must be a boolean")
            current = record.get("current_bytes")
            if current is not None and not isinstance(current, (bytes, bytearray)):
                raise table_error(f"record {raw_id} current_bytes must be bytes")
            recursive = record.get("recursive", False)
            if recursive is None:
                recursive = False
            if type(recursive) is not bool:
                raise table_error(f"record {raw_id} recursive flag must be a boolean")
            profile = record.get("value_profile")
            if profile is not None:
                if not isinstance(profile, Mapping):
                    raise table_error(f"record {raw_id} value_profile must be a mapping")
                try:
                    validate_value_profile(dict(profile))
                except ValueTypeError as exc:
                    raise table_error(
                        f"record {raw_id} has an invalid value profile: {exc}") from exc
            size = record.get("size")
            if size is not None and (type(size) is not int or size < 0):
                raise table_error(f"record {raw_id} size must be a non-negative integer")
        except table_error:
            raise
        except (TypeError, ValueError, RecursionError) as exc:
            raise table_error(f"record {raw_id!r} failed normalization: {exc}") from exc
        if kind == "value":
            if profile is not None:
                expected = _PROFILE_VARIABLE_TYPES.get(profile["kind"])
                if expected is None or variable_type != expected:
                    raise table_error(
                        f"record {raw_id} variable_type does not match its value profile")
                if (show_as_hex != profile["properties"]["ShowAsHex"]
                        or show_as_signed != profile["properties"]["ShowAsSigned"]):
                    raise table_error(
                        f"record {raw_id} display flags do not match its value profile")
            derived = profile["size"] if profile is not None else _SIMPLE_SIZES.get(variable_type)
            if size is not None and size != derived:
                raise table_error(
                    f"record {raw_id} size {size} does not match its declared span "
                    f"{derived if derived is not None else 'unknown'}")
        table[raw_id] = {
            "id": raw_id,
            "label": label,
            "parent_id": parent_id,
            "kind": kind,
            "supported": record["supported"],
            "selected": record["selected"],
            "variable_type": variable_type,
            "show_as_hex": show_as_hex,
            "show_as_signed": show_as_signed,
            "value_profile": copy.deepcopy(dict(profile)) if profile is not None else None,
            "dropdown_choices": tuple(choices),
            "dropdown_link": link_name.strip() if link_name else None,
            "dropdown_read_only": read_only,
            "current_bytes": bytes(current) if current is not None else None,
            "address": address,
            "recursive": recursive,
        }
    for record in table.values():
        parent = record["parent_id"]
        if parent is not None and parent not in table:
            raise table_error(
                f"record {record['id']} ('{record['label']}') references unknown parent {parent}")
    return table


class RecursiveSetValueModel:
    """Static closure and byte-exact write plans for moRecursiveSetValue parents.

    The plan covers the flagged target and every writable value descendant.
    Order is deterministic: deepest records first, ties by ascending record
    id, so the target itself is written last.  Non-value children (script /
    navigation / blocked) are skipped (never written) and logged with a
    reason; unselected or unsupported value children are skipped the same
    way and never block the closure, so their value descendants are still
    collected.  Cycles (including a self-parent) and relative depths above
    :data:`MAX_RECURSIVE_DEPTH` are refused with the offending path/record.
    The input table is deep-copied on construction and the model never
    mutates it.
    """

    def __init__(self, records):
        self._records = _normalize_table(records, RecursiveTableError)
        self._children: dict[int, list[int]] = {}
        for record in self._records.values():
            if record["parent_id"] is not None:
                self._children.setdefault(record["parent_id"], []).append(record["id"])
        for children in self._children.values():
            children.sort()

    def plan_writes(self, target_id: int, value_text: str) -> dict:
        """Return the deterministic byte-exact write plan for one value text."""
        if type(target_id) is not int or target_id not in self._records:
            raise RecursiveTargetError(
                f"unknown recursive value target record id {target_id!r}")
        target = self._records[target_id]
        if target["kind"] != "value":
            raise RecursiveTargetError(
                f"recursive value target {target_id} ('{target['label']}') is not a value "
                f"record (kind={target['kind']})")
        if not target["supported"]:
            raise RecursiveTargetError(
                f"recursive value target {target_id} ('{target['label']}') is unsupported")
        if not target["selected"]:
            raise RecursiveTargetError(
                f"recursive value target {target_id} ('{target['label']}') is not selected")
        if not target["recursive"]:
            raise RecursiveTargetError(
                f"recursive value target {target_id} ('{target['label']}') is not "
                "flagged moRecursiveSetValue")
        self._require_profile(target)
        if not isinstance(value_text, str):
            raise RecursiveValueParseError(
                f"target value must be text, got {type(value_text).__name__}")
        writes: dict[int, int] = {}
        skipped: dict[int, tuple[int, str]] = {}
        self._collect(target_id, 0, (target_id,), writes, skipped)
        elements = [self._element(record_id, writes[record_id], value_text)
                    for record_id in sorted(writes, key=lambda record_id: (-writes[record_id], record_id))]
        skipped_entries = [
            {"record_id": record_id, "label": self._records[record_id]["label"],
             "depth": depth, "kind": self._records[record_id]["kind"], "reason": reason}
            for record_id, (depth, reason) in sorted(skipped.items())
        ]
        plan = {
            "schema": SCHEMA_RECURSIVE_PLAN,
            "target_id": target_id,
            "value_text": value_text,
            "writes": elements,
            "skipped": skipped_entries,
            "write_count": len(elements),
            "skipped_count": len(skipped_entries),
        }
        plan["plan_sha256"] = _plan_sha(plan)
        return plan

    def _collect(self, node_id: int, depth: int, path, writes, skipped) -> None:
        record = self._records[node_id]
        if record["kind"] == "value":
            if not record["supported"]:
                skipped[node_id] = (depth, "unsupported value record is never written")
            elif not record["selected"]:
                skipped[node_id] = (depth, "unselected value record is never written")
            else:
                self._require_profile(record)
                writes[node_id] = depth
        else:
            skipped[node_id] = (depth, f"not a value record (kind={record['kind']})")
        for child_id in self._children.get(node_id, ()):
            if child_id in path:
                cycle = path[path.index(child_id):] + (child_id,)
                names = " -> ".join(
                    f"{record_id} ('{self._records[record_id]['label']}')" for record_id in cycle)
                raise RecursiveCycleError(f"parent chain cycle: {names}", cycle)
            if depth + 1 > MAX_RECURSIVE_DEPTH:
                raise RecursiveDepthError(
                    f"recursive value closure exceeds {MAX_RECURSIVE_DEPTH} levels at record "
                    f"{child_id} ('{self._records[child_id]['label']}')")
            self._collect(child_id, depth + 1, path + (child_id,), writes, skipped)

    def _require_profile(self, record: dict) -> None:
        profile = record["value_profile"]
        if profile is not None:
            if profile["kind"] == "bitfield" and record["current_bytes"] is None:
                raise RecursiveSnapshotRequiredError(
                    f"bit field record {record['id']} ('{record['label']}') requires a current "
                    "snapshot to preserve unowned bits")
            return
        variable_type = record["variable_type"]
        if variable_type not in _SIMPLE_SIZES:
            raise RecursiveNoValueProfileError(
                f"record {record['id']} ('{record['label']}') has no usable value profile "
                f"(variable_type={variable_type!r})")
        if record["show_as_hex"] and variable_type in {"Float", "Double"}:
            raise RecursiveNoValueProfileError(
                f"record {record['id']} ('{record['label']}') uses unsupported "
                "hexadecimal floating-point display")

    def _element(self, record_id: int, depth: int, value_text: str) -> dict:
        record = self._records[record_id]
        return _plan_element(record, depth, value_text, self._value_bytes(record, value_text))

    def _value_bytes(self, record: dict, value_text: str) -> bytes:
        profile = record["value_profile"]
        if profile is not None:
            try:
                return parse_profile_value(profile, value_text, record["current_bytes"])
            except ValueTypeError as exc:
                raise RecursiveValueParseError(
                    f"record {record['id']} ('{record['label']}'): {exc}") from exc
        try:
            return _simple_value_bytes(record["variable_type"], record["show_as_hex"],
                                       record["show_as_signed"], value_text)
        except ValueError as exc:
            raise RecursiveValueParseError(
                f"record {record['id']} ('{record['label']}'): {exc}") from exc


def recursive_write_closure(records, target_id: int) -> list[int]:
    """Deterministic write closure of a recursive value target.

    Returns the target plus every supported, selected value descendant,
    deepest records first, ties by ascending record id, the target last.
    The walk mirrors ``RecursiveSetValueModel.plan_writes`` so compile-time
    plan metadata and runtime plans always agree on write set and order.
    Unknown or inactive targets, targets that are not value records,
    parent-chain cycles, and closures deeper than ``MAX_RECURSIVE_DEPTH``
    are refused with the model's named errors. Records need only the
    fields ``kind``, ``supported``, ``selected`` and ``parent_id``.
    """
    if type(target_id) is not int or target_id < 0:
        raise RecursiveTargetError(f"unknown recursive value target record id {target_id!r}")
    if not isinstance(records, Mapping) or not records:
        raise RecursiveTableError("record table must be a non-empty mapping of record id to record")
    by_id: dict[int, dict] = {}
    for raw_id, raw in records.items():
        if type(raw_id) is not int or raw_id < 0:
            raise RecursiveTableError(f"record ids must be non-negative integers, found {raw_id!r}")
        if not isinstance(raw, Mapping):
            raise RecursiveTableError(f"record {raw_id!r} must be a mapping")
        by_id[raw_id] = raw
    target = by_id[target_id]
    if target.get("kind") != "value":
        raise RecursiveTargetError(
            f"recursive value target {target_id} is not a value record (kind={target.get('kind')!r})")
    if target.get("supported") is not True:
        raise RecursiveTargetError(f"recursive value target {target_id} is unsupported")
    if target.get("selected") is not True:
        raise RecursiveTargetError(f"recursive value target {target_id} is not selected")
    children: dict[int, list[int]] = {}
    for record_id, record in by_id.items():
        parent = record.get("parent_id")
        if parent is None:
            continue
        if type(parent) is not int or parent < 0 or parent not in by_id:
            raise RecursiveTableError(f"record {record_id} references unknown parent {parent!r}")
        children.setdefault(parent, []).append(record_id)
    for child_ids in children.values():
        child_ids.sort()
    writes: dict[int, int] = {}
    stack: list[tuple[int, int, tuple[int, ...]]] = [(target_id, 0, (target_id,))]
    while stack:
        node_id, depth, path = stack.pop()
        record = by_id[node_id]
        if (record.get("kind") == "value" and record.get("supported") is True
                and record.get("selected") is True):
            writes[node_id] = depth
        for child_id in children.get(node_id, ()):
            if child_id in path:
                cycle = path[path.index(child_id):] + (child_id,)
                names = " -> ".join(
                    f"{node} ('{by_id[node].get('label', '?')}')" for node in cycle)
                raise RecursiveCycleError(f"parent chain cycle: {names}", cycle)
            if depth + 1 > MAX_RECURSIVE_DEPTH:
                raise RecursiveDepthError(
                    f"recursive value closure exceeds {MAX_RECURSIVE_DEPTH} levels at record "
                    f"{child_id} ('{by_id[child_id].get('label', '?')}')")
            stack.append((child_id, depth + 1, path + (child_id,)))
    return sorted(writes, key=lambda record_id: (-writes[record_id], record_id))


class DropdownLinkModel:
    """Static validation and byte-exact write plans for cross-record
    ``DropDownListLink``.

    Binding model decision: the value stored by the link pair is the
    zero-based index into the target record's dropdown choices (index 0 =
    first choice).  The target record is the value record named by the
    link; it must be a numeric value record (one of the six simple numeric
    types) whose dropdown holds concrete, individually parseable literal
    choices.  The linked record (the record carrying the
    ``DropDownListLink`` attribute) is the cross-record handle: it must be
    a value record, its own value type does not drive the plan, and it
    must not name a second link.

    ``resolve(link_record_id, target_value)`` parses the target record's
    current value text under the target's own type and display flags and
    returns ``(index, choice description, raw bytes)``.
    ``apply(link_record_id, index)`` returns the byte-exact write plan for
    the target record, encoding the index through the target record's value
    profile.  ``inspect(link_record_id, current_value=None)`` is a read-only
    assessment: it reports the target name, choices, read-only state,
    activatability and the current index without ever modifying any record.

    Selection and support are an activatability condition: ``inspect``
    reports them, while ``resolve``/``apply`` refuse a non-activatable
    link with every problem named.  Structural problems (missing or
    ambiguous target name, non-numeric or chained target, empty or unusable
    dropdown) are refused by every method.  Name identity is case-folded on
    both sides, matching the existing symbol-matching practice; two records
    that differ only by case are therefore ambiguous, never silently merged.
    """

    def __init__(self, records):
        self._records = _normalize_table(records, DropdownLinkTableError)
        self._by_label: dict[str, list[int]] = {}
        for record in self._records.values():
            self._by_label.setdefault(record["label"].casefold(), []).append(record["id"])
        for ids in self._by_label.values():
            ids.sort()

    def _pair(self, link_record_id: int):
        """Return (linked record, target record, usable choices) or refuse."""
        if type(link_record_id) is not int or link_record_id not in self._records:
            raise DropdownLinkError(f"unknown dropdown link record id {link_record_id!r}")
        link = self._records[link_record_id]
        if link["kind"] != "value":
            raise DropdownLinkTypeRefused(
                f"linked record {link['id']} ('{link['label']}') is not a value record "
                f"(kind={link['kind']})")
        name = link["dropdown_link"]
        if name is None:
            raise DropdownLinkTargetError(
                f"record {link['id']} ('{link['label']}') has no dropdown link name",
                link_name=None, candidates=())
        matches = self._by_label.get(name.casefold(), ())
        if not matches:
            raise DropdownLinkTargetError(
                f"dropdown link target {name!r} of record {link['id']} "
                f"('{link['label']}') is not found in the table",
                link_name=name, candidates=())
        if len(matches) > 1:
            raise DropdownLinkTargetError(
                f"dropdown link target {name!r} of record {link['id']} is ambiguous "
                f"({len(matches)} records match case-insensitively)",
                link_name=name, candidates=list(matches))
        target = self._records[matches[0]]
        if target["id"] == link_record_id:
            raise DropdownLinkCycleError(
                f"dropdown link target of record {link_record_id} ('{link['label']}') is "
                "the record itself", path=(link_record_id,))
        if target["kind"] != "value":
            raise DropdownLinkTypeRefused(
                f"dropdown link target {target['id']} ('{target['label']}') is not a value "
                f"record (kind={target['kind']})")
        if target["variable_type"] not in SIMPLE_VALUE_TYPES:
            raise DropdownLinkTypeRefused(
                f"dropdown link target {target['id']} ('{target['label']}') is not a numeric "
                f"value record (variable_type={target['variable_type']!r})")
        if target["show_as_hex"] and target["variable_type"] in {"Float", "Double"}:
            raise DropdownLinkTypeRefused(
                f"dropdown link target {target['id']} ('{target['label']}') uses unsupported "
                "hexadecimal floating-point display")
        choices = [choice for choice in target["dropdown_choices"] if choice[0] != "*"]
        if not choices:
            raise DropdownLinkEmptyRefused(
                f"dropdown of target record {target['id']} ('{target['label']}') has no "
                "concrete choices")
        for value, _ in choices:
            try:
                _simple_value_bytes(target["variable_type"], target["show_as_hex"],
                                    target["show_as_signed"], value)
            except ValueError as exc:
                raise DropdownLinkEmptyRefused(
                    f"dropdown of target record {target['id']} ('{target['label']}') "
                    f"contains unusable literal {value!r}: {exc}") from exc
        if target["dropdown_link"] is not None:
            raise DropdownLinkCycleError(
                f"dropdown link target {target['id']} ('{target['label']}') links again to "
                f"{target['dropdown_link']!r}; chained dropdown links are unsupported",
                path=(link_record_id, target["id"],
                      self._by_label.get(target["dropdown_link"].casefold(), ())))
        return link, target, choices

    def _activatable_problems(self, link: dict, target: dict) -> list:
        problems = []
        if not link["supported"]:
            problems.append(f"link record {link['id']} ('{link['label']}') is unsupported")
        if not link["selected"]:
            problems.append(f"link record {link['id']} ('{link['label']}') is not selected")
        if not target["supported"]:
            problems.append(f"target record {target['id']} ('{target['label']}') is unsupported")
        if not target["selected"]:
            problems.append(f"target record {target['id']} ('{target['label']}') is not selected")
        return problems

    def _index_of(self, record: dict, raw: bytes) -> int:
        variable_type = record["variable_type"]
        if variable_type in {"Float", "Double"}:
            number = struct.unpack("<f" if variable_type == "Float" else "<d", raw)[0]
            if not math.isfinite(number) or number != int(number):
                raise DropdownLinkValueParseError(
                    f"target record {record['id']} ('{record['label']}') value {number!r} "
                    "is not a whole index")
            return int(number)
        signed = record["show_as_signed"] is True and not record["show_as_hex"]
        return int.from_bytes(raw, "little", signed=signed)

    def inspect(self, link_record_id: int, current_value: str | None = None) -> dict:
        """Read-only assessment: target name, choices, current index.

        Never mutates any record.  Structural problems are refused with
        named errors; selection/support problems are reported in
        ``activatable``/``problems`` without refusing.  ``current_value``
        is the target record's present value text (a runtime read); when
        omitted or unparseable the current index stays unknown.
        """
        link, target, choices = self._pair(link_record_id)
        problems = self._activatable_problems(link, target)
        current_index: int | None = None
        current_choice: str | None = None
        current_error: str | None = None
        if current_value is not None:
            if not isinstance(current_value, str):
                current_error = f"current value must be text, got {type(current_value).__name__}"
            else:
                try:
                    raw = _simple_value_bytes(target["variable_type"], target["show_as_hex"],
                                              target["show_as_signed"], current_value)
                except ValueError as exc:
                    current_error = str(exc)
                else:
                    try:
                        index = self._index_of(target, raw)
                    except DropdownLinkValueParseError as exc:
                        current_error = str(exc)
                    else:
                        if 0 <= index < len(choices):
                            current_index = index
                            current_choice = choices[index][1]
                        else:
                            current_error = (
                                f"value {index} is outside the choice range 0..{len(choices) - 1}")
        result = {
            "schema": SCHEMA_DROPDOWN_INSPECTION,
            "link_record_id": link["id"],
            "link_record_label": link["label"],
            "link_name": link["dropdown_link"],
            "target_record_id": target["id"],
            "target_record_label": target["label"],
            "target_variable_type": target["variable_type"],
            "choices": [{"index": position, "value": value, "description": description}
                        for position, (value, description) in enumerate(choices)],
            "read_only": target["dropdown_read_only"],
            "activatable": not problems,
            "problems": problems,
            "current_index": current_index,
            "current_choice": current_choice,
            "current_error": current_error,
        }
        return result

    def resolve(self, link_record_id: int, target_value: str):
        """Return (index, choice description, raw bytes) for one value text.

        The value text is the target record's stored value, parsed under the
        target record's own type and display flags; the resulting integer is
        the zero-based index into the target's usable choices.  The link
        must be activatable (both records selected and supported).
        """
        link, target, choices = self._pair(link_record_id)
        problems = self._activatable_problems(link, target)
        if problems:
            raise DropdownLinkActivatableError(
                "dropdown link is not activatable: " + "; ".join(problems), problems)
        if not isinstance(target_value, str):
            raise DropdownLinkValueParseError(
                f"target value must be text, got {type(target_value).__name__}")
        try:
            raw = _simple_value_bytes(target["variable_type"], target["show_as_hex"],
                                      target["show_as_signed"], target_value)
        except ValueError as exc:
            raise DropdownLinkValueParseError(
                f"target record {target['id']} ('{target['label']}') value {target_value!r}: "
                f"{exc}") from exc
        index = self._index_of(target, raw)
        if not 0 <= index < len(choices):
            raise DropdownIndexError(
                f"target record {target['id']} ('{target['label']}') value {index} is outside "
                f"the choice range 0..{len(choices) - 1}",
                index=index, choice_count=len(choices))
        return index, choices[index][1], raw

    def apply(self, link_record_id: int, index: int) -> dict:
        """Return the byte-exact write plan for the given choice index.

        The index is stored as the target record's value, encoded through
        the target record's own value profile (its type and display flags);
        the plan is deterministic and carries a stable SHA.  The link must
        be activatable (both records selected and supported).
        """
        link, target, choices = self._pair(link_record_id)
        problems = self._activatable_problems(link, target)
        if problems:
            raise DropdownLinkActivatableError(
                "dropdown link is not activatable: " + "; ".join(problems), problems)
        if type(index) is not int:
            raise DropdownIndexError(
                f"index must be an integer, got {type(index).__name__}",
                index=None, choice_count=len(choices))
        if not 0 <= index < len(choices):
            raise DropdownIndexError(
                f"index {index} is outside the choice range 0..{len(choices) - 1}",
                index=index, choice_count=len(choices))
        literal = format(index, "X") if target["show_as_hex"] else str(index)
        raw = _simple_value_bytes(target["variable_type"], target["show_as_hex"],
                                  target["show_as_signed"], literal)
        plan = {
            "schema": SCHEMA_DROPDOWN_PLAN,
            "link_record_id": link["id"],
            "target_record_id": target["id"],
            "index": index,
            "choice_description": choices[index][1],
            "writes": [_plan_element(target, 0, literal, raw)],
        }
        plan["plan_sha256"] = _plan_sha(plan)
        return plan
