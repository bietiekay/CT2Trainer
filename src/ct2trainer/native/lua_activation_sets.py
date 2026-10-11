"""Statically extracted record-ID activation sets from embedded table Lua.

WP-14 (C3): multi-step tables carry a "master toggle" record whose embedded
``{$lua}`` section flips a known set of other records on or off by record
ID, for example::

    [ENABLE]
    getAddressList().getMemoryRecordByID(2).Active = true
    getAddressList().getMemoryRecordByID(6).Active = true
    [DISABLE]
    getAddressList().getMemoryRecordByID(2).Active = false
    getAddressList().getMemoryRecordByID(6).Active = false

The converter extracts those sets purely statically — no Lua execution
anywhere in this path.  The supported grammar is deliberately narrow;
anything outside it (loops, dynamic IDs, mixed directions, duplicate or
unknown record IDs, record-ID manipulation outside a phase, self-reference,
missing phase sections, other receiver chains) fails closed, in which case
the caller keeps the record's ordinary Lua profile and no activation-set
metadata is attached.

Supported line forms (after stripping a trailing ``--`` comment):

- ``getMemoryRecordByID(<id>).Active = true|false``, optionally preceded by
  the canonical receiver ``getAddressList().``
- ``(local) <var> = getMemoryRecordByID(<id>)`` (optionally through the
  same receiver) followed later by ``<var>.Active = true|false``

A bound variable may be used once per phase; the same record ID may appear
in both phases (the normal toggle pair).  Direction is section-bound:
assignments in the ``[ENABLE]`` section must set ``true`` and assignments in
the ``[DISABLE]`` section must set ``false``.  Both sections must exist and
each must contain at least one assignment.  The call name matches
case-insensitively (tables spell it as both ``getMemoryRecordByID`` and
``getMemoryRecordById``); the ``.Active`` property, the ``true``/``false``
keywords, ``local`` and variable names match case-sensitively, and the
``[ENABLE]``/``[DISABLE]`` phase markers match case-insensitively.
"""

from __future__ import annotations

import re

#: Plan value identifying the source of an activation_sets field.
SOURCE_TAG = "lua-static-extract"

#: Upper bound of record IDs per direction (bounded plan metadata).
MAX_SET_SIZE = 256

_PHASE_ENABLE = re.compile(r"\[ENABLE\]\s*$", re.I)
_PHASE_DISABLE = re.compile(r"\[DISABLE\]\s*$", re.I)
_ANY_CALL = re.compile(r"getMemoryRecordByID", re.I)
_RECEIVER = r"(?:getAddressList\(\)\s*\.\s*)?"
_DIRECT = re.compile(
    _RECEIVER + r"getMemoryRecordByID\(\s*(\d+)\s*\)\s*\.Active\s*=\s*(true|false)$",
    re.I)
_BINDING = re.compile(
    r"(?:local\s+)?([A-Za-z_]\w*)\s*=\s*" + _RECEIVER +
    r"getMemoryRecordByID\(\s*(\d+)\s*\)\s*$", re.I)
_USE = re.compile(r"([A-Za-z_]\w*)\.Active\s*=\s*(true|false)$")


def extract_activation_sets(lua_source, known_ids, own_id=None):
    """Return ``{"enable": [...], "disable": [...], "source": SOURCE_TAG}``.

    ``lua_source`` is the record's full AssemblerScript text (the same
    normalized text stored in the plan's ``lua_program.source``).
    ``known_ids`` is the collection of record IDs present in the table.
    ``own_id`` is the calling record's own ID; a set that would contain it
    is refused.  Returns ``None`` whenever the embedded Lua does not match
    the narrow master-toggle grammar, so callers fall back to the record's
    ordinary Lua profile.
    """
    if not isinstance(lua_source, str) or not lua_source.strip():
        return None
    try:
        known = {int(value) for value in known_ids}
    except TypeError:
        return None
    if own_id is not None:
        known.discard(int(own_id))

    sets = {"enable": set(), "disable": set()}
    bindings = {}
    phase = None

    def add(record_id, flag):
        target = "enable" if flag == "true" else "disable"
        if (target != phase or record_id not in known
                or record_id in sets[target]
                or len(sets[target]) >= MAX_SET_SIZE):
            return False
        sets[target].add(record_id)
        return True

    lines = lua_source.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        if _PHASE_ENABLE.fullmatch(line):
            if phase is not None:
                return None
            phase = "enable"
            continue
        if _PHASE_DISABLE.fullmatch(line):
            if phase != "enable":
                return None
            phase = "disable"
            continue
        cut = line.split("--", 1)[0].strip() if "--" in line else line
        direct = _DIRECT.fullmatch(cut)
        if direct is not None:
            if phase is None:
                # Record-ID manipulation outside an explicit phase section.
                return None
            if not add(int(direct.group(1)), direct.group(2)):
                return None
            continue
        binding = _BINDING.fullmatch(cut)
        if binding is not None:
            if phase is None:
                return None
            variable, record_id = binding.group(1), int(binding.group(2))
            if variable in bindings and bindings[variable] != record_id:
                return None
            bindings[variable] = record_id
            continue
        use = _USE.fullmatch(cut)
        if use is not None:
            if phase is None:
                return None
            variable = use.group(1)
            if variable not in bindings:
                return None
            if not add(bindings[variable], use.group(2)):
                return None
            continue
        if not _ANY_CALL.search(line):
            # Free-form lines ({$lua} markers, engine calls, refreshes,
            # comments) are ignored as long as they contain no
            # getMemoryRecordByID and are not a bound-variable .Active use
            # (checked above, so bound toggles can never be missed).
            continue
        # A getMemoryRecordByID occurrence outside the narrow grammar.
        return None

    if phase != "disable" or not sets["enable"] or not sets["disable"]:
        return None
    return {"enable": sorted(sets["enable"]),
            "disable": sorted(sets["disable"]),
            "source": SOURCE_TAG}
