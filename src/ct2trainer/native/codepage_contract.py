"""Pinned CodePage contract for bounded CT String writes.

This module is a pure function layer that pins, once and deterministically,
the encoding contract the Native string verification will rely on.  It
installs no runtime/engine profile and reads no CE implementation input;
the table below is derived from the public ``MemoryRecord.CodePage``
metadata semantics only:

    0     ANSI default = Windows-1252 alias (identical to plain ASCII in
          the ASCII range, fully cp1252 otherwise)
    1250  cp1250  (Central European)
    1251  cp1251  (Cyrillic)
    1252  cp1252  (Western)
    1253  cp1253  (Greek)
    1254  cp1254  (Turkish)
    1257  cp1257  (Baltic)
    65001 UTF-8   (code unit = byte)

Every other CodePage value is refused fail-closed: there is no implicit
default translation.  Only the Python standard-library codecs are used.

Byte-length contract:
    encoded_length(text, codepage)
        exact encoded byte length of the literal alone (no implicit NUL
        extension); unrepresentable text raises IncompleteSequence with
        the first offending codepoint and its position.
    encode_bounded(text, codepage, max_bytes)
        the full encoding when it already fits in max_bytes, exactly
        max_bytes bytes when the clip lands on a codepoint boundary, or
        TruncationRefused when the clip would split a multi-byte codepoint
        (splitting is a clear pinned error, never a silent truncation).
    decode_bounded(blob, codepage, max_bytes)
        decodes min(len(blob), max_bytes) bytes; a bounded tail that is an
        unfinished multi-byte sequence (or an undefined byte in the
        pinned single-byte codec) raises IncompleteSequence.
    is_lossless(text, codepage)
        True iff decode(encode(text, cp), cp) == text.
"""


class CodePageContractError(ValueError):
    """Base error for the pinned CodePage contract."""


class UnsupportedCodePage(CodePageContractError):
    """CodePage value is not in the pinned table (fail-closed)."""


class IncompleteSequence(CodePageContractError):
    """A byte or text sequence is incomplete for the pinned codec."""


class TruncationRefused(CodePageContractError):
    """A bounded write would split a multi-byte codepoint."""


_CODECPAGE_CODECS = {
    0: 'cp1252',
    1250: 'cp1250',
    1251: 'cp1251',
    1252: 'cp1252',
    1253: 'cp1253',
    1254: 'cp1254',
    1257: 'cp1257',
    65001: 'utf-8',
}

_CODECPAGE_NAMES = {
    0: 'ANSI default (Windows-1252 alias)',
    1250: 'Windows-1250 (Central European)',
    1251: 'Windows-1251 (Cyrillic)',
    1252: 'Windows-1252 (Western)',
    1253: 'Windows-1253 (Greek)',
    1254: 'Windows-1254 (Turkish)',
    1257: 'Windows-1257 (Baltic)',
    65001: 'UTF-8',
}


def _check_codepage(codepage):
    """Return the pinned stdlib codec name for a supported CodePage value."""
    if type(codepage) is not int:
        raise UnsupportedCodePage(
            'CodePage must be an exact integer, got ' + type(codepage).__name__)
    if codepage not in _CODECPAGE_CODECS:
        raise UnsupportedCodePage(
            'CodePage %d is not in the pinned table %r' % (
                codepage, tuple(sorted(_CODECPAGE_CODECS))))
    return _CODECPAGE_CODECS[codepage]


def _check_text(text):
    if type(text) is not str:
        raise CodePageContractError(
            'text must be str, got ' + type(text).__name__)


def _check_blob(blob):
    if type(blob) is not bytes:
        raise CodePageContractError(
            'blob must be bytes, got ' + type(blob).__name__)


def _check_bound(max_bytes):
    if type(max_bytes) is not int or max_bytes < 0:
        raise CodePageContractError(
            'max_bytes must be a non-negative integer')


def _encode(text, codec, codepage):
    try:
        return text.encode(codec, 'strict')
    except UnicodeEncodeError as error:
        raise IncompleteSequence(
            'text is not representable in the pinned %s codec for CodePage %d '
            '(U+%04X at position %d)' % (
                _CODECPAGE_NAMES[codepage], codepage,
                ord(text[error.start]), error.start)) from error


def supported_codepages():
    """The pinned, deterministic CodePage table, ascending."""
    return tuple(sorted(_CODECPAGE_CODECS))


def codepage_name(codepage):
    """Human-readable pinned name for a supported CodePage value."""
    if type(codepage) is not int or codepage not in _CODECPAGE_CODECS:
        raise UnsupportedCodePage(
            'CodePage %r is not in the pinned table' % (codepage,))
    return _CODECPAGE_NAMES[codepage]


def codec_for(codepage):
    """Return the stdlib codec name pinned for a supported CodePage value."""
    return _check_codepage(codepage)


def encoded_length(text, codepage):
    """Exact encoded byte length of the literal alone.

    No implicit NUL extension and no error-crash: unrepresentable text
    raises IncompleteSequence naming the first offending codepoint.
    """
    _check_codepage(codepage)
    _check_text(text)
    return len(_encode(text, _check_codepage(codepage), codepage))


def encode_bounded(text, codepage, max_bytes):
    """Encode for a bounded write without ever splitting a codepoint.

    Returns the full encoding when it fits in max_bytes, exactly
    max_bytes bytes when the clip lands on a codepoint boundary, and
    TruncationRefused when the clip would split a multi-byte codepoint.
    The result is never padded with implicit NUL bytes.
    """
    _check_codepage(codepage)
    _check_bound(max_bytes)
    _check_text(text)
    codec = codec_for(codepage)
    full = _encode(text, codec, codepage)
    if len(full) <= max_bytes:
        return full
    try:
        full[:max_bytes].decode(codec, 'strict')
    except UnicodeDecodeError:
        raise TruncationRefused(
            'clipping at byte %d would split a multi-byte codepoint of the '
            'pinned %s codec for CodePage %d' % (max_bytes, codec, codepage))
    return full[:max_bytes]


def decode_bounded(blob, codepage, max_bytes):
    """Decode at most max_bytes of a bounded byte span.

    The span is min(len(blob), max_bytes) bytes.  A bounded tail that is an
    unfinished multi-byte sequence, or an undefined byte of the pinned
    single-byte codec, raises IncompleteSequence.
    """
    _check_codepage(codepage)
    _check_bound(max_bytes)
    _check_blob(blob)
    codec = codec_for(codepage)
    take = min(len(blob), max_bytes)
    try:
        return blob[:take].decode(codec, 'strict')
    except UnicodeDecodeError as error:
        raise IncompleteSequence(
            'bounded %s span ends in an incomplete or undefined sequence at '
            'byte offset %d of %d bytes' % (codec, error.start, take)) from error


def is_lossless(text, codepage):
    """True iff the text round-trips decode(encode(text, cp), cp) == text."""
    _check_codepage(codepage)
    _check_text(text)
    codec = codec_for(codepage)
    try:
        raw = text.encode(codec, 'strict')
    except UnicodeEncodeError:
        return False
    return raw.decode(codec, 'strict') == text
