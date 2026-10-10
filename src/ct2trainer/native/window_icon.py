"""Resolve the CT2Trainer window icons for the frozen EXEs.

The frozen converter/trainer carries both icons under
<ct2trainer>/assets (PyInstaller --add-data layout); in source mode the
repository assets are used directly.
"""
from __future__ import annotations
from pathlib import Path
import sys

_ASSETS = Path(__file__).resolve().parents[1] / "assets"


def window_icon_path(kind: str) -> Path:
    """One exact legacy icon: 'converter' or 'trainer'."""
    if kind not in ("converter", "trainer"):
        raise ValueError("Unknown window icon: " + kind)
    name = "ct2trainer-" + kind + ".ico"
    if not getattr(sys, "frozen", False):
        return _ASSETS / name
    base = Path(getattr(sys, "_MEIPASS", _ASSETS.parent))
    return base / "ct2trainer" / "assets" / name
