"""Master Trainer 0.37: per-table process binding persistence (MT-28).

Covers the new pure ``table_attach`` layer - the persisted
``table-attach.json`` document (schema 1, under the state home, keyed
by the table content sha256 - the same identity as the MT-24 analysis
and the MT-27 notes documents) with its strict key-set / field
validation, the checksummed envelope, the 1024-entry LRU bound,
load-refused-treated-as-absent, the ``AttachStore`` (set /
clear / eviction), and the pure decision + display helpers
(``binding_target`` - honour the remembered PID only while it is one
of the live candidates whose name still matches, otherwise the
documented fallback; ``details_attach_lines``).

No real process is attached; the candidates are plain
``ProcessSnapshotEntry`` rows.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from unittest.mock import patch

from ct2trainer.native.master_trainer.process_watch import (
    ProcessSnapshotEntry,
    names_match,
)
from ct2trainer.native.master_trainer import table_attach
from ct2trainer.native.master_trainer.table_attach import (
    ATTACH_DOC_NAME,
    ATTACH_ENTRIES_LIMIT,
    ATTACH_SCHEMA,
    PROCESS_NAME_MAX,
    AttachRefusal,
    AttachStore,
    attach_document_from_bytes,
    attach_document_to_bytes,
    binding_entry,
    binding_target,
    details_attach_lines,
    evict_oldest,
    load_attach_document,
    save_attach_document,
    sha256_key_ok,
)

SHA = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
NAME = "GameA.exe"
TS = "2026-11-09T12:00:00Z"


def _entry(process=NAME, pid=7, now=TS):
    return {"process": process, "pid": pid, "updated_at": now}


def _doc(tables):
    return {"schema": ATTACH_SCHEMA, "tables": tables}


class BindingEntryTests(unittest.TestCase):
    def test_valid_entry(self):
        self.assertEqual(binding_entry(NAME, 7, TS), _entry())

    def test_strips_the_process_name(self):
        self.assertEqual(binding_entry("  " + NAME + "  ", 7, TS)["process"],
                         NAME)

    def test_empty_process_refused(self):
        with self.assertRaises(AttachRefusal):
            binding_entry("", 7, TS)
        with self.assertRaises(AttachRefusal):
            binding_entry("   ", 7, TS)

    def test_non_string_process_refused(self):
        with self.assertRaises(AttachRefusal):
            binding_entry(None, 7, TS)
        with self.assertRaises(AttachRefusal):
            binding_entry(7, 7, TS)

    def test_overlong_process_refused(self):
        with self.assertRaises(AttachRefusal):
            binding_entry("x" * (PROCESS_NAME_MAX + 1), 7, TS)
        # Exactly the bound is accepted.
        self.assertEqual(binding_entry("x" * PROCESS_NAME_MAX, 7, TS)
                         ["process"], "x" * PROCESS_NAME_MAX)

    def test_non_integer_pid_refused(self):
        for bad in (None, "7", 7.0, True, False):
            with self.assertRaises(AttachRefusal):
                binding_entry(NAME, bad, TS)

    def test_non_positive_pid_refused(self):
        for bad in (0, -3):
            with self.assertRaises(AttachRefusal):
                binding_entry(NAME, bad, TS)


class DocumentTests(unittest.TestCase):
    def test_round_trip(self):
        payload = _doc({SHA: _entry()})
        raw = attach_document_to_bytes(payload)
        self.assertEqual(attach_document_from_bytes(raw), payload)

    def test_envelope_has_checksum_and_trailing_newline(self):
        raw = attach_document_to_bytes(_doc({SHA: _entry()}))
        self.assertTrue(raw.endswith(b"\n"))
        document = json.loads(raw.decode("utf-8"))
        self.assertEqual(set(document), {"payload", "sha256"})
        self.assertEqual(document["payload"], _doc({SHA: _entry()}))

    def test_tampered_checksum_refused(self):
        raw = bytearray(attach_document_to_bytes(_doc({SHA: _entry()})))
        # Flip a byte inside the payload (the "process" value region).
        idx = raw.find(b"GameA.exe")
        raw[idx] = ord("X")
        with self.assertRaises(AttachRefusal):
            attach_document_from_bytes(bytes(raw))

    def test_not_json_refused(self):
        with self.assertRaises(AttachRefusal):
            attach_document_from_bytes(b"not json")

    def test_fields_mismatch_refused(self):
        with self.assertRaises(AttachRefusal):
            attach_document_from_bytes(
                json.dumps({"payload": _doc({}), "other": 1,
                            "sha256": "x"}).encode("utf-8"))

    def test_unknown_entry_field_refused(self):
        with self.assertRaises(AttachRefusal):
            attach_document_to_bytes(
                _doc({SHA: dict(_entry(), extra="x")}))

    def test_missing_entry_field_refused(self):
        entry = _entry()
        del entry["pid"]
        with self.assertRaises(AttachRefusal):
            attach_document_to_bytes(_doc({SHA: entry}))

    def test_bad_pid_refused(self):
        for bad in (0, -1, "7", None, True):
            entry = _entry()
            entry["pid"] = bad
            with self.assertRaises(AttachRefusal):
                attach_document_to_bytes(_doc({SHA: entry}))

    def test_bad_process_refused(self):
        for bad in ("", None, "x" * (PROCESS_NAME_MAX + 1)):
            entry = _entry()
            entry["process"] = bad
            with self.assertRaises(AttachRefusal):
                attach_document_to_bytes(_doc({SHA: entry}))

    def test_bad_timestamp_refused(self):
        entry = _entry()
        entry["updated_at"] = "2026-11-09 12:00:00"
        with self.assertRaises(AttachRefusal):
            attach_document_to_bytes(_doc({SHA: entry}))

    def test_unknown_schema_refused(self):
        payload = _doc({SHA: _entry()})
        payload["schema"] = ATTACH_SCHEMA + 1
        with self.assertRaises(AttachRefusal):
            attach_document_to_bytes(payload)

    def test_bad_key_refused(self):
        for bad in ("a" * 63, "A" * 64, "a" * 65, "zzz"):
            with self.assertRaises(AttachRefusal):
                attach_document_to_bytes(_doc({bad: _entry()}))

    def test_tables_not_object_refused(self):
        with self.assertRaises(AttachRefusal):
            attach_document_to_bytes({"schema": ATTACH_SCHEMA,
                                      "tables": []})

    def test_root_fields_mismatch_refused(self):
        with self.assertRaises(AttachRefusal):
            attach_document_to_bytes(
                {"schema": ATTACH_SCHEMA, "tables": {}, "extra": 1})

    def test_over_entry_limit_refused(self):
        tables = {"%064x" % i: _entry(pid=i + 1)
                  for i in range(ATTACH_ENTRIES_LIMIT + 1)}
        with self.assertRaises(AttachRefusal):
            attach_document_to_bytes(_doc(tables))

    def test_exactly_at_entry_limit_ok(self):
        tables = {"%064x" % i: _entry(pid=i + 1)
                  for i in range(ATTACH_ENTRIES_LIMIT)}
        self.assertEqual(attach_document_from_bytes(
            attach_document_to_bytes(_doc(tables))), _doc(tables))


class LoadSaveTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / ATTACH_DOC_NAME

    def test_absent_file_is_none(self):
        self.assertIsNone(load_attach_document(self.path))

    def test_load_round_trip(self):
        payload = _doc({SHA: _entry()})
        save_attach_document(payload, self.path)
        self.assertEqual(load_attach_document(self.path), payload)

    def test_refused_file_is_none(self):
        self.path.write_bytes(b"corrupt")
        self.assertIsNone(load_attach_document(self.path))

    def test_save_creates_parent(self):
        nested = Path(self.temporary.name) / "deep" / ATTACH_DOC_NAME
        save_attach_document(_doc({SHA: _entry()}), nested)
        self.assertTrue(nested.is_file())


class EvictOldestTests(unittest.TestCase):
    def test_noop_under_limit(self):
        tables = {SHA: _entry(now="2026-01-01T00:00:00Z"),
                  SHA_B: _entry(now="2026-02-01T00:00:00Z")}
        self.assertEqual(evict_oldest(tables, limit=10), tables)

    def test_drops_oldest_by_updated_at(self):
        tables = {
            SHA: _entry(now="2026-01-01T00:00:00Z"),
            SHA_B: _entry(now="2026-03-01T00:00:00Z"),
            SHA_C: _entry(now="2026-02-01T00:00:00Z"),
        }
        evict_oldest(tables, limit=2)
        self.assertEqual(set(tables), {SHA_B, SHA_C})

    def test_tie_broken_by_sha(self):
        tables = {SHA_B: _entry(now=TS), SHA: _entry(now=TS)}
        evict_oldest(tables, limit=1)
        # SHA ("a" * 64) sorts below SHA_B ("b" * 64) -> dropped first.
        self.assertEqual(set(tables), {SHA_B})

    def test_default_limit(self):
        tables = {"%064x" % i: _entry(pid=i + 1)
                  for i in range(ATTACH_ENTRIES_LIMIT + 5)}
        evict_oldest(tables)
        self.assertEqual(len(tables), ATTACH_ENTRIES_LIMIT)


class AttachStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.store = AttachStore(self.temporary.name)

    def test_absent_document_is_empty(self):
        self.assertEqual(self.store.document(),
                         {"schema": ATTACH_SCHEMA, "tables": {}})
        self.assertIsNone(self.store.get(SHA))
        self.assertFalse(self.store.has(SHA))

    def test_set_get_round_trip(self):
        with patch.object(table_attach, "utc_now", lambda: TS):
            self.store.set_binding(SHA, NAME, 7)
        self.assertEqual(self.store.get(SHA), _entry())
        self.assertTrue(self.store.has(SHA))

    def test_set_replaces(self):
        self.store.set_binding(SHA, NAME, 7)
        self.store.set_binding(SHA, NAME, 9)
        self.assertEqual(self.store.get(SHA)["pid"], 9)

    def test_clear_binding(self):
        self.store.set_binding(SHA, NAME, 7)
        self.assertTrue(self.store.clear_binding(SHA))
        self.assertFalse(self.store.has(SHA))

    def test_clear_binding_missing_key(self):
        self.assertFalse(self.store.clear_binding(SHA))

    def test_malformed_key_refused(self):
        with self.assertRaises(AttachRefusal):
            self.store.set_binding("nope", NAME, 7)

    def test_out_of_bounds_refused(self):
        with self.assertRaises(AttachRefusal):
            self.store.set_binding(SHA, "", 7)
        with self.assertRaises(AttachRefusal):
            self.store.set_binding(SHA, NAME, 0)

    def test_eviction_over_limit(self):
        for i in range(ATTACH_ENTRIES_LIMIT + 3):
            sha = "%064x" % i
            self.store.set_binding(
                sha, NAME, i + 1)
        self.assertEqual(len(self.store.document()["tables"]),
                         ATTACH_ENTRIES_LIMIT)

    def test_clear_resets(self):
        self.store.set_binding(SHA, NAME, 7)
        self.store.clear()
        self.assertFalse(self.store.has(SHA))

    def test_persists_to_disk(self):
        with patch.object(table_attach, "utc_now", lambda: TS):
            self.store.set_binding(SHA, NAME, 7)
        other = AttachStore(self.temporary.name)
        self.assertEqual(other.get(SHA), _entry())

    def test_refused_document_is_empty(self):
        self.store.path.write_bytes(b"corrupt")
        self.assertEqual(self.store.document(),
                         {"schema": ATTACH_SCHEMA, "tables": {}})


def _cand(name, pid):
    return ProcessSnapshotEntry(pid, name)


class BindingTargetTests(unittest.TestCase):
    def test_none_binding(self):
        self.assertIsNone(binding_target(None, [_cand(NAME, 7)]))

    def test_no_candidates(self):
        self.assertIsNone(binding_target(_entry(), ()))

    def test_honours_live_matching_pid(self):
        cands = (_cand(NAME, 7), _cand(NAME, 9))
        self.assertIs(binding_target(_entry(pid=9), cands), cands[1])

    def test_case_insensitive_name(self):
        cands = (_cand("gamea.EXE", 7),)
        # names_match is case-insensitive; the stored NAME still matches.
        self.assertIsNotNone(binding_target(_entry(pid=7), cands))

    def test_stale_pid(self):
        cands = (_cand(NAME, 9),)
        self.assertIsNone(binding_target(_entry(pid=7), cands))

    def test_pid_reused_by_other_name(self):
        # The same PID now belongs to a different process name: the
        # binding must not honour it (name no longer matches).
        cands = (_cand("Other.exe", 7),)
        self.assertIsNone(binding_target(_entry(pid=7), cands))

    def test_malformed_binding(self):
        cands = (_cand(NAME, 7),)
        self.assertIsNone(binding_target({"process": NAME, "pid": "7"},
                                         cands))
        self.assertIsNone(binding_target({"process": 7, "pid": 7}, cands))
        self.assertIsNone(binding_target({}, cands))


class DetailsLinesTests(unittest.TestCase):
    def test_none(self):
        self.assertEqual(details_attach_lines(None),
                         [("Remembered process", "none")])

    def test_bound(self):
        self.assertEqual(details_attach_lines(_entry()),
                         [("Remembered process", "GameA.exe (PID 7)")])


class NamesMatchSanityTests(unittest.TestCase):
    def test_matches_case_insensitively(self):
        self.assertTrue(names_match("GameA.exe", "gamea.EXE"))

    def test_mismatch(self):
        self.assertFalse(names_match("GameA.exe", "GameB.exe"))


if __name__ == "__main__":
    unittest.main()
