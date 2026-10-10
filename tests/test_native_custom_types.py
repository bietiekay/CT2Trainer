"""Static custom type codecs reject invalid forms without partial state."""

import json
import unittest
import xml.etree.ElementTree as ET

from ct2trainer.native.custom_types import (ABORT_SCHEMA, MAX_ARRAY_COUNT,
                                              MAX_CUSTOM_SIZE, MAX_FIELDS,
                                              MAX_NAME_LENGTH,
                                              CustomTypeAbort, CustomTypeError,
                                              custom_types_from_ct_root,
                                              decode_custom_fields,
                                              decode_custom_value,
                                              encode_custom_fields,
                                              encode_custom_value,
                                              format_custom_value,
                                              parse_custom_type_definition,
                                              parse_custom_types_section,
                                              validate_custom_type)


def ct(format_text, **options):
    return parse_custom_type_definition('T', format_text, **options)


RE2_SECTION = (
    '<CustomTypes>'
    '<CustomType name="RE2_Hrs">1</CustomType>'
    '<CustomType name="RE2_Mins">2</CustomType>'
    '<CustomType name="RE2_Secs">1</CustomType>'
    '<CustomType name="Composite" Endian="big">2 4</CustomType>'
    '<CustomType name="Triplet" Inverse="1" Signed="1">2[3]</CustomType>'
    '</CustomTypes>')

RE2_CT = (
    '<CheatTable CheatEngineTableVersion="45">'
    '<CustomTypes><CustomType name="RE2_Hrs">1</CustomType></CustomTypes>'
    '<CheatEntries>'
    '<CheatEntry><ID>13181</ID><Description>"Hours"</Description>'
    '<VariableType>Custom</VariableType><CustomType>RE2_Hrs</CustomType>'
    '<Address>game.exe+1000</Address></CheatEntry>'
    '</CheatEntries>'
    '</CheatTable>')


class NativeCustomTypeTests(unittest.TestCase):
    def test_element_sizes_little_endian_roundtrip(self):
        for size in (1, 2, 4, 8):
            with self.subTest(size=size):
                profile = ct(str(size))
                self.assertEqual(profile.size, size)
                value = 0x0102030405060708 % (1 << (8 * size))
                raw = encode_custom_value(profile, value)
                self.assertEqual(raw, value.to_bytes(size, 'little'))
                self.assertEqual(decode_custom_value(profile, raw), value)
                self.assertEqual(format_custom_value(profile, raw), str(value))

    def test_element_sizes_big_endian_roundtrip(self):
        for size in (1, 2, 4, 8):
            with self.subTest(size=size):
                profile = ct(str(size), endianness='big')
                value = 0x0102030405060708 % (1 << (8 * size))
                raw = encode_custom_value(profile, value)
                self.assertEqual(raw, value.to_bytes(size, 'big'))
                self.assertEqual(decode_custom_value(profile, raw), value)

    def test_signed_two_complement_per_size(self):
        for size in (1, 2, 4, 8):
            with self.subTest(size=size):
                profile = ct(str(size), signed=True)
                lowest = -(1 << (8 * size - 1))
                highest = (1 << (8 * size - 1)) - 1
                for value in (lowest, highest, -1, 1, 0):
                    raw = encode_custom_value(profile, value)
                    self.assertEqual(raw, value.to_bytes(size, 'little', signed=True))
                    self.assertEqual(decode_custom_value(profile, raw), value)

    def test_unsigned_rejects_negative_values(self):
        for size in (1, 2, 4, 8):
            with self.subTest(size=size):
                with self.assertRaisesRegex(CustomTypeError, 'outside'):
                    encode_custom_value(ct(str(size)), -1)

    def test_signed_rejects_out_of_range_boundaries(self):
        for size in (1, 2, 4, 8):
            with self.subTest(size=size):
                unsigned = ct(str(size))
                for value in (-(1 << (8 * size)), 1 << (8 * size)):
                    with self.assertRaisesRegex(CustomTypeError, 'outside'):
                        encode_custom_value(unsigned, value)
                signed = ct(str(size), signed=True)
                for value in (-(1 << (8 * size - 1)) - 1, 1 << (8 * size - 1)):
                    with self.assertRaisesRegex(CustomTypeError, 'outside'):
                        encode_custom_value(signed, value)

    def test_inverse_bytes_reverse_the_full_span(self):
        profile = ct('4', inverse=True)
        # Little-endian encoding of 0x01020304 is b'\x04\x03\x02\x01';
        # inverse reverses the complete span.
        self.assertEqual(encode_custom_value(profile, 0x01020304), b'\x01\x02\x03\x04')
        self.assertEqual(decode_custom_value(profile, b'\x01\x02\x03\x04'), 0x01020304)
        for size in (1, 2, 4, 8):
            with self.subTest(size=size):
                inverse = ct(str(size), inverse=True)
                plain = ct(str(size))
                value = 0xA5 % (1 << (8 * size))
                self.assertEqual(encode_custom_value(inverse, value),
                                 encode_custom_value(plain, value)[::-1])
                self.assertEqual(decode_custom_value(inverse,
                                                     encode_custom_value(inverse, value)),
                                 value)

    def test_inverse_combined_with_big_endian(self):
        profile = ct('4', endianness='big', inverse=True)
        self.assertEqual(encode_custom_value(profile, 0x01020304), b'\x04\x03\x02\x01')
        self.assertEqual(decode_custom_value(profile, b'\x04\x03\x02\x01'), 0x01020304)
        self.assertEqual(encode_custom_value(ct('4', endianness='big'), 0x01020304),
                         b'\x01\x02\x03\x04')

    def test_composite_layout_offsets_and_total_size(self):
        profile = ct('2 4')
        self.assertEqual(profile.size, 6)
        self.assertEqual(profile.element_count, 2)
        self.assertEqual([(field.size, field.count, field.offset)
                          for field in profile.fields], [(2, 1, 0), (4, 1, 2)])

    def test_array_repeats_elements_sequentially(self):
        profile = ct('4[3]')
        self.assertEqual(profile.size, 12)
        self.assertEqual(profile.element_count, 3)
        self.assertEqual(profile.fields,
                         (type(profile.fields[0])(4, 3, 0),))

    def test_mixed_composite_and_array_layout(self):
        profile = ct('2[2] 8')
        self.assertEqual(profile.size, 12)
        self.assertEqual(profile.element_count, 3)
        self.assertEqual([(field.size, field.count, field.offset)
                          for field in profile.fields], [(2, 2, 0), (8, 1, 4)])

    def test_array_limits_reject_unbounded_layouts(self):
        with self.assertRaisesRegex(CustomTypeError, 'exceeds'):
            ct(f'1[{MAX_ARRAY_COUNT + 1}]')
        self.assertEqual(ct(f'1[{MAX_ARRAY_COUNT}]').size, MAX_ARRAY_COUNT)
        self.assertEqual(ct('8[512]').size, MAX_CUSTOM_SIZE)
        with self.assertRaisesRegex(CustomTypeError, 'limit is'):
            ct('8[600]')

    def test_field_count_limit_is_enforced(self):
        with self.assertRaisesRegex(CustomTypeError, 'More than'):
            ct(' '.join(['1'] * (MAX_FIELDS + 1)))
        self.assertEqual(ct(' '.join(['1'] * MAX_FIELDS)).size, MAX_FIELDS)

    def test_empty_format_rejected(self):
        for text in ('', '   ', '\t\n'):
            with self.subTest(text=text):
                with self.assertRaisesRegex(CustomTypeError, 'Empty format'):
                    ct(text)

    def test_unknown_size_tokens_rejected(self):
        for token in ('3', '16', '0', '64', '2 3', '4 16'):
            with self.subTest(token=token):
                with self.assertRaisesRegex(CustomTypeError, 'not one of 1/2/4/8'):
                    ct(token)

    def test_invalid_array_syntax_rejected(self):
        cases = {'4[]': 'Malformed array', '4[0]': 'positive number',
                 '4[04]': 'leading zeros', '4[': 'Malformed array',
                 '4]': 'Malformed array', '[4': 'Malformed array',
                 '4[1]]': 'Malformed array', '4 4[': 'Malformed array'}
        for token, message in cases.items():
            with self.subTest(token=token):
                with self.assertRaisesRegex(CustomTypeError, message):
                    ct(token)

    def test_unknown_characters_rejected(self):
        cases = {'4,2': 1, '4;2': 1, '4x2': 1, '4\u00a02': 1, '4*2': 1,
                 'a2': 0, '4-2': 1}
        for text, offset in cases.items():
            with self.subTest(text=text):
                try:
                    ct(text)
                    self.fail('expected CustomTypeError for ' + repr(text))
                except CustomTypeError as error:
                    self.assertEqual(error.code, 'custom-format-unknown-character')
                    self.assertEqual(error.offset, offset)
                    self.assertEqual(error.stage, 'parse')

    def test_name_validation(self):
        for name in ('', 'a' * (MAX_NAME_LENGTH + 1), 'bad\0name', ' padded',
                     None, 42):
            with self.subTest(name=name):
                with self.assertRaisesRegex(CustomTypeError, 'name must be'):
                    parse_custom_type_definition(name, '4')
        self.assertEqual(parse_custom_type_definition('a' * MAX_NAME_LENGTH, '4').name,
                         'a' * MAX_NAME_LENGTH)

    def test_endianness_validation(self):
        self.assertEqual(ct('4', endianness='BIG').endianness, 'big')
        self.assertEqual(ct('4', endianness=' little ').endianness, 'little')
        for value in ('middle', '', None, True, 'LittleEndian'):
            with self.subTest(value=value):
                with self.assertRaisesRegex(CustomTypeError, 'Endianness'):
                    ct('4', endianness=value)

    def test_boolean_flag_validation(self):
        for value in (True, False, 0, 1, '0', '1', ' 1 '):
            with self.subTest(value=value):
                self.assertEqual(ct('4', inverse=value).inverse,
                                 bool(value) if not isinstance(value, str) else value.strip() == '1')
        for value in ('2', 'true', None, 2, -1):
            with self.subTest(value=value):
                with self.assertRaisesRegex(CustomTypeError, 'must be 0 or 1'):
                    ct('4', inverse=value)
                with self.assertRaisesRegex(CustomTypeError, 'must be 0 or 1'):
                    ct('4', signed=value)

    def test_span_mismatch_rejected(self):
        profile = ct('4')
        for raw in (b'\x00', b'\x00' * 5, b''):
            with self.subTest(raw=raw):
                for operation in (decode_custom_value, decode_custom_fields,
                                  format_custom_value):
                    with self.assertRaisesRegex(CustomTypeError,
                                                f'Expected exactly {4} bytes'):
                        operation(profile, raw)

    def test_non_bytes_and_non_integer_inputs_rejected(self):
        profile = ct('2')
        for raw in ('ab', None, [1, 2], 42, memoryview(b'\x00\x00')):
            with self.subTest(raw=raw):
                with self.assertRaisesRegex(CustomTypeError, 'must be bytes'):
                    decode_custom_value(profile, raw)
        for value in (True, 1.5, '2', None):
            with self.subTest(value=value):
                with self.assertRaisesRegex(CustomTypeError, 'must be an integer'):
                    encode_custom_value(profile, value)

    def test_whole_value_and_element_views_agree_for_single_element_types(self):
        for size in (1, 2, 4, 8):
            with self.subTest(size=size):
                profile = ct(str(size), endianness='big')
                value = 0x0A0B0C0D % (1 << (8 * size))
                raw = encode_custom_value(profile, value)
                self.assertEqual(decode_custom_fields(profile, raw), (value,))
                self.assertEqual(encode_custom_fields(profile, (value,)), raw)

    def test_encode_fields_count_and_range_errors(self):
        profile = ct('2 4')
        self.assertEqual(encode_custom_fields(profile, (1, 2)),
                         b'\x01\x00\x02\x00\x00\x00')
        self.assertEqual(encode_custom_fields(profile, (1, 2), ),
                         encode_custom_fields(profile, [1, 2]))
        try:
            encode_custom_fields(profile, (1,))
            self.fail('expected CustomTypeError')
        except CustomTypeError as error:
            self.assertEqual(error.code, 'custom-field-count-mismatch')
            self.assertEqual(error.offset, 1)
            self.assertEqual(error.stage, 'encode')
        try:
            encode_custom_fields(profile, (1, 1 << 32))
            self.fail('expected CustomTypeError')
        except CustomTypeError as error:
            self.assertEqual(error.code, 'custom-value-out-of-range')
            self.assertEqual(error.offset, 2)
        with self.assertRaisesRegex(CustomTypeError, 'tuple or list'):
            encode_custom_fields(profile, '12')
        signed = ct('2', signed=True)
        self.assertEqual(encode_custom_value(signed, -1), b'\xff\xff')
        self.assertEqual(decode_custom_value(signed, b'\xff\xff'), -1)

    def test_profile_validation_detects_tampering(self):
        # Only derived fields are detectable by reconstruction; name,
        # endianness, inverse and signed are source inputs, not derived.
        original = ct('2 4')
        for key, value in {'size': 5, 'element_count': 3,
                           'fields': (original.fields[0],),
                           'endianness': 'middle', 'format_text': '2 8'}.items():
            with self.subTest(key=key):
                tampered = type(original)(**{**original.__dict__, key: value})
                with self.assertRaisesRegex(CustomTypeError, 'profile metadata'):
                    validate_custom_type(tampered)
        for profile in ({}, None, '2 4', 42):
            with self.subTest(profile=profile):
                with self.assertRaisesRegex(CustomTypeError,
                                            'must be a CustomTypeProfile'):
                    validate_custom_type(profile)

    def test_error_objects_carry_named_code_reason_and_offset(self):
        cases = (
            (lambda: ct('3'), 'parse', None),
            (lambda: decode_custom_value(ct('4'), b'\x01\x02'), 'decode', 2),
            (lambda: encode_custom_value(ct('1'), 256), 'encode', None),
            (lambda: parse_custom_type_definition('', '4'), 'parse', None),
            (lambda: encode_custom_fields(ct('2 4'), (70000, 1)), 'encode', 0),
        )
        for operation, stage, offset in cases:
            with self.assertRaises(CustomTypeError) as caught:
                operation()
            error = caught.exception
            self.assertIsInstance(error, ValueError)
            self.assertTrue(error.code.startswith('custom-'))
            self.assertTrue(error.reason)
            self.assertEqual(error.stage, stage)
            self.assertEqual(error.offset, offset)

    def test_abort_payload_is_stable_for_lua_host(self):
        def host_call(profile, value):
            """Pure model call: either exact bytes or a named abort, never partial."""
            try:
                return ('ok', encode_custom_value(profile, value))
            except CustomTypeError as error:
                return ('abort', error.to_abort().to_dict())

        status, payload = host_call(ct('1'), 300)
        self.assertEqual(status, 'abort')
        self.assertEqual(set(payload), {'schema', 'code', 'reason', 'offset', 'stage'})
        self.assertEqual(payload['schema'], ABORT_SCHEMA)
        self.assertEqual(payload['code'], 'custom-value-out-of-range')
        self.assertEqual(payload['stage'], 'encode')
        self.assertIsNone(payload['offset'])
        json.dumps(payload)
        status, raw = host_call(ct('2 4', inverse=True), 2)
        self.assertEqual(status, 'ok')
        # Whole value 2 in a 6-byte little-endian span, then full-span inverse.
        self.assertEqual(raw, b'\x00\x00\x00\x00\x00\x02')
        abort = CustomTypeAbort('custom-span-mismatch', 'text', 3, 'decode')
        self.assertEqual(CustomTypeError('text', code='custom-span-mismatch',
                                         stage='decode', offset=3).to_abort(), abort)

    def test_section_parses_definitions_and_attributes(self):
        profiles = parse_custom_types_section(RE2_SECTION)
        by_name = {profile.name: profile for profile in profiles}
        self.assertEqual(len(profiles), 5)
        self.assertEqual([profile.name for profile in profiles],
                         ['RE2_Hrs', 'RE2_Mins', 'RE2_Secs', 'Composite', 'Triplet'])
        self.assertEqual(by_name['RE2_Hrs'].size, 1)
        self.assertEqual(by_name['Composite'].size, 6)
        self.assertEqual(by_name['Composite'].endianness, 'big')
        self.assertTrue(by_name['Triplet'].inverse)
        self.assertTrue(by_name['Triplet'].signed)
        self.assertEqual(by_name['Triplet'].size, 6)
        self.assertEqual(profiles[0].fields[0].offset, 0)
        for profile in profiles:
            validate_custom_type(profile)

    def test_section_rejects_invalid_members(self):
        invalid = {
            '<CustomTypes><CustomType name="A">1</CustomType>'
            '<CustomType name="A">2</CustomType></CustomTypes>':
            'Duplicate custom type name',
            '<CustomTypes><CustomType>1</CustomType></CustomTypes>':
            'has no name',
            '<CustomTypes><CustomType name="A" Bogus="1">1</CustomType>'
            '</CustomTypes>': 'Unknown custom type attributes',
            '<CustomTypes><CustomX name="A">1</CustomX></CustomTypes>':
            'Unknown <CustomTypes> member',
            '<CustomTypes><CustomType name="A"/></CustomTypes>':
            'Empty format',
            '<CustomTypes><CustomType name="A">4</CustomType>'
            '<CustomType name="B" Endian="middle">4</CustomType></CustomTypes>':
            'Endianness',
            '<CustomTypes><CustomType name="A" Inverse="2">4</CustomType>'
            '</CustomTypes>': 'must be 0 or 1',
        }
        for text, message in invalid.items():
            with self.subTest(text=text[:40]):
                with self.assertRaisesRegex(CustomTypeError, message):
                    parse_custom_types_section(text)

    def test_section_rejects_wrong_root_and_dtd(self):
        for text in ('<CheatTable/>', '<CustomType name="A">4</CustomType>',
                     '<!DOCTYPE CustomTypes><CustomTypes/>',
                     '<CustomTypes><CustomType name="A">4</CustomType></CustomTypes>EXTRA'):
            with self.subTest(text=text):
                try:
                    parse_custom_types_section(text)
                    self.fail('expected CustomTypeError for ' + repr(text))
                except CustomTypeError as error:
                    self.assertEqual(error.code, 'custom-section-invalid')
        with self.assertRaisesRegex(CustomTypeError, 'must be an element or XML text'):
            parse_custom_types_section(42)
        with self.assertRaisesRegex(CustomTypeError, 'not valid UTF-8'):
            parse_custom_types_section(b'\xff<CustomTypes/>')

    def test_ct_root_helper_extracts_custom_types(self):
        profiles = custom_types_from_ct_root(RE2_CT)
        self.assertEqual([profile.name for profile in profiles], ['RE2_Hrs'])
        self.assertEqual(profiles[0].size, 1)
        self.assertEqual(custom_types_from_ct_root(ET.fromstring(RE2_CT))[0].name,
                         'RE2_Hrs')
        empty = RE2_CT.replace('<CustomTypes><CustomType name="RE2_Hrs">1</CustomType>'
                               '</CustomTypes>', '')
        self.assertEqual(custom_types_from_ct_root(empty), ())
        with self.assertRaisesRegex(CustomTypeError, 'Expected <CheatTable>'):
            custom_types_from_ct_root(RE2_SECTION)
        with self.assertRaisesRegex(CustomTypeError, 'DTD/ENTITY'):
            custom_types_from_ct_root('<!DOCTYPE CheatTable><CheatTable/>')

    def test_format_text_allows_ascii_whitespace_runs(self):
        profile = ct('2 \t 4')
        self.assertEqual(profile.size, 6)
        self.assertEqual(profile.format_text, '2 \t 4')
        self.assertEqual(decode_custom_fields(profile, b'\x01\x00\x02\x00\x00\x00'),
                         (1, 2))

    def test_re2_hours_synthetic_one_byte_unsigned(self):
        # Synthetic stand-in for re2.CT record 13181 (RE2_Hrs). The audit
        # (Befund C-04) names the record and its Lua-defined custom type but
        # not the exact format, so this case pins an equivalent 1-byte
        # unsigned definition.
        profiles = parse_custom_types_section(RE2_SECTION)
        profile = next(item for item in profiles if item.name == 'RE2_Hrs')
        self.assertEqual(encode_custom_value(profile, 23), b'\x17')
        self.assertEqual(decode_custom_value(profile, b'\x17'), 23)
        self.assertEqual(encode_custom_value(profile, 255), b'\xff')
        with self.assertRaisesRegex(CustomTypeError, 'outside'):
            encode_custom_value(profile, 256)
        self.assertEqual(decode_custom_value(profile, b'\x00'), 0)

    def test_re2_minutes_synthetic_two_byte_little_endian(self):
        # Synthetic stand-in for re2.CT record 13182 (RE2_Mins) as a 2-byte
        # little-endian definition; see Befund C-04 for the real record.
        profile = parse_custom_type_definition('RE2_Mins', '2')
        self.assertEqual(encode_custom_value(profile, 59), b'\x3b\x00')
        self.assertEqual(decode_custom_value(profile, b'\x3b\x00'), 59)
        self.assertEqual(encode_custom_value(profile, 0x0102), b'\x02\x01')
        big = parse_custom_type_definition('RE2_Mins_BE', '2', endianness='big')
        self.assertEqual(encode_custom_value(big, 59), b'\x00\x3b')

    def test_re2_seconds_synthetic_one_byte_signed(self):
        # Synthetic stand-in for re2.CT record 13183 (RE2_Secs) as a signed
        # 1-byte definition; see Befund C-04 for the real record.
        profile = parse_custom_type_definition('RE2_Secs', '1', signed=True)
        self.assertEqual(decode_custom_value(profile, b'\xff'), -1)
        self.assertEqual(encode_custom_value(profile, -1), b'\xff')
        self.assertEqual(decode_custom_value(profile, b'\x1e'), 30)
        self.assertEqual(encode_custom_value(profile, -128), b'\x80')
        self.assertEqual(encode_custom_value(profile, 127), b'\x7f')
        for value in (-129, 128):
            with self.subTest(value=value):
                with self.assertRaisesRegex(CustomTypeError, 'outside'):
                    encode_custom_value(profile, value)


if __name__ == '__main__':
    unittest.main()
