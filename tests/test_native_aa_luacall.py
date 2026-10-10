# -*- coding: utf-8 -*-
"""Focused fixture-driven tests for the pinned AA luaCall plan model.

Drives ``src/ct2trainer/native/aa_luacall.py`` against the synthetic,
hand-verified programs of ``tests/aa_luacall_fixture_data.py`` (no
TableReferences, no CE inputs).  Pinned scenarios:

- Expression parsing: strict single-line call grammar (string literals
  with a pinned escape set, decimal numbers, plain identifiers), no
  nesting, no trailing content, bounded arguments/strings, one-based
  line context carried into every refusal.
- AOB recognition: ``lua_aobscan`` (3 args, occurrence defaults to 1)
  and ``ct2trainerNthAOB`` (3 or 4 args), exact module basenames,
  ``**`` -> ``?`` pattern normalization with fully-wildcard refusal,
  occurrence bounds, single definition per symbol across the program.
- Program analysis: per-phase operations with 1-based line numbers,
  preamble calls attributed to enable, comment inertness, one-shot
  detection, CRLF normalization, and every structural refusal
  (unbalanced parentheses, trailing content, multi-line calls,
  unterminated strings, mode sections, phase rules).
- Binding validation: function-name coverage, the injectable
  ``NthAobPort`` requirement for AOB references, exact field names in
  every refusal, empty-plan passes.
- Operation planning: enable-before-disable deterministic order,
  stable report serialization.
"""
import json
import unittest

from ct2trainer.native import aa_luacall
from ct2trainer.native.aa_luacall import (
    LuaCallBinding,
    LuaCallBindingRefused,
    LuaCallParseError,
    NthAobPort,
    analyze_luacall_program,
    parse_luacall,
    plan_luacall_ops,
    validate_luacall_binding,
)

try:
    from aa_luacall_fixture_data import (
        AOB_ONE_SHOT,
        AOB_TWO_PHASE,
        BAD_AOB_ALL_WILDCARD,
        BAD_AOB_ARG_COUNT,
        BAD_AOB_MODULE,
        BAD_AOB_NONSTRING_MODULE,
        BAD_AOB_OCCURRENCE_HUGE,
        BAD_AOB_OCCURRENCE_ZERO,
        BAD_AOB_SYMBOL_ALL_HEX,
        BAD_BAD_EXPRESSION,
        BAD_DUPLICATE_PHASE,
        BAD_MULTI_LINE,
        BAD_NO_PHASES,
        BAD_PHASE_ORDER,
        BAD_SYMBOL_CONFLICT,
        BAD_TRAILING,
        BAD_UNBALANCED,
        BAD_UNTERMINATED_STRING,
        COMMENTED_CALLS,
        EXPR_INVALID,
        EXPR_NON_STR,
        EXPR_VALID,
        GENERIC_CALLS,
        NTH_AOB_CALL,
        PREAMBLE_CALL,
    )
except ModuleNotFoundError:  # invoked as tests.test_native_aa_luacall
    from tests.aa_luacall_fixture_data import (
        AOB_ONE_SHOT,
        AOB_TWO_PHASE,
        BAD_AOB_ALL_WILDCARD,
        BAD_AOB_ARG_COUNT,
        BAD_AOB_MODULE,
        BAD_AOB_NONSTRING_MODULE,
        BAD_AOB_OCCURRENCE_HUGE,
        BAD_AOB_OCCURRENCE_ZERO,
        BAD_AOB_SYMBOL_ALL_HEX,
        BAD_BAD_EXPRESSION,
        BAD_DUPLICATE_PHASE,
        BAD_MULTI_LINE,
        BAD_NO_PHASES,
        BAD_PHASE_ORDER,
        BAD_SYMBOL_CONFLICT,
        BAD_TRAILING,
        BAD_UNBALANCED,
        BAD_UNTERMINATED_STRING,
        COMMENTED_CALLS,
        EXPR_INVALID,
        EXPR_NON_STR,
        EXPR_VALID,
        GENERIC_CALLS,
        NTH_AOB_CALL,
        PREAMBLE_CALL,
    )


class _FakePort(NthAobPort):
    def scan(self, *, symbol, module, pattern, occurrence):
        return 0x140000000


class _FullBinding(LuaCallBinding):
    def function_names(self):
        return frozenset({'lua_aobscan', 'ct2trainerNthAOB',
                          'setValue', 'flag_on', 'init'})

    def aob_port(self):
        return _FakePort()


def _program(call_body):
    return ('[ENABLE]\nluaCall(' + call_body + ')\n[DISABLE]\n')


class ParseLuacallTests(unittest.TestCase):
    def test_valid_expressions_parse_to_deterministic_ast(self):
        for expression in EXPR_VALID:
            call = parse_luacall(expression)
            self.assertIsInstance(call.function, str)
            self.assertTrue(call.function)
            for argument in call.arguments:
                self.assertIn(argument.kind, ('string', 'number', 'symbol'))
        self.assertEqual(parse_luacall('x("a")'),
                         parse_luacall('x("a")'))

    def test_aobscan_call_argument_kinds(self):
        call = parse_luacall(EXPR_VALID[0])
        self.assertEqual(call.function, 'lua_aobscan')
        self.assertEqual([(a.kind, a.value) for a in call.arguments],
                         [('string', 'sym'), ('string', 'mod.exe'),
                          ('string', 'EB **')])

    def test_nth_aob_occurrence_is_number(self):
        call = parse_luacall(EXPR_VALID[1])
        self.assertEqual(call.function, 'ct2trainerNthAOB')
        self.assertEqual(call.arguments[3].kind, 'number')
        self.assertEqual(call.arguments[3].value, 3)

    def test_mixed_argument_kinds(self):
        call = parse_luacall("setValue('speed', 2)")
        self.assertEqual([(a.kind, a.value) for a in call.arguments],
                         [('string', 'speed'), ('number', 2)])

    def test_zero_arguments(self):
        call = parse_luacall('noop()')
        self.assertEqual(call.arguments, ())

    def test_whitespace_is_normalized(self):
        call = parse_luacall('a(  1 ,  2 )')
        self.assertEqual([(a.kind, a.value) for a in call.arguments],
                         [('number', 1), ('number', 2)])

    def test_escaped_quote_is_decoded(self):
        call = parse_luacall('x("say \\"hi\\"")')
        self.assertEqual(call.arguments[0].value, 'say "hi"')

    def test_escape_sequences_are_decoded(self):
        call = parse_luacall('x("tab\\there")')
        self.assertEqual(call.arguments[0].value, 'tab\there')
        call = parse_luacall('x("back\\\\slash")')
        self.assertEqual(call.arguments[0].value, 'back\\slash')

    def test_invalid_expressions_are_refused(self):
        for expression in EXPR_INVALID:
            with self.subTest(expression=expression):
                with self.assertRaises(LuaCallParseError):
                    parse_luacall(expression)

    def test_non_string_expressions_are_refused(self):
        for value in EXPR_NON_STR:
            with self.subTest(value=repr(value)):
                with self.assertRaises(LuaCallParseError):
                    parse_luacall(value)

    def test_too_many_arguments_are_refused(self):
        expression = 'x(' + ', '.join(str(i) for i in range(65)) + ')'
        with self.assertRaises(LuaCallParseError):
            parse_luacall(expression)

    def test_oversized_string_is_refused(self):
        expression = 'x("' + 'a' * 8193 + '")'
        with self.assertRaises(LuaCallParseError):
            parse_luacall(expression)

    def test_unicode_digit_argument_is_refused(self):
        with self.assertRaises(LuaCallParseError):
            parse_luacall('x(\u0663)')

    def test_error_carries_line_context(self):
        with self.assertRaises(LuaCallParseError) as ctx:
            parse_luacall('x(1,)', line=5)
        self.assertEqual(ctx.exception.line, 5)
        self.assertIn('line 5', str(ctx.exception))


class AobRecognitionTests(unittest.TestCase):
    def test_lua_aobscan_defaults_occurrence_to_one(self):
        plan = analyze_luacall_program(_program(
            'lua_aobscan("sym", "mod.exe", "EB ** ** 75")'))
        self.assertEqual(len(plan.operations), 1)
        operation = plan.operations[0]
        self.assertEqual(operation.aob, {
            'symbol': 'sym', 'module': 'mod.exe',
            'pattern': 'EB ?? ?? 75', 'occurrence': 1,
        })
        self.assertEqual(plan.aob_symbols, ('sym',))

    def test_nth_aob_occurrence_is_kept(self):
        plan = analyze_luacall_program(NTH_AOB_CALL)
        self.assertEqual(len(plan.operations), 2)
        for operation in plan.operations:
            self.assertEqual(operation.aob['occurrence'], 2)
            self.assertEqual(operation.aob['module'], 'mod.exe')

    def test_non_aob_function_has_no_aob_reference(self):
        plan = analyze_luacall_program(_program('setValue("speed", 2)'))
        self.assertEqual(plan.operations[0].aob, None)
        self.assertEqual(plan.aob_symbols, ())

    def test_pattern_normalization_collapse_whitespace(self):
        plan = analyze_luacall_program(_program(
            'lua_aobscan("s", "m.exe", "EB  **   **  75")'))
        self.assertEqual(plan.operations[0].aob['pattern'], 'EB ?? ?? 75')

    def test_wrong_argument_count_is_refused(self):
        with self.assertRaises(LuaCallParseError):
            analyze_luacall_program(BAD_AOB_ARG_COUNT)

    def test_non_string_module_is_refused(self):
        with self.assertRaises(LuaCallParseError) as ctx:
            analyze_luacall_program(BAD_AOB_NONSTRING_MODULE)
        self.assertIn('module', str(ctx.exception))

    def test_bad_module_basename_is_refused(self):
        with self.assertRaises(LuaCallParseError):
            analyze_luacall_program(BAD_AOB_MODULE)

    def test_all_wildcard_pattern_is_refused(self):
        with self.assertRaises(LuaCallParseError):
            analyze_luacall_program(BAD_AOB_ALL_WILDCARD)

    def test_occurrence_zero_is_refused(self):
        with self.assertRaises(LuaCallParseError):
            analyze_luacall_program(BAD_AOB_OCCURRENCE_ZERO)

    def test_occurrence_above_max_is_refused(self):
        with self.assertRaises(LuaCallParseError):
            analyze_luacall_program(BAD_AOB_OCCURRENCE_HUGE)

    def test_all_hex_symbol_is_refused(self):
        with self.assertRaises(LuaCallParseError):
            analyze_luacall_program(BAD_AOB_SYMBOL_ALL_HEX)

    def test_symbol_conflict_is_refused(self):
        with self.assertRaises(LuaCallParseError) as ctx:
            analyze_luacall_program(BAD_SYMBOL_CONFLICT)
        self.assertIn("symbol 'sym'", str(ctx.exception))
        self.assertEqual(ctx.exception.line, 3)


class ProgramAnalysisTests(unittest.TestCase):
    def test_full_aob_program_operations(self):
        plan = analyze_luacall_program(AOB_TWO_PHASE)
        self.assertEqual(len(plan.operations), 2)
        self.assertEqual(plan.operations[0].phase, 'enable')
        self.assertEqual(plan.operations[0].line, 2)
        self.assertEqual(plan.operations[1].phase, 'disable')
        self.assertEqual(plan.operations[1].line, 6)
        self.assertFalse(plan.one_shot)
        self.assertEqual(plan.aob_symbols, ('healthAnchor',))
        self.assertEqual(
            plan.operations[0].expression,
            'lua_aobscan("healthAnchor", "re2.exe", "EB ** ** 75")')

    def test_one_shot_program_is_detected(self):
        plan = analyze_luacall_program(AOB_ONE_SHOT)
        self.assertTrue(plan.one_shot)
        self.assertEqual(len(plan.operations), 1)
        self.assertEqual(plan.operations[0].phase, 'enable')

    def test_preamble_call_is_attributed_to_enable(self):
        plan = analyze_luacall_program(PREAMBLE_CALL)
        self.assertEqual(len(plan.operations), 1)
        self.assertEqual(plan.operations[0].phase, 'enable')
        self.assertEqual(plan.operations[0].line, 1)
        self.assertTrue(plan.one_shot)

    def test_comments_do_not_count_as_calls(self):
        plan = analyze_luacall_program(COMMENTED_CALLS)
        self.assertEqual(plan.operations, ())
        self.assertFalse(plan.one_shot)

    def test_no_calls_gives_empty_plan(self):
        plan = analyze_luacall_program('[ENABLE]\ndb 01\n[DISABLE]\ndb 00\n')
        self.assertEqual(plan.operations, ())
        self.assertFalse(plan.one_shot)
        self.assertEqual(plan.aob_symbols, ())

    def test_generic_calls_plan(self):
        plan = analyze_luacall_program(GENERIC_CALLS)
        self.assertEqual([op.function for op in plan.operations],
                         ['setValue', 'flag_on', 'setValue'])
        self.assertEqual([op.line for op in plan.operations], [2, 4, 6])
        self.assertFalse(plan.one_shot)
        self.assertEqual(plan.operations[1].expression,
                         'flag_on("manual")')

    def test_unbalanced_parentheses_are_refused(self):
        with self.assertRaises(LuaCallParseError) as ctx:
            analyze_luacall_program(BAD_UNBALANCED)
        self.assertEqual(ctx.exception.line, 2)

    def test_trailing_content_is_refused(self):
        with self.assertRaises(LuaCallParseError) as ctx:
            analyze_luacall_program(BAD_TRAILING)
        self.assertIn('own AA command line', str(ctx.exception))

    def test_multi_line_call_is_refused(self):
        with self.assertRaises(LuaCallParseError):
            analyze_luacall_program(BAD_MULTI_LINE)

    def test_unterminated_string_is_refused(self):
        with self.assertRaises(LuaCallParseError):
            analyze_luacall_program(BAD_UNTERMINATED_STRING)

    def test_bad_expression_is_refused(self):
        with self.assertRaises(LuaCallParseError) as ctx:
            analyze_luacall_program(BAD_BAD_EXPRESSION)
        self.assertEqual(ctx.exception.line, 2)

    def test_missing_phase_is_refused(self):
        with self.assertRaises(LuaCallParseError):
            analyze_luacall_program(BAD_NO_PHASES)

    def test_phases_out_of_order_are_refused(self):
        with self.assertRaises(LuaCallParseError):
            analyze_luacall_program(BAD_PHASE_ORDER)

    def test_duplicate_phase_is_refused(self):
        with self.assertRaises(LuaCallParseError) as ctx:
            analyze_luacall_program(BAD_DUPLICATE_PHASE)
        self.assertEqual(ctx.exception.line, 2)

    def test_line_numbers_are_one_based(self):
        plan = analyze_luacall_program(AOB_TWO_PHASE)
        self.assertEqual(min(op.line for op in plan.operations), 2)

    def test_crlf_source_is_normalized(self):
        lf = analyze_luacall_program(AOB_TWO_PHASE)
        crlf = analyze_luacall_program(AOB_TWO_PHASE.replace('\n', '\r\n'))
        self.assertEqual(lf.report(), crlf.report())

    def test_non_string_source_is_refused(self):
        with self.assertRaises(LuaCallParseError):
            analyze_luacall_program(None)


class BindingTests(unittest.TestCase):
    def test_valid_binding_passes(self):
        validate_luacall_binding(analyze_luacall_program(AOB_TWO_PHASE),
                                 _FullBinding())
        validate_luacall_binding(analyze_luacall_program(GENERIC_CALLS),
                                 _FullBinding())

    def test_no_binding_is_refused(self):
        with self.assertRaises(LuaCallBindingRefused) as ctx:
            validate_luacall_binding(analyze_luacall_program(AOB_TWO_PHASE),
                                     None)
        self.assertIn('function_names', str(ctx.exception))

    def test_non_binding_object_is_refused(self):
        with self.assertRaises(LuaCallBindingRefused):
            validate_luacall_binding(analyze_luacall_program(AOB_TWO_PHASE),
                                     object())

    def test_missing_function_is_refused_by_name(self):
        class _Partial(LuaCallBinding):
            def function_names(self):
                return frozenset({'setValue'})

            def aob_port(self):
                return None

        with self.assertRaises(LuaCallBindingRefused) as ctx:
            validate_luacall_binding(analyze_luacall_program(GENERIC_CALLS),
                                     _Partial())
        self.assertIn('flag_on', str(ctx.exception))
        self.assertEqual(ctx.exception.line, 4)

    def test_missing_aob_port_is_refused_by_field_and_symbol(self):
        class _NoPort(LuaCallBinding):
            def function_names(self):
                return frozenset({'lua_aobscan'})

            def aob_port(self):
                return None

        with self.assertRaises(LuaCallBindingRefused) as ctx:
            validate_luacall_binding(analyze_luacall_program(AOB_TWO_PHASE),
                                     _NoPort())
        self.assertIn('aob_port', str(ctx.exception))
        self.assertIn('healthAnchor', str(ctx.exception))
        self.assertEqual(ctx.exception.line, 2)

    def test_function_names_must_be_frozenset(self):
        class _BadNames(LuaCallBinding):
            def function_names(self):
                return set({'lua_aobscan'})

            def aob_port(self):
                return _FakePort()

        with self.assertRaises(LuaCallBindingRefused) as ctx:
            validate_luacall_binding(analyze_luacall_program(AOB_TWO_PHASE),
                                     _BadNames())
        self.assertIn('frozenset', str(ctx.exception))

    def test_aob_port_must_be_nth_aob_port(self):
        class _BadPort(LuaCallBinding):
            def function_names(self):
                return frozenset({'lua_aobscan'})

            def aob_port(self):
                return object()

        with self.assertRaises(LuaCallBindingRefused) as ctx:
            validate_luacall_binding(analyze_luacall_program(AOB_TWO_PHASE),
                                     _BadPort())
        self.assertIn('NthAobPort', str(ctx.exception))

    def test_empty_plan_passes_with_empty_binding(self):
        class _Empty(LuaCallBinding):
            def function_names(self):
                return frozenset()

            def aob_port(self):
                return None

        plan = analyze_luacall_program(
            '[ENABLE]\ndb 01\n[DISABLE]\ndb 00\n')
        validate_luacall_binding(plan, _Empty())

    def test_wrong_plan_type_is_refused(self):
        with self.assertRaises(LuaCallBindingRefused):
            validate_luacall_binding(object(), _FullBinding())


class PlanOpsTests(unittest.TestCase):
    def test_enable_comes_before_disable(self):
        operations = plan_luacall_ops(analyze_luacall_program(AOB_TWO_PHASE))
        self.assertEqual([op['phase'] for op in operations],
                         ['enable', 'disable'])
        self.assertEqual([op['line'] for op in operations], [2, 6])

    def test_operation_fields_are_pinned(self):
        operations = plan_luacall_ops(analyze_luacall_program(AOB_TWO_PHASE))
        self.assertEqual(operations[0]['op'], 'luacall')
        self.assertEqual(operations[0]['function'], 'lua_aobscan')
        self.assertEqual(operations[0]['port'], 'aob')
        self.assertEqual(operations[0]['arguments'],
                         [['string', 'healthAnchor'], ['string', 're2.exe'],
                          ['string', 'EB ** ** 75']])
        self.assertEqual(operations[0]['aob']['occurrence'], 1)

    def test_order_within_phase_follows_source_lines(self):
        operations = plan_luacall_ops(analyze_luacall_program(GENERIC_CALLS))
        self.assertEqual([op['line'] for op in operations], [2, 4, 6])
        self.assertEqual([op['port'] for op in operations],
                         ['lua', 'lua', 'lua'])

    def test_empty_plan_plans_nothing(self):
        plan = analyze_luacall_program('[ENABLE]\ndb 01\n[DISABLE]\ndb 00\n')
        self.assertEqual(plan_luacall_ops(plan), [])

    def test_report_is_serializable_and_deterministic(self):
        plan = analyze_luacall_program(AOB_TWO_PHASE)
        payload = json.dumps(plan.report(), sort_keys=True)
        self.assertIsInstance(payload, str)
        self.assertEqual(payload,
                         json.dumps(analyze_luacall_program(AOB_TWO_PHASE)
                                     .report(), sort_keys=True))


if __name__ == '__main__':
    unittest.main()
