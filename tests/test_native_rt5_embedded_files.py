"""RT-5 item A: embedded <Files> extraction and the Lua surface contract.

Covers, for independently authored synthetic fixtures (no corpus files are
loaded; the fixtures reproduce the corpus usage shapes):

- the CE-alphabet Ascii85 codec: roundtrip over every tail length,
  whitespace tolerance, and the exact named decode refusals (empty text,
  out-of-alphabet character, single trailing character, truncated
  deflate, payload shorter than the size prefix, size-prefix/payload
  mismatch, and the 4 MiB per-file size-prefix bound);
- the CE hex branch (Encoding attribute missing or not exactly
  ``Ascii85``): hex text -> raw deflate, read until EOF, no size prefix -
  roundtrip plus the exact named refusals (odd character count, non-hex
  character, invalid deflate, content over the 4 MiB per-file bound);
- the fail-closed table-load contract: a malformed <Files> entry aborts
  the table load with its named TableError (empty child, over the 64-file
  or 16 MiB total bounds; the hex branch is loadable, malformed hex is
  refused; duplicate names are tolerated, matching the CE table load);
- the plan projection: casefold-sorted entries with the derived
  metadata, the absent key when a table carries no files, and both plan
  validators re-deriving hash and size from the stored text (forged
  metadata, the 16 MiB plan-level total bound, and a schema-1 plan are
  refused);
- the runtime contract end to end: the P5 table-Lua shape
  (findTableFile -> readStringLocal -> load -> define, table globals
  consumed by a record, byte-exact write and disable restore), the
  RiftApart record shape (tFileList iteration -> createStringStream ->
  copyFrom -> stringlist.Text -> loadstring), readStringLocal maxsize
  semantics (omitted or negative maxsize returns the full content and
  there is no NUL truncation - the documented deviation from CE
  readStringEx), case-sensitive first-match duplicate resolution, and
  the named runtime refusals with zero memory writes.
"""
from copy import deepcopy
from hashlib import sha256
import tempfile
import unittest
from pathlib import Path
import xml.sax.saxutils
import zlib

from test_native_engine import FakeMemory
from test_native_engine_code import Coordinator
from ct2trainer.native.compiler import NativeCompileError, compile_table, validate_plan
from ct2trainer.native.engine import (NativeRuntimeError, TrainerEngine,
                                      validate_plan as validate_runtime_plan)
from ct2trainer.native.embedded_files import (CE_BASE85_ALPHABET,
                                              EmbeddedFileError,
                                              decode_ascii85,
                                              decode_embedded_file,
                                              validate_embedded_files)
from ct2trainer.native.lua_host import LuaHostError, TableLuaBroker
from ct2trainer.table import TableError, read_table


PROCESS = "FixtureTarget.exe"


def _base85_block(value: int) -> str:
    digits = []
    for _ in range(5):
        value, r = divmod(value, 85)
        digits.append(CE_BASE85_ALPHABET[r])
    return "".join(reversed(digits))


def _encode_raw_base85(data: bytes) -> str:
    """CE-alphabet Ascii85 over an arbitrary byte string (fixture tool).

    A short final block is padded with the decoder's value-84 padding so
    the dropped digits are exactly the pad's digits.
    """
    out = []
    i, n = 0, len(data)
    while i + 4 <= n:
        out.append(_base85_block(int.from_bytes(data[i:i + 4], "big")))
        i += 4
    rem = n - i
    if rem:
        pad = 4 - rem
        value = int.from_bytes(data[i:i + rem] + (85 ** pad - 1).to_bytes(pad, "big"),
                               "big")
        out.append(_base85_block(value)[:5 - pad])
    return "".join(out)


def _raw_deflate(payload: bytes) -> bytes:
    return zlib.compress(payload, 9)[2:-4]


def _embed_file_text(content: bytes) -> str:
    """Raw stored text of one embedded file: CE-alphabet Ascii85 over the
    raw-deflate stream of the 4-byte little-endian size prefix plus the
    content (the corpus format, verified byte-exact on the reference
    tables)."""
    payload = len(content).to_bytes(4, "little") + content
    return _encode_raw_base85(_raw_deflate(payload))


def _hex_embed_text(content: bytes) -> str:
    """Raw stored text of a CE hex-branch embedded file: hex digits of the
    raw-deflate stream of the content alone (no size prefix, read until
    EOF)."""
    return _raw_deflate(content).hex()


def escape(text: str) -> str:
    return xml.sax.saxutils.escape(text)


def value_record(entry_id: int, address: str = "1000") -> str:
    return (f'<CheatEntry><ID>{entry_id}</ID><Description>Value {entry_id}</Description>'
            f'<VariableType>4 Bytes</VariableType><Address>{address}</Address></CheatEntry>')


def lua_record(entry_id: int, script: str) -> str:
    return (f'<CheatEntry><ID>{entry_id}</ID><Description>"Record {entry_id}"</Description>'
            f'<VariableType>Auto Assembler Script</VariableType>'
            f'<AssemblerScript>{escape(script)}</AssemblerScript></CheatEntry>')


def table_xml(body: str, lua_script: str = "", files: str = "") -> str:
    return ('<CheatTable CheatEngineTableVersion="45"><LuaScript>'
            + lua_script + '</LuaScript><CheatEntries>' + body
            + '</CheatEntries>' + files + '</CheatTable>')


def files_section(*entries: tuple[str, str]) -> str:
    """A <Files> section from (name, encoded-text) pairs (Ascii85)."""
    inner = "".join(
        f'<{name} Encoding="Ascii85">{escape(text)}</{name}>\n'
        for name, text in entries)
    return f'<Files>\n{inner}</Files>\n'


def enable_lua_record(entry_id: int, enable_lua: str,
                      disable_lua: str = "") -> str:
    """An AA record whose enable phase is one Lua chunk (the corpus shape);
    the disable phase may stay empty."""
    enable = "[ENABLE]\n{$lua}\n" + enable_lua + "\n{$asm}\n"
    disable = ("[DISABLE]\n{$lua}\n" + disable_lua + "\n{$asm}\n"
               if disable_lua else "[DISABLE]\n{$asm}\n")
    return lua_record(entry_id, enable + disable)


class Memory(FakeMemory):
    @property
    def identity(self):
        return self.pid, self.creation_time

    def _range(self, address, size):
        if not self.base <= address or address + size > self.base + len(self.data):
            raise ValueError('Outside owned fixture memory')

    def is_executable(self, address, size):
        return False


# ---------------------------------------------------------------------------
# Codec
# ---------------------------------------------------------------------------

class EmbeddedFileCodecTests(unittest.TestCase):
    """The CE-alphabet Ascii85 + raw-deflate + size-prefix pipeline."""

    def test_roundtrip_all_tail_lengths(self):
        for size in list(range(1, 40)) + [100, 1000, 4096, 5000]:
            content = bytes((i * 31 + 7) % 256 for i in range(size))
            self.assertEqual(decode_embedded_file(_embed_file_text(content)),
                             content, f"size {size}")

    def test_roundtrip_binary_and_utf8_content(self):
        content = "h\u00e9llo\nworld\0tail".encode("utf-8") + b"\x00\xff\xfe"
        self.assertEqual(decode_embedded_file(_embed_file_text(content)), content)

    def test_whitespace_in_stored_text_is_tolerated(self):
        content = b"whitespace tolerance fixture"
        text = _embed_file_text(content)
        spaced = "\n".join(text[i:i + 7] for i in range(0, len(text), 7)) + "  \n"
        self.assertEqual(decode_embedded_file(spaced), content)

    def test_empty_text_is_refused(self):
        with self.assertRaises(EmbeddedFileError) as ctx:
            decode_ascii85("")
        self.assertEqual(str(ctx.exception), "Embedded file text is empty.")

    def test_single_trailing_character_is_refused(self):
        text = _encode_raw_base85(bytes(12))  # 15 characters
        with self.assertRaises(EmbeddedFileError) as ctx:
            decode_ascii85(text[:6])
        self.assertIn("single character", str(ctx.exception))

    def test_out_of_alphabet_character_is_refused(self):
        text = _embed_file_text(b"abcdef")
        with self.assertRaises(EmbeddedFileError) as ctx:
            decode_embedded_file('"' + text[1:])
        self.assertIn("outside the CE alphabet", str(ctx.exception))

    def test_truncated_deflate_is_refused(self):
        payload = len(b"xy").to_bytes(4, "little") + b"xy"
        raw = _raw_deflate(payload)[:-1]
        with self.assertRaises(EmbeddedFileError) as ctx:
            decode_embedded_file(_encode_raw_base85(raw))
        self.assertIn("not a valid raw-deflate stream", str(ctx.exception))

    def test_payload_shorter_than_prefix_is_refused(self):
        with self.assertRaises(EmbeddedFileError) as ctx:
            decode_embedded_file(_encode_raw_base85(_raw_deflate(b"ab")))
        self.assertEqual(str(ctx.exception),
                         "Embedded file payload is shorter than the "
                         "4-byte size prefix.")

    def test_size_prefix_mismatch_is_refused(self):
        content = b"payload"
        payload = (len(content) + 3).to_bytes(4, "little") + content
        with self.assertRaises(EmbeddedFileError) as ctx:
            decode_embedded_file(_encode_raw_base85(_raw_deflate(payload)))
        self.assertIn("does not match the payload length", str(ctx.exception))

    def test_size_prefix_over_bound_is_refused(self):
        # Per-file transport-tracking bound: one readStringLocal must be
        # able to return the whole file (4 MiB per-call limit).
        big = (4 * 1024 * 1024 + 1).to_bytes(4, "little")
        with self.assertRaises(EmbeddedFileError) as ctx:
            decode_embedded_file(_encode_raw_base85(_raw_deflate(big)))
        self.assertEqual(str(ctx.exception),
                         "Embedded file size prefix exceeds the 4 MiB bound.")


# ---------------------------------------------------------------------------
# Codec: CE hex branch
# ---------------------------------------------------------------------------

class EmbeddedFileHexBranchTests(unittest.TestCase):
    """Encoding attribute missing or not exactly 'Ascii85' -> hex branch."""

    def test_roundtrip_lowercase_and_uppercase_hex(self):
        content = "hex branch roundtrip \u00fcmlaut".encode("utf-8")
        self.assertEqual(decode_embedded_file(_hex_embed_text(content), ""),
                         content)
        self.assertEqual(decode_embedded_file(_hex_embed_text(content).upper(), "Hex"),
                         content)

    def test_odd_character_count_is_refused(self):
        with self.assertRaises(EmbeddedFileError) as ctx:
            decode_embedded_file(_hex_embed_text(b"abc")[:-1], "Hex")
        self.assertEqual(str(ctx.exception),
                         "Embedded file hex text has an odd character count.")

    def test_non_hex_character_is_refused(self):
        text = _hex_embed_text(b"abc")
        with self.assertRaises(EmbeddedFileError) as ctx:
            decode_embedded_file("zz" + text[2:], "Hex")
        self.assertEqual(str(ctx.exception),
                         "Embedded file hex text contains non-hex character 'z'.")

    def test_invalid_deflate_is_refused(self):
        with self.assertRaises(EmbeddedFileError) as ctx:
            decode_embedded_file(b"\x01\x02\x03\x04".hex(), "")
        self.assertIn("not a valid raw-deflate stream", str(ctx.exception))

    def test_content_over_per_file_bound_is_refused(self):
        content = b"A" * (4 * 1024 * 1024 + 1)
        with self.assertRaises(EmbeddedFileError) as ctx:
            decode_embedded_file(_hex_embed_text(content), "Hex")
        self.assertEqual(str(ctx.exception),
                         "Embedded file content exceeds the 4 MiB bound.")

# ---------------------------------------------------------------------------
# Plan-level validation of embedded_files
# ---------------------------------------------------------------------------

class ValidateEmbeddedFilesTests(unittest.TestCase):
    """validate_embedded_files re-derives hash and size from the text."""

    def _valid(self, content=b"alpha", name="a.txt", **overrides):
        entry = {"name": name, "encoding": "Ascii85",
                 "text": _embed_file_text(content),
                 "sha256": sha256(content).hexdigest(),
                 "size": len(content)}
        entry.update(overrides)
        return entry

    def test_valid_entries_are_accepted(self):
        entries = [self._valid(b"alpha"), self._valid(b"beta", "B.txt")]
        self.assertIs(validate_embedded_files(entries), entries)

    def test_hex_encoding_entries_are_accepted(self):
        # Any encoding other than exactly 'Ascii85' takes the CE hex branch;
        # the plan level accepts it the same way table load does.
        hex_entry = self._valid(b"hex content", "h.bin", encoding="Hex",
                                text=_hex_embed_text(b"hex content"))
        missing = self._valid(b"plain content", "m.bin", encoding="",
                              text=_hex_embed_text(b"plain content"))
        self.assertEqual(validate_embedded_files([hex_entry, missing]),
                         [hex_entry, missing])

    def test_forged_hash_is_refused(self):
        entry = self._valid(sha256="0" * 64)
        with self.assertRaises(EmbeddedFileError) as ctx:
            validate_embedded_files([entry])
        self.assertIn("content does not match its stored hash", str(ctx.exception))

    def test_forged_size_is_refused(self):
        entry = self._valid(size=len(b"alpha") + 1)
        with self.assertRaises(EmbeddedFileError) as ctx:
            validate_embedded_files([entry])
        self.assertIn("size does not match its stored content", str(ctx.exception))

    def test_shape_violations_are_refused(self):
        entry = self._valid()
        for name, entry in (("missing key", {k: v for k, v in entry.items()
                                             if k != "size"}),
                            ("extra key", dict(entry, note="x"))):
            with self.subTest(name=name):
                with self.assertRaises(EmbeddedFileError) as ctx:
                    validate_embedded_files([entry])
                self.assertIn("Invalid embedded file entry shape", str(ctx.exception))

    def test_duplicate_names_are_tolerated_casefold(self):
        # CE loads duplicate embedded-file names; the runtime registry keeps
        # the first occurrence (engine seeds with setdefault).
        entries = [self._valid(b"a", "A.TXT"), self._valid(b"b", "a.txt")]
        self.assertEqual(validate_embedded_files(entries), entries)

    def test_too_many_files_are_refused(self):
        entries = [self._valid(b"x", f"f{i:02d}.txt") for i in range(65)]
        with self.assertRaises(EmbeddedFileError) as ctx:
            validate_embedded_files(entries)
        self.assertIn("More than 64 embedded files", str(ctx.exception))

    def test_total_size_bound_refused(self):
        # Plan-level total bound (table load caps earlier per file; forged
        # plan entries can still exceed the table total): 5 x 3.5 MiB.
        entries = [self._valid(b"A" * 3_500_000, f"f{i}.bin") for i in range(5)]
        with self.assertRaises(EmbeddedFileError) as ctx:
            validate_embedded_files(entries)
        self.assertIn("Embedded files exceed their 16 MiB total bound",
                      str(ctx.exception))

    def test_invalid_sha256_format_is_refused(self):
        entry = self._valid(sha256="xyz")
        with self.assertRaises(EmbeddedFileError) as ctx:
            validate_embedded_files([entry])
        self.assertIn("carries an invalid sha256", str(ctx.exception))

    def test_non_integer_size_is_refused(self):
        # bool is an int subclass but not the accepted shape.
        entry = self._valid(size=True)
        with self.assertRaises(EmbeddedFileError) as ctx:
            validate_embedded_files([entry])
        self.assertIn("carries an invalid size", str(ctx.exception))

    def test_empty_text_is_refused(self):
        entry = self._valid(text="")
        with self.assertRaises(EmbeddedFileError) as ctx:
            validate_embedded_files([entry])
        self.assertIn("text must be non-empty", str(ctx.exception))

    def test_oversized_name_is_refused(self):
        entry = self._valid(name="x" * 256)
        with self.assertRaises(EmbeddedFileError) as ctx:
            validate_embedded_files([entry])
        self.assertIn("Invalid embedded file name", str(ctx.exception))

    def test_non_list_is_refused(self):
        with self.assertRaises(EmbeddedFileError) as ctx:
            validate_embedded_files(self._valid())
        self.assertIn("embedded_files must be a list", str(ctx.exception))


# ---------------------------------------------------------------------------
# Table-load contract
# ---------------------------------------------------------------------------

class EmbeddedFilesTableLoadTests(unittest.TestCase):
    """A malformed <Files> entry aborts the table load with a named error."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def write_ct(self, name: str, files_inner: str) -> Path:
        path = self.root / name
        path.write_text(
            '<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
            + value_record(0) + "</CheatEntries>"
            + files_inner + "</CheatTable>", encoding="utf-8")
        return path

    def test_valid_files_section_loads_with_derived_metadata(self):
        path = self.write_ct(
            "ok.ct",
            '<Files><a.bin Encoding="Ascii85">'
            + _embed_file_text(b"abc")
            + "</a.bin></Files>")
        table = read_table(str(path))
        self.assertEqual([f.name for f in table.embedded_files], ["a.bin"])
        entry = table.embedded_files[0]
        self.assertEqual(entry.encoding, "Ascii85")
        self.assertEqual(entry.sha256, sha256(b"abc").hexdigest())
        self.assertEqual(entry.size, 3)
        self.assertEqual(decode_embedded_file(entry.text), b"abc")
        # The presentation dict mirrors only the derived metadata.
        projected = table.to_dict()["embedded_files"]
        self.assertEqual(projected, [{"name": "a.bin", "encoding": "Ascii85",
                                      "sha256": sha256(b"abc").hexdigest(),
                                      "size": 3}])

    def test_missing_encoding_uses_the_hex_branch(self):
        # CE createFromXML: no Encoding attribute -> hex read-until-EOF
        # branch (no size prefix). The entry loads and keeps encoding "".
        path = self.write_ct(
            "hex.ct",
            "<Files><x.bin>" + _hex_embed_text(b"hex branch")
            + "</x.bin></Files>")
        table = read_table(str(path))
        entry = table.embedded_files[0]
        self.assertEqual(entry.encoding, "")
        self.assertEqual(entry.size, len(b"hex branch"))
        self.assertEqual(entry.sha256, sha256(b"hex branch").hexdigest())
        self.assertEqual(decode_embedded_file(entry.text, entry.encoding),
                         b"hex branch")

    def test_unknown_encoding_uses_the_hex_branch(self):
        # Any Encoding value other than exactly 'Ascii85' (e.g. 'Hex')
        # takes the hex branch, mirroring CE.
        path = self.write_ct(
            "hex2.ct",
            '<Files><x.bin Encoding="Hex">'
            + _hex_embed_text(b"hex branch two")
            + "</x.bin></Files>")
        table = read_table(str(path))
        entry = table.embedded_files[0]
        self.assertEqual(entry.encoding, "Hex")
        self.assertEqual(decode_embedded_file(entry.text, entry.encoding),
                         b"hex branch two")

    def test_hex_odd_char_count_refuses_the_table_load(self):
        odd = _hex_embed_text(b"abc")[:-1]
        path = self.write_ct(
            "badhex.ct", f'<Files><x.bin Encoding="Hex">{odd}</x.bin></Files>')
        with self.assertRaises(TableError) as ctx:
            read_table(str(path))
        self.assertIn(
            "Embedded file 'x.bin' cannot be decoded: Embedded file hex text "
            "has an odd character count.", str(ctx.exception))

    def test_hex_non_hex_char_refuses_the_table_load(self):
        bad = "zz" + _hex_embed_text(b"abc")[2:]
        path = self.write_ct(
            "badhex2.ct",
            f'<Files><x.bin Encoding="Hex">{bad}</x.bin></Files>')
        with self.assertRaises(TableError) as ctx:
            read_table(str(path))
        self.assertIn(
            "Embedded file 'x.bin' cannot be decoded: Embedded file hex text "
            "contains non-hex character 'z'.", str(ctx.exception))

    def test_undecodable_payload_refuses_the_table_load(self):
        bad = _encode_raw_base85(b"\x01\x02\x03\x04\x05")  # not deflate
        path = self.write_ct(
            "bad.ct", f'<Files><x.bin Encoding="Ascii85">{bad}</x.bin></Files>')
        with self.assertRaises(TableError) as ctx:
            read_table(str(path))
        self.assertIn("Embedded file 'x.bin' cannot be decoded",
                      str(ctx.exception))

    def test_duplicate_names_are_tolerated_casefold(self):
        # CE loads duplicate embedded-file names; document order is kept and
        # the runtime lookup resolves the first occurrence.
        path = self.write_ct(
            "dup.ct",
            '<Files><A.TXT Encoding="Ascii85">' + _embed_file_text(b"first")
            + "</A.TXT><a.txt Encoding=\"Ascii85\">"
            + _embed_file_text(b"second") + "</a.txt></Files>")
        table = read_table(str(path))
        self.assertEqual([f.name for f in table.embedded_files],
                         ["A.TXT", "a.txt"])
        self.assertEqual([f.size for f in table.embedded_files], [5, 6])

    def test_empty_child_refuses_the_table_load(self):
        path = self.write_ct(
            "empty.ct",
            '<Files><x.bin Encoding="Ascii85"></x.bin></Files>')
        with self.assertRaises(TableError) as ctx:
            read_table(str(path))
        self.assertIn("Embedded file 'x.bin' is empty.", str(ctx.exception))

    def test_more_than_64_files_refuse_the_table_load(self):
        inner = "".join(
            f'<f{i:02d}.txt Encoding="Ascii85">'
            + _embed_file_text(b"x") + f"</f{i:02d}.txt>\n"
            for i in range(65))
        path = self.write_ct("many.ct", f"<Files>\n{inner}</Files>")
        with self.assertRaises(TableError) as ctx:
            read_table(str(path))
        self.assertIn("Files section carries 65 embedded files; "
                      "the bound is 64", str(ctx.exception))

    def test_total_size_bound_refuses_the_table_load(self):
        # 5 files x 3.5 MiB each: every single file passes the 4 MiB
        # per-file bound, the cumulative total crosses 16 MiB.
        one = _embed_file_text(b"A" * 3_500_000)
        inner = "".join(
            f'<f{i}.bin Encoding="Ascii85">{one}</f{i}.bin>' for i in range(5))
        path = self.write_ct("big.ct", f"<Files>\n{inner}</Files>")
        with self.assertRaises(TableError) as ctx:
            read_table(str(path))
        self.assertIn("Embedded files exceed their 16 MiB total bound",
                      str(ctx.exception))


# ---------------------------------------------------------------------------
# Plan projection and both plan validators
# ---------------------------------------------------------------------------

class EmbeddedFilesPlanTests(unittest.TestCase):
    """The plan carries the raw text plus derived metadata, re-validated."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def compile(self, name: str, files: str) -> dict:
        path = self.root / name
        path.write_text(table_xml(value_record(0), "", files), encoding="utf-8")
        return compile_table(str(path), PROCESS)

    def test_projection_is_casefold_sorted_and_exact(self):
        a_txt, b_txt, c_txt = b"alpha", b"beta", b"gamma"
        plan = self.compile(
            "sorted.ct",
            files_section(("B.txt", _embed_file_text(b_txt)),
                          ("a.txt", _embed_file_text(a_txt)),
                          ("C.TXT", _embed_file_text(c_txt))))
        validate_plan(plan)
        validate_runtime_plan(plan)
        self.assertEqual([e["name"] for e in plan["embedded_files"]],
                         ["a.txt", "B.txt", "C.TXT"])
        self.assertEqual(plan["embedded_files"], [
            {"name": "a.txt", "encoding": "Ascii85",
             "text": _embed_file_text(a_txt),
             "sha256": sha256(a_txt).hexdigest(), "size": len(a_txt)},
            {"name": "B.txt", "encoding": "Ascii85",
             "text": _embed_file_text(b_txt),
             "sha256": sha256(b_txt).hexdigest(), "size": len(b_txt)},
            {"name": "C.TXT", "encoding": "Ascii85",
             "text": _embed_file_text(c_txt),
             "sha256": sha256(c_txt).hexdigest(), "size": len(c_txt)},
        ])

    def test_hex_entry_is_projected_and_validated(self):
        plan = self.compile(
            "hex.ct",
            '<Files><h.bin Encoding="Hex">'
            + _hex_embed_text(b"hex plan") + "</h.bin></Files>")
        validate_plan(plan)
        validate_runtime_plan(plan)
        self.assertEqual(plan["embedded_files"], [{
            "name": "h.bin", "encoding": "Hex",
            "text": _hex_embed_text(b"hex plan"),
            "sha256": sha256(b"hex plan").hexdigest(),
            "size": len(b"hex plan"),
        }])

    def test_key_absent_without_a_files_section(self):
        plan = self.compile("nofiles.ct", "")
        self.assertNotIn("embedded_files", plan)

    def test_forged_hash_is_refused_by_both_plan_validators(self):
        plan = self.compile("forged.ct",
                            files_section(("a.txt", _embed_file_text(b"alpha"))))
        forged = deepcopy(plan)
        forged["embedded_files"][0]["sha256"] = "0" * 64
        with self.assertRaises(NativeCompileError):
            validate_plan(forged)
        with self.assertRaises(NativeRuntimeError):
            validate_runtime_plan(forged)

    def test_forged_size_is_refused_by_both_plan_validators(self):
        plan = self.compile("forgedsize.ct",
                            files_section(("a.txt", _embed_file_text(b"alpha"))))
        forged = deepcopy(plan)
        forged["embedded_files"][0]["size"] += 1
        with self.assertRaises(NativeCompileError) as src:
            validate_plan(forged)
        with self.assertRaises(NativeRuntimeError) as rt:
            validate_runtime_plan(forged)
        self.assertEqual(str(src.exception), str(rt.exception))

    def test_schema_one_plan_cannot_carry_embedded_files(self):
        plan = self.compile("schema1.ct",
                            files_section(("a.txt", _embed_file_text(b"alpha"))))
        forged = deepcopy(plan)
        forged["schema"] = 1
        # Schema 1 is legacy x64 and carries no architecture profile.
        del forged["target_architecture"]
        with self.assertRaises(NativeCompileError) as ctx:
            validate_plan(forged)
        self.assertEqual(str(ctx.exception), "embedded_files requires schema 2")
        with self.assertRaises(NativeRuntimeError) as rt:
            validate_runtime_plan(forged)
        self.assertEqual(str(rt.exception), "embedded_files requires schema 2")



# ---------------------------------------------------------------------------
# Runtime contract (engine end-to-end)
# ---------------------------------------------------------------------------

class EmbeddedFilesRuntimeTests(unittest.TestCase):
    """Embedded files feed the table/record Lua surface; refusals are named."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.memory = None
        self.engines = []

    def tearDown(self):
        if self.memory is not None and not self.memory.closed:
            self.memory.alive = False
        for engine in self.engines:
            if not engine.closed:
                engine.poll()
                engine.close()

    def attach(self, body: str, lua_script: str = "", files: str = ""):
        path = self.root / "rt5.CT"
        path.write_text(table_xml(body, lua_script, files), encoding="utf-8")
        plan = compile_table(str(path), PROCESS)
        self.memory = Memory()
        # A fresh state dir per engine: a subtest loop may hold several
        # live engines in one test, and the state lock is per state dir.
        engine = TrainerEngine(plan, state_dir=self.root / f'state{len(self.engines)}',
                               process_lock_dir=self.root / f'shared{len(self.engines)}',
                               memory_factory=lambda name: self.memory,
                               hook_coordinator=Coordinator())
        self.engines.append(engine)
        engine.poll()
        return engine

    def test_p5_table_lua_shape_loads_embedded_file_and_record_uses_global(self):
        rt5base = b"return 4641\n"
        table_lua = (
            'local tf = findTableFile("rt5base.lua")\n'
            'assert(tf, "missing rt5base.lua")\n'
            'RT5base = assert(load(readStringLocal(tf.stream.memory, '
            'tf.stream.size)))()\n'
            'RT5missing = findTableFile("missing.lua") == nil\n')
        record = enable_lua_record(
            1,
            'if not syntaxcheck then\n'
            '  writeInteger(0x1080, RT5base)\n'
            '  assert(RT5missing == true)\n'
            'end\n',
            'assert(readInteger(0x1080)==4641)\n')
        engine = self.attach(value_record(0) + record, table_lua,
                             files_section(("rt5base.lua", _embed_file_text(rt5base))))
        plan = engine.plan
        self.assertEqual(plan["table_lua"],
                         {"executed": True, "reasons": [],
                          "record_scripts_inactive": 1})
        self.assertEqual(plan["embedded_files"], [{
            "name": "rt5base.lua", "encoding": "Ascii85",
            "text": _embed_file_text(rt5base),
            "sha256": sha256(rt5base).hexdigest(), "size": len(rt5base),
        }])
        # The engine seeds its runtime registry from the validated plan.
        self.assertEqual(engine._embedded_files, [bytes(rt5base)])
        self.assertEqual(engine._embedded_by_name, {"rt5base.lua": 0})
        self.assertEqual(self.memory.read(0x1080, 4), bytes(4))
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.memory.read(0x1080, 4), (4641).to_bytes(4, "little"))
        self.assertFalse(engine.toggle(1, False))
        self.assertEqual(self.memory.read(0x1080, 4), bytes(4))
        self.assertFalse(engine.blocked)

    def test_riftapart_record_shape_stream_stringlist_loadstring(self):
        tfilelist = b"a.js\nb.js"
        files = files_section(
            ("tFileList", _embed_file_text(tfilelist)),
            ("a.js", _embed_file_text(b"function ra() return 7 end\n")),
            ("b.js", _embed_file_text(b"function rb() return 11 end\n")),
        )
        enable_lua = (
            "local file = findTableFile('tFileList')\n"
            "if file == nil then return end\n"
            "local stringStream = createStringStream()\n"
            "stringStream.copyFrom(file.Stream, file.Stream.Size)\n"
            "local tFileList = createStringList()\n"
            "tFileList.Text = stringStream.DataString\n"
            "stringStream.destroy()\n"
            "for i = 0, tFileList.Count - 1 do\n"
            "  local tFile = findTableFile(tFileList[i])\n"
            "  if tFile then\n"
            "    local sStream = createStringStream()\n"
            "    sStream.copyFrom(tFile.Stream, tFile.Stream.Size)\n"
            "    assert(loadstring(sStream.DataString))()\n"
            "    sStream.destroy()\n"
            "  end\n"
            "end\n"
            "tFileList.destroy()\n"
            "if not syntaxcheck then\n"
            "  writeInteger(0x1090, ra() + rb())\n"
            "end\n")
        engine = self.attach(
            value_record(0) + enable_lua_record(1, enable_lua), "", files)
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.memory.read(0x1090, 4), (18).to_bytes(4, "little"))
        self.assertFalse(engine.toggle(1, False))
        self.assertFalse(engine.blocked)

    def test_read_string_local_maxsize_and_nul_semantics(self):
        # Documented deviations from CE readStringEx: an omitted or
        # negative maxsize returns the full content (CE defaults to 50
        # bytes), and there is no NUL truncation because the content is
        # the asset itself (CE stops at the first NUL).
        long_bin = b"A" * 80
        nul_bin = b"AB\x00CD"
        files = files_section(("long.bin", _embed_file_text(long_bin)),
                              ("nul.bin", _embed_file_text(nul_bin)))
        enable_lua = (
            "local f = findTableFile('long.bin')\n"
            "local full = readStringLocal(f.stream.memory)\n"
            "local half = readStringLocal(f.stream.memory, 50)\n"
            "local neg = readStringLocal(f.stream.memory, -1)\n"
            "local zero = readStringLocal(f.stream.memory, 0)\n"
            "local n = findTableFile('nul.bin')\n"
            "local nuls = readStringLocal(n.stream.memory, 32768)\n"
            "writeInteger(0x1090, #full)\n"
            "writeInteger(0x1094, #half)\n"
            "writeInteger(0x1098, #neg)\n"
            "writeInteger(0x109c, #zero)\n"
            "writeInteger(0x10a0, #nuls)\n")
        engine = self.attach(
            value_record(0) + enable_lua_record(1, enable_lua), "", files)
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.memory.read(0x1090, 4), (80).to_bytes(4, "little"))
        self.assertEqual(self.memory.read(0x1094, 4), (50).to_bytes(4, "little"))
        self.assertEqual(self.memory.read(0x1098, 4), (80).to_bytes(4, "little"))
        self.assertEqual(self.memory.read(0x109c, 4), (0).to_bytes(4, "little"))
        # No NUL truncation: all five bytes of "AB\x00CD" come back.
        self.assertEqual(self.memory.read(0x10a0, 4), (5).to_bytes(4, "little"))
        self.assertFalse(engine.toggle(1, False))

    def test_read_string_local_refuses_invalid_utf8(self):
        # Decoding is strict UTF-8; invalid bytes are a named refusal,
        # the record fails visibly with zero memory writes.
        files = files_section(("bin.dat", _embed_file_text(b"\xff\xfeAB")))
        enable_lua = (
            "local f = findTableFile('bin.dat')\n"
            "local s = readStringLocal(f.stream.memory)\n")
        engine = self.attach(
            value_record(0) + enable_lua_record(1, enable_lua), "", files)
        with self.assertRaises(NativeRuntimeError):
            engine.toggle(1, True)
        self.assertIn("Embedded content is not valid UTF-8 text",
                      engine.entry_errors[1])
        self.assertNotIn(1, engine.applied)
        self.assertEqual(self.memory.writes, [])
        self.assertFalse(engine.blocked)

    def test_find_table_file_returns_nil_for_missing_files(self):
        files = files_section(("present.lua", _embed_file_text(b"return 1\n")))
        enable_lua = (
            "local hit = findTableFile('present.lua')\n"
            "assert(hit ~= nil)\n"
            "local miss = findTableFile('MISSING.lua')\n"
            "assert(miss == nil)\n"
            "assert(FindTableFile('present.lua') ~= nil)\n"
            "if not syntaxcheck then writeInteger(0x1090, 7) end\n")
        engine = self.attach(
            value_record(0) + enable_lua_record(1, enable_lua), "", files)
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.memory.read(0x1090, 4), (7).to_bytes(4, "little"))
        self.assertFalse(engine.blocked)

    def test_casefold_duplicate_names_resolve_case_sensitively(self):
        # CE findTableFile is exact-name, case-sensitive: 'A.TXT' and
        # 'a.txt' are distinct entries, each resolves to its own content.
        files = files_section(("A.TXT", _embed_file_text(b"first\n")),
                              ("a.txt", _embed_file_text(b"second\n")))
        enable_lua = (
            "local f = findTableFile('A.TXT')\n"
            "assert(f ~= nil)\n"
            "local s1 = readStringLocal(f.stream.memory)\n"
            "local g = findTableFile('a.txt')\n"
            "assert(g ~= nil)\n"
            "local s2 = readStringLocal(g.stream.memory)\n"
            "writeInteger(0x1090, s1 == 'first\\n' and 1 or 2)\n"
            "writeInteger(0x1094, s2 == 'second\\n' and 1 or 2)\n")
        engine = self.attach(
            value_record(0) + enable_lua_record(1, enable_lua), "", files)
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.memory.read(0x1090, 4), (1).to_bytes(4, "little"))
        self.assertEqual(self.memory.read(0x1094, 4), (1).to_bytes(4, "little"))
        self.assertFalse(engine.blocked)

    def test_exact_duplicate_names_resolve_to_the_first_occurrence(self):
        # Two <a.txt> entries (CE tolerates the duplicate): the runtime
        # registry keeps the first occurrence (engine seeds with
        # setdefault over the casefold-sorted plan order).
        files = files_section(("a.txt", _embed_file_text(b"first\n")),
                              ("a.txt", _embed_file_text(b"second\n")))
        enable_lua = (
            "local f = findTableFile('a.txt')\n"
            "assert(f ~= nil)\n"
            "local s = readStringLocal(f.stream.memory)\n"
            "writeInteger(0x1090, s == 'first\\n' and 1 or 2)\n")
        engine = self.attach(
            value_record(0) + enable_lua_record(1, enable_lua), "", files)
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.memory.read(0x1090, 4), (1).to_bytes(4, "little"))
        self.assertFalse(engine.blocked)

    def test_read_string_local_reads_string_stream_tokens(self):
        # readStringLocal also accepts live string-stream tokens (ct2ss:),
        # with the same maxsize semantics as embedded-file tokens.
        engine = self.attach(value_record(0))
        broker = TableLuaBroker(engine)
        created = broker.call('stringstream.create', (),
                              generation=broker.generation, syntaxcheck=False)
        token = created['token']
        broker.call('stringstream.copyFrom', (token, 'hello stream'),
                    generation=broker.generation, syntaxcheck=False)
        self.assertEqual(broker.call('readStringLocal', (token,),
                                     generation=broker.generation,
                                     syntaxcheck=False), 'hello stream')
        self.assertEqual(broker.call('readStringLocal', (token, 5),
                                     generation=broker.generation,
                                     syntaxcheck=False), 'hello')
        self.assertEqual(broker.call('readStringLocal', (token, 0),
                                     generation=broker.generation,
                                     syntaxcheck=False), '')
        with self.assertRaises(LuaHostError) as ctx:
            broker.call('readStringLocal', ('ct2ss:999',),
                        generation=broker.generation, syntaxcheck=False)
        self.assertIn("readStringLocal token does not name a live string stream",
                      str(ctx.exception))

    def test_refusal_matrix_named_reasons_and_no_memory_writes(self):
        cases = (
            ("readStringLocal(0x1234)",
             "readStringLocal requires an embedded-file or string-stream token"),
            ("local f = findTableFile('rt5base.lua')\n"
             "readStringLocal(f.stream.memory, 10, true)",
             "readStringLocal wide strings are outside this profile"),
            ("local f = findTableFile('rt5base.lua')\n"
             "readStringLocal(f.stream.memory, 2.5)",
             "readStringLocal maxsize must be an integer"),
            ("local f = findTableFile('rt5base.lua')\n"
             "readStringLocal(f.stream.memory, 10, 'yes')",
             "readStringLocal wide flag must be boolean"),
            ("readStringLocal('ct2tf:9')",
             "readStringLocal token does not name an embedded file"),
            ("createTableFile('rt5new.lua')",
             "createTableFile is outside this profile"),
            ("CreateTableFile('rt5new.lua')",
             "createTableFile is outside this profile"),
            ("local sl = createStringList()\n"
             "sl:destroy()\n"
             "sl.Text = 'x'",
             "String list is destroyed"),
            ("findTableFile('rt5base.lua'):delete()",
             "Table-file deletion is outside this profile"),
            ("local f = findTableFile('rt5base.lua')\n"
             "f.Stream.write(1)",
             "Table-file stream writes are outside this profile"),
            ("local s = createStringStream()\n"
             "s:destroy()\n"
             "local x = s.Size",
             "String stream is not open"),
            ("local s = createStringStream()\n"
             "s:destroy()\n"
             "s.copyFrom('x')",
             "String stream is not open"),
        )
        files = files_section(("rt5base.lua", _embed_file_text(b"return 4641\n")))
        for source, expected in cases:
            with self.subTest(case=expected):
                engine = self.attach(
                    value_record(0) + enable_lua_record(1, source), "", files)
                with self.assertRaises(NativeRuntimeError):
                    engine.toggle(1, True)
                self.assertIn(expected, engine.entry_errors[1])
                self.assertNotIn(1, engine.applied)
                self.assertEqual(self.memory.writes, [])
                self.assertFalse(engine.blocked)


if __name__ == "__main__":
    unittest.main()
