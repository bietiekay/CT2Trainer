"""Master Trainer 0.35: per-table notes / tags (MT-27).

Covers the new pure ``table_notes`` layer (the ``parse_tags``
comma-string parser with its dedupe / length / count rules, the
``note_entry`` builder, the persisted ``table-notes.json`` document
with its schema-1 discipline - strict key sets, the checksummed
envelope, the 1024-entry LRU bound, load-refused-treated-as-absent),
the Note-column / details-window text helpers, and the MT-27
extension of the pure waiting-view filter (note text and tags join
the match surface, backward-compatible when no lookup is passed).

The Tk wiring tests cover the waiting-view Note column, the row
context menu ("Edit note..." between load and pin), the note editor
Toplevel (prefill, save persistence + re-render, cancel, the
named refusal inside the dialog for an over-limit note, the
no-content-sha refusal in the status line), and the note / tag rows
of the MT-22 details window.  No real process is attached (a
_FakeLister stands in).
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

try:
    import tkinter as tk
except ImportError:  # pragma: no cover - environment without Tcl/Tk
    tk = None

from test_native_master_ui import (CT_GAMEA, _all_widgets, _make_app)

from native_tk_teardown import force_root_release

from ct2trainer.native.master_trainer.table_filter import filter_tables
from ct2trainer.native.master_trainer.table_index import TableEntry
from ct2trainer.native.master_trainer.table_notes import (
    NOTE_COLUMN_MAX,
    NOTE_MAX_LEN,
    NOTES_DOC_NAME,
    NOTES_ENTRIES_LIMIT,
    NOTES_SCHEMA,
    TAG_MAX_LEN,
    TAGS_LIMIT,
    NotesRefusal,
    NotesStore,
    details_note_lines,
    evict_oldest,
    load_notes_document,
    note_column_text,
    note_entry,
    notes_document_from_bytes,
    notes_document_to_bytes,
    parse_tags,
    save_notes_document,
    sha256_key_ok,
)
from ct2trainer.native.master_trainer.master_ui import MasterWindow


def _sha(i: int) -> str:
    """A deterministic 64-char lowercase hex key for test ``i``."""
    return hashlib.sha256(("notes-table-%d" % i).encode("utf-8")).hexdigest()


def _entry(note="", tags=(), at="2026-11-09T00:00:00Z"):
    return {"note": note, "tags": list(tags), "updated_at": at}


def _doc(tables):
    return {"schema": NOTES_SCHEMA, "tables": dict(tables)}


def _table_entries(rel, sha, status="ok", detail=None):
    """Duck-typed entries for the pure filter tests."""
    return [
        TableEntry(rel, 10, 0, sha, ("GameA.exe",), status, detail),
    ]


# ---------------------------------------------------------------------
# parse_tags
# ---------------------------------------------------------------------


class ParseTagsTests(unittest.TestCase):
    """MT-27 (0.35): the editor's comma-separated tag string parser."""

    def test_split_strip_and_order(self):
        self.assertEqual(parse_tags("  alpha , beta ,, gamma "),
                         ["alpha", "beta", "gamma"])

    def test_empty_input_is_an_empty_list(self):
        self.assertEqual(parse_tags(""), [])
        self.assertEqual(parse_tags(" , , "), [])
        self.assertEqual(parse_tags(None), [])

    def test_duplicates_are_casefold_deduped_first_spelling_wins(self):
        self.assertEqual(parse_tags("Alpha, alpha, ALPHA, beta"),
                         ["Alpha", "beta"])

    def test_the_limit_caps_the_list_first_seen_wins(self):
        tags = ", ".join("tag-%d" % i for i in range(10))
        self.assertEqual(parse_tags(tags),
                         ["tag-%d" % i for i in range(TAGS_LIMIT)])

    def test_an_over_long_tag_is_a_named_refusal(self):
        long = "x" * (TAG_MAX_LEN + 1)
        with self.assertRaises(NotesRefusal) as ctx:
            parse_tags("ok," + long)
        self.assertIn("exceeds", str(ctx.exception))
        self.assertIn(str(TAG_MAX_LEN), str(ctx.exception))

    def test_a_tag_at_the_limit_is_accepted(self):
        ok = "y" * TAG_MAX_LEN
        self.assertEqual(parse_tags(ok), [ok])

    def test_a_non_string_is_a_named_refusal(self):
        with self.assertRaises(NotesRefusal):
            parse_tags(["alpha"])


# ---------------------------------------------------------------------
# note_entry
# ---------------------------------------------------------------------


class NoteEntryTests(unittest.TestCase):
    """MT-27 (0.35): the persisted per-table notes entry builder."""

    def test_the_entry_shape(self):
        entry = note_entry("hello", ["a", "b"], "2026-11-09T00:00:00Z")
        self.assertEqual(entry, {"note": "hello", "tags": ["a", "b"],
                                 "updated_at": "2026-11-09T00:00:00Z"})

    def test_an_empty_note_and_no_tags_is_valid(self):
        entry = note_entry("", [], "2026-11-09T00:00:00Z")
        self.assertEqual(entry, {"note": "", "tags": [],
                                 "updated_at": "2026-11-09T00:00:00Z"})

    def test_a_note_at_the_limit_is_accepted(self):
        entry = note_entry("z" * NOTE_MAX_LEN, [], "2026-11-09T00:00:00Z")
        self.assertEqual(len(entry["note"]), NOTE_MAX_LEN)

    def test_an_over_long_note_is_a_named_refusal(self):
        with self.assertRaises(NotesRefusal) as ctx:
            note_entry("x" * (NOTE_MAX_LEN + 1), [],
                       "2026-11-09T00:00:00Z")
        self.assertIn("note exceeds", str(ctx.exception))

    def test_too_many_tags_are_a_named_refusal(self):
        with self.assertRaises(NotesRefusal) as ctx:
            note_entry("n", ["t"] * (TAGS_LIMIT + 1),
                       "2026-11-09T00:00:00Z")
        self.assertIn("tags exceed", str(ctx.exception))

    def test_an_empty_tag_is_a_named_refusal(self):
        with self.assertRaises(NotesRefusal):
            note_entry("n", ["", "ok"], "2026-11-09T00:00:00Z")

    def test_a_non_string_note_is_a_named_refusal(self):
        with self.assertRaises(NotesRefusal):
            note_entry(None, [], "2026-11-09T00:00:00Z")


# ---------------------------------------------------------------------
# document bytes / validation
# ---------------------------------------------------------------------


class NotesDocumentTests(unittest.TestCase):
    """MT-27 (0.35): the table-notes.json schema-1 discipline."""

    def test_the_round_trip(self):
        doc = _doc({_sha(1): _entry("note one", ["a", "b"])})
        payload = notes_document_from_bytes(notes_document_to_bytes(doc))
        self.assertEqual(payload, doc)

    def test_the_envelope_is_canonical_and_checksummed(self):
        doc = _doc({_sha(1): _entry("note one", ["a"])})
        raw = notes_document_to_bytes(doc)
        self.assertEqual(raw, notes_document_to_bytes(dict(doc)))
        self.assertTrue(raw.endswith(b"\n"))
        env = json.loads(raw.decode("utf-8"))
        self.assertEqual(set(env), {"payload", "sha256"})
        canonical = json.dumps(doc, sort_keys=True,
                               separators=(",", ":"),
                               ensure_ascii=True).encode("utf-8")
        self.assertEqual(hashlib.sha256(canonical).hexdigest(),
                         env["sha256"])

    def test_a_tampered_checksum_is_refused(self):
        doc = _doc({_sha(1): _entry("note one")})
        payload = json.dumps(doc, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")
        env = json.dumps({"payload": doc, "sha256": "0" * 64},
                         sort_keys=True, separators=(",", ":")).encode()
        with self.assertRaises(NotesRefusal) as ctx:
            notes_document_from_bytes(env)
        self.assertIn("checksum", str(ctx.exception))
        # The canonical re-serialization proves the mismatch is real.
        self.assertNotEqual(hashlib.sha256(payload).hexdigest(), "0" * 64)

    def test_invalid_json_is_refused(self):
        with self.assertRaises(NotesRefusal) as ctx:
            notes_document_from_bytes(b"not json")
        self.assertIn("not valid JSON", str(ctx.exception))

    def test_a_document_with_extra_fields_is_refused(self):
        doc = _doc({})
        doc["extra"] = 1
        with self.assertRaises(NotesRefusal) as ctx:
            notes_document_to_bytes(doc)
        self.assertIn("fields mismatch", str(ctx.exception))

    def test_an_unknown_schema_is_refused(self):
        doc = {"schema": 99, "tables": {}}
        payload = json.dumps(doc, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")
        env = json.dumps({"payload": doc,
                          "sha256": hashlib.sha256(payload).hexdigest()},
                         sort_keys=True, separators=(",", ":")).encode()
        with self.assertRaises(NotesRefusal) as ctx:
            notes_document_from_bytes(env)
        self.assertIn("schema", str(ctx.exception))

    def test_a_non_sha_table_key_is_refused(self):
        with self.assertRaises(NotesRefusal) as ctx:
            notes_document_to_bytes(
                {"schema": NOTES_SCHEMA,
                 "tables": {"not-a-sha": _entry()}})
        self.assertIn("not a sha256", str(ctx.exception))

    def test_an_entry_with_unknown_fields_is_refused(self):
        entry = _entry("n")
        entry["bogus"] = True
        with self.assertRaises(NotesRefusal) as ctx:
            notes_document_to_bytes(_doc({_sha(1): entry}))
        self.assertIn("unknown fields", str(ctx.exception))

    def test_an_invalid_timestamp_is_refused(self):
        with self.assertRaises(NotesRefusal) as ctx:
            notes_document_to_bytes(
                _doc({_sha(1): _entry(at="yesterday")}))
        self.assertIn("updated_at", str(ctx.exception))

    def test_an_over_limit_document_is_refused(self):
        tables = {_sha(i): _entry() for i in range(NOTES_ENTRIES_LIMIT + 1)}
        with self.assertRaises(NotesRefusal) as ctx:
            notes_document_to_bytes(_doc(tables))
        self.assertIn("limit", str(ctx.exception))

    def test_an_entry_at_the_document_limit_is_accepted(self):
        tables = {_sha(i): _entry()
                  for i in range(NOTES_ENTRIES_LIMIT)}
        doc = _doc(tables)
        payload = notes_document_from_bytes(notes_document_to_bytes(doc))
        self.assertEqual(len(payload["tables"]), NOTES_ENTRIES_LIMIT)


# ---------------------------------------------------------------------
# evict_oldest + NotesStore
# ---------------------------------------------------------------------


class EvictOldestTests(unittest.TestCase):
    """MT-27 (0.35): the deterministic LRU bound."""

    def test_the_oldest_by_updated_at_is_dropped(self):
        tables = {
            _sha(1): _entry(at="2026-11-09T01:00:00Z"),
            _sha(2): _entry(at="2026-11-09T00:00:00Z"),
            _sha(3): _entry(at="2026-11-09T02:00:00Z"),
            _sha(4): _entry(at="2026-11-09T03:00:00Z"),
        }
        evict_oldest(tables, limit=3)
        # _sha(2) was the oldest (00:00) and is dropped.
        self.assertEqual(sorted(tables),
                         sorted((_sha(1), _sha(3), _sha(4))))

    def test_ties_are_broken_by_the_sha_key(self):
        # All three entries share the timestamp; evicting to one
        # drops the two smallest keys and keeps the largest.
        tables = {
            _sha(2): _entry(at="2026-11-09T00:00:00Z"),
            _sha(1): _entry(at="2026-11-09T00:00:00Z"),
            _sha(3): _entry(at="2026-11-09T00:00:00Z"),
        }
        evict_oldest(tables, limit=1)
        self.assertEqual(list(tables), [max(_sha(1), _sha(2), _sha(3))])

    def test_no_eviction_below_the_limit(self):
        tables = {_sha(1): _entry()}
        self.assertIs(evict_oldest(tables, limit=4), tables)


class NotesStoreTests(unittest.TestCase):
    """MT-27 (0.35): the persistent per-sha notes store."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.store = NotesStore(self.home)

    def test_an_absent_document_is_the_empty_state(self):
        self.assertEqual(self.store.document(),
                         {"schema": NOTES_SCHEMA, "tables": {}})
        self.assertIsNone(self.store.get(_sha(1)))
        self.assertFalse(self.store.has(_sha(1)))

    def test_set_and_get_round_trip(self):
        self.store.set_note(_sha(1), "my note", ["tag-a", "tag-b"])
        got = self.store.get(_sha(1))
        self.assertEqual(got["note"], "my note")
        self.assertEqual(got["tags"], ["tag-a", "tag-b"])
        self.assertTrue((self.home / NOTES_DOC_NAME).is_file())
        # The persisted entry carries a valid timestamp.
        self.assertTrue(
            len(got["updated_at"]) == 20
            and got["updated_at"].endswith("Z"))

    def test_set_replaces_an_existing_entry(self):
        self.store.set_note(_sha(1), "first", ["a"])
        self.store.set_note(_sha(1), "second", [])
        got = self.store.get(_sha(1))
        self.assertEqual(got["note"], "second")
        self.assertEqual(got["tags"], [])
        self.assertEqual(len(self.store.document()["tables"]), 1)

    def test_a_malformed_key_is_a_refusal(self):
        with self.assertRaises(NotesRefusal) as ctx:
            self.store.set_note("short", "n", [])
        self.assertIn("sha256", str(ctx.exception))

    def test_an_over_limit_note_is_refused_and_not_persisted(self):
        with self.assertRaises(NotesRefusal):
            self.store.set_note(_sha(1), "x" * (NOTE_MAX_LEN + 1), [])
        self.assertIsNone(self.store.get(_sha(1)))

    def test_set_note_evicts_over_the_limit(self):
        tables = {_sha(i): _entry(at="2000-01-01T00:00:00Z")
                  for i in range(NOTES_ENTRIES_LIMIT)}
        save_notes_document(_doc(tables), self.store.path)
        self.store.set_note(_sha(424242), "new", [])
        doc = self.store.document()
        self.assertEqual(len(doc["tables"]), NOTES_ENTRIES_LIMIT)
        # The oldest entry (all the seeded ones tie, so the min key)
        # is evicted, the new entry survives.
        self.assertNotIn(min(tables), doc["tables"])
        self.assertIn(_sha(424242), doc["tables"])
        self.assertEqual(doc["tables"][_sha(424242)]["note"], "new")

    def test_clear_note_removes_a_single_entry(self):
        self.store.set_note(_sha(1), "n", [])
        self.store.set_note(_sha(2), "n", [])
        self.assertTrue(self.store.clear_note(_sha(1)))
        self.assertIsNone(self.store.get(_sha(1)))
        self.assertIsNotNone(self.store.get(_sha(2)))
        self.assertFalse(self.store.clear_note(_sha(1)))
        self.assertFalse(self.store.clear_note("not-a-sha"))
        self.assertIsNotNone(self.store.get(_sha(2)))

    def test_clear_resets_the_document(self):
        self.store.set_note(_sha(1), "n", [])
        self.store.clear()
        self.assertEqual(self.store.document(),
                         {"schema": NOTES_SCHEMA, "tables": {}})

    def test_a_refused_document_is_treated_as_absent(self):
        (self.home / NOTES_DOC_NAME).write_text("garbage",
                                                encoding="utf-8")
        self.assertEqual(self.store.document(),
                         {"schema": NOTES_SCHEMA, "tables": {}})
        self.assertIsNone(self.store.get(_sha(1)))
        # A refused document never breaks the next save.
        self.store.set_note(_sha(1), "n", [])
        self.assertEqual(self.store.get(_sha(1))["note"], "n")


# ---------------------------------------------------------------------
# column / details text helpers
# ---------------------------------------------------------------------


class NoteColumnTextTests(unittest.TestCase):
    """MT-27 (0.35): the waiting-view Note column text."""

    def test_none_is_empty(self):
        self.assertEqual(note_column_text(None), "")

    def test_note_only(self):
        self.assertEqual(note_column_text(_entry("hello")), "hello")

    def test_tags_only_render_the_bracketed_tags(self):
        self.assertEqual(note_column_text(_entry("", ["a", "b"])),
                         "[a, b]")

    def test_note_and_tags_join_with_a_space(self):
        self.assertEqual(note_column_text(_entry("hello", ["a"])),
                         "hello [a]")

    def test_newlines_are_folded_to_single_spaces(self):
        out = note_column_text(_entry("line one\nline two"))
        self.assertEqual(out, "line one line two")
        self.assertNotIn("\n", out)

    def test_the_note_is_truncated_to_the_column_limit(self):
        out = note_column_text(_entry("x" * 100))
        self.assertTrue(out.endswith("\u2026"))
        self.assertLessEqual(len(out), NOTE_COLUMN_MAX)

    def test_the_note_is_truncated_to_make_room_for_the_tags(self):
        tags = ["a" * TAG_MAX_LEN, "b" * TAG_MAX_LEN]
        suffix = "[" + ", ".join(tags) + "]"
        out = note_column_text(_entry("x" * 100, tags))
        self.assertTrue(out.endswith(suffix))
        # The note is truncated to zero width, leaving only the
        # ellipsis before the (space-separated) tag suffix.
        self.assertTrue(out.endswith("\u2026 " + suffix))


class DetailsNoteLinesTests(unittest.TestCase):
    """MT-27 (0.35): the details-window note / tag rows."""

    def test_none_gives_the_none_placeholders(self):
        self.assertEqual(details_note_lines(None),
                         [("Note", "none"), ("Tags", "none")])

    def test_note_and_tags_render_both_rows(self):
        lines = details_note_lines(_entry("hello", ["a", "b"]))
        self.assertEqual(lines,
                         [("Note", "hello"), ("Tags", "a, b")])

    def test_an_empty_note_shows_none_but_the_tags_render(self):
        lines = details_note_lines(_entry("", ["a"]))
        self.assertEqual(lines, [("Note", "none"), ("Tags", "a")])

    def test_a_note_without_tags_renders_tags_none(self):
        lines = details_note_lines(_entry("hello"))
        self.assertEqual(lines, [("Note", "hello"), ("Tags", "none")])


# ---------------------------------------------------------------------
# filter_tables extension
# ---------------------------------------------------------------------


class FilterTablesNotesTests(unittest.TestCase):
    """MT-27 (0.35): the note / tag match surface of the filter."""

    def test_note_lookup_is_optional_and_backward_compatible(self):
        entries = _table_entries("a.ct", _sha(1))
        self.assertEqual(filter_tables(entries, "a.ct"), entries)
        self.assertEqual(filter_tables(entries, "a.ct", note_lookup={}),
                         entries)
        # An empty query is the identity, lookup or not.
        self.assertEqual(filter_tables(entries, "   ",
                                       note_lookup={_sha(1):
                                                    _entry("x")}),
                         entries)

    def test_the_note_text_joins_the_match_surface(self):
        entries = _table_entries("a.ct", _sha(1))
        lookup = {_sha(1): _entry("the special save helper")}
        hit = filter_tables(entries, "special", note_lookup=lookup)
        self.assertEqual(hit, entries)
        self.assertEqual(
            filter_tables(entries, "zzz-not-present",
                          note_lookup=lookup), [])

    def test_the_matching_is_casefolded(self):
        entries = _table_entries("a.ct", _sha(1))
        lookup = {_sha(1): _entry("The Special Note")}
        self.assertEqual(filter_tables(entries, "sPeCiAl",
                                       note_lookup=lookup), entries)

    def test_the_tags_join_the_match_surface(self):
        entries = _table_entries("a.ct", _sha(1))
        lookup = {_sha(1): _entry("", ["combat", "spoilers"])}
        self.assertEqual(filter_tables(entries, "combat",
                                       note_lookup=lookup), entries)
        self.assertEqual(filter_tables(entries, "spoiler",
                                       note_lookup=lookup), entries)
        self.assertEqual(filter_tables(entries, "zzz",
                                       note_lookup=lookup), [])

    def test_the_name_match_still_works_without_a_lookup(self):
        entries = _table_entries("a.ct", _sha(1))
        lookup = {_sha(1): _entry("", ["combat"])}
        self.assertEqual(filter_tables(entries, "a.ct",
                                       note_lookup=lookup), entries)
        self.assertEqual(
            filter_tables(entries, "gamea.exe", note_lookup=lookup),
            entries)

    def test_an_entry_without_a_content_sha_never_note_matches(self):
        entries = _table_entries("bad.ct", "", status="unreadable",
                                 detail="read failed: simulated")
        lookup = {"0" * 64: _entry("special")}
        self.assertEqual(filter_tables(entries, "special",
                                       note_lookup=lookup), [])
        self.assertEqual(filter_tables(entries, "bad",
                                       note_lookup=lookup), entries)


# ---------------------------------------------------------------------
# Tk wiring
# ---------------------------------------------------------------------


def _plan(sha: str) -> dict:
    return {"schema": 2, "table_sha256": sha, "entries": [
        {"id": 1, "supported": True, "kind": "value", "reason": ""},
    ]}


@unittest.skipIf(tk is None, "tkinter not available")
class _NotesUiBase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.folder = root / "tables"
        self.folder.mkdir()
        self.state_home = root / "state"
        self.state_home.mkdir()
        (self.folder / "a.ct").write_text(CT_GAMEA, encoding="utf-8")
        self.root = tk.Tk()
        self.addCleanup(force_root_release, [self.root],
                        ((self, "root"), (self, "window"), (self, "app")))

    def _app(self):
        return _make_app(self.folder, self.state_home)

    def _window(self, app):
        self.window = MasterWindow(self.root, app)
        self.app = app
        return self.window

    def _row_values(self, rel):
        tree = self.window._table_tree
        for child in tree.get_children():
            values = tree.item(child, "values")
            if values and values[0] == rel:
                return list(values)
        self.fail("row for " + rel + " not found in the table tree")

    def _toplevels(self, title=None):
        out = []
        for child in self.root.winfo_children():
            if isinstance(child, tk.Toplevel) \
                    and (title is None or child.title() == title):
                out.append(child)
        return out

    def _destroy_toplevels(self):
        for top in self._toplevels():
            top.destroy()


@unittest.skipIf(tk is None, "tkinter not available")
class NoteColumnUiTests(_NotesUiBase):
    """MT-27 (0.35): the waiting-view Note column."""

    def setUp(self):
        super().setUp()
        self.addCleanup(self._destroy_toplevels)

    def test_the_note_column_is_present_and_empty_without_a_note(self):
        window = self._window(self._app())
        tree = window._table_tree
        self.assertEqual(list(tree["columns"])[-1], "note")
        self.assertEqual(tree.heading("note")["text"], "Note")
        values = self._row_values("a.ct")
        self.assertEqual(len(values), 11)
        self.assertEqual(values[10], "")

    def test_a_saved_note_shows_in_the_column_and_the_filter(self):
        app = self._app()
        window = self._window(app)
        sha = app.index.get("a.ct").sha256
        app.notes_store.set_note(sha, "the special save helper",
                                 ["combat", "spoilers"])
        window._render_tables()
        values = self._row_values("a.ct")
        self.assertEqual(values[10],
                         "the special save helper [combat, spoilers]")
        # The note text and a tag are part of the match surface.
        window._filter_query = "special"
        window._render_tables()
        self.assertEqual(len(window._table_tree.get_children()), 1)
        self.assertEqual(self._row_values("a.ct")[0], "a.ct")
        window._filter_query = "spoilers"
        window._render_tables()
        self.assertEqual(len(window._table_tree.get_children()), 1)
        window._filter_query = "zzz-not-present"
        window._render_tables()
        self.assertEqual(len(window._table_tree.get_children()), 0)


@unittest.skipIf(tk is None, "tkinter not available")
class NoteEditorUiTests(_NotesUiBase):
    """MT-27 (0.35): the row menu + the note editor Toplevel."""

    def setUp(self):
        super().setUp()
        self.addCleanup(self._destroy_toplevels)

    def test_the_row_menu_offers_edit_note_between_load_and_pin(self):
        app = self._app()
        window = self._window(app)
        item = window._table_tree.get_children()[0]
        created = []

        class Rec(tk.Menu):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.commands = []

            def add_command(self, label="", command=None, **kwargs):
                self.commands.append(label)
                return super().add_command(label=label, command=command,
                                           **kwargs)

            def tk_popup(self, *args, **kwargs):
                pass

        def factory(*args, **kwargs):
            menu = Rec(*args, **kwargs)
            created.append(menu)
            return menu

        with patch("tkinter.Menu", factory), \
                patch.object(window._table_tree, "identify_row",
                             return_value=item):
            window._table_context_menu(
                MagicMock(y=0, x_root=0, y_root=0))
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].commands,
                         ["Table details", "Load this table",
                          "Edit note\u2026", "Pin to top"])

    def test_a_table_without_a_content_sha_is_a_named_refusal(self):
        app = self._app()
        window = self._window(app)
        # An unreadable entry the scanner could not hash.
        bad = TableEntry("bad.ct", 0, 0, "", (), "unreadable",
                         "read failed: simulated", root=app.folder)
        app.index.indexes[0].entries["bad.ct"] = bad
        window._open_note_editor("bad.ct")
        self.assertIsNone(window._note_editor_win)
        self.assertEqual(len(self._toplevels()), 0)
        self.assertIn("no content sha for bad.ct",
                      window._status_var.get())

    def test_a_missing_index_entry_is_a_named_refusal(self):
        app = self._app()
        window = self._window(app)
        window._open_note_editor("missing.ct")
        self.assertIsNone(window._note_editor_win)
        self.assertIn("No index entry for missing.ct",
                      window._status_var.get())

    def test_the_editor_prefills_the_stored_note_and_tags(self):
        app = self._app()
        window = self._window(app)
        sha = app.index.get("a.ct").sha256
        app.notes_store.set_note(sha, "stored note", ["alpha", "beta"])
        window._open_note_editor("a.ct")
        win = window._note_editor_win
        self.assertIsNotNone(win)
        self.assertEqual(win.title(), "Edit note - a.ct")
        note_box = [w for w in _all_widgets(win)
                    if isinstance(w, tk.Text)][0]
        tag_entry = [w for w in _all_widgets(win)
                     if isinstance(w, tk.Entry)][0]
        self.assertEqual(note_box.get("1.0", "end"),
                         "stored note\n")
        self.assertEqual(tag_entry.get(), "alpha, beta")
        win.destroy()
        window._note_editor_win = None

    def test_save_persists_the_note_and_tags_and_renders(self):
        app = self._app()
        window = self._window(app)
        sha = app.index.get("a.ct").sha256
        window._open_note_editor("a.ct")
        win = window._note_editor_win
        note_box = [w for w in _all_widgets(win)
                    if isinstance(w, tk.Text)][0]
        note_box.insert("1.0", "my note")
        tag_entry = [w for w in _all_widgets(win)
                     if isinstance(w, tk.Entry)][0]
        tag_entry.insert(0, "tag-a, tag-b, tag-a")
        buttons = {str(w.cget("text")): w
                   for w in _all_widgets(win)
                   if isinstance(w, tk.Button)}
        buttons["Save"].invoke()
        self.assertFalse(win.winfo_exists())
        self.assertIsNone(window._note_editor_win)
        got = app.notes_store.get(sha)
        self.assertEqual(got["note"], "my note")
        self.assertEqual(got["tags"], ["tag-a", "tag-b"])
        self.assertIn("Note saved for a.ct",
                      window._status_var.get())
        # The waiting view re-rendered with the new Note cell.
        values = self._row_values("a.ct")
        self.assertEqual(values[10], "my note [tag-a, tag-b]")

    def test_an_over_limit_note_is_refused_inside_the_dialog(self):
        app = self._app()
        window = self._window(app)
        sha = app.index.get("a.ct").sha256
        window._open_note_editor("a.ct")
        win = window._note_editor_win
        note_box = [w for w in _all_widgets(win)
                    if isinstance(w, tk.Text)][0]
        note_box.insert("1.0", "x" * (NOTE_MAX_LEN + 1))
        buttons = {str(w.cget("text")): w
                   for w in _all_widgets(win)
                   if isinstance(w, tk.Button)}
        buttons["Save"].invoke()
        # The dialog stays open and names the refusal; nothing is
        # persisted.
        self.assertTrue(win.winfo_exists())
        labels = [str(w.cget("text"))
                  for w in _all_widgets(win)
                  if isinstance(w, tk.Label)]
        self.assertTrue(any("note exceeds" in text for text in labels))
        self.assertIsNone(app.notes_store.get(sha))

    def test_an_over_long_tag_is_refused_inside_the_dialog(self):
        app = self._app()
        window = self._window(app)
        sha = app.index.get("a.ct").sha256
        window._open_note_editor("a.ct")
        win = window._note_editor_win
        tag_entry = [w for w in _all_widgets(win)
                     if isinstance(w, tk.Entry)][0]
        tag_entry.insert(0, "x" * (TAG_MAX_LEN + 1))
        buttons = {str(w.cget("text")): w
                   for w in _all_widgets(win)
                   if isinstance(w, tk.Button)}
        buttons["Save"].invoke()
        self.assertTrue(win.winfo_exists())
        labels = [str(w.cget("text"))
                  for w in _all_widgets(win)
                  if isinstance(w, tk.Label)]
        self.assertTrue(any("exceeds" in text and str(TAG_MAX_LEN) in text
                            for text in labels))
        self.assertIsNone(app.notes_store.get(sha))

    def test_cancel_closes_without_persisting(self):
        app = self._app()
        window = self._window(app)
        sha = app.index.get("a.ct").sha256
        window._open_note_editor("a.ct")
        win = window._note_editor_win
        note_box = [w for w in _all_widgets(win)
                    if isinstance(w, tk.Text)][0]
        note_box.insert("1.0", "discarded")
        buttons = {str(w.cget("text")): w
                   for w in _all_widgets(win)
                   if isinstance(w, tk.Button)}
        buttons["Cancel"].invoke()
        self.assertFalse(win.winfo_exists())
        self.assertIsNone(window._note_editor_win)
        self.assertIsNone(app.notes_store.get(sha))
        self.assertIn("Note edit cancelled for a.ct",
                      window._status_var.get())

    def test_a_second_open_lifts_the_window(self):
        app = self._app()
        window = self._window(app)
        window._open_note_editor("a.ct")
        first = window._note_editor_win
        window._open_note_editor("a.ct")
        self.assertIs(first, window._note_editor_win)
        first.destroy()
        window._note_editor_win = None


@unittest.skipIf(tk is None, "tkinter not available")
class NoteDetailsUiTests(_NotesUiBase):
    """MT-27 (0.35): the note / tag rows of the details window."""

    def setUp(self):
        super().setUp()
        self.addCleanup(self._destroy_toplevels)

    def _value_rows(self, win):
        labels = [w for w in _all_widgets(win) if isinstance(w, tk.Label)]
        return [str(w.cget("text"))
                for w in labels if w.cget("wraplength") == 520]

    def test_the_details_window_shows_the_note_and_tags(self):
        app = self._app()
        window = self._window(app)
        sha = app.index.get("a.ct").sha256
        app.notes_store.set_note(sha, "the details note",
                                 ["combat", "spoilers"])
        window._open_table_details("a.ct")
        win = window._details_win
        self.assertIsNotNone(win)
        self.addCleanup(win.destroy)
        values = self._value_rows(win)
        # MT-28 (0.37): the "Remembered process" row follows the
        # note / tag rows (no binding in this test -> "none").
        self.assertEqual(values[-3], "the details note")
        self.assertEqual(values[-2], "combat, spoilers")
        self.assertEqual(values[-1], "none")

    def test_the_details_window_shows_the_none_placeholders(self):
        app = self._app()
        window = self._window(app)
        window._open_table_details("a.ct")
        win = window._details_win
        self.assertIsNotNone(win)
        self.addCleanup(win.destroy)
        values = self._value_rows(win)
        # MT-28 (0.37): three trailing "none" rows - note, tags,
        # remembered process.
        self.assertEqual(values[-3], "none")
        self.assertEqual(values[-2], "none")
        self.assertEqual(values[-1], "none")


if __name__ == "__main__":
    unittest.main()
