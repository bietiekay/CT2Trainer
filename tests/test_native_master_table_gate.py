"""Master Trainer load-time table gate (MT-9): compatibility + size
re-proof of one table file at the moment a load is requested.

Covers: the passing gate (valid XML table, sub-folders, exact size and
sha), every named refusal (missing file, directory path, empty file,
oversized file vs the load limit, drift vs the index entry, unparseable
content, DTD/entity refusal, unparseable legacy binary, change during
analysis) with its stable code and displayable detail, and the
``TableLoadGateRefusal`` contract (named code + detail, ValueError
family, displayable string). All tests run on temporary folders; no
real processes are spawned.
"""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from ct2trainer.native.master_trainer.table_gate import (
    CODE_CHANGED_DURING_ANALYSIS,
    CODE_CHANGED_SINCE_LAST_SCAN,
    CODE_EMPTY,
    CODE_FILE_MISSING,
    CODE_NOT_A_FILE,
    CODE_NOT_LOADABLE,
    CODE_READ_FAILED,
    CODE_TOO_LARGE,
    TableGateResult,
    TableLoadGateRefusal,
    gate_table_for_load,
)
from ct2trainer.native.master_trainer.table_index import TableEntry

# One distinct EXE token; the same shape as the MT-1/MT-4 fixtures.
CT_VALID = '''<CheatTable CheatEngineTableVersion="46"><CheatEntries>
<CheatEntry><ID>1</ID><Description>"HP"</Description>
<VariableType>Auto Assembler Script</VariableType><AssemblerScript>[ENABLE]
assert(GameA.exe+10, 90)
GameA.exe+10:
db CC
[DISABLE]
GameA.exe+10:
db 90
</AssemblerScript></CheatEntry>
</CheatEntries></CheatTable>'''


class GateFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def _write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def _entry(self, path, sha=None, size=None):
        """An index entry for one file: fresh sha/size unless overridden."""
        if sha is None:
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
        if size is None:
            size = path.stat().st_size
        return TableEntry(path.name, size, 123, sha, ("GameA.exe",), "ok", None)


class GatePassTests(GateFixture):
    def test_valid_xml_table_passes_with_size_and_sha(self):
        path = self._write("a.ct", CT_VALID)
        result = gate_table_for_load(path, self._entry(path))
        self.assertTrue(result.ok)
        self.assertEqual(result.size, path.stat().st_size)
        self.assertEqual(result.sha256,
                         hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertIsNone(result.code)
        self.assertIsNone(result.detail)

    def test_valid_table_in_subfolder_passes(self):
        path = self._write("sub/dir/a.ct", CT_VALID)
        result = gate_table_for_load(path, self._entry(path))
        self.assertTrue(result.ok)
        self.assertEqual(result.size, path.stat().st_size)

    def test_ok_result_fields_are_exact(self):
        path = self._write("a.ct", CT_VALID)
        result = gate_table_for_load(path, self._entry(path))
        self.assertEqual(
            result, TableGateResult(True, size=result.size,
                                    sha256=result.sha256))


class GateRefusalTests(GateFixture):
    def test_missing_file_is_named(self):
        # No file on disk: build the entry from a known hash.
        entry = TableEntry("gone.ct", 10, 123, "ab" * 32,
                           ("GameA.exe",), "ok", None)
        result = gate_table_for_load(self.root / "gone.ct", entry)
        self.assertFalse(result.ok)
        self.assertEqual(result.code, CODE_FILE_MISSING)
        self.assertIn("gone.ct", result.detail)
        self.assertIn("missing", result.detail)
        self.assertIsNone(result.sha256)

    def test_directory_path_is_named(self):
        sub = self.root / "dir.ct"
        sub.mkdir()
        entry = TableEntry("dir.ct", 4, 123, "cd" * 32,
                           ("GameA.exe",), "ok", None)
        result = gate_table_for_load(sub, entry)
        self.assertFalse(result.ok)
        self.assertEqual(result.code, CODE_NOT_A_FILE)
        self.assertIn("not a regular file", result.detail)

    def test_empty_file_is_named_with_size_zero(self):
        path = self._write("empty.ct", "")
        entry = self._entry(path)  # sha of the empty content
        result = gate_table_for_load(path, entry)
        self.assertFalse(result.ok)
        self.assertEqual(result.code, CODE_EMPTY)
        self.assertEqual(result.size, 0)
        self.assertIn("0 bytes", result.detail)

    def test_oversized_file_is_named_with_limit_and_size(self):
        path = self._write("big.ct", CT_VALID)
        entry = self._entry(path)
        with mock.patch("ct2trainer.table.MAX_TABLE_BYTES", 32):
            result = gate_table_for_load(path, entry)
        self.assertFalse(result.ok)
        self.assertEqual(result.code, CODE_TOO_LARGE)
        self.assertEqual(result.size, path.stat().st_size)
        self.assertIn("32-byte load limit", result.detail)
        self.assertIn(str(path.stat().st_size), result.detail)

    def test_oversized_refusal_never_reads_content(self):
        # A file over the limit must be refused on the stat alone: no
        # content read, no parse attempt (no read_table call).
        path = self._write("big.ct", CT_VALID)
        entry = self._entry(path)
        with mock.patch("ct2trainer.table.MAX_TABLE_BYTES", 32), \
                mock.patch("ct2trainer.table.read_table") as read:
            result = gate_table_for_load(path, entry)
        self.assertEqual(result.code, CODE_TOO_LARGE)
        read.assert_not_called()

    def test_drift_vs_index_entry_is_named_stale_refusal(self):
        path = self._write("a.ct", CT_VALID)
        entry = self._entry(path)
        path.write_text(CT_VALID.replace('GameA.exe', 'GameB.exe'),
                        encoding="utf-8")
        result = gate_table_for_load(path, entry)
        self.assertFalse(result.ok)
        self.assertEqual(result.code, CODE_CHANGED_SINCE_LAST_SCAN)
        self.assertIn("Rescan", result.detail)
        self.assertEqual(result.size, path.stat().st_size)

    def test_garbage_bytes_are_named_not_loadable(self):
        path = self._write("bad.ct", "not a table at all")
        entry = self._entry(path)  # sha matches the garbage content
        result = gate_table_for_load(path, entry)
        self.assertFalse(result.ok)
        self.assertEqual(result.code, CODE_NOT_LOADABLE)
        self.assertIn("TableError", result.detail)

    def test_legacy_binary_magic_is_named_not_loadable(self):
        # The legacy CT magic prefix routes into the legacy reader; an
        # unparseable body stays a named refusal (distinct reason from
        # malformed XML, same as the table parser contract).
        path = self.root / "legacy.ct"
        path.write_bytes(b"CHEATENGINE" + b"\x00" * 40)
        entry = self._entry(path)
        result = gate_table_for_load(path, entry)
        self.assertFalse(result.ok)
        self.assertEqual(result.code, CODE_NOT_LOADABLE)
        # The legacy reader's own named error (LegacyCTError, a TableError
        # subclass) is carried through displayable.
        self.assertIn("LegacyCTError", result.detail)

    def test_dtd_entity_table_is_named_not_loadable(self):
        dtd = ('<?xml version="1.0"?>\n'
               '<!DOCTYPE CheatTable [\n'
               '  <!ENTITY x "1">\n'
               ']>\n<CheatTable><CheatEntries></CheatEntries></CheatTable>')
        path = self._write("dtd.ct", dtd)
        entry = self._entry(path)
        result = gate_table_for_load(path, entry)
        self.assertFalse(result.ok)
        self.assertEqual(result.code, CODE_NOT_LOADABLE)
        self.assertIn("TableError", result.detail)

    def test_change_during_analysis_is_named(self):
        path = self._write("a.ct", CT_VALID)
        entry = self._entry(path)
        stale = SimpleNamespace(source_sha256="00" * 32)
        with mock.patch("ct2trainer.table.read_table",
                        side_effect=lambda p: stale):
            result = gate_table_for_load(path, entry)
        self.assertFalse(result.ok)
        self.assertEqual(result.code, CODE_CHANGED_DURING_ANALYSIS)
        self.assertIn("analyzed", result.detail)

    def test_check_order_is_cheapest_first(self):
        # A missing file must not reach the parser; an oversized file
        # must not reach the drift comparison.  Proven with stubbed
        # parser that would record any call.
        entry = TableEntry("x.ct", 10, 123, "ab" * 32,
                           ("GameA.exe",), "ok", None)
        with mock.patch("ct2trainer.table.read_table") as read:
            gate_table_for_load(self.root / "missing.ct", entry)
        read.assert_not_called()
        path = self._write("big.ct", CT_VALID)
        entry2 = self._entry(path)
        with mock.patch("ct2trainer.table.MAX_TABLE_BYTES", 32), \
                mock.patch("ct2trainer.table.read_table") as read2:
            gate_table_for_load(path, entry2)
        read2.assert_not_called()


class RefusalContractTests(GateFixture):
    def test_refusal_exception_carries_code_and_detail(self):
        exc = TableLoadGateRefusal(CODE_TOO_LARGE,
                                   "table exceeds the 32-byte load limit")
        self.assertEqual(exc.code, CODE_TOO_LARGE)
        self.assertEqual(exc.detail, "table exceeds the 32-byte load limit")
        self.assertEqual(str(exc), "table exceeds the 32-byte load limit")
        self.assertIsInstance(exc, ValueError)

    def test_codes_are_stable_distinct_strings(self):
        codes = {CODE_FILE_MISSING, CODE_NOT_A_FILE, CODE_READ_FAILED,
                 CODE_EMPTY, CODE_TOO_LARGE, CODE_CHANGED_SINCE_LAST_SCAN,
                 CODE_NOT_LOADABLE, CODE_CHANGED_DURING_ANALYSIS}
        self.assertEqual(len(codes), 8)
        for code in codes:
            self.assertTrue(code.startswith("table-"))


if __name__ == "__main__":
    unittest.main()
