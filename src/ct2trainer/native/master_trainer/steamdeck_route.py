"""SteamOS / CheatDeck target-route surface for the Master Trainer (MT-7).

This module is the *documented-route surface* only — deliberately NOT a
Linux attach backend. The engine attach backend is platform-specific to
Windows (as in the rest of CT2Trainer); on a Steam Deck / SteamOS the
supported route is the **Proton-wrapped standalone CT2Trainer Windows
trainer EXE** (CheatDeck-compatible). The Linux/SteamOS Master Trainer
runs detection + table index + waiting UI only, and any attempt to run the
engine attach there is refused fail-closed with the named
:class:`DeckAttachUnavailableError` — no silent fallback to a non-owned
attach path.

The owned Linux attach backend (and the real Deck protocol run with exact
build hashes, ``tests/deck/compatibility-matrix.md``) remain later work
items for root/user field work.

Pure standard library; this module imports cleanly on Linux and carries no
Windows-specific API surface anywhere.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass

#: The documented SteamOS / Steam Deck route text. It is the single source
#: of truth for the refusal detail, the named error message and the UI
#: status-line hint, so every surface states the same bounded deviation.
STEAMDECK_ROUTE_TEXT = (
    "Engine attach is not available on this platform (fail-closed, no "
    "silent fallback). On a Steam Deck / SteamOS the supported route is "
    "the Proton-wrapped standalone CT2Trainer Windows trainer EXE "
    "(CheatDeck-compatible). The Linux/SteamOS Master Trainer runs "
    "detection, table index and waiting UI only; an owned Linux attach "
    "backend remains a later work item.")

WINDOWS_ROUTE_TEXT = (
    "Engine attach available: the native Windows engine "
    "(the unchanged standalone-trainer path).")


@dataclass(frozen=True)
class AttachRoute:
    """The attach-route decision for one platform."""

    platform: str          # "windows" | "linux" | "other"
    attach_available: bool
    route_name: str        # "native-windows-engine" | "steamdeck-proton-wrapped"
    detail: str            # human-readable, displayable


class DeckAttachUnavailableError(ValueError):
    """A non-Windows platform attempted an engine attach (fail-closed).

    The message carries the documented bounded deviation
    (:data:`STEAMDECK_ROUTE_TEXT`); the ``route`` attribute carries the
    full decision for programmatic use.
    """

    def __init__(self, route: AttachRoute):
        super().__init__(STEAMDECK_ROUTE_TEXT)
        self.route = route


def detect_platform() -> str:
    """The runtime platform as ``"windows" | "linux" | "other"``.

    Mirrors the sys.platform spelling used by
    :mod:`ct2trainer.native.master_trainer.process_watch`
    (``"win32"`` -> windows, ``linux*`` -> linux).
    """
    if sys.platform == "win32":
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    return "other"


def _resolve_platform(platform: str | None) -> str:
    """Normalize a caller-supplied platform; ``None`` means the host."""
    if platform is None:
        return detect_platform()
    name = str(platform).strip().lower()
    if name in ("windows", "win32"):
        return "windows"
    if name == "linux":
        return "linux"
    return "other"


def attach_gate(platform: str | None = None) -> AttachRoute:
    """The attach-route decision; never raises for platform inputs.

    ``platform`` ``None`` uses :func:`detect_platform`; an explicit value
    makes the decision testable without touching platform globals.
    Windows -> attach available through the existing engine path
    (behavior unchanged); Linux/anything else -> attach unavailable
    through the documented SteamOS route.
    """
    plat = _resolve_platform(platform)
    if plat == "windows":
        return AttachRoute("windows", True, "native-windows-engine",
                           WINDOWS_ROUTE_TEXT)
    return AttachRoute(plat, False, "steamdeck-proton-wrapped",
                       STEAMDECK_ROUTE_TEXT)


def require_engine_attach(platform: str | None = None) -> AttachRoute:
    """Attach gate that fails closed on non-Windows platforms.

    Returns the :class:`AttachRoute` on Windows; raises
    :class:`DeckAttachUnavailableError` (carrying the documented route
    text) everywhere else.
    """
    route = attach_gate(platform)
    if not route.attach_available:
        raise DeckAttachUnavailableError(route)
    return route


def route_text(platform: str | None = None) -> str:
    """Displayable route/refusal text for the UI status line.

    On non-Windows platforms this is the permanent hint shown by the
    waiting view; on Windows it names the available native path.
    """
    route = attach_gate(platform)
    if route.attach_available:
        return WINDOWS_ROUTE_TEXT
    return STEAMDECK_ROUTE_TEXT
