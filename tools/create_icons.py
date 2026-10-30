"""Rebuild the CT2Trainer Windows icons from the committed PNG masters.

The committed reference PNGs (ct2trainer-converter.png, ct2trainer-trainer.png)
are the user-provided artwork masters (1024x1024, since 0.20). The multi-size
ICO files the frozen EXEs embed are derived from them by this script, so a
rebuild can never silently replace the shipped artwork.

Requires Pillow locally; it is not part of the offline build, and the
committed PNG and ICO files do not need it.
"""

from pathlib import Path
from PIL import Image


ROOT = Path(__file__).resolve().parents[1] / "src" / "ct2trainer" / "assets"


def rebuild(name: str) -> None:
    master = Image.open(ROOT / f"{name}.png")
    if master.mode != "RGBA":
        master = master.convert("RGBA")
    master.save(ROOT / f"{name}.ico", format="ICO",
                sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                       (64, 64), (128, 128), (256, 256)])


if __name__ == "__main__":
    rebuild("ct2trainer-converter")
    rebuild("ct2trainer-trainer")
