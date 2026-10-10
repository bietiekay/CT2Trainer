"""Suggest the target EXE from a CT file.

Mirrors the legacy converter heuristic: a CT often spells out the module
filename in addresses or AA code. A single distinct EXE is a suggestion,
never proof; the user can always override it.
"""
from __future__ import annotations
import re

_EXE_TOKEN = re.compile(rb"[A-Za-z0-9_.-]+\.exe\b", re.IGNORECASE)


def find_candidates(data: bytes) -> list[str]:
    """Distinct .exe tokens in first-seen order (case-insensitive identity)."""
    seen: dict[str, str] = {}
    for match in _EXE_TOKEN.findall(data):
        name = match.decode("ascii")
        seen.setdefault(name.casefold(), name)
    return list(seen.values())


def suggest_process_name(data: bytes) -> str | None:
    """Exactly one distinct EXE name is suggested; zero or many stay empty."""
    candidates = find_candidates(data)
    return candidates[0] if len(candidates) == 1 else None


def resolve_process(explicit: str | None, data: bytes) -> tuple[str, str]:
    """CLI/GUI resolution: an explicit name always wins (still validated
    later by the compiler); otherwise a single CT candidate fills the field.

    Returns (process_name, source) with source 'explicit' or 'ct-suggestion'.
    Raises ValueError with the visible candidates when no safe fill exists.
    """
    if explicit:
        return explicit, "explicit"
    candidates = find_candidates(data)
    if len(candidates) == 1:
        return candidates[0], "ct-suggestion"
    if candidates:
        raise ValueError(
            "The CT contains multiple distinct EXE names; choose the target explicitly: "
            + ", ".join(candidates))
    raise ValueError("No target EXE given and the CT contains no .exe name to suggest")
