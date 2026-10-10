"""Resolve exports in held remote PE images using documented PE metadata.

All reads are against the target, including forwarded modules. No address from
local GetProcAddress/LoadLibrary is substituted, and no module is remotely loaded.
Unmapped API-set contracts are explicit compatibility gaps until a held-target
API-set schema resolver is implemented and verified.

Format specification: https://learn.microsoft.com/windows/win32/debug/pe-format
"""
from __future__ import annotations

from collections.abc import Callable
import re
import struct


MAX_EXPORTS = 65536
MAX_EXPORT_NAME = 1024
MAX_FORWARD_DEPTH = 16
MAX_EXPORT_READ_BYTES = 8 * 1024 * 1024
MAX_EXPORT_READS = 4096
MAX_IMAGE_SIZE = 1024 * 1024 * 1024


class ExportResolutionError(ValueError):
    """The exact remote export cannot be verified without guessing."""


def _module_name(value: str) -> str:
    if (not isinstance(value, str) or not value or len(value) > 255
            or value != value.strip() or any(ord(c) < 32 or c in '\\/:<>|?*"' for c in value)
            or value in {".", ".."}):
        raise ExportResolutionError("An exact remote module base name is required.")
    return value if "." in value else value + ".dll"


def _export_name(value: str) -> str:
    if (not isinstance(value, str) or not 1 <= len(value) <= MAX_EXPORT_NAME
            or any(not 32 <= ord(character) < 127 for character in value)):
        raise ExportResolutionError("Export names must be bounded exact ASCII names or #decimal ordinals.")
    if value.startswith("#") and (not re.fullmatch(r"#[0-9]{1,10}", value)
                                 or int(value[1:]) > 0xFFFFFFFF):
        raise ExportResolutionError("Invalid remote export ordinal.")
    return value


class _Resolver:
    def __init__(self, read: Callable[[int, int], bytes],
                 module: Callable[[str], tuple[int, int]]):
        self.read = read
        self.module = module
        self.snapshots: dict[str, tuple[int, int]] = {}
        self.observations: list[tuple[int, bytes]] = []
        self.read_bytes = 0

    def observe(self, address: int, size: int) -> bytes:
        if (type(size) is not int or not 0 < size <= MAX_EXPORT_READ_BYTES
                or self.read_bytes + size > MAX_EXPORT_READ_BYTES
                or len(self.observations) >= MAX_EXPORT_READS):
            raise ExportResolutionError("Remote export metadata exceeded its bounded read budget.")
        raw = self.read(address, size)
        if not isinstance(raw, bytes) or len(raw) != size:
            raise ExportResolutionError("Remote export metadata read was incomplete.")
        self.observations.append((address, raw))
        self.read_bytes += size
        return raw

    def resolve(self, module_name: str, export_name: str,
                path: set[tuple[str, str]]) -> int:
        module_name, export_name = _module_name(module_name), _export_name(export_name)
        key = module_name.casefold(), export_name
        if key in path or len(path) >= MAX_FORWARD_DEPTH:
            raise ExportResolutionError("Remote export forwarding contains a cycle or exceeds its depth bound.")
        path = path | {key}
        try:
            base, size = self.module(module_name)
        except Exception as exc:
            if module_name.lower().startswith(("api-", "ext-")):
                raise ExportResolutionError(
                    "The target API-set contract is not a loaded module; held-target schema mapping is required.") from exc
            raise ExportResolutionError(f"Forwarded/exact module {module_name} is not uniquely loaded in the target.") from exc
        if (type(base) is not int or type(size) is not int or not 0 < base <= 0x7FFFFFFFFFFF
                or not 64 <= size <= MAX_IMAGE_SIZE or size - 1 > 0x7FFFFFFFFFFF - base):
            raise ExportResolutionError("Invalid remote PE image range.")
        previous = self.snapshots.setdefault(module_name, (base, size))
        if previous != (base, size):
            raise ExportResolutionError("The remote module changed while resolving its exports.")

        def read_rva(rva: int, length: int) -> bytes:
            if type(rva) is not int or type(length) is not int or not 0 <= rva < size or not 0 < length <= size - rva:
                raise ExportResolutionError("Remote PE metadata RVA is outside its held module image.")
            return self.observe(base + rva, length)

        def cstring(rva: int, upper: int = size) -> str:
            if not 0 < rva < upper <= size:
                raise ExportResolutionError("Remote PE string RVA is outside its allowed directory.")
            content = bytearray()
            while len(content) <= MAX_EXPORT_NAME:
                count = min(64, MAX_EXPORT_NAME + 1 - len(content), upper - rva - len(content))
                if not count:
                    break
                chunk = read_rva(rva + len(content), count)
                terminator = chunk.find(b"\x00")
                if terminator >= 0:
                    content.extend(chunk[:terminator])
                    if not content or len(content) > MAX_EXPORT_NAME:
                        raise ExportResolutionError("Remote PE export string is empty or oversized.")
                    try:
                        result = content.decode("ascii")
                    except UnicodeDecodeError as exc:
                        raise ExportResolutionError("Remote PE export string is not ASCII.") from exc
                    return _export_name(result)
                content.extend(chunk)
            raise ExportResolutionError("Remote PE export string is unterminated within its bound.")

        dos = read_rva(0, 64)
        if dos[:2] != b"MZ":
            raise ExportResolutionError("Remote image has no DOS signature.")
        pe_offset = struct.unpack_from("<I", dos, 0x3C)[0]
        if not 64 <= pe_offset <= min(size - 24, 1024 * 1024):
            raise ExportResolutionError("Remote PE header offset is invalid or oversized.")
        pe = read_rva(pe_offset, 24)
        if pe[:4] != b"PE\x00\x00":
            raise ExportResolutionError("Remote image has no PE signature.")
        machine = struct.unpack_from("<H", pe, 4)[0]
        optional_size = struct.unpack_from("<H", pe, 20)[0]
        if not 104 <= optional_size <= 4096:
            raise ExportResolutionError("Remote PE optional header size is unsupported.")
        optional = read_rva(pe_offset + 24, optional_size)
        magic = struct.unpack_from("<H", optional)[0]
        if magic == 0x10B and machine == 0x14C:
            count_offset, directory_offset = 92, 96
        elif magic == 0x20B and machine == 0x8664:
            count_offset, directory_offset = 108, 112
        else:
            raise ExportResolutionError("Only consistent x86 PE32 or x64 PE32+ remote exports are supported.")
        if len(optional) < directory_offset + 8:
            raise ExportResolutionError("Remote optional header lacks the export directory.")
        image_size = struct.unpack_from("<I", optional, 56)[0]
        if image_size != size:
            raise ExportResolutionError("Remote PE SizeOfImage differs from the held module snapshot.")
        directories = struct.unpack_from("<I", optional, count_offset)[0]
        if directories < 1:
            raise ExportResolutionError("Remote PE image has no export directory.")
        export_rva, export_size = struct.unpack_from("<II", optional, directory_offset)
        if not export_rva or not 40 <= export_size <= size - export_rva:
            raise ExportResolutionError("Remote export directory range is invalid or absent.")
        directory = read_rva(export_rva, 40)
        ordinal_base, functions, names, function_rva, names_rva, ordinal_rva = struct.unpack_from("<IIIIII", directory, 16)
        if not 1 <= functions <= MAX_EXPORTS or not 0 <= names <= MAX_EXPORTS:
            raise ExportResolutionError("Remote export table counts exceed their bounds.")
        if not function_rva:
            raise ExportResolutionError("Remote export address table is absent.")
        addresses = read_rva(function_rva, functions * 4)
        if export_name.startswith("#"):
            index = int(export_name[1:]) - ordinal_base
            if not 0 <= index < functions:
                raise ExportResolutionError("Remote export ordinal is outside the address table.")
        else:
            if not names or not names_rva or not ordinal_rva:
                raise ExportResolutionError(f"Remote export {export_name} is not named in this image.")
            pointers = read_rva(names_rva, names * 4)
            ordinals = read_rva(ordinal_rva, names * 2)
            lower, upper, match = 0, names, None
            # The documented name pointer table is lexically sorted; use its
            # bounded binary search, not an unbounded scan through remote data.
            while lower < upper:
                position = (lower + upper) // 2
                name = cstring(struct.unpack_from("<I", pointers, position * 4)[0])
                if name == export_name:
                    match = position
                    break
                if name < export_name:
                    lower = position + 1
                else:
                    upper = position
            if match is None:
                raise ExportResolutionError(f"Exact remote export {export_name} was not found.")
            for neighbor in (match - 1, match + 1):
                if 0 <= neighbor < names and cstring(struct.unpack_from("<I", pointers, neighbor * 4)[0]) == export_name:
                    raise ExportResolutionError("The exact remote export name is ambiguous.")
            index = struct.unpack_from("<H", ordinals, match * 2)[0]
            if index >= functions:
                raise ExportResolutionError("Remote export ordinal index exceeds its address table.")
        address_rva = struct.unpack_from("<I", addresses, index * 4)[0]
        if not 0 < address_rva < size:
            raise ExportResolutionError("Remote export is an absent slot or has an out-of-image RVA.")
        if export_rva <= address_rva < export_rva + export_size:
            forwarder = cstring(address_rva, export_rva + export_size)
            forwarded_module, separator, forwarded_export = forwarder.rpartition(".")
            if not separator or not forwarded_module or not forwarded_export:
                raise ExportResolutionError("Remote export forwarder has no exact module/export pair.")
            return self.resolve(forwarded_module, forwarded_export, path)
        return base + address_rva

    def verify(self) -> None:
        for name, expected in self.snapshots.items():
            if self.module(name) != expected:
                raise ExportResolutionError("A remote module changed before export resolution completed.")
        for address, expected in self.observations:
            if self.read(address, len(expected)) != expected:
                raise ExportResolutionError("Remote export metadata changed during resolution.")


def resolve_remote_export(read: Callable[[int, int], bytes],
                          module: Callable[[str], tuple[int, int]],
                          module_name: str, export_name: str) -> int:
    """Read and recheck exact held-target PE exports and bounded forwarders."""
    resolver = _Resolver(read, module)
    address = resolver.resolve(module_name, export_name, set())
    resolver.verify()
    return address
