"""Synthetic fixture data for the AA rest-directives lane (lane-aa-directives).

Self-contained: no TableReferences, no real PE files, no target process.
Provides deterministic in-memory doubles for the five directive contracts
in ``src/ct2trainer/native/aa_directives.py``:

* a scripted thread backend (pending-poll counts, exit codes, spawn
  refusals, call trace);
* a scripted protection backend (static foreign region table, apply/release
  refusal sets, call traces);
* an in-memory held-image export backend built from synthetic PE bytes
  (independent implementation of the documented PE export layout, consumed
  by the read-only ``pe_exports`` resolver);
* a deterministic stub disassembler with injectable single defects;
* the section-structure source corpus used by the section-contract tests.
"""
from __future__ import annotations

import struct

from ct2trainer.native.aa_directives import (
    DisassemblerPort,
    ExportBackend,
    ForeignRegion,
    ProtectionBackend,
    ThreadBackend,
    ThreadPoll,
)


# ---------------------------------------------------------------------------
# Synthetic PE images (documented layout, own independent implementation)
# ---------------------------------------------------------------------------


def build_pe_image(exports, *, bitness=64, ordinal_base=1):
    """Build a synthetic mapped PE image with a named export table.

    ``exports`` maps ASCII export names to either an integer target RVA or
    a ``"module.export"`` / ``"module.#ordinal"`` forwarder string. The
    name pointer table is lexically sorted, as the PE format requires for
    the resolver's binary search. Layout: DOS header at 0, PE header at
    0x80, optional header at 0x98, export directory at 0x400 (40 bytes),
    address table at 0x450, name pointers at 0x500, ordinal table at 0x550,
    name strings from 0x600, forwarder strings from 0x750 (inside the
    export directory range so they are detected as forwarders).
    """
    if not exports:
        raise ValueError("at least one export is required")
    raw = bytearray(0x2000)
    raw[:2] = b"MZ"
    struct.pack_into("<I", raw, 0x3C, 0x80)
    raw[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", raw, 0x84, 0x8664 if bitness == 64 else 0x14C)
    optional = 0x98
    optional_size = 240 if bitness == 64 else 224
    struct.pack_into("<H", raw, 0x94, optional_size)
    struct.pack_into("<H", raw, optional, 0x20B if bitness == 64 else 0x10B)
    struct.pack_into("<I", raw, optional + 56, len(raw))
    count_offset = 108 if bitness == 64 else 92
    directory_offset = 112 if bitness == 64 else 96
    struct.pack_into("<I", raw, optional + count_offset, 16)
    struct.pack_into("<II", raw, optional + directory_offset, 0x400, 0x400)
    items = sorted(exports.items())
    struct.pack_into("<IIIIII", raw, 0x410, ordinal_base, len(items), len(items),
                     0x450, 0x500, 0x550)
    name_cursor = 0x600
    forward_cursor = 0x750
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
    return bytes(raw)


def fixture_images(bitness=64):
    """Standard fixture image table for the target-API tests."""
    return {
        "fixture.dll": (0x710000, build_pe_image(
            {"Alpha": 0x1100, "Zulu": 0x1200}, bitness=bitness, ordinal_base=7)),
        "second.dll": (0x930000, build_pe_image(
            {"Target": 0x1200}, bitness=bitness, ordinal_base=9)),
        "forwarder.dll": (0xA00000, build_pe_image(
            {"ByName": "second.Target", "ByOrdinal": "second.dll.#9"},
            bitness=bitness)),
    }


class HeldExportBackend(ExportBackend):
    """In-memory held-target images for the read-only pe_exports resolver.

    ``images`` maps a module base name (any case) to ``(base, raw_image)``.
    Every read is recorded in ``reads``; reads outside every held image
    raise, mirroring an out-of-process read refusal.
    """

    def __init__(self, images):
        self._images = {}
        for name, (base, raw) in images.items():
            key = name.casefold()
            if key in self._images:
                raise ValueError("duplicate fixture module: %r" % (name,))
            self._images[key] = (base, bytes(raw))
        self.reads = []

    def module(self, name):
        key = name.casefold()
        if key not in self._images:
            raise LookupError(
                "module %r is not uniquely held in the target" % (name,))
        base, raw = self._images[key]
        return base, len(raw)

    def read(self, address, size):
        self.reads.append((address, size))
        for key, (base, raw) in sorted(self._images.items()):
            if base <= address and address + size <= base + len(raw):
                return raw[address - base:address - base + size]
        raise LookupError("held image read outside any module: %#x+%d"
                          % (address, size))


class DriftingExportBackend(HeldExportBackend):
    """Reports a shifted module base after the first lookup (snapshot drift)."""

    def __init__(self, images, drift=0x10000):
        super().__init__(images)
        self._drift = drift
        self._lookups = {}

    def module(self, name):
        base, size = super().module(name)
        key = name.casefold()
        self._lookups[key] = self._lookups.get(key, 0) + 1
        if self._lookups[key] > 1:
            return base + self._drift, size
        return base, size


# ---------------------------------------------------------------------------
# Thread backend
# ---------------------------------------------------------------------------


class ScriptedThreadBackend(ThreadBackend):
    """Deterministic thread backend for plan-flow tests.

    ``pending_polls``: per spawned thread, how many polls report
    not-exited before the first exited poll. ``exit_codes`` may override
    the per-ordinal exit code. ``spawn_refusals`` is a set of ordinals
    whose spawn() raises. ``never_exit`` makes every poll pending
    (poll-bound tests). ``calls`` records ("spawn"|"poll", ordinal) in
    call order, so tests can pin the exact sequential backend flow.
    """

    def __init__(self, pending_polls=0, exit_code=0, spawn_refusals=(),
                 exit_codes=None, never_exit=False):
        self._pending_polls = pending_polls
        self._exit_code = exit_code
        self._spawn_refusals = set(spawn_refusals)
        self._exit_codes = dict(exit_codes or {})
        self._never_exit = never_exit
        self._remaining = {}
        self.calls = []

    def spawn(self, handle):
        self.calls.append(("spawn", handle.ordinal))
        if handle.ordinal in self._spawn_refusals:
            self._spawn_refusals.discard(handle.ordinal)  # one-shot refusal
            raise RuntimeError("backend refused spawn of thread %d"
                               % handle.ordinal)
        self._remaining[handle.ordinal] = self._pending_polls

    def poll(self, handle):
        self.calls.append(("poll", handle.ordinal))
        if self._never_exit:
            return ThreadPoll(exited=False)
        remaining = self._remaining.get(handle.ordinal)
        if remaining is None:
            raise RuntimeError("poll before spawn for thread %d"
                               % handle.ordinal)
        if remaining > 0:
            self._remaining[handle.ordinal] = remaining - 1
            return ThreadPoll(exited=False)
        return ThreadPoll(exited=True,
                          exit_code=self._exit_codes.get(handle.ordinal,
                                                         self._exit_code))


# ---------------------------------------------------------------------------
# Protection backend
# ---------------------------------------------------------------------------


class ScriptedProtectionBackend(ProtectionBackend):
    """Deterministic protection backend with a static foreign region table.

    ``foreign``: (base, size, owner) tuples. ``apply_refusals`` is a set of
    (base, size, page) and ``release_refusals`` a set of (base, size) that
    make the backend raise. All successful calls are recorded.
    """

    def __init__(self, foreign=(), *, apply_refusals=frozenset(),
                 release_refusals=frozenset(), address_limit=0x7FFFFFFFFFFF):
        self._foreign = tuple(ForeignRegion(base, size, owner)
                              for base, size, owner in foreign)
        self._apply_refusals = set(apply_refusals)
        self._release_refusals = set(release_refusals)
        self._limit = address_limit
        self.applies = []
        self.releases = []

    def foreign_regions(self, start, size):
        end = start + size
        return tuple(region for region in self._foreign
                     if region.base < end and start < region.base + region.size)

    def apply(self, base, size, page):
        if (base, size, page) in self._apply_refusals:
            raise RuntimeError("backend refused protect")
        if base <= 0 or size <= 0 or base + size - 1 > self._limit:
            raise RuntimeError("range outside held address space")
        self.applies.append((base, size, page))

    def release(self, base, size):
        if (base, size) in self._release_refusals:
            raise RuntimeError("backend refused unprotect")
        self.releases.append((base, size))


# ---------------------------------------------------------------------------
# Disassembler
# ---------------------------------------------------------------------------


class StubDisassembler(DisassemblerPort):
    """Deterministic stub disassembler.

    Emits ``instruction_size``-byte "nop" instructions, gapless and
    address-ordered. ``defect`` injects exactly one contract violation for
    negative tests: 'gap' | 'reordered' | 'short' | 'long' | 'zero_size' |
    'bad_mnemonic'. ``calls`` records (address, count, bitness) in call
    order.
    """

    def __init__(self, instruction_size=5, defect=None, mnemonic="nop"):
        if type(instruction_size) is not int or not 1 <= instruction_size <= 15:
            raise ValueError("stub instruction size must be 1..15")
        allowed = (None, "gap", "reordered", "short", "long",
                   "zero_size", "bad_mnemonic")
        if defect not in allowed:
            raise ValueError("unknown stub defect: %r" % (defect,))
        self._size = instruction_size
        self._defect = defect
        self._mnemonic = mnemonic
        self.calls = []

    def disassemble(self, address, count, bitness):
        self.calls.append((address, count, bitness))
        items = [{"address": address + index * self._size,
                  "size": self._size,
                  "mnemonic": self._mnemonic}
                 for index in range(count)]
        if self._defect == "gap" and count >= 2:
            items[1]["address"] += 1
        elif self._defect == "reordered" and count >= 2:
            items[0], items[1] = items[1], items[0]
        elif self._defect == "short":
            items = items[:-1]
        elif self._defect == "long":
            items.append({"address": address + count * self._size,
                          "size": self._size,
                          "mnemonic": self._mnemonic})
        elif self._defect == "zero_size" and items:
            items[0]["size"] = 0
        elif self._defect == "bad_mnemonic" and items:
            items[0]["mnemonic"] = ""
        return items


# ---------------------------------------------------------------------------
# Section-structure source corpus
# ---------------------------------------------------------------------------

SECTION_SOURCES = {
    # The dedicated edge cases of the lane brief.
    "eof_after_enable": "[ENABLE]",
    "empty_enable": "[ENABLE]\n[DISABLE]\nassert(1000,01)\n1000:\ndb 00",
    "disable_without_enable": "[DISABLE]\nassert(1000,01)\n1000:\ndb 00",
    "missing_disable": "[ENABLE]\nassert(1000,00)\n1000:\ndb 01",
    "empty_disable": "[ENABLE]\nassert(1000,00)\n1000:\ndb 01\n[DISABLE]",
    # Supporting structural cases.
    "complete": "[ENABLE]\nassert(1000,00)\n1000:\ndb 01\n[DISABLE]\n"
                "assert(1000,01)\n1000:\ndb 00",
    "both_empty": "[ENABLE]\n[DISABLE]",
    "missing_disable_with_preamble":
        "define(Anchor,1000)\n[ENABLE]\nassert(Anchor,00)\nAnchor:\ndb 01",
    "no_markers": "assert(1000,00)\n1000:\ndb 01",
    "duplicate_enable": "[ENABLE]\nassert(1000,00)\n1000:\ndb 01\n[ENABLE]\n"
                       "[DISABLE]\nassert(1000,01)\n1000:\ndb 00",
    "disable_before_enable": "[DISABLE]\nassert(1000,01)\n1000:\ndb 00\n"
                             "[ENABLE]\nassert(1000,00)\n1000:\ndb 01",
    "symbol_only_empty_disable":
        "[ENABLE]\ndefine(Anchor,1000)\nregistersymbol(Anchor)\n[DISABLE]\n"
        "unregistersymbol(Anchor)",
}
