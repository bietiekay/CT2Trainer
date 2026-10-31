"""Contract: the committed converter/trainer icon assets are valid Windows
icons for the frozen EXEs.

0.20 ships user-provided artwork (the "Generator" icon for the CT2Trainer
tool, the "Standalone Trainer" icon for the generated trainer .exe) as the
committed multi-size ICOs plus 1024x1024 PNG masters; 0.21 adds the
"Master Trainer" icon for the Master Trainer window (MT-5). This test
pins the structure all consumers require: PyInstaller `--icon` (the
frozen EXE resource) and `tk.iconbitmap` (the runtime window icon) both
need the standard 16/24/32/48/64/128/256 px image set, 32 bpp; the PNG
masters are the rebuild source for `tools/create_icons.py`. Pure stdlib
parsing: the test needs no Pillow.
"""
from __future__ import annotations

import struct
import unittest
from pathlib import Path

from ct2trainer.native.window_icon import window_icon_path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "src" / "ct2trainer" / "assets"

ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def ico_entries(data: bytes):
    """(reserved, image_type, [(w, h, bitcount, size, offset), ...])."""
    reserved, image_type, count = struct.unpack_from("<HHH", data, 0)
    entries = []
    offset = 6
    for _ in range(count):
        width, height, _colors, _reserved, _planes, bitcount, size, data_offset = \
            struct.unpack_from("<BBBBHHII", data, offset)
        entries.append(((width or 256), (height or 256), bitcount, size, data_offset))
        offset += 16
    return reserved, image_type, entries


def png_dimensions(data: bytes) -> tuple[int, int]:
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError("not a PNG signature")
    if data[8:16] != struct.pack(">I4s", 13, b"IHDR"):
        raise AssertionError("first chunk is not IHDR")
    return struct.unpack_from(">II", data, 16)


class CommittedIconContractTests(unittest.TestCase):
    """Both shipped icons: the tool (converter) and the generated trainer."""

    def _assert_ico_contract(self, name: str, png_name: str) -> None:
        ico = ASSETS / (name + ".ico")
        self.assertTrue(ico.is_file(), f"missing icon asset {ico}")
        data = ico.read_bytes()
        reserved, image_type, entries = ico_entries(data)
        self.assertEqual((reserved, image_type), (0, 1), "not a 32-bit color ICO")
        self.assertEqual([w for w, _h, _b, _s, _o in entries], list(ICO_SIZES),
                         "ICO must carry the 16-256 px set in ascending order")
        self.assertEqual([h for _w, h, _b, _s, _o in entries], list(ICO_SIZES),
                         "ICO square image set")
        self.assertEqual([b for _w, _h, b, _s, _o in entries], [32] * len(ICO_SIZES),
                         "32 bpp on every image")
        total = 6 + 16 * len(entries) + sum(s for _w, _h, _b, s, _o in entries)
        self.assertEqual(total, len(data), "ICO image blobs do not tile the file")
        for _w, _h, _b, size, data_offset in entries:
            self.assertGreaterEqual(len(data) - data_offset, size,
                                    "truncated image blob")
        png = ASSETS / (png_name + ".png")
        self.assertTrue(png.is_file(), f"missing PNG master {png}")
        self.assertEqual(png_dimensions(png.read_bytes()), (1024, 1024),
                         "the committed PNG master must be the 1024x1024 rebuild source")

    def test_converter_icon_contract(self):
        self._assert_ico_contract("ct2trainer-converter", "ct2trainer-converter")

    def test_trainer_icon_contract(self):
        self._assert_ico_contract("ct2trainer-trainer", "ct2trainer-trainer")

    def test_master_icon_contract(self):
        # MT-5 (0.21): the user-provided Master Trainer icon ships with the
        # same multi-size / 32-bpp / 1024-PNG-master structure.
        self._assert_ico_contract("Master_Trainer", "Master_Trainer")

    def test_window_icon_paths_resolve_to_the_committed_assets(self):
        for kind in ("converter", "trainer", "master"):
            path = window_icon_path(kind)
            self.assertTrue(path.is_file(), f"window icon for {kind} is missing")
            self.assertEqual(path.parent, ASSETS,
                             "window icon must come from the committed assets directory")

    def test_unknown_icon_kind_is_refused(self):
        # "master" is a valid kind since MT-5 (0.21); only genuinely
        # unknown kinds are refused.
        with self.assertRaises(ValueError):
            window_icon_path("no-such-kind")


if __name__ == "__main__":
    unittest.main()
