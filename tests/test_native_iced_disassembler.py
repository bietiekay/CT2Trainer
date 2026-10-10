"""Real iced-x86 disassembler port: contract conformance and fail-closed bounds.

The port implements the tested ``DisassemblerPort`` contract from
``aa_directives.py`` on top of the pinned iced-x86 decoder (1.21.0, vendored
under ``dependencies/native/iced-x86`` and bundled by ``tools/native_build.py``).
Happy paths decode bounded fixture code for both bitnesses; failure paths
(short reads, failing reads, out-of-bounds address/count/bitness, invalid
instructions, module-boundary reads) refuse visibly with named
``DisassemblerError`` reasons. The final test proves the real decoder output
passes the Stage-1 ``DisassembleDirectiveModel`` output validation.
"""
import unittest

from ct2trainer.native.aa_directives import (DisassembleDirectiveModel,
                                               DisassemblerError,
                                               DisassemblerPort)
from ct2trainer.native.iced_disassembler import IcedDisassemblerPort

BASE = 0x140001000
# nop, nop, mov rax, qword ptr [rip+0x0] (7 bytes), ret
X64_CODE = bytes.fromhex("9090488b0500000000c3")
# nop, ret, push ebx
X86_CODE = bytes.fromhex("90c353")


def make_read(address, data):
    """A read_bytes callable over a fixed fixture window."""
    def read(addr, size):
        if addr < address or addr + size > address + len(data):
            raise OSError("read outside fixture range")
        return data[addr - address:addr - address + size]
    return read


def padded(code, size):
    return code + bytes(size - len(code))


class IcedDisassemblerPortTests(unittest.TestCase):
    def test_port_implements_disassembler_port_contract(self):
        port = IcedDisassemblerPort(make_read(BASE, padded(X64_CODE, 60)))
        self.assertIsInstance(port, DisassemblerPort)

    def test_x64_run_is_gapless_exact_count_with_bounded_mnemonics(self):
        port = IcedDisassemblerPort(make_read(BASE, padded(X64_CODE, 60)))
        out = port.disassemble(BASE, 4, 64)
        self.assertEqual(len(out), 4)
        self.assertEqual([item["address"] for item in out],
                         [BASE, BASE + 1, BASE + 2, BASE + 9])
        self.assertEqual([item["size"] for item in out], [1, 1, 7, 1])
        self.assertEqual([item["mnemonic"] for item in out],
                         ["nop", "nop", "mov", "ret"])
        for item in out:
            self.assertTrue(1 <= item["size"] <= 15)
            self.assertTrue(item["mnemonic"].isascii())
            self.assertLessEqual(len(item["mnemonic"]), 64)

    def test_x86_run_with_32bit_bitness(self):
        base32 = 0x00401000
        port = IcedDisassemblerPort(make_read(base32, padded(X86_CODE, 45)))
        out = port.disassemble(base32, 3, 32)
        self.assertEqual([item["mnemonic"] for item in out],
                         ["nop", "ret", "push"])
        self.assertEqual([item["address"] for item in out],
                         [base32, base32 + 1, base32 + 2])

    def test_invalid_instruction_in_middle_refuses_with_address(self):
        # 0x06 (push es) is invalid in 64-bit mode.
        port = IcedDisassemblerPort(make_read(BASE, padded(b"\x90\x06\x90", 30)))
        with self.assertRaisesRegex(DisassemblerError,
                                    "invalid instruction at 0x140001001"):
            port.disassemble(BASE, 2, 64)

    def test_count_out_of_bounded_range_refused(self):
        port = IcedDisassemblerPort(make_read(BASE, padded(X64_CODE, 60)))
        with self.assertRaisesRegex(DisassemblerError, "bounded range"):
            port.disassemble(BASE, 0, 64)
        with self.assertRaisesRegex(DisassemblerError, "bounded range"):
            port.disassemble(BASE, 4097, 64)

    def test_bitness_must_be_32_or_64(self):
        port = IcedDisassemblerPort(make_read(BASE, padded(X64_CODE, 60)))
        with self.assertRaisesRegex(DisassemblerError, "32/64"):
            port.disassemble(BASE, 1, 16)

    def test_address_out_of_bounded_space_refused(self):
        port = IcedDisassemblerPort(make_read(BASE, padded(X64_CODE, 60)))
        with self.assertRaisesRegex(DisassemblerError, "bounded integer address"):
            port.disassemble(0, 1, 64)
        with self.assertRaisesRegex(DisassemblerError, "bounded integer address"):
            port.disassemble(0x8000_0000_0000_0000, 1, 64)

    def test_short_read_refused(self):
        port = IcedDisassemblerPort(lambda addr, size: b"\x90")
        with self.assertRaisesRegex(DisassemblerError, "expected"):
            port.disassemble(BASE, 4, 64)

    def test_failing_read_refused_with_named_reason(self):
        def failing_read(addr, size):
            raise OSError("access denied")
        port = IcedDisassemblerPort(failing_read)
        with self.assertRaisesRegex(DisassemblerError,
                                    "target memory read failed"):
            port.disassemble(BASE, 1, 64)

    def test_read_returning_int_list_is_accepted(self):
        buf = padded(X64_CODE, 60)
        port = IcedDisassemblerPort(lambda addr, size: list(buf[:size]))
        out = port.disassemble(BASE, 4, 64)
        self.assertEqual([item["mnemonic"] for item in out],
                         ["nop", "nop", "mov", "ret"])

    def test_module_boundary_shrinks_probe_read(self):
        # Only 10 bytes are available, but count=2 needs a 30-byte probe:
        # the read shrinks 30 -> 15 -> 7 and two complete nops decode.
        port = IcedDisassemblerPort(make_read(BASE, X64_CODE))
        out = port.disassemble(BASE, 2, 64)
        self.assertEqual([item["mnemonic"] for item in out], ["nop", "nop"])
        self.assertEqual([item["address"] for item in out],
                         [BASE, BASE + 1])

    def test_shrunk_read_stops_before_truncated_instruction(self):
        # count=4 needs 60 bytes; only 10 exist. After two nops the 7-byte
        # mov is truncated in the shrunk probe: the port must fail as a
        # decode stop, not as an invalid instruction.
        port = IcedDisassemblerPort(make_read(BASE, X64_CODE))
        with self.assertRaisesRegex(DisassemblerError,
                                    "could not decode 4 instructions"):
            port.disassemble(BASE, 4, 64)

    def test_decode_stops_at_clamped_read_bound(self):
        # 32-bit address space ends at 0xFFFFFFFF: the clamped read covers
        # only the last three bytes, so count=5 cannot be decoded.
        port = IcedDisassemblerPort(make_read(0xFFFFFFFD, b"\x90\x90\x90"))
        with self.assertRaisesRegex(DisassemblerError, "could not decode"):
            port.disassemble(0xFFFFFFFD, 5, 32)

    def test_non_callable_read_bytes_refused_at_construction(self):
        with self.assertRaisesRegex(DisassemblerError, "callable"):
            IcedDisassemblerPort("not callable")

    def test_conformance_through_stage1_directive_model(self):
        port = IcedDisassemblerPort(make_read(BASE, padded(X64_CODE, 60)))
        model = DisassembleDirectiveModel(port, bitness=64)
        op = model.disassemble(BASE, 4)
        self.assertEqual(op["op"], "disassemble")
        self.assertEqual(op["address"], BASE)
        self.assertEqual(op["count"], 4)
        self.assertEqual(len(op["output"]), 4)
        for item in op["output"]:
            self.assertEqual(set(item), {"address", "size", "mnemonic"})
        self.assertIsInstance(model.report(), dict)


if __name__ == "__main__":
    unittest.main()
