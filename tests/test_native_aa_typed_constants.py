"""Typed inline constants: the CE 7.5 AA value-constant family.

Clean-room parity with the CE 7.5 reference (read-only): ``StrToQWordEx``
(parsers.pas) governs the integer family - integer parse of decimal or
``0x``/``$`` hex, a decimal/exponent form falls back to the toward-zero
truncation of the float parse, and the value is bounded to the type's
two's-complement range (named refusal otherwise).  ``StrToFloatEx`` /
Delphi ``StrToFloat`` govern float/double: decimal/exponent grammar plus
the named ``Inf``/``Infinity``/``NaN`` forms (signed).  The type decides
the memory-operand size prefix (byte/word/dword/qword), superseding the
unsized-integer-is-dword heuristic; a cast over a symbol (or a type/
literal mismatch, e.g. hex for float) stays on the WP-30 cast no-op
path.  Corpus evidence: the DS-pair root ``mov [rax+000002BC],(int)0.00``,
Borderlands3 ``cmp [flag],(byte)2`` (byte-compare parity fix), the 5
``dq (double)Inf`` records and the APlagueTale ``define(name, (float)X)``
idiom.  Byte pins below were verified on the real NASM path.
"""

from __future__ import annotations

import struct
import unittest

from ct2trainer.native.aa_program import (
    ProgramError,
    _typed_bits,
    link_program,
    prepare_program,
)
from ct2trainer.native.assembler import AssemblyError, NasmAssembler


def f32(value: float) -> int:
    return int.from_bytes(struct.pack("<f", value), "little")


def f64(value: float) -> int:
    return int.from_bytes(struct.pack("<d", value), "little")


class Memory:
    """Zero-filled bounded fake process memory for allocation-only programs."""

    def read(self, address, size):
        return bytes(size)

    def module(self, name):
        raise ValueError("Unknown owned module")

    def scan_module(self, module, pattern):
        return 0x140001000


ALLOCATIONS = {"cave": {"address": 0x140002000, "size": 4096, "executable": True}}


class TypedConstantSemanticsTests(unittest.TestCase):
    """The pure value decision of _typed_bits; no assembler involved."""

    def test_integer_family_values(self):
        cases = [
            ("(int)0.00", (0, 4)),
            ("(int)999", (999, 4)),
            ("(int)999999999", (999999999, 4)),
            ("(int)1085763612", (1085763612, 4)),
            ("(int)-1", (0xFFFFFFFF, 4)),
            ("(int)+5", (5, 4)),
            ("(int)0x2BC", (0x2BC, 4)),
            ("(int)$2BC", (0x2BC, 4)),
            ("(int)-0x10", (0xFFFFFFF0, 4)),
            ("(dword)4294967295", (0xFFFFFFFF, 4)),
            ("(dword)-1", (0xFFFFFFFF, 4)),
            ("(qword)18446744073709551615", (0xFFFFFFFFFFFFFFFF, 8)),
            ("(qword)-1", (0xFFFFFFFFFFFFFFFF, 8)),
            ("(word)65535", (0xFFFF, 2)),
            ("(word)-1", (0xFFFF, 2)),
            ("(byte)255", (0xFF, 1)),
            ("(byte)-1", (0xFF, 1)),
            ("(byte)2", (2, 1)),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(_typed_bits(text), expected)

    def test_decimal_and_exponent_forms_truncate_toward_zero(self):
        # CE StrToQWordEx fallback: non-integer literal -> float parse ->
        # trunc toward zero (not banker's, not floor).
        cases = [
            ("(int)1e3", (1000, 4)),
            ("(int)2.7", (2, 4)),
            ("(int)-2.7", (0xFFFFFFFE, 4)),
            ("(int)0.5", (0, 4)),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(_typed_bits(text), expected)

    def test_integer_range_refusals_named(self):
        cases = [
            ("(byte)256", "Typed constant exceeds the byte representation."),
            ("(byte)-129", "Typed constant exceeds the byte representation."),
            ("(word)65536", "Typed constant exceeds the word representation."),
            ("(int)4294967296", "Typed constant exceeds the int representation."),
            ("(int)-2147483649", "Typed constant exceeds the int representation."),
            ("(dword)4294967296", "Typed constant exceeds the dword representation."),
            ("(qword)18446744073709551616", "Typed constant exceeds the qword representation."),
        ]
        for text, message in cases:
            with self.subTest(text=text):
                with self.assertRaises(ProgramError) as ctx:
                    _typed_bits(text)
                self.assertEqual(str(ctx.exception), message)

    def test_float_double_values(self):
        cases = [
            ("(float)0", (0, 4)),
            ("(float)1.0", (f32(1.0), 4)),
            ("(float)1.5", (f32(1.5), 4)),
            ("(float)1000", (f32(1000.0), 4)),
            ("(float)-98", (f32(-98.0), 4)),
            ("(float)0.03", (f32(0.03), 4)),
            ("(float)1e2", (f32(100.0), 4)),
            ("(float)5999.990234", (f32(5999.990234), 4)),
            ("(float)Inf", (f32(float("inf")), 4)),
            ("(float)-Inf", (f32(float("-inf")), 4)),
            ("(float)NaN", (0x7FC00000, 4)),
            ("(double)0", (0, 8)),
            ("(double)2.5", (f64(2.5), 8)),
            ("(double)600", (f64(600.0), 8)),
            ("(double)Inf", (f64(float("inf")), 8)),
            ("(double)-Inf", (f64(float("-inf")), 8)),
            ("(double)+Inf", (f64(float("inf")), 8)),
            ("(double)Infinity", (f64(float("inf")), 8)),
            ("(double)NaN", (0x7FF8000000000000, 8)),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(_typed_bits(text), expected)

    def test_float_finite_refusal_named(self):
        # Byte-stable refusal of the pre-existing float/double path.
        for text in ("(float)1e400", "(double)1e400"):
            with self.subTest(text=text):
                with self.assertRaises(ProgramError) as ctx:
                    _typed_bits(text)
                self.assertEqual(str(ctx.exception), "Floating constants must be finite.")

    def test_cast_no_op_boundaries(self):
        # A type over a non-literal (or a type/literal mismatch) is not a
        # typed constant; it keeps the WP-30 cast no-op / symbol behavior.
        for text in (
            "(int)abc", "(int)Inf", "(int)-Inf", "(float)0x1",
            "(int)999abc", "(float)1.0abc", "(uint)5", "(long)5",
            "float 1.0", "(int)",
        ):
            with self.subTest(text=text):
                self.assertIsNone(_typed_bits(text))

    def test_type_spelling_and_whitespace(self):
        self.assertEqual(_typed_bits("(INT)42"), (42, 4))
        self.assertEqual(_typed_bits("(Float)1.0"), (f32(1.0), 4))
        self.assertEqual(_typed_bits("(float) 1.0"), (f32(1.0), 4))


class RealNasmTypedConstantTests(unittest.TestCase):
    """Byte pins through the real NASM link path."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.assembler = NasmAssembler()
        except AssemblyError as exc:
            raise unittest.SkipTest(str(exc))

    def assemble(self, body, symbols=None):
        source = ("[ENABLE]\nalloc(cave,1000)\ncave:\n" + body +
                  "[DISABLE]\ndealloc(cave)\n")
        program = prepare_program(source)
        return link_program(program, Memory(), symbols=symbols or {},
                            allocations=ALLOCATIONS, assembler=self.assembler)

    def refuse(self, body, fragment):
        source = ("[ENABLE]\nalloc(cave,1000)\ncave:\n" + body +
                  "[DISABLE]\ndealloc(cave)\n")
        with self.assertRaises(ProgramError) as ctx:
            program = prepare_program(source)
            link_program(program, Memory(), allocations=ALLOCATIONS,
                         assembler=self.assembler)
        self.assertIn(fragment, str(ctx.exception))

    def test_death_stranding_root_operand(self):
        # The DS-pair root record: mov [rax+000002BC],(int)0.00 (script line
        # 1492) - the decimal literal in an int cast used to fail the whole
        # record and cascade ~241 rows per table.
        linked = self.assemble(" mov [rax+000002BC],(int)0.00\n")
        self.assertEqual(linked["blocks"][0]["bytes"], "C780BC02000000000000")

    def test_integer_operand_bytes(self):
        pins = [
            (" mov [rax+700],(int)999\n", "C78000070000E7030000"),
            (" mov [rax+700],(int)-1\n", "C78000070000FFFFFFFF"),
            (" mov [rax+700],(int)0x2BC\n", "C78000070000BC020000"),
            (" mov [rax+700],(int)$2BC\n", "C78000070000BC020000"),
            (" mov [rax+700],(int)1e3\n", "C78000070000E8030000"),
            (" mov [rax+700],(int)2.7\n", "C7800007000002000000"),
            (" mov [rax+700],(int)1085763612\n", "C780000700001C70B740"),
            (" mov [rax+700],(dword)5\n", "C7800007000005000000"),
        ]
        for body, expected in pins:
            with self.subTest(body=body):
                linked = self.assemble(body)
                self.assertEqual(linked["blocks"][0]["bytes"], expected)

    def test_type_decides_memory_operand_size(self):
        # The cast type decides the operand size (CE semantics), not the
        # unsized-integer-is-dword heuristic.
        pins = [
            (" cmp [rax+700],(byte)2\n", "80B80007000002"),
            (" mov [rax+700],(word)1234\n", "66C78000070000D204"),
        ]
        for body, expected in pins:
            with self.subTest(body=body):
                linked = self.assemble(body)
                self.assertEqual(linked["blocks"][0]["bytes"], expected)

    def test_borderlands3_byte_compare_parity(self):
        # cmp [DaylightModifierFlag],(byte)2 assembles as a byte compare
        # (CE parity); before the package the cast was a no-op and the
        # operand size fell back to the dword heuristic.
        linked = self.assemble(" cmp [rax+700],(byte)2\n")
        self.assertEqual(linked["blocks"][0]["bytes"], "80B80007000002")

    def test_float_operand_bytes(self):
        pins = [
            (" mov [rax+700],(float)1000\n", "C7800007000000007A44"),
            # byte-stable pin against the pre-existing float path
            (" mov [rax+700],(float)1.0\n", "C780000700000000803F"),
            (" mov [rax+700],(float)5999.990234\n", "C78000070000EC7FBB45"),
            (" mov [rax+700],(float)NaN\n", "C780000700000000C07F"),
        ]
        for body, expected in pins:
            with self.subTest(body=body):
                linked = self.assemble(body)
                self.assertEqual(linked["blocks"][0]["bytes"], expected)

    def test_unsized_integer_heuristic_intact(self):
        linked = self.assemble(" mov [rax+700],5\n")
        self.assertEqual(linked["blocks"][0]["bytes"], "C7800007000005000000")

    def test_unsized_hex_dialect_intact(self):
        # Dialect boundary: an unsized integer operand stays on the
        # established hex-by-default AA dialect (integer()), while a typed
        # constant follows the CE StrToQWordEx decimal contract -
        # (int)999 is decimal 999 (0x3E7), unsized 999 is 0x999.
        linked = self.assemble(" mov [rax+700],999\n")
        self.assertEqual(linked["blocks"][0]["bytes"], "C7800007000099090000")

    def test_cast_over_symbol_stays_no_op(self):
        linked = self.assemble(" mov [rax+700],(int)mysym\n",
                               symbols={"mysym": 0x1234})
        self.assertEqual(linked["blocks"][0]["bytes"], "C7800007000034120000")

    def test_data_directive_typed_values(self):
        pins = [
            (" dd (int)999999999\n", "FFC99A3B"),
            (" dd (int)0.5\n", "00000000"),
            (" dd (int)0\n", "00000000"),
            (" db (byte)255\n", "FF"),
            (" dd (float)1.0 (float)1.1\n", "0000803FCDCC8C3F"),
        ]
        for body, expected in pins:
            with self.subTest(body=body):
                linked = self.assemble(body)
                self.assertEqual(linked["blocks"][0]["bytes"], expected)

    def test_data_directive_inf_nan(self):
        # The 5 corpus records ``dq (double)Inf`` were blocked on the
        # undefined symbol 'Inf'; the named form is a data value now.
        pins = [
            (" dq (double)Inf\n", "000000000000F07F"),
            (" dq (double)-Inf\n", "000000000000F0FF"),
            (" dq (double)NaN\n", "000000000000F87F"),
        ]
        for body, expected in pins:
            with self.subTest(body=body):
                linked = self.assemble(body)
                self.assertEqual(linked["blocks"][0]["bytes"], expected)

    def test_data_directive_strict_width_refusal(self):
        # Consistent with the pre-existing float/double data strictness.
        self.refuse(" dw (int)65535\n", "Typed constant does not fit the data directive.")

    def test_define_typed_family(self):
        pins = [
            ("define(X,(int)0.00)\n mov [rax+700],X\n", "C7800007000000000000"),
            ("define(X,(int)999999999)\n dd X\n", "FFC99A3B"),
            ("define(Y,(double)2.5)\n dq Y\n", "0000000000000440"),
            ("define(bval,(byte)2)\n cmp [rax+700],bval\n", "83B80007000002"),
            ("define(wval,(word)1234)\n mov [rax+700],wval\n", "C78000070000D2040000"),
            ("define(qval,(qword)18446744073709551615)\n dq qval\n", "FFFFFFFFFFFFFFFF"),
            ("define(dinf,(double)Inf)\n dq dinf\n", "000000000000F07F"),
            ("define(iv,(int)2.7)\n mov [rax+700],iv\n", "C7800007000002000000"),
        ]
        for body, expected in pins:
            with self.subTest(body=body.split()[0]):
                linked = self.assemble(body)
                self.assertEqual(linked["blocks"][0]["bytes"], expected)

    def test_define_float_idiom_corpus(self):
        # APlagueTale idiom: define(movespeedmultiplierdefault,(float)0.64) -
        # byte-stable against the pre-existing float-define path.
        body = ("define(movespeedmultiplierdefault,(float)0.64)\n"
                " mov [rax+700],movespeedmultiplierdefault\n")
        linked = self.assemble(body)
        self.assertEqual(linked["blocks"][0]["bytes"], "C780000700000AD7233F")

    def test_define_preamble_placement(self):
        source = ("define(X,1234)\n[ENABLE]\nalloc(cave,1000)\ncave:\n"
                  " mov [rax+700],X\n[DISABLE]\ndealloc(cave)\n")
        program = prepare_program(source)
        linked = link_program(program, Memory(), allocations=ALLOCATIONS,
                              assembler=self.assembler)
        self.assertEqual(linked["blocks"][0]["bytes"], "C7800007000034120000")

    def test_operand_range_refusals_named(self):
        for body, fragment in [
            (" mov [rax+700],(byte)256\n", "Typed constant exceeds the byte representation."),
            (" mov [rax+700],(int)4294967296\n", "Typed constant exceeds the int representation."),
            (" mov [rax+700],(word)65536\n", "Typed constant exceeds the word representation."),
            (" mov [rax+700],(dword)4294967296\n", "Typed constant exceeds the dword representation."),
            (" mov [rax+700],(qword)18446744073709551616\n", "Typed constant exceeds the qword representation."),
        ]:
            with self.subTest(body=body):
                self.refuse(body, fragment)

    def test_operand_finite_refusal_named(self):
        self.refuse(" mov [rax+700],(float)1e400\n", "Floating constants must be finite.")


if __name__ == "__main__":
    unittest.main()
