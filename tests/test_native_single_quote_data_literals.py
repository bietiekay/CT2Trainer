"""WP-43: single-quoted string data literals.

Single-quoted string literals are accepted exactly where double-quoted
string literals are accepted — data directives (native dialect db/dw/dd/dq
parsing, data dialect db) and instruction operands — and they produce
byte-identical results.  Backslash escapes inside quoted data literals are
refused fail-closed in both quote styles; symbol, module and address
grammars stay quote-unaware.
"""
import unittest

from ct2trainer.native import aa as aadata
from ct2trainer.native import aa_program as aa
from ct2trainer.native.aa import AAError
from ct2trainer.native.aa_program import ProgramError, _literal_bytes


def _source(body, extra=""):
    return ("[ENABLE]\n" + extra + "\nalloc(cave,1000)\ncave:\n" + body
            + "\n0x1000:\njmp cave\n[DISABLE]\n0x1000:\ndb B8 01 00 00 00\ndealloc(cave)")


class SingleQuotedDataLiteralTests(unittest.TestCase):
    def test_data_dialect_db_single_quoted_bytes(self):
        self.assertEqual(aadata._data_bytes("db", "'Console'"), "436f6e736f6c65")

    def test_data_dialect_single_quoted_bytes_equal_double_quoted_twin(self):
        self.assertEqual(aadata._data_bytes("db", "'Console'"),
                         aadata._data_bytes("db", '"Console"'))
        self.assertEqual(aadata._data_bytes("db", "'Ryo '"),
                         aadata._data_bytes("db", '"Ryo "'))

    def test_data_dialect_quoted_string_with_space_stays_one_token(self):
        self.assertEqual(aadata._data_bytes("db", "'Ryo '"), "52796f20")
        self.assertEqual(aadata._data_bytes("db", "'Ryo ', 0x11"), "52796f2011")

    def test_data_dialect_empty_single_quoted_string_is_zero_bytes(self):
        self.assertEqual(aadata._data_bytes("db", "''"), "")

    def test_non_db_directives_refuse_quoted_strings_in_data_dialect(self):
        for directive in ("dw", "dd", "dq"):
            with self.subTest(directive=directive):
                with self.assertRaisesRegex(AAError,
                                            "Only db supports ASCII string constants"):
                    aadata._data_bytes(directive, "'RR'")

    def test_backslash_refused_in_both_quote_styles_data_dialect(self):
        for text in ("'a\\b'", '"a\\b"'):
            with self.subTest(text=text):
                with self.assertRaisesRegex(AAError, "backslash"):
                    aadata._data_bytes("db", text)

    def test_unterminated_single_quoted_literal_refused_data_dialect(self):
        with self.assertRaisesRegex(AAError, "Unterminated quoted data literal"):
            aadata._data_bytes("db", "'abc")

    def test_native_db_single_quoted_bytes_equal_double_quoted_twin(self):
        single = aa._data_values("'======>G25'", "db")
        double = aa._data_values('"======>G25"', "db")
        node_s = {"op": "data", "directive": "db", "values": single}
        node_d = {"op": "data", "directive": "db", "values": double}
        self.assertEqual(_literal_bytes(node_s, None, {}), b"======>G25")
        self.assertEqual(_literal_bytes(node_s, None, {}),
                         _literal_bytes(node_d, None, {}))

    def test_native_non_db_directives_refuse_single_quoted_strings(self):
        for directive in ("dw", "dd", "dq"):
            with self.subTest(directive=directive):
                with self.assertRaisesRegex(ProgramError,
                                            "Only db supports ASCII string constants"):
                    aa._data_values("'RR'", directive)

    def test_native_backslash_and_non_ascii_refused(self):
        with self.assertRaisesRegex(ProgramError, "backslash"):
            aa._data_values("'a\\b'", "db")
        with self.assertRaisesRegex(ProgramError, "backslash"):
            aa._data_values('"a\\b"', "db")
        with self.assertRaisesRegex(ProgramError,
                                    "Only db supports ASCII string constants"):
            aa._data_values("'éé'", "db")

    def test_native_full_program_db_single_quoted(self):
        profile = aa.prepare_program(_source("db '======>G25'"), bitness=64)
        node = next(n for n in profile["enable"] if n["op"] == "data")
        self.assertEqual(node["values"], ["'======>G25'"])
        self.assertEqual(_literal_bytes(node, None, profile), b"======>G25")
        aa.validate_program(profile)


class SingleQuotedInstructionOperandTests(unittest.TestCase):
    def test_multichar_string_encodes_as_little_endian_integer(self):
        self.assertEqual(aa._operand_tokens("[rcx+rdx],'Ryo '"),
                         ["[", "rcx", "+", "rdx", "]", ",", "0x206F7952"])

    def test_single_char_behavior_unchanged(self):
        self.assertEqual(aa._operand_tokens("'R'"), ["0x52"])

    def test_two_char_string(self):
        self.assertEqual(aa._operand_tokens("'do'"), ["0x6F64"])

    def test_full_instruction_with_string_immediate(self):
        profile = aa.prepare_program(_source("mov [rcx+rdx],'Akir'"), bitness=64)
        inst = next(n for n in profile["enable"] if n["op"] == "instruction")
        self.assertEqual(inst["text"], "mov [rcx+rdx],'Akir'")
        aa.validate_program(profile)

    def test_oversized_string_refused(self):
        with self.assertRaisesRegex(ProgramError, "1–8 printable ASCII bytes"):
            aa._operand_tokens("'123456789'")

    def test_backslash_refused_in_operand(self):
        with self.assertRaisesRegex(ProgramError, "backslash"):
            aa._operand_tokens("'a\\b'")

    def test_non_printable_refused_in_operand(self):
        with self.assertRaisesRegex(ProgramError, "printable ASCII byte"):
            aa._operand_tokens("'é'")
        with self.assertRaisesRegex(ProgramError, "1–8 printable ASCII bytes"):
            aa._operand_tokens("'a\t'")
        with self.assertRaisesRegex(ProgramError, "1–8 printable ASCII bytes"):
            aa._operand_tokens("''")

    def test_unterminated_quoted_operand_refused(self):
        with self.assertRaisesRegex(ProgramError, "Unsupported instruction operand"):
            aa._operand_tokens("'R")


if __name__ == "__main__":
    unittest.main()
