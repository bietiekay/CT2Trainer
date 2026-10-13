"""AA conditional-block wiring: ``{$if}``/``{$else}``/``{$endif}`` pruned at compile time.

The pinned corpus carries zero conditional-block records (gap class
``aa_conditional_block``, 0 weighted actions), so fixture shapes mirror the
adopted Stage-1 grammar of ``ct2trainer.native.aa_blocks`` (pinned in
``tests/test_native_aa_blocks.py``): define-based conditions with
decimal/``$``/``0x`` literals, case-insensitive directives, whole-line
macros.  This file proves the full product chain on own synthetic
fixtures: prepare_program -> compile_table -> both plan validators ->
engine install -> byte-exact enable/disable roundtrip, plus every
fail-closed refusal of the wiring (nothing compiled, nothing written).
"""
from pathlib import Path
import tempfile
import unittest

from test_native_engine import FakeMemory
from test_native_engine_code import Coordinator

from ct2trainer.native.aa_program import ProgramError, prepare_program, validate_program
from ct2trainer.native.compiler import NativeCompileError, compile_table, validate_plan as validate_compiler_plan
from ct2trainer.native.engine import NativeRuntimeError, TrainerEngine, validate_plan as validate_engine_plan

PROCESS = "FixtureTarget.exe"

# 1 {$define BUILD 2} / 2 [ENABLE] / 3 {$if BUILD=2} / 4 cursor+40 /
# 5 db AA.. / 6 {$else} / 7 cursor+44 / 8 db 11.. / 9 {$endif} /
# 10 [DISABLE] / 11 {$if BUILD=2} / 12 cursor+40 / 13 db 00.. /
# 14 {$else} / 15 cursor+44 / 16 db 55.. / 17 {$endif}
def conditional_source(build: int) -> str:
    return (
        f"{{$define BUILD {build}}}\n"
        "[ENABLE]\n"
        "{$if BUILD=2}\n"
        "FixtureTarget.exe+40:\n"
        "db 90 90 90 90\n"
        "{$else}\n"
        "FixtureTarget.exe+44:\n"
        "db 91 91 91 91\n"
        "{$endif}\n"
        "[DISABLE]\n"
        "{$if BUILD=2}\n"
        "FixtureTarget.exe+40:\n"
        "db 00 00 00 00\n"
        "{$else}\n"
        "FixtureTarget.exe+44:\n"
        "db 55 66 77 88\n"
        "{$endif}\n"
    )


def ct_body(script: str) -> str:
    return ('<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
            '<CheatEntry><ID>1</ID><Description>"Conditional build patch"'
            '</Description><VariableType>Auto Assembler Script</VariableType>'
            f'<AssemblerScript>{script}</AssemblerScript></CheatEntry>'
            '</CheatEntries></CheatTable>')


class ConditionalProgramTests(unittest.TestCase):
    """Compiler level: the prune selects one branch; metadata is byte-verifiable."""

    def test_selected_if_branch_survives_with_decisions(self):
        program = prepare_program(conditional_source(2), PROCESS)
        self.assertEqual(program["defines"], {"build": 2})
        self.assertEqual(program["conditional_decisions"], [
            {"line": 3, "condition": "BUILD=2", "chosen": "if"},
            {"line": 11, "condition": "BUILD=2", "chosen": "if"}])
        self.assertEqual(program["enable"], [
            {"op": "cursor", "expression": "FixtureTarget.exe+40"},
            {"op": "data", "directive": "db", "values": ["90", "90", "90", "90"]}])
        self.assertEqual(program["disable"], [
            {"op": "cursor", "expression": "FixtureTarget.exe+40"},
            {"op": "data", "directive": "db", "values": ["00", "00", "00", "00"]}])
        validate_program(program)

    def test_else_branch_selected(self):
        program = prepare_program(conditional_source(1), PROCESS)
        self.assertEqual(program["defines"], {"build": 1})
        self.assertEqual(program["conditional_decisions"], [
            {"line": 3, "condition": "BUILD=2", "chosen": "else"},
            {"line": 11, "condition": "BUILD=2", "chosen": "else"}])
        self.assertEqual(program["enable"], [
            {"op": "cursor", "expression": "FixtureTarget.exe+44"},
            {"op": "data", "directive": "db", "values": ["91", "91", "91", "91"]}])
        self.assertEqual(program["disable"], [
            {"op": "cursor", "expression": "FixtureTarget.exe+44"},
            {"op": "data", "directive": "db", "values": ["55", "66", "77", "88"]}])
        validate_program(program)

    def test_case_insensitive_macros_and_branches(self):
        source = ("{$DEFINE Mode 1}\n"
                  "[ENABLE]\n"
                  "{$IF MODE=1}\n"
                  "FixtureTarget.exe+40:\n"
                  "db 0A\n"
                  "{$ELSE}\n"
                  "FixtureTarget.exe+40:\n"
                  "db 0B\n"
                  "{$ENDIF}\n"
                  "[DISABLE]\n"
                  "FixtureTarget.exe+40:\n"
                  "db 00\n")
        program = prepare_program(source, PROCESS)
        self.assertEqual(program["defines"], {"mode": 1})
        self.assertEqual(program["conditional_decisions"],
                         [{"line": 3, "condition": "MODE=1", "chosen": "if"}])
        self.assertEqual(program["enable"][1]["values"], ["0A"])
        validate_program(program)

    def test_hex_0x_literals_and_define_operands(self):
        for left, right in (("A", "B"), ("FLAG", "255")):
            with self.subTest(condition=f"{left}={right}"):
                source = (
                    "{$define A 5}\n"
                    "{$define B $5}\n"
                    "{$define FLAG 0xFF}\n"
                    "[ENABLE]\n"
                    f"{{$if {left}={right}}}\n"
                    "FixtureTarget.exe+40:\n"
                    "db 01\n"
                    "{$endif}\n"
                    "[DISABLE]\n"
                    "FixtureTarget.exe+40:\n"
                    "db 00\n")
                program = prepare_program(source, PROCESS)
                decision = program["conditional_decisions"][0]
                self.assertEqual(decision["condition"], f"{left}={right}")
                self.assertEqual(decision["chosen"], "if")
                self.assertEqual(program["enable"][1]["values"], ["01"])
                validate_program(program)

    def test_nested_selection_is_deterministic(self):
        source = ("{$define A 1}\n"
                  "{$define B 0}\n"
                  "[ENABLE]\n"
                  "{$if A=1}\n"
                  "{$if B=0}\n"
                  "FixtureTarget.exe+40:\n"
                  "db 0A\n"
                  "{$else}\n"
                  "FixtureTarget.exe+40:\n"
                  "db 0B\n"
                  "{$endif}\n"
                  "{$endif}\n"
                  "[DISABLE]\n"
                  "FixtureTarget.exe+40:\n"
                  "db 00\n")
        program = prepare_program(source, PROCESS)
        self.assertEqual(program["conditional_decisions"], [
            {"line": 4, "condition": "A=1", "chosen": "if"},
            {"line": 5, "condition": "B=0", "chosen": "if"}])
        self.assertEqual(program["enable"][1]["values"], ["0A"])
        self.assertEqual(program, prepare_program(source, PROCESS))
        validate_program(program)

    def test_prune_is_a_no_op_without_conditionals(self):
        plain = ("[ENABLE]\n"
                 "FixtureTarget.exe+40:\n"
                 "db 01\n"
                 "[DISABLE]\n"
                 "FixtureTarget.exe+40:\n"
                 "db 00\n")
        program = prepare_program(plain, PROCESS)
        self.assertEqual(program["defines"], {})
        self.assertEqual(program["conditional_decisions"], [])
        validate_program(program)

    def test_pruned_program_matches_the_equivalent_static_script(self):
        pruned = prepare_program(conditional_source(2), PROCESS)
        static = prepare_program(
            "[ENABLE]\n"
            "FixtureTarget.exe+40:\n"
            "db 90 90 90 90\n"
            "[DISABLE]\n"
            "FixtureTarget.exe+40:\n"
            "db 00 00 00 00\n", PROCESS)
        dropped = {"source", "source_sha256", "defines", "conditional_decisions"}
        self.assertEqual({key: value for key, value in pruned.items() if key not in dropped},
                         {key: value for key, value in static.items() if key not in dropped})

    def test_commented_directives_are_inert(self):
        source = ("/* {$if MISSING=1} */\n"
                  "// {$else}\n"
                  "[ENABLE]\n"
                  "FixtureTarget.exe+40:\n"
                  "db 01\n"
                  "[DISABLE]\n"
                  "FixtureTarget.exe+40:\n"
                  "db 00\n")
        program = prepare_program(source, PROCESS)
        self.assertEqual(program["defines"], {})
        self.assertEqual(program["conditional_decisions"], [])
        validate_program(program)


class ConditionalRefusalTests(unittest.TestCase):
    """Every refusal of the wiring raises a named error and compiles nothing."""

    def program(self, source: str):
        with self.assertRaises(ProgramError):
            prepare_program(source, PROCESS)

    def test_undefined_define_refused(self):
        source = ("[ENABLE]\n"
                  "{$if MISSING=1}\n"
                  "FixtureTarget.exe+40:\n"
                  "db 01\n"
                  "{$endif}\n"
                  "[DISABLE]\n"
                  "FixtureTarget.exe+40:\n"
                  "db 00\n")
        with self.assertRaisesRegex(ProgramError, "undefined define 'MISSING'"):
            prepare_program(source, PROCESS)

    def test_unterminated_block_refused(self):
        source = ("{$define A 1}\n"
                  "[ENABLE]\n"
                  "{$if A=1}\n"
                  "FixtureTarget.exe+40:\n"
                  "db 01\n"
                  "[DISABLE]\n"
                  "FixtureTarget.exe+40:\n"
                  "db 00\n")
        with self.assertRaisesRegex(ProgramError, "unterminated"):
            prepare_program(source, PROCESS)

    def test_orphan_else_and_endif_refused(self):
        for directive in ("{$else}", "{$endif}"):
            with self.subTest(directive=directive):
                source = ("{$define A 1}\n"
                          "[ENABLE]\n"
                          "FixtureTarget.exe+40:\n"
                          "db 01\n"
                          f"{directive}\n"
                          "[DISABLE]\n"
                          "FixtureTarget.exe+40:\n"
                          "db 00\n")
                self.program(source)

    def test_double_else_refused(self):
        source = ("{$define A 1}\n"
                  "[ENABLE]\n"
                  "{$if A=1}\n"
                  "db 01\n"
                  "{$else}\n"
                  "db 02\n"
                  "{$else}\n"
                  "db 03\n"
                  "{$endif}\n"
                  "[DISABLE]\n"
                  "db 00\n")
        with self.assertRaisesRegex(ProgramError, "duplicate \\{\\$else\\}"):
            prepare_program(source, PROCESS)

    def test_nesting_depth_overflow_refused(self):
        source = ("{$define A 1}\n"
                  "[ENABLE]\n"
                  + "".join("{$if A=1}\n" for _ in range(17))
                  + "db 01\n"
                  + "".join("{$endif}\n" for _ in range(17))
                  + "[DISABLE]\n"
                  "db 00\n")
        with self.assertRaisesRegex(ProgramError, "exceeds its bound"):
            prepare_program(source, PROCESS)

    def test_unsupported_condition_shape_refused(self):
        source = ("{$define A 1}\n"
                  "[ENABLE]\n"
                  "{$if A < 1}\n"
                  "FixtureTarget.exe+40:\n"
                  "db 01\n"
                  "{$endif}\n"
                  "[DISABLE]\n"
                  "FixtureTarget.exe+40:\n"
                  "db 00\n")
        with self.assertRaisesRegex(
                ProgramError, "unsupported conditional expression"):
            prepare_program(source, PROCESS)

    def test_malformed_define_refused(self):
        for body in ("{$define A}", "{$define A 1 2}", "{$define A $GG}",
                     "{$define 1A 1}", "{$define A foo}"):
            with self.subTest(body=body):
                source = (body + "\n"
                          "[ENABLE]\n"
                          "FixtureTarget.exe+40:\n"
                          "db 01\n"
                          "[DISABLE]\n"
                          "FixtureTarget.exe+40:\n"
                          "db 00\n")
                with self.assertRaisesRegex(
                        ProgramError, "\\$define requires"):
                    prepare_program(source, PROCESS)

    def test_duplicate_define_refused(self):
        source = ("{$define A 1}\n"
                  "{$define a 2}\n"
                  "[ENABLE]\n"
                  "FixtureTarget.exe+40:\n"
                  "db 01\n"
                  "[DISABLE]\n"
                  "FixtureTarget.exe+40:\n"
                  "db 00\n")
        with self.assertRaisesRegex(ProgramError, "defined more than once"):
            prepare_program(source, PROCESS)

    def test_unrelated_directives_stay_refused(self):
        # WP-26: {$asm} and {$STRICT} are accepted no-ops now; every other
        # non-conditional {$...} form keeps its named fail-closed refusal.
        for line in ("{$lua}", "{$alloc(x,10)}",
                     "{$undefine A}"):
            with self.subTest(line=line):
                source = ("[ENABLE]\n"
                          + line + "\n"
                          "FixtureTarget.exe+40:\n"
                          "db 01\n"
                          "[DISABLE]\n"
                          "FixtureTarget.exe+40:\n"
                          "db 00\n")
                with self.assertRaisesRegex(
                        ProgramError, r"Non-profile \{\$...\} directive"):
                    prepare_program(source, PROCESS)

    def test_noop_directives_are_stripped(self):
        # WP-26: CE-recognized no-op directives are stripped, not refused;
        # the parsed program is identical to the directive-free source
        # (the stored original source and its hash differ by definition).
        for line in ("{$asm}", "{$STRICT}", "{$ccode}", "{$luacode}",
                     "{$try}", "{$except}"):
            with self.subTest(line=line):
                source = ("[ENABLE]\n"
                          + line + "\n"
                          "FixtureTarget.exe+40:\n"
                          "db 01\n"
                          "[DISABLE]\n"
                          "FixtureTarget.exe+40:\n"
                          "db 00\n")
                plain = source.replace(line + "\n", "")
                decorated = prepare_program(source, PROCESS)
                bare = prepare_program(plain, PROCESS)
                for key in ("source", "source_sha256"):
                    decorated.pop(key)
                    bare.pop(key)
                self.assertEqual(decorated, bare)
                for directive in ("{$", "$strict", "$ccode", "$luacode",
                                  "$asm", "$try", "$except"):
                    self.assertNotIn(directive,
                                     "".join(
                                         repr(node)
                                         for key in ("preamble", "enable", "disable")
                                         for node in decorated[key])
                                     .casefold())


class ConditionalCompilerTests(unittest.TestCase):
    """compile_table routes conditional records through the program profile."""

    def compile(self, script: str) -> dict:
        with tempfile.TemporaryDirectory() as directory:
            table = Path(directory) / "conditional.ct"
            table.write_text(ct_body(script), encoding="utf-8")
            return compile_table(table, PROCESS)

    def test_supported_record_carries_program_and_decisions(self):
        plan = self.compile(conditional_source(2))
        entry = plan["entries"][0]
        self.assertTrue(entry["supported"], entry["reason"])
        self.assertEqual(entry["kind"], "script")
        self.assertIn("program", entry)
        self.assertEqual(entry["program"]["defines"], {"build": 2})
        self.assertEqual(len(entry["program"]["conditional_decisions"]), 2)
        validate_compiler_plan(plan)
        validate_engine_plan(plan)

    def test_refused_scripts_block_the_record_without_operations(self):
        cases = [
            ("[ENABLE]\n{$if MISSING=1}\nFixtureTarget.exe+40:\ndb 01\n"
             "{$endif}\n[DISABLE]\nFixtureTarget.exe+40:\ndb 00\n",
             "undefined define"),
            ("{$define A 1}\n[ENABLE]\n{$if A=1}\nFixtureTarget.exe+40:\ndb 01\n"
             "[DISABLE]\nFixtureTarget.exe+40:\ndb 00\n",
             "unterminated"),
            ("{$define A 1}\n[ENABLE]\n{$if A=1}\ndb 01\n{$else}\ndb 02\n"
             "{$else}\ndb 03\n{$endif}\n[DISABLE]\ndb 00\n",
             "duplicate {$else}"),
        ]
        for script, marker in cases:
            with self.subTest(marker=marker):
                plan = self.compile(script)
                entry = plan["entries"][0]
                self.assertFalse(entry["supported"], entry["reason"])
                self.assertIn(marker, entry["reason"])
                self.assertNotIn("program", entry)
                self.assertNotIn("enable", entry)
                self.assertNotIn("disable", entry)
                validate_compiler_plan(plan)
                validate_engine_plan(plan)

    def test_tampered_conditional_metadata_is_refused_by_both_validators(self):
        mutations = [
            lambda entry: entry["program"]["conditional_decisions"].__setitem__(
                0, dict(entry["program"]["conditional_decisions"][0],
                        chosen="else")),
            lambda entry: entry["program"]["defines"].update({"forged": 9}),
            lambda entry: entry["program"]["defines"].__setitem__("build", 1),
            lambda entry: entry["program"]["conditional_decisions"].append(
                {"line": 99, "condition": "FORGED=1", "chosen": "if"}),
            lambda entry: entry["program"]["enable"].__setitem__(
                0, {"op": "cursor", "expression": "FixtureTarget.exe+44"}),
        ]
        for mutate in mutations:
            plan = self.compile(conditional_source(2))
            mutate(plan["entries"][0])
            with self.assertRaises(NativeCompileError):
                validate_compiler_plan(plan)
            memory = ConditionalMemory()
            with tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(NativeRuntimeError):
                    TrainerEngine(plan, state_dir=Path(directory) / "state",
                                  memory_factory=lambda name: memory,
                                  hook_coordinator=Coordinator())
            self.assertFalse(memory.writes)


class ConditionalEngineTests(unittest.TestCase):
    """Engine level: the selected branch patches byte-exactly; the other stays untouched."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.memory = ConditionalMemory()
        self.engine = None

    def tearDown(self):
        if self.engine is not None:
            self.engine.close()

    def start_engine(self, build: int):
        table = self.root / f"conditional-{build}.ct"
        table.write_text(ct_body(conditional_source(build)), encoding="utf-8")
        plan = compile_table(table, PROCESS)
        self.engine = TrainerEngine(
            plan, state_dir=self.root / f"state-{build}",
            process_lock_dir=self.root / f"shared-{build}",
            memory_factory=lambda name: self.memory,
            hook_coordinator=Coordinator())
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)
        return self.engine

    def test_if_branch_enable_disable_roundtrip(self):
        self.start_engine(2)
        self.assertTrue(self.engine.toggle(1, True))
        self.assertEqual(self.memory.read(0x1040, 4),
                         bytes.fromhex("90909090"))
        # The non-selected branch leaves no trace.
        self.assertEqual(self.memory.read(0x1044, 4),
                         bytes.fromhex("55667788"))
        self.assertEqual({address for address, _ in self.memory.writes},
                         {0x1040})
        self.assertFalse(self.engine.toggle(1, False))
        self.assertEqual(self.memory.read(0x1040, 4), bytes(4))

    def test_else_branch_enable_disable_roundtrip(self):
        self.start_engine(1)
        self.assertTrue(self.engine.toggle(1, True))
        self.assertEqual(self.memory.read(0x1044, 4),
                         bytes.fromhex("91919191"))
        self.assertEqual(self.memory.read(0x1040, 4), bytes(4))
        self.assertEqual({address for address, _ in self.memory.writes},
                         {0x1044})
        self.assertFalse(self.engine.toggle(1, False))
        self.assertEqual(self.memory.read(0x1044, 4),
                         bytes.fromhex("55667788"))


class ConditionalMemory(FakeMemory):
    """Base 0x1000; +0x40 starts zeroed, +0x44 holds the B-branch original."""

    def __init__(self):
        super().__init__()
        self.data[0x40:0x44] = bytes(4)
        self.data[0x44:0x48] = bytes.fromhex("55667788")

    @property
    def identity(self):
        return self.pid, self.creation_time

    def is_executable(self, address, size):
        return False


if __name__ == "__main__":
    unittest.main()
