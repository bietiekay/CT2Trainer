"""Contract tests for the custom-type write gate, abort path and RE2 registry."""

import json
import unittest

from ct2trainer.native.custom_types import (ABORT_SCHEMA,
                                              CustomTypeError,
                                              parse_custom_type_definition,
                                              parse_custom_types_section)
from ct2trainer.native.custom_type_runtime import (BLOCK_RUNTIME_DEFINITION,
                                                     BLOCK_WRITE_GATE,
                                                     CustomTypeHostAbort,
                                                     CustomTypeRegistry,
                                                     CustomTypeRuntimeError,
                                                     build_write_plan,
                                                     host_call,
                                                     lua_abort_payload,
                                                     lua_host_error,
                                                     plan_from_dict,
                                                     plan_to_dict,
                                                     verify_write_plan)


def ct(name, format_text, **options):
    return parse_custom_type_definition(name, format_text, **options)


# RE2-style fixture records, owned by this test file (not from TableReferences):
# hours/minutes/seconds are the classic re2.CT time records; the two Lua-only
# records stand in for registerCustomTypeAutoAssembler runtime definitions.
RE2_SECTION = (
    '<CustomTypes>'
    '<CustomType name="RE2_Hrs">1</CustomType>'
    '<CustomType name="RE2_Mins">2</CustomType>'
    '<CustomType name="RE2_Secs" Inverse="1">4</CustomType>'
    '<CustomType name="RE2_Score" Signed="1">8</CustomType>'
    '<CustomType name="RE2_Mixed">2 4</CustomType>'
    '</CustomTypes>')

RE2_RECORDS = (
    (13181, 'Hours', 'RE2_Hrs'),
    (13182, 'Minutes', 'RE2_Mins'),
    (13183, 'Seconds', 'RE2_Secs'),
    (13184, 'Score', 'RE2_Score'),
    (13185, 'Mixed', 'RE2_Mixed'),
)

RE2_LUA_ONLY_RECORDS = (
    (13190, 'AsyncTimer', None),
    (13191, 'Combo', None),
)

ADDRESS64 = 0x7FF000000000
ADDRESS32 = 0x0F000000


def profiles():
    return {p.name: p for p in parse_custom_types_section(RE2_SECTION)}


class WritePlanByteOrderTests(unittest.TestCase):
    def test_whole_value_plan_little_and_big_endian(self):
        for size in (1, 2, 4, 8):
            for endian in ('little', 'big'):
                with self.subTest(size=size, endian=endian):
                    profile = ct('T', str(size), endianness=endian)
                    value = 0x0102030405060708 % (1 << (8 * size))
                    plan = build_write_plan(profile, ADDRESS64, value=value)
                    self.assertEqual(plan.raw, value.to_bytes(size, endian))
                    self.assertEqual(plan.endianness, endian)
                    self.assertEqual(plan.size, size)
                    again = build_write_plan(profile, ADDRESS64, value=value)
                    self.assertEqual(again.raw, plan.raw)
                    self.assertEqual(again.plan_id, plan.plan_id)

    def test_signed_plan_uses_twos_complement_bytes(self):
        profile = ct('S', '4', signed=True)
        self.assertEqual(build_write_plan(profile, ADDRESS64, value=-1).raw,
                         b'\xff\xff\xff\xff')
        one = ct('O', '1', signed=True)
        self.assertEqual(build_write_plan(one, ADDRESS64, value=-128).raw,
                         b'\x80')
        self.assertEqual(build_write_plan(one, ADDRESS64, value=127).raw,
                         b'\x7f')

    def test_inverse_plan_reverses_full_span(self):
        for size in (2, 4, 8):
            with self.subTest(size=size):
                inverse = ct('I', str(size), inverse=True)
                plain = ct('P', str(size))
                value = 0x0102030405060708 % (1 << (8 * size))
                plan = build_write_plan(inverse, ADDRESS64, value=value)
                self.assertEqual(plan.raw,
                                 value.to_bytes(size, 'little')[::-1])
                self.assertEqual(plan.raw,
                                 build_write_plan(plain, ADDRESS64,
                                                  value=value).raw[::-1])
                verify_write_plan(plan)

    def test_composite_fields_plan_bytes_and_element_binding(self):
        profile = ct('M', '2 4')
        plan = build_write_plan(profile, ADDRESS64, field_values=(1, 2))
        self.assertEqual(plan.raw, b'\x01\x00\x02\x00\x00\x00')
        self.assertEqual(plan.field_values, (1, 2))
        self.assertIsNone(plan.value)
        self.assertEqual([(e.offset, e.size, e.value) for e in plan.elements],
                         [(0, 2, 1), (2, 4, 2)])

    def test_array_fields_plan(self):
        profile = ct('A', '2[3]')
        plan = build_write_plan(profile, ADDRESS64, field_values=(1, 2, 3))
        self.assertEqual(plan.raw, b'\x01\x00\x02\x00\x03\x00')
        self.assertEqual([(e.offset, e.size, e.value) for e in plan.elements],
                         [(0, 2, 1), (2, 2, 2), (4, 2, 3)])

    def test_plan_bytes_match_codec_encode_exactly(self):
        cases = (
            (ct('A', '1'), 23, None),
            (ct('B', '4', endianness='big'), 0x01020304, None),
            (ct('C', '4', inverse=True), 0x01020304, None),
            (ct('D', '8', signed=True), -2, None),
            (ct('E', '2 4'), None, (1, 2)),
        )
        for profile, value, field_values in cases:
            with self.subTest(profile=profile.name):
                plan = build_write_plan(profile, ADDRESS64, value=value,
                                        field_values=field_values)
                if value is not None:
                    from ct2trainer.native.custom_types import (
                        encode_custom_value)
                    expected = encode_custom_value(profile, value)
                else:
                    from ct2trainer.native.custom_types import (
                        encode_custom_fields)
                    expected = encode_custom_fields(profile, field_values)
                self.assertEqual(plan.raw, expected)


class WritePlanGateRefusalsTests(unittest.TestCase):
    def test_value_out_of_range_is_named_codec_rejection(self):
        profile = ct('U', '1')
        with self.assertRaises(CustomTypeError) as caught:
            build_write_plan(profile, ADDRESS64, value=256)
        self.assertEqual(caught.exception.code, 'custom-value-out-of-range')
        with self.assertRaises(CustomTypeError):
            build_write_plan(profile, ADDRESS64, value=-1)

    def test_signed_out_of_range_rejected(self):
        profile = ct('S', '2', signed=True)
        # -32768 is the valid minimum; only the neighbours are outside.
        for value in (-(1 << 15) - 1, 1 << 15):
            with self.subTest(value=value):
                with self.assertRaises(CustomTypeError) as caught:
                    build_write_plan(profile, ADDRESS64, value=value)
                self.assertEqual(caught.exception.code,
                                 'custom-value-out-of-range')
        self.assertEqual(build_write_plan(profile, ADDRESS64,
                                          value=-(1 << 15)).raw, b'\x00\x80')

    def test_non_integer_value_refused(self):
        profile = ct('V', '4')
        for value in (True, 1.5, '4'):
            with self.subTest(value=value):
                with self.assertRaisesRegex(CustomTypeRuntimeError,
                                            'must be an integer'):
                    build_write_plan(profile, ADDRESS64, value=value)

    def test_field_count_mismatch_rejected(self):
        profile = ct('M', '2 4')
        for values in ((1,), (1, 2, 3), []):
            with self.subTest(values=values):
                with self.assertRaises(CustomTypeError) as caught:
                    build_write_plan(profile, ADDRESS64, field_values=values)
                self.assertEqual(caught.exception.code,
                                 'custom-field-count-mismatch')

    def test_field_out_of_range_reports_span_offset(self):
        profile = ct('M', '2 4')
        with self.assertRaises(CustomTypeError) as caught:
            build_write_plan(profile, ADDRESS64, field_values=(1, 1 << 32))
        self.assertEqual(caught.exception.code, 'custom-value-out-of-range')
        self.assertEqual(caught.exception.offset, 2)

    def test_field_value_non_integer_refused(self):
        profile = ct('M', '2 4')
        with self.assertRaisesRegex(CustomTypeRuntimeError,
                                    'must be integers'):
            build_write_plan(profile, ADDRESS64, field_values=(1, True))
        with self.assertRaisesRegex(CustomTypeRuntimeError,
                                    'tuple or list'):
            build_write_plan(profile, ADDRESS64, field_values='12')

    def test_input_selection_rules(self):
        profile = ct('M', '2 4')
        with self.assertRaisesRegex(CustomTypeRuntimeError, 'exactly one'):
            build_write_plan(profile, ADDRESS64, value=1, field_values=(1, 2))
        with self.assertRaisesRegex(CustomTypeRuntimeError, 'exactly one'):
            build_write_plan(profile, ADDRESS64)

    def test_address_and_width_validation(self):
        profile = ct('W', '4')
        for address in (0, -5, True, '0x1000'):
            with self.subTest(address=address):
                with self.assertRaisesRegex(CustomTypeRuntimeError,
                                            'address must be'):
                    build_write_plan(profile, address, value=1)
        with self.assertRaisesRegex(CustomTypeRuntimeError, '4 or 8'):
            build_write_plan(profile, ADDRESS32, value=1, pointer_size=6)
        # Width-4 boundary: a normal width-4 address is fine, the last full
        # 4-byte span is accepted, one beyond the address space is refused.
        plan = build_write_plan(profile, ADDRESS32, value=1, pointer_size=4)
        self.assertEqual(plan.pointer_size, 4)
        last = build_write_plan(profile, 0xFFFFFFFC, value=1, pointer_size=4)
        self.assertEqual(last.raw, b'\x01\x00\x00\x00')
        with self.assertRaisesRegex(CustomTypeRuntimeError, 'address space'):
            build_write_plan(profile, 0xFFFFFFFD, value=1, pointer_size=4)

    def test_profile_and_tampered_profile_refused(self):
        for bad in (None, '2 4', {}, 42):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(CustomTypeRuntimeError,
                                            'CustomTypeProfile'):
                    build_write_plan(bad, ADDRESS64, value=1)
        original = ct('T', '2 4')
        tampered = type(original)(**{**original.__dict__, 'size': 5})
        with self.assertRaises(CustomTypeError) as caught:
            build_write_plan(tampered, ADDRESS64, value=1)
        self.assertEqual(caught.exception.code, 'custom-profile-invalid')


class InverseReadbackTests(unittest.TestCase):
    def test_inverse_readback_reproduces_value_and_bytes(self):
        profile = ct('I', '4', inverse=True)
        plan = build_write_plan(profile, ADDRESS64, value=0x0A0B0C0D)
        from ct2trainer.native.custom_types import (decode_custom_value,
                                                      encode_custom_value)
        self.assertEqual(decode_custom_value(profile, plan.raw), 0x0A0B0C0D)
        self.assertEqual(encode_custom_value(profile, 0x0A0B0C0D), plan.raw)
        twin = ct('P', '4')
        self.assertEqual(encode_custom_value(twin, 0x0A0B0C0D), plan.raw[::-1])

    def test_tampered_plan_bytes_fail_verification(self):
        profile = ct('M', '2 4')
        plan = build_write_plan(profile, ADDRESS64, field_values=(1, 2))
        tampered = type(plan)(**{**plan.__dict__,
                                 'raw': plan.raw[:-1] + b'\x01'})
        with self.assertRaisesRegex(CustomTypeRuntimeError, 're-encode'):
            verify_write_plan(tampered)

    def test_forged_plan_id_fails_verification(self):
        profile = ct('I', '2', inverse=True)
        plan = build_write_plan(profile, ADDRESS64, value=7)
        forged = type(plan)(**{**plan.__dict__, 'plan_id': '0' * 64})
        with self.assertRaisesRegex(CustomTypeRuntimeError, 'plan id'):
            verify_write_plan(forged)

    def test_tampered_metadata_fails_verification(self):
        profile = ct('M', '2 4')
        plan = build_write_plan(profile, ADDRESS64, field_values=(1, 2))
        for key, value in {'endianness': 'middle', 'size': 5,
                           'inverse': True, 'signed': True}.items():
            with self.subTest(key=key):
                tampered = type(plan)(**{**plan.__dict__, key: value})
                with self.assertRaises(CustomTypeRuntimeError):
                    verify_write_plan(tampered)
        outside = type(plan)(**{**plan.__dict__, 'address': 0xFFFFFFFFFFFF})
        with self.assertRaises(CustomTypeRuntimeError):
            verify_write_plan(outside)

    def test_verify_rejects_non_plan_objects(self):
        for bad in (None, {}, 'plan', 42):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(CustomTypeRuntimeError,
                                            'must be a CustomTypeWritePlan'):
                    verify_write_plan(bad)


class PlanJsonTests(unittest.TestCase):
    def test_plan_json_roundtrip(self):
        profile = ct('M', '2 4', endianness='big', signed=True)
        plan = build_write_plan(profile, ADDRESS64, field_values=(-1, 0x40000000))
        payload = plan_to_dict(plan)
        text = json.dumps(payload, sort_keys=True)
        rebuilt = plan_from_dict(json.loads(text))
        self.assertEqual(rebuilt, plan)
        verify_write_plan(rebuilt)

    def test_plan_dict_is_json_stable(self):
        profile = ct('I', '4', inverse=True)
        plan = build_write_plan(profile, ADDRESS32, value=0xA5)
        first = json.dumps(plan_to_dict(plan), sort_keys=True)
        second = json.dumps(plan_to_dict(build_write_plan(profile, ADDRESS32, value=0xA5)),
                            sort_keys=True)
        self.assertEqual(first, second)
        self.assertNotIn('0xA5', first)

    def test_plan_from_dict_rejects_forged_payloads(self):
        profile = ct('M', '2 4')
        base = plan_to_dict(build_write_plan(profile, ADDRESS64, field_values=(1, 2)))
        cases = {
            'missing': {k: v for k, v in base.items() if k != 'raw'},
            'extra': {**base, 'extra': 1},
            'bad-hex': {**base, 'raw': 'zz'},
            'value-string': {**base, 'value': '2'},
            'size-string': {**base, 'size': '6'},
            'inverse-not-bool': {**base, 'inverse': '1'},
            'pointer-size': {**base, 'pointer_size': 6},
            'elements-not-list': {**base, 'elements': 'nope'},
            'element-shape': {**base, 'elements': [[0, 2]]},
            'bad-schema': {**base, 'schema': 'other/v1'},
        }
        for label, payload in cases.items():
            with self.subTest(label=label):
                with self.assertRaises(CustomTypeRuntimeError) as caught:
                    plan_from_dict(payload)
                self.assertEqual(caught.exception.code, 'custom-plan-invalid')


class LuaAbortPathTests(unittest.TestCase):
    def _codec_error(self):
        return CustomTypeError('span too short', code='custom-span-mismatch',
                               stage='decode', offset=2)

    def test_abort_payload_matches_wiring_contract(self):
        exc = self._codec_error()
        payload = lua_abort_payload(exc)
        self.assertEqual(payload, exc.to_abort().to_dict())
        self.assertEqual(set(payload),
                         {'schema', 'code', 'reason', 'offset', 'stage'})
        self.assertEqual(payload['schema'], ABORT_SCHEMA)
        self.assertEqual(payload['code'], 'custom-span-mismatch')
        self.assertEqual(payload['stage'], 'decode')
        self.assertEqual(payload['offset'], 2)
        json.dumps(payload, sort_keys=True)

    def test_abort_payload_refuses_foreign_errors(self):
        for exc in (ValueError('boom'), RuntimeError('boom'),
                    CustomTypeRuntimeError('boom', code='custom-plan-invalid')):
            with self.subTest(exc=type(exc).__name__):
                with self.assertRaisesRegex(CustomTypeRuntimeError,
                                            'custom-type abort contract'):
                    lua_abort_payload(exc)

    def test_host_error_message_named_and_traceback_free(self):
        exc = self._codec_error()
        error = lua_host_error(exc)
        self.assertIsInstance(error, CustomTypeHostAbort)
        self.assertIsInstance(error, RuntimeError)
        self.assertEqual(str(error), 'custom-span-mismatch: span too short')
        self.assertEqual(error.abort_payload, lua_abort_payload(exc))
        self.assertNotIn('Traceback', str(error))

    def test_host_call_ok_and_abort_paths(self):
        from ct2trainer.native.custom_types import encode_custom_value
        ok_profile = ct('K', '1')
        status, raw = host_call(encode_custom_value, ok_profile, 23)
        self.assertEqual((status, raw), ('ok', b'\x17'))
        status, payload = host_call(encode_custom_value, ok_profile, 300)
        self.assertEqual(status, 'abort')
        self.assertEqual(payload['code'], 'custom-value-out-of-range')
        self.assertEqual(payload['stage'], 'encode')
        self.assertEqual(set(payload),
                         {'schema', 'code', 'reason', 'offset', 'stage'})

        def foreign():
            raise ValueError('not a codec error')
        with self.assertRaises(ValueError):
            host_call(foreign)

    def test_runtime_error_carries_its_own_abort_payload(self):
        error = CustomTypeRuntimeError('Write plan address is invalid',
                                       code='custom-plan-address-invalid',
                                       stage='gate')
        payload = error.to_abort_dict()
        self.assertEqual(set(payload),
                         {'schema', 'code', 'reason', 'offset', 'stage'})
        self.assertEqual(payload['schema'], ABORT_SCHEMA)
        self.assertIsNone(payload['offset'])
        json.dumps(payload)


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.profiles = profiles()

    def test_re2_static_record_registration_shows_write_gate_reason(self):
        registry = CustomTypeRegistry()
        for record_id, name, type_name in RE2_RECORDS:
            with self.subTest(record=record_id):
                registration = registry.register(record_id, name, 'table-lua',
                                                 profile=self.profiles[type_name])
                self.assertEqual(registration.block_reason, BLOCK_WRITE_GATE)
                self.assertIn('write gate', registration.block_reason_text)
                self.assertIn(str(record_id), registration.block_reason_text)
                self.assertEqual(registration.profile_name, type_name)
                self.assertEqual(registration.profile_size,
                                 self.profiles[type_name].size)
        report = registry.report()
        self.assertEqual(report['write_gate'], 'closed')
        self.assertEqual([r['record_id'] for r in report['registrations']],
                         [r for r, _, _ in RE2_RECORDS])

    def test_re2_lua_only_record_shows_runtime_definition_reason(self):
        registry = CustomTypeRegistry()
        for record_id, name, _ in RE2_LUA_ONLY_RECORDS:
            registration = registry.register(record_id, name, 'table-lua')
            self.assertEqual(registration.block_reason,
                             BLOCK_RUNTIME_DEFINITION)
            self.assertIn('no static definition', registration.block_reason_text)
            self.assertIsNone(registration.profile_name)
            self.assertIsNone(registration.profile_size)

    def test_duplicate_registration_refused_even_across_scopes(self):
        registry = CustomTypeRegistry()
        registry.register(13181, 'Hours', 'table-lua',
                          profile=self.profiles['RE2_Hrs'])
        with self.assertRaises(CustomTypeRuntimeError) as caught:
            registry.register(13181, 'Hours', 'controller',
                              profile=self.profiles['RE2_Hrs'])
        self.assertEqual(caught.exception.code, 'custom-record-duplicate')
        self.assertIn("'table-lua'", str(caught.exception))
        self.assertEqual(len(registry.registrations()), 1)
        registry.register(13182, 'Minutes', 'controller',
                          profile=self.profiles['RE2_Mins'])
        self.assertEqual(len(registry.registrations()), 2)

    def test_teardown_scoped_and_idempotent(self):
        registry = CustomTypeRegistry()
        registry.register(13181, 'Hours', 'table-lua',
                          profile=self.profiles['RE2_Hrs'])
        registry.register(13182, 'Minutes', 'table-lua',
                          profile=self.profiles['RE2_Mins'])
        registry.register(13190, 'AsyncTimer', 'controller')
        self.assertEqual(registry.teardown('table-lua'), 2)
        self.assertEqual(registry.teardown('table-lua'), 0)
        self.assertEqual([r.record_id for r in registry.registrations()],
                         [13190])
        self.assertEqual(registry.teardown('controller'), 1)
        self.assertEqual(registry.teardown(None), 0)
        self.assertEqual(registry.registrations(), ())
        # A torn-down id may be registered again under a fresh scope.
        registry.register(13181, 'Hours', 'fresh-scope',
                          profile=self.profiles['RE2_Hrs'])
        self.assertEqual(len(registry.registrations()), 1)

    def test_registration_input_validation(self):
        registry = CustomTypeRegistry()
        profile = self.profiles['RE2_Hrs']
        for bad_id in (0, -1, True, '13181'):
            with self.subTest(id=bad_id):
                with self.assertRaisesRegex(CustomTypeRuntimeError,
                                            'Record id'):
                    registry.register(bad_id, 'Hours', 'table-lua',
                                      profile=profile)
        for bad_name in ('', ' Hours', 'Hours\u00fc', 'H' * 65, None, 7):
            with self.subTest(name=bad_name):
                with self.assertRaisesRegex(CustomTypeRuntimeError,
                                            'Record name'):
                    registry.register(13181, bad_name, 'table-lua',
                                      profile=profile)
        for bad_scope in ('', ' ' * 10, 'a' * 129, ' a'):
            with self.subTest(scope=bad_scope):
                with self.assertRaisesRegex(CustomTypeRuntimeError, 'Scope'):
                    registry.register(13181, 'Hours', bad_scope,
                                      profile=profile)

    def test_tampered_profile_registration_refused(self):
        registry = CustomTypeRegistry()
        profile = self.profiles['RE2_Mins']
        tampered = type(profile)(**{**profile.__dict__, 'size': 99})
        with self.assertRaises(CustomTypeError) as caught:
            registry.register(13182, 'Minutes', 'table-lua', profile=tampered)
        self.assertEqual(caught.exception.code, 'custom-profile-invalid')
        self.assertEqual(registry.registrations(), ())
        with self.assertRaisesRegex(CustomTypeRuntimeError,
                                    'CustomTypeProfile'):
            registry.register(13182, 'Minutes', 'table-lua', profile='2')

    def test_report_json_stable_and_gate_closed(self):
        registry = CustomTypeRegistry()
        registry.register(13181, 'Hours', 'table-lua',
                          profile=self.profiles['RE2_Hrs'])
        registry.register(13190, 'AsyncTimer', 'controller')
        first = json.dumps(registry.report(), sort_keys=True)
        second = json.dumps(registry.report(), sort_keys=True)
        self.assertEqual(first, second)
        report = json.loads(first)
        self.assertEqual(report['schema'], 'ct2trainer-custom-type-runtime/v1')
        self.assertEqual(report['write_gate'], 'closed')
        self.assertEqual(len(report['registrations']), 2)
        for item in report['registrations']:
            self.assertIn(item['block_reason'],
                          (BLOCK_WRITE_GATE, BLOCK_RUNTIME_DEFINITION))
