"""Static canonical profile for explicitly requested read-only Lua helpers.

Preparation does not execute source or establish that its top-level calls are
supported. A private activation installs the source under the host's read-only
gate; a failed installation cancels that activation. No automatic table load.
"""
from __future__ import annotations

import hashlib


SCHEMA = "ct2trainer-lua-bootstrap/v1"
PROFILE = "activation-read-only/v1"
MAX_SOURCE_BYTES = 1024 * 1024


class LuaBootstrapError(ValueError):
    """Malformed, oversized, changed, or unsupported bootstrap profile."""


def prepare_lua_bootstrap(source: str) -> dict:
    if type(source) is not str:
        raise LuaBootstrapError("Lua bootstrap source must be text")
    try:
        raw = source.encode("utf-8")
    except UnicodeError as exc:
        raise LuaBootstrapError("Lua bootstrap source must be valid UTF-8 text") from exc
    if len(raw) > MAX_SOURCE_BYTES:
        raise LuaBootstrapError("Lua bootstrap source exceeds its 1 MiB bound")
    return {"schema": SCHEMA, "profile": PROFILE, "source": source,
            "source_sha256": hashlib.sha256(raw).hexdigest()}


def validate_lua_bootstrap(profile: dict) -> dict:
    if (type(profile) is not dict or set(profile) != {"schema", "profile", "source", "source_sha256"}
            or any(type(value) is not str for value in profile.values())
            or profile["schema"] != SCHEMA or profile["profile"] != PROFILE):
        raise LuaBootstrapError("Unknown or malformed Lua bootstrap profile")
    canonical = prepare_lua_bootstrap(profile["source"])
    if profile != canonical:
        raise LuaBootstrapError("Lua bootstrap source or hash differs from its canonical profile")
    return canonical
