"""Post-0.44 residual lane: the CE 7.5 trailing-offset parity.

The five 'Unexpected trailing address expression tokens.' rows of the
post-0.46 census (qt-ds-1 / qt-ds-2 records 130674 + 130675: the
``[mats]20`` / ``[mats]28`` value-record addresses next to the supported
``[mats]+8`` / ``[mats]+10`` / ``[mats]+18`` siblings) are closed by the
bounded grammar extension in ``address_expression.parse_expression``:
one value atom directly after a ``]`` token takes an implicit ``+``
operand, mirroring CE ``TSymhandler`` (symbolhandler.pas L3073-3140
tokenize, L5516-5553 ``]`` dereference, L5603-5655 arithmetic with ``+``
as the default operation: ``[mats]20`` reads as ``[mats]+0x20``, hex
default).

Covered:
- byte-stability: ``[mats]20`` parses to the exact same AST as
  ``[mats]+20`` and resolves byte-exactly (deref + 0x20); the explicit
  forms ``[mats]`` / ``[mats]+20`` / ``[mats]-20`` / ``[mats]*20`` /
  ``[mats]/20`` / ``[[a]]`` keep their exact ASTs.
- the CE hex default: ``[mats]2f`` is 0x2F, not decimal 29.
- the symbol / deref value atoms: ``[mats]cat`` and ``[mats][dog]``
  (CE resolves the two dereferences and adds them).
- the clean-room extensions, documented as such: ``[[a]20]`` parses as
  ``[[a]+20]`` (CE's nested digit-merge concatenates the hex digits) and
  a quoted module atom after ``]``.
- the named fail-closed refusals that stay: 0x/$/#-prefixed numbers
  (CE's StrToQWordEx arithmetic rejects them), a ``(`` after ``]`` (CE's
  record-by-description lookup path, L5461-5494, out of parity scope),
  a longer bare trailing run, and the rayman 'Made by' string address.
- the plan level: the synthetic qt-ds shape (``alloc(mats,8,...)`` +
  ``registersymbol(mats)`` + the two trailing-offset records) is fully
  supported with the symbol requirement, and the refused shapes keep
  the exact named block reason.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ct2trainer.native.address_expression import (
    AddressExpressionError,
    expression_symbols,
    parse_expression,
    resolve_expression,
)
from ct2trainer.native.compiler import compile_table, validate_plan
from ct2trainer.native.engine import validate_plan as validate_engine_plan

PROCESS = "FixtureTarget.exe"

SYMBOL = 0x1000
POINTER = 0x2000


class FakePointerMemory:
    """8-byte pointer memory: read() always returns the seeded pointer."""

    pointer_size = 8

    def __init__(self, pointer=POINTER):
        self.pointer = pointer
        self.reads = []

    def read(self, address, size):
        if size not in (4, 8):
            raise OSError("Invalid read size")
        self.reads.append((address, size))
        return self.pointer.to_bytes(size, "little")

    def write(self, address, raw):
        raise OSError("No writes in the trailing-offset proof")


def _refused(text, message):
    with unittest.TestCase().assertRaises(AddressExpressionError) as caught:
        parse_expression(text)
    assert str(caught.exception) == message, (text, str(caught.exception))


class TrailingOffsetGrammarTests(unittest.TestCase):
    """parse_expression: the implicit '+' after a closing bracket."""

    def test_trailing_hex_offset_is_ast_identical_to_explicit_plus(self):
        expected = {
            "kind": "binary", "operator": "+",
            "left": {"kind": "deref",
                     "value": {"kind": "symbol", "name": "mats"}},
            "right": {"kind": "integer", "value": 0x20},
        }
        self.assertEqual(parse_expression("[mats]20"), expected)
        self.assertEqual(parse_expression("[mats]+20"), expected)

    def test_trailing_offset_keeps_the_ce_hex_default(self):
        self.assertEqual(
            parse_expression("[mats]2f"),
            {"kind": "binary", "operator": "+",
             "left": {"kind": "deref",
                      "value": {"kind": "symbol", "name": "mats"}},
             "right": {"kind": "integer", "value": 0x2F}})

    def test_trailing_symbol_atom(self):
        # "cat" carries a non-hex character, so it tokenizes as a symbol
        # (the unsized dialect stays hex-by-default for bare hex runs).
        self.assertEqual(
            parse_expression("[mats]cat"),
            parse_expression("[mats]+cat"))
        self.assertEqual(
            parse_expression("[mats]cat"),
            {"kind": "binary", "operator": "+",
             "left": {"kind": "deref",
                      "value": {"kind": "symbol", "name": "mats"}},
             "right": {"kind": "symbol", "name": "cat"}})

    def test_trailing_deref_atom(self):
        # CE resolves both dereferences and adds their values; the clean
        # room equivalent is the explicit '+' form.
        self.assertEqual(
            parse_expression("[mats][dog]"),
            parse_expression("[mats]+[dog]"))

    def test_nested_trailing_is_a_documented_clean_room_extension(self):
        # CE's nested digit-merge concatenates the hex digits
        # ("[[mats]20]" -> the pointer value with "20" appended); the
        # bounded extension parses it as the regular [[mats]+20] instead.
        self.assertEqual(
            parse_expression("[[mats]20]"),
            parse_expression("[[mats]+20]"))

    def test_explicit_forms_keep_their_exact_asts(self):
        self.assertEqual(
            parse_expression("[mats]"),
            {"kind": "deref",
             "value": {"kind": "symbol", "name": "mats"}})
        self.assertEqual(
            parse_expression("[mats]+20"),
            {"kind": "binary", "operator": "+",
             "left": {"kind": "deref",
                      "value": {"kind": "symbol", "name": "mats"}},
             "right": {"kind": "integer", "value": 0x20}})
        self.assertEqual(
            parse_expression("[mats]-20"),
            {"kind": "binary", "operator": "-",
             "left": {"kind": "deref",
                      "value": {"kind": "symbol", "name": "mats"}},
             "right": {"kind": "integer", "value": 0x20}})
        self.assertEqual(
            parse_expression("[mats]*20"),
            {"kind": "binary", "operator": "*",
             "left": {"kind": "deref",
                      "value": {"kind": "symbol", "name": "mats"}},
             "right": {"kind": "integer", "value": 0x20}})
        self.assertEqual(
            parse_expression("[mats]/20"),
            {"kind": "binary", "operator": "/",
             "left": {"kind": "deref",
                      "value": {"kind": "symbol", "name": "mats"}},
             "right": {"kind": "integer", "value": 0x20}})
        self.assertEqual(
            parse_expression("[[mats]]"),
            {"kind": "deref",
             "value": {"kind": "deref",
                       "value": {"kind": "symbol", "name": "mats"}}})

    def test_trailing_offset_then_explicit_operator(self):
        # "[a]20+30" reads as ([a]+20)+30 in CE (the arithmetic
        # accumulation adds 20 and 30 over the deref); "[a]20-30" and
        # "[a]20*4" keep the CE precedence (multiplication first).
        parsed = parse_expression("[a]20+30")
        self.assertEqual(parsed["operator"], "+")
        self.assertEqual(parsed["right"],
                         {"kind": "integer", "value": 0x30})
        self.assertEqual(parse_expression("[a]20-30"),
                         parse_expression("[a]+20-30"))
        self.assertEqual(parse_expression("[a]20*4"),
                         parse_expression("[a]+20*4"))

    def test_expression_symbols_pick_up_the_dereferenced_symbol(self):
        self.assertEqual(expression_symbols("[mats]20"), ["mats"])
        self.assertEqual(expression_symbols("[mats]+20"), ["mats"])

    def test_prefixed_numbers_after_bracket_stay_refused(self):
        # CE's StrToQWordEx('$'+token) arithmetic rejects every
        # 0x/$/# spelling; the refusal stays fail-closed.
        for text in ("[mats]0x20", "[mats]0X20", "[mats]$20", "[mats]#42"):
            _refused(text, "Unexpected trailing address expression tokens.")

    def test_paren_after_bracket_stays_refused(self):
        # CE's "(" after "]" is the record-by-description lookup path
        # (symbolhandler.pas L5461-5494), out of parity scope.
        for text in ("[a](b)", "[a](byte)b"):
            _refused(text, "Unexpected trailing address expression tokens.")

    def test_longer_bare_trailing_run_stays_refused(self):
        _refused("[a]20 b", "Unexpected trailing address expression tokens.")

    def test_repeated_bracket_stays_refused(self):
        _refused("[a]]", "Unexpected trailing address expression tokens.")

    def test_unbalanced_forms_stay_refused(self):
        _refused("[a", "Unbalanced address brackets.")
        _refused("a]", "Unexpected trailing address expression tokens.")

    def test_rayman_made_by_string_address_stays_refused(self):
        # The rayman 'Made by' string record: two bare atoms without a
        # closing bracket - the fix ("]"-anchored) does not touch it.
        _refused("Made by", "Unexpected trailing address expression tokens.")


class TrailingOffsetResolutionTests(unittest.TestCase):
    """resolve_expression: byte-exact deref + implicit offset."""

    def _symbols(self):
        return {"mats": SYMBOL}

    def test_corpus_shapes_resolve_byte_exactly(self):
        memory = FakePointerMemory()
        self.assertEqual(
            resolve_expression("[mats]20", memory, self._symbols()),
            POINTER + 0x20)
        self.assertEqual(
            resolve_expression("[mats]28", memory, self._symbols()),
            POINTER + 0x28)
        self.assertEqual(memory.reads, [(SYMBOL, 8), (SYMBOL, 8)])

    def test_identical_to_the_explicit_plus_form(self):
        implicit = FakePointerMemory()
        explicit = FakePointerMemory()
        self.assertEqual(
            resolve_expression("[mats]20", implicit, self._symbols()),
            resolve_expression("[mats]+20", explicit, self._symbols()))
        self.assertEqual(implicit.reads, explicit.reads)

    def test_trailing_offset_then_explicit_arithmetic(self):
        for text, expected in (("[mats]20+30", POINTER + 0x50),
                               ("[mats]20-30", POINTER - 0x10),
                               ("[mats]20*4", POINTER + 0x80)):
            self.assertEqual(
                resolve_expression(text, FakePointerMemory(), self._symbols()),
                expected, text)


# The synthetic table mirrors the qt-ds shape: one AA record allocating
# and registering "mats", then the value records with the trailing-
# offset addresses next to their explicit-plus siblings.
SYMBOL_SCRIPT = (
    '<CheatEntry><ID>1</ID><Description>"Symbol provider"'
    '</Description><VariableType>Auto Assembler Script'
    '</VariableType><AssemblerScript>'
    '[ENABLE]'
    '\nalloc(mats,8,' + PROCESS + ')'
    '\nregistersymbol(mats)'
    '\nmats:'
    '\ndd 0'
    '\n[DISABLE]'
    '\ndd 0'
    '\ndealloc(mats)'
    '\nunregistersymbol(mats)'
    '</AssemblerScript></CheatEntry>')


def value(record_id, label, address, variable_type="4 Bytes"):
    return (
        f'<CheatEntry><ID>{record_id}</ID><Description>"{label}"'
        f'</Description><VariableType>{variable_type}</VariableType>'
        f'<Address>{address}</Address></CheatEntry>')


class TrailingOffsetPlanTests(unittest.TestCase):
    """compile_table: the qt-ds census rows supported, refusals named."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def _compile(self, body):
        table = self.root / "trailing.ct"
        table.write_text(
            '<CheatTable CheatEngineTableVersion="45">'
            '<CheatEntries>' + body + '</CheatEntries></CheatTable>',
            encoding="utf-8")
        plan = compile_table(table, PROCESS)
        validate_plan(plan)
        validate_engine_plan(plan)
        return plan

    def test_trailing_offset_records_are_supported(self):
        plan = self._compile(
            SYMBOL_SCRIPT
            + value(2, "Explicit plus", "[mats]+20")
            + value(3, "Trailing 20", "[mats]20")
            + value(4, "Trailing 28", "[mats]28")
            + value(5, "Plain deref", "[mats]"))
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        for record_id in (2, 3, 4, 5):
            self.assertTrue(by_id[record_id]["supported"],
                            by_id[record_id]["reason"])
            self.assertEqual(by_id[record_id]["requires"], ["mats"])
        self.assertEqual(by_id[3]["address"], "[mats]20")
        self.assertEqual(by_id[4]["address"], "[mats]28")
        self.assertEqual(by_id[1]["supported"], True, by_id[1]["reason"])

    def test_refused_shapes_keep_the_exact_named_reason(self):
        plan = self._compile(
            SYMBOL_SCRIPT
            + value(2, "Prefixed", "[mats]0x20")
            + value(3, "Paren", "[mats](byte)10")
            + value(4, "Bare run", "[mats]20 b"))
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        for record_id in (2, 3, 4):
            self.assertFalse(by_id[record_id]["supported"])
            self.assertEqual(
                by_id[record_id]["reason"],
                "Unexpected trailing address expression tokens.")


if __name__ == "__main__":
    unittest.main()
