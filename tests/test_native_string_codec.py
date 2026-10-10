import dataclasses
import unittest
from ct2trainer.native.string_values import *

class StringContractTests(unittest.TestCase):
    def profile(self,**values):return prepare({'Length':8,**values})
    def test_unicode_counts_utf16_units_and_terminator(self):
        p=self.profile(Unicode=1,Length=4)
        self.assertEqual(parse(p,'A🙂').replacement,bytes.fromhex('41003dd842de0000'))
        with self.assertRaises(StringValueError):parse(p,'AB🙂')
    def test_terminated_write_does_not_zero_bounded_tail(self):
        p=self.profile()
        value=parse(p,'ab')
        self.assertEqual(value.replacement,b'ab\0')
        self.assertEqual(value.read_bound,8)
        current=b'ab\0TAIL!'
        self.assertTrue(desired_matches(p,value,current))
        self.assertTrue(desired_matches(p,value,b'ab\0DIFF!'))
        self.assertFalse(desired_matches(p,value,b'ac\0TAIL!'))
    def test_unicode_terminator_is_aligned(self):
        p=self.profile(Unicode=True,Length=4)
        self.assertEqual(format_value(p,'ĀX'.encode('utf-16-le')+b'\0'*4),'ĀX')
    def test_malformed_tail_after_terminator_is_ignored(self):
        p=self.profile(Unicode=True,Length=4)
        self.assertEqual(format_value(p,b'A\0\0\0\0\xd8\xff\xff'),'A')
    def test_malformed_visible_surrogate_is_refused(self):
        p=self.profile(Unicode=True,Length=2)
        with self.assertRaises(StringValueError):format_value(p,b'\0\xd8\0\0')
        with self.assertRaises(StringValueError):parse(p,'\ud800')
    def test_ascii_profile_does_not_invent_codepage(self):
        p=self.profile()
        with self.assertRaises(StringValueError):parse(p,'ä')
        with self.assertRaises(StringValueError):format_value(p,b'\xe4'+b'\0'*7)
        with self.assertRaises(StringValueError):prepare({'Length':8,'CodePage':True})
    def test_fixed_units_require_exact_bytes_and_allow_embedded_zero(self):
        p=self.profile(ZeroTerminate=False,Length=3)
        self.assertEqual(parse(p,'a\0b').replacement,b'a\0b')
        self.assertEqual(format_value(p,b'a\0b'),'a\0b')
        with self.assertRaises(StringValueError):parse(p,'ab')
    def test_empty_literal_has_only_terminator(self):
        self.assertEqual(parse(self.profile(),'').replacement,b'\0')
        self.assertEqual(parse(self.profile(Unicode=1),'').replacement,b'\0\0')
    def test_embedded_terminated_zero_is_refused(self):
        with self.assertRaises(StringValueError):parse(self.profile(),'a\0b')
    def test_zero_length_has_no_action(self):
        p=self.profile(Length=0)
        self.assertFalse(p['actionable'])
        for operation in (lambda:parse(p,''),lambda:format_value(p,b'')):
            with self.assertRaises(StringValueError):operation()
    def test_lengths_flags_and_byte_ceiling(self):
        for value in (True,-1,65537,'-1','0x10','1.0',None):
            with self.subTest(value=value),self.assertRaises(StringValueError):prepare({'Length':value})
        with self.assertRaises(StringValueError):self.profile(Unicode=1,Length=32769)
        self.assertEqual(self.profile(Unicode=1,Length=32768)['size'],65536)
        for value in (2,'yes',{},0.0):
            with self.subTest(value=value),self.assertRaises(StringValueError):self.profile(Unicode=value)
    def test_whitespace_text_is_literal(self):
        self.assertEqual(parse(self.profile(),'  a  ').replacement,b'  a  \0')
    def test_source_derived_profile_cannot_be_forged(self):
        p=self.profile(Unicode=True)
        validate(p)
        for change in ({'size':1},{'encoding':'utf-8'},{'extra':True}):
            with self.subTest(change=change),self.assertRaises(StringValueError):validate({**p,**change})
    def test_current_requires_complete_span(self):
        p=self.profile()
        with self.assertRaises(StringValueError):format_value(p,b'ab\0')
        with self.assertRaises(StringValueError):desired_matches(p,parse(p,'ab'),b'ab\0')
    def test_forged_desire_has_no_authority(self):
        p=self.profile()
        original=parse(p,'ab')
        for change in ({'replacement':b'ab'},{'replacement':b'a\0b\0'},{'replacement':b'\xe4\0'},
                       {'read_bound':2},{'unit_bytes':2}):
            with self.subTest(change=change),self.assertRaises(StringValueError):
                desired_matches(p,dataclasses.replace(original,**change),b'ab\0TAIL!')
    def test_maximum_ascii_length_leaves_terminator_room(self):
        p=self.profile(Length=65536)
        self.assertEqual(len(parse(p,'x'*65535).replacement),65536)
        with self.assertRaises(StringValueError):parse(p,'x'*65536)

    def test_desire_metadata_requires_exact_integer_types_and_concrete_class(self):
        p=self.profile()
        original=parse(p,'ab')
        for change in ({'read_bound':8.0},{'unit_bytes':1.0},{'unit_bytes':True}):
            with self.subTest(change=change),self.assertRaises(StringValueError):
                desired_matches(p,dataclasses.replace(original,**change),b'ab\0TAIL!')
        class AlternateWrite(type(original)):
            pass
        with self.assertRaises(StringValueError):
            desired_matches(p,AlternateWrite(original.replacement,original.read_bound,original.unit_bytes),b'ab\0TAIL!')
        single=self.profile(Length=1)
        with self.assertRaises(StringValueError):
            desired_matches(single,dataclasses.replace(parse(single,''),read_bound=True),b'\0')

    def test_metadata_nan_has_the_domain_error_type(self):
        with self.assertRaises(StringValueError):validate({**self.profile(),'size':float('nan')})

    def test_flag_text_is_bounded_and_uses_ascii_metadata_whitespace(self):
        for flag in (' '*100000+'1','\u00a01', '1'+' '*100000):
            with self.subTest(flag_length=len(flag)),self.assertRaises(StringValueError):
                self.profile(Unicode=flag)

    def test_unterminated_read_is_visible_but_not_a_terminated_write_capacity(self):
        p=self.profile()
        visible=format_value(p,b'abcdefgh')
        self.assertEqual(visible,'abcdefgh')
        with self.assertRaises(StringValueError):parse(p,visible)

if __name__=='__main__':unittest.main()
