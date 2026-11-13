"""Lane (compatibility): AA extended-register ``l`` alias + ``dqword`` size parity.

The nine residual rows of the post-0.44 catalog census (seven ``rXl``
extended-register spellings across DS2 / HellPie / RAGE2 / Sinking City /
SOTTR / YakuzaLikeADragon and two ``dqword`` 128-bit size spellings across
Fallout4 / SOTTR) were blocked because the clean-room token sets do not
admit the CE spellings and the pinned NASM assembles neither of them.

CE ``TSingleLineAssembler.getreg`` (Assemblerunit.pas) accepts the ``l``
32-bit alias ``R8L``..``R15L`` as the low-dword register, and CE ``dqword``
is the 128-bit operand size that NASM spells ``oword`` (the same size CE's
``xmmword`` already maps to here).  This file proves, on owned synthetic
programs:

* recognition -- ``r8l``..``r15l`` are registers and ``dqword`` a size
  keyword, so neither enters a program's symbol requires (the catalog
  block origin);
* normalization -- the NASM source generation rewrites ``rXl`` -> ``rXd``
  and ``dqword`` -> ``oword`` (the CE spellings NASM rejects);
* byte identity -- through the pinned NASM, the ``l`` / ``dqword``
  spellings assemble to byte-identical code to the canonical ``d`` /
  ``oword`` spellings.
"""
from __future__ import annotations

import unittest

from ct2trainer.native.aa_program import (
    _KEYWORDS,
    _REGISTERS,
    _translate_operands,
    dry_link_program,
    prepare_program,
)
from ct2trainer.native.assembler import AssemblyError, NasmAssembler

PROCESS = "owned.exe"


class Memory:
    """Read-only fixture memory: zero everywhere, one owned module."""

    def read(self, address, size):
        return bytes(size)

    def module(self, name):
        if name.casefold() != PROCESS.casefold():
            raise ValueError("Unknown owned module")
        return 0x140000000, 0x100000

    def scan_module(self, module, pattern):
        return 0x140001000


def cave_bytes(instruction: str, assembler, alloc_size: int = 64) -> str:
    """Assemble one instruction in an owned cave and return the cave bytes.

    The cave block is the allocation: the instruction at offset zero, then
    zero fill, then the size/metadata footer.  Two structurally identical
    programs therefore compare byte-for-byte on their cave blocks.
    """
    source = ("[ENABLE]\nalloc(cave, %d)\ncave:\n%s\n[DISABLE]\ndealloc(*)"
              % (alloc_size, instruction))
    program = prepare_program(source, PROCESS)
    dry = dry_link_program(program, Memory(), {}, assembler=assembler)
    return dry["enable"]["blocks"][0]["bytes"]


class RecognitionTests(unittest.TestCase):
    """The CE spellings are admitted as registers / sizes, not symbols."""

    def test_extended_register_l_alias_is_in_the_register_set(self):
        for index in range(8, 16):
            with self.subTest(index=index):
                for suffix in ("", "d", "w", "b", "l"):
                    self.assertIn(f"r{index}{suffix}", _REGISTERS)
        # The legacy low bytes keep their own spellings (no ``l`` alias
        # beyond the extended registers).
        for name in ("al", "bl", "cl", "dl", "sil", "dil", "bpl", "spl"):
            self.assertIn(name, _REGISTERS)

    def test_dqword_is_in_the_size_keyword_set(self):
        self.assertIn("dqword", _KEYWORDS)
        # The canonical 128-bit NASM spelling it maps to stays present.
        self.assertIn("oword", _KEYWORDS)


class NormalizationTests(unittest.TestCase):
    """The NASM source rewrites the CE spellings to the NASM spellings."""

    @staticmethod
    def _translate(token):
        return _translate_operands(token, {}, None, None, {}, None, None)

    def test_l_alias_registers_normalize_to_the_d_spelling(self):
        for index in range(8, 16):
            with self.subTest(index=index):
                self.assertEqual(self._translate(f"r{index}l"), f"r{index}d")

    def test_dqword_normalizes_to_oword(self):
        self.assertEqual(self._translate("dqword"), "oword")

    def test_canonical_spellings_pass_through_unchanged(self):
        # The d/w/b extended forms and the plain sizes are already NASM
        # spellings; they must not be rewritten.
        for token, expected in (
            ("r13d", "r13d"), ("r8w", "r8w"), ("r15b", "r15b"), ("r9", "r9"),
            ("oword", "oword"), ("dword", "dword"), ("qword", "qword"),
            ("xmmword", "oword"), ("ymmword", "yword"), ("zmmword", "zword"),
            ("rax", "rax"), ("eax", "eax"),
        ):
            with self.subTest(token=token):
                self.assertEqual(self._translate(token), expected)


class SymbolRequirementTests(unittest.TestCase):
    """The spellings no longer enter a program's symbol requires."""

    def test_l_alias_registers_are_not_symbol_requirements(self):
        source = ("[ENABLE]\nalloc(newmem, 32)\nlabel(returnhere)\nnewmem:\n"
                  "cmp dword [rcx+0x11E], r13l\n"
                  "test r15l, r15l\n"
                  "xor r11l, r11l\n"
                  "mov r9l, byte [r9]\n"
                  "mov r8l, [r8+rdx]\n"
                  "jmp returnhere\nreturnhere:\ndealloc(newmem)\n"
                  "[DISABLE]\ndealloc(newmem)")
        program = prepare_program(source, PROCESS)
        self.assertEqual(program["requires"], [])

    def test_dqword_is_not_a_symbol_requirement(self):
        source = ("[ENABLE]\nalloc(newmem, 32)\nlabel(returnhere)\nnewmem:\n"
                  "movdqu dqword [rsp], xmm0\n"
                  "jmp returnhere\nreturnhere:\ndealloc(newmem)\n"
                  "[DISABLE]\ndealloc(newmem)")
        program = prepare_program(source, PROCESS)
        self.assertEqual(program["requires"], [])


class ByteIdentityTests(unittest.TestCase):
    """Through the pinned NASM the CE spellings assemble byte-identically
    to the canonical spellings (the bytes CE's getreg would produce)."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.assembler = NasmAssembler()
        except AssemblyError as exc:
            raise unittest.SkipTest(str(exc))

    def test_l_alias_assembles_byte_identical_to_the_d_spelling(self):
        alias = cave_bytes("mov r13l, eax", self.assembler)
        canonical = cave_bytes("mov r13d, eax", self.assembler)
        self.assertEqual(alias, canonical)
        # mov r13d, eax = REX.B (0x41) + mov r/m32, r32 (0x89) +
        # ModRM 11 000 101 (0xC5): the 32-bit low-dword register.
        self.assertEqual(alias[:6], "4189C5")

    def test_dqword_assembles_byte_identical_to_oword(self):
        alias = cave_bytes("movdqu dqword [rsp], xmm0", self.assembler)
        canonical = cave_bytes("movdqu oword [rsp], xmm0", self.assembler)
        self.assertEqual(alias, canonical)
        # movdqu xmm0, [rsp] = SSE (0xF3) + 0F 7F + ModRM 00 000 100 +
        # SIB 00 100 100 ([rsp]).
        self.assertEqual(alias[:10], "F30F7F0424")


if __name__ == "__main__":
    unittest.main()
