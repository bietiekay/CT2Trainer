"""Parent/child activation wiring: flagged CT groups route through the tested policy.

The tested stage-1/2 model (``activation_policy``) is pinned by
``tests/test_native_activation_policy.py`` and
``tests/test_native_activation_fixture.py``.  This file proves the stage-3
wiring: ``compile_table`` classifies the CT group options into the tested
flag classes (both flags -> ``required_dependency``, activate-only ->
``direct_activation``, deactivate-only -> ``collective_off``;
``moBindActivation`` stays a visible named block), derives the
selected/supported subtree relations, and ``validate_plan`` re-derives them
byte-exactly.  The engine builds a second ActivationController, cascades ON
top-down and OFF bottom-up through the ordinary per-record paths with
persistence disabled (save boundary: ON stores only the requested heading's
wish; OFF clears every deactivated child's wish), mirrors engine-side effect
and wish state so the controller also sees children driven through their own
toggles, and keeps ``moBindActivation`` refused before any write, whether it
sits on the target or anywhere inside the cascade.  WP-14 extends the
contract to script parents: the parent's own effect (symbol provider) runs
first on ON, staged value children unlock through provider liveness, and
the OFF releases staged freezes before the provider teardown.  Value
(other non-heading) parents stay fail-closed with a named reason.
"""
from pathlib import Path
import json
import shutil
import tempfile
import unittest

from test_native_engine import FakeMemory

from ct2trainer.native.compiler import (NativeCompileError, compile_table,
                                          validate_plan as validate_compiler_plan)
from ct2trainer.native.engine import (TrainerEngine, NativeRuntimeError,
                                        validate_plan as validate_engine_plan)

PROCESS = "FixtureTarget.exe"

ANCHOR = (
    "[ENABLE]\n"
    "aobscanmodule(FixtureAnchor,FixtureTarget.exe,43 54 32 54 2D 46 49 58 2D 32 30 32 36 2D 30 31)\n"
    "registersymbol(FixtureAnchor)\n"
    "\n"
    "[DISABLE]\n"
    "unregistersymbol(FixtureAnchor)\n"
)

CHILD = (
    "[ENABLE]\n"
    "assert(FixtureAnchor+64,00 00 00 00)\n"
    "FixtureAnchor+64:\n"
    "  dd 1\n"
    "\n"
    "[DISABLE]\n"
    "assert(FixtureAnchor+64,01 00 00 00)\n"
    "FixtureAnchor+64:\n"
    "  dd 0\n"
)

GRANDCHILD = (
    "[ENABLE]\n"
    "assert(FixtureAnchor+68,00 00 00 00)\n"
    "FixtureAnchor+68:\n"
    "  dd 2\n"
    "\n"
    "[DISABLE]\n"
    "assert(FixtureAnchor+68,02 00 00 00)\n"
    "FixtureAnchor+68:\n"
    "  dd 0\n"
)

PLAIN_SCRIPT = (
    "[ENABLE]\n"
    "FixtureTarget.exe+40:\n"
    "db 01\n"
    "[DISABLE]\n"
    "FixtureTarget.exe+40:\n"
    "db 00\n"
)


def parent_table_xml(group_options='moActivateChildrenAsWell="1" '
                                  'moDeactivateChildrenAsWell="1"',
                     sub_options=""):
    """Own fixture table: 0 anchor script; 1 flagged group with 2 script
    child, 3 value child, 4 subgroup (optionally flagged) containing 5
    script grandchild."""
    options = f'<Options {group_options}/>' if group_options else ""
    sub = f'<Options {sub_options}/>' if sub_options else ""
    anchor = ('<CheatEntry><ID>0</ID><Description>"Anchor"</Description>'
              '<VariableType>Auto Assembler Script</VariableType>'
              f'<AssemblerScript>{ANCHOR}</AssemblerScript></CheatEntry>')
    child = ('<CheatEntry><ID>2</ID><Description>"Child"</Description>'
             '<VariableType>Auto Assembler Script</VariableType>'
             f'<AssemblerScript>{CHILD}</AssemblerScript></CheatEntry>')
    value = ('<CheatEntry><ID>3</ID><Description>"Value"</Description>'
             '<VariableType>4 Bytes</VariableType>'
             '<Address>FixtureAnchor+72</Address></CheatEntry>')
    grandchild = ('<CheatEntry><ID>5</ID><Description>"Grandchild"</Description>'
                  '<VariableType>Auto Assembler Script</VariableType>'
                  f'<AssemblerScript>{GRANDCHILD}</AssemblerScript></CheatEntry>')
    sub_group = ('<CheatEntry><ID>4</ID><Description>"Subgroup"</Description>'
                 '<GroupHeader>1</GroupHeader>' + sub +
                 '<CheatEntries>' + grandchild + '</CheatEntries></CheatEntry>')
    group = ('<CheatEntry><ID>1</ID><Description>"Group"</Description>'
             '<GroupHeader>1</GroupHeader>' + options +
             '<CheatEntries>' + child + value + sub_group +
             '</CheatEntries></CheatEntry>')
    return ('<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
            + anchor + group + '</CheatEntries></CheatTable>')


class ParentActivationCompilerTests(unittest.TestCase):
    """compile_table: option classification, subtree relations, validation."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="native-parent-compiler-"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def compile(self, name, xml, selected=None):
        table = self.root / name
        table.write_text(xml, encoding="utf-8")
        return compile_table(table, PROCESS, selected_ids=selected)

    def entries(self, plan):
        return {entry["id"]: entry for entry in plan["entries"]}

    def test_both_flags_classify_as_required_dependency(self):
        plan = self.compile("both.ct", parent_table_xml())
        by_id = self.entries(plan)
        self.assertEqual(by_id[1]["parent_activation"], "required_dependency")
        self.assertEqual(by_id[1]["kind"], "heading")
        self.assertTrue(by_id[1]["supported"])
        self.assertIn("required_dependency", by_id[1]["reason"])
        self.assertNotIn("parent_mo_bind", by_id[1])
        self.assertEqual(plan["parent_relations"],
                         {"1": {"2": "required_dependency",
                                "3": "required_dependency",
                                "4": "required_dependency",
                                "5": "required_dependency"}})
        validate_compiler_plan(plan)
        validate_engine_plan(plan)

    def test_activate_only_is_direct_activation(self):
        plan = self.compile("direct.ct",
                            parent_table_xml('moActivateChildrenAsWell="1"'))
        by_id = self.entries(plan)
        self.assertEqual(by_id[1]["parent_activation"], "direct_activation")
        self.assertEqual(plan["parent_relations"]["1"]["2"], "direct_activation")
        validate_compiler_plan(plan)

    def test_deactivate_only_is_collective_off(self):
        plan = self.compile("collective.ct",
                            parent_table_xml('moDeactivateChildrenAsWell="1"'))
        by_id = self.entries(plan)
        self.assertEqual(by_id[1]["parent_activation"], "collective_off")
        self.assertEqual(plan["parent_relations"]["1"]["5"], "collective_off")
        validate_compiler_plan(plan)

    def test_mo_bind_activation_stays_a_visible_named_block(self):
        plan = self.compile("mobind.ct",
                            parent_table_xml('moBindActivation="1"'))
        by_id = self.entries(plan)
        self.assertIs(by_id[1]["parent_mo_bind"], True)
        self.assertNotIn("parent_activation", by_id[1])
        self.assertNotIn("parent_relations", plan)
        self.assertIn("moBindActivation", by_id[1]["reason"])
        self.assertTrue(by_id[1]["supported"])
        validate_compiler_plan(plan)
        validate_engine_plan(plan)

    def test_mo_bind_descendant_keeps_marker_inside_flagged_subtree(self):
        plan = self.compile("mobind-nested.ct",
                            parent_table_xml(sub_options='moBindActivation="1"'))
        by_id = self.entries(plan)
        self.assertEqual(by_id[1]["parent_activation"], "required_dependency")
        self.assertIs(by_id[4]["parent_mo_bind"], True)
        self.assertEqual(plan["parent_relations"]["1"]["4"],
                         "required_dependency")
        validate_compiler_plan(plan)

    def script_parent_xml(self, options):
        # WP-14 (C2): a script record with children; the value child sits at
        # a literal address (no symbol dependency, so no staged metadata).
        return ('<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
                '<CheatEntry><ID>0</ID><Description>"Parent script"'
                '</Description><VariableType>Auto Assembler Script'
                '</VariableType>'
                f'<Options {options}/>'
                f'<AssemblerScript>{PLAIN_SCRIPT}</AssemblerScript>'
                '<CheatEntries>'
                '<CheatEntry><ID>1</ID><Description>"Value"'
                '</Description><VariableType>4 Bytes</VariableType>'
                '<Address>1000</Address></CheatEntry>'
                '</CheatEntries></CheatEntry>'
                '</CheatEntries></CheatTable>')

    def test_script_parent_flags_supported(self):
        # WP-14 (C2): script parents get the tested flag classes, mirroring
        # the heading contract (marker, subtree relations, re-derivation).
        plan = self.compile("script-both.ct", self.script_parent_xml(
            'moActivateChildrenAsWell="1" moDeactivateChildrenAsWell="1"'))
        by_id = self.entries(plan)
        self.assertTrue(by_id[0]["supported"])
        self.assertEqual(by_id[0]["kind"], "script")
        self.assertEqual(by_id[0]["parent_activation"], "required_dependency")
        self.assertIn("required_dependency", by_id[0]["reason"])
        self.assertNotIn("parent_mo_bind", by_id[0])
        self.assertEqual(plan["parent_relations"],
                         {"0": {"1": "required_dependency"}})
        validate_compiler_plan(plan)
        validate_engine_plan(plan)
        plan = self.compile("script-direct.ct",
                            self.script_parent_xml('moActivateChildrenAsWell="1"'))
        self.assertEqual(self.entries(plan)[0]["parent_activation"],
                         "direct_activation")
        validate_compiler_plan(plan)
        plan = self.compile("script-collective.ct",
                            self.script_parent_xml('moDeactivateChildrenAsWell="1"'))
        self.assertEqual(self.entries(plan)[0]["parent_activation"],
                         "collective_off")
        validate_compiler_plan(plan)

    def test_script_parent_mo_bind_stays_a_visible_named_block(self):
        plan = self.compile("script-mobind.ct",
                            self.script_parent_xml('moBindActivation="1"'))
        by_id = self.entries(plan)
        self.assertFalse(by_id[0]["supported"])
        self.assertIn("moBindActivation on a script parent", by_id[0]["reason"])
        self.assertNotIn("parent_activation", by_id[0])
        self.assertNotIn("parent_relations", plan)
        validate_compiler_plan(plan)

    def test_value_parent_flags_are_inert(self):
        # WP-14 (C2): pointer-chain "base" value records carry the same CT
        # propagation flags, but values have no activation of their own,
        # so the flags are inert: the record compiles as an ordinary
        # value, no parent marker, no cascade relation.
        xml = ('<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
               '<CheatEntry><ID>0</ID><Description>"Parent value"'
               '</Description><VariableType>4 Bytes</VariableType>'
               '<Address>1000</Address>'
               '<Options moActivateChildrenAsWell="1" moDeactivateChildrenAsWell="1"/>'
               '<CheatEntries>'
               '<CheatEntry><ID>1</ID><Description>"Value"'
               '</Description><VariableType>4 Bytes</VariableType>'
               '<Address>1004</Address></CheatEntry>'
               '</CheatEntries></CheatEntry>'
               '</CheatEntries></CheatTable>')
        plan = self.compile("value-parent.ct", xml)
        by_id = self.entries(plan)
        self.assertTrue(by_id[0]["supported"])
        self.assertEqual(by_id[0]["kind"], "value")
        self.assertNotIn("parent_activation", by_id[0])
        self.assertNotIn("parent_mo_bind", by_id[0])
        self.assertNotIn("parent_relations", plan)
        self.assertTrue(by_id[1]["supported"])
        validate_compiler_plan(plan)
        validate_engine_plan(plan)

    def test_plain_group_keeps_navigation_semantics(self):
        plan = self.compile("plain.ct", parent_table_xml(""))
        by_id = self.entries(plan)
        self.assertNotIn("parent_activation", by_id[1])
        self.assertNotIn("parent_mo_bind", by_id[1])
        self.assertNotIn("parent_relations", plan)
        self.assertEqual(by_id[1]["reason"],
                         "Navigation heading; CE group activation is not executed.")
        validate_compiler_plan(plan)

    def test_flag_without_supported_targets_drops_marker(self):
        # No supported+selected descendant -> the flagged group promises
        # nothing and stays a plain navigation heading.
        xml = ('<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
               '<CheatEntry><ID>1</ID><Description>"Group"</Description>'
               '<GroupHeader>1</GroupHeader>'
               '<Options moActivateChildrenAsWell="1"/>'
               '<CheatEntries>'
               '<CheatEntry><ID>2</ID><Description>"Broken"</Description>'
               '<VariableType>4 Bytes</VariableType></CheatEntry>'
               '</CheatEntries></CheatEntry>'
               '</CheatEntries></CheatTable>')
        plan = self.compile("empty-subtree.ct", xml)
        by_id = self.entries(plan)
        self.assertFalse(by_id[2]["supported"])
        self.assertNotIn("parent_activation", by_id[1])
        self.assertNotIn("parent_relations", plan)
        validate_compiler_plan(plan)

    def test_unselected_children_stay_outside_the_relations(self):
        plan = self.compile("selected.ct", parent_table_xml(), selected=[5])
        # The selection closure pulls the ancestors and the symbol provider.
        self.assertEqual(plan["selected_ids"], [0, 1, 4, 5])
        self.assertEqual(plan["parent_relations"],
                         {"1": {"4": "required_dependency",
                                "5": "required_dependency"}})
        validate_compiler_plan(plan)

    def test_validation_detects_tampered_relations(self):
        plan = self.compile("both.ct", parent_table_xml())
        plan["parent_relations"]["1"]["2"] = "collective_off"
        with self.assertRaisesRegex(NativeCompileError, "re-derive"):
            validate_compiler_plan(plan)
        plan = self.compile("both.ct", parent_table_xml())
        del plan["parent_relations"]["1"]["5"]
        with self.assertRaisesRegex(NativeCompileError, "re-derive"):
            validate_compiler_plan(plan)
        plan = self.compile("both.ct", parent_table_xml())
        plan["parent_relations"]["9"] = {"2": "required_dependency"}
        with self.assertRaisesRegex(NativeCompileError, "re-derive"):
            validate_compiler_plan(plan)

    def test_validation_detects_tampered_markers(self):
        plan = self.compile("both.ct", parent_table_xml())
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        by_id[1]["parent_activation"] = "collective_off"
        with self.assertRaisesRegex(NativeCompileError, "re-derive"):
            validate_compiler_plan(plan)
        plan = self.compile("plain.ct", parent_table_xml(""))
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        by_id[1]["parent_activation"] = "direct_activation"
        with self.assertRaisesRegex(NativeCompileError, "re-derive"):
            validate_compiler_plan(plan)
        # Marker on a supported selected heading without any supported
        # selected descendant: refused for the missing cascade target.
        plan = self.compile("empty-subtree.ct",
                             ('<CheatTable CheatEngineTableVersion="45">'
                              '<CheatEntries>'
                              '<CheatEntry><ID>1</ID><Description>"Group"'
                              '</Description><GroupHeader>1</GroupHeader>'
                              '<CheatEntries>'
                              '<CheatEntry><ID>2</ID><Description>"Broken"'
                              '</Description><VariableType>4 Bytes'
                              '</VariableType></CheatEntry>'
                              '</CheatEntries></CheatEntry>'
                              '</CheatEntries></CheatTable>'))
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        by_id[1]["parent_activation"] = "collective_off"
        with self.assertRaisesRegex(NativeCompileError,
                                    "without any cascade target"):
            validate_compiler_plan(plan)
        # Marker on a non-heading entry: refused for the kind.
        plan = self.compile("empty-subtree.ct",
                             ('<CheatTable CheatEngineTableVersion="45">'
                              '<CheatEntries>'
                              '<CheatEntry><ID>1</ID><Description>"Group"'
                              '</Description><GroupHeader>1</GroupHeader>'
                              '<CheatEntries>'
                              '<CheatEntry><ID>2</ID><Description>"Broken"'
                              '</Description><VariableType>4 Bytes'
                              '</VariableType></CheatEntry>'
                              '</CheatEntries></CheatEntry>'
                              '</CheatEntries></CheatTable>'))
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        by_id[2]["parent_activation"] = "collective_off"
        with self.assertRaisesRegex(NativeCompileError,
                                    "requires a supported selected heading"):
            validate_compiler_plan(plan)

    def test_json_roundtrip_revalidates(self):
        plan = self.compile("both.ct", parent_table_xml())
        restored = json.loads(json.dumps(plan))
        validate_compiler_plan(restored)
        validate_engine_plan(restored)


class ParentEngineMemory(FakeMemory):
    """Fixture memory carrying the identity the hook manager requires."""

    @property
    def identity(self):
        return self.pid, self.creation_time

    def is_executable(self, address, size):
        return False


class ParentActivationEngineTests(unittest.TestCase):
    """Engine roundtrip: cascades run through the ordinary per-record paths."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="native-parent-engine-"))
        self.memory = ParentEngineMemory()
        self.engine = None
        self.plan = None

    def tearDown(self):
        if self.engine is not None and not self.engine.closed:
            self.engine.close()
        shutil.rmtree(self.root, ignore_errors=True)

    def start_engine(self, name, group_options, sub_options=""):
        table = self.root / name
        table.write_text(parent_table_xml(group_options, sub_options),
                         encoding="utf-8")
        self.plan = compile_table(table, PROCESS)
        self.engine = TrainerEngine(
            self.plan, state_dir=self.root / (name + "-state"),
            process_lock_dir=self.root / (name + "-shared"),
            memory_factory=lambda _name: self.memory)
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)
        return self.engine

    BOTH = 'moActivateChildrenAsWell="1" moDeactivateChildrenAsWell="1"'

    def test_required_on_cascades_subtree_and_saves_only_parent_wish(self):
        engine = self.start_engine("required.ct", self.BOTH)
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(set(engine.applied), {0, 2, 5})
        self.assertEqual(self.memory.read(0x1064, 4), b"\x01\x00\x00\x00")
        self.assertEqual(self.memory.read(0x1068, 4), b"\x02\x00\x00\x00")
        # The value child gets no effect; only the heading's wish persists.
        self.assertEqual(self.memory.read(0x1072, 4), bytes(4))
        self.assertEqual(engine.desired, {1})

    def test_required_off_restores_children_and_clears_wishes(self):
        engine = self.start_engine("required.ct", self.BOTH)
        engine.toggle(1, True)
        self.assertFalse(engine.toggle(1, False))
        self.assertEqual(self.memory.read(0x1064, 4), bytes(4))
        self.assertEqual(self.memory.read(0x1068, 4), bytes(4))
        self.assertNotIn(2, engine.applied)
        self.assertNotIn(5, engine.applied)
        self.assertEqual(engine.desired, set())

    def test_saved_parent_wish_replays_on_next_attach(self):
        engine = self.start_engine("replay.ct", self.BOTH)
        engine.toggle(1, True)
        self.assertTrue(engine.close())
        self.memory = ParentEngineMemory()
        self.engine = TrainerEngine(
            self.plan, state_dir=self.root / "replay.ct-state",
            process_lock_dir=self.root / "replay.ct-shared",
            memory_factory=lambda _name: self.memory)
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)
        self.assertEqual(self.engine.desired, {1})
        self.assertNotIn(1, self.engine.applied)
        self.assertIn(2, self.engine.applied)
        self.assertIn(5, self.engine.applied)
        self.assertEqual(self.memory.read(0x1064, 4), b"\x01\x00\x00\x00")
        self.assertEqual(self.memory.read(0x1068, 4), b"\x02\x00\x00\x00")

    def test_direct_activation_honours_child_wishes(self):
        engine = self.start_engine("direct.ct",
                                   'moActivateChildrenAsWell="1"')
        self.assertTrue(engine.toggle(2, True))
        self.assertEqual(self.memory.read(0x1064, 4), b"\x01\x00\x00\x00")
        self.assertTrue(engine.toggle(1, True))
        # The wished child stays on; the unwished grandchild is not pulled
        # in by the parent ON.
        self.assertIn(2, engine.applied)
        self.assertNotIn(5, engine.applied)
        self.assertEqual(self.memory.read(0x1068, 4), bytes(4))
        self.assertEqual(engine.desired, {0, 1, 2})
        self.assertFalse(engine.toggle(1, False))
        # The parent OFF deactivates the explicitly active child and clears
        # both wishes; the provider anchor keeps its own wish.
        self.assertNotIn(2, engine.applied)
        self.assertEqual(self.memory.read(0x1064, 4), bytes(4))
        self.assertEqual(engine.desired, {0})

    def test_collective_off_parent_on_is_passive_and_off_clears_active(self):
        engine = self.start_engine("collective.ct",
                                   'moDeactivateChildrenAsWell="1"')
        self.assertTrue(engine.toggle(1, True))
        # ON activates nothing; the heading only saves its own wish.
        self.assertNotIn(2, engine.applied)
        self.assertNotIn(5, engine.applied)
        self.assertEqual(self.memory.read(0x1064, 4), bytes(4))
        self.assertEqual(engine.desired, {1})
        self.assertTrue(engine.toggle(2, True))
        self.assertFalse(engine.toggle(1, False))
        # The OFF sees the child enabled through its own toggle (mirrored
        # into the controller) and deactivates it, clearing its wish.
        self.assertNotIn(2, engine.applied)
        self.assertEqual(self.memory.read(0x1064, 4), bytes(4))
        self.assertEqual(engine.desired, {0})

    def test_mo_bind_group_refused_visibly_without_effects(self):
        engine = self.start_engine("mobind.ct", 'moBindActivation="1"')
        with self.assertRaisesRegex(NativeRuntimeError, "moBindActivation"):
            engine.toggle(1, True)
        with self.assertRaisesRegex(NativeRuntimeError, "moBindActivation"):
            engine.toggle(1, False)
        self.assertEqual(self.memory.writes, [])
        self.assertEqual(set(engine.applied), set())
        self.assertEqual(engine.desired, set())
        self.assertFalse(engine.blocked)
        self.assertIn("moBindActivation", engine.entry_errors[1])
        self.assertEqual(engine.parent_query(1),
                         {"record_id": 2, "active": False, "hold": False,
                          "saved_wish": False})

    def test_mo_bind_descendant_blocks_whole_cascade_before_writes(self):
        engine = self.start_engine("mobind-nested.ct", self.BOTH,
                                   sub_options='moBindActivation="1"')
        with self.assertRaisesRegex(NativeRuntimeError, "moBindActivation"):
            engine.toggle(1, True)
        self.assertEqual(self.memory.writes, [])
        self.assertEqual(set(engine.applied), set())
        self.assertEqual(engine.desired, set())
        # With no active children the OFF request expands to the parent
        # record alone (the moBind record can never be active, so it never
        # enters the cascade): the trivial no-op succeeds and the state
        # stays exactly as the refusal left it.
        self.assertFalse(engine.toggle(1, False))
        self.assertEqual(self.memory.writes, [])
        self.assertEqual(set(engine.applied), set())
        self.assertEqual(engine.desired, set())

    def test_partial_cascade_failure_holds_subtree_and_keeps_partial_effect(self):
        engine = self.start_engine("partial.ct", self.BOTH)
        self.memory.data[104] = 9  # break the grandchild's enable assertion (0x1068)
        with self.assertRaisesRegex(NativeRuntimeError, "assertion"):
            engine.toggle(1, True)
        # The first child landed before the failure: the partial state stays
        # visible, nothing is saved, and the cascade is under a safety hold.
        self.assertIn(2, engine.applied)
        self.assertEqual(self.memory.read(0x1064, 4), b"\x01\x00\x00\x00")
        self.assertNotIn(5, engine.applied)
        self.assertEqual(engine.desired, set())
        self.assertFalse(engine.blocked)
        with self.assertRaisesRegex(NativeRuntimeError, "safety hold"):
            engine.toggle(1, False)
        self.assertTrue(engine.parent_query(1)["hold"])

    def test_toggle_before_attach_refused_and_auto_on_waits_for_attach(self):
        table = self.root / "autoon.ct"
        table.write_text(parent_table_xml(self.BOTH), encoding="utf-8")
        self.plan = compile_table(table, PROCESS)
        self.engine = TrainerEngine(
            self.plan, state_dir=self.root / "autoon.ct-state",
            process_lock_dir=self.root / "autoon.ct-shared",
            memory_factory=lambda _name: self.memory)
        with self.assertRaisesRegex(NativeRuntimeError, "not connected"):
            self.engine.toggle(1, True)
        self.engine.request_auto_on(1)
        self.assertEqual(self.engine.desired, {1})
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)
        self.assertIn(2, self.engine.applied)
        self.assertIn(5, self.engine.applied)
        self.assertEqual(self.engine.desired, {1})

    def test_plain_group_heading_stays_a_navigation_noop(self):
        engine = self.start_engine("plain.ct", "")
        with self.assertRaisesRegex(NativeRuntimeError, "Navigation heading"):
            engine.toggle(1, True)

    def start_script_parent_engine(self, name, options):
        # WP-14 (C2): the anchor provider is itself the flagged parent; its
        # value child is staged on the symbol it registers at activation.
        xml = ('<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
               '<CheatEntry><ID>0</ID><Description>"Provider parent"'
               '</Description><VariableType>Auto Assembler Script'
               '</VariableType>'
               f'<Options {options}/>'
               f'<AssemblerScript>{ANCHOR}</AssemblerScript>'
               '<CheatEntries>'
               '<CheatEntry><ID>1</ID><Description>"Staged value"'
               '</Description><VariableType>4 Bytes</VariableType>'
               '<Address>FixtureAnchor+72</Address></CheatEntry>'
               '</CheatEntries></CheatEntry>'
               '</CheatEntries></CheatTable>')
        table = self.root / name
        table.write_text(xml, encoding="utf-8")
        self.plan = compile_table(table, PROCESS)
        self.engine = TrainerEngine(
            self.plan, state_dir=self.root / (name + "-state"),
            process_lock_dir=self.root / (name + "-shared"),
            memory_factory=lambda _name: self.memory)
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)
        return self.engine

    def test_script_parent_on_unlocks_staged_child_and_saves_only_parent_wish(self):
        engine = self.start_script_parent_engine("sp-on.ct", self.BOTH)
        # The staged child is pending while the provider is inactive.
        with self.assertRaisesRegex(NativeRuntimeError,
                                    "requires active provider"):
            engine.read_value(1)
        with self.assertRaisesRegex(NativeRuntimeError,
                                    "requires active provider"):
            engine.set_value(1, "7")
        with self.assertRaisesRegex(NativeRuntimeError,
                                    "requires active provider"):
            engine.set_freeze(1, True)
        # The parent's own effect lands first, then the staged child is
        # usable through provider liveness.
        self.assertTrue(engine.toggle(0, True))
        self.assertIn(0, engine.applied)
        self.assertEqual(engine.read_value(1), "0")
        self.assertEqual(engine.set_value(1, "7"), "7")
        self.assertEqual(self.memory.read(0x1072, 4), b"\x07\x00\x00\x00")
        engine.set_freeze(1, True)
        self.assertIn(1, engine.frozen)
        # Save boundary: only the requested parent's wish persists.
        self.assertEqual(engine.desired, {0})

    def test_script_parent_off_releases_staged_freeze_before_teardown(self):
        engine = self.start_script_parent_engine("sp-off.ct", self.BOTH)
        engine.toggle(0, True)
        engine.set_freeze(1, True)
        self.assertIn(1, engine.frozen)
        self.assertFalse(engine.toggle(0, False))
        # The staged freeze was released with the provider teardown, the
        # provider effect is gone, and no wish remains.
        self.assertNotIn(1, engine.frozen)
        self.assertNotIn(0, engine.applied)
        self.assertEqual(engine.desired, set())
        with self.assertRaisesRegex(NativeRuntimeError,
                                    "requires active provider"):
            engine.read_value(1)
        self.assertFalse(engine.blocked)

    def test_script_parent_wish_replays_provider_before_children_on_attach(self):
        engine = self.start_script_parent_engine("sp-replay.ct", self.BOTH)
        engine.toggle(0, True)
        self.assertEqual(engine.read_value(1), "0")
        self.assertTrue(engine.close())
        self.memory = ParentEngineMemory()
        self.engine = TrainerEngine(
            self.plan, state_dir=self.root / "sp-replay.ct-state",
            process_lock_dir=self.root / "sp-replay.ct-shared",
            memory_factory=lambda _name: self.memory)
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)
        self.assertEqual(self.engine.desired, {0})
        self.assertIn(0, self.engine.applied)
        self.assertEqual(self.engine.read_value(1), "0")


if __name__ == "__main__":
    unittest.main()
