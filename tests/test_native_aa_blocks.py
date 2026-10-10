# -*- coding: utf-8 -*-
"""Focused fixture-driven tests for the pinned AA block models.

Drives ``src/ct2trainer/native/aa_blocks.py`` against the synthetic,
hand-verified programs of ``tests/aa_blocks_fixture_data.py`` (no
TableReferences, no CE inputs).  Pinned scenarios:

- ``prune_conditionals``: ``{$if <define>=<value>}`` / ``{$if ... != ...}``
  with define-name or integer-literal operands (decimal, ``$``/``0x`` hex,
  negative), case-insensitive directives and define lookup, nested
  branches with depth bound 16, defined-but-false branches pruned,
  decisions and original line numbers recorded; undefined defines,
  unsupported operators, unclosed blocks, orphaned markers, duplicate
  ``{$else}`` and over-deep nesting are refused with line context.
- ``resolve_nested_assembly``: ``autoassemble("Label")`` /
  ``autoasm("Label")`` resolved against internal ``name:`` definitions and
  an injectable external label registry, deterministic callee-before-
  caller topological order, invocation depths, and refusal of unknown
  labels, internal/external name collisions, duplicate invocations,
  duplicate definitions and cycles (path named).
- ``analyze_blocks``: pruning first, then nested resolution on the
  pruned source; nested errors remapped back to original source lines;
  deterministic combined reports.
"""
import json
import unittest

from ct2trainer.native.aa_blocks import (
    BlockAnalysis,
    BlockStructureError,
    CycleError,
    DuplicateInvocationError,
    LabelCollisionError,
    UnknownLabelError,
    analyze_blocks,
    prune_conditionals,
    resolve_nested_assembly,
)

try:
    from aa_blocks_fixture_data import (
        CASE_INSENSITIVE,
        CALLS_EXTERNAL,
        COLLISION_INTERNAL,
        CONDITIONAL_ELSE,
        CONDITIONAL_TRUE,
        COMBINED_ANALYZE,
        CYCLE,
        DEAD_BODY_UNKNOWN,
        DEFINE_NAME_RHS,
        DOUBLE_ELSE,
        DUP_DEFINE,
        DUP_INVOKE,
        EXTERNAL_SHARED,
        HEX_LITERAL,
        LABELS_CHAIN,
        NEGATIVE_LITERAL,
        NESTED_INNER_ELSE,
        NESTED_TRUE,
        ORPHAN_ELSE,
        ORPHAN_ENDIF,
        REMAP,
        SELF_CYCLE,
        UNCLOSED_IF,
        UNDEFINED_DEFINE,
        UNKNOWN_LABEL,
        UNSUPPORTED_EXPR,
        depth_program,
    )
except ModuleNotFoundError:  # invoked as tests.test_native_aa_blocks
    from tests.aa_blocks_fixture_data import (
        CASE_INSENSITIVE,
        CALLS_EXTERNAL,
        COLLISION_INTERNAL,
        CONDITIONAL_ELSE,
        CONDITIONAL_TRUE,
        COMBINED_ANALYZE,
        CYCLE,
        DEAD_BODY_UNKNOWN,
        DEFINE_NAME_RHS,
        DOUBLE_ELSE,
        DUP_DEFINE,
        DUP_INVOKE,
        EXTERNAL_SHARED,
        HEX_LITERAL,
        LABELS_CHAIN,
        NEGATIVE_LITERAL,
        NESTED_INNER_ELSE,
        NESTED_TRUE,
        ORPHAN_ELSE,
        ORPHAN_ENDIF,
        REMAP,
        SELF_CYCLE,
        UNCLOSED_IF,
        UNDEFINED_DEFINE,
        UNKNOWN_LABEL,
        UNSUPPORTED_EXPR,
        depth_program,
    )


class ConditionalPruningTests(unittest.TestCase):
    def test_true_branch_kept_and_decision_recorded(self):
        plan = prune_conditionals(CONDITIONAL_TRUE, {"DEBUG": 1})
        self.assertEqual(plan.lines, ("[ENABLE]", "db 01", "db 02", "[DISABLE]", "db 00"))
        self.assertEqual(plan.decisions[0].line, 2)
        self.assertEqual(plan.decisions[0].condition, "DEBUG=1")
        self.assertEqual(plan.decisions[0].chosen, "if")
        self.assertEqual(plan.line_map, (1, 3, 5, 6, 7))
        self.assertEqual(plan.max_depth, 1)

    def test_false_branch_dropped_without_else(self):
        plan = prune_conditionals(CONDITIONAL_TRUE, {"DEBUG": 0})
        self.assertEqual(plan.lines, ("[ENABLE]", "db 02", "[DISABLE]", "db 00"))
        self.assertEqual(plan.decisions[0].chosen, "else")

    def test_else_branch_selected(self):
        plan = prune_conditionals(CONDITIONAL_ELSE, {"MODE": 1})
        self.assertEqual(plan.lines, ("[ENABLE]", "db 02"))
        self.assertEqual(plan.line_map, (1, 5))
        self.assertEqual(plan.decisions[0].chosen, "else")

    def test_if_branch_selected_when_equal(self):
        plan = prune_conditionals(CONDITIONAL_ELSE, {"MODE": 2})
        self.assertEqual(plan.lines, ("[ENABLE]", "db 01"))
        self.assertEqual(plan.decisions[0].chosen, "if")

    def test_nested_three_levels_all_if(self):
        plan = prune_conditionals(NESTED_TRUE, {"A": 1, "B": 1, "C": 1})
        self.assertEqual(plan.lines, ("[ENABLE]", "db 0A"))
        self.assertEqual(plan.max_depth, 3)
        self.assertEqual([d.chosen for d in plan.decisions], ["if", "if", "if"])

    def test_nested_inner_else_selected(self):
        plan = prune_conditionals(NESTED_INNER_ELSE, {"A": 1, "B": 1})
        self.assertEqual(plan.lines, ("[ENABLE]", "db 0B"))
        self.assertEqual([d.chosen for d in plan.decisions], ["if", "else"])
        self.assertEqual(plan.line_map, (1, 6))

    def test_define_name_right_hand_side(self):
        plan = prune_conditionals(DEFINE_NAME_RHS, {"A": 5, "B": 5})
        self.assertEqual(plan.lines, ("db 01",))
        self.assertEqual(plan.decisions[0].chosen, "if")
        plan = prune_conditionals(DEFINE_NAME_RHS, {"A": 5, "B": 6})
        self.assertEqual(plan.lines, ())

    def test_hex_literal(self):
        plan = prune_conditionals(HEX_LITERAL, {"A": 255})
        self.assertEqual(plan.lines, ("db 01",))
        self.assertEqual(plan.decisions[0].chosen, "if")

    def test_negative_literal(self):
        plan = prune_conditionals(NEGATIVE_LITERAL, {"A": -1})
        self.assertEqual(plan.lines, ("db 01",))

    def test_case_insensitive_directives_and_lookup(self):
        plan = prune_conditionals(CASE_INSENSITIVE, {"debug": 1})
        self.assertEqual(plan.lines, ("db 01",))
        self.assertEqual(plan.decisions[0].condition, "DEBUG=1")

    def test_undefined_define_is_refused(self):
        with self.assertRaises(BlockStructureError) as ctx:
            prune_conditionals(UNDEFINED_DEFINE, {})
        self.assertEqual(ctx.exception.line, 1)
        self.assertIn("'MISSING'", str(ctx.exception))

    def test_unsupported_expression_is_refused(self):
        with self.assertRaises(BlockStructureError) as ctx:
            prune_conditionals(UNSUPPORTED_EXPR, {"A": 1})
        self.assertEqual(ctx.exception.line, 1)

    def test_unclosed_if_refused_with_opening_line(self):
        with self.assertRaises(BlockStructureError) as ctx:
            prune_conditionals(UNCLOSED_IF, {"DEBUG": 1})
        self.assertEqual(ctx.exception.line, 2)
        self.assertIn("line 2", str(ctx.exception))

    def test_orphan_else_refused(self):
        with self.assertRaises(BlockStructureError) as ctx:
            prune_conditionals(ORPHAN_ELSE, {"DEBUG": 1})
        self.assertEqual(ctx.exception.line, 3)

    def test_orphan_endif_refused(self):
        with self.assertRaises(BlockStructureError) as ctx:
            prune_conditionals(ORPHAN_ENDIF, {"DEBUG": 1})
        self.assertEqual(ctx.exception.line, 3)

    def test_duplicate_else_refused(self):
        with self.assertRaises(BlockStructureError) as ctx:
            prune_conditionals(DOUBLE_ELSE, {"A": 1})
        self.assertEqual(ctx.exception.line, 5)

    def test_depth_16_is_allowed(self):
        plan = prune_conditionals(depth_program(16), {"A": 1})
        self.assertEqual(plan.max_depth, 16)
        self.assertEqual(plan.lines, ("db 01",))

    def test_depth_17_is_refused(self):
        with self.assertRaises(BlockStructureError) as ctx:
            prune_conditionals(depth_program(17), {"A": 1})
        self.assertEqual(ctx.exception.line, 17)

    def test_empty_source_is_empty_plan(self):
        plan = prune_conditionals("")
        self.assertEqual(plan.lines, ())
        self.assertEqual(plan.decisions, ())
        self.assertEqual(plan.max_depth, 0)

    def test_non_string_source_is_refused(self):
        with self.assertRaises(BlockStructureError):
            prune_conditionals(None)

    def test_defines_validation(self):
        with self.assertRaises(BlockStructureError):
            prune_conditionals(HEX_LITERAL, ("A", 255))
        with self.assertRaises(BlockStructureError):
            prune_conditionals(HEX_LITERAL, {"A": "255"})
        with self.assertRaises(BlockStructureError):
            prune_conditionals(HEX_LITERAL, {"A": 1, "a": 2})
        with self.assertRaises(BlockStructureError):
            prune_conditionals(HEX_LITERAL, {"1A": 255})

    def test_crlf_source_is_normalized(self):
        lf = prune_conditionals(CONDITIONAL_TRUE, {"DEBUG": 1})
        crlf = prune_conditionals(CONDITIONAL_TRUE.replace("\n", "\r\n"), {"DEBUG": 1})
        self.assertEqual(lf.report(), crlf.report())

    def test_report_is_deterministic_and_serializable(self):
        plan = prune_conditionals(NESTED_TRUE, {"A": 1, "B": 1, "C": 0})
        self.assertEqual(plan.report(), prune_conditionals(NESTED_TRUE, {"A": 1, "B": 1, "C": 0}).report())
        json.dumps(plan.report())


class NestedAssemblyTests(unittest.TestCase):
    def test_chain_topological_order(self):
        plan = resolve_nested_assembly(LABELS_CHAIN)
        self.assertEqual(plan.order, ("third", "second", "first"))

    def test_chain_invocation_depths(self):
        plan = resolve_nested_assembly(LABELS_CHAIN)
        self.assertEqual(
            {(i.label, i.line, i.depth) for i in plan.invocations},
            {("second", 3, 1), ("third", 6, 2)},
        )

    def test_external_label_resolved(self):
        plan = resolve_nested_assembly(CALLS_EXTERNAL, {"sharedHelper": EXTERNAL_SHARED})
        self.assertEqual(plan.order, ("sharedHelper", "patch"))
        self.assertEqual(len(plan.invocations), 1)
        self.assertEqual((plan.invocations[0].label, plan.invocations[0].line,
                          plan.invocations[0].depth), ("sharedHelper", 2, 1))

    def test_collision_refused(self):
        with self.assertRaises(LabelCollisionError) as ctx:
            resolve_nested_assembly(COLLISION_INTERNAL, {"sharedHelper": EXTERNAL_SHARED})
        self.assertEqual(ctx.exception.label, "sharedHelper")
        self.assertEqual(ctx.exception.line, 1)

    def test_duplicate_invocation_refused_with_lines(self):
        with self.assertRaises(DuplicateInvocationError) as ctx:
            resolve_nested_assembly(DUP_INVOKE)
        self.assertEqual(ctx.exception.label, "helper")
        self.assertEqual(ctx.exception.lines, (1, 4))

    def test_duplicate_definition_refused(self):
        with self.assertRaises(BlockStructureError) as ctx:
            resolve_nested_assembly(DUP_DEFINE)
        self.assertEqual(ctx.exception.line, 3)

    def test_cycle_refused_with_path(self):
        with self.assertRaises(CycleError) as ctx:
            resolve_nested_assembly(CYCLE)
        self.assertEqual(ctx.exception.path, ("a", "b", "a"))

    def test_self_cycle_refused(self):
        with self.assertRaises(CycleError) as ctx:
            resolve_nested_assembly(SELF_CYCLE)
        self.assertEqual(ctx.exception.path, ("a", "a"))

    def test_unknown_label_refused(self):
        with self.assertRaises(UnknownLabelError) as ctx:
            resolve_nested_assembly(UNKNOWN_LABEL)
        self.assertEqual(ctx.exception.label, "missing")
        self.assertEqual(ctx.exception.line, 1)

    def test_dead_body_still_validated(self):
        with self.assertRaises(UnknownLabelError):
            resolve_nested_assembly(DEAD_BODY_UNKNOWN)

    def test_no_labels_no_invocations(self):
        plan = resolve_nested_assembly("db 01\ndb 02\n")
        self.assertEqual(plan.order, ())
        self.assertEqual(plan.invocations, ())

    def test_label_with_comment_is_recognized(self):
        plan = resolve_nested_assembly("label1: // note\ndb 01\n")
        self.assertEqual(plan.order, ("label1",))

    def test_address_label_is_not_a_named_label(self):
        plan = resolve_nested_assembly("1000:\ndb 01\n")
        self.assertEqual(plan.order, ())

    def test_opaque_invocation_spelling_is_ignored(self):
        plan = resolve_nested_assembly("autoasm('x')\ndb 01\n")
        self.assertEqual(plan.invocations, ())

    def test_isolated_labels_ordered_by_definition_line(self):
        plan = resolve_nested_assembly("zeta:\ndb 01\nalpha:\ndb 02\n")
        self.assertEqual(plan.order, ("zeta", "alpha"))

    def test_registry_validation(self):
        with self.assertRaises(BlockStructureError):
            resolve_nested_assembly(CALLS_EXTERNAL, ("sharedHelper", EXTERNAL_SHARED))
        with self.assertRaises(BlockStructureError):
            resolve_nested_assembly(CALLS_EXTERNAL, {"sharedHelper": 7})
        with self.assertRaises(BlockStructureError):
            resolve_nested_assembly(
                CALLS_EXTERNAL, {"sharedHelper": EXTERNAL_SHARED, "SHAREDHELPER": EXTERNAL_SHARED}
            )

    def test_report_is_deterministic_and_serializable(self):
        plan = resolve_nested_assembly(LABELS_CHAIN)
        self.assertEqual(plan.report(), resolve_nested_assembly(LABELS_CHAIN).report())
        json.dumps(plan.report())


class AnalyzeBlocksTests(unittest.TestCase):
    def test_combined_ok(self):
        analysis = analyze_blocks(COMBINED_ANALYZE, defines={"PATCH": 1})
        self.assertTrue(analysis.ok)
        self.assertIsNotNone(analysis.block_plan)
        self.assertIsNotNone(analysis.nested)
        self.assertEqual(analysis.nested.order, ("second", "first"))
        self.assertEqual(len(analysis.nested.invocations), 1)
        self.assertEqual(analysis.block_plan.decisions[0].chosen, "if")

    def test_nested_error_line_is_remapped_to_source(self):
        analysis = analyze_blocks(REMAP, defines={"X": 1})
        self.assertFalse(analysis.ok)
        self.assertIsInstance(analysis.errors[0], UnknownLabelError)
        self.assertEqual(analysis.errors[0].line, 3)

    def test_pruned_branch_dropped_before_nested_resolution(self):
        analysis = analyze_blocks(REMAP, defines={"X": 0})
        self.assertTrue(analysis.ok)
        self.assertEqual(analysis.nested.invocations, ())
        self.assertEqual(analysis.block_plan.lines, ("[ENABLE]",))

    def test_structural_error_leaves_no_nested_plan(self):
        analysis = analyze_blocks(UNCLOSED_IF, defines={"DEBUG": 1})
        self.assertFalse(analysis.ok)
        self.assertIsNone(analysis.block_plan)
        self.assertIsNone(analysis.nested)
        self.assertIsInstance(analysis.errors[0], BlockStructureError)

    def test_report_serializable_with_errors(self):
        analysis = analyze_blocks(CYCLE)
        payload = json.dumps(analysis.report(), sort_keys=True)
        self.assertIn("nested assembly cycle", payload)
        self.assertIsInstance(analysis, BlockAnalysis)


if __name__ == "__main__":
    unittest.main()
