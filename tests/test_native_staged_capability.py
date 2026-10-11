"""WP-14 (C1): staged value gating on provider liveness.

A staged record (its address needs a symbol a provider registers at
activation) is value-accessible only while every provider is live.  Value
reads, writes and freezes are refused with a named error while any
provider is inactive - a state, not a fault - and the value path never
auto-enables providers (script activation keeps its ordinary
dependency-ordered auto-enable).  Both plan validators re-derive the
``staged`` marker byte-exactly and refuse tampered metadata.
"""
from copy import deepcopy
import tempfile
import unittest
from pathlib import Path

from test_native_engine import FakeMemory

from ct2trainer.native.compiler import (NativeCompileError, compile_table,
                                        validate_plan as validate_compiler_plan)
from ct2trainer.native.engine import (NativeRuntimeError, TrainerEngine,
                                      validate_plan as validate_engine_plan)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "windows" / "fixture_target" / "fixture.ct"
PROCESS = "FixtureTarget.exe"


class StagedPlanTests(unittest.TestCase):
    """Compiler marker + validator re-derivation on the pinned fixture."""

    def setUp(self):
        self.plan = compile_table(FIXTURE, PROCESS)

    def entries(self):
        return {entry["id"]: entry for entry in self.plan["entries"]}

    def test_fixture_staged_markers_match_dependency_resolution(self):
        by_id = self.entries()
        # Record 0 (the anchor) registers FixtureAnchor; records 1-3
        # resolve their addresses through it and are staged on it.
        self.assertNotIn("staged", by_id[0])
        for identifier in (1, 2, 3):
            self.assertEqual(
                by_id[identifier]["staged"],
                {"provider_ids": [0],
                 "provider_labels": [by_id[0]["path"]]},
            )
        validate_compiler_plan(self.plan)
        validate_engine_plan(self.plan)

    def test_tampered_staged_metadata_refused_by_both_validators(self):
        invalid = deepcopy(self.plan)
        by_id = {entry["id"]: entry for entry in invalid["entries"]}
        by_id[2]["staged"]["provider_ids"] = [1]
        with self.assertRaisesRegex(NativeCompileError, "Staged metadata"):
            validate_compiler_plan(invalid)
        with self.assertRaises(NativeRuntimeError):
            validate_engine_plan(invalid)

    def test_staged_marker_missing_or_forged_is_refused(self):
        # Stripping the marker from a staged record is refused.
        invalid = deepcopy(self.plan)
        by_id = {entry["id"]: entry for entry in invalid["entries"]}
        del by_id[2]["staged"]
        with self.assertRaisesRegex(NativeCompileError, "Staged metadata"):
            validate_compiler_plan(invalid)
        # Forging a marker on a dependency-less record is refused.
        invalid = deepcopy(self.plan)
        by_id = {entry["id"]: entry for entry in invalid["entries"]}
        by_id[0]["staged"] = {"provider_ids": [1], "provider_labels": ["x"]}
        with self.assertRaisesRegex(NativeCompileError,
                                    "requires supported non-heading"):
            validate_compiler_plan(invalid)


class StagedEngineTests(unittest.TestCase):
    """Value access paths gate on provider liveness (fixture engine)."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.shared = self.directory / "shared"
        self.plan = compile_table(FIXTURE, PROCESS)
        self.memory = FakeMemory()
        self.factory = lambda _name: self.memory
        self.engine = None

    def tearDown(self):
        if self.engine is not None and not self.engine.closed:
            self.engine.close()
        self.temp.cleanup()

    def start(self):
        self.engine = TrainerEngine(self.plan, self.directory, self.factory,
                                    self.shared)
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)
        return self.engine

    def test_value_access_refused_while_provider_inactive(self):
        engine = self.start()
        for call in (lambda: engine.read_value(2),
                     lambda: engine.set_value(2, "1"),
                     lambda: engine.set_freeze(2, True)):
            with self.subTest():
                with self.assertRaisesRegex(NativeRuntimeError,
                                            "requires active provider"):
                    call()
        self.assertEqual(self.memory.writes, [])
        self.assertEqual(engine.desired, set())
        self.assertFalse(engine.blocked)
        self.assertNotIn(2, engine.frozen)

    def test_provider_enable_unlocks_value_path_and_disable_relocks(self):
        engine = self.start()
        # Script activation keeps its ordinary auto-enable of providers.
        engine.toggle(1, True)
        self.assertEqual(set(engine.applied), {0, 1})
        self.assertEqual(engine.read_value(2), "1234")
        self.assertEqual(engine.set_value(2, "4321"), "4321")
        self.assertEqual(self.memory.read(0x1010, 4), b"\xe1\x10\x00\x00")
        engine.set_freeze(2, True)
        self.assertIn(2, engine.frozen)
        # A direct provider disable is refused while dependents are live
        # (existing dependent guard).
        with self.assertRaisesRegex(NativeRuntimeError, "dependent"):
            engine.toggle(0, False)
        engine.set_freeze(2, False)
        engine.toggle(1, False)
        self.assertFalse(engine.toggle(0, False))
        # The staged child is pending again.
        with self.assertRaisesRegex(NativeRuntimeError,
                                    "requires active provider"):
            engine.read_value(2)
        self.assertEqual(engine.desired, set())
        self.assertFalse(engine.blocked)


if __name__ == "__main__":
    unittest.main()
