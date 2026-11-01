"""Field-fix regression (2026-11-01): placeholder headings carry no plan-level
symbol dependencies.

A zero-length byte-array group header whose display address names a symbol
compiles to a supported, non-actionable placeholder heading (WP-32/WP-33);
the compiler pins its ``requires`` list to that display address and both
plan validators enforce the match.  Those symbols are display metadata
only: heading activation performs no target-memory operation, and the
actionable records that truly need the symbol resolve it through their own
entries - they are blocked at compile time when the base is unresolvable.
The plan-level symbol walk (``validate_plan``) and the engine dependency
walk (``_dependencies``) therefore must not treat a placeholder heading's
``requires`` as runtime dependencies.  Field evidence (local-only, never
quoted): a mono-based reference table whose pointer group headers lost
their symbol provider made the converter build refuse with "Selected entry
requires an unavailable symbol" although every actionable consumer was
already blocked and the build selection contained only supported records.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import struct
import tempfile
import unittest

from test_native_engine_code import Coordinator
from test_native_lua_activation import Memory
from ct2trainer.native.bundle import build_trainer, read_embedded_plan
from ct2trainer.native.compiler import compile_table
from ct2trainer.native.compiler import validate_plan as validate_compile_plan
from ct2trainer.native.engine import (NativeRuntimeError, TrainerEngine,
                                      validate_plan as validate_runtime_plan)

PROCESS = "FixtureTarget.exe"

GROUP_TABLE = (
    '<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
    '<CheatEntry><ID>1</ID><Description>Group</Description>'
    '<VariableType>Array of byte</VariableType><ByteLength>0</ByteLength>'
    '<Address>MissingBase</Address>'
    '<CheatEntries>'
    '<CheatEntry><ID>2</ID><Description>Kid Relative</Description>'
    '<VariableType>4 Bytes</VariableType>'
    '<Address>+4</Address></CheatEntry>'
    '<CheatEntry><ID>3</ID><Description>Kid Absolute</Description>'
    '<VariableType>4 Bytes</VariableType>'
    '<Address>1040</Address></CheatEntry>'
    '</CheatEntries></CheatEntry>'
    '</CheatEntries></CheatTable>')

PROVIDER_TABLE = (
    '<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
    '<CheatEntry><ID>10</ID><Description>Provider</Description>'
    '<VariableType>Auto Assembler Script</VariableType>'
    '<AssemblerScript>[ENABLE]'
    '\ndefine(BaseSym,1000)'
    '\nregistersymbol(BaseSym)'
    '\n[DISABLE]'
    '\nunregistersymbol(BaseSym)'
    '</AssemblerScript></CheatEntry>'
    '<CheatEntry><ID>11</ID><Description>Value Kid</Description>'
    '<VariableType>4 Bytes</VariableType>'
    '<Address>BaseSym+8</Address></CheatEntry>'
    '</CheatEntries></CheatTable>')


def _write_table(root, name, body):
    table = root / name
    table.write_text(body, encoding="utf-8")
    return table


def _fake_template(root):
    template = root / "template.exe"
    stub = bytearray(128)
    stub[:2] = b"MZ"
    struct.pack_into("<I", stub, 0x3C, 64)
    stub[64:68] = b"PE\0\0"
    struct.pack_into("<H", stub, 68, 0x8664)
    template.write_bytes(bytes(stub) + sha256(stub).digest() + b"CT2BASE1")
    return template


class PlaceholderHeadingPlanTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.table = _write_table(self.root, "group.ct", GROUP_TABLE)
        self.plan = compile_table(self.table, PROCESS)
        self.by_id = {e["id"]: e for e in self.plan["entries"]}

    def test_zero_length_group_header_demotes_to_supported_placeholder(self):
        entry = self.by_id[1]
        self.assertEqual(entry["kind"], "heading")
        self.assertTrue(entry["supported"])
        self.assertEqual(entry["address"], "MissingBase")
        self.assertEqual(entry["requires"], ["MissingBase"])

    def test_relative_child_blocked_absolute_child_supported(self):
        self.assertFalse(self.by_id[2]["supported"], self.by_id[2]["reason"])
        self.assertTrue(self.by_id[3]["supported"], self.by_id[3]["reason"])
        self.assertEqual(self.by_id[3]["kind"], "value")

    def test_plan_walk_ignores_placeholder_heading_requires(self):
        # The build gate (bundle.build_trainer) and the engine init both
        # run this walk; with the display-address symbol unresolved it
        # must not refuse the plan (the actionable consumer of the symbol
        # is the blocked child, visited on its own).
        validate_runtime_plan(self.plan)
        validate_compile_plan(self.plan)

    def test_control_walk_still_gates_real_dependencies(self):
        # The compiler's selection closure always pulls in an initially
        # unselected sole provider, so a forged plan is the only shape
        # where a selected supported record needs an unavailable symbol.
        # Re-bind the trainer identity to the forged selection so the
        # identity check cannot mask the walk: the symbol walk itself
        # must be what refuses.
        import hashlib
        import json
        table = _write_table(self.root, "provider.ct", PROVIDER_TABLE)
        plan = compile_table(table, PROCESS)
        validate_runtime_plan(plan)
        tampered = deepcopy(plan)
        for entry in tampered["entries"]:
            if entry["id"] == 10:
                entry["selected"] = False
        tampered["selected_ids"] = sorted(e["id"] for e in tampered["entries"]
                                          if e["selected"])
        identity_fields = {"engine": "ct2trainer",
                           "schema": tampered["schema"],
                           "table_sha256": tampered["table_sha256"],
                           "process_name": tampered["process_name"].casefold(),
                           "selected_ids": tampered["selected_ids"]}
        if tampered["schema"] == 2:
            identity_fields["target_architecture"] = \
                tampered["target_architecture"]
        identity = json.dumps(identity_fields, sort_keys=True,
                              separators=(",", ":")).encode("utf-8")
        tampered["trainer_id"] = hashlib.sha256(identity).hexdigest()[:16]
        with self.assertRaisesRegex(
                NativeRuntimeError,
                "Selected entry requires an unavailable symbol: BaseSym"):
            validate_runtime_plan(tampered)


class PlaceholderHeadingBuildTests(unittest.TestCase):
    """The exact converter build path: compile + build_trainer + roundtrip."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.table = _write_table(self.root, "group.ct", GROUP_TABLE)
        self.template = _fake_template(self.root)

    def test_default_selection_builds(self):
        # The converter default keeps every record selected (blocked rows
        # included as selected-but-unsupported); the build gate must pass
        # with the placeholder heading selected.
        plan = compile_table(self.table, PROCESS)
        output, _report = build_trainer(plan, self.root / "trainer.exe",
                                        self.template)
        self.assertEqual(read_embedded_plan(output), plan)

    def test_supported_only_selection_builds(self):
        # The converter GUI default selection: supported records only.
        plan = compile_table(self.table, PROCESS)
        supported = [e["id"] for e in plan["entries"] if e["supported"]]
        plan = compile_table(self.table, PROCESS, selected_ids=supported)
        output, _report = build_trainer(plan, self.root / "selected.exe",
                                        self.template)
        self.assertEqual(read_embedded_plan(output), plan)
        self.assertEqual(len(plan["entries"]), 3)


class PlaceholderHeadingEngineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.table = _write_table(self.root, "group.ct", GROUP_TABLE)
        self.memory = Memory()
        self.coordinator = Coordinator()
        self.plan = compile_table(self.table, PROCESS)
        validate_runtime_plan(self.plan)
        self.engine = TrainerEngine(self.plan,
                                    state_dir=self.root / "state",
                                    process_lock_dir=self.root / "shared",
                                    memory_factory=lambda name: self.memory,
                                    hook_coordinator=self.coordinator)
        self.engine.poll()

    def tearDown(self):
        self.engine.close()

    def test_heading_toggle_succeeds_without_resolving_display_symbol(self):
        # WP-53: activating the placeholder flips the group's own active
        # state only; the display-address symbol is never a runtime
        # dependency.
        self.assertTrue(self.engine.toggle(1))
        self.assertNotIn(1, self.engine.entry_errors)
        self.assertIn(1, self.engine.applied)

    def test_heading_toggle_roundtrips_off(self):
        self.assertTrue(self.engine.toggle(1))
        self.assertFalse(self.engine.toggle(1))
        self.assertNotIn(1, self.engine.applied)

    def test_heading_value_actions_refused_with_placeholder_reason(self):
        for operation in (lambda: self.engine.set_value(1, "1"),
                          lambda: self.engine.read_value(1)):
            with self.assertRaisesRegex(NativeRuntimeError,
                                        "non-actionable table placeholder"):
                operation()
        self.assertFalse(self.memory.writes)

    def test_absolute_child_stays_writable(self):
        self.assertEqual(self.engine.set_value(3, "7"), "7")
        self.assertEqual(self.memory.read(0x1040, 4), b"\x07\x00\x00\x00")


if __name__ == "__main__":
    unittest.main()
