"""RT-4.3: address-expression and identifier dialect wiring (positive proof).

Dedicated lane-contract test file for the RT-4.3 dialect changes, proving
the wiring positively end-to-end on own synthetic fixtures: grammar ->
plan -> engine -> byte-exact effect, plus the new fail-closed refusals
(each refusal asserted to leave the target memory untouched).

Covered classes:
- O10 SYM_CHARS: digit-leading and hyphen-bearing identifiers, .exe/.dll
  module anchors, all-hex name refusal at the label contract.
- O23 QUOTED_ATOM: quoted atoms must be module basenames; refusals name
  the offending token.
- O27 OTHER: multi-segment Type:Member atoms (A:B:C) are managed labels,
  resolved through the injected IL2CPP resolver, refused with an
  actionable error otherwise.
- O3 PTR_OFFSET: pointer-chase slots that are address expressions are
  staged verbatim and resolved against the live symbol table at
  activation.
- O1 RELADDR / O9 RELADDR_NO_ANC: relative values are staged on the
  skip-fold or the runtime-base marker and resolve byte-exactly once the
  group base is written at runtime; forged markers stay fail-closed.
- O13 INDIRECT_DATA: directive-aware string literals (dd/dq/dw) write
  the documented bytes.
"""
from __future__ import annotations

import copy
from pathlib import Path
import struct
import tempfile
import unittest

from test_native_engine import FakeMemory
from test_native_engine_code import Coordinator
from test_native_il2cpp_host import default_base
from test_native_lua_activation import Memory
from test_native_strings import StringMemory
from test_native_value_runtime import DataCoordinator

from ct2trainer.native.aa import AAError, validate_symbol
from ct2trainer.native.address_expression import (
    AddressExpressionError, expression_symbols, is_managed_label,
    parse_expression, resolve_expression)
from ct2trainer.native.compiler import (NativeCompileError, compile_table,
                                        validate_plan)
from ct2trainer.native.engine import (NativeRuntimeError, TrainerEngine,
                                      validate_plan as validate_engine_plan)

PROCESS = "FixtureTarget.exe"


class _MinimalMemory:
    """Expression-level memory stand-in (no target writes are possible)."""

    pointer_size = 8
    base = 0x1000

    def __init__(self, modules=None):
        self.modules = {name.casefold(): (self.base, 0x100)
                        for name in (modules or ())}
        self.exports = {}
        self.export_requests = []

    def module(self, name):
        try:
            return self.modules[name.casefold()]
        except KeyError as exc:
            raise OSError("Unknown module: " + name) from exc

    def resolve_export(self, module, symbol):
        self.export_requests.append((module, symbol))
        try:
            return self.exports[(module.casefold(), symbol.casefold())]
        except KeyError as exc:
            raise OSError("Unknown export") from exc


class ExportAtomTokenTests(unittest.TestCase):
    """Module-qualified export atoms keep their .exe/.dll suffixes (O10)."""

    def test_module_export_atoms_resolve_with_suffix_preserved(self):
        memory = _MinimalMemory()
        memory.exports = {
            ("nativehookfixture.exe", "fixture_result"): 0x1000,
            ("kernel32.dll", "gettickcount64"): 0x1000,
            ("user32.dll", "getasynckeystate"): 0x1000,
        }
        self.assertEqual(
            resolve_expression("NativeHookFixture.exe.fixture_result", memory),
            0x1000)
        self.assertEqual(
            resolve_expression("Kernel32.dll.GetTickCount64", memory), 0x1000)
        self.assertEqual(
            resolve_expression("user32.GetAsyncKeyState", memory), 0x1000)
        self.assertEqual(
            memory.export_requests,
            [("NativeHookFixture.exe", "fixture_result"),
             ("Kernel32.dll", "GetTickCount64"),
             ("user32.dll", "GetAsyncKeyState")])

    def test_module_export_atoms_carry_no_symbol_requirement(self):
        self.assertEqual(
            expression_symbols("Kernel32.dll.GetTickCount64+10"), [])
        self.assertEqual(expression_symbols("user32.GetAsyncKeyState"), [])

    def test_bare_module_grammar_unchanged(self):
        # A plain basename still tokenizes as a module (no export tail).
        parsed = parse_expression("OwnedGame.exe+20")
        self.assertEqual(parsed["kind"], "binary")
        self.assertEqual(parsed["left"], {"kind": "module",
                                          "name": "OwnedGame.exe"})


class IdentifierDialectGrammarTests(unittest.TestCase):
    """O10 identifier strictness, O23 quoted atoms, O27 managed grammar."""

    def test_digit_leading_symbol_names_resolve(self):
        memory = _MinimalMemory()
        # The dialect is hex-literal-first: +10 is +0x10.
        self.assertEqual(
            resolve_expression("8PathSteal+10", memory,
                               {"8PathSteal": 0x1050}), 0x1060)
        self.assertEqual(expression_symbols("8PathSteal"), ["8PathSteal"])
        self.assertEqual(
            parse_expression("20XX"), {"kind": "symbol", "name": "20XX"})

    def test_hyphen_module_bases_resolve(self):
        memory = _MinimalMemory(modules=("Octopath_Traveler-Win64-Shipping.exe",))
        self.assertEqual(
            resolve_expression("Octopath_Traveler-Win64-Shipping.exe+40",
                               memory), 0x1040)
        self.assertEqual(
            expression_symbols("Octopath_Traveler-Win64-Shipping.exe+40"), [])

    def test_all_hex_names_stay_refused_by_the_label_contract(self):
        with self.assertRaises(AAError):
            validate_symbol("AB12")
        self.assertEqual(validate_symbol("AB12g"), "AB12g")
        self.assertEqual(validate_symbol("20XX"), "20XX")

    def test_quoted_atom_must_be_a_module_basename(self):
        memory = _MinimalMemory(modules=("owned.exe",))
        self.assertEqual(resolve_expression('"owned.exe"+20', memory), 0x1020)
        # The corpus typo row: the refusal names the offending token.
        with self.assertRaisesRegex(
                AddressExpressionError,
                r"Quoted atom '\$proces' must be a module basename \(\.exe/\.dll\)\."):
            resolve_expression('"$proces"+20', memory)
        with self.assertRaisesRegex(AddressExpressionError, r"Quoted atom"):
            resolve_expression('"C:\\x\\y.exe"+20', memory)

    def test_multi_segment_managed_label_grammar(self):
        for label in ("Class:Method", "Class::Method", "A:B:C", "A::B::C",
                      "A.B:C:D",
                      "Failbetter.Core.QAssoc.BaseClasses:"
                      "BaseQPossession:set_Flag"):
            with self.subTest(label=label):
                self.assertTrue(is_managed_label(label))
        for label in ("Foo.Bar", "A", "A:", ":A", "A.B.C", "A::"):
            with self.subTest(label=label):
                self.assertFalse(is_managed_label(label))

    def test_managed_label_parse_and_resolution(self):
        memory = _MinimalMemory()
        self.assertEqual(
            parse_expression("A:B:C+10")["left"],
            {"kind": "managed", "name": "A:B:C"})
        self.assertEqual(resolve_expression("A:B:C", memory,
                                            {"A:B:C": 0x1050}), 0x1050)
        # Casefolded lookup, like the ordinary symbol table.
        self.assertEqual(resolve_expression("a:b:c", memory,
                                            {"A:B:C": 0x1050}), 0x1050)
        with self.assertRaisesRegex(
                AddressExpressionError,
                r"Unresolved managed method label: A:B:C\."):
            resolve_expression("A:B:C", memory, {})


class ExpressionOffsetEngineTests(unittest.TestCase):
    """O3: pointer-chase slots that are address expressions (E2E)."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.table = self.root / "offset_expr.ct"
        self.table.write_text(
            '<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
            '<CheatEntry><ID>0</ID><Description>"symbols"'
            '</Description><VariableType>Auto Assembler Script'
            '</VariableType><AssemblerScript>[ENABLE]'
            '\ndefine(pInv,1020)'
            '\nregistersymbol(pInv)'
            '\ndefine(off,4)'
            '\nregistersymbol(off)'
            '\n[DISABLE]'
            '\nunregistersymbol(pInv)'
            '\nunregistersymbol(off)'
            '</AssemblerScript></CheatEntry>'
            '<CheatEntry><ID>1</ID><Description>"chain"'
            '</Description><VariableType>4 Bytes</VariableType>'
            '<Address>pInv</Address>'
            '<Offsets><Offset>28</Offset><Offset>off+4</Offset></Offsets>'
            '</CheatEntry></CheatEntries></CheatTable>',
            encoding="utf-8")
        self.memory = Memory()
        # Pointer chain: read(0x1020) -> 0x1040; + (off+4)=8 -> 0x1048;
        # read(0x1048) -> 0x1050; + 0x28 -> 0x1078 (the 4-byte value).
        self.memory.data[0x20:0x28] = struct.pack("<Q", 0x1040)
        self.memory.data[0x48:0x50] = struct.pack("<Q", 0x1050)
        self.engine = TrainerEngine(
            compile_table(self.table, PROCESS),
            state_dir=self.root / "state",
            process_lock_dir=self.root / "shared",
            memory_factory=lambda name: self.memory,
            hook_coordinator=Coordinator())
        self.engine.poll()

    def tearDown(self):
        if getattr(self, "engine", None) is None:
            return
        self.memory.alive = False
        self.engine.poll()
        self.engine.close()

    def test_plan_keeps_the_expression_slot_verbatim(self):
        entry = self.engine.plan["entries"][1]
        self.assertTrue(entry["supported"], entry["reason"])
        self.assertEqual(entry["pointer_offsets"], [0x28, "off+4"])
        self.assertEqual(entry["requires"], ["pInv", "off"])
        # Both symbols are provided by the same record (one binding each).
        self.assertEqual(entry["dependency_ids"], [0, 0])
        validate_plan(self.engine.plan)
        validate_engine_plan(self.engine.plan)

    def test_expression_offset_chain_writes_the_resolved_byte(self):
        engine = self.engine
        self.assertTrue(engine.toggle(0, True))
        # The live symbol table is keyed casefolded.
        self.assertEqual(engine.symbols["pinv"], 0x1020)
        self.assertEqual(engine.symbols["off"], 4)
        self.assertEqual(engine.read_value(1), "0")
        self.assertEqual(engine.set_value(1, "1234"), "1234")
        self.assertEqual(self.memory.read(0x1078, 4),
                         struct.pack("<I", 1234))
        self.assertEqual(engine.read_value(1), "1234")

    def test_forged_expression_offset_refused_by_both_plan_gates(self):
        forged = copy.deepcopy(self.engine.plan)
        forged["entries"][1]["pointer_offsets"] = [0x28, "no_provider_sym+1"]
        with self.assertRaises(NativeRuntimeError):
            validate_engine_plan(copy.deepcopy(forged))
        with self.assertRaises(NativeCompileError):
            validate_plan(copy.deepcopy(forged))


class RuntimeBaseStagingEngineTests(unittest.TestCase):
    """O1 skip-fold and O9 runtime-base staging (plan + E2E)."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.memory = Memory()
        self.coordinator = Coordinator()

    def _engine(self, table_body):
        table = self.root / "stage.ct"
        table.write_text(
            '<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
            + table_body + '</CheatEntries></CheatTable>',
            encoding="utf-8")
        plan = compile_table(table, PROCESS)
        validate_plan(plan)
        validate_engine_plan(plan)
        engine = TrainerEngine(
            plan, state_dir=self.root / "state",
            process_lock_dir=self.root / "shared",
            memory_factory=lambda name: self.memory,
            hook_coordinator=self.coordinator)
        engine.poll()
        self.assertTrue(engine.connected, engine.status)
        return engine

    def test_o1_skip_fold_stages_over_addressless_intermediate(self):
        engine = self._engine(
            '<CheatEntry><ID>1</ID><Description>"Absolute base"'
            '</Description><VariableType>4 Bytes</VariableType>'
            '<Address>1040</Address>'
            '<CheatEntries>'
            '<CheatEntry><ID>2</ID><Description>"Addressless mid"'
            '</Description><VariableType>Byte</VariableType>'
            '<CheatEntries>'
            '<CheatEntry><ID>3</ID><Description>"Relative kid"'
            '</Description><VariableType>Byte</VariableType>'
            '<Address>+20</Address></CheatEntry>'
            '</CheatEntries>'
            '</CheatEntry>'
            '</CheatEntries>'
            '</CheatEntry>')
        by_id = {entry["id"]: entry for entry in engine.plan["entries"]}
        self.assertTrue(by_id[3]["supported"], by_id[3]["reason"])
        self.assertEqual(by_id[3]["address"], "(1040)+20")
        self.assertEqual(by_id[3]["address_profile"], "expression/v1")
        self.assertEqual(by_id[3]["pointer_offsets"], [])
        self.assertEqual(by_id[3]["requires"], [])
        self.assertNotIn("runtime_base_required", by_id[3])
        # The addressless intermediate keeps its demotion reason.
        self.assertEqual(by_id[2]["kind"], "heading")
        self.assertTrue(by_id[2]["supported"])
        # Byte-exact: the folded base plus the relative offset.
        self.assertEqual(engine.read_value(3), "0")
        self.assertEqual(engine.set_value(3, "7"), "7")
        self.assertEqual(self.memory.read(0x1060, 1), b"\x07")
        # The absolute ancestor stays independently usable.
        self.assertEqual(engine.set_value(1, "5"), "5")
        self.assertEqual(self.memory.read(0x1040, 4),
                         struct.pack("<I", 5))

    def test_o1_forged_relative_without_marker_fails_closed(self):
        engine = self._engine(
            '<CheatEntry><ID>1</ID><Description>"Absolute base"'
            '</Description><VariableType>4 Bytes</VariableType>'
            '<Address>1040</Address>'
            '<CheatEntries>'
            '<CheatEntry><ID>2</ID><Description>"Addressless mid"'
            '</Description><VariableType>Byte</VariableType>'
            '<CheatEntries>'
            '<CheatEntry><ID>3</ID><Description>"Relative kid"'
            '</Description><VariableType>Byte</VariableType>'
            '<Address>+20</Address></CheatEntry>'
            '</CheatEntries>'
            '</CheatEntry>'
            '</CheatEntries>'
            '</CheatEntry>')
        forged = copy.deepcopy(engine.plan)
        forged["entries"][2]["address"] = "+20"
        with self.assertRaises(NativeRuntimeError):
            validate_engine_plan(copy.deepcopy(forged))

    def test_o9_runtime_base_staging_and_live_resolution(self):
        engine = self._engine(
            '<CheatEntry><ID>1</ID><Description>"Base group"'
            '</Description><GroupHeader>1</GroupHeader>'
            '<CheatEntries>'
            '<CheatEntry><ID>2</ID><Description>"Relative value"'
            '</Description><VariableType>4 Bytes</VariableType>'
            '<Address>+20</Address></CheatEntry>'
            '</CheatEntries>'
            '</CheatEntry>'
            '<CheatEntry><ID>3</ID><Description>"Base finder"'
            '</Description><VariableType>Auto Assembler Script'
            '</VariableType><AssemblerScript>[ENABLE]'
            '\nassert(1010,00 00 00 00)'
            '\n1010:'
            '\ndd 1'
            '\n[DISABLE]'
            '\n1010:'
            '\ndd 0'
            '</AssemblerScript></CheatEntry>')
        by_id = {entry["id"]: entry for entry in engine.plan["entries"]}
        self.assertTrue(by_id[2]["supported"], by_id[2]["reason"])
        self.assertEqual(by_id[2]["address"], "+20")
        self.assertTrue(by_id[2]["runtime_base_required"])
        self.assertEqual(by_id[2]["runtime_base_anchor"], 1)
        self.assertEqual(by_id[2]["requires"], [])
        self.assertTrue(by_id[1]["runtime_base_target"])
        self.assertTrue(by_id[3]["supported"], by_id[3]["reason"])
        # Inert until the group base is written; the refusal names the
        # anchor.  No write has happened yet.
        with self.assertRaisesRegex(
                NativeRuntimeError,
                r"Runtime base for group record 1 \('Base group'\) is not "
                r"provided yet"):
            engine.read_value(2)
        self.assertFalse(self.memory.writes)
        # The table's own supported addressless script writes the base.
        engine.set_dynamic_address(1, 0x1040, scope=3)
        self.assertEqual(engine.dynamic_addresses[1], 0x1040)
        self.assertEqual(engine.read_value(2), "0")
        self.assertEqual(engine.set_value(2, "1234"), "1234")
        # anchor base 0x1040 + relative 0x20 -> 0x1060
        self.assertEqual(self.memory.read(0x1060, 4),
                         struct.pack("<I", 1234))
        self.assertEqual(engine.read_value(2), "1234")
        # Clearing the base re-inerts the row.
        engine.set_dynamic_address(1, None, scope=3)
        self.assertEqual(engine.dynamic_addresses, {})
        with self.assertRaisesRegex(
                NativeRuntimeError, "is not provided yet"):
            engine.read_value(2)

    def test_o9_anchor_write_contract(self):
        engine = self._engine(
            '<CheatEntry><ID>1</ID><Description>"Base group"'
            '</Description><GroupHeader>1</GroupHeader>'
            '<CheatEntries>'
            '<CheatEntry><ID>2</ID><Description>"Relative value"'
            '</Description><VariableType>4 Bytes</VariableType>'
            '<Address>+20</Address></CheatEntry>'
            '</CheatEntries>'
            '</CheatEntry>'
            '<CheatEntry><ID>3</ID><Description>"Base finder"'
            '</Description><VariableType>Auto Assembler Script'
            '</VariableType><AssemblerScript>[ENABLE]'
            '\nassert(1010,00 00 00 00)'
            '\n1010:'
            '\ndd 1'
            '\n[DISABLE]'
            '\n1010:'
            '\ndd 0'
            '</AssemblerScript></CheatEntry>')
        # Only a supported addressless script record may write the anchor.
        for scope in (2, 1, 999, None):
            with self.subTest(scope=scope):
                with self.assertRaisesRegex(
                        NativeRuntimeError,
                        r"Runtime-base anchor write outside the planned "
                        r"provider contract\."):
                    engine.set_dynamic_address(1, 0x1040, scope=scope)
        # A non-anchor record is not writable at all.
        with self.assertRaisesRegex(
                NativeRuntimeError,
                r"Dynamic address write outside the planned provider "
                r"contract\."):
            engine.set_dynamic_address(2, 0x1040, scope=3)
        # Non-integer and out-of-range values keep the range refusal.
        with self.assertRaisesRegex(
                NativeRuntimeError,
                r"Dynamic address must be an integer in address range\."):
            engine.set_dynamic_address(1, "x", scope=3)
        with self.assertRaisesRegex(
                NativeRuntimeError,
                r"Dynamic address must be an integer in address range\."):
            engine.set_dynamic_address(1, 0x999999, scope=3)
        self.assertFalse(self.memory.writes)


class ManagedLabelRuntimeTests(unittest.TestCase):
    """O27: multi-segment managed labels resolve through the resolver."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.base = default_base(64)

    def _memory(self):
        memory = FakeMemory()
        memory.base = self.base
        memory.data = bytearray(0x200)
        memory.data[0x40] = 0x55  # original byte at the patch site
        memory.identity = (memory.pid, memory.creation_time)

        def is_executable(address, size):
            return (self.base + 0x40 <= address
                    and address + size <= self.base + 0x41)

        memory.is_executable = is_executable
        return memory

    def _table(self):
        table = self.root / "managed.ct"
        table.write_text(
            '<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
            '<CheatEntry><ID>500</ID><Description>"Triple managed label"'
            '</Description><VariableType>Auto Assembler Script'
            '</VariableType><AssemblerScript>[ENABLE]'
            '\nA:B:C:'
            '\ndb c3'
            '\n[DISABLE]'
            '\nA:B:C:'
            '\ndb 55'
            '</AssemblerScript></CheatEntry>'
            '</CheatEntries></CheatTable>',
            encoding="utf-8")
        return table

    def test_multi_segment_label_roundtrip_is_byte_exact(self):
        memory = self._memory()
        engine = TrainerEngine(
            compile_table(self._table(), PROCESS),
            state_dir=self.root / "state",
            process_lock_dir=self.root / "shared",
            memory_factory=lambda name: memory,
            hook_coordinator=Coordinator(),
            il2cpp_resolver=lambda label: self.base + 0x40)
        engine.poll()
        self.assertTrue(engine.toggle(500, True))
        self.assertEqual(memory.read(self.base + 0x40, 1), b"\xc3")
        self.assertFalse(engine.toggle(500, False))
        self.assertEqual(memory.read(self.base + 0x40, 1), b"\x55")
        engine.close()

    def test_missing_resolver_refuses_before_any_write(self):
        memory = self._memory()
        engine = TrainerEngine(
            compile_table(self._table(), PROCESS),
            state_dir=self.root / "state",
            process_lock_dir=self.root / "shared",
            memory_factory=lambda name: memory,
            hook_coordinator=Coordinator())
        engine.poll()
        with self.assertRaisesRegex(
                NativeRuntimeError,
                "Managed method labels require an IL2CPP resolver"):
            engine.toggle(500, True)
        self.assertFalse(memory.writes)
        engine.close()

    def test_resolver_without_the_exact_name_refuses(self):
        memory = self._memory()

        def resolver(label):
            # The live binding proves no method for this exact
            # multi-segment name, so the refusal is named per label.
            return None

        engine = TrainerEngine(
            compile_table(self._table(), PROCESS),
            state_dir=self.root / "state",
            process_lock_dir=self.root / "shared",
            memory_factory=lambda name: memory,
            hook_coordinator=Coordinator(),
            il2cpp_resolver=resolver)
        engine.poll()
        with self.assertRaisesRegex(
                NativeRuntimeError,
                r"IL2CPP resolver returned an invalid address for A:B:C\."):
            engine.toggle(500, True)
        self.assertFalse(memory.writes)
        engine.close()


class DirectiveStringEngineTests(unittest.TestCase):
    """O13: directive-aware string literals write the documented bytes."""

    def test_dd_dq_string_literals_are_byte_exact(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        table = root / "directive.ct"
        table.write_text(
            '<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
            '<CheatEntry><ID>600</ID><Description>"directive strings"'
            '</Description><VariableType>Auto Assembler Script'
            '</VariableType><AssemblerScript>[ENABLE]'
            '\nassert(1050,00 00 00 00 00 00 00 00 00 00 00 00)'
            '\n1050:'
            '\ndd \'RRRR\''
            '\ndw \'RR\''
            '\ndq \'Q\''
            '\n[DISABLE]'
            '\n1050:'
            '\ndd 0'
            '\ndw 0,0'
            '\ndq 0'
            '</AssemblerScript></CheatEntry>'
            '</CheatEntries></CheatTable>',
            encoding="utf-8")
        # The pure-literal program is admitted as external committed-RW
        # data (sealed permits, held data coordinator), never as code.
        memory = StringMemory()
        coordinator = DataCoordinator()
        engine = TrainerEngine(
            compile_table(table, PROCESS),
            state_dir=root / "state",
            process_lock_dir=root / "shared",
            memory_factory=lambda name: memory,
            hook_coordinator=coordinator)
        engine.poll()
        self.assertTrue(engine.toggle(600, True))
        # dd: the 4-char string packed little-endian into one unit.
        self.assertEqual(memory.read(0x1050, 4), b"RRRR")
        # dw: UTF-16LE words of any length.
        self.assertEqual(memory.read(0x1054, 4), b"R\x00R\x00")
        # dq: the string zero-padded into one 8-byte unit.
        self.assertEqual(memory.read(0x1058, 8), b"Q" + b"\x00" * 7)
        self.assertFalse(engine.toggle(600, False))
        self.assertEqual(memory.read(0x1050, 4), b"\x00" * 4)
        self.assertEqual(memory.read(0x1054, 4), b"\x00" * 4)
        self.assertEqual(memory.read(0x1058, 8), b"\x00" * 8)
        engine.close()


if __name__ == "__main__":
    unittest.main()
