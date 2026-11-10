"""Digit-leading label names (CE 7.5 getPotentialLabels parity).

CE contract (autoassembler.pas getPotentialLabels L707-730 and the main
path L2843-2900, read-only reference): a ``name:`` line is a positional
label definition iff ``trystrtoint64('$'+name)`` fails - i.e. the name
does not parse fully as a hexadecimal literal.  A digit-leading name
that is not a value literal (``0CurrentWeight``) is therefore a
program-local positional label; an all-hex name (``0078``, ``11105``)
stays the classic externally-provided symbol cursor, and the 0x/$-
prefixed hex and #N decimal spellings are value literals, never names.
Letter-starting names are unaffected by the rule.

The fix covers the DS-pair "Load Table" record (script lines with
``0CurrentWeight:``/``0StructureBuildTime:``/``10MinDrillTrainingTimer:``
before their ``resb 8`` padding), whose reservation lines used to fall
outside the owned allocation region because the strict symbol token
refused the label names.
"""

from __future__ import annotations

import unittest

from ct2trainer.native.aa_program import (
    ProgramError,
    _symbol_name_token,
    link_program,
    prepare_program,
)
from ct2trainer.native.assembler import AssemblyError, NasmAssembler


class Memory:
    """Zero-filled bounded fake process memory for link tests."""

    pointer_size = 8

    def read(self, address, size):
        return bytes(size)

    def module(self, name):
        return (0x140000000, 0x100000)

    def scan_module(self, module, pattern):
        return 0x140001000


ALLOCATIONS = {"cave": {"address": 0x140002000, "size": 0x1000,
                        "executable": True, "writable": True}}

# The Octopath record shape (reference-table-derived, inlined): a
# digit-leading scan symbol used as the alloc near argument and as the
# injection-point cursor, with the classic registersymbol/unregistersymbol
# lifecycle.  The cursor must keep the classic symbol resolution (the
# scan address), never bind to the patch position.
OCTOPATH_REPLICA = (
    "[ENABLE]\n"
    "\n"
    "aobscanmodule(8PathSteal,probe.exe,E8 90 F9 64 01)\n"
    "alloc(newmem,$1000,8PathSteal)\n"
    "\n"
    "label(return)\n"
    "\n"
    "newmem:\n"
    "  mov [rax],#99\n"
    "  jmp return\n"
    "\n"
    "8PathSteal:\n"
    "  jmp newmem\n"
    "return:\n"
    "registersymbol(8PathSteal)\n"
    "\n"
    "[DISABLE]\n"
    "\n"
    "8PathSteal:\n"
    "  db E8 90 F9 64 01\n"
    "\n"
    "unregistersymbol(8PathSteal)\n"
    "dealloc(newmem)\n"
)


class SymbolNameTokenTests(unittest.TestCase):
    """The pure predicate: CE 7.5 label-name contract."""

    def test_letter_starting_names_unchanged(self):
        # Classic symbol tokens stay admitted, including letter-leading
        # all-hex spellings (they remain positional labels in the walk,
        # byte-stable against the pre-fix behavior).
        for name in ("myLabel", "ABC", "A0", "_x", "PlayerXInjection"):
            self.assertTrue(_symbol_name_token(name), name)

    def test_at_label_tokens_unchanged(self):
        # @-labels keep their own validation; @f/@b are symbol-token
        # shaped and excluded by name at the operand sites.
        for name in ("@foo", "@f", "@b"):
            self.assertTrue(_symbol_name_token(name), name)
        for name in ("@0bad", "@$x"):
            self.assertFalse(_symbol_name_token(name), name)

    def test_digit_leading_non_hex_names_are_label_names(self):
        # Not hex-parseable -> positional label names (CE contract).
        for name in ("0CurrentWeight", "0StructureBuildTime",
                     "10MinDrillTrainingTimer", "8PathSteal",
                     "0Dup", "9UnknownTarget", "0current", "10x"):
            self.assertTrue(_symbol_name_token(name), name)

    def test_digit_leading_all_hex_names_stay_symbol_cursors(self):
        # Hex-parseable names remain the classic externally-provided
        # symbol cursor (module+offset address specifier), not labels.
        for name in ("0078", "11105", "0000002C", "0a", "0F"):
            self.assertFalse(_symbol_name_token(name), name)

    def test_value_literals_never_admitted(self):
        # 0x/$-prefixed hex and #N decimal are value tokens, never
        # symbol or label names (the typed-constant substitution emits
        # the 0x form into operand streams).
        for name in ("0x1F", "0X1F", "0x0", "$1F", "#123"):
            self.assertFalse(_symbol_name_token(name), name)


class DigitLabelPrepareTests(unittest.TestCase):
    """Prepare-level label binding (no target attach)."""

    def alloc_source(self, body: str) -> str:
        return ("[ENABLE]\nalloc(cave,$100)\ncave:\n" + body +
                "[DISABLE]\ndealloc(cave)\n")

    def positional(self, program: dict) -> set[str]:
        return {label.casefold()
                for label in program.get("positional_labels", [])}

    def test_digit_label_inside_alloc_is_local(self):
        # The DS-pair shape: the digit label sits inside the owned
        # allocation and keeps the region for the following reservations.
        program = prepare_program(self.alloc_source(
            "0CurrentWeight:\n  resb 8\n  resb 8\n"))
        self.assertEqual(program["requires"], [])
        self.assertIn("0currentweight", self.positional(program))

    def test_all_hex_cursor_keeps_reservation_refusal(self):
        # All-hex name:lines are not labels; the cursor leaves the owned
        # region and the reservation keeps the fail-closed refusal.
        for name in ("0078", "11105"):
            with self.subTest(name=name):
                with self.assertRaises(ProgramError) as ctx:
                    prepare_program(self.alloc_source(name + ":\n  resb 8\n"))
                self.assertIn("program-owned allocation", str(ctx.exception))

    def test_digit_label_branch_target_stays_local(self):
        # The label definition itself is program-local; the operand
        # tokenizer's hex-prefix split of digit-leading identifiers is a
        # pre-existing dialect boundary (no corpus record branches to a
        # digit label).
        program = prepare_program(self.alloc_source(
            "  jmp 10MinDrill\n10MinDrill:\n  mov [rax+1],0\n"))
        self.assertIn("10mindrill", self.positional(program))

    def test_self_defined_digit_label_outside_alloc(self):
        # A bare name: line defines its own label (CE contract); it is a
        # positional label, never a requirement.
        source = ("[ENABLE]\n  mov [rax+1],0\n9Solo:\n"
                  "[DISABLE]\n  mov [rax+1],1\n")
        program = prepare_program(source)
        self.assertEqual(program["requires"], [])
        self.assertIn("9solo", self.positional(program))

    def test_typed_constant_operands_never_enter_requires(self):
        # The 0x-form literal tokens emitted by typed-constant
        # substitution are values, not symbol references.
        program = prepare_program(self.alloc_source(
            "  mov [rax+1],(int)0.00\n  mov [rax+2],(float)1.5\n"))
        self.assertEqual(program["requires"], [])

    def test_duplicate_digit_label_prepare_parity(self):
        # The named duplicate refusal is a link-time check, exactly as
        # for letter-starting labels (prepare admits both).
        program = prepare_program(self.alloc_source(
            "0Dup:\n  resb 8\n0Dup:\n  resb 8\n"))
        self.assertEqual(program["requires"], [])
        self.assertIn("0dup", self.positional(program))


class DigitLabelNasmTests(unittest.TestCase):
    """Byte pins through the real NASM link path."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.assembler = NasmAssembler()
        except AssemblyError as exc:
            raise unittest.SkipTest(str(exc))

    def link(self, body: str) -> dict:
        source = ("[ENABLE]\nalloc(cave,1000)\ncave:\n" + body +
                  "[DISABLE]\ndealloc(cave)\n")
        program = prepare_program(source)
        return link_program(program, Memory(), allocations=ALLOCATIONS,
                            assembler=self.assembler)

    def test_digit_label_byte_stability(self):
        # The same script spelled with a letter label vs a digit-leading
        # label assembles to byte-identical blocks.
        bodies = ("  mov [rax+1],0\nmyLabel:\n  resb 8\n  resb 8\n"
                  "  dq (double)Inf\n",
                  "  mov [rax+1],0\n0DigitLabel:\n  resb 8\n  resb 8\n"
                  "  dq (double)Inf\n")
        blocks = [self.link(body)["blocks"][0]["bytes"] for body in bodies]
        self.assertEqual(blocks[0], blocks[1])
        # mov [rax+1],0 (C7 40 01 + imm32) + 16 resb zero bytes
        # + 8B +Inf (little-endian)
        self.assertEqual(blocks[0],
                         "C74001" + "00000000" + "00" * 16
                         + "000000000000F07F")

    def test_death_stranding_root_idiom(self):
        # The DS "Load Table" record shape: a decimal-cast int constant,
        # the digit-leading local label and the resb padding all inside
        # one allocation.
        linked = self.link(
            "  mov [rax+000002BC],(int)0.00\n"
            "0CurrentWeight:\n  resb 8\n  resb 8\n  resb 8\n")
        # 10B mov + 24 resb zero bytes
        self.assertEqual(linked["blocks"][0]["bytes"],
                         "C780BC02000000000000" + "00" * 24)

    def test_duplicate_digit_label_refused(self):
        for body in ("0Dup:\n  resb 8\n0Dup:\n  resb 8\n",
                     "myDup:\n  resb 8\nmyDup:\n  resb 8\n"):
            with self.subTest(body=body):
                with self.assertRaises(ProgramError) as ctx:
                    self.link(body)
                self.assertIn(
                    "Local label is duplicated or has no address cursor.",
                    str(ctx.exception))

    def test_octopath_digit_scan_symbol_link(self):
        program = prepare_program(OCTOPATH_REPLICA, "probe.exe")
        linked = link_program(
            program, Memory(),
            allocations={"newmem": {"address": 0x140003000, "size": 0x2000,
                                    "executable": True,
                                    "writable": True}},
            assembler=self.assembler)
        self.assertEqual(len(linked["blocks"]), 2)
        bytes_list = [block["bytes"] for block in linked["blocks"]]
        # The injection block is the jmp newmem at the scan address
        # (0x140001000): E9 + rel32 (0x140003000 - 0x140001000 - 5).
        self.assertIn("E9FB1F0000", bytes_list)


if __name__ == "__main__":
    unittest.main()
