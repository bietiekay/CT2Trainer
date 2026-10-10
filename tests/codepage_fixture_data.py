# -*- coding: utf-8 -*-
"""Hand-verified byte expectations for the pinned CodePage contract.

No TableReferences, no CE inputs.  Every expected byte string is a literal
verified once against the stdlib codecs (the pinned IANA/Microsoft tables),
never recomputed at test time as the expectation itself.
"""

# codepage -> list of (label, text, expected_bytes_hex)
CODEPAGE_FIXTURES = {
    0: [
        ('ansi-alias-euro', '\u20ac', '80'),
        ('ansi-alias-western-umlauts', '\u00c4\u00f6\u00fc', 'c4f6fc'),
        ('ansi-alias-german-ss', '\u00df', 'df'),
        ('ansi-alias-quotes-ellipsis', '\u201e\u2026\u201d', '848594'),
    ],
    1250: [
        ('cafe-with-acute', 'Caf\u00e9', '436166e9'),
        ('scarred-s', '\u0161', '9a'),
        ('ogonek-run', '\u015a\u0142\u017a', '8cb39f'),
        ('caron-run', '\u017d\u0107', '8ee6'),
    ],
    1251: [
        ('cyrillic-greeting', '\u041f\u0440\u0438\u0432\u0435\u0442', 'cff0e8e2e5f2'),
        ('yo-pair', '\u0451\u0401', 'b8a8'),
    ],
    1252: [
        ('western-umlauts', '\u00c4\u00f6\u00fc', 'c4f6fc'),
        ('euro-sign', '\u20ac', '80'),
        ('typographic-run', '\u201e\u2026\u201d', '848594'),
        ('german-ss', '\u00df', 'df'),
    ],
    1253: [
        ('greek-country', '\u0395\u03bb\u03bb\u03ac\u03b4\u03b1', 'c5ebebdce4e1'),
        ('greek-omega', '\u03a9', 'd9'),
    ],
    1254: [
        ('turkish-run', '\u0130\u011f\u00fc\u015f', 'ddf0fcfe'),
        ('dotless-i', '\u0131', 'fd'),
    ],
    1257: [
        ('baltic-run', '\u010d\u0160\u0105', 'e8d0e0'),
        ('k-ce-caron', '\u0136', 'cd'),
    ],
    65001: [
        ('ascii', 'A', '41'),
        ('two-byte', '\u00e9', 'c3a9'),
        ('three-byte', '\u20ac', 'e282ac'),
        ('four-byte', '\U0001f642', 'f09f9982'),
        ('mixed-run', 'A\u00e9\U0001f642', '41c3a9f09f9982'),
    ],
}

# (text, codepage) pairs that are NOT representable in the target codec.
LOSSY_CASES = [
    ('\u041f\u0440\u0438\u0432\u0435\u0442', 1252),    # Cyrillic in Western
    ('Caf\u00e9', 1251),                                # Latin in Cyrillic
    ('\u0395\u03bb\u03bb\u03ac\u03b4\u03b1', 1250),     # Greek in CE
    ('\u0130\u011f\u00fc\u015f', 1252),                 # Turkish in Western
    ('\U0001f642', 0),                                  # emoji in ANSI alias
    ('\ud800', 65001),                                  # lone surrogate in UTF-8
    ('\ud800', 1252),                                   # lone surrogate in Western
]

# (codepage, text, max_bytes, expected_hex_or_None)
# None means TruncationRefused is expected.
BOUNDED_ENCODE_CASES = [
    (0, '\u00c4\u00f6\u00fc\u20ac\u00df', 5, 'c4f6fc80df'),
    (1252, '\u00c4\u00f6\u00fc\u20ac\u00df', 3, 'c4f6fc'),
    (65001, '\U0001f642A', 4, 'f09f9982'),
    (65001, '\U0001f642A', 5, 'f09f998241'),
    (65001, 'A\u00e9\U0001f642', 3, '41c3a9'),
    (65001, 'A\u00e9\U0001f642', 2, None),
    (65001, 'A\u00e9\U0001f642', 4, None),
    (65001, 'A\u00e9\U0001f642', 5, None),
    (65001, 'A\u00e9\U0001f642', 6, None),
    (65001, '', 0, ''),
    (65001, '\U0001f642', 0, ''),
    (1250, 'Caf\u00e9', 3, '436166'),
    (1257, '\u010d\u0160\u0105', 2, 'e8d0'),
]

# (codepage, blob_hex, max_bytes, expected_text_or_None)
# None means IncompleteSequence is expected.
BOUNDED_DECODE_CASES = [
    (65001, '41c3a9f09f9982', 3, 'A\u00e9'),
    (65001, '41c3a9f09f9982', 7, 'A\u00e9\U0001f642'),
    (65001, '41c3a9f09f9982', 16, 'A\u00e9\U0001f642'),
    (65001, '41c3a9f09f9982', 5, None),
    (65001, 'f09f99', 3, None),
    (65001, 'e282', 2, None),
    (65001, 'c3', 1, None),
    (0, '80', 1, '\u20ac'),
    (0, '8485', 1, '\u201e'),
    (0, '81', 1, None),
    (1251, 'cff0e8e2e5f2', 5, '\u041f\u0440\u0438\u0432\u0435'),
    (1253, 'c5ebebdce4e1', 6, '\u0395\u03bb\u03bb\u03ac\u03b4\u03b1'),
]

# Integers that are NOT in the pinned table.
UNSUPPORTED_CODEPAGES = (
    1, 2, 437, 720, 850, 852, 858, 932,
    1255, 1256, 1258, 20127, 65000, 65002, 65003,
    -1, 0xFFFF,
)

# Non-integer values that must be rejected.
NON_INTEGER_CODEPAGES = (True, False, 1252.0, '1252', None, b'1252')
