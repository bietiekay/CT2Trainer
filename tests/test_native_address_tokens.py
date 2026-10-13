"""WP-22 + WP-23: address-token grammar (digit-leading modules, ``::`` label alias).

Pinned reference-corpus shapes (gap classes GC-B4 / GC-B5):

- GC-B4 (20XX table, whole table): value-record addresses such as
  ``20XX.exe+47B88B8`` whose module basename starts with a digit.  The
  tokenizer used to split the basename into a bare integer plus a trailing
  identifier, which the parser rejected with
  ``Unexpected trailing address expression tokens.``  The grammar now emits
  the full basename as one module atom (alternative ordered before the
  bare-integer alternative) and resolves it through the existing
  ``memory.module`` path.  A bare digit run without a ``.exe``/``.dll``
  suffix tokenizes and parses exactly as before.
- GC-B5 (Kena, BatmanAK): IL2CPP managed method labels spelled
  ``Class::Method`` in addition to ``Class:Method``.  Both spellings
  classify as ``kind: managed`` with the label kept verbatim and resolve
  through the identical symbol-map / ``il2cpp_resolver`` path; other
  punctuation around the colon segments stays fail-closed.

This file proves the chain grammar -> plan -> engine -> byte-exact effect
on own synthetic fixtures (process token ``ct2synth01.exe``, owned IL2CPP
host binding) and pins every refusal that stays fail-closed.
"""
from pathlib import Path
import copy
import re
import struct
import tempfile
import unittest

from test_native_engine import FakeMemory
from test_native_engine_code import Coordinator
from test_native_il2cpp_host import IDENTITY, default_base, make_host
from test_native_managed_method import ManagedMemory

from ct2trainer.native.address_expression import (
    AddressExpressionError,
    expression_symbols,
    parse_expression,
    resolve_expression,
)
from ct2trainer.native.aa_program import ProgramError, prepare_program, validate_program
from ct2trainer.native.compiler import NativeCompileError, compile_table, validate_plan
from ct2trainer.native.engine import (
    NativeRuntimeError,
    TrainerEngine,
    validate_plan as validate_runtime_plan,
)
from ct2trainer.native.il2cpp_host import AliasSpec


class DigitModuleGrammarTests(unittest.TestCase):
    """WP-22: digit-leading module basenames in the token grammar."""

    def test_module_atom_with_corpus_offset(self):
        self.assertEqual(
            parse_expression("20XX.exe+47B88B8"),
            {"kind": "binary", "operator": "+",
             "left": {"kind": "module", "name": "20XX.exe"},
             "right": {"kind": "integer", "value": 0x47B88B8}})

    def test_module_atom_variants(self):
        for text, name in (("20XX.exe", "20XX.exe"),
                           ("20XX.EXE+10", "20XX.EXE"),
                           ("9game.dll+20", "9game.dll"),
                           ("0.dll", "0.dll"),
                           ("1234.Game.dll+1", "1234.Game.dll")):
            parsed = parse_expression(text)
            atom = parsed if parsed["kind"] == "module" else parsed["left"]
            self.assertEqual(atom["kind"], "module", text)
            self.assertEqual(atom["name"], name, text)

    def test_parenthesized_and_deref_forms(self):
        self.assertEqual(
            parse_expression("(20XX.exe)+10"),
            {"kind": "binary", "operator": "+",
             "left": {"kind": "module", "name": "20XX.exe"},
             "right": {"kind": "integer", "value": 0x10}})
        parsed = parse_expression("[20XX.exe+10]+20")
        self.assertEqual(parsed["kind"], "binary")
        self.assertEqual(parsed["left"]["kind"], "deref")
        self.assertEqual(parsed["left"]["value"]["left"],
                         {"kind": "module", "name": "20XX.exe"})

    def test_module_has_no_symbol_dependency(self):
        self.assertEqual(expression_symbols("20XX.exe+47B88B8"), [])

    def test_resolves_through_existing_module_path(self):
        class Memory:
            pointer_size = 8
            def module(self, name):
                if name.casefold() != "20xx.exe":
                    raise OSError("Unknown module")
                return 0x7FF60000, 0x1000000
        self.assertEqual(
            resolve_expression("20XX.exe+47B88B8", Memory()),
            0x7FF60000 + 0x47B88B8)

    def test_bare_integers_and_offsets_unchanged(self):
        self.assertEqual(parse_expression("20"), {"kind": "integer", "value": 0x20})
        self.assertEqual(
            parse_expression("20+10"),
            {"kind": "binary", "operator": "+",
             "left": {"kind": "integer", "value": 0x20},
             "right": {"kind": "integer", "value": 0x10}})
        self.assertEqual(parse_expression("20AB"), {"kind": "integer", "value": 0x20AB})
        self.assertEqual(parse_expression("$20"), {"kind": "integer", "value": 0x20})
        self.assertEqual(parse_expression("0x20"), {"kind": "integer", "value": 0x20})
        self.assertEqual(parse_expression("#42"), {"kind": "integer", "value": 42})
        self.assertEqual(parse_expression("1000"), {"kind": "integer", "value": 0x1000})

    def test_digit_tokens_without_module_suffix_stay_refused(self):
        for text, message in (("20XX", "Unexpected trailing address expression tokens."),
                              ("20XX.ex+10", "Unexpected trailing address expression tokens."),
                              ("20XX.exe.foo+1", "Invalid address expression near '.foo+1'.")):
            with self.subTest(text=text):
                with self.assertRaisesRegex(AddressExpressionError, re.escape(message)):
                    parse_expression(text)


class DoubleColonLabelGrammarTests(unittest.TestCase):
    """WP-23: ``Class::Method`` alias of the managed method label."""

    def test_single_and_double_colon_parse_as_managed(self):
        self.assertEqual(parse_expression("A:B"), {"kind": "managed", "name": "A:B"})
        self.assertEqual(parse_expression("A::B"), {"kind": "managed", "name": "A::B"})

    def test_offset_attaches_to_double_colon_label(self):
        self.assertEqual(
            parse_expression("A::B+10"),
            {"kind": "binary", "operator": "+",
             "left": {"kind": "managed", "name": "A::B"},
             "right": {"kind": "integer", "value": 0x10}})

    def test_both_spellings_resolve_to_identical_result(self):
        class Memory:
            pointer_size = 8
        symbols = {"A:B": 0x1234, "A::B": 0x1234}
        single = resolve_expression("A:B", Memory(), symbols)
        double = resolve_expression("A::B", Memory(), symbols)
        self.assertEqual(single, 0x1234)
        self.assertEqual(double, 0x1234)
        self.assertEqual(single, double)

    def test_resolution_stays_casefolded_symbol_map_lookup(self):
        class Memory:
            pointer_size = 8
        self.assertEqual(resolve_expression("a::b", Memory(), {"A::B": 0x99}), 0x99)

    def test_unresolved_double_colon_label_is_named_error(self):
        class Memory:
            pointer_size = 8
        with self.assertRaisesRegex(AddressExpressionError,
                                    "Unresolved managed method label: A::B."):
            resolve_expression("A::B", Memory(), {})

    def test_double_colon_has_no_symbol_dependency(self):
        self.assertEqual(expression_symbols("A::B+10"), [])
        self.assertEqual(expression_symbols("A:B+10"), [])

    def test_malformed_colon_forms_stay_refused(self):
        for text, message in (("A:::B", "Invalid address expression near ':::B'."),
                              ("A:B:C", "Invalid address expression near ':C'."),
                              (":B", "Invalid address expression near ':B'."),
                              ("A:", "Invalid address expression near ':'.")):
            with self.subTest(text=text):
                with self.assertRaisesRegex(AddressExpressionError, re.escape(message)):
                    parse_expression(text)

    def test_existing_managed_and_export_forms_unchanged(self):
        self.assertEqual(parse_expression("Namespace.Class.Method"),
                         {"kind": "managed", "name": "Namespace.Class.Method"})
        self.assertEqual(parse_expression("GameEngine.GameInstance"),
                         {"kind": "export", "name": "GameEngine.GameInstance"})

    def test_dotted_export_stays_fail_closed_without_resolver(self):
        class Memory:
            pointer_size = 8
        with self.assertRaisesRegex(
                AddressExpressionError,
                "The memory backend has no remote PE export resolver."):
            resolve_expression("GameEngine.GameInstance", Memory())


class DigitModulePlanTests(unittest.TestCase):
    """Compile level: digit-leading module addresses land in expression/v1."""

    CT_BODY = '''<CheatTable CheatEngineTableVersion="45"><CheatEntries>
<CheatEntry><ID>910</ID><Description>"HP"</Description><VariableType>4 Bytes</VariableType><Address>20XX.exe+47B88B8</Address></CheatEntry>
<CheatEntry><ID>911</ID><Description>"MP"</Description><VariableType>4 Bytes</VariableType><Address>20XX.exe+4699188</Address></CheatEntry>
<CheatEntry><ID>920</ID><Description>"Base group"</Description><GroupHeader>1</GroupHeader><Address>20XX.exe</Address>
<CheatEntries>
<CheatEntry><ID>921</ID><Description>"Score"</Description><VariableType>4 Bytes</VariableType><Address>+40</Address></CheatEntry>
</CheatEntries>
</CheatEntry>
</CheatEntries></CheatTable>'''

    def compile(self, body, process="ct2synth01.exe"):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "owned.ct"
            path.write_text(body, encoding="utf-8")
            return compile_table(path, process)

    def test_digit_module_addresses_compile_as_expression_profile(self):
        plan = self.compile(self.CT_BODY)
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        for identifier, address in ((910, "20XX.exe+47B88B8"),
                                   (911, "20XX.exe+4699188")):
            row = by_id[identifier]
            self.assertTrue(row["supported"], row["reason"])
            self.assertEqual(row["address_profile"], "expression/v1")
            self.assertEqual(row["address"], address)
            self.assertEqual(row["source_address"], address)
            self.assertEqual(row["pointer_offsets"], [])
            self.assertEqual(row["requires"], [])
        child = by_id[921]
        self.assertTrue(child["supported"], child["reason"])
        self.assertEqual(child["address_profile"], "expression/v1")
        self.assertEqual(child["address"], "(20XX.exe)+40")
        self.assertEqual(child["source_address"], "+40")
        self.assertEqual(child["pointer_offsets"], [])

    def test_compiled_plan_passes_both_validators(self):
        plan = self.compile(self.CT_BODY)
        validate_plan(plan)
        validate_runtime_plan(plan)

    def test_forged_plan_metadata_rejected_by_both_validators(self):
        plan = self.compile(self.CT_BODY)
        cases = (("address", "+1"), ("pointer_offsets", [1]),
                 ("address_profile", "arbitrary"), ("requires", ["unknown"]))
        for key, value in cases:
            with self.subTest(key=key):
                malformed = copy.deepcopy(plan)
                malformed["entries"][0][key] = value
                for validator, error in ((validate_plan, NativeCompileError),
                                         (validate_runtime_plan, NativeRuntimeError)):
                    with self.assertRaises(error):
                        validator(malformed)
        missing_source = copy.deepcopy(plan)
        del missing_source["entries"][0]["source_address"]
        for validator, error in ((validate_plan, NativeCompileError),
                                 (validate_runtime_plan, NativeRuntimeError)):
            with self.assertRaises(error):
                validator(missing_source)

    def test_digit_address_without_module_suffix_stays_blocked(self):
        body = ('<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
                '<CheatEntry><ID>940</ID><Description>"Bad"</Description>'
                '<VariableType>4 Bytes</VariableType><Address>20XX</Address></CheatEntry>'
                '</CheatEntries></CheatTable>')
        row = self.compile(body)["entries"][0]
        self.assertFalse(row["supported"])
        self.assertEqual(row["reason"], "Unexpected trailing address expression tokens.")


class DoubleColonProgramTests(unittest.TestCase):
    """AA program level: ``::`` labels feed managed_method_labels unchanged."""

    DOUBLE_COLON_SCRIPT = ("[ENABLE]\n"
                           "assert(Counter::DoIt,55)\n"
                           "Counter::DoIt:\n"
                           "db c3\n"
                           "[DISABLE]\n"
                           "Counter::DoIt:\n"
                           "db 55\n")
    SINGLE_COLON_SCRIPT = ("[ENABLE]\n"
                           "assert(Counter:DoIt,55)\n"
                           "Counter:DoIt:\n"
                           "db c3\n"
                           "[DISABLE]\n"
                           "Counter:DoIt:\n"
                           "db 55\n")

    def test_program_records_double_colon_managed_label(self):
        program = prepare_program(self.DOUBLE_COLON_SCRIPT, "FixtureTarget.exe")
        self.assertEqual(program["managed_method_labels"], ["Counter::DoIt"])
        self.assertEqual(program["requires"], [])
        validate_program(program)

    def test_single_colon_program_still_records_label(self):
        program = prepare_program(self.SINGLE_COLON_SCRIPT, "FixtureTarget.exe")
        self.assertEqual(program["managed_method_labels"], ["Counter:DoIt"])
        self.assertEqual(program["requires"], [])
        validate_program(program)

    def test_tampered_label_manifest_is_refused(self):
        for script, expected in ((self.DOUBLE_COLON_SCRIPT, "Counter::DoIt"),
                                 (self.SINGLE_COLON_SCRIPT, "Counter:DoIt")):
            with self.subTest(expected=expected):
                program = prepare_program(script, "FixtureTarget.exe")
                program["managed_method_labels"] = ["Forged::Label"]
                with self.assertRaises(ProgramError):
                    validate_program(program)

    def test_malformed_double_colon_script_is_refused(self):
        script = ("[ENABLE]\nassert(A:::B,55)\nA:::B:\ndb c3\n[DISABLE]\n"
                  "A:::B:\ndb 55\n")
        with self.assertRaisesRegex(ProgramError,
                                    re.escape("Invalid address expression near ':::B'.")):
            prepare_program(script, "FixtureTarget.exe")

    def test_digit_module_in_aa_define(self):
        script = ("[ENABLE]\ndefine(base,20XX.exe+47B88B8)\n"
                  "assert(base,00)\nbase:\ndb 01\n[DISABLE]\nbase:\ndb 00\n")
        program = prepare_program(script, "FixtureTarget.exe")
        self.assertEqual(program["requires"], [])
        validate_program(program)


class ModuleMemory(FakeMemory):
    """FakeMemory plus a second owned module image with a digit-leading basename."""

    def __init__(self):
        super().__init__()
        self.module_base = 0x7FF60000
        self.module_data = bytearray(0x100)
        struct.pack_into("<I", self.module_data, 0x40, 0x11223344)

    @property
    def identity(self):
        return self.pid, self.creation_time

    def is_executable(self, address, size):
        return False

    def module(self, name):
        if name.casefold() == "20xx.exe":
            return self.module_base, len(self.module_data)
        return super().module(name)

    def read(self, address, size):
        if self.module_base <= address < self.module_base + len(self.module_data):
            offset = address - self.module_base
            if offset + size > len(self.module_data):
                raise OSError("Invalid address")
            return bytes(self.module_data[offset:offset + size])
        return super().read(address, size)

    def write(self, address, raw):
        if self.module_base <= address < self.module_base + len(self.module_data):
            offset = address - self.module_base
            self.writes.append((address, raw))
            self.module_data[offset:offset + len(raw)] = raw
            return
        super().write(address, raw)


CT_BODY_VALUE = '''<CheatTable CheatEngineTableVersion="45"><CheatEntries>
<CheatEntry><ID>900</ID><Description>"20XX module base"</Description><GroupHeader>1</GroupHeader><Address>20XX.exe</Address>
<CheatEntries>
<CheatEntry><ID>901</ID><Description>"HP"</Description><VariableType>4 Bytes</VariableType><Address>+40</Address></CheatEntry>
</CheatEntries>
</CheatEntry>
</CheatEntries></CheatTable>'''


class DigitModuleEngineTests(unittest.TestCase):
    """Engine level: byte-exact value writes at module-base + offset."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.table = self.root / "digit.ct"
        self.table.write_text(CT_BODY_VALUE, encoding="utf-8")
        self.memory = ModuleMemory()
        self.engine = TrainerEngine(
            compile_table(self.table, "ct2synth01.exe"),
            state_dir=self.root / "state",
            process_lock_dir=self.root / "shared",
            memory_factory=lambda name: self.memory,
            hook_coordinator=Coordinator())
        self.engine.poll()

    def tearDown(self):
        self.engine.close()

    def test_set_value_writes_byte_exact_at_module_base_plus_offset(self):
        address = self.memory.module_base + 0x40
        self.assertEqual(self.engine.set_value(901, "255"), "255")
        self.assertEqual(self.memory.read(address, 4), b"\xff\x00\x00\x00")
        self.assertEqual(self.engine.read_value(901), "255")
        self.assertEqual(self.memory.read(self.memory.module_base + 0x41, 3), b"\x00\x00\x00")

    def test_freeze_holds_value_after_target_tamper(self):
        address = self.memory.module_base + 0x40
        self.engine.set_value(901, "7")
        self.engine.set_freeze(901, True)
        self.memory.module_data[0x40] = 0xFF
        self.engine.poll()
        self.assertFalse(self.engine.blocked, self.engine.error)
        self.assertEqual(self.memory.read(address, 4), b"\x07\x00\x00\x00")
        self.engine.set_freeze(901, False)

    def test_missing_module_fails_closed_without_writes(self):
        memory = FakeMemory()
        engine = TrainerEngine(
            compile_table(self.table, "ct2synth01.exe"),
            state_dir=self.root / "state-nomod",
            process_lock_dir=self.root / "shared-nomod",
            memory_factory=lambda name: memory,
            hook_coordinator=Coordinator())
        engine.poll()
        try:
            with self.assertRaises(NativeRuntimeError):
                engine.set_value(901, "1")
        finally:
            engine.close()
        self.assertFalse(memory.writes)


def make_double_colon_host():
    host, _tables = make_host()
    # Both spellings are registered against the same proven method identity,
    # so each spelling resolves to the identical host-proven address.
    for alias in ("Counter::DoIt", "Counter:DoIt"):
        host.register_alias(AliasSpec(
            alias=alias, kind="method",
            image=IDENTITY[0], namespace=IDENTITY[1], class_name=IDENTITY[2],
            name="GetCurrentStatus"))
    return host


CT_BODY_MANAGED = '''<CheatTable CheatEngineTableVersion="45"><CheatEntries>
<CheatEntry><ID>930</ID><Description>"Double colon managed method"</Description><VariableType>Auto Assembler Script</VariableType><AssemblerScript>[ENABLE]
assert(Counter::DoIt,55)
Counter::DoIt:
db c3
[DISABLE]
Counter::DoIt:
db 55
</AssemblerScript></CheatEntry>
<CheatEntry><ID>931</ID><Description>"Single colon managed method"</Description><VariableType>Auto Assembler Script</VariableType><AssemblerScript>[ENABLE]
assert(Counter:DoIt,55)
Counter:DoIt:
db c3
[DISABLE]
Counter:DoIt:
db 55
</AssemblerScript></CheatEntry>
</CheatEntries></CheatTable>'''


class DoubleColonEngineTests(unittest.TestCase):
    """Engine level: ``::`` label -> resolver -> symbol overlay -> byte-exact patch."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.table = self.root / "managed.ct"
        self.table.write_text(CT_BODY_MANAGED, encoding="utf-8")
        self.memory = ManagedMemory()
        self.host = make_double_colon_host()
        self.engine = TrainerEngine(
            compile_table(self.table, "FixtureTarget.exe"),
            state_dir=self.root / "state",
            process_lock_dir=self.root / "shared",
            memory_factory=lambda name: self.memory,
            hook_coordinator=Coordinator(),
            il2cpp_resolver=lambda label: self.host.resolve_alias(label).va)
        self.engine.poll()

    def tearDown(self):
        self.engine.close()

    def test_plan_carries_double_colon_labels_with_clean_requires(self):
        by_id = {entry["id"]: entry for entry in self.engine.plan["entries"]}
        self.assertEqual(by_id[930]["program"]["managed_method_labels"],
                         ["Counter::DoIt"])
        self.assertEqual(by_id[931]["program"]["managed_method_labels"],
                         ["Counter:DoIt"])
        for entry in by_id.values():
            self.assertEqual(entry["program"]["requires"], [])
            self.assertEqual(entry["requires"], [])

    def test_double_colon_label_enable_disable_roundtrip(self):
        base = default_base(64)
        address = self.host.resolve_alias("Counter::DoIt").va
        self.assertEqual(address, base + 0x1040)
        self.assertTrue(self.engine.toggle(930, True))
        self.assertEqual(self.memory.read(address, 1), b"\xc3")
        self.assertFalse(self.engine.toggle(930, False))
        self.assertEqual(self.memory.read(address, 1), b"\x55")

    def test_single_colon_label_enable_disable_roundtrip(self):
        base = default_base(64)
        address = self.host.resolve_alias("Counter:DoIt").va
        self.assertEqual(address, base + 0x1040)
        self.assertTrue(self.engine.toggle(931, True))
        self.assertEqual(self.memory.read(address, 1), b"\xc3")
        self.assertFalse(self.engine.toggle(931, False))
        self.assertEqual(self.memory.read(address, 1), b"\x55")

    def test_both_spellings_resolve_the_identical_target(self):
        # The same method (same identity) is reached through both spellings
        # and receives the identical patch bytes.  Each spelling is enabled
        # on its own because the second ENABLE's assert(…,55) preflight
        # would see the byte patched by the first one.
        self.assertEqual(self.host.resolve_alias("Counter::DoIt").va,
                         self.host.resolve_alias("Counter:DoIt").va)
        self.assertTrue(self.engine.toggle(930, True))
        patch_double = list(self.memory.writes)
        self.assertFalse(self.engine.toggle(930, False))
        self.memory.writes.clear()
        self.assertTrue(self.engine.toggle(931, True))
        patch_single = list(self.memory.writes)
        self.assertFalse(self.engine.toggle(931, False))
        self.assertEqual(patch_single, patch_double)

    def test_writes_land_at_host_proven_addresses(self):
        proven_double = self.host.resolve_alias("Counter::DoIt").va
        proven_single = self.host.resolve_alias("Counter:DoIt").va
        self.assertEqual(proven_double, proven_single)
        # Enable/disable each spelling separately: while one program is
        # active the byte at the shared address is patched, so the other
        # program's assert(…,55) preflight would (correctly) refuse.
        self.assertTrue(self.engine.toggle(930, True))
        addresses_double = {address for address, _ in self.memory.writes}
        self.assertIn(proven_double, addresses_double)
        self.assertFalse(self.engine.toggle(930, False))
        self.memory.writes.clear()
        self.assertTrue(self.engine.toggle(931, True))
        addresses_single = {address for address, _ in self.memory.writes}
        self.assertIn(proven_single, addresses_single)
        self.assertFalse(self.engine.toggle(931, False))

    def test_forged_program_metadata_rejected_before_attach(self):
        plan = compile_table(self.table, "FixtureTarget.exe")
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        by_id[930]["program"]["managed_method_labels"] = ["Forged::Label"]
        for validator, error in ((validate_plan, NativeCompileError),
                                 (validate_runtime_plan, NativeRuntimeError)):
            with self.assertRaises(error):
                validator(plan)

    def test_missing_resolver_fails_closed_before_any_write(self):
        memory = ManagedMemory()
        engine = TrainerEngine(
            compile_table(self.table, "FixtureTarget.exe"),
            state_dir=self.root / "state-nor",
            process_lock_dir=self.root / "shared-nor",
            memory_factory=lambda name: memory,
            hook_coordinator=Coordinator())
        engine.poll()
        try:
            with self.assertRaisesRegex(NativeRuntimeError, "IL2CPP resolver"):
                engine.toggle(930, True)
        finally:
            engine.close()
        self.assertFalse(memory.writes)

    def test_resolver_failure_blocks_entry_without_writes(self):
        def failing_resolver(label):
            raise NativeRuntimeError("IL2CPP binding unavailable")
        memory = ManagedMemory()
        engine = TrainerEngine(
            compile_table(self.table, "FixtureTarget.exe"),
            state_dir=self.root / "state-fail",
            process_lock_dir=self.root / "shared-fail",
            memory_factory=lambda name: memory,
            hook_coordinator=Coordinator(),
            il2cpp_resolver=failing_resolver)
        engine.poll()
        try:
            with self.assertRaises(NativeRuntimeError):
                engine.toggle(930, True)
        finally:
            engine.close()
        self.assertFalse(memory.writes)


if __name__ == "__main__":
    unittest.main()
