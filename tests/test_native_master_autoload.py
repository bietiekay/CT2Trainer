"""Master Trainer 0.39: per-table auto-load policy (MT-29).

Covers the new pure ``table_autoload`` layer: the ``autoload_entry``
builder (strict key set, the documented policy set), the persisted
``table-autoload.json`` document with its schema-1 discipline (strict
key sets, the checksummed envelope, the 1024-entry LRU bound,
load-refused-treated-as-absent), the :class:`AutoLoadStore` (the
documented default ``auto`` is the ABSENCE of an entry - setting it
drops a persisted manual-only entry; ``policy`` resolves the
effective policy), the details-window text helper, and the MT-29
extension of the pure waiting-view filter (the persisted policy text
joins the match surface, backward-compatible when no lookup is
passed).  The orchestrator exclusion and the Tk wiring live in
``tests/test_native_master_ui_mt29.py``.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from ct2trainer.native.master_trainer.table_autoload import (
    AUTOLOAD_DOC_NAME,
    AUTOLOAD_ENTRIES_LIMIT,
    AUTOLOAD_MANUAL_ONLY,
    AUTOLOAD_POLICIES,
    AUTOLOAD_SCHEMA,
    AutoLoadRefusal,
    AutoLoadStore,
    autoload_document_from_bytes,
    autoload_document_to_bytes,
    autoload_entry,
    details_autoload_lines,
    evict_oldest,
    load_autoload_document,
    save_autoload_document,
    sha256_key_ok,
)
from ct2trainer.native.master_trainer.table_filter import filter_tables
from ct2trainer.native.master_trainer.table_index import TableEntry


def _sha(i: int) -> str:
    """A deterministic 64-char lowercase hex key for test ``i``."""
    return hashlib.sha256(("autoload-table-%d" % i).encode("utf-8")).hexdigest()


def _entry(policy=AUTOLOAD_MANUAL_ONLY, at="2026-11-10T00:00:00Z"):
    return {"policy": policy, "updated_at": at}


def _doc(tables):
    return {"schema": AUTOLOAD_SCHEMA, "tables": dict(tables)}


def _table_entries(rel, sha, status="ok", detail=None):
    """Duck-typed entries for the pure filter tests."""
    return [
        TableEntry(rel, 10, 0, sha, ("GameA.exe",), status, detail),
    ]


# ---------------------------------------------------------------------
# entry builder
# ---------------------------------------------------------------------


class AutoloadEntryTests(unittest.TestCase):
    """MT-29 (0.39): the persisted entry builder."""

    def test_manual_only_entry_has_the_strict_key_set(self):
        entry = autoload_entry(AUTOLOAD_MANUAL_ONLY, "2026-11-10T00:00:00Z")
        self.assertEqual(entry,
                         {"policy": AUTOLOAD_MANUAL_ONLY,
                          "updated_at": "2026-11-10T00:00:00Z"})

    def test_the_explicit_auto_entry_is_format_legal(self):
        entry = autoload_entry("auto", "2026-11-10T00:00:00Z")
        self.assertEqual(entry["policy"], "auto")

    def test_an_unknown_policy_is_a_named_refusal(self):
        with self.assertRaises(AutoLoadRefusal) as ctx:
            autoload_entry("never", "2026-11-10T00:00:00Z")
        self.assertIn("not one of", str(ctx.exception))
        self.assertIn(AUTOLOAD_MANUAL_ONLY, str(ctx.exception))

    def test_a_non_string_policy_is_a_named_refusal(self):
        with self.assertRaises(AutoLoadRefusal):
            autoload_entry(12, "2026-11-10T00:00:00Z")


# ---------------------------------------------------------------------
# document validation
# ---------------------------------------------------------------------


class AutoloadDocumentTests(unittest.TestCase):
    """MT-29 (0.39): the persisted document discipline."""

    def test_round_trip_is_byte_stable(self):
        doc = {_sha(1): _entry()}
        payload = _doc(doc)
        raw = autoload_document_to_bytes(payload)
        self.assertEqual(raw.endswith(b"\n"), True)
        self.assertEqual(json.loads(raw)["payload"], payload)
        self.assertEqual(autoload_document_from_bytes(raw), payload)

    def test_tampered_payload_fails_the_checksum(self):
        raw = autoload_document_to_bytes(_doc({_sha(1): _entry()}))
        document = json.loads(raw)
        document["payload"]["tables"][_sha(2)] = _entry()
        tampered = json.dumps(document).encode("utf-8")
        with self.assertRaises(AutoLoadRefusal) as ctx:
            autoload_document_from_bytes(tampered)
        self.assertIn("checksum", str(ctx.exception))

    def test_invalid_json_is_a_refusal(self):
        with self.assertRaises(AutoLoadRefusal) as ctx:
            autoload_document_from_bytes(b"not json")
        self.assertIn("not valid JSON", str(ctx.exception))

    def test_a_missing_envelope_field_is_a_refusal(self):
        with self.assertRaises(AutoLoadRefusal):
            autoload_document_from_bytes(
                json.dumps({"payload": _doc({})}).encode("utf-8"))

    def test_an_unknown_schema_is_a_refusal(self):
        doc = {"schema": 2, "tables": {}}
        canonical = json.dumps(doc, sort_keys=True, separators=(",", ":"),
                               allow_nan=False, ensure_ascii=True)
        import hashlib as _h
        envelope = json.dumps(
            {"payload": doc,
             "sha256": _h.sha256(canonical.encode("utf-8")).hexdigest()})
        with self.assertRaises(AutoLoadRefusal) as ctx:
            autoload_document_from_bytes(envelope.encode("utf-8"))
        self.assertIn("unsupported table-autoload schema", str(ctx.exception))

    def test_an_entry_with_an_unknown_field_is_a_refusal(self):
        doc = _doc({_sha(1): {"policy": AUTOLOAD_MANUAL_ONLY,
                              "updated_at": "2026-11-10T00:00:00Z",
                              "extra": 1}})
        with self.assertRaises(AutoLoadRefusal) as ctx:
            autoload_document_to_bytes(doc)
        self.assertIn("unknown fields", str(ctx.exception))

    def test_a_non_sha256_table_key_is_a_refusal(self):
        doc = _doc({"not-a-sha": _entry()})
        with self.assertRaises(AutoLoadRefusal) as ctx:
            autoload_document_to_bytes(doc)
        self.assertIn("not a sha256", str(ctx.exception))

    def test_a_bad_updated_at_is_a_refusal(self):
        doc = _doc({_sha(1): _entry(at="yesterday")})
        with self.assertRaises(AutoLoadRefusal) as ctx:
            autoload_document_to_bytes(doc)
        self.assertIn("invalid updated_at", str(ctx.exception))

    def test_an_invalid_entry_policy_is_a_refusal(self):
        doc = _doc({_sha(1): _entry(policy="never")})
        with self.assertRaises(AutoLoadRefusal) as ctx:
            autoload_document_to_bytes(doc)
        self.assertIn("invalid policy", str(ctx.exception))

    def test_over_the_entry_limit_is_a_refusal(self):
        tables = {_sha(i): _entry() for i in range(AUTOLOAD_ENTRIES_LIMIT + 1)}
        with self.assertRaises(AutoLoadRefusal) as ctx:
            autoload_document_to_bytes(_doc(tables))
        self.assertIn(str(AUTOLOAD_ENTRIES_LIMIT), str(ctx.exception))


class AutoloadFileTests(unittest.TestCase):
    """MT-29 (0.39): the file round trip (absent / refused -> None)."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / AUTOLOAD_DOC_NAME

    def test_absent_file_loads_as_none(self):
        self.assertIsNone(load_autoload_document(self.path))

    def test_refused_document_loads_as_none(self):
        self.path.write_text("garbage", encoding="utf-8")
        self.assertIsNone(load_autoload_document(self.path))

    def test_save_creates_parent_and_round_trips(self):
        nested = Path(self.temporary.name) / "a" / "b" / AUTOLOAD_DOC_NAME
        doc = _doc({_sha(1): _entry()})
        save_autoload_document(doc, nested)
        self.assertEqual(load_autoload_document(nested), doc)


# ---------------------------------------------------------------------
# bounded store
# ---------------------------------------------------------------------


class EvictOldestTests(unittest.TestCase):
    """MT-29 (0.39): the LRU bound (oldest by updated_at, sha tie)."""

    def test_the_oldest_entry_is_evicted(self):
        tables = {
            _sha(1): _entry(at="2026-11-10T00:00:00Z"),
            _sha(2): _entry(at="2026-11-09T00:00:00Z"),
            _sha(3): _entry(at="2026-11-08T00:00:00Z"),
        }
        evict_oldest(tables, limit=2)
        self.assertEqual(set(tables), {_sha(1), _sha(2)})

    def test_ties_are_broken_by_the_sha_key(self):
        at = "2026-11-10T00:00:00Z"
        tables = {_sha(1): _entry(at=at), _sha(2): _entry(at=at)}
        evict_oldest(tables, limit=1)
        # min() over the equal timestamps keeps the lower sha.
        self.assertEqual(set(tables), {_sha(1)})


class AutoLoadStoreTests(unittest.TestCase):
    """MT-29 (0.39): the persistent per-sha policy cache."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.store = AutoLoadStore(self.temporary.name)

    def test_a_fresh_home_is_the_empty_default(self):
        self.assertEqual(self.store.document(),
                         {"schema": AUTOLOAD_SCHEMA, "tables": {}})
        self.assertIsNone(self.store.get(_sha(1)))
        self.assertFalse(self.store.has(_sha(1)))
        self.assertEqual(self.store.policy(_sha(1)), "auto")

    def test_set_manual_only_persists_and_resolves(self):
        self.store.set_policy(_sha(1), AUTOLOAD_MANUAL_ONLY)
        self.assertEqual(self.store.policy(_sha(1)), AUTOLOAD_MANUAL_ONLY)
        other = AutoLoadStore(self.temporary.name)
        self.assertEqual(other.policy(_sha(1)), AUTOLOAD_MANUAL_ONLY)

    def test_setting_auto_drops_the_persisted_entry(self):
        self.store.set_policy(_sha(1), AUTOLOAD_MANUAL_ONLY)
        self.store.set_policy(_sha(1), "auto")
        self.assertIsNone(self.store.get(_sha(1)))
        self.assertEqual(self.store.policy(_sha(1)), "auto")

    def test_a_malformed_key_is_a_named_refusal(self):
        with self.assertRaises(AutoLoadRefusal) as ctx:
            self.store.set_policy("short", AUTOLOAD_MANUAL_ONLY)
        self.assertIn("sha256 key", str(ctx.exception))

    def test_an_unknown_policy_is_a_named_refusal(self):
        with self.assertRaises(AutoLoadRefusal) as ctx:
            self.store.set_policy(_sha(1), "never")
        self.assertIn("not one of", str(ctx.exception))
        self.assertIsNone(self.store.get(_sha(1)))

    def test_clear_policy_drops_the_entry(self):
        self.store.set_policy(_sha(1), AUTOLOAD_MANUAL_ONLY)
        self.assertTrue(self.store.clear_policy(_sha(1)))
        self.assertFalse(self.store.clear_policy(_sha(1)))
        self.assertFalse(self.store.clear_policy("short"))

    def test_the_entry_limit_evicts_the_oldest(self):
        for i in range(AUTOLOAD_ENTRIES_LIMIT + 2):
            self.store.set_policy(_sha(i), AUTOLOAD_MANUAL_ONLY)
        document = self.store.document()
        self.assertEqual(len(document["tables"]), AUTOLOAD_ENTRIES_LIMIT)


# ---------------------------------------------------------------------
# display + filter helpers
# ---------------------------------------------------------------------


class DetailsAutoloadLinesTests(unittest.TestCase):
    """MT-29 (0.39): the MT-22 details-window row."""

    def test_none_is_the_documented_default(self):
        lines = details_autoload_lines(None)
        self.assertEqual(lines, [("Auto-load policy",
                                  "automatic (the documented default)")])

    def test_a_manual_only_entry_shows_the_effective_policy(self):
        lines = details_autoload_lines(_entry())
        self.assertEqual(lines,
                         [("Auto-load policy",
                           "manual only (never auto-loaded; "
                           "load it explicitly)")])

    def test_a_format_legal_auto_entry_resolves_to_the_default(self):
        lines = details_autoload_lines(_entry(policy="auto"))
        self.assertEqual(lines, [("Auto-load policy",
                                  "automatic (the documented default)")])


class FilterAutoloadLookupTests(unittest.TestCase):
    """MT-29 (0.39): the policy text joins the filter match surface."""

    def test_the_manual_only_policy_matches(self):
        tables = {_sha(1): _entry()}
        entries = _table_entries("other-table.ct", _sha(1))
        self.assertEqual(filter_tables(entries, "manual-only",
                                       autoload_lookup=tables), entries)
        self.assertEqual(filter_tables(entries, "manual",
                                       autoload_lookup=tables), entries)

    def test_the_default_policy_carries_no_match_surface(self):
        # "auto" is the ABSENCE of an entry; a manual-only policy
        # string does not contain "auto", so nothing matches.
        tables = {_sha(1): _entry()}
        entries = _table_entries("other-table.ct", _sha(1))
        self.assertEqual(filter_tables(entries, "auto",
                                       autoload_lookup=tables), [])

    def test_none_lookup_is_the_exact_pre_039_behavior(self):
        entries = _table_entries("manual-only-table.ct", _sha(1))
        self.assertEqual(filter_tables(entries, "manual-only"), entries)
        entries2 = _table_entries("other-table.ct", _sha(1))
        self.assertEqual(filter_tables(entries2, "manual-only"), [])

    def test_an_entry_without_a_lookup_entry_keeps_the_old_behavior(self):
        tables = {_sha(1): _entry()}
        entries = _table_entries("other-table.ct", _sha(2))
        self.assertEqual(filter_tables(entries, "manual-only",
                                       autoload_lookup=tables), [])


if __name__ == "__main__":
    unittest.main()
