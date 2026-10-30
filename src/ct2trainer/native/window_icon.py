"""Resolve the CT2Trainer window icons for the frozen EXEs.

The frozen converter/trainer carries both icons under
<ct2trainer>/assets (PyInstaller --add-data layout); in source mode the
repository assets are used directly.
"""
from __future__ import annotations
from pathlib import Path
import sys

_ASSETS = Path(__file__).resolve().parents[1] / "assets"

_ICON_NAMES = {
    "converter": "ct2trainer-converter.ico",
    "trainer": "ct2trainer-trainer.ico",
    # MT-5 (Master Trainer): user-provided master icon (CONCEPT.md).
    "master": "Master_Trainer.ico",
}


def window_icon_path(kind: str) -> Path:
    """One exact shipped icon: 'converter' (the CT2Trainer tool),
    'trainer' (the standalone trainer .exe the tool generates) or
    'master' (the Master Trainer window)."""
    if kind not in _ICON_NAMES:
        raise ValueError("Unknown window icon: " + kind)
    name = _ICON_NAMES[kind]
    if not getattr(sys, "frozen", False):
        return _ASSETS / name
    base = Path(getattr(sys, "_MEIPASS", _ASSETS.parent))
    return base / "ct2trainer" / "assets" / name
