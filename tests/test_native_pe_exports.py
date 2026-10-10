"""Bounded remote PE export parsing and owned Win32 forwarded exports."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import struct
import sys
import unittest

from ct2trainer.native.memory import ProcessMemory, ProcessMemoryError
from ct2trainer.native.pe_exports import ExportResolutionError, resolve_remote_export


def _image(exports, *, bitness=64, ordinal_base=1):
    """Independently authored mapped-image fixture, with lexically sorted names."""
    raw = bytearray(0x2000)
    raw[:2] = b"MZ"
    struct.pack_into("<I", raw, 0x3C, 0x80)
    raw[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", raw, 0x84, 0x8664 if bitness == 64 else 0x14C)
    struct.pack_into("<H", raw, 0x94, 240 if bitness == 64 else 224)
    optional = 0x98
    struct.pack_into("<H", raw, optional, 0x20B if bitness == 64 else 0x10B)
    struct.pack_into("<I", raw, optional + 56, len(raw))
    struct.pack_into("<I", raw, optional + (108 if bitness == 64 else 92), 16)
    struct.pack_into("<II", raw, optional + (112 if bitness == 64 else 96), 0x400, 0x400)
    items = sorted(exports.items())
    struct.pack_into("<IIIIII", raw, 0x410, ordinal_base, len(items), len(items),
                     0x450, 0x500, 0x550)
    name_cursor, forward_cursor = 0x600, 0x750
    for index, (name, target) in enumerate(items):
        name_bytes = name.encode("ascii") + b"\0"
        raw[name_cursor:name_cursor + len(name_bytes)] = name_bytes
        struct.pack_into("<I", raw, 0x500 + index * 4, name_cursor)
        struct.pack_into("<H", raw, 0x550 + index * 2, index)
        name_cursor += len(name_bytes)
        if isinstance(target, str):
            encoded = target.encode("ascii") + b"\0"
            raw[forward_cursor:forward_cursor + len(encoded)] = encoded
            address = forward_cursor
            forward_cursor += len(encoded)
        else:
            address = target
        struct.pack_into("<I", raw, 0x450 + index * 4, address)
    return raw


class _Remote:
    def __init__(self, images):
        self.images = {name.casefold(): (base, raw) for name, (base, raw) in images.items()}
        self.reads = []

    def module(self, name):
        base, raw = self.images[name.casefold()]
        return base, len(raw)

    def read(self, address, size):
        self.reads.append((address, size))
        for base, raw in self.images.values():
            if base <= address and address + size <= base + len(raw):
                return bytes(raw[address - base:address - base + size])
        raise AssertionError("Out-of-image read must be rejected before backend access")

    def resolve(self, module, export):
        return resolve_remote_export(self.read, self.module, module, export)


class RemoteExportsTests(unittest.TestCase):
    def test_x86_x64_exact_names_and_ordinals_use_held_remote_bases(self):
        for bitness in (32, 64):
            remote = _Remote({"fixture.dll": (0x710000, _image({"Alpha": 0x1100, "Zulu": 0x1200},
                                                              bitness=bitness, ordinal_base=7))})
            self.assertEqual(remote.resolve("FIXTURE", "Alpha"), 0x711100)
            self.assertEqual(remote.resolve("fixture.dll", "#8"), 0x711200)
            with self.assertRaisesRegex(ExportResolutionError, "not found"):
                remote.resolve("fixture", "alpha")
            with self.assertRaisesRegex(ExportResolutionError, "outside"):
                remote.resolve("fixture", "#6")

    def test_forwarded_names_and_ordinals_follow_actual_target_modules(self):
        remote = _Remote({
            "first.dll": (0x710000, _image({"ByName": "second.Target", "ByOrdinal": "second.dll.#9"})),
            "second.dll": (0x930000, _image({"Target": 0x1200}, ordinal_base=9)),
        })
        self.assertEqual(remote.resolve("first", "ByName"), 0x931200)
        self.assertEqual(remote.resolve("first", "ByOrdinal"), 0x931200)
        self.assertTrue(any(0x930000 <= address < 0x932000 for address, _ in remote.reads))

    def test_unmapped_api_set_forwarder_is_explicit_gap_without_local_substitution(self):
        remote = _Remote({"fixture.dll": (0x710000, _image({"Target": "api-ms-win-core-test-l1-1-0.Target"}))})
        with self.assertRaisesRegex(ExportResolutionError, "held-target schema"):
            remote.resolve("fixture", "Target")

    def test_forwarder_cycle_and_missing_module_are_rejected(self):
        remote = _Remote({"a.dll": (0x710000, _image({"Target": "b.Target"})),
                          "b.dll": (0x930000, _image({"Target": "a.Target"}))})
        with self.assertRaisesRegex(ExportResolutionError, "cycle"):
            remote.resolve("a", "Target")
        remote = _Remote({"a.dll": (0x710000, _image({"Target": "missing.Target"}))})
        with self.assertRaisesRegex(ExportResolutionError, "not uniquely loaded"):
            remote.resolve("a", "Target")

    def test_invalid_image_headers_counts_rvas_and_holes_are_rejected_before_oob_read(self):
        mutations = [
            lambda raw: raw.__setitem__(slice(0, 2), b"XX"),
            lambda raw: struct.pack_into("<I", raw, 0x3C, 0xFFFFFFF0),
            lambda raw: struct.pack_into("<H", raw, 0x94, 1),
            lambda raw: struct.pack_into("<I", raw, 0x98 + 56, 0x3000),
            lambda raw: struct.pack_into("<I", raw, 0x98 + 108, 0),
            lambda raw: struct.pack_into("<II", raw, 0x98 + 112, 0x1FF0, 40),
            lambda raw: struct.pack_into("<I", raw, 0x414, 0xFFFFFFFF),
            lambda raw: struct.pack_into("<I", raw, 0x41C, 0x1FFF),
            lambda raw: struct.pack_into("<I", raw, 0x500, 0x3000),
            lambda raw: struct.pack_into("<H", raw, 0x550, 7),
            lambda raw: struct.pack_into("<I", raw, 0x450, 0),
            lambda raw: struct.pack_into("<I", raw, 0x450, 0x3000),
        ]
        for mutation in mutations:
            raw = _image({"Target": 0x1200})
            mutation(raw)
            remote = _Remote({"fixture.dll": (0x710000, raw)})
            with self.subTest(mutation=mutation), self.assertRaises(ExportResolutionError):
                remote.resolve("fixture", "Target")

    def test_forwarder_string_must_terminate_inside_export_directory(self):
        raw = _image({"Target": 0x7FE})
        raw[0x7FE:0x800] = b"AA"
        remote = _Remote({"fixture.dll": (0x710000, raw)})
        with self.assertRaisesRegex(ExportResolutionError, "unterminated"):
            remote.resolve("fixture", "Target")

    def test_export_name_metadata_and_module_snapshot_are_rechecked_before_return(self):
        remote = _Remote({"fixture.dll": (0x710000, _image({"Target": 0x1200}))})
        original = remote.read
        reads = 0
        def changing_read(address, size):
            nonlocal reads
            if address == 0x710000:
                reads += 1
                if reads == 2:
                    remote.images["fixture.dll"][1][0x10] ^= 1
            return original(address, size)
        with self.assertRaisesRegex(ExportResolutionError, "metadata changed"):
            resolve_remote_export(changing_read, remote.module, "fixture", "Target")
        calls = 0
        def changing_module(name):
            nonlocal calls
            calls += 1
            base, size = remote.module(name)
            return base + (0x10000 if calls > 1 else 0), size
        with self.assertRaisesRegex(ExportResolutionError, "module changed"):
            resolve_remote_export(remote.read, changing_module, "fixture", "Target")

    def test_invalid_inputs_cannot_trigger_remote_reads(self):
        remote = _Remote({"fixture.dll": (0x710000, _image({"Target": 0x1200}))})
        for module, name in (("../fixture", "Target"), ("fixture", "#999999999999"),
                             ("fixture", "\0"), ("fixture", "X" * 1025)):
            with self.subTest(module=module, name=name), self.assertRaises(ExportResolutionError):
                remote.resolve(module, name)
        self.assertEqual(remote.reads, [])


@unittest.skipUnless(sys.platform == "win32", "owned held-process PE export verification")
class OwnedWindowsExportsTests(unittest.TestCase):
    def test_real_kernel32_forwarders_and_user32_exports_resolve_in_owned_process(self):
        # Local loading is only fixture setup: the parser still reads held target
        # images. GetProcAddress addresses are used solely as a test oracle.
        kernel = ctypes.WinDLL("kernel32")
        user = ctypes.WinDLL("user32")
        memory = ProcessMemory(Path(sys.executable).name, os.getpid())
        self.addCleanup(memory.close)
        for module, library, name in (("kernel32", kernel, "GetCurrentProcessId"),
                                      ("kernel32", kernel, "GetTickCount64"),
                                      ("user32", user, "GetAsyncKeyState"),
                                      ("user32", user, "GetForegroundWindow")):
            with self.subTest(module=module, name=name):
                resolved = memory.resolve_export(module, name)
                self.assertEqual(resolved, ctypes.cast(getattr(library, name), ctypes.c_void_p).value)
        address = memory.resolve_export("kernel32", "GetCurrentProcessId")
        self.assertEqual(ctypes.WINFUNCTYPE(wintypes.DWORD)(address)(), os.getpid())
        # On this Windows host GetProcAddress intercepts this one name through
        # apphelp.dll, while the target EAT names the original user32 code.
        # Our contract is the held remote EAT, not local loader shim semantics.
        address = memory.resolve_export("user32", "GetWindowThreadProcessId")
        base, size = memory.module("user32.dll")
        self.assertTrue(base <= address < base + size)
        get_id = ctypes.WINFUNCTYPE(wintypes.DWORD, wintypes.HWND,
                                    ctypes.POINTER(wintypes.DWORD))(address)
        process = wintypes.DWORD()
        self.assertEqual(get_id(None, ctypes.byref(process)), 0)
        with self.assertRaisesRegex(ProcessMemoryError, "not found"):
            memory.resolve_export("kernel32", "DefinitelyMissingCT2TrainerExport")


if __name__ == "__main__":
    unittest.main()
