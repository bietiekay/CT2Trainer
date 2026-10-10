# -*- coding: utf-8 -*-
"""Focused fixture-driven tests for the pinned CodePage contract.

Drives ``src/ct2trainer/native/codepage_contract.py`` against the
hand-verified byte expectations of ``tests/codepage_fixture_data.py``
(no TableReferences, no CE inputs).  Pinned scenarios:

- Table completeness: the supported set is exactly
  {0, 1250, 1251, 1252, 1253, 1254, 1257, 65001}; 0 is the cp1252 alias;
  1250-1254/1257 map to the exact IANA/Microsoft cp125x codecs; 65001 is
  UTF-8 with code unit = byte; every other integer and every non-integer
  value is refused fail-closed.
- Lengths: ASCII identity across all codepages, pinned multi-byte lengths
  per codec, UTF-8 1/2/3/4-byte sequences, empty text.
- Bounded encode: exact fits, no implicit NUL extension, single-byte
  clips at arbitrary boundaries, UTF-8 clips only on codepoint starts,
  TruncationRefused on any multi-byte split, zero-bound empty spans.
- Bounded decode: full/prefix/exact-boundary decodes, IncompleteSequence
  on truncated tails, undefined cp1252 bytes.
- Roundtrip: every fixture text per codepage, surrogate refusal.
- Lossless predicate: native texts true, cross-codepage and surrogate
  texts false, unsupported codepages still refused.
"""
import unittest

from ct2trainer.native.codepage_contract import (
    CodePageContractError,
    IncompleteSequence,
    TruncationRefused,
    UnsupportedCodePage,
    codec_for,
    codepage_name,
    decode_bounded,
    encode_bounded,
    encoded_length,
    is_lossless,
    supported_codepages,
)

try:
    from codepage_fixture_data import (
        BOUNDED_DECODE_CASES,
        BOUNDED_ENCODE_CASES,
        CODEPAGE_FIXTURES,
        LOSSY_CASES,
        NON_INTEGER_CODEPAGES,
        UNSUPPORTED_CODEPAGES,
    )
except ModuleNotFoundError:  # invoked as tests.test_native_codepage_contract
    from tests.codepage_fixture_data import (
        BOUNDED_DECODE_CASES,
        BOUNDED_ENCODE_CASES,
        CODEPAGE_FIXTURES,
        LOSSY_CASES,
        NON_INTEGER_CODEPAGES,
        UNSUPPORTED_CODEPAGES,
    )

PINNED = (0, 1250, 1251, 1252, 1253, 1254, 1257, 65001)
PINNED_CODECS = {
    0: 'cp1252',
    1250: 'cp1250',
    1251: 'cp1251',
    1252: 'cp1252',
    1253: 'cp1253',
    1254: 'cp1254',
    1257: 'cp1257',
    65001: 'utf-8',
}


class PinnedTableTests(unittest.TestCase):
    def test_supported_codepages_are_exactly_the_pinned_set(self):
        self.assertEqual(supported_codepages(), PINNED)

    def test_supported_codepages_is_immutable_tuple(self):
        self.assertIs(type(supported_codepages()), tuple)
        with self.assertRaises(TypeError):
            supported_codepages()[0] = 999

    def test_codec_for_maps_each_pinned_value_to_its_codec(self):
        for codepage, codec in PINNED_CODECS.items():
            with self.subTest(codepage=codepage):
                self.assertEqual(codec_for(codepage), codec)

    def test_codepage_name_maps_each_pinned_value_to_its_name(self):
        for codepage in PINNED:
            with self.subTest(codepage=codepage):
                self.assertIsInstance(codepage_name(codepage), str)
                self.assertGreater(len(codepage_name(codepage)), 0)

    def test_zero_is_the_windows_1252_alias(self):
        self.assertEqual(codec_for(0), codec_for(1252))
        for text in ('abc', 'Äöü€ß', '\u201e\u2026\u201d'):
            with self.subTest(text=text):
                self.assertEqual(encoded_length(text, 0), encoded_length(text, 1252))
                self.assertEqual(
                    encode_bounded(text, 0, 32), encode_bounded(text, 1252, 32))
                raw = encode_bounded(text, 0, 32)
                self.assertEqual(
                    decode_bounded(raw, 0, len(raw)),
                    decode_bounded(raw, 1252, len(raw)))
                self.assertEqual(is_lossless(text, 0), is_lossless(text, 1252))

    def test_sixty_five_thousand_and_one_is_utf8_byte_semantics(self):
        self.assertEqual(codec_for(65001), 'utf-8')
        self.assertEqual(encoded_length('🙂', 65001), 4)
        self.assertEqual(encoded_length('€', 65001), 3)
        self.assertEqual(encoded_length('é', 65001), 2)
        self.assertEqual(encoded_length('A', 65001), 1)

    def test_non_pinned_integers_are_refused_fail_closed(self):
        for value in UNSUPPORTED_CODEPAGES:
            with self.subTest(codepage=value):
                for operation in (
                    lambda: codec_for(value),
                    lambda: codepage_name(value),
                    lambda: encoded_length('a', value),
                    lambda: encode_bounded('a', value, 4),
                    lambda: decode_bounded(b'a', value, 4),
                    lambda: is_lossless('a', value),
                ):
                    with self.assertRaises(UnsupportedCodePage):
                        operation()

    def test_non_integer_codepages_are_refused(self):
        for value in NON_INTEGER_CODEPAGES:
            with self.subTest(codepage=repr(value)):
                for operation in (
                    lambda: codec_for(value),
                    lambda: encoded_length('a', value),
                    lambda: encode_bounded('a', value, 4),
                    lambda: decode_bounded(b'a', value, 4),
                    lambda: is_lossless('a', value),
                ):
                    with self.assertRaises(UnsupportedCodePage):
                        operation()

    def test_error_classes_form_a_valueerror_family(self):
        self.assertTrue(issubclass(UnsupportedCodePage, CodePageContractError))
        self.assertTrue(issubclass(IncompleteSequence, CodePageContractError))
        self.assertTrue(issubclass(TruncationRefused, CodePageContractError))
        self.assertTrue(issubclass(CodePageContractError, ValueError))


class EncodedLengthTests(unittest.TestCase):
    def test_ascii_length_is_identity_in_every_codepage(self):
        for codepage in PINNED:
            with self.subTest(codepage=codepage):
                self.assertEqual(encoded_length('abcdef', codepage), 6)

    def test_pinned_fixture_lengths_per_codec(self):
        for codepage, entries in CODEPAGE_FIXTURES.items():
            for label, text, expected in entries:
                with self.subTest(codepage=codepage, label=label):
                    self.assertEqual(
                        encoded_length(text, codepage), len(expected) // 2)

    def test_utf8_one_two_three_four_byte_sequence_lengths(self):
        self.assertEqual(encoded_length('A', 65001), 1)
        self.assertEqual(encoded_length('é', 65001), 2)
        self.assertEqual(encoded_length('€', 65001), 3)
        self.assertEqual(encoded_length('🙂', 65001), 4)
        self.assertEqual(encoded_length('Aé€🙂', 65001), 10)

    def test_empty_text_has_zero_length_in_every_codepage(self):
        for codepage in PINNED:
            with self.subTest(codepage=codepage):
                self.assertEqual(encoded_length('', codepage), 0)

    def test_unrepresentable_text_is_refused_not_crashed(self):
        for text, codepage in LOSSY_CASES:
            with self.subTest(text=repr(text), codepage=codepage):
                with self.assertRaises(IncompleteSequence):
                    encoded_length(text, codepage)

    def test_refusal_message_names_offending_codepoint(self):
        with self.assertRaisesRegex(
                IncompleteSequence, r'U\+041F at position 0'):
            encoded_length('Привет', 1252)
        with self.assertRaisesRegex(
                IncompleteSequence, r'U\+D800 at position 0'):
            encoded_length('\ud800', 65001)

    def test_non_str_text_is_refused(self):
        for value in (None, 7, b'abc', 1.5):
            with self.subTest(value=repr(value)):
                with self.assertRaises(CodePageContractError):
                    encoded_length(value, 1252)


class EncodeBoundedTests(unittest.TestCase):
    def test_exact_fit_returns_full_encoding(self):
        self.assertEqual(
            encode_bounded('\u00c4\u00f6\u00fc\u20ac\u00df', 0, 5),
            bytes.fromhex('c4f6fc80df'))
        self.assertEqual(encode_bounded('🙂A', 65001, 5),
                         bytes.fromhex('f09f998241'))

    def test_shorter_text_is_returned_unpadded_no_implicit_nul(self):
        raw = encode_bounded('A', 65001, 8)
        self.assertEqual(raw, b'A')
        self.assertEqual(len(raw), 1)
        self.assertFalse(raw.endswith(b'\0'))
        self.assertEqual(encode_bounded('Hi', 1252, 65536), b'Hi')

    def test_single_byte_codecs_clip_at_any_boundary(self):
        for codepage in (0, 1250, 1251, 1252, 1253, 1254, 1257):
            with self.subTest(codepage=codepage):
                text = 'abcd'
                self.assertEqual(
                    encode_bounded(text, codepage, 2), b'ab')
                self.assertEqual(
                    encode_bounded(text, codepage, 3), b'abc')

    def test_utf8_clips_only_on_codepoint_starts(self):
        for case in BOUNDED_ENCODE_CASES:
            codepage, text, max_bytes, expected = case
            if expected is not None:
                with self.subTest(codepage=codepage, text=text,
                                  max_bytes=max_bytes):
                    self.assertEqual(
                        encode_bounded(text, codepage, max_bytes),
                        bytes.fromhex(expected))

    def test_utf8_multi_byte_split_is_refused(self):
        for case in BOUNDED_ENCODE_CASES:
            codepage, text, max_bytes, expected = case
            if expected is None:
                with self.subTest(codepage=codepage, text=text,
                                  max_bytes=max_bytes):
                    with self.assertRaises(TruncationRefused):
                        encode_bounded(text, codepage, max_bytes)

    def test_refusal_message_names_clip_position_and_codec(self):
        with self.assertRaisesRegex(
                TruncationRefused,
                r'clipping at byte 4 would split a multi-byte codepoint '
                r'of the pinned utf-8 codec for CodePage 65001'):
            encode_bounded('Aé🙂', 65001, 4)

    def test_zero_bound_returns_empty_span(self):
        for codepage, text in ((65001, '🙂'), (1252, 'Ä'), (0, 'abc')):
            with self.subTest(codepage=codepage, text=text):
                self.assertEqual(encode_bounded(text, codepage, 0), b'')

    def test_unrepresentable_text_is_refused_before_any_output(self):
        for text, codepage in LOSSY_CASES:
            with self.subTest(text=repr(text), codepage=codepage):
                with self.assertRaises(IncompleteSequence):
                    encode_bounded(text, codepage, 64)

    def test_invalid_max_bytes_is_refused(self):
        for value in (-1, True, False, 3.0, '8', None):
            with self.subTest(max_bytes=repr(value)):
                with self.assertRaises(CodePageContractError):
                    encode_bounded('A', 65001, value)

    def test_non_str_text_is_refused(self):
        for value in (None, 7, b'abc', ('a',)):
            with self.subTest(value=repr(value)):
                with self.assertRaises(CodePageContractError):
                    encode_bounded(value, 65001, 8)

    def test_unsupported_codepage_is_refused(self):
        with self.assertRaises(UnsupportedCodePage):
            encode_bounded('A', 1255, 8)


class DecodeBoundedTests(unittest.TestCase):
    def test_full_decode_of_pinned_fixture_bytes(self):
        for codepage, entries in CODEPAGE_FIXTURES.items():
            for label, text, expected in entries:
                with self.subTest(codepage=codepage, label=label):
                    self.assertEqual(
                        decode_bounded(bytes.fromhex(expected), codepage,
                                       len(expected) // 2),
                        text)

    def test_prefix_decode_at_codepoint_start(self):
        for case in BOUNDED_DECODE_CASES:
            codepage, blob_hex, max_bytes, expected = case
            if expected is not None and max_bytes < len(blob_hex) // 2:
                with self.subTest(codepage=codepage, max_bytes=max_bytes):
                    self.assertEqual(
                        decode_bounded(bytes.fromhex(blob_hex), codepage,
                                       max_bytes),
                        expected)

    def test_exact_boundary_decode(self):
        blob = bytes.fromhex('41c3a9f09f9982')
        self.assertEqual(decode_bounded(blob, 65001, 7), 'A\u00e9\U0001f642')
        self.assertEqual(decode_bounded(blob, 65001, 3), 'A\u00e9')
        # Byte 4 is the first byte of the 4-byte emoji: cutting there is not
        # an exact codepoint boundary.
        with self.assertRaises(IncompleteSequence):
            decode_bounded(blob, 65001, 4)

    def test_bound_above_span_decodes_full_blob(self):
        blob = bytes.fromhex('cff0e8e2e5f2')
        self.assertEqual(decode_bounded(blob, 1251, 10**6),
                         '\u041f\u0440\u0438\u0432\u0435\u0442')

    def test_truncated_tail_is_an_incomplete_sequence(self):
        for case in BOUNDED_DECODE_CASES:
            codepage, blob_hex, max_bytes, expected = case
            if expected is None:
                with self.subTest(codepage=codepage, blob_hex=blob_hex):
                    with self.assertRaises(IncompleteSequence):
                        decode_bounded(bytes.fromhex(blob_hex), codepage,
                                       max_bytes)

    def test_undefined_cp1252_byte_is_refused(self):
        for undefined in (0x81, 0x8D, 0x8F, 0x90, 0x9D):
            with self.subTest(byte=hex(undefined)):
                with self.assertRaises(IncompleteSequence):
                    decode_bounded(bytes([undefined]), 1252, 1)

    def test_undefined_byte_in_the_zero_alias_is_refused(self):
        with self.assertRaises(IncompleteSequence):
            decode_bounded(b'\x81', 0, 1)

    def test_empty_blob_is_empty_text(self):
        for codepage in PINNED:
            with self.subTest(codepage=codepage):
                self.assertEqual(decode_bounded(b'', codepage, 8), '')

    def test_invalid_blob_or_bound_is_refused(self):
        with self.assertRaises(CodePageContractError):
            decode_bounded('abc', 1252, 8)
        with self.assertRaises(CodePageContractError):
            decode_bounded(bytearray(b'ab'), 1252, 8)
        for value in (-1, True, 2.0, None):
            with self.subTest(max_bytes=repr(value)):
                with self.assertRaises(CodePageContractError):
                    decode_bounded(b'ab', 1252, value)

    def test_unsupported_codepage_is_refused(self):
        with self.assertRaises(UnsupportedCodePage):
            decode_bounded(b'\x80', 1255, 1)


class RoundtripTests(unittest.TestCase):
    def test_roundtrip_every_fixture_text_per_codepage(self):
        for codepage, entries in CODEPAGE_FIXTURES.items():
            for label, text, expected in entries:
                with self.subTest(codepage=codepage, label=label):
                    raw = encode_bounded(text, codepage, 4096)
                    self.assertEqual(raw, bytes.fromhex(expected))
                    self.assertEqual(
                        decode_bounded(raw, codepage, len(raw)), text)

    def test_roundtrip_zero_alias_matches_1252(self):
        for text in ('abc', 'Äöüß', '\u201e\u2026\u201d'):
            with self.subTest(text=text):
                raw = encode_bounded(text, 0, 64)
                self.assertEqual(
                    decode_bounded(raw, 0, len(raw)),
                    decode_bounded(raw, 1252, len(raw)))

    def test_lone_surrogates_have_no_roundtrip(self):
        for codepage in PINNED:
            with self.subTest(codepage=codepage):
                with self.assertRaises(IncompleteSequence):
                    encode_bounded('\ud800', codepage, 8)
                self.assertFalse(is_lossless('\ud800', codepage))

    def test_roundtrip_is_deterministic_across_calls(self):
        text = 'Café € 🙂 \u041f\u0440\u0438\u0432\u0435\u0442'
        raws = {encode_bounded(text, 65001, 512) for _ in range(5)}
        self.assertEqual(len(raws), 1)
        self.assertEqual(encoded_length(text, 65001),
                         len(next(iter(raws))))


class LosslessPredicateTests(unittest.TestCase):
    def test_native_fixture_texts_are_lossless(self):
        for codepage, entries in CODEPAGE_FIXTURES.items():
            for label, text, _ in entries:
                with self.subTest(codepage=codepage, label=label):
                    self.assertTrue(is_lossless(text, codepage))

    def test_cross_codepage_texts_are_lossy(self):
        for text, codepage in LOSSY_CASES:
            with self.subTest(text=repr(text), codepage=codepage):
                self.assertFalse(is_lossless(text, codepage))

    def test_cyrillic_text_under_1252_is_lossy(self):
        self.assertFalse(is_lossless('Привет', 1252))
        self.assertTrue(is_lossless('Привет', 1251))

    def test_turkish_text_under_1252_is_lossy(self):
        self.assertFalse(is_lossless('İğüş', 1252))
        self.assertTrue(is_lossless('İğüş', 1254))

    def test_lossless_agrees_with_roundtrip_invariant(self):
        samples = (
            'abc', 'Äöü', 'é', '€', '🙂', '\u0130\u011f', '\u010d\u0160',
            '\u041f\u0440\u0438', '\u0395\u03bb\u03bb\u03ac',
            '\ud800', '',
        )
        for text in samples:
            for codepage in PINNED:
                with self.subTest(text=repr(text), codepage=codepage):
                    try:
                        raw = encode_bounded(text, codepage, 4096)
                        roundtrip = (
                            decode_bounded(raw, codepage, len(raw)) == text)
                    except CodePageContractError:
                        roundtrip = False
                    self.assertEqual(is_lossless(text, codepage), roundtrip)

    def test_lossless_still_refuses_unsupported_codepage(self):
        for value in UNSUPPORTED_CODEPAGES:
            with self.subTest(codepage=value):
                with self.assertRaises(UnsupportedCodePage):
                    is_lossless('a', value)

    def test_lossless_refuses_non_str_text(self):
        for value in (None, 7, b'abc'):
            with self.subTest(value=repr(value)):
                with self.assertRaises(CodePageContractError):
                    is_lossless(value, 1252)


if __name__ == '__main__':
    unittest.main()
