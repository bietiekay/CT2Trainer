"""Owned byte patterns validate codecs independently of process-memory access."""

import copy
import unittest

from ct2trainer.native.value_types import (MAX_BYTE_LENGTH, ValueTypeError,
                                            format_profile_value, merge_profile_value,
                                            parse_profile_value, prepare_value_profile,
                                            profile_mask, profile_size,
                                            profile_value_matches, validate_value_profile)


def bits(start, length, **properties):
    return prepare_value_profile('Binary', {'BitStart':start,'BitLength':length,**properties})


class NativeValueTypeTests(unittest.TestCase):
    def test_byte_array_exact_hex_roundtrip_and_raw_unsigned_policy(self):
        profile=prepare_value_profile('Array of byte',{'ByteLength':'4','ShowAsHex':'0','ShowAsSigned':'1'})
        self.assertEqual(profile_size(profile),4)
        self.assertEqual(profile['display'],'hex_bytes')
        self.assertFalse(profile['signed'])
        self.assertEqual(profile_mask(profile),b'\xff'*4)
        self.assertEqual(parse_profile_value(profile,' 00\t7f\n80 FF '),b'\x00\x7f\x80\xff')
        self.assertEqual(format_profile_value(profile,b'\x00\x7f\x80\xff'),'00 7F 80 FF')
        self.assertTrue(profile_value_matches(profile,b'\x00\x7f\x80\xff',b'\x00\x7f\x80\xff'))
        self.assertFalse(profile_value_matches(profile,b'\x00\x7f\x80\xff',b'\x00\x7f\x80\xfe'))
        self.assertEqual(merge_profile_value(profile,b'\x01\x02\x03\x04',b'\xff'*4),b'\x01\x02\x03\x04')

    def test_byte_array_rejects_wildcards_expressions_and_wrong_lengths(self):
        profile=prepare_value_profile('Array of byte',{'ByteLength':2})
        for text in ('AA ??','AA **','A? BB','AA *','AABB','0xAA BB','AA,BB','AA','AA BB CC',
                     'GG BB','AA BB;writeBytes()','170 187','AA\u00a0BB','-1 00',''):
            with self.subTest(text=text),self.assertRaises(ValueTypeError):
                parse_profile_value(profile,text)
        for raw in (b'\x00',b'\x00'*3,[],None):
            with self.subTest(raw=raw),self.assertRaises(ValueTypeError):
                format_profile_value(profile,raw)
        with self.assertRaises(ValueTypeError):
            parse_profile_value(profile,'AA BB',b'\x00')

    def test_zero_length_array_is_an_explicit_non_actionable_placeholder(self):
        profile=prepare_value_profile('Array of byte',{'ByteLength':'0','ShowAsHex':'1','ShowAsSigned':'1'})
        validate_value_profile(profile)
        self.assertFalse(profile['actionable'])
        self.assertTrue(profile['read_only'])
        self.assertIn('placeholder',profile['reason'])
        self.assertEqual(profile_size(profile),0)
        self.assertEqual(profile_mask(profile),b'')
        self.assertEqual(format_profile_value(profile,b''),'')
        for operation in (lambda:parse_profile_value(profile,''),
                          lambda:merge_profile_value(profile,b'',b''),
                          lambda:profile_value_matches(profile,b'',b'')):
            with self.assertRaisesRegex(ValueTypeError,'non-actionable'):
                operation()

    def test_metadata_bounds_and_flag_errors_are_rejected(self):
        invalid=(('Array of byte',{}),('Array of byte',{'ByteLength':'-1'}),
                 ('Array of byte',{'ByteLength':MAX_BYTE_LENGTH+1}),
                 ('Array of byte',{'ByteLength':True}),('Array of byte',{'ByteLength':'0x10'}),
                 ('Array of byte',{'ByteLength':1,'ShowAsBinary':1}),
                 ('Binary',{'BitLength':1}),('Binary',{'BitStart':0}),
                 ('Binary',{'BitStart':8,'BitLength':1}),('Binary',{'BitStart':-1,'BitLength':1}),
                 ('Binary',{'BitStart':0,'BitLength':0}),('Binary',{'BitStart':0,'BitLength':65}),
                 ('Binary',{'BitStart':False,'BitLength':1}),
                 ('Binary',{'BitStart':0,'BitLength':1,'ShowAsHex':'true'}),
                 ('Binary',{'BitStart':0,'BitLength':1,'ShowAsHex':2}),
                 ('Binary',{'BitStart':0,'BitLength':1,'ShowAsHex':1,'ShowAsBinary':1}),
                 ('Custom',{}))
        for kind,properties in invalid:
            with self.subTest(kind=kind,properties=properties),self.assertRaises(ValueTypeError):
                prepare_value_profile(kind,properties)
        with self.assertRaises(ValueTypeError):prepare_value_profile('Array of byte',None)
        maximum=prepare_value_profile('Array of byte',{'ByteLength':MAX_BYTE_LENGTH})
        self.assertEqual(profile_size(maximum),MAX_BYTE_LENGTH)
        self.assertEqual(len(profile_mask(maximum)),MAX_BYTE_LENGTH)

    def test_profile_validation_reconstructs_all_derived_metadata(self):
        original=bits(7,10,ShowAsBinary=1)
        for key,value in {'size':1,'kind':'byte_array','bit_order':'msb0','byte_order':'big',
                          'display':'decimal','signed':True,'actionable':False,'read_only':True,
                          'reason':'forged','extra':True}.items():
            with self.subTest(key=key):
                changed=copy.deepcopy(original);changed[key]=value
                with self.assertRaises(ValueTypeError):validate_value_profile(changed)
        changed=copy.deepcopy(original);changed['properties']['unexpected']='ignored'
        with self.assertRaises(ValueTypeError):validate_value_profile(changed)
        changed=copy.deepcopy(original);changed['properties']['BitLength']='10'
        with self.assertRaises(ValueTypeError):validate_value_profile(changed)
        changed=copy.deepcopy(original);changed['size']=float('nan')
        with self.assertRaises(ValueTypeError):validate_value_profile(changed)

    def test_single_bit_fields_use_lsb_zero_and_preserve_every_other_bit(self):
        for start in range(8):
            with self.subTest(start=start):
                profile=bits(start,1)
                self.assertEqual(profile_size(profile),1)
                self.assertEqual(profile_mask(profile),bytes([1<<start]))
                set_bit=parse_profile_value(profile,'1',b'\x00')
                self.assertEqual(set_bit,bytes([1<<start]))
                self.assertEqual(format_profile_value(profile,set_bit),'1')
                clear_bit=parse_profile_value(profile,'0',b'\xff')
                self.assertEqual(clear_bit,bytes([0xff^(1<<start)]))
                self.assertEqual(format_profile_value(profile,clear_bit),'0')
                with self.assertRaises(ValueTypeError):parse_profile_value(profile,'2',b'\x00')

    def test_cross_byte_little_endian_field_preserves_prefix_and_suffix_bits(self):
        profile=bits(7,10)
        self.assertEqual(profile_size(profile),3)
        self.assertEqual(profile_mask(profile),b'\x80\xff\x01')
        original=b'\x55\xaa\xfe'
        written=parse_profile_value(profile,'682',original)
        self.assertEqual(written,b'\x55\x55\xff')
        self.assertEqual(format_profile_value(profile,written),'682')
        self.assertEqual(parse_profile_value(profile,'0',written),b'\x55\x00\xfe')

    def test_full_sixty_four_bit_field_can_span_nine_bytes(self):
        profile=bits(7,64)
        self.assertEqual(profile_size(profile),9)
        self.assertEqual(profile_mask(profile),b'\x80'+b'\xff'*7+b'\x7f')
        self.assertEqual(parse_profile_value(profile,'0',b'\xff'*9),b'\x7f'+b'\x00'*7+b'\x80')
        maximum=str(2**64-1)
        self.assertEqual(format_profile_value(profile,parse_profile_value(profile,maximum,b'\xff'*9)),maximum)
        with self.assertRaises(ValueTypeError):parse_profile_value(profile,str(2**64),b'\x00'*9)

    def test_signed_decimal_uses_field_width_without_signing_adjacent_bits(self):
        profile=bits(5,3,ShowAsSigned=1)
        self.assertTrue(profile['signed'])
        self.assertEqual(parse_profile_value(profile,'-4',b'\xff'),b'\x9f')
        self.assertEqual(format_profile_value(profile,b'\x9f'),'-4')
        self.assertEqual(parse_profile_value(profile,'3',b'\xff'),b'\x7f')
        self.assertEqual(format_profile_value(profile,b'\xff'),'-1')
        for text in ('4','-5','0x1','1+1','1.0','True'):
            with self.subTest(text=text),self.assertRaises(ValueTypeError):
                parse_profile_value(profile,text,b'\x00')
        one=bits(0,1,ShowAsSigned=1)
        self.assertEqual(format_profile_value(one,b'\x01'),'-1')
        unsigned=bits(5,3)
        with self.assertRaises(ValueTypeError):parse_profile_value(unsigned,'-1',b'\x00')

    def test_binary_display_uses_fixed_msb_first_digits_and_unsigned_patterns(self):
        profile=bits(3,5,ShowAsBinary=1,ShowAsSigned=1)
        self.assertFalse(profile['signed'])
        self.assertEqual(format_profile_value(profile,b'\xd5'),'11010')
        self.assertEqual(parse_profile_value(profile,'00101',b'\xd5'),b'\x2d')
        self.assertEqual(format_profile_value(profile,parse_profile_value(profile,'1',b'\x00')),'00001')
        for text in ('100000','0b101','2','-1','+1','1 0',''):
            with self.subTest(text=text),self.assertRaises(ValueTypeError):
                parse_profile_value(profile,text,b'\x00')

    def test_hex_display_is_raw_unsigned_with_field_bound_not_nibble_bound(self):
        profile=bits(3,5,ShowAsHex=1,ShowAsSigned=1)
        self.assertFalse(profile['signed'])
        self.assertEqual(format_profile_value(profile,b'\xd5'),'1A')
        self.assertEqual(parse_profile_value(profile,'0x1f',b'\xd5'),b'\xfd')
        self.assertEqual(parse_profile_value(profile,'0X1F',b'\xd5'),b'\xfd')
        for text in ('20','100','-1','+1','1Fh','0b10',''):
            with self.subTest(text=text),self.assertRaises(ValueTypeError):
                parse_profile_value(profile,text,b'\x00')

    def test_binary_requires_a_complete_current_snapshot(self):
        profile=bits(7,10)
        for raw in (None,b'',b'\x00',b'\x00'*2,b'\x00'*4,[],17):
            with self.subTest(raw=raw),self.assertRaises(ValueTypeError):
                parse_profile_value(profile,'1',raw)
        self.assertEqual(parse_profile_value(profile,'1',bytearray(b'\x00'*3)),b'\x80\x00\x00')
        with self.assertRaises(ValueTypeError):format_profile_value(profile,b'\x00'*2)
        with self.assertRaises(ValueTypeError):merge_profile_value(profile,b'\x00'*2,b'\x00'*3)

    def test_freeze_merge_and_restore_do_not_restore_stale_neighbor_bits(self):
        first=bits(0,1);second=bits(1,1)
        first_original=b'\x00'
        first_desired=parse_profile_value(first,'1',first_original)
        current=b'\x81'  # The target independently set its seventh bit.
        second_desired=parse_profile_value(second,'1',current)
        self.assertEqual(second_desired,b'\x83')
        self.assertEqual(merge_profile_value(first,first_desired,second_desired),b'\x83')
        self.assertTrue(profile_value_matches(first,first_desired,b'\x83'))
        self.assertFalse(profile_value_matches(first,first_desired,b'\x82'))
        restored=merge_profile_value(first,first_original,b'\x83')
        self.assertEqual(restored,b'\x82')
        self.assertTrue(profile_value_matches(second,second_desired,restored))

    def test_ownership_mask_overlap_distinguishes_fields_sharing_one_byte(self):
        first=profile_mask(bits(0,1));second=profile_mask(bits(1,1));wide=profile_mask(bits(0,2))
        self.assertFalse(any(a&b for a,b in zip(first,second)))
        self.assertTrue(any(a&b for a,b in zip(wide,second)))


    def test_string_show_as_hex_stages_byte_array_and_binary_stays_refused(self):
        # RT-4.4 (O7): a ShowAsHex string record exposes its bounded byte
        # buffer as a byte-array value (roadmap O7 row); the literal-text
        # codec and its encoding rules no longer apply to this view.
        profile = prepare_value_profile('String', {'Length': 8, 'ZeroTerminate': 1,
                                                   'ShowAsHex': 1})
        self.assertEqual(profile['kind'], 'byte_array')
        self.assertEqual(profile['size'], 8)
        self.assertEqual(profile['display'], 'hex_bytes')
        self.assertEqual(profile['byte_order'], 'address')
        self.assertFalse(profile['signed'])
        self.assertTrue(profile['actionable'])
        self.assertFalse(profile['read_only'])
        self.assertEqual(profile['variable_type'], 'String')
        self.assertTrue(profile['properties']['ShowAsHex'])
        self.assertTrue(profile['properties']['ZeroTerminate'])
        validate_value_profile(profile)
        # The canonical write literal is exact hex byte pairs over the
        # full buffer; anything else is refused by the byte-array codec.
        self.assertEqual(parse_profile_value(profile, '01 02 03 04 05 06 07 08'),
                         b'\x01\x02\x03\x04\x05\x06\x07\x08')
        self.assertEqual(format_profile_value(profile, b'\x01\x02\x03\x04\x05\x06\x07\x08'),
                         '01 02 03 04 05 06 07 08')
        for text in ('01 02', '01 02 03 04 05 06 07 08 09',
                     'GG GG GG GG GG GG GG GG', '01 02 03 04 05 06 07', 'hello'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_profile_value(profile, text)
        # Unicode sizing still bounds the byte-array span (Length * unit).
        wide = prepare_value_profile('String', {'Length': 4, 'Unicode': 1, 'ShowAsHex': 1})
        self.assertEqual(wide['kind'], 'byte_array')
        self.assertEqual(wide['size'], 8)
        self.assertEqual(parse_profile_value(wide, '01 02 03 04 05 06 07 08'),
                         b'\x01\x02\x03\x04\x05\x06\x07\x08')
        # WP-34 pin: the ShowAsBinary byte view is still refused with the
        # named flag, byte-identical to the pre-RT-4.4 message.
        with self.assertRaises(ValueError) as caught:
            prepare_value_profile('String', {'Length': 8, 'ZeroTerminate': 1,
                                             'ShowAsBinary': 1})
        self.assertEqual(str(caught.exception),
                         'Strings require literal text display; the ShowAsBinary byte view is unsupported.')
        ok = prepare_value_profile('String', {'Length': 8, 'ZeroTerminate': 1,
                                              'ShowAsHex': 0, 'ShowAsBinary': 0})
        self.assertEqual(ok['kind'], 'string')
        self.assertTrue(ok['actionable'])


if __name__=='__main__':
    unittest.main()
