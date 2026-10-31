"""Master Trainer table folder index (MT-1): the incremental reconcile contract.

Covers: deterministic recursive discovery, the (size, mtime_ns) skip
contract (unchanged files are listed, never re-read), the sha256
short-circuit (content-identical mtime moves keep the derived names and
classify as unchanged), change/add/remove bookkeeping, unreadable entries
with named errors, and the checksum-bound persistence document (roundtrip,
foreign schema, tampered checksum, foreign root rebuild).
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from ct2trainer.native.master_trainer import table_index as ti
from ct2trainer.native.master_trainer.table_index import (
    TableIndex, TableIndexRefusal, index_from_bytes, index_to_bytes,
    load_index, reconcile, save_index,
)

# The CT carries one distinct EXE token; the index binds it.
CT_A = '''<CheatTable CheatEngineTableVersion="46"><CheatEntries>
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

# A second table naming a different EXE (plus a repeat in other casing).
CT_B = '''<CheatTable CheatEngineTableVersion="46"><CheatEntries>
<CheatEntry><ID>1</ID><Description>"SP"</Description>
<VariableType>Auto Assembler Script</VariableType><AssemblerScript>[ENABLE]
assert(GameB.exe+20, 90)
GameB.exe+20:
db CC
[DISABLE]
GameB.exe+20:
db 90
</AssemblerScript></CheatEntry>
</CheatEntries><UserDescription>module: gameb.exe</UserDescription></CheatTable>'''

# A table naming two distinct EXEs: both become candidates.
CT_MULTI = '''<CheatTable CheatEngineTableVersion="46"><CheatEntries>
<CheatEntry><ID>1</ID><Description>"X"</Description>
<VariableType>Auto Assembler Script</VariableType><AssemblerScript>[ENABLE]
assert(Dual.exe+10, 90)
Dual.exe+10:
db CC
[DISABLE]
Dual.exe+10:
db 90
</AssemblerScript></CheatEntry>
<CheatEntry><ID>2</ID><Description>"Y"</Description>
<VariableType>Auto Assembler Script</VariableType><AssemblerScript>[ENABLE]
assert(Dual2.exe+30, 90)
Dual2.exe+30:
db CC
[DISABLE]
Dual2.exe+30:
db 90
</AssemblerScript></CheatEntry>
</CheatEntries></CheatTable>'''


def _make_tree():
    temp = tempfile.TemporaryDirectory()
    root = Path(temp.name)
    return temp, root


class IndexScanTests(unittest.TestCase):
    def setUp(self):
        self.temp, self.root = _make_tree()
        self.addCleanup(self.temp.cleanup)
        (self.root / "sub").mkdir()
        (self.root / "a.ct").write_text(CT_A, encoding="utf-8")
        (self.root / "sub" / "b.ct").write_text(CT_B, encoding="utf-8")
        (self.root / "notes.txt").write_text("not a table", encoding="utf-8")

    def test_initial_scan_finds_nested_tables_and_binds_names(self):
        result = reconcile(self.root, None)
        self.assertIsNone(result.scan_error)
        self.assertEqual(len(result.index.entries), 2)
        a = result.index.entries["a.ct"]
        b = result.index.entries["sub/b.ct"]
        self.assertEqual(a.status, "ok")
        self.assertEqual(a.process_names, ("GameA.exe",))
        # casefold-deduped, first-seen spelling kept
        self.assertEqual(b.process_names, ("GameB.exe",))
        kinds = {c.kind for c in result.changes}
        self.assertEqual(kinds, {"added"})

    def test_initial_scan_reads_every_file_exactly_once(self):
        calls = []
        real_read = ti._read_and_hash
        def counting(path):
            calls.append(str(path))
            return real_read(path)
        self.addCleanup(setattr, ti, "_read_and_hash", real_read)
        ti._read_and_hash = counting
        reconcile(self.root, None)
        self.assertEqual(len(calls), 2)

    def test_unchanged_tree_never_re_reads_tables(self):
        first = reconcile(self.root, None)
        calls = []
        real_read = ti._read_and_hash
        def counting(path):
            calls.append(str(path))
            return real_read(path)
        self.addCleanup(setattr, ti, "_read_and_hash", real_read)
        ti._read_and_hash = counting
        second = reconcile(self.root, first.index)
        self.assertEqual(calls, [])  # listing only, no re-reads
        self.assertEqual([c.kind for c in second.changes],
                         ["unchanged", "unchanged"])
        self.assertEqual(second.index.entries, first.index.entries)

    def test_content_change_rederives_process_names(self):
        first = reconcile(self.root, None)
        (self.root / "a.ct").write_text(CT_MULTI, encoding="utf-8")
        second = reconcile(self.root, first.index)
        changed = {c.kind for c in second.changes}
        self.assertEqual(changed, {"changed", "unchanged"})
        a = second.index.entries["a.ct"]
        self.assertEqual(a.process_names, ("Dual.exe", "Dual2.exe"))
        # The hash is over the on-disk bytes (write_text applies the
        # platform newline translation), not the in-memory source.
        self.assertEqual(a.sha256,
                         hashlib.sha256((self.root / "a.ct").read_bytes()).hexdigest())

    def test_mtime_only_change_short_circuits_on_sha256(self):
        first = reconcile(self.root, None)
        # Move the fingerprint without touching the content: the file is
        # read once for the sha, the stored names survive, and the change
        # classifies as unchanged (content is the authority).
        st = os.stat(self.root / "a.ct")
        os.utime(self.root / "a.ct", ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000))
        derive_calls = []
        real_derive = ti._derive_names
        def counting(source):
            derive_calls.append(None)
            return real_derive(source)
        self.addCleanup(setattr, ti, "_derive_names", real_derive)
        ti._derive_names = counting
        second = reconcile(self.root, first.index)
        a = second.index.entries["a.ct"]
        self.assertEqual(a.process_names, ("GameA.exe",))
        # The hash is over the on-disk bytes (write_text applies the
        # platform newline translation), not the in-memory source.
        self.assertEqual(a.sha256,
                         hashlib.sha256((self.root / "a.ct").read_bytes()).hexdigest())
        self.assertNotEqual(a.mtime_ns, first.index.entries["a.ct"].mtime_ns)
        kinds = sorted(c.kind for c in second.changes)
        self.assertEqual(kinds, ["unchanged", "unchanged"])
        self.assertEqual(derive_calls, [])  # names kept, not re-derived

    def test_added_and_removed_paths(self):
        first = reconcile(self.root, None)
        (self.root / "sub" / "c.ct").write_text(CT_MULTI, encoding="utf-8")
        second = reconcile(self.root, first.index)
        kinds = {c.kind: c.relative_path for c in second.changes}
        self.assertEqual(kinds["added"], "sub/c.ct")
        (self.root / "a.ct").unlink()
        third = reconcile(self.root, second.index)
        kinds = {c.kind: c.relative_path for c in third.changes}
        self.assertEqual(kinds["removed"], "a.ct")
        self.assertNotIn("a.ct", third.index.entries)
        self.assertEqual(len(third.index.entries), 2)

    def test_unreadable_table_is_visible_and_binds_nothing(self):
        (self.root / "bad.ct").write_text(
            "<CheatTable><CheatEntries><unclosed></CheatEntries>",
            encoding="utf-8")
        result = reconcile(self.root, None)
        bad = result.index.entries["bad.ct"]
        self.assertEqual(bad.status, "unreadable")
        self.assertIn("parse failed", bad.detail)
        self.assertEqual(bad.process_names, ())
        self.assertEqual(result.index.entries_for_process("GameA.exe"),
                         [result.index.entries["a.ct"]])

    def test_empty_ct_is_unreadable(self):
        (self.root / "empty.ct").write_bytes(b"")
        result = reconcile(self.root, None)
        empty = result.index.entries["empty.ct"]
        self.assertEqual(empty.status, "unreadable")
        self.assertEqual(empty.detail, "empty file")

    def test_missing_root_is_named_and_keeps_stored_entries(self):
        # A missing root is a scan error, not an index loss: the stored
        # entries survive (transient drive unmount, folder rename in
        # progress) and the error stays visible to the caller.
        missing = self.root / "nope"
        result = reconcile(missing, None)
        self.assertIn("missing or not a directory", result.scan_error)
        self.assertEqual(result.index.entries, {})
        seeded = TableIndex(str(missing), {"x.ct": ti.TableEntry(
            "x.ct", 1, 2, "0" * 64, ("X.exe",), "ok", None)})
        again = reconcile(missing, seeded)
        self.assertIn("missing or not a directory", again.scan_error)
        self.assertEqual(again.index.entries, seeded.entries)
        self.assertEqual(again.changes, ())


class IndexLookupTests(unittest.TestCase):
    def _index(self, root="C:\\tables"):
        def entry(rel, names, status="ok"):
            return ti.TableEntry(rel, 10, 20, "ab" * 32, tuple(names),
                                 status, None if status == "ok" else "e")
        return TableIndex(root, {
            "alpha.ct": entry("alpha.ct", ("Game.exe", "Helper.exe")),
            "beta.ct": entry("beta.ct", ("GAME.EXE",)),
            "gamma.ct": entry("gamma.ct", (), "unreadable"),
        })

    def test_process_names_distinct_and_sorted_by_key(self):
        self.assertEqual(self._index().process_names(),
                         ["Game.exe", "Helper.exe"])

    def test_entries_for_process_is_case_insensitive_and_skips_unreadable(self):
        index = self._index()
        self.assertEqual(index.entries_for_process("game.exe"),
                         [index.entries["alpha.ct"], index.entries["beta.ct"]])
        self.assertEqual(index.entries_for_process("Game.EXE"),
                         [index.entries["alpha.ct"], index.entries["beta.ct"]])
        self.assertEqual(index.entries_for_process("helper.exe"),
                         [index.entries["alpha.ct"]])
        self.assertEqual(index.entries_for_process("ghost.exe"), [])

    def test_tables_are_stably_ordered(self):
        index = self._index()
        self.assertEqual([t.relative_path for t in index.tables()],
                         ["alpha.ct", "beta.ct", "gamma.ct"])


class IndexPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "tables"
        self.root.mkdir()
        (self.root / "a.ct").write_text(CT_A, encoding="utf-8")
        self.index = reconcile(self.root, None).index

    def test_save_load_roundtrip_is_byte_identical(self):
        path = Path(self.temp.name) / "state" / "tables-index.json"
        save_index(self.index, path)
        loaded = load_index(path)
        self.assertEqual(loaded.root, self.index.root)
        self.assertEqual(loaded.entries, self.index.entries)
        self.assertEqual(index_to_bytes(loaded), index_to_bytes(self.index))

    def test_tampered_checksum_is_refused(self):
        raw = index_to_bytes(self.index).decode("utf-8")
        document = json.loads(raw)
        entry = document["payload"]["entries"]["a.ct"]
        entry["sha256"] = "00" * 32
        with self.assertRaises(TableIndexRefusal) as ctx:
            index_from_bytes(json.dumps(document, sort_keys=True).encode())
        self.assertIn("checksum does not match", str(ctx.exception))

    def test_foreign_schema_is_refused(self):
        raw = index_to_bytes(self.index).decode("utf-8")
        document = json.loads(raw)
        document["payload"]["schema"] = 99
        # Re-sign the document so only the schema is the problem.
        canonical = json.dumps(document["payload"], sort_keys=True,
                               separators=(",", ":"),
                               allow_nan=False, ensure_ascii=True).encode()
        document["sha256"] = hashlib.sha256(canonical).hexdigest()
        with self.assertRaises(TableIndexRefusal) as ctx:
            index_from_bytes(json.dumps(document, sort_keys=True).encode())
        self.assertIn("schema", str(ctx.exception))

    def test_tampered_root_is_refused_by_reconcile_as_rebuild(self):
        path = Path(self.temp.name) / "state" / "tables-index.json"
        save_index(self.index, path)
        # Point the stored root at a different folder: the document is
        # still loadable, but reconcile treats it as foreign (full rebuild).
        raw = path.read_bytes().decode("utf-8")
        document = json.loads(raw)
        document["payload"]["root"] = str(Path(self.temp.name) / "other")
        canonical = json.dumps(document["payload"], sort_keys=True,
                               separators=(",", ":"),
                               allow_nan=False, ensure_ascii=True).encode()
        document["sha256"] = hashlib.sha256(canonical).hexdigest()
        path.write_bytes(json.dumps(document, sort_keys=True).encode() + b"\n")
        stored = load_index(path)
        result = reconcile(self.root, stored)
        # Foreign root: full rebuild from an empty prior, so every live
        # table is added and nothing is reported as removed.
        self.assertEqual({c.kind for c in result.changes}, {"added"})
        self.assertEqual(len(result.index.entries), 1)

    def test_missing_file_load_raises(self):
        with self.assertRaises(FileNotFoundError):
            load_index(Path(self.temp.name) / "absent" / "tables-index.json")

    def test_index_never_lives_in_the_table_folder(self):
        path = Path(self.temp.name) / "state" / "tables-index.json"
        save_index(self.index, path)
        self.assertNotIn(path, [self.root / name
                                for name in ("tables-index.json",)])
        self.assertEqual(list(self.root.iterdir()), [self.root / "a.ct"])


if __name__ == "__main__":
    unittest.main()
