"""RT-4.6: optional user-symbol import (compile-time map + runtime seed).

An operator may import static symbol -> address pairs for requirements that
no record registers.  The import joins the same zero-candidate fallback as
the table-level <UserdefinedSymbols> map (no record dependency arises), is
emitted into the plan as the residual ``user_symbols`` field (record
providers always win), is strict-validated by both plan validators, and is
seeded into the runtime symbol table by the engine after the UDS seed, so
an explicit import overrides a table-level definition of the same name.
"""
from __future__ import annotations

from copy import deepcopy
import json
import tempfile
import unittest
from pathlib import Path
import xml.sax.saxutils

from test_native_engine import FakeMemory

from ct2trainer.native.compiler import (MAX_UDS_ENTRIES, NativeCompileError,
                                        _normalize_user_symbols, compile_table,
                                        load_user_symbols, validate_plan)
from ct2trainer.native.engine import (NativeRuntimeError, TrainerEngine,
                                      validate_plan as validate_runtime_plan)


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


class UserSymbolNormalizeTests(unittest.TestCase):
    """Compile-time validation of the optional import map."""

    def test_none_stays_empty(self):
        self.assertEqual(_normalize_user_symbols(None), {})

    def test_valid_map_is_casefolded(self):
        self.assertEqual(
            _normalize_user_symbols({"ImportedSym": 0x1020, "Other": 5}),
            {"importedsym": 0x1020, "other": 5},
        )

    def test_non_mapping_is_refused(self):
        for bad in ([("ImportedSym", 1)], "ImportedSym", 42):
            with self.assertRaisesRegex(NativeCompileError, "mapping"):
                _normalize_user_symbols(bad)

    def test_oversized_map_is_refused(self):
        bad = {f"S{i}": i for i in range(MAX_UDS_ENTRIES + 1)}
        with self.assertRaisesRegex(NativeCompileError,
                                    f"at most {MAX_UDS_ENTRIES}"):
            _normalize_user_symbols(bad)

    def test_non_string_or_empty_name_is_refused(self):
        for bad in ({123: 1}, {"": 1}):
            with self.assertRaisesRegex(NativeCompileError, "nonempty text"):
                _normalize_user_symbols(bad)

    def test_invalid_symbol_names_are_refused(self):
        with self.assertRaisesRegex(NativeCompileError,
                                    "All-hexadecimal"):
            _normalize_user_symbols({"DEADBEEF": 1})
        # RT-4.3 (O10): dots are admitted in symbol names; the hyphen is
        # still outside the identifier contract.
        with self.assertRaisesRegex(NativeCompileError,
                                    "digits, underscores or dots"):
            _normalize_user_symbols({"my-sym": 1})

    def test_out_of_range_or_non_integer_addresses_are_refused(self):
        for bad in (-1, 1 << 64, "0x1000", 1.0, True):
            with self.assertRaisesRegex(NativeCompileError,
                                        "64-bit unsigned"):
                _normalize_user_symbols({"Sym": bad})

    def test_duplicate_casefold_name_is_refused(self):
        with self.assertRaisesRegex(NativeCompileError,
                                    "Duplicate user-symbol name"):
            _normalize_user_symbols({"Sym": 1, "SYM": 2})


class LoadUserSymbolsTests(unittest.TestCase):
    """The JSON import file: decimal/hex strings and bare integers."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="ct2-rt46-usfile-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def write_json(self, name: str, payload) -> Path:
        path = self.root / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_integer_values_pass_through(self):
        path = self.write_json("ints.json", {"SymA": 12345})
        self.assertEqual(load_user_symbols(path), {"SymA": 12345})

    def test_hex_and_dollar_strings(self):
        path = self.write_json("hex.json", {"SymB": "0x1040",
                                            "SymC": "$2000",
                                            "SymD": "0XFF"})
        self.assertEqual(load_user_symbols(path),
                         {"SymB": 0x1040, "SymC": 0x2000, "SymD": 0xFF})

    def test_decimal_strings(self):
        path = self.write_json("dec.json", {"SymE": "4096"})
        self.assertEqual(load_user_symbols(path), {"SymE": 4096})

    def test_invalid_string_is_refused(self):
        for bad in ("0xZZ", "not-hex", "12.5", ""):
            path = self.write_json("bad.json", {"SymF": bad})
            with self.assertRaisesRegex(
                    NativeCompileError,
                    "must be a decimal integer or a 0x/\\$ hex string"):
                load_user_symbols(path)

    def test_non_object_json_is_refused(self):
        path = self.write_json("list.json", [{"SymG": 1}])
        with self.assertRaisesRegex(NativeCompileError, "JSON object"):
            load_user_symbols(path)

    def test_malformed_or_missing_file_is_refused(self):
        bad = self.root / "malformed.json"
        bad.write_text("{", encoding="utf-8")
        with self.assertRaisesRegex(NativeCompileError,
                                    "not readable JSON"):
            load_user_symbols(bad)
        with self.assertRaisesRegex(NativeCompileError, "not readable JSON"):
            load_user_symbols(self.root / "missing.json")


class UserSymbolProviderSemanticsTests(unittest.TestCase):
    """Imported symbols act as table-level static definitions; records win."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="ct2-rt46-ussem-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def write_ct(self, name: str, body: str, uds: str = "") -> Path:
        path = self.root / name
        suffix = f"</CheatEntries>{uds}" if uds else "</CheatEntries>"
        path.write_text(
            table_xml(body).replace("</CheatEntries>", suffix),
            encoding="utf-8")
        return path

    def test_import_only_value_record_is_unblocked(self):
        path = self.write_ct("import-only.ct",
                             value_entry(1, "Import value", "ImportedSym"))
        plan = compile_table(str(path), PROCESS,
                             user_symbols={"ImportedSym": 0x1020})
        entry = plan["entries"][0]
        self.assertTrue(entry["supported"], entry["reason"])
        self.assertEqual(entry["dependency_ids"], [])
        self.assertEqual(plan["user_symbols"], {"importedsym": 0x1020})
        self.assertNotIn(
            "Required symbol",
            " ".join(plan.get("blocked_reasons", ())),
        )

    def test_import_symbol_is_resolvable_in_address_expression(self):
        path = self.write_ct("import-expr.ct",
                             value_entry(1, "Import value +10",
                                         "ImportedSym+10"))
        plan = compile_table(str(path), PROCESS,
                             user_symbols={"ImportedSym": 0x1020})
        entry = plan["entries"][0]
        self.assertTrue(entry["supported"], entry["reason"])
        self.assertEqual(entry["requires"], ["ImportedSym"])
        self.assertEqual(entry["dependency_ids"], [])

    def test_script_provider_beats_imported_symbol(self):
        path = self.write_ct(
            "script-wins.ct",
            alloc_provider_entry(2, "Provider", "SharedSym")
            + value_entry(1, "Consumer", "SharedSym"))
        plan = compile_table(str(path), PROCESS,
                             user_symbols={"SharedSym": 0x2000})
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        # The record provider wins: the consumer is staged against record 2
        # and the imported symbol stays out of the plan field.
        self.assertTrue(by_id[1]["supported"], by_id[1]["reason"])
        self.assertEqual(by_id[1]["dependency_ids"], [2])
        self.assertNotIn("user_symbols", plan)

    def test_default_plan_has_no_user_symbols_field(self):
        path = self.write_ct("plain.ct", value_entry(1, "Plain", "1000"))
        plan = compile_table(str(path), PROCESS)
        self.assertNotIn("user_symbols", plan)

    def test_unregistered_symbol_without_import_keeps_the_actionable_report(self):
        # Without the import the same record is blocked with the RT-4.6
        # actionable per-symbol report.
        path = self.write_ct("missing.ct",
                             value_entry(1, "Import value", "ImportedSym"))
        plan = compile_table(str(path), PROCESS)
        entry = plan["entries"][0]
        self.assertFalse(entry["supported"])
        self.assertIn(
            "is not registered anywhere in this table", entry["reason"])


class UserSymbolPlanValidationTests(unittest.TestCase):
    """The plan field is strict-validated by both plan validators."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="ct2-rt46-usplan-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        path = self.root / "base.ct"
        path.write_text(
            table_xml(value_entry(1, "Import value", "ImportedSym")),
            encoding="utf-8")
        self.plan = compile_table(str(path), PROCESS,
                                  user_symbols={"ImportedSym": 0x1020})

    def mutate(self, user_map) -> dict:
        plan = deepcopy(self.plan)
        if user_map is None:
            plan.pop("user_symbols", None)
        else:
            plan["user_symbols"] = user_map
        return plan

    def test_valid_map_passes_both_validators(self):
        validate_plan(self.plan)
        validate_runtime_plan(self.plan)

    def test_map_without_its_field_passes_both_validators(self):
        # The field is optional: a plan with no user-symbol requirement and
        # no user_symbols field passes both validators.
        path = self.root / "plain.ct"
        path.write_text(
            table_xml(value_entry(1, "Plain", "1000")),
            encoding="utf-8")
        plan = compile_table(str(path), PROCESS)
        self.assertNotIn("user_symbols", plan)
        validate_plan(plan)
        validate_runtime_plan(plan)

    def test_dropping_the_field_of_a_requiring_plan_is_refused(self):
        # Fail-closed: a record that requires an imported symbol cannot lose
        # the map (the runtime validator walks the live requirement graph).
        plan = self.mutate(None)
        with self.assertRaisesRegex(
                NativeRuntimeError, "unavailable symbol"):
            validate_runtime_plan(plan)

    def test_forged_shadowing_of_record_provider_is_refused(self):
        path = self.root / "shadow.ct"
        path.write_text(
            table_xml(
                alloc_provider_entry(2, "Provider", "UdsBase")
                + value_entry(1, "Consumer", "UdsBase")),
            encoding="utf-8")
        plan = compile_table(str(path), PROCESS,
                             user_symbols={"UdsBase": 0x10000000})
        # The honest plan excludes the record-provided symbol ...
        self.assertNotIn("user_symbols", plan)
        # ... and a forged plan that reintroduces it is refused by both
        # validators (the engine validator delegates to the compiler's).
        forged = deepcopy(plan)
        forged["user_symbols"] = {"udsbase": 0x10000000}
        with self.assertRaisesRegex(NativeCompileError, "may not shadow"):
            validate_plan(forged)
        with self.assertRaisesRegex(NativeRuntimeError, "may not shadow"):
            validate_runtime_plan(forged)

    def test_out_of_range_value_is_refused(self):
        plan = self.mutate({"importedsym": 1 << 64})
        with self.assertRaisesRegex(NativeCompileError, "64-bit unsigned"):
            validate_plan(plan)
        with self.assertRaisesRegex(NativeRuntimeError, "64-bit unsigned"):
            validate_runtime_plan(plan)

    def test_negative_and_non_integer_values_are_refused(self):
        for value in (-1, 1.0, "1024"):
            plan = self.mutate({"importedsym": value})
            with self.assertRaisesRegex(NativeCompileError,
                                        "64-bit unsigned"):
                validate_plan(plan)

    def test_duplicate_casefold_key_is_refused(self):
        plan = self.mutate({"ImportedSym": 0x1020, "IMPORTEDSYM": 0x2000})
        with self.assertRaisesRegex(NativeCompileError,
                                    "Duplicate user symbol name"):
            validate_plan(plan)

    def test_invalid_symbol_key_is_refused(self):
        # RT-4.3 (O10): a digit-leading key is now a valid CE identifier
        # (the name stops parsing as hex at its first non-hex character),
        # so it must pass; the hyphenated key stays refused.
        plan = self.mutate({"123sym": 0x1020})
        validate_plan(plan)
        plan = self.mutate({"my-sym": 0x1020})
        with self.assertRaisesRegex(NativeCompileError,
                                    "digits, underscores or dots"):
            validate_plan(plan)
        plan = self.mutate({"DEADBEEF": 0x1020})
        with self.assertRaisesRegex(NativeCompileError,
                                    "All-hexadecimal"):
            validate_plan(plan)

    def test_unbounded_map_is_refused(self):
        plan = self.mutate({f"S{i}": i for i in range(MAX_UDS_ENTRIES + 1)})
        with self.assertRaisesRegex(NativeCompileError,
                                    "bounded symbol map"):
            validate_plan(plan)


class UserSymbolEngineTests(unittest.TestCase):
    """The engine seeds the runtime symbol table from the plan's import map."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="ct2-rt46-useng-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.state_dir = self.root / "state"
        self.shared = self.root / "shared"
        path = self.root / "seed.ct"
        path.write_text(
            table_xml(value_entry(1, "Import value", "ImportedSym")),
            encoding="utf-8")
        self.plan = compile_table(str(path), PROCESS,
                                  user_symbols={"ImportedSym": 0x1020})

    def test_engine_seeds_casefolded_user_symbols_at_init(self):
        engine = TrainerEngine(self.plan, self.state_dir,
                               lambda _name: None, self.shared)
        self.addCleanup(engine.close)
        # The plan field is casefolded; the seed keys are too, and the value
        # record's address expression resolves against it.
        self.assertEqual(engine.symbols.get("importedsym"), 0x1020)
        self.assertNotIn("ImportedSym", engine.symbols)

    def test_user_symbol_overrides_uds_definition_of_same_name(self):
        # Table-level UDS 0x1000 plus an operator import 0x2000: the import
        # is seeded after the UDS seed and wins the collision.
        path = self.root / "collision.ct"
        path.write_text(
            table_xml(value_entry(1, "Import value", "ImportedSym")).replace(
                "</CheatEntries>",
                "</CheatEntries>"
                + uds_section(uds_entry("ImportedSym", "1000"))),
            encoding="utf-8")
        plan = compile_table(str(path), PROCESS,
                             user_symbols={"ImportedSym": 0x2000})
        self.assertEqual(plan["user_defined_symbols"],
                         {"importedsym": 0x1000})
        self.assertEqual(plan["user_symbols"], {"importedsym": 0x2000})
        engine = TrainerEngine(plan, self.root / "state-collision",
                               lambda _name: None, self.shared)
        self.addCleanup(engine.close)
        self.assertEqual(engine.symbols.get("importedsym"), 0x2000)

    def test_engine_does_not_seed_symbols_provided_by_records(self):
        path = self.root / "shadow.ct"
        path.write_text(
            table_xml(
                alloc_provider_entry(2, "Provider", "UdsBase")
                + value_entry(1, "Consumer", "UdsBase")),
            encoding="utf-8")
        plan = compile_table(str(path), PROCESS,
                             user_symbols={"UdsBase": 0x10000000})
        self.assertNotIn("user_symbols", plan)
        engine = TrainerEngine(plan, self.root / "state-shadow",
                               lambda _name: None, self.shared)
        self.addCleanup(engine.close)
        self.assertNotIn("udsbase", engine.symbols)

    def test_set_value_roundtrip_proves_the_runtime_seed_path(self):
        # The seeded import address is what the value write lands on: a
        # round-trip through set_value/read_value proves the runtime
        # resolution, not just the seed map.
        memory = FakeMemory()
        engine = TrainerEngine(self.plan, self.root / "state-roundtrip",
                               lambda _name: memory, self.shared)
        self.addCleanup(engine.close)
        engine.poll()
        self.assertTrue(engine.connected, engine.status)
        self.assertEqual(engine.set_value(1, "4321"), "4321")
        self.assertEqual(engine.read_value(1), "4321")
        # The "4 Bytes" value is decimal by default (RT-4.4 value
        # semantics): 4321 = 0x10E1, little-endian.
        self.assertEqual(
            bytes(memory.data[0x20:0x24]), bytes.fromhex("e1100000"))


if __name__ == "__main__":
    unittest.main()
