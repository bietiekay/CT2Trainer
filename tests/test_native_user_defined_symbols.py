"""WP-46 (part 1): table-level <UserdefinedSymbols> interpretation.

Covers the fail-closed SymbolEntry parsing in the table reader, the UDS
provider semantics in the compiler (UDS provides a symbol only when no
supported record provides it; keep-first between record providers stays
untouched), the warning suppression for empty/fully-interpreted sections,
the strict plan-field validation in both plan validators, and the engine
symbol-table seed.
"""
from __future__ import annotations

import zlib
from copy import deepcopy
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path
import xml.sax.saxutils

from ct2trainer.native.compiler import (NativeCompileError, compile_table,
                                        validate_plan)
from ct2trainer.native.engine import (NativeRuntimeError, TrainerEngine,
                                      validate_plan as validate_runtime_plan)
from ct2trainer.table import MAX_UDS_ENTRIES, read_table


PROCESS = "UdsFixture.exe"


def uds_section(*entries: str) -> str:
    return "<UserdefinedSymbols>" + "".join(entries) + "</UserdefinedSymbols>"


def uds_entry(name: str, address: str) -> str:
    return (f"<SymbolEntry><Name>{xml.sax.saxutils.escape(name)}</Name>"
            f"<Address>{xml.sax.saxutils.escape(address)}</Address></SymbolEntry>")


def table_xml(body: str) -> str:
    return (
        '<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
        + body
        + "</CheatEntries></CheatTable>"
    )


def value_entry(entry_id: int, description: str, address: str) -> str:
    return (
        f'<CheatEntry><ID>{entry_id}</ID>'
        f'<Description>{description}</Description>'
        f"<VariableType>4 Bytes</VariableType>"
        f"<Address>{xml.sax.saxutils.escape(address)}</Address></CheatEntry>"
    )


_CE_BASE85_ALPHABET = (
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz!#$%()*+,-./:;=?@[]^_{}"
)


def _embed_file_text(content: bytes) -> str:
    """Raw stored text of one embedded file (RT-5 item A fixture helper):
    Ascii85 (CE alphabet) over the raw-deflate stream of the 4-byte
    little-endian size prefix plus the content."""
    def block(value: int) -> str:
        digits = []
        for _ in range(5):
            value, r = divmod(value, 85)
            digits.append(_CE_BASE85_ALPHABET[r])
        return "".join(reversed(digits))
    out = []
    payload = len(content).to_bytes(4, "little") + content
    raw = zlib.compress(payload, 9)[2:-4]
    i, n = 0, len(raw)
    while i + 4 <= n:
        out.append(block(int.from_bytes(raw[i:i + 4], "big")))
        i += 4
    rem = n - i
    if rem:
        pad = 4 - rem
        value = int.from_bytes(raw[i:i + rem] + (85 ** pad - 1).to_bytes(pad, "big"),
                               "big")
        out.append(block(value)[:5 - pad])
    return "".join(out)


def alloc_provider_entry(entry_id: int, description: str, symbol: str) -> str:
    """A supported allocation-only script record that provides one symbol."""
    script = (
        f"[ENABLE]\n"
        f"alloc({symbol},64)\n"
        f"registersymbol({symbol})\n"
        f"[DISABLE]\n"
        f"unregistersymbol({symbol})\n"
        f"dealloc({symbol})"
    )
    return (
        f'<CheatEntry><ID>{entry_id}</ID>'
        f'<Description>{description}</Description>'
        f"<VariableType>Auto Assembler Script</VariableType>"
        f"<AssemblerScript>{xml.sax.saxutils.escape(script)}</AssemblerScript>"
        f"</CheatEntry>"
    )


class UdsTableParseTests(unittest.TestCase):
    """Fail-closed SymbolEntry parsing in read_table."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="ct2-wp46-uds-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def write_ct(self, name: str, uds: str, body: str) -> Path:
        path = self.root / name
        path.write_text(table_xml(body).replace("</CheatEntries>",
                                                f"</CheatEntries>{uds}"),
                        encoding="utf-8")
        return path

    def test_empty_self_closing_section_yields_no_symbols_and_no_warning(self):
        path = self.write_ct("empty.ct", "<UserdefinedSymbols/>",
                             value_entry(1, "V", "1000"))
        table = read_table(path)
        self.assertEqual(table.user_defined_symbols, ())
        self.assertEqual(table.warnings, ())

    def test_absent_section_yields_no_symbols_and_no_warning(self):
        path = self.root / "absent.ct"
        path.write_text(table_xml(value_entry(1, "V", "1000")), encoding="utf-8")
        table = read_table(path)
        self.assertEqual(table.user_defined_symbols, ())
        self.assertEqual(table.warnings, ())

    def test_valid_hex_entries_are_parsed(self):
        path = self.write_ct(
            "valid.ct",
            uds_section(uds_entry("UdsBase", "10000000"),
                        uds_entry("Prefixed", "0x20000000"),
                        uds_entry("Dollar", "$30000000")),
            value_entry(1, "V", "1000"),
        )
        table = read_table(path)
        self.assertEqual(
            {(s.name, s.address) for s in table.user_defined_symbols},
            {("UdsBase", 0x10000000), ("Prefixed", 0x20000000),
             ("Dollar", 0x30000000)},
        )
        self.assertEqual(table.warnings, ())

    def test_decimal_looking_address_is_read_as_hex(self):
        # CE stores these addresses as hex; a decimal-looking string is
        # ambiguous and is read as hex (documented decision).
        path = self.write_ct("dec.ct", uds_section(uds_entry("DecLike", "12345")),
                             value_entry(1, "V", "1000"))
        table = read_table(path)
        self.assertEqual(table.user_defined_symbols[0].address, 0x12345)
        self.assertEqual(table.warnings, ())

    def test_missing_name_is_ignored_with_named_warning(self):
        path = self.write_ct(
            "noname.ct",
            uds_section(uds_entry("", "10000000"), uds_entry("Good", "20000000")),
            value_entry(1, "V", "1000"),
        )
        table = read_table(path)
        self.assertEqual([s.name for s in table.user_defined_symbols], ["Good"])
        self.assertEqual(
            table.warnings,
            ("UserdefinedSymbols entry 1: missing <Name>; entry ignored.",),
        )

    def test_missing_or_empty_address_is_ignored_with_named_warning(self):
        path = self.write_ct(
            "noaddr.ct",
            uds_section(uds_entry("NoAddr", ""),
                        uds_entry("EmptyAddr", "   ")),
            value_entry(1, "V", "1000"),
        )
        table = read_table(path)
        self.assertEqual(table.user_defined_symbols, ())
        self.assertEqual(
            table.warnings,
            (
                "UserdefinedSymbols entry 'NoAddr': missing or empty "
                "<Address>; entry ignored.",
                "UserdefinedSymbols entry 'EmptyAddr': missing or empty "
                "<Address>; entry ignored.",
            ),
        )

    def test_nonhex_address_is_ignored_with_named_warning(self):
        path = self.write_ct(
            "badaddr.ct",
            uds_section(uds_entry("Dotted", "deadf00.bar"),
                        uds_entry("BadHex", "0xZZ"),
                        uds_entry("TooLong", "1" * 17)),
            value_entry(1, "V", "1000"),
        )
        table = read_table(path)
        self.assertEqual(table.user_defined_symbols, ())
        self.assertEqual(
            table.warnings,
            (
                "UserdefinedSymbols entry 'Dotted': address 'deadf00.bar' "
                "is not a hexadecimal absolute integer; entry ignored.",
                "UserdefinedSymbols entry 'BadHex': address '0xZZ' is not a "
                "hexadecimal absolute integer; entry ignored.",
                "UserdefinedSymbols entry 'TooLong': address '11111111111111111' "
                "is not a hexadecimal absolute integer; entry ignored.",
            ),
        )

    def test_invalid_symbol_names_are_ignored_with_named_warnings(self):
        # All-hex names are ambiguous (validate_symbol contract); names with
        # non-identifier characters are refused as well.
        path = self.write_ct(
            "badname.ct",
            uds_section(uds_entry("DEADBEEF", "10000000"),
                        uds_entry("my-sym", "20000000")),
            value_entry(1, "V", "1000"),
        )
        table = read_table(path)
        self.assertEqual(table.user_defined_symbols, ())
        self.assertEqual(
            table.warnings,
            (
                "UserdefinedSymbols entry 'DEADBEEF': invalid symbol name "
                "(All-hexadecimal symbol names are ambiguous and "
                "unsupported.); entry ignored.",
                "UserdefinedSymbols entry 'my-sym': invalid symbol name "
                "(Symbol must contain ASCII letters, digits, underscores or "
                "dots.); entry ignored.",
            ),
        )

    def test_duplicate_casefold_name_keeps_first_with_warning(self):
        path = self.write_ct(
            "dup.ct",
            uds_section(uds_entry("UdsDup", "10000000"),
                        uds_entry("UDSDUP", "20000000")),
            value_entry(1, "V", "1000"),
        )
        table = read_table(path)
        self.assertEqual(
            [(s.name, s.address) for s in table.user_defined_symbols],
            [("UdsDup", 0x10000000)],
        )
        self.assertEqual(
            table.warnings,
            ("UserdefinedSymbols entry 'UDSDUP': duplicate symbol name "
             "(kept first occurrence); later entry ignored.",),
        )

    def test_oversized_section_is_ignored_with_warning(self):
        entries = "".join(uds_entry(f"S{i}", f"{i:08X}") for i in range(MAX_UDS_ENTRIES + 1))
        path = self.write_ct("overflow.ct", uds_section(entries),
                             value_entry(1, "V", "1000"))
        table = read_table(path)
        self.assertEqual(table.user_defined_symbols, ())
        self.assertEqual(
            table.warnings,
            (f"UserdefinedSymbols section exceeds {MAX_UDS_ENTRIES} "
             f"entries; section ignored.",),
        )

    def test_to_dict_exposes_user_defined_symbols(self):
        path = self.write_ct("dict.ct", uds_section(uds_entry("UdsBase", "10000000")),
                             value_entry(1, "V", "1000"))
        table = read_table(path)
        self.assertEqual(
            table.to_dict()["user_defined_symbols"],
            [{"name": "UdsBase", "address": 0x10000000}],
        )


class UdsProviderSemanticsTests(unittest.TestCase):
    """UDS symbols act as table-level static definitions; record providers win."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="ct2-wp46-sem-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def write_ct(self, name: str, uds: str, body: str) -> Path:
        path = self.root / name
        path.write_text(table_xml(body).replace("</CheatEntries>",
                                                f"</CheatEntries>{uds}"),
                        encoding="utf-8")
        return path

    def test_uds_only_value_record_is_unblocked(self):
        path = self.write_ct(
            "uds-only.ct",
            uds_section(uds_entry("UdsBase", "10000000")),
            value_entry(1, "Uds value", "UdsBase"),
        )
        plan = compile_table(str(path), PROCESS)
        entry = plan["entries"][0]
        self.assertTrue(entry["supported"])
        self.assertEqual(entry["dependency_ids"], [])
        self.assertEqual(plan["user_defined_symbols"], {"udsbase": 0x10000000})
        self.assertNotIn(
            "Required symbol has no unique supported provider",
            plan["blocked_reasons"],
        )

    def test_uds_symbol_is_resolvable_in_address_expression(self):
        path = self.write_ct(
            "uds-expr.ct",
            uds_section(uds_entry("UdsBase", "10000000")),
            value_entry(1, "Uds value +10", "UdsBase+10"),
        )
        plan = compile_table(str(path), PROCESS)
        entry = plan["entries"][0]
        self.assertTrue(entry["supported"])
        self.assertEqual(entry["requires"], ["UdsBase"])
        self.assertEqual(entry["dependency_ids"], [])

    def test_script_provider_beats_uds_symbol(self):
        path = self.write_ct(
            "script-wins.ct",
            uds_section(uds_entry("SharedSym", "20000000")),
            alloc_provider_entry(2, "Provider", "SharedSym")
            + value_entry(1, "Consumer", "SharedSym"),
        )
        plan = compile_table(str(path), PROCESS)
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        # The record provider wins: the consumer is staged against record 2
        # and the UDS symbol stays out of the plan field.
        self.assertTrue(by_id[1]["supported"])
        self.assertEqual(by_id[1]["dependency_ids"], [2])
        self.assertNotIn("user_defined_symbols", plan)

    def test_two_script_providers_keep_first_with_uds_present(self):
        path = self.write_ct(
            "keep-first.ct",
            uds_section(uds_entry("DupSym", "30000000")),
            alloc_provider_entry(2, "First provider", "DupSym")
            + alloc_provider_entry(3, "Second provider", "DupSym")
            + value_entry(1, "Consumer", "DupSym"),
        )
        plan = compile_table(str(path), PROCESS)
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        # Keep-first between the two script providers is unchanged by the
        # UDS entry: the first provider stays the visible provider, the
        # duplicate stays supported (RT-4.1, CE dupIgnore) and the
        # consumer resolves against the kept one.
        self.assertTrue(by_id[2]["supported"])
        self.assertTrue(by_id[3]["supported"], by_id[3]["reason"])
        self.assertTrue(by_id[1]["supported"])
        self.assertEqual(by_id[1]["dependency_ids"], [2])
        self.assertNotIn("user_defined_symbols", plan)

    def test_empty_uds_section_is_byte_stable_in_plan(self):
        # CE 7.x writes the empty tag into every table; it must not add the
        # plan field and must not change the warning set.
        path = self.write_ct(
            "empty-stable.ct",
            "<UserdefinedSymbols/>",
            value_entry(1, "Plain", "1000"),
        )
        plan = compile_table(str(path), PROCESS)
        self.assertNotIn("user_defined_symbols", plan)
        self.assertNotIn("UserdefinedSymbols", plan["ignored_sections"])
        self.assertNotIn(
            "Table-level sections not interpreted",
            " ".join(plan["warnings"]),
        )


class UdsWarningSuppressionTests(unittest.TestCase):
    """The UDS section is interpreted: it never appears in the omission warning."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="ct2-wp46-warn-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def write_ct(self, name: str, extra_sections: str, body: str) -> Path:
        path = self.root / name
        path.write_text(
            table_xml(body).replace("</CheatEntries>",
                                    f"</CheatEntries>{extra_sections}"),
            encoding="utf-8",
        )
        return path

    def test_empty_uds_does_not_enter_omitted_warning(self):
        # RT-5 item A: a decodable embedded file is now interpreted (the
        # plan carries embedded_files), so an empty UDS plus a valid Files
        # section produces no omission warning at all.
        encoded = _embed_file_text(b"fixture license text")
        path = self.write_ct(
            "empty+files.ct",
            '<UserdefinedSymbols/><Files>'
            '<License.txt Encoding="Ascii85">' + encoded +
            "</License.txt></Files>",
            value_entry(1, "Plain", "1000"),
        )
        plan = compile_table(str(path), PROCESS)
        self.assertEqual(plan["ignored_sections"], [])
        self.assertEqual(plan["warnings"], [])
        self.assertEqual(plan["embedded_files"], [{
            "name": "License.txt",
            "encoding": "Ascii85",
            "text": encoded,
            "sha256": sha256(b"fixture license text").hexdigest(),
            "size": 20,
        }])

    def test_fully_interpreted_uds_does_not_enter_omitted_warning(self):
        path = self.write_ct(
            "full+forms.ct",
            uds_section(uds_entry("UdsBase", "10000000")) + "<Forms/>",
            value_entry(1, "Uds value", "UdsBase"),
        )
        plan = compile_table(str(path), PROCESS)
        self.assertEqual(plan["ignored_sections"], ["Forms"])
        self.assertIn("Table-level sections not interpreted: Forms.",
                      plan["warnings"])

    def test_partially_rejected_uds_names_rejected_entries(self):
        path = self.write_ct(
            "partial.ct",
            uds_section(uds_entry("Good", "10000000"),
                        uds_entry("NotHexAddr", "not-hex-at-all")),
            value_entry(1, "Uds value", "Good"),
        )
        plan = compile_table(str(path), PROCESS)
        self.assertTrue(plan["entries"][0]["supported"])
        self.assertIn(
            "UserdefinedSymbols entry 'NotHexAddr': address 'not-hex-at-all' is "
            "not a hexadecimal absolute integer; entry ignored.",
            plan["warnings"],
        )
        self.assertEqual(plan["user_defined_symbols"], {"good": 0x10000000})


class UdsPlanValidationTests(unittest.TestCase):
    """The plan field is strict-validated by both plan validators."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="ct2-wp46-plan-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        path = self.root / "base.ct"
        path.write_text(
            table_xml(
                value_entry(1, "Plain", "1000")
            ).replace("</CheatEntries>",
                      f"</CheatEntries>{uds_section(uds_entry('UdsBase', '10000000'))}"),
            encoding="utf-8",
        )
        self.plan = compile_table(str(path), PROCESS)

    def mutate(self, uds_map) -> dict:
        plan = deepcopy(self.plan)
        if uds_map is None:
            plan.pop("user_defined_symbols", None)
        else:
            plan["user_defined_symbols"] = uds_map
        return plan

    def test_valid_map_passes_both_validators(self):
        validate_plan(self.plan)
        validate_runtime_plan(self.plan)

    def test_map_without_its_field_passes_both_validators(self):
        plan = self.mutate(None)
        validate_plan(plan)
        validate_runtime_plan(plan)

    def test_forged_shadowing_of_record_provider_is_refused(self):
        # Build a plan in which a supported script record provides the same
        # symbol the UDS map claims.
        path = self.root / "shadow.ct"
        path.write_text(
            table_xml(
                alloc_provider_entry(2, "Provider", "UdsBase")
                + value_entry(1, "Consumer", "UdsBase")
            ).replace("</CheatEntries>",
                      f"</CheatEntries>{uds_section(uds_entry('UdsBase', '10000000'))}"),
            encoding="utf-8",
        )
        # The honest plan excludes the record-provided symbol ...
        plan = compile_table(str(path), PROCESS)
        self.assertNotIn("user_defined_symbols", plan)
        # ... and a forged plan that reintroduces it is refused by both
        # validators (the engine validator delegates to the compiler's).
        forged = deepcopy(plan)
        forged["user_defined_symbols"] = {"udsbase": 0x10000000}
        with self.assertRaisesRegex(NativeCompileError, "may not shadow"):
            validate_plan(forged)
        with self.assertRaisesRegex(NativeRuntimeError, "may not shadow"):
            validate_runtime_plan(forged)

    def test_out_of_range_value_is_refused(self):
        plan = self.mutate({"udsbase": (1 << 64)})
        with self.assertRaisesRegex(NativeCompileError, "64-bit unsigned"):
            validate_plan(plan)
        with self.assertRaisesRegex(NativeRuntimeError, "64-bit unsigned"):
            validate_runtime_plan(plan)

    def test_negative_and_non_integer_values_are_refused(self):
        for value in (-1, 1.0, "10000000"):
            plan = self.mutate({"udsbase": value})
            with self.assertRaisesRegex(NativeCompileError, "64-bit unsigned"):
                validate_plan(plan)

    def test_duplicate_casefold_key_is_refused(self):
        plan = self.mutate({"UdsBase": 0x10000000, "UDSBASE": 0x20000000})
        with self.assertRaisesRegex(NativeCompileError,
                                    "Duplicate user-defined symbol name"):
            validate_plan(plan)

    def test_invalid_symbol_key_is_refused(self):
        # RT-4.3 (O10): digit-leading names are now valid symbol names; a
        # hyphen remains outside the grammar.
        plan = self.mutate({"my-sym": 0x10000000})
        with self.assertRaisesRegex(NativeCompileError,
                                    "ASCII letters, digits, underscores or dots"):
            validate_plan(plan)
        plan = self.mutate({"DEADBEEF": 0x10000000})
        with self.assertRaisesRegex(NativeCompileError, "All-hexadecimal"):
            validate_plan(plan)

    def test_unbounded_map_is_refused(self):
        plan = self.mutate({f"S{i}": i for i in range(MAX_UDS_ENTRIES + 1)})
        with self.assertRaisesRegex(NativeCompileError,
                                    "bounded symbol map"):
            validate_plan(plan)


class UdsEngineSeedTests(unittest.TestCase):
    """The engine seeds the runtime symbol table with the plan's UDS map."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="ct2-wp46-eng-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.state_dir = self.root / "state"
        self.shared = self.root / "shared"
        path = self.root / "seed.ct"
        path.write_text(
            table_xml(value_entry(1, "Uds value", "UdsBase")).replace(
                "</CheatEntries>",
                f"</CheatEntries>{uds_section(uds_entry('UdsBase', '10000000'))}",
            ),
            encoding="utf-8",
        )
        self.plan = compile_table(str(path), PROCESS)

    def test_engine_seeds_casefolded_uds_symbols_at_init(self):
        engine = TrainerEngine(self.plan, self.state_dir,
                               lambda _name: None, self.shared)
        self.addCleanup(engine.close)
        # The plan field is casefolded; the seed keys are too, and the value
        # record's address expression resolves against it.
        self.assertEqual(engine.symbols.get("udsbase"), 0x10000000)
        self.assertNotIn("UdsBase", engine.symbols)

    def test_engine_does_not_seed_symbols_provided_by_records(self):
        path = self.root / "shadow.ct"
        path.write_text(
            table_xml(
                alloc_provider_entry(2, "Provider", "UdsBase")
                + value_entry(1, "Consumer", "UdsBase")
            ).replace("</CheatEntries>",
                      f"</CheatEntries>{uds_section(uds_entry('UdsBase', '10000000'))}"),
            encoding="utf-8",
        )
        plan = compile_table(str(path), PROCESS)
        engine = TrainerEngine(plan, self.state_dir / "shadow",
                               lambda _name: None, self.shared)
        self.addCleanup(engine.close)
        self.assertNotIn("udsbase", engine.symbols)


if __name__ == "__main__":
    unittest.main()
