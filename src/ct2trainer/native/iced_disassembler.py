"""Owned real-disassembler backend for the ``DisassemblerPort`` contract.

Implements the read-only ``disassemble(address, count, bitness)`` operation
on top of the pinned iced-x86 decoder (``iced-x86==1.21.0``, vendored under
``dependencies/native/iced-x86`` and bundled by ``tools/native_build.py``).
The port is stateless: it receives a ``read_bytes(address, size) -> bytes``
callable bound to one target memory and returns exactly the contract shape
``[{"address", "size", "mnemonic"}, ...]`` — gapless, address-ordered,
exactly ``count`` items, bounded printable-ASCII mnemonics.

Fail-closed: an invalid instruction, a short or failing read, or an
out-of-bounds address/count raises :class:`DisassemblerError` with a visible
named reason; nothing is ever partially returned.
"""
from __future__ import annotations

import iced_x86

from .aa_directives import (ADDRESS_LIMIT_32, ADDRESS_LIMIT_64,
                            DisassemblerError, DisassemblerPort,
                            MAX_DISASSEMBLE_COUNT, MAX_INSTRUCTION_BYTES,
                            MAX_MNEMONIC_CHARS)

#: x86/x64 instruction length bound (bytes) used to size one bounded read.
MAX_INSTRUCTION_LENGTH = MAX_INSTRUCTION_BYTES


def _mnemonic(instruction) -> str:
    """First token of the iced formatter output; bounded printable ASCII."""
    text = str(instruction)
    first = text.split(None, 1)[0] if text else ""
    if (not first or len(first) > MAX_MNEMONIC_CHARS
            or any(32 > ord(char) or char > "~" for char in first)):
        raise DisassemblerError(
            "disassembler produced an out-of-bounds mnemonic: %r" % first)
    return first


class IcedDisassemblerPort(DisassemblerPort):
    """Real disassembler bound to one target memory via ``read_bytes``.

    One bounded probe read (``count * 15`` bytes, clamped to the
    address-space limit) feeds the iced-x86 decoder. If the target read
    fails (e.g. module end), the probe size is halved until the read
    succeeds, and the inspection covers the readable range. Decoding fails
    closed as soon as the decoder reports an invalid instruction outside
    the last 15 bytes of a shrunk read (truncation is not "invalid
    code"), or the readable range does not cover ``count`` instructions.
    """

    def __init__(self, read_bytes):
        if not callable(read_bytes):
            raise DisassemblerError(
                "IcedDisassemblerPort requires a callable "
                "read_bytes(address, size) -> bytes.")
        self._read_bytes = read_bytes

    def disassemble(self, address: int, count: int, bitness: int) -> list:
        if type(bitness) is not int or bitness not in (32, 64):
            raise DisassemblerError(
                "IcedDisassemblerPort supports only 32/64-bit targets "
                "(got %r)" % (bitness,))
        limit = ADDRESS_LIMIT_32 if bitness == 32 else ADDRESS_LIMIT_64
        if type(address) is not int or not 0 < address <= limit:
            raise DisassemblerError(
                "disassemble requires a resolved bounded integer address",
                address=address)
        if type(count) is not int or not 1 <= count <= MAX_DISASSEMBLE_COUNT:
            raise DisassemblerError(
                "disassemble count must be within its bounded range",
                count=count)
        requested = min(count * MAX_INSTRUCTION_LENGTH, limit - address + 1)
        probe = requested
        raw = None
        while True:
            try:
                raw = self._read_bytes(address, probe)
                break
            except DisassemblerError:
                raise
            except Exception as exc:
                if probe <= 1:
                    raise DisassemblerError(
                        "target memory read failed for disassemble",
                        address=address) from exc
                probe = probe // 2
        shrunk = probe < requested
        if type(raw) is not bytes:
            try:
                raw = bytes(raw)
            except Exception as exc:
                raise DisassemblerError(
                    "target memory read returned non-byte data for "
                    "disassemble", address=address
                ) from exc
        if len(raw) != probe:
            raise DisassemblerError(
                "target memory read returned %d bytes, expected %d; "
                "disassemble refused" % (len(raw), probe), address=address)
        decoder = iced_x86.Decoder(bitness, raw, ip=address)
        output = []
        cursor = address
        while len(output) < count and decoder.can_decode:
            instruction = decoder.decode()
            if shrunk and instruction.ip + instruction.len >= address + len(raw):
                break
            if instruction.code == iced_x86.Code.INVALID:
                raise DisassemblerError(
                    "invalid instruction at 0x%X; disassemble refused"
                    % cursor,
                    address=cursor, count=count)
            output.append({
                "address": instruction.ip,
                "size": instruction.len,
                "mnemonic": _mnemonic(instruction),
            })
            cursor = instruction.ip + instruction.len
        if len(output) < count:
            raise DisassemblerError(
                "could not decode %d instructions at 0x%X; decode stopped at "
                "0x%X" % (count, address, cursor),
                address=address, count=count)
        return output
