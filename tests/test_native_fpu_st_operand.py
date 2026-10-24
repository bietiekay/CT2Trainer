"""RT-4.6: FPU ``st`` / ``st(N)`` operand tokens (CE 7.5 parity).

CE 7.5's Assemblerunit token classifier (Assemblerunit.pas:3283-3291)
treats ``ST``, ``ST(0)``-``ST(7)`` (case-insensitive) as single register
tokens, and a bare ``ST`` is the stack top ``ST(0)``.  The clean-room
tokenizer used to split ``st(0)`` into ``st``, ``(``, ``0``, ``)``, so
the bare ``st`` entered the requirements as an unsatisfied symbol and
blocked the record ("Required symbol has no unique supported provider:
st.") - two Witcher3 rows and one LustForDarkness row in the reference
corpus.  The token loop now folds the FPU stack token; ``st(N)`` with N
outside 0-7 is not a register token in CE either, so the bare ``st``
name is kept for the ordinary fail-closed symbol machinery.
"""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from test_native_engine import FakeMemory
from test_native_engine_code import Coordinator

from ct2trainer.native import aa_program
from ct2trainer.native.aa_program import prepare_program
from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import TrainerEngine

PROCESS = "FixtureTarget.exe"


def tokens(text: str):
    return aa_program._operand_tokens(text)


class StTokenTests(unittest.TestCase):
    """Tokenizer level: the fold follows the CE 7.5 register table."""

    def test_st_parenthesized_zero_through_seven_fold_to_registers(self):
        for n in range(8):
            with self.subTest(n=n):
                self.assertEqual(tokens(f"st({n})"), [f"st{n}"])

    def test_fold_is_case_insensitive(self):
        self.assertEqual(tokens("ST(3)"), ["st3"])
        self.assertEqual(tokens("St(7)"), ["st7"])
        self.assertEqual(tokens("ST"), ["st0"])

    def test_bare_st_is_stack_top(self):
        self.assertEqual(tokens("st"), ["st0"])
        # The tokenizer emits whitespace runs as their own tokens; the fold
        # must leave the separator structure untouched.
        self.assertEqual(tokens("st, st(1)"), ["st0", ",", " ", "st1"])
        self.assertEqual(tokens("[rax], st(2)"), ["[", "rax", "]", ",", " ", "st2"])

    def test_out_of_range_index_keeps_the_bare_symbol(self):
        # st(N) with N outside 0-7 is not a register token (CE agrees):
        # the bare st name must survive so the symbol machinery reports
        # it fail-closed.
        self.assertEqual(tokens("st(8)"), ["st", "(", "8", ")"])
        self.assertEqual(tokens("ST(31)"), ["ST", "(", "31", ")"])

    def test_longer_identifiers_are_unaffected(self):
        # Greedy tokenization keeps std/st0-style names whole; only the
        # exact bare st token folds.
        self.assertEqual(tokens("std"), ["std"])
        self.assertEqual(tokens("st0"), ["st0"])
        self.assertEqual(tokens("st0, st(4)"), ["st0", ",", " ", "st4"])


class StProgramTests(unittest.TestCase):
    """Program level: folded tokens leave no symbol requirement behind."""

    def source(self, instruction: str) -> str:
        return (f"[ENABLE]\nFixtureTarget.exe+40:\n{instruction}\n"
                "[DISABLE]\nFixtureTarget.exe+40:\ndb 00\n")

    def test_parenthesized_indices_leave_no_st_requirement(self):
        for n in range(8):
            with self.subTest(n=n):
                requires = prepare_program(
                    self.source(f"fstp st({n})"), PROCESS)["requires"]
                self.assertNotIn("st", requires)

    def test_bare_st_leaves_no_st_requirement(self):
        requires = prepare_program(self.source("fadd ST"), PROCESS)["requires"]
        self.assertNotIn("st", requires)

    def test_out_of_range_st_stays_a_requirement(self):
        requires = prepare_program(self.source("fstp st(8)"), PROCESS)["requires"]
        self.assertIn("st", requires)

    def test_fcomip_st_instruction_assembles_via_nasm_at_engine_level(self):
        # The folded tokens must reach the NASM line as st0/st1: a
        # byte-exact enable (DF F1 = FCOMIP ST(1), ST(0)) proves the full
        # chain tokenizer -> program -> NASM -> publish.  The fixture uses
        # fcomip because the pinned NASM 3.02 carries an upstream x86
        # table defect for the FSTP register form (``fstp st0`` assembles
        # to DD D8 instead of DF C0); fcomip st(0),st(1) is the reference
        # corpus's actual FPU pattern and encodes correctly.
        with tempfile.TemporaryDirectory() as directory:
            table = Path(directory) / "st.ct"
            table.write_text(
                '<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
                '<CheatEntry><ID>1</ID><Description>"FPU stack compare"'
                '</Description><VariableType>Auto Assembler Script'
                '</VariableType><AssemblerScript>[ENABLE]\n'
                'assert(FixtureTarget.exe+40,00 00)'
                '\nFixtureTarget.exe+40:'
                '\nfcomip st(0),st(1)'
                '\n[DISABLE]\n'
                'FixtureTarget.exe+40:'
                '\ndb 00 00'
                '</AssemblerScript></CheatEntry>'
                '</CheatEntries></CheatTable>',
                encoding="utf-8",
            )
            plan = compile_table(table, PROCESS)
            entry = plan["entries"][0]
            self.assertTrue(entry["supported"], entry["reason"])
            memory = StMemory()
            engine = TrainerEngine(
                plan, state_dir=Path(directory) / "state",
                process_lock_dir=Path(directory) / "shared",
                memory_factory=lambda name: memory,
                hook_coordinator=Coordinator())
            engine.poll()
            self.assertTrue(engine.connected, engine.status)
            self.assertTrue(engine.toggle(1, True))
            self.assertEqual(memory.read(memory.base + 0x40, 2),
                             bytes.fromhex("dff1"))
            self.assertFalse(engine.toggle(1, False))
            self.assertEqual(memory.read(memory.base + 0x40, 2), bytes(2))
            engine.close()


class StMemory(FakeMemory):
    """Base 0x1000; the +0x40 slot is executable and starts zeroed."""

    @property
    def identity(self):
        return self.pid, self.creation_time

    def is_executable(self, address, size):
        return self.base + 0x40 <= address < self.base + 0x42


if __name__ == "__main__":
    unittest.main()
