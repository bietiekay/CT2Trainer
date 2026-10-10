"""Nested-assembly wiring: ``autoAssemble``/``autoasm`` in the active AA pipeline.

The tested Stage-1 resolver (``aa_blocks.resolve_nested_assembly``) is pinned
by ``tests/test_native_aa_blocks.py``.  This file proves the pipeline wiring:
``prepare_program`` resolves label bodies (internal ``name:`` definitions and
the optional external table-level registry) and inlines them at the
invocation sites with deterministic topological order and invocation
metadata; ``validate_program`` re-derives the metadata byte-exactly;
``compile_table`` builds the table-level label registry from all
AssemblerScript records (ambiguous names refused fail-closed, own
definitions excluded per record); label bodies may not contain section
markers (internal spans and external registry entries alike); programs
without invocations keep the exact pre-wiring plan shape.  The engine
roundtrip proves byte-exact enable/disable of inlined nested bodies on
own fixtures.
"""
from pathlib import Path
import tempfile
import unittest

from test_native_engine import FakeMemory
from test_native_engine_code import Coordinator

from ct2trainer.native.aa_program import ProgramError, prepare_program, validate_program
from ct2trainer.native.compiler import (NativeCompileError, compile_table,
                                          validate_plan as validate_compiler_plan)
from ct2trainer.native.engine import (TrainerEngine,
                                        validate_plan as validate_engine_plan)

PROCESS = "FixtureTarget.exe"

# 1 [ENABLE] / 2 cursor+40 / 3 autoAssemble("beta") / 4 db 91 /
# 5 [DISABLE] / 6 cursor+40 / 7 db 00 00 / 8 alpha: / 9 db 90 /
# 10 beta: / 11 autoAssemble("alpha")
# 0x90 (NOP) and 0x91 (XCHG [ECX],EAX) are single-byte x64 instructions, so
# the inlined enable bytes also pass the engine's entry control-flow gate.
INTERNAL = (
    "[ENABLE]\n"
    "FixtureTarget.exe+40:\n"
    'autoAssemble("beta")\n'
    "db 91\n"
    "[DISABLE]\n"
    "FixtureTarget.exe+40:\n"
    "db 00 00\n"
    "alpha:\n"
    "db 90\n"
    "beta:\n"
    'autoAssemble("alpha")\n'
)

# 1 [ENABLE] / 2 cursor+40 / 3 autoasm("shared_helper") /
# 4 [DISABLE] / 5 cursor+40 / 6 db 00 00
EXTERNAL = (
    "[ENABLE]\n"
    "FixtureTarget.exe+40:\n"
    'autoasm("shared_helper")\n'
    "[DISABLE]\n"
    "FixtureTarget.exe+40:\n"
    "db 00 00\n"
)

# No invocation: exact pre-wiring shape, no nested fields.
PLAIN = (
    "[ENABLE]\n"
    "FixtureTarget.exe+40:\n"
    "db 01\n"
    "[DISABLE]\n"
    "FixtureTarget.exe+40:\n"
    "db 00\n"
)

# Plain address labels may repeat between sections while no invocation
# engages the resolver's single-definition rule.
REPEATED_LABELS = (
    "[ENABLE]\n"
    "FixtureTarget.exe+40:\n"
    "patch_point:\n"
    "db 01\n"
    "[DISABLE]\n"
    "FixtureTarget.exe+40:\n"
    "patch_point:\n"
    "db 00\n"
)

UNKNOWN = (
    "[ENABLE]\n"
    "FixtureTarget.exe+40:\n"
    'autoAssemble("missing")\n'
    "[DISABLE]\n"
    "FixtureTarget.exe+40:\n"
    "db 00\n"
)

# The second call sits inside alpha's own body: one label, two call
# sites -> duplicate refusal.
DUPLICATE = (
    "[ENABLE]\n"
    "FixtureTarget.exe+40:\n"
    'autoAssemble("alpha")\n'
    "alpha:\n"
    "db 01\n"
    'autoAssemble("alpha")\n'
    "[DISABLE]\n"
    "FixtureTarget.exe+40:\n"
    "db 00\n"
)

# Mutual body invocations with no top-level call: a -> b -> a.
CYCLE = (
    "[ENABLE]\n"
    "FixtureTarget.exe+40:\n"
    "db 01\n"
    "a:\n"
    'autoAssemble("b")\n'
    "b:\n"
    'autoAssemble("a")\n'
    "[DISABLE]\n"
    "FixtureTarget.exe+40:\n"
    "db 00\n"
)

# Internal label and registry entry with the same name.
COLLISION = (
    "[ENABLE]\n"
    "FixtureTarget.exe+40:\n"
    'autoAssemble("shared")\n'
    "shared:\n"
    "db 02\n"
    "[DISABLE]\n"
    "FixtureTarget.exe+40:\n"
    "db 00\n"
)

# The [DISABLE] marker falls inside top's span (body to end of source).
INTERNAL_MARKER = (
    "[ENABLE]\n"
    "FixtureTarget.exe+40:\n"
    'autoAssemble("top")\n'
    "top:\n"
    "[DISABLE]\n"
    "db 01\n"
)


def ct_entries(*scripts: str) -> str:
    body = "".join(
        '<CheatEntry><ID>%d</ID><Description>"Record %d"</Description>'
        '<VariableType>Auto Assembler Script</VariableType>'
        "<AssemblerScript>%s</AssemblerScript></CheatEntry>" % (i + 1, i + 1, s)
        for i, s in enumerate(scripts))
    return ('<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
            + body + "</CheatEntries></CheatTable>")


class NestedProgramTests(unittest.TestCase):
    """prepare_program: resolution, inlining and plan metadata."""

    def test_internal_labels_inlined_with_metadata(self):
        program = prepare_program(INTERNAL, PROCESS)
        self.assertEqual(program["enable"], [
            {"op": "cursor", "expression": "FixtureTarget.exe+40"},
            {"op": "data", "directive": "db", "values": ["90"]},
            {"op": "data", "directive": "db", "values": ["91"]}])
        self.assertEqual(program["disable"], [
            {"op": "cursor", "expression": "FixtureTarget.exe+40"},
            {"op": "data", "directive": "db", "values": ["00", "00"]}])
        self.assertEqual(program["nested_invocations"], [
            {"label": "beta", "line": 3, "depth": 1},
            {"label": "alpha", "line": 11, "depth": 2}])
        self.assertEqual(program["nested_label_order"], ["alpha", "beta"])
        self.assertNotIn("external_labels", program)
        self.assertFalse(program["one_shot"])
        validate_program(program)

    def test_external_registry_inlined_with_stored_registry(self):
        program = prepare_program(EXTERNAL, PROCESS,
                                  labels={"shared_helper": "db 55 66"})
        self.assertEqual(program["enable"], [
            {"op": "cursor", "expression": "FixtureTarget.exe+40"},
            {"op": "data", "directive": "db", "values": ["55", "66"]}])
        self.assertEqual(program["nested_invocations"], [
            {"label": "shared_helper", "line": 3, "depth": 1}])
        self.assertEqual(program["nested_label_order"], ["shared_helper"])
        self.assertEqual(program["external_labels"],
                         {"shared_helper": "db 55 66"})
        validate_program(program)

    def test_external_bodies_can_nest_into_each_other(self):
        program = prepare_program(EXTERNAL, PROCESS,
                                  labels={"shared_helper": 'autoAssemble("inner")',
                                          "inner": "db 77"})
        self.assertEqual(program["enable"], [
            {"op": "cursor", "expression": "FixtureTarget.exe+40"},
            {"op": "data", "directive": "db", "values": ["77"]}])
        self.assertEqual(program["nested_invocations"], [
            {"label": "shared_helper", "line": 3, "depth": 1},
            {"label": "inner", "line": None, "depth": 2}])
        self.assertEqual(program["nested_label_order"],
                         ["inner", "shared_helper"])
        validate_program(program)

    def test_invocation_and_labels_are_case_insensitive(self):
        cased = INTERNAL.replace('autoAssemble("beta")',
                                 'autoAssemble("BETA")')
        program = prepare_program(cased, PROCESS)
        reference = prepare_program(INTERNAL, PROCESS)
        self.assertEqual(program["enable"], reference["enable"])
        self.assertEqual(program["disable"], reference["disable"])
        self.assertEqual(program["nested_label_order"],
                         reference["nested_label_order"])
        # The invocation metadata keeps the call-site spelling.
        self.assertEqual(program["nested_invocations"][0]["label"], "BETA")
        validate_program(program)

    def test_plain_program_shape_is_byte_identical_to_pre_wiring(self):
        program = prepare_program(PLAIN, PROCESS)
        self.assertEqual(program["enable"], [
            {"op": "cursor", "expression": "FixtureTarget.exe+40"},
            {"op": "data", "directive": "db", "values": ["01"]}])
        self.assertNotIn("nested_invocations", program)
        self.assertNotIn("nested_label_order", program)
        self.assertNotIn("external_labels", program)
        validate_program(program)

    def test_repeated_plain_labels_without_invocation_are_allowed(self):
        program = prepare_program(REPEATED_LABELS, PROCESS)
        self.assertEqual(program["requires"], ["patch_point"])
        self.assertNotIn("nested_invocations", program)
        self.assertNotIn("external_labels", program)
        validate_program(program)

    def test_unknown_label_is_refused(self):
        with self.assertRaisesRegex(ProgramError,
                                    r"unknown label 'missing'"):
            prepare_program(UNKNOWN, PROCESS)

    def test_duplicate_invocation_is_refused(self):
        with self.assertRaisesRegex(ProgramError, "autoassembled more than once"):
            prepare_program(DUPLICATE, PROCESS)

    def test_cycle_is_refused_with_its_path(self):
        with self.assertRaisesRegex(ProgramError, r"cycle: a -> b -> a"):
            prepare_program(CYCLE, PROCESS)

    def test_internal_external_collision_is_refused(self):
        with self.assertRaisesRegex(
                ProgramError, "defined in the program and the registry"):
            prepare_program(COLLISION, PROCESS, labels={"shared": "db 01"})

    def test_duplicate_label_definition_is_refused(self):
        source = (
            "[ENABLE]\n"
            "FixtureTarget.exe+40:\n"
            'autoAssemble("dup")\n'
            "dup:\n"
            "db 01\n"
            "dup:\n"
            "db 02\n"
            "[DISABLE]\n"
            "FixtureTarget.exe+40:\n"
            "db 00\n"
        )
        with self.assertRaisesRegex(ProgramError, "defined more than once"):
            prepare_program(source, PROCESS)

    def test_internal_body_section_marker_is_refused(self):
        with self.assertRaisesRegex(ProgramError, "section marker"):
            prepare_program(INTERNAL_MARKER, PROCESS)

    def test_external_body_section_marker_is_refused(self):
        with self.assertRaisesRegex(ProgramError, "section marker"):
            prepare_program(EXTERNAL, PROCESS,
                            labels={"shared_helper":
                                    "db 55\n[DISABLE]\ndb 00"})

    def test_validation_detects_tampered_invocation_metadata(self):
        program = prepare_program(INTERNAL, PROCESS)
        program["nested_invocations"][0]["depth"] = 99
        with self.assertRaises(ProgramError):
            validate_program(program)
        program = prepare_program(INTERNAL, PROCESS)
        program["nested_label_order"].reverse()
        with self.assertRaises(ProgramError):
            validate_program(program)


class NestedTableTests(unittest.TestCase):
    """compile_table: the table-level label registry."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="native-nested-table-"))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)

    def start_table(self, name, *scripts):
        table = self.root / name
        table.write_text(ct_entries(*scripts), encoding="utf-8")
        return compile_table(table, PROCESS)

    def test_table_registry_inlines_across_records(self):
        owner = (
            "[ENABLE]\n"
            "FixtureTarget.exe+40:\n"
            "db 55 66\n"
            "[DISABLE]\n"
            "FixtureTarget.exe+40:\n"
            "db 00 00\n"
            "shared_helper:\n"
            "db 55 66\n"
        )
        plan = self.start_table("registry.ct", owner, EXTERNAL)
        entries = {entry["id"]: entry for entry in plan["entries"]}
        # The owner record references the bare label as an address symbol
        # nobody provides, so it stays blocked (visible reason).
        self.assertFalse(entries[1]["supported"])
        self.assertIn("shared_helper", entries[1]["reason"])
        # The caller inlines the registry body at its invocation site.
        self.assertTrue(entries[2]["supported"], entries[2]["reason"])
        program = entries[2]["program"]
        self.assertEqual(program["enable"], [
            {"op": "cursor", "expression": "FixtureTarget.exe+40"},
            {"op": "data", "directive": "db", "values": ["55", "66"]}])
        self.assertEqual(program["external_labels"],
                         {"shared_helper": "db 55 66"})
        validate_compiler_plan(plan)
        validate_engine_plan(plan)

    def test_ambiguous_registry_name_is_refused_fail_closed(self):
        owner_a = (
            "[ENABLE]\n"
            "FixtureTarget.exe+40:\n"
            "db 55 66\n"
            "[DISABLE]\n"
            "FixtureTarget.exe+40:\n"
            "db 00 00\n"
            "shared_helper:\n"
            "db 55 66\n"
        )
        owner_b = owner_a.replace("db 55 66\n[DISABLE]", "db 77 88\n[DISABLE]")
        plan = self.start_table("ambiguous.ct", owner_a, owner_b, EXTERNAL)
        entries = {entry["id"]: entry for entry in plan["entries"]}
        # Both owners define the name -> the registry drops it entirely.
        self.assertFalse(entries[3]["supported"])
        self.assertIn("unknown label", entries[3]["reason"])

    def test_registry_body_with_section_marker_blocks_the_caller(self):
        owner = (
            "[ENABLE]\n"
            "FixtureTarget.exe+40:\n"
            "shared_helper:\n"
            "db 55 66\n"
            "[DISABLE]\n"
            "FixtureTarget.exe+40:\n"
            "db 00 00\n"
        )
        plan = self.start_table("marker.ct", owner, EXTERNAL)
        entries = {entry["id"]: entry for entry in plan["entries"]}
        # The owner's registry body runs past the [DISABLE] marker into the
        # next section; inlining it would duplicate sections, so the caller
        # is refused with a visible reason instead.
        self.assertFalse(entries[2]["supported"])
        self.assertIn("section marker", entries[2]["reason"])

    def test_own_definitions_are_excluded_from_own_registry(self):
        plan = self.start_table("self.ct", INTERNAL)
        entry = plan["entries"][0]
        # The table registry contains alpha/beta from this very record; if
        # the own-definition exclusion failed, the internal definitions
        # would collide with the registry and the record would be blocked.
        self.assertTrue(entry["supported"], entry["reason"])
        self.assertNotIn("external_labels", entry["program"])
        validate_compiler_plan(plan)
        validate_engine_plan(plan)


class NestedEngineMemory(FakeMemory):
    """Fixture memory carrying the identity the hook manager requires."""

    @property
    def identity(self):
        return self.pid, self.creation_time

    def is_executable(self, address, size):
        return False


class NestedEngineTests(unittest.TestCase):
    """Engine roundtrip: inlined nested bodies patch byte-exactly."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="native-nested-engine-"))
        self.memory = NestedEngineMemory()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)

    def start_engine(self, name, *scripts):
        table = self.root / name
        table.write_text(ct_entries(*scripts), encoding="utf-8")
        plan = compile_table(table, PROCESS)
        engine = TrainerEngine(
            plan, state_dir=self.root / (name + "-state"),
            process_lock_dir=self.root / (name + "-shared"),
            memory_factory=lambda _name: self.memory,
            hook_coordinator=Coordinator())
        engine.poll()
        self.assertTrue(engine.connected, engine.status)
        return engine

    def test_internal_nested_roundtrip(self):
        engine = self.start_engine("internal.ct", INTERNAL)
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.memory.read(0x1040, 2), b"\x90\x91")
        self.assertFalse(engine.toggle(1, False))
        self.assertEqual(self.memory.read(0x1040, 2), b"\x00\x00")
        engine.close()

    def test_table_registry_roundtrip(self):
        owner = (
            "[ENABLE]\n"
            "FixtureTarget.exe+40:\n"
            "db 90 91\n"
            "[DISABLE]\n"
            "FixtureTarget.exe+40:\n"
            "db 00 00\n"
            "shared_helper:\n"
            "db 90 91\n"
        )
        engine = self.start_engine("registry.ct", owner, EXTERNAL)
        self.assertTrue(engine.toggle(2, True))
        self.assertEqual(self.memory.read(0x1040, 2), b"\x90\x91")
        self.assertFalse(engine.toggle(2, False))
        self.assertEqual(self.memory.read(0x1040, 2), b"\x00\x00")
        engine.close()


if __name__ == "__main__":
    unittest.main()
